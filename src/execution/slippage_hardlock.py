"""
滑点硬拦截器（Slippage Hard-Lock）

在 AI 思考期间（3-5秒）检查价格滑点，超过阈值则撤销交易
"""
import time
import logging
import statistics
from typing import Tuple, Dict, Optional, Callable

logger = logging.getLogger(__name__)


class SlippageHardlock:
    """滑点硬拦截器"""

    def __init__(
        self,
        base_threshold_pct: float = 0.5,
        timeout_sec: float = 5.0,
        volatility_multiplier: float = 2.0
    ):
        """
        初始化滑点硬拦截器

        Args:
            base_threshold_pct: 基础滑点阈值（百分比），默认 0.5%
            timeout_sec: 超时时间（秒），默认 5 秒
            volatility_multiplier: 波动率乘数，用于动态调整阈值
        """
        self.base_threshold_pct = base_threshold_pct
        self.timeout_sec = timeout_sec
        self.volatility_multiplier = volatility_multiplier

        # 动态阈值缓存 {symbol: (threshold, timestamp)}
        self._dynamic_thresholds: Dict[str, Tuple[float, float]] = {}

        # 锁定的价格 {symbol: (price, timestamp)}
        self._locked_prices: Dict[str, Tuple[float, float]] = {}

        # 波动率计算函数（外部注入）
        self._volatility_calculator: Optional[Callable] = None

        logger.info(
            f"SlippageHardlock 初始化完成 "
            f"(基础阈值: {base_threshold_pct}%, 超时: {timeout_sec}s, "
            f"波动率乘数: {volatility_multiplier}x)"
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
        current_price: float,
        exchange=None
    ) -> Tuple[bool, str]:
        """
        检查滑点是否超过阈值

        Args:
            symbol: 交易对
            current_price: 当前最新价格
            exchange: 交易所实例（可选，用于计算动态阈值）

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

        # 获取动态阈值（如果有 exchange）
        if exchange is not None:
            threshold_pct = self.get_dynamic_threshold(exchange, symbol)
        else:
            threshold_pct = self.get_threshold(symbol)

        # 计算滑点
        slippage_pct = abs(current_price - locked_price) / locked_price * 100
        direction = "↑" if current_price > locked_price else "↓"

        # 判断是否超过阈值
        if slippage_pct > threshold_pct:
            self._cleanup(symbol)
            return False, (
                f"[{symbol}] 🚨 滑点过大（{slippage_pct:.2f}% > {threshold_pct:.2f}%），"
                f"错过最佳击球区！"
                f"触发价 ${locked_price:,.2f} {direction} 当前价 ${current_price:,.2f}，"
                f"耗时 {elapsed:.1f}s"
            )

        # 通过检查
        logger.info(
            f"[{symbol}] ✅ 滑点检查通过: {slippage_pct:.2f}% (阈值: {threshold_pct:.2f}%) "
            f"({elapsed:.1f}s)"
        )
        self._cleanup(symbol)
        return True, (
            f"滑点 {slippage_pct:.2f}% 在可接受范围内 (阈值 {threshold_pct:.2f}%) "
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

    def set_volatility_calculator(self, calculator: Callable) -> None:
        """
        设置波动率计算函数

        Args:
            calculator: 波动率计算函数，签名: (symbol: str) -> float (返回百分比)
        """
        self._volatility_calculator = calculator
        logger.info("波动率计算函数已设置")

    def calculate_volatility(
        self,
        exchange,
        symbol: str,
        periods: int = 24
    ) -> float:
        """
        计算 24 小时历史波动率（百分比）

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
                logger.warning(f"{symbol} K线数据不足，使用默认波动率 1%")
                return 1.0

            # 计算收益率
            returns = [(closes[i] - closes[i-1]) / closes[i-1] for i in range(1, len(closes))]

            if len(returns) < 2:
                return 1.0

            # 计算标准差
            volatility = statistics.stdev(returns)

            return volatility * 100  # 转换为百分比

        except Exception as e:
            logger.warning(f"波动率计算失败: {e}，使用默认波动率 1%")
            return 1.0

    def get_dynamic_threshold(self, exchange, symbol: str) -> float:
        """
        获取动态滑点阈值

        根据历史波动率动态调整：
        dynamic_threshold = base_threshold + (volatility * multiplier)

        例如：
        - 波动率 1% → 阈值 = 0.5% + 2% = 2.5%
        - 波动率 2% → 阈值 = 0.5% + 4% = 4.5%
        - 波动率 5% → 阈值 = 0.5% + 10% = 10.5%

        Args:
            exchange: 交易所实例
            symbol: 交易对

        Returns:
            动态滑点阈值（百分比）
        """
        # 如果有外部注入的波动率计算函数，优先使用
        if self._volatility_calculator:
            volatility = self._volatility_calculator(symbol)
        else:
            # 使用内置计算
            volatility = self.calculate_volatility(exchange, symbol)

        # 动态阈值 = 基础阈值 + 波动率 * 乘数
        dynamic_threshold = self.base_threshold_pct + (volatility * self.volatility_multiplier)

        # 缓存动态阈值（5分钟有效）
        self._dynamic_thresholds[symbol] = (dynamic_threshold, time.time())

        logger.info(
            f"[{symbol}] 动态滑点阈值计算: "
            f"基础 {self.base_threshold_pct}% + 波动率 {volatility:.2f}% x {self.volatility_multiplier} = {dynamic_threshold:.2f}%"
        )

        return dynamic_threshold

    def get_threshold(self, symbol: str) -> float:
        """
        获取当前阈值（优先使用缓存）

        Args:
            symbol: 交易对

        Returns:
            滑点阈值（百分比）
        """
        if symbol in self._dynamic_thresholds:
            threshold, timestamp = self._dynamic_thresholds[symbol]
            # 缓存有效期 5 分钟
            if time.time() - timestamp < 300:
                return threshold

        # 没有缓存，返回基础阈值
        return self.base_threshold_pct

    def get_stats(self) -> Dict:
        """
        获取统计信息

        Returns:
            {
                'locked_count': 当前锁定数量,
                'base_threshold_pct': 基础滑点阈值,
                'timeout_sec': 超时时间,
                'volatility_multiplier': 波动率乘数
            }
        """
        return {
            'locked_count': len(self._locked_prices),
            'base_threshold_pct': self.base_threshold_pct,
            'timeout_sec': self.timeout_sec,
            'volatility_multiplier': self.volatility_multiplier
        }
