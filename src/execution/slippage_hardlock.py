"""
滑点硬拦截器（Slippage Hard-Lock）

在 AI 思考期间（3-5秒）检查价格滑点，超过阈值则撤销交易
"""
import time
import logging
from typing import Tuple, Dict, Optional

logger = logging.getLogger(__name__)


class SlippageHardlock:
    """滑点硬拦截器"""

    def __init__(
        self,
        threshold_pct: float = 0.5,
        timeout_sec: float = 5.0
    ):
        """
        初始化滑点硬拦截器

        Args:
            threshold_pct: 滑点阈值（百分比），默认 0.5%
            timeout_sec: 超时时间（秒），默认 5 秒
        """
        self.threshold_pct = threshold_pct
        self.timeout_sec = timeout_sec

        # 锁定的价格 {symbol: (price, timestamp)}
        self._locked_prices: Dict[str, Tuple[float, float]] = {}

        logger.info(
            f"SlippageHardlock 初始化完成 "
            f"(阈值: {threshold_pct}%, 超时: {timeout_sec}s)"
        )

    def lock_trigger_price(self, symbol: str, price: float) -> None:
        """
        锁定触发价格

        Args:
            symbol: 交易对
            price: 触发时的价格
        """
        self._locked_prices[symbol] = (price, time.time())
        logger.info(f"[{symbol}] 🔒 锁定触发价格: ${price:,.2f}")

    def check_slippage(
        self,
        symbol: str,
        current_price: float
    ) -> Tuple[bool, str]:
        """
        检查滑点是否超过阈值

        Args:
            symbol: 交易对
            current_price: 当前最新价格

        Returns:
            (是否通过, 原因)
        """
        # 检查是否锁定
        if symbol not in self._locked_prices:
            return False, f"[{symbol}] 未锁定价格，无法检查滑点"

        locked_price, timestamp = self._locked_prices[symbol]

        # 检查是否超时
        elapsed = time.time() - timestamp
        if elapsed > self.timeout_sec:
            self._cleanup(symbol)
            return False, (
                f"[{symbol}] ⏱️ 决策超时（{elapsed:.1f}s > {self.timeout_sec}s），"
                f"撤销交易"
            )

        # 计算滑点
        slippage_pct = abs(current_price - locked_price) / locked_price * 100
        direction = "↑" if current_price > locked_price else "↓"

        # 判断是否超过阈值
        if slippage_pct > self.threshold_pct:
            self._cleanup(symbol)
            return False, (
                f"[{symbol}] 🚨 滑点过大（{slippage_pct:.2f}% > {self.threshold_pct}%），"
                f"错过最佳击球区！"
                f"触发价 ${locked_price:,.2f} {direction} 当前价 ${current_price:,.2f}，"
                f"耗时 {elapsed:.1f}s"
            )

        # 通过检查
        logger.info(
            f"[{symbol}] ✅ 滑点检查通过: {slippage_pct:.2f}% "
            f"({elapsed:.1f}s)"
        )
        self._cleanup(symbol)
        return True, (
            f"滑点 {slippage_pct:.2f}% 在可接受范围内 "
            f"({elapsed:.1f}s)"
        )

    def get_locked_price(self, symbol: str) -> Optional[float]:
        """
        获取锁定的价格

        Args:
            symbol: 交易对

        Returns:
            锁定的价格，如果未锁定则返回 None
        """
        if symbol not in self._locked_prices:
            return None

        price, _ = self._locked_prices[symbol]
        return price

    def get_elapsed_time(self, symbol: str) -> Optional[float]:
        """
        获取距离锁定的时间

        Args:
            symbol: 交易对

        Returns:
            距离锁定的秒数，如果未锁定则返回 None
        """
        if symbol not in self._locked_prices:
            return None

        _, timestamp = self._locked_prices[symbol]
        return time.time() - timestamp

    def _cleanup(self, symbol: str) -> None:
        """清理锁定的价格"""
        if symbol in self._locked_prices:
            del self._locked_prices[symbol]

    def clear_all(self) -> None:
        """清理所有锁定的价格"""
        self._locked_prices.clear()
        logger.info("已清理所有锁定的价格")

    def get_stats(self) -> Dict:
        """
        获取统计信息

        Returns:
            {
                'locked_count': 当前锁定数量,
                'threshold_pct': 滑点阈值,
                'timeout_sec': 超时时间
            }
        """
        return {
            'locked_count': len(self._locked_prices),
            'threshold_pct': self.threshold_pct,
            'timeout_sec': self.timeout_sec
        }
