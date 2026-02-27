"""
多时间框架 K 线收集器

从 Binance 获取多时间周期的 K 线数据。
"""
import logging
import os
from typing import Dict, List, Optional

import aiohttp
import pandas as pd

from ..context import KLineData

logger = logging.getLogger(__name__)

# 支持的时间周期
INTERVALS = ['15m', '1h', '4h', '1d']

# K线列名
KLINE_COLUMNS = [
    'timestamp', 'open', 'high', 'low', 'close', 'volume',
    'close_time', 'quote_volume', 'trades', 'taker_buy_base',
    'taker_buy_quote', 'ignore'
]

# 代理配置
PROXY = os.environ.get("HTTP_PROXY") or os.environ.get("HTTPS_PROXY") or os.environ.get("ALL_PROXY")


class MTFKlinesCollector:
    """多时间框架 K 线收集器"""

    def __init__(self, session: aiohttp.ClientSession):
        """
        初始化

        Args:
            session: aiohttp session
        """
        self.session = session
        self.base_url = "https://fapi.binance.com/fapi/v1/klines"

    async def fetch(
        self,
        symbol: str,
        interval: str,
        limit: int = 100
    ) -> Optional[KLineData]:
        """
        获取指定周期的 K 线数据

        Args:
            symbol: 交易对 (如 BTCUSDT)
            interval: 时间周期 (15m, 1h, 4h, 1d)
            limit: 获取数量

        Returns:
            KLineData 或 None
        """
        params = {
            'symbol': symbol,
            'interval': interval,
            'limit': limit,
        }

        try:
            # 构建请求参数
            request_kwargs = {
                'url': self.base_url,
                'params': params,
            }
            # 添加代理支持
            if PROXY:
                request_kwargs['proxy'] = PROXY
                logger.debug(f"使用代理: {PROXY}")

            async with self.session.get(**request_kwargs) as response:
                if response.status != 200:
                    logger.error(f"获取 {interval} K线失败: HTTP {response.status}")
                    return None

                data = await response.json()
                if not data:
                    logger.warning(f"{interval} 无 K 线数据")
                    return None

                df = pd.DataFrame(data, columns=KLINE_COLUMNS)

                # 转换数据类型
                numeric_cols = ['open', 'high', 'low', 'close', 'volume', 'quote_volume']
                for col in numeric_cols:
                    df[col] = pd.to_numeric(df[col], errors='coerce')

                df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')

                logger.debug(f"获取 {symbol} {interval} K线 {len(df)} 根")

                return KLineData(interval=interval, df=df)

        except Exception as e:
            logger.error(f"获取 {symbol} {interval} K线异常: {e}")
            return None

    async def fetch_all(
        self,
        symbol: str,
        intervals: List[str] = None
    ) -> Dict[str, KLineData]:
        """
        并发获取所有时间周期的 K 线

        Args:
            symbol: 交易对 (如 BTCUSDT)
            intervals: 时间周期列表，默认 ['15m', '1h', '4h', '1d']

        Returns:
            {interval: KLineData}
        """
        import asyncio

        intervals = intervals or INTERVALS
        symbol = symbol.replace('/', '')  # 转换为 BTCUSDT 格式

        tasks = [self.fetch(symbol, interval) for interval in intervals]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        klines = {}
        for interval, result in zip(intervals, results):
            if isinstance(result, Exception):
                logger.error(f"获取 {interval} K线失败: {result}")
            elif result is not None:
                klines[interval] = result

        logger.info(f"成功获取 {len(klines)}/{len(intervals)} 个时间周期的 K 线")
        return klines
