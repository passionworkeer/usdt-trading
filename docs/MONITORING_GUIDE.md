# v7.2 实时监控面板使用指南

## 概述

v7.2 版本新增了专业的 Web 监控面板，提供实时数据可视化，让你能够：

- 📊 **实时追踪仓位** - 查看当前持仓、盈亏、ROE
- 📈 **交易统计** - 胜率、总盈亏、平均盈亏
- 🔌 **WebSocket 状态** - 连接池健康度
- ⚖️ **OBI 拦截统计** - 订单簿失衡拦截记录
- 💻 **系统健康** - CPU、内存、磁盘使用率
- 📜 **事件日志** - 实时交易操作记录

---

## 快速启动

### 方法 1: 集成到 SniperTrader

监控面板已集成到 `sniper_trader.py`，只需设置环境变量：

```bash
# .env 文件
ENABLE_MONITORING=true
MONITORING_PORT=8765

# 启动交易系统
python scripts/sniper_trader.py
```

然后打开浏览器访问：**http://localhost:8765**

### 方法 2: 独立启动监控服务

```bash
# 启动监控面板（独立模式）
python scripts/start_monitoring.py
```

### 方法 3: 测试模式

```bash
# 模拟数据测试监控面板
python scripts/test_monitoring.py
```

---

## 环境变量配置

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `ENABLE_MONITORING` | `true` | 是否启用监控 |
| `MONITORING_PORT` | `8765` | 监控服务端口 |
| `MONITORING_HOST` | `0.0.0.0` | 监听地址（0.0.0.0 允许远程访问） |

---

## 功能详解

### 1. 当前持仓 (Current Positions)

显示内容：
- 交易对、方向、杠杆
- 入场价、当前价
- 未实现盈亏（P&L）
- ROE（Return on Equity）
- 止损价、止盈价、移动止盈价
- 持仓时间

**颜色标识：**
- 🟢 绿色 = 盈利（P&L > 0）
- 🔴 红色 = 亏损（P&L < 0）

### 2. 交易统计 (Trading Statistics)

显示内容：
- **Total Trades** - 总交易笔数
- **Win Rate** - 胜率（百分比）
- **Total P&L** - 总盈亏（USDT）
- **Avg P&L** - 平均盈亏（USDT）

### 3. WebSocket 状态 (WebSocket Status)

显示内容：
- **连接状态指示灯** - 绿色=已连接，红色=断开
- **Connections** - 总连接数
- **Messages** - 接收消息总数
- **Subscriptions** - 订阅的流数量
- **Errors** - 错误次数

### 4. OBI 拦截器 (OBI Interceptor)

显示内容：
- **Updates** - 订单簿更新次数
- **Rejects** - 拦截次数
- **Reject Rate** - 拦截率（百分比）
- **Symbols** - 追踪的交易对数量

### 5. 系统健康 (System Health)

显示内容：
- **CPU Usage** - CPU 使用率（进度条 + 百分比）
- **Memory Usage** - 内存使用率（进度条 + 百分比）
- **Disk Usage** - 磁盘使用率（进度条 + 百分比）

**颜色警告：**
- 🟢 < 70% = 正常
- 🟡 70-90% = 警告
- 🔴 > 90% = 危险

### 6. 事件日志 (Event Log)

显示内容：
- 实时交易操作日志
- 开仓/平仓事件
- 止损/止盈触发
- 系统警告

**图标标识：**
- 🟢 开仓（绿色边框）
- 🔴 平仓（红色边框）
- 🟡 警告（黄色边框）

---

## 实时更新频率

- **仓位数据** - 1 秒
- **交易统计** - 1 秒
- **WebSocket 状态** - 1 秒
- **OBI 统计** - 1 秒
- **系统健康** - 1 秒
- **事件日志** - 实时推送

---

## 远程访问

如果你想在其他设备上查看监控面板：

### 1. 修改监听地址

```bash
# .env 文件
MONITORING_HOST=0.0.0.0  # 允许远程访问
```

### 2. 配置防火墙

确保你的服务器防火墙允许 8765 端口：

```bash
# Windows (PowerShell)
New-NetFirewallRule -DisplayName "Sniper Monitor" -Direction Inbound -LocalPort 8765 -Protocol TCP -Action Allow

# Linux
sudo ufw allow 8765/tcp
```

### 3. 访问面板

在浏览器中输入：**http://YOUR_SERVER_IP:8765**

⚠️ **安全提示：** 生产环境建议使用反向代理（如 Nginx）+ SSL 加密。

---

## 架构说明

```
┌─────────────────────────────────────────────────────────┐
│                    Web 浏览器                            │
│  http://localhost:8765                                   │
└─────────────────────┬───────────────────────────────────┘
                      │ WebSocket
                      ↓
┌─────────────────────────────────────────────────────────┐
│              MonitoringServer (FastAPI)                  │
│  - WebSocket 推送                                        │
│  - 1 秒频率更新                                          │
│  - 事件日志广播                                          │
└─────────────────────┬───────────────────────────────────┘
                      ↓
┌─────────────────────────────────────────────────────────┐
│           MonitoringCollector (数据采集)                 │
│  - 仓位数据                                              │
│  - WebSocket 统计                                        │
│  - OBI 统计                                              │
│  - 系统健康指标                                          │
└─────────────────────┬───────────────────────────────────┘
                      ↓
┌─────────────────────────────────────────────────────────┐
│            SniperTrader (交易系统)                       │
│  - SniperPositionManager                                │
│  - MTFResonanceLock                                      │
│  - WebSocketPool                                         │
└─────────────────────────────────────────────────────────┘
```

---

## 常见问题

### Q1: 监控面板无法连接？

**A:** 检查以下几点：
1. 确认交易系统已启动
2. 确认端口未被占用（`netstat -ano | findstr 8765`）
3. 检查防火墙设置
4. 查看 `logs/sniper_trader.log` 日志

### Q2: 数据不更新？

**A:** 可能原因：
1. WebSocket 连接断开（查看浏览器控制台）
2. 交易系统主循环异常
3. 检查日志文件错误信息

### Q3: 如何修改更新频率？

**A:** 修改 `src/monitoring/monitoring_server.py` 第 345 行：

```python
# 当前：1 秒
await asyncio.sleep(1)

# 改为 5 秒（减少资源消耗）
await asyncio.sleep(5)
```

### Q4: 资源占用过高？

**A:** 可以：
1. 降低更新频率（见 Q3）
2. 减少事件日志大小（修改 `max_event_log`）
3. 关闭监控（`ENABLE_MONITORING=false`）

---

## 技术栈

| 组件 | 技术 | 版本 |
|------|------|------|
| Web 框架 | FastAPI | >= 0.109.0 |
| 服务器 | Uvicorn | >= 0.27.0 |
| WebSocket | 原生 Python | - |
| 系统监控 | psutil | >= 5.9.0 |
| 前端 | 原生 HTML/CSS/JS | - |

---

## 安全建议

1. **生产环境使用反向代理**
   ```nginx
   location /monitor/ {
       proxy_pass http://localhost:8765;
       proxy_http_version 1.1;
       proxy_set_header Upgrade $http_upgrade;
       proxy_set_header Connection "upgrade";
   }
   ```

2. **启用 SSL/TLS**
   ```bash
   # 使用 Let's Encrypt 免费证书
   certbot --nginx -d yourdomain.com
   ```

3. **限制访问 IP**
   ```python
   # 在 monitoring_server.py 添加 IP 白名单
   ALLOWED_IPS = ['127.0.0.1', '192.168.1.100']
   ```

---

**版本**: v7.2

**更新日期**: 2026-02-25

**作者**: Sniper Trading Team
