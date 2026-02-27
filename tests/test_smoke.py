"""
冒烟测试 - 验证核心模块可以正常导入和初始化
"""
import pytest


def test_import_models():
    """测试数据模型可以导入"""
    from src.ai.models import (
        EvidenceBasedDecision,
        TradingSignal,
        MarketContext,
        TradeResult,
        ReviewReport,
        LearningReport,
        ActionType,
        SignalStrength,
        MarketRegime,
        TradeOutcome,
    )
    assert EvidenceBasedDecision is not None


def test_import_database():
    """测试数据库模块可以导入"""
    from src.storage.database import TradingDatabase, Trade, Review, TradeStatistics
    assert TradingDatabase is not None


def test_import_risk_controller():
    """测试风控模块可以导入"""
    from src.risk.evidence_controller import (
        EvidenceBasedDecision,
        EvidenceBasedRiskController,
        ActionType,
    )
    assert EvidenceBasedRiskController is not None


def test_import_ai_provider():
    """测试 AI Provider 模块可以导入"""
    from src.ai.provider.base import AIProvider
    from src.ai.provider.manager import AIProviderManager
    assert AIProvider is not None
    assert AIProviderManager is not None


def test_import_claude_provider():
    """测试 Claude Provider 可以导入"""
    from src.ai.provider.claude import ClaudeProvider
    assert ClaudeProvider is not None


def test_import_openclaw_provider():
    """测试 OpenClaw Provider 可以导入"""
    from src.ai.provider.openclaw import OpenClawProvider
    assert OpenClawProvider is not None


def test_import_strategy_pool():
    """测试策略池模块可以导入"""
    from src.ai.strategy.pool import SignalPool
    from src.ai.strategy.selector import StrategySelector
    assert SignalPool is not None
    assert StrategySelector is not None


def test_import_review_system():
    """测试复盘系统可以导入"""
    from src.ai.review.system import ReviewSystem
    assert ReviewSystem is not None


def test_import_trading_engine():
    """测试交易引擎可以导入"""
    from src.orchestrator.trading_engine import TradingEngine, EngineStats
    assert TradingEngine is not None
    assert EngineStats is not None


def test_evidence_based_decision_creation():
    """测试证据链决策创建"""
    from src.risk.evidence_controller import EvidenceBasedDecision
    from src.ai.provider.base import ActionType

    decision = EvidenceBasedDecision(
        action=ActionType.BUY,  # Use ActionType enum instead of string
        evidence_count=2,
        evidence_chain=["证据1", "证据2"],
        veto_flag=False,
        entry_price=100.0,
        stop_loss=95.0,
        take_profit=110.0,
        position_size=10.0,
    )
    assert decision.action == ActionType.BUY
    assert decision.evidence_count == 2
    assert decision.veto_flag is False


def test_risk_controller_validate():
    """测试风控验证逻辑"""
    from src.risk.evidence_controller import EvidenceBasedRiskController, EvidenceBasedDecision
    from src.ai.provider.base import ActionType

    controller = EvidenceBasedRiskController(min_evidence_count=2)

    # 有效的决策
    valid_decision = EvidenceBasedDecision(
        action=ActionType.BUY,  # Use ActionType enum
        evidence_count=2,
        evidence_chain=["证据1", "证据2"],
        veto_flag=False,
        entry_price=100.0,
        stop_loss=95.0,
        take_profit=110.0,
        position_size=10.0,
    )
    is_valid, reason = controller.validate(valid_decision)
    assert is_valid is True

    # 证据不足
    invalid_decision = EvidenceBasedDecision(
        action="long",
        evidence_count=1,
        evidence_chain=["证据1"],
        veto_flag=False,
        entry_price=100.0,
        stop_loss=95.0,
        take_profit=110.0,
        position_size=10.0,
    )
    is_valid, reason = controller.validate(invalid_decision)
    assert is_valid is False

    # 有否决标记
    veto_decision = EvidenceBasedDecision(
        action="long",
        evidence_count=2,
        evidence_chain=["证据1", "证据2"],
        veto_flag=True,
        entry_price=100.0,
        stop_loss=95.0,
        take_profit=110.0,
        position_size=10.0,
    )
    is_valid, reason = controller.validate(veto_decision)
    assert is_valid is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
