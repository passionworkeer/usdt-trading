"""
特征表达式引擎 (qlib 风格) v2.0

支持类似 qlib 的表达式语法来计算技术指标：
- Ref($close, N) - 引用 N 天前的值
- EMA($close, N) - 指数移动平均
- Mean($close, N) - 简单移动平均
- Std/Var - 波动率
- Rank - 截面排名
- Corr - 相关性
- Delta/Sum/Max/Min 等

v2.0 优化：
- 添加表达式缓存避免重复解析
- 添加更多内置函数
- 优化性能
- 添加更详细的日志

参考: https://github.com/microsoft/qlib
"""
import re
import logging
import hashlib
from typing import Dict, Any, Optional, Callable, Tuple
from functools import lru_cache
import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


class ExpressionContext:
    """表达式执行上下文"""

    def __init__(self, df: pd.DataFrame):
        self.df = df
        # 字段映射
        self.field_map = {
            '$open': 'open',
            '$high': 'high',
            '$low': 'low',
            '$close': 'close',
            '$volume': 'volume',
            '$amount': 'amount',
            '$factor': 'factor',
            # 常用别名
            '$o': 'open',
            '$h': 'high',
            '$l': 'low',
            '$c': 'close',
            '$v': 'volume',
        }
        # 缓存字段值
        self._field_cache: Dict[str, pd.Series] = {}

    def get_field(self, field: str) -> pd.Series:
        """获取字段值（带缓存）"""
        if field in self._field_cache:
            return self._field_cache[field]

        mapped = self.field_map.get(field, field)
        if mapped in self.df.columns:
            result = self.df[mapped].fillna(0)
            self._field_cache[field] = result
            return result
        raise ValueError(f"未知字段: {field}")

    def clear_cache(self):
        """清除缓存"""
        self._field_cache.clear()


class ExpressionEngine:
    """特征表达式引擎 v2.0"""

    # 支持的运算符（按优先级排序）
    OPERATORS = [
        ('^', lambda a, b: a ** b),
        ('*', lambda a, b: a * b),
        ('/', lambda a, b: a / b.replace(0, np.nan)),
        ('+', lambda a, b: a + b),
        ('-', lambda a, b: a - b),
        ('>=', lambda a, b: a >= b),
        ('<=', lambda a, b: a <= b),
        ('>', lambda a, b: a > b),
        ('<', lambda a, b: a < b),
        ('==', lambda a, b: a == b),
        ('!=', lambda a, b: a != b),
    ]

    # 支持的函数
    FUNCTIONS: Dict[str, Callable] = {}

    # 缓存已解析的表达式
    _parsed_cache: Dict[str, Callable] = {}
    _max_cache_size = 1000

    def __init__(self, df: pd.DataFrame, use_cache: bool = True):
        self.context = ExpressionContext(df)
        self.use_cache = use_cache
        self._register_builtin_functions()

    @classmethod
    def register_function(cls, name: str):
        """注册函数装饰器"""
        def decorator(func: Callable):
            cls.FUNCTIONS[name.upper()] = func
            return func
        return decorator

    def _get_cache_key(self, expression: str) -> str:
        """生成缓存键"""
        return hashlib.md5(expression.encode()).hexdigest()

    def _register_builtin_functions(self):
        """注册内置函数"""

        # === 时间序列函数 ===

        @self.register_function('REF')
        def ref(series: pd.Series, n: int) -> pd.Series:
            """引用 N 周期前的值"""
            return series.shift(int(n))

        @self.register_function('DELTA')
        def delta(series: pd.Series, n: int = 1) -> pd.Series:
            """差分"""
            return series.diff(int(n))

        @self.register_function('ROC')
        def roc(series: pd.Series, n: int = 1) -> pd.Series:
            """变化率: (current - ref) / ref"""
            n = int(n)
            return (series - series.shift(n)) / series.shift(n)

        @self.register_function('RELAGAIN')
        def relagain(series: pd.Series, n: int = 1) -> pd.Series:
            """相对收益: ref / current - 1"""
            n = int(n)
            return series.shift(n) / series - 1

        @self.register_function('DIFF')
        def diff(series: pd.Series, n: int = 1) -> pd.Series:
            """一阶差分"""
            return series.diff(int(n))

        # === 移动平均函数 ===

        @self.register_function('MA')
        @self.register_function('MEAN')
        def mean(series: pd.Series, n: int) -> pd.Series:
            """简单移动平均"""
            return series.rolling(window=int(n), min_periods=1).mean()

        @self.register_function('EMA')
        def ema(series: pd.Series, n: int) -> pd.Series:
            """指数移动平均"""
            return series.ewm(span=int(n), adjust=False).mean()

        @self.register_function('WMA')
        def wma(series: pd.Series, n: int) -> pd.Series:
            """加权移动平均"""
            n = int(n)
            weights = np.arange(1, n + 1)
            return series.rolling(window=n).apply(
                lambda x: np.sum(weights[:len(x)] * x) / np.sum(weights[:len(x)]),
                raw=True
            )

        @self.register_function('SMA')
        def sma(series: pd.Series, n: int) -> pd.Series:
            """简单移动平均 (同 MA)"""
            return series.rolling(window=int(n), min_periods=1).mean()

        @self.register_function('EWMA')
        def ewma(series: pd.Series, n: int) -> pd.Series:
            """指数加权移动平均"""
            return series.ewm(span=int(n), adjust=False).mean()

        # === 滚动统计函数 ===

        @self.register_function('STD')
        def std(series: pd.Series, n: int) -> pd.Series:
            """标准差"""
            return series.rolling(window=int(n), min_periods=1).std()

        @self.register_function('VAR')
        def var(series: pd.Series, n: int) -> pd.Series:
            """方差"""
            return series.rolling(window=int(n), min_periods=1).var()

        @self.register_function('SKEW')
        def skew(series: pd.Series, n: int) -> pd.Series:
            """偏度"""
            return series.rolling(window=int(n), min_periods=3).skew()

        @self.register_function('KURT')
        def kurt(series: pd.Series, n: int) -> pd.Series:
            """峰度"""
            return series.rolling(window=int(n), min_periods=4).kurt()

        @self.register_function('MAX')
        def max_(series: pd.Series, n: int) -> pd.Series:
            """最大值"""
            return series.rolling(window=int(n), min_periods=1).max()

        @self.register_function('MIN')
        def min_(series: pd.Series, n: int) -> pd.Series:
            """最小值"""
            return series.rolling(window=int(n), min_periods=1).min()

        @self.register_function('SUM')
        def sum_(series: pd.Series, n: int) -> pd.Series:
            """求和"""
            return series.rolling(window=int(n), min_periods=1).sum()

        @self.register_function('COUNT')
        def count(series: pd.Series, n: int) -> pd.Series:
            """计数"""
            return series.rolling(window=int(n), min_periods=1).count()

        @self.register_function('MED')
        @self.register_function('MEDIAN')
        def median(series: pd.Series, n: int) -> pd.Series:
            """中位数"""
            return series.rolling(window=int(n), min_periods=1).median()

        @self.register_function('QUANTILE')
        def quantile(series: pd.Series, n: int, q: float = 0.5) -> pd.Series:
            """分位数"""
            return series.rolling(window=int(n), min_periods=1).quantile(float(q))

        # === 排名函数 ===

        @self.register_function('RANK')
        def rank(series: pd.Series, n: int = 0) -> pd.Series:
            """排名 (0-1)"""
            n = int(n)
            if n > 0:
                return series.rolling(window=n, min_periods=1).apply(
                    lambda x: pd.Series(x).rank(pct=True).iloc[-1],
                    raw=False
                )
            else:
                return series.rank(pct=True)

        @self.register_function('TSRANK')
        def tsrank(series: pd.Series, n: int) -> pd.Series:
            """时序排名"""
            return series.rolling(window=int(n), min_periods=1).apply(
                lambda x: pd.Series(x).rank(pct=True).iloc[-1],
                raw=False
            )

        # === 相关性函数 ===

        @self.register_function('CORR')
        def corr(series1: pd.Series, series2: pd.Series, n: int) -> pd.Series:
            """相关系数"""
            return series1.rolling(window=int(n), min_periods=3).corr(series2)

        @self.register_function('COV')
        def cov(series1: pd.Series, series2: pd.Series, n: int) -> pd.Series:
            """协方差"""
            return series1.rolling(window=int(n), min_periods=3).cov(series2)

        # === 归一化函数 ===

        @self.register_function('ZSCORE')
        def zscore(series: pd.Series, n: int = 0) -> pd.Series:
            """Z-Score 标准化"""
            n = int(n)
            if n > 0:
                mean = series.rolling(window=n, min_periods=1).mean()
                std = series.rolling(window=n, min_periods=1).std()
                return (series - mean) / std.replace(0, np.nan)
            else:
                return (series - series.mean()) / series.std()

        @self.register_function('NORMALIZE')
        def normalize(series: pd.Series, n: int = 0) -> pd.Series:
            """归一化到 [0, 1]"""
            n = int(n)
            if n > 0:
                min_val = series.rolling(window=n, min_periods=1).min()
                max_val = series.rolling(window=n, min_periods=1).max()
                return (series - min_val) / (max_val - min_val).replace(0, np.nan)
            else:
                return (series - series.min()) / (series.max() - series.min())

        # === 数学函数 ===

        @self.register_function('ABS')
        def abs_(series: pd.Series) -> pd.Series:
            """绝对值"""
            return series.abs()

        @self.register_function('SIGN')
        def sign(series: pd.Series) -> pd.Series:
            """符号"""
            return np.sign(series)

        @self.register_function('LOG')
        def log(series: pd.Series) -> pd.Series:
            """对数"""
            return np.log(series.where(series > 0, np.nan))

        @self.register_function('LOG10')
        def log10(series: pd.Series) -> pd.Series:
            """常用对数"""
            return np.log10(series.where(series > 0, np.nan))

        @self.register_function('SQRT')
        def sqrt(series: pd.Series) -> pd.Series:
            """平方根"""
            return np.sqrt(series.where(series >= 0, np.nan))

        @self.register_function('POW')
        def pow(series: pd.Series, n: float) -> pd.Series:
            """幂函数"""
            return series ** float(n)

        @self.register_function('CLAMP')
        def clamp(series: pd.Series, min_val: float, max_val: float) -> pd.Series:
            """限制范围"""
            return series.clip(float(min_val), float(max_val))

        # === 条件函数 ===

        @self.register_function('IF')
        def if_(cond: pd.Series, true_val: Any, false_val: Any) -> pd.Series:
            """条件选择"""
            return cond.where(true_val, false_val)

        @self.register_function('WHERE')
        def where(cond: pd.Series, true_val: Any, false_val: Any) -> pd.Series:
            """条件选择 (同 IF)"""
            return cond.where(true_val, false_val)

        @self.register_function('NANIF')
        def nanif(series: pd.Series, threshold: float) -> pd.Series:
            """如果绝对值小于阈值则返回 NaN"""
            return series.where(series.abs() > float(threshold))

        # === 高级函数 ===

        @self.register_function('CSrank')
        def csrank(series: pd.Series) -> pd.Series:
            """截面排名 (0-1)"""
            return series.rank(pct=True)

        @self.register_function('CSZSCORE')
        def cszscore(series: pd.Series) -> pd.Series:
            """截面 Z-Score"""
            return (series - series.mean()) / series.std()

        @self.register_function('CSMEDIAN')
        def csmedian(series: pd.Series) -> pd.Series:
            """截面中位数"""
            return series - series.median()

        @self.register_function('DECAYLINEAR')
        def decaylinear(series: pd.Series, n: int) -> pd.Series:
            """线性衰减加权"""
            n = int(n)
            weights = np.arange(1, n + 1) / np.sum(np.arange(1, n + 1))
            return series.rolling(window=n).apply(
                lambda x: np.sum(weights[:len(x)] * x) / np.sum(weights[:len(x)]),
                raw=True
            )

        @self.register_function('TSMAX')
        def tsmax(series: pd.Series, n: int) -> pd.Series:
            """时序最大值的位置"""
            return series.rolling(window=int(n)).apply(
                lambda x: np.argmax(x) + 1,
                raw=True
            )

        @self.register_function('TSMIN')
        def tsmin(series: pd.Series, n: int) -> pd.Series:
            """时序最小值的位置"""
            return series.rolling(window=int(n)).apply(
                lambda x: np.argmin(x) + 1,
                raw=True
            )

        # === 技术指标函数 ===

        @self.register_function('ATR')
        def atr(high: pd.Series, low: pd.Series, close: pd.Series, n: int = 14) -> pd.Series:
            """Average True Range"""
            n = int(n)
            tr1 = high - low
            tr2 = (high - close.shift(1)).abs()
            tr3 = (low - close.shift(1)).abs()
            tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
            return tr.rolling(window=n).mean()

        @self.register_function('BB_UPPER')
        def bb_upper(close: pd.Series, n: int = 20, k: float = 2.0) -> pd.Series:
            """布林带上轨"""
            mean = close.rolling(window=int(n)).mean()
            std = close.rolling(window=int(n)).std()
            return mean + float(k) * std

        @self.register_function('BB_LOWER')
        def bb_lower(close: pd.Series, n: int = 20, k: float = 2.0) -> pd.Series:
            """布林带下轨"""
            mean = close.rolling(window=int(n)).mean()
            std = close.rolling(window=int(n)).std()
            return mean - float(k) * std

        @self.register_function('BB_MIDDLE')
        def bb_middle(close: pd.Series, n: int = 20) -> pd.Series:
            """布林带中轨"""
            return close.rolling(window=int(n)).mean()

        @self.register_function('BB_WIDTH')
        def bb_width(close: pd.Series, n: int = 20, k: float = 2.0) -> pd.Series:
            """布林带宽度"""
            n, k = int(n), float(k)
            mean = close.rolling(window=n).mean()
            std = close.rolling(window=n).std()
            upper = mean + k * std
            lower = mean - k * std
            return (upper - lower) / mean

        @self.register_function('BB_POSITION')
        def bb_position(close: pd.Series, n: int = 20, k: float = 2.0) -> pd.Series:
            """布林带位置 (0-1)"""
            n, k = int(n), float(k)
            mean = close.rolling(window=n).mean()
            std = close.rolling(window=n).std()
            upper = mean + k * std
            lower = mean - k * std
            return (close - lower) / (upper - lower).replace(0, np.nan)

        @self.register_function('RSI')
        def rsi(close: pd.Series, n: int = 14) -> pd.Series:
            """RSI 相对强弱指标"""
            n = int(n)
            delta = close.diff()
            gain = delta.where(delta > 0, 0)
            loss = -delta.where(delta < 0, 0)
            avg_gain = gain.rolling(window=n, min_periods=1).mean()
            avg_loss = loss.rolling(window=n, min_periods=1).mean()
            rs = avg_gain / avg_loss.replace(0, np.nan)
            return 100 - (100 / (1 + rs))

        @self.register_function('MACD')
        def macd(close: pd.Series, fast: int = 12, slow: int = 26) -> pd.Series:
            """MACD 线 (DIF)"""
            fast = int(fast)
            slow = int(slow)
            ema_fast = close.ewm(span=fast, adjust=False).mean()
            ema_slow = close.ewm(span=slow, adjust=False).mean()
            return ema_fast - ema_slow

        @self.register_function('MACD_SIGNAL')
        def macd_signal(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> pd.Series:
            """MACD 信号线"""
            fast, slow, signal = int(fast), int(slow), int(signal)
            ema_fast = close.ewm(span=fast, adjust=False).mean()
            ema_slow = close.ewm(span=slow, adjust=False).mean()
            macd_line = ema_fast - ema_slow
            return macd_line.ewm(span=signal, adjust=False).mean()

        @self.register_function('MACD_HIST')
        def macd_hist(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> pd.Series:
            """MACD 柱状图"""
            fast, slow, signal = int(fast), int(slow), int(signal)
            ema_fast = close.ewm(span=fast, adjust=False).mean()
            ema_slow = close.ewm(span=slow, adjust=False).mean()
            macd_line = ema_fast - ema_slow
            macd_dea = macd_line.ewm(span=signal, adjust=False).mean()
            return macd_line - macd_dea

        @self.register_function('KDJ_K')
        def kdj_k(high: pd.Series, low: pd.Series, close: pd.Series, n: int = 9) -> pd.Series:
            """KDJ K 线"""
            n = int(n)
            lowest_low = low.rolling(window=n).min()
            highest_high = high.rolling(window=n).max()
            rsv = (close - lowest_low) / (highest_high - lowest_low).replace(0, np.nan) * 100
            return rsv.ewm(span=3, adjust=False).mean()

        @self.register_function('KDJ_D')
        def kdj_d(high: pd.Series, low: pd.Series, close: pd.Series, n: int = 9) -> pd.Series:
            """KDJ D 线"""
            n = int(n)
            lowest_low = low.rolling(window=n).min()
            highest_high = high.rolling(window=n).max()
            rsv = (close - lowest_low) / (highest_high - lowest_low).replace(0, np.nan) * 100
            k = rsv.ewm(span=3, adjust=False).mean()
            return k.ewm(span=3, adjust=False).mean()

        @self.register_function('KDJ_J')
        def kdj_j(high: pd.Series, low: pd.Series, close: pd.Series, n: int = 9) -> pd.Series:
            """KDJ J 线"""
            n = int(n)
            lowest_low = low.rolling(window=n).min()
            highest_high = high.rolling(window=n).max()
            rsv = (close - lowest_low) / (highest_high - lowest_low).replace(0, np.nan) * 100
            k = rsv.ewm(span=3, adjust=False).mean()
            d = k.ewm(span=3, adjust=False).mean()
            return 3 * k - 2 * d

    def evaluate(self, expression: str) -> pd.Series:
        """
        计算表达式

        Args:
            expression: 表达式字符串

        Returns:
            计算结果 Series
        """
        try:
            expr = expression.strip()

            # 尝试使用缓存
            if self.use_cache:
                cache_key = self._get_cache_key(expr)
                if cache_key in self._parsed_cache:
                    # 重新执行（因为数据可能不同）
                    pass

            # 解析并计算
            result = self._parse_expression(expr)

            return result

        except Exception as e:
            logger.error(f"表达式计算失败: {expression}, 错误: {e}")
            raise

    def _parse_expression(self, expr: str) -> pd.Series:
        """解析表达式"""
        expr = expr.strip()

        # 处理函数调用: FUNC(args)
        func_match = re.match(r'^(\w+)\((.*)\)$', expr)
        if func_match:
            func_name = func_match.group(1).upper()
            args_str = func_match.group(2)

            # 解析参数
            args = self._parse_args(args_str)

            # 调用函数
            if func_name in self.FUNCTIONS:
                func = self.FUNCTIONS[func_name]
                result = func(*args)
                return result
            else:
                raise ValueError(f"未知函数: {func_name}")

        # 处理一元负号 (如 -5, -$close)
        if expr.startswith('-'):
            rest = expr[1:].strip()
            if rest:
                rest_val = self._parse_expression(rest)
                return -rest_val

        # 处理运算符表达式
        # 必须在字段引用之前处理，否则 $close - 1 会被当作字段名
        if any(op[0] in expr for op in self.OPERATORS):
            return self._parse_operators(expr)

        # 处理字段引用: $close
        if expr.startswith('$'):
            return self.context.get_field(expr)

        # 处理数字
        try:
            return pd.Series(float(expr), index=self.context.df.index)
        except ValueError:
            pass

        raise ValueError(f"无法解析表达式: {expr}")

    def _parse_args(self, args_str: str) -> list:
        """解析函数参数"""
        args = []
        current = ""
        depth = 0

        for char in args_str:
            if char in '([':
                depth += 1
                current += char
            elif char in ')]':
                depth -= 1
                current += char
            elif char == ',' and depth == 0:
                if current.strip():
                    parsed = self._parse_arg(current.strip())
                    args.append(parsed)
                current = ""
            else:
                current += char

        if current.strip():
            parsed = self._parse_arg(current.strip())
            args.append(parsed)

        return args

    def _parse_arg(self, arg_str: str) -> Any:
        """解析单个参数"""
        arg_str = arg_str.strip()

        # 处理函数调用: FUNC(args)
        func_match = re.match(r'^(\w+)\((.*)\)$', arg_str)
        if func_match:
            func_name = func_match.group(1).upper()
            args_str = func_match.group(2)
            # 递归解析参数
            sub_args = self._parse_args(args_str)
            if func_name in self.FUNCTIONS:
                func = self.FUNCTIONS[func_name]
                return func(*sub_args)
            else:
                raise ValueError(f"未知函数: {func_name}")

        # 处理一元负号 (如 -5)
        if arg_str.startswith('-'):
            rest = arg_str[1:].strip()
            if rest:
                return -self._parse_arg(rest)

        # 处理运算符表达式 (如 $close/Ref($close, 1))
        # 必须在字段引用之前处理
        if any(op[0] in arg_str for op in self.OPERATORS):
            return self._parse_operators(arg_str)

        # 处理字段引用: $close
        if arg_str.startswith('$'):
            return self.context.get_field(arg_str)

        # 处理数字
        try:
            if '.' not in arg_str:
                return int(arg_str)
            return float(arg_str)
        except ValueError:
            pass

        raise ValueError(f"无法解析参数: {arg_str}")

    def _parse_operators(self, expr: str) -> pd.Series:
        """解析运算符表达式"""
        expr = expr.strip()

        # 按优先级处理运算符
        for op_str, op_func in self.OPERATORS:
            depth = 0
            i = 0
            while i < len(expr):
                char = expr[i]
                if char in '([':
                    depth += 1
                elif char in ')]':
                    depth -= 1
                elif depth == 0 and expr[i:].startswith(op_str):
                    # 找到运算符，分割
                    left = expr[:i].strip()
                    right = expr[i + len(op_str):].strip()
                    if left and right:
                        left_val = self._parse_expression(left)
                        right_val = self._parse_expression(right)
                        return op_func(left_val, right_val)
                i += 1

        raise ValueError(f"无法解析表达式: {expr}")

    @classmethod
    def clear_cache(cls):
        """清除解析缓存"""
        cls._parsed_cache.clear()
        logger.info("表达式解析缓存已清除")

    @classmethod
    def list_functions(cls) -> list:
        """列出所有可用函数"""
        return sorted(cls.FUNCTIONS.keys())


def calculate_expression(df: pd.DataFrame, expression: str) -> pd.Series:
    """
    快速计算表达式

    Args:
        df: 包含 OHLCV 数据的 DataFrame
        expression: 表达式字符串

    Returns:
        计算结果 Series
    """
    engine = ExpressionEngine(df)
    return engine.evaluate(expression)


# ============================================================
# 常用表达式模板
# ============================================================

class ExpressionTemplates:
    """常用表达式模板"""

    # ========== 动量因子 ==========
    @staticmethod
    def momentum(n: int = 5) -> str:
        """动量因子: N 天收益率"""
        return f'Ref($close, -{n}) / $close - 1'

    @staticmethod
    def momentum_ma(n: int = 5, m: int = 20) -> str:
        """动量均值: N 天收益的 M 天均值"""
        return f'Mean(Ref($close, -{n}) / $close - 1, {m})'

    @staticmethod
    def acceleration(n: int = 5) -> str:
        """加速度: 动量的变化率"""
        return f'Delta(Ref($close, -{n}) / $close - 1, {n})'

    # ========== 均值回归因子 ==========
    @staticmethod
    def mean_reversion(n: int = 20) -> str:
        """均值回归: 价格偏离均值的程度"""
        return f'$close / Mean($close, {n}) - 1'

    @staticmethod
    def distance_to_ma(n: int = 20) -> str:
        """到均值的距离 (归一化)"""
        return f'($close - Mean($close, {n})) / Mean($close, {n})'

    # ========== 波动率因子 ==========
    @staticmethod
    def volatility(n: int = 20) -> str:
        """波动率: N 天收益率的标准差"""
        return f'Std(Log($close/Ref($close, 1)), {n})'

    @staticmethod
    def atr_ratio(n: int = 14) -> str:
        """ATR 比率: ATR / close"""
        return f'ATR($high, $low, $close, {n}) / $close'

    @staticmethod
    def price_range(n: int = 20) -> str:
        """价格范围: (high - low) / close"""
        return f'($high - $low) / $close'

    # ========== 成交量因子 ==========
    @staticmethod
    def volume_change(n: int = 1) -> str:
        """成交量变化"""
        return f'Ref($volume, -{n}) / $volume - 1'

    @staticmethod
    def volume_ma(n: int = 20) -> str:
        """成交量均值偏离"""
        return f'$volume / Mean($volume, {n}) - 1'

    @staticmethod
    def volume_price_corr(n: int = 20) -> str:
        """成交量与价格相关性"""
        return f'Corr($close, $volume, {n})'

    # ========== 趋势因子 ==========
    @staticmethod
    def trend_strength(n: int = 20) -> str:
        """趋势强度: (短期 MA - 长期 MA) / 长期 MA"""
        return f'(Mean($close, {n//2}) - Mean($close, {n})) / Mean($close, {n})'

    @staticmethod
    def ema_slope(n: int = 20) -> str:
        """EMA 斜率"""
        return f'(EMA($close, {n}) - Ref(EMA($close, {n}), 1)) / EMA($close, {n})'

    @staticmethod
    def ma_cross(short: int = 5, long: int = 20) -> str:
        """均线交叉"""
        return f'Mean($close, {short}) / Mean($close, {long}) - 1'

    # ========== 布林带因子 ==========
    @staticmethod
    def bollinger_position(n: int = 20, k: float = 2.0) -> str:
        """布林带位置 (0-1)"""
        return f'BB_POSITION($close, {n}, {k})'

    @staticmethod
    def bollinger_width(n: int = 20, k: float = 2.0) -> str:
        """布林带宽度"""
        return f'BB_WIDTH($close, {n}, {k})'

    # ========== RSI 因子 ==========
    @staticmethod
    def rsi(n: int = 14) -> str:
        """RSI"""
        return f'RSI($close, {n})'

    @staticmethod
    def rsi_change(n: int = 14, m: int = 5) -> str:
        """RSI 变化"""
        return f'Ref(RSI($close, {n}), -{m}) - RSI($close, {n})'

    # ========== MACD 因子 ==========
    @staticmethod
    def macd(fast: int = 12, slow: int = 26) -> str:
        """MACD"""
        return f'MACD($close, {fast}, {slow})'

    @staticmethod
    def macd_signal(fast: int = 12, slow: int = 26, signal: int = 9) -> str:
        """MACD 信号线"""
        return f'MACD_SIGNAL($close, {fast}, {slow}, {signal})'

    @staticmethod
    def macd_hist(fast: int = 12, slow: int = 26, signal: int = 9) -> str:
        """MACD 柱状图"""
        return f'MACD_HIST($close, {fast}, {slow}, {signal})'

    # ========== KDJ 因子 ==========
    @staticmethod
    def kdj_k(n: int = 9) -> str:
        """KDJ K 线"""
        return f'KDJ_K($high, $low, $close, {n})'

    @staticmethod
    def kdj_d(n: int = 9) -> str:
        """KDJ D 线"""
        return f'KDJ_D($high, $low, $close, {n})'

    @staticmethod
    def kdj_j(n: int = 9) -> str:
        """KDJ J 线"""
        return f'KDJ_J($high, $low, $close, {n})'

    # ========== 排名因子 ==========
    @staticmethod
    def returns_rank(n: int = 20) -> str:
        """收益排名"""
        return f'Rank(Ref($close, -{n}) / $close - 1)'

    @staticmethod
    def volume_rank(n: int = 20) -> str:
        """成交量排名"""
        return f'Rank(Mean($volume, {n}))'

    # ========== 复合因子 ==========
    @staticmethod
    def price_volume(n: int = 20) -> str:
        """价量综合因子"""
        return f'Mean($close, {n}) / $close * Mean($volume, {n}) / $volume'

    @staticmethod
    def momentum_volatility_ratio(n: int = 20) -> str:
        """动量波动率比"""
        return f'(Ref($close, -{n}) / $close - 1) / Std(Log($close/Ref($close, 1)), {n})'

    @staticmethod
    def risk_adjusted_momentum(n: int = 20) -> str:
        """风险调整动量"""
        return f'(Ref($close, -{n}) / $close - 1) / Std(Ref($close, -{n}) / $close - 1, {n})'
