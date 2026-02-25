"""
集成测试 - 完整交易流程测试

测试覆盖：
1. 完整交易流程测试：策略池 → AI Provider → 证据链风控 → 执行交易 → SQLite → 复盘
2. 证据链风控测试：证据不足、veto_flag、价格异常
3. SQLite 存储测试
4. Provider 切换测试
"""
import asyncio
import pytest
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional
from unittest.mock import AsyncMock, MagicMock, patch
from dataclasses import dataclass, field

# 导入被测试模块
from src.ai.provider.base import (
    AIBaseProvider,
    AIProvider,
    ActionType,
    RiskLevel,
    MarketContext,
    Evidence,
    EvidenceChain,
    EvidenceBasedDecision,
    TradeResult,
    ReviewFinding,
    ReviewReport,
)
from src.ai.provider.manager import (
    AIProviderManager,
    ProviderStatus,
    ProviderNotFoundError,
)
from src.risk.evidence_controller import EvidenceBasedRiskController
from src.storage.database import TradingDatabase, Trade, Review
from src.ai.strategy.pool import SignalPool, BaseStrategy, MarketData, StrategyType
from src.ai.models import TradingSignal, SignalStrength, ActionType as ModelActionType


# ============================================================================
# Mock Provider 实现
# ============================================================================

class MockAIProvider(AIBaseProvider):
    """用于测试的 Mock AI Provider"""

    def __init__(
        self,
        name: str = "mock",
        version: str = "1.0.0",
        should_succeed: bool = True,
        response_delay: float = 0.0,
    ):
        super().__init__()
        self._name = name
        self._version = version
        self._should_succeed = should_succeed
        self._response_delay = response_delay
        self._analyze_count = 0
        self._review_count = 0

    @property
    def name(self) -> str:
        return self._name

    @property
    def version(self) -> str:
        return self._version

    def _do_initialize(self) -> bool:
        return True

    async def analyze(self, context: MarketContext) -> EvidenceBasedDecision:
        self._analyze_count += 1

        if self._response_delay > 0:
            await asyncio.sleep(self._response_delay)

        if not self._should_succeed:
            raise RuntimeError(f"Provider {self._name} failed")

        # 生成基于上下文的决策
        action = ActionType.BUY if context.current_price < 50000 else ActionType.SELL
        confidence = 0.75

        # 创建证据链
        evidence_chain = EvidenceChain()
        evidence_chain.add_evidence(Evidence(
            source="technical",
            metric="rsi",
            value=65.0,
            weight=0.3,
            confidence=0.8,
            description="RSI 显示超买"
        ))
        evidence_chain.add_evidence(Evidence(
            source="fundamental",
            metric="volume",
            value=context.volume_24h or 1000000,
            weight=0.2,
            confidence=0.9,
            description="成交量放大"
        ))
        evidence_chain.add_evidence(Evidence(
            source="sentiment",
            metric="news",
            value="positive",
            weight=0.1,
            confidence=0.7,
            description="新闻情绪偏多"
        ))

        return EvidenceBasedDecision(
            action=action,
            confidence=confidence,
            reasoning=f"基于 {context.symbol} 的技术分析和市场情绪",
            evidence_chain=evidence_chain,
            suggested_amount=1000.0,
            stop_loss_pct=2.0,
            take_profit_pct=5.0,
            risk_level=RiskLevel.MEDIUM,
            metadata={"provider": self._name, "symbol": context.symbol},
        )

    async def review(self, trade: TradeResult) -> ReviewReport:
        self._review_count += 1

        findings = [
            ReviewFinding(
                category="decision_quality",
                severity="info",
                description="入场时机选择合理",
                recommendation="保持当前策略",
                evidence={"entry_price": trade.entry_price}
            ),
            ReviewFinding(
                category="risk_management",
                severity="info",
                description="风险管理得当",
                recommendation="继续执行当前止损策略",
                evidence={}
            ),
        ]

        return ReviewReport(
            trade_id=f"{trade.symbol}_{trade.entry_time.isoformat()}",
            overall_assessment="交易执行良好，符合策略预期",
            findings=findings,
            lessons_learned=["保持纪律性", "及时止损"],
            improvements=["可以适当扩大仓位"],
            score=85.0,
            metadata={"provider": self._name},
        )

    async def health_check(self) -> bool:
        return self._should_succeed


class MockStrategy(BaseStrategy):
    """用于测试的 Mock 策略"""

    def __init__(
        self,
        name: str = "mock_strategy",
        should_generate_signal: bool = True,
        signal_action: ModelActionType = ModelActionType.BUY,
    ):
        super().__init__(
            name=name,
            strategy_type=StrategyType.TECHNICAL,
            priority=1,
        )
        self._should_generate_signal = should_generate_signal
        self._signal_action = signal_action
        self._generate_count = 0

    async def generate_signal(self, market_data: MarketData) -> Optional[TradingSignal]:
        self._generate_count += 1

        if not self._should_generate_signal:
            return None

        return self._create_signal(
            symbol=market_data.symbol,
            action=self._signal_action,
            strength=SignalStrength.STRONG,
            confidence=0.85,
            metadata={"strategy": self._name}
        )


class MockExecutor:
    """用于测试的执行器"""

    def __init__(self, should_succeed: bool = True):
        self._should_succeed = should_succeed
        self._execute_count = 0
        self._last_decision: Optional[EvidenceBasedDecision] = None

    async def execute(self, decision: EvidenceBasedDecision) -> TradeResult:
        self._execute_count += 1
        self._last_decision = decision

        if not self._should_succeed:
            raise RuntimeError("Execution failed")

        # 根据决策创建交易结果
        action_map = {
            "buy": ActionType.BUY,
            "sell": ActionType.SELL,
        }
        action = action_map.get(decision.action.value.lower(), ActionType.BUY)

        entry_price = 50000.0 if action == ActionType.BUY else 51000.0
        pnl = 100.0 if action == ActionType.BUY else -50.0

        return TradeResult(
            symbol=decision.metadata.get("symbol", "BTCUSDT"),
            action=action,
            entry_price=entry_price,
            quantity=0.1,
            pnl=pnl,
            pnl_pct=pnl / entry_price * 100,
            entry_time=datetime.now(),
            status="closed",
            metadata={
                "decision": decision.metadata,
                "executor": "mock"
            },
        )


class MockReviewSystem:
    """用于测试的复盘系统"""

    def __init__(self, database: Optional[TradingDatabase] = None):
        self._database = database
        self._recorded_trades: List[TradeResult] = []

    async def record_trade(self, trade: TradeResult) -> None:
        self._recorded_trades.append(trade)

        if self._database:
            # 转换为数据库 Trade 对象
            db_trade = Trade(
                symbol=trade.symbol,
                side="BUY" if trade.action == ActionType.BUY else "SELL",
                quantity=trade.quantity,
                price=trade.entry_price,
                pnl=trade.pnl or 0.0,
                fee=0.0,
                strategy="integration_test",
                signal_strength=0.85,
                execution_time_ms=100,
                metadata=trade.metadata,
            )
            await self._database.save_trade(db_trade)

    async def generate_review(self, trade: TradeResult) -> ReviewReport:
        # 生成简单的复盘报告
        return ReviewReport(
            trade_id=f"{trade.symbol}_{trade.entry_time.isoformat()}",
            overall_assessment="测试复盘报告",
            findings=[],
            lessons_learned=[],
            improvements=[],
            score=75.0,
        )


# ============================================================================
# 测试夹具
# ============================================================================

@pytest.fixture
async def temp_db():
    """创建临时数据库"""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_integration.db"
        db = TradingDatabase(db_path)
        await db.initialize()
        yield db
        await db.close()


@pytest.fixture
def signal_pool():
    """创建信号池"""
    pool = SignalPool()
    pool.register_strategy(MockStrategy(name="strategy_1"))
    pool.register_strategy(MockStrategy(name="strategy_2"))
    return signal_pool


@pytest.fixture
def risk_controller():
    """创建风控控制器"""
    return EvidenceBasedRiskController(
        min_evidence_count=2,
        max_evidence_count=10,
        allow_veto_override=False,
    )


@pytest.fixture
def provider_manager():
    """创建 Provider 管理器"""
    manager = AIProviderManager()
    manager.register(MockAIProvider(name="claude"), set_active=True)
    return manager


@pytest.fixture
def mock_executor():
    """创建模拟执行器"""
    return MockExecutor(should_succeed=True)


@pytest.fixture
def mock_review_system(temp_db):
    """创建模拟复盘系统"""
    return MockReviewSystem(database=temp_db)


# ============================================================================
# 1. 完整交易流程测试
# ============================================================================

class TestCompleteTradingFlow:
    """测试完整交易流程"""

    @pytest.mark.asyncio
    async def test_full_trading_flow_with_all_components(
        self,
        temp_db,
        signal_pool,
        risk_controller,
        provider_manager,
        mock_executor,
    ):
        """测试完整的交易流程：信号 → 决策 → 风控 → 执行 → 存储"""

        # 1. 准备市场数据
        market_data = MarketData(
            symbol="BTCUSDT",
            timestamp=datetime.now(),
            current_price=48000.0,
            volume_24h=1000000000.0,
            indicators={"rsi": 35, "macd": 150},
        )

        # 2. 策略池收集信号
        signals = await signal_pool.collect_signals(market_data)
        assert len(signals) > 0, "应该有信号产生"

        # 3. AI Provider 生成决策
        context = MarketContext(
            symbol=market_data.symbol,
            current_price=market_data.current_price,
            price_history=[47000, 47500, 48000],
            volume_24h=market_data.volume_24h,
            indicators=market_data.indicators,
        )

        decision = await provider_manager.analyze(context)
        assert decision is not None
        assert decision.confidence > 0

        # 4. 证据链风控验证
        # 转换 provider 决策格式到风控格式
        risk_decision = EvidenceBasedDecision(
            action=decision.action.value,
            evidence_count=len(decision.evidence_chain.evidences),
            evidence_chain=[e.description for e in decision.evidence_chain.evidences],
            veto_flag=False,  # 从 metadata 获取或默认 False
            entry_price=50000.0,
            stop_loss=50000.0 * (1 - (decision.stop_loss_pct or 2.0) / 100),
            take_profit=50000.0 * (1 + (decision.take_profit_pct or 5.0) / 100),
            position_size=decision.suggested_amount or 1000.0,
            symbol=context.symbol,
        )

        is_valid, reason = risk_controller.validate(risk_decision)
        assert is_valid, f"风控验证失败: {reason}"

        # 5. 执行交易
        trade_result = await mock_executor.execute(decision)
        assert trade_result is not None
        assert trade_result.status == "closed"

        # 6. 存储到数据库
        db_trade = Trade(
            symbol=trade_result.symbol,
            side=trade_result.action.value.upper(),
            quantity=trade_result.quantity,
            price=trade_result.entry_price,
            pnl=trade_result.pnl or 0.0,
            fee=0.0,
            strategy="integration_test",
            signal_strength=decision.confidence,
            execution_time_ms=100,
            metadata={"decision_metadata": decision.metadata},
        )
        trade_id = await temp_db.save_trade(db_trade)
        assert trade_id > 0

        # 7. 验证数据完整性
        retrieved_trade = await temp_db.get_trade(trade_id)
        assert retrieved_trade is not None
        assert retrieved_trade.symbol == "BTCUSDT"
        assert retrieved_trade.pnl == trade_result.pnl

    @pytest.mark.asyncio
    async def test_trading_flow_with_multiple_providers(
        self,
        temp_db,
        risk_controller,
    ):
        """测试多 Provider 的交易流程"""

        # 创建多个 Provider
        manager = AIProviderManager()
        provider1 = MockAIProvider(name="claude")
        provider2 = MockAIProvider(name="openclaw")
        manager.register(provider1, set_active=True)
        manager.register(provider2)

        # 切换到第二个 Provider
        manager.set_active("openclaw")
        assert manager.active_provider_name == "openclaw"

        # 使用活动 Provider 分析
        context = MarketContext(
            symbol="ETHUSDT",
            current_price=3000.0,
            price_history=[2900, 2950, 3000],
        )

        decision = await manager.analyze(context)
        assert decision is not None
        assert decision.metadata.get("provider") == "openclaw"

    @pytest.mark.asyncio
    async def test_trading_flow_with_review(
        self,
        temp_db,
        provider_manager,
    ):
        """测试包含复盘的完整流程"""

        # 1. 创建交易
        trade = TradeResult(
            symbol="BTCUSDT",
            action=ActionType.BUY,
            entry_price=50000.0,
            quantity=0.1,
            pnl=100.0,
            pnl_pct=0.2,
            entry_time=datetime.now(),
            status="closed",
        )

        # 2. 生成复盘报告
        review = await provider_manager.review(trade)

        assert review is not None
        assert review.score > 0
        assert len(review.findings) > 0

        # 3. 保存复盘到数据库
        db_review = Review(
            trade_id=1,
            review_type="trade",
            summary=review.overall_assessment,
            strengths=", ".join(review.lessons_learned) if review.lessons_learned else "",
            weaknesses="",
            improvements=", ".join(review.improvements) if review.improvements else "",
            market_conditions="",
            emotion_analysis="",
            metadata={"score": review.score},
        )
        review_id = await temp_db.save_review(db_review)
        assert review_id > 0


# ============================================================================
# 2. 证据链风控测试
# ============================================================================

class TestEvidenceChainRiskControl:
    """测试证据链风控验证"""

    def test_insufficient_evidence_blocked(self, risk_controller):
        """测试证据不足时被拦截"""
        decision = EvidenceBasedDecision(
            action="long",
            evidence_count=1,  # 少于最小要求（2）
            evidence_chain=["只有一条证据"],
            veto_flag=False,
            entry_price=50000.0,
            stop_loss=48000.0,
            take_profit=55000.0,
            position_size=1000.0,
        )

        is_valid, reason = risk_controller.validate(decision)

        assert is_valid is False
        assert "证据不足" in reason
        assert risk_controller.stats['rejected'] == 1

    def test_veto_flag_blocked(self, risk_controller):
        """测试 veto_flag=true 时被拦截"""
        decision = EvidenceBasedDecision(
            action="long",
            evidence_count=3,
            evidence_chain=["趋势向上", "成交量放大", "突破阻力位"],
            veto_flag=True,  # 被否决
            entry_price=50000.0,
            stop_loss=48000.0,
            take_profit=55000.0,
            position_size=1000.0,
        )

        is_valid, reason = risk_controller.validate(decision)

        assert is_valid is False
        assert "否决" in reason

    def test_abnormal_price_parameters_blocked(self, risk_controller):
        """测试价格参数异常时被拦截"""
        # 测试做多：止损 > 入场（错误）
        decision = EvidenceBasedDecision(
            action="long",
            evidence_count=3,
            evidence_chain=["趋势向上", "成交量放大", "突破阻力位"],
            veto_flag=False,
            entry_price=50000.0,
            stop_loss=52000.0,  # 错误：止损高于入场
            take_profit=55000.0,
            position_size=1000.0,
        )

        is_valid, reason = risk_controller.validate(decision)

        assert is_valid is False
        assert "价格" in reason or "止损" in reason

    def test_abnormal_price_parameters_short(self, risk_controller):
        """测试做空价格参数异常"""
        # 测试做空：止盈 > 入场（错误）
        decision = EvidenceBasedDecision(
            action="short",
            evidence_count=3,
            evidence_chain=["趋势向下", "成交量放大", "跌破支撑位"],
            veto_flag=False,
            entry_price=50000.0,
            stop_loss=48000.0,  # 错误方向
            take_profit=52000.0,  # 止盈高于入场
            position_size=1000.0,
        )

        is_valid, reason = risk_controller.validate(decision)

        assert is_valid is False

    def test_valid_long_decision_passed(self, risk_controller):
        """测试有效的做多决策通过"""
        decision = EvidenceBasedDecision(
            action="long",
            evidence_count=3,
            evidence_chain=["趋势向上", "成交量放大", "突破阻力位"],
            veto_flag=False,
            entry_price=50000.0,
            stop_loss=49000.0,  # 止损 < 入场
            take_profit=55000.0,  # 止盈 > 入场
            position_size=1000.0,
        )

        is_valid, reason = risk_controller.validate(decision)

        assert is_valid is True
        assert reason == "通过"
        assert risk_controller.stats['passed'] == 1

    def test_valid_short_decision_passed(self, risk_controller):
        """测试有效的做空决策通过"""
        decision = EvidenceBasedDecision(
            action="short",
            evidence_count=3,
            evidence_chain=["趋势向下", "成交量放大", "跌破支撑位"],
            veto_flag=False,
            entry_price=50000.0,
            stop_loss=52000.0,  # 止损 > 入场
            take_profit=47000.0,  # 止盈 < 入场
            position_size=1000.0,
        )

        is_valid, reason = risk_controller.validate(decision)

        assert is_valid is True
        assert reason == "通过"

    def test_close_action_passed(self, risk_controller):
        """测试平仓动作不需要价格验证"""
        decision = EvidenceBasedDecision(
            action="close",
            evidence_count=2,
            evidence_chain=["触及止损", "趋势反转"],
            veto_flag=False,
            entry_price=0.0,
            stop_loss=0.0,
            take_profit=0.0,
            position_size=0.0,
        )

        is_valid, reason = risk_controller.validate(decision)

        assert is_valid is True


# ============================================================================
# 3. SQLite 存储测试
# ============================================================================

class TestSQLiteStorage:
    """测试 SQLite 存储功能"""

    @pytest.mark.asyncio
    async def test_save_and_query_trade(self, temp_db):
        """测试保存和查询交易"""
        trade = Trade(
            symbol="BTCUSDT",
            side="BUY",
            quantity=0.5,
            price=50000.0,
            pnl=100.0,
            fee=0.5,
            strategy="sniper_v1",
            signal_strength=0.85,
            execution_time_ms=150,
            metadata={"test": "integration"}
        )

        trade_id = await temp_db.save_trade(trade)
        assert trade_id > 0

        retrieved = await temp_db.get_trade(trade_id)
        assert retrieved is not None
        assert retrieved.symbol == "BTCUSDT"
        assert retrieved.pnl == 100.0

    @pytest.mark.asyncio
    async def test_sql_aggregation_statistics(self, temp_db):
        """测试 SQL 聚合统计"""
        # 创建测试数据
        trades = [
            Trade(symbol="BTCUSDT", side="BUY", quantity=1.0, price=50000, pnl=100, strategy="sniper", execution_time_ms=100),
            Trade(symbol="BTCUSDT", side="BUY", quantity=1.0, price=50100, pnl=150, strategy="sniper", execution_time_ms=120),
            Trade(symbol="BTCUSDT", side="SELL", quantity=1.0, price=50200, pnl=200, strategy="trend", execution_time_ms=150),
            Trade(symbol="BTCUSDT", side="BUY", quantity=1.0, price=50300, pnl=-50, strategy="sniper", execution_time_ms=100),
            Trade(symbol="BTCUSDT", side="SELL", quantity=1.0, price=50400, pnl=-100, strategy="trend", execution_time_ms=140),
        ]

        for trade in trades:
            await temp_db.save_trade(trade)

        # SQL 聚合统计
        stats = await temp_db.get_statistics(days=30)

        assert stats.total_trades == 5
        assert stats.winning_trades == 3  # pnl > 0
        assert stats.losing_trades == 2   # pnl < 0
        assert stats.total_pnl == 300.0  # 100 + 150 + 200 - 50 - 100

    @pytest.mark.asyncio
    async def test_save_review_report(self, temp_db):
        """测试保存复盘报告"""
        # 先保存交易
        trade = Trade(
            symbol="ETHUSDT",
            side="BUY",
            quantity=10.0,
            price=3000.0,
            pnl=50.0,
            strategy="test",
        )
        trade_id = await temp_db.save_trade(trade)

        # 保存复盘
        review = Review(
            trade_id=trade_id,
            review_type="trade",
            summary="交易执行良好",
            strengths="入场时机精准",
            weaknesses="出场稍早",
            improvements="可以持有更久",
            market_conditions="牛市环境",
            emotion_analysis="保持冷静",
        )

        review_id = await temp_db.save_review(review)
        assert review_id > 0

        # 查询复盘
        reviews = await temp_db.get_reviews(trade_id=trade_id)
        assert len(reviews) == 1
        assert reviews[0].summary == "交易执行良好"

    @pytest.mark.asyncio
    async def test_trade_filtering(self, temp_db):
        """测试交易过滤"""
        # 创建不同策略的交易
        trades = [
            Trade(symbol="BTCUSDT", side="BUY", quantity=1.0, price=50000, pnl=100, strategy="sniper"),
            Trade(symbol="ETHUSDT", side="BUY", quantity=10.0, price=3000, pnl=50, strategy="sniper"),
            Trade(symbol="BTCUSDT", side="SELL", quantity=1.0, price=51000, pnl=-20, strategy="trend"),
        ]

        for trade in trades:
            await temp_db.save_trade(trade)

        # 按 symbol 过滤
        btc_trades = await temp_db.get_trades(symbol="BTCUSDT")
        assert len(btc_trades) == 2

        # 按策略过滤
        sniper_trades = await temp_db.get_trades(strategy="sniper")
        assert len(sniper_trades) == 2


# ============================================================================
# 4. Provider 切换测试
# ============================================================================

class TestProviderSwitching:
    """测试 Provider 切换功能"""

    @pytest.mark.asyncio
    async def test_switch_from_claude_to_openclaw(self):
        """测试 Claude → OpenClaw 切换"""
        manager = AIProviderManager()

        # 注册两个 Provider
        claude = MockAIProvider(name="claude")
        openclaw = MockAIProvider(name="openclaw")

        manager.register(claude, set_active=True)
        manager.register(openclaw)

        # 初始活动 Provider
        assert manager.active_provider_name == "claude"

        # 切换到 OpenClaw
        manager.set_active("openclaw")
        assert manager.active_provider_name == "openclaw"

        # 分析时使用新的活动 Provider
        context = MarketContext(symbol="BTCUSDT", current_price=50000.0)
        decision = await manager.analyze(context)

        assert decision.metadata.get("provider") == "openclaw"

    @pytest.mark.asyncio
    async def test_health_check_all_providers(self):
        """测试所有 Provider 的健康检查"""
        manager = AIProviderManager()

        provider1 = MockAIProvider(name="claude", should_succeed=True)
        provider2 = MockAIProvider(name="openclaw", should_succeed=False)

        manager.register(provider1)
        manager.register(provider2)

        # 健康检查
        results = await manager.health_check_all()

        assert results["claude"] == ProviderStatus.HEALTHY
        assert results["openclaw"] == ProviderStatus.UNHEALTHY

    @pytest.mark.asyncio
    async def test_fallback_on_provider_failure(self):
        """测试 Provider 失败时的故障转移"""
        manager = AIProviderManager()

        # 第一个失败，第二个成功
        provider1 = MockAIProvider(name="claude", should_succeed=False)
        provider2 = MockAIProvider(name="openclaw", should_succeed=True)

        manager.register(provider1, set_active=True)
        manager.register(provider2)

        # 设置故障转移顺序
        manager.set_fallback_order(["claude", "openclaw"])

        # 使用故障转移分析
        context = MarketContext(symbol="BTCUSDT", current_price=50000.0)
        decision = await manager.analyze_with_fallback(context)

        # 应该成功切换到第二个 Provider
        assert decision.metadata.get("provider") == "openclaw"

    @pytest.mark.asyncio
    async def test_unregister_active_provider_switches(self):
        """测试注销活动 Provider 后自动切换"""
        manager = AIProviderManager()

        provider1 = MockAIProvider(name="claude")
        provider2 = MockAIProvider(name="openclaw")

        manager.register(provider1, set_active=True)
        manager.register(provider2)

        # 注销活动的 Provider
        manager.unregister("claude")

        # 应该自动切换到另一个
        assert manager.active_provider_name == "openclaw"

    @pytest.mark.asyncio
    async def test_provider_statistics_tracking(self):
        """测试 Provider 统计追踪"""
        manager = AIProviderManager()

        provider = MockAIProvider(name="claude")
        manager.register(provider, set_active=True)

        context = MarketContext(symbol="BTCUSDT", current_price=50000.0)

        # 执行多次分析
        for _ in range(3):
            await manager.analyze(context)

        # 检查统计
        stats = manager.get_statistics()
        assert stats["providers"]["claude"]["success_count"] == 3


# ============================================================================
# 5. 边界情况测试
# ============================================================================

class TestEdgeCases:
    """测试边界情况"""

    @pytest.mark.asyncio
    async def test_no_signals_generated(self, signal_pool):
        """测试无信号产生的情况"""
        # 使用不生成信号的策略
        pool = SignalPool()
        pool.register_strategy(MockStrategy(name="silent", should_generate_signal=False))

        market_data = MarketData(
            symbol="BTCUSDT",
            timestamp=datetime.now(),
            current_price=50000.0,
        )

        signals = await pool.collect_signals(market_data)
        assert len(signals) == 0

    @pytest.mark.asyncio
    async def test_empty_database_statistics(self, temp_db):
        """测试空数据库统计"""
        stats = await temp_db.get_statistics(days=30)

        assert stats.total_trades == 0
        assert stats.winning_trades == 0
        assert stats.losing_trades == 0
        assert stats.total_pnl == 0.0

    def test_risk_controller_extreme_values(self):
        """测试风控极端值"""
        controller = EvidenceBasedRiskController(
            min_evidence_count=0,
            max_evidence_count=100,
        )

        # 零证据（允许）应该通过
        decision = EvidenceBasedDecision(
            action="close",
            evidence_count=0,
            evidence_chain=[],
            veto_flag=False,
            entry_price=0.0,
            stop_loss=0.0,
            take_profit=0.0,
            position_size=0.0,
        )

        is_valid, reason = controller.validate(decision)
        assert is_valid is True

    @pytest.mark.asyncio
    async def test_concurrent_database_writes(self, temp_db):
        """测试并发数据库写入"""

        async def write_trades(n: int):
            for i in range(n):
                trade = Trade(
                    symbol="BTCUSDT",
                    side="BUY",
                    quantity=1.0,
                    price=50000 + i,
                    pnl=10.0,
                    strategy="concurrent",
                )
                await temp_db.save_trade(trade)

        # 并发写入
        await asyncio.gather(
            write_trades(10),
            write_trades(10),
            write_trades(10),
        )

        # 验证总数
        stats = await temp_db.get_statistics(days=30)
        assert stats.total_trades == 30


# ============================================================================
# 运行入口
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
