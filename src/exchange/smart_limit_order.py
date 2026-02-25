"""
v6.1 智能限价单执行器（Smart Limit Order Executor）

废除市价追高，改用斐波那契回撤位限价单
"""
import logging
from typing import Optional, Tuple
from datetime import datetime
from enum import Enum

logger = logging.getLogger(__name__)


class Side(Enum):
    """交易方向"""
    LONG = "LONG"
    SHORT = "SHORT"


class FibonacciRetracement:
    """
    斐波那契回撤位计算器

    回撤位：
    - 0.236 (浅回撤)
    - 0.382 (中等回撤，推荐入场点)
    - 0.500 (深回撤)
    - 0.618 (黄金分割，强支撑/阻力)
    """

    @staticmethod
    def calculate_retracement_levels(
        high: float,
        low: float,
        side: Side
    ) -> dict:
        """
        计算斐波那契回撤位

        Args:
            high: 最高价
            low: 最低价
            side: 交易方向

        Returns:
            回撤位字典
        """
        diff = high - low

        if side == Side.LONG:
            # 做多：在回撤位挂限价买单
            return {
                '0.236': high - diff * 0.236,
                '0.382': high - diff * 0.382,  # 推荐
                '0.500': high - diff * 0.500,
                '0.618': high - diff * 0.618,
            }
        else:
            # 做空：在回撤位挂限价卖单（反弹位）
            return {
                '0.236': low + diff * 0.236,
                '0.382': low + diff * 0.382,  # 推荐
                '0.500': low + diff * 0.500,
                '0.618': low + diff * 0.618,
            }

    @staticmethod
    def get_entry_price(
        current_price: float,
        breakthrough_price: float,
        side: Side,
        retracement: float = 0.382
    ) -> Tuple[float, str]:
        """
        获取推荐入场价（斐波那契 0.382 回撤位）

        Args:
            current_price: 当前价格
            breakthrough_price: 突破价格
            side: 交易方向
            retracement: 回撤位比例（默认 0.382）

        Returns:
            (入场价, 原因)
        """
        if side == Side.LONG:
            # 做多：突破价 > 旧价格，等待回撤到 0.382
            high = current_price
            low = breakthrough_price

            if high <= low:
                # 价格未突破，使用 VWAP
                return breakthrough_price, "未突破，使用 VWAP"

            entry = high - (high - low) * retracement

            # 确保入场价在合理范围内
            if entry < low:
                entry = low
            elif entry > high:
                entry = high

            reason = f"斐波那契 {retracement:.3f} 回撤位: ${entry:.2f} (区间 ${low:.2f} - ${high:.2f})"

        else:
            # 做空：突破价 < 旧价格，等待反弹到 0.382
            high = breakthrough_price
            low = current_price

            if low >= high:
                # 价格未突破，使用 VWAP
                return breakthrough_price, "未突破，使用 VWAP"

            entry = low + (high - low) * retracement

            # 确保入场价在合理范围内
            if entry < low:
                entry = low
            elif entry > high:
                entry = high

            reason = f"斐波那契 {retracement:.3f} 反弹位: ${entry:.2f} (区间 ${low:.2f} - ${high:.2f})"

        return entry, reason


class SmartLimitOrderExecutor:
    """
    智能限价单执行器

    策略：
    1. 废除市价追高（MARKET_MOMENTUM）
    2. 改用动态限价单追踪斐波那契 0.382 回撤位
    3. 只在价格回踩/反弹到目标位时成交
    4. 超过 5 分钟未成交 → 撤单
    """

    def __init__(self):
        """初始化智能限价单执行器"""
        self.pending_orders = {}

    def create_limit_order(
        self,
        symbol: str,
        side: Side,
        breakthrough_price: float,
        current_price: float,
        vwap: float,
        quantity: float,
        leverage: int
    ) -> Optional[dict]:
        """
        创建智能限价单

        Args:
            symbol: 交易对
            side: 交易方向
            breakthrough_price: 突破价格
            current_price: 当前价格
            vwap: VWAP 价格
            quantity: 数量
            leverage: 杠杆

        Returns:
            订单字典
        """
        # 计算斐波那契 0.382 回撤位
        entry_price, reason = FibonacciRetracement.get_entry_price(
            current_price=current_price,
            breakthrough_price=breakthrough_price,
            side=side,
            retracement=0.382
        )

        logger.info(f"🎯 {symbol} 智能限价单:")
        logger.info(f"   {reason}")
        logger.info(f"   当前价: ${current_price:.2f}")
        logger.info(f"   目标价: ${entry_price:.2f}")
        logger.info(f"   数量: {quantity:.6f}")
        logger.info(f"   杠杆: {leverage}x")

        order = {
            'symbol': symbol,
            'side': side,
            'entry_price': entry_price,
            'quantity': quantity,
            'leverage': leverage,
            'breakthrough_price': breakthrough_price,
            'current_price': current_price,
            'vwap': vwap,
            'timestamp': datetime.now(),
            'reason': reason,
            'status': 'PENDING',
        }

        self.pending_orders[symbol] = order

        return order

    def check_order_fill(
        self,
        symbol: str,
        current_price: float
    ) -> Tuple[bool, Optional[dict]]:
        """
        检查订单是否成交

        Args:
            symbol: 交易对
            current_price: 当前价格

        Returns:
            (是否成交, 订单信息)
        """
        if symbol not in self.pending_orders:
            return False, None

        order = self.pending_orders[symbol]
        entry_price = order['entry_price']
        side = order['side']
        order_time = order['timestamp']

        # 检查超时（5 分钟）
        elapsed = (datetime.now() - order_time).total_seconds() / 60
        if elapsed > 5:
            del self.pending_orders[symbol]
            logger.warning(f"⏰ {symbol} 限价单超时 5 分钟，已撤销")
            return False, None

        # 检查成交
        if side == Side.LONG:
            # 做多：当前价格 <= 入场价（回踩到位）
            if current_price <= entry_price:
                logger.critical(f"✅ {symbol} 做多限价单成交！")
                logger.critical(f"   入场价: ${entry_price:.2f}")
                logger.critical(f"   成交价: ${current_price:.2f}")
                logger.critical(f"   滑点: {((current_price / entry_price) - 1) * 100:+.2f}%")

                del self.pending_orders[symbol]
                return True, order

        else:
            # 做空：当前价格 >= 入场价（反弹到位）
            if current_price >= entry_price:
                logger.critical(f"✅ {symbol} 做空限价单成交！")
                logger.critical(f"   入场价: ${entry_price:.2f}")
                logger.critical(f"   成交价: ${current_price:.2f}")
                logger.critical(f"   滑点: {((current_price / entry_price) - 1) * 100:+.2f}%")

                del self.pending_orders[symbol]
                return True, order

        return False, None

    def cancel_order(self, symbol: str) -> bool:
        """
        取消订单

        Args:
            symbol: 交易对

        Returns:
            是否成功
        """
        if symbol in self.pending_orders:
            del self.pending_orders[symbol]
            logger.warning(f"❌ {symbol} 限价单已取消")
            return True

        return False

    def get_pending_orders(self) -> dict:
        """获取所有挂单"""
        return self.pending_orders.copy()


if __name__ == '__main__':
    # 测试代码
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - [%(name)s] - %(levelname)s - %(message)s'
    )

    executor = SmartLimitOrderExecutor()

    # 测试做多
    order = executor.create_limit_order(
        symbol='BTCUSDT',
        side=Side.LONG,
        breakthrough_price=50000,
        current_price=52000,
        vwap=50500,
        quantity=0.001,
        leverage=50
    )

    print("\n订单信息:")
    print(order)

    # 测试成交检查
    filled, _ = executor.check_order_fill('BTCUSDT', 51000)
    print(f"\n是否成交: {filled}")

    # 继续回踩
    filled, order_info = executor.check_order_fill('BTCUSDT', 50700)
    print(f"是否成交: {filled}")
    if order_info:
        print(f"成交订单: {order_info}")
