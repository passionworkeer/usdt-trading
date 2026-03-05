"""
技术指标增强模块 (Technical Indicators Enhanced)

提供更多高级技术指标
"""
import math
from typing import List, Dict, Tuple, Optional
import pandas as pd
import numpy as np


class TechnicalIndicators:
    """
    技术指标计算器

    包含常用和高级技术指标
    """

    @staticmethod
    def sma(series: pd.Series, period: int) -> pd.Series:
        """简单移动平均 (SMA)"""
        return series.rolling(window=period).mean()

    @staticmethod
    def ema(series: pd.Series, period: int) -> pd.Series:
        """指数移动平均 (EMA)"""
        return series.ewm(span=period, adjust=False).mean()

    @staticmethod
    def rsi(series: pd.Series, period: int = 14) -> pd.Series:
        """相对强弱指数 (RSI)"""
        delta = series.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        return 100 - (100 / (1 + rs))

    @staticmethod
    def macd(
        series: pd.Series,
        fast: int = 12,
        slow: int = 26,
        signal: int = 9
    ) -> Tuple[pd.Series, pd.Series, pd.Series]:
        """
        MACD (Moving Average Convergence Divergence)

        Returns:
            (MACD线, 信号线, 柱状图)
        """
        ema_fast = series.ewm(span=fast, adjust=False).mean()
        ema_slow = series.ewm(span=slow, adjust=False).mean()
        macd_line = ema_fast - ema_slow
        signal_line = macd_line.ewm(span=signal, adjust=False).mean()
        histogram = macd_line - signal_line
        return macd_line, signal_line, histogram

    @staticmethod
    def bollinger_bands(
        series: pd.Series,
        period: int = 20,
        std_dev: float = 2.0
    ) -> Tuple[pd.Series, pd.Series, pd.Series]:
        """布林带 (Bollinger Bands)"""
        sma = series.rolling(window=period).mean()
        std = series.rolling(window=period).std()
        upper = sma + (std_dev * std)
        lower = sma - (std_dev * std)
        return upper, sma, lower

    @staticmethod
    def atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
        """平均真实波幅 (ATR)"""
        tr1 = high - low
        tr2 = abs(high - close.shift())
        tr3 = abs(low - close.shift())
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        return tr.rolling(window=period).mean()

    @staticmethod
    def stochastic(
        high: pd.Series,
        low: pd.Series,
        close: pd.Series,
        k_period: int = 14,
        d_period: int = 3
    ) -> Tuple[pd.Series, pd.Series]:
        """随机指标 (Stochastic)"""
        lowest_low = low.rolling(window=k_period).min()
        highest_high = high.rolling(window=k_period).max()
        k = 100 * (close - lowest_low) / (highest_high - lowest_low)
        d = k.rolling(window=d_period).mean()
        return k, d

    @staticmethod
    def adx(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
        """平均趋向指数 (ADX)"""
        plus_dm = high.diff()
        minus_dm = -low.diff()

        plus_dm[plus_dm < 0] = 0
        minus_dm[minus_dm < 0] = 0

        tr = TechnicalIndicators.atr(high, low, close, period)

        plus_di = 100 * (plus_dm.rolling(window=period).mean() / tr)
        minus_di = 100 * (minus_dm.rolling(window=period).mean() / tr)

        dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di)
        adx = dx.rolling(window=period).mean()

        return adx

    @staticmethod
    def ichimoku(
        high: pd.Series,
        low: pd.Series,
        close: pd.Series
    ) -> Dict[str, pd.Series]:
        """
        一目均衡表 (Ichimoku Cloud)

        Returns:
            {'tenkan_sen': ..., 'kijun_sen': ..., 'senkou_span_a': ...,
             'senkou_span_b': ..., 'chikou_span': ...}
        """
        # 转换线 (Tenkan-sen)
        tenkan_sen = (high.rolling(window=9).max() + low.rolling(window=9).min()) / 2

        # 基准线 (Kijun-sen)
        kijun_sen = (high.rolling(window=26).max() + low.rolling(window=26).min()) / 2

        # 先行带 A (Senkou Span A)
        senkou_span_a = ((tenkan_sen + kijun_sen) / 2).shift(26)

        # 先行带 B (Senkou Span B)
        senkou_span_b = (
            (high.rolling(window=52).max() + low.rolling(window=52).min()) / 2
        ).shift(26)

        # 延迟线 (Chikou Span)
        chikou_span = close.shift(-26)

        return {
            'tenkan_sen': tenkan_sen,
            'kijun_sen': kijun_sen,
            'senkou_span_a': senkou_span_a,
            'senkou_span_b': senkou_span_b,
            'chikou_span': chikou_span
        }

    @staticmethod
    def vwap(high: pd.Series, low: pd.Series, close: pd.Series, volume: pd.Series) -> pd.Series:
        """
        成交量加权平均价 (VWAP)
        """
        typical_price = (high + low + close) / 3
        vwap = (typical_price * volume).cumsum() / volume.cumsum()
        return vwap

    @staticmethod
    def obv(close: pd.Series, volume: pd.Series) -> pd.Series:
        """
        能量潮 (OBV)
        """
        obv = (np.sign(close.diff()) * volume).fillna(0).cumsum()
        return obv

    @staticmethod
    def mfi(high: pd.Series, low: pd.Series, close: pd.Series, volume: pd.Series, period: int = 14) -> pd.Series:
        """
        资金流量指标 (MFI)
        """
        typical_price = (high + low + close) / 3
        raw_money_flow = typical_price * volume

        money_flow_sign = np.where(typical_price > typical_price.shift(1), 1, -1)
        signed_flow = raw_money_flow * money_flow_sign

        positive_flow = signed_flow.where(signed_flow > 0, 0).rolling(window=period).sum()
        negative_flow = signed_flow.where(signed_flow < 0, 0).rolling(window=period).sum()

        mfi = 100 - (100 / (1 + positive_flow / negative_flow))
        return mfi

    @staticmethod
    def cci(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 20) -> pd.Series:
        """
        商品通道指标 (CCI)
        """
        typical_price = (high + low + close) / 3
        sma = typical_price.rolling(window=period).mean()
        mad = typical_price.rolling(window=period).apply(lambda x: np.abs(x - x.mean()).mean())
        cci = (typical_price - sma) / (0.015 * mad)
        return cci

    @staticmethod
    def williams_r(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
        """
        威廉指标 (Williams %R)
        """
        highest_high = high.rolling(window=period).max()
        lowest_low = low.rolling(window=period).min()
        williams_r = -100 * (highest_high - close) / (highest_high - lowest_low)
        return williams_r

    @staticmethod
    def momentum(series: pd.Series, period: int = 10) -> pd.Series:
        """动量指标 (Momentum)"""
        return series.diff(period)

    @staticmethod
    def roc(series: pd.Series, period: int = 12) -> pd.Series:
        """变动率指标 (ROC)"""
        return ((series - series.shift(period)) / series.shift(period)) * 100

    @staticmethod
    def supertrend(
        high: pd.Series,
        low: pd.Series,
        close: pd.Series,
        period: int = 10,
        multiplier: float = 3.0
    ) -> Tuple[pd.Series, pd.Series]:
        """
        超级趋势指标 (Supertrend)

        Returns:
            (supertrend线, 方向)
        """
        atr = TechnicalIndicators.atr(high, low, close, period)

        # 上轨和下轨
        upper_band = (high + low) / 2 + multiplier * atr
        lower_band = (high + low) / 2 - multiplier * atr

        # 初始化
        supertrend = pd.Series(index=close.index, dtype=float)
        direction = pd.Series(1, index=close.index)  # 1 = 多头, -1 = 空头

        for i in range(1, len(close)):
            if close.iloc[i] > upper_band.iloc[i-1]:
                direction.iloc[i] = 1
            elif close.iloc[i] < lower_band.iloc[i-1]:
                direction.iloc[i] = -1
            else:
                direction.iloc[i] = direction.iloc[i-1]

            # 更新轨线
            if direction.iloc[i] == 1:
                lower_band.iloc[i] = max(lower_band.iloc[i], lower_band.iloc[i-1])
            else:
                upper_band.iloc[i] = min(upper_band.iloc[i], upper_band.iloc[i-1])

            # 计算超级趋势值
            if direction.iloc[i] == 1:
                supertrend.iloc[i] = lower_band.iloc[i]
            else:
                supertrend.iloc[i] = upper_band.iloc[i]

        return supertrend, direction

    @staticmethod
    def pivot_points(high: pd.Series, low: pd.Series, close: pd.Series) -> Dict[str, float]:
        """
        枢轴点 (Pivot Points)

        Returns:
            {'pivot': ..., 'r1': ..., 'r2': ..., 'r3': ...,
             's1': ..., 's2': ..., 's3': ...}
        """
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

    @staticmethod
    def fibonacci_retracement(high: float, low: float) -> Dict[str, float]:
        """
        斐波那契回撤

        Returns:
            {'0.0%': ..., '23.6%': ..., '38.2%': ..., '50%': ..., '61.8%': ..., '100%': ...}
        """
        diff = high - low
        levels = [0.0, 0.236, 0.382, 0.5, 0.618, 0.786, 1.0]
        return {
            f"{int(level * 100)}%": high - (diff * level)
            for level in levels
        }


# 预计算指标快捷函数
def calculate_all_indicators(
    df: pd.DataFrame,
    price_column: str = 'close'
) -> pd.DataFrame:
    """
    计算所有常用指标

    Args:
        df: 包含 high, low, close, volume 的 DataFrame
        price_column: 价格列名

    Returns:
        添加了指标的 DataFrame
    """
    ti = TechnicalIndicators()
    close = df[price_column]
    high = df['high']
    low = df['low']
    volume = df['volume']

    # 移动平均
    df['sma_20'] = ti.sma(close, 20)
    df['sma_50'] = ti.sma(close, 50)
    df['sma_200'] = ti.sma(close, 200)

    df['ema_12'] = ti.ema(close, 12)
    df['ema_26'] = ti.ema(close, 26)

    # RSI
    df['rsi_14'] = ti.rsi(close, 14)

    # MACD
    df['macd'], df['macd_signal'], df['macd_hist'] = ti.macd(close)

    # 布林带
    df['bb_upper'], df['bb_middle'], df['bb_lower'] = ti.bollinger_bands(close)

    # ATR
    df['atr_14'] = ti.atr(high, low, close, 14)

    # 随机指标
    df['stoch_k'], df['stoch_d'] = ti.stochastic(high, low, close)

    # ADX
    df['adx_14'] = ti.adx(high, low, close)

    # MFI
    df['mfi_14'] = ti.mfi(high, low, close, volume)

    # CCI
    df['cci_20'] = ti.cci(high, low, close, 20)

    # 威廉指标
    df['williams_r_14'] = ti.williams_r(high, low, close, 14)

    # 动量
    df['momentum_10'] = ti.momentum(close, 10)
    df['roc_12'] = ti.roc(close, 12)

    # OBV
    df['obv'] = ti.obv(close, volume)

    # VWAP
    df['vwap'] = ti.vwap(high, low, close, volume)

    # 枢轴点
    pp = ti.pivot_points(high.iloc[-1], low.iloc[-1], close.iloc[-1])
    df['pivot'] = pp['pivot']
    df['r1'] = pp['r1']
    df['s1'] = pp['s1']

    return df
