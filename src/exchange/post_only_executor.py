"""
v7.0 Post-Only 订单执行器（Post-Only Order Executor）

强制 Maker 费率，防止限价单变成市价单
"""
import logging
from typing import Optional, Dict
from enum import Enum

logger = logging.getLogger(__name__)


class TimeInForce(Enum):
    """订单有效期类型"""
    GTC = "GTC"  # Good Till Cancel - 取消前有效
    IOC = "IOC"  # Immediate Or Cancel - 立即成交或取消
    FOK = "FOK"  # Fill Or Kill - 全部成交或取消
    GTX = "GTX"  # Post-Only - 只做 Maker ⭐关键


class PostOnlyOrderExecutor:
    """
    Post-Only 订单执行器

    功能：
    1. 强制所有限价单使用 Post-Only（GTX）
    2. 如果订单会吃掉盘口流动性 → 直接拒绝
    3. 保证拿到 Maker 费率（0.02%）vs Taker 费率（0.06%）
    4. 避免限价单变成市价单

    Post-Only (GTX) 机制：
    - 如果限价单会立即成交（吃单）→ 币安拒绝订单（REJECTED）
    - 如果限价单进入订单簿（挂单）→ 正常提交
    - 保证不会意外付出 Taker 手续费

    费率对比：
    - Maker: 0.02%（挂单）
    - Taker: 0.06%（吃单）
    - 节省: 0.04%（在 50x 杠杆下非常关键）
    """

    # 手续费率
    MAKER_FEE = 0.0002  # 0.02%
    TAKER_FEE = 0.0006  # 0.06%

    def __init__(self):
        """初始化 Post-Only 订单执行器"""
        self.order_count = 0
        self.rejected_count = 0
        self.maker_fee_saved = 0.0

        logger.info("Post-Only 订单执行器初始化:")
        logger.info(f"   Maker 费率: {self.MAKER_FEE * 100:.2f}%")
        logger.info(f"   Taker 费率: {self.TAKER_FEE * 100:.2f}%")
        logger.info(f"   节省费率: {(self.TAKER_FEE - self.MAKER_FEE) * 100:.2f}%")

    def create_limit_order_params(
        self,
        symbol: str,
        side: str,
        price: float,
        quantity: float,
        force_post_only: bool = True,
    ) -> Dict:
        """
        创建限价单参数（强制 Post-Only）

        Args:
            symbol: 交易对
            side: 方向（'BUY' or 'SELL'）
            price: 价格
            quantity: 数量
            force_post_only: 是否强制 Post-Only

        Returns:
            订单参数字典
        """
        params = {
            'symbol': symbol,
            'side': side,
            'type': 'LIMIT',
            'quantity': quantity,
            'price': price,
        }

        if force_post_only:
            # 强制 Post-Only
            params['timeInForce'] = TimeInForce.GTX.value

            logger.info(f"🎯 创建 Post-Only 订单:")
            logger.info(f"   交易对: {symbol}")
            logger.info(f"   方向: {side}")
            logger.info(f"   价格: ${price:.2f}")
            logger.info(f"   数量: {quantity:.6f}")
            logger.info(f"   TimeInForce: GTX (Post-Only)")
            logger.info(f"   ⚠️ 如果会吃单 → 订单会被拒绝")

        else:
            # 普通 GTC
            params['timeInForce'] = TimeInForce.GTC.value

            logger.warning(f"⚠️ 创建普通限价单（非 Post-Only）:")
            logger.warning(f"   可能会变成市价单吃单")
            logger.warning(f"   Taker 费率: {self.TAKER_FEE * 100:.2f}%")

        self.order_count += 1

        return params

    def handle_order_rejection(
        self,
        symbol: str,
        side: str,
        price: float,
        quantity: float,
        rejection_reason: str,
    ) -> Dict:
        """
        处理订单拒绝（Post-Only 被拒绝）

        Args:
            symbol: 交易对
            side: 方向
            price: 价格
            quantity: 数量
            rejection_reason: 拒绝原因

        Returns:
            处理结果
        """
        self.rejected_count += 1

        logger.critical(f"❌ Post-Only 订单被拒绝:")
        logger.critical(f"   交易对: {symbol}")
        logger.critical(f"   方向: {side}")
        logger.critical(f"   价格: ${price:.2f}")
        logger.critical(f"   数量: {quantity:.6f}")
        logger.critical(f"   拒绝原因: {rejection_reason}")
        logger.critical(f"   说明: 订单会吃掉盘口流动性，违反 Post-Only")

        # 计算节省的手续费
        notional_value = price * quantity
        saved_fee = notional_value * (self.TAKER_FEE - self.MAKER_FEE)
        self.maker_fee_saved += saved_fee

        logger.critical(f"   节省手续费: ${saved_fee:.2f}（避免 Taker 费率）")

        # 策略建议
        logger.info(f"💡 策略建议:")
        logger.info(f"   1. 等待价格回踩到 {price:.2f} 后再挂单")
        logger.info(f"   2. 或者调整挂单价格，使其不会立即成交")

        return {
            'status': 'REJECTED',
            'reason': rejection_reason,
            'saved_fee': saved_fee,
            'action': 'WAIT_OR_ADJUST_PRICE',
        }

    def calculate_fee_savings(
        self,
        notional_value: float,
    ) -> float:
        """
        计算节省的手续费

        Args:
            notional_value: 名义价值

        Returns:
            节省的手续费
        """
        taker_fee = notional_value * self.TAKER_FEE
        maker_fee = notional_value * self.MAKER_FEE
        saved = taker_fee - maker_fee

        return saved

    def get_stats(self) -> dict:
        """获取统计信息"""
        return {
            'order_count': self.order_count,
            'rejected_count': self.rejected_count,
            'maker_fee_saved': self.maker_fee_saved,
            'rejection_rate': self.rejected_count / self.order_count if self.order_count > 0 else 0,
        }


# 全局实例
_post_only_executor: Optional[PostOnlyOrderExecutor] = None


def get_post_only_executor() -> PostOnlyOrderExecutor:
    """获取全局 Post-Only 执行器实例"""
    global _post_only_executor
    if _post_only_executor is None:
        _post_only_executor = PostOnlyOrderExecutor()
    return _post_only_executor


if __name__ == '__main__':
    # 测试代码
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - [%(name)s] - %(levelname)s - %(message)s'
    )

    executor = PostOnlyOrderExecutor()

    # 创建 Post-Only 订单参数
    params = executor.create_limit_order_params(
        symbol='BTCUSDT',
        side='BUY',
        price=50000,
        quantity=0.01,
        force_post_only=True,
    )

    print("\n订单参数:")
    for key, value in params.items():
        print(f"  {key}: {value}")

    # 模拟订单被拒绝
    result = executor.handle_order_rejection(
        symbol='BTCUSDT',
        side='BUY',
        price=50000,
        quantity=0.01,
        rejection_reason='Post-Only order would cross the book',
    )

    print("\n拒绝结果:")
    for key, value in result.items():
        print(f"  {key}: {value}")

    # 计算节省手续费
    saved = executor.calculate_fee_savings(50000 * 0.01)
    print(f"\n节省手续费: ${saved:.2f}")

    # 打印统计
    print("\n统计信息:")
    print(executor.get_stats())
