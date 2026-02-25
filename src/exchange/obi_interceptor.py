"""
v7.0 订单簿失衡拦截器（Order Book Imbalance Interceptor）

防止在流动性有毒时接飞刀
"""
import asyncio
import logging
from typing import Dict, Optional, Tuple
from datetime import datetime
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class OrderBookSnapshot:
    """订单簿快照"""
    symbol: str
    timestamp: datetime

    # 买盘（Bid）
    bid_prices: list  # [price1, price2, ...]
    bid_quantities: list  # [qty1, qty2, ...]
    bid_total: float  # 买盘总量

    # 卖盘（Ask）
    ask_prices: list
    ask_quantities: list
    ask_total: float  # 卖盘总量

    # 订单簿失衡率
    obi: float  # (bid_total - ask_total) / (bid_total + ask_total)

    # 事件时间（用于延迟检测）
    event_time: int  # 毫秒时间戳


class OrderBookImbalanceInterceptor:
    """
    订单簿失衡拦截器

    功能：
    1. 实时订阅 5 档深度
    2. 计算订单簿失衡率（OBI）
    3. 检测流动性是否有毒
    4. 在限价单触发前一秒拦截

    OBI 公式：
    OBI = (V_bid - V_ask) / (V_bid + V_ask)

    阈值：
    - OBI > 0.5：买盘压倒性优势 → 做多安全
    - OBI < -0.5：卖盘压倒性优势 → 做多危险（接飞刀）
    - -0.5 <= OBI <= 0.5：相对平衡 → 正常交易
    """

    # OBI 阈值
    OBI_THRESHOLD_LONG = 0.5  # 做多阈值
    OBI_THRESHOLD_SHORT = -0.5  # 做空阈值

    def __init__(
        self,
        obi_threshold_long: float = 0.5,
        obi_threshold_short: float = -0.5,
    ):
        """
        初始化订单簿失衡拦截器

        Args:
            obi_threshold_long: 做多 OBI 阈值
            obi_threshold_short: 做空 OBI 阈值
        """
        self.obi_threshold_long = obi_threshold_long
        self.obi_threshold_short = obi_threshold_short

        # 订单簿缓存
        self.orderbooks: Dict[str, OrderBookSnapshot] = {}

        # 统计信息
        self.update_count = 0
        self.reject_count = 0

        logger.info(f"订单簿失衡拦截器初始化:")
        logger.info(f"   做多阈值: OBI > {obi_threshold_long}")
        logger.info(f"   做空阈值: OBI < {obi_threshold_short}")

    def update_orderbook(
        self,
        symbol: str,
        bids: list,  # [[price, qty], ...]
        asks: list,
        event_time: int,
    ) -> OrderBookSnapshot:
        """
        更新订单簿

        Args:
            symbol: 交易对
            bids: 买盘 [[price, qty], ...]
            asks: 卖盘 [[price, qty], ...]
            event_time: 事件时间戳（毫秒）

        Returns:
            订单簿快照
        """
        # 解析买盘
        bid_prices = [float(bid[0]) for bid in bids[:5]]  # 取前 5 档
        bid_quantities = [float(bid[1]) for bid in bids[:5]]
        bid_total = sum(bid_quantities)

        # 解析卖盘
        ask_prices = [float(ask[0]) for ask in asks[:5]]
        ask_quantities = [float(ask[1]) for ask in asks[:5]]
        ask_total = sum(ask_quantities)

        # 计算 OBI
        total_volume = bid_total + ask_total
        obi = (bid_total - ask_total) / total_volume if total_volume > 0 else 0

        # 创建快照
        snapshot = OrderBookSnapshot(
            symbol=symbol,
            timestamp=datetime.now(),
            bid_prices=bid_prices,
            bid_quantities=bid_quantities,
            bid_total=bid_total,
            ask_prices=ask_prices,
            ask_quantities=ask_quantities,
            ask_total=ask_total,
            obi=obi,
            event_time=event_time,
        )

        # 更新缓存
        self.orderbooks[symbol] = snapshot
        self.update_count += 1

        return snapshot

    def check_obi_intercept(
        self,
        symbol: str,
        side: str,  # 'LONG' or 'SHORT'
    ) -> Tuple[bool, str, Optional[OrderBookSnapshot]]:
        """
        检查 OBI 拦截

        Args:
            symbol: 交易对
            side: 交易方向

        Returns:
            (是否允许交易, 原因, 订单簿快照)
        """
        # 获取订单簿快照
        snapshot = self.orderbooks.get(symbol)

        if snapshot is None:
            return False, f"❌ 无 {symbol} 订单簿数据", None

        obi = snapshot.obi

        # 检查 OBI
        if side == 'LONG':
            # 做多：卖盘压单过大 → 危险
            if obi < self.obi_threshold_short:
                reason = (
                    f"⛔ OBI 拦截触发：{symbol} 做多危险！"
                    f"OBI = {obi:.2f} < {self.obi_threshold_short} "
                    f"(卖盘压单: {snapshot.ask_total:.2f} > 买盘: {snapshot.bid_total:.2f})"
                )
                logger.critical(reason)
                self.reject_count += 1
                return False, reason, snapshot

        elif side == 'SHORT':
            # 做空：买盘压单过大 → 危险
            if obi > self.obi_threshold_long:
                reason = (
                    f"⛔ OBI 拦截触发：{symbol} 做空危险！"
                    f"OBI = {obi:.2f} > {self.obi_threshold_long} "
                    f"(买盘压单: {snapshot.bid_total:.2f} > 卖盘: {snapshot.ask_total:.2f})"
                )
                logger.critical(reason)
                self.reject_count += 1
                return False, reason, snapshot

        # 通过检查
        reason = (
            f"✅ OBI 检查通过：{symbol} {side} "
            f"OBI = {obi:.2f} "
            f"(买盘: {snapshot.bid_total:.2f}, 卖盘: {snapshot.ask_total:.2f})"
        )
        logger.info(reason)

        return True, reason, snapshot

    def get_orderbook(self, symbol: str) -> Optional[OrderBookSnapshot]:
        """获取订单簿快照"""
        return self.orderbooks.get(symbol)

    def get_stats(self) -> dict:
        """获取统计信息"""
        return {
            'update_count': self.update_count,
            'reject_count': self.reject_count,
            'symbols_tracked': list(self.orderbooks.keys()),
        }


# 全局实例
_obi_interceptor: Optional[OrderBookImbalanceInterceptor] = None


def get_obi_interceptor() -> OrderBookImbalanceInterceptor:
    """获取全局 OBI 拦截器实例"""
    global _obi_interceptor
    if _obi_interceptor is None:
        _obi_interceptor = OrderBookImbalanceInterceptor()
    return _obi_interceptor


if __name__ == '__main__':
    # 测试代码
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - [%(name)s] - %(levelname)s - %(message)s'
    )

    interceptor = OrderBookImbalanceInterceptor()

    # 测试更新订单簿
    snapshot = interceptor.update_orderbook(
        symbol='BTCUSDT',
        bids=[
            [50000, 10],
            [49999, 20],
            [49998, 30],
            [49997, 40],
            [49996, 50],
        ],
        asks=[
            [50001, 100],
            [50002, 150],
            [50003, 200],
            [50004, 250],
            [50005, 300],
        ],
        event_time=int(datetime.now().timestamp() * 1000),
    )

    print(f"\n订单簿快照:")
    print(f"  OBI: {snapshot.obi:.2f}")
    print(f"  买盘总量: {snapshot.bid_total:.2f}")
    print(f"  卖盘总量: {snapshot.ask_total:.2f}")

    # 测试 OBI 拦截
    allowed, reason, _ = interceptor.check_obi_intercept('BTCUSDT', 'LONG')
    print(f"\n允许交易: {allowed}")
    print(f"原因: {reason}")

    # 打印统计
    print(f"\n统计信息:")
    print(interceptor.get_stats())
