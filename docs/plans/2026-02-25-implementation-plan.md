# MCP AI 交易系统 - 实现计划

**版本**: 1.0
**日期**: 2026-02-25
**关联设计**: [2026-02-25-mcp-ai-trading-design.md](./2026-02-25-mcp-ai-trading-design.md)

---

## 实现策略

采用 **渐进式开发**，分 5 个阶段：

1. **Phase 1**: 基础架构搭建 (2-3 小时)
2. **Phase 2**: AI Provider 接口实现 (3-4 小时)
3. **Phase 3**: 策略池与动态选择 (2-3 小时)
4. **Phase 4**: 复盘系统 (2 小时)
5. **Phase 5**: 集成测试与上线 (2-3 小时)

**预计总工时**: 11-15 小时

---

## Phase 1: 基础架构搭建

### 任务 1.1: 创建目录结构

**优先级**: P0
**预估时间**: 10 分钟

```bash
mkdir -p src/mcp
mkdir -p src/ai/provider
mkdir -p src/ai/strategy
mkdir -p src/ai/review
mkdir -p src/risk
mkdir -p data/reviews
mkdir -p config
```

**验收标准**:
- [ ] 目录结构符合设计文档

---

### 任务 1.2: 定义数据模型

**优先级**: P0
**预估时间**: 30 分钟

**文件**: `src/ai/models.py`

**内容**:
```python
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional

@dataclass
class TradingSignal:
    strategy: str
    symbol: str
    action: str  # BUY / SELL
    strength: float  # 0.0 - 1.0
    entry_price: float
    stop_loss: float
    take_profit: float
    created_at: datetime

@dataclass
class MarketContext:
    symbol: str
    timeframe: str
    klines: list
    depth: dict
    signals: List[TradingSignal]
    balance: float
    positions: list

@dataclass
class AIDecision:
    action: str  # BUY / SELL / PASS
    confidence: float  # 0.0 - 1.0
    reason: str
    strategy: str
    entry_price: float
    stop_loss: float
    take_profit: float
    position_size: float

@dataclass
class TradeResult:
    order_id: str
    symbol: str
    action: str
    qty: float
    entry_price: float
    exit_price: float
    pnl: float
    pnl_percent: float
    holding_time: int
    ai_decision: AIDecision
    created_at: datetime
    closed_at: Optional[datetime]

@dataclass
class ReviewReport:
    trade_id: str
    analysis: str
    lessons: str
    score: float  # 0-100
    recommendations: list

@dataclass
class LearningReport:
    total_trades: int
    win_rate: float
    avg_pnl: float
    by_strategy: dict
    recommendations: list
```

**验收标准**:
- [ ] 所有数据类定义完整
- [ ] 类型注解正确
- [ ] 可以正常导入

---

### 任务 1.3: 实现 AIProvider 抽象基类

**优先级**: P0
**预估时间**: 20 分钟

**文件**: `src/ai/provider/base.py`

**内容**:
```python
from abc import ABC, abstractmethod
from typing import Optional
from ..models import MarketContext, AIDecision, TradeResult, ReviewReport

class AIProvider(ABC):
    """AI 引擎抽象接口"""

    @property
    @abstractmethod
    def name(self) -> str:
        pass

    @property
    @abstractmethod
    def config(self) -> dict:
        pass

    @abstractmethod
    async def analyze(self, context: MarketContext) -> AIDecision:
        pass

    @abstractmethod
    async def review(self, trade: TradeResult) -> ReviewReport:
        pass

    @abstractmethod
    async def health_check(self) -> bool:
        pass
```

**验收标准**:
- [ ] 抽象类定义正确
- [ ] 所有方法签名符合设计

---

### 任务 1.4: 实现 Provider 管理器

**优先级**: P0
**预估时间**: 30 分钟

**文件**: `src/ai/provider/manager.py`

**内容**:
```python
from typing import Dict, List, Optional
from .base import AIProvider

class AIProviderManager:
    def __init__(self):
        self._providers: Dict[str, AIProvider] = {}
        self._active_provider: Optional[str] = None

    def register(self, provider: AIProvider):
        self._providers[provider.name] = provider

    def set_active(self, name: str):
        if name not in self._providers:
            raise ValueError(f"Unknown provider: {name}")
        self._active_provider = name

    def get_active(self) -> AIProvider:
        if not self._active_provider:
            raise ValueError("No active provider")
        return self._providers[self._active_provider]

    def list_providers(self) -> List[str]:
        return list(self._providers.keys())

    async def health_check_all(self) -> Dict[str, bool]:
        results = {}
        for name, provider in self._providers.items():
            try:
                results[name] = await provider.health_check()
            except:
                results[name] = False
        return results
```

**验收标准**:
- [ ] 可以注册多个 Provider
- [ ] 可以切换活跃 Provider
- [ ] 健康检查正常工作

---

### 任务 1.5: 创建配置文件

**优先级**: P1
**预估时间**: 15 分钟

**文件**: `config/ai_providers.yaml`

```yaml
providers:
  claude:
    enabled: true
    model: claude-sonnet-4-6
    temperature: 0.7
    max_tokens: 4096

  openclaw:
    enabled: false
    endpoint: http://localhost:8000
    timeout: 30

strategy:
  min_confidence: 0.85
  signal_lookback_periods: 100

risk:
  max_position_usdt: 20
  daily_loss_limit: 0.05
  max_slippage: 0.005
```

**验收标准**:
- [ ] YAML 格式正确
- [ ] 所有配置项完整

---

## Phase 2: AI Provider 实现

### 任务 2.1: 实现 Claude Provider

**优先级**: P0
**预估时间**: 2 小时

**文件**: `src/ai/provider/claude.py`

**关键实现点**:

1. **初始化**
```python
class ClaudeProvider(AIProvider):
    def __init__(self, api_key: str, model: str = "claude-sonnet-4-6"):
        self.api_key = api_key
        self.model = model
        self.client = anthropic.AsyncAnthropic(api_key=api_key)
```

2. **分析市场**
```python
async def analyze(self, context: MarketContext) -> AIDecision:
    prompt = self._build_prompt(context)
    response = await self.client.messages.create(
        model=self.model,
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}]
    )
    return self._parse_response(response.content[0].text)
```

3. **构建提示词**
```python
def _build_prompt(self, context: MarketContext) -> str:
    return f"""
你是一个专业的加密货币交易决策助手。

当前市场数据:
- 交易对: {context.symbol}
- 时间周期: {context.timeframe}
- K线数据: {context.klines[-50:]}  # 最近50根
- 深度数据: {context.depth}
- 可用资金: {context.balance} USDT
- 当前持仓: {context.positions}

可用信号:
{self._format_signals(context.signals)}

请分析市场并给出决策。输出 JSON 格式:
{{
  "action": "BUY/SELL/PASS",
  "confidence": 0.0-1.0,
  "reason": "决策理由",
  "strategy": "使用的策略",
  "entry_price": 价格,
  "stop_loss": 止损价,
  "take_profit": 止盈价,
  "position_size": 仓位大小(USDT)
}}
"""
```

4. **解析响应**
```python
def _parse_response(self, response_text: str) -> AIDecision:
    # 提取 JSON
    json_str = extract_json(response_text)
    data = json.loads(json_str)
    return AIDecision(**data)
```

**验收标准**:
- [ ] 可以调用 Claude API
- [ ] 提示词构建正确
- [ ] 响应解析正确
- [ ] 返回 AIDecision 对象

---

### 任务 2.2: 实现 OpenClaw Provider

**优先级**: P1
**预估时间**: 1.5 小时

**文件**: `src/ai/provider/openclaw.py`

**关键实现点**:

1. **初始化**
```python
class OpenClawProvider(AIProvider):
    def __init__(self, endpoint: str, api_key: Optional[str] = None):
        self.endpoint = endpoint
        self.api_key = api_key
        self.session = aiohttp.ClientSession()
```

2. **调用 API**
```python
async def analyze(self, context: MarketContext) -> AIDecision:
    url = f"{self.endpoint}/api/analyze"
    headers = {}
    if self.api_key:
        headers["Authorization"] = f"Bearer {self.api_key}"

    async with self.session.post(
        url,
        json=context.to_dict(),
        headers=headers
    ) as resp:
        data = await resp.json()
        return AIDecision(**data)
```

**验收标准**:
- [ ] 可以调用 OpenClaw API
- [ ] 错误处理完善
- [ ] 返回 AIDecision 对象

---

### 任务 2.3: 编写 Provider 单元测试

**优先级**: P1
**预估时间**: 1 小时

**文件**: `tests/test_providers.py`

**测试用例**:
1. Mock Claude API 测试
2. Mock OpenClaw API 测试
3. 管理器切换测试
4. 健康检查测试

**验收标准**:
- [ ] 覆盖率 > 80%
- [ ] 所有测试通过

---

## Phase 3: 策略池与动态选择

### 任务 3.1: 实现信号池

**优先级**: P0
**预估时间**: 1 小时

**文件**: `src/ai/strategy/pool.py`

**关键实现**:
```python
class SignalPool:
    def __init__(self):
        self._strategies: Dict[str, Strategy] = {}

    def register_strategy(self, strategy: Strategy):
        self._strategies[strategy.name] = strategy

    async def collect_signals(self, market_data) -> List[TradingSignal]:
        signals = []
        for name, strategy in self._strategies.items():
            signal = await strategy.generate_signal(market_data)
            if signal:
                signals.append(signal)
        signals.sort(key=lambda x: x.strength, reverse=True)
        return signals
```

**验收标准**:
- [ ] 可以注册多个策略
- [ ] 信号收集正常
- [ ] 按强度排序

---

### 任务 3.2: 集成现有 MTF 策略

**优先级**: P0
**预估时间**: 1 小时

**文件**: `src/ai/strategy/mtf_adapter.py`

**目标**: 将现有的 `src/quantitative/mtf_resonance_lock.py` 适配到信号池

**验收标准**:
- [ ] MTF 信号可以加入信号池
- [ ] 信号格式正确

---

### 任务 3.3: 实现动态选择器

**优先级**: P0
**预估时间**: 1 小时

**文件**: `src/ai/strategy/selector.py`

**关键实现**:
```python
class StrategySelector:
    def __init__(self, provider_manager, min_confidence=0.85):
        self.provider_manager = provider_manager
        self.min_confidence = min_confidence

    async def select(self, signals, market_context) -> Optional[AIDecision]:
        provider = self.provider_manager.get_active()
        context = MarketContext(..., signals=signals, ...)
        decision = await provider.analyze(context)

        if decision.confidence < self.min_confidence:
            return None

        return decision
```

**验收标准**:
- [ ] 置信度检查正确
- [ ] 返回正确的决策

---

## Phase 4: 复盘系统

### 任务 4.1: 实现存储层

**优先级**: P1
**预估时间**: 45 分钟

**文件**: `src/ai/review/storage.py`

**关键实现**:
```python
class ReviewStorage:
    def __init__(self, path: str):
        self.path = path

    async def save(self, trade: TradeResult):
        filepath = f"{self.path}/{trade.order_id}.json"
        with open(filepath, 'w') as f:
            json.dump(trade.to_dict(), f, indent=2, default=str)

    async def load(self, order_id: str) -> Optional[TradeResult]:
        ...

    async def list_all(self, limit=100) -> List[TradeResult]:
        ...
```

**验收标准**:
- [ ] 可以保存/读取交易
- [ ] JSON 序列化正确

---

### 任务 4.2: 实现复盘系统

**优先级**: P1
**预估时间**: 1 小时

**文件**: `src/ai/review/system.py`

**关键功能**:
1. 记录交易
2. 生成复盘报告
3. 学习统计

**验收标准**:
- [ ] 可以生成复盘报告
- [ ] 可以统计学习数据

---

## Phase 5: MCP Server 与集成

### 任务 5.1: 实现 MCP Server

**优先级**: P0
**预估时间**: 2 小时

**文件**: `src/mcp/server.py`

**关键实现**:

1. **服务器初始化**
```python
from mcp.server import Server
from mcp.types import Tool

app = Server("sniper-trading-mcp")
```

2. **注册工具**
```python
@app.tool()
async def get_balance() -> dict:
    ...

@app.tool()
async def analyze_market(symbol: str, timeframe: str) -> dict:
    ...

@app.tool()
async def execute_trade(decision: dict) -> dict:
    ...
```

3. **启动服务器**
```python
if __name__ == "__main__":
    app.run(transport="stdio")
```

**验收标准**:
- [ ] 所有工具注册成功
- [ ] 可以响应 MCP 调用
- [ ] 错误处理完善

---

### 任务 5.2: 集成主交易循环

**优先级**: P0
**预估时间**: 1.5 小时

**文件**: `scripts/mcp_trader.py`

**主循环**:
```python
async def main_loop():
    while True:
        # 1. 获取市场数据
        market_data = await get_market_data()

        # 2. 收集信号
        signals = await signal_pool.collect_signals(market_data)

        # 3. AI 决策
        decision = await selector.select(signals, market_context)

        # 4. 执行交易
        if decision:
            await execute_trade(decision)

        # 5. 等待下次循环
        await asyncio.sleep(300)  # 5 分钟
```

**验收标准**:
- [ ] 主循环正常运行
- [ ] 可以执行完整流程

---

### 任务 5.3: 编写集成测试

**优先级**: P0
**预估时间**: 1 小时

**文件**: `tests/test_integration.py`

**测试场景**:
1. 完整交易流程测试
2. MCP 工具调用测试
3. 风控拦截测试
4. 复盘流程测试

**验收标准**:
- [ ] 所有集成测试通过
- [ ] 覆盖关键路径

---

### 任务 5.4: Dry-Run 测试

**优先级**: P0
**预估时间**: 1 小时

**目标**: 在 Dry-Run 模式下完整测试 24 小时

**验收标准**:
- [ ] 系统稳定运行 24 小时
- [ ] 无异常或崩溃
- [ ] 交易记录完整

---

## 实施顺序

```
Phase 1 (基础架构)
├─ 1.1 目录结构
├─ 1.2 数据模型
├─ 1.3 AIProvider 基类
├─ 1.4 Provider 管理器
└─ 1.5 配置文件

Phase 2 (AI Provider)
├─ 2.1 Claude Provider
├─ 2.2 OpenClaw Provider
└─ 2.3 单元测试

Phase 3 (策略池)
├─ 3.1 信号池
├─ 3.2 MTF 集成
└─ 3.3 动态选择器

Phase 4 (复盘系统)
├─ 4.1 存储层
└─ 4.2 复盘系统

Phase 5 (集成)
├─ 5.1 MCP Server
├─ 5.2 主循环
├─ 5.3 集成测试
└─ 5.4 Dry-Run
```

---

## 依赖管理

### 新增依赖

```txt
# requirements.txt 新增
mcp>=0.9.0
aiohttp>=3.9.0
pyyaml>=6.0
```

**安装命令**:
```bash
pip install mcp aiohttp pyyaml
```

---

## 风险与缓解

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| Claude API 限流 | 决策延迟 | 添加重试机制 + 降级到 OpenClaw |
| OpenClaw 服务不可用 | 无法使用 | 健康检查 + 自动切换 |
| 置信度门限过高 | 错过机会 | 可配置调整，记录日志分析 |
| 复盘存储失败 | 数据丢失 | 定期备份 + 云存储 |

---

## 里程碑

- [ ] **M1**: Phase 1 完成，基础架构可用
- [ ] **M2**: Phase 2 完成，AI Provider 可用
- [ ] **M3**: Phase 3 完成，策略池可用
- [ ] **M4**: Phase 4 完成，复盘系统可用
- [ ] **M5**: Phase 5 完成，系统上线

---

## 下一步行动

1. **立即开始**: Phase 1 任务 1.1 创建目录结构
2. **并行准备**: 申请 Claude API Key（如果还没有）
3. **确认**: OpenClaw 的访问方式（endpoint、认证）
