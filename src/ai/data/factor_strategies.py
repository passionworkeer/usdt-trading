"""
基于因子的交易策略

提供多种基于技术指标因子的交易策略：
- 双均线交叉策略
- RSI 超买超卖策略
- MACD 策略
- 布林带突破策略
- KDJ 金叉死叉策略
- 多因子综合策略

参考: https://github.com/microsoft/qlib
"""
import logging
from typing import Dict, List, Optional, Tuple
from enum import Enum
import pandas as pd
import numpy as np

from .expression_engine import ExpressionEngine
from .alpha_factors import get_alpha_library

logger = logging.getLogger(__name__)


class SignalType(Enum):
    """信号类型"""
    BUY = 1      # 买入信号
    SELL = -1    # 卖出信号
    HOLD = 0     # 持有信号


class TradingSignal:
    """交易信号"""

    def __init__(self, signal_type: SignalType, strength: float = 0.0,
                 reason: str = "", factor_name: str = ""):
        self.signal_type = signal_type
        self.strength = abs(strength)  # 信号强度 0-1
        self.reason = reason
        self.factor_name = factor_name

    def __repr__(self):
        return f"Signal({self.signal_type.name}, strength={self.strength:.2f}, reason={self.reason})"


class FactorSignalGenerator:
    """基于因子的信号生成器"""

    def __init__(self, df: pd.DataFrame):
        self.df = df
        self.engine = ExpressionEngine(df)
        self.library = get_alpha_library()

    def ma_cross_signal(self, short_period: int = 5, long_period: int = 20,
                       threshold: float = 0.02) -> TradingSignal:
        """
        双均线交叉策略

        逻辑：
        - 短期均线 > 长期均线 → 买入信号
        - 短期均线 < 长期均线 → 卖出信号
        """
        close = self.df['close']

        # 计算均线
        ma_short = close.rolling(window=short_period).mean()
        ma_long = close.rolling(window=long_period).mean()

        # 计算交叉
        current_diff = (ma_short.iloc[-1] - ma_long.iloc[-1]) / ma_long.iloc[-1]
        prev_diff = (ma_short.iloc[-2] - ma_long.iloc[-2]) / ma_long.iloc[-2]

        if current_diff > threshold and prev_diff <= threshold:
            return TradingSignal(
                SignalType.BUY,
                strength=min(abs(current_diff) / threshold, 1.0),
                reason=f"MA{short_period} crosses above MA{long_period}",
                factor_name=f"ma_cross_{short_period}_{long_period}"
            )
        elif current_diff < -threshold and prev_diff >= -threshold:
            return TradingSignal(
                SignalType.SELL,
                strength=min(abs(current_diff) / threshold, 1.0),
                reason=f"MA{short_period} crosses below MA{long_period}",
                factor_name=f"ma_cross_{short_period}_{long_period}"
            )
        elif current_diff > 0:
            return TradingSignal(SignalType.HOLD, reason="Uptrend")
        else:
            return TradingSignal(SignalType.HOLD, reason="Downtrend")

    def rsi_signal(self, period: int = 14, oversold: float = 30,
                   overbought: float = 70) -> TradingSignal:
        """
        RSI 超买超卖策略

        逻辑：
        - RSI < oversold → 买入信号（超卖）
        - RSI > overbought → 卖出信号（超买）
        """
        rsi = self.engine.evaluate(f'RSI($close, {period})')
        current_rsi = rsi.iloc[-1]

        if current_rsi < oversold:
            return TradingSignal(
                SignalType.BUY,
                strength=(oversold - current_rsi) / oversold,
                reason=f"RSI oversold ({current_rsi:.1f})",
                factor_name=f"rsi_{period}d"
            )
        elif current_rsi > overbought:
            return TradingSignal(
                SignalType.SELL,
                strength=(current_rsi - overbought) / (100 - overbought),
                reason=f"RSI overbought ({current_rsi:.1f})",
                factor_name=f"rsi_{period}d"
            )
        else:
            return TradingSignal(SignalType.HOLD, reason=f"RSI neutral ({current_rsi:.1f})")

    def macd_signal(self, fast: int = 12, slow: int = 26,
                   signal_period: int = 9) -> TradingSignal:
        """
        MACD 策略

        逻辑：
        - MACD 线从下向上穿过信号线 → 买入
        - MACD 线从上向下穿过信号线 → 卖出
        """
        macd = self.engine.evaluate(f'MACD($close, {fast}, {slow})')
        signal = self.engine.evaluate(f'MACD_SIGNAL($close, {fast}, {slow}, {signal_period})')

        current_diff = macd.iloc[-1] - signal.iloc[-1]
        prev_diff = macd.iloc[-2] - signal.iloc[-2]

        if current_diff > 0 and prev_diff <= 0:
            return TradingSignal(
                SignalType.BUY,
                strength=min(abs(current_diff) / 100, 1.0),
                reason="MACD golden cross",
                factor_name="macd"
            )
        elif current_diff < 0 and prev_diff >= 0:
            return TradingSignal(
                SignalType.SELL,
                strength=min(abs(current_diff) / 100, 1.0),
                reason="MACD death cross",
                factor_name="macd"
            )
        elif current_diff > 0:
            return TradingSignal(SignalType.HOLD, reason="MACD bullish")
        else:
            return TradingSignal(SignalType.HOLD, reason="MACD bearish")

    def bollinger_breakout_signal(self, period: int = 20,
                                  k: float = 2.0) -> TradingSignal:
        """
        布林带突破策略

        逻辑：
        - 价格突破上轨 → 买入
        - 价格突破下轨 → 卖出
        """
        bb_upper = self.engine.evaluate(f'BB_UPPER($close, {period}, {k})')
        bb_lower = self.engine.evaluate(f'BB_LOWER($close, {period}, {k})')
        bb_position = self.engine.evaluate(f'BB_POSITION($close, {period}, {k})')

        current_price = self.df['close'].iloc[-1]
        upper = bb_upper.iloc[-1]
        lower = bb_lower.iloc[-1]
        position = bb_position.iloc[-1]

        if current_price > upper:
            return TradingSignal(
                SignalType.BUY,
                strength=min((current_price - upper) / upper * 10, 1.0),
                reason="Price breaks BB upper band",
                factor_name="bb_breakout"
            )
        elif current_price < lower:
            return TradingSignal(
                SignalType.SELL,
                strength=min((lower - current_price) / lower * 10, 1.0),
                reason="Price breaks BB lower band",
                factor_name="bb_breakout"
            )
        elif position > 0.8:
            return TradingSignal(
                SignalType.SELL,
                strength=position - 0.5,
                reason="BB position overbought",
                factor_name="bb_position"
            )
        elif position < 0.2:
            return TradingSignal(
                SignalType.BUY,
                strength=0.5 - position,
                reason="BB position oversold",
                factor_name="bb_position"
            )
        else:
            return TradingSignal(SignalType.HOLD, reason="BB normal")

    def kdj_signal(self, period: int = 9) -> TradingSignal:
        """
        KDJ 金叉死叉策略

        逻辑：
        - K 线从下向上穿过 D 线 → 买入
        - K 线从上向下穿过 D 线 → 卖出
        """
        k = self.engine.evaluate(f'KDJ_K($high, $low, $close, {period})')
        d = self.engine.evaluate(f'KDJ_D($high, $low, $close, {period})')
        j = self.engine.evaluate(f'KDJ_J($high, $low, $close, {period})')

        current_k = k.iloc[-1]
        current_d = d.iloc[-1]
        current_j = j.iloc[-1]

        prev_k = k.iloc[-2]
        prev_d = d.iloc[-2]

        # 金叉
        if current_k > current_d and prev_k <= prev_d:
            return TradingSignal(
                SignalType.BUY,
                strength=min((current_j - 100) / 100, 1.0) if current_j > 100 else 0.5,
                reason="KDJ golden cross",
                factor_name="kdj"
            )
        # 死叉
        elif current_k < current_d and prev_k >= prev_d:
            return TradingSignal(
                SignalType.SELL,
                strength=min((100 - current_j) / 100, 1.0) if current_j < 100 else 0.5,
                reason="KDJ death cross",
                factor_name="kdj"
            )
        # 超卖
        elif current_j < 20:
            return TradingSignal(
                SignalType.BUY,
                strength=(20 - current_j) / 20,
                reason="KDJ oversold",
                factor_name="kdj"
            )
        # 超买
        elif current_j > 80:
            return TradingSignal(
                SignalType.SELL,
                strength=(current_j - 80) / 20,
                reason="KDJ overbought",
                factor_name="kdj"
            )
        else:
            return TradingSignal(SignalType.HOLD, reason="KDJ neutral")

    def momentum_signal(self, period: int = 20, threshold: float = 0.05) -> TradingSignal:
        """
        动量策略

        逻辑：
        - 动量 > threshold → 买入
        - 动量 < -threshold → 卖出
        """
        momentum = self.engine.evaluate(f'Ref($close, -{period}) / $close - 1')
        current_momentum = momentum.iloc[-1]

        if current_momentum > threshold:
            return TradingSignal(
                SignalType.BUY,
                strength=min(current_momentum / (threshold * 2), 1.0),
                reason=f"Strong momentum ({current_momentum:.2%})",
                factor_name="momentum"
            )
        elif current_momentum < -threshold:
            return TradingSignal(
                SignalType.SELL,
                strength=min(abs(current_momentum) / (threshold * 2), 1.0),
                reason=f"Weak momentum ({current_momentum:.2%})",
                factor_name="momentum"
            )
        else:
            return TradingSignal(SignalType.HOLD, reason=f"Neutral momentum ({current_momentum:.2%})")

    def atr_volatility_signal(self, period: int = 14, threshold: float = 0.03) -> TradingSignal:
        """
        ATR 波动率策略

        逻辑：
        - ATR 突然放大 → 可能突破
        - ATR 处于低位 → 可能盘整
        """
        atr = self.engine.evaluate(f'ATR($high, $low, $close, {period})')
        close = self.df['close']

        current_atr = atr.iloc[-1]
        atr_pct = current_atr / close.iloc[-1]

        # 计算 ATR 变化
        atr_mean = atr.iloc[-20:-1].mean()
        atr_change = (current_atr - atr_mean) / atr_mean

        if atr_change > 0.5 and atr_pct > threshold:
            # ATR 突然放大，可能突破
            return TradingSignal(
                SignalType.HOLD,
                strength=min(atr_change / 2, 1.0),
                reason=f"ATR breakout signal ({atr_change:.1%})",
                factor_name="atr"
            )
        elif atr_pct < threshold / 2:
            # ATR 处于低位，可能盘整
            return TradingSignal(
                SignalType.HOLD,
                strength=0.3,
                reason=f"Low volatility ({atr_pct:.2%})",
                factor_name="atr"
            )
        else:
            return TradingSignal(SignalType.HOLD, reason="Normal volatility")

    def multi_factor_signal(self, weights: Optional[Dict[str, float]] = None) -> TradingSignal:
        """
        多因子综合策略

        Args:
            weights: 各因子权重，如 {'ma': 0.2, 'rsi': 0.3, 'macd': 0.3, 'kdj': 0.2}

        Returns:
            加权综合信号
        """
        if weights is None:
            weights = {'ma': 0.2, 'rsi': 0.3, 'macd': 0.3, 'kdj': 0.2}

        signals = {}

        # 获取各因子信号
        try:
            if 'ma' in weights:
                signals['ma'] = self.ma_cross_signal()
            if 'rsi' in weights:
                signals['rsi'] = self.rsi_signal()
            if 'macd' in weights:
                signals['macd'] = self.macd_signal()
            if 'kdj' in weights:
                signals['kdj'] = self.kdj_signal()
            if 'momentum' in weights:
                signals['momentum'] = self.momentum_signal()
            if 'bb' in weights:
                signals['bb'] = self.bollinger_breakout_signal()
        except Exception as e:
            logger.error(f"Error generating multi-factor signal: {e}")
            return TradingSignal(SignalType.HOLD, reason="Error")

        # 计算加权信号
        total_weight = sum(weights.values())
        weighted_signal = 0.0
        reasons = []

        for name, weight in weights.items():
            if name in signals:
                signal = signals[name]
                factor_weight = weight / total_weight

                if signal.signal_type == SignalType.BUY:
                    weighted_signal += signal.strength * factor_weight
                elif signal.signal_type == SignalType.SELL:
                    weighted_signal -= signal.strength * factor_weight

                reasons.append(f"{name}({signal.signal_type.name})")

        # 阈值判断
        threshold = 0.15
        if weighted_signal > threshold:
            return TradingSignal(
                SignalType.BUY,
                strength=min(weighted_signal / (threshold * 2), 1.0),
                reason="Multi-factor BUY: " + ", ".join(reasons),
                factor_name="multi_factor"
            )
        elif weighted_signal < -threshold:
            return TradingSignal(
                SignalType.SELL,
                strength=min(abs(weighted_signal) / (threshold * 2), 1.0),
                reason="Multi-factor SELL: " + ", ".join(reasons),
                factor_name="multi_factor"
            )
        else:
            return TradingSignal(
                SignalType.HOLD,
                reason="Multi-factor neutral"
            )

    def get_all_signals(self) -> Dict[str, TradingSignal]:
        """获取所有策略的信号"""
        signals = {}

        try:
            signals['ma_cross'] = self.ma_cross_signal()
        except Exception as e:
            logger.warning(f"MA cross signal error: {e}")

        try:
            signals['rsi'] = self.rsi_signal()
        except Exception as e:
            logger.warning(f"RSI signal error: {e}")

        try:
            signals['macd'] = self.macd_signal()
        except Exception as e:
            logger.warning(f"MACD signal error: {e}")

        try:
            signals['kdj'] = self.kdj_signal()
        except Exception as e:
            logger.warning(f"KDJ signal error: {e}")

        try:
            signals['bollinger'] = self.bollinger_breakout_signal()
        except Exception as e:
            logger.warning(f"Bollinger signal error: {e}")

        try:
            signals['momentum'] = self.momentum_signal()
        except Exception as e:
            logger.warning(f"Momentum signal error: {e}")

        try:
            signals['multi_factor'] = self.multi_factor_signal()
        except Exception as e:
            logger.warning(f"Multi-factor signal error: {e}")

        return signals


def generate_signals(df: pd.DataFrame, strategy: str = 'all') -> Dict[str, TradingSignal]:
    """
    快速生成交易信号

    Args:
        df: OHLCV 数据
        strategy: 策略名称 ('all', 'ma', 'rsi', 'macd', 'kdj', 'bollinger', 'momentum', 'multi')

    Returns:
        信号字典
    """
    generator = FactorSignalGenerator(df)

    if strategy == 'all':
        return generator.get_all_signals()
    elif strategy == 'ma':
        return {'ma_cross': generator.ma_cross_signal()}
    elif strategy == 'rsi':
        return {'rsi': generator.rsi_signal()}
    elif strategy == 'macd':
        return {'macd': generator.macd_signal()}
    elif strategy == 'kdj':
        return {'kdj': generator.kdj_signal()}
    elif strategy == 'bollinger':
        return {'bollinger': generator.bollinger_breakout_signal()}
    elif strategy == 'momentum':
        return {'momentum': generator.momentum_signal()}
    elif strategy == 'multi':
        return {'multi_factor': generator.multi_factor_signal()}
    else:
        raise ValueError(f"Unknown strategy: {strategy}")
