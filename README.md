# Sniper Trading System - 狙击手交易系统

**版本**: v8.0 AI Agent 双轨架构
**最后更新**: 2026-02-25

---

## 项目概述

这是一套军工级的超低频、极高置信度加密货币交易系统，专为 200 USDT 超小资金设计。

### 核心特性

| 特性 | 说明 |
|------|------|
| 🤖 **AI Agent 双轨架构** | 宏观大局观（每小时）+ 微观审批（3-5秒） |
| 🎯 **狙击手模式** | 一周 1-2 次开仓，MTF 三重共振确认 |
| ⚡ **超低延迟** | 进程级隔离，<50ms 交易延迟 |
| 🔒 **滑点硬拦截** | AI 思考期间价格变动 >0.5% 自动撤销 |
| 🧪 **Dry-Run** | 完整模拟模式，零风险测试 |
| 📡 **异步预警** | Telegram/Discord 实时通知 |

---

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置环境变量

```bash
# 复制配置模板
cp .env.example .env

# 编辑 .env 文件，填入以下必需配置：
# - BINANCE_API_KEY=your_key
# - BINANCE_API_SECRET=your_secret
# - ANTHROPIC_API_KEY=your_key  # v8.0 AI Agent 必需
# - ENABLE_AI_AGENT=true
```

### 3. 启动交易系统

交易日志、仓位状态、AI 市场报告及本地助手配置保存在本机，并已加入 `.gitignore`。运行时由脚本生成这些文件；仓库中的 `data/historical_klines/` 与 `scripts/trading_dashboard/data/` 保留市场 K 线数据。

```bash
# 启动核心交易进程
python scripts/sniper_trader.py
```

---

## 文档导航

### 📖 核心文档

| 文档 | 说明 |
|------|------|
| [USAGE.md](docs/USAGE.md) | 完整使用指南 |
| [ARCHITECTURE.md](docs/ARCHITECTURE.md) | 系统架构详解 |
| [CONFIGURATION.md](docs/CONFIGURATION.md) | 配置参数详解 |
| [VERSION_v8.0.md](docs/VERSION_v8.0.md) | v8.0 版本说明 |

### 🏗️ 架构文档

| 文档 | 说明 |
|------|------|
| [docs/SYSTEM_ARCHITECTURE.md](docs/SYSTEM_ARCHITECTURE.md) | 系统架构总览 |
| [docs/LATENCY_BUDGET.md](docs/LATENCY_BUDGET.md) | 延迟预算设计 |

### 🔧 运维文档

| 文档 | 说明 |
|------|------|
| [docs/MONITORING_GUIDE.md](docs/MONITORING_GUIDE.md) | 监控面板使用 |
| [docs/ENHANCED_GUIDE.md](docs/ENHANCED_GUIDE.md) | 高级使用指南 |

### 📦 归档文档

| 文档 | 说明 |
|------|------|
| [docs/archive/](docs/archive/) | 历史版本文档归档 |

---

## v8.0 AI Agent 架构概览

```
┌─────────────────────────────────────────────────────────────┐
│                   双轨混合智能体架构                        │
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
│  └───────────────────────────────────────────────────────┘  │
│                                                             │
│  ┌───────────────────────────────────────────────────────┐  │
│  │ 轨道 2: 同步微观审批（触发瞬间）                       │  │
│  │                                                       │  │
│  │  MTF Trigger                                      │     │
│  │  (放量突破)  ───→  锁定 Trigger_Price              │     │  │
│  │        │                       │                      │     │  │
│  │        ↓                       ↓                      │     │  │
│  │  Micro Data         NLT Data Translator           │     │  │
│  │  (Order Book)  ────→  (技术面报告)                │     │  │
│  │        │                       │                      │     │  │
│  │        └───────────────────────┼───────────────┐     │  │
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
│  └───────────────────────────────────────────────────────┘  │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## 项目结构

```
sniper-trading-system/
├── src/
│   ├── ai/                       # AI Agent 组件
│   │   ├── decision_engine.py    # Claude 决策引擎
│   │   ├── nlt_translator.py     # 自然语言数据翻译器
│   │   └── macro_oracle.py       # 宏观大局观生成器
│   ├── intelligence/             # 情报模块
│   │   └── web_scraper.py        # Twitter/新闻嗅探器
│   ├── exchange/                 # 交易所集成
│   │   ├── exchange_info_manager.py    # Binance 交易所信息
│   │   └── sniper_position_manager.py  # 仓位管理器
│   ├── quantitative/             # 量化策略
│   │   └── mtf_resonance_lock.py       # MTF 三重共振锁
│   ├── monitoring/               # 监控模块
│   │   ├── state_broadcaster.py        # Redis 状态广播
│   │   └── monitoring_daemon.py        # 独立监控守护进程
│   ├── execution/                # 执行层
│   │   └── slippage_hardlock.py        # 滑点硬拦截器
│   └── utils/                    # 工具函数
│       └── webhook_alerter.py          # Telegram/Discord 预警
│
├── scripts/                      # 执行脚本
│   ├── sniper_trader.py          # 主交易脚本（v8.0）
│   ├── monitoring_daemon.py      # 监控守护进程
│   └── start_monitoring.py       # 监控启动脚本
│
├── tests/                        # 测试文件
├── docs/                         # 文档
│   ├── archive/                  # 历史文档归档
│   └── ...
│
├── logs/                         # 日志目录
├── .env                          # 环境变量配置
├── .env.example                  # 环境变量模板
└── requirements.txt              # Python 依赖
```

---

## 交易流程

```
MTF 三重共振触发
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

## 版本历史

| 版本 | 日期 | 核心变更 |
|------|------|----------|
| v8.0 | 2026-02-25 | AI Agent 双轨架构（宏观+微观） |
| v7.3 | 2026-02-25 | 进程级解耦（Redis Pub/Sub） |
| v7.2 | 2026-02-25 | 实时监控面板（已废弃） |
| v7.1 | 2026-02-24 | 机构级工程交付 |
| v7.0 | 2026-02-24 | 华尔街微观执行层 |
| v6.0 | 2026-02-23 | 掠夺者模式 |
| v5.0 | 2026-02-23 | 狙击手模式初始版本 |

---

## 安全警告

⚠️ **生产环境必须遵守**：

1. **API Key 保护**：
   - 启用 IP 白名单
   - 只交易权限（禁止提现）
   - 定期轮换密钥

2. **从小金额开始**：先用 < 10 USDT 测试

3. **测试网验证**：主网前必须通过测试网验证

4. **Dry-Run 模式**：首次运行务必使用 `DRY_RUN=true`

---

## 许可证

MIT License

---

## 联系方式

- 项目维护：Sniper Trading Team
- 架构审查：CTO Office
- 安全审查：Security Team
