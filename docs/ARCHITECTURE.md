# Sniper Trading System - 架构文档

**版本**: v8.0 AI Agent 双轨架构
**最后更新**: 2026-02-25

---

## 目录

1. [系统架构概览](#系统架构概览)
2. [核心组件](#核心组件)
3. [数据流](#数据流)
4. [AI Agent 架构](#ai-agent-架构)
5. [进程隔离设计](#进程隔离设计)
6. [延迟预算](#延迟预算)

---

## 系统架构概览

```
┌─────────────────────────────────────────────────────────────┐
│                    v8.0 双轨混合智能体架构                   │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌───────────────────────────────────────────────────────┐  │
│  │ 轨道 1: 异步宏观大局观（每小时）                       │  │
│  │                                                       │  │
│  │  Web/Social Scraper     NLT Data Translator          │  │
│  │  (Twitter/News)    ────→  (Prompt Engineering)       │  │
│  │        │                       │                      │  │
│  │        ↓                       ↓                      │  │
│  │  "全网恐慌"          结构化自然语言                  │  │
│  │  "多头狂欢"          (发送给 AI)                     │  │
│  │        │                       │                      │  │
│  │        └───────────────────────┼───────────────┐     │  │
│  │                                ↓               │     │  │
│  │  ┌──────────────────────────────────────────────┐ │     │  │
│  │  │  AI 宏观大局观（CoT 深度思考）             │ │     │  │
│  │  │  - 全局市场状态                           │ │     │  │
│  │  │  - 主导叙事分析                           │ │     │  │
│  │  │  - 交易禁区声明                           │ │     │  │
│  │  └──────────────────────────────────────────────┘ │     │  │
│  │                                │               │     │  │
│  │                                ↓               │     │  │
│  │  ┌──────────────────────────────────────────────┐ │     │  │
│  │  │  Macro State Cache (内存)                  │ │     │  │
│  │  │  - global_sentiment: "FEAR"                │ │     │  │
│  │  │  - dominant_narrative: "Rate hike fears"   │ │     │  │
│  │  │  - trading_ban: ["LONG", "ALL"]           │ │     │  │
│  │  └──────────────────────────────────────────────┘ │     │  │
│  └───────────────────────────────────────────────────────┘  │
│                                                             │
│  ┌───────────────────────────────────────────────────────┐  │
│  │ 轨道 2: 同步微观审批（触发瞬间）                       │  │
│  │                                                       │  │
│  │  MTF Trigger                                      │     │  │
│  │  (放量突破)  ───→  Record Trigger_Price            │     │  │
│  │        │                       │                      │     │  │
│  │        ↓                       ↓                      │     │  │
│  │  Micro Data         NLT Data Translator           │     │  │
│  │  (Order Book)  ────→  (技术面报告)                │     │  │
│  │        │                       │                      │     │  │
│  │        └───────────────────────┼───────────────┐     │  │
│  │                                ↓               │     │  │
│  │  ┌──────────────────────────────────────────────┐ │     │  │
│  │  │  Prompt Assembler (最终 Prompt)           │ │     │  │
│  │  │  ┌──────────────────────────────────────┐   │ │     │  │
│  │  │  │ 1. 宏观大局观（来自 Cache）          │   │ │     │  │
│  │  │  │ 2. 技术面报告（NLT 翻译）            │   │ │     │  │
│  │  │  │ 3. 情报摘要（Twitter/News）         │   │ │     │  │
│  │  │  │ 4. Trigger Price 锁定              │   │ │     │  │
│  │  │  └──────────────────────────────────────┘   │ │     │  │
│  │  └──────────────────────────────────────────────┘ │     │  │
│  │                                │               │     │  │
│  │                                ↓               │     │  │
│  │  ┌──────────────────────────────────────────────┐ │     │  │
│  │  │  AI Final Confirmation (3-5 秒思考)        │ │     │  │
│  │  │  - CoT 推理链                             │ │     │  │
│  │  │  - BUY/SELL/PASS                         │ │     │  │
│  │  │  - Confidence 0-1                        │ │     │  │
│  │  └──────────────────────────────────────────────┘ │     │  │
│  │                                │               │     │  │
│  │                                ↓               │     │  │
│  │  ┌──────────────────────────────────────────────┐ │     │  │
│  │  │  Slippage Hard-Lock (5 秒物理铁律)        │ │     │  │
│  │  │  if |current_price - trigger_price| > 0.5% │     │  │
│  │  │     ABORT ("错过最佳击球区")              │ │     │  │
│  │  └──────────────────────────────────────────────┘ │     │  │
│  │                                │               │     │  │
│  │                                ↓               │     │  │
│  │  ┌──────────────────────────────────────────────┐ │     │  │
│  │  │  Execution Layer (Python 微观防守)        │ │     │  │
│  │  │  - 订单执行                                │ │     │  │
│  │  │  - 风控检查                                │ │     │  │
│  │  │  - 止损止盈                                │ │     │  │
│  │  └──────────────────────────────────────────────┘ │     │  │
│  └───────────────────────────────────────────────────────┘  │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## 核心组件

### 1. AI Agent 组件

#### 1.1 自然语言数据翻译器 (NLT Translator)

**文件**: `src/ai/nlt_translator.py`

**功能**: 将 JSON 数据转换为自然语言报告

**示例**:
```python
# 输入
snapshot = {
    "funding_rate": 0.08,
    "order_book_imbalance": 0.7,
    "volume_ratio": 3.5
}

# 输出
"""
技术面报告：
- 资金费率 8.00%（处于历史极高拥挤区，多头过度贪婪）
- 盘口失衡率 0.70，巨量冰山买单支撑
- 15m 级别巨量爆发（成交量 3.5x 平均水平）
"""
```

#### 1.2 宏观大局观生成器 (Macro Oracle)

**文件**: `src/ai/macro_oracle.py`

**功能**: 每小时生成全局市场状态

**数据结构**:
```python
@dataclass
class MacroState:
    global_sentiment: str  # 'panic' | 'neutral' | 'euphoric'
    dominant_narrative: str
    trading_bans: list  # ['LONG'] | ['SHORT'] | []
    recommended_stance: str  # 'defensive' | 'neutral' | 'aggressive'
    reasoning: str
    timestamp: datetime
```

#### 1.3 情报嗅探器 (Intelligence Sniffer)

**文件**: `src/intelligence/web_scraper.py`

**功能**:
- Twitter API v2 集成（可选）
- CoinDesk RSS 新闻抓取
- 关键词情绪分析

#### 1.4 滑点硬拦截器 (Slippage Hardlock)

**文件**: `src/execution/slippage_hardlock.py`

**功能**:
- 锁定触发价格
- 检查滑点阈值（0.5%）
- 超时保护（5 秒）

### 2. 量化策略组件

#### 2.1 MTF 三重共振锁

**文件**: `src/quantitative/mtf_resonance_lock.py`

**触发条件**:
1. 4H 趋势突破（EMA-50）
2. 资金费率/OI 极端值
3. 15m 级别放量（>2x 平均）

#### 2.2 仓位管理器

**文件**: `src/exchange/sniper_position_manager.py`

**功能**:
- 动态仓位计算
- 止损止盈管理
- 风险敞口控制

### 3. 执行层组件

#### 3.1 交易所信息管理器

**文件**: `src/exchange/exchange_info_manager.py`

**功能**:
- Binance API 封装
- 市场数据获取
- 订单执行

---

## 数据流

### 宏观轨道（每小时）

```
1. IntelligenceSniffer.scrape_twitter_sentiment()
   ↓
2. IntelligenceSniffer.scrape_macro_news()
   ↓
3. NLTDataTranslator.translate_twitter_sentiment()
   ↓
4. NLTDataTranslator.translate_macro_news()
   ↓
5. MacroOracle.generate_macro_state()
   ↓
6. MacroState Cache（内存）
```

### 微观轨道（触发瞬间）

```
1. MTFResonanceLock.check_triple_resonance()
   ↓
2. SlippageHardlock.lock_trigger_price()
   ↓
3. NLTDataTranslator.translate_micro_snapshot()
   ↓
4. ClaudeDecisionEngine.analyze()
   ↓
5. SlippageHardlock.check_slippage()
   ↓
6. OrderExecutor.execute()
```

---

## AI Agent 架构

### 决策流程

```
┌─────────────────────────────────────────┐
│ 1. MTF 触发                              │
│    - 4H 趋势确认                         │
│    - 资金费率极端值                      │
│    - 15m 放量                            │
└─────────────────────────────────────────┘
                  ↓
┌─────────────────────────────────────────┐
│ 2. 宏观禁令检查                          │
│    - 读取 MacroState Cache               │
│    - 检查 trading_bans                   │
│    - 如果禁止则直接 PASS                 │
└─────────────────────────────────────────┘
                  ↓
┌─────────────────────────────────────────┐
│ 3. 锁定触发价格                          │
│    - SlippageHardlock.lock()             │
│    - 记录 timestamp                      │
└─────────────────────────────────────────┘
                  ↓
┌─────────────────────────────────────────┐
│ 4. AI 微观审批（3-5 秒）                 │
│    - 组装 Prompt                         │
│      - 宏观大局观                        │
│      - 技术面报告（NLT）                 │
│      - 情报摘要                          │
│      - Trigger Price                     │
│    - 调用 Claude API                     │
│    - 解析决策                            │
│    - 检查置信度（≥ 0.6）                 │
└─────────────────────────────────────────┘
                  ↓
┌─────────────────────────────────────────┐
│ 5. 滑点检查                              │
│    - 计算价格变动                        │
│    - 如果 > 0.5% 则 ABORT                │
│    - 如果超时（5s）则 ABORT              │
└─────────────────────────────────────────┘
                  ↓
┌─────────────────────────────────────────┐
│ 6. 执行交易                              │
│    - 下单                                │
│    - 设置止损止盈                        │
│    - 发送预警                            │
└─────────────────────────────────────────┘
```

### Prompt 工程

**微观审批 Prompt 模板**:
```
你是一位专业的加密货币交易员。现在有一个潜在交易机会，请你做最终决策。

## 宏观大局观
{macro_report}

## 技术面报告
{micro_report}

## 外部情报
{intel_report}

## MTF 信号
- 方向: {signal}
- 置信度: {confidence}
- 触发时间: {timestamp}
- 锁定价格: ${trigger_price}

## 你的任务
基于以上信息，给出最终决策（你有 3-5 秒思考时间）：

```json
{
    "decision": "BUY" | "SELL" | "PASS",
    "confidence": 0.0-1.0,
    "reasoning": "简短推理（CoT）",
    "risk_factors": ["风险1", "风险2"],
    "key_catalyst": "关键催化剂（1句话）"
}
```

**重要原则**：
1. 如果宏观禁止该方向，直接 PASS
2. 技术面和宏观必须一致
3. 保守优先，不确定时 PASS
```

---

## 进程隔离设计

### v7.3 架构

```
┌─────────────────────────────────────────────┐
│                    服务器                    │
├─────────────────────────────────────────────┤
│                                             │
│  ┌────────────────────────────────────────┐ │
│  │ 进程 1: 核心交易引擎                    │ │
│  │                                        │ │
│  │  - SniperTrader                        │ │
│  │  - MTFResonanceLock                    │ │
│  │  - StateBroadcaster（Redis Pub/Sub）   │ │
│  └────────────────────────────────────────┘ │
│                       │                     │
│                       │ Redis Pub/Sub       │
│                       │ (<1ms 延迟)         │
│                       │                     │
│  ┌────────────────────────────────────────┐ │
│  │ 进程 2: 监控守护进程                    │ │
│  │                                        │ │
│  │  - Redis 订阅器                        │ │
│  │  - FastAPI（127.0.0.1:8765）           │ │
│  └────────────────────────────────────────┘ │
│                                             │
└─────────────────────────────────────────────┘
```

### 通信协议

**Redis Pub/Sub**:
```python
# 发布状态
state_broadcaster.publish({
    "event": "trade_executed",
    "symbol": "BTCUSDT",
    "side": "LONG",
    "price": 43256.78,
    "quantity": 0.0046,
    "timestamp": "2026-02-25T14:30:05Z"
})

# 订阅状态
def on_message(channel, message):
    if message["event"] == "trade_executed":
        update_dashboard(message)
```

---

## 延迟预算

| 阶段 | 目标延迟 | 说明 |
|------|---------|------|
| MTF 触发检测 | < 10ms | 本地计算 |
| 宏观禁令检查 | < 1ms | 内存读取 |
| 价格锁定 | < 1ms | 内存写入 |
| AI 审批 | 3-5s | Claude API 调用 |
| 滑点检查 | < 1ms | 本地计算 |
| 订单执行 | < 50ms | Binance API |
| **总计** | **3-5s + < 60ms** | **可接受** |

---

## 扩展性设计

### 新增数据源

```python
# src/intelligence/custom_scraper.py
class CustomScraper:
    async def scrape_custom_data(self, symbol: str) -> Dict:
        # 实现自定义数据源
        pass

# 集成到 IntelligenceSniffer
class IntelligenceSniffer:
    def __init__(self):
        self.custom_scraper = CustomScraper()

    async def get_intelligence_summary(self, symbol: str) -> Dict:
        custom_data = await self.custom_scraper.scrape_custom_data(symbol)
        # 合并数据
```

### 新增 AI 模型

```python
# src/ai/custom_engine.py
class CustomAIEngine:
    async def analyze(self, prompt: str) -> Dict:
        # 调用自定义 AI 模型
        pass

# 替换 ClaudeDecisionEngine
class SniperTrader:
    def __init__(self):
        if enable_ai_agent:
            self.decision_engine = CustomAIEngine()
```

---

## 性能优化

### 1. 异步 I/O

所有网络请求使用 `asyncio`:
- API 调用
- 数据抓取
- Redis 通信

### 2. 缓存机制

- 宏观状态缓存（1 小时）
- 交易所信息缓存（15 分钟）
- WebSocket 连接池

### 3. 批量操作

- 批量获取市场数据
- 批量发送预警通知

---

## 安全设计

### 1. API Key 保护

- 环境变量存储
- 禁止硬编码
- IP 白名单

### 2. 交易权限控制

- 只交易权限（禁止提现）
- 仓位大小限制
- 单日交易次数限制

### 3. 监控端口保护

- 绑定 127.0.0.1（禁止公网访问）
- SSH 隧道访问
- 日志审计

---

## 监控指标

### 系统指标

- CPU 使用率
- 内存使用率
- 进程运行时间

### 交易指标

- 总交易次数
- 胜率
- 盈亏比
- 最大回撤

### AI 指标

- AI 决策延迟
- AI 置信度分布
- 交易撤销次数（滑点）

---

## 故障恢复

### 1. 进程崩溃

- 监控守护进程独立运行
- 核心交易进程可重启
- Redis 持久化状态

### 2. 网络中断

- WebSocket 自动重连
- API 调用重试机制
- 降级模式（禁用 AI）

### 3. API 限流

- 指数退避重试
- 请求频率限制
- 备用 API 端点

---

## 下一步

- 查看使用指南: [USAGE.md](USAGE.md)
- 了解配置参数: [CONFIGURATION.md](CONFIGURATION.md)
- 查看 v8.0 版本说明: [VERSION_v8.0.md](VERSION_v8.0.md)
