# 免费数据获取模块使用指南

## 增强功能

我已经为你大幅增强了 `free_klines.py` 模块，现在支持：

### 1. 多数据源（5个）
| 数据源 | 特点 | 适用场景 |
|--------|------|---------|
| **CoinCap** | 免费，无key | 首选数据源 |
| **CoinGecko** | 免费，限流 | 备选方案 |
| **Binance** | 公开API | 币安网络好时 |
| **OKX** | 公开API | 最后备选 |
| **本地SQLite** | 完全离线 | 无网络时使用 |

### 2. 离线缓存系统
- **SQLite 本地数据库**：自动保存获取的数据
- **缓存位置**：`~/.cache/usdt_klines/klines_cache.db`
- **智能回退**：所有在线源失败时自动使用缓存

### 3. CSV 导入/导出
```python
# 导出到 CSV（用于备份或在 Excel/TradingView 中查看）
fetcher.export_to_csv('BTC/USDT', '1h', days=30, filepath='btc_data.csv')

# 从 CSV 导入（比如从 TradingView 导出的数据）
df = fetcher.import_from_csv('btc_data.csv', 'BTC/USDT', '1h')
```

### 4. 网络不好时的使用策略

#### 首次使用（需要联网）
```python
from src.ai.data.free_klines import fetch_klines_sync

# 获取数据并自动保存到本地缓存
df = fetch_klines_sync('BTC/USDT', '1h', days=7)
```

#### 离线使用（无网络）
```python
from src.ai.data.free_klines import FreeKlineFetcher

fetcher = FreeKlineFetcher()

# 从本地 SQLite 加载缓存数据
df = fetcher._load_from_sqlite('BTC/USDT', '1h', days=7)
if not df.empty:
    print(f"使用离线缓存数据: {len(df)} 条")
```

#### 从 TradingView 导入离线数据
1. 在 TradingView 导出 CSV 数据
2. 使用代码导入：
```python
fetcher = FreeKlineFetcher()
df = fetcher.import_from_csv('tradingview_export.csv', 'BTC/USDT', '1h')
```

## 数据源优先级

获取数据时的优先级：
1. **本地缓存**（如果启用 `use_offline_cache=True`）
2. **CoinCap**（免费，稳定）
3. **Binance**（币安公开 API）
4. **OKX**（OKX 公开 API）
5. **CoinGecko**（备选，有限流）
6. **本地缓存（过期数据）**（所有在线源失败时）

## 配置文件

可以设置代理（如果需要）：
```python
from src.ai.data.free_klines import PROXY

# 修改代理
PROXY = "http://127.0.0.1:7890"  # 你的代理地址
```

## 完整使用示例

```python
import asyncio
from src.ai.data.free_klines import FreeKlineFetcher

async def main():
    fetcher = FreeKlineFetcher()

    # 1. 获取数据（自动选择最佳数据源并保存到本地缓存）
    df = await fetcher.fetch_free_klines('BTC/USDT', '1h', days=7)
    print(f"获取到 {len(df)} 条数据")

    # 2. 批量获取多币种
    results = await fetcher.fetch_multiple_symbols(
        ['BTC/USDT', 'ETH/USDT', 'SOL/USDT'],
        interval='1h',
        days=7
    )
    for symbol, data in results.items():
        print(f"{symbol}: {len(data)} 条")

    # 3. 导出到 CSV
    fetcher.export_to_csv('BTC/USDT', '1h', days=30, filepath='btc_monthly.csv')

    # 4. 离线时使用本地缓存
    offline_df = fetcher._load_from_sqlite('BTC/USDT', '1h', days=7)
    if not offline_df.empty:
        print(f"离线缓存: {len(offline_df)} 条")

if __name__ == '__main__':
    asyncio.run(main())
```

## 故障排除

### 所有数据源都失败
- 检查网络连接
- 检查代理设置是否正确
- 使用本地缓存数据：`fetcher._load_from_sqlite()`

### 数据不完整
- 尝试不同的时间间隔
- 减少获取天数
- 从多个数据源获取并合并

### 网络限制
- 设置代理：`PROXY = "http://你的代理地址:端口"`
- 使用本地缓存
- 从 CSV 导入数据

---

现在即使网络不好，你也可以使用本地缓存的 SQLite 数据继续交易分析！
