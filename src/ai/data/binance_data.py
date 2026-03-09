"""
Binance 数据获取模块

从 Binance 获取 K 线数据并转换为 DataFrame 格式
支持多种时间周期和批量获取
"""
import logging
from typing import Optional, List
from datetime import datetime, timedelta
import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)

# 尝试导入 ccxt
try:
    import ccxt
    CCXT_AVAILABLE = True
except ImportError:
    CCXT_AVAILABLE = False
    logger.warning("ccxt not installed, using fallback method")


class BinanceDataFetcher:
    """Binance 数据获取器"""

    # 支持的时间周期
    INTERVALS = {
        '1m': '1m',
        '5m': '5m',
        '15m': '15m',
        '30m': '30m',
        '1h': '1h',
        '4h': '4h',
        '1d': '1d',
        '1w': '1w',
    }

    def __init__(self, symbol: str = 'BTC/USDT', interval: str = '1h',
                 proxy: Optional[str] = None):
        """
        初始化

        Args:
            symbol: 交易对
            interval: 时间周期
            proxy: 代理地址
        """
        self.symbol = symbol
        self.interval = interval
        self.proxy = proxy

        if CCXT_AVAILABLE:
            self.exchange = ccxt.binance({
                'enableRateLimit': True,
                'options': {'defaultType': 'future'}  # 合约
            })
            if proxy:
                self.exchange.proxies = {'http': proxy, 'https': proxy}

    def fetch_ohlcv(self, start_time: Optional[str] = None,
                    end_time: Optional[str] = None,
                    limit: int = 1000) -> pd.DataFrame:
        """
        获取 K 线数据

        Args:
            start_time: 开始时间 (ISO format or timestamp)
            end_time: 结束时间 (ISO format or timestamp)
            limit: 获取数量 (max 1000)

        Returns:
            OHLCV DataFrame
        """
        if not CCXT_AVAILABLE:
            logger.error("ccxt not installed")
            return pd.DataFrame()

        try:
            # 转换时间格式
            since = None
            if start_time:
                if isinstance(start_time, str):
                    since = int(pd.Timestamp(start_time).timestamp() * 1000)
                else:
                    since = start_time

            params = {'limit': limit}
            if since:
                params['since'] = since

            # 获取数据
            ohlcv = self.exchange.fetch_ohlcv(self.symbol, self.interval, **params)

            # 转换为 DataFrame
            df = pd.DataFrame(
                ohlcv,
                columns=['timestamp', 'open', 'high', 'low', 'close', 'volume']
            )

            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            df.set_index('timestamp', inplace=True)

            # 过滤结束时间
            if end_time:
                end_ts = int(pd.Timestamp(end_time).timestamp() * 1000)
                df = df[df['timestamp'].astype('int64') <= end_ts]

            logger.info(f"Fetched {len(df)} candles for {self.symbol}")
            return df

        except Exception as e:
            logger.error(f"Error fetching data: {e}")
            return pd.DataFrame()

    def fetch_recent(self, days: int = 7) -> pd.DataFrame:
        """获取最近 N 天的数据"""
        end_time = datetime.now()
        start_time = end_time - timedelta(days=days)

        # 估算需要的 K 线数量
        interval_hours = {
            '1m': 1/60, '5m': 5/60, '15m': 15/60, '30m': 30/60,
            '1h': 1, '4h': 4, '1d': 24, '1w': 24*7
        }
        hours = interval_hours.get(self.interval, 1)
        limit = int(days * 24 / hours) + 100

        return self.fetch_ohlcv(start_time.isoformat(), limit=min(limit, 1000))

    def fetch_batch(self, start_time: str, end_time: str,
                   max_per_request: int = 1000) -> pd.DataFrame:
        """
        批量获取数据（超过 1000 条时使用）

        Args:
            start_time: 开始时间
            end_time: 结束时间
            max_per_request: 每次请求最大数量

        Returns:
            合并后的 DataFrame
        """
        all_data = []
        current_start = pd.Timestamp(start_time)
        end = pd.Timestamp(end_time)

        while current_start < end:
            df = self.fetch_ohlcv(
                current_start.isoformat(),
                end_time,
                limit=max_per_request
            )

            if df.empty:
                break

            all_data.append(df)
            current_start = df.index[-1] + pd.Timedelta(self.interval)

        if all_data:
            return pd.concat(all_data).drop_duplicates()
        return pd.DataFrame()


def fetch_binance_data(symbol: str = 'BTC/USDT',
                      interval: str = '1h',
                      days: int = 30,
                      proxy: Optional[str] = None) -> pd.DataFrame:
    """
    快速获取 Binance 数据

    Args:
        symbol: 交易对
        interval: 时间周期
        days: 天数
        proxy: 代理

    Returns:
        OHLCV DataFrame
    """
    fetcher = BinanceDataFetcher(symbol, interval, proxy)
    return fetcher.fetch_recent(days)


# 便捷函数：获取多个交易对的数据
def fetch_multiple_symbols(symbols: List[str],
                          interval: str = '1h',
                          days: int = 7,
                          proxy: Optional[str] = None) -> dict:
    """
    获取多个交易对的数据

    Args:
        symbols: 交易对列表
        interval: 时间周期
        days: 天数
        proxy: 代理

    Returns:
        {symbol: DataFrame}
    """
    result = {}
    for symbol in symbols:
        try:
            df = fetch_binance_data(symbol, interval, days, proxy)
            if not df.empty:
                result[symbol] = df
        except Exception as e:
            logger.error(f"Error fetching {symbol}: {e}")

    return result


# 便捷函数：获取主流币种数据
def fetch_top_coins(interval: str = '1h',
                   days: int = 7,
                   proxy: Optional[str] = None) -> dict:
    """获取主流币种数据"""
    symbols = [
        'BTC/USDT',
        'ETH/USDT',
        'BNB/USDT',
        'SOL/USDT',
        'XRP/USDT',
    ]
    return fetch_multiple_symbols(symbols, interval, days, proxy)
