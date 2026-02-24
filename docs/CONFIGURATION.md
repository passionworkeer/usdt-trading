# OpenClaw Crypto Trader - 完整配置指南

## 项目概述

这是一个基于 AI 的全自动加密货币交易系统，支持：
- 接入 OpenClaw 进行自然语言控制
- 实时价格监控和自动交易
- Claude AI 驱动的智能决策
- 完整的风险管理系统

## 系统架构

```
用户/OpenClaw
     ↓
[MCP 工具接口]
     ↓
[价格监控服务] → [AI 决策引擎] → [风险控制器]
     ↓                                    ↓
[订单执行器] ← ← ← ← ← ← ← ← ← ← ← ← ← ←
     ↓
[Binance API]
```

## 安装步骤

### 1. 安装 Python 依赖

```bash
cd E:\desktop\usdt
D:\python\python.exe -m pip install -r requirements.txt
```

### 2. 配置环境变量

```bash
copy .env.example .env
```

编辑 `.env` 文件：

```bash
# Binance API（必需）
BINANCE_API_KEY=your_binance_api_key
BINANCE_API_SECRET=your_binance_secret
BINANCE_TESTNET=true  # 开发时使用 true

# Claude AI（可选，用于智能决策）
ANTHROPIC_API_KEY=your_anthropic_api_key

# 风控参数
MAX_POSITION_SIZE=1000
MAX_DAILY_LOSS=500
MAX_OPEN_POSITIONS=5
DEFAULT_STOP_LOSS_PCT=-5
DEFAULT_TAKE_PROFIT_PCT=15

# 监控配置
MONITOR_SYMBOLS=BTC/USDT,ETH/USDT
CHECK_INTERVAL=300

# AI 配置
ENABLE_AI=true
AUTO_TRADE=false  # 设为 true 启用自动交易
MIN_CONFIDENCE=0.7

# 日志
LOG_LEVEL=INFO
LOG_FILE=logs/trading_service.log
```

### 3. 运行测试

```bash
# 运行所有测试
D:\python\python.exe -m pytest tests/ -v

# 应该看到 27+ 个测试通过
```

## 运行方式

### 方式 1: 基础自动交易（演示模式）

仅监控价格，不自动交易：

```bash
D:\python\python.exe scripts/auto_trade.py
```

### 方式 2: AI 驱动的交易服务

启用 AI 分析，可选择是否自动执行：

```bash
# 仅监控和分析，不自动交易（推荐先测试）
D:\python\python.exe scripts/trading_service.py --symbols BTC/USDT ETH/USDT

# 启用自动交易（需谨慎！）
D:\python\python.exe scripts/trading_service.py --symbols BTC/USDT --auto-trade
```

### 方式 3: 作为 OpenClaw 插件

1. 将整个项目目录复制到 OpenClaw 的 skills 目录
2. 重启 OpenClaw
3. 通过自然语言控制：

```
初始化 Binance 连接
分析 BTC/USDT 市场状况
买入 $100 的 BTC
```

## 功能模块

### 1. 订单执行器 (`src/exchange/order_executor.py`)

- 市价单/限价单
- OCO 订单（止盈止损）
- 余额查询
- 价格查询

### 2. 风险控制器 (`src/exchange/risk_manager.py`)

- 仓位大小限制
- 日损失限制
- 并发仓位限制
- 交易频率控制
- 紧急停止

### 3. 价格监控 (`src/monitoring/price_monitor.py`)

- 实时价格更新
- 价格历史记录
- 价格警报
- 回调通知

### 4. AI 决策引擎 (`src/ai/decision_engine.py`)

- Claude API 集成
- 市场分析
- 交易建议生成
- 情绪分析
- 技术指标计算

### 5. MCP 工具接口 (`src/mcp_tools.py`)

18 个 OpenClaw 工具：
- `crypto_init` - 初始化
- `crypto_get_price` - 获取价格
- `crypto_buy` - 买入
- `crypto_sell` - 卖出
- `crypto_analyze` - AI 分析
- ... 等

## 安全配置

### Binance API 配置

1. 登录 Binance → API Management
2. 创建新 API Key
3. **重要安全设置**：
   - ✅ 启用 IP 白名单
   - ✅ 只授予 "Enable Reading" 和 "Enable Spot & Margin Trading"
   - ❌ **禁用** "Enable Withdrawals"
   - ❌ **禁用** "Enable Internal Transfer"

### 测试网使用

**强烈推荐**先在测试网测试：

1. 访问 https://testnet.binance.vision/
2. 注册并获取测试网 API Key
3. 获取测试币：https://testnet.binance.vision/faucet

## 监控和日志

### 查看实时日志

```bash
# Windows
type logs\trading_service.log

# 实时查看（需要安装 Get-Content 或 tail）
Get-Content logs\trading_service.log -Wait
```

### 日志级别

在 `.env` 中设置：
- `LOG_LEVEL=DEBUG` - 详细调试信息
- `LOG_LEVEL=INFO` - 一般信息（推荐）
- `LOG_LEVEL=WARNING` - 仅警告和错误

## 常见问题

### Q: 测试失败？
```bash
# 确保依赖已安装
D:\python\python.exe -m pip install -r requirements.txt

# 单独运行测试
D:\python\python.exe -m pytest tests/test_risk_manager.py -v
```

### Q: Claude API 调用失败？
- 检查 `ANTHROPIC_API_KEY` 是否正确
- 确保账户有余额
- 检查网络连接

### Q: Binance API 错误？
- 检查 API Key 和 Secret
- 确认 IP 白名单设置
- 确认时间同步（Binance 要求时间戳误差 < 1s）

### Q: 如何紧急停止？
```bash
# 创建紧急停止文件
type NUL > .emergency_stop

# 移除紧急停止
del .emergency_stop
```

## 下一步

1. **测试网验证** - 在测试网完整测试所有功能
2. **小额测试** - 主网小额（$10-$100）测试
3. **调整策略** - 根据表现调整风控参数
4. **监控日志** - 密切关注日志输出
5. **逐步增加** - 确认稳定后再增加资金

## 技术支持

- 查看日志：`logs/trading_service.log`
- 运行测试：`D:\python\python.exe -m pytest tests/ -v`
- 检查配置：确保 `.env` 文件正确

---

**⚠️ 风险警告**：
- 加密货币交易存在重大风险
- 本软件按"现状"提供，不保证盈利
- 永远不要投入超过您承受能力的资金
- 始终在测试网充分验证后再使用真实资金
