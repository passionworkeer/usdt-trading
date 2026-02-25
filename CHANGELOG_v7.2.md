# v7.2 实时监控面板 - 更新日志

## 发布日期: 2026-02-25

---

## 🎯 核心功能

### 实时监控面板

新增专业级 Web 监控面板，提供以下功能：

#### 1. 当前持仓追踪
- 实时显示所有持仓
- 入场价、当前价、盈亏、ROE
- 止损/止盈/移动止盈价格
- 持仓时间统计

#### 2. 交易统计
- 总交易笔数
- 胜率（百分比）
- 总盈亏
- 平均盈亏

#### 3. WebSocket 状态监控
- 连接状态指示灯
- 总连接数
- 消息接收数
- 订阅流数量
- 错误计数

#### 4. OBI 拦截统计
- 订单簿更新次数
- 拦截次数
- 拦截率
- 追踪交易对数量

#### 5. 系统健康监控
- CPU 使用率（实时进度条）
- 内存使用率（实时进度条）
- 磁盘使用率（实时进度条）

#### 6. 实时事件日志
- 开仓/平仓事件
- 止损/止盈触发
- 系统警告
- 自动滚动，保留最近 100 条

---

## 📁 新增文件

### 核心组件

| 文件 | 说明 |
|------|------|
| `src/monitoring/monitoring_collector.py` | 监控数据采集器 |
| `src/monitoring/monitoring_server.py` | WebSocket 监控服务器（含前端 HTML） |
| `src/monitoring/__init__.py` | 模块导出 |

### 脚本

| 文件 | 说明 |
|------|------|
| `scripts/start_monitoring.py` | 独立启动监控服务 |
| `scripts/test_monitoring.py` | 监控面板测试脚本 |

### 文档

| 文件 | 说明 |
|------|------|
| `docs/MONITORING_GUIDE.md` | 监控面板使用指南 |

---

## 🔧 修改文件

### 核心修改

| 文件 | 修改内容 |
|------|----------|
| `scripts/sniper_trader.py` | 集成监控服务 |
| `src/monitoring/__init__.py` | 导出新组件 |
| `requirements.txt` | 添加 FastAPI、Uvicorn、psutil |

---

## 🚀 使用方法

### 集成模式（推荐）

监控已集成到 `sniper_trader.py`：

```bash
# .env 文件
ENABLE_MONITORING=true
MONITORING_PORT=8765

# 启动交易系统
python scripts/sniper_trader.py
```

访问：http://localhost:8765

### 独立模式

```bash
# 独立启动监控服务
python scripts/start_monitoring.py
```

### 测试模式

```bash
# 模拟数据测试
python scripts/test_monitoring.py
```

---

## 🔌 技术架构

```
浏览器 (WebSocket)
    ↓
FastAPI Server (Uvicorn)
    ↓
MonitoringCollector (数据采集)
    ↓
SniperTrader (交易系统)
```

---

## 📊 数据流

1. **SniperTrader** 执行交易操作
2. **MonitoringCollector** 采集实时数据
3. **MonitoringServer** 1 秒频率推送
4. **浏览器** 实时更新显示

---

## 🎨 界面特性

- **响应式设计** - 支持桌面/平板/手机
- **实时更新** - 1 秒刷新频率
- **暗色主题** - 适合长时间监控
- **颜色标识** - 绿色=盈利，红色=亏损
- **进度条** - 直观显示系统资源

---

## ⚙️ 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `ENABLE_MONITORING` | `true` | 是否启用监控 |
| `MONITORING_PORT` | `8765` | 监控服务端口 |
| `MONITORING_HOST` | `0.0.0.0` | 监听地址 |

---

## 🔒 安全建议

1. 生产环境使用反向代理（Nginx）
2. 启用 SSL/TLS 加密
3. 配置 IP 白名单
4. 使用防火墙限制访问

---

## 🐛 已知限制

1. **单机监控** - 当前不支持多服务器聚合
2. **历史数据** - 事件日志仅保留最近 1000 条
3. **浏览器兼容** - 需要支持 WebSocket 的现代浏览器

---

## 🔮 未来计划

### v7.3 规划

- [ ] 历史盈亏曲线图
- [ ] 多交易对并发监控
- [ ] 移动端优化
- [ ] 告警推送集成
- [ ] 回测数据导入

---

## 📝 升级指南

### 从 v7.1 升级

```bash
# 1. 拉取代码
git pull

# 2. 安装新依赖
pip install fastapi uvicorn psutil

# 3. 更新 .env
echo "ENABLE_MONITORING=true" >> .env
echo "MONITORING_PORT=8765" >> .env

# 4. 重启系统
python scripts/sniper_trader.py

# 5. 访问监控面板
# http://localhost:8765
```

---

## 🙏 致谢

感谢以下开源项目：

- [FastAPI](https://fastapi.tiangolo.com/) - 现代化 Web 框架
- [Uvicorn](https://www.uvicorn.org/) - 高性能 ASGI 服务器
- [psutil](https://psutil.readthedocs.io/) - 系统监控库

---

**版本**: v7.2

**发布日期**: 2026-02-25

**Git Commit**: TBD
