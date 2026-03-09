"""
Alpha 因子库 (qlib 风格) v2.0

提供可供 AI 学习的关键因子：
- 动量因子 (Momentum)
- 均值回归因子 (Mean Reversion)
- 波动率因子 (Volatility)
- 成交量因子 (Volume)
- 趋势因子 (Trend)
- 布林带因子 (Bollinger Bands)
- MACD 因子
- RSI 因子
- KDJ 因子
- ATR 因子
- 威廉指标因子
- CCI 因子
- 复合因子 (Composite)

v2.0 新增：
- 更多技术指标因子
- 批量计算优化
- 因子分组功能

参考: https://github.com/microsoft/qlib
"""
import logging
from typing import Dict, List, Optional, Tuple
import pandas as pd
import numpy as np

from .expression_engine import ExpressionEngine, ExpressionTemplates

logger = logging.getLogger(__name__)


class AlphaFactor:
    """Alpha 因子"""

    def __init__(self, name: str, expression: str, category: str, description: str = ""):
        self.name = name
        self.expression = expression
        self.category = category
        self.description = description

    def calculate(self, df: pd.DataFrame) -> pd.Series:
        """计算因子值"""
        try:
            engine = ExpressionEngine(df)
            return engine.evaluate(self.expression)
        except Exception as e:
            logger.error(f"计算因子 {self.name} 失败: {e}")
            return pd.Series(0, index=df.index)


class AlphaFactorLibrary:
    """Alpha 因子库 v2.0"""

    # 类别常量
    MOMENTUM = "动量"
    MEAN_REVERSION = "均值回归"
    VOLATILITY = "波动率"
    VOLUME = "成交量"
    TREND = "趋势"
    BOLLINGER = "布林带"
    MACD = "MACD"
    RSI = "RSI"
    KDJ = "KDJ"
    ATR = "ATR"
    WILLIAM = "威廉指标"
    CCI = "CCI"
    COMPOSITE = "复合"

    def __init__(self):
        self.factors: Dict[str, AlphaFactor] = {}
        self._register_factors()

    def _register_factors(self):
        """注册所有因子"""

        # ========== 动量因子 ==========

        # 短期动量
        self.register(AlphaFactor(
            "momentum_5d", "Ref($close, -5) / $close - 1",
            self.MOMENTUM, "5 日动量"
        ))
        self.register(AlphaFactor(
            "momentum_10d", "Ref($close, -10) / $close - 1",
            self.MOMENTUM, "10 日动量"
        ))
        self.register(AlphaFactor(
            "momentum_20d", "Ref($close, -20) / $close - 1",
            self.MOMENTUM, "20 日动量"
        ))
        self.register(AlphaFactor(
            "momentum_60d", "Ref($close, -60) / $close - 1",
            self.MOMENTUM, "60 日动量"
        ))

        # 动量变化（加速度）
        self.register(AlphaFactor(
            "momentum_accel_5d", "Delta(Ref($close, -5) / $close - 1, 5)",
            self.MOMENTUM, "5 日动量加速度"
        ))

        # 动量均值
        self.register(AlphaFactor(
            "momentum_ma_5_20d", "Mean(Ref($close, -5) / $close - 1, 20)",
            self.MOMENTUM, "5 日动量的 20 日均值"
        ))

        # ========== 均值回归因子 ==========

        self.register(AlphaFactor(
            "mean_reversion_5d", "$close / Mean($close, 5) - 1",
            self.MEAN_REVERSION, "价格偏离 5 日均线"
        ))
        self.register(AlphaFactor(
            "mean_reversion_20d", "$close / Mean($close, 20) - 1",
            self.MEAN_REVERSION, "价格偏离 20 日均线"
        ))
        self.register(AlphaFactor(
            "mean_reversion_60d", "$close / Mean($close, 60) - 1",
            self.MEAN_REVERSION, "价格偏离 60 日均线"
        ))

        # ========== 波动率因子 ==========

        self.register(AlphaFactor(
            "volatility_5d", "Std(Log($close/Ref($close, 1)), 5)",
            self.VOLATILITY, "5 日波动率"
        ))
        self.register(AlphaFactor(
            "volatility_10d", "Std(Log($close/Ref($close, 1)), 10)",
            self.VOLATILITY, "10 日波动率"
        ))
        self.register(AlphaFactor(
            "volatility_20d", "Std(Log($close/Ref($close, 1)), 20)",
            self.VOLATILITY, "20 日波动率"
        ))
        self.register(AlphaFactor(
            "volatility_60d", "Std(Log($close/Ref($close, 1)), 60)",
            self.VOLATILITY, "60 日波动率"
        ))

        # 价格范围波动率
        self.register(AlphaFactor(
            "price_range_5d", "Std(($high - $low) / $close, 5)",
            self.VOLATILITY, "5 日价格范围波动"
        ))
        self.register(AlphaFactor(
            "price_range_20d", "Std(($high - $low) / $close, 20)",
            self.VOLATILITY, "20 日价格范围波动"
        ))

        # ========== 成交量因子 ==========

        self.register(AlphaFactor(
            "volume_change_1d", "Ref($volume, -1) / $volume - 1",
            self.VOLUME, "1 日成交量变化"
        ))
        self.register(AlphaFactor(
            "volume_change_5d", "Ref($volume, -5) / $volume - 1",
            self.VOLUME, "5 日成交量变化"
        ))
        self.register(AlphaFactor(
            "volume_ma_ratio_5d", "$volume / Mean($volume, 5) - 1",
            self.VOLUME, "成交量偏离 5 日均值"
        ))
        self.register(AlphaFactor(
            "volume_ma_ratio_20d", "$volume / Mean($volume, 20) - 1",
            self.VOLUME, "成交量偏离 20 日均值"
        ))

        # 成交量与价格相关性
        self.register(AlphaFactor(
            "price_volume_corr_5d", "Corr($close, $volume, 5)",
            self.VOLUME, "5 日价量相关性"
        ))
        self.register(AlphaFactor(
            "price_volume_corr_20d", "Corr($close, $volume, 20)",
            self.VOLUME, "20 日价量相关性"
        ))

        # OBV 变化
        self.register(AlphaFactor(
            "obv_change_5d", "Ref(Sign($close - Ref($close, 1)) * $volume, -5) / ($volume + 1)",
            self.VOLUME, "5 日 OBV 变化"
        ))

        # ========== 趋势因子 ==========

        # 均线交叉
        self.register(AlphaFactor(
            "ma_cross_5_20", "Mean($close, 5) / Mean($close, 20) - 1",
            self.TREND, "5/20 日均线交叉"
        ))
        self.register(AlphaFactor(
            "ma_cross_10_60", "Mean($close, 10) / Mean($close, 60) - 1",
            self.TREND, "10/60 日均线交叉"
        ))
        self.register(AlphaFactor(
            "ma_cross_20_200", "Mean($close, 20) / Mean($close, 200) - 1",
            self.TREND, "20/200 日均线交叉"
        ))

        # EMA 斜率
        self.register(AlphaFactor(
            "ema_slope_5d", "(EMA($close, 5) - Ref(EMA($close, 5), 5)) / EMA($close, 5)",
            self.TREND, "5 日 EMA 斜率"
        ))
        self.register(AlphaFactor(
            "ema_slope_20d", "(EMA($close, 20) - Ref(EMA($close, 20), 20)) / EMA($close, 20)",
            self.TREND, "20 日 EMA 斜率"
        ))

        # 趋势强度
        self.register(AlphaFactor(
            "trend_strength_20d", "(Mean($close, 10) - Mean($close, 20)) / Mean($close, 20)",
            self.TREND, "20 日趋势强度"
        ))

        # ========== 布林带因子 ==========

        self.register(AlphaFactor(
            "bb_position_20d", "BB_POSITION($close, 20, 2)",
            self.BOLLINGER, "20 日布林带位置 (0-1)"
        ))
        self.register(AlphaFactor(
            "bb_width_20d", "BB_WIDTH($close, 20, 2)",
            self.BOLLINGER, "20 日布林带宽度"
        ))

        # ========== MACD 因子 ==========

        self.register(AlphaFactor(
            "macd_diff", "MACD($close, 12, 26)",
            self.MACD, "MACD 差值"
        ))
        self.register(AlphaFactor(
            "macd_signal", "MACD_SIGNAL($close, 12, 26, 9)",
            self.MACD, "MACD 信号线"
        ))
        self.register(AlphaFactor(
            "macd_histogram", "MACD_HIST($close, 12, 26, 9)",
            self.MACD, "MACD 柱状图"
        ))

        # ========== RSI 因子 ==========

        self.register(AlphaFactor(
            "rsi_6d", "RSI($close, 6)",
            self.RSI, "6 日 RSI"
        ))
        self.register(AlphaFactor(
            "rsi_12d", "RSI($close, 12)",
            self.RSI, "12 日 RSI"
        ))
        self.register(AlphaFactor(
            "rsi_24d", "RSI($close, 24)",
            self.RSI, "24 日 RSI"
        ))

        # RSI 变化
        self.register(AlphaFactor(
            "rsi_change_5d", "Ref(RSI($close, 6), -5) - RSI($close, 6)",
            self.RSI, "RSI 5 日变化"
        ))

        # ========== KDJ 因子 ==========

        self.register(AlphaFactor(
            "kdj_k_9d", "KDJ_K($high, $low, $close, 9)",
            self.KDJ, "9 日 KDJ K 线"
        ))
        self.register(AlphaFactor(
            "kdj_d_9d", "KDJ_D($high, $low, $close, 9)",
            self.KDJ, "9 日 KDJ D 线"
        ))
        self.register(AlphaFactor(
            "kdj_j_9d", "KDJ_J($high, $low, $close, 9)",
            self.KDJ, "9 日 KDJ J 线"
        ))

        # ========== ATR 因子 ==========

        self.register(AlphaFactor(
            "atr_14d", "ATR($high, $low, $close, 14)",
            self.ATR, "14 日 ATR"
        ))
        self.register(AlphaFactor(
            "atr_20d", "ATR($high, $low, $close, 20)",
            self.ATR, "20 日 ATR"
        ))

        # ATR 百分比
        self.register(AlphaFactor(
            "atr_pct_14d", "ATR($high, $low, $close, 14) / $close",
            self.ATR, "14 日 ATR 百分比"
        ))

        # ========== 威廉指标因子 ==========

        self.register(AlphaFactor(
            "wr_14d", "100 * ($high - $close) / ($high - $low)",
            self.WILLIAM, "14 日威廉指标"
        ))

        # ========== CCI 因子 ==========

        self.register(AlphaFactor(
            "cci_14d", "($close - Mean(($high + $low + $close) / 3, 14)) / (0.015 * Std(($high + $low + $close) / 3, 14))",
            self.CCI, "14 日 CCI"
        ))

        # ========== 复合因子 ==========

        # 动量波动率比
        self.register(AlphaFactor(
            "momentum_vol_ratio_20d", "(Ref($close, -20) / $close - 1) / Std(Log($close/Ref($close, 1)), 20)",
            self.COMPOSITE, "20 日动量/波动率比"
        ))

        # 价量综合
        self.register(AlphaFactor(
            "price_volume_20d", "(Mean($close, 20) / $close) * (Mean($volume, 20) / $volume)",
            self.COMPOSITE, "20 日价量综合因子"
        ))

        # 趋势成交量综合
        self.register(AlphaFactor(
            "trend_volume_20d", "(Mean($close, 10) / Mean($close, 20) - 1) * (Mean($volume, 10) / Mean($volume, 20))",
            self.COMPOSITE, "趋势成交量综合"
        ))

    def register(self, factor: AlphaFactor):
        """注册因子"""
        self.factors[factor.name] = factor
        logger.debug(f"注册因子: {factor.name}")

    def get(self, name: str) -> Optional[AlphaFactor]:
        """获取因子"""
        return self.factors.get(name)

    def get_by_category(self, category: str) -> List[AlphaFactor]:
        """按类别获取因子"""
        return [f for f in self.factors.values() if f.category == category]

    def get_all_names(self) -> List[str]:
        """获取所有因子名称"""
        return list(self.factors.keys())

    def get_by_names(self, names: List[str]) -> Dict[str, AlphaFactor]:
        """获取指定因子"""
        return {name: self.factors[name] for name in names if name in self.factors}

    def calculate(self, df: pd.DataFrame, factor_names: Optional[List[str]] = None) -> pd.DataFrame:
        """
        计算因子

        Args:
            df: 包含 OHLCV 数据的 DataFrame
            factor_names: 要计算的因子名称列表，None 表示全部

        Returns:
            因子 DataFrame
        """
        if factor_names is None:
            factors = self.factors.values()
        else:
            factors = [self.factors[name] for name in factor_names if name in self.factors]

        result = {}
        for factor in factors:
            try:
                result[factor.name] = factor.calculate(df)
                logger.debug(f"计算因子: {factor.name}")
            except Exception as e:
                logger.error(f"计算因子 {factor.name} 失败: {e}")

        return pd.DataFrame(result)

    def calculate_batch(self, df: pd.DataFrame, categories: Optional[List[str]] = None) -> pd.DataFrame:
        """
        按类别计算因子

        Args:
            df: 包含 OHLCV 数据的 DataFrame
            categories: 要计算的类别列表，None 表示全部

        Returns:
            因子 DataFrame
        """
        if categories is None:
            return self.calculate(df)

        factors = []
        for cat in categories:
            factors.extend(self.get_by_category(cat))

        factor_names = [f.name for f in factors]
        return self.calculate(df, factor_names)

    def calculate_optimized(self, df: pd.DataFrame, factor_names: Optional[List[str]] = None) -> pd.DataFrame:
        """
        优化计算因子（复用 ExpressionEngine）

        Args:
            df: 包含 OHLCV 数据的 DataFrame
            factor_names: 要计算的因子名称列表

        Returns:
            因子 DataFrame
        """
        if factor_names is None:
            factors = self.factors.values()
        else:
            factors = [self.factors[name] for name in factor_names if name in self.factors]

        # 创建一个共享的 engine
        engine = ExpressionEngine(df)

        result = {}
        for factor in factors:
            try:
                result[factor.name] = engine.evaluate(factor.expression)
            except Exception as e:
                logger.error(f"计算因子 {factor.name} 失败: {e}")

        return pd.DataFrame(result)

    def get_factor_groups(self) -> Dict[str, List[str]]:
        """获取预设因子组"""
        return {
            # 基础因子
            'basic': [
                'momentum_5d', 'momentum_20d',
                'volatility_20d', 'volume_ma_ratio_20d',
            ],
            # 技术指标
            'technical': [
                'rsi_6d', 'rsi_12d', 'rsi_24d',
                'macd_diff', 'macd_signal',
                'kdj_k_9d', 'kdj_d_9d', 'kdj_j_9d',
                'atr_14d', 'bb_position_20d',
            ],
            # 趋势
            'trend': [
                'ma_cross_5_20', 'ma_cross_20_200',
                'ema_slope_20d', 'trend_strength_20d',
            ],
            # 动量
            'momentum': [
                'momentum_5d', 'momentum_10d', 'momentum_20d', 'momentum_60d',
                'momentum_accel_5d',
            ],
            # 波动率
            'volatility': [
                'volatility_5d', 'volatility_10d', 'volatility_20d', 'volatility_60d',
                'atr_14d', 'atr_20d', 'bb_width_20d',
            ],
            # 成交量
            'volume': [
                'volume_change_1d', 'volume_change_5d',
                'volume_ma_ratio_5d', 'volume_ma_ratio_20d',
                'price_volume_corr_20d',
            ],
            # 完整因子
            'full': list(self.factors.keys()),
        }

    def get_group(self, group_name: str) -> List[str]:
        """获取预设因子组"""
        groups = self.get_factor_groups()
        return groups.get(group_name, [])

    def calculate_group(self, df: pd.DataFrame, group_name: str) -> pd.DataFrame:
        """计算预设因子组"""
        factor_names = self.get_group(group_name)
        return self.calculate(df, factor_names)

    def analyze_correlation(self, df: pd.DataFrame, factor_names: Optional[List[str]] = None,
                           top_n: int = 10) -> pd.DataFrame:
        """
        分析因子相关性

        Args:
            df: 包含 OHLCV 数据的 DataFrame
            factor_names: 要分析的因子列表
            top_n: 返回前 N 个高度相关的因子对

        Returns:
            相关性矩阵
        """
        if factor_names is None:
            factor_names = list(self.factors.keys())[:20]

        # 计算因子
        factors_df = self.calculate(df, factor_names)

        # 计算相关性
        corr_matrix = factors_df.corr()

        # 提取高度相关的因子对
        high_corr = []
        for i in range(len(corr_matrix.columns)):
            for j in range(i + 1, len(corr_matrix.columns)):
                corr_val = corr_matrix.iloc[i, j]
                if abs(corr_val) > 0.8:
                    high_corr.append({
                        'factor1': corr_matrix.columns[i],
                        'factor2': corr_matrix.columns[j],
                        'correlation': corr_val
                    })

        if high_corr:
            high_corr_df = pd.DataFrame(high_corr)
            high_corr_df = high_corr_df.sort_values('correlation', key=abs, ascending=False)
            return high_corr_df.head(top_n)

        return pd.DataFrame()

    def print_summary(self):
        """打印因子库摘要"""
        logger.info("=" * 60)
        logger.info("Alpha 因子库摘要")
        logger.info("=" * 60)

        # 按类别统计
        categories = {}
        for factor in self.factors.values():
            if factor.category not in categories:
                categories[factor.category] = []
            categories[factor.category].append(factor.name)

        for cat, names in categories.items():
            logger.info(f"\n{cat} ({len(names)} 个):")
            for name in names:
                logger.info(f"  - {name}")

        logger.info(f"\n总计: {len(self.factors)} 个因子")
        logger.info("=" * 60)


# 全局因子库实例
_alpha_library: Optional[AlphaFactorLibrary] = None


def get_alpha_library() -> AlphaFactorLibrary:
    """获取全局因子库实例"""
    global _alpha_library
    if _alpha_library is None:
        _alpha_library = AlphaFactorLibrary()
    return _alpha_library


def calculate_factors(df: pd.DataFrame, factor_names: Optional[List[str]] = None) -> pd.DataFrame:
    """
    快速计算因子

    Args:
        df: 包含 OHLCV 数据的 DataFrame
        factor_names: 要计算的因子名称列表

    Returns:
        因子 DataFrame
    """
    library = get_alpha_library()
    return library.calculate(df, factor_names)


def get_factor_names() -> List[str]:
    """获取所有因子名称"""
    return get_alpha_library().get_all_names()


# ============================================================
# 标签定义 (用于训练)
# ============================================================

class LabelDefinition:
    """标签定义"""

    # 未来收益率 (qlib Alpha158 标准标签)
    LABEL_RETURN_1 = 'Ref($close, -2) / Ref($close, -1) - 1'  # T+1 到 T+2 收益率
    LABEL_RETURN_2 = 'Ref($close, -3) / Ref($close, -1) - 1'  # T+1 到 T+3 收益率
    LABEL_RETURN_5 = 'Ref($close, -5) / Ref($close, -1) - 1'  # T+1 到 T+5 收益率

    @staticmethod
    def get_label(expression: str) -> pd.Series:
        """
        计算标签

        注意：标签需要 shift(-1) 避免前视偏差
        """
        # 这里的实现需要在具体数据上计算
        pass


# ============================================================
# 因子权重建议 (AI 可参考)
# ============================================================

class FactorWeights:
    """因子权重建议"""

    # 动量因子权重
    MOMENTUM_WEIGHTS = {
        'momentum_5d': 0.3,
        'momentum_10d': 0.25,
        'momentum_20d': 0.25,
        'momentum_60d': 0.2,
    }

    # 波动率因子权重
    VOLATILITY_WEIGHTS = {
        'volatility_5d': 0.2,
        'volatility_10d': 0.3,
        'volatility_20d': 0.3,
        'volatility_60d': 0.2,
    }

    # 趋势因子权重
    TREND_WEIGHTS = {
        'ma_cross_5_20': 0.3,
        'ma_cross_10_60': 0.35,
        'ma_cross_20_200': 0.35,
    }

    # 成交量因子权重
    VOLUME_WEIGHTS = {
        'volume_change_1d': 0.2,
        'volume_change_5d': 0.25,
        'volume_ma_ratio_5d': 0.25,
        'volume_ma_ratio_20d': 0.3,
    }

    @classmethod
    def get_weights(cls, category: str) -> Dict[str, float]:
        """获取类别权重"""
        return getattr(cls, f'{category.upper()}_WEIGHTS', {})

    @classmethod
    def get_all_weights(cls) -> Dict[str, float]:
        """获取所有权重"""
        weights = {}
        weights.update(cls.MOMENTUM_WEIGHTS)
        weights.update(cls.VOLATILITY_WEIGHTS)
        weights.update(cls.TREND_WEIGHTS)
        weights.update(cls.VOLUME_WEIGHTS)
        return weights
