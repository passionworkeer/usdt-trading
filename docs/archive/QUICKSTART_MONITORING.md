# 🎯 v7.2 实时监控面板 - 快速启动

## 5 分钟快速上手

### 第一步：安装依赖

```bash
pip install fastapi uvicorn psutil
```

### 第二步：启动监控面板

#### 方法 A：集成模式（推荐）

```bash
# 启动交易系统（监控自动启动）
python scripts/sniper_trader.py
```

访问：http://localhost:8765

#### 方法 B：测试模式

```bash
# 模拟数据测试监控面板
python scripts/test_monitoring.py
```

访问：http://localhost:8765

---

## 📊 你将看到什么？

### 当前持仓
- 交易对、方向、杠杆
- 入场价、当前价
- **实时盈亏**（绿色=赚，红色=亏）
- ROE（Return on Equity）

### 交易统计
- 总交易笔数
- 胜率（百分比）
- 总盈亏

### WebSocket 状态
- 连接状态指示灯
- 消息接收数

### 系统健康
- CPU 使用率（进度条）
- 内存使用率（进度条）
- 磁盘使用率（进度条）

### 事件日志
- 开仓/平仓记录
- 止损/止盈触发
- 实时滚动

---

## 🎨 界面预览

```
┌─────────────────────────────────────────────────────────────┐
│  🎯 Sniper Trading Monitor                                 │
├─────────────────────────────────────────────────────────────┤
│  当前持仓                    │  交易统计                     │
│  ┌───────────────────────┐    │  ┌───────────────────────┐  │
│  │ BTC/USDT LONG 20x     │    │  │ Total Trades: 10      │  │
│  │ Entry: $50,000        │    │  │ Win Rate: 60%         │  │
│  │ Current: $51,500      │    │  │ Total P&L: +$120      │  │
│  │ P&L: +$30.00 ✅       │    │  └───────────────────────┘  │
│  │ ROE: +30.00% ✅       │    │                             │
│  └───────────────────────┘    │  WebSocket 状态              │
│                               │  ┌───────────────────────┐  │
│  系统健康                     │  │ ✅ Connected          │  │
│  CPU:     ███████░░ 70%      │  │ Connections: 5         │  │
│  Memory:  ████░░░░░ 40%      │  │ Messages: 12345        │  │
│  Disk:    ████░░░░░ 45%      │  └───────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

---

## 🔧 配置选项

### 修改端口

```bash
# .env 文件
MONITORING_PORT=9999

# 访问
# http://localhost:9999
```

### 远程访问

```bash
# .env 文件
MONITORING_HOST=0.0.0.0

# 访问
# http://YOUR_SERVER_IP:8765
```

### 禁用监控

```bash
# .env 文件
ENABLE_MONITORING=false
```

---

## 📱 移动端访问

1. 确保手机和电脑在同一 Wi-Fi
2. 设置 `MONITORING_HOST=0.0.0.0`
3. 浏览器输入：`http://YOUR_COMPUTER_IP:8765`

---

## 🐛 故障排除

### 问题 1: 无法访问面板

**解决：**
1. 确认交易系统已启动
2. 检查端口是否占用：`netstat -ano | findstr 8765`
3. 检查防火墙设置

### 问题 2: 数据不更新

**解决：**
1. 检查浏览器控制台（F12）
2. 查看 `logs/sniper_trader.log`
3. 刷新页面

### 问题 3: 端口被占用

**解决：**
```bash
# 修改端口
MONITORING_PORT=8766
```

---

## 📖 完整文档

详细使用指南：[docs/MONITORING_GUIDE.md](docs/MONITORING_GUIDE.md)

更新日志：[CHANGELOG_v7.2.md](CHANGELOG_v7.2.md)

---

**版本**: v7.2

**更新日期**: 2026-02-25

**Git Commit**: `fae4a27`
