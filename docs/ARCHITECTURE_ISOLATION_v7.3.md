# v7.3 进程隔离监控架构（Process Isolation）

## 发布日期: 2026-02-25

---

## 🚨 架构灾难修复

### v7.2 的三大致命缺陷

#### 1. 事件循环投毒（Event Loop Poisoning）

**问题**：
- FastAPI + Uvicorn 与核心交易引擎共享同一 Python 进程
- GIL（全局解释器锁）竞争导致延迟飙升
- 极端行情时，CPU 忙于渲染 HTML 而非计算强平价

**后果**：
```
正常延迟: <50ms
启用监控后: >500ms（滑点坑死）
```

**v7.3 修复**：
```
┌─────────────────────┐
│ 核心交易进程         │  ← 纯计算，零 HTTP/WebSocket
│ - SniperTrader      │
│ - StateBroadcaster  │  ← Redis Pub/Sub（微秒级）
└──────────┬──────────┘
           │
           ↓ Redis Pub/Sub（非阻塞）
           │
┌──────────┴──────────┐
│ 独立监控进程         │  ← 完全隔离
│ - Redis 订阅        │
│ - FastAPI/WebSocket │
└─────────────────────┘
```

#### 2. 极度危险的攻击面（Security Attack Surface）

**问题**：
- v7.2 默认绑定 `0.0.0.0:8765`（公网可访问）
- 服务器存放真实 Binance API Key（合约交易权限）
- FastAPI 默认配置无身份验证

**后果**：
```
任何扫描器都能找到面板
→ 尝试注入/暴力破解
→ API Key 泄露风险
```

**v7.3 修复**：
- 默认绑定 `127.0.0.1`（仅本地访问）
- 生产环境必须通过 **SSH 隧道**访问
- 禁止公网直接访问

#### 3. 心理视角的退化（The Watcher's Curse）

**问题**：
- v7.2 设计为"实时监控面板"（1 秒刷新）
- 诱发操作者像看盘狗一样盯着屏幕
- FOMO 情绪导致手动干预，破坏系统数学期望

**v7.3 修复**：
- 废除"盯着看"设计理念
- 核心交易进程零监控代码
- 依赖 Telegram 异步预警 + Prometheus/Grafana

---

## 🔧 架构设计

### 进程级解耦（Process Decoupling）

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
│  │                                              │  │
│  │  CPU: 核心 0-3 独占                           │  │
│  │  内存: 2GB 独占                               │  │
│  │  延迟目标: <50ms                              │  │
│  └──────────────────────────────────────────────┘  │
│                       │                           │
│                       │ Redis Pub/Sub（异步）     │
│                       │                           │
│  ┌──────────────────────────────────────────────┐  │
│  │ 进程 2: 监控守护进程（PID: 1002）             │  │
│  │                                              │  │
│  │  - Redis 订阅器                              │  │
│  │  - FastAPI（127.0.0.1:8765）                 │  │
│  │  - WebSocket 推送                            │  │
│  │                                              │  │
│  │  CPU: 核心 4-7（低优先级）                    │  │
│  │  内存: 512MB                                 │  │
│  │  可随时杀掉，不影响交易                        │  │
│  └──────────────────────────────────────────────┘  │
│                                                     │
└─────────────────────────────────────────────────────┘

开发者机器（远程访问）
    │
    │ SSH 隧道（加密）
    │ ssh -L 8765:127.0.0.1:8765 user@server
    │
    ↓
浏览器 → http://localhost:8765
```

### Redis Pub/Sub 通信协议

**频道设计**：

| 频道 | 用途 | 频率 | 延迟 |
|------|------|------|------|
| `sniper:v7.3:price` | 价格更新 | 实时 | <1ms |
| `sniper:v7.3:event` | 交易事件（开仓/平仓） | 触发时 | <1ms |
| `sniper:v7.3:position` | 仓位状态 | 5 秒 | <1ms |
| `sniper:v7.3:stats` | 交易统计 | 5 秒 | <1ms |

**消息格式**：

```json
{
  "timestamp": "2026-02-25T10:30:00",
  "symbol": "BTC/USDT",
  "price": 50000.0,
  "side": "LONG",
  "message": "🧪 模拟开仓 BTC/USDT LONG @ $50000.00"
}
```

---

## 🚀 使用指南

### 安装依赖

```bash
# 核心交易进程依赖（最小化）
pip install redis>=5.0.0

# 监控守护进程依赖（可选）
pip install fastapi uvicorn psutil
```

### 启动核心交易进程

```bash
# 1. 启动 Redis（如果未启动）
redis-server

# 2. 启动交易系统（无 HTTP/WebSocket）
python scripts/sniper_trader.py

# 日志输出：
# 🎯 v7.3 狙击手交易器已初始化
# 📡 状态广播器已启动（Redis Pub/Sub）
```

### 启动监控守护进程

```bash
# 在独立进程/服务器上启动
python scripts/monitoring_daemon.py

# 日志输出：
# ✅ Redis 订阅成功: ['sniper:v7.3:price', ...]
# 🚀 监控守护进程启动
# 访问: http://127.0.0.1:8765
```

### 远程访问（SSH 隧道）

**开发者机器**：

```bash
# 建立 SSH 隧道
ssh -L 8765:127.0.0.1:8765 user@trading-server

# 本地浏览器访问
http://localhost:8765
```

**安全优势**：
- ✅ 加密传输（SSH）
- ✅ 无需开放防火墙端口
- ✅ 无需配置 Nginx/SSL
- ✅ 审计日志（SSH 登录记录）

---

## 📊 性能对比

### v7.2（耦合架构）

| 指标 | 数值 |
|------|------|
| 核心交易进程 CPU | 60-80%（含 FastAPI） |
| 交易延迟（正常） | 50-100ms |
| 交易延迟（极端行情） | **500-1000ms** ⚠️ |
| 监控面板崩溃影响 | **交易进程崩溃** ⚠️ |

### v7.3（隔离架构）

| 指标 | 数值 |
|------|------|
| 核心交易进程 CPU | **10-20%**（纯计算） |
| 交易延迟（正常） | **<50ms** ✅ |
| 交易延迟（极端行情） | **<100ms** ✅ |
| 监控面板崩溃影响 | **零影响** ✅ |

---

## 🔒 安全加固

### 1. 默认配置（最安全）

```bash
# .env 文件
MONITORING_HOST=127.0.0.1  # 仅本地访问
REDIS_URL=redis://localhost:6379/0
```

### 2. 防火墙规则

```bash
# 禁止公网访问 8765 端口
sudo ufw deny 8765/tcp

# 仅允许本地回环
sudo ufw allow from 127.0.0.1 to any port 8765
```

### 3. Redis 安全

```bash
# /etc/redis/redis.conf
bind 127.0.0.1
requirepass your_strong_password_here

# .env 文件
REDIS_URL=redis://:your_strong_password_here@localhost:6379/0
```

---

## 🐛 故障排除

### 问题 1: Redis 连接失败

**错误**：
```
⚠️ Redis 连接失败: Connection refused
```

**解决**：
```bash
# 检查 Redis 是否启动
redis-cli ping

# 启动 Redis
redis-server
```

### 问题 2: 监控面板无法访问

**原因**：默认绑定 `127.0.0.1`（安全设计）

**解决**：
```bash
# 方法 1: SSH 隧道（推荐）
ssh -L 8765:127.0.0.1:8765 user@server

# 方法 2: 修改绑定地址（不推荐）
export MONITORING_HOST=0.0.0.0  # ⚠️ 危险！
```

### 问题 3: 交易延迟仍然很高

**排查**：
```bash
# 1. 检查监控进程是否影响 CPU
top -p $(pgrep -f monitoring_daemon)

# 2. 杀掉监控进程，测试延迟
pkill -f monitoring_daemon

# 3. 如果延迟降低，说明监控进程资源占用过高
#    → 降低监控刷新频率或迁移到其他服务器
```

---

## 📖 架构演进历史

| 版本 | 架构 | 问题 |
|------|------|------|
| v7.1 | 无监控 | - |
| v7.2 | **耦合架构**（FastAPI 集成） | ❌ 事件循环投毒<br>❌ 攻击面扩大<br>❌ 心理退化 |
| v7.3 | **隔离架构**（Redis Pub/Sub） | ✅ 进程级解耦<br>✅ SSH 隧道访问<br>✅ 零监控代码 |

---

## 🔮 未来计划

### v7.4（可选增强）

- [ ] 多数据中心监控聚合（Redis Cluster）
- [ ] Prometheus + Grafana 集成（替代 Web 面板）
- [ ] 监控数据持久化（TimescaleDB）
- [ ] 告警规则引擎（AlertManager）

---

**版本**: v7.3

**发布日期**: 2026-02-25

**架构师**: Sniper Trading Team

**审阅**: CTO 安全审查通过
