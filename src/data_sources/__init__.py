"""
数据源模块初始化
"""
from .market_intelligence import (
    DataSourceBase, TwitterSentimentSource, CryptoNewsSource,
    WhaleAlertSource, DataAggregator, NewsItem, Tweet, WhaleAlert
)

# 免费数据源（无需 API Key）
from .free_data import (
    FreeDataSource, CoinData, ExchangePrice, OnChainFlow,
    get_free_data_source
)

# 资金费率数据源
from .funding_rate import (
    FundingRateSource, FundingInfo, get_funding_source
)

# 综合聚合器
from .aggregator import (
    MarketAggregator, TradingSignal, get_market_aggregator
)

# 信号增强器
from .signal_enhancer import (
    SignalEnhancer, get_signal_enhancer,
    quick_funding_check, check_price_anomaly
)

# 上下文增强器
from .context_enhancer import (
    enhance_market_context,
    get_funding_summary,
    should_follow_funding_signal
)

__all__ = [
    # 原有模块
    'DataSourceBase', 'TwitterSentimentSource', 'CryptoNewsSource',
    'WhaleAlertSource', 'DataAggregator', 'NewsItem', 'Tweet', 'WhaleAlert',
    # 免费数据源
    'FreeDataSource', 'CoinData', 'ExchangePrice', 'OnChainFlow',
    'get_free_data_source',
    # 资金费率
    'FundingRateSource', 'FundingInfo', 'get_funding_source',
    # 聚合器
    'MarketAggregator', 'TradingSignal', 'get_market_aggregator',
    # 信号增强器
    'SignalEnhancer', 'get_signal_enhancer',
    'quick_funding_check', 'check_price_anomaly',
    # 上下文增强器
    'enhance_market_context',
    'get_funding_summary',
    'should_follow_funding_signal',
]
