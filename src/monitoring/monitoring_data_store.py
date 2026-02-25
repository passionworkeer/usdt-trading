"""
P2-24: 监控数据持久化（Monitoring Data Persistence）

将历史监控数据保存到 SQLite 数据库或 JSON 文件
"""
import os
import json
import logging
import sqlite3
from typing import Dict, List, Any, Optional
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock

logger = logging.getLogger(__name__)


class MonitoringDataStore:
    """
    监控数据存储管理器

    支持两种存储方式：
    1. SQLite - 适合大量结构化数据查询
    2. JSON - 适合快速查看和调试

    存储内容：
    - 历史监控指标
    - 仓位快照
    - 交易统计
    - 系统健康数据
    """

    def __init__(
        self,
        db_path: str = 'data/monitoring.db',
        json_dir: str = 'data/monitoring/json',
        retention_days: int = 30,
    ):
        """
        初始化监控数据存储

        Args:
            db_path: SQLite 数据库路径
            json_dir: JSON 文件存储目录
            retention_days: 数据保留天数
        """
        self.db_path = db_path
        self.json_dir = json_dir
        self.retention_days = retention_days
        self._lock = Lock()

        # 创建目录
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        os.makedirs(json_dir, exist_ok=True)

        # 初始化数据库
        self._init_db()

        logger.info("📊 监控数据存储已初始化")
        logger.info(f"  数据库: {db_path}")
        logger.info(f"  JSON 目录: {json_dir}")
        logger.info(f"  保留天数: {retention_days}")

    def _init_db(self) -> None:
        """初始化数据库表结构"""
        with self._lock:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            # 监控快照表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS monitoring_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    snapshot_data TEXT NOT NULL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # 仓位历史表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS position_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT NOT NULL,
                    side TEXT NOT NULL,
                    entry_price REAL,
                    exit_price REAL,
                    quantity REAL,
                    leverage INTEGER,
                    pnl REAL,
                    open_time TEXT,
                    close_time TEXT,
                    close_reason TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # 交易统计表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS trading_stats (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    date TEXT NOT NULL,
                    total_trades INTEGER,
                    win_rate REAL,
                    avg_pnl REAL,
                    total_pnl REAL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # 系统健康历史表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS system_health_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    cpu_percent REAL,
                    memory_percent REAL,
                    disk_percent REAL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # AI 决策日志表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS ai_decisions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    symbol TEXT,
                    request_data TEXT,
                    response_data TEXT,
                    decision TEXT,
                    executed BOOLEAN,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # 创建索引
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_snapshots_timestamp
                ON monitoring_snapshots(timestamp)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_position_symbol
                ON position_history(symbol)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_position_open_time
                ON position_history(open_time)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_ai_decisions_timestamp
                ON ai_decisions(timestamp)
            """)

            conn.commit()
            conn.close()

    def save_metrics(self, metrics: Dict[str, Any]) -> bool:
        """
        保存监控指标

        Args:
            metrics: 监控指标字典

        Returns:
            是否保存成功
        """
        try:
            with self._lock:
                timestamp = datetime.now(timezone.utc).isoformat()

                # 保存到 SQLite
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()

                cursor.execute(
                    """INSERT INTO monitoring_snapshots (timestamp, snapshot_data)
                       VALUES (?, ?)""",
                    (timestamp, json.dumps(metrics))
                )

                conn.commit()
                conn.close()

                # 同时保存到 JSON（可选，用于快速查看）
                self._save_json_snapshot(timestamp, metrics)

                logger.debug(f"已保存监控指标: {timestamp}")
                return True

        except Exception as e:
            logger.error(f"保存监控指标失败: {e}")
            return False

    def _save_json_snapshot(self, timestamp: str, data: Dict[str, Any]) -> None:
        """保存 JSON 快照"""
        try:
            # 按日期组织文件
            date_str = timestamp[:10]  # YYYY-MM-DD
            filename = f"{self.json_dir}/{date_str}.jsonl"

            with open(filename, 'a', encoding='utf-8') as f:
                f.write(json.dumps({
                    'timestamp': timestamp,
                    'data': data,
                }, ensure_ascii=False) + '\n')

        except Exception as e:
            logger.warning(f"保存 JSON 快照失败: {e}")

    def save_position_history(
        self,
        symbol: str,
        side: str,
        entry_price: float,
        quantity: float,
        leverage: int,
        open_time: str,
    ) -> Optional[int]:
        """
        保存开仓记录

        Args:
            symbol: 交易对
            side: 方向
            entry_price: 入场价
            quantity: 数量
            leverage: 杠杆
            open_time: 开仓时间

        Returns:
            记录ID
        """
        try:
            with self._lock:
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()

                cursor.execute(
                    """INSERT INTO position_history
                       (symbol, side, entry_price, quantity, leverage, open_time)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (symbol, side, entry_price, quantity, leverage, open_time)
                )

                record_id = cursor.lastrowid
                conn.commit()
                conn.close()

                logger.info(f"已保存开仓记录: {symbol} {side}")
                return record_id

        except Exception as e:
            logger.error(f"保存开仓记录失败: {e}")
            return None

    def update_position_close(
        self,
        symbol: str,
        exit_price: float,
        pnl: float,
        close_time: str,
        close_reason: str,
    ) -> bool:
        """
        更新平仓记录

        Args:
            symbol: 交易对
            exit_price: 出场价
            pnl: 盈亏
            close_time: 平仓时间
            close_reason: 平仓原因

        Returns:
            是否更新成功
        """
        try:
            with self._lock:
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()

                cursor.execute(
                    """UPDATE position_history
                       SET exit_price = ?, pnl = ?, close_time = ?, close_reason = ?
                       WHERE symbol = ? AND close_time IS NULL
                       ORDER BY open_time DESC LIMIT 1""",
                    (exit_price, pnl, close_time, close_reason, symbol)
                )

                conn.commit()
                affected = cursor.rowcount
                conn.close()

                if affected > 0:
                    logger.info(f"已更新平仓记录: {symbol} PnL: {pnl:.2f}")
                    return True
                else:
                    logger.warning(f"未找到待平仓记录: {symbol}")
                    return False

        except Exception as e:
            logger.error(f"更新平仓记录失败: {e}")
            return False

    def save_trading_stats(self, stats: Dict[str, Any]) -> bool:
        """
        保存交易统计

        Args:
            stats: 交易统计数据

        Returns:
            是否保存成功
        """
        try:
            with self._lock:
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()

                date_str = datetime.now(timezone.utc).strftime('%Y-%m-%d')

                cursor.execute(
                    """INSERT INTO trading_stats
                       (date, total_trades, win_rate, avg_pnl, total_pnl)
                       VALUES (?, ?, ?, ?, ?)""",
                    (
                        date_str,
                        stats.get('total_trades', 0),
                        stats.get('win_rate', 0.0),
                        stats.get('avg_pnl', 0.0),
                        stats.get('total_pnl', 0.0),
                    )
                )

                conn.commit()
                conn.close()

                logger.info(f"已保存交易统计: {date_str}")
                return True

        except Exception as e:
            logger.error(f"保存交易统计失败: {e}")
            return False

    def save_system_health(self, health_data: Dict[str, Any]) -> bool:
        """
        保存系统健康数据

        Args:
            health_data: 系统健康数据

        Returns:
            是否保存成功
        """
        try:
            with self._lock:
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()

                timestamp = datetime.now(timezone.utc).isoformat()

                cursor.execute(
                    """INSERT INTO system_health_history
                       (timestamp, cpu_percent, memory_percent, disk_percent)
                       VALUES (?, ?, ?, ?)""",
                    (
                        timestamp,
                        health_data.get('cpu_percent'),
                        health_data.get('memory_percent'),
                        health_data.get('disk_percent'),
                    )
                )

                conn.commit()
                conn.close()

                return True

        except Exception as e:
            logger.error(f"保存系统健康数据失败: {e}")
            return False

    def get_snapshots(
        self,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """
        获取监控快照

        Args:
            start_time: 开始时间 (ISO格式)
            end_time: 结束时间 (ISO格式)
            limit: 返回数量限制

        Returns:
            快照列表
        """
        try:
            with self._lock:
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()

                query = "SELECT timestamp, snapshot_data FROM monitoring_snapshots"
                params = []

                if start_time:
                    query += " WHERE timestamp >= ?"
                    params.append(start_time)

                if end_time:
                    if start_time:
                        query += " AND timestamp <= ?"
                    else:
                        query += " WHERE timestamp <= ?"
                    params.append(end_time)

                query += " ORDER BY timestamp DESC LIMIT ?"
                params.append(limit)

                cursor.execute(query, params)
                rows = cursor.fetchall()
                conn.close()

                return [
                    {
                        'timestamp': row[0],
                        'data': json.loads(row[1]),
                    }
                    for row in rows
                ]

        except Exception as e:
            logger.error(f"获取监控快照失败: {e}")
            return []

    def get_position_history(
        self,
        symbol: Optional[str] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """
        获取仓位历史

        Args:
            symbol: 交易对过滤
            start_time: 开始时间
            end_time: 结束时间
            limit: 返回数量限制

        Returns:
            仓位历史列表
        """
        try:
            with self._lock:
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()

                query = "SELECT * FROM position_history WHERE 1=1"
                params = []

                if symbol:
                    query += " AND symbol = ?"
                    params.append(symbol)

                if start_time:
                    query += " AND open_time >= ?"
                    params.append(start_time)

                if end_time:
                    query += " AND open_time <= ?"
                    params.append(end_time)

                query += " ORDER BY open_time DESC LIMIT ?"
                params.append(limit)

                cursor.execute(query, params)
                rows = cursor.fetchall()
                conn.close()

                # 获取列名
                cursor = conn.cursor()
                cursor.execute("PRAGMA table_info(position_history)")
                columns = [col[1] for col in cursor.fetchall()]

                return [dict(zip(columns, row)) for row in rows]

        except Exception as e:
            logger.error(f"获取仓位历史失败: {e}")
            return []

    def get_trading_stats_summary(
        self,
        days: int = 30,
    ) -> Dict[str, Any]:
        """
        获取交易统计摘要

        Args:
            days: 统计天数

        Returns:
            统计摘要
        """
        try:
            with self._lock:
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()

                cursor.execute(
                    """SELECT
                           COUNT(*) as total_trades,
                           SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) as wins,
                           AVG(pnl) as avg_pnl,
                           SUM(pnl) as total_pnl
                       FROM position_history
                       WHERE close_time >= datetime('now', '-{} days')""".format(days)
                )

                row = cursor.fetchone()
                conn.close()

                if row and row[0]:
                    total_trades = row[0]
                    wins = row[1] or 0

                    return {
                        'total_trades': total_trades,
                        'wins': wins,
                        'losses': total_trades - wins,
                        'win_rate': wins / total_trades if total_trades > 0 else 0,
                        'avg_pnl': row[2] or 0,
                        'total_pnl': row[3] or 0,
                        'days': days,
                    }

                return {
                    'total_trades': 0,
                    'wins': 0,
                    'losses': 0,
                    'win_rate': 0,
                    'avg_pnl': 0,
                    'total_pnl': 0,
                    'days': days,
                }

        except Exception as e:
            logger.error(f"获取交易统计摘要失败: {e}")
            return {}

    def cleanup_old_data(self) -> int:
        """
        清理过期数据

        Returns:
            删除的记录数
        """
        try:
            with self._lock:
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()

                # 清理监控快照
                cursor.execute(
                    """DELETE FROM monitoring_snapshots
                       WHERE timestamp < datetime('now', '-{} days')""".format(
                        self.retention_days
                    )
                )
                snapshots_deleted = cursor.rowcount

                # 清理系统健康历史
                cursor.execute(
                    """DELETE FROM system_health_history
                       WHERE timestamp < datetime('now', '-{} days')""".format(
                        self.retention_days
                    )
                )
                health_deleted = cursor.rowcount

                conn.commit()
                conn.close()

                total_deleted = snapshots_deleted + health_deleted
                logger.info(f"已清理 {total_deleted} 条过期记录")

                return total_deleted

        except Exception as e:
            logger.error(f"清理过期数据失败: {e}")
            return 0


# 便捷函数
def get_monitoring_store(
    db_path: str = 'data/monitoring.db',
) -> MonitoringDataStore:
    """
    获取监控数据存储实例（单例）

    Args:
        db_path: 数据库路径

    Returns:
        MonitoringDataStore 实例
    """
    global _monitoring_store

    if not hasattr(get_monitoring_store, '_instance'):
        get_monitoring_store._instance = MonitoringDataStore(db_path=db_path)

    return get_monitoring_store._instance


# 全局实例
_monitoring_store: Optional[MonitoringDataStore] = None


if __name__ == '__main__':
    """测试监控数据存储"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # 创建存储实例
    store = MonitoringDataStore()

    # 测试保存监控指标
    test_metrics = {
        'positions': [
            {
                'symbol': 'BTCUSDT',
                'side': 'LONG',
                'entry_price': 50000,
                'current_price': 51000,
                'pnl': 100,
                'roe': 0.02,
            }
        ],
        'trading_stats': {
            'total_trades': 10,
            'win_rate': 0.6,
            'total_pnl': 500,
        },
        'system_health': {
            'cpu_percent': 25.5,
            'memory_percent': 60.0,
            'disk_percent': 45.0,
        },
    }

    print("\n测试1: 保存监控指标")
    result = store.save_metrics(test_metrics)
    print(f"保存结果: {result}")

    # 测试保存仓位
    print("\n测试2: 保存仓位开仓记录")
    record_id = store.save_position_history(
        symbol='BTCUSDT',
        side='LONG',
        entry_price=50000,
        quantity=0.01,
        leverage=20,
        open_time=datetime.now(timezone.utc).isoformat(),
    )
    print(f"记录ID: {record_id}")

    # 测试更新平仓记录
    print("\n测试3: 更新平仓记录")
    result = store.update_position_close(
        symbol='BTCUSDT',
        exit_price=51000,
        pnl=100,
        close_time=datetime.now(timezone.utc).isoformat(),
        close_reason='TAKE_PROFIT',
    )
    print(f"更新结果: {result}")

    # 测试获取统计摘要
    print("\n测试4: 获取交易统计摘要")
    summary = store.get_trading_stats_summary(days=30)
    print(f"统计摘要: {summary}")
