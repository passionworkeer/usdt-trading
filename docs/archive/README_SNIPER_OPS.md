# v5.3 狙击手实盘操作手册（Sniper Ops Manual）

**OpenClaw Crypto Trader - 200 USDT 超小资金专用**

---

## 1. 快速部署（Linux 服务器）

### 1.1 克隆项目

```bash
git clone https://github.com/your-username/openclaw-crypto-trader.git
cd openclaw-crypto-trader
```

### 1.2 安装依赖

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 1.3 配置环境变量

```bash
cp .env.example .env
nano .env
```

**最小化配置模板：**

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

### 1.4 测试运行（Dry-Run 模式）

```bash
python scripts/sniper_trader.py
```

确认系统正常运行，MTF 共振检查、挂单逻辑、移动止盈等都正常。

---

## 2. Systemd 守护进程配置（7x24 运行）

### 2.1 创建 systemd 服务文件

```bash
sudo nano /etc/systemd/system/sniper-trader.service
```

**内容：**

```ini
[Unit]
Description=OpenClaw Sniper Trader v5.3
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/openclaw-crypto-trader
Environment="PATH=/home/ubuntu/openclaw-crypto-trader/venv/bin"
ExecStart=/home/ubuntu/openclaw-crypto-trader/venv/bin/python scripts/sniper_trader.py
Restart=always
RestartSec=10s  # 宕机后 10 秒重启
StandardOutput=append:/home/ubuntu/openclaw-crypto-trader/logs/sniper_trader.log
StandardError=append:/home/ubuntu/openclaw-crypto-trader/logs/sniper_trader_error.log

[Install]
WantedBy=multi-user.target
```

### 2.2 启动服务

```bash
# 重载 systemd 配置
sudo systemctl daemon-reload

# 启动服务
sudo systemctl start sniper-trader

# 开机自启
sudo systemctl enable sniper-trader

# 查看状态
sudo systemctl status sniper-trader

# 查看日志
tail -f logs/sniper_trader.log
```

### 2.3 停止 / 重启服务

```bash
# 停止
sudo systemctl stop sniper-trader

# 重启
sudo systemctl restart sniper-trader

# 禁用开机自启
sudo systemctl disable sniper-trader
```

---

## 3. 实盘前检查清单

**✅ 必须全部确认后才能切换到 LIVE 模式！**

### 3.1 API 配置

- [ ] Binance API Key 已创建（只交易权限，禁止提现）
- [ ] API Key IP 白名单已设置
- [ ] BINANCE_TESTNET=false（已切换到主网）
- [ ] API Key 已在主网测试过（小额测试）

### 3.2 资金配置

- [ ] CAPITAL=200（确认总资金）
- [ ] 账户余额 >= 200 USDT
- [ ] 已理解 50% 资金单次开仓风险

### 3.3 风控配置

- [ ] 已在 Dry-Run 模式运行至少 1 周
- [ ] 至少观察到 1 次 MTF 共振信号
- [ ] 确认挂单、动量代偿、移动止盈逻辑正常
- [ ] 已理解 12 小时时间止损机制

### 3.4 预警配置

- [ ] Telegram Bot 已创建并测试
- [ ] 或 Discord Webhook 已配置并测试
- [ ] 已收到测试预警消息

### 3.5 心理准备

- [ ] 已理解 200 USDT 可能归零
- [ ] 已理解高杠杆（20-50x）爆仓风险
- [ ] 已理解极低频（一周 0-2 次开仓）
- [ ] 已做好最坏打算

---

## 4. 常见报错排查指南

### 4.1 MIN_NOTIONAL 精度被拒绝

**错误信息：**

```
❌ 订单验证失败: 名义价值 $4.50 < MIN_NOTIONAL $5.00
```

**原因：**
- 资金太小，即使最大杠杆也无法满足 MIN_NOTIONAL

**解决方案：**

1. **手动调整杠杆**（临时方案）：
   ```bash
   # 在 .env 中增加 CAPITAL
   CAPITAL=250  # 从 200 增加到 250
   ```

2. **切换到更低价格币种**（推荐）：
   ```bash
   # 修改 scripts/sniper_trader.py 中的 watch_symbols
   self.watch_symbols = ['ETH/USDT', 'SOL/USDT']  # 移除 BTC/USDT
   ```

3. **检查 exchangeInfo**（调试）：
   ```python
   from src.exchange.exchange_info_manager import BinanceExchangeInfo
   info = BinanceExchangeInfo(testnet=True)
   info.fetch_symbol_info('BTC/USDT')
   # 查看输出中的 min_notional, max_leverage
   ```

### 4.2 API Rate Limit Exceeded (429)

**错误信息：**

```
⚠️ fetch_ticker 失败 (尝试 1/4): Rate Limit 超限
```

**原因：**
- 请求频率过高

**解决方案：**

1. **系统已自动重试**（指数退避）：
   - 第 1 次重试：2s
   - 第 2 次重试：4s
   - 第 3 次重试：8s

2. **增加检查间隔**：
   ```python
   # 在 scripts/sniper_trader.py 中修改
   await trader.run(check_interval_minutes=20)  # 从 15 分钟增加到 20 分钟
   ```

### 4.3 Connection Reset / Timeout

**错误信息：**

```
⚠️ fetch_ticker 失败: Connection error
```

**原因：**
- 网络不稳定
- Binance 服务器问题

**解决方案：**

1. **系统已自动重试**（最多 3 次）
2. **检查服务器网络**：
   ```bash
   ping fapi.binance.com
   curl https://fapi.binance.com/fapi/v1/ping
   ```
3. **检查防火墙**：
   ```bash
   sudo ufw status
   sudo ufw allow 443/tcp
   ```

### 4.4 仓位计算失败

**错误信息：**

```
❌ 资金不足，无法开仓 BTC/USDT
```

**原因：**
- 即使最大杠杆也无法满足 MIN_NOTIONAL

**解决方案：**

1. **检查资金**：
   ```bash
   # 在 .env 中确认
   CAPITAL=200
   ```

2. **检查交易对规则**：
   ```python
   from src.exchange.exchange_info_manager import BinanceExchangeInfo
   info = BinanceExchangeInfo(testnet=True)
   info.fetch_symbol_info('BTC/USDT')
   # 查看 min_notional, max_leverage
   ```

3. **切换到更便宜的币种**（推荐）：
   ```bash
   # ETH/USDT 或 SOL/USDT 的 MIN_NOTIONAL 更低
   ```

### 4.5 Telegram 预警发送失败

**错误信息：**

```
❌ Telegram 发送失败: 401 - Unauthorized
```

**原因：**
- Bot Token 错误
- Chat ID 错误

**解决方案：**

1. **检查 Bot Token**：
   ```bash
   # 在 Telegram 中找到 @BotFather
   # /newbot 创建新 Bot
   # 复制 Token 到 .env
   TELEGRAM_BOT_TOKEN=1234567890:ABCdefGHIjklMNOpqrsTUVwxyz
   ```

2. **获取 Chat ID**：
   ```bash
   # 在 Telegram 中找到 @userinfobot
   # 发送任意消息，获取 Chat ID
   TELEGRAM_CHAT_ID=123456789
   ```

3. **测试发送**：
   ```bash
   python src/utils/webhook_alerter.py
   ```

---

## 5. 实盘切换步骤（Dry-Run → LIVE）

### 5.1 最后确认

```bash
# 1. 停止 Dry-Run 服务
sudo systemctl stop sniper-trader

# 2. 修改 .env
nano .env
```

**修改以下配置：**

```bash
BINANCE_TESTNET=false  # 切换到主网
DRY_RUN=false  # 切换到实盘
```

### 5.2 重启服务

```bash
# 重启服务
sudo systemctl restart sniper-trader

# 实时监控日志
tail -f logs/sniper_trader.log
```

### 5.3 首次观察

- **前 1 小时**：观察是否有异常报错
- **前 24 小时**：观察是否有 MTF 共振信号
- **前 1 周**：观察是否有成交、止盈、止损

---

## 6. 监控与维护

### 6.1 日志监控

```bash
# 实时日志
tail -f logs/sniper_trader.log

# 搜索关键事件
grep "🎯" logs/sniper_trader.log  # 开仓
grep "💰" logs/sniper_trader.log  # 盈亏
grep "🚨" logs/sniper_trader.log  # 紧急平仓
```

### 6.2 系统监控

```bash
# 查看服务状态
sudo systemctl status sniper-trader

# 查看资源占用
htop

# 查看磁盘空间
df -h
```

### 6.3 定期检查

- **每天**：检查 Telegram 预警是否正常
- **每周**：检查日志中的错误
- **每月**：检查盈亏统计

---

## 7. 紧急情况处理

### 7.1 紧急停止

```bash
# 立即停止服务
sudo systemctl stop sniper-trader
```

### 7.2 手动平仓

如果系统故障，需要手动平仓：

1. 登录 Binance 合约账户
2. 找到当前持仓
3. 市价平仓

### 7.3 紧急联系

- **Binance 客服**：https://www.binance.com/zh-CN/support
- **Telegram 群组**：@your_telegram_group

---

## 8. 风险警告

⚠️ **v5.3 狙击手模式是高风险策略：**

1. **孤注一掷**: 50% 资金单次开仓
2. **高杠杆**: 20-50x 杠杆，爆仓风险极高
3. **爆仓即止损**: 不设传统止损，直接打到爆仓线
4. **极低频**: 一周可能只有 0-1 次开仓
5. **归零风险**: 200 USDT 可能归零

**适用场景:**
- ✅ 超小资金（< 500 USDT）
- ✅ 能承受归零风险
- ✅ 有耐心等待极端机会
- ✅ 理解高杠杆风险

**不适用场景:**
- ❌ 大资金（> 1000 USDT）
- ❌ 保守投资者
- ❌ 频繁交易者
- ❌ 不理解风险的新手

---

## 9. 核心参数速查表

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

---

## 10. 技术支持

- **GitHub Issues**: https://github.com/your-username/openclaw-crypto-trader/issues
- **文档**: [SNIPER_MODE_V5.0.md](./SNIPER_MODE_V5.0.md)
- **日志分析**: `logs/sniper_trader.log`

---

**版本**: v5.3

**更新日期**: 2026-02-25

**核心理念**: 宁可错过，不做错。孤注一掷，要么归零要么翻倍。

**这不是机枪，这是狙击步枪。**
