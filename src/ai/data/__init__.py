"""
AI 数据收集模块

提供增强的市场数据给 AI 分析层，包括：
- 多时间框架 K 线数据
- 技术指标计算
- K 线形态识别
- 宏观市场数据
"""
from .collector import MarketDataCollector
from .indicators import TechnicalIndicatorsCalculator, IndicatorSet
from .patterns import PatternRecognizer, CandlestickPattern
from .macro_data import MacroDataFetcher, MacroMarketData
from .mtf_klines import MTFKlinesCollector

__all__ = [
    'MarketDataCollector',
    'TechnicalIndicatorsCalculator',
    'IndicatorSet',
    'PatternRecognizer',
    'CandlestickPattern',
    'MacroDataFetcher',
    'MacroMarketData',
    'MTFKlinesCollector',
]
