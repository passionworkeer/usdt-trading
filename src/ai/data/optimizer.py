"""
策略优化器模块

提供策略参数优化功能：
- 网格搜索优化
- 随机搜索优化
- 遗传算法优化
- Walk-forward 分析
- 参数敏感性分析

参考: qlib data generator 优化模块
"""
import logging
from typing import Dict, List, Optional, Tuple, Any, Callable
from dataclasses import dataclass
from itertools import product
import pandas as pd
import numpy as np
from concurrent.futures import ProcessPoolExecutor, as_completed
import random

from .backtest import BacktestEngine, StrategyBacktester, BacktestResult

logger = logging.getLogger(__name__)


@dataclass
class OptimizationResult:
    """优化结果"""
    best_params: Dict[str, Any]
    best_score: float
    all_results: List[Dict[str, Any]]
    optimization_time: float


class GridSearchOptimizer:
    """
    网格搜索优化器

    在参数空间中穷举搜索最优参数组合
    """

    def __init__(self, param_grid: Dict[str, List[Any]],
                 metric: str = 'sharpe_ratio',
                 minimize: bool = False):
        """
        初始化优化器

        Args:
            param_grid: 参数网格 {param_name: [values]}
            metric: 优化指标 (sharpe_ratio, total_pnl_pct, win_rate, etc.)
            minimize: 是否最小化指标
        """
        self.param_grid = param_grid
        self.metric = metric
        self.minimize = minimize
        self.results: List[Dict[str, Any]] = []

    def _generate_combinations(self) -> List[Dict[str, Any]]:
        """生成参数组合"""
        keys = list(self.param_grid.keys())
        values = list(self.param_grid.values())

        combinations = []
        for combo in product(*values):
            params = dict(zip(keys, combo))
            combinations.append(params)

        return combinations

    def optimize(self, df: pd.DataFrame,
                strategy_class,
                **kwargs) -> OptimizationResult:
        """
        执行优化

        Args:
            df: OHLCV 数据
            strategy_class: 策略类
            **kwargs: 传递给回测引擎的参数

        Returns:
            优化结果
        """
        import time
        start_time = time.time()

        combinations = self._generate_combinations()
        logger.info(f"Testing {len(combinations)} parameter combinations...")

        best_score = float('-inf') if not self.minimize else float('inf')
        best_params = None

        for i, params in enumerate(combinations):
            try:
                # 创建策略实例
                strategy = strategy_class(**params)

                # 回测
                result = run_strategy_backtest(df, strategy, **kwargs)

                # 获取指标
                score = getattr(result, self.metric, 0)

                # 记录结果
                self.results.append({
                    'params': params,
                    'score': score,
                    'total_trades': result.total_trades,
                    'win_rate': result.win_rate,
                    'total_pnl_pct': result.total_pnl_pct,
                    'max_drawdown_pct': result.max_drawdown_pct,
                })

                # 更新最优
                is_better = (score > best_score) if not self.minimize else (score < best_score)
                if is_better:
                    best_score = score
                    best_params = params

                if (i + 1) % 10 == 0:
                    logger.info(f"Progress: {i+1}/{len(combinations)}, Best: {best_score:.4f}")

            except Exception as e:
                logger.warning(f"Error with params {params}: {e}")
                continue

        optimization_time = time.time() - start_time

        return OptimizationResult(
            best_params=best_params,
            best_score=best_score,
            all_results=self.results,
            optimization_time=optimization_time
        )


class RandomSearchOptimizer:
    """
    随机搜索优化器

    在参数空间中随机采样搜索
    适合大参数空间
    """

    def __init__(self, param_distributions: Dict[str, Tuple[Any, Any]],
                 n_iter: int = 50,
                 metric: str = 'sharpe_ratio',
                 minimize: bool = False):
        """
        初始化优化器

        Args:
            param_distributions: 参数分布 {param_name: (min, max)} 或 {param_name: [choices]}
            n_iter: 迭代次数
            metric: 优化指标
            minimize: 是否最小化指标
        """
        self.param_distributions = param_distributions
        self.n_iter = n_iter
        self.metric = metric
        self.minimize = minimize
        self.results: List[Dict[str, Any]] = []

    def _sample_params(self) -> Dict[str, Any]:
        """随机采样参数"""
        params = {}
        for name, dist in self.param_distributions.items():
            if isinstance(dist, (list, tuple)) and len(dist) == 2:
                # 连续分布
                if isinstance(dist[0], int) and isinstance(dist[1], int):
                    params[name] = random.randint(dist[0], dist[1])
                else:
                    params[name] = random.uniform(dist[0], dist[1])
            else:
                # 离散选择
                params[name] = random.choice(dist)
        return params

    def optimize(self, df: pd.DataFrame,
                strategy_class,
                **kwargs) -> OptimizationResult:
        """执行随机搜索优化"""
        import time
        start_time = time.time()

        logger.info(f"Random search with {self.n_iter} iterations...")

        best_score = float('-inf') if not self.minimize else float('inf')
        best_params = None

        for i in range(self.n_iter):
            params = self._sample_params()

            try:
                strategy = strategy_class(**params)
                result = run_strategy_backtest(df, strategy, **kwargs)

                score = getattr(result, self.metric, 0)

                self.results.append({
                    'params': params,
                    'score': score,
                    'total_trades': result.total_trades,
                    'win_rate': result.win_rate,
                    'total_pnl_pct': result.total_pnl_pct,
                })

                is_better = (score > best_score) if not self.minimize else (score < best_score)
                if is_better:
                    best_score = score
                    best_params = params

                if (i + 1) % 10 == 0:
                    logger.info(f"Progress: {i+1}/{self.n_iter}, Best: {best_score:.4f}")

            except Exception as e:
                logger.warning(f"Error with params {params}: {e}")
                continue

        optimization_time = time.time() - start_time

        return OptimizationResult(
            best_params=best_params,
            best_score=best_score,
            all_results=self.results,
            optimization_time=optimization_time
        )


class GeneticOptimizer:
    """
    遗传算法优化器

    使用进化算法搜索最优参数
    适合复杂参数空间
    """

    def __init__(self, param_ranges: Dict[str, Tuple[Any, Any]],
                 population_size: int = 20,
                 n_generations: int = 30,
                 mutation_rate: float = 0.1,
                 crossover_rate: float = 0.7,
                 metric: str = 'sharpe_ratio',
                 minimize: bool = False):
        """
        初始化遗传算法优化器

        Args:
            param_ranges: 参数范围 {param_name: (min, max)} 或 {param_name: [choices]}
            population_size: 种群大小
            n_generations: 迭代代数
            mutation_rate: 变异率
            crossover_rate: 交叉率
            metric: 优化指标
            minimize: 是否最小化指标
        """
        self.param_ranges = param_ranges
        self.population_size = population_size
        self.n_generations = n_generations
        self.mutation_rate = mutation_rate
        self.crossover_rate = crossover_rate
        self.metric = metric
        self.minimize = minimize
        self.param_names = list(param_ranges.keys())

    def _init_population(self) -> List[Dict[str, Any]]:
        """初始化种群"""
        population = []
        for _ in range(self.population_size):
            individual = {}
            for name, range_ in self.param_ranges.items():
                if isinstance(range_[0], int):
                    individual[name] = random.randint(range_[0], range_[1])
                else:
                    individual[name] = random.uniform(range_[0], range_[1])
            population.append(individual)
        return population

    def _evaluate(self, individual: Dict[str, Any],
                  df: pd.DataFrame, strategy_class, **kwargs) -> float:
        """评估个体"""
        try:
            strategy = strategy_class(**individual)
            result = run_strategy_backtest(df, strategy, **kwargs)
            return getattr(result, self.metric, 0)
        except Exception:
            return float('-inf') if not self.minimize else float('inf')

    def _selection(self, population: List[Dict[str, Any]],
                   scores: List[float]) -> List[Dict[str, Any]]:
        """选择"""
        # 锦标赛选择
        selected = []
        for _ in range(len(population)):
            tournament_size = 3
            indices = random.sample(range(len(population)), tournament_size)
            tournament_scores = [scores[i] for i in indices]

            if not self.minimize:
                winner_idx = indices[np.argmax(tournament_scores)]
            else:
                winner_idx = indices[np.argmin(tournament_scores)]

            selected.append(population[winner_idx].copy())
        return selected

    def _crossover(self, parent1: Dict[str, Any],
                   parent2: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """交叉"""
        if random.random() > self.crossover_rate:
            return parent1.copy(), parent2.copy()

        child1, child2 = {}, {}
        for name in self.param_names:
            if random.random() < 0.5:
                child1[name] = parent1[name]
                child2[name] = parent2[name]
            else:
                child2[name] = parent1[name]
                child1[name] = parent2[name]

        return child1, child2

    def _mutate(self, individual: Dict[str, Any]) -> Dict[str, Any]:
        """变异"""
        for name in self.param_names:
            if random.random() < self.mutation_rate:
                range_ = self.param_ranges[name]
                if isinstance(range_[0], int):
                    individual[name] = random.randint(range_[0], range_[1])
                else:
                    individual[name] = random.uniform(range_[0], range_[1])
        return individual

    def optimize(self, df: pd.DataFrame,
                strategy_class,
                **kwargs) -> OptimizationResult:
        """执行遗传算法优化"""
        import time
        start_time = time.time()

        # 初始化
        population = self._init_population()
        best_individual = None
        best_score = float('-inf') if not self.minimize else float('inf')
        all_results = []

        for gen in range(self.n_generations):
            # 评估
            scores = []
            for individual in population:
                score = self._evaluate(individual, df, strategy_class, **kwargs)
                scores.append(score)

                all_results.append({
                    'generation': gen,
                    'params': individual.copy(),
                    'score': score,
                })

            # 记录最优
            gen_best_idx = np.argmax(scores) if not self.minimize else np.argmin(scores)
            gen_best_score = scores[gen_best_idx]

            if (not self.minimize and gen_best_score > best_score) or \
               (self.minimize and gen_best_score < best_score):
                best_score = gen_best_score
                best_individual = population[gen_best_idx].copy()

            logger.info(f"Generation {gen+1}/{self.n_generations}, Best: {best_score:.4f}")

            # 选择
            selected = self._selection(population, scores)

            # 交叉和变异
            new_population = []
            for i in range(0, len(selected), 2):
                if i + 1 < len(selected):
                    child1, child2 = self._crossover(selected[i], selected[i+1])
                    new_population.append(self._mutate(child1))
                    new_population.append(self._mutate(child2))
                else:
                    new_population.append(selected[i])

            population = new_population[:self.population_size]

        optimization_time = time.time() - start_time

        return OptimizationResult(
            best_params=best_individual,
            best_score=best_score,
            all_results=all_results,
            optimization_time=optimization_time
        )


class WalkForwardAnalyzer:
    """
    Walk-forward 分析器

    用于验证策略在历史数据上的稳定性
    """

    def __init__(self, train_size: int = 500,
                 test_size: int = 100,
                 step_size: int = 50):
        """
        初始化分析器

        Args:
            train_size: 训练集大小
            test_size: 测试集大小
            step_size: 步长
        """
        self.train_size = train_size
        self.test_size = test_size
        self.step_size = step_size

    def analyze(self, df: pd.DataFrame,
               strategy_class,
               param_ranges: Dict[str, Tuple[Any, Any]],
               **kwargs) -> List[Dict[str, Any]]:
        """
        执行 Walk-forward 分析

        Args:
            df: OHLCV 数据
            strategy_class: 策略类
            param_ranges: 参数范围
            **kwargs: 传递给回测的参数

        Returns:
            分析结果列表
        """
        results = []
        n_samples = len(df)

        train_start = 0
        test_start = self.train_size

        iteration = 0

        while test_start + self.test_size <= n_samples:
            logger.info(f"Walk-forward iteration {iteration+1}: "
                       f"train={train_start}:{test_start}, "
                       f"test={test_start}:{test_start+self.test_size}")

            # 划分数据
            train_df = df.iloc[train_start:test_start]
            test_df = df.iloc[test_start:test_start + self.test_size]

            # 优化参数
            optimizer = RandomSearchOptimizer(
                param_ranges,
                n_iter=20,
                metric='sharpe_ratio'
            )

            best_result = optimizer.optimize(
                train_df,
                strategy_class,
                **kwargs
            )

            # 在测试集上验证
            best_params = best_result.best_params
            strategy = strategy_class(**best_params)
            test_result = run_strategy_backtest(test_df, strategy, **kwargs)

            results.append({
                'iteration': iteration,
                'train_start': train_start,
                'train_end': test_start,
                'test_start': test_start,
                'test_end': test_start + self.test_size,
                'best_params': best_params,
                'train_score': best_result.best_score,
                'test_score': test_result.sharpe_ratio,
                'test_pnl_pct': test_result.total_pnl_pct,
                'test_trades': test_result.total_trades,
                'test_win_rate': test_result.win_rate,
            })

            # 移动窗口
            train_start += self.step_size
            test_start += self.step_size
            iteration += 1

        return results


def sensitivity_analysis(df: pd.DataFrame,
                        strategy_class,
                        base_params: Dict[str, Any],
                        param_to_test: str,
                        values: List[Any],
                        **kwargs) -> pd.DataFrame:
    """
    参数敏感性分析

    Args:
        df: OHLCV 数据
        strategy_class: 策略类
        base_params: 基础参数
        param_to_test: 要测试的参数
        values: 要测试的值列表

    Returns:
        敏感性分析结果
    """
    results = []

    for value in values:
        params = base_params.copy()
        params[param_to_test] = value

        try:
            strategy = strategy_class(**params)
            result = run_strategy_backtest(df, strategy, **kwargs)

            results.append({
                'value': value,
                'sharpe_ratio': result.sharpe_ratio,
                'total_pnl_pct': result.total_pnl_pct,
                'win_rate': result.win_rate,
                'max_drawdown_pct': result.max_drawdown_pct,
                'total_trades': result.total_trades,
            })
        except Exception as e:
            logger.warning(f"Error testing {param_to_test}={value}: {e}")

    return pd.DataFrame(results)


# 预设优化配置
OPTIMIZATION_CONFIGS = {
    'trend_following': {
        'strategy_class': None,  # 需要导入后设置
        'param_ranges': {
            'fast_ema': (5, 20),
            'slow_ema': (20, 60),
            'adx_period': (10, 30),
            'adx_threshold': (15, 40),
        }
    },
    'mean_reversion': {
        'strategy_class': None,
        'param_ranges': {
            'bb_period': (10, 30),
            'bb_std': (1.5, 3.0),
            'rsi_period': (5, 20),
            'rsi_oversold': (20, 40),
            'rsi_overbought': (60, 80),
        }
    },
    'breakout': {
        'strategy_class': None,
        'param_ranges': {
            'lookback_period': (10, 40),
            'volume_ma_period': (10, 30),
            'volume_multiplier': (1.5, 3.0),
        }
    }
}
