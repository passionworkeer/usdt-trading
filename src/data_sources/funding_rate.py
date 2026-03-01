"""
资金费率数据源 - 免费的合约多空情绪指标
通过 Binance API 获取，无需额外 key
"""
import os
import asyncio
import logging
from typing import Dict, List, Optional
from dataclasses import dataclass
from datetime import datetime, timedelta
import aiohttp

logger = logging.getLogger(__name__)

# 代理配置
PROXY = os.environ.get("HTTP_PROXY") or os.environ.get("HTTPS_PROXY") or os.environ.get("ALL_PROXY")


@dataclass
class FundingInfo:
    """资金费率信息"""
    symbol: str
    funding_rate: float          # 当前资金费率 (%)
    funding_rate_indicative: float  # 下一期预测
    mark_price: float            # 标记价格
    index_price: float           # 指数价格
    next_funding_time: datetime # 下次结算时间
    open_interest: float        # 未平仓合约量
    long_short_ratio: float      # 多空比
    timestamp: datetime


class FundingRateSource:
    """资金费率数据源"""

    # 热门合约列表
    POPULAR_CONTRACTS = [
        'BTCUSDT', 'ETHUSDT', 'BNBUSDT', 'SOLUSDT',
        'XRPUSDT', 'ADAUSDT', 'DOGEUSDT', 'AVAXUSDT',
        'DOTUSDT', 'MATICUSDT', 'LINKUSDT', 'UNIUSDT'
    ]

    def __init__(self):
        self.session: Optional[aiohttp.ClientSession] = None
        self._cache: Dict = {}
        self._cache_duration = 60  # 1分钟缓存

    async def _get_session(self) -> aiohttp.ClientSession:
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=10),
                proxy=PROXY
            )
        return self.session

    def _is_cache_valid(self, key: str) -> bool:
        if key not in self._cache:
            return False
        _, timestamp = self._cache[key]
        return (datetime.now() - timestamp).total_seconds() < self._cache_duration

    async def get_funding_rate(self, symbol: str) -> Optional[FundingInfo]:
        """
        获取单个币种的资金费率
        """
        cache_key = f"funding_{symbol}"
        if self._is_cache_valid(cache_key):
            return self._cache[cache_key][0]

        try:
            session = await self._get_session()
            # 确保是 USDT 合约
            symbol_clean = symbol.upper().replace('/', '').replace('-', '')
            if not symbol_clean.endswith('USDT'):
                symbol_upper = f"{symbol_clean}USDT"
            else:
                symbol_upper = symbol_clean

            # 获取标记价格和资金费率
            url = "https://fapi.binance.com/fapi/v1/premiumIndex"
            params = {'symbol': symbol_upper}

            async with session.get(url, params=params) as response:
                if response.status != 200:
                    logger.warning(f"获取资金费率失败: {symbol}, status: {response.status}")
                    return None

                data = await response.json()

                # 解析下次结算时间
                next_funding_time = datetime.fromtimestamp(
                    data.get('nextFundingTime', 0) / 1000
                )

                funding_info = FundingInfo(
                    symbol=symbol_upper,
                    funding_rate=float(data.get('lastFundingRate', 0)) * 100,  # 转为百分比
                    funding_rate_indicative=float(data.get('nextFundingRate', 0)) * 100,
                    mark_price=float(data.get('markPrice', 0)),
                    index_price=float(data.get('indexPrice', 0)),
                    next_funding_time=next_funding_time,
                    open_interest=0,  # 需要另外请求
                    long_short_ratio=0,  # 需要另外请求
                    timestamp=datetime.now()
                )

                self._cache[cache_key] = (funding_info, datetime.now())
                return funding_info

        except Exception as e:
            logger.error(f"获取资金费率异常: {symbol}, {e}")
            return None

    async def get_long_short_ratio(self, symbol: str) -> Optional[Dict]:
        """
        获取多空比（通过持仓数据估算）
        """
        try:
            session = await self._get_session()
            symbol_clean = symbol.upper().replace('/', '').replace('-', '')
            if not symbol_clean.endswith('USDT'):
                symbol_upper = f"{symbol_clean}USDT"
            else:
                symbol_upper = symbol_clean

            # 使用期货顶部/底部统计
            url = "https://fapi.binance.com/futures/data/topLongShortPositionRatio"
            params = {
                'symbol': symbol_upper,
                'periodType': '1h',
                'limit': 10
            }

            async with session.get(url, params=params) as response:
                if response.status != 200:
                    return None

                data = await response.json()

                if not data or not isinstance(data, list):
                    return None

                # 取最新的数据
                latest = data[-1]

                return {
                    'long_ratio': float(latest.get('longPositionRatio', 50)),
                    'short_ratio': float(latest.get('shortPositionRatio', 50)),
                    'timestamp': datetime.fromtimestamp(latest.get('timestamp', 0) / 1000)
                }

        except Exception as e:
            logger.debug(f"获取多空比失败: {symbol}, {e}")
            return None

    async def get_taker_long_short_ratio(self, symbol: str) -> Optional[Dict]:
        """
        获取吃单多空比（更准确）
        """
        try:
            session = await self._get_session()
            symbol_clean = symbol.upper().replace('/', '').replace('-', '')
            if not symbol_clean.endswith('USDT'):
                symbol_upper = f"{symbol_clean}USDT"
            else:
                symbol_upper = symbol_clean

            url = "https://fapi.binance.com/futures/data/takerLongShortRatio"
            params = {
                'symbol': symbol_upper,
                'periodType': '1h',
                'limit': 10
            }

            async with session.get(url, params=params) as response:
                if response.status != 200:
                    return None

                data = await response.json()

                if not data or not isinstance(data, list):
                    return None

                latest = data[-1]

                return {
                    'long_buy_ratio': float(latest.get('buySellRatio', 1)),
                    'long_vol': float(latest.get('buyVol', 0)),
                    'short_vol': float(latest.get('sellVol', 0)),
                    'timestamp': datetime.fromtimestamp(latest.get('timestamp', 0) / 1000)
                }

        except Exception as e:
            logger.debug(f"获取吃单多空比失败: {symbol}, {e}")
            return None

    async def get_comprehensive_funding(self, symbol: str) -> Dict:
        """
        获取综合资金费率数据
        """
        funding = await self.get_funding_rate(symbol)
        long_short = await self.get_long_short_ratio(symbol)
        taker_ratio = await self.get_taker_long_short_ratio(symbol)

        if not funding:
            return {}

        # 计算综合多空信号
        signals = []

        # 资金费率信号
        if funding.funding_rate > 0.1:  # > 0.1% 付费做多
            signals.append({
                'type': 'high_funding_long',
                'value': funding.funding_rate,
                'message': f'资金费率偏高({funding.funding_rate:.3f}%),多头支付高费率'
            })
        elif funding.funding_rate < -0.1:
            signals.append({
                'type': 'high_funding_short',
                'value': funding.funding_rate,
                'message': f'资金费率偏低({funding.funding_rate:.3f}%),空头支付高费率'
            })

        # 多空比信号
        if long_short:
            if long_short['long_ratio'] > 70:
                signals.append({
                    'type': 'extreme_long',
                    'value': long_short['long_ratio'],
                    'message': f'多头持仓占比极高({long_short["long_ratio"]:.1f}%),可能反转'
                })
            elif long_short['short_ratio'] > 70:
                signals.append({
                    'type': 'extreme_short',
                    'value': long_short['short_ratio'],
                    'message': f'空头持仓占比极高({long_short["short_ratio"]:.1f}%),可能反转'
                })

        # 吃单信号
        if taker_ratio:
            if taker_ratio['long_buy_ratio'] > 1.5:
                signals.append({
                    'type': 'taker_long_dominant',
                    'value': taker_ratio['long_buy_ratio'],
                    'message': '主力买入积极'
                })
            elif taker_ratio['long_buy_ratio'] < 0.67:
                signals.append({
                    'type': 'taker_short_dominant',
                    'value': taker_ratio['long_buy_ratio'],
                    'message': '主力卖出积极'
                })

        # 计算情绪评分
        sentiment_score = 0.5

        if funding.funding_rate > 0:
            sentiment_score += 0.1
        else:
            sentiment_score -= 0.1

        if long_short:
            sentiment_score += (long_short['long_ratio'] - 50) / 100

        if taker_ratio:
            if taker_ratio['long_buy_ratio'] > 1:
                sentiment_score += 0.1
            else:
                sentiment_score -= 0.1

        sentiment_score = max(0, min(1, sentiment_score))

        # 确定情绪
        if sentiment_score > 0.65:
            sentiment = 'bullish'
        elif sentiment_score < 0.35:
            sentiment = 'bearish'
        else:
            sentiment = 'neutral'

        return {
            'symbol': symbol,
            'timestamp': datetime.now().isoformat(),
            'funding_rate': funding.funding_rate,
            'next_funding_time': funding.next_funding_time.isoformat(),
            'mark_price': funding.mark_price,
            'index_price': funding.index_price,
            'long_short': long_short,
            'taker_ratio': taker_ratio,
            'sentiment': sentiment,
            'sentiment_score': sentiment_score,
            'signals': signals,
            'funding_time_remaining': (
                funding.next_funding_time - datetime.now()
            ).total_seconds() / 3600  # 小时
        }

    async def get_all_popular_funding(self) -> List[Dict]:
        """获取热门币种资金费率"""
        results = []

        # 并发获取
        tasks = [
            self.get_comprehensive_funding(symbol.replace('USDT', ''))
            for symbol in self.POPULAR_CONTRACTS
        ]

        import asyncio
        all_results = await asyncio.gather(*tasks, return_exceptions=True)

        for symbol, result in zip(self.POPULAR_CONTRACTS, all_results):
            if result and not isinstance(result, Exception):
                results.append(result)

        # 按资金费率排序
        results.sort(key=lambda x: x.get('funding_rate', 0), reverse=True)

        return results

    def find_funding_arbitrage(self, fundings: List[Dict]) -> List[Dict]:
        """
        寻找资金费率套利机会
        找出做多高资金费率的币种
        """
        opportunities = []

        for f in fundings:
            if f.get('funding_rate', 0) > 0.05:  # > 0.05% 每小时
                opportunities.append({
                    'symbol': f['symbol'],
                    'funding_rate': f['funding_rate'],
                    'annualized_rate': f['funding_rate'] * 24 * 365,  # 年化
                    'sentiment': f.get('sentiment'),
                    'score': f.get('sentiment_score', 0.5)
                })

        # 按年化收益率排序
        opportunities.sort(key=lambda x: x['annualized_rate'], reverse=True)

        return opportunities[:5]

    async def close(self):
        if self.session:
            await self.session.close()


# 全局实例
_funding_source: Optional[FundingRateSource] = None


async def get_funding_source() -> FundingRateSource:
    global _funding_source
    if _funding_source is None:
        _funding_source = FundingRateSource()
    return _funding_source


# ========== 测试 ==========

if __name__ == '__main__':
    async def test():
        source = FundingRateSource()

        # 测试单个币种
        print("=== BTC 资金费率 ===")
        btc_funding = await source.get_comprehensive_funding('BTC')
        print(f"资金费率: {btc_funding.get('funding_rate', 0):.4f}%")
        print(f"情绪: {btc_funding.get('sentiment')}")
        print(f"评分: {btc_funding.get('sentiment_score', 0):.2f}")
        print("信号:")
        for sig in btc_funding.get('signals', []):
            print(f"  - {sig.get('message')}")

        # 测试多空比
        print("\n=== 多空比 ===")
        ls = await source.get_long_short_ratio('BTC')
        if ls:
            print(f"多头: {ls.get('long_ratio')}% | 空头: {ls.get('short_ratio')}%")

        # 测试热门币种
        print("\n=== 热门币种资金费率 ===")
        all_funding = await source.get_all_popular_funding()
        for f in all_funding[:5]:
            print(f"{f['symbol']}: {f.get('funding_rate', 0):.4f}% ({f.get('sentiment')})")

        # 找套利机会
        print("\n=== 资金费率套利机会 ===")
        opportunities = source.find_funding_arbitrage(all_funding)
        for op in opportunities:
            print(f"{op['symbol']}: {op['funding_rate']:.4f}% (年化 {op['annualized_rate']:.1f}%)")

        await source.close()

    asyncio.run(test())
