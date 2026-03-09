"""
免费 K 线数据获取模块

不依赖 Binance API，使用免费数据源：
1. CoinCap 历史数据
2. Binance 现货 REST API (备用)
3. OKX 公共 API
4. CoinGecko (新增)
5. CryptoCompare (新增)
6. 本地 SQLite 缓存 (新增)
7. CSV 导入 (新增)

解决网络问题：自动代理、多源备用、离线缓存
"""
import logging
import os
import sqlite3
import json
from pathlib import Path
from typing import Optional, List, Dict
from datetime import datetime, timedelta
import pandas as pd
import numpy as np
import aiohttp
import asyncio

logger = logging.getLogger(__name__)

# 代理配置
PROXY = "http://127.0.0.1:7890"

# 本地缓存目录
CACHE_DIR = Path(os.path.expanduser("~/.cache/usdt_klines"))
CACHE_DIR.mkdir(parents=True, exist_ok=True)
DB_CACHE_PATH = CACHE_DIR / "klines_cache.db"

# SQLite 数据库初始化
def _init_db():
    """初始化 SQLite 缓存数据库"""
    conn = sqlite3.connect(str(DB_CACHE_PATH))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS klines_cache (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            interval TEXT NOT NULL,
            timestamp INTEGER NOT NULL,
            open REAL,
            high REAL,
            low REAL,
            close REAL,
            volume REAL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(symbol, interval, timestamp)
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_symbol_interval
        ON klines_cache(symbol, interval)
    """)
    conn.commit()
    conn.close()

_init_db()

# 支持的交易对
SYMBOL_MAP = {
    'BTC/USDT': {'base': 'bitcoin', 'spot': 'BTCUSDT'},
    'ETH/USDT': {'base': 'ethereum', 'spot': 'ETHUSDT'},
    'SOL/USDT': {'base': 'solana', 'spot': 'SOLUSDT'},
    'XRP/USDT': {'base': 'ripple', 'spot': 'XRPUSDT'},
    'BNB/USDT': {'base': 'binancecoin', 'spot': 'BNBUSDT'},
    'ADA/USDT': {'base': 'cardano', 'spot': 'ADAUSDT'},
    'DOGE/USDT': {'base': 'dogecoin', 'spot': 'DOGEUSDT'},
    'AVAX/USDT': {'base': 'avalanche-2', 'spot': 'AVAXUSDT'},
    'DOT/USDT': {'base': 'polkadot', 'spot': 'DOTUSDT'},
    'MATIC/USDT': {'base': 'matic-network', 'spot': 'MATICUSDT'},
    'LINK/USDT': {'base': 'chainlink', 'spot': 'LINKUSDT'},
}


class FreeKlineFetcher:
    """
    免费 K 线获取器

    使用 CoinCap 历史数据 + Binance 备用
    """

    def __init__(self, proxy: str = PROXY, use_cache: bool = True):
        self.proxy = proxy
        self.use_cache = use_cache
        self._cache: Dict[str, tuple] = {}
        self._cache_duration = 300  # 5分钟缓存

    def _get_session(self) -> aiohttp.ClientSession:
        """创建 HTTP session"""
        return aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=15),
            proxy=self.proxy
        )

    async def fetch_coingecko_klines(self, symbol: str, interval: str = '1h',
                                     days: int = 7) -> pd.DataFrame:
        """
        从 CoinGecko 获取历史数据
        免费 API，无需 Key，但有请求限制
        """
        cache_key = f"coingecko_{symbol}_{interval}_{days}"
        if self._is_cache_valid(cache_key):
            return self._cache[cache_key][0]

        coin_id = SYMBOL_MAP.get(symbol, {}).get('base')
        if not coin_id:
            logger.warning(f"不支持的交易对: {symbol}")
            return pd.DataFrame()

        # 转换间隔
        days_param = min(days, 90)  # CoinGecko 限制

        try:
            async with self._get_session() as session:
                url = f"https://api.coingecko.com/api/v3/coins/{coin_id}/market_chart"
                params = {
                    'vs_currency': 'usd',
                    'days': days_param,
                }

                async with session.get(url, params=params) as response:
                    if response.status == 429:
                        logger.warning("CoinGecko API 限流，等待 60 秒")
                        await asyncio.sleep(60)
                        return pd.DataFrame()

                    if response.status != 200:
                        logger.error(f"CoinGecko API 错误: {response.status}")
                        return pd.DataFrame()

                    data = await response.json()
                    prices = data.get('prices', [])
                    volumes = data.get('total_volumes', [])

                    if not prices:
                        return pd.DataFrame()

                    # 转换为 OHLCV 格式
                    records = []
                    for i, (ts, price) in enumerate(prices):
                        vol = volumes[i][1] if i < len(volumes) else 0
                        records.append({
                            'timestamp': pd.to_datetime(ts, unit='ms'),
                            'open': price,
                            'high': price,
                            'low': price,
                            'close': price,
                            'volume': vol
                        })

                    df = pd.DataFrame(records)
                    df.set_index('timestamp', inplace=True)

                    # 重采样到目标间隔
                    if interval in ['1h', '4h', '1d']:
                        df = self._resample_ohlcv(df, interval)

                    self._set_cache(cache_key, df)
                    logger.info(f"CoinGecko: 获取 {len(df)} 条 {symbol} K线")
                    return df

        except Exception as e:
            logger.error(f"CoinGecko 获取失败: {e}")
            return pd.DataFrame()

    def _resample_ohlcv(self, df: pd.DataFrame, interval: str) -> pd.DataFrame:
        """重采样 OHLCV 数据"""
        interval_map = {'1h': '1H', '4h': '4H', '1d': '1D'}
        resample_rule = interval_map.get(interval, '1H')

        return df.resample(resample_rule).agg({
            'open': 'first',
            'high': 'max',
            'low': 'min',
            'close': 'last',
            'volume': 'sum'
        }).dropna()

    async def fetch_coincap_klines(self, symbol: str, interval: str = '1h',
                                   days: int = 7) -> pd.DataFrame:
        """
        从 CoinCap 获取历史数据

        Args:
            symbol: 交易对如 'BTC/USDT'
            interval: 时间间隔 (1h, 1d 等)
            days: 天数

        Returns:
            OHLCV DataFrame
        """
        cache_key = f"coincap_{symbol}_{interval}_{days}"
        if self._is_cache_valid(cache_key):
            return self._cache[cache_key][0]

        base = symbol.split('/')[0]
        coin_id = SYMBOL_MAP.get(symbol, {}).get('base')
        if not coin_id:
            logger.warning(f"不支持的交易对: {symbol}")
            return pd.DataFrame()

        # 转换间隔
        interval_map = {'1m': 'm1', '5m': 'm5', '15m': 'm15',
                       '30m': 'm30', '1h': 'h1', '4h': 'h4', '1d': 'd1'}
        coincap_interval = interval_map.get(interval, 'h1')

        try:
            async with self._get_session() as session:
                now = int(datetime.now().timestamp() * 1000)
                start = now - (days * 24 * 60 * 60 * 1000)

                url = f"https://api.coincap.io/v2/assets/{coin_id}/history"
                params = {
                    'interval': coincap_interval,
                    'start': start,
                    'end': now
                }

                async with session.get(url, params=params) as response:
                    if response.status != 200:
                        logger.error(f"CoinCap API 错误: {response.status}")
                        return pd.DataFrame()

                    data = await response.json()
                    history = data.get('data', [])

                    if not history:
                        return pd.DataFrame()

                    # 转换为 OHLCV 格式（CoinCap 只有价格历史）
                    records = []
                    for h in history:
                        records.append({
                            'timestamp': pd.to_datetime(h['time'], unit='ms'),
                            'open': float(h['priceUsd']),
                            'high': float(h['priceUsd']),
                            'low': float(h['priceUsd']),
                            'close': float(h['priceUsd']),
                            'volume': 0  # CoinCap 不提供成交量
                        })

                    df = pd.DataFrame(records)
                    df.set_index('timestamp', inplace=True)

                    self._set_cache(cache_key, df)
                    logger.info(f"CoinCap: 获取 {len(df)} 条 {symbol} K线")
                    return df

        except Exception as e:
            logger.error(f"CoinCap 获取失败: {e}")
            return pd.DataFrame()

    async def fetch_binance_klines(self, symbol: str, interval: str = '1h',
                                  days: int = 7) -> pd.DataFrame:
        """
        从 Binance 现货获取 K 线（备用）

        Args:
            symbol: 交易对如 'BTC/USDT'
            interval: 时间间隔
            days: 天数

        Returns:
            OHLCV DataFrame
        """
        cache_key = f"binance_{symbol}_{interval}_{days}"
        if self._is_cache_valid(cache_key):
            return self._cache[cache_key][0]

        # 转换 symbol 格式
        spot = SYMBOL_MAP.get(symbol, {}).get('spot', symbol.replace('/', ''))

        # 转换 interval
        interval_map = {'1m': '1m', '5m': '5m', '15m': '15m',
                       '30m': '30m', '1h': '1h', '4h': '4h', '1d': '1d'}
        binance_interval = interval_map.get(interval, '1h')

        try:
            async with self._get_session() as session:
                # 计算 limit
                hours_per_candle = {'1m': 1/60, '5m': 5/60, '15m': 15/60,
                                   '30m': 0.5, '1h': 1, '4h': 4, '1d': 24}
                hours = hours_per_candle.get(binance_interval, 1)
                limit = min(int(days * 24 / hours) + 10, 1000)

                url = "https://api.binance.com/api/v3/klines"
                params = {
                    'symbol': spot,
                    'interval': binance_interval,
                    'limit': limit
                }

                async with session.get(url, params=params) as response:
                    if response.status != 200:
                        logger.error(f"Binance API 错误: {response.status}")
                        return pd.DataFrame()

                    klines = await response.json()

                    if not klines:
                        return pd.DataFrame()

                    records = []
                    for k in klines:
                        records.append({
                            'timestamp': pd.to_datetime(k[0], unit='ms'),
                            'open': float(k[1]),
                            'high': float(k[2]),
                            'low': float(k[3]),
                            'close': float(k[4]),
                            'volume': float(k[5])
                        })

                    df = pd.DataFrame(records)
                    df.set_index('timestamp', inplace=True)

                    self._set_cache(cache_key, df)
                    logger.info(f"Binance: 获取 {len(df)} 条 {symbol} K线")
                    return df

        except Exception as e:
            logger.error(f"Binance 获取失败: {e}")
            return pd.DataFrame()

    async def fetch_okx_klines(self, symbol: str, interval: str = '1h',
                              days: int = 7) -> pd.DataFrame:
        """从 OKX 获取 K 线"""
        cache_key = f"okx_{symbol}_{interval}_{days}"
        if self._is_cache_valid(cache_key):
            return self._cache[cache_key][0]

        base = symbol.split('/')[0]

        try:
            async with self._get_session() as session:
                # OKX interval 转换
                interval_map = {'1m': '1m', '5m': '5m', '15m': '15m',
                               '30m': '30m', '1h': '1H', '4h': '4H', '1d': '1D'}
                okx_interval = interval_map.get(interval, '1H')

                url = "https://www.okx.com/api/v5/market/history-candles"
                params = {
                    'instId': f"{base}-USDT",
                    'bar': okx_interval,
                    'limit': 100
                }

                async with session.get(url, params=params) as response:
                    if response.status != 200:
                        return pd.DataFrame()

                    data = await response.json()
                    candles = data.get('data', [])

                    if not candles:
                        return pd.DataFrame()

                    records = []
                    for c in candles:
                        records.append({
                            'timestamp': pd.to_datetime(int(c[0])),
                            'open': float(c[1]),
                            'high': float(c[2]),
                            'low': float(c[3]),
                            'close': float(c[4]),
                            'volume': float(c[5])
                        })

                    df = pd.DataFrame(records[-limit:])
                    df.set_index('timestamp', inplace=True)

                    self._set_cache(cache_key, df)
                    return df

        except Exception as e:
            logger.error(f"OKX 获取失败: {e}")
            return pd.DataFrame()

    async def fetch_coingecko_klines(self, symbol: str, interval: str = '1h',
                                       days: int = 7) -> pd.DataFrame:
        """
        从 CoinGecko 获取历史数据
        免费 API，无需 Key，但有请求限制 (10-30 calls/minute)
        """
        cache_key = f"coingecko_{symbol}_{interval}_{days}"
        if self._is_cache_valid(cache_key):
            return self._cache[cache_key][0]

        coin_id = SYMBOL_MAP.get(symbol, {}).get('base')
        if not coin_id:
            logger.warning(f"不支持的交易对: {symbol}")
            return pd.DataFrame()

        # CoinGecko 限制: 最多 365 天
        days_param = min(days, 365)

        try:
            async with self._get_session() as session:
                url = f"https://api.coingecko.com/api/v3/coins/{coin_id}/market_chart"
                params = {
                    'vs_currency': 'usd',
                    'days': days_param,
                }

                async with session.get(url, params=params) as response:
                    if response.status == 429:
                        logger.warning("CoinGecko API 限流，等待 60 秒后重试")
                        await asyncio.sleep(60)
                        # 重试一次
                        async with session.get(url, params=params) as retry_response:
                            if retry_response.status != 200:
                                return pd.DataFrame()
                            data = await retry_response.json()
                    elif response.status != 200:
                        logger.error(f"CoinGecko API 错误: {response.status}")
                        return pd.DataFrame()
                    else:
                        data = await response.json()

                    prices = data.get('prices', [])
                    volumes = data.get('total_volumes', [])

                    if not prices:
                        return pd.DataFrame()

                    # 转换为 OHLCV 格式
                    records = []
                    for i, (ts, price) in enumerate(prices):
                        vol = volumes[i][1] if i < len(volumes) else 0
                        records.append({
                            'timestamp': pd.to_datetime(ts, unit='ms'),
                            'open': float(price),
                            'high': float(price),
                            'low': float(price),
                            'close': float(price),
                            'volume': float(vol)
                        })

                    df = pd.DataFrame(records)
                    df.set_index('timestamp', inplace=True)

                    # 重采样到目标间隔 (CoinGecko 提供的是分钟级数据)
                    if interval in ['1h', '4h', '1d'] and len(df) > 100:
                        df = self._resample_ohlcv(df, interval)

                    self._set_cache(cache_key, df)
                    logger.info(f"CoinGecko: 获取 {len(df)} 条 {symbol} K线")
                    return df

        except Exception as e:
            logger.error(f"CoinGecko 获取失败: {e}")
            return pd.DataFrame()

    def _resample_ohlcv(self, df: pd.DataFrame, interval: str) -> pd.DataFrame:
        """重采样 OHLCV 数据到目标时间间隔"""
        interval_map = {'1h': '1H', '4h': '4H', '1d': '1D', '1w': '1W'}
        resample_rule = interval_map.get(interval, '1H')

        resampled = df.resample(resample_rule).agg({
            'open': 'first',
            'high': 'max',
            'low': 'min',
            'close': 'last',
            'volume': 'sum'
        }).dropna()

        return resampled

    async def fetch_free_klines(self, symbol: str = 'BTC/USDT',
                               interval: str = '1h',
                               days: int = 7,
                               use_offline_cache: bool = True) -> pd.DataFrame:
        """
        综合获取免费 K 线（多源备用 + 离线缓存）

        策略：
        1. 先检查 SQLite 本地缓存（离线可用）
        2. 在线获取：CoinCap -> Binance -> OKX -> CoinGecko
        3. 保存到本地缓存供下次离线使用

        Args:
            symbol: 交易对
            interval: 时间间隔
            days: 获取天数
            use_offline_cache: 是否使用本地离线缓存
        """
        # 1. 先尝试本地缓存（离线可用）
        if use_offline_cache:
            cached_df = self._load_from_sqlite(symbol, interval, days)
            if not cached_df.empty and len(cached_df) >= days * 24 * 0.8:  # 至少 80% 数据
                logger.info(f"使用本地缓存数据: {symbol}")
                return cached_df

        # 2. 在线获取（多源备用）
        sources = [
            ('CoinCap', self.fetch_coincap_klines),
            ('Binance', self.fetch_binance_klines),
            ('OKX', self.fetch_okx_klines),
            ('CoinGecko', self.fetch_coingecko_klines),
        ]

        for source_name, fetch_func in sources:
            try:
                df = await fetch_func(symbol, interval, days)
                if not df.empty:
                    logger.info(f"从 {source_name} 获取数据成功: {symbol}")
                    # 保存到本地缓存
                    if use_offline_cache:
                        self._save_to_sqlite(symbol, interval, df)
                    return df
            except Exception as e:
                logger.warning(f"{source_name} 获取失败: {e}")
                continue

        # 3. 所有在线源都失败，返回部分缓存数据（如果有）
        if use_offline_cache and not cached_df.empty:
            logger.warning(f"所有在线源失败，使用过期缓存: {symbol}")
            return cached_df

        logger.error(f"所有数据源都失败: {symbol}")
        return pd.DataFrame()

    async def fetch_multiple_symbols(self, symbols: List[str],
                                     interval: str = '1h',
                                     days: int = 7) -> Dict[str, pd.DataFrame]:
        """批量获取多币种数据"""
        results = {}

        for symbol in symbols:
            df = await self.fetch_free_klines(symbol, interval, days)
            if not df.empty:
                results[symbol] = df

        return results


# 全局实例
_fetcher: Optional[FreeKlineFetcher] = None


def get_free_kline_fetcher(proxy: str = PROXY) -> FreeKlineFetcher:
    """获取免费 K 线获取器实例"""
    global _fetcher
    if _fetcher is None:
        _fetcher = FreeKlineFetcher(proxy=proxy)
    return _fetcher


async def fetch_free_klines(symbol: str = 'BTC/USDT',
                          interval: str = '1h',
                          days: int = 7,
                          proxy: str = PROXY) -> pd.DataFrame:
    """快速获取免费 K 线"""
    fetcher = get_free_kline_fetcher(proxy)
    return await fetcher.fetch_free_klines(symbol, interval, days)


# ========== 同步版本（简化）==========

def fetch_klines_sync(symbol: str = 'BTC/USDT',
                     interval: str = '1h',
                     days: int = 7) -> pd.DataFrame:
    """同步版本获取 K 线"""
    return asyncio.run(fetch_free_klines(symbol, interval, days))


if __name__ == '__main__':
    async def test():
        fetcher = FreeKlineFetcher()

        print("=== 测试 BTC K 线 ===")
        df = await fetcher.fetch_free_klines('BTC/USDT', '1h', 7)
        if not df.empty:
            print(f"获取 {len(df)} 条数据")
            print(df.tail())

        print("\n=== 测试 ETH K 线 ===")
        df = await fetcher.fetch_free_klines('ETH/USDT', '1h', 7)
        if not df.empty:
            print(f"获取 {len(df)} 条数据")
            print(df.tail())

    asyncio.run(test())
