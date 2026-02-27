"""
K线形态识别器

识别常见的 K 线形态：锤子线、吞没形态、十字星、旗形、三角形等。
"""
import logging
from typing import List, Dict, Optional

import pandas as pd

from .context import CandlestickPattern, KLineData

logger = logging.getLogger(__name__)


class PatternRecognizer:
    """K线形态识别器"""

    # 形态定义
    PATTERNS = {
        'hammer': {
            'name': '锤子线',
            'direction': 'bullish',
            'min_confidence': 0.6,
        },
        'inverted_hammer': {
            'name': '倒锤子线',
            'direction': 'bullish',
            'min_confidence': 0.6,
        },
        'bullish_engulfing': {
            'name': '看涨吞没',
            'direction': 'bullish',
            'min_confidence': 0.7,
        },
        'bearish_engulfing': {
            'name': '看跌吞没',
            'direction': 'bearish',
            'min_confidence': 0.7,
        },
        'doji': {
            'name': '十字星',
            'direction': 'neutral',
            'min_confidence': 0.5,
        },
        'morning_star': {
            'name': '早晨之星',
            'direction': 'bullish',
            'min_confidence': 0.7,
        },
        'evening_star': {
            'name': '黄昏之星',
            'direction': 'bearish',
            'min_confidence': 0.7,
        },
        'piercing': {
            'name': '刺透形态',
            'direction': 'bullish',
            'min_confidence': 0.65,
        },
        'dark_cloud_cover': {
            'name': '乌云盖顶',
            'direction': 'bearish',
            'min_confidence': 0.65,
        },
    }

    @staticmethod
    def recognize(klines: Dict[str, KLineData]) -> Dict[str, List[CandlestickPattern]]:
        """
        识别所有时间周期的形态

        Args:
            klines: {interval: KLineData}

        Returns:
            {interval: [CandlestickPattern]}
        """
        patterns = {}
        for interval, kline_data in klines.items():
            detected = PatternRecognizer._recognize_single(kline_data.df)
            if detected:
                patterns[interval] = detected

        logger.info(f"识别到 {sum(len(p) for p in patterns.values())} 个形态")
        return patterns

    @staticmethod
    def _recognize_single(df: pd.DataFrame) -> List[CandlestickPattern]:
        """
        识别单周期形态

        Args:
            df: K线 DataFrame

        Returns:
            [CandlestickPattern]
        """
        if df is None or len(df) < 3:
            return []

        patterns = []
        close = df['close'].astype(float)
        open_ = df['open'].astype(float)
        high = df['high'].astype(float)
        low = df['low'].astype(float)

        # 最新K线
        current = len(df) - 1

        # 1. 锤子线 / 倒锤子线
        body = abs(close.iloc[current] - open_.iloc[current])
        upper_shadow = high.iloc[current] - max(close.iloc[current], open_.iloc[current])
        lower_shadow = min(close.iloc[current], open_.iloc[current]) - low.iloc[current]
        total_range = high.iloc[current] - low.iloc[current]

        if total_range > 0:
            body_ratio = body / total_range
            upper_ratio = upper_shadow / total_range
            lower_ratio = lower_shadow / total_range

            # 锤子线: 下影线是实体的2倍以上，上影线很短
            if lower_ratio > 0.6 and body_ratio < 0.4 and upper_ratio < 0.1:
                confidence = lower_ratio * 0.9
                patterns.append(CandlestickPattern(
                    name='锤子线',
                    interval='',
                    confidence=confidence,
                    direction='bullish',
                    description='下影线是实体的2倍以上，看涨反转信号'
                ))

            # 倒锤子线: 上影线是实体的2倍以上，下影线很短
            elif upper_ratio > 0.6 and body_ratio < 0.4 and lower_ratio < 0.1:
                confidence = upper_ratio * 0.9
                patterns.append(CandlestickPattern(
                    name='倒锤子线',
                    interval='',
                    confidence=confidence,
                    direction='bullish',
                    description='上影线是实体的2倍以上，看涨反转信号'
                ))

        # 2. 吞没形态 (需要至少2根K线)
        if len(df) >= 2:
            prev = current - 1
            prev_body = abs(close.iloc[prev] - open_.iloc[prev])
            curr_body = abs(close.iloc[current] - open_.iloc[current])

            # 看涨吞没: 阴包阳
            if (close.iloc[prev] < open_.iloc[prev] and  # 前一根是阴线
                close.iloc[current] > open_.iloc[current] and  # 当前是阳线
                close.iloc[current] > open_.iloc[prev] and  # 当前收盘价超过前一根开盘价
                open_.iloc[current] < close.iloc[prev]):  # 当前开盘价低于前一根收盘价

                confidence = min(1.0, curr_body / prev_body * 0.8)
                patterns.append(CandlestickPattern(
                    name='看涨吞没',
                    interval='',
                    confidence=confidence,
                    direction='bullish',
                    description='阴包阳形态，多头反转信号'
                ))

            # 看跌吞没: 阳包阴
            elif (close.iloc[prev] > open_.iloc[prev] and  # 前一根是阳线
                  close.iloc[current] < open_.iloc[current] and  # 当前是阴线
                  close.iloc[current] < open_.iloc[prev] and  # 当前收盘价低于前一根开盘价
                  open_.iloc[current] > close.iloc[prev]):  # 当前开盘价高于前一根收盘价

                confidence = min(1.0, curr_body / prev_body * 0.8)
                patterns.append(CandlestickPattern(
                    name='看跌吞没',
                    interval='',
                    confidence=confidence,
                    direction='bearish',
                    description='阳包阴形态，空头反转信号'
                ))

        # 3. 十字星
        body = abs(close.iloc[current] - open_.iloc[current])
        total_range = high.iloc[current] - low.iloc[current]
        if total_range > 0 and body / total_range < 0.1:
            # 长上下影线
            upper_shadow = high.iloc[current] - max(close.iloc[current], open_.iloc[current])
            lower_shadow = min(close.iloc[current], open_.iloc[current]) - low.iloc[current]
            if upper_shadow > body and lower_shadow > body:
                patterns.append(CandlestickPattern(
                    name='十字星',
                    interval='',
                    confidence=0.7,
                    direction='neutral',
                    description='长上下影线，市场犹豫信号'
                ))

        # 4. 早晨之星 / 黄昏之星 (需要3根K线)
        if len(df) >= 3:
            first = current - 2
            second = current - 1

            # 早晨之星: 大阴线 + 小星线 + 大阳线
            first_body = abs(close.iloc[first] - open_.iloc[first])
            second_body = abs(close.iloc[second] - open_.iloc[second])
            third_body = abs(close.iloc[current] - open_.iloc[current])

            if (close.iloc[first] < open_.iloc[first] and  # 第一根阴线
                second_body < first_body * 0.3 and  # 第二根星线
                close.iloc[current] > open_.iloc[current] and  # 第三根阳线
                close.iloc[current] > (open_.iloc[first] + close.iloc[first]) / 2):  # 收盘超过第一天中点

                patterns.append(CandlestickPattern(
                    name='早晨之星',
                    interval='',
                    confidence=0.75,
                    direction='bullish',
                    description='三根K线组合，多头反转信号'
                ))

            # 黄昏之星: 大阳线 + 小星线 + 大阴线
            elif (close.iloc[first] > open_.iloc[first] and  # 第一根阳线
                  second_body < first_body * 0.3 and  # 第二根星线
                  close.iloc[current] < open_.iloc[current] and  # 第三根阴线
                  close.iloc[current] < (open_.iloc[first] + close.iloc[first]) / 2):  # 收盘低于第一天中点

                patterns.append(CandlestickPattern(
                    name='黄昏之星',
                    interval='',
                    confidence=0.75,
                    direction='bearish',
                    description='三根K线组合，空头反转信号'
                ))

        # 5. 刺透形态 / 乌云盖顶
        if len(df) >= 2:
            prev = current - 1

            # 刺透: 阴线后阳线切入
            if (close.iloc[prev] < open_.iloc[prev] and
                close.iloc[current] > open_.iloc[current] and
                close.iloc[current] > open_.iloc[prev] and
                close.iloc[current] < open_.iloc[prev] + (open_.iloc[prev] - close.iloc[prev]) * 0.5):
                patterns.append(CandlestickPattern(
                    name='刺透形态',
                    interval='',
                    confidence=0.65,
                    direction='bullish',
                    description='阳线切入阴线实体50%以上，看涨'
                ))

            # 乌云盖顶: 阳线后阴线覆盖
            elif (close.iloc[prev] > open_.iloc[prev] and
                  close.iloc[current] < open_.iloc[current] and
                  close.iloc[current] < open_.iloc[prev] and
                  close.iloc[current] > open_.iloc[prev] - (close.iloc[prev] - open_.iloc[prev]) * 0.5):
                patterns.append(CandlestickPattern(
                    name='乌云盖顶',
                    interval='',
                    confidence=0.65,
                    direction='bearish',
                    description='阴线覆盖阳线实体50%以上，看跌'
                ))

        # 按置信度排序，返回前3个
        patterns.sort(key=lambda x: x.confidence, reverse=True)
        return patterns[:3]
