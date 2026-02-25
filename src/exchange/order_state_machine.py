"""
v7.0 订单状态机（Order State Machine）

处理部分成交（Partial Fill）地狱
"""
import logging
from typing import Optional, Dict
from datetime import datetime
from enum import Enum
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


class OrderStatus(Enum):
    """订单状态"""
    PENDING = "PENDING"  # 待提交
    NEW = "NEW"  # 已提交，等待成交
    PARTIALLY_FILLED = "PARTIALLY_FILLED"  # 部分成交 ⭐关键
    FILLED = "FILLED"  # 完全成交
    CANCELED = "CANCELED"  # 已撤销
    REJECTED = "REJECTED"  # 被拒绝
    EXPIRED = "EXPIRED"  # 已过期


class OrderSide(Enum):
    """订单方向"""
    BUY = "BUY"
    SELL = "SELL"


class OrderType(Enum):
    """订单类型"""
    LIMIT = "LIMIT"
    MARKET = "MARKET"
    STOP = "STOP"
    STOP_MARKET = "STOP_MARKET"


@dataclass
class Order:
    """订单对象"""
    order_id: str  # 订单 ID
    client_order_id: str  # 客户端订单 ID
    symbol: str  # 交易对
    side: OrderSide  # 方向
    order_type: OrderType  # 类型
    price: float  # 价格
    quantity: float  # 委托数量
    status: OrderStatus = OrderStatus.PENDING  # 状态

    # 成交信息
    filled_quantity: float = 0.0  # 已成交数量
    cumulative_quote_quantity: float = 0.0  # 累计成交金额
    avg_price: float = 0.0  # 平均成交价

    # 时间信息
    create_time: datetime = field(default_factory=datetime.now)
    update_time: datetime = field(default_factory=datetime.now)

    # Post-Only 标记
    is_post_only: bool = False

    # 部分成交处理
    partial_fill_count: int = 0  # 部分成交次数
    last_partial_fill_time: Optional[datetime] = None  # 最后部分成交时间


class OrderStateMachine:
    """
    订单状态机

    功能：
    1. 处理部分成交（PARTIALLY_FILLED）
    2. 自动撤销超时的部分成交订单
    3. 重新计算已成交部分的名义价值和风控参数
    4. 防止计算链条崩溃

    部分成交处理逻辑：
    1. 订单状态变为 PARTIALLY_FILLED
    2. 记录已成交数量和金额
    3. 检查距离上次部分成交的时间
    4. 如果超过 5 分钟 → 撤销剩余挂单
    5. 针对已成交部分重新计算仓位
    """

    # 部分成交超时时间（分钟）
    PARTIAL_FILL_TIMEOUT = 5

    def __init__(self, partial_fill_timeout: int = 5):
        """
        初始化订单状态机

        Args:
            partial_fill_timeout: 部分成交超时时间（分钟）
        """
        self.partial_fill_timeout = partial_fill_timeout

        # 订单缓存
        self.orders: Dict[str, Order] = {}

        # 统计信息
        self.order_count = 0
        self.partial_fill_count = 0
        self.cancel_count = 0

        logger.info(f"订单状态机初始化:")
        logger.info(f"   部分成交超时: {partial_fill_timeout} 分钟")

    def create_order(
        self,
        order_id: str,
        client_order_id: str,
        symbol: str,
        side: OrderSide,
        order_type: OrderType,
        price: float,
        quantity: float,
        is_post_only: bool = False,
    ) -> Order:
        """
        创建订单

        Args:
            order_id: 订单 ID
            client_order_id: 客户端订单 ID
            symbol: 交易对
            side: 方向
            order_type: 类型
            price: 价格
            quantity: 数量
            is_post_only: 是否 Post-Only

        Returns:
            订单对象
        """
        order = Order(
            order_id=order_id,
            client_order_id=client_order_id,
            symbol=symbol,
            side=side,
            order_type=order_type,
            price=price,
            quantity=quantity,
            status=OrderStatus.PENDING,
            is_post_only=is_post_only,
        )

        self.orders[order_id] = order
        self.order_count += 1

        logger.info(f"创建订单: {order_id}")
        logger.info(f"   交易对: {symbol}")
        logger.info(f"   方向: {side.value}")
        logger.info(f"   价格: ${price:.2f}")
        logger.info(f"   数量: {quantity:.6f}")
        logger.info(f"   Post-Only: {is_post_only}")

        return order

    def update_order_status(
        self,
        order_id: str,
        status: OrderStatus,
        filled_quantity: float = 0.0,
        cumulative_quote_quantity: float = 0.0,
        avg_price: float = 0.0,
    ) -> Optional[Order]:
        """
        更新订单状态

        Args:
            order_id: 订单 ID
            status: 新状态
            filled_quantity: 已成交数量
            cumulative_quote_quantity: 累计成交金额
            avg_price: 平均成交价

        Returns:
            更新后的订单对象
        """
        order = self.orders.get(order_id)
        if not order:
            logger.error(f"订单不存在: {order_id}")
            return None

        old_status = order.status
        order.status = status
        order.update_time = datetime.now()

        # 更新成交信息
        if filled_quantity > 0:
            order.filled_quantity = filled_quantity
            order.cumulative_quote_quantity = cumulative_quote_quantity
            order.avg_price = avg_price

        # 处理部分成交
        if status == OrderStatus.PARTIALLY_FILLED:
            order.partial_fill_count += 1
            order.last_partial_fill_time = datetime.now()
            self.partial_fill_count += 1

            logger.warning(f"⚠️ 订单部分成交: {order_id}")
            logger.warning(f"   委托数量: {order.quantity:.6f}")
            logger.warning(f"   已成交: {filled_quantity:.6f} ({filled_quantity / order.quantity * 100:.1f}%)")
            logger.warning(f"   平均价格: ${avg_price:.2f}")
            logger.warning(f"   部分成交次数: {order.partial_fill_count}")

        # 完全成交
        elif status == OrderStatus.FILLED:
            logger.critical(f"✅ 订单完全成交: {order_id}")
            logger.critical(f"   成交数量: {filled_quantity:.6f}")
            logger.critical(f"   平均价格: ${avg_price:.2f}")
            logger.critical(f"   成交金额: ${cumulative_quote_quantity:.2f}")

        # 状态变更日志
        logger.info(f"订单状态变更: {order_id} {old_status.value} → {status.value}")

        return order

    def check_partial_fill_timeout(
        self,
        order_id: str
    ) -> Tuple[bool, Optional[Order]]:
        """
        检查部分成交超时

        Args:
            order_id: 订单 ID

        Returns:
            (是否需要撤销, 订单对象)
        """
        order = self.orders.get(order_id)
        if not order:
            return False, None

        # 只检查部分成交状态的订单
        if order.status != OrderStatus.PARTIALLY_FILLED:
            return False, order

        # 检查距离上次部分成交的时间
        if order.last_partial_fill_time is None:
            return False, order

        elapsed = (datetime.now() - order.last_partial_fill_time).total_seconds() / 60

        if elapsed > self.partial_fill_timeout:
            logger.warning(f"⏰ 订单部分成交超时: {order_id}")
            logger.warning(f"   超时时间: {elapsed:.1f} 分钟 > {self.partial_fill_timeout} 分钟")
            logger.warning(f"   撤销剩余挂单")

            self.cancel_count += 1
            return True, order

        return False, order

    def calculate_partial_position(
        self,
        order_id: str
    ) -> Optional[Dict]:
        """
        计算部分成交的仓位信息

        Args:
            order_id: 订单 ID

        Returns:
            仓位信息字典
        """
        order = self.orders.get(order_id)
        if not order:
            return None

        # 计算已成交部分的名义价值
        notional_value = order.cumulative_quote_quantity

        # 计算剩余未成交数量
        remaining_quantity = order.quantity - order.filled_quantity

        # 计算成交比例
        fill_ratio = order.filled_quantity / order.quantity if order.quantity > 0 else 0

        return {
            'order_id': order_id,
            'symbol': order.symbol,
            'side': order.side.value,
            'order_quantity': order.quantity,
            'filled_quantity': order.filled_quantity,
            'remaining_quantity': remaining_quantity,
            'fill_ratio': fill_ratio,
            'avg_price': order.avg_price,
            'notional_value': notional_value,
            'partial_fill_count': order.partial_fill_count,
        }

    def cancel_order(self, order_id: str) -> bool:
        """
        撤销订单

        Args:
            order_id: 订单 ID

        Returns:
            是否成功
        """
        order = self.orders.get(order_id)
        if not order:
            return False

        order.status = OrderStatus.CANCELED
        order.update_time = datetime.now()

        logger.warning(f"❌ 订单已撤销: {order_id}")

        return True

    def get_order(self, order_id: str) -> Optional[Order]:
        """获取订单"""
        return self.orders.get(order_id)

    def get_stats(self) -> dict:
        """获取统计信息"""
        return {
            'order_count': self.order_count,
            'partial_fill_count': self.partial_fill_count,
            'cancel_count': self.cancel_count,
            'active_orders': len([o for o in self.orders.values() if o.status in [OrderStatus.NEW, OrderStatus.PARTIALLY_FILLED]]),
        }


# 需要导入 Tuple
from typing import Tuple


# 全局实例
_order_state_machine: Optional[OrderStateMachine] = None


def get_order_state_machine() -> OrderStateMachine:
    """获取全局订单状态机实例"""
    global _order_state_machine
    if _order_state_machine is None:
        _order_state_machine = OrderStateMachine()
    return _order_state_machine


if __name__ == '__main__':
    # 测试代码
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - [%(name)s] - %(levelname)s - %(message)s'
    )

    sm = OrderStateMachine()

    # 创建订单
    order = sm.create_order(
        order_id='12345',
        client_order_id='client_12345',
        symbol='BTCUSDT',
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        price=50000,
        quantity=0.01,
        is_post_only=True,
    )

    # 模拟部分成交
    sm.update_order_status(
        order_id='12345',
        status=OrderStatus.PARTIALLY_FILLED,
        filled_quantity=0.002,
        cumulative_quote_quantity=100,
        avg_price=50000,
    )

    # 计算部分仓位
    position_info = sm.calculate_partial_position('12345')
    print("\n部分仓位信息:")
    for key, value in position_info.items():
        print(f"  {key}: {value}")

    # 打印统计
    print("\n统计信息:")
    print(sm.get_stats())
