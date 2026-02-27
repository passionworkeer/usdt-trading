"""
市场数据收集器

协调所有数据收集模块，并发获取完整的市场数据。
"""
import asyncio
import logging
import os
from datetime import datetime
from typing import Optional

import aiohttp

from ..context import AIAnalysisContext
from .indicators import TechnicalIndicatorsCalculator
from .macro_data import MacroDataFetcher
from .mtf_klines import MTFKlinesCollector
from .patterns import PatternRecognizer

logger = logging.getLogger(__name__)

# 默认代理配置
DEFAULT_PROXY = os.environ.get("HTTP_PROXY") or os.environ.get("HTTPS_PROXY") or os.environ.get("ALL_PROXY")


class MarketDataCollector:
    """
    市场数据收集器

    并发收集所有市场数据，为 AI 分析提供完整的上下文。
    """

    def __init__(self, session: Optional[aiohttp.ClientSession] = None):
        """
        初始化

        Args:
            session: aiohttp session，如果为None则创建新的
        """
        self._owns_session = session is None
        self.session = session

        # 初始化子模块
        self._klines_collector: Optional[MTFKlinesCollector] = None
        self._indicators_calculator = TechnicalIndicatorsCalculator()
        self._pattern_recognizer = PatternRecognizer()
        self._macro_fetcher: Optional[MacroDataFetcher] = None

    async def _ensure_session(self) -> aiohttp.ClientSession:
        """确保 session 可用"""
        if self.session is None:
            timeout = aiohttp.ClientTimeout(total=30)
            # 配置代理
            connector = None
            if DEFAULT_PROXY:
                connector = aiohttp.TCPConnector(local_addr=None, limit=100)
                logger.info(f"使用代理: {DEFAULT_PROXY}")
            self.session = aiohttp.ClientSession(timeout=timeout, connector=connector)
            self._owns_session = True

        if self._klines_collector is None:
            self._klines_collector = MTFKlinesCollector(self.session)
        if self._macro_fetcher is None:
            self._macro_fetcher = MacroDataFetcher(self.session)

        return self.session

    async def collect(
        self,
        symbol: str,
        intervals: list = None
    ) -> Optional[AIAnalysisContext]:
        """
        收集完整的市场数据

        Args:
            symbol: 交易对 (如 BTC/USDT)
            intervals: 时间周期列表，默认 ['15m', '1h', '4h', '1d']

        Returns:
            AIAnalysisContext 或 None
        """
        intervals = intervals or ['15m', '1h', '4h', '1d']

        try:
            await self._ensure_session()

            logger.info(f"开始收集 {symbol} 的市场数据...")

            # 并发收集所有数据
            klines_task = self._klines_collector.fetch_all(symbol, intervals)
            macro_task = self._macro_fetcher.fetch(symbol)

            klines, macro_data = await asyncio.gather(
                klines_task,
                macro_task,
                return_exceptions=True
            )

            # 处理异常
            if isinstance(klines, Exception):
                logger.error(f"获取K线失败: {klines}")
                klines = {}

            if isinstance(macro_data, Exception):
                logger.error(f"获取宏观数据失败: {macro_data}")
                macro_data = None

            # 计算技术指标
            indicators = TechnicalIndicatorsCalculator.calculate_all(klines)

            # 识别K线形态
            patterns = PatternRecognizer.recognize(klines)

            # 构建上下文
            context = AIAnalysisContext(
                symbol=symbol,
                timestamp=datetime.now(),
                klines=klines,
                indicators=indicators,
                patterns=patterns,
                macro_data=macro_data,
            )

            logger.info(
                f"数据收集完成: {symbol}, "
                f"K线周期: {len(klines)}, "
                f"指标: {len(indicators)}, "
                f"形态: {sum(len(p) for p in patterns.values())}"
            )

            return context

        except Exception as e:
            logger.error(f"收集市场数据异常: {e}")
            return None

    async def close(self):
        """关闭 session"""
        if self._owns_session and self.session:
            await self.session.close()
            self.session = None
            self._klines_collector = None
            self._macro_fetcher = None

    async def __aenter__(self):
        """上下文管理器入口"""
        await self._ensure_session()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """上下文管理器退出"""
        await self.close()
