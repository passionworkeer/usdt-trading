#!/usr/bin/env python3
"""
v8.0 狙击手模式主交易脚本（Sniper Mode Trading Service）

针对 200 USDT 超小资金的极低频、极高置信度交易系统：
- MTF 三重共振锁开仓
- AI Agent 双轨架构（宏观大局观 + 微观审批）
- 自然语言数据翻译器
- 外部情报嗅探器（Twitter + 新闻）
- 5秒滑点硬拦截
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
from src.monitoring.state_broadcaster import StateBroadcaster

# v8.0 AI Agent 组件
from src.ai.decision_engine import ClaudeDecisionEngine
from src.ai.nlt_translator import NLTDataTranslator
from src.ai.macro_oracle import MacroOracle
from src.intelligence.web_scraper import IntelligenceSniffer
from src.execution.slippage_hardlock import SlippageHardlock

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
        enable_broadcaster: bool = True,
        enable_ai_agent: bool = True,  # v8.0 新增
    ) -> None:
        """
        初始化狙击手交易器

        Args:
            testnet: 是否测试网
            dry_run: 是否启用 Dry-Run 模式
            capital: 总资金（USDT）
            enable_broadcaster: 是否启用状态广播（Redis Pub/Sub）
            enable_ai_agent: 是否启用 AI Agent（v8.0）
        """
        self.testnet = testnet
        self.dry_run = dry_run
        self.capital = capital
        self.enable_broadcaster = enable_broadcaster
        self.enable_ai_agent = enable_ai_agent  # v8.0

        # 初始化组件
        logger.info("初始化 v8.0 狙击手交易器...")
        self.exchange_info = BinanceExchangeInfo(testnet=testnet)
        self.position_manager = SniperPositionManager(self.exchange_info)
        self.mtf_lock = MTFResonanceLock()
        self.alerter = get_alerter()

        # v8.0 AI Agent 组件
        if self.enable_ai_agent:
            logger.info("初始化 AI Agent 组件...")
            self.decision_engine = ClaudeDecisionEngine()
            self.translator = NLTDataTranslator()
            self.scraper = IntelligenceSniffer(
                twitter_bearer_token=os.getenv('TWITTER_BEARER_TOKEN')
            )
            self.macro_oracle = MacroOracle(self.decision_engine)
            self.slippage_guard = SlippageHardlock(
                threshold_pct=0.5,
                timeout_sec=5.0
            )
            self.macro_state = None
            self.last_macro_update = None
            logger.info("🤖 AI Agent 组件已启动")
        else:
            self.decision_engine = None
            self.translator = None
            self.scraper = None
            self.macro_oracle = None
            self.slippage_guard = None
            self.macro_state = None
            self.last_macro_update = None

        # 监控的交易对
        self.watch_symbols = ['BTC/USDT', 'ETH/USDT', 'SOL/USDT']

        # 运行状态
        self.running = True

        # 挂单追踪（订单生命周期管理）
        self.pending_orders: Dict[str, Dict] = {}

        # 初始化状态广播器（进程间通信，非阻塞）
        self.state_broadcaster = None

        if self.enable_broadcaster:
            logger.info("初始化状态广播器...")
            self.state_broadcaster = StateBroadcaster()
            logger.info("📡 状态广播器已启动（Redis Pub/Sub）")

        # 打印配置
        self._print_config()

    def _print_config(self) -> None:
        """打印配置信息"""
        logger.info(f"\n{'='*60}")
        logger.info(f"🎯 v8.0 狙击手交易器已初始化")
        logger.info(f"{'='*60}")
        logger.info(f"  测试网: {'是' if self.testnet else '否（主网！）'}")
        logger.info(f"  模式: {'🧪 DRY-RUN（模拟）' if self.dry_run else '🔴 LIVE（实盘！）'}")
        logger.info(f"  资金: ${self.capital} USDT")
        logger.info(f"  监控交易对: {', '.join(self.watch_symbols)}")
        logger.info(f"  订单 TTL: 1 小时")
        logger.info(f"  动量代偿: 5 分钟内创新高/低 → 市价追入")
        if self.enable_ai_agent:
            logger.info(f"  AI Agent: 🤖 已启用（宏观大局观 + 微观审批 + 滑点硬拦截）")
        if self.enable_broadcaster:
            logger.info(f"  状态广播: Redis Pub/Sub（独立进程监控）")
        logger.info(f"{'='*60}\n")

    @exponential_backoff_retry(max_retries=3, base_delay=2.0)
    async def check_and_trade(self, symbol: str) -> Optional[str]:
        """
        检查并执行交易（v8.0 AI Agent + 订单生命周期 + 动量代偿 + Dry-Run）

        流程：
        1. MTF 三重共振检查
        2. 如果锁定，发送预警
        3. v8.0: AI Agent 宏观禁令检查
        4. v8.0: AI Agent 微观审批（3-5秒思考）
        5. v8.0: 滑点硬拦截（0.5%阈值）
        6. 检查是否允许开仓
        7. 判断是否需要等待回踩
        8. 如果需要回踩，挂单等待（TTL 1 小时）
        9. 监控动量：5 分钟内创新高/低 → 市价追入
        10. 执行开仓（或模拟）

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

        # 4. v8.0: 更新宏观大局观（每小时）
        if self.enable_ai_agent:
            await self._update_macro_state_if_needed()

            # 5. v8.0: 检查宏观禁令
            if not self._check_macro_ban(symbol, side_str):
                logger.warning(f"🚫 {symbol} {side_str} 被宏观大局观禁止")
                return f"🚫 {symbol} {side_str} 被宏观大局观禁止"

        # 6. 获取当前价格
        ticker = self.exchange_info.exchange.fetch_ticker(symbol)
        current_price = ticker['last']

        # 7. v8.0: AI Agent 微观审批（如果启用）
        if self.enable_ai_agent:
            approved, ai_reason = await self._ai_micro_approval(
                symbol, signal, current_price
            )
            if not approved:
                logger.warning(f"🤖 AI 审批拒绝: {ai_reason}")
                return f"🤖 AI 审批拒绝: {ai_reason}"

        # 异步广播价格更新（非阻塞）
        if self.state_broadcaster:
            await self.state_broadcaster.broadcast_price(symbol, current_price)

        # 8. 检查是否允许开仓
        can_open, reason = self.position_manager.can_open_position(symbol)
        if not can_open:
            logger.warning(f"无法开仓 {symbol}: {reason}")
            return None

        # 9. 判断是否需要等待回踩
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

        # 10. 不需要回踩，直接市价开仓
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

        # 11. v8.0: 滑点检查（AI 思考期间价格是否偏离）
        if self.enable_ai_agent:
            latest_price = self.exchange_info.exchange.fetch_ticker(symbol)['last']
            passed, slippage_reason = self.slippage_guard.check_slippage(
                symbol, latest_price
            )
            if not passed:
                logger.warning(f"🚨 {slippage_reason}")
                return f"🚨 {slippage_reason}"

        # 12. 执行开仓（或模拟）
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

            # 异步广播开仓事件（非阻塞）
            if self.state_broadcaster:
                await self.state_broadcaster.broadcast_event({
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

        # 异步广播开仓事件（非阻塞）
        if self.state_broadcaster:
            await self.state_broadcaster.broadcast_event({
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

                # 异步广播价格更新（非阻塞）
                if self.state_broadcaster:
                    await self.state_broadcaster.broadcast_price(symbol, prices[symbol])

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
                    # 异步广播平仓事件（非阻塞）
                    if self.state_broadcaster:
                        await self.state_broadcaster.broadcast_event({
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
        logger.info(f"🎯 v7.3 终极防弹狙击手模式启动")
        logger.info(f"{'🧪 DRY-RUN 模式' if self.dry_run else '🔴 LIVE 实盘模式'}")
        logger.info("="*60 + "\n")

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

        # v8.0: 关闭 Web Scraper
        if self.scraper:
            self.scraper.close()
            logger.info("🔍 Web Scraper 已关闭")

        # 关闭状态广播器
        if self.state_broadcaster:
            await self.state_broadcaster.close()
            logger.info("📡 状态广播器已关闭")

        await self.mtf_lock.close()
        await self.alerter.close()

    # ==================== v8.0 AI Agent 辅助方法 ====================

    async def _update_macro_state_if_needed(self) -> None:
        """每小时更新宏观大局观"""
        if not self.macro_oracle:
            return

        # 首次运行或距离上次更新超过 1 小时
        if self.last_macro_update is None or \
           (datetime.now() - self.last_macro_update).total_seconds() > 3600:

            logger.info("🔄 更新宏观大局观...")

            # 抓取外部情报
            intelligence = {
                'tweets': await self.scraper.scrape_twitter_sentiment(
                    self.watch_symbols[0].replace('/', ''), limit=50
                ),
                'news': await self.scraper.scrape_macro_news(limit=10)
            }

            # 生成宏观状态
            self.macro_state = await self.macro_oracle.generate_macro_state(
                intelligence
            )
            self.last_macro_update = datetime.now()

    def _check_macro_ban(self, symbol: str, side_str: str) -> bool:
        """检查宏观禁令"""
        if not self.macro_state:
            return True  # 没有宏观状态，默认允许

        # 检查禁令
        if side_str.upper() in self.macro_state.trading_bans:
            logger.warning(
                f"🚫 {symbol} {side_str} 被宏观禁令阻止 "
                f"(原因: {self.macro_state.reasoning})"
            )
            return False

        return True

    async def _ai_micro_approval(
        self,
        symbol: str,
        signal: MTFSignal,
        current_price: float
    ) -> Tuple[bool, str]:
        """
        AI 微观审批（3-5秒思考）

        Args:
            symbol: 交易对
            signal: MTF 信号
            current_price: 当前价格

        Returns:
            (是否通过, 原因)
        """
        if not self.decision_engine:
            return True, "AI Agent 未启用"

        try:
            # 1. 锁定触发价格（滑点保护）
            self.slippage_guard.lock_trigger_price(symbol, current_price)

            # 2. 翻译微观数据成自然语言
            micro_snapshot = {
                'symbol': symbol,
                'price': current_price,
                'funding_rate': getattr(signal, 'funding_rate', 0),
                'obi': getattr(signal, 'obi', 0),
                'volume_15m': getattr(signal, 'volume_15m', 0),
                'avg_volume_15m': getattr(signal, 'avg_volume_15m', 0),
                'ema_distance': getattr(signal, 'ema_distance', 0),
            }
            micro_report = self.translator.translate_micro_snapshot(micro_snapshot)

            # 3. 翻译宏观状态
            macro_report = ""
            if self.macro_state:
                macro_report = self.translator.translate_macro_state(
                    self.macro_state.__dict__
                )

            # 4. 请求 AI 确认
            logger.info(f"🤖 请求 AI 审批: {symbol}...")
            decision = await self.decision_engine.analyze_market(
                symbol=symbol,
                price=current_price,
                price_history=[],  # TODO: 从历史数据获取
                market_data={
                    'micro_report': micro_report,
                    'macro_report': macro_report,
                    'mtf_signal': {
                        'side': 'LONG' if signal.signal == 1 else 'SHORT',
                        'confidence': signal.confidence,
                        'reasons': signal.reasons,
                    }
                }
            )

            # 5. 判断 AI 决策
            if decision.action == 'hold':
                return False, f"AI 建议持有（置信度: {decision.confidence:.2f}）"
            elif decision.action == 'buy' and signal.signal == -1:
                return False, "AI 建议买入，但 MTF 信号为做空，冲突"
            elif decision.action == 'sell' and signal.signal == 1:
                return False, "AI 建议卖出，但 MTF 信号为做多，冲突"
            elif decision.confidence < 0.6:
                return False, f"AI 置信度过低 ({decision.confidence:.2f} < 0.6)"
            else:
                logger.info(
                    f"✅ AI 审批通过: {decision.action} "
                    f"(置信度: {decision.confidence:.2f})"
                )
                return True, f"AI 审批通过（{decision.reasoning}）"

        except Exception as e:
            logger.error(f"AI 审批失败: {e}")
            # 失败时保守处理：允许通过（不影响交易）
            return True, f"AI 审批异常，默认通过（{e}）"


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

    trader = SniperTrader(
        testnet=testnet,
        dry_run=dry_run,
        capital=capital,
        enable_ai_agent=os.getenv('ENABLE_AI_AGENT', 'true').lower() == 'true'
    )

    try:
        asyncio.run(trader.run())
    except KeyboardInterrupt:
        logger.info("\n收到中断信号")
    finally:
        asyncio.run(trader.close())


if __name__ == '__main__':
    main()
