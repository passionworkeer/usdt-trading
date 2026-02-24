# 增强版 AI 交易系统 - 完整指南

## 系统概述

这是一个全自动、多因素驱动的 AI 加密货币交易系统。

### 核心特性

1. **多策略技术分析**
   - RSI 超买超卖
   - 移动平均线交叉
   - 布林带突破
   - 成交量突破
   - 网格交易

2. **市场情报抓取**
   - Twitter/X 情绪分析
   - 加密货币新闻
   - 鲸鱼大额转账追踪

3. **AI 深度分析**
   - Claude API 驱动
   - 多因素整合决策
   - 风险评估

4. **风险控制**
   - 仓位限制
   - 日损失限制
   - 自动止损止盈

## 测试结果

```
42 个测试，41 个通过 ✅
1 个需要 API key
```

## 快速开始

### 1. 安装依赖

```bash
cd E:\desktop\usdt
D:\python\python.exe -m pip install -r requirements.txt
```

### 2. 配置 API Keys

编辑 `.env` 文件：

```bash
# 必需
BINANCE_API_KEY=your_key
BINANCE_API_SECRET=your_secret

# AI 分析（强烈推荐）
ANTHROPIC_API_KEY=your_claude_key

# 市场情报（可选但推荐）
TWITTER_BEARER_TOKEN=your_token      # Twitter API
NEWS_API_KEY=your_key                # NewsAPI.org
WHALE_ALERT_API_KEY=your_key         # Whale Alert
```

### 3. 运行服务

**基础模式**（仅监控和分析）：
```bash
D:\python\python.exe scripts/enhanced_trading_service.py --symbols BTC/USDT ETH/USDT
```

**自动交易模式**（谨慎使用！）：
```bash
D:\python\python.exe scripts/enhanced_trading_service.py --symbols BTC/USDT --auto-trade
```

## 运行示例输出

```
======================================================================
综合分析: BTC/USDT @ $95,234.56
======================================================================
📊 技术分析...
  综合信号: BUY (强度: 0.72)
  原因: Combined: 0.68 buy vs 0.22 sell
  [RSI Strategy] buy (0.85): RSI: 28.45 - Oversold (< 30)
  [MA Cross Strategy] hold (0.00): Short MA: 94500, Long MA: 95800 - Neutral
  [Bollinger Bands Strategy] buy (0.80): Price at lower band (potential bounce)
  [Volume Breakout Strategy] buy (0.60): Volume breakout UP (2.5x avg, +3.2%)

📱 市场情报...
  Twitter 情绪: 0.68 (看涨)
  新闻情绪: 0.62
  鲸鱼净流向: $15,000,000 (流出交易所=看涨)
  综合情绪: BULLISH (置信度: 0.75)

🤖 AI 深度分析...
  AI 决策: BUY
  置信度: 0.85
  风险等级: medium
  分析: Strong buy signal with oversold RSI and positive sentiment...

======================================================================
最终决策: BUY
决策强度: 0.78
决策理由: 技术看涨, 情绪bullish, AI buy
======================================================================

💰 执行买入: 0.010517 BTC/USDT @ $95,234.56
✅ 订单已创建: 12345
🎯 止损止盈已设置: SL=$90,472.83, TP=$109,519.74
```

## 决策流程

```
价格更新
    ↓
1. 技术分析（30%权重）
   - RSI 策略
   - MA 交叉策略
   - 布林带策略
   - 成交量策略
    ↓
2. 市场情报（40%权重）
   - Twitter 情绪（25%）
   - 新闻分析（15%）
   - 鲸鱼活动（15%）
    ↓
3. AI 分析（30%权重）
   - Claude API
   - 综合所有因素
    ↓
4. 风控检查
   - 仓位限制
   - 日损失限制
   - 置信度验证
    ↓
5. 执行交易
   - 下单
   - 设置止损止盈
   - 记录日志
```

## 策略说明

### RSI 策略
- 超卖区（RSI < 30）→ 买入
- 超买区（RSI > 70）→ 卖出
- 权重: 1.0

### MA 交叉策略
- 短期 MA > 长期 MA 2% → 买入
- 短期 MA < 长期 MA 2% → 卖出
- 权重: 0.8

### 布林带策略
- 价格触及下轨 → 买入
- 价格触及上轨 → 卖出
- 权重: 0.9

### 成交量突破策略
- 放量上涨（成交量 > 2倍平均） → 买入
- 放量下跌 → 卖出
- 权重: 0.7

## API 获取指南

### Twitter API
1. 访问 https://developer.twitter.com/
2. 申请 Essential access（免费）
3. 创建项目获取 Bearer Token

### News API
1. 访问 https://newsapi.org/
2. 注册账户
3. 获取 API Key（免费版 100 请求/天）

### Whale Alert API
1. 访问 https://docs.whale-alert.io/
2. 注册获取 API Key
3. 免费版 100 请求/小时

### Claude API
1. 访问 https://console.anthropic.com/
2. 注册并获取 API Key
3. 按使用量付费

## 风险管理

### 默认配置
- 最大仓位: $1,000
- 日损失限制: $500
- 最大并发仓位: 5
- 止损: -5%
- 止盈: +15%

### 紧急停止
```bash
# 创建紧急停止文件
type NUL > .emergency_stop

# 移除
del .emergency_stop
```

## 性能优化

### 调整检查间隔
```bash
# 更频繁检查（60秒）
CHECK_INTERVAL=60

# 较少检查（5分钟）
CHECK_INTERVAL=300
```

### 调整置信度阈值
```bash
# 更严格（减少交易）
MIN_CONFIDENCE=0.8

# 更宽松（更多交易）
MIN_CONFIDENCE=0.6
```

## 监控和日志

### 查看实时日志
```bash
type logs\enhanced_trading.log
```

### 日志级别
- `DEBUG` - 详细调试
- `INFO` - 一般信息（推荐）
- `WARNING` - 仅警告

## 常见问题

**Q: 没有 Twitter API 怎么办？**
A: 系统会自动使用模拟数据进行测试。

**Q: 可以只用技术分析吗？**
A: 可以，设置 `ENABLE_AI=false` 和 `ENABLE_TWITTER=false`。

**Q: 如何回测策略？**
A: 系统记录所有决策到 `decision_history`，可以事后分析。

**Q: 自动交易安全吗？**
A: 始终在测试网和小额资金充分验证后再使用真实资金！

## 项目文件结构

```
E:\desktop\usdt\
├── scripts/
│   ├── auto_trade.py              # 基础版本
│   ├── trading_service.py         # 标准版本
│   └── enhanced_trading_service.py # 增强版本 ⭐
├── src/
│   ├── strategies/                # 交易策略
│   ├── data_sources/              # 数据抓取
│   ├── ai/                        # AI 分析
│   ├── monitoring/                # 价格监控
│   └── exchange/                  # 交易执行
└── tests/                         # 42 个测试
```

---

⚠️ **重要提醒**:
1. 先在测试网验证
2. 从小额开始（$10-$100）
3. 密切监控日志
4. 理解每一项配置
5. 永远不要投入超过承受能力的资金
