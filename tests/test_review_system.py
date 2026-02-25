"""
复盘系统单元测试

测试 ReviewSystem 的所有功能
"""

import asyncio
import pytest
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import Mock, AsyncMock, MagicMock

from src.ai.review.system import ReviewSystem, LearningReport
from src.storage.database import TradingDatabase, Trade, Review
from src.ai.provider.base import (
    TradeResult, ReviewReport, ReviewFinding,
    ActionType, EvidenceBasedDecision
)


@pytest.fixture
def temp_db():
    """创建临时数据库用于测试"""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        db = TradingDatabase(db_path)
        yield db


@pytest.fixture
def mock_provider_manager():
    """创建模拟的 ProviderManager"""
    manager = Mock(spec=object())

    # 模拟 get_active 返回一个 mock provider
    mock_provider = Mock()
    mock_provider.review = AsyncMock(return_value=ReviewReport(
        trade_id="123",
        overall_assessment="测试复盘",
        findings=[
            ReviewFinding(
                category="decision_quality",
                severity="info",
                description="入场时机良好",
                recommendation="继续保持"
            )
        ],
        lessons_learned=["耐心等待"],
        improvements=["设置更宽的止损"],
        score=85.0
    ))

    manager.get_active = Mock(return_value=mock_provider)
    return manager


@pytest.fixture
def sample_trade_result():
    """创建示例交易结果"""
    return TradeResult(
        symbol="BTCUSDT",
        action=ActionType.BUY,
        entry_price=50000.0,
        exit_price=51000.0,
        quantity=1.0,
        pnl=1000.0,
        pnl_pct=2.0,
        entry_time=datetime.now() - timedelta(hours=1),
        exit_time=datetime.now(),
        status="closed",
        metadata={"strategy": "sniper_v1", "signal_strength": 0.85}
    )


@pytest.fixture
def review_system(temp_db, mock_provider_manager):
    """创建复盘系统实例"""
    return ReviewSystem(temp_db, mock_provider_manager)


class TestRecordTrade:
    """测试交易记录功能"""

    @pytest.mark.asyncio
    async def test_record_trade_success(self, review_system, sample_trade_result):
        """测试成功记录交易"""
        await review_system.initialize()

        trade_id = await review_system.record_trade(sample_trade_result)

        assert trade_id > 0

        # 验证交易已保存
        saved_trade = await review_system.database.get_trade(trade_id)
        assert saved_trade is not None
        assert saved_trade.symbol == sample_trade_result.symbol
        assert saved_trade.side == "BUY"
        assert saved_trade.pnl == sample_trade_result.pnl

    @pytest.mark.asyncio
    async def test_record_trade_with_metadata(self, review_system):
        """测试记录带元数据的交易"""
        await review_system.initialize()

        trade = TradeResult(
            symbol="ETHUSDT",
            action=ActionType.SELL,
            entry_price=3000.0,
            exit_price=2900.0,
            quantity=10.0,
            pnl=-1000.0,
            status="closed",
            metadata={
                "strategy": "trend_following",
                "signal_strength": 0.75,
                "market_context": {"trend": "downtrend"}
            }
        )

        trade_id = await review_system.record_trade(trade)

        saved = await review_system.database.get_trade(trade_id)
        assert saved.strategy == "trend_following"
        assert saved.metadata["signal_strength"] == 0.75


class TestGenerateReview:
    """测试生成复盘报告功能"""

    @pytest.mark.asyncio
    async def test_generate_review_success(self, review_system, sample_trade_result):
        """测试成功生成复盘报告"""
        await review_system.initialize()

        # 先保存交易
        trade_id = await review_system.record_trade(sample_trade_result)

        # 生成复盘
        report = await review_system.generate_review(str(trade_id))

        assert report is not None
        assert report.trade_id == str(trade_id)
        assert report.overall_assessment == "测试复盘"
        assert len(report.findings) > 0
        assert report.score == 85.0

    @pytest.mark.asyncio
    async def test_generate_review_not_found(self, review_system):
        """测试交易不存在时的处理"""
        await review_system.initialize()

        with pytest.raises(ValueError, match="Trade not found"):
            await review_system.generate_review("99999")


class TestGenerateLearningReport:
    """测试生成学习报告功能"""

    @pytest.mark.asyncio
    async def test_learning_report_basic(self, review_system):
        """测试基本学习报告生成"""
        await review_system.initialize()

        # 创建测试交易数据
        trades = [
            Trade(symbol="BTCUSDT", side="BUY", quantity=1.0, price=50000, pnl=100, strategy="sniper"),
            Trade(symbol="BTCUSDT", side="BUY", quantity=1.0, price=50100, pnl=150, strategy="sniper"),
            Trade(symbol="BTCUSDT", side="SELL", quantity=1.0, price=50200, pnl=200, strategy="trend"),
            Trade(symbol="BTCUSDT", side="BUY", quantity=1.0, price=50300, pnl=-50, strategy="sniper"),
            Trade(symbol="BTCUSDT", side="SELL", quantity=1.0, price=50400, pnl=-100, strategy="trend"),
        ]

        for trade in trades:
            await review_system.database.save_trade(trade)

        # 生成学习报告
        report = await review_system.generate_learning_report(days=30)

        assert report.total_trades == 5
        assert report.win_rate == 0.6  # 3 赢 / 5 总
        assert report.avg_pnl == 60.0  # (100+150+200-50-100)/5 = 300/5 = 60

    @pytest.mark.asyncio
    async def test_learning_report_by_strategy(self, review_system):
        """测试按策略分组的学习报告"""
        await review_system.initialize()

        # 创建不同策略的交易
        trades = [
            # sniper 策略：3 赢 1 亏，胜率 75%
            Trade(symbol="BTCUSDT", side="BUY", quantity=1.0, price=50000, pnl=100, strategy="sniper"),
            Trade(symbol="BTCUSDT", side="BUY", quantity=1.0, price=50100, pnl=150, strategy="sniper"),
            Trade(symbol="BTCUSDT", side="SELL", quantity=1.0, price=50200, pnl=200, strategy="sniper"),
            Trade(symbol="BTCUSDT", side="BUY", quantity=1.0, price=50300, pnl=-50, strategy="sniper"),
            # trend 策略：1 赢 2 亏，胜率 33%
            Trade(symbol="BTCUSDT", side="SELL", quantity=1.0, price=50400, pnl=80, strategy="trend"),
            Trade(symbol="BTCUSDT", side="BUY", quantity=1.0, price=50500, pnl=-100, strategy="trend"),
            Trade(symbol="BTCUSDT", side="SELL", quantity=1.0, price=50600, pnl=-120, strategy="trend"),
        ]

        for trade in trades:
            await review_system.database.save_trade(trade)

        report = await review_system.generate_learning_report(days=30)

        # 验证 sniper 策略
        assert 'sniper' in report.by_strategy
        sniper_stats = report.by_strategy['sniper']
        assert sniper_stats['total_trades'] == 4
        assert sniper_stats['win_rate'] == 0.75

        # 验证 trend 策略
        assert 'trend' in report.by_strategy
        trend_stats = report.by_strategy['trend']
        assert trend_stats['total_trades'] == 3
        assert trend_stats['win_rate'] == pytest.approx(1/3, 0.01)

        # 验证建议中包含策略比较
        strategy_recommendations = [r for r in report.recommendations if '策略' in r or 'sniper' in r]
        assert len(strategy_recommendations) > 0

    @pytest.mark.asyncio
    async def test_learning_report_empty_data(self, review_system):
        """测试空数据的学习报告"""
        await review_system.initialize()

        report = await review_system.generate_learning_report(days=30)

        assert report.total_trades == 0
        assert report.win_rate == 0.0
        assert report.avg_pnl == 0.0
        assert report.by_strategy == {}

    @pytest.mark.asyncio
    async def test_recommendations_generation(self, review_system):
        """测试建议生成功能"""
        await review_system.initialize()

        # 创建低胜率数据
        trades = []
        for i in range(10):
            trades.append(Trade(
                symbol="BTCUSDT",
                side="BUY",
                quantity=1.0,
                price=50000 + i * 100,
                pnl=-100 if i < 7 else 200  # 70% 亏损
            ))

        for trade in trades:
            await review_system.database.save_trade(trade)

        report = await review_system.generate_learning_report(days=30)

        # 验证生成了低胜率建议
        low_winrate_advice = [r for r in report.recommendations if '胜率' in r and '较低' in r]
        assert len(low_winrate_advice) > 0


class TestUtilityMethods:
    """测试工具方法"""

    @pytest.mark.asyncio
    async def test_trade_to_trade_result(self, review_system):
        """测试 Trade 到 TradeResult 的转换"""
        trade = Trade(
            id=123,
            symbol="BTCUSDT",
            side="SELL",
            quantity=2.0,
            price=55000.0,
            pnl=500.0,
            strategy="trend",
            signal_strength=0.9,
            metadata={"market_conditions": "bullish"}
        )

        result = review_system._trade_to_trade_result(trade)

        assert result.symbol == "BTCUSDT"
        assert result.action == ActionType.SELL
        assert result.quantity == 2.0
        assert result.entry_price == 55000.0
        assert result.pnl == 500.0
        assert result.metadata['strategy'] == "trend"
        assert result.metadata['signal_strength'] == 0.9
