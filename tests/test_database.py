"""
数据库模块单元测试
测试 TradingDatabase 的所有功能
"""

import asyncio
import pytest
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

from src.storage.database import (
    TradingDatabase, Trade, Review, TradeStatistics
)


@pytest.fixture
async def temp_db():
    """创建临时数据库用于测试"""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        db = TradingDatabase(db_path)
        await db.initialize()
        yield db
        await db.close()


@pytest.fixture
def sample_trade():
    """创建示例交易"""
    return Trade(
        symbol="BTCUSDT",
        side="BUY",
        quantity=0.5,
        price=50000.0,
        pnl=100.0,
        fee=0.5,
        strategy="sniper_v1",
        signal_strength=0.85,
        execution_time_ms=150,
        metadata={"source": "test"}
    )


@pytest.fixture
def sample_review():
    """创建示例复盘"""
    return Review(
        trade_id=1,
        review_type="trade",
        summary="这是一次成功的交易",
        strengths="入场时机精准",
        weaknesses="出场稍早",
        improvements="可以持有更久",
        market_conditions="牛市环境",
        emotion_analysis="保持冷静"
    )


class TestTradeOperations:
    """测试交易操作"""

    @pytest.mark.asyncio
    async def test_save_and_get_trade(self, temp_db, sample_trade):
        """测试保存和获取交易"""
        trade_id = await temp_db.save_trade(sample_trade)
        assert trade_id > 0

        retrieved = await temp_db.get_trade(trade_id)
        assert retrieved is not None
        assert retrieved.symbol == sample_trade.symbol
        assert retrieved.side == sample_trade.side
        assert retrieved.quantity == sample_trade.quantity
        assert retrieved.price == sample_trade.price
        assert retrieved.pnl == sample_trade.pnl

    @pytest.mark.asyncio
    async def test_get_trades_with_filters(self, temp_db):
        """测试带过滤条件的交易查询"""
        # 创建多个交易
        trades = [
            Trade(symbol="BTCUSDT", side="BUY", quantity=1.0, price=50000, pnl=100, strategy="sniper"),
            Trade(symbol="ETHUSDT", side="SELL", quantity=10.0, price=3000, pnl=-50, strategy="sniper"),
            Trade(symbol="BTCUSDT", side="BUY", quantity=0.5, price=51000, pnl=200, strategy="trend"),
        ]

        for trade in trades:
            await temp_db.save_trade(trade)

        # 按 symbol 过滤
        btc_trades = await temp_db.get_trades(symbol="BTCUSDT")
        assert len(btc_trades) == 2

        # 按策略过滤
        sniper_trades = await temp_db.get_trades(strategy="sniper")
        assert len(sniper_trades) == 2

        # 组合过滤
        filtered = await temp_db.get_trades(symbol="BTCUSDT", strategy="trend")
        assert len(filtered) == 1

    @pytest.mark.asyncio
    async def test_get_trades_pagination(self, temp_db):
        """测试交易分页查询"""
        # 创建 15 个交易
        for i in range(15):
            trade = Trade(
                symbol="BTCUSDT",
                side="BUY",
                quantity=1.0,
                price=50000 + i * 100,
                pnl=100
            )
            await temp_db.save_trade(trade)

        # 第一页
        page1 = await temp_db.get_trades(limit=5, offset=0)
        assert len(page1) == 5

        # 第二页
        page2 = await temp_db.get_trades(limit=5, offset=5)
        assert len(page2) == 5

        # 第三页
        page3 = await temp_db.get_trades(limit=5, offset=10)
        assert len(page3) == 5


class TestStatistics:
    """测试统计功能"""

    @pytest.mark.asyncio
    async def test_get_statistics_basic(self, temp_db):
        """测试基本统计计算"""
        # 创建测试数据：5 赢 3 亏
        trades = [
            Trade(symbol="BTCUSDT", side="BUY", quantity=1.0, price=50000, pnl=100, strategy="sniper", execution_time_ms=100),
            Trade(symbol="BTCUSDT", side="BUY", quantity=1.0, price=50100, pnl=150, strategy="sniper", execution_time_ms=120),
            Trade(symbol="BTCUSDT", side="SELL", quantity=1.0, price=50200, pnl=200, strategy="trend", execution_time_ms=150),
            Trade(symbol="BTCUSDT", side="BUY", quantity=1.0, price=50300, pnl=80, strategy="sniper", execution_time_ms=110),
            Trade(symbol="BTCUSDT", side="SELL", quantity=1.0, price=50400, pnl=120, strategy="trend", execution_time_ms=130),
            Trade(symbol="BTCUSDT", side="BUY", quantity=1.0, price=50500, pnl=-50, strategy="sniper", execution_time_ms=100),
            Trade(symbol="BTCUSDT", side="SELL", quantity=1.0, price=50600, pnl=-100, strategy="trend", execution_time_ms=140),
            Trade(symbol="BTCUSDT", side="BUY", quantity=1.0, price=50700, pnl=-80, strategy="sniper", execution_time_ms=115),
        ]

        for trade in trades:
            await temp_db.save_trade(trade)

        # 获取统计
        stats = await temp_db.get_statistics(days=30)

        # 验证基本计数
        assert stats.total_trades == 8  # 修正：创建了8笔交易
        assert stats.winning_trades == 5  # pnl > 0
        assert stats.losing_trades == 3   # pnl < 0

        # 验证盈亏计算
        expected_total_pnl = sum(t.pnl for t in trades)
        assert abs(stats.total_pnl - expected_total_pnl) < 0.01
        assert abs(stats.avg_pnl - expected_total_pnl / 8) < 0.01  # 修正：8笔交易

        # 验证胜率
        expected_win_rate = 5 / 8  # 修正：5胜8笔
        assert abs(stats.win_rate - expected_win_rate) < 0.01

        # 验证执行时间
        expected_avg_exec = sum(t.execution_time_ms for t in trades) / 8  # 修正：8笔交易
        assert abs(stats.avg_execution_time_ms - expected_avg_exec) < 0.1

    @pytest.mark.asyncio
    async def test_get_statistics_with_filters(self, temp_db):
        """测试带过滤的统计"""
        # 创建不同策略和交易对的数据
        trades = [
            Trade(symbol="BTCUSDT", side="BUY", quantity=1.0, price=50000, pnl=100, strategy="sniper"),
            Trade(symbol="BTCUSDT", side="BUY", quantity=1.0, price=50100, pnl=150, strategy="sniper"),
            Trade(symbol="ETHUSDT", side="BUY", quantity=10.0, price=3000, pnl=200, strategy="sniper"),
            Trade(symbol="BTCUSDT", side="SELL", quantity=1.0, price=50200, pnl=-50, strategy="trend"),
            Trade(symbol="ETHUSDT", side="SELL", quantity=10.0, price=3100, pnl=-100, strategy="trend"),
        ]

        for trade in trades:
            await temp_db.save_trade(trade)

        # 按策略过滤
        sniper_stats = await temp_db.get_statistics(days=30, strategy="sniper")
        assert sniper_stats.total_trades == 3
        assert sniper_stats.total_pnl == 450  # 100 + 150 + 200

        trend_stats = await temp_db.get_statistics(days=30, strategy="trend")
        assert trend_stats.total_trades == 2
        assert trend_stats.total_pnl == -150  # -50 + (-100)

        # 按交易对过滤
        btc_stats = await temp_db.get_statistics(days=30, symbol="BTCUSDT")
        assert btc_stats.total_trades == 3  # 2 sniper + 1 trend

        eth_stats = await temp_db.get_statistics(days=30, symbol="ETHUSDT")
        assert eth_stats.total_trades == 2

    @pytest.mark.asyncio
    async def test_get_statistics_empty_data(self, temp_db):
        """测试空数据的统计"""
        stats = await temp_db.get_statistics(days=30)

        assert stats.total_trades == 0
        assert stats.winning_trades == 0
        assert stats.losing_trades == 0
        assert stats.total_pnl == 0.0
        assert stats.win_rate == 0.0
        assert stats.profit_factor == 0.0


class TestReviewOperations:
    """测试复盘操作"""

    @pytest.mark.asyncio
    async def test_save_and_get_review(self, temp_db, sample_trade, sample_review):
        """测试保存和获取复盘"""
        # 先保存交易
        trade_id = await temp_db.save_trade(sample_trade)

        # 创建复盘（关联交易）
        review = Review(
            trade_id=trade_id,
            review_type="trade",
            summary="交易表现不错",
            strengths="执行果断",
            weaknesses="止盈过早",
            improvements="设置更合理的止盈位",
            market_conditions="上涨趋势",
            emotion_analysis="情绪稳定"
        )

        review_id = await temp_db.save_review(review)
        assert review_id > 0

        # 查询复盘
        reviews = await temp_db.get_reviews(trade_id=trade_id)
        assert len(reviews) == 1
        assert reviews[0].summary == "交易表现不错"
        assert reviews[0].strengths == "执行果断"

    @pytest.mark.asyncio
    async def test_get_reviews_by_type(self, temp_db):
        """测试按类型查询复盘"""
        # 创建不同类型的复盘
        reviews = [
            Review(trade_id=1, review_type="daily", summary="日复盘1"),
            Review(trade_id=2, review_type="daily", summary="日复盘2"),
            Review(trade_id=None, review_type="weekly", summary="周复盘"),
            Review(trade_id=None, review_type="monthly", summary="月复盘"),
        ]

        for review in reviews:
            await temp_db.save_review(review)

        # 按类型查询
        daily_reviews = await temp_db.get_reviews(review_type="daily")
        assert len(daily_reviews) == 2

        weekly_reviews = await temp_db.get_reviews(review_type="weekly")
        assert len(weekly_reviews) == 1

        monthly_reviews = await temp_db.get_reviews(review_type="monthly")
        assert len(monthly_reviews) == 1


class TestEdgeCases:
    """测试边界情况"""

    @pytest.mark.asyncio
    async def test_concurrent_access(self, temp_db, sample_trade):
        """测试并发访问"""
        async def save_multiple_trades(n):
            for i in range(n):
                trade = Trade(
                    symbol="BTCUSDT",
                    side="BUY",
                    quantity=1.0,
                    price=50000 + i,
                    pnl=100 + i
                )
                await temp_db.save_trade(trade)

        # 并发保存
        await asyncio.gather(
            save_multiple_trades(10),
            save_multiple_trades(10),
            save_multiple_trades(10)
        )

        # 验证总数
        stats = await temp_db.get_statistics(days=30)
        assert stats.total_trades == 30

    @pytest.mark.asyncio
    async def test_large_pnl_values(self, temp_db):
        """测试大数值盈亏"""
        trades = [
            Trade(symbol="BTCUSDT", side="BUY", quantity=1.0, price=50000, pnl=1_000_000),
            Trade(symbol="BTCUSDT", side="SELL", quantity=1.0, price=51000, pnl=-500_000),
            Trade(symbol="BTCUSDT", side="BUY", quantity=1.0, price=52000, pnl=0.0001),
        ]

        for trade in trades:
            await temp_db.save_trade(trade)

        stats = await temp_db.get_statistics(days=30)
        assert stats.total_trades == 3
        assert stats.total_pnl == 500_000.0001

    @pytest.mark.asyncio
    async def test_metadata_handling(self, temp_db, sample_trade):
        """测试元数据处理"""
        sample_trade.metadata = {
            "entry_signal": "breakout",
            "confidence": 0.95,
            "market_context": {
                "trend": "up",
                "volatility": "high"
            },
            "tags": ["momentum", "breakout"]
        }

        trade_id = await temp_db.save_trade(sample_trade)
        retrieved = await temp_db.get_trade(trade_id)

        assert retrieved.metadata == sample_trade.metadata
        assert retrieved.metadata["market_context"]["trend"] == "up"
        assert "momentum" in retrieved.metadata["tags"]

    @pytest.mark.asyncio
    async def test_invalid_data_handling(self, temp_db):
        """测试无效数据处理"""
        # 测试获取不存在的交易
        non_existent = await temp_db.get_trade(99999)
        assert non_existent is None

        # 测试空复盘列表
        empty_reviews = await temp_db.get_reviews(trade_id=99999)
        assert empty_reviews == []


class TestDatabaseContextManager:
    """测试上下文管理器"""

    @pytest.mark.asyncio
    async def test_async_context_manager(self):
        """测试异步上下文管理器"""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"

            async with TradingDatabase(db_path) as db:
                # 数据库应已初始化
                trade = Trade(
                    symbol="BTCUSDT",
                    side="BUY",
                    quantity=1.0,
                    price=50000,
                    pnl=100
                )
                trade_id = await db.save_trade(trade)
                assert trade_id > 0

            # 退出上下文后，数据应该还在
            db2 = TradingDatabase(db_path)
            await db2.initialize()
            retrieved = await db2.get_trade(trade_id)
            assert retrieved is not None
            assert retrieved.pnl == 100
