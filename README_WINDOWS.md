# v6.0 Windows 掠夺者模式部署指南（Predator Mode）

**OpenClaw Crypto Trader - 全景流动性雷达狙击手**

---

## 1. Windows 环境准备

### 1.1 安装 Python

```powershell
# 1. 下载 Python 3.10+
# https://www.python.org/downloads/windows/

# 2. 安装时勾选 "Add Python to PATH"

# 3. 验证安装
python --version
pip --version
```

### 1.2 克隆项目

```powershell
# 克隆项目
git clone https://github.com/your-username/openclaw-crypto-trader.git
cd openclaw-crypto-trader
```

### 1.3 创建虚拟环境

```powershell
# 创建虚拟环境
python -m venv venv

# 激活虚拟环境
.\venv\Scripts\activate

# 升级 pip
pip install --upgrade pip

# 安装依赖
pip install -r requirements.txt
```

### 1.4 安装额外依赖

```powershell
# WebSocket 支持
pip install websockets

# 系统锁（防止休眠）
# 无需额外依赖，使用 Windows API
```

---

## 2. 配置环境变量

### 2.1 创建配置文件

```powershell
# 复制示例配置
cp .env.example .env

# 编辑配置
notepad .env
```

### 2.2 最小化配置模板

```bash
# Binance API
BINANCE_API_KEY=your_binance_api_key
BINANCE_API_SECRET=your_binance_secret
BINANCE_TESTNET=true  # 开发时用 true，实盘改为 false

# 交易参数
CAPITAL=200  # 总资金（USDT）
DRY_RUN=true  # Dry-Run 模式（模拟），实盘改为 false

# Telegram 预警（可选）
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
TELEGRAM_CHAT_ID=your_telegram_chat_id

# Discord 预警（可选）
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...
```

---

## 3. Windows 守护进程配置

### 3.1 方法 1：Watchdog 脚本（推荐新手）

```powershell
# 直接运行 watchdog.bat
.\scripts\watchdog.bat
```

**特点：**
- 自动崩溃重启
- 自动禁止系统休眠
- 自动禁止网卡节能
- 简单易用

### 3.2 方法 2：NSSM Windows 服务（推荐进阶）

#### 步骤 1：下载 NSSM

```
https://nssm.cc/download
```

下载后解压，将 `nssm.exe` 放入 PATH 环境变量（如 `C:\Windows\System32`）

#### 步骤 2：注册服务

```powershell
# 以管理员身份运行
.\scripts\install_service.bat
```

#### 步骤 3：管理服务

```powershell
# 启动服务
nssm start OpenClawSniperTrader

# 停止服务
nssm stop OpenClawSniperTrader

# 重启服务
nssm restart OpenClawSniperTrader

# 查看状态
nssm status OpenClawSniperTrader

# 查看日志
type logs\service_out.log

# 删除服务
nssm remove OpenClawSniperTrader confirm
```

---

## 4. 测试运行（Dry-Run 模式）

### 4.1 手动测试

```powershell
# 激活虚拟环境
.\venv\Scripts\activate

# 运行狙击手
python scripts\sniper_trader.py
```

### 4.2 观察日志

```powershell
# 实时查看日志
Get-Content logs\sniper_trader.log -Wait -Tail 50
```

### 4.3 验证功能

- [ ] MTF 三重共振检查正常
- [ ] 挂单逻辑正常
- [ ] 移动止盈逻辑正常
- [ ] Telegram/Discord 预警正常
- [ ] 系统锁定正常（不休眠）

---

## 5. Windows 系统锁定

### 5.1 自动锁定（推荐）

运行 `watchdog.bat` 或注册服务后，系统会自动：

```python
# 禁止系统休眠
powercfg -change -standby-timeout-ac 0
powercfg -change -monitor-timeout-ac 0
powercfg -change -hibernate-timeout-ac 0

# 禁止网卡节能（需要管理员权限）
Get-NetAdapter | Set-NetAdapterPowerManagement -WakeOnMagicPacket Enabled
```

### 5.2 手动锁定（可选）

```powershell
# 禁用休眠
powercfg -h off

# 设置电源方案为 "高性能"
powercfg -setactive 8c5e7fda-e8bf-45a6-a6cc-4b3c3f300d00

# 禁用硬盘休眠
powercfg -setacvalueindex SCHEME_CURRENT SUB_DISK 01234567-8765-4321-8765-123456789012 0
powercfg -setdcvalueindex SCHEME_CURRENT SUB_DISK 01234567-8765-4321-8765-123456789012 0
```

---

## 6. 全景流动性雷达配置

### 6.1 启用雷达模式

编辑 `.env` 文件：

```bash
# 启用全景雷达（扫描前 30 个币种）
ENABLE_GLOBAL_SCREENER=true

# 扫描参数
SCREENER_TOP_N=30  # 扫描前 N 个币种
SCREENER_MIN_VOLUME=10000000  # 最小成交量（1000万 USDT）
SCREENER_CHECK_INTERVAL=15  # 检查间隔（分钟）
```

### 6.2 运行雷达模式

```powershell
# 激活虚拟环境
.\venv\Scripts\activate

# 运行雷达模式
python scripts\sniper_trader.py --screener
```

---

## 7. 实盘切换步骤（Dry-Run → LIVE）

### 7.1 最后确认

```powershell
# 1. 停止服务
nssm stop OpenClawSniperTrader

# 2. 编辑 .env
notepad .env
```

**修改以下配置：**

```bash
BINANCE_TESTNET=false  # 切换到主网
DRY_RUN=false  # 切换到实盘
```

### 7.2 重启服务

```powershell
# 重启服务
nssm restart OpenClawSniperTrader

# 实时监控日志
Get-Content logs\sniper_trader.log -Wait -Tail 100
```

---

## 8. Windows 防火墙配置

### 8.1 允许 Python 访问网络

```powershell
# 添加防火墙规则（管理员权限）
New-NetFirewallRule -DisplayName "OpenClaw Sniper Trader" -Direction Outbound -Program "venv\Scripts\python.exe" -Action Allow
```

### 8.2 允许 Binance API 端口

```powershell
# 允许 HTTPS（443）
New-NetFirewallRule -DisplayName "Binance API" -Direction Outbound -Protocol TCP -RemotePort 443 -Action Allow

# 允许 WebSocket（WSS）
# 通常使用 443 端口，无需额外配置
```

---

## 9. 常见问题排查

### 9.1 程序崩溃重启

**问题：** 程序意外退出

**解决方案：**
1. 检查日志：`logs\sniper_trader.log`
2. 检查错误日志：`logs\service_err.log`
3. Watchdog 会自动重启（10 秒延迟）

### 9.2 系统休眠

**问题：** Windows 自动休眠，程序停止运行

**解决方案：**
```powershell
# 检查电源设置
powercfg -q

# 禁用休眠
powercfg -h off

# 设置不休眠
powercfg -change -standby-timeout-ac 0
```

### 9.3 WebSocket 断线

**问题：** WebSocket 连接断开

**解决方案：**
- v6.0 已实现自动重连机制
- 检查网络连接：`ping fapi.binance.com`
- 检查防火墙设置

### 9.4 TLS 握手慢

**问题：** API 请求延迟高

**解决方案：**
- v6.0 已实现全局 Session Keep-Alive
- 首次请求会慢（TLS 握手）
- 后续请求复用连接（50ms 延迟）

### 9.5 系统时间不准确

**问题：** 系统时间不同步，导致签名失败

**解决方案：**
```powershell
# 同步系统时间
w32tm /resync

# 查看时间状态
w32tm /query /status
```

---

## 10. 监控与维护

### 10.1 日志监控

```powershell
# 实时日志
Get-Content logs\sniper_trader.log -Wait -Tail 50

# 搜索关键事件
Select-String -Path logs\sniper_trader.log -Pattern "🎯"  # 开仓
Select-String -Path logs\sniper_trader.log -Pattern "💰"  # 盈亏
Select-String -Path logs\sniper_trader.log -Pattern "🚨"  # 紧急平仓
```

### 10.2 服务监控

```powershell
# 查看服务状态
nssm status OpenClawSniperTrader

# 查看服务属性
nssm dump OpenClawSniperTrader

# 查看进程
Get-Process python
```

### 10.3 定期检查

- **每天**：检查 Telegram/Discord 预警是否正常
- **每周**：检查日志中的错误
- **每月**：检查盈亏统计

---

## 11. 紧急情况处理

### 11.1 紧急停止

```powershell
# 停止服务
nssm stop OpenClawSniperTrader

# 或强制结束进程
taskkill /F /IM python.exe
```

### 11.2 手动平仓

如果系统故障，需要手动平仓：

1. 登录 Binance 合约账户
2. 找到当前持仓
3. 市价平仓

---

## 12. 性能优化

### 12.1 连接池配置

编辑 `src/utils/session_manager.py`：

```python
connector = aiohttp.TCPConnector(
    limit=100,  # 最大连接数
    limit_per_host=30,  # 每个主机最大连接数
    keepalive_timeout=60,  # Keep-Alive 超时
)
```

### 12.2 WebSocket 心跳配置

编辑 `src/exchange/websocket_pool.py`：

```python
client = BinanceWebSocketClient(
    ping_interval=30.0,  # Ping 间隔（秒）
    ping_timeout=10.0,   # Ping 超时（秒）
)
```

---

## 13. 安全注意事项

### 13.1 API Key 管理

- [ ] 只授予交易权限，禁止提现
- [ ] 设置 IP 白名单
- [ ] 定期轮换 API Key
- [ ] 不要在代码中硬编码 Key

### 13.2 文件权限

```powershell
# 限制 .env 文件权限（仅管理员可写）
icacls .env /inheritance:r
icacls .env /grant:r "$env:USERNAME:F"
icacls .env /grant:r "Administrators:F"
```

### 13.3 防病毒软件

添加排除规则：
- 排除项目目录：`E:\desktop\usdt`
- 排除 Python 进程：`python.exe`

---

## 14. 核心参数速查表

| 参数 | 默认值 | 说明 |
|------|--------|------|
| CAPITAL | 200 | 总资金（USDT） |
| POSITION_RATIO | 50% | 单次开仓比例 |
| MAX_POSITIONS | 1 | 最大并发仓位 |
| TARGET_RR_RATIO | 1:5 | 目标盈亏比 |
| CHECK_INTERVAL | 15 min | 扫描间隔 |
| ORDER_TTL | 1 hour | 挂单超时 |
| MOMENTUM_OVERRIDE | 5 min | 动量代偿窗口 |
| TRAILING_ROE_TRIGGER | 50% | 移动止盈启动阈值 |
| TRAILING_ROE_DISTANCE | 20% | 移动止盈回撤 |
| TIME_STOP_HOURS | 12 | 时间止损（小时） |
| TIME_STOP_ROE_THRESHOLD | 20% | 时间止损 ROE 阈值 |
| SCREENER_TOP_N | 30 | 全景雷达扫描数量 |
| SCREENER_MIN_VOLUME | 10M | 最小成交量（USDT） |
| SCREENER_CHECK_INTERVAL | 15 min | 雷达扫描间隔 |
| WEBSOCKET_PING_INTERVAL | 30 sec | WebSocket Ping 间隔 |
| WEBSOCKET_PING_TIMEOUT | 10 sec | WebSocket Ping 超时 |
| SESSION_KEEP_ALIVE | 60 sec | TLS Keep-Alive 超时 |

---

## 15. 版本更新日志

### v6.0 (2026-02-25)

**新增功能：**
- ✅ Windows 守护进程（NSSM & Watchdog）
- ✅ WebSocket 自动重连池（24 小时死亡陷阱防御）
- ✅ 全景流动性雷达（Top 30 币种并发扫描）
- ✅ 全局 Session Keep-Alive（TLS 握手延迟消除）

**修复问题：**
- ✅ Windows 休眠导致程序停止
- ✅ WebSocket 24 小时强制断线
- ✅ 单一币种视野限制
- ✅ TLS 握手重复延迟（50-100ms）

**性能优化：**
- ⚡ TCP 连接复用
- ⚡ DNS 缓存（5 分钟）
- ⚡ 连接池管理（100 连接）
- ⚡ 并发扫描（30 币种）

---

**版本**: v6.0

**更新日期**: 2026-02-25

**核心理念**: 全景视野，伺机而动。谁先暴露破绽，狙击枪就对准谁。

**这是掠夺者的时代。** 🦅
