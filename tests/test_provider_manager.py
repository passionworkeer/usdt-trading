"""
测试 AI Provider Manager

测试覆盖：
- Provider 注册/注销
- 活动 Provider 设置/切换
- 健康检查
- 故障转移
"""
import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
import asyncio

from src.ai.provider import (
    ActionType,
    RiskLevel,
    MarketContext,
    Evidence,
    EvidenceChain,
    EvidenceBasedDecision,
    TradeResult,
    ReviewFinding,
    ReviewReport,
    AIBaseProvider,
    AIProviderManager,
    ProviderStatus,
    ProviderNotFoundError,
    NoActiveProviderError,
)


class MockProvider(AIBaseProvider):
    """测试用 Mock Provider"""

    def __init__(
        self,
        name: str = "mock",
        version: str = "1.0.0",
        should_initialize: bool = True,
        should_health_check: bool = True,
    ):
        super().__init__()
        self._name = name
        self._version = version
        self._should_initialize = should_initialize
        self._should_health_check = should_health_check
        self._analyze_call_count = 0
        self._review_call_count = 0

    @property
    def name(self) -> str:
        return self._name

    @property
    def version(self) -> str:
        return self._version

    def _do_initialize(self) -> bool:
        return self._should_initialize

    async def analyze(self, context: MarketContext) -> EvidenceBasedDecision:
        self._analyze_call_count += 1

        if not self._should_health_check:
            raise Exception("Provider unhealthy")

        return EvidenceBasedDecision(
            action=ActionType.BUY,
            evidence_count=3,
            evidence_chain=[
                f"证据1: {context.symbol} 技术指标良好",
                f"证据2: RSI 低于30，超卖区域",
                f"证据3: 成交量放大确认趋势"
            ],
            veto_flag=False,
            entry_price=context.current_price,
            stop_loss=context.current_price * 0.98,
            take_profit=context.current_price * 1.04,
            position_size=100.0,
            reasoning=f"Mock analysis for {context.symbol}",
        )

    async def review(self, trade: TradeResult) -> ReviewReport:
        self._review_call_count += 1

        if not self._should_health_check:
            raise Exception("Provider unhealthy")

        return ReviewReport(
            trade_id=trade.symbol,
            overall_assessment="Mock review",
            score=80.0,
        )

    async def health_check(self) -> bool:
        return self._should_health_check


class TestMarketContext:
    """测试 MarketContext"""

    def test_create_market_context(self):
        """测试创建市场上下文"""
        context = MarketContext(
            symbol="BTCUSDT",
            current_price=50000.0,
            price_history=[49000, 49500, 50000],
        )

        assert context.symbol == "BTCUSDT"
        assert context.current_price == 50000.0
        assert len(context.price_history) == 3

    def test_market_context_to_dict(self):
        """测试转换为字典"""
        context = MarketContext(
            symbol="BTCUSDT",
            current_price=50000.0,
            volume_24h=1000000.0,
        )

        data = context.to_dict()

        assert data['symbol'] == "BTCUSDT"
        assert data['current_price'] == 50000.0
        assert data['volume_24h'] == 1000000.0


class TestEvidenceChain:
    """测试 EvidenceChain"""

    def test_create_evidence_chain(self):
        """测试创建证据链"""
        chain = EvidenceChain()

        assert len(chain.evidences) == 0

    def test_add_evidence(self):
        """测试添加证据"""
        chain = EvidenceChain()
        evidence = Evidence(
            source="technical",
            metric="rsi",
            value=70.0,
            description="RSI overbought",
        )

        chain.add_evidence(evidence)

        assert len(chain.evidences) == 1
        assert chain.evidences[0].source == "technical"

    def test_get_total_weight(self):
        """测试获取总权重"""
        chain = EvidenceChain()
        chain.add_evidence(Evidence(source="t1", metric="m1", value=1, weight=0.5, confidence=0.8))
        chain.add_evidence(Evidence(source="t2", metric="m2", value=2, weight=0.3, confidence=1.0))

        total = chain.get_total_weight()

        # 0.5 * 0.8 + 0.3 * 1.0 = 0.4 + 0.3 = 0.7
        assert abs(total - 0.7) < 0.001

    def test_get_by_source(self):
        """测试按来源获取证据"""
        chain = EvidenceChain()
        chain.add_evidence(Evidence(source="technical", metric="rsi", value=70))
        chain.add_evidence(Evidence(source="technical", metric="macd", value=1))
        chain.add_evidence(Evidence(source="fundamental", metric="news", value="positive"))

        technical = chain.get_by_source("technical")

        assert len(technical) == 2


class TestEvidenceBasedDecision:
    """测试 EvidenceBasedDecision"""

    def test_create_decision(self):
        """测试创建决策"""
        decision = EvidenceBasedDecision(
            action=ActionType.BUY,
            evidence_count=3,
            evidence_chain=["证据1", "证据2", "证据3"],
            veto_flag=False,
            entry_price=50000.0,
            stop_loss=49000.0,
            take_profit=52000.0,
            position_size=100.0,
            reasoning="Strong uptrend",
        )

        assert decision.action == ActionType.BUY
        assert decision.evidence_count == 3
        assert decision.veto_flag == False

    def test_confidence_validation(self):
        """测试证据数量验证（替代原来的置信度测试）"""
        # 有效范围
        decision = EvidenceBasedDecision(
            action=ActionType.HOLD,
            evidence_count=2,
            evidence_chain=["证据1", "证据2"],
            veto_flag=False,
            entry_price=50000.0,
            stop_loss=49000.0,
            take_profit=51000.0,
            position_size=0.0,
            reasoning="Test",
        )
        assert decision.evidence_count == 2

        # 证据数量不匹配
        with pytest.raises(ValueError):
            EvidenceBasedDecision(
                action=ActionType.HOLD,
                evidence_count=3,  # 错误：与列表长度不匹配
                evidence_chain=["证据1", "证据2"],
                veto_flag=False,
                entry_price=50000.0,
                stop_loss=49000.0,
                take_profit=51000.0,
                position_size=0.0,
                reasoning="Test",
            )

    def test_to_dict(self):
        """测试转换为字典"""
        decision = EvidenceBasedDecision(
            action=ActionType.SELL,
            evidence_count=2,
            evidence_chain=["证据1", "证据2"],
            veto_flag=False,
            entry_price=50000.0,
            stop_loss=51000.0,
            take_profit=48000.0,
            position_size=100.0,
            reasoning="Downtrend",
        )

        data = decision.to_dict()

        assert data['action'] == "sell"
        assert data['evidence_count'] == 2
        assert data['veto_flag'] == False


class TestTradeResult:
    """测试 TradeResult"""

    def test_create_trade_result(self):
        """测试创建交易结果"""
        trade = TradeResult(
            symbol="BTCUSDT",
            action=ActionType.BUY,
            entry_price=50000.0,
            quantity=0.1,
        )

        assert trade.symbol == "BTCUSDT"
        assert trade.status == "open"
        assert trade.pnl is None

    def test_close_trade_buy_profit(self):
        """测试关闭买入交易（盈利）"""
        trade = TradeResult(
            symbol="BTCUSDT",
            action=ActionType.BUY,
            entry_price=50000.0,
            quantity=0.1,
        )

        trade.close(exit_price=55000.0)

        assert trade.status == "closed"
        assert trade.exit_price == 55000.0
        # 盈利: (55000 - 50000) * 0.1 = 500
        assert trade.pnl == 500.0
        # 盈利百分比: (55000 - 50000) / 50000 * 100 = 10%
        assert abs(trade.pnl_pct - 10.0) < 0.001

    def test_close_trade_sell_profit(self):
        """测试关闭卖出交易（盈利）"""
        trade = TradeResult(
            symbol="BTCUSDT",
            action=ActionType.SELL,
            entry_price=50000.0,
            quantity=0.1,
        )

        trade.close(exit_price=45000.0)

        assert trade.status == "closed"
        # 卖出盈利: (50000 - 45000) * 0.1 = 500
        assert trade.pnl == 500.0


class TestAIProviderManager:
    """测试 AIProviderManager"""

    # ==================== 初始化测试 ====================

    def test_init(self):
        """测试初始化"""
        manager = AIProviderManager()

        assert manager.provider_count == 0
        assert manager.active_provider_name is None
        assert len(manager.provider_names) == 0

    # ==================== 注册测试 ====================

    def test_register_provider(self):
        """测试注册 Provider"""
        manager = AIProviderManager()
        provider = MockProvider(name="test_provider")

        result = manager.register(provider)

        assert result is True
        assert manager.provider_count == 1
        assert "test_provider" in manager.provider_names

    def test_register_and_set_active(self):
        """测试注册并设为活动"""
        manager = AIProviderManager()
        provider = MockProvider(name="test_provider")

        manager.register(provider, set_active=True)

        assert manager.active_provider_name == "test_provider"

    def test_register_auto_set_first_as_active(self):
        """测试第一个 Provider 自动设为活动"""
        manager = AIProviderManager()
        provider = MockProvider(name="first")

        manager.register(provider)

        assert manager.active_provider_name == "first"

    def test_register_initialize_failure(self):
        """测试注册时初始化失败"""
        manager = AIProviderManager()
        provider = MockProvider(name="fail", should_initialize=False)

        result = manager.register(provider)

        assert result is False
        assert manager.provider_count == 0

    def test_register_skip_initialize(self):
        """测试跳过初始化"""
        manager = AIProviderManager()
        provider = MockProvider(name="skip", should_initialize=False)

        result = manager.register(provider, initialize=False)

        assert result is True
        assert manager.provider_count == 1

    def test_register_override_existing(self):
        """测试覆盖已存在的 Provider"""
        manager = AIProviderManager()
        provider1 = MockProvider(name="test", version="1.0.0")
        provider2 = MockProvider(name="test", version="2.0.0")

        manager.register(provider1)
        manager.register(provider2)

        assert manager.provider_count == 1
        assert manager.get_provider("test").version == "2.0.0"

    # ==================== 注销测试 ====================

    def test_unregister_provider(self):
        """测试注销 Provider"""
        manager = AIProviderManager()
        provider = MockProvider(name="test")
        manager.register(provider)

        result = manager.unregister("test")

        assert result is True
        assert manager.provider_count == 0

    def test_unregister_nonexistent(self):
        """测试注销不存在的 Provider"""
        manager = AIProviderManager()

        result = manager.unregister("nonexistent")

        assert result is False

    def test_unregister_active_provider(self):
        """测试注销活动 Provider"""
        manager = AIProviderManager()
        provider1 = MockProvider(name="provider1")
        provider2 = MockProvider(name="provider2")
        manager.register(provider1)
        manager.register(provider2)

        manager.unregister("provider1")

        # 应该自动切换到其他 Provider
        assert manager.active_provider_name != "provider1"

    # ==================== 活动设置测试 ====================

    def test_set_active(self):
        """测试设置活动 Provider"""
        manager = AIProviderManager()
        provider1 = MockProvider(name="provider1")
        provider2 = MockProvider(name="provider2")
        manager.register(provider1)
        manager.register(provider2)

        manager.set_active("provider2")

        assert manager.active_provider_name == "provider2"

    def test_set_active_nonexistent(self):
        """测试设置不存在的 Provider 为活动"""
        manager = AIProviderManager()

        with pytest.raises(ProviderNotFoundError):
            manager.set_active("nonexistent")

    def test_get_active(self):
        """测试获取活动 Provider"""
        manager = AIProviderManager()
        provider = MockProvider(name="test")
        manager.register(provider)

        active = manager.get_active()

        assert active.name == "test"

    def test_get_active_no_provider(self):
        """测试没有活动 Provider 时获取"""
        manager = AIProviderManager()

        with pytest.raises(NoActiveProviderError):
            manager.get_active()

    # ==================== 健康检查测试 ====================

    @pytest.mark.asyncio
    async def test_health_check_healthy(self):
        """测试健康检查 - 健康"""
        manager = AIProviderManager()
        provider = MockProvider(name="test", should_health_check=True)
        manager.register(provider)

        status = await manager.health_check("test")

        assert status == ProviderStatus.HEALTHY

    @pytest.mark.asyncio
    async def test_health_check_unhealthy(self):
        """测试健康检查 - 不健康"""
        manager = AIProviderManager()
        provider = MockProvider(name="test", should_health_check=False)
        manager.register(provider, initialize=False)

        status = await manager.health_check("test")

        assert status == ProviderStatus.UNHEALTHY

    @pytest.mark.asyncio
    async def test_health_check_all(self):
        """测试检查所有 Provider"""
        manager = AIProviderManager()
        provider1 = MockProvider(name="healthy", should_health_check=True)
        provider2 = MockProvider(name="unhealthy", should_health_check=False)
        manager.register(provider1)
        manager.register(provider2, initialize=False)

        results = await manager.health_check_all()

        assert results["healthy"] == ProviderStatus.HEALTHY
        assert results["unhealthy"] == ProviderStatus.UNHEALTHY

    # ==================== 分析测试 ====================

    @pytest.mark.asyncio
    async def test_analyze(self):
        """测试分析"""
        manager = AIProviderManager()
        provider = MockProvider(name="test")
        manager.register(provider)

        context = MarketContext(
            symbol="BTCUSDT",
            current_price=50000.0,
        )

        decision = await manager.analyze(context)

        assert decision.action == ActionType.BUY
        assert decision.evidence_count == 3
        assert decision.veto_flag == False

    @pytest.mark.asyncio
    async def test_analyze_with_fallback(self):
        """测试带故障转移的分析"""
        manager = AIProviderManager()
        provider1 = MockProvider(name="fail", should_health_check=False)
        provider2 = MockProvider(name="success", should_health_check=True)
        manager.register(provider1, initialize=False)
        manager.register(provider2)

        context = MarketContext(
            symbol="BTCUSDT",
            current_price=50000.0,
        )

        # 设置故障转移顺序
        manager.set_fallback_order(["fail", "success"])

        decision = await manager.analyze_with_fallback(context)

        assert decision.action == ActionType.BUY

    # ==================== 复盘测试 ====================

    @pytest.mark.asyncio
    async def test_review(self):
        """测试复盘"""
        manager = AIProviderManager()
        provider = MockProvider(name="test")
        manager.register(provider)

        trade = TradeResult(
            symbol="BTCUSDT",
            action=ActionType.BUY,
            entry_price=50000.0,
        )

        report = await manager.review(trade)

        assert report.trade_id == "BTCUSDT"
        assert report.score == 80.0

    # ==================== 统计测试 ====================

    def test_get_statistics(self):
        """测试获取统计信息"""
        manager = AIProviderManager()
        provider = MockProvider(name="test", version="1.0.0")
        manager.register(provider)

        stats = manager.get_statistics()

        assert stats['total_providers'] == 1
        assert stats['active_provider'] == "test"
        assert "test" in stats['providers']
        assert stats['providers']['test']['version'] == "1.0.0"


class TestMockProvider:
    """测试 MockProvider"""

    def test_mock_provider_properties(self):
        """测试 Mock Provider 属性"""
        provider = MockProvider(name="custom", version="2.0.0")

        assert provider.name == "custom"
        assert provider.version == "2.0.0"

    @pytest.mark.asyncio
    async def test_mock_provider_analyze(self):
        """测试 Mock Provider 分析"""
        provider = MockProvider()
        provider.initialize()

        context = MarketContext(
            symbol="BTCUSDT",
            current_price=50000.0,
        )

        decision = await provider.analyze(context)

        assert decision.action == ActionType.BUY
        assert "BTCUSDT" in decision.reasoning

    @pytest.mark.asyncio
    async def test_mock_provider_health_check(self):
        """测试 Mock Provider 健康检查"""
        provider = MockProvider(should_health_check=True)

        result = await provider.health_check()

        assert result is True


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
