# v9.2 后续详细实施计划

## 📋 概述

本计划基于 v9.1 修复的成果，继续完善系统安全性、功能完整性和测试覆盖率，最终达到 v9.2 稳定版本。

---

## 🎯 目标

1. **测试通过率**: 78% → 95%
2. **安全评分**: 解决所有 P0/P1 安全问题
3. **代码质量**: 解决所有高优先级代码审查问题
4. **功能完整**: 所有核心功能通过集成测试

---

## 📅 详细实施计划

### Phase 1: 紧急修复 (Week 1, Day 1-2)

#### 1.1 修复 ActionType 枚举不一致

**问题**: `base.py` 使用 BUY/SELL/HOLD，而 `evidence_controller.py` 使用 LONG/SHORT/CLOSE/HOLD

**影响**: 类型不匹配会导致运行时错误

**修复方案**:
```python
# src/risk/evidence_controller.py
# 统一使用 base.py 中的 ActionType 定义

# 映射关系:
# LONG -> BUY
# SHORT -> SELL
# CLOSE -> 根据当前持仓方向决定 BUY/SELL
# HOLD -> HOLD

# 在证据链风控中添加方向转换逻辑
def _normalize_action(self, action: str, current_position: Optional[str] = None) -> str:
    """将 LONG/SHORT/CLOSE 标准化为 BUY/SELL/HOLD"""
    action_map = {
        "long": "buy",
        "short": "sell",
        "buy": "buy",
        "sell": "sell",
        "hold": "hold",
    }

    normalized = action_map.get(action.lower(), "hold")

    # 处理 CLOSE 情况
    if action.lower() == "close" and current_position:
        # 平多 = 卖出，平空 = 买入
        position_map = {"long": "sell", "short": "buy"}
        normalized = position_map.get(current_position.lower(), "hold")

    return normalized
```

**工作量**: 2小时
**测试**: 更新相关测试用例

---

#### 1.2 修复价格字段空值检查

**问题**: `entry_price = 0` 会导致所有衍生价格为 0

**当前代码**:
```python
if decision.entry_price <= 0 or stop_loss <= 0:
    return False, "价格必须为正数"
```

**修复后**:
```python
# 检查价格是否为零（可能是未初始化）
if decision.entry_price == 0:
    return False, "入场价格不能为零，请检查数据初始化"

if decision.stop_loss == 0:
    return False, "止损价格不能为零"

if decision.take_profit == 0:
    return False, "止盈价格不能为零"

# 检查负数
if decision.entry_price < 0:
    return False, "入场价格不能为负数"

if decision.stop_loss < 0:
    return False, "止损价格不能为负数"

# 检查价格合理性
if decision.stop_loss >= decision.entry_price:
    return False, "止损价格必须低于入场价格（做多）"

if decision.take_profit <= decision.entry_price:
    return False, "止盈价格必须高于入场价格（做多）"
```

**工作量**: 1小时
**测试**: 更新相关测试用例

---

### Phase 2: 数据库和迁移 (Week 1, Day 3)

#### 2.1 完善数据库迁移脚本

**文件**: `scripts/migrate_v8_to_v9.py`

**完整实现**:
```python
#!/usr/bin/env python3
"""
v8.0 到 v9.0 数据库迁移脚本

迁移内容:
1. trades 表新增证据链字段
2. 添加新索引
3. 数据迁移（如果有）
"""

import asyncio
import aiosqlite
import logging
from pathlib import Path
from typing import Optional

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class DatabaseMigrator:
    """数据库迁移器"""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._lock = asyncio.Lock()

    async def get_current_version(self) -> int:
        """获取当前数据库版本"""
        async with aiosqlite.connect(self.db_path) as db:
            try:
                cursor = await db.execute(
                    "SELECT version FROM schema_version ORDER BY id DESC LIMIT 1"
                )
                row = await cursor.fetchone()
                return row[0] if row else 0
            except aiosqlite.OperationalError:
                # 表不存在，返回 0
                return 0

    async def migrate_to_v9(self) -> bool:
        """迁移到 v9.0"""
        async with self._lock:
            try:
                current_version = await self.get_current_version()

                if current_version >= 9:
                    logger.info(f"数据库已经是 v{current_version}，无需迁移")
                    return True

                logger.info(f"开始从 v{current_version} 迁移到 v9.0")

                async with aiosqlite.connect(self.db_path) as db:
                    # 检查 trades 表结构
                    cursor = await db.execute("PRAGMA table_info(trades)")
                    columns = {row[1] for row in await cursor.fetchall()}

                    # 需要添加的列
                    new_columns = {
                        'evidence_count': 'INTEGER DEFAULT 0',
                        'evidence_chain': 'TEXT',
                        'veto_flag': 'BOOLEAN DEFAULT 0',
                        'entry_price': 'REAL',
                        'stop_loss': 'REAL',
                        'take_profit': 'REAL',
                        'position_size': 'REAL',
                    }

                    for column, col_type in new_columns.items():
                        if column not in columns:
                            logger.info(f"添加列: {column}")
                            await db.execute(f"ALTER TABLE trades ADD COLUMN {column} {col_type}")

                    # 创建 schema_version 表（如果不存在）
                    await db.execute("""
                        CREATE TABLE IF NOT EXISTS schema_version (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            version INTEGER NOT NULL,
                            migrated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            description TEXT
                        )
                    """)

                    # 记录迁移版本
                    await db.execute(
                        "INSERT INTO schema_version (version, description) VALUES (?, ?)",
                        (9, "Migration to v9.0: Added evidence chain fields")
                    )

                    await db.commit()

                logger.info("✅ 迁移到 v9.0 完成")
                return True

            except Exception as e:
                logger.error(f"❌ 迁移失败: {e}")
                return False


async def main():
    """主函数"""
    import sys

    if len(sys.argv) < 2:
        print("Usage: python migrate_v8_to_v9.py <database_path>")
        print("Example: python migrate_v8_to_v9.py data/trading.db")
        sys.exit(1)

    db_path = sys.argv[1]

    if not Path(db_path).exists():
        print(f"❌ 数据库不存在: {db_path}")
        sys.exit(1)

    migrator = DatabaseMigrator(db_path)
    success = await migrator.migrate_to_v9()

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    asyncio.run(main())
```

**工作量**: 3小时
**测试**: 在测试数据库上验证迁移

---

### Phase 3: 测试修复 (Week 1, Day 4-5)

#### 3.1 修复 test_claude_provider.py

**主要修改点**:
1. 更新 Mock Provider 返回新 `EvidenceBasedDecision` 格式
2. 修复 `confidence` 断言 → `evidence_count`
3. 添加新字段断言 (`veto_flag`, `entry_price`, `stop_loss`, `take_profit`, `position_size`)

**工作量**: 2小时

---

#### 3.2 修复 test_openclaw_provider.py

与 claude provider 类似的修改

**工作量**: 1小时

---

#### 3.3 修复 test_strategy_pool.py

**主要修改点**:
- 修复 `StrategySelector` 的 `confidence` 检查 → `evidence_count`
- 更新测试数据以匹配新的证据链格式

**工作量**: 1小时

---

#### 3.4 修复 test_trading_engine.py

**主要修改点**:
- 更新测试以使用新的数据结构
- 适配 `EvidenceBasedDecision` 的新字段

**工作量**: 2小时

---

#### 3.5 修复 test_database.py

**主要修改点**:
- 修复统计测试中的日期过滤问题
- 更新测试数据以包含新字段（`evidence_count`, `evidence_chain` 等）

**工作量**: 1小时

---

### Phase 4: 代码质量优化 (Week 2, Day 1-2)

#### 4.1 JSON注入防护

**文件**: `src/ai/provider/claude.py`, `openclaw.py`

**实现**:
```python
# 限制响应大小
MAX_RESPONSE_SIZE = 100_000  # 100KB

response_text = response.content[0].text
if len(response_text) > MAX_RESPONSE_SIZE:
    logger.warning(f"Response too large ({len(response_text)} bytes), possible attack")
    return self._create_fallback_decision(context, "Response too large")

# 验证 JSON 结构
try:
    data = json.loads(response_text)
except json.JSONDecodeError as e:
    logger.warning(f"Invalid JSON: {e}")
    return self._create_fallback_decision(context, f"Invalid JSON: {e}")

# 验证必需字段
required_fields = ['action', 'evidence_count', 'evidence_chain', 'veto_flag']
missing = [f for f in required_fields if f not in data]
if missing:
    logger.warning(f"Missing required fields: {missing}")
    return self._create_fallback_decision(context, f"Missing fields: {missing}")
```

**工作量**: 1小时

---

#### 4.2 类型转换安全

**文件**: 所有进行 `float()` 和 `int()` 转换的文件

**实现**:
```python
# 创建安全的类型转换函数
def safe_float(value: Any, default: float = 0.0, min_val: Optional[float] = None, max_val: Optional[float] = None) -> float:
    """安全的 float 转换"""
    try:
        result = float(value)
        if min_val is not None:
            result = max(result, min_val)
        if max_val is not None:
            result = min(result, max_val)
        return result
    except (ValueError, TypeError) as e:
        logger.warning(f"Failed to convert {value} to float: {e}, using default {default}")
        return default

def safe_int(value: Any, default: int = 0, min_val: Optional[int] = None, max_val: Optional[int] = None) -> int:
    """安全的 int 转换"""
    try:
        result = int(value)
        if min_val is not None:
            result = max(result, min_val)
        if max_val is not None:
            result = min(result, max_val)
        return result
    except (ValueError, TypeError) as e:
        logger.warning(f"Failed to convert {value} to int: {e}, using default {default}")
        return default
```

**工作量**: 1.5小时

---

#### 4.3 异常处理优化

**实现**:
```python
# 定义具体的异常类型
class ValidationError(Exception):
    """数据验证错误"""
    pass

class ConfigurationError(Exception):
    """配置错误"""
    pass

class ProviderError(Exception):
    """Provider 错误"""
    pass

class RiskControlError(Exception):
    """风控错误"""
    pass

# 使用具体异常类型
try:
    price = float(data["entry_price"])
except KeyError as e:
    raise ValidationError(f"Missing required field: {e}")
except ValueError as e:
    raise ValidationError(f"Invalid price format: {e}")

# Provider 错误处理
try:
    response = await self._client.messages.create(...)
except anthropic.AuthenticationError as e:
    raise ProviderError(f"Authentication failed: {e}")
except anthropic.RateLimitError as e:
    raise ProviderError(f"Rate limit exceeded: {e}")
except anthropic.APIError as e:
    raise ProviderError(f"API error: {e}")
```

**工作量**: 2小时

---

#### 4.4 配置化硬编码值

**文件**: `config/trading_config.yaml` (已创建)

**实现配置加载器**:
```python
# src/utils/config_loader.py
import yaml
from pathlib import Path
from typing import Dict, Any, Optional

class ConfigLoader:
    """配置加载器"""

    _instance = None
    _config: Optional[Dict[str, Any]] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def load(self, config_path: Optional[str] = None) -> Dict[str, Any]:
        """加载配置文件"""
        if self._config is not None:
            return self._config

        if config_path is None:
            # 默认路径
            config_path = Path(__file__).parent.parent.parent / "config" / "trading_config.yaml"

        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                self._config = yaml.safe_load(f)
            return self._config
        except FileNotFoundError:
            raise ConfigurationError(f"Config file not found: {config_path}")
        except yaml.YAMLError as e:
            raise ConfigurationError(f"Invalid YAML format: {e}")

    def get(self, *keys: str, default: Any = None) -> Any:
        """获取配置值"""
        if self._config is None:
            self.load()

        value = self._config
        for key in keys:
            if isinstance(value, dict):
                value = value.get(key, default)
            else:
                return default
        return value


# 全局配置访问
def get_config() -> ConfigLoader:
    """获取配置加载器实例"""
    return ConfigLoader()


# 使用示例
# from src.utils.config_loader import get_config
# config = get_config()
# min_evidence = config.get("risk_control", "min_evidence_count", default=2)
```

**工作量**: 1.5小时

---

### Phase 5: 测试修复和优化 (Week 2, Day 3-5)

#### 5.1 测试修复计划

| 测试文件 | 失败数 | 预计工作量 | 修复重点 |
|---------|--------|-----------|---------|
| test_claude_provider.py | 14 | 3h | 更新 Mock 返回新格式 |
| test_openclaw_provider.py | 7 | 2h | 更新 Mock 返回新格式 |
| test_strategy_pool.py | 5 errors | 1.5h | 修复 confidence 检查 |
| test_trading_engine.py | 9 errors | 2.5h | 更新数据结构 |
| test_database.py | 4 | 1h | 修复日期过滤 |

**总计**: 10小时

**详细修复计划**:

1. **test_claude_provider.py**:
   - 更新 Mock Provider 返回 `EvidenceBasedDecision` 新格式
   - 移除 `confidence` 断言
   - 添加 `evidence_count`, `veto_flag`, `entry_price` 等字段断言

2. **test_openclaw_provider.py**:
   - 同上

3. **test_strategy_pool.py**:
   - 修复 `StrategySelector` 使用 `evidence_count` 而非 `confidence`
   - 更新测试数据

4. **test_trading_engine.py**:
   - 更新测试以使用新的数据结构
   - 适配 `EvidenceBasedDecision` 新字段

5. **test_database.py**:
   - 修复统计测试中的日期过滤问题
   - 更新测试数据以包含新字段

---

#### 5.2 集成测试

**目标**: 确保所有组件协同工作

**测试场景**:
1. 完整交易流程 (信号 → 决策 → 风控 → 执行 → 复盘)
2. Provider 故障转移
3. 并发场景下的数据一致性
4. 异常情况下的系统稳定性

**工作量**: 4小时

---

### Phase 6: 性能优化 (Week 2, Day 5)

#### 6.1 性能基准测试

**目标**: 建立性能基线

**测试指标**:
- 单次交易决策延迟 (< 100ms)
- 数据库查询性能 (< 10ms)
- 并发处理能力 (> 100 req/s)

**工作量**: 2小时

#### 6.2 优化热点

基于性能测试结果，针对性优化:
- 数据库查询优化（添加索引）
- 缓存策略优化
- 异步处理优化

**工作量**: 2-4小时

---

## 📊 时间安排总结

| Phase | 内容 | 工作量 | 负责人 |
|-------|------|--------|--------|
| 1 | P0/P1 修复 | 4天 | Agent 集群 |
| 2 | 数据库迁移 | 1天 | 已完成 |
| 3 | 测试修复 | 3天 | Agent 集群 |
| 4 | 集成测试 | 2天 | Agent 集群 |
| 5 | 性能优化 | 2天 | Agent 集群 |
| **总计** | | **14天** | |

---

## 🎯 验收标准

1. **功能验收**:
   - [ ] 所有 P0/P1 问题已修复
   - [ ] 测试通过率 ≥ 95%
   - [ ] 集成测试全部通过

2. **性能验收**:
   - [ ] 单次决策延迟 < 100ms
   - [ ] 并发处理能力 > 100 req/s

3. **安全验收**:
   - [ ] 安全审计无高危问题
   - [ ] 代码审查无高优先级问题

4. **文档验收**:
   - [ ] API 文档已更新
   - [ ] 部署文档已更新
   - [ ] 变更日志已更新

---

## 🚀 后续行动计划

### 立即执行
1. ✅ 完成 P0/P1 修复（已完成）
2. 🔄 继续测试修复（进行中）
3. 📋 准备集成测试

### 本周内完成
1. 完成所有测试修复
2. 执行集成测试
3. 性能基准测试

### 下周完成
1. 性能优化
2. 最终验收
3. v9.2 发布

---

**备注**: 本计划可根据实际进度调整。