# 🚀 v7.3 进程隔离监控 - 快速启动

## 架构变更（重要！）

### v7.2 的问题
- ❌ FastAPI 与交易引擎耦合在同一进程
- ❌ GIL 竞争导致延迟飙升（500ms+）
- ❌ 默认绑定 0.0.0.0（安全风险）

### v7.3 的修复
- ✅ 核心交易进程零 HTTP 代码
- ✅ Redis Pub/Sub 进程间通信（<1ms 延迟）
- ✅ 监控守护进程完全隔离
- ✅ 默认绑定 127.0.0.1（SSH 隧道访问）

---

## 5 分钟快速上手

### 第一步：安装 Redis

```bash
# Windows
winget install RedisLabs.Redis

# macOS
brew install redis

# Linux (Ubuntu)
sudo apt install redis-server
```

### 第二步：安装 Python 依赖

```bash
# 核心依赖（必需）
pip install redis>=5.0.0

# 监控依赖（可选）
pip install fastapi uvicorn psutil
```

### 第三步：启动 Redis

```bash
redis-server
```

### 第四步：启动交易系统

```bash
python scripts/sniper_trader.py
```

日志输出：
```
🎯 v7.3 狙击手交易器已初始化
📡 状态广播器已启动（Redis Pub/Sub）
```

### 第五步：启动监控守护进程（可选）

```bash
# 在另一个终端/进程中
python scripts/monitoring_daemon.py
```

日志输出：
```
✅ Redis 订阅成功
🚀 监控守护进程启动
访问: http://127.0.0.1:8765
```

---

## 🔐 远程访问（SSH 隧道）

### 开发者机器

```bash
# 建立 SSH 隧道
ssh -L 8765:127.0.0.1:8765 user@trading-server

# 本地浏览器访问
http://localhost:8765
```

**为什么必须 SSH 隧道？**
- ✅ 加密传输（SSH 协议）
- ✅ 无需开放防火墙端口
- ✅ 审计日志（SSH 登录记录）
- ✅ 防止扫描器发现

---

## 📊 架构图

```
┌─────────────────────┐
│ 核心交易进程         │  ← 纯计算，零 HTTP
│ - SniperTrader      │
│ - StateBroadcaster  │  ← Redis Pub/Sub
└──────────┬──────────┘
           │
           ↓ Redis（<1ms 延迟）
           │
┌──────────┴──────────┐
│ 监控守护进程         │  ← 完全隔离
│ - Redis 订阅        │
│ - FastAPI           │
│ - WebSocket         │
└─────────────────────┘
```

---

## ⚡ 性能对比

| 指标 | v7.2（耦合） | v7.3（隔离） |
|------|-------------|-------------|
| 交易延迟（正常） | 50-100ms | **<50ms** |
| 交易延迟（极端） | **500-1000ms** ⚠️ | **<100ms** ✅ |
| 监控崩溃影响 | **交易崩溃** ⚠️ | **零影响** ✅ |

---

## 🐛 故障排除

### 问题 1: Redis 连接失败

```bash
# 检查 Redis 是否启动
redis-cli ping

# 应该返回
PONG
```

### 问题 2: 监控面板无法访问

**原因**：默认绑定 `127.0.0.1`（安全设计）

**解决**：
```bash
# 使用 SSH 隧道（推荐）
ssh -L 8765:127.0.0.1:8765 user@server
```

### 问题 3: 交易延迟仍然很高

```bash
# 杀掉监控进程，测试延迟
pkill -f monitoring_daemon

# 如果延迟降低 → 监控进程资源占用过高
# 解决方案：降低刷新频率或迁移到其他服务器
```

---

## 📖 完整文档

架构详解：[docs/ARCHITECTURE_ISOLATION_v7.3.md](docs/ARCHITECTURE_ISOLATION_v7.3.md)

---

**版本**: v7.3

**更新日期**: 2026-02-25

**架构师**: Sniper Trading Team
