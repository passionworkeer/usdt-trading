"""
交易对配置管理

定义不同风险等级的交易对池
"""
from typing import List, Dict
from dataclasses import dataclass
from enum import Enum


class RiskLevel(Enum):
    """风险等级"""
    LOW = "low"      # 低风险（主流币）
    MEDIUM = "medium"  # 中风险（主流+热门）
    HIGH = "high"    # 高风险（memecoin）


@dataclass
class TradingPairConfig:
    """交易对配置"""
    symbol: str
    risk_level: RiskLevel
    max_position_pct: float  # 最大仓位占比
    min_volume_24h: float  # 最小24小时成交量(USDT)
    enabled: bool = True


# 交易对池配置 - 放宽配置增加机会
TRADING_PAIRS_POOL: List[TradingPairConfig] = [
    # 低风险 - 主流币（默认全部启用）
    TradingPairConfig('BTC/USDT', RiskLevel.LOW, 0.40, 1_000_000_000),
    TradingPairConfig('ETH/USDT', RiskLevel.LOW, 0.30, 500_000_000),
    TradingPairConfig('SOL/USDT', RiskLevel.LOW, 0.15, 200_000_000),

    # 中风险 - 热门币（启用更多交易机会）
    TradingPairConfig('BNB/USDT', RiskLevel.MEDIUM, 0.10, 100_000_000),
    TradingPairConfig('XRP/USDT', RiskLevel.MEDIUM, 0.10, 200_000_000),
    TradingPairConfig('ADA/USDT', RiskLevel.MEDIUM, 0.08, 100_000_000),
    TradingPairConfig('DOGE/USDT', RiskLevel.MEDIUM, 0.08, 150_000_000),
    TradingPairConfig('AVAX/USDT', RiskLevel.MEDIUM, 0.08, 80_000_000),
    TradingPairConfig('DOT/USDT', RiskLevel.MEDIUM, 0.06, 50_000_000),
    TradingPairConfig('MATIC/USDT', RiskLevel.MEDIUM, 0.06, 50_000_000),

    # 高风险 - 潜力币（可选启用）
    TradingPairConfig('ARB/USDT', RiskLevel.HIGH, 0.05, 30_000_000),
    TradingPairConfig('OP/USDT', RiskLevel.HIGH, 0.05, 30_000_000),
    TradingPairConfig('PEPE/USDT', RiskLevel.HIGH, 0.03, 20_000_000),
    TradingPairConfig('WIF/USDT', RiskLevel.HIGH, 0.03, 15_000_000),
]


def get_active_symbols(
    include_medium: bool = False,
    include_high: bool = False
) -> List[str]:
    """
    获取活跃的交易对列表

    Args:
        include_medium: 是否包含中风险币
        include_high: 是否包含高风险币

    Returns:
        交易对符号列表
    """
    symbols = []
    for config in TRADING_PAIRS_POOL:
        if not config.enabled:
            continue
        if config.risk_level == RiskLevel.LOW:
            symbols.append(config.symbol)
        elif config.risk_level == RiskLevel.MEDIUM and include_medium:
            symbols.append(config.symbol)
        elif config.risk_level == RiskLevel.HIGH and include_high:
            symbols.append(config.symbol)
    return symbols


def get_symbol_config(symbol: str) -> TradingPairConfig:
    """获取交易对配置"""
    for config in TRADING_PAIRS_POOL:
        if config.symbol == symbol:
            return config
    # 默认配置
    return TradingPairConfig(symbol, RiskLevel.MEDIUM, 0.10, 10_000_000)


def get_total_max_position_pct(include_medium: bool = False) -> float:
    """获取总的最大仓位占比"""
    total = 0.0
    for config in TRADING_PAIRS_POOL:
        if not config.enabled:
            continue
        if config.risk_level == RiskLevel.LOW:
            total += config.max_position_pct
        elif config.risk_level == RiskLevel.MEDIUM and include_medium:
            total += config.max_position_pct
    return total


# 预设配置
DEFAULT_WATCH_SYMBOLS = get_active_symbols(include_medium=False)
MEDIUM_RISK_WATCH_SYMBOLS = get_active_symbols(include_medium=True)
ALL_WATCH_SYMBOLS = get_active_symbols(include_medium=True, include_high=True)
