# v8.0 AI Agent 双轨架构 - 版本说明

**发布日期**: 2026-02-25
**架构版本**: v8.0
**代号**: "Claude's Double-Track"

---

## 版本概述

v8.0 是 Sniper Trading System 的重大架构升级，引入了 **AI Agent 双轨混合智能体架构**。

### 核心理念

- **Python 负责微观防守**: 数字计算、风控、滑点检测、数据采集
- **AI 负责宏观进攻**: 全网情绪、新闻博弈、宏观叙事、最终裁判

### 关键特性

| 特性 | 说明 |
|------|------|
| 🤖 **双轨架构** | 异步宏观（每小时）+ 同步微观（触发瞬间） |
| 🌐 **外部情报** | Twitter 情绪 + CoinDesk 新闻 |
| 📝 **自然语言翻译** | JSON → 结构化自然语言（AI 可理解） |
| 🔒 **滑点硬拦截** | AI 思考期间价格变动 >0.5% 自动撤销 |
| ⏱️ **超时保护** | AI 思考超过 5 秒自动撤销 |

---

## 新增组件

### 1. 自然语言数据翻译器

**文件**: `src/ai/nlt_translator.py`

**功能**: 将冰冷的 JSON 数据翻译成 AI 能理解的自然语言

**示例**:
```python
# 输入: {"funding_rate": 0.08, "OBI": 0.7}
# 输出: "资金费率 8.00%（处于历史极高拥挤区，多头过度贪婪）"
```

### 2. 宏观大局观生成器

**文件**: `src/ai/macro_oracle.py`

**功能**: 每小时生成全局市场状态

**输出**:
```python
{
    "global_sentiment": "panic",
    "dominant_narrative": "美联储加息恐慌",
    "trading_bans": ["LONG"],
    "recommended_stance": "defensive",
    "reasoning": "市场恐慌情绪蔓延，建议防御性立场"
}
```

### 3. 情报嗅探器

**文件**: `src/intelligence/web_scraper.py`

**功能**:
- Twitter API v2 集成（可选）
- CoinDesk RSS 新闻抓取
- 关键词情绪分析

### 4. 滑点硬拦截器

**文件**: `src/execution/slippage_hardlock.py`

**功能**:
- 锁定触发价格
- 检查滑点阈值（0.5%）
- 超时保护（5 秒）

---

## 交易流程

### v7.3 流程

```
MTF 三重共振 → 执行交易
```

### v8.0 流程

```
MTF 三重共振
    ↓
宏观禁令检查（每小时更新）
    ↓
AI 微观审批（3-5秒）
    ↓
锁定触发价格
    ↓
AI 思考...
    ↓
滑点检查（0.5%阈值，5秒超时）
    ↓
执行交易 / 撤销
```

---

## 环境变量

### 新增配置

```bash
# v8.0 AI Agent 配置
ENABLE_AI_AGENT=true  # 启用 AI Agent
ANTHROPIC_API_KEY=your_key  # Claude API 密钥

# Twitter API（可选）
TWITTER_BEARER_TOKEN=your_token  # Twitter Bearer Token
```

### 兼容性

- v8.0 **完全向后兼容** v7.3
- 如果 `ENABLE_AI_AGENT=false`，系统回退到纯技术面交易

---

## API 调用

### Anthropic Claude API

**端点**: `https://api.anthropic.com/v1/messages`

**模型**: `claude-sonnet-4-5-20250514`

**计费**: 按使用量计费（约 $0.003/1K tokens）

**典型成本**:
- 宏观分析（每小时）: ~2000 tokens → $0.006
- 微观审批（每次触发）: ~1500 tokens → $0.0045
- **每日估算**: $0.006 × 24 + $0.0045 × 10 ≈ $0.19/天

---

## 依赖变更

### 新增依赖

```
# v8.0 AI Agent 双轨架构
anthropic>=0.18.0
requests>=2.31.0
beautifulsoup4>=4.12.0
lxml>=4.9.0
```

### 可选依赖

- **Twitter API**: 没有也能运行，只是跳过情绪分析
- **Claude API**: 必需，否则 AI Agent 不可用

---

## 文件变更

### 新增文件（5 个）

| 文件 | 行数 | 功能 |
|------|------|------|
| `src/ai/nlt_translator.py` | ~260 | 自然语言数据翻译器 |
| `src/ai/macro_oracle.py` | ~200 | 宏观大局观生成器 |
| `src/intelligence/__init__.py` | ~5 | Intelligence 包初始化 |
| `src/intelligence/web_scraper.py` | ~240 | Twitter/新闻情报嗅探器 |
| `src/execution/slippage_hardlock.py` | ~120 | 5秒滑点硬拦截器 |

**总计**: ~825 行代码

### 修改文件（3 个）

| 文件 | 修改内容 |
|------|----------|
| `scripts/sniper_trader.py` | 集成 AI Agent 组件，修改 `check_and_trade` 流程 |
| `requirements.txt` | 添加 anthropic, requests, beautifulsoup4, lxml |
| `.env.example` | 添加 ANTHROPIC_API_KEY, TWITTER_BEARER_TOKEN, ENABLE_AI_AGENT |

---

## 架构对比

### v7.3 进程隔离架构

```
核心交易进程 ←Redis Pub/Sub→ 监控守护进程
```

### v8.0 AI Agent 双轨架构

```
轨道 1: 异步宏观（每小时）
轨道 2: 同步微观（触发瞬间）

两者都接入核心交易进程
```

---

## 性能影响

### 延迟

| 阶段 | v7.3 延迟 | v8.0 延迟 |
|------|----------|----------|
| MTF 触发检测 | <10ms | <10ms |
| AI 审批 | - | 3-5s |
| 滑点检查 | - | <1ms |
| 订单执行 | <50ms | <50ms |
| **总计** | **<60ms** | **3-5s + <60ms** |

### 资源占用

| 指标 | v7.3 | v8.0 |
|------|------|------|
| 内存 | ~50MB | ~60MB (+10MB) |
| CPU | ~2% | ~3% (+1%) |
| 网络 | ~1KB/s | ~5KB/s (+4KB/s) |

---

## 优势与风险

### 优势

1. **全局视角**: AI 能整合技术面 + 宏观面 + 情报
2. **风险规避**: 宏观禁令能避免极端市场损失
3. **滑点保护**: 物理铁律，无法绕过
4. **CoT 推理**: AI 决策过程可解释

### 风险

1. **AI 延迟**: 3-5 秒 AI 思考时间可能错过最佳价格
2. **API 成本**: 每日约 $0.19（约 ¥1.4）
3. **API 依赖**: 如果 Claude API 宕机，系统降级为纯技术面
4. **幻觉风险**: AI 可能产生错误判断

---

## 回退方案

### 如果 AI Agent 不可用

系统会自动降级为 v7.3 纯技术面模式：

```python
if self.enable_ai_agent:
    # AI Agent 模式
    approved, reason = await self._ai_micro_approval(...)
else:
    # 纯技术面模式（v7.3）
    approved = True  # 直接通过
```

### 如果 Claude API 宕机

```python
try:
    response = await self.claude_api.analyze(prompt)
except APIError:
    logger.warning("Claude API 不可用，降级为纯技术面模式")
    return True, "AI 不可用，使用纯技术面信号"
```

---

## 迁移指南

### 从 v7.3 升级到 v8.0

1. **安装新依赖**:
   ```bash
   pip install anthropic requests beautifulsoup4 lxml
   ```

2. **配置 .env**:
   ```bash
   ENABLE_AI_AGENT=true
   ANTHROPIC_API_KEY=your_key
   ```

3. **重启系统**:
   ```bash
   python scripts/sniper_trader.py
   ```

### 验证升级

检查日志中是否出现:
```
[INFO] AI Agent: 已启用
[INFO] 宏观大局观: neutral (无交易限制)
```

---

## 已知问题

1. **Twitter API 限流**: 免费版有速率限制，可能无法获取足够数据
2. **AI 偏见**: Claude 可能有过度保守的倾向
3. **新闻源单一**: 目前只有 CoinDesk，计划加入 Bloomberg Crypto

---

## 未来计划

### v8.1 计划

- [ ] 添加更多新闻源（Bloomberg Crypto, CoinTelegraph）
- [ ] 优化 AI prompt（根据实际交易效果）
- [ ] 添加 AI 决策解释器（可视化 CoT）

### v8.2 计划

- [ ] 支持多 AI 模型（GPT-4, Gemini Pro）
- [ ] 强化学习微调
- [ ] 情绪分析升级（NLP 模型）

---

## 致谢

- **Claude (Anthropic)**: 提供 Claude API
- **Binance**: 提供交易 API
- **Redis**: 提供进程间通信
- **开源社区**: 提供基础框架

---

## 反馈与支持

如有问题或建议，请：

1. 提交 Issue
2. 联系开发团队
3. 查看 [ARCHITECTURE.md](ARCHITECTURE.md) 和 [USAGE.md](USAGE.md)

---

**v8.0 AI Agent 双轨架构——让 AI 成为你的交易副手！** 🚀
