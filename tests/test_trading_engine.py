"""
交易引擎集成测试

测试交易引擎的主循环和各组件集成。
"""
import asyncio
import pytest
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, patch

from src.ai.models import (
    ActionType,
    EvidenceBasedDecision,
    SignalStrength,
    TradeOutcome,
    TradingSignal,
    TradeResult,
)
from src.orchestrator.trading_engine import (
    TradingEngine,
    EngineStats,
    SignalPool,
    StrategySelector,
    ExchangeExecutor,
    ReviewSystem,
    create_trading_engine,
)
from src.risk.evidence_controller import EvidenceBasedRiskController


# ============================================================================
# Mock 实现
# ============================================================================

class MockSignalPool:
    """模拟信号池"""

    def __init__(self, signals: List[TradingSignal] = None):
        self._signals = signals or []
        self.collect_signals = AsyncMock(return_value=self._signals)

    def set_signals(self, signals: List[TradingSignal]):
        self._signals = signals
        self.collect_signals = AsyncMock(return_value=self._signals)


class MockStrategySelector:
    """模拟策略选择器"""

    def __init__(self, decision: Optional[EvidenceBasedDecision] = None):
        self._decision = decision
        self.select = AsyncMock(return_value=self._decision)

    def set_decision(self, decision: Optional[EvidenceBasedDecision]):
        self._decision = decision
        self.select = AsyncMock(return_value=self._decision)


class MockExchangeExecutor:
    """模拟交易所执行器"""

    def __init__(self, trade_result: Optional[TradeResult] = None):
        self._trade_result = trade_result
        self.execute = AsyncMock(return_value=self._trade_result)

    def set_result(self, trade_result: TradeResult):
        self._trade_result = trade_result
        self.execute = AsyncMock(return_value=self._trade_result)


class MockReviewSystem:
    """模拟复盘系统"""

    def __init__(self):
        self.record_trade = AsyncMock()


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def mock_signal_pool():
    """模拟信号池 fixture"""
    signal = TradingSignal(
        symbol="BTC/USDT",
        timestamp=datetime.now(),
        signal_type=ActionType.BUY,
        strength=SignalStrength.STRONG,
        confidence=0.85,
        source="test",
    )
    return MockSignalPool([signal])


@pytest.fixture
def mock_strategy_selector():
    """模拟策略选择器 fixture"""
    decision = EvidenceBasedDecision(
        action="long",
        evidence_count=3,
        evidence_chain=["信号1", "信号2", "信号3"],
        veto_flag=False,
        entry_price=50000.0,
        stop_loss=48000.0,
        take_profit=55000.0,
        position_size=0.1,
        symbol="BTC/USDT",
    )
    return MockStrategySelector(decision)


@pytest.fixture
def risk_controller():
    """风控控制器 fixture"""
    return EvidenceBasedRiskController(
        min_evidence_count=1,
        max_evidence_count=10,
        allow_veto_override=False
    )


@pytest.fixture
def mock_exchange_executor():
    """模拟交易所执行器 fixture"""
    trade_result = TradeResult(
        trade_id="test_trade_001",
        symbol="BTC/USDT",
        entry_time=datetime.now(),
        exit_time=datetime.now(),
        entry_price=50000.0,
        exit_price=51000.0,
        position_size=0.1,
        direction="long",
        outcome=TradeOutcome.WIN,
        pnl=100.0,
        pnl_percent=2.0,
        fees=1.0,
        slippage=0.0,
        max_drawdown=0.5,
        exit_reason="take_profit",
    )
    return MockExchangeExecutor(trade_result)


@pytest.fixture
def mock_review_system():
    """模拟复盘系统 fixture"""
    return MockReviewSystem()


@pytest.fixture
def engine(
    mock_signal_pool,
    mock_strategy_selector,
    risk_controller,
    mock_exchange_executor,
    mock_review_system
):
    """交易引擎 fixture"""
    config = {
        'tick_interval': 1,  # 1 秒用于测试
        'dry_run': True,
    }

    return TradingEngine(
        signal_pool=mock_signal_pool,
        strategy_selector=mock_strategy_selector,
        risk_controller=risk_controller,
        exchange_executor=mock_exchange_executor,
        review_system=mock_review_system,
        config=config
    )


# ============================================================================
# 测试用例
# ============================================================================

class TestTradingEngine:
    """交易引擎测试类"""

    @pytest.mark.asyncio
    async def test_engine_initialization(self, engine):
        """测试引擎初始化"""
        assert engine.is_running is False
        assert engine.stats.tick_count == 0
        assert engine.stats.trade_count == 0

    @pytest.mark.asyncio
    async def test_engine_start_stop(self, engine):
        """测试引擎启动和停止"""
        # 启动引擎（在后台运行）
        run_task = asyncio.create_task(engine.run())

        # 等待一下让引擎启动
        await asyncio.sleep(0.5)

        # 验证引擎已启动
        assert engine.is_running is True

        # 关闭引擎
        await engine.shutdown()

        # 等待任务完成
        try:
            await asyncio.wait_for(run_task, timeout=2.0)
        except asyncio.TimeoutError:
            run_task.cancel()
            try:
                await run_task
            except asyncio.CancelledError:
                pass

        # 验证引擎已停止
        assert engine.is_running is False

    @pytest.mark.asyncio
    async def test_tick_signal_collection(self, engine):
        """测试 Tick 信号收集"""
        # 直接调用 _tick 方法测试
        await engine._tick()

        # 验证信号池的 collect_signals 被调用
        engine.signal_pool.collect_signals.assert_called_once()

    @pytest.mark.asyncio
    async def test_tick_decision_making(self, engine):
        """测试 Tick 决策生成"""
        await engine._tick()

        # 验证策略选择器的 select 被调用
        engine.strategy_selector.select.assert_called_once()

    @pytest.mark.asyncio
    async def test_tick_trade_execution(self, engine):
        """测试 Tick 交易执行"""
        await engine._tick()

        # 验证交易所执行器的 execute 被调用
        engine.exchange_executor.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_tick_review_recording(self, engine):
        """测试 Tick 复盘记录"""
        await engine._tick()

        # 验证复盘系统的 record_trade 被调用
        engine.review_system.record_trade.assert_called_once()

    @pytest.mark.asyncio
    async def test_tick_no_signals(self, engine):
        """测试无信号时跳过"""
        # 设置信号池返回空列表
        engine.signal_pool = MockSignalPool([])

        await engine._tick()

        # 验证策略选择器没有被调用
        engine.strategy_selector.select.assert_not_called()

    @pytest.mark.asyncio
    async def test_tick_decision_rejected(self, engine, risk_controller):
        """测试决策被拒绝"""
        # 创建一个带有否决标志的决策
        decision = EvidenceBasedDecision(
            action="long",
            evidence_count=1,
            evidence_chain=["test"],
            veto_flag=True,  # 否决标记
            entry_price=50000.0,
            stop_loss=48000.0,
            take_profit=55000.0,
            position_size=0.1,
            symbol="BTC/USDT",
        )
        engine.strategy_selector = MockStrategySelector(decision)

        await engine._tick()

        # 验证交易没有被执行（因为风控拦截）
        engine.exchange_executor.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_stats_tracking(self, engine):
        """测试统计信息追踪"""
        # 运行一次 tick
        await engine._tick()

        # 验证统计信息
        assert engine.stats.tick_count == 0  # tick_count 在 run() 中增加
        assert engine.stats.signal_count > 0
        assert engine.stats.decision_count > 0
        assert engine.stats.trade_count > 0


class TestCreateTradingEngine:
    """测试 create_trading_engine 便捷函数"""

    @pytest.mark.asyncio
    async def test_create_engine(self):
        """测试创建引擎"""
        signal_pool = MockSignalPool()
        strategy_selector = MockStrategySelector()
        risk_controller = EvidenceBasedRiskController()
        exchange_executor = MockExchangeExecutor()
        review_system = MockReviewSystem()

        engine = create_trading_engine(
            signal_pool=signal_pool,
            strategy_selector=strategy_selector,
            risk_controller=risk_controller,
            exchange_executor=exchange_executor,
            review_system=review_system,
            tick_interval=60,
            dry_run=True,
        )

        assert isinstance(engine, TradingEngine)
        assert engine.config['tick_interval'] == 60
        assert engine.config['dry_run'] is True


class TestEngineProtocols:
    """测试引擎的 Protocol 接口"""

    def test_signal_pool_protocol(self):
        """测试 SignalPool 协议"""
        pool = MockSignalPool()
        # 检查是否符合协议
        assert hasattr(pool, 'collect_signals')

    def test_strategy_selector_protocol(self):
        """测试 StrategySelector 协议"""
        selector = MockStrategySelector()
        assert hasattr(selector, 'select')

    def test_exchange_executor_protocol(self):
        """测试 ExchangeExecutor 协议"""
        executor = MockExchangeExecutor()
        assert hasattr(executor, 'execute')

    def test_review_system_protocol(self):
        """测试 ReviewSystem 协议"""
        review = MockReviewSystem()
        assert hasattr(review, 'record_trade')


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
