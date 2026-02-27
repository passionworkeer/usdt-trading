"""
技术指标计算器

计算各种技术指标：趋势、动量、波动率、成交量。
"""
import logging
from typing import Dict, Optional

import numpy as np
import pandas as pd

from ..context import IndicatorSet, KLineData

logger = logging.getLogger(__name__)


class TechnicalIndicatorsCalculator:
    """技术指标计算器"""

    @staticmethod
    def calculate(df: pd.DataFrame) -> IndicatorSet:
        """
        计算所有技术指标

        Args:
            df: K线 DataFrame

        Returns:
            IndicatorSet
        """
        if df is None or len(df) < 20:
            logger.warning("K线数据不足，无法计算指标")
            return IndicatorSet()

        try:
            close = df['close'].astype(float)
            high = df['high'].astype(float)
            low = df['low'].astype(float)
            volume = df['volume'].astype(float)

            indicators = IndicatorSet()

            # ========== 趋势指标 ==========
            indicators.ema_9 = float(close.ewm(span=9, adjust=False).mean().iloc[-1])
            indicators.ema_21 = float(close.ewm(span=21, adjust=False).mean().iloc[-1])
            indicators.ema_50 = float(close.ewm(span=50, adjust=False).mean().iloc[-1])
            indicators.ema_200 = float(close.ewm(span=200, adjust=False).mean().iloc[-1])
            indicators.sma_20 = float(close.rolling(window=20).mean().iloc[-1])

            # VWAP
            typical_price = (high + low + close) / 3
            vwap = (typical_price * volume).cumsum() / volume.cumsum()
            indicators.vwap = float(vwap.iloc[-1])

            # ========== 动量指标 ==========
            # RSI(14)
            delta = close.diff()
            gain = delta.where(delta > 0, 0)
            loss = -delta.where(delta < 0, 0)
            avg_gain = gain.rolling(window=14).mean()
            avg_loss = loss.rolling(window=14).mean()
            rs = avg_gain / avg_loss
            rsi = 100 - (100 / (1 + rs))
            indicators.rsi_14 = float(rsi.iloc[-1])

            # MACD
            ema_12 = close.ewm(span=12, adjust=False).mean()
            ema_26 = close.ewm(span=26, adjust=False).mean()
            macd_line = ema_12 - ema_26
            signal_line = macd_line.ewm(span=9, adjust=False).mean()
            histogram = macd_line - signal_line

            indicators.macd = float(macd_line.iloc[-1])
            indicators.macd_signal = float(signal_line.iloc[-1])
            indicators.macd_histogram = float(histogram.iloc[-1])

            # Stochastic
            lowest_14 = low.rolling(window=14).min()
            highest_14 = high.rolling(window=14).max()
            stochastic = 100 * (close - lowest_14) / (highest_14 - lowest_14)
            indicators.stochastic_k = float(stochastic.iloc[-1])
            indicators.stochastic_d = float(stochastic.rolling(window=3).mean().iloc[-1])

            # ========== 波动指标 ==========
            # ATR(14)
            tr1 = high - low
            tr2 = abs(high - close.shift(1))
            tr3 = abs(low - close.shift(1))
            tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
            atr = tr.rolling(window=14).mean()
            indicators.atr_14 = float(atr.iloc[-1])

            # Bollinger Bands (20, 2)
            bb_middle = close.rolling(window=20).mean()
            bb_std = close.rolling(window=20).std()
            bb_upper = bb_middle + (bb_std * 2)
            bb_lower = bb_middle - (bb_std * 2)

            indicators.bb_upper = float(bb_upper.iloc[-1])
            indicators.bb_middle = float(bb_middle.iloc[-1])
            indicators.bb_lower = float(bb_lower.iloc[-1])

            # 布林带位置 (0-1)
            current_price = close.iloc[-1]
            bb_range = bb_upper.iloc[-1] - bb_lower.iloc[-1]
            if bb_range > 0:
                indicators.bb_position = float((current_price - bb_lower.iloc[-1]) / bb_range)

            # ========== 成交量指标 ==========
            # OBV
            obv = (np.sign(close.diff()) * volume).cumsum()
            indicators.obv = float(obv.iloc[-1])

            # 成交量比率
            avg_volume = volume.rolling(window=20).mean().iloc[-1]
            current_volume = volume.iloc[-1]
            if avg_volume > 0:
                indicators.volume_ratio = float(current_volume / avg_volume)

            return indicators

        except Exception as e:
            logger.error(f"计算技术指标失败: {e}")
            return IndicatorSet()

    @staticmethod
    def calculate_all(klines: Dict[str, KLineData]) -> Dict[str, IndicatorSet]:
        """
        计算所有时间周期的指标

        Args:
            klines: {interval: KLineData}

        Returns:
            {interval: IndicatorSet}
        """
        indicators = {}
        for interval, kline_data in klines.items():
            ind = TechnicalIndicatorsCalculator.calculate(kline_data.df)
            if ind:
                indicators[interval] = ind

        logger.info(f"计算了 {len(indicators)} 个时间周期的技术指标")
        return indicators
