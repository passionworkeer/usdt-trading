# 安全审计报告

**审计日期**: 2026-02-26
**审计范围**: MCP AI 交易系统 v9.0 代码变更
**审计文件**:
- src/storage/database.py
- src/risk/evidence_controller.py
- src/ai/provider/base.py
- src/ai/provider/claude.py
- src/ai/provider/openclaw.py
- src/ai/strategy/selector.py

---

## 执行摘要

### 发现漏洞统计
- **Critical (致命)**: 0
- **High (高危)**: 2
- **Medium (中危)**: 4
- **Low (低危)**: 3

### 总体评估
代码整体安全意识较强，未发现致命漏洞。主要问题集中在**输入验证不充分**和**错误信息泄露风险**。建议优先修复高危和中危问题。

---

## 详细漏洞清单

### 🔴 High Severity (高危)

#### 1. SQL 注入风险 - database.py:348-374
**位置**: `TradingDatabase.get_statistics()`
**严重程度**: High
**CVSS**: 7.5 (AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:N/A:N)

**漏洞描述**:
```python
# Line 348 - 使用 f-string 直接拼接 SQL
conditions = [f"created_at >= datetime('now', '-{days} days')"]
```

虽然 `days` 参数通过类型系统保证为 int，但如果攻击者能控制输入，仍存在风险。

**攻击场景**:
- 如果 `days` 参数来源不可信（如 API 请求、配置文件），可能导致 SQL 注入
- 示例攻击: `days = "1 days') OR 1=1--"`

**修复建议**:
```python
# 使用参数化查询
conditions = ["created_at >= datetime('now', '-' || ? || ' days')"]
params.append(days)
```

**影响**:
- 数据泄露：攻击者可能读取敏感交易数据
- 数据篡改：可能修改统计结果

---

#### 2. API 密钥泄露风险 - claude.py:52, openclaw.py:75
**位置**: `ClaudeProvider.__init__()`, `OpenClawProvider.__init__()`
**严重程度**: High
**CVSS**: 6.5 (AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:N/A:N)

**漏洞描述**:
```python
# claude.py:52
self._api_key = self._config.get("api_key") or os.environ.get("ANTHROPIC_API_KEY")

# openclaw.py:75
self.api_key = api_key
```

API 密钥以明文形式存储在实例变量中，可能通过以下途径泄露：
1. 日志输出（如果代码后续打印对象）
2. 调试器/内存转储
3. 异常堆栈信息

**修复建议**:
```python
# 使用环境变量优先，避免在配置中硬编码
self._api_key = os.environ.get("ANTHROPIC_API_KEY")
if not self._api_key:
    raise ValueError("ANTHROPIC_API_KEY environment variable must be set")

# 或使用密钥管理服务
self._api_key = get_secret_from_vault("anthropic_api_key")
```

**额外建议**:
- 在 `__repr__` 方法中屏蔽密钥
- 添加日志脱敏机制

---

### 🟡 Medium Severity (中危)

#### 3. JSON 注入风险 - openclaw.py:160, database.py:229
**位置**: 多处 JSON 解析
**严重程度**: Medium
**CVSS**: 5.3 (AV:N/AC:L/PR:N/UI:N/S:U/C:L/I:N/A:N)

**漏洞描述**:
```python
# openclaw.py:160 - 无验证的 JSON 解析
response_data = await response.json()

# database.py:229 - 直接序列化用户输入
json.dumps(trade.evidence_chain) if trade.evidence_chain else None
```

**攻击场景**:
- 恶意 API 返回超大型 JSON 导致内存耗尽
- 循环引用导致序列化异常
- 特殊字符导致数据库注入

**修复建议**:
```python
# 1. 限制 JSON 大小
MAX_JSON_SIZE = 10 * 1024 * 1024  # 10MB
if len(response_text) > MAX_JSON_SIZE:
    raise ValueError("Response too large")

# 2. 验证 JSON 结构
try:
    data = await response.json()
    if not isinstance(data, dict):
        raise ValueError("Invalid JSON structure")
except json.JSONDecodeError as e:
    raise OpenClawAPIError(f"Invalid JSON response") from e

# 3. 序列化前验证
if not isinstance(trade.evidence_chain, list):
    raise ValueError("evidence_chain must be a list")
```

---

#### 4. 类型转换异常 - evidence_controller.py:250, claude.py:367
**位置**: 多处 `float()` 转换
**严重程度**: Medium
**CVSS**: 5.0 (AV:N/AC:L/PR:N/UI:N/S:U/C:N/I:N/A:L)

**漏洞描述**:
```python
# evidence_controller.py:250 - 无验证的类型转换
entry_price = float(data.get("entry_price", current_price or data.get("current_price", 0)))
```

**攻击场景**:
- API 返回 `None` 或非数字值导致 `TypeError`
- `float("inf")` 或 `float("NaN")` 导致后续计算异常
- 极大数值导致浮点溢出

**修复建议**:
```python
def safe_float(value, default=0.0, min_val=None, max_val=None) -> float:
    """安全的浮点转换"""
    if value is None:
        return default

    try:
        result = float(value)
    except (TypeError, ValueError):
        return default

    # 检查特殊值
    if not math.isfinite(result):
        return default

    # 范围限制
    if min_val is not None and result < min_val:
        return min_val
    if max_val is not None and result > max_val:
        return max_val

    return result

# 使用
entry_price = safe_float(data.get("entry_price"), default=current_price)
```

---

#### 5. 错误信息泄露 - database.py:526-527, claude.py:114-115
**位置**: 多处异常处理
**严重程度**: Medium
**CVSS**: 5.0 (AV:N/AC:L/PR:N/UI:N/S:U/C:L/I:N/A:N)

**漏洞描述**:
```python
# database.py:526-527 - 直接输出异常信息
except json.JSONDecodeError:
    pass  # 静默失败

# claude.py:114-115 - 泄露 API 错误详情
except anthropic.APIError as e:
    logger.error(f"Claude API 错误: {e}")
    raise RuntimeError(f"Claude API 调用失败: {str(e)}")
```

**风险**:
- 异常信息可能包含敏感数据（API 密钥、内部路径）
- 用户可以通过错误信息推断系统架构
- 日志未脱敏可能被未授权访问

**修复建议**:
```python
# 1. 自定义错误消息
class APIError(Exception):
    def __init__(self, message: str, internal_details: str = None):
        super().__init__(message)
        self._internal_details = internal_details

# 2. 日志脱敏
def sanitize_for_log(error: Exception) -> str:
    """移除敏感信息的错误消息"""
    msg = str(error)
    # 移除 API 密钥模式
    msg = re.sub(r'sk-ant-[a-zA-Z0-9\-_]+', '[REDACTED]', msg)
    # 移除路径
    msg = re.sub(r'/[a-zA-Z0-9_/\\]+', '[PATH]', msg)
    return msg

# 3. 分层错误处理
except anthropic.APIError as e:
    logger.error(f"API error: {sanitize_for_log(e)}")
    raise RuntimeError("External service unavailable") from None
```

---

#### 6. 资源泄漏风险 - openclaw.py:349-360
**位置**: `OpenClawProvider.__del__`
**严重程度**: Medium
**CVSS**: 4.7 (AV:N/AC:L/PR:N/UI:N/S:U/C:N/I:N/A:L)

**漏洞描述**:
```python
def __del__(self):
    if self._session and not self._session.closed:
        try:
            loop = asyncio.get_event_loop()
            # 在析构函数中创建异步任务可能失败
            loop.create_task(self._session.close())
        except Exception:
            pass  # 吞掉异常
```

**问题**:
1. 析构函数中运行异步代码不可靠
2. 异常被静默吞掉，隐藏问题
3. 可能导致 aiohttp session 未正确关闭

**修复建议**:
```python
async def close(self) -> None:
    """显式关闭方法"""
    if self._session and not self._session.closed:
        await self._session.close()
        self._session = None

def __del__(self):
    # 仅记录警告，不尝试清理
    if self._session and not self._session.closed:
        import warnings
        warnings.warn(
            f"OpenClawProvider session not properly closed. "
            f"Use async with or call await close() explicitly.",
            ResourceWarning
        )
```

---

### 🟢 Low Severity (低危)

#### 7. 缺少输入长度验证 - evidence_controller.py:226-231
**位置**: `EvidenceBasedRiskController.build_prompt_for_ai()`
**严重程度**: Low
**CVSS**: 3.5 (AV:N/AC:L/PR:N/UI:N/S:U/C:N/I:N/A:L)

**漏洞描述**:
```python
for i, evidence in enumerate(decision.evidence_chain, 1):
    lines.append(f"    {i}. {evidence}")
```

未限制 evidence_chain 长度，攻击者可能：
- 提供超长证据导致内存溢出
- 构造恶意提示词注入 AI 指令

**修复建议**:
```python
MAX_EVIDENCE_LENGTH = 1000
for i, evidence in enumerate(decision.evidence_chain[:50], 1):  # 限制数量
    truncated = evidence[:MAX_EVIDENCE_LENGTH]  # 限制长度
    lines.append(f"    {i}. {truncated}")
```

---

#### 8. 时间戳伪造 - base.py:58, evidence_controller.py:48
**位置**: 多处 `datetime.now()`
**严重程度**: Low
**CVSS**: 3.1 (AV:N/AC:H/PR:N/UI:N/S:U/C:N/I:N/A:L)

**漏洞描述**:
```python
timestamp: datetime = field(default_factory=datetime.now)
```

**问题**:
- 时间戳由客户端生成，可被伪造
- 无法保证数据的时间顺序
- 审计日志不可信

**修复建议**:
```python
# 在数据库层设置时间戳
# database.py 已正确处理
created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP

# 在应用层验证时间戳合理性
def validate_timestamp(ts: datetime) -> bool:
    max_future = datetime.now() + timedelta(minutes=5)
    max_past = datetime.now() - timedelta(days=365)
    return max_past <= ts <= max_future
```

---

#### 9. 并发竞态条件 - database.py:108, selector.py:166-171
**位置**: 异步代码中的竞态
**严重程度**: Low
**CVSS**: 3.0 (AV:N/AC:H/PR:N/UI:N/S:U/C:N/I:N/A:N)

**漏洞描述**:
```python
# database.py:108 - Lock 范围不足
self._lock = asyncio.Lock()

async def initialize(self) -> None:
    if self._initialized:  # 非原子检查
        return
    async with self._lock:  # 可能重复初始化
```

**修复建议**:
```python
async def initialize(self) -> None:
    async with self._lock:  # 先获取锁
        if self._initialized:
            return
        # 初始化逻辑
```

---

## 通过的安全检查 ✅

### 1. SQL 注入防护 (部分通过)
- ✅ 大部分查询使用参数化 (database.py:217-237)
- ✅ f-string 使用在安全上下文 (database.py:310-320)
- ⚠️ 例外：Line 348 需修复

### 2. 认证和授权
- ✅ API 密钥通过环境变量获取 (claude.py:52)
- ✅ 无硬编码密钥
- ✅ Bearer Token 认证 (openclaw.py:107)

### 3. 密码和敏感数据
- ✅ 无密码存储
- ✅ 使用环境变量管理密钥

### 4. 异步操作安全
- ✅ 正确使用 aiosqlite
- ✅ 异步上下文管理器实现正确

### 5. 类型安全
- ✅ 使用 dataclass 进行数据验证
- ✅ `__post_init__` 验证数据一致性

---

## 优先修复建议

### 立即修复 (P0)
1. **SQL 注入风险** - database.py:348
2. **API 密钥泄露** - claude.py:52, openclaw.py:75

### 尽快修复 (P1)
3. JSON 注入防护
4. 类型转换安全化
5. 错误信息脱敏

### 后续改进 (P2)
6. 资源泄漏修复
7. 输入长度限制
8. 时间戳验证
9. 并发竞态修复

---

## 安全增强建议

### 1. 添加安全头和验证
```python
# database.py - 添加数据完整性检查
CHECK(evidence_count >= 0)
CHECK(position_size >= 0)
CHECK(entry_price > 0)
```

### 2. 实施日志脱敏
```python
class RedactingFormatter(logging.Formatter):
    """自动脱敏敏感信息的日志格式化器"""
    SENSITIVE_PATTERNS = [
        (r'sk-ant-[a-zA-Z0-9\-_]+', '[API_KEY]'),
        (r'Bearer\s+[a-zA-Z0-9\-_\.]+', '[TOKEN]'),
    ]
```

### 3. 添加速率限制
```python
# openclaw.py - 防止 API 滥用
from asyncio import Semaphore
self._rate_limiter = Semaphore(max_concurrent_requests)
```

### 4. 实施输入验证框架
```python
from pydantic import BaseModel, validator

class EvidenceBaseDecision(BaseModel):
    action: str
    evidence_count: int
    evidence_chain: List[str]

    @validator('evidence_chain')
    def validate_evidence_chain(cls, v):
        if len(v) > 50:
            raise ValueError('Too many evidence items')
        if any(len(e) > 1000 for e in v):
            raise ValueError('Evidence too long')
        return v
```

---

## 测试建议

### 1. 安全测试用例
```python
def test_sql_injection_attempts():
    """测试 SQL 注入防护"""
    malicious_inputs = [
        "1' OR '1'='1",
        "1; DROP TABLE trades--",
        "1' UNION SELECT * FROM trades--",
    ]
    for input in malicious_inputs:
        with pytest.raises(ValueError):
            db.get_statistics(days=input)

def test_api_key_not_logged():
    """确保 API 密钥不出现在日志中"""
    provider = ClaudeProvider()
    # 触发各种日志场景
    # 验证日志中不包含密钥
```

### 2. 模糊测试
```python
async def test_malformed_json():
    """测试恶意 JSON 处理"""
    malicious_jsons = [
        '{"a":' + 'x' * 1000000 + '}',  # 超大 JSON
        '{"recursive": {"recursive": null}}',  # 循环引用
        '{"evidence": "\ud800"}',  # 无效 Unicode
    ]
```

---

## 合规性检查

### OWASP Top 10 (2021)
- ✅ A01:2021 – Broken Access Control: 通过
- ✅ A02:2021 – Cryptographic Failures: 通过
- ⚠️ A03:2021 – Injection: 需修复 SQL 注入
- ✅ A04:2021 – Insecure Design: 通过
- ⚠️ A05:2021 – Security Misconfiguration: 错误信息泄露
- ⚠️ A06:2021 – Vulnerable Components: 建议更新依赖版本
- ✅ A07:2021 – Authentication Failures: 通过
- ⚠️ A08:2021 – Software and Data Integrity: 缺少输入验证
- ✅ A09:2021 – Security Logging: 通过（需脱敏）
- ✅ A10:2021 – Server-Side Request Forgery: 不适用

---

## 结论

本次审计发现 **2 个高危**、**4 个中危**、**3 个低危** 漏洞。代码整体质量较好，安全意识较强，主要问题集中在输入验证和错误处理细节。

**建议优先级**:
1. 立即修复 SQL 注入和 API 密钥泄露问题
2. 在一周内完成中危问题修复
3. 在下一个迭代中处理低危问题和增强建议

**持续改进建议**:
- 集成静态安全分析工具（如 Bandit、Safety）
- 定期进行安全审计
- 实施安全编码规范
- 添加自动化安全测试

---

**审计人员**: Security Agent
**审计时间**: 2026-02-26
**下次审计建议**: 2026-03-26（一个月后）
