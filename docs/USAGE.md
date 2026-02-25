# Sniper Trading System - 使用指南

**版本**: v8.0 AI Agent 双轨架构
**最后更新**: 2026-02-25

---

## 目录

1. [环境准备](#环境准备)
2. [配置说明](#配置说明)
3. [快速启动](#快速启动)
4. [交易流程](#交易流程)
5. [AI Agent 配置](#ai-agent-配置)
6. [监控面板](#监控面板)
7. [常见问题](#常见问题)

---

## 环境准备

### 系统要求

- **操作系统**: Windows 10+, Linux, macOS
- **Python**: 3.10+
- **Redis**: 5.0+（用于进程间通信）

### 安装依赖

```bash
# 1. 克隆项目
git clone https://github.com/your-org/sniper-trading-system.git
cd sniper-trading-system

# 2. 安装 Python 依赖
pip install -r requirements.txt

# 3. 启动 Redis（Windows）
# 下载 Redis for Windows 或使用 WSL
redis-server

# 4. 验证安装
python -c "import ccxt, redis, anthropic; print('依赖安装成功')"
```

---

## 配置说明

### 环境变量配置

复制 `.env.example` 到 `.env` 并配置：

```bash
# ==================== Binance API ====================
BINANCE_API_KEY=your_binance_api_key
BINANCE_API_SECRET=your_binance_secret
BINANCE_TESTNET=true  # 测试网: true, 主网: false

# ==================== 交易参数 ====================
CAPITAL=200  # 总资金（USDT）
DRY_RUN=true  # 模拟运行（测试时使用 true）

# ==================== v8.0 AI Agent 配置 ====================
ENABLE_AI_AGENT=true  # 启用 AI Agent
ANTHROPIC_API_KEY=your_anthropic_api_key  # Claude API 密钥

# Twitter API（可选，用于情绪分析）
TWITTER_BEARER_TOKEN=your_twitter_bearer_token

# ==================== 预警配置（可选）====================
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
TELEGRAM_CHAT_ID=your_telegram_chat_id
DISCORD_WEBHOOK_URL=your_discord_webhook_url
```

### API Key 获取

#### Binance API

1. 登录 [Binance](https://www.binance.com)
2. 进入 **API Management**
3. 创建新 API Key
4. **重要**: 只勾选 "Enable Spot & Margin Trading" 和 "Enable Futures"
5. **禁止**: 勾选 "Enable Withdrawals"
6. 设置 IP 白名单

#### Anthropic API (Claude AI)

1. 访问 [Anthropic Console](https://console.anthropic.com/)
2. 注册/登录
3. 获取 API Key
4. 充值额度（按使用量计费）

#### Twitter API（可选）

1. 访问 [Twitter Developer Portal](https://developer.twitter.com/)
2. 创建新 App
3. 获取 Bearer Token

---

## 快速启动

### 1. Dry-Run 模式测试

```bash
# 确保 .env 中设置了 DRY_RUN=true
python scripts/sniper_trader.py
```

**预期输出**:
```
[2026-02-25 10:00:00] INFO - Sniper Trading System v8.0
[2026-02-25 10:00:00] INFO - AI Agent: 已启用
[2026-02-25 10:00:00] INFO - Dry-Run 模式: 已启用
[2026-02-25 10:00:00] INFO - 开始监控市场...
```

### 2. 启动监控面板（可选）

```bash
# 新终端窗口
python scripts/start_monitoring.py
```

访问: http://127.0.0.1:8765

### 3. 主网交易（谨慎！）

```bash
# 1. 确保 .env 中设置了:
#    BINANCE_TESTNET=false
#    DRY_RUN=false

# 2. 先用小金额测试（CAPITAL=10）

# 3. 确认无误后运行
python scripts/sniper_trader.py
```

---

## 交易流程

### MTF 三重共振

系统只在满足以下**全部条件**时才会触发交易：

1. **4H 趋势突破**: 价格突破 EMA-50
2. **资金费率/OI 极端值**: Funding > ±0.05% 或 OI 异常
3. **15m 级别放量**: 成交量 > 2x 平均水平

### AI Agent 审批流程

```
MTF 触发
    ↓
宏观大局观检查（每小时更新）
    ↓
AI 微观审批（3-5秒）
    ↓
锁定触发价格
    ↓
AI 思考...
    ↓
滑点检查（0.5%阈值）
    ↓
执行交易 / 撤销
```

### 交易示例

```log
[2026-02-25 14:30:00] INFO - [BTCUSDT] MTF 三重共振触发！
[2026-02-25 14:30:00] INFO - 宏观大局观: neutral (无交易限制)
[2026-02-25 14:30:01] INFO - 锁定触发价格: $43,256.78
[2026-02-25 14:30:04] INFO - AI 决策: BUY (confidence: 0.85)
[2026-02-25 14:30:04] INFO - 滑点检查: 0.12% (通过)
[2026-02-25 14:30:05] INFO - 订单已执行: LONG 0.0046 BTC @ $43,260.50
```

---

## AI Agent 配置

### 宏观大局观

**更新频率**: 每小时

**分析内容**:
- Twitter 情绪（过去 1 小时）
- 宏观新闻（过去 24 小时）
- 市场主叙事识别
- 交易禁区声明

**输出示例**:
```json
{
  "global_sentiment": "neutral",
  "dominant_narrative": "美联储加息预期",
  "trading_bans": [],
  "recommended_stance": "neutral",
  "reasoning": "市场情绪平稳，无极端事件"
}
```

### 微观审批

**触发时机**: MTF 共振时

**分析内容**:
- 技术面报告（NLT 翻译）
- 宏观大局观（来自缓存）
- 外部情报摘要
- CoT 推理链

**输出示例**:
```json
{
  "decision": "BUY",
  "confidence": 0.85,
  "reasoning": "技术面突破确认，宏观环境支持",
  "risk_factors": ["短期超买", "阻力位 $44,000"],
  "key_catalyst": "成交量放大确认突破"
}
```

### 滑点硬拦截

**规则**:
- AI 思考期间价格变动 > 0.5% → 撤销
- AI 思考超过 5 秒 → 撤销

**示例**:
```log
[2026-02-25 14:30:00] INFO - 锁定触发价格: $43,256.78
[2026-02-25 14:30:05] WARNING - 滑点过大 (0.62% > 0.5%)，错过最佳击球区！
[2026-02-25 14:30:05] INFO - 交易已撤销
```

---

## 监控面板

### 启动监控

```bash
python scripts/start_monitoring.py
```

### 访问面板

打开浏览器访问: http://127.0.0.1:8765

### 监控指标

| 指标 | 说明 |
|------|------|
| 系统状态 | 运行时间、内存使用、CPU 使用率 |
| 交易统计 | 总交易次数、胜率、盈亏比 |
| 当前仓位 | 开仓价格、数量、未实现盈亏 |
| AI 状态 | 宏观情绪、交易禁令、最近决策 |
| 市场数据 | 实时价格、资金费率、OI |

### SSH 隧道访问（生产环境）

```bash
# 本地机器
ssh -L 8765:127.0.0.1:8765 user@your-server

# 访问 http://localhost:8765
```

---

## 常见问题

### Q1: AI Agent 响应慢怎么办？

**A**: 正常情况下 AI 审批需要 3-5 秒。如果超过 5 秒：
- 检查网络连接
- 检查 Anthropic API 额度
- 查看日志中的错误信息

### Q2: 没有 Twitter API 可以用吗？

**A**: 可以。系统会跳过 Twitter 情绪分析，只使用新闻数据。

### Q3: 如何禁用 AI Agent？

**A**: 在 `.env` 中设置 `ENABLE_AI_AGENT=false`，系统将使用纯技术面信号。

### Q4: Dry-Run 模式安全吗？

**A**: 完全安全。Dry-Run 模式不会执行任何实际交易，只会模拟。

### Q5: 如何调整滑点阈值？

**A**: 修改 `scripts/sniper_trader.py` 中的:
```python
self.slippage_guard = SlippageHardlock(threshold_pct=0.5, timeout_sec=5.0)
```

### Q6: 系统支持哪些交易对？

**A**: 理论上支持所有 Binance U 本位合约交易对。建议使用高流动性交易对:
- BTCUSDT
- ETHUSDT
- BNBUSDT

### Q7: 最小资金要求？

**A**:
- 测试网: 0 USDT
- 主网: 建议 ≥ 50 USDT（最小仓位约 10 USDT）

---

## 安全建议

1. **从小金额开始**: 首次主网交易建议 ≤ 10 USDT
2. **测试网验证**: 主网前务必在测试网验证完整流程
3. **API Key 保护**:
   - 设置 IP 白名单
   - 禁用提现权限
   - 定期轮换密钥
4. **监控日志**: 定期检查 `logs/` 目录下的日志文件
5. **预警通知**: 配置 Telegram/Discord 预警，及时获知交易状态

---

## 下一步

- 阅读完整架构文档: [ARCHITECTURE.md](ARCHITECTURE.md)
- 查看 v8.0 版本说明: [VERSION_v8.0.md](VERSION_v8.0.md)
- 了解配置参数: [CONFIGURATION.md](CONFIGURATION.md)
