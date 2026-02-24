"""
实时波动率熔断系统 v4.0

核心功能：
1. 实时监控 BTC 1分钟真实波动率
2. 3σ 统计检测（超过 3 个标准差触发熔断）
3. 熔断期间禁止新开仓，强制进入防守模式
4. 支持 Deribit DVOL 隐含波动率监控（可选）
"""
import logging
import asyncio
import numpy as np
import pandas as pd
from typing import Tuple, Optional, List
from datetime import datetime, timedelta
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class CircuitBreakerState:
    """熔断状态"""
    is_triggered: bool
    trigger_time: Optional[datetime]
    reason: str
    volatility_1m: float
    volatility_threshold: float
    current_positions: List[str]  # 当前持仓列表


class RealTimeVolatilityMonitor:
    """
    实时波动率监控器

    监控逻辑：
    1. 计算最近 5 分钟的波动率
    2. 与历史波动率分布比较
    3. 如果超过 3σ → 触发熔断
    """

    def __init__(self,
                 volatility_window: int = 5,  # 5 分钟窗口
                 historical_window: int = 100,  # 100 根 K 线历史
                 sigma_threshold: float = 3.0):  # 3σ 阈值
        """
        初始化波动率监控器

        Args:
            volatility_window: 波动率计算窗口（分钟）
            historical_window: 历史统计窗口
            sigma_threshold: 标准差倍数阈值
        """
        self.volatility_window = volatility_window
        self.historical_window = historical_window
        self.sigma_threshold = sigma_threshold

        self.historical_volatilities: List[float] = []
        self.state = CircuitBreakerState(
            is_triggered=False,
            trigger_time=None,
            reason="",
            volatility_1m=0,
            volatility_threshold=0,
            current_positions=[],
        )

    def calculate_realized_volatility(self, highs: pd.Series, lows: pd.Series, closes: pd.Series) -> float:
        """
        计算已实现波动率（Realized Volatility）

        使用 Garman-Klass 类似方法：
        RV = (High - Low) / Close

        Args:
            highs: 最高价序列
            lows: 最低价序列
            closes: 收盘价序列

        Returns:
            波动率（百分比）
        """
        if len(closes) == 0:
            return 0

        recent_high = highs.iloc[-1]
        recent_low = lows.iloc[-1]
        close = closes.iloc[-1]

        if close == 0:
            return 0

        volatility = (recent_high - recent_low) / close * 100
        return volatility

    def update_historical_volatilities(self, df: pd.DataFrame):
        """
        更新历史波动率分布

        Args:
            df: 包含 high, low, close 列的 DataFrame
        """
        volatilities = []

        for i in range(self.historical_window, len(df)):
            highs = df['high'].iloc[i-self.historical_window:i]
            lows = df['low'].iloc[i-self.historical_window:i]
            closes = df['close'].iloc[i-self.historical_window:i]

            vol = self.calculate_realized_volatility(highs, lows, closes)
            volatilities.append(vol)

        self.historical_volatilities = volatilities

        logger.info(f"已更新历史波动率分布: {len(volatilities)} 个数据点")
        logger.info(f"  均值: {np.mean(volatilities):.2f}%")
        logger.info(f"  标准差: {np.std(volatilities):.2f}%")

    def check_circuit_breaker(self, df: pd.DataFrame, order_executor=None) -> CircuitBreakerState:
        """
        v4.1: 检查是否触发熔断（立即撤单优先！）

        优先级：
        1. 🔴 第一步：撤销所有未成交订单（Cancel All Open Orders）
        2. 🛑 第二步：禁止新开仓
        3. ⚠️ 第三步：评估是否需要紧急平仓

        Args:
            df: 最新的 K 线数据
            order_executor: 订单执行器（用于撤单）

        Returns:
            熔断状态
        """
        if len(df) < self.historical_window + self.volatility_window:
            return CircuitBreakerState(
                is_triggered=False,
                trigger_time=None,
                reason="数据不足",
                volatility_1m=0,
                volatility_threshold=0,
                current_positions=[],
            )

        # 更新历史波动率
        self.update_historical_volatilities(df)

        # 计算当前波动率
        current_volatility = self.calculate_realized_volatility(
            df['high'].iloc[-self.volatility_window:],
            df['low'].iloc[-self.volatility_window:],
            df['close'].iloc[-self.volatility_window:]
        )

        # 计算统计阈值
        mean_vol = np.mean(self.historical_volatilities)
        std_vol = np.std(self.historical_volatilities)
        threshold = mean_vol + self.sigma_threshold * std_vol

        # 判断是否触发熔断
        is_triggered = current_volatility > threshold

        if is_triggered and not self.state.is_triggered:
            # 🔴🔴🔴 首次触发熔断 - 立即撤单！🔴🔴🔴
            logger.critical(f"🔴🔴🔴 波动率熔断触发！🔴🔴🔴")
            logger.critical(f"当前波动率: {current_volatility:.2f}%")
            logger.critical(f"熔断阈值: {threshold:.2f}% (均值 {mean_vol:.2f}% + {self.sigma_threshold}σ)")
            logger.critical(f"超过阈值: {current_volatility - threshold:.2f}%")

            # v4.1: 第一步 - 撤销所有未成交订单（防止 Adverse Selection）
            if order_executor:
                try:
                    # 同步撤单
                    if hasattr(order_executor, 'cancel_all_orders'):
                        for symbol in ['BTC/USDT', 'ETH/USDT']:  # TODO: 从持仓列表获取
                            try:
                                order_executor.cancel_all_orders(symbol)
                                logger.critical(f"✅ 已撤销 {symbol} 所有订单（防止成为流动性活靶子）")
                            except Exception as e:
                                logger.error(f"撤单失败 {symbol}: {e}")

                    # 异步撤单
                    elif hasattr(order_executor, 'cancel_all_orders'):
                        import asyncio
                        async def cancel_all():
                            for symbol in ['BTC/USDT', 'ETH/USDT']:
                                await order_executor.cancel_all_orders(symbol)
                                logger.critical(f"✅ 已撤销 {symbol} 所有订单（异步）")

                        # 如果在事件循环中
                        try:
                            loop = asyncio.get_running_loop()
                            asyncio.create_task(cancel_all())
                        except RuntimeError:
                            # 如果没有事件循环，新建一个
                            asyncio.run(cancel_all())

                except Exception as e:
                    logger.error(f"撤单失败: {e}")

            logger.critical(f"🛑 立即停止所有新开仓！进入防守模式！")

            self.state = CircuitBreakerState(
                is_triggered=True,
                trigger_time=datetime.now(),
                reason=f"波动率 {current_volatility:.2f}% 超过 {threshold:.2f}%",
                volatility_1m=current_volatility,
                volatility_threshold=threshold,
                current_positions=[],
            )
        elif not is_triggered and self.state.is_triggered:
            # 熔断解除
            logger.info(f"✅ 波动率熔断解除")
            logger.info(f"当前波动率: {current_volatility:.2f}%")
            logger.info(f"熔断阈值: {threshold:.2f}%")

            self.state = CircuitBreakerState(
                is_triggered=False,
                trigger_time=None,
                reason="",
                volatility_1m=current_volatility,
                volatility_threshold=threshold,
                current_positions=[],
            )
        else:
            # 更新状态
            self.state.volatility_1m = current_volatility
            self.state.volatility_threshold = threshold

        return self.state

    def is_new_order_allowed(self, symbol: str) -> Tuple[bool, str]:
        """
        检查是否允许新开仓

        Args:
            symbol: 交易对

        Returns:
            (是否允许, 原因)
        """
        if self.state.is_triggered:
            return False, f"🔴 熔断中！波动率 {self.state.volatility_1m:.2f}% 超过阈值 {self.state.volatility_threshold:.2f}%，禁止新开仓"

        # 检查是否接近熔断阈值（2.5σ）
        if len(self.historical_volatilities) > 0:
            mean_vol = np.mean(self.historical_volatilities)
            std_vol = np.std(self.historical_volatilities)
            warning_threshold = mean_vol + 2.5 * std_vol

            if self.state.volatility_1m > warning_threshold:
                return False, f"⚠️ 接近熔断！波动率 {self.state.volatility_1m:.2f}% 接近警告阈值 {warning_threshold:.2f}%"

        return True, "OK"

    def should_emergency_close_all(self) -> bool:
        """
        判断是否需要紧急平仓

        Returns:
            是否需要紧急平仓
        """
        # 如果波动率超过 4σ，建议紧急平仓
        if len(self.historical_volatilities) > 0:
            mean_vol = np.mean(self.historical_volatilities)
            std_vol = np.std(self.historical_volatilities)
            emergency_threshold = mean_vol + 4 * std_vol

            if self.state.volatility_1m > emergency_threshold:
                logger.critical(f"🚨🚨🚨 极端波动率！建议立即平仓！🚨🚨🚨")
                logger.critical(f"当前波动率: {self.state.volatility_1m:.2f}%")
                logger.critical(f"紧急阈值: {emergency_threshold:.2f}% (4σ)")
                return True

        return False


class DeribitDVOLMonitor:
    """
    Deribit DVOL 隐含波动率监控（可选）

    DVOL 是 Deribit 的 BTC 隐含波动率指数，反映市场对未来波动的预期
    """

    def __init__(self):
        """初始化 DVOL 监控器"""
        self.dvol_value: Optional[float] = None
        self.last_update: Optional[datetime] = None

    async def fetch_dvol(self) -> Optional[float]:
        """
        获取 DVOL 值

        Returns:
            DVOL 值（百分比）
        """
        try:
            import aiohttp

            url = "https://www.deribit.com/api/v2/public/get_volatility_index_data"
            params = {"currency": "BTC", "index_name": "btc_cvol"}

            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params) as response:
                    data = await response.json()

                    if data.get('result'):
                        self.dvol_value = data['result'].get('volatility_index')
                        self.last_update = datetime.now()
                        return self.dvol_value

        except Exception as e:
            logger.warning(f"获取 DVOL 失败: {e}")

        return None


if __name__ == '__main__':
    # 测试代码
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # 创建模拟数据
    dates = pd.date_range(start='2024-01-01', periods=200, freq='1min')
    np.random.seed(42)

    # 正常市场数据（波动率约 0.5%）
    normal_returns = np.random.normal(0, 0.001, 200)
    normal_prices = 50000 * (1 + normal_returns).cumprod()

    # 构造 OHLC
    df = pd.DataFrame({
        'timestamp': dates,
        'close': normal_prices,
    })
    df.set_index('timestamp', inplace=True)
    df['high'] = df['close'] * (1 + np.abs(np.random.normal(0, 0.001, 200)))
    df['low'] = df['close'] * (1 - np.abs(np.random.normal(0, 0.001, 200)))

    # 添加极端波动（最后 5 分钟）
    extreme_vol = 0.05  # 5% 波动
    df.iloc[-5:, df.columns.get_loc('high')] = df['close'].iloc[-5] * (1 + extreme_vol)
    df.iloc[-5:, df.columns.get_loc('low')] = df['close'].iloc[-5] * (1 - extreme_vol)

    # 测试监控器
    monitor = RealTimeVolatilityMonitor()

    # 检查熔断
    state = monitor.check_circuit_breaker(df)

    print(f"\n熔断状态: {state.is_triggered}")
    print(f"当前波动率: {state.volatility_1m:.2f}%")
    print(f"熔断阈值: {state.volatility_threshold:.2f}%")
    print(f"原因: {state.reason}")

    # 检查是否允许开仓
    allowed, reason = monitor.is_new_order_allowed('BTC/USDT')
    print(f"\n允许开仓: {allowed}")
    print(f"原因: {reason}")

    # 检查是否需要紧急平仓
    emergency = monitor.should_emergency_close_all()
    print(f"\n紧急平仓: {emergency}")
