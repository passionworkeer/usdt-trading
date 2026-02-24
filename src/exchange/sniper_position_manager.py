"""
v5.0: 狙击手仓位管理器（Sniper Position Manager）

针对 200 USDT 超小资金的孤注一掷模型：
- 20%-50% 高杠杆单次开仓
- 把爆仓线当止损线
- 只做极低频、极高置信度交易
"""
import logging
from typing import Dict, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime

from .exchange_info_manager import BinanceExchangeInfo

logger = logging.getLogger(__name__)


@dataclass
class SniperPosition:
    """狙击手仓位"""
    symbol: str
    side: str  # 'LONG' or 'SHORT'
    entry_price: float
    quantity: float
    leverage: int
    stop_loss_price: float  # 爆仓线 = 止损线
    take_profit_price: float
    trailing_stop_price: Optional[float] = None  # 移动止盈
    entry_time: datetime = None
    pnl: float = 0
    status: str = 'OPEN'  # OPEN, CLOSED, LIQUIDATED


class SniperPositionManager:
    """
    v5.0 狙击手仓位管理器

    核心理念：
    1. 孤注一掷 - 50% 资金高杠杆单次开仓
    2. 爆仓即止损 - 不设传统止损，直接打到爆仓线
    3. 移动止盈 - 让利润奔跑，追求 1:5 盈亏比
    4. 极低频 - 一周最多 1-2 次开仓机会
    """

    def __init__(self, exchange_info: BinanceExchangeInfo):
        """
        初始化仓位管理器

        Args:
            exchange_info: exchangeInfo 管理器
        """
        self.exchange_info = exchange_info
        self.positions: Dict[str, SniperPosition] = {}
        self.closed_positions: list = []

        # v5.0 狙击手参数
        self.position_ratio = 0.5  # 每次用 50% 资金
        self.max_positions = 1  # 同时只持有 1 个仓位
        self.target_rr_ratio = 5.0  # 目标盈亏比 1:5

        logger.info("✅ 狙击手仓位管理器已初始化")
        logger.info(f"  开仓比例: {self.position_ratio*100:.0f}%")
        logger.info(f"  最大并发仓位: {self.max_positions}")
        logger.info(f"  目标盈亏比: 1:{self.target_rr_ratio}")

    def calculate_sniper_position(self, symbol: str, capital: float,
                                  side: str, entry_price: float,
                                  stop_distance_pct: float = 0.02) -> Optional[SniperPosition]:
        """
        计算狙击手仓位（孤注一掷模型）

        策略：
        1. 使用 50% 资金作为保证金
        2. 自动调整杠杆满足 MIN_NOTIONAL
        3. 爆仓线距离 = 止损距离（2%-5%）
        4. 目标盈利 = 5 × 止损距离（10%-25%）

        Args:
            symbol: 交易对
            capital: 总资金（USDT）
            side: 'LONG' or 'SHORT'
            entry_price: 入场价格
            stop_distance_pct: 爆仓距离百分比（默认 2%）

        Returns:
            SniperPosition 对象，如果计算失败返回 None
        """
        # 计算可用保证金（50% 资金）
        margin = capital * self.position_ratio

        # 自动计算杠杆和数量
        quantity, leverage, feasible = self.exchange_info.calculate_min_quantity_for_capital(
            symbol, margin, leverage=20
        )

        if not feasible:
            logger.error(f"❌ 资金不足，无法开仓 {symbol}")
            return None

        # 计算爆仓线（= 止损线）
        if side == 'LONG':
            stop_loss_price = entry_price * (1 - stop_distance_pct)
            take_profit_price = entry_price * (1 + stop_distance_pct * self.target_rr_ratio)
        else:  # SHORT
            stop_loss_price = entry_price * (1 + stop_distance_pct)
            take_profit_price = entry_price * (1 - stop_distance_pct * self.target_rr_ratio)

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

        # 验证订单
        valid, reason = self.exchange_info.validate_order(symbol, quantity, entry_price)
        if not valid:
            logger.error(f"❌ 订单验证失败: {reason}")
            return None

        # 打印仓位信息
        self._print_position_summary(position, capital)

        return position

    def _print_position_summary(self, position: SniperPosition, capital: float):
        """打印仓位摘要"""
        notional = position.quantity * position.entry_price
        margin_used = notional / position.leverage

        logger.info(f"\n{'='*60}")
        logger.info(f"🎯 狙击手仓位计算结果")
        logger.info(f"{'='*60}")
        logger.info(f"交易对: {position.symbol}")
        logger.info(f"方向: {position.side}")
        logger.info(f"杠杆: {position.leverage}x")
        logger.info(f"入场价: ${position.entry_price:.2f}")
        logger.info(f"数量: {position.quantity:.6f}")
        logger.info(f"名义价值: ${notional:.2f}")
        logger.info(f"占用保证金: ${margin_used:.2f} ({margin_used/capital*100:.1f}% 资金)")
        logger.info(f"爆仓线(止损): ${position.stop_loss_price:.2f} ({abs(position.stop_loss_price/position.entry_price - 1)*100:.2f}%)")
        logger.info(f"目标止盈: ${position.take_profit_price:.2f} ({abs(position.take_profit_price/position.entry_price - 1)*100:.2f}%)")
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

    def open_position(self, position: SniperPosition):
        """开仓"""
        self.positions[position.symbol] = position
        logger.info(f"✅ 已开仓 {position.symbol} {position.side}")

    def close_position(self, symbol: str, exit_price: float,
                      reason: str = 'MANUAL') -> Optional[SniperPosition]:
        """
        平仓

        Args:
            symbol: 交易对
            exit_price: 出场价格
            reason: 平仓原因（MANUAL, STOP_LOSS, TAKE_PROFIT, TRAILING_STOP）

        Returns:
            已平仓的 SniperPosition，如果不存在返回 None
        """
        position = self.positions.pop(symbol, None)
        if not position:
            logger.warning(f"⚠️ 未找到 {symbol} 仓位")
            return None

        # 计算盈亏
        if position.side == 'LONG':
            pnl = (exit_price - position.entry_price) * position.quantity
        else:  # SHORT
            pnl = (position.entry_price - exit_price) * position.quantity

        position.pnl = pnl
        position.status = 'CLOSED'

        # 记录到历史
        self.closed_positions.append(position)

        logger.info(f"✅ 已平仓 {symbol} {position.side}")
        logger.info(f"  出场价: ${exit_price:.2f}")
        logger.info(f"  盈亏: ${pnl:+.2f} ({pnl/position.entry_price/position.quantity*100:+.2f}%)")
        logger.info(f"  原因: {reason}")

        return position

    def update_trailing_stop(self, symbol: str, current_price: float,
                            trailing_distance_pct: float = 0.05):
        """
        v5.0 核心：更新移动止盈（Trailing Stop）

        逻辑：
        - 只有盈利时才启动移动止盈
        - 移动距离 = 当前价格 × 5%
        - 永远只向上移动，不向下移动

        Args:
            symbol: 交易对
            current_price: 当前价格
            trailing_distance_pct: 移动距离百分比（默认 5%）
        """
        position = self.positions.get(symbol)
        if not position:
            return

        # 计算当前盈亏
        if position.side == 'LONG':
            unrealized_pnl_pct = (current_price - position.entry_price) / position.entry_price
        else:  # SHORT
            unrealized_pnl_pct = (position.entry_price - current_price) / position.entry_price

        # 只有盈利超过 10% 才启动移动止盈
        if unrealized_pnl_pct < 0.1:
            return

        # 计算新的移动止盈价格
        if position.side == 'LONG':
            new_trailing_stop = current_price * (1 - trailing_distance_pct)

            # 只向上移动，不向下
            if position.trailing_stop_price is None or new_trailing_stop > position.trailing_stop_price:
                position.trailing_stop_price = new_trailing_stop
                logger.info(f"🔼 {symbol} 移动止盈上调: ${new_trailing_stop:.2f}")
        else:  # SHORT
            new_trailing_stop = current_price * (1 + trailing_distance_pct)

            # 只向下移动，不向上
            if position.trailing_stop_price is None or new_trailing_stop < position.trailing_stop_price:
                position.trailing_stop_price = new_trailing_stop
                logger.info(f"🔽 {symbol} 移动止盈下调: ${new_trailing_stop:.2f}")

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

        if position.side == 'LONG':
            # 做多：价格跌破移动止盈线
            if current_price < position.trailing_stop_price:
                logger.critical(f"🎯 {symbol} 移动止盈触发！价格 ${current_price:.2f} < 止盈线 ${position.trailing_stop_price:.2f}")
                return True
        else:  # SHORT
            # 做空：价格涨破移动止盈线
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
            return 0, 0

        if position.side == 'LONG':
            pnl = (current_price - position.entry_price) * position.quantity
            pnl_pct = (current_price - position.entry_price) / position.entry_price
        else:  # SHORT
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
        total_pnl = 0
        total_margin = 0

        for symbol, position in self.positions.items():
            current_price = prices.get(symbol, position.entry_price)
            pnl, _ = self.get_position_unrealized_pnl(symbol, current_price)
            total_pnl += pnl
            total_margin += (position.quantity * position.entry_price) / position.leverage

        total_pnl_pct = total_pnl / total_margin if total_margin > 0 else 0

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

            # 检查是否达到爆仓线（= 止损线）
            if position.side == 'LONG':
                if current_price <= position.stop_loss_price:
                    return True, f"🚨 {symbol} LONG 达到爆仓线！${current_price:.2f} <= ${position.stop_loss_price:.2f}"
            else:  # SHORT
                if current_price >= position.stop_loss_price:
                    return True, f"🚨 {symbol} SHORT 达到爆仓线！${current_price:.2f} >= ${position.stop_loss_price:.2f}"

        return False, ""

    def get_trading_statistics(self) -> Dict:
        """获取交易统计"""
        if not self.closed_positions:
            return {
                'total_trades': 0,
                'win_rate': 0,
                'avg_pnl': 0,
                'total_pnl': 0,
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
    capital = 200  # USDT
    btc_price = 50000  # 假设 BTC 价格

    position = position_manager.calculate_sniper_position(
        symbol='BTC/USDT',
        capital=capital,
        side='LONG',
        entry_price=btc_price,
        stop_distance_pct=0.02  # 2% 爆仓距离
    )

    if position:
        # 模拟盈利 20% 启动移动止盈
        current_price = btc_price * 1.2
        position_manager.update_trailing_stop('BTC/USDT', current_price)

        # 模拟价格回调触发移动止盈
        trigger_price = btc_price * 1.1
        if position_manager.check_trailing_stop_trigger('BTC/USDT', trigger_price):
            position_manager.close_position('BTC/USDT', trigger_price, reason='TRAILING_STOP')

        # 打印统计
        stats = position_manager.get_trading_statistics()
        print(f"\n交易统计:")
        print(f"  总交易: {stats['total_trades']}")
        print(f"  胜率: {stats['win_rate']:.2%}")
        print(f"  总盈亏: ${stats['total_pnl']:.2f}")
