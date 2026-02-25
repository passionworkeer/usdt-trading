"""
v6.0 全景流动性雷达（Global Screener）

扫描全网成交量排名前 30 的 U 本位合约，并发执行 MTF 三重共振检查
"""
import asyncio
import logging
from typing import List, Dict, Optional, Tuple
from datetime import datetime

import aiohttp

logger = logging.getLogger(__name__)


class GlobalScreener:
    """
    全景流动性雷达

    功能：
    1. 扫描全网成交量排名前 30 的 U 本位合约
    2. 并发执行 MTF 三重共振检查
    3. 返回第一个满足条件的信号
    4. 自动过滤低流动性币种
    """

    # 币安 API 端点
    FAPI_URL = "https://fapi.binance.com/fapi/v1"

    # 排除币种（稳定币）
    EXCLUDE_SYMBOLS = {
        'USDCUSDT', 'TUSDUSDT', 'BUSDUSDT', 'USDPUSDT',
        'DAIUSDT', 'FRAXUSDT', 'USDNUSDT', 'USDTBUSD',
    }

    def __init__(
        self,
        top_n: int = 30,  # 扫描前 N 个币种
        min_volume_usdt: float = 10_000_000,  # 最小成交量（1000万 USDT）
        check_interval: int = 15,  # 检查间隔（分钟）
        testnet: bool = False,
    ):
        self.top_n = top_n
        self.min_volume_usdt = min_volume_usdt
        self.check_interval = check_interval
        self.testnet = testnet

        # Session（全局 Keep-Alive）
        self.session: Optional[aiohttp.ClientSession] = None

        # MTF 锁（延迟导入，避免循环依赖）
        self.mtf_lock = None

        # 运行状态
        self.running = False

        # 统计信息
        self.scan_count = 0
        self.signal_count = 0
        self.last_scan_time: Optional[datetime] = None

        logger.info(f"全景流动性雷达初始化: Top {top_n}, 最小成交量 {min_volume_usdt:,.0f} USDT")

    async def init_session(self) -> None:
        """初始化全局 Session（TLS Keep-Alive）"""
        if self.session is None:
            # 配置连接器（Keep-Alive + 连接池）
            connector = aiohttp.TCPConnector(
                limit=100,  # 最大连接数
                limit_per_host=30,  # 每个主机最大连接数
                ttl_dns_cache=300,  # DNS 缓存 5 分钟
                keepalive_timeout=60,  # Keep-Alive 超时 60 秒
                enable_cleanup_closed=True,  # 清理关闭的连接
            )

            # 配置超时
            timeout = aiohttp.ClientTimeout(
                total=30,  # 总超时 30 秒
                connect=10,  # 连接超时 10 秒
                sock_read=5,  # 读取超时 5 秒
            )

            self.session = aiohttp.ClientSession(
                connector=connector,
                timeout=timeout,
            )

            logger.info("✅ 全局 Session 已初始化（Keep-Alive）")

    async def close_session(self) -> None:
        """关闭 Session"""
        if self.session:
            await self.session.close()
            self.session = None
            logger.info("🔌 全局 Session 已关闭")

    async def fetch_top_volume_symbols(self) -> List[str]:
        """
        获取成交量排名前 N 的币种

        Returns:
            币种列表（如 ['BTCUSDT', 'ETHUSDT', ...]）
        """
        await self.init_session()

        url = f"{self.FAPI_URL}/ticker/24hr"

        try:
            async with self.session.get(url) as response:
                if response.status != 200:
                    logger.error(f"获取 24h 行情失败: HTTP {response.status}")
                    return []

                data = await response.json()

                # 解析数据
                symbols_data = []
                for item in data:
                    symbol = item.get('symbol', '')
                    quote_volume = float(item.get('quoteVolume', 0))

                    # 过滤条件
                    # 1. 必须是 USDT 本位
                    # 2. 排除稳定币
                    # 3. 达到最小成交量
                    if (
                        symbol.endswith('USDT') and
                        symbol not in self.EXCLUDE_SYMBOLS and
                        quote_volume >= self.min_volume_usdt
                    ):
                        symbols_data.append({
                            'symbol': symbol,
                            'volume': quote_volume,
                        })

                # 按成交量排序
                symbols_data.sort(key=lambda x: x['volume'], reverse=True)

                # 取前 N 个
                top_symbols = [item['symbol'] for item in symbols_data[:self.top_n]]

                logger.info(f"📊 扫描目标: {len(top_symbols)} 个币种")
                logger.info(f"   Top 5: {', '.join(top_symbols[:5])}")

                return top_symbols

        except Exception as e:
            logger.error(f"获取 24h 行情异常: {e}")
            return []

    async def scan_single_symbol(self, symbol: str) -> Optional[Dict]:
        """
        扫描单个币种（执行 MTF 三重共振检查）

        Args:
            symbol: 币种（如 'BTCUSDT'）

        Returns:
            信号字典（如果满足条件）或 None
        """
        # 延迟初始化 MTF 锁（避免循环依赖）
        if self.mtf_lock is None:
            from src.quantitative.mtf_resonance_lock import MTFResonanceLock
            self.mtf_lock = MTFResonanceLock()

        try:
            # 执行 MTF 三重共振检查
            signal = await self.mtf_lock.check_triple_resonance(symbol)

            # 检查是否满足条件
            if signal.signal != 0 and signal.is_locked:
                self.signal_count += 1

                logger.critical(f"🎯 {symbol} 触发三重共振！")
                logger.critical(f"   方向: {'LONG' if signal.signal == 1 else 'SHORT'}")
                logger.critical(f"   置信度: {signal.confidence:.0%}")

                return {
                    'symbol': symbol,
                    'signal': signal.signal,
                    'confidence': signal.confidence,
                    'reasons': signal.reasons,
                    'entry_price': signal.suggested_entry_price,
                    'breakthrough_price': signal.breakthrough_price,
                }

        except Exception as e:
            logger.error(f"❌ {symbol} MTF 检查失败: {e}")

        return None

    async def scan_market(self) -> Optional[Dict]:
        """
        扫描市场（并发执行）

        Returns:
            第一个满足条件的信号，或 None
        """
        # 1. 获取 Top N 币种
        symbols = await self.fetch_top_volume_symbols()

        if not symbols:
            logger.warning("⚠️ 无可扫描币种")
            return None

        # 2. 并发执行 MTF 检查
        logger.info(f"🔍 开始并发扫描 {len(symbols)} 个币种...")

        tasks = [self.scan_single_symbol(symbol) for symbol in symbols]

        # 使用 asyncio.as_completed 返回第一个完成的信号
        for coro in asyncio.as_completed(tasks):
            result = await coro

            if result:
                # 找到第一个满足条件的信号
                logger.critical(f"🎯🎯🎯 猎杀目标锁定: {result['symbol']}！")

                # 取消其他任务
                for task in tasks:
                    if not task.done():
                        task.cancel()

                return result

        # 3. 无信号
        self.scan_count += 1
        self.last_scan_time = datetime.now()

        logger.info(f"✅ 扫描完成，无满足条件的信号（第 {self.scan_count} 次扫描）")

        return None

    async def run_continuous(self) -> None:
        """
        持续扫描模式

        每隔 N 分钟扫描一次，直到找到满足条件的信号
        """
        self.running = True

        logger.info(f"\n{'='*60}")
        logger.info(f"🎯 v6.0 全景流动性雷达启动")
        logger.info(f"{'='*60}\n")

        while self.running:
            try:
                logger.info(f"\n⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} - 开始全景扫描")

                # 扫描市场
                signal = await self.scan_market()

                if signal:
                    # 找到信号
                    logger.critical(f"\n{'='*60}")
                    logger.critical(f"🎯🎯🎯 发现完美猎杀信号！")
                    logger.critical(f"{'='*60}")
                    logger.critical(f"币种: {signal['symbol']}")
                    logger.critical(f"方向: {'LONG 📈' if signal['signal'] == 1 else 'SHORT 📉'}")
                    logger.critical(f"置信度: {signal['confidence']:.0%}")
                    logger.critical(f"突破价: ${signal['breakthrough_price']:.2f}")
                    logger.critical(f"建议入场价: ${signal['entry_price']:.2f}")
                    logger.critical(f"{'='*60}\n")

                    return signal

                # 等待下次扫描
                logger.info(f"⏰ 下次扫描: {self.check_interval} 分钟后\n")

                await asyncio.sleep(self.check_interval * 60)

            except asyncio.CancelledError:
                logger.info("\n收到中断信号")
                break
            except Exception as e:
                logger.error(f"扫描异常: {e}", exc_info=True)
                await asyncio.sleep(60)  # 异常后等待 1 分钟

        logger.info("🛑 全景流动性雷达已停止")

    def stop(self) -> None:
        """停止扫描"""
        self.running = False

    def get_stats(self) -> Dict:
        """获取统计信息"""
        return {
            'scan_count': self.scan_count,
            'signal_count': self.signal_count,
            'last_scan_time': self.last_scan_time.isoformat() if self.last_scan_time else None,
            'running': self.running,
        }


async def test_screener():
    """测试全景流动性雷达"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - [%(name)s] - %(levelname)s - %(message)s'
    )

    screener = GlobalScreener(
        top_n=10,  # 测试用，只扫描前 10 个
        min_volume_usdt=10_000_000,
        check_interval=15,
    )

    try:
        # 单次扫描测试
        signal = await screener.scan_market()

        if signal:
            print(f"\n发现信号: {signal}")

    finally:
        await screener.close_session()


if __name__ == '__main__':
    asyncio.run(test_screener())
