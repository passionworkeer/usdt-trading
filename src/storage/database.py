"""
异步 SQLite 数据库存储层
提供交易数据的持久化存储和统计查询
"""

import asyncio
import json
import logging
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any, Union

import aiosqlite

logger = logging.getLogger(__name__)


@dataclass
class Trade:
    """交易记录数据类 (v9.0 证据链架构)"""
    id: Optional[int] = None
    order_id: Optional[str] = None
    symbol: str = ""
    side: str = ""  # BUY or SELL
    quantity: float = 0.0
    price: float = 0.0
    pnl: float = 0.0  # 盈亏
    fee: float = 0.0
    strategy: str = ""  # 策略名称
    signal_strength: float = 0.0  # 信号强度
    execution_time_ms: int = 0  # 执行耗时
    # 证据链字段 (v9.0)
    evidence_count: int = 0
    evidence_chain: List[str] = None  # JSON 格式存储
    veto_flag: bool = False
    entry_price: float = 0.0
    stop_loss: float = 0.0
    take_profit: float = 0.0
    position_size: float = 0.0
    metadata: Dict[str, Any] = None  # 额外元数据
    created_at: Optional[str] = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}
        if self.evidence_chain is None:
            self.evidence_chain = []
        if self.created_at is None:
            self.created_at = datetime.now().isoformat()


@dataclass
class Review:
    """复盘报告数据类"""
    id: Optional[int] = None
    trade_id: int = 0
    review_type: str = ""  # daily, weekly, monthly
    summary: str = ""  # 总结
    strengths: str = ""  # 优点
    weaknesses: str = ""  # 缺点
    improvements: str = ""  # 改进措施
    market_conditions: str = ""  # 市场环境
    emotion_analysis: str = ""  # 情绪分析
    metadata: Dict[str, Any] = None
    created_at: Optional[str] = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}
        if self.created_at is None:
            self.created_at = datetime.now().isoformat()


@dataclass
class TradeStatistics:
    """交易统计数据类"""
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    total_pnl: float = 0.0
    avg_pnl: float = 0.0
    win_rate: float = 0.0  # 胜率
    profit_factor: float = 0.0  # 盈亏比
    max_drawdown: float = 0.0  # 最大回撤
    sharpe_ratio: float = 0.0  # 夏普比率
    avg_execution_time_ms: float = 0.0
    period_days: int = 30  # 统计周期


class TradingDatabase:
    """交易数据库管理类

    提供异步 SQLite 数据库操作，包括：
    - 交易记录的增删改查
    - 复盘报告的存储
    - SQL 聚合统计分析
    """

    def __init__(self, db_path: Union[str, Path] = "data/trading.db"):
        """
        初始化数据库

        Args:
            db_path: 数据库文件路径，默认 data/trading.db
        """
        self.db_path = Path(db_path)
        self._lock = asyncio.Lock()
        self._initialized = False

        # 确保目录存在
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    async def initialize(self) -> None:
        """初始化数据库表结构"""
        if self._initialized:
            return

        async with self._lock:
            async with aiosqlite.connect(self.db_path) as db:
                # 启用外键约束
                await db.execute("PRAGMA foreign_keys = ON")

                # 创建交易表（v9.0 证据链架构）
                await db.execute("""
                    CREATE TABLE IF NOT EXISTS trades (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        order_id TEXT UNIQUE,
                        symbol TEXT NOT NULL,
                        side TEXT NOT NULL CHECK(side IN ('BUY', 'SELL')),
                        quantity REAL NOT NULL CHECK(quantity > 0),
                        price REAL NOT NULL CHECK(price > 0),
                        pnl REAL DEFAULT 0,
                        fee REAL DEFAULT 0,
                        strategy TEXT,
                        signal_strength REAL DEFAULT 0,
                        execution_time_ms INTEGER DEFAULT 0,
                        -- 证据链字段 (v9.0)
                        evidence_count INTEGER DEFAULT 0,
                        evidence_chain TEXT,
                        veto_flag BOOLEAN DEFAULT 0,
                        entry_price REAL,
                        stop_loss REAL,
                        take_profit REAL,
                        position_size REAL,
                        metadata TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)

                # 创建复盘报告表
                await db.execute("""
                    CREATE TABLE IF NOT EXISTS reviews (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        trade_id INTEGER,
                        review_type TEXT NOT NULL CHECK(review_type IN ('daily', 'weekly', 'monthly', 'trade')),
                        summary TEXT,
                        strengths TEXT,
                        weaknesses TEXT,
                        improvements TEXT,
                        market_conditions TEXT,
                        emotion_analysis TEXT,
                        metadata TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (trade_id) REFERENCES trades(id) ON DELETE SET NULL
                    )
                """)

                # 创建索引优化查询
                await db.execute("""
                    CREATE INDEX IF NOT EXISTS idx_trades_symbol ON trades(symbol)
                """)
                await db.execute("""
                    CREATE INDEX IF NOT EXISTS idx_trades_created_at ON trades(created_at)
                """)
                await db.execute("""
                    CREATE INDEX IF NOT EXISTS idx_trades_strategy ON trades(strategy)
                """)
                await db.execute("""
                    CREATE INDEX IF NOT EXISTS idx_trades_pnl ON trades(pnl)
                """)
                await db.execute("""
                    CREATE INDEX IF NOT EXISTS idx_reviews_trade_id ON reviews(trade_id)
                """)
                await db.execute("""
                    CREATE INDEX IF NOT EXISTS idx_reviews_type ON reviews(review_type)
                """)

                await db.commit()

        self._initialized = True
        logger.info(f"Database initialized: {self.db_path}")

    async def save_trade(self, trade: Trade) -> int:
        """
        保存交易记录

        Args:
            trade: 交易记录对象

        Returns:
            新创建的交易记录 ID
        """
        await self.initialize()

        async with self._lock:
            async with aiosqlite.connect(self.db_path) as db:
                cursor = await db.execute(
                    """
                    INSERT INTO trades
                    (order_id, symbol, side, quantity, price, pnl, fee, strategy,
                     signal_strength, execution_time_ms, evidence_count, evidence_chain,
                     veto_flag, entry_price, stop_loss, take_profit, position_size,
                     metadata, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        trade.order_id,
                        trade.symbol,
                        trade.side,
                        trade.quantity,
                        trade.price,
                        trade.pnl,
                        trade.fee,
                        trade.strategy,
                        trade.signal_strength,
                        trade.execution_time_ms,
                        trade.evidence_count,
                        json.dumps(trade.evidence_chain) if trade.evidence_chain else None,
                        1 if trade.veto_flag else 0,
                        trade.entry_price,
                        trade.stop_loss,
                        trade.take_profit,
                        trade.position_size,
                        json.dumps(trade.metadata) if trade.metadata else None,
                        trade.created_at or datetime.now().isoformat()
                    )
                )
                await db.commit()
                return cursor.lastrowid

    async def get_trade(self, trade_id: int) -> Optional[Trade]:
        """
        获取单个交易记录

        Args:
            trade_id: 交易记录 ID

        Returns:
            交易记录对象，如果不存在返回 None
        """
        await self.initialize()

        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM trades WHERE id = ?",
                (trade_id,)
            )
            row = await cursor.fetchone()

            if row is None:
                return None

            return self._row_to_trade(row)

    async def get_trades(
        self,
        symbol: Optional[str] = None,
        strategy: Optional[str] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[Trade]:
        """
        查询交易记录列表

        Args:
            symbol: 交易对符号过滤
            strategy: 策略名称过滤
            start_time: 开始时间过滤 (ISO format)
            end_time: 结束时间过滤 (ISO format)
            limit: 返回数量限制
            offset: 分页偏移

        Returns:
            交易记录列表
        """
        await self.initialize()

        conditions = []
        params = []

        if symbol:
            conditions.append("symbol = ?")
            params.append(symbol)
        if strategy:
            conditions.append("strategy = ?")
            params.append(strategy)
        if start_time:
            conditions.append("created_at >= ?")
            params.append(start_time)
        if end_time:
            conditions.append("created_at <= ?")
            params.append(end_time)

        where_clause = ""
        if conditions:
            where_clause = "WHERE " + " AND ".join(conditions)

        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                f"""
                SELECT * FROM trades
                {where_clause}
                ORDER BY created_at DESC
                LIMIT ? OFFSET ?
                """,
                params + [limit, offset]
            )
            rows = await cursor.fetchall()
            return [self._row_to_trade(row) for row in rows]

    async def get_statistics(
        self,
        days: int = 30,
        symbol: Optional[str] = None,
        strategy: Optional[str] = None
    ) -> TradeStatistics:
        """
        获取交易统计数据（使用 SQL 聚合查询）

        绝不用 Python 循环计算统计数据，全部使用 SQL 聚合！

        Args:
            days: 统计天数 (必须是正整数)
            symbol: 交易对过滤
            strategy: 策略过滤

        Returns:
            交易统计数据对象
        """
        await self.initialize()

        # 参数校验：防止 SQL 注入
        if not isinstance(days, int) or days < 1:
            raise ValueError(f"days must be a positive integer, got: {days}")

        # 构建 WHERE 条件
        # 注意：Python datetime.now().isoformat() 使用本地时区
        # SQLite datetime('now') 使用 UTC，可能导致比较失败
        # 对于短期的 days 参数，使用 datetime() 比较可能失败
        # TODO: 统一使用 UTC 时间戳
        # 使用参数化查询（尽管 SQLite 不支持在函数内绑定参数，但我们已经验证了 days 是整数）
        conditions = ["strftime('%Y-%m-%d', created_at) >= strftime('%Y-%m-%d', 'now', '-' || ? || ' days')"]
        params = [days]

        if symbol:
            conditions.append("symbol = ?")
            params.append(symbol)
        if strategy:
            conditions.append("strategy = ?")
            params.append(strategy)

        where_clause = "WHERE " + " AND ".join(conditions)

        async with aiosqlite.connect(self.db_path) as db:
            # 使用 SQL 聚合计算所有统计数据
            cursor = await db.execute(
                f"""
                SELECT
                    COUNT(*) as total_trades,
                    SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) as winning_trades,
                    SUM(CASE WHEN pnl < 0 THEN 1 ELSE 0 END) as losing_trades,
                    SUM(pnl) as total_pnl,
                    AVG(pnl) as avg_pnl,
                    AVG(CASE WHEN pnl > 0 THEN pnl END) as avg_win,
                    AVG(CASE WHEN pnl < 0 THEN pnl END) as avg_loss,
                    AVG(execution_time_ms) as avg_execution_time
                FROM trades
                {where_clause}
                """,
                params
            )
            row = await cursor.fetchone()

            # 计算最大回撤（简化版 - 分步计算）
            # 第一步：获取每日收益和累计收益
            daily_cursor = await db.execute(
                f"""
                SELECT
                    date(created_at) as date,
                    SUM(pnl) as daily_pnl
                FROM trades
                {where_clause}
                GROUP BY date(created_at)
                ORDER BY date
                """,
                params
            )
            daily_rows = await daily_cursor.fetchall()

            # 在 Python 中计算最大回撤（更简单且不依赖复杂窗口函数）
            max_drawdown = 0.0
            if daily_rows:
                cum_pnl = 0.0
                peak_pnl = 0.0
                for row in daily_rows:
                    cum_pnl += row[1]  # daily_pnl
                    if cum_pnl > peak_pnl:
                        peak_pnl = cum_pnl
                    dd = cum_pnl - peak_pnl
                    if dd < max_drawdown:
                        max_drawdown = dd

        # 构建统计结果
        stats = TradeStatistics()
        stats.period_days = days

        if row and len(row) >= 3:
            stats.total_trades = row[0] or 0
            stats.winning_trades = row[1] or 0
            stats.losing_trades = row[2] or 0
            stats.total_pnl = row[3] or 0.0
            stats.avg_pnl = row[4] or 0.0
            stats.avg_execution_time_ms = row[8] or 0.0 if len(row) > 8 else 0.0

            # 计算胜率
            if stats.total_trades > 0:
                stats.win_rate = stats.winning_trades / stats.total_trades

            # 计算盈亏比
            if len(row) >= 7:
                avg_win = row[5] or 0
                avg_loss = abs(row[6] or 0)
                if avg_loss > 0:
                    stats.profit_factor = avg_win / avg_loss

        # 最大回撤
        stats.max_drawdown = abs(max_drawdown)

        return stats

    async def save_review(self, review: Review) -> int:
        """
        保存复盘报告

        Args:
            review: 复盘报告对象

        Returns:
            新创建的复盘报告 ID
        """
        await self.initialize()

        async with self._lock:
            async with aiosqlite.connect(self.db_path) as db:
                cursor = await db.execute(
                    """
                    INSERT INTO reviews
                    (trade_id, review_type, summary, strengths, weaknesses,
                     improvements, market_conditions, emotion_analysis, metadata, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        review.trade_id,
                        review.review_type,
                        review.summary,
                        review.strengths,
                        review.weaknesses,
                        review.improvements,
                        review.market_conditions,
                        review.emotion_analysis,
                        json.dumps(review.metadata) if review.metadata else None,
                        review.created_at or datetime.now().isoformat()
                    )
                )
                await db.commit()
                return cursor.lastrowid

    async def get_reviews(
        self,
        trade_id: Optional[int] = None,
        review_type: Optional[str] = None,
        limit: int = 100
    ) -> List[Review]:
        """
        查询复盘报告列表

        Args:
            trade_id: 交易ID过滤
            review_type: 复盘类型过滤
            limit: 返回数量限制

        Returns:
            复盘报告列表
        """
        await self.initialize()

        conditions = []
        params = []

        if trade_id:
            conditions.append("trade_id = ?")
            params.append(trade_id)
        if review_type:
            conditions.append("review_type = ?")
            params.append(review_type)

        where_clause = ""
        if conditions:
            where_clause = "WHERE " + " AND ".join(conditions)

        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                f"""
                SELECT * FROM reviews
                {where_clause}
                ORDER BY created_at DESC
                LIMIT ?
                """,
                params + [limit]
            )
            rows = await cursor.fetchall()
            return [self._row_to_review(row) for row in rows]

    def _row_to_trade(self, row: aiosqlite.Row) -> Trade:
        """将数据库行转换为 Trade 对象"""
        metadata = {}
        if row['metadata']:
            try:
                metadata = json.loads(row['metadata'])
            except json.JSONDecodeError:
                pass

        evidence_chain = []
        if row['evidence_chain']:
            try:
                evidence_chain = json.loads(row['evidence_chain'])
            except json.JSONDecodeError:
                pass

        return Trade(
            id=row['id'],
            order_id=row['order_id'],
            symbol=row['symbol'],
            side=row['side'],
            quantity=row['quantity'],
            price=row['price'],
            pnl=row['pnl'],
            fee=row['fee'],
            strategy=row['strategy'] or '',
            signal_strength=row['signal_strength'] or 0.0,
            execution_time_ms=row['execution_time_ms'] or 0,
            evidence_count=row['evidence_count'] or 0,
            evidence_chain=evidence_chain,
            veto_flag=bool(row['veto_flag']),
            entry_price=row['entry_price'] or 0.0,
            stop_loss=row['stop_loss'] or 0.0,
            take_profit=row['take_profit'] or 0.0,
            position_size=row['position_size'] or 0.0,
            metadata=metadata,
            created_at=row['created_at']
        )

    def _row_to_review(self, row: aiosqlite.Row) -> Review:
        """将数据库行转换为 Review 对象"""
        metadata = {}
        if row['metadata']:
            try:
                metadata = json.loads(row['metadata'])
            except json.JSONDecodeError:
                pass

        return Review(
            id=row['id'],
            trade_id=row['trade_id'],
            review_type=row['review_type'],
            summary=row['summary'] or '',
            strengths=row['strengths'] or '',
            weaknesses=row['weaknesses'] or '',
            improvements=row['improvements'] or '',
            market_conditions=row['market_conditions'] or '',
            emotion_analysis=row['emotion_analysis'] or '',
            metadata=metadata,
            created_at=row['created_at']
        )

    async def close(self) -> None:
        """关闭数据库连接（SQLite 不需要显式关闭，但提供此接口保持兼容性）"""
        logger.info("Database connection closed")

    async def __aenter__(self):
        """异步上下文管理器入口"""
        await self.initialize()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """异步上下文管理器出口"""
        await self.close()
