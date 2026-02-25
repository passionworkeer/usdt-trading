#!/usr/bin/env python3
"""
v5.3 狙击手模式主交易脚本（Sniper Mode Trading Service）

针对 200 USDT 超小资金的极低频、极高置信度交易系统：
- MTF 三重共振锁开仓
- 高杠杆孤注一掷（50% 资金）
- 移动止盈追求 1:5 盈亏比
- 把爆仓线当止损线
- Dry-Run 模式支持
- Telegram/Discord 实时预警
"""
import asyncio
import logging
import os
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, Optional, Tuple
from enum import Enum

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv

from src.exchange.exchange_info_manager import BinanceExchangeInfo
from src.exchange.sniper_position_manager import (
    SniperPositionManager,
    Side,
    CloseReason
)
from src.quantitative.mtf_resonance_lock import MTFResonanceLock, MTFSignal
from src.utils.webhook_alerter import WebhookAlerter, get_alerter
from src.utils.api_retry import exponential_backoff_retry, classify_binance_error
from src.monitoring.monitoring_collector import MonitoringCollector
from src.monitoring.monitoring_server import MonitoringServer

load_dotenv()

# 确保 logs 目录存在
Path('logs').mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - [%(name)s] - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/sniper_trader.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class DryRunMode(Enum):
    """Dry-Run 模式"""
    ENABLED = "DRY_RUN"
    DISABLED = "LIVE"


class SniperTrader:
    """
    v5.3 狙击手交易器（军工级战备版）

    核心理念：
    - 极低频（一周 1-2 次）
    - 极高置信度（三重共振）
    - 高杠杆孤注一掷（50% 资金）
    - 1:5 盈亏比（移动止盈）
    - 动态波动率安全垫
    - 订单生命周期 + 动量代偿
    - Dry-Run 模式支持
    - Telegram/Discord 实时预警
    """

    def __init__(
        self,
        testnet: bool = True,
        dry_run: bool = True,
        capital: float = 200.0,
        enable_monitoring: bool = True,
        monitoring_port: int = 8765,
    ) -> None:
        """
        初始化狙击手交易器

        Args:
            testnet: 是否测试网
            dry_run: 是否启用 Dry-Run 模式
            capital: 总资金（USDT）
            enable_monitoring: 是否启用监控服务
            monitoring_port: 监控服务端口
        """
        self.testnet = testnet
        self.dry_run = dry_run
        self.capital = capital
        self.enable_monitoring = enable_monitoring
        self.monitoring_port = monitoring_port

        # 初始化组件
        logger.info("初始化 v5.3 狙击手交易器...")
        self.exchange_info = BinanceExchangeInfo(testnet=testnet)
        self.position_manager = SniperPositionManager(self.exchange_info)
        self.mtf_lock = MTFResonanceLock()
        self.alerter = get_alerter()

        # 监控的交易对
        self.watch_symbols = ['BTC/USDT', 'ETH/USDT', 'SOL/USDT']

        # 运行状态
        self.running = True

        # 挂单追踪（订单生命周期管理）
        self.pending_orders: Dict[str, Dict] = {}

        # 初始化监控服务
        self.monitoring_collector = None
        self.monitoring_server = None

        if self.enable_monitoring:
            logger.info("初始化监控服务...")
            self.monitoring_collector = MonitoringCollector(
                position_manager=self.position_manager,
                obi_interceptor=None,  # 可以后续添加
                ws_pool=None,  # 可以后续添加
            )
            self.monitoring_server = MonitoringServer(
                collector=self.monitoring_collector,
                port=self.monitoring_port,
            )
            logger.info(f"📊 监控面板: http://localhost:{self.monitoring_port}")

        # 打印配置
        self._print_config()

    def _print_config(self) -> None:
        """打印配置信息"""
        logger.info(f"\n{'='*60}")
        logger.info(f"🎯 v5.3 狙击手交易器已初始化")
        logger.info(f"{'='*60}")
        logger.info(f"  测试网: {'是' if self.testnet else '否（主网！）'}")
        logger.info(f"  模式: {'🧪 DRY-RUN（模拟）' if self.dry_run else '🔴 LIVE（实盘！）'}")
        logger.info(f"  资金: ${self.capital} USDT")
        logger.info(f"  监控交易对: {', '.join(self.watch_symbols)}")
        logger.info(f"  订单 TTL: 1 小时")
        logger.info(f"  动量代偿: 5 分钟内创新高/低 → 市价追入")
        if self.enable_monitoring:
            logger.info(f"  监控面板: http://localhost:{self.monitoring_port}")
        logger.info(f"{'='*60}\n")

    @exponential_backoff_retry(max_retries=3, base_delay=2.0)
    async def check_and_trade(self, symbol: str) -> Optional[str]:
        """
        检查并执行交易（订单生命周期 + 动量代偿 + Dry-Run）

        流程：
        1. MTF 三重共振检查
        2. 如果锁定，发送预警
        3. 检查是否等待回踩
        4. 如果需要回踩，挂单等待（TTL 1 小时）
        5. 监控动量：5 分钟内创新高/低 → 市价追入
        6. 执行开仓（或模拟）

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

        # 3. 发送三重共振预警
        side_str = 'LONG' if signal.signal == 1 else 'SHORT'
        await self.alerter.alert_resonance_locked(
            symbol=symbol,
            side=side_str,
            confidence=signal.confidence,
            reasons=signal.reasons,
            entry_price=signal.breakthrough_price,
            vwap=signal.suggested_entry_price
        )

        # 4. 检查是否允许开仓
        can_open, reason = self.position_manager.can_open_position(symbol)
        if not can_open:
            logger.warning(f"无法开仓 {symbol}: {reason}")
            return None

        # 5. 获取当前价格
        ticker = self.exchange_info.exchange.fetch_ticker(symbol)
        current_price = ticker['last']

        # 更新监控价格缓存
        if self.monitoring_collector:
            await self.monitoring_collector.update_price_cache(symbol, current_price)

        # 6. 判断是否需要等待回踩
        if signal.wait_for_pullback and signal.suggested_entry_price:
            # 挂单等待回踩
            self.pending_orders[symbol] = {
                'signal': signal,
                'timestamp': datetime.now(),
                'side': Side.LONG if signal.signal == 1 else Side.SHORT,
                'vwap': signal.suggested_entry_price,
                'breakthrough_price': signal.breakthrough_price,
            }

            logger.info(f"📝 {symbol} 挂单等待回踩 VWAP ${signal.suggested_entry_price:.2f}")

            return f"📝 挂单等待 {symbol} 回踩 VWAP ${signal.suggested_entry_price:.2f}"

        # 7. 不需要回踩，直接市价开仓
        side = Side.LONG if signal.signal == 1 else Side.SHORT
        position = self.position_manager.calculate_sniper_position(
            symbol=symbol,
            capital=self.capital,
            side=side,
            entry_price=current_price,
        )

        if not position:
            logger.error(f"❌ 仓位计算失败: {symbol}")
            return None

        # 8. 执行开仓（或模拟）
        return await self._execute_open_position(position, current_price, "MARKET")

    async def _execute_open_position(
        self,
        position,
        execution_price: float,
        fill_type: str
    ) -> Optional[str]:
        """
        执行开仓（支持 Dry-Run）

        Args:
            position: 仓位对象
            execution_price: 成交价格
            fill_type: 成交类型（MARKET / LIMIT / MARKET_MOMENTUM）

        Returns:
            交易结果消息
        """
        symbol = position.symbol
        side_str = position.side.value

        # Dry-Run 模式
        if self.dry_run:
            logger.critical(f"🧪 [DRY-RUN] 模拟开仓：{symbol} {side_str} @ ${execution_price:.2f}")
            logger.critical(f"   杠杆: {position.leverage}x")
            logger.critical(f"   数量: {position.quantity:.6f}")
            logger.critical(f"   止损价: ${position.stop_loss_price:.2f}")
            logger.critical(f"   止盈价: ${position.take_profit_price:.2f}")
            logger.critical(f"   类型: {fill_type}")

            # 模拟开仓（不实际调用 API）
            self.position_manager.open_position(position)

            # 记录监控事件
            if self.monitoring_server:
                self.monitoring_server.add_event({
                    'type': 'open',
                    'symbol': symbol,
                    'side': side_str,
                    'price': execution_price,
                    'message': f"🧪 [DRY-RUN] 模拟开仓 {symbol} {side_str} @ ${execution_price:.2f}",
                })

            return f"🧪 [DRY-RUN] 模拟开仓 {symbol} {side_str} @ ${execution_price:.2f}"

        # 实盘模式
        logger.critical(f"🔴 [LIVE] 实盘开仓：{symbol} {side_str} @ ${execution_price:.2f}")

        # TODO: 调用 Binance API 下单
        # order = self.exchange_info.exchange.create_market_order(...)
        # 验证订单成功后，再开仓

        self.position_manager.open_position(position)

        # 记录监控事件
        if self.monitoring_server:
            self.monitoring_server.add_event({
                'type': 'open',
                'symbol': symbol,
                'side': side_str,
                'price': execution_price,
                'message': f"🎯 [LIVE] 实盘开仓 {symbol} {side_str} @ ${execution_price:.2f}",
            })

        # 发送订单成交预警
        await self.alerter.alert_order_filled(
            symbol=symbol,
            side=side_str,
            entry_price=execution_price,
            quantity=position.quantity,
            leverage=position.leverage,
            stop_loss=position.stop_loss_price,
            take_profit=position.take_profit_price,
            fill_type=fill_type
        )

        return f"🎯 已开仓 {symbol} {side_str} @ ${execution_price:.2f}"

    @exponential_backoff_retry(max_retries=3, base_delay=2.0)
    async def check_pending_orders(self) -> None:
        """
        检查挂单状态（生命周期 + 动量代偿）

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
                if side == Side.LONG and current_price > breakthrough_price:
                    # 做多创新高 → 市价追入
                    logger.critical(f"🚀 {symbol} 动量代偿触发！价格 ${current_price:.2f} > 突破价 ${breakthrough_price:.2f}")

                    position = self.position_manager.calculate_sniper_position(
                        symbol=symbol,
                        capital=self.capital,
                        side=side,
                        entry_price=current_price,
                    )

                    if position:
                        await self._execute_open_position(position, current_price, "MARKET_MOMENTUM")
                        del self.pending_orders[symbol]
                        continue

                elif side == Side.SHORT and current_price < breakthrough_price:
                    # 做空创新低 → 市价追入
                    logger.critical(f"🚀 {symbol} 动量代偿触发！价格 ${current_price:.2f} < 突破价 ${breakthrough_price:.2f}")

                    position = self.position_manager.calculate_sniper_position(
                        symbol=symbol,
                        capital=self.capital,
                        side=side,
                        entry_price=current_price,
                    )

                    if position:
                        await self._execute_open_position(position, current_price, "MARKET_MOMENTUM")
                        del self.pending_orders[symbol]
                        continue

            # 3. 检查价格回踩（触及 VWAP → 限价成交）
            if side == Side.LONG and current_price <= vwap:
                # 做多回踩到 VWAP → 成交
                logger.info(f"✅ {symbol} 回踩到 VWAP ${vwap:.2f}")

                position = self.position_manager.calculate_sniper_position(
                    symbol=symbol,
                    capital=self.capital,
                    side=side,
                    entry_price=vwap,
                )

                if position:
                    await self._execute_open_position(position, vwap, "LIMIT")
                    del self.pending_orders[symbol]
                    continue

            elif side == Side.SHORT and current_price >= vwap:
                # 做空回踩到 VWAP → 成交
                logger.info(f"✅ {symbol} 回踩到 VWAP ${vwap:.2f}")

                position = self.position_manager.calculate_sniper_position(
                    symbol=symbol,
                    capital=self.capital,
                    side=side,
                    entry_price=vwap,
                )

                if position:
                    await self._execute_open_position(position, vwap, "LIMIT")
                    del self.pending_orders[symbol]
                    continue

    async def update_positions(self) -> None:
        """更新仓位（移动止盈、止损检查 + 预警）"""
        if not self.position_manager.positions:
            return

        # 获取所有持仓的当前价格
        prices = {}
        for symbol in self.position_manager.positions.keys():
            try:
                ticker = self.exchange_info.exchange.fetch_ticker(symbol)
                prices[symbol] = ticker['last']

                # 更新监控价格缓存
                if self.monitoring_collector:
                    await self.monitoring_collector.update_price_cache(symbol, prices[symbol])

            except Exception as e:
                logger.error(f"获取 {symbol} 价格失败: {e}")
                continue

        # 1. 检查紧急平仓（达到爆仓线）
        emergency_close, reason = self.position_manager.should_emergency_close_all(prices)
        if emergency_close:
            logger.critical(f"🚨 紧急平仓触发！{reason}")

            for symbol, exit_price in prices.items():
                position = self.position_manager.positions.get(symbol)
                if position:
                    self.position_manager.close_position(symbol, exit_price, CloseReason.STOP_LOSS)

                    # 发送预警
                    await self.alerter.alert_stop_loss(
                        symbol=symbol,
                        side=position.side.value,
                        entry_price=position.entry_price,
                        exit_price=exit_price,
                        pnl=position.pnl,
                    )
            return

        # 2. 检查每个仓位的平仓条件
        for symbol, current_price in prices.items():
            should_close, reason, close_reason = self.position_manager.should_close_position(symbol, current_price)

            if should_close:
                position = self.position_manager.positions.get(symbol)
                if not position:
                    continue

                # 平仓
                closed_position = self.position_manager.close_position(symbol, current_price, close_reason)

                if closed_position:
                    # 记录监控事件
                    if self.monitoring_server:
                        self.monitoring_server.add_event({
                            'type': 'close',
                            'symbol': symbol,
                            'side': position.side.value,
                            'entry_price': position.entry_price,
                            'exit_price': current_price,
                            'pnl': position.pnl,
                            'reason': close_reason.value,
                            'message': f"✅ 平仓 {symbol} {position.side.value} @ ${current_price:.2f} | P&L: ${position.pnl:+.2f}",
                        })

                    # 根据平仓原因发送不同预警
                    if close_reason == CloseReason.TIME_STOP:
                        holding_duration = datetime.now() - position.entry_time
                        holding_hours = holding_duration.total_seconds() / 3600
                        roe = self.position_manager.calculate_roe(position, current_price)

                        await self.alerter.alert_time_stop(
                            symbol=symbol,
                            side=position.side.value,
                            holding_hours=holding_hours,
                            roe=roe
                        )

                    elif close_reason == CloseReason.TRAILING_STOP:
                        roe = self.position_manager.calculate_roe(position, current_price)

                        await self.alerter.alert_trailing_stop(
                            symbol=symbol,
                            side=position.side.value,
                            entry_price=position.entry_price,
                            exit_price=current_price,
                            pnl=position.pnl,
                            roe=roe
                        )

                continue

            # 3. 更新移动止盈
            self.position_manager.update_trailing_stop(symbol, current_price)

        # 4. 打印当前盈亏
        total_pnl, total_pnl_pct = self.position_manager.get_total_unrealized_pnl(prices)
        if total_pnl != 0:
            logger.info(f"💰 当前盈亏: ${total_pnl:+.2f} ({total_pnl_pct:+.2%})")

    async def run(self, check_interval_minutes: int = 15) -> None:
        """
        主循环（极低频 + 挂单管理）

        策略：
        - 每 N 分钟检查一次 MTF 三重共振
        - 每次循环检查挂单状态
        - 平时只更新移动止盈
        - 一天最多 1-2 次开仓机会

        Args:
            check_interval_minutes: 检查间隔（分钟）
        """
        logger.info("\n" + "="*60)
        logger.info(f"🎯 v5.3 终极防弹狙击手模式启动")
        logger.info(f"{'🧪 DRY-RUN 模式' if self.dry_run else '🔴 LIVE 实盘模式'}")
        logger.info("="*60 + "\n")

        # 启动监控服务（后台任务）
        if self.enable_monitoring and self.monitoring_server:
            logger.info(f"📊 启动监控服务...")
            asyncio.create_task(self.monitoring_server.start())

        check_interval = check_interval_minutes * 60  # 转换为秒

        while self.running:
            try:
                logger.info(f"\n⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} - 开始扫描")

                # 1. 更新仓位
                await self.update_positions()

                # 2. 检查挂单状态
                await self.check_pending_orders()

                # 3. 检查是否可以开新仓
                if len(self.position_manager.positions) < self.position_manager.max_positions:
                    for symbol in self.watch_symbols:
                        message = await self.check_and_trade(symbol)

                        if message:
                            logger.critical(message)
                            break  # 最多开一个仓

                # 4. 打印统计
                stats = self.position_manager.get_trading_statistics()
                if stats['total_trades'] > 0:
                    logger.info(
                        f"📊 交易统计: {stats['total_trades']} 笔 | "
                        f"胜率 {stats['win_rate']:.0%} | "
                        f"总盈亏 ${stats['total_pnl']:+.2f}"
                    )

                # 打印挂单状态
                if self.pending_orders:
                    logger.info(f"📝 挂单中: {', '.join(self.pending_orders.keys())}")

                logger.info(f"⏰ 下次扫描: {check_interval // 60} 分钟后\n")

                await asyncio.sleep(check_interval)

            except KeyboardInterrupt:
                logger.info("\n收到中断信号")
                break
            except Exception as e:
                logger.error(f"主循环异常: {e}", exc_info=True)
                await asyncio.sleep(60)  # 异常后等待 1 分钟

        logger.info("🛑 狙击手交易器已停止")

    async def close(self) -> None:
        """清理资源"""
        logger.info("清理资源...")

        # 停止监控服务
        if self.monitoring_server:
            self.monitoring_server.stop()
            logger.info("📊 监控服务已停止")

        await self.mtf_lock.close()
        await self.alerter.close()


def main():
    """主函数"""
    # 从环境变量读取配置
    testnet = os.getenv('BINANCE_TESTNET', 'true').lower() == 'true'
    dry_run = os.getenv('DRY_RUN', 'true').lower() == 'true'
    capital = float(os.getenv('CAPITAL', '200'))

    # 主网模式确认
    if not testnet:
        logger.critical("⚠️⚠️⚠️ 主网模式！将使用真实资金！⚠️⚠️⚠️")
        confirm = input("确认继续？(yes/no): ")
        if confirm.lower() != 'yes':
            logger.info("已取消")
            return

    # 实盘模式确认
    if not dry_run:
        logger.critical("⚠️⚠️⚠️ LIVE 实盘模式！将使用真实资金下单！⚠️⚠️⚠️")
        confirm = input("确认继续？(yes/no): ")
        if confirm.lower() != 'yes':
            logger.info("已取消")
            return

    trader = SniperTrader(testnet=testnet, dry_run=dry_run, capital=capital)

    try:
        asyncio.run(trader.run())
    except KeyboardInterrupt:
        logger.info("\n收到中断信号")
    finally:
        asyncio.run(trader.close())


if __name__ == '__main__':
    main()
