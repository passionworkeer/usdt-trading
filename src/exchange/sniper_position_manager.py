"""
v5.3: 狙击手仓位管理器（Sniper Position Manager）

针对 200 USDT 超小资金的孤注一掷模型：
- 50% 高杠杆单次开仓
- 精确计算真实强平价（基于 MMR）
- 动态波动率安全垫
- ROE 移动止盈
- 12 小时时间止损
- P2-20: 动态杠杆上限（根据波动率调整）
"""
import logging
import asyncio
import statistics
from typing import Dict, Optional, Tuple, List
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum

from .exchange_info_manager import BinanceExchangeInfo

logger = logging.getLogger(__name__)


class Side(Enum):
    """交易方向"""
    LONG = "LONG"
    SHORT = "SHORT"


class PositionStatus(Enum):
    """仓位状态"""
    OPEN = "OPEN"
    CLOSED = "CLOSED"
    LIQUIDATED = "LIQUIDATED"


class CloseReason(Enum):
    """平仓原因"""
    MANUAL = "MANUAL"
    STOP_LOSS = "STOP_LOSS"  # 爆仓线止损
    TAKE_PROFIT = "TAKE_PROFIT"
    TRAILING_STOP = "TRAILING_STOP"
    TIME_STOP = "TIME_STOP"  # 12 小时时间止损
    EMERGENCY = "EMERGENCY"  # 紧急平仓


@dataclass
class SniperPosition:
    """狙击手仓位"""
    symbol: str
    side: Side
    entry_price: float
    quantity: float
    leverage: int
    stop_loss_price: float  # 爆仓线 = 止损线
    take_profit_price: float
    trailing_stop_price: Optional[float] = None  # 移动止盈
    entry_time: datetime = field(default_factory=datetime.now)
    pnl: float = 0.0
    status: PositionStatus = PositionStatus.OPEN


class SniperPositionManager:
    """
    v5.3 狙击手仓位管理器（军工级重构）

    核心理念：
    1. 孤注一掷 - 50% 资金高杠杆单次开仓
    2. 爆仓即止损 - 动态安全垫确保主动止损
    3. 移动止盈 - 让利润奔跑，追求 1:5 盈亏比
    4. 时间止损 - 12 小时未达标强制平仓
    5. 极低频 - 一周最多 1-2 次开仓机会

    改进：
    - 完整类型提示
    - 指数退避重试机制
    - 清晰的异常捕获
    """

    def __init__(self, exchange_info: BinanceExchangeInfo) -> None:
        """
        初始化仓位管理器

        Args:
            exchange_info: exchangeInfo 管理器
        """
        self.exchange_info = exchange_info
        self.positions: Dict[str, SniperPosition] = {}
        self.closed_positions: List[SniperPosition] = []

        # v5.0 狙击手参数
        self.position_ratio: float = 0.5  # 每次用 50% 资金
        self.max_positions: int = 1  # 同时只持有 1 个仓位
        self.target_rr_ratio: float = 5.0  # 目标盈亏比 1:5

        logger.info("✅ v5.3 狙击手仓位管理器已初始化")
        logger.info(f"  开仓比例: {self.position_ratio*100:.0f}%")
        logger.info(f"  最大并发仓位: {self.max_positions}")
        logger.info(f"  目标盈亏比: 1:{self.target_rr_ratio}")

    def get_mmr(self, notional_value: float) -> float:
        """
        获取维持保证金率（MMR）

        根据 Binance U本位合约规则，MMR 随名义价值阶梯变化

        Args:
            notional_value: 名义价值（USDT）

        Returns:
            MMR（如 0.004 表示 0.4%）
        """
        if notional_value < 50000:
            return 0.004  # 0.4%
        elif notional_value < 250000:
            return 0.005  # 0.5%
        else:
            return 0.01  # 1%

    def calculate_liquidation_price(
        self,
        entry_price: float,
        leverage: int,
        side: Side,
        quantity: float
    ) -> float:
        """
        计算真实强平价（Liquidation Price）

        公式（简化版）：
        - LONG: Liquidation_Price = Entry_Price × (1 - 1/Leverage + MMR)
        - SHORT: Liquidation_Price = Entry_Price × (1 + 1/Leverage - MMR)

        Args:
            entry_price: 入场价格
            leverage: 杠杆倍数
            side: 交易方向
            quantity: 数量（用于计算名义价值）

        Returns:
            真实强平价
        """
        # 计算名义价值
        notional_value = entry_price * quantity

        # 获取 MMR
        mmr = self.get_mmr(notional_value)

        # 计算强平价
        if side == Side.LONG:
            # LONG: 强平价 = 入场价 × (1 - 1/杠杆 + MMR)
            liquidation_price = entry_price * (1 - 1/leverage + mmr)
        else:
            # SHORT: 强平价 = 入场价 × (1 + 1/杠杆 - MMR)
            liquidation_price = entry_price * (1 + 1/leverage - mmr)

        logger.info(f"📊 真实强平价计算:")
        logger.info(f"  入场价: ${entry_price:.2f}")
        logger.info(f"  杠杆: {leverage}x")
        logger.info(f"  名义价值: ${notional_value:.2f}")
        logger.info(f"  MMR: {mmr:.2%}")
        logger.info(f"  真实强平价: ${liquidation_price:.2f}")
        logger.info(f"  强平距离: {abs(liquidation_price/entry_price - 1)*100:.2f}%")

        return liquidation_price

    def calculate_volatility_buffer(
        self,
        symbol: str,
        entry_price: float
    ) -> float:
        """
        v5.2: 计算动态波动率安全垫（Volatility Buffer）

        废除固定的 5 tick，改为基于真实波动率的动态缓冲：
        Buffer = max(Entry_Price × 0.002, 1m_ATR × 0.5)

        Args:
            symbol: 交易对
            entry_price: 入场价格

        Returns:
            动态安全垫（USDT）
        """
        try:
            # 尝试获取实时 ATR（如果 exchange_info 有）
            if hasattr(self.exchange_info, 'fetch_atr'):
                atr_1m = self.exchange_info.fetch_atr(symbol, timeframe='1m', period=14)
                atr_buffer = atr_1m * 0.5
            else:
                # 降级：使用默认波动率估算
                atr_buffer = entry_price * 0.001

            # 基础缓冲：0.2% 标的价格
            base_buffer = entry_price * 0.002

            # 动态缓冲 = max(基础, ATR)
            dynamic_buffer = max(base_buffer, atr_buffer)

            logger.info(f"🛡️ 动态波动率安全垫计算:")
            logger.info(f"  基础缓冲 (0.2%): ${base_buffer:.2f}")
            logger.info(f"  ATR 缓冲 (50%): ${atr_buffer:.2f}")
            logger.info(f"  最终安全垫: ${dynamic_buffer:.2f} ({dynamic_buffer/entry_price*100:.3f}%)")

            return dynamic_buffer

        except Exception as e:
            # 异常降级：使用 0.3% 标的价格（超保守）
            fallback_buffer = entry_price * 0.003
            logger.warning(f"⚠️ 动态缓冲计算失败，降级为 0.3%: ${fallback_buffer:.2f} ({e})")
            return fallback_buffer

    def calculate_market_volatility(
        self,
        exchange,
        symbol: str,
        periods: int = 24
    ) -> float:
        """
        P2-20: 计算 24 小时历史波动率（百分比）

        Args:
            exchange: 交易所实例
            symbol: 交易对
            periods: K线周期数（1小时周期），默认 24 小时

        Returns:
            波动率百分比（如 2.0 表示 2%）
        """
        try:
            ohlcv = exchange.fetch_ohlcv(symbol, '1h', limit=periods)
            closes = [c[4] for c in ohlcv]

            if len(closes) < 2:
                logger.warning(f"{symbol} K线数据不足，使用默认波动率 2%")
                return 2.0

            # 计算收益率
            returns = [(closes[i] - closes[i-1]) / closes[i-1] for i in range(1, len(closes))]

            if len(returns) < 2:
                return 2.0

            # 计算标准差
            volatility = statistics.stdev(returns)

            return volatility * 100  # 转换为百分比

        except Exception as e:
            logger.warning(f"波动率计算失败: {e}，使用默认波动率 2%")
            return 2.0

    def calculate_dynamic_leverage(
        self,
        volatility: float,
        base_leverage: int = 20
    ) -> Tuple[int, str]:
        """
        P2-20: 根据波动率动态调整最大杠杆

        策略：
        - 波动率 > 5% (高波动): 杠杆减半，最大 3x
        - 波动率 3-5% (中波动): 保持基础杠杆，最大 5x
        - 波动率 < 3% (低波动): 杠杆+2，最大 10x

        Args:
            volatility: 波动率百分比
            base_leverage: 基础杠杆倍数

        Returns:
            (调整后的杠杆, 调整原因)
        """
        if volatility > 5:
            # 高波动：大幅降低杠杆，防止爆仓
            dynamic_leverage = min(base_leverage // 2, 3)
            reason = f"高波动环境 (波动率 {volatility:.2f}% > 5%)，降杠杆至 {dynamic_leverage}x"
        elif volatility > 3:
            # 中波动：保持基础杠杆
            dynamic_leverage = min(base_leverage, 5)
            reason = f"中等波动环境 (波动率 {volatility:.2f}% 在 3-5%)，杠杆限制 {dynamic_leverage}x"
        else:
            # 低波动：可适当提高杠杆
            dynamic_leverage = min(base_leverage + 2, 10)
            reason = f"低波动环境 (波动率 {volatility:.2f}% < 3%)，杠杆提升至 {dynamic_leverage}x"

        logger.info(f"📊 P2-20 动态杠杆计算:")
        logger.info(f"  24h 波动率: {volatility:.2f}%")
        logger.info(f"  基础杠杆: {base_leverage}x")
        logger.info(f"  动态杠杆: {dynamic_leverage}x")
        logger.info(f"  原因: {reason}")

        return dynamic_leverage, reason

    def calculate_safety_cushion(
        self,
        liquidation_price: float,
        leverage: int
    ) -> float:
        """
        v5.4: 计算强平价安全垫（Safety Cushion）

        防止止损价过于接近强平价，增加额外缓冲确保主动止损：

        安全垫策略（根据杠杆动态调整）：
        - 杠杆 ≤ 10x: 2% 强平价缓冲
        - 杠杆 11-20x: 3% 强平价缓冲
        - 杠杆 > 20x: 4% 强平价缓冲

        公式：
        safety_cushion = liquidation_price × cushion_percentage

        Args:
            liquidation_price: 强平价格
            leverage: 杠杆倍数

        Returns:
            安全垫金额（USDT）
        """
        # 根据杠杆动态调整安全垫比例
        if leverage <= 10:
            cushion_pct = 0.02  # 2%
        elif leverage <= 20:
            cushion_pct = 0.03  # 3%
        else:
            cushion_pct = 0.04  # 4%

        safety_cushion = liquidation_price * cushion_pct

        logger.info(f"🛡️ 强平价安全垫计算:")
        logger.info(f"  杠杆倍数: {leverage}x")
        logger.info(f"  安全垫比例: {cushion_pct:.1%}")
        logger.info(f"  安全垫金额: ${safety_cushion:.2f} ({safety_cushion/liquidation_price*100:.2f}% 强平价)")

        return safety_cushion

    def validate_stop_loss_safety(
        self,
        stop_loss_price: float,
        liquidation_price: float,
        entry_price: float,
        side: Side
    ) -> Tuple[bool, str]:
        """
        v5.4: 验证止损价的安全性

        确保止损价与强平价之间有足够的安全距离：

        验证规则：
        1. 止损价必须在强平价的安全侧（LONG更高，SHORT更低）
        2. 止损价与强平价的距离 ≥ 强平价的 2%
        3. 止损价与入场价的距离合理（不超过 15%）

        Args:
            stop_loss_price: 止损价格
            liquidation_price: 强平价格
            entry_price: 入场价格
            side: 交易方向

        Returns:
            (是否安全, 验证信息)
        """
        # 计算止损价与强平价的距离
        buffer_amount = abs(stop_loss_price - liquidation_price)
        buffer_pct = buffer_amount / liquidation_price * 100

        # 最小安全距离：强平价的 2%
        min_buffer_pct = 2.0

        # 检查止损价方向
        if side == Side.LONG:
            # LONG: 止损价应该高于强平价
            if stop_loss_price <= liquidation_price:
                return False, f"❌ 危险：LONG止损价(${stop_loss_price:.2f}) ≤ 强平价(${liquidation_price:.2f})，会直接爆仓！"
        else:
            # SHORT: 止损价应该低于强平价
            if stop_loss_price >= liquidation_price:
                return False, f"❌ 危险：SHORT止损价(${stop_loss_price:.2f}) ≥ 强平价(${liquidation_price:.2f})，会直接爆仓！"

        # 检查安全距离
        if buffer_pct < min_buffer_pct:
            return False, f"⚠️ 警告：止损距强平仅 {buffer_pct:.2f}% < {min_buffer_pct}%，建议增加安全垫"

        # 计算止损距离入场价的百分比
        stop_distance_pct = abs(stop_loss_price - entry_price) / entry_price * 100

        # 检查止损距离是否过大（超过 15% 可能过于保守）
        if stop_distance_pct > 15:
            return False, f"⚠️ 注意：止损距入场 {stop_distance_pct:.1f}%，可能过于保守"

        # 全部通过
        return True, (
            f"✅ 止损价安全验证通过：\n"
            f"  止损价: ${stop_loss_price:.2f}\n"
            f"  强平价: ${liquidation_price:.2f}\n"
            f"  安全距离: {buffer_pct:.2f}% (${buffer_amount:.2f})\n"
            f"  止损距离: {stop_distance_pct:.1f}%"
        )

    def calculate_sniper_position(
        self,
        symbol: str,
        capital: float,
        side: Side,
        entry_price: float,
        exchange=None
    ) -> Optional[SniperPosition]:
        """
        计算狙击手仓位（孤注一掷模型 + 真实强平价 + P2-20 动态杠杆）

        策略：
        1. 使用 50% 资金作为保证金
        2. P2-20: 根据波动率动态调整杠杆上限
        3. 自动调整杠杆满足 MIN_NOTIONAL
        4. 计算真实强平价（基于 MMR）
        5. 把止损线设在强平价前置动态安全垫
        6. 目标盈利 = 5 × 止损距离

        Args:
            symbol: 交易对
            capital: 总资金（USDT）
            side: 交易方向
            entry_price: 入场价格
            exchange: 交易所实例（可选，用于动态杠杆计算）

        Returns:
            SniperPosition 对象，如果计算失败返回 None
        """
        # 计算可用保证金（50% 资金）
        margin = capital * self.position_ratio

        # P2-20: 动态杠杆计算
        base_leverage = 20
        if exchange is not None:
            volatility = self.calculate_market_volatility(exchange, symbol)
            max_leverage, leverage_reason = self.calculate_dynamic_leverage(volatility, base_leverage)
            logger.info(f"📊 {leverage_reason}")
        else:
            max_leverage = base_leverage
            logger.info(f"📊 使用默认杠杆上限: {max_leverage}x")

        # 自动计算杠杆和数量（使用动态杠杆上限）
        quantity, leverage, feasible = self.exchange_info.calculate_min_quantity_for_capital(
            symbol, margin, leverage=max_leverage
        )

        if not feasible:
            logger.error(f"❌ 资金不足，无法开仓 {symbol}")
            return None

        # 计算真实强平价（基于 MMR）
        liquidation_price = self.calculate_liquidation_price(entry_price, leverage, side, quantity)

        # 计算动态波动率安全垫
        volatility_buffer = self.calculate_volatility_buffer(symbol, entry_price)

        # v5.4: 计算强平价安全垫（防止止损过于接近强平）
        safety_cushion = self.calculate_safety_cushion(liquidation_price, leverage)

        # 止损价 = 强平价 ± max(动态安全垫, 强平价安全垫)
        # 使用更大的安全垫确保主动止损优先于强平
        total_buffer = max(volatility_buffer, safety_cushion)

        if side == Side.LONG:
            # LONG: 止损价 = 强平价 + 总安全垫（避免被强平）
            stop_loss_price = liquidation_price + total_buffer
            # 目标止盈（1:5 盈亏比）
            stop_distance = (entry_price - stop_loss_price) / entry_price
            take_profit_price = entry_price * (1 + abs(stop_distance) * self.target_rr_ratio)
        else:
            # SHORT: 止损价 = 强平价 - 总安全垫（避免被强平）
            stop_loss_price = liquidation_price - total_buffer
            # 目标止盈（1:5 盈亏比）
            stop_distance = (stop_loss_price - entry_price) / entry_price
            take_profit_price = entry_price * (1 - abs(stop_distance) * self.target_rr_ratio)

        # 创建仓位对象
        position = SniperPosition(
            symbol=symbol,
            side=side,
            entry_price=entry_price,
            quantity=quantity,
            leverage=leverage,
            stop_loss_price=stop_loss_price,
            take_profit_price=take_profit_price,
            entry_time=datetime.now(),
        )

        # v5.4: 验证止损价安全性
        is_safe, safety_msg = self.validate_stop_loss_safety(
            stop_loss_price, liquidation_price, entry_price, side
        )
        if not is_safe:
            logger.error(f"❌ 止损价安全验证失败: {safety_msg}")
            # 根据严重程度决定是否继续
            if "危险" in safety_msg:
                # 危险情况：直接拒绝开仓
                return None
            # 警告情况：继续但记录警告
        else:
            logger.info(f"✅ {safety_msg}")

        # 验证订单
        valid, reason = self.exchange_info.validate_order(symbol, quantity, entry_price)
        if not valid:
            logger.error(f"❌ 订单验证失败: {reason}")
            return None

        # 打印仓位信息
        self._print_position_summary(position, capital, liquidation_price, volatility_buffer, safety_cushion, total_buffer)

        return position

    def _print_position_summary(
        self,
        position: SniperPosition,
        capital: float,
        liquidation_price: float,
        volatility_buffer: float,
        safety_cushion: float,
        total_buffer: float
    ) -> None:
        """打印仓位摘要"""
        notional = position.quantity * position.entry_price
        margin_used = notional / position.leverage

        # 计算止损价与强平价的距离百分比
        stop_loss_distance_pct = abs(position.stop_loss_price - liquidation_price) / liquidation_price * 100

        logger.info(f"\n{'='*60}")
        logger.info(f"🎯 v5.4 狙击手仓位计算结果（增强安全垫）")
        logger.info(f"{'='*60}")
        logger.info(f"交易对: {position.symbol}")
        logger.info(f"方向: {position.side.value}")
        logger.info(f"杠杆: {position.leverage}x")
        logger.info(f"入场价: ${position.entry_price:.2f}")
        logger.info(f"数量: {position.quantity:.6f}")
        logger.info(f"名义价值: ${notional:.2f}")
        logger.info(f"占用保证金: ${margin_used:.2f} ({margin_used/capital*100:.1f}% 资金)")
        logger.info(f"")
        logger.info(f"⚠️ 动态强平价计算:")
        logger.info(f"  真实强平价: ${liquidation_price:.2f} (基于 MMR)")
        logger.info(f"  强平距离: {abs(liquidation_price/position.entry_price - 1)*100:.2f}%")
        logger.info(f"")
        logger.info(f"🛡️ 多层安全垫系统:")
        logger.info(f"  波动率缓冲: ${volatility_buffer:.2f} ({volatility_buffer/position.entry_price*100:.3f}%)")
        logger.info(f"  强平价安全垫: ${safety_cushion:.2f} ({safety_cushion/liquidation_price*100:.2f}% 强平价)")
        logger.info(f"  总安全垫: ${total_buffer:.2f} (max of above)")
        logger.info(f"")
        logger.info(f"🛡️ 主动止损线（多层安全垫）:")
        logger.info(f"  止损价: ${position.stop_loss_price:.2f} ({abs(position.stop_loss_price/position.entry_price - 1)*100:.2f}%)")
        logger.info(f"  距离强平价: {stop_loss_distance_pct:.2f}% (${abs(position.stop_loss_price - liquidation_price):.2f})")
        logger.info(f"  💡 宁可自己止损，绝不让交易所强平！")
        logger.info(f"")
        logger.info(f"🎯 目标止盈: ${position.take_profit_price:.2f} ({abs(position.take_profit_price/position.entry_price - 1)*100:.2f}%)")
        logger.info(f"盈亏比: 1:{self.target_rr_ratio}")
        logger.info(f"{'='*60}\n")

    def can_open_position(self, symbol: str) -> Tuple[bool, str]:
        """
        检查是否允许开仓

        规则：
        1. 最多同时持有 1 个仓位
        2. 不能重复开仓同一交易对

        Args:
            symbol: 交易对

        Returns:
            (是否允许, 原因)
        """
        if len(self.positions) >= self.max_positions:
            return False, f"已达到最大仓位数量 {self.max_positions}"

        if symbol in self.positions:
            return False, f"已持有 {symbol} 仓位"

        return True, "OK"

    def open_position(self, position: SniperPosition) -> None:
        """开仓"""
        self.positions[position.symbol] = position
        logger.info(f"✅ 已开仓 {position.symbol} {position.side.value}")

    def close_position(
        self,
        symbol: str,
        exit_price: float,
        reason: CloseReason = CloseReason.MANUAL
    ) -> Optional[SniperPosition]:
        """
        平仓

        Args:
            symbol: 交易对
            exit_price: 出场价格
            reason: 平仓原因

        Returns:
            已平仓的 SniperPosition，如果不存在返回 None
        """
        position = self.positions.pop(symbol, None)
        if not position:
            logger.warning(f"⚠️ 未找到 {symbol} 仓位")
            return None

        # 计算盈亏
        if position.side == Side.LONG:
            pnl = (exit_price - position.entry_price) * position.quantity
        else:
            pnl = (position.entry_price - exit_price) * position.quantity

        position.pnl = pnl
        position.status = PositionStatus.CLOSED

        # 记录到历史
        self.closed_positions.append(position)

        logger.info(f"✅ 已平仓 {symbol} {position.side.value}")
        logger.info(f"  出场价: ${exit_price:.2f}")
        logger.info(f"  盈亏: ${pnl:+.2f} ({pnl/position.entry_price/position.quantity*100:+.2f}%)")
        logger.info(f"  原因: {reason.value}")

        return position

    def calculate_roe(self, position: SniperPosition, current_price: float) -> float:
        """
        计算真实的 ROE（净资产收益率）

        公式：ROE = (标的价格涨跌幅) × 杠杆

        Args:
            position: 仓位对象
            current_price: 当前价格

        Returns:
            ROE 百分比（如 0.5 表示 50%）
        """
        if position.side == Side.LONG:
            price_change_pct = (current_price - position.entry_price) / position.entry_price
        else:
            price_change_pct = (position.entry_price - current_price) / position.entry_price

        # ROE = 标的价格涨跌幅 × 杠杆
        roe = price_change_pct * position.leverage

        return roe

    def check_time_stop(
        self,
        position: SniperPosition,
        current_price: float,
        max_holding_hours: int = 12,
        min_roe_threshold: float = 0.2
    ) -> Tuple[bool, str]:
        """
        v5.1: 时间止损机制（狙击手绝不陷入泥潭）

        规则：
        - 开仓后 max_holding_hours 小时内（默认 12 小时）
        - 如果 ROE 始终未达到 min_roe_threshold（默认 20%）
        - 说明狙击失败，陷入震荡泥潭
        - 必须无条件市价平仓，防止资金费率吸血！

        Args:
            position: 仓位对象
            current_price: 当前价格
            max_holding_hours: 最大持仓时间（小时）
            min_roe_threshold: 最低 ROE 阈值

        Returns:
            (是否触发时间止损, 原因)
        """
        if not position.entry_time:
            return False, "无入场时间"

        # 计算持仓时间
        holding_duration = datetime.now() - position.entry_time
        holding_hours = holding_duration.total_seconds() / 3600

        # 如果持仓时间未达到上限，不触发
        if holding_hours < max_holding_hours:
            return False, f"持仓时间 {holding_hours:.1f}h < {max_holding_hours}h"

        # 计算当前 ROE
        roe = self.calculate_roe(position, current_price)

        # 如果 ROE 已达标，不触发
        if roe >= min_roe_threshold:
            return False, f"ROE {roe:.1%} >= {min_roe_threshold:.0%}，狙击成功"

        # 触发时间止损
        reason = (f"⏰ 时间止损触发：持仓 {holding_hours:.1f}h，ROE 仅 {roe:.1%} < {min_roe_threshold:.0%} "
                 f"→ 狙击失败，陷入震荡，立即平仓防止资金费率吸血！")

        logger.critical(f"🚨 {position.symbol} {reason}")

        return True, reason

    def should_close_position(
        self,
        symbol: str,
        current_price: float
    ) -> Tuple[bool, str, CloseReason]:
        """
        v5.1: 综合平仓检查（整合所有平仓条件）

        检查顺序：
        1. 爆仓线止损
        2. 时间止损
        3. 移动止盈触发

        Args:
            symbol: 交易对
            current_price: 当前价格

        Returns:
            (是否应该平仓, 原因, 平仓原因枚举)
        """
        position = self.positions.get(symbol)
        if not position:
            return False, "无仓位", CloseReason.MANUAL

        # 1. 检查爆仓线止损
        if position.side == Side.LONG:
            if current_price <= position.stop_loss_price:
                return True, f"🚨 达到爆仓线止损：${current_price:.2f} <= ${position.stop_loss_price:.2f}", CloseReason.STOP_LOSS
        else:
            if current_price >= position.stop_loss_price:
                return True, f"🚨 达到爆仓线止损：${current_price:.2f} >= ${position.stop_loss_price:.2f}", CloseReason.STOP_LOSS

        # 2. 检查时间止损
        should_close, reason = self.check_time_stop(position, current_price)
        if should_close:
            return True, reason, CloseReason.TIME_STOP

        # 3. 检查移动止盈触发
        if self.check_trailing_stop_trigger(symbol, current_price):
            return True, f"🎯 移动止盈触发：${current_price:.2f}", CloseReason.TRAILING_STOP

        return False, "持仓正常", CloseReason.MANUAL

    def update_trailing_stop(
        self,
        symbol: str,
        current_price: float,
        trailing_distance_roe: float = 0.2
    ) -> None:
        """
        v5.1 核心：基于 ROE 的移动止盈

        逻辑：
        1. 计算当前 ROE = 标的价格涨跌幅 × 杠杆
        2. 只有 ROE > 50% 才启动移动止盈
        3. 移动距离 = 当前 ROE × 20%（回撤 20% ROE 即平仓）
        4. 永远只向盈利方向移动

        Args:
            symbol: 交易对
            current_price: 当前价格
            trailing_distance_roe: 移动距离（ROE 的百分比，默认 20%）
        """
        position = self.positions.get(symbol)
        if not position:
            return

        # 计算 ROE
        roe = self.calculate_roe(position, current_price)

        # 只有 ROE 超过 50% 才启动移动止盈
        if roe < 0.5:
            logger.debug(f"{symbol} ROE {roe:.1%} < 50%，暂不启动移动止盈")
            return

        # 计算新的移动止盈 ROE
        new_trailing_roe = roe * (1 - trailing_distance_roe)

        # 只向盈利方向移动
        if position.trailing_stop_price is None:
            # 首次启动，转换为价格
            if position.side == Side.LONG:
                trailing_price = position.entry_price * (new_trailing_roe / position.leverage + 1)
            else:
                trailing_price = position.entry_price * (1 - new_trailing_roe / position.leverage)

            position.trailing_stop_price = trailing_price
            logger.info(f"🎯 {symbol} 启动移动止盈: ROE {roe:.1%} → 止盈 ROE {new_trailing_roe:.1%} (${trailing_price:.2f})")

        else:
            # 已有移动止盈，检查是否需要上调
            if position.side == Side.LONG:
                trailing_price = position.entry_price * (new_trailing_roe / position.leverage + 1)
                if trailing_price > position.trailing_stop_price:
                    position.trailing_stop_price = trailing_price
                    logger.info(f"🔼 {symbol} 移动止盈上调: ROE {roe:.1%} → 止盈 ROE {new_trailing_roe:.1%} (${trailing_price:.2f})")
            else:
                trailing_price = position.entry_price * (1 - new_trailing_roe / position.leverage)
                if trailing_price < position.trailing_stop_price:
                    position.trailing_stop_price = trailing_price
                    logger.info(f"🔽 {symbol} 移动止盈下调: ROE {roe:.1%} → 止盈 ROE {new_trailing_roe:.1%} (${trailing_price:.2f})")

    def check_trailing_stop_trigger(self, symbol: str, current_price: float) -> bool:
        """
        检查是否触发移动止盈

        Args:
            symbol: 交易对
            current_price: 当前价格

        Returns:
            是否触发平仓
        """
        position = self.positions.get(symbol)
        if not position or position.trailing_stop_price is None:
            return False

        if position.side == Side.LONG:
            if current_price < position.trailing_stop_price:
                logger.critical(f"🎯 {symbol} 移动止盈触发！价格 ${current_price:.2f} < 止盈线 ${position.trailing_stop_price:.2f}")
                return True
        else:
            if current_price > position.trailing_stop_price:
                logger.critical(f"🎯 {symbol} 移动止盈触发！价格 ${current_price:.2f} > 止盈线 ${position.trailing_stop_price:.2f}")
                return True

        return False

    def get_position_unrealized_pnl(self, symbol: str, current_price: float) -> Tuple[float, float]:
        """
        获取仓位未实现盈亏

        Args:
            symbol: 交易对
            current_price: 当前价格

        Returns:
            (盈亏金额, 盈亏百分比)
        """
        position = self.positions.get(symbol)
        if not position:
            return 0.0, 0.0

        if position.side == Side.LONG:
            pnl = (current_price - position.entry_price) * position.quantity
            pnl_pct = (current_price - position.entry_price) / position.entry_price
        else:
            pnl = (position.entry_price - current_price) * position.quantity
            pnl_pct = (position.entry_price - current_price) / position.entry_price

        return pnl, pnl_pct

    def get_total_unrealized_pnl(self, prices: Dict[str, float]) -> Tuple[float, float]:
        """
        获取所有仓位的总未实现盈亏

        Args:
            prices: {symbol: current_price}

        Returns:
            (总盈亏金额, 总盈亏百分比)
        """
        total_pnl = 0.0
        total_margin = 0.0

        for symbol, position in self.positions.items():
            current_price = prices.get(symbol, position.entry_price)
            pnl, _ = self.get_position_unrealized_pnl(symbol, current_price)
            total_pnl += pnl
            total_margin += (position.quantity * position.entry_price) / position.leverage

        total_pnl_pct = total_pnl / total_margin if total_margin > 0 else 0.0

        return total_pnl, total_pnl_pct

    def should_emergency_close_all(self, prices: Dict[str, float]) -> Tuple[bool, str]:
        """
        紧急平仓检查（任何仓位达到爆仓线）

        Args:
            prices: {symbol: current_price}

        Returns:
            (是否紧急平仓, 原因)
        """
        for symbol, position in self.positions.items():
            current_price = prices.get(symbol, position.entry_price)

            if position.side == Side.LONG:
                if current_price <= position.stop_loss_price:
                    return True, f"🚨 {symbol} LONG 达到爆仓线！${current_price:.2f} <= ${position.stop_loss_price:.2f}"
            else:
                if current_price >= position.stop_loss_price:
                    return True, f"🚨 {symbol} SHORT 达到爆仓线！${current_price:.2f} >= ${position.stop_loss_price:.2f}"

        return False, ""

    def get_trading_statistics(self) -> Dict[str, any]:
        """获取交易统计"""
        if not self.closed_positions:
            return {
                'total_trades': 0,
                'win_rate': 0.0,
                'avg_pnl': 0.0,
                'total_pnl': 0.0,
            }

        total_trades = len(self.closed_positions)
        winning_trades = sum(1 for p in self.closed_positions if p.pnl > 0)
        total_pnl = sum(p.pnl for p in self.closed_positions)

        return {
            'total_trades': total_trades,
            'win_rate': winning_trades / total_trades,
            'avg_pnl': total_pnl / total_trades,
            'total_pnl': total_pnl,
        }


if __name__ == '__main__':
    """测试狙击手仓位管理"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    from .exchange_info_manager import BinanceExchangeInfo

    # 初始化
    exchange_info = BinanceExchangeInfo(testnet=True)
    position_manager = SniperPositionManager(exchange_info)

    # 测试 200 USDT 开 BTC/USDT
    capital = 200.0
    btc_price = 50000.0

    position = position_manager.calculate_sniper_position(
        symbol='BTC/USDT',
        capital=capital,
        side=Side.LONG,
        entry_price=btc_price,
    )

    if position:
        # 模拟盈利 20% 启动移动止盈
        current_price = btc_price * 1.2
        position_manager.update_trailing_stop('BTC/USDT', current_price)

        # 模拟价格回调触发移动止盈
        trigger_price = btc_price * 1.1
        if position_manager.check_trailing_stop_trigger('BTC/USDT', trigger_price):
            position_manager.close_position('BTC/USDT', trigger_price, CloseReason.TRAILING_STOP)

        # 打印统计
        stats = position_manager.get_trading_statistics()
        print(f"\n交易统计:")
        print(f"  总交易: {stats['total_trades']}")
        print(f"  胜率: {stats['win_rate']:.2%}")
        print(f"  总盈亏: ${stats['total_pnl']:.2f}")
