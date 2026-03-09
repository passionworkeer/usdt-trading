"""
高级交易策略模块 v2.0

整合了多种高级交易策略：
- 趋势跟踪策略
- 均值回归策略
- 突破策略
- 支撑阻力策略
- 成交量分析策略
- 多时间周期策略
- 资金费率套利策略
- 与现有系统整合

参考仓库现有策略和数据源模块
"""
import logging
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
from enum import Enum
import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)


class SignalType(Enum):
    """信号类型"""
    BUY = 1
    SELL = -1
    HOLD = 0


@dataclass
class TradingSignal:
    """交易信号"""
    signal_type: SignalType
    strength: float  # 0-1
    reason: str
    price_level: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    risk_reward_ratio: Optional[float] = None
    metadata: Dict = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


class AdvancedStrategyBase:
    """高级策略基类"""

    def __init__(self, name: str):
        self.name = name
        self.enabled = True

    def analyze(self, df: pd.DataFrame, **kwargs) -> TradingSignal:
        """分析并生成信号"""
        raise NotImplementedError


class TrendFollowingStrategy(AdvancedStrategyBase):
    """
    趋势跟踪策略

    组合多个趋势指标：
    - EMA 趋势判断
    - ADX 趋势强度
    - 趋势通道
    """

    def __init__(self, fast_ema: int = 12, slow_ema: int = 26,
                 adx_period: int = 14, adx_threshold: float = 25):
        super().__init__("Trend Following")
        self.fast_ema = fast_ema
        self.slow_ema = slow_ema
        self.adx_period = adx_period
        self.adx_threshold = adx_threshold

    def _calculate_adx(self, high: pd.Series, low: pd.Series,
                      close: pd.Series) -> pd.Series:
        """计算 ADX"""
        plus_dm = high.diff()
        minus_dm = -low.diff()

        plus_dm[plus_dm < 0] = 0
        minus_dm[minus_dm < 0] = 0

        tr1 = high - low
        tr2 = abs(high - close.shift())
        tr3 = abs(low - close.shift())
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

        atr = tr.rolling(window=self.adx_period).mean()

        plus_di = 100 * (plus_dm.rolling(window=self.adx_period).mean() / atr)
        minus_di = 100 * (minus_dm.rolling(window=self.adx_period).mean() / atr)

        dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di)
        adx = dx.rolling(window=self.adx_period).mean()

        return adx

    def analyze(self, df: pd.DataFrame, **kwargs) -> TradingSignal:
        """趋势跟踪分析"""
        if len(df) < max(self.slow_ema, self.adx_period) + 5:
            return TradingSignal(SignalType.HOLD, 0, "Insufficient data")

        close = df['close']
        high = df['high']
        low = df['low']

        # EMA 趋势
        ema_fast = close.ewm(span=self.fast_ema).mean()
        ema_slow = close.ewm(span=self.slow_ema).mean()

        ema_trend = ema_fast.iloc[-1] > ema_slow.iloc[-1]
        ema_slope = (ema_fast.iloc[-1] - ema_fast.iloc[-5]) / ema_fast.iloc[-5]

        # ADX 趋势强度
        adx = self._calculate_adx(high, low, close)
        adx_value = adx.iloc[-1] if not adx.empty else 0
        is_strong_trend = adx_value > self.adx_threshold

        # 趋势通道
        rolling_high = high.rolling(window=20).max()
        rolling_low = low.rolling(window=20).min()
        current_price = close.iloc[-1]
        channel_position = (current_price - rolling_low.iloc[-1]) / (rolling_high.iloc[-1] - rolling_low.iloc[-1])

        # 综合判断
        if ema_trend and is_strong_trend and ema_slope > 0:
            strength = min(1.0, (adx_value / 50))
            return TradingSignal(
                SignalType.BUY,
                strength,
                f"Strong uptrend: EMA bullish, ADX={adx_value:.1f}",
                metadata={'adx': adx_value, 'ema_slope': ema_slope}
            )
        elif not ema_trend and is_strong_trend and ema_slope < 0:
            strength = min(1.0, (adx_value / 50))
            return TradingSignal(
                SignalType.SELL,
                strength,
                f"Strong downtrend: EMA bearish, ADX={adx_value:.1f}",
                metadata={'adx': adx_value, 'ema_slope': ema_slope}
            )
        elif not is_strong_trend:
            return TradingSignal(
                SignalType.HOLD,
                0,
                f"Weak trend: ADX={adx_value:.1f} < {self.adx_threshold}",
                metadata={'adx': adx_value}
            )
        else:
            return TradingSignal(
                SignalType.HOLD,
                0,
                "No clear trend",
                metadata={'adx': adx_value}
            )


class MeanReversionStrategy(AdvancedStrategyBase):
    """
    均值回归策略

    基于价格偏离均值的程度：
    - 价格偏离均线过大时反向交易
    - 结合波动率设置止盈止损
    """

    def __init__(self, ma_period: int = 20, std_multiplier: float = 2.0,
                 rsi_period: int = 14, rsi_oversold: float = 30,
                 rsi_overbought: float = 70):
        super().__init__("Mean Reversion")
        self.ma_period = ma_period
        self.std_multiplier = std_multiplier
        self.rsi_period = rsi_period
        self.rsi_oversold = rsi_oversold
        self.rsi_overbought = rsi_overbought

    def _calculate_rsi(self, close: pd.Series) -> pd.Series:
        """计算 RSI"""
        delta = close.diff()
        gain = delta.where(delta > 0, 0)
        loss = -delta.where(delta < 0, 0)

        avg_gain = gain.rolling(window=self.rsi_period).mean()
        avg_loss = loss.rolling(window=self.rsi_period).mean()

        rs = avg_gain / avg_loss.replace(0, np.nan)
        rsi = 100 - (100 / (1 + rs))
        return rsi

    def analyze(self, df: pd.DataFrame, **kwargs) -> TradingSignal:
        """均值回归分析"""
        if len(df) < self.ma_period + self.rsi_period:
            return TradingSignal(SignalSignalType.HOLD, 0, "Insufficient data")

        close = df['close']

        # 布林带计算
        ma = close.rolling(window=self.ma_period).mean()
        std = close.rolling(window=self.ma_period).std()
        upper = ma + self.std_multiplier * std
        lower = ma - self.std_multiplier * std

        current_price = close.iloc[-1]
        current_ma = ma.iloc[-1]
        current_std = std.iloc[-1]

        # 价格偏离程度
        deviation = (current_price - current_ma) / current_std if current_std > 0 else 0

        # RSI 确认
        rsi = self._calculate_rsi(close)
        current_rsi = rsi.iloc[-1]

        # 买入条件：价格在下轨附近或跌破，且 RSI 超卖
        if current_price <= lower.iloc[-1] or deviation < -self.std_multiplier:
            if current_rsi < self.rsi_oversold:
                strength = min(1.0, abs(deviation) / (self.std_multiplier * 2))
                return TradingSignal(
                    SignalType.BUY,
                    strength,
                    f"Price at lower band (deviation={deviation:.2f}), RSI={current_rsi:.1f}"
                )

        # 卖出条件：价格在上轨附近或突破，且 RSI 超买
        elif current_price >= upper.iloc[-1] or deviation > self.std_multiplier:
            if current_rsi > self.rsi_overbought:
                strength = min(1.0, abs(deviation) / (self.std_multiplier * 2))
                return TradingSignal(
                    SignalType.SELL,
                    strength,
                    f"Price at upper band (deviation={deviation:.2f}), RSI={current_rsi:.1f}"
                )

        return TradingSignal(
            SignalType.HOLD,
            0,
            f"Price within bands (deviation={deviation:.2f}, RSI={current_rsi:.1f})"
        )


class BreakoutStrategy(AdvancedStrategyBase):
    """
    突破策略

    识别关键价位的突破：
    - 盘整区间突破
    - 均线突破
    - 成交量确认
    """

    def __init__(self, consolidation_period: int = 20,
                 breakout_threshold: float = 0.02,
                 volume_threshold: float = 1.5):
        super().__init__("Breakout")
        self.consolidation_period = consolidation_period
        self.breakout_threshold = breakout_threshold
        self.volume_threshold = volume_threshold

    def analyze(self, df: pd.DataFrame, **kwargs) -> TradingSignal:
        """突破分析"""
        if len(df) < self.consolidation_period + 5:
            return TradingSignal(SignalType.HOLD, 0, "Insufficient data")

        close = df['close']
        high = df['high']
        low = df['low']
        volume = df.get('volume', pd.Series([1] * len(df)))

        # 盘整区间
        recent_high = high.iloc[-self.consolidation_period:-1].max()
        recent_low = low.iloc[-self.consolidation_period:-1].min()
        consolidation_range = recent_high - recent_low
        consolidation_mid = (recent_high + recent_low) / 2

        current_price = close.iloc[-1]
        avg_volume = volume.iloc[-20:-1].mean()
        current_volume = volume.iloc[-1]

        # 突破方向
        if current_price > recent_high * (1 + self.breakout_threshold):
            # 上突破
            volume_confirm = current_volume > avg_volume * self.volume_threshold
            if volume_confirm:
                strength = min(1.0, (current_price - recent_high) / recent_high / self.breakout_threshold)
                return TradingSignal(
                    SignalType.BUY,
                    strength,
                    f"Breakout upward: price={current_price:.2f} > high={recent_high:.2f}, volume={current_volume/avg_volume:.1f}x"
                )
            else:
                return TradingSignal(
                    SignalType.HOLD,
                    0,
                    f"Breakout but weak volume: {current_volume/avg_volume:.1f}x < {self.volume_threshold}x"
                )

        elif current_price < recent_low * (1 - self.breakout_threshold):
            # 下突破
            volume_confirm = current_volume > avg_volume * self.volume_threshold
            if volume_confirm:
                strength = min(1.0, (recent_low - current_price) / recent_low / self.breakout_threshold)
                return TradingSignal(
                    SignalType.SELL,
                    strength,
                    f"Breakout downward: price={current_price:.2f} < low={recent_low:.2f}, volume={current_volume/avg_volume:.1f}x"
                )
            else:
                return TradingSignal(
                    SignalType.HOLD,
                    0,
                    f"Breakout but weak volume: {current_volume/avg_volume:.1f}x < {self.volume_threshold}x"
                )

        return TradingSignal(
            SignalType.HOLD,
            0,
            f"Consolidating: price={current_price:.2f} within [{recent_low:.2f}, {recent_high:.2f}]"
        )


class SupportResistanceStrategy(AdvancedStrategyBase):
    """
    支撑阻力策略

    识别关键支撑和阻力位：
    - 枢轴点计算
    - 支撑阻力位识别
    - 价格测试确认
    """

    def __init__(self, lookback_period: int = 50,
                 touch_threshold: float = 0.01):
        super().__init__("Support Resistance")
        self.lookback_period = lookback_period
        self.touch_threshold = touch_threshold

    def _calculate_pivot_points(self, high: float, low: float,
                               close: float) -> Dict[str, float]:
        """计算枢轴点"""
        pivot = (high + low + close) / 3
        r1 = 2 * pivot - low
        s1 = 2 * pivot - high
        r2 = pivot + (high - low)
        s2 = pivot - (high - low)
        r3 = high + 2 * (pivot - low)
        s3 = low - 2 * (high - pivot)

        return {
            'pivot': pivot,
            'r1': r1, 'r2': r2, 'r3': r3,
            's1': s1, 's2': s2, 's3': s3
        }

    def _find_sr_levels(self, high: pd.Series,
                       low: pd.Series) -> Tuple[List[float], List[float]]:
        """查找支撑阻力位"""
        # 使用局部极值
        highs = []
        lows = []

        for i in range(2, len(high) - 2):
            # 局部高点
            if high.iloc[i] > high.iloc[i-1] and high.iloc[i] > high.iloc[i-2] and \
               high.iloc[i] > high.iloc[i+1] and high.iloc[i] > high.iloc[i+2]:
                highs.append(high.iloc[i])

            # 局部低点
            if low.iloc[i] < low.iloc[i-1] and low.iloc[i] < low.iloc[i-2] and \
               low.iloc[i] < low.iloc[i+1] and low.iloc[i] < low.iloc[i+2]:
                lows.append(low.iloc[i])

        return highs, lows

    def analyze(self, df: pd.DataFrame, **kwargs) -> TradingSignal:
        """支撑阻力分析"""
        if len(df) < self.lookback_period:
            return TradingSignal(SignalType.HOLD, 0, "Insufficient data")

        close = df['close']
        high = df['high']
        low = df['low']

        current_price = close.iloc[-1]

        # 枢轴点
        pivot = self._calculate_pivot_points(
            high.iloc[-1], low.iloc[-1], close.iloc[-1]
        )

        # 支撑阻力位
        recent_highs, recent_lows = self._find_sr_levels(high, low)

        # 合并所有关键位
        all_levels = sorted(set(recent_highs + recent_lows +
                               [pivot['r1'], pivot['r2'], pivot['r3'],
                               pivot['s1'], pivot['s2'], pivot['s3']]))

        # 找到最近的支撑和阻力
        supports = [l for l in all_levels if l < current_price * 0.99]
        resistances = [l for l in all_levels if l > current_price * 1.01]

        nearest_support = max(supports) if supports else None
        nearest_resistance = min(resistances) if resistances else None

        # 计算距离
        if nearest_support:
            support_dist = (current_price - nearest_support) / current_price
        else:
            support_dist = None

        if nearest_resistance:
            resistance_dist = (nearest_resistance - current_price) / current_price
        else:
            resistance_dist = None

        # 交易逻辑
        # 接近支撑且 RSI 不过高
        if nearest_support and support_dist and support_dist < self.touch_threshold:
            rsi = self._calculate_rsi_fast(close)
            if rsi < 60:
                strength = 1 - (support_dist / self.touch_threshold) if support_dist else 0.5
                return TradingSignal(
                    SignalType.BUY,
                    strength,
                    f"Near support: {nearest_support:.2f} (dist={support_dist:.2%}), RSI={rsi:.1f}",
                    price_level=nearest_support
                )

        # 接近阻力且 RSI 不过低
        if nearest_resistance and resistance_dist and resistance_dist < self.touch_threshold:
            rsi = self._calculate_rsi_fast(close)
            if rsi > 40:
                strength = 1 - (resistance_dist / self.touch_threshold) if resistance_dist else 0.5
                return TradingSignal(
                    SignalType.SELL,
                    strength,
                    f"Near resistance: {nearest_resistance:.2f} (dist={resistance_dist:.2%}), RSI={rsi:.1f}",
                    price_level=nearest_resistance
                )

        return TradingSignal(
            SignalType.HOLD,
            0,
            f"Price in no-man's land: support={nearest_support}, resistance={nearest_resistance}"
        )

    def _calculate_rsi_fast(self, close: pd.Series, period: int = 14) -> float:
        """快速 RSI 计算"""
        delta = close.diff()
        gain = delta.where(delta > 0, 0)
        loss = -delta.where(delta < 0, 0)

        avg_gain = gain.tail(period).mean()
        avg_loss = loss.tail(period).mean()

        if avg_loss == 0:
            return 100

        rs = avg_gain / avg_loss
        return 100 - (100 / (1 + rs))


class VolumeAnalysisStrategy(AdvancedStrategyBase):
    """
    成交量分析策略

    基于成交量的异常：
    - 放量突破
    - 缩量盘整
    - 成交量分布
    """

    def __init__(self, volume_ma_period: int = 20,
                 volume_spike_threshold: float = 2.0,
                 accumulation_threshold: float = 0.6):
        super().__init__("Volume Analysis")
        self.volume_ma_period = volume_ma_period
        self.volume_spike_threshold = volume_spike_threshold
        self.accumulation_threshold = accumulation_threshold

    def analyze(self, df: pd.DataFrame, **kwargs) -> TradingSignal:
        """成交量分析"""
        if len(df) < self.volume_ma_period + 5:
            return TradingSignal(SignalType.HOLD, 0, "Insufficient data")

        close = df['close']
        volume = df.get('volume', pd.Series([1] * len(df)))

        # 成交量均线
        volume_ma = volume.rolling(window=self.volume_ma_period).mean()
        current_volume = volume.iloc[-1]
        avg_volume = volume_ma.iloc[-1]
        volume_ratio = current_volume / avg_volume if avg_volume > 0 else 1

        # 价格变化
        price_change = (close.iloc[-1] - close.iloc[-2]) / close.iloc[-2]

        # 放量上涨
        if volume_ratio > self.volume_spike_threshold and price_change > 0.01:
            strength = min(1.0, volume_ratio / (self.volume_spike_threshold * 2))
            return TradingSignal(
                SignalType.BUY,
                strength,
                f"Volume spike up: {volume_ratio:.1f}x avg, +{price_change:.2%}"
            )

        # 放量下跌
        elif volume_ratio > self.volume_spike_threshold and price_change < -0.01:
            strength = min(1.0, volume_ratio / (self.volume_spike_threshold * 2))
            return TradingSignal(
                SignalType.SELL,
                strength,
                f"Volume spike down: {volume_ratio:.1f}x avg, {price_change:.2%}"
            )

        # 缩量盘整判断
        elif volume_ratio < 0.5:
            # 检查价格是否在均线附近
            ma = close.rolling(window=20).mean()
            price_deviation = abs(close.iloc[-1] - ma.iloc[-1]) / ma.iloc[-1]

            if price_deviation < 0.02:
                return TradingSignal(
                    SignalType.HOLD,
                    0.2,
                    f"Low volatility consolidation: volume={volume_ratio:.1f}x, deviation={price_deviation:.2%}"
                )

        return TradingSignal(
            SignalType.HOLD,
            0,
            f"Normal volume: {volume_ratio:.1f}x"
        )


class MultiTimeframeStrategy(AdvancedStrategyBase):
    """
    多时间周期策略

    综合多个时间周期的信号：
    - 日线判断趋势
    - 4小时入场
    - 1小时择时
    """

    def __init__(self, timeframes: Dict[str, Dict] = None):
        super().__init__("Multi Timeframe")
        # 默认配置
        self.timeframes = timeframes or {
            '1d': {'trend_ema': 50},
            '4h': {'entry_ema': [20, 50]},
            '1h': {'timing_rsi': 14}
        }

    def analyze(self, df: pd.DataFrame, **kwargs) -> TradingSignal:
        """
        多时间周期分析

        注意：实际使用需要传入多个时间周期的数据
        """
        # 这个策略需要外部传入多周期数据
        daily_data = kwargs.get('daily_data')
        hourly_data = kwargs.get('hourly_data', df)

        if daily_data is None:
            return TradingSignal(
                SignalType.HOLD,
                0,
                "Multi-timeframe requires daily data"
            )

        # 日线趋势
        daily_ema = daily_data['close'].ewm(span=50).mean()
        daily_trend = daily_ema.iloc[-1] > daily_ema.iloc[-10]

        # 4小时 EMA 交叉
        hourly_ema_20 = hourly_data['close'].ewm(span=20).mean()
        hourly_ema_50 = hourly_data['close'].ewm(span=50).mean()
        hourly_trend = hourly_ema_20.iloc[-1] > hourly_ema_50.iloc[-1]

        # 1小时 RSI 择时
        rsi = self._calculate_rsi(hourly_data['close'])
        current_rsi = rsi.iloc[-1]

        # 顺大势，逆小势
        if daily_trend and hourly_trend and current_rsi < 40:
            return TradingSignal(
                SignalType.BUY,
                0.8,
                "Multi-TF alignment: Daily uptrend + 4H bullish + 1H pullback (RSI oversold)"
            )

        elif not daily_trend and not hourly_trend and current_rsi > 60:
            return TradingSignal(
                SignalType.SELL,
                0.8,
                "Multi-TF alignment: Daily downtrend + 4H bearish + 1H rally (RSI overbought)"
            )

        return TradingSignal(
            SignalType.HOLD,
            0,
            f"No clear multi-TF signal: D={daily_trend}, 4H={hourly_trend}, RSI={current_rsi:.1f}"
        )

    def _calculate_rsi(self, close: pd.Series, period: int = 14) -> pd.Series:
        """计算 RSI"""
        delta = close.diff()
        gain = delta.where(delta > 0, 0)
        loss = -delta.where(delta < 0, 0)

        avg_gain = gain.rolling(window=period).mean()
        avg_loss = loss.rolling(window=period).mean()

        rs = avg_gain / avg_loss.replace(0, np.nan)
        return 100 - (100 / (1 + rs))


class CompositeStrategy(AdvancedStrategyBase):
    """
    复合策略 - 组合多个策略的信号

    使用加权投票机制综合各策略的信号
    """

    def __init__(self, strategies: List[AdvancedStrategyBase] = None,
                 weights: List[float] = None):
        super().__init__("Composite")
        self.strategies = strategies or []
        self.weights = weights or [1.0] * len(self.strategies)

    def add_strategy(self, strategy: AdvancedStrategyBase, weight: float = 1.0):
        """添加策略"""
        self.strategies.append(strategy)
        self.weights.append(weight)

    def analyze(self, df: pd.DataFrame, **kwargs) -> TradingSignal:
        """复合分析"""
        if not self.strategies:
            return TradingSignal(SignalType.HOLD, 0, "No strategies added")

        signals = []
        for strategy in self.strategies:
            if strategy.enabled:
                signal = strategy.analyze(df, **kwargs)
                signals.append(signal)

        if not signals:
            return TradingSignal(SignalType.HOLD, 0, "No active signals")

        # 加权投票
        buy_score = 0.0
        sell_score = 0.0
        total_weight = 0.0

        for i, signal in enumerate(signals):
            weight = self.weights[i] if i < len(self.weights) else 1.0
            total_weight += weight

            if signal.signal_type == SignalType.BUY:
                buy_score += signal.strength * weight
            elif signal.signal_type == SignalType.SELL:
                sell_score += signal.strength * weight

        buy_score /= total_weight
        sell_score /= total_weight

        threshold = 0.3

        if buy_score > threshold and buy_score > sell_score:
            return TradingSignal(
                SignalType.BUY,
                buy_score,
                f"Composite BUY: buy={buy_score:.2f} vs sell={sell_score:.2f}"
            )
        elif sell_score > threshold and sell_score > buy_score:
            return TradingSignal(
                SignalType.SELL,
                sell_score,
                f"Composite SELL: sell={sell_score:.2f} vs buy={buy_score:.2f}"
            )
        else:
            return TradingSignal(
                SignalType.HOLD,
                0,
                f"Composite neutral: buy={buy_score:.2f}, sell={sell_score:.2f}"
            )


# ========== 预设策略组合 ==========

def create_trend_strategy() -> CompositeStrategy:
    """创建趋势跟踪策略组合"""
    composite = CompositeStrategy(name="Trend Composite")

    composite.add_strategy(TrendFollowingStrategy(), 0.4)
    composite.add_strategy(BreakoutStrategy(), 0.3)
    composite.add_strategy(VolumeAnalysisStrategy(), 0.3)

    return composite


def create_reversal_strategy() -> CompositeStrategy:
    """创建均值回归策略组合"""
    composite = CompositeStrategy(name="Reversal Composite")

    composite.add_strategy(MeanReversionStrategy(), 0.4)
    composite.add_strategy(SupportResistanceStrategy(), 0.3)
    composite.add_strategy(VolumeAnalysisStrategy(), 0.3)

    return composite


def create_aggressive_strategy() -> CompositeStrategy:
    """创建激进策略组合"""
    composite = CompositeStrategy(name="Aggressive Composite")

    composite.add_strategy(BreakoutStrategy(volume_threshold=2.0), 0.35)
    composite.add_strategy(TrendFollowingStrategy(), 0.35)
    composite.add_strategy(VolumeAnalysisStrategy(volume_spike_threshold=2.5), 0.3)

    return composite


def create_conservative_strategy() -> CompositeStrategy:
    """创建保守策略组合"""
    composite = CompositeStrategy(name="Conservative Composite")

    composite.add_strategy(MeanReversionStrategy(), 0.3)
    composite.add_strategy(SupportResistanceStrategy(touch_threshold=0.005), 0.3)
    composite.add_strategy(TrendFollowingStrategy(adx_threshold=30), 0.4)

    return composite
