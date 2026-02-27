"""
宏观市场数据获取器

获取资金费率、OI、成交量、多空比等宏观数据。
"""
import logging
import os
from datetime import datetime
from typing import Optional

import aiohttp

from ..context import MacroMarketData

logger = logging.getLogger(__name__)

# 代理配置
PROXY = os.environ.get("HTTP_PROXY") or os.environ.get("HTTPS_PROXY") or os.environ.get("ALL_PROXY")


class MacroDataFetcher:
    """宏观市场数据获取器"""

    def __init__(self, session: aiohttp.ClientSession):
        """
        初始化

        Args:
            session: aiohttp session
        """
        self.session = session
        self.base_url = "https://fapi.binance.com/fapi/v1"

    async def fetch(self, symbol: str) -> Optional[MacroMarketData]:
        """
        获取宏观市场数据

        Args:
            symbol: 交易对 (如 BTCUSDT)

        Returns:
            MacroMarketData 或 None
        """
        symbol = symbol.replace('/', '')  # 转换为 BTCUSDT 格式

        try:
            # 并发获取所有数据
            funding_task = self._fetch_funding(symbol)
            oi_task = self._fetch_oi(symbol)
            oi_hist_task = self._fetch_oi_hist(symbol)
            ticker_task = self._fetch_ticker(symbol)
            long_short_task = self._fetch_long_short_ratio(symbol)

            funding_data, oi_data, oi_hist_data, ticker_data, ls_data = await self._gather(
                funding_task, oi_task, oi_hist_task, ticker_task, long_short_task
            )

            macro = MacroMarketData()

            # 1. 资金费率
            if funding_data:
                macro.funding_rate = float(funding_data.get('lastFundingRate', 0))
                macro.mark_price = float(funding_data.get('markPrice', 0))
                macro.index_price = float(funding_data.get('indexPrice', 0))

                # 计算价格差异
                if macro.index_price and macro.index_price > 0:
                    macro.price_diff_pct = ((macro.mark_price - macro.index_price) / macro.index_price) * 100

                # 下次资金时间
                funding_time = int(funding_data.get('nextFundingTime', 0))
                if funding_time > 0:
                    macro.next_funding_time = datetime.fromtimestamp(funding_time / 1000)

            # 2. OI 数据
            if oi_data:
                macro.oi_current = float(oi_data.get('openInterest', 0))

            # 3. OI 历史变化
            if oi_hist_data and len(oi_hist_data) >= 2:
                current_oi = float(oi_hist_data[-1].get('openInterest', 0))

                # 1小时变化 (12个5分钟 = 1小时)
                if len(oi_hist_data) >= 12:
                    oi_1h_ago = float(oi_hist_data[0].get('openInterest', 0))
                    if oi_1h_ago > 0:
                        macro.oi_change_1h = ((current_oi - oi_1h_ago) / oi_1h_ago) * 100

                # 4小时变化 (48个5分钟 = 4小时)
                if len(oi_hist_data) >= 48:
                    oi_4h_ago = float(oi_hist_data[-48].get('openInterest', 0))
                    if oi_4h_ago > 0:
                        macro.oi_change_4h = ((current_oi - oi_4h_ago) / oi_4h_ago) * 100

            # 4. 24小时成交量
            if ticker_data:
                macro.volume_24h = float(ticker_data.get('volume', 0))
                macro.quote_volume_24h = float(ticker_data.get('quoteVolume', 0))

            # 5. 多空比
            if ls_data:
                macro.long_short_ratio = float(ls_data.get('longShortRatio', 1))
                macro.long_ratio = float(ls_data.get('longAccount', 0.5))
                macro.short_ratio = float(ls_data.get('shortAccount', 0.5))

            return macro

        except Exception as e:
            logger.error(f"获取宏观数据失败: {e}")
            return None

    async def _fetch_funding(self, symbol: str) -> Optional[dict]:
        """获取资金费率"""
        url = f"{self.base_url}/premiumIndex"
        params = {'symbol': symbol}

        try:
            async with self.session.get(url, params=params, proxy=PROXY) as response:
                if response.status == 200:
                    return await response.json()
        except Exception as e:
            logger.warning(f"获取资金费率失败: {e}")

        return None

    async def _fetch_oi(self, symbol: str) -> Optional[dict]:
        """获取当前 OI"""
        url = f"{self.base_url}/openInterest"
        params = {'symbol': symbol}

        try:
            async with self.session.get(url, params=params, proxy=PROXY) as response:
                if response.status == 200:
                    return await response.json()
        except Exception as e:
            logger.warning(f"获取 OI 失败: {e}")

        return None

    async def _fetch_oi_hist(self, symbol: str) -> Optional[list]:
        """获取 OI 历史"""
        url = f"{self.base_url}/openInterestHist"
        params = {
            'symbol': symbol,
            'period': '5m',
            'limit': 60,  # 5小时历史
        }

        try:
            async with self.session.get(url, params=params, proxy=PROXY) as response:
                if response.status == 200:
                    return await response.json()
        except Exception as e:
            logger.warning(f"获取 OI 历史失败: {e}")

        return None

    async def _fetch_ticker(self, symbol: str) -> Optional[dict]:
        """获取24小时行情"""
        url = f"{self.base_url}/ticker/24hr"
        params = {'symbol': symbol}

        try:
            async with self.session.get(url, params=params, proxy=PROXY) as response:
                if response.status == 200:
                    return await response.json()
        except Exception as e:
            logger.warning(f"获取24小时行情失败: {e}")

        return None

    async def _fetch_long_short_ratio(self, symbol: str) -> Optional[dict]:
        """获取多空比"""
        url = f"{self.base_url}/longShortRatio"
        params = {
            'symbol': symbol,
            'period': '1h',
            'limit': 1,
        }

        try:
            async with self.session.get(url, params=params, proxy=PROXY) as response:
                if response.status == 200:
                    data = await response.json()
                    if isinstance(data, list) and len(data) > 0:
                        return data[-1]
        except Exception as e:
            logger.warning(f"获取多空比失败: {e}")

        return None

    async def _gather(self, *tasks):
        """并发执行所有任务"""
        import asyncio
        results = await asyncio.gather(*tasks, return_exceptions=True)
        return [
            r if not isinstance(r, Exception) else None
            for r in results
        ]
