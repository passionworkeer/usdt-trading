"""
AI Trading System - Core Data Models

This module defines the core data structures used throughout the AI trading system.
All classes are immutable dataclasses to ensure data consistency and thread safety.

Note: Core models have been moved to src.models package.
This module is kept for backward compatibility and re-exports.
"""

from src.models import (
    # Enums
    ActionType,
    SignalStrength,
    MarketRegime,
    TradeOutcome,
    # Data Classes
    EvidenceBasedDecision,
    MarketContext,
    ReviewReport,
    TradingSignal,
    TradeResult as BaseTradeResult,
    LearningReport,
)

# 为了向后兼容，也从 provider.base 导入 SimpleTradeResult
from src.ai.provider.base import TradeResult as SimpleTradeResult


# 为了向后兼容，保留旧的本地 TradeResult 定义
# 注意：新代码应使用 src.models 中的定义
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Optional


@dataclass
class TradeResult:
    """
    Result of a completed trade (扩展版本).

    This captures all relevant information about a trade's lifecycle,
    from entry to exit, for performance analysis and learning.

    Note: This is an extended version that adds fields like trade_id, direction, fees, etc.
    For new code, consider using src.models.TradeResult instead.
    """

    trade_id: str = ""
    symbol: str = ""
    entry_time: datetime = field(default_factory=datetime.now)
    entry_price: float = 0.0
    exit_time: Optional[datetime] = None
    exit_price: Optional[float] = None
    position_size: float = 0.0
    direction: str = "long"  # "long" or "short"
    action: ActionType = ActionType.HOLD
    outcome: TradeOutcome = TradeOutcome.OPEN
    pnl: Optional[float] = None
    pnl_percent: Optional[float] = None
    fees: float = 0.0
    slippage: float = 0.0
    max_drawdown: float = 0.0
    exit_reason: str = ""
    quantity: float = 0.0
    status: str = "open"
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        """Validate the trade result after initialization."""
        if self.position_size <= 0:
            raise ValueError("position_size must be positive")
        if self.direction not in ("long", "short"):
            raise ValueError("direction must be 'long' or 'short'")

    def close(self, exit_price: float, exit_time: Optional[datetime] = None) -> None:
        """Close the trade and calculate PnL"""
        self.exit_price = exit_price
        self.exit_time = exit_time or datetime.now()
        self.status = "closed"

        # Calculate PnL
        if self.action == ActionType.BUY:
            self.pnl = (exit_price - self.entry_price) * self.quantity
            self.pnl_percent = (exit_price - self.entry_price) / self.entry_price * 100 if self.entry_price > 0 else 0
        else:  # SELL
            self.pnl = (self.entry_price - exit_price) * self.quantity
            self.pnl_percent = (self.entry_price - exit_price) / self.entry_price * 100 if self.entry_price > 0 else 0

    def duration_seconds(self) -> float:
        """Calculate the duration of the trade in seconds."""
        if self.exit_time:
            return (self.exit_time - self.entry_time).total_seconds()
        return 0.0

    def is_profitable(self) -> bool:
        """Check if the trade was profitable."""
        return self.pnl is not None and self.pnl > 0

    def risk_adjusted_return(self) -> float:
        """Calculate risk-adjusted return (return per unit of risk)."""
        if self.max_drawdown == 0 or self.pnl_percent is None:
            return 0.0
        return self.pnl_percent / abs(self.max_drawdown)


# Export all classes and enums for convenient importing
__all__ = [
    # Enums
    "ActionType",
    "SignalStrength",
    "MarketRegime",
    "TradeOutcome",
    # Data Classes
    "TradingSignal",
    "MarketContext",
    "TradeResult",
    "ReviewReport",
    "LearningReport",
    # For backward compatibility
    "SimpleTradeResult",
    "EvidenceBasedDecision",
]
