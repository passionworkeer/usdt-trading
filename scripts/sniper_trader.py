#!/usr/bin/env python3
"""
v5.0 狙击手模式主交易脚本（Sniper Mode Trading Service）

针对 200 USDT 超小资金的极低频、极高置信度交易系统：
- MTF 三重共振锁开仓
- 高杠杆孤注一掷（50% 资金）
- 移动止盈追求 1:5 盈亏比
- 把爆仓线当止损线
"""
import asyncio
import logging
import os
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, Optional

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv
from src.exchange.exchange_info_manager import BinanceExchangeInfo
from src.exchange.sniper_position_manager import SniperPositionManager
from src.quantitative.mtf_resonance_lock import MTFResonanceLock

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - [%(name)s] - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/sniper_trader.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class SniperTrader:
    """
    v5.2 狙击手交易器（终极防弹版）

    核心理念：
    - 极低频（一周 1-2 次）
    - 极高置信度（三重共振）
    - 高杠杆孤注一掷（50% 资金）
    - 1:5 盈亏比（移动止盈）
    - 动态波动率安全垫（废除 5 tick）
    - 订单生命周期 + 动量代偿（防止踏空）
    """

    def __init__(self, testnet: bool = True):
        """
        初始化狙击手交易器

        Args:
            testnet: 是否测试网
        """
        self.testnet = testnet
        self.capital = 200  # USDT（超小资金）

        # 初始化组件
        logger.info("初始化 v5.2 狙击手交易器...")
        self.exchange_info = BinanceExchangeInfo(testnet=testnet)
        self.position_manager = SniperPositionManager(self.exchange_info)
        self.mtf_lock = MTFResonanceLock()

        # 监控的交易对
        self.watch_symbols = ['BTC/USDT', 'ETH/USDT', 'SOL/USDT']

        # 运行状态
        self.running = True

        # v5.2: 挂单追踪（订单生命周期管理）
        self.pending_orders = {}  # {symbol: {'signal': MTFSignal, 'timestamp': datetime, 'side': str}}

        logger.info(f"✅ v5.2 狙击手交易器已初始化")
        logger.info(f"  测试网: {'是' if testnet else '否（主网！）'}")
        logger.info(f"  资金: ${self.capital} USDT")
        logger.info(f"  监控交易对: {', '.join(self.watch_symbols)}")
        logger.info(f"  订单 TTL: 1 小时（4 根 15m K线）")
        logger.info(f"  动量代偿: 5 分钟内创新高/低 → 市价追入")

    async def check_and_trade(self, symbol: str) -> Optional[str]:
        """
        v5.2: 检查并执行交易（增加订单生命周期 + 动量代偿）

        流程：
        1. MTF 三重共振检查
        2. 如果锁定，检查是否等待回踩
        3. 如果需要回踩，挂单等待（TTL 1 小时）
        4. 监控动量：5 分钟内创新高/低 → 市价追入
        5. 执行开仓

        Args:
            symbol: 交易对

        Returns:
            交易结果消息
        """
        # 1. MTF 三重共振检查
        signal = await self.mtf_lock.check_triple_resonance(symbol)

        # 2. 如果无信号或未锁定，跳过
        if signal.signal == 0 or not signal.is_locked:
            return None

        # 3. 检查是否允许开仓
        can_open, reason = self.position_manager.can_open_position(symbol)
        if not can_open:
            logger.warning(f"无法开仓 {symbol}: {reason}")
            return None

        # 4. 获取当前价格
        ticker = self.exchange_info.exchange.fetch_ticker(symbol)
        current_price = ticker['last']

        # 5. v5.2: 判断是否需要等待回踩
        if signal.wait_for_pullback and signal.suggested_entry_price:
            # 挂单等待回踩
            self.pending_orders[symbol] = {
                'signal': signal,
                'timestamp': datetime.now(),
                'side': 'LONG' if signal.signal == 1 else 'SHORT',
                'vwap': signal.suggested_entry_price,
                'breakthrough_price': signal.breakthrough_price,
            }

            logger.info(f"📝 {symbol} 挂单等待回踩 VWAP ${signal.suggested_entry_price:.2f}")
            logger.info(f"  突破价格: ${signal.breakthrough_price:.2f}")
            logger.info(f"  当前价格: ${current_price:.2f}")
            logger.info(f"  TTL: 1 小时（超时自动撤销）")
            logger.info(f"  动量代偿: 5 分钟内创新高/低 → 市价追入")

            return f"📝 挂单等待 {symbol} 回踩 VWAP ${signal.suggested_entry_price:.2f}"

        # 6. 不需要回踩，直接市价开仓
        side = 'LONG' if signal.signal == 1 else 'SHORT'
        position = self.position_manager.calculate_sniper_position(
            symbol=symbol,
            capital=self.capital,
            side=side,
            entry_price=current_price,
            stop_distance_pct=0.02
        )

        if not position:
            logger.error(f"❌ 仓位计算失败: {symbol}")
            return None

        # 7. 开仓
        self.position_manager.open_position(position)

        message = f"🎯 已开仓 {symbol} {side} @ ${current_price:.2f}"
        logger.critical(message)

        return message

    async def check_pending_orders(self):
        """
        v5.2: 检查挂单状态（生命周期 + 动量代偿）

        逻辑：
        1. 检查挂单 TTL（超时 1 小时 → 撤销）
        2. 检查动量代偿（5 分钟内创新高/低 → 市价追入）
        3. 检查价格回踩（价格触及 VWAP → 限价成交）
        """
        if not self.pending_orders:
            return

        for symbol, order in list(self.pending_orders.items()):
            signal = order['signal']
            order_time = order['timestamp']
            vwap = order['vwap']
            breakthrough_price = order['breakthrough_price']
            side = order['side']

            # 获取当前价格
            try:
                ticker = self.exchange_info.exchange.fetch_ticker(symbol)
                current_price = ticker['last']
            except Exception as e:
                logger.error(f"获取 {symbol} 价格失败: {e}")
                continue

            # 1. 检查 TTL（超时 1 小时）
            holding_duration = datetime.now() - order_time
            holding_minutes = holding_duration.total_seconds() / 60

            if holding_minutes > 60:
                # 超时撤销
                del self.pending_orders[symbol]
                logger.warning(f"⏰ {symbol} 挂单超时 1 小时，已撤销")
                continue

            # 2. 检查动量代偿（5 分钟内创新高/低）
            if holding_minutes <= 5:
                # 检查是否创新高/低
                if side == 'LONG' and current_price > breakthrough_price:
                    # 做多创新高 → 市价追入
                    logger.critical(f"🚀 {symbol} 动量代偿触发！价格 ${current_price:.2f} > 突破价 ${breakthrough_price:.2f} → 市价追入！")

                    # 计算仓位
                    position = self.position_manager.calculate_sniper_position(
                        symbol=symbol,
                        capital=self.capital,
                        side=side,
                        entry_price=current_price,
                        stop_distance_pct=0.02
                    )

                    if position:
                        self.position_manager.open_position(position)
                        del self.pending_orders[symbol]
                        logger.critical(f"🎯 动量追入成功 {symbol} {side} @ ${current_price:.2f}")
                        continue

                elif side == 'SHORT' and current_price < breakthrough_price:
                    # 做空创新低 → 市价追入
                    logger.critical(f"🚀 {symbol} 动量代偿触发！价格 ${current_price:.2f} < 突破价 ${breakthrough_price:.2f} → 市价追入！")

                    # 计算仓位
                    position = self.position_manager.calculate_sniper_position(
                        symbol=symbol,
                        capital=self.capital,
                        side=side,
                        entry_price=current_price,
                        stop_distance_pct=0.02
                    )

                    if position:
                        self.position_manager.open_position(position)
                        del self.pending_orders[symbol]
                        logger.critical(f"🎯 动量追入成功 {symbol} {side} @ ${current_price:.2f}")
                        continue

            # 3. 检查价格回踩（触及 VWAP → 限价成交）
            if side == 'LONG' and current_price <= vwap:
                # 做多回踩到 VWAP → 成交
                logger.info(f"✅ {symbol} 回踩到 VWAP ${vwap:.2f}，当前价 ${current_price:.2f} → 限价成交")

                position = self.position_manager.calculate_sniper_position(
                    symbol=symbol,
                    capital=self.capital,
                    side=side,
                    entry_price=vwap,  # 使用 VWAP 作为入场价
                    stop_distance_pct=0.02
                )

                if position:
                    self.position_manager.open_position(position)
                    del self.pending_orders[symbol]
                    logger.critical(f"🎯 限价成交成功 {symbol} {side} @ ${vwap:.2f}")
                    continue

            elif side == 'SHORT' and current_price >= vwap:
                # 做空回踩到 VWAP → 成交
                logger.info(f"✅ {symbol} 回踩到 VWAP ${vwap:.2f}，当前价 ${current_price:.2f} → 限价成交")

                position = self.position_manager.calculate_sniper_position(
                    symbol=symbol,
                    capital=self.capital,
                    side=side,
                    entry_price=vwap,  # 使用 VWAP 作为入场价
                    stop_distance_pct=0.02
                )

                if position:
                    self.position_manager.open_position(position)
                    del self.pending_orders[symbol]
                    logger.critical(f"🎯 限价成交成功 {symbol} {side} @ ${vwap:.2f}")
                    continue

    async def update_positions(self):
        """更新仓位（移动止盈、止损检查）"""
        if not self.position_manager.positions:
            return

        # 获取所有持仓的当前价格
        prices = {}
        for symbol in self.position_manager.positions.keys():
            try:
                ticker = self.exchange_info.exchange.fetch_ticker(symbol)
                prices[symbol] = ticker['last']
            except Exception as e:
                logger.error(f"获取 {symbol} 价格失败: {e}")
                continue

        # 1. 检查紧急平仓（达到爆仓线）
        emergency_close, reason = self.position_manager.should_emergency_close_all(prices)
        if emergency_close:
            logger.critical(f"🚨 紧急平仓触发！{reason}")
            for symbol, exit_price in prices.items():
                self.position_manager.close_position(symbol, exit_price, reason='STOP_LOSS')
            return

        # 2. 更新移动止盈
        for symbol, current_price in prices.items():
            self.position_manager.update_trailing_stop(symbol, current_price)

            # 3. 检查移动止盈触发
            if self.position_manager.check_trailing_stop_trigger(symbol, current_price):
                self.position_manager.close_position(symbol, current_price, reason='TRAILING_STOP')

        # 4. 打印当前盈亏
        total_pnl, total_pnl_pct = self.position_manager.get_total_unrealized_pnl(prices)
        if total_pnl != 0:
            logger.info(f"💰 当前盈亏: ${total_pnl:+.2f} ({total_pnl_pct:+.2%})")

    async def run(self):
        """
        v5.2: 主循环（极低频 + 挂单管理）

        策略：
        - 每 15 分钟检查一次 MTF 三重共振
        - 每次循环检查挂单状态（TTL、动量代偿、回踩成交）
        - 平时只更新移动止盈
        - 一天最多 1-2 次开仓机会
        """
        logger.info("\n" + "="*60)
        logger.info("🎯 v5.2 终极防弹狙击手模式启动")
        logger.info("="*60 + "\n")

        check_interval = 15 * 60  # 15 分钟检查一次

        while self.running:
            try:
                logger.info(f"\n⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} - 开始扫描")

                # 1. 更新仓位
                await self.update_positions()

                # 2. v5.2: 检查挂单状态（TTL、动量代偿、回踩成交）
                await self.check_pending_orders()

                # 3. 检查是否可以开新仓
                if len(self.position_manager.positions) < self.position_manager.max_positions:
                    # 遍历监控交易对
                    for symbol in self.watch_symbols:
                        message = await self.check_and_trade(symbol)

                        # 如果开仓成功，停止扫描其他交易对
                        if message:
                            logger.critical(message)
                            break

                # 4. 打印统计
                stats = self.position_manager.get_trading_statistics()
                if stats['total_trades'] > 0:
                    logger.info(f"📊 交易统计: {stats['total_trades']} 笔 | 胜率 {stats['win_rate']:.0%} | 总盈亏 ${stats['total_pnl']:+.2f}")

                # v5.2: 打印挂单状态
                if self.pending_orders:
                    logger.info(f"📝 挂单中: {', '.join(self.pending_orders.keys())}")

                logger.info(f"⏰ 下次扫描: {check_interval // 60} 分钟后\n")

                # 等待下一次扫描
                await asyncio.sleep(check_interval)

            except KeyboardInterrupt:
                logger.info("\n收到中断信号")
                break
            except Exception as e:
                logger.error(f"主循环异常: {e}", exc_info=True)
                await asyncio.sleep(60)  # 异常后等待 1 分钟

        logger.info("🛑 狙击手交易器已停止")

    async def close(self):
        """清理资源"""
        await self.mtf_lock.close()


def main():
    """主函数"""
    testnet = os.getenv('BINANCE_TESTNET', 'true').lower() == 'true'

    if not testnet:
        logger.critical("⚠️⚠️⚠️ 主网模式！将使用真实资金！⚠️⚠️⚠️")
        confirm = input("确认继续？(yes/no): ")
        if confirm.lower() != 'yes':
            logger.info("已取消")
            return

    trader = SniperTrader(testnet=testnet)

    try:
        asyncio.run(trader.run())
    except KeyboardInterrupt:
        logger.info("\n收到中断信号")
    finally:
        asyncio.run(trader.close())


if __name__ == '__main__':
    main()
