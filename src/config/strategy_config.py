"""
交易策略配置 (Trading Strategy Config)

集中管理交易策略参数
"""
from dataclasses import dataclass
from typing import Dict, List, Optional
from enum import Enum


class StrategyMode(Enum):
    """策略模式"""
    CONSERVATIVE = "conservative"  # 保守
    MODERATE = "moderate"         # 稳健
    AGGRESSIVE = "aggressive"        # 激进


@dataclass
class MTFConfig:
    """MTF 三重共振配置"""
    # 4H 趋势确认
    require_4h_trend: bool = True
    allow_sideways_4h: bool = False  # 是否允许横盘

    # 动量确认
    price_change_threshold: float = 0.005  # 0.5% 价格变化阈值
    max_momentum_deviation: float = 0.02   # 最大动量偏离 2%

    # 15m 放量确认
    base_volume_threshold: float = 2.0     # 基础成交量阈值 2x
    use_dynamic_threshold: bool = True      # 使用动态阈值
    min_volume_threshold: float = 1.8        # 最小成交量阈值

    # RSI 过滤
    rsi_oversold: float = 30.0            # RSI 超卖阈值
    rsi_overbought: float = 70.0            # RSI 超买阈值
    use_rsi_filter: bool = True             # 使用 RSI 过滤


@dataclass
class RiskConfig:
    """风险配置"""
    # 仓位管理
    max_position_pct: float = 0.40           # 最大单笔仓位 40%
    max_total_exposure_pct: float = 0.50     # 最大总敞口 50%
    min_position_value: float = 10.0          # 最小仓位价值 10U

    # 止损配置
    stop_loss_pct: float = 0.02              # 止损 2%
    time_stop_hours: float = 12.0            # 时间止损 12 小时

    # 止盈配置
    use_trailing_stop: bool = True
    trailing_start_pct: float = 0.02          # 2% 后开始追踪
    trailing_distance_pct: float = 0.015     # 追踪距离 1.5%
    min_rr_ratio: float = 2.0               # 最小盈亏比 1:2


@dataclass
class ExecutionConfig:
    """执行配置"""
    # 订单类型
    order_type: str = "limit"                # limit / market
    post_only: bool = True                   # 只做 Maker

    # 滑点保护
    max_slippage_pct: float = 0.005          # 最大滑点 0.5%
    slippage_check_timeout: float = 5.0      # 滑点检查超时 5 秒

    # 重试配置
    max_retries: int = 3                      # 最大重试次数
    retry_delay_seconds: float = 1.0        # 重试延迟


# 预设策略配置
PRESET_STRATEGIES: Dict[StrategyMode, Dict] = {
    StrategyMode.CONSERVATIVE: {
        "mtf": MTFConfig(
            require_4h_trend=True,
            allow_sideways_4h=False,
            base_volume_threshold=2.5,        # 更严格的放量要求
            min_volume_threshold=2.0,
            use_rsi_filter=True,
            rsi_oversold=25.0,                # 更严格的超卖
            rsi_overbought=75.0,
        ),
        "risk": RiskConfig(
            max_position_pct=0.30,
            max_total_exposure_pct=0.40,
            stop_loss_pct=0.015,              # 更紧的止损
            min_rr_ratio=2.5,                 # 更高的盈亏比要求
        ),
    },
    StrategyMode.MODERATE: {
        "mtf": MTFConfig(),
        "risk": RiskConfig(),
    },
    StrategyMode.AGGRESSIVE: {
        "mtf": MTFConfig(
            base_volume_threshold=1.8,         # 更低的放量要求
            min_volume_threshold=1.5,
            use_rsi_filter=False,
            allow_sideways_4h=True,           # 允许横盘
        ),
        "risk": RiskConfig(
            max_position_pct=0.50,
            max_total_exposure_pct=0.70,
            stop_loss_pct=0.025,              # 更宽的止损
            min_rr_ratio=1.5,                # 更低的盈亏比要求
        ),
    },
}


def get_strategy_config(mode: StrategyMode = StrategyMode.MODERATE) -> Dict:
    """
    获取策略配置

    Args:
        mode: 策略模式

    Returns:
        策略配置字典
    """
    return PRESET_STRATEGIES.get(mode, PRESET_STRATEGIES[StrategyMode.MODERATE])


def load_from_env() -> Dict:
    """
    从环境变量加载配置

    Returns:
        配置字典
    """
    import os

    config = {
        "mtf": MTFConfig(),
        "risk": RiskConfig(),
        "execution": ExecutionConfig(),
    }

    # MTF 配置
    if os.getenv("VOLUME_THRESHOLD"):
        config["mtf"].base_volume_threshold = float(os.getenv("VOLUME_THRESHOLD"))
    if os.getenv("USE_RSI_FILTER"):
        config["mtf"].use_rsi_filter = os.getenv("USE_RSI_FILTER").lower() == "true"

    # 风险配置
    if os.getenv("MAX_POSITION_PCT"):
        config["risk"].max_position_pct = float(os.getenv("MAX_POSITION_PCT"))
    if os.getenv("STOP_LOSS_PCT"):
        config["risk"].stop_loss_pct = float(os.getenv("STOP_LOSS_PCT"))

    # 执行配置
    if os.getenv("ORDER_TYPE"):
        config["execution"].order_type = os.getenv("ORDER_TYPE")
    if os.getenv("MAX_SLIPPAGE_PCT"):
        config["execution"].max_slippage_pct = float(os.getenv("MAX_SLIPPAGE_PCT"))

    return config
