"""
v6.1 智能扫描器（Smart Screener）

WebSocket 全量 Ticker 流前置过滤 + REST 精准验证
避免 API 权重耗尽和 IP 封禁
"""
import asyncio
import json
import logging
from typing import Dict, List, Optional, Callable, Set
from datetime import datetime

from src.exchange.websocket_pool import BinanceWebSocketClient

logger = logging.getLogger(__name__)


class SmartScreener:
    """
    智能扫描器

    策略：
    1. 订阅币安 WebSocket 全量 Ticker 流（!ticker@arr）
    2. 前置过滤：成交量异动 + 价格波动率
    3. 只有满足条件的币种才发起 REST 请求
    4. 避免暴力并发 30 x 3 = 90 个 REST 请求

    性能优化：
    - WebSocket 长连接（无 HTTP 开销）
    - 前置过滤（减少 90%+ REST 请求）
    - 异步验证（只验证高潜力币种）
    """

    # WebSocket 端点（全量 Ticker 流）
    TICKER_STREAM = "!ticker@arr"

    # 过滤阈值
    MIN_VOLUME_USDT = 10_000_000  # 最小成交量（1000万 USDT）
    MIN_PRICE_CHANGE_PCT = 0.5  # 最小价格波动率（0.5%）

    # 排除币种（稳定币）
    EXCLUDE_SYMBOLS = {
        'USDCUSDT', 'TUSDUSDT', 'BUSDUSDT', 'USDPUSDT',
        'DAIUSDT', 'FRAXUSDT', 'USDNUSDT', 'USDTBUSD',
    }

    def __init__(
        self,
        testnet: bool = False,
        on_signal: Optional[Callable] = None,
        min_volume_usdt: float = 10_000_000,
        min_price_change_pct: float = 0.5,
    ):
        """
        初始化智能扫描器

        Args:
            testnet: 是否测试网
            on_signal: 信号回调
            min_volume_usdt: 最小成交量（USDT）
            min_price_change_pct: 最小价格波动率（%）
        """
        self.testnet = testnet
        self.on_signal = on_signal
        self.min_volume_usdt = min_volume_usdt
        self.min_price_change_pct = min_price_change_pct

        # WebSocket 客户端
        self.ws_client: Optional[BinanceWebSocketClient] = None

        # 运行状态
        self.running = False

        # Ticker 缓存（实时更新）
        self.tickers: Dict[str, dict] = {}

        # 候选币种（满足前置过滤）
        self.candidates: Set[str] = set()

        # 统计信息
        self.ticker_count = 0
        self.rest_request_count = 0
        self.signal_count = 0

        logger.info(f"智能扫描器初始化:")
        logger.info(f"   最小成交量: ${min_volume_usdt:,.0f}")
        logger.info(f"   最小波动率: {min_price_change_pct}%")

    async def start(self) -> None:
        """启动智能扫描器"""
        self.running = True

        logger.info(f"\n{'='*60}")
        logger.info(f"🚀 v6.1 智能扫描器启动")
        logger.info(f"{'='*60}\n")

        # 创建 WebSocket 客户端
        self.ws_client = BinanceWebSocketClient(
            testnet=self.testnet,
            on_message=self._on_ticker_message,
            on_error=self._on_error,
        )

        # 订阅全量 Ticker 流
        await self.ws_client.subscribe(self.TICKER_STREAM)

        # 运行 WebSocket
        await self.ws_client.run()

    async def stop(self) -> None:
        """停止智能扫描器"""
        self.running = False

        if self.ws_client:
            await self.ws_client.disconnect()

        logger.info("智能扫描器已停止")

    async def _on_ticker_message(self, data: dict) -> None:
        """
        处理 Ticker 消息

        Args:
            data: Ticker 数据
        """
        # 全量 Ticker 流返回数组
        if isinstance(data, list):
            for ticker in data:
                await self._process_ticker(ticker)
        else:
            await self._process_ticker(data)

    async def _process_ticker(self, ticker: dict) -> None:
        """
        处理单个 Ticker

        Args:
            ticker: Ticker 数据
        """
        # 解析数据
        symbol = ticker.get('s', '')
        if not symbol:
            return

        # 过滤稳定币
        if symbol in self.EXCLUDE_SYMBOLS:
            return

        # 只处理 USDT 本位
        if not symbol.endswith('USDT'):
            return

        # 更新缓存
        self.tickers[symbol] = ticker
        self.ticker_count += 1

        # 前置过滤
        passes_filter = await self._prefilter_ticker(ticker)

        if passes_filter:
            # 满足条件，加入候选
            if symbol not in self.candidates:
                self.candidates.add(symbol)

                logger.info(f"🎯 {symbol} 满足前置过滤:")
                logger.info(f"   成交量: ${float(ticker.get('q', 0)):,.0f}")
                logger.info(f"   波动率: {float(ticker.get('P', 0)):.2f}%")

                # 触发深度验证
                await self._deep_verify(symbol)

    async def _prefilter_ticker(self, ticker: dict) -> bool:
        """
        前置过滤（快速筛选）

        Args:
            ticker: Ticker 数据

        Returns:
            是否满足条件
        """
        # 1. 成交量过滤
        quote_volume = float(ticker.get('q', 0))
        if quote_volume < self.min_volume_usdt:
            return False

        # 2. 价格波动率过滤
        price_change_pct = float(ticker.get('P', 0))
        if abs(price_change_pct) < self.min_price_change_pct:
            return False

        return True

    async def _deep_verify(self, symbol: str) -> None:
        """
        深度验证（MTF 三重共振）

        Args:
            symbol: 交易对
        """
        self.rest_request_count += 1

        logger.info(f"🔍 {symbol} 发起深度验证...")

        # 延迟导入，避免循环依赖
        from src.quantitative.mtf_resonance_lock import MTFResonanceLock

        try:
            # 执行 MTF 三重共振检查
            mtf_lock = MTFResonanceLock()
            signal = await mtf_lock.check_triple_resonance(symbol)

            # 检查是否满足条件
            if signal.signal != 0 and signal.is_locked:
                self.signal_count += 1

                logger.critical(f"\n{'='*60}")
                logger.critical(f"🎯🎯🎯 {symbol} 猎杀信号确认！")
                logger.critical(f"{'='*60}")
                logger.critical(f"方向: {'LONG 📈' if signal.signal == 1 else 'SHORT 📉'}")
                logger.critical(f"置信度: {signal.confidence:.0%}")
                logger.critical(f"原因: {'; '.join(signal.reasons)}")
                logger.critical(f"突破价: ${signal.breakthrough_price:.2f}")
                logger.critical(f"建议入场价: ${signal.suggested_entry_price:.2f}")
                logger.critical(f"{'='*60}\n")

                # 触发回调
                if self.on_signal:
                    await self.on_signal({
                        'symbol': symbol,
                        'signal': signal.signal,
                        'confidence': signal.confidence,
                        'reasons': signal.reasons,
                        'entry_price': signal.suggested_entry_price,
                        'breakthrough_price': signal.breakthrough_price,
                    })

        except Exception as e:
            logger.error(f"❌ {symbol} 深度验证失败: {e}")

    async def _on_error(self, error: Exception) -> None:
        """错误处理"""
        logger.error(f"WebSocket 错误: {error}")

    def get_stats(self) -> dict:
        """获取统计信息"""
        return {
            'ticker_count': self.ticker_count,
            'rest_request_count': self.rest_request_count,
            'signal_count': self.signal_count,
            'candidates': list(self.candidates),
            'running': self.running,
        }

    def get_ticker(self, symbol: str) -> Optional[dict]:
        """获取指定币种的 Ticker"""
        return self.tickers.get(symbol)

    def get_all_tickers(self) -> Dict[str, dict]:
        """获取所有 Ticker"""
        return self.tickers.copy()


async def test_smart_screener():
    """测试智能扫描器"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - [%(name)s] - %(levelname)s - %(message)s'
    )

    screener = SmartScreener(
        testnet=True,
        min_volume_usdt=10_000_000,
        min_price_change_pct=0.5,
    )

    try:
        # 运行 60 秒
        await asyncio.wait_for(screener.start(), timeout=60)

    except asyncio.TimeoutError:
        logger.info("测试完成")

    finally:
        await screener.stop()

        # 打印统计
        print("\n统计信息:")
        print(json.dumps(screener.get_stats(), indent=2))


if __name__ == '__main__':
    asyncio.run(test_smart_screener())
