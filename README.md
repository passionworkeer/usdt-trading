# Sniper Trading System - 狙击手交易系统

**版本**: v7.3 进程隔离架构
**最后更新**: 2026-02-25

---

## 项目概述

这是一套军工级的超低频、极高置信度加密货币交易系统，专为 200 USDT 超小资金设计。

### 核心特性

| 特性 | 说明 |
|------|------|
| 🎯 **狙击手模式** | 一周 1-2 次开仓，三重共振确认 |
| ⚡ **超低延迟** | 进程级隔离，<50ms 交易延迟 |
| 🔒 **安全优先** | SSH 隧道访问，Redis Pub/Sub 通信 |
| 🧪 **Dry-Run** | 完整模拟模式，零风险测试 |
| 📡 **异步预警** | Telegram/Discord 实时通知 |

---

## 快速开始

### 1. 安装依赖

```bash
# 核心依赖（必需）
pip install redis>=5.0.0

# 监控依赖（可选）
pip install fastapi uvicorn psutil
```

### 2. 启动 Redis

```bash
redis-server
```

### 3. 配置环境变量

```bash
# .env 文件
BINANCE_TESTNET=true
DRY_RUN=true
CAPITAL=200
```

### 4. 启动交易系统

```bash
python scripts/sniper_trader.py
```

---

## 文档导航

### 📖 核心文档

| 文档 | 说明 |
|------|------|
| [README_SNIPER_OPS.md](README_SNIPER_OPS.md) | 狙击手模式操作指南 |
| [README_WINDOWS.md](README_WINDOWS.md) | Windows 环境设置指南 |
| [SNIPER_MODE_V5.0.md](SNIPER_MODE_V5.0.md) | v5.0 核心设计文档 |

### 🏗️ 架构文档

| 文档 | 说明 |
|------|------|
| [docs/ARCHITECTURE_ISOLATION_v7.3.md](docs/ARCHITECTURE_ISOLATION_v7.3.md) | v7.3 进程隔离架构 |
| [docs/SYSTEM_ARCHITECTURE.md](docs/SYSTEM_ARCHITECTURE.md) | 系统架构总览 |
| [docs/LATENCY_BUDGET.md](docs/LATENCY_BUDGET.md) | 延迟预算设计 |

### 🚀 快速启动

| 文档 | 说明 |
|------|------|
| [docs/QUICKSTART_ISOLATION_v7.3.md](docs/QUICKSTART_ISOLATION_v7.3.md) | v7.3 快速启动指南 |
| [docs/GETTING_STARTED.md](docs/GETTING_STARTED.md) | 新手入门指南 |
| [docs/CONFIGURATION.md](docs/CONFIGURATION.md) | 配置参数详解 |

### 🔧 运维文档

| 文档 | 说明 |
|------|------|
| [docs/ENHANCED_GUIDE.md](docs/ENHANCED_GUIDE.md) | 高级使用指南 |

---

## 项目结构

```
sniper-trading-system/
├── src/
│   ├── exchange/              # 交易所集成
│   │   ├── exchange_info_manager.py    # Binance 交易所信息
│   │   └── sniper_position_manager.py  # 仓位管理器
│   ├── quantitative/          # 量化策略
│   │   └── mtf_resonance_lock.py       # MTF 三重共振锁
│   ├── monitoring/            # 监控模块
│   │   ├── state_broadcaster.py        # Redis 状态广播
│   │   └── monitoring_daemon.py        # 独立监控守护进程
│   └── utils/                 # 工具函数
│       ├── webhook_alerter.py          # Telegram/Discord 预警
│       └── api_retry.py                # API 重试机制
│
├── scripts/                   # 执行脚本
│   ├── sniper_trader.py       # 主交易脚本
│   └── monitoring_daemon.py   # 监控守护进程
│
├── tests/                     # 测试文件
├── docs/                      # 文档
│   ├── archive/               # 历史文档归档
│   └── ...
│
├── logs/                      # 日志目录
├── .env                       # 环境变量配置
└── requirements.txt           # Python 依赖
```

---

## 架构概览

```
┌─────────────────────────────────────────────────────┐
│                    服务器（生产环境）                 │
├─────────────────────────────────────────────────────┤
│                                                     │
│  ┌──────────────────────────────────────────────┐  │
│  │ 进程 1: 核心交易引擎（PID: 1001）             │  │
│  │                                              │  │
│  │  - SniperTrader                              │  │
│  │  - MTFResonanceLock                          │  │
│  │  - StateBroadcaster（Redis Pub/Sub）         │  │
│  └──────────────────────────────────────────────┘  │
│                       │                           │
│                       │ Redis Pub/Sub（<1ms 延迟）  │
│                       │                           │
│  ┌──────────────────────────────────────────────┐  │
│  │ 进程 2: 监控守护进程（PID: 1002）             │  │
│  │                                              │  │
│  │  - Redis 订阅器                              │  │
│  │  - FastAPI（127.0.0.1:8765）                 │  │
│  └──────────────────────────────────────────────┘  │
│                                                     │
└─────────────────────────────────────────────────────┘
```

---

## 版本历史

| 版本 | 日期 | 核心变更 |
|------|------|----------|
| v7.3 | 2026-02-25 | 进程级解耦（Redis Pub/Sub） |
| v7.2 | 2026-02-25 | 实时监控面板（已废弃） |
| v7.1 | 2026-02-24 | 机构级工程交付 |
| v7.0 | 2026-02-24 | 华尔街微观执行层 |
| v6.0 | 2026-02-23 | 掠夺者模式 |
| v5.0 | 2026-02-23 | 狙击手模式初始版本 |

---

## 安全警告

⚠️ **生产环境必须遵守**：

1. **SSH 隧道访问**：禁止公网直接开放监控端口
   ```bash
   ssh -L 8765:127.0.0.1:8765 user@server
   ```

2. **API Key 保护**：
   - 启用 IP 白名单
   - 只交易权限（禁止提现）
   - 定期轮换密钥

3. **从小金额开始**：先用 < 10 USDT 测试

4. **测试网验证**：主网前必须通过测试网验证

---

## 许可证

MIT License

---

## 联系方式

- 项目维护：Sniper Trading Team
- 架构审查：CTO Office
- 安全审查：Security Team
