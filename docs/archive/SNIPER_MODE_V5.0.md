# v5.0 狙击手模式（Sniper Mode）- 200 USDT 超小资金专用

## 背景

v4.1 的高频架构虽然技术漂亮，但完全搞错了业务场景！

**200 USDT 超小资金需要的是：**
- ❌ 不是高频机枪（需要狙击步枪）
- ❌ 不怕爆仓（爆仓线 = 止损线）
- ❌ 不需要微观指标（容易被操纵）
- ✅ 极低频、极高置信度
- ✅ 高杠杆孤注一掷
- ✅ 1:5 盈亏比（要么归零，要么翻倍）

## v5.0 核心改进

### 1. 彻底解决 MIN_NOTIONAL 拦截死局

**问题：**
- 200 USDT 资金很小
- BTC 价格 50000 USDT
- MIN_NOTIONAL 通常是 5-10 USDT
- 传统 1% 风险模型根本无法开仓

**解决方案：**
- ✅ 基于 `exchangeInfo` 的精度处理
- ✅ 动态计算最小可开仓数量
- ✅ 自动调整杠杆满足 MIN_NOTIONAL
- ✅ 针对超小资金改为 20%-50% 高比例开仓

**核心代码：**
```python
# src/exchange/exchange_info_manager.py

def calculate_min_quantity_for_capital(self, symbol: str, capital: float,
                                      leverage: int = 20) -> Tuple[float, float, bool]:
    """
    v5.0 核心：根据资金计算最小可开仓数量

    策略：
    1. 计算最大可用名义价值 = capital × leverage
    2. 计算最小数量满足 MIN_NOTIONAL
    3. 如果资金不足，自动提高杠杆
    """
    info = self.fetch_symbol_info(symbol)
    max_notional = capital * leverage

    # 检查：最大名义价值是否满足 MIN_NOTIONAL
    if max_notional < info.min_notional:
        # 尝试提高杠杆
        while leverage < info.max_leverage:
            leverage += 5
            max_notional = capital * leverage
            if max_notional >= info.min_notional:
                break

        # 如果达到最大杠杆仍不足
        if max_notional < info.min_notional:
            logger.error(f"❌ 资金不足！")
            return 0, 0, False

    # 计算数量（向下取整到 step_size）
    quantity = max_notional / current_price
    quantity = self.round_quantity(symbol, quantity)

    return quantity, leverage, True
```

### 2. 封杀微观假信号 - MTF 三重共振锁

**问题：**
- 分钟级技术指标容易被操纵
- 假信号太多，200U 经不起频繁止损

**解决方案 - MTF 三重共振锁：**
- ✅ 关闭所有分钟级微观指标
- ✅ 开仓必须同时满足三个条件，缺一不可
- ✅ 宁可错过行情，不做假信号

**三重条件：**

1. **4H 宏观趋势确认**
   - EMA 20 vs EMA 50
   - 避免逆势抄底

2. **极端 Open Interest/资金费率偏离**
   - 极度正费率（> 0.05%）→ 多头过度拥挤 → 做空信号
   - 极度负费率（< -0.05%）→ 空头过度拥挤 → 做多信号

3. **15m 精准放量猎杀**
   - 成交量 >= 2 倍平均
   - 价格突破 > 0.5%
   - 精确入场点

**核心代码：**
```python
# src/quantitative/mtf_resonance_lock.py

async def check_triple_resonance(self, symbol: str) -> MTFSignal:
    """
    v5.0 核心：检查三重共振

    规则：
    - 必须同时满足三个条件
    - 任何一环不满足 = 无信号
    """
    # 并发获取三个条件
    trend_4h, reason_4h = await self.fetch_4h_trend(symbol)
    funding_oi, reason_funding = await self.fetch_funding_and_oi(symbol)
    volume_15m, reason_volume = await self.fetch_15m_volume_spike(symbol)

    # 统计信号方向
    long_votes = sum(1 for s in signals if s == 1)
    short_votes = sum(1 for s in signals if s == -1)

    # 判断是否锁定（三重共振）
    if long_votes == 3:  # 全部做多
        final_signal = 1
        confidence = 1.0
        is_locked = True
    elif short_votes == 3:  # 全部做空
        final_signal = -1
        confidence = 1.0
        is_locked = True
    else:
        final_signal = 0
        is_locked = False

    return MTFSignal(
        symbol=symbol,
        signal=final_signal,
        confidence=confidence,
        is_locked=is_locked
    )
```

### 3. 高杠杆孤注一掷模型

**策略：**
- ✅ 每次用 50% 资金开仓
- ✅ 爆仓线 = 止损线（2% 距离）
- ✅ 目标盈利 = 5 × 止损距离（10% 盈利）
- ✅ 同时最多持有 1 个仓位

**核心代码：**
```python
# src/exchange/sniper_position_manager.py

def calculate_sniper_position(self, symbol: str, capital: float,
                              side: str, entry_price: float,
                              stop_distance_pct: float = 0.02):
    """
    计算狙击手仓位（孤注一掷模型）

    策略：
    1. 使用 50% 资金作为保证金
    2. 自动调整杠杆满足 MIN_NOTIONAL
    3. 爆仓线距离 = 止损距离（2%）
    4. 目标盈利 = 5 × 止损距离（10%）
    """
    # 计算可用保证金（50% 资金）
    margin = capital * 0.5

    # 自动计算杠杆和数量
    quantity, leverage, feasible = self.exchange_info.calculate_min_quantity_for_capital(
        symbol, margin, leverage=20
    )

    # 计算爆仓线（= 止损线）
    if side == 'LONG':
        stop_loss_price = entry_price * (1 - stop_distance_pct)
        take_profit_price = entry_price * (1 + stop_distance_pct * 5.0)

    return SniperPosition(
        symbol=symbol,
        side=side,
        entry_price=entry_price,
        quantity=quantity,
        leverage=leverage,
        stop_loss_price=stop_loss_price,
        take_profit_price=take_profit_price,
    )
```

### 4. 极高盈亏比追踪机制

**策略：**
- ✅ 目标盈亏比 1:5
- ✅ 盈利超过 10% 启动移动止盈
- ✅ 移动距离 = 当前价格 × 5%
- ✅ 永远只向上移动，不向下移动

**核心代码：**
```python
# src/exchange/sniper_position_manager.py

def update_trailing_stop(self, symbol: str, current_price: float,
                        trailing_distance_pct: float = 0.05):
    """
    v5.0 核心：更新移动止盈（Trailing Stop）

    逻辑：
    - 只有盈利超过 10% 才启动移动止盈
    - 移动距离 = 当前价格 × 5%
    - 永远只向上移动，不向下移动
    """
    position = self.positions.get(symbol)

    # 计算当前盈亏
    unrealized_pnl_pct = (current_price - position.entry_price) / position.entry_price

    # 只有盈利超过 10% 才启动
    if unrealized_pnl_pct < 0.1:
        return

    # 计算新的移动止盈价格
    if position.side == 'LONG':
        new_trailing_stop = current_price * (1 - trailing_distance_pct)

        # 只向上移动，不向下
        if position.trailing_stop_price is None or new_trailing_stop > position.trailing_stop_price:
            position.trailing_stop_price = new_trailing_stop
            logger.info(f"🔼 移动止盈上调: ${new_trailing_stop:.2f}")
```

## 使用示例

### 1. 初始化 exchangeInfo 管理器

```python
from src.exchange.exchange_info_manager import BinanceExchangeInfo

# 创建 exchangeInfo 管理器
info_manager = BinanceExchangeInfo(testnet=True)

# 测试 200 USDT 能否开 BTC/USDT
capital = 200  # USDT

quantity, leverage, feasible = info_manager.calculate_min_quantity_for_capital(
    'BTC/USDT', capital, leverage=20
)

if feasible:
    print(f"✅ 可行！")
    print(f"  杠杆: {leverage}x")
    print(f"  数量: {quantity:.6f} BTC")
else:
    print(f"❌ 不可行！资金不足")
```

### 2. 计算狙击手仓位

```python
from src.exchange.sniper_position_manager import SniperPositionManager

position_manager = SniperPositionManager(info_manager)

# 计算 BTC/USDT 做多仓位
position = position_manager.calculate_sniper_position(
    symbol='BTC/USDT',
    capital=200,
    side='LONG',
    entry_price=50000,
    stop_distance_pct=0.02  # 2% 爆仓距离
)

print(f"入场价: ${position.entry_price:.2f}")
print(f"数量: {position.quantity:.6f} BTC")
print(f"杠杆: {position.leverage}x")
print(f"爆仓线(止损): ${position.stop_loss_price:.2f}")
print(f"目标止盈: ${position.take_profit_price:.2f}")
```

### 3. MTF 三重共振检查

```python
from src.quantitative.mtf_resonance_lock import MTFResonanceLock
import asyncio

async def check_signal():
    lock = MTFResonanceLock()

    # 检查 BTC/USDT 三重共振
    signal = await lock.check_triple_resonance('BTC/USDT')

    print(f"信号方向: {signal.signal}")  # 1=做多, -1=做空, 0=无信号
    print(f"置信度: {signal.confidence:.0%}")
    print(f"是否锁定: {signal.is_locked}")

    await lock.close()

asyncio.run(check_signal())
```

### 4. 启动狙击手交易器

```bash
# 测试网
python scripts/sniper_trader.py

# 主网（警告：真实资金！）
export BINANCE_TESTNET=false
python scripts/sniper_trader.py
```

## 交易示例

### 场景 1: 200 USDT 开 BTC/USDT 多单

```
资金: 200 USDT
BTC 价格: 50000 USDT
开仓比例: 50% (100 USDT)
杠杆: 自动调整（假设 25x）

计算结果:
- 名义价值: 100 × 25 = 2500 USDT
- 数量: 2500 / 50000 = 0.05 BTC
- 爆仓线(止损): 50000 × (1 - 0.02) = 49000 USDT (-2%)
- 目标止盈: 50000 × (1 + 0.10) = 55000 USDT (+10%)
- 盈亏比: 1:5

如果成功:
- 止损损失: -2% = -4 USDT
- 止盈盈利: +10% = +20 USDT
- 实际盈亏比: 1:5 ✅
```

### 场景 2: 移动止盈追踪

```
入场价: 50000 USDT
当前价: 55000 USDT (+10%)

启动移动止盈:
- 移动距离: 55000 × 5% = 2750 USDT
- 移动止盈线: 55000 - 2750 = 52250 USDT

价格继续上涨到 60000 USDT:
- 新移动止盈线: 60000 × (1 - 5%) = 57000 USDT
- 只向上移动 ✅

价格回调到 57000 USDT:
- 触发移动止盈 ✅
- 实际盈利: (57000 - 50000) / 50000 = +14%
```

## 关键参数

| 参数 | 值 | 说明 |
|------|-----|------|
| 资金 | 200 USDT | 超小资金 |
| 开仓比例 | 50% | 孤注一掷 |
| 杠杆 | 自动调整 | 满足 MIN_NOTIONAL |
| 爆仓距离 | 2% | 爆仓线 = 止损线 |
| 目标盈利 | 10% | 5 × 止损距离 |
| 盈亏比 | 1:5 | 极高盈亏比 |
| 最大仓位 | 1 | 同时只持有 1 个仓位 |
| 扫描间隔 | 15 分钟 | 极低频 |

## 文件结构

```
src/
├── exchange/
│   ├── exchange_info_manager.py       # exchangeInfo 精度处理
│   └── sniper_position_manager.py     # 狙击手仓位管理
├── quantitative/
│   └── mtf_resonance_lock.py          # MTF 三重共振锁
scripts/
└── sniper_trader.py                   # 主交易脚本
```

## 风险警告

⚠️ **v5.0 狙击手模式是高风险策略：**

1. **孤注一掷**: 50% 资金单次开仓，一次失误损失惨重
2. **高杠杆**: 可能达到 20-50x 杠杆，爆仓风险极高
3. **爆仓即止损**: 不设传统止损，直接打到爆仓线
4. **极低频**: 一周可能只有 0-1 次开仓机会
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

## 总结

v5.0 狙击手模式不是给大多数人用的，是给**超小资金、高风险偏好、有耐心**的狙击手用的。

**核心理念:**
- 宁可错过，不做错
- 孤注一掷，要么归零要么翻倍
- 极低频，极高置信度
- 1:5 盈亏比，让利润奔跑

**这不是机枪，这是狙击步枪。**
