"""
统一的数据模型包

此包包含项目中所有核心数据模型的统一定义。
建议所有新代码从此处导入模型，而不是从其他子模块导入。

导入示例:
    from src.models import EvidenceBasedDecision, ActionType, MarketContext
    from src.models import TradeResult, ReviewReport

向后兼容性:
    为了保持向后兼容，以下导入路径仍然可用:
    - from src.ai.provider.base import EvidenceBasedDecision  # 不推荐
    - from src.ai.models import EvidenceBasedDecision  # 不推荐
"""
from src.models.decision import (
    # Enums
    ActionType,
    ConfidenceLevel,
    RiskLevel,
    SignalStrength,
    MarketRegime,
    TradeOutcome,
    # Data Classes
    MarketContext,
    Evidence,
    EvidenceChain,
    EvidenceBasedDecision,
    TradeResult,
    ReviewFinding,
    ReviewReport,
    TradingSignal,
    LearningReport,
)

__all__ = [
    # Enums
    "ActionType",
    "ConfidenceLevel",
    "RiskLevel",
    "SignalStrength",
    "MarketRegime",
    "TradeOutcome",
    # Data Classes
    "MarketContext",
    "Evidence",
    "EvidenceChain",
    "EvidenceBasedDecision",
    "TradeResult",
    "ReviewFinding",
    "ReviewReport",
    "TradingSignal",
    "LearningReport",
]
