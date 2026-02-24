# 快速开始指南

## 1. 安装 Python

首先确保您的系统已安装 Python 3.10 或更高版本。

**Windows**:
```powershell
# 从官网下载安装
# https://www.python.org/downloads/

# 或使用 scoop 安装
scoop install python

# 验证安装
python --version
```

**macOS/Linux**:
```bash
# 使用 homebrew
brew install python3

# 验证安装
python3 --version
```

## 2. 安装依赖

```bash
# 进入项目目录
cd E:\desktop\usdt

# 安装依赖
pip install -r requirements.txt
```

## 3. 配置环境变量

```bash
# 复制环境变量模板
cp .env.example .env

# 编辑 .env 文件，填入您的 API 密钥
```

### 获取 Binance API 密钥

1. 登录 Binance 账户
2. 进入 "API Management"
3. 创建新的 API Key
4. **重要**: 启用 IP 白名单
5. **重要**: 只授予交易权限，不授予提现权限

### 环境变量说明

| 变量 | 说明 | 示例 |
|------|------|------|
| `BINANCE_API_KEY` | Binance API 密钥 | `your_api_key_here` |
| `BINANCE_API_SECRET` | Binance API 密钥 | `your_secret_here` |
| `BINANCE_TESTNET` | 是否使用测试网 | `true` (开发时) |
| `MAX_POSITION_SIZE` | 最大仓位大小 | `1000` (USD) |
| `MAX_DAILY_LOSS` | 日损失限制 | `500` (USD) |
| `MAX_OPEN_POSITIONS` | 最大并发仓位 | `5` |

## 4. 运行测试

```bash
# 运行所有测试
python -m pytest tests/ -v

# 运行特定测试文件
python -m pytest tests/test_order_executor.py -v
python -m pytest tests/test_risk_manager.py -v
```

## 5. 启动自动交易

```bash
# 模拟运行（不下单）
python scripts/auto_trade.py

# 或设置环境变量
export DRY_RUN=true
python scripts/auto_trade.py
```

## 6. 紧急停止

创建紧急停止文件可以立即停止交易：

```bash
# Windows
type NUL > .emergency_stop

# Linux/macOS
touch .emergency_stop

# 移除紧急停止标志
rm .emergency_stop
```

## 项目结构

```
openclaw-crypto-trader/
├── src/
│   ├── exchange/
│   │   ├── order_executor.py    # 订单执行器
│   │   └── risk_manager.py       # 风险控制器
│   └── utils/
│       └── logger.py             # 日志工具
├── scripts/
│   └── auto_trade.py             # 自动交易主脚本
├── tests/                        # 测试文件
└── logs/                         # 日志输出
```

## 下一步

1. **测试网验证**: 先在 Binance 测试网验证所有功能
2. **小额测试**: 从小额开始（如 $10-$100）
3. **监控日志**: 关注 `logs/auto_trade.log`
4. **调整策略**: 根据实际情况调整风控参数

## Binance 测试网

- **测试网地址**: https://testnet.binance.vision/
- **获取测试币**: https://testnet.binance.vision/faucet
- **测试网 API**: https://testnet.binance.vision/en/api-keys

## 常见问题

### Q: 如何检查 Python 版本？
```bash
python --version
# 或
python3 --version
```

### Q: pip 安装依赖失败？
```bash
# 升级 pip
python -m pip install --upgrade pip

# 使用国内镜像源
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
```

### Q: 测试失败？
- 确保已安装依赖: `pip install -r requirements.txt`
- 检查网络连接
- 确认 Binance API 密钥配置正确

### Q: 如何添加自定义策略？
编辑 `scripts/auto_trade.py` 中的 `run_demo_strategy()` 方法，或者创建新的策略类。
