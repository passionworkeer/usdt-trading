"""
策略池模块单元测试
"""
import asyncio
import pytest
from datetime import datetime
from typing import Optional, List, Dict, Any

from src.ai.models import TradingSignal, ActionType, SignalStrength
from src.ai.provider.base import MarketContext, EvidenceBasedDecision
from src.ai.strategy.pool import (
    SignalPool,
    BaseStrategy,
    StrategyType,
    MarketData,
)
from src.ai.strategy.selector import StrategySelector
from src.ai.strategy.mtf_adapter import MTFStrategyAdapter


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def sample_market_data():
    """样本市场数据"""
    return MarketData(
        symbol="BTC/USDT",
        timestamp=datetime.now(),
        current_price=50000.0,
        volume_24h=1000000000.0,
        price_history=[48000.0, 49000.0, 50000.0],
        indicators={"rsi": 65, "macd": 0.5},
    )


@pytest.fixture
def sample_market_context():
    """样本市场上下文"""
    return MarketContext(
        symbol="BTC/USDT",
        current_price=50000.0,
        price_history=[48000.0, 49000.0, 50000.0],
        volume_24h=1000000000.0,
        indicators={"rsi": 65, "macd": 0.5},
    )


@pytest.fixture
def sample_signal():
    """样本交易信号"""
    return TradingSignal(
        symbol="BTC/USDT",
        timestamp=datetime.now(),
        signal_type=ActionType.BUY,
        strength=SignalStrength.STRONG,
        confidence=0.85,
        source="TestStrategy",
        metadata={"reason": "test"},
    )


@pytest.fixture
def signal_pool():
    """信号池实例"""
    return SignalPool()


# ============================================================================
# Test Strategy Classes
# ============================================================================

class MockStrategy(BaseStrategy):
    """用于测试的模拟策略"""

    def __init__(
        self,
        name: str,
        priority: int = 100,
        signal_to_return: Optional[TradingSignal] = None,
        should_fail: bool = False,
    ):
        super().__init__(
            name=name,
            strategy_type=StrategyType.TECHNICAL,
            priority=priority,
        )
        self.signal_to_return = signal_to_return
        self.should_fail = should_fail
        self.call_count = 0

    async def generate_signal(self, market_data: MarketData) -> Optional[TradingSignal]:
        self.call_count += 1

        if self.should_fail:
            raise Exception("模拟信号生成失败")

        if self.signal_to_return:
            # 更新信号中的 symbol 和 timestamp
            return TradingSignal(
                symbol=market_data.symbol,
                timestamp=datetime.now(),
                signal_type=self.signal_to_return.signal_type,
                strength=self.signal_to_return.strength,
                confidence=self.signal_to_return.confidence,
                source=self.name,
                metadata={
                    **self.signal_to_return.metadata,
                    "strategy": self.name,
                },
            )
        return None


# ============================================================================
# SignalPool Tests
# ============================================================================

class TestSignalPool:
    """SignalPool 测试类"""

    def test_init(self):
        """测试初始化"""
        pool = SignalPool()
        assert pool.strategy_count == 0
        assert pool.strategy_names == []

    def test_register_strategy(self, signal_pool):
        """测试注册策略"""
        strategy = MockStrategy(name="TestStrategy")

        result = signal_pool.register_strategy(strategy)

        assert result is True
        assert signal_pool.strategy_count == 1
        assert "TestStrategy" in signal_pool.strategy_names

    def test_register_duplicate_strategy(self, signal_pool):
        """测试注册重复策略"""
        strategy1 = MockStrategy(name="TestStrategy")
        strategy2 = MockStrategy(name="TestStrategy")

        signal_pool.register_strategy(strategy1)
        signal_pool.register_strategy(strategy2)  # 应该覆盖

        assert signal_pool.strategy_count == 1

    def test_unregister_strategy(self, signal_pool):
        """测试注销策略"""
        strategy = MockStrategy(name="TestStrategy")
        signal_pool.register_strategy(strategy)

        result = signal_pool.unregister_strategy("TestStrategy")

        assert result is True
        assert signal_pool.strategy_count == 0

    def test_unregister_nonexistent_strategy(self, signal_pool):
        """测试注销不存在的策略"""
        result = signal_pool.unregister_strategy("Nonexistent")

        assert result is False

    def test_get_strategy(self, signal_pool):
        """测试获取策略"""
        strategy = MockStrategy(name="TestStrategy")
        signal_pool.register_strategy(strategy)

        retrieved = signal_pool.get_strategy("TestStrategy")

        assert retrieved is not None
        assert retrieved.name == "TestStrategy"

    def test_get_enabled_strategies(self, signal_pool):
        """测试获取启用的策略"""
        strategy1 = MockStrategy(name="Strategy1")
        strategy2 = MockStrategy(name="Strategy2")
        strategy2.enabled = False

        signal_pool.register_strategy(strategy1)
        signal_pool.register_strategy(strategy2)

        enabled = signal_pool.get_enabled_strategies()

        assert len(enabled) == 1
        assert enabled[0].name == "Strategy1"

    @pytest.mark.asyncio
    async def test_collect_signals(self, signal_pool, sample_market_data):
        """测试收集信号"""
        # 创建带返回信号的策略
        signal1 = TradingSignal(
            symbol="BTC/USDT",
            timestamp=datetime.now(),
            signal_type=ActionType.BUY,
            strength=SignalStrength.STRONG,
            confidence=0.9,
            source="Test",
        )

        strategy = MockStrategy(
            name="TestStrategy",
            priority=10,
            signal_to_return=signal1
        )

        signal_pool.register_strategy(strategy)

        # 收集信号
        signals = await signal_pool.collect_signals(sample_market_data)

        assert len(signals) == 1
        assert signals[0].source == "TestStrategy"
        assert signals[0].confidence == 0.9

    @pytest.mark.asyncio
    async def test_collect_signals_with_failure(self, signal_pool, sample_market_data):
        """测试收集信号时处理失败"""
        # 一个失败的策略
        fail_strategy = MockStrategy(
            name="FailStrategy",
            should_fail=True
        )

        # 一个成功的策略
        signal = TradingSignal(
            symbol="BTC/USDT",
            timestamp=datetime.now(),
            signal_type=ActionType.BUY,
            strength=SignalStrength.MODERATE,
            confidence=0.75,
            source="Test",
        )
        success_strategy = MockStrategy(
            name="SuccessStrategy",
            signal_to_return=signal
        )

        signal_pool.register_strategy(fail_strategy)
        signal_pool.register_strategy(success_strategy)

        signals = await signal_pool.collect_signals(sample_market_data)

        assert len(signals) == 1
        assert signals[0].source == "SuccessStrategy"

    @pytest.mark.asyncio
    async def test_collect_signals_sorting(self, signal_pool, sample_market_data):
        """测试信号排序"""
        # 创建不同强度的信号
        signal_weak = TradingSignal(
            symbol="BTC/USDT",
            timestamp=datetime.now(),
            signal_type=ActionType.BUY,
            strength=SignalStrength.WEAK,
            confidence=0.5,
            source="Test",
        )

        signal_strong = TradingSignal(
            symbol="BTC/USDT",
            timestamp=datetime.now(),
            signal_type=ActionType.BUY,
            strength=SignalStrength.STRONG,
            confidence=0.95,
            source="Test",
        )

        signal_moderate = TradingSignal(
            symbol="BTC/USDT",
            timestamp=datetime.now(),
            signal_type=ActionType.BUY,
            strength=SignalStrength.MODERATE,
            confidence=0.75,
            source="Test",
        )

        strategy1 = MockStrategy(name="Strategy1", priority=1, signal_to_return=signal_weak)
        strategy2 = MockStrategy(name="Strategy2", priority=2, signal_to_return=signal_strong)
        strategy3 = MockStrategy(name="Strategy3", priority=3, signal_to_return=signal_moderate)

        signal_pool.register_strategy(strategy1)
        signal_pool.register_strategy(strategy2)
        signal_pool.register_strategy(strategy3)

        signals = await signal_pool.collect_signals(sample_market_data)

        # 验证排序：STRONG > MODERATE > WEAK
        assert len(signals) == 3
        assert signals[0].strength == SignalStrength.STRONG
        assert signals[1].strength == SignalStrength.MODERATE
        assert signals[2].strength == SignalStrength.WEAK

    def test_get_stats(self, signal_pool):
        """测试获取统计信息"""
        strategy = MockStrategy(name="TestStrategy")
        signal_pool.register_strategy(strategy)

        stats = signal_pool.get_stats()

        assert 'total_signals' in stats
        assert 'signals_by_strategy' in stats
        assert 'signals_by_symbol' in stats
        assert 'TestStrategy' in stats['signals_by_strategy']

    def test_reset_stats(self, signal_pool):
        """测试重置统计信息"""
        # 添加一些统计
        signal_pool._stats['total_signals'] = 10
        signal_pool.register_strategy(MockStrategy(name="TestStrategy"))
        signal_pool._stats['signals_by_strategy']['TestStrategy'] = 5

        signal_pool.reset_stats()

        assert signal_pool._stats['total_signals'] == 0
        assert signal_pool._stats['signals_by_strategy']['TestStrategy'] == 0


# ============================================================================
# StrategySelector Tests
# ============================================================================

class TestStrategySelector:
    """StrategySelector 测试类"""

    @pytest.fixture
    def mock_provider_manager(self, mocker):
        """模拟 Provider Manager"""
        mock = mocker.MagicMock()
        mock.get_active = mocker.MagicMock()
        return mock

    @pytest.fixture
    def mock_risk_controller(self, mocker):
        """模拟风控控制器"""
        mock = mocker.MagicMock()
        mock.validate = mocker.MagicMock(return_value=(True, "通过"))
        return mock

    @pytest.fixture
    def selector(self, mock_provider_manager, mock_risk_controller):
        """StrategySelector 实例"""
        return StrategySelector(
            provider_manager=mock_provider_manager,
            risk_controller=mock_risk_controller,
            min_confidence=0.6,
            max_signals=10,
        )

    @pytest.mark.asyncio
    async def test_select_no_signals(self, selector):
        """测试无信号时返回 None"""
        result = await selector.select([], None)

        assert result is None

    @pytest.mark.asyncio
    async def test_select_success(
        self,
        selector,
        mock_provider_manager,
        mock_risk_controller,
        sample_signal,
        sample_market_context,
    ):
        """测试成功的选择流程"""
        # 设置模拟决策
        mock_decision = EvidenceBasedDecision(
            action=ActionType.BUY,
            confidence=0.8,
            reasoning="Test reasoning",
            evidence_chain=["evidence1", "evidence2"],
            veto_flag=False,
            entry_price=50000.0,
            stop_loss=48000.0,
            take_profit=55000.0,
            position_size=0.1,
            symbol="BTC/USDT",
            evidence_count=2,
        )

        mock_provider = mock_provider_manager.get_active.return_value
        mock_provider.analyze = lambda x: mock_decision

        signals = [sample_signal]

        result = await selector.select(signals, sample_market_context)

        assert result is not None
        assert result.action == ActionType.BUY
        assert result.confidence == 0.8

        # 验证风控被调用
        mock_risk_controller.validate.assert_called_once()

    @pytest.mark.asyncio
    async def test_select_risk_rejected(
        self,
        selector,
        mock_provider_manager,
        mock_risk_controller,
        sample_signal,
        sample_market_context,
    ):
        """测试风控拒绝的情况"""
        # 设置风控返回失败
        mock_risk_controller.validate.return_value = (False, "风险过高")

        # 设置模拟决策
        mock_decision = EvidenceBasedDecision(
            action=ActionType.BUY,
            confidence=0.8,
            reasoning="Test reasoning",
            evidence_chain=["evidence1"],
            veto_flag=False,
            entry_price=50000.0,
            stop_loss=48000.0,
            take_profit=55000.0,
            position_size=0.1,
            symbol="BTC/USDT",
            evidence_count=1,
        )

        mock_provider = mock_provider_manager.get_active.return_value
        mock_provider.analyze = lambda x: mock_decision

        signals = [sample_signal]

        result = await selector.select(signals, sample_market_context)

        assert result is None  # 风控拒绝应返回 None
        assert selector._stats['risk_rejected'] == 1

    @pytest.mark.asyncio
    async def test_select_low_confidence(
        self,
        selector,
        mock_provider_manager,
        mock_risk_controller,
        sample_signal,
        sample_market_context,
    ):
        """测试置信度过低的情况"""
        # 设置模拟决策（低置信度）
        mock_decision = EvidenceBasedDecision(
            action=ActionType.BUY,
            confidence=0.5,  # 低于 min_confidence=0.6
            reasoning="Test reasoning",
            evidence_chain=["evidence1"],
            veto_flag=False,
            entry_price=50000.0,
            stop_loss=48000.0,
            take_profit=55000.0,
            position_size=0.1,
            symbol="BTC/USDT",
            evidence_count=1,
        )

        mock_provider = mock_provider_manager.get_active.return_value
        mock_provider.analyze = lambda x: mock_decision

        signals = [sample_signal]

        result = await selector.select(signals, sample_market_context)

        assert result is None  # 置信度过低应返回 None

    def test_get_stats(self, selector, mock_provider_manager, mock_risk_controller):
        """测试获取统计信息"""
        stats = selector.get_stats()

        assert 'total_selections' in stats
        assert 'risk_rejected' in stats
        assert 'accepted' in stats
        assert 'errors' in stats
        assert 'accept_rate' in stats
        assert 'risk_rejection_rate' in stats

    def test_reset_stats(self, selector):
        """测试重置统计信息"""
        # 修改一些统计
        selector._stats['total_selections'] = 10
        selector._stats['accepted'] = 5

        selector.reset_stats()

        assert selector._stats['total_selections'] == 0
        assert selector._stats['accepted'] == 0


# ============================================================================
# MTFStrategyAdapter Tests
# ============================================================================

class TestMTFStrategyAdapter:
    """MTF 策略适配器测试类"""

    @pytest.mark.asyncio
    async def test_initialization(self):
        """测试初始化"""
        adapter = MTFStrategyAdapter(priority=10)

        assert adapter.name == "MTFResonanceLock"
        assert adapter.strategy_type == StrategyType.TECHNICAL
        assert adapter.priority == 10

    @pytest.mark.asyncio
    async def test_health_check(self):
        """测试健康检查"""
        adapter = MTFStrategyAdapter()

        # 初始化前应该返回 False
        assert await adapter.health_check() is True  # 会触发初始化

    @pytest.mark.asyncio
    async def test_generate_signal_no_lock(self, sample_market_data):
        """测试无锁定情况下的信号生成"""
        adapter = MTFStrategyAdapter()

        # 由于 MTF 需要真实的市场数据，这里可能会返回 None
        signal = await adapter.generate_signal(sample_market_data)

        # 由于未连接到真实市场，信号可能是 None 或未锁定
        if signal is not None:
            assert signal.symbol == sample_market_data.symbol
            assert signal.source == "MTFResonanceLock"

    def test_convert_mtf_signal(self):
        """测试 MTF 信号转换"""
        from src.quantitative.mtf_resonance_lock import MTFSignal

        adapter = MTFStrategyAdapter()

        mtf_signal = MTFSignal(
            symbol="BTC/USDT",
            signal=1,  # 做多
            confidence=0.95,
            reasons=["4H 趋势向上", "费率极端", "15m 放量"],
            timestamp=datetime.now(),
            is_locked=True,
            breakthrough_price=50000.0,
            breakthrough_vwap=49800.0,
            suggested_entry_price=49800.0,
            wait_for_pullback=True,
        )

        trading_signal = adapter._convert_mtf_signal(mtf_signal)

        assert trading_signal.symbol == "BTC/USDT"
        assert trading_signal.signal_type == ActionType.BUY
        assert trading_signal.strength == SignalStrength.STRONG
        assert trading_signal.confidence == 0.95
        assert trading_signal.source == "MTFResonanceLock"
        assert trading_signal.metadata['mtf_is_locked'] is True
        assert trading_signal.metadata['suggested_entry_price'] == 49800.0

    def test_convert_mtf_signal_sell(self):
        """测试做空信号转换"""
        from src.quantitative.mtf_resonance_lock import MTFSignal

        adapter = MTFStrategyAdapter()

        mtf_signal = MTFSignal(
            symbol="BTC/USDT",
            signal=-1,  # 做空
            confidence=0.85,
            reasons=["4H 趋势向下", "费率极端", "15m 放量"],
            timestamp=datetime.now(),
            is_locked=True,
        )

        trading_signal = adapter._convert_mtf_signal(mtf_signal)

        assert trading_signal.signal_type == ActionType.SELL
        assert trading_signal.strength == SignalStrength.STRONG

    def test_convert_mtf_signal_low_confidence(self):
        """测试低置信度信号转换"""
        from src.quantitative.mtf_resonance_lock import MTFSignal

        adapter = MTFStrategyAdapter()

        mtf_signal = MTFSignal(
            symbol="BTC/USDT",
            signal=1,
            confidence=0.6,  # 低置信度
            reasons=["部分条件满足"],
            timestamp=datetime.now(),
            is_locked=True,
        )

        trading_signal = adapter._convert_mtf_signal(mtf_signal)

        assert trading_signal.strength == SignalStrength.WEAK


# ============================================================================
# Integration Tests
# ============================================================================

class TestIntegration:
    """集成测试"""

    @pytest.mark.asyncio
    async def test_pool_with_mtf_adapter(self, sample_market_data):
        """测试信号池与 MTF 适配器集成"""
        pool = SignalPool()
        adapter = MTFStrategyAdapter(priority=10)

        pool.register_strategy(adapter)

        assert pool.strategy_count == 1

        # 收集信号（由于需要真实市场数据，可能返回空列表）
        signals = await pool.collect_signals(sample_market_data)

        # 验证返回的是列表
        assert isinstance(signals, list)

        # 清理
        await adapter.close()

    @pytest.mark.asyncio
    async def test_multiple_strategies(self, sample_market_data):
        """测试多个策略集成"""
        pool = SignalPool()

        # 创建多个策略
        signal1 = TradingSignal(
            symbol="BTC/USDT",
            timestamp=datetime.now(),
            signal_type=ActionType.BUY,
            strength=SignalStrength.STRONG,
            confidence=0.9,
            source="Test",
        )

        signal2 = TradingSignal(
            symbol="BTC/USDT",
            timestamp=datetime.now(),
            signal_type=ActionType.SELL,
            strength=SignalStrength.MODERATE,
            confidence=0.75,
            source="Test",
        )

        strategy1 = MockStrategy(name="Strategy1", priority=1, signal_to_return=signal1)
        strategy2 = MockStrategy(name="Strategy2", priority=2, signal_to_return=signal2)

        pool.register_strategy(strategy1)
        pool.register_strategy(strategy2)

        signals = await pool.collect_signals(sample_market_data)

        assert len(signals) == 2
        # 验证排序：STRONG > MODERATE
        assert signals[0].strength == SignalStrength.STRONG
        assert signals[1].strength == SignalStrength.MODERATE


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
