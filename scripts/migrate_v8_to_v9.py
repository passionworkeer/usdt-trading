#!/usr/bin/env python3
"""
数据库迁移脚本: v8.0 -> v9.0

功能：
1. 添加证据链字段 (evidence_count, evidence_chain, veto_flag)
2. 添加价格字段 (entry_price, stop_loss, take_profit, position_size)
3. 保持向后兼容，现有数据自动初始化为默认值

使用方法：
    python scripts/migrate_v8_to_v9.py
"""
import asyncio
import logging
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

import aiosqlite
from datetime import datetime

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class MigrationV8ToV9:
    """数据库迁移器 v8.0 -> v9.0"""

    def __init__(self, db_path: str = "data/trading.db"):
        self.db_path = Path(db_path)
        self.backup_path = self.db_path.with_suffix(f'.{datetime.now().strftime("%Y%m%d_%H%M%S")}.bak')

    async def check_column_exists(self, db: aiosqlite.Connection, table: str, column: str) -> bool:
        """检查列是否存在"""
        cursor = await db.execute(
            f"PRAGMA table_info({table})"
        )
        columns = await cursor.fetchall()
        return any(col[1] == column for col in columns)

    async def backup_database(self) -> bool:
        """备份数据库"""
        try:
            import shutil
            logger.info(f"备份数据库到: {self.backup_path}")
            shutil.copy2(self.db_path, self.backup_path)
            logger.info("备份完成")
            return True
        except Exception as e:
            logger.error(f"备份失败: {e}")
            return False

    async def migrate(self) -> bool:
        """执行迁移"""
        if not self.db_path.exists():
            logger.error(f"数据库文件不存在: {self.db_path}")
            return False

        # 1. 备份数据库
        if not await self.backup_database():
            return False

        try:
            async with aiosqlite.connect(self.db_path) as db:
                # 启用外键约束
                await db.execute("PRAGMA foreign_keys = ON")

                # 2. 检查并添加新列
                new_columns = {
                    'evidence_count': 'INTEGER DEFAULT 0',
                    'evidence_chain': 'TEXT',
                    'veto_flag': 'BOOLEAN DEFAULT 0',
                    'entry_price': 'REAL',
                    'stop_loss': 'REAL',
                    'take_profit': 'REAL',
                    'position_size': 'REAL',
                }

                for column, definition in new_columns.items():
                    if not await self.check_column_exists(db, 'trades', column):
                        logger.info(f"添加列: {column}")
                        await db.execute(
                            f"ALTER TABLE trades ADD COLUMN {column} {definition}"
                        )
                    else:
                        logger.info(f"列已存在，跳过: {column}")

                # 3. 为现有数据设置默认值
                logger.info("更新现有数据的默认值...")
                await db.execute("""
                    UPDATE trades
                    SET
                        evidence_count = COALESCE(evidence_count, 0),
                        veto_flag = COALESCE(veto_flag, 0),
                        entry_price = COALESCE(entry_price, 0.0),
                        stop_loss = COALESCE(stop_loss, 0.0),
                        take_profit = COALESCE(take_profit, 0.0),
                        position_size = COALESCE(position_size, 0.0)
                    WHERE evidence_count IS NULL
                       OR veto_flag IS NULL
                       OR entry_price IS NULL
                """)

                # 4. 验证迁移
                cursor = await db.execute("SELECT COUNT(*) FROM trades")
                total_trades = (await cursor.fetchone())[0]
                logger.info(f"交易记录总数: {total_trades}")

                # 5. 创建版本表（如果不存在）
                await db.execute("""
                    CREATE TABLE IF NOT EXISTS db_version (
                        version TEXT PRIMARY KEY,
                        applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        description TEXT
                    )
                """)

                # 6. 记录迁移版本
                await db.execute("""
                    INSERT OR REPLACE INTO db_version (version, description)
                    VALUES ('9.0', '添加证据链风控字段')
                """)

                await db.commit()
                logger.info("迁移完成!")

                return True

        except Exception as e:
            logger.error(f"迁移失败: {e}")
            logger.info(f"备份文件位于: {self.backup_path}")
            return False

    async def verify(self) -> bool:
        """验证迁移结果"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                # 检查列是否存在
                required_columns = [
                    'evidence_count', 'evidence_chain', 'veto_flag',
                    'entry_price', 'stop_loss', 'take_profit', 'position_size'
                ]

                missing_columns = []
                for column in required_columns:
                    if not await self.check_column_exists(db, 'trades', column):
                        missing_columns.append(column)

                if missing_columns:
                    logger.error(f"缺少列: {missing_columns}")
                    return False

                # 检查版本
                cursor = await db.execute(
                    "SELECT version, applied_at FROM db_version WHERE version = '9.0'"
                )
                version_info = await cursor.fetchone()

                if not version_info:
                    logger.warning("版本记录未找到")
                else:
                    logger.info(f"数据库版本: {version_info[0]}, 迁移时间: {version_info[1]}")

                logger.info("验证通过!")
                return True

        except Exception as e:
            logger.error(f"验证失败: {e}")
            return False


async def main():
    """主函数"""
    db_path = "data/trading.db"

    # 允许通过命令行参数指定数据库路径
    if len(sys.argv) > 1:
        db_path = sys.argv[1]

    logger.info(f"开始迁移: {db_path}")
    logger.info("=" * 60)

    migrator = MigrationV8ToV9(db_path)

    # 执行迁移
    success = await migrator.migrate()

    if success:
        # 验证迁移
        await migrator.verify()
        logger.info("=" * 60)
        logger.info("迁移成功完成!")
        return 0
    else:
        logger.error("=" * 60)
        logger.error("迁移失败!")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
