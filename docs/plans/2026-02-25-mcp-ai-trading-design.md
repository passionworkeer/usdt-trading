# MCP AI 交易系统 - 可插拔 AI 架构设计

**版本**: 1.0
**日期**: 2026-02-25
**状态**: 待用户批准

---

## 1. 目标概述

将现有 v8.0 交易系统改造为可插拔的 MCP AI 交易平台，支持：
- 多种 AI 引擎灵活切换（Claude / OpenClaw / 未来扩展）
- 完整交易能力通过 MCP 暴露
- 策略池动态选择
- 自动复盘学习系统

**核心原则**：宁可错过机会，不做低置信度决策（置信度门限 >= 0.85）

---

## 2. 系统架构

### 2.1 整体架构

```
┌─────────────────────────────────────────────────────────────┐
│                     双轨 AI 交易系统                         │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│   ┌─────────────┐     ┌─────────────┐     ┌─────────────┐  │
│   │   Claude    │     │  OpenClaw   │     │  未来扩展   │  │
│   │  (MCP Client)   │  (MCP Client)   │  (MCP Client)   │  │
│   └──────┬──────┘     └──────┬──────┘     └──────┬──────┘  │
│          │                   │                   │          │
│          └─────────┬─────────┴───────────────────┘          │
│                    ↓                                         │
│          ┌─────────────────────┐                             │
│          │    MCP Server       │                             │
│          │  (统一 AI 接口层)   │                             │
│          └──────────┬──────────┘                             │
│                     │                                        │
│          ┌──────────┴──────────┐                             │
│          ↓                     ↓                             │
│   ┌──────────────┐      ┌──────────────┐                    │
│   │ AI Provider  │      │  策略池 +    │                    │
│   │   接口层      │      │  动态选择    │                    │
│   └──────┬───────┘      └──────┬───────┘                    │
│          │                      │                             │
│          └──────────┬───────────┘                             │
│                     ↓                                        │
│          ┌─────────────────────┐                             │
│          │    交易执行层       │                             │
│          │  (现有 v8.0 核心)  │                             │
│          └─────────────────────┘                             │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 模块职责

| 模块 | 职责 |
|------|------|
| MCP Server | 暴露统一工具接口给 AI 客户端 |
| AI Provider 接口层 | 抽象 AI 引擎，统一调用方式 |
| Claude Provider | Claude API 实现 |
| OpenClaw Provider | OpenClaw 引擎实现 |
| 策略池 | 收集和管理各类交易信号 |
| 动态选择器 | 根据市场状态选择最优策略 |
| 交易执行层 | 现有 v8.0 核心逻辑 |
| 复盘系统 | 记录、分析、学习交易经验 |

---

## 3. MCP Server 工具定义

### 3.1 工具列表

| 工具名称 | 功能 | 返回值 |
|---------|------|--------|
| `get_balance` | 查询账户余额 | {available: float, positions: []} |
| `get_positions` | 查询当前持仓 | [{symbol, qty, entry_price, pnl}] |
| `get_market_data` | 获取市场数据 | {klines, depth, ticker} |
| `get_signal_pool` | 获取信号池 | [{strategy, signal, strength, created_at}] |
| `analyze_market` | AI 分析市场 | {decision, confidence, reason} |
| `execute_trade` | 执行交易 | {order_id, status, filled_qty} |
| `cancel_order` | 取消订单 | {success, order_id} |
| `get_trade_history` | 交易历史 | [{trade}] |
| `get_review` | 复盘报告 | {analysis, lessons, score} |
| `get_system_status` | 系统状态 | {health, active_strategies, last_trade} |

### 3.2 数据结构

```python
# 市场上下文
class MarketContext:
    symbol: str              # 交易对
    timeframe: str           # 时间周期
    klines: list             # K线数据
    depth: dict              # 深度数据
    signals: list            # 当前信号
    balance: float           # 可用资金
    positions: list          # 当前持仓

# AI 决策结果
class AIDecision:
    action: str              # BUY / SELL / PASS
    confidence: float        # 0.0 - 1.0
    reason: str              # 决策理由
    strategy: str            # 使用的策略
    entry_price: float       # 建议入场价
    stop_loss: float         # 止损价
    take_profit: float      # 止盈价
    position_size: float      # 仓位大小 (USDT)

# 交易结果
class TradeResult:
    order_id: str
    symbol: str
    action: str
    qty: float
    entry_price: float
    exit_price: float
    pnl: float
    pnl_percent: float
    holding_time: int        # 持仓秒数
    ai_decision: AIDecision
    created_at: datetime
    closed_at: datetime
```

---

## 4. 可插拔 AI 引擎设计

### 4.1 抽象接口

```python
from abc import ABC, abstractmethod
from typing import Optional

class AIProvider(ABC):
    """AI 引擎抽象接口"""

    @property
    @abstractmethod
    def name(self) -> str:
        """引擎名称"""
        pass

    @property
    @abstractmethod
    def config(self) -> dict:
        """引擎配置"""
        pass

    @abstractmethod
    async def analyze(self, context: MarketContext) -> AIDecision:
        """
        分析市场并给出决策

        Args:
            context: 市场上下文

        Returns:
            AIDecision: 包含决策、置信度和理由
        """
        pass

    @abstractmethod
    async def review(self, trade: TradeResult) -> ReviewReport:
        """
        复盘单笔交易

        Args:
            trade: 交易结果

        Returns:
            ReviewReport: 复盘报告
        """
        pass

    @abstractmethod
    async def health_check(self) -> bool:
        """
        检查 AI 服务健康状态

        Returns:
            bool: 服务是否可用
        """
        pass
```

### 4.2 Claude Provider 实现

```python
class ClaudeProvider(AIProvider):
    """Claude API 实现"""

    def __init__(
        self,
        api_key: str,
        model: str = "claude-sonnet-4-6",
        max_tokens: int = 4096,
        temperature: float = 0.7
    ):
        self.api_key = api_key
        self.model = model
        self.max_tokens = max_tokens
        self.temperature = temperature

    async def analyze(self, context: MarketContext) -> AIDecision:
        """使用 Claude API 分析市场"""
        # 1. 构建提示词
        prompt = self._build_prompt(context)
        # 2. 调用 API
        response = await self._call_api(prompt)
        # 3. 解析响应
        return self._parse_response(response)

    async def review(self, trade: TradeResult) -> ReviewReport:
        """使用 Claude 复盘交易"""
        prompt = self._build_review_prompt(trade)
        response = await self._call_api(prompt)
        return self._parse_review(response)

    async def health_check(self) -> bool:
        """检查 Claude API 可用性"""
        # 尝试调用轻量级请求验证
        ...
```

### 4.3 OpenClaw Provider 实现

```python
class OpenClawProvider(AIProvider):
    """OpenClaw 引擎实现"""

    def __init__(
        self,
        endpoint: str = "http://localhost:8000",
        api_key: Optional[str] = None,
        timeout: int = 30
    ):
        self.endpoint = endpoint
        self.api_key = api_key
        self.timeout = timeout

    async def analyze(self, context: MarketContext) -> AIDecision:
        """使用 OpenClaw 分析市场"""
        # 调用 OpenClaw API
        response = await self._call_api(context.to_dict())
        return self._parse_response(response)

    async def review(self, trade: TradeResult) -> ReviewReport:
        """使用 OpenClaw 复盘交易"""
        ...

    async def health_check(self) -> bool:
        """检查 OpenClaw 服务可用性"""
        ...
```

### 4.4 引擎管理器

```python
class AIProviderManager:
    """AI 引擎管理器"""

    def __init__(self):
        self._providers: Dict[str, AIProvider] = {}
        self._active_provider: Optional[str] = None

    def register(self, provider: AIProvider):
        """注册 AI 引擎"""
        self._providers[provider.name] = provider

    def set_active(self, name: str):
        """设置活跃引擎"""
        if name not in self._providers:
            raise ValueError(f"Unknown provider: {name}")
        self._active_provider = name

    def get_active(self) -> AIProvider:
        """获取活跃引擎"""
        if not self._active_provider:
            raise ValueError("No active provider")
        return self._providers[self._active_provider]

    def list_providers(self) -> List[str]:
        """列出所有可用引擎"""
        return list(self._providers.keys())

    async def health_check_all(self) -> Dict[str, bool]:
        """检查所有引擎健康状态"""
        results = {}
        for name, provider in self._providers.items():
            try:
                results[name] = await provider.health_check()
            except:
                results[name] = False
        return results
```

---

## 5. 策略池与动态选择

### 5.1 策略池

```python
class SignalPool:
    """信号池 - 收集各类策略信号"""

    def __init__(self):
        self._signals: List[TradingSignal] = []
        self._strategies: Dict[str, Strategy] = {}

    def register_strategy(self, strategy: Strategy):
        """注册策略"""
        self._strategies[strategy.name] = strategy

    async def collect_signals(self, market_data: MarketData) -> List[TradingSignal]:
        """收集所有策略信号"""
        signals = []
        for name, strategy in self._strategies.items():
            signal = await strategy.generate_signal(market_data)
            if signal:
                signals.append(signal)
        # 按强度排序
        signals.sort(key=lambda x: x.strength, reverse=True)
        return signals
```

### 5.2 动态选择器

```python
class StrategySelector:
    """策略动态选择器"""

    def __init__(
        self,
        provider_manager: AIProviderManager,
        min_confidence: float = 0.85
    ):
        self.provider_manager = provider_manager
        self.min_confidence = min_confidence

    async def select(
        self,
        signals: List[TradingSignal],
        market_context: MarketContext
    ) -> Optional[AIDecision]:
        """
        根据信号选择最优策略并获取 AI 确认

        Returns:
            AIDecision 或 None（置信度不足时）
        """
        # 1. 让 AI 评估所有信号
        provider = self.provider_manager.get_active()

        # 2. 构建分析请求
        context = MarketContext(
            symbol=market_context.symbol,
            timeframe=market_context.timeframe,
            klines=market_context.klines,
            depth=market_context.depth,
            signals=signals,
            balance=market_context.balance,
            positions=market_context.positions
        )

        # 3. 获取 AI 决策
        decision = await provider.analyze(context)

        # 4. 置信度检验
        if decision.confidence < self.min_confidence:
            return None

        return decision
```

---

## 6. 自动复盘系统

### 6.1 复盘记录

```python
class ReviewSystem:
    """自动复盘系统"""

    def __init__(self, storage_path: str):
        self.storage_path = storage_path

    async def record(self, trade: TradeResult):
        """记录交易"""
        # 保存到 JSON 文件
        filepath = f"{self.storage_path}/{trade.order_id}.json"
        with open(filepath, 'w') as f:
            json.dump(trade.to_dict(), f, indent=2, default=str)

    async def get_trade(self, order_id: str) -> Optional[TradeResult]:
        """获取交易记录"""
        ...

    async def list_trades(
        self,
        limit: int = 100,
        offset: int = 0
    ) -> List[TradeResult]:
        """列出交易历史"""
        ...
```

### 6.2 复盘分析

```python
    async def generate_review(self, trade: TradeResult) -> ReviewReport:
        """生成复盘报告"""
        provider = self.provider_manager.get_active()
        return await provider.review(trade)

    async def learn(self) -> LearningReport:
        """从历史交易中学习"""
        trades = await self.list_trades(limit=1000)

        # 统计
        total = len(trades)
        winning = sum(1 for t in trades if t.pnl > 0)
        win_rate = winning / total if total > 0 else 0

        avg_pnl = sum(t.pnl for t in trades) / total if total > 0 else 0

        # 按策略分组统计
        by_strategy = {}
        for trade in trades:
            strategy = trade.ai_decision.strategy
            if strategy not in by_strategy:
                by_strategy[strategy] = {'wins': 0, 'losses': 0, 'total_pnl': 0}
            if trade.pnl > 0:
                by_strategy[strategy]['wins'] += 1
            else:
                by_strategy[strategy]['losses'] += 1
            by_strategy[strategy]['total_pnl'] += trade.pnl

        return LearningReport(
            total_trades=total,
            win_rate=win_rate,
            avg_pnl=avg_pnl,
            by_strategy=by_strategy,
            recommendations=self._generate_recommendations(by_strategy)
        )
```

---

## 7. 风险控制

### 7.1 风险参数

| 参数 | 值 | 说明 |
|------|-----|------|
| MIN_CONFIDENCE | 0.85 | 最低置信度门限 |
| MAX_POSITION_SIZE | 0.10 | 单笔最大仓位比例 |
| MAX_POSITION_USDT | 20 | 单笔最大仓位 (USDT) |
| DAILY_LOSS_LIMIT | 0.05 | 日亏损上限 |
| MAX_SLIPPAGE | 0.005 | 滑点阈值 (0.5%) |
| HARD_STOP_LOSS | 0.10 | 硬止损 (10%) |
| HARD_TAKE_PROFIT | 0.20 | 硬止盈 (20%) |

### 7.2 风控检查

```python
class RiskController:
    """风险控制器"""

    def __init__(self, config: RiskConfig):
        self.config = config
        self.daily_loss = 0.0

    def check_before_trade(self, decision: AIDecision, balance: float) -> Tuple[bool, str]:
        """
        交易前风控检查

        Returns:
            (是否通过, 拒绝原因)
        """
        # 1. 置信度检查
        if decision.confidence < self.config.min_confidence:
            return False, f"Confidence {decision.confidence} < {self.config.min_confidence}"

        # 2. 仓位检查
        position_size = decision.position_size
        if position_size > balance * self.config.max_position_size:
            return False, f"Position size {position_size} exceeds limit"
        if position_size > self.config.max_position_usdt:
            return False, f"Position size {position_size} exceeds {self.config.max_position_usdt} USDT"

        # 3. 日亏损检查
        if self.daily_loss >= balance * self.config.daily_loss_limit:
            return False, f"Daily loss limit reached: {self.daily_loss}"

        return True, ""

    def check_slippage(self, entry_price: float, current_price: float) -> bool:
        """滑点检查"""
        change = abs(current_price - entry_price) / entry_price
        return change <= self.config.max_slippage
```

---

## 8. 执行流程

```
┌─────────────────────────────────────────────────────────────┐
│                      主循环流程                               │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  1. 定时触发 (每 5 分钟)                                    │
│           ↓                                                 │
│  2. 获取市场数据                                             │
│           ↓                                                 │
│  3. 策略池收集信号                                           │
│           ↓                                                 │
│  4. 有有效信号?                                              │
│      否 → 等待下次循环                                       │
│      是 ↓                                                   │
│  5. 构建市场上下文                                           │
│           ↓                                                 │
│  6. AI 分析决策 (可插拔引擎)                                 │
│           ↓                                                 │
│  7. 置信度 >= 0.85?                                         │
│      否 → 记录 PASS，跳过                                    │
│      是 ↓                                                   │
│  8. 风控检查                                                 │
│      不通过 → 记录拒绝原因                                    │
│           ↓                                                 │
│  9. 执行交易                                                 │
│           ↓                                                 │
│  10. 滑点检查 (5 秒超时)                                     │
│      失败 → 撤销订单                                        │
│           ↓                                                 │
│  11. 记录交易结果                                            │
│           ↓                                                 │
│  12. 止盈/止损监控 (后台异步)                                │
│           ↓                                                 │
│  13. 平仓时触发复盘                                          │
│           ↓                                                 │
│  14. 定期学习 (每小时)                                       │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## 9. 配置管理

### 9.1 环境变量

```bash
# MCP Server
MCP_HOST=0.0.0.0
MCP_PORT=3000

# AI Providers
ANTHROPIC_API_KEY=sk-ant-...
OPENCLAW_ENDPOINT=http://localhost:8000
OPENCLAW_API_KEY=...

# Active Provider
ACTIVE_AI_PROVIDER=claude  # 或 openclaw

# Risk Control
MIN_CONFIDENCE=0.85
MAX_POSITION_USDT=20
DAILY_LOSS_LIMIT=0.05

# Storage
REVIEW_STORAGE_PATH=./data/reviews
```

### 9.2 Provider 配置示例

```yaml
# config/ai_providers.yaml
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
```

---

## 10. 文件结构

```
src/
├── mcp/
│   ├── __init__.py
│   ├── server.py              # MCP Server 主入口
│   ├── tools.py               # 工具定义
│   └── context.py             # 上下文构建
│
├── ai/
│   ├── __init__.py
│   ├── provider/
│   │   ├── __init__.py
│   │   ├── base.py            # AIProvider 抽象基类
│   │   ├── manager.py         # Provider 管理器
│   │   ├── claude.py          # Claude 实现
│   │   └── openclaw.py       # OpenClaw 实现
│   │
│   ├── strategy/
│   │   ├── __init__.py
│   │   ├── pool.py            # 信号池
│   │   └── selector.py        # 策略选择器
│   │
│   └── review/
│       ├── __init__.py
│       ├── system.py          # 复盘系统
│       └── storage.py         # 存储层
│
├── risk/
│   ├── __init__.py
│   └── controller.py         # 风控控制器
│
└── existing_v8/               # 现有 v8.0 代码
    ├── ...
```

---

## 11. 验收标准

### 11.1 功能验收

- [ ] MCP Server 可以启动并响应工具调用
- [ ] Claude Provider 可以正常分析市场并返回决策
- [ ] OpenClaw Provider 可以正常分析市场并返回决策
- [ ] 可以动态切换活跃的 AI 引擎
- [ ] 置信度 < 0.85 的决策会被正确跳过
- [ ] 风控检查可以正确阻止不合规的交易
- [ ] 交易完成后自动记录到复盘系统
- [ ] 可以生成单笔交易的复盘报告
- [ ] 可以统计整体学习报告

### 11.2 性能验收

- [ ] MCP 响应时间 < 100ms
- [ ] AI 分析时间 < 10 秒
- [ ] 交易执行延迟 < 50ms

### 11.3 安全验收

- [ ] API Key 不硬编码
- [ ] 敏感操作有日志记录
- [ ] 异常情况有完整错误处理

---

## 12. 后续扩展

- **多引擎投票**：支持多个引擎同时分析，取多数决策
- **策略市场**：支持加载第三方策略
- **模拟交易**：支持 Paper Trading 模式
- **移动端通知**：支持更多通知渠道

---

## 附录：相关文件

- `docs/plans/2026-02-25-mcp-ai-trading-design.md` (本文档)
- `docs/plans/` (后续实现计划)
