"""
数据预处理模块 (qlib 风格)

提供标准化的数据预处理处理器：
- ZscoreNorm: Z-Score 标准化
- MinMaxNorm: 最小最大归一化
- CSZScoreNorm: 截面 Z-Score 标准化
- CSRankNorm: 截面排名标准化
- DropnaProcessor: 去除 N/A 值
- ProcessInf: 处理无穷值
- TanhProcess: Tanh 处理噪声数据

参考: https://github.com/microsoft/qlib
"""
import logging
from typing import Optional, Dict, Any, List
from abc import ABC, abstractmethod
import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


class BaseProcessor(ABC):
    """处理器基类"""

    @abstractmethod
    def fit(self, df: pd.DataFrame) -> 'BaseProcessor':
        """拟合数据"""
        pass

    @abstractmethod
    def transform(self, df: pd.DataFrame) -> pd.DataFrame:
        """转换数据"""
        pass

    def fit_transform(self, df: pd.DataFrame) -> pd.DataFrame:
        """拟合并转换"""
        self.fit(df)
        return self.transform(df)


class ZscoreNorm(BaseProcessor):
    """
    Z-Score 标准化

    公式: (x - mean) / std

    适用于：特征标准化，使不同量纲的特征可比
    """

    def __init__(self, window: Optional[int] = None):
        """
        Args:
            window: 滚动窗口大小。如果为 None，则使用全局统计
        """
        self.window = window
        self.mean: Optional[pd.Series] = None
        self.std: Optional[pd.Series] = None

    def fit(self, df: pd.DataFrame) -> 'ZscoreNorm':
        """拟合统计量"""
        if self.window is None:
            # 全局统计
            self.mean = df.mean()
            self.std = df.std()
        else:
            # 滚动统计（不直接存储，在 transform 中计算）
            logger.info(f"ZscoreNorm 使用滚动窗口 {self.window}")
        return self

    def transform(self, df: pd.DataFrame) -> pd.DataFrame:
        """Z-Score 标准化"""
        if self.window is None:
            # 全局标准化
            return (df - self.mean) / self.std.replace(0, np.nan)
        else:
            # 滚动标准化
            mean = df.rolling(window=self.window, min_periods=1).mean()
            std = df.rolling(window=self.window, min_periods=1).std()
            return (df - mean) / std.replace(0, np.nan)


class MinMaxNorm(BaseProcessor):
    """
    最小最大归一化

    公式: (x - min) / (max - min)

    适用于：将特征归一化到 [0, 1] 范围
    """

    def __init__(self, feature_range: tuple = (0, 1), window: Optional[int] = None):
        """
        Args:
            feature_range: 目标范围
            window: 滚动窗口大小
        """
        self.feature_range = feature_range
        self.window = window
        self.min_val: Optional[pd.Series] = None
        self.max_val: Optional[pd.Series] = None

    def fit(self, df: pd.DataFrame) -> 'MinMaxNorm':
        """拟合统计量"""
        if self.window is None:
            self.min_val = df.min()
            self.max_val = df.max()
        return self

    def transform(self, df: pd.DataFrame) -> pd.DataFrame:
        """归一化"""
        if self.window is None:
            min_val = self.min_val
            max_val = self.max_val
        else:
            min_val = df.rolling(window=self.window, min_periods=1).min()
            max_val = df.rolling(window=self.window, min_periods=1).max()

        # 归一化到 [0, 1]
        normalized = (df - min_val) / (max_val - min_val).replace(0, np.nan)

        # 缩放到目标范围
        if self.feature_range != (0, 1):
            min_f, max_f = self.feature_range
            normalized = normalized * (max_f - min_f) + min_f

        return normalized


class RobustZScoreNorm(BaseProcessor):
    """
    鲁棒 Z-Score 标准化

    使用中位数和 MAD (中位数绝对偏差) 而非均值和标准差
    对异常值更加鲁棒

    公式: (x - median) / MAD, 其中 MAD = median(|x - median|)
    """

    def __init__(self, window: Optional[int] = None, limit: float = 5.0):
        """
        Args:
            window: 滚动窗口大小
            limit: 异常值限制阈值
        """
        self.window = window
        self.limit = limit
        self.median: Optional[pd.Series] = None
        self.mad: Optional[pd.Series] = None

    def fit(self, df: pd.DataFrame) -> 'RobustZScoreNorm':
        """拟合统计量"""
        if self.window is None:
            self.median = df.median()
            self.mad = (df - self.median).abs().median()
        return self

    def transform(self, df: pd.DataFrame) -> pd.DataFrame:
        """鲁棒 Z-Score 标准化"""
        if self.window is None:
            median = self.median
            mad = self.mad
        else:
            median = df.rolling(window=self.window, min_periods=1).median()
            mad = (df - median).abs().rolling(window=self.window, min_periods=1).median()

        # 标准化
        normalized = (df - median) / mad.replace(0, np.nan)

        # 限制异常值
        normalized = normalized.clip(-self.limit, self.limit)

        return normalized


class CSZScoreNorm(BaseProcessor):
    """
    截面 Z-Score 标准化

    在每个时间点，对所有标的进行 Z-Score 标准化
    常用于多标的选择

    公式: (x - cross_section_mean) / cross_section_std
    """

    def __init__(self):
        pass

    def fit(self, df: pd.DataFrame) -> 'CSZScoreNorm':
        return self

    def transform(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        截面标准化

        注意：df 的 index 应该是时间，columns 应该是标的
        """
        # 每个时间点的截面均值和标准差
        mean = df.mean(axis=1)
        std = df.std(axis=1)

        # 广播到所有列
        return (df.sub(mean, axis=0)).div(std.replace(0, np.nan), axis=0)


class CSRankNorm(BaseProcessor):
    """
    截面排名标准化

    在每个时间点，对所有标的进行排名
    常用于多标的选择，消除量纲影响

    公式: rank(x) / N (0-1 之间)
    """

    def __init__(self, clip_outlier: bool = True, lower: float = 0.0, upper: float = 1.0):
        """
        Args:
            clip_outlier: 是否裁剪异常值
            lower: 排名下限
            upper: 排名上限
        """
        self.clip_outlier = clip_outlier
        self.lower = lower
        self.upper = upper

    def fit(self, df: pd.DataFrame) -> 'CSRankNorm':
        return self

    def transform(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        截面排名

        注意：df 的 index 应该是时间，columns 应该是标的
        """
        # 每个时间点的截面排名
        ranked = df.rank(axis=1, pct=True)

        if self.clip_outlier:
            # 裁剪极端值 (如前 0.25% 和后 0.25%)
            ranked = ranked.clip(self.lower, self.upper)

        return ranked


class CSMedianNorm(BaseProcessor):
    """
    截面中位数标准化

    在每个时间点，减去中位数

    公式: x - cross_section_median
    """

    def __init__(self):
        pass

    def fit(self, df: pd.DataFrame) -> 'CSMedianNorm':
        return self

    def transform(self, df: pd.DataFrame) -> pd.DataFrame:
        """截面中位数标准化"""
        median = df.median(axis=1)
        return df.sub(median, axis=0)


class CSFillna(BaseProcessor):
    """
    截面均值填充

    用每个时间点的截面均值填充 N/A 值
    """

    def __init__(self):
        pass

    def fit(self, df: pd.DataFrame) -> 'CSFillna':
        return self

    def transform(self, df: pd.DataFrame) -> pd.DataFrame:
        """截面均值填充"""
        mean = df.mean(axis=1)
        return df.fillna(mean, axis=0)


class DropnaProcessor(BaseProcessor):
    """去除 N/A 值"""

    def __init__(self, how: str = 'any', threshold: Optional[float] = None):
        """
        Args:
            how: 'any' - 任意 N/A 则去除整行/列
                 'all' - 全部为 N/A 才去除
            threshold: 阈值，N/A 比例超过此值则去除
        """
        self.how = how
        self.threshold = threshold

    def fit(self, df: pd.DataFrame) -> 'DropnaProcessor':
        return self

    def transform(self, df: pd.DataFrame) -> pd.DataFrame:
        if self.threshold is not None:
            # 按阈值去除
            na_ratio = df.isna().mean()
            if na_ratio.max() > self.threshold:
                df = df.dropna(axis=1, thresh=int(len(df) * (1 - self.threshold)))
        else:
            df = df.dropna(how=self.how)
        return df


class ProcessInf(BaseProcessor):
    """处理无穷值"""

    def __init__(self, method: str = 'replace_mean'):
        """
        Args:
            method: 处理方法
                - 'replace_mean': 替换为均值
                - 'replace_median': 替换为中位数
                - 'clip': 裁剪到有限范围
                - 'drop': 去除包含无穷值的行/列
        """
        self.method = method

    def fit(self, df: pd.DataFrame) -> 'ProcessInf':
        self.mean = df.replace([np.inf, -np.inf], np.nan).mean()
        self.median = df.replace([np.inf, -np.inf], np.nan).median()
        return self

    def transform(self, df: pd.DataFrame) -> pd.DataFrame:
        if self.method == 'replace_mean':
            return df.replace([np.inf, -np.inf], np.nan).fillna(self.mean)
        elif self.method == 'replace_median':
            return df.replace([np.inf, -np.inf], np.nan).fillna(self.median)
        elif self.method == 'clip':
            df = df.replace([np.inf, -np.inf], np.nan)
            finite_vals = df.dropna()
            if len(finite_vals) > 0:
                return df.clip(finite_vals.min().min(), finite_vals.max().max())
            return df
        elif self.method == 'drop':
            return df.replace([np.inf, -np.inf], np.nan).dropna()
        return df


class TanhProcessor(BaseProcessor):
    """
    Tanh 处理器

    使用 tanh 函数处理数据，减少异常值影响
    同时将数据归一化到 (-1, 1) 范围

    公式: tanh(x)
    """

    def __init__(self, threshold: Optional[float] = 3.0):
        """
        Args:
            threshold: 阈值，超过此值的数据先进行 Z-Score 标准化
        """
        self.threshold = threshold

    def fit(self, df: pd.DataFrame) -> 'TanhProcessor':
        self.mean = df.mean()
        self.std = df.std()
        return self

    def transform(self, df: pd.DataFrame) -> pd.DataFrame:
        if self.threshold is not None:
            # 先 Z-Score 标准化
            z = (df - self.mean) / self.std.replace(0, np.nan)
            # 裁剪
            z = z.clip(-self.threshold, self.threshold)
            # Tanh 变换
            return np.tanh(z)
        else:
            return np.tanh(df)


class FillnaProcessor(BaseProcessor):
    """填充 N/A 值"""

    def __init__(self, method: str = 'ffill', value: Optional[float] = None):
        """
        Args:
            method: 填充方法
                - 'ffill': 前向填充
                - 'bfill': 后向填充
                - 'mean': 均值填充
                - 'median': 中位数填充
                - 'zero': 填充为 0
                - 'value': 指定值填充
        """
        self.method = method
        self.value = value

    def fit(self, df: pd.DataFrame) -> 'FillnaProcessor':
        if self.method in ('mean', 'median'):
            self.fill_value = df.mean() if self.method == 'mean' else df.median()
        return self

    def transform(self, df: pd.DataFrame) -> pd.DataFrame:
        if self.method == 'ffill':
            return df.fillna(method='ffill')
        elif self.method == 'bfill':
            return df.fillna(method='bfill')
        elif self.method in ('mean', 'median'):
            return df.fillna(self.fill_value)
        elif self.method == 'zero':
            return df.fillna(0)
        elif self.method == 'value':
            return df.fillna(self.value)
        return df


class ClipProcessor(BaseProcessor):
    """裁剪异常值"""

    def __init__(self, lower: Optional[float] = None, upper: Optional[float] = None,
                 method: str = 'std', n_std: float = 3.0):
        """
        Args:
            lower: 下界
            upper: 上界
            method: 'std' - 使用标准差
                   'percentile' - 使用百分位
            n_std: 标准差倍数 (method='std' 时使用)
        """
        self.lower = lower
        self.upper = upper
        self.method = method
        self.n_std = n_std

    def fit(self, df: pd.DataFrame) -> 'ClipProcessor':
        if self.method == 'std':
            self.mean = df.mean()
            self.std = df.std()
        elif self.method == 'percentile':
            self.lower_p = df.quantile(0.01) if self.lower is None else None
            self.upper_p = df.quantile(0.99) if self.upper is None else None
        return self

    def transform(self, df: pd.DataFrame) -> pd.DataFrame:
        if self.method == 'std':
            lower = self.mean - self.n_std * self.std if self.lower is None else self.lower
            upper = self.mean + self.n_std * self.std if self.upper is None else self.upper
        elif self.method == 'percentile':
            lower = self.lower_p if self.lower is None else self.lower
            upper = self.upper_p if self.upper is None else self.upper
        else:
            lower, upper = self.lower, self.upper

        return df.clip(lower, upper)


# ============================================================
# 处理器组合
# ============================================================

class ProcessorPipeline:
    """处理器流水线"""

    def __init__(self, processors: Optional[List[BaseProcessor]] = None):
        self.processors = processors or []

    def add(self, processor: BaseProcessor) -> 'ProcessorPipeline':
        """添加处理器"""
        self.processors.append(processor)
        return self

    def fit(self, df: pd.DataFrame) -> 'ProcessorPipeline':
        """拟合并转换"""
        for p in self.processors:
            p.fit(df)
        return self

    def transform(self, df: pd.DataFrame) -> pd.DataFrame:
        """转换"""
        result = df.copy()
        for p in self.processors:
            result = p.transform(result)
        return result

    def fit_transform(self, df: pd.DataFrame) -> pd.DataFrame:
        """拟合并转换"""
        self.fit(df)
        return self.transform(df)


# ============================================================
# 便捷函数
# ============================================================

def create_standard_pipeline() -> ProcessorPipeline:
    """创建标准预处理流水线"""
    return ProcessorPipeline([
        DropnaProcessor(threshold=0.5),  # 去除 N/A 超过 50% 的列
        ProcessInf(method='replace_mean'),  # 处理无穷值
        ZscoreNorm(),  # Z-Score 标准化
    ])


def create_ranking_pipeline() -> ProcessorPipeline:
    """创建排名流水线（用于多标的选择）"""
    return ProcessorPipeline([
        DropnaProcessor(threshold=0.5),
        ProcessInf(method='replace_mean'),
        CSRankNorm(),  # 截面排名
    ])


def create_robust_pipeline() -> ProcessorPipeline:
    """创建鲁棒流水线（对异常值更鲁棒）"""
    return ProcessorPipeline([
        DropnaProcessor(threshold=0.5),
        ProcessInf(method='replace_median'),
        RobustZScoreNorm(limit=5.0),  # 鲁棒 Z-Score
    ])
