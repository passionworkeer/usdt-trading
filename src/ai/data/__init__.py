"""
AI 数据收集模块

提供增强的市场数据给 AI 分析层，包括：
- 多时间框架 K 线数据
- 技术指标计算
- K 线形态识别
- 宏观市场数据
- 特征表达式引擎 (qlib 风格)
- 数据预处理
- Alpha 因子库
- 基于因子的交易策略
- Binance 数据获取
- 高级交易策略
- 回测引擎
- 策略优化器
"""
from .collector import MarketDataCollector
from .indicators import TechnicalIndicatorsCalculator, IndicatorSet
from .patterns import PatternRecognizer, CandlestickPattern
from .macro_data import MacroDataFetcher, MacroMarketData
from .mtf_klines import MTFKlinesCollector

# qlib 风格模块
from .expression_engine import ExpressionEngine, ExpressionTemplates, calculate_expression
from .processors import (
    BaseProcessor,
    ZscoreNorm,
    MinMaxNorm,
    RobustZScoreNorm,
    CSZScoreNorm,
    CSRankNorm,
    CSMedianNorm,
    CSFillna,
    DropnaProcessor,
    ProcessInf,
    TanhProcessor,
    FillnaProcessor,
    ClipProcessor,
    ProcessorPipeline,
    create_standard_pipeline,
    create_ranking_pipeline,
    create_robust_pipeline,
)
from .alpha_factors import (
    AlphaFactor,
    AlphaFactorLibrary,
    get_alpha_library,
    calculate_factors,
    get_factor_names,
    FactorWeights,
)

# 策略模块
from .factor_strategies import (
    SignalType,
    TradingSignal,
    FactorSignalGenerator,
    generate_signals,
)

# Binance 数据获取
from .binance_data import (
    BinanceDataFetcher,
    fetch_binance_data,
    fetch_multiple_symbols,
    fetch_top_coins,
)

# 高级策略
from .advanced_strategies import (
    SignalType as AdvancedSignalType,
    TradingSignal as AdvancedTradingSignal,
    AdvancedStrategyBase,
    TrendFollowingStrategy,
    MeanReversionStrategy,
    BreakoutStrategy,
    SupportResistanceStrategy,
    VolumeAnalysisStrategy,
    MultiTimeframeStrategy,
    CompositeStrategy,
    create_trend_strategy,
    create_reversal_strategy,
    create_aggressive_strategy,
    create_conservative_strategy,
)

# 回测引擎
from .backtest import (
    BacktestEngine,
    StrategyBacktester,
    BacktestResult,
    Trade,
    Position,
    PositionSide,
    create_engine,
    run_strategy_backtest,
    compare_strategies,
)

# 策略优化器
from .optimizer import (
    GridSearchOptimizer,
    RandomSearchOptimizer,
    GeneticOptimizer,
    WalkForwardAnalyzer,
    OptimizationResult,
    sensitivity_analysis,
    OPTIMIZATION_CONFIGS,
)

# 智能资金检测
from .smart_money import (
    SmartMoneyDetector,
    SmartMoneySignal,
    FlowDirection,
    OrderBookAnalyzer,
    ArbitrageDetector,
    InstitutionalActivityDetector,
    create_smart_money_detector,
    create_order_book_analyzer,
    create_arbitrage_detector,
    create_institutional_detector,
)

# 免费 K 线
from .free_klines import (
    FreeKlineFetcher,
    fetch_free_klines,
    fetch_klines_sync,
    get_free_kline_fetcher,
)

__all__ = [
    # 原有模块
    'MarketDataCollector',
    'TechnicalIndicatorsCalculator',
    'IndicatorSet',
    'PatternRecognizer',
    'CandlestickPattern',
    'MacroDataFetcher',
    'MacroMarketData',
    'MTFKlinesCollector',
    # 表达式引擎
    'ExpressionEngine',
    'ExpressionTemplates',
    'calculate_expression',
    # 处理器
    'BaseProcessor',
    'ZscoreNorm',
    'MinMaxNorm',
    'RobustZScoreNorm',
    'CSZScoreNorm',
    'CSRankNorm',
    'CSMedianNorm',
    'CSFillna',
    'DropnaProcessor',
    'ProcessInf',
    'TanhProcessor',
    'FillnaProcessor',
    'ClipProcessor',
    'ProcessorPipeline',
    'create_standard_pipeline',
    'create_ranking_pipeline',
    'create_robust_pipeline',
    # Alpha 因子
    'AlphaFactor',
    'AlphaFactorLibrary',
    'get_alpha_library',
    'calculate_factors',
    'get_factor_names',
    'FactorWeights',
    # 策略
    'SignalType',
    'TradingSignal',
    'FactorSignalGenerator',
    'generate_signals',
    # Binance 数据
    'BinanceDataFetcher',
    'fetch_binance_data',
    'fetch_multiple_symbols',
    'fetch_top_coins',
    # 高级策略
    'AdvancedSignalType',
    'AdvancedTradingSignal',
    'AdvancedStrategyBase',
    'TrendFollowingStrategy',
    'MeanReversionStrategy',
    'BreakoutStrategy',
    'SupportResistanceStrategy',
    'VolumeAnalysisStrategy',
    'MultiTimeframeStrategy',
    'CompositeStrategy',
    'create_trend_strategy',
    'create_reversal_strategy',
    'create_aggressive_strategy',
    'create_conservative_strategy',
    # 回测
    'BacktestEngine',
    'StrategyBacktester',
    'BacktestResult',
    'Trade',
    'Position',
    'PositionSide',
    'create_engine',
    'run_strategy_backtest',
    'compare_strategies',
    # 优化器
    'GridSearchOptimizer',
    'RandomSearchOptimizer',
    'GeneticOptimizer',
    'WalkForwardAnalyzer',
    'OptimizationResult',
    'sensitivity_analysis',
    'OPTIMIZATION_CONFIGS',
    # 智能资金检测
    'SmartMoneyDetector',
    'SmartMoneySignal',
    'FlowDirection',
    'OrderBookAnalyzer',
    'ArbitrageDetector',
    'InstitutionalActivityDetector',
    'create_smart_money_detector',
    'create_order_book_analyzer',
    'create_arbitrage_detector',
    'create_institutional_detector',
    # 免费 K 线
    'FreeKlineFetcher',
    'fetch_free_klines',
    'fetch_klines_sync',
    'get_free_kline_fetcher',
]
