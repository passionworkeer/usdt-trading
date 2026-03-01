"""
免费数据源 - 不需要 API Key
包括：CoinCap（价格+链上）、资金费率、多源价格验证
"""
import os
import asyncio
import logging
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from collections import deque
import aiohttp
import json

logger = logging.getLogger(__name__)

# 代理配置
PROXY = os.environ.get("HTTP_PROXY") or os.environ.get("HTTPS_PROXY") or os.environ.get("ALL_PROXY")


@dataclass
class CoinData:
    """代币数据"""
    symbol: str
    name: str
    price_usd: float
    change_24h: float
    change_24h_pct: float
    market_cap: float
    volume_24h: float
    circulating_supply: float
    timestamp: datetime


@dataclass
class FundingRateData:
    """资金费率数据"""
    symbol: str
    funding_rate: float
    next_funding_time: datetime
    mark_price: float
    index_price: float
    timestamp: datetime


@dataclass
class ExchangePrice:
    """交易所价格"""
    exchange: str
    symbol: str
    price: float
    bid: float  # 买一价
    ask: float  # 卖一价
    spread_pct: float
    volume_24h: float
    timestamp: datetime


@dataclass
class OnChainFlow:
    """链上资金流向"""
    symbol: str
    exchange_inflow_24h: float      # 24h 流入交易所（美元）
    exchange_outflow_24h: float     # 24h 流出交易所（美元）
    net_flow: float                 # 净流入
    active_addresses: int           # 活跃地址数
    large_transactions: int         # 大额交易数
    velocity: float                 # 资金周转率
    timestamp: datetime


class FreeDataSource:
    """
    免费数据源汇总
    完全不需要 API Key
    """

    # 支持的币种
    # 支持的币种 (symbol -> CoinCap ID)
    SUPPORTED_COINS = {
        'BTC': 'bitcoin',
        'ETH': 'ethereum',
        'BNB': 'binancecoin',
        'SOL': 'solana',
        'XRP': 'ripple',
        'ADA': 'cardano',
        'DOGE': 'dogecoin',
        'AVAX': 'avalanche-2',
        'DOT': 'polkadot',
        'MATIC': 'matic-network',
        'LINK': 'chainlink',
        'UNI': 'uniswap',
        'ATOM': 'cosmos',
        'LTC': 'litecoin',
    }

    def __init__(self):
        self.session: Optional[aiohttp.ClientSession] = None
        self._cache: Dict[str, tuple] = {}  # (data, timestamp)
        self._cache_duration = 30  # 30秒缓存

    async def _get_session(self) -> aiohttp.ClientSession:
        """获取或创建 HTTP session"""
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=10),
                proxy=PROXY
            )
        return self.session

    def _is_cache_valid(self, key: str) -> bool:
        """检查缓存是否有效"""
        if key not in self._cache:
            return False
        _, timestamp = self._cache[key]
        return (datetime.now() - timestamp).total_seconds() < self._cache_duration

    def _set_cache(self, key: str, data: Any):
        """设置缓存"""
        self._cache[key] = (data, datetime.now())

    async def close(self):
        """关闭 session"""
        if self.session and not self.session.closed:
            await self.session.close()

    # ========== CoinCap API (免费，无需 key) ==========

    async def get_price_coincap(self, symbol: str) -> Optional[CoinData]:
        """
        获取 CoinCap 价格数据
        免费 API，每分钟 300 次请求
        """
        cache_key = f"coincap_{symbol}"
        if self._is_cache_valid(cache_key):
            return self._cache[cache_key][0]

        coin_id = self.SUPPORTED_COINS.get(symbol.upper())
        if not coin_id:
            logger.warning(f"不支持的币种: {symbol}")
            return None

        try:
            session = await self._get_session()
            url = f"https://api.coincap.io/v2/assets/{coin_id}"

            async with session.get(url) as response:
                if response.status != 200:
                    logger.error(f"CoinCap API 错误: {response.status}")
                    return None

                data = await response.json()
                asset = data.get('data', {})

                if not asset:
                    return None

                coin_data = CoinData(
                    symbol=symbol.upper(),
                    name=asset.get('name', ''),
                    price_usd=float(asset.get('priceUsd', 0)),
                    change_24h=float(asset.get('changePercent24Hr', 0)),
                    change_24h_pct=float(asset.get('changePercent24Hr', 0)),
                    market_cap=float(asset.get('marketCapUsd', 0)),
                    volume_24h=float(asset.get('volumeUsd24Hr', 0)),
                    circulating_supply=float(asset.get('supply', 0)),
                    timestamp=datetime.now()
                )

                self._set_cache(cache_key, coin_data)
                return coin_data

        except Exception as e:
            logger.error(f"获取 CoinCap 数据失败: {e}")
            return None

    async def get_price_binance(self, symbol: str) -> Optional[CoinData]:
        """
        通过 Binance 获取价格数据（备用）
        """
        cache_key = f"binance_{symbol}"
        if self._is_cache_valid(cache_key):
            return self._cache[cache_key][0]

        try:
            session = await self._get_session()
            symbol_usdt = f"{symbol.upper()}USDT"

            # 获取 24h ticker
            url = "https://api.binance.com/api/v3/ticker/24hr"
            params = {'symbol': symbol_usdt}

            async with session.get(url, params=params) as response:
                if response.status != 200:
                    logger.warning(f"Binance API 错误: {response.status}")
                    return None

                data = await response.json()

                coin_data = CoinData(
                    symbol=symbol.upper(),
                    name=symbol.upper(),
                    price_usd=float(data.get('lastPrice', 0)),
                    change_24h=float(data.get('priceChange', 0)),
                    change_24h_pct=float(data.get('priceChangePercent', 0)),
                    market_cap=0,  # Binance 不提供
                    volume_24h=float(data.get('quoteVolume', 0)),
                    circulating_supply=0,
                    timestamp=datetime.now()
                )

                self._set_cache(cache_key, coin_data)
                return coin_data

        except Exception as e:
            logger.error(f"获取 Binance 价格失败: {e}")
            return None

    async def get_price(self, symbol: str) -> Optional[CoinData]:
        """
        获取价格（优先 CoinCap，失败则用 Binance）
        """
        # 先尝试 CoinCap
        price = await self.get_price_coincap(symbol)
        if price and price.price_usd > 0:
            return price

        # 备用 Binance
        logger.info(f"使用 Binance 作为备用: {symbol}")
        return await self.get_price_binance(symbol)

    async def get_onchain_flow(self, symbol: str) -> Optional[OnChainFlow]:
        """
        获取链上资金流向（通过 CoinCap 的市场数据推断）
        """
        cache_key = f"onchain_{symbol}"
        if self._is_cache_valid(cache_key):
            return self._cache[cache_key][0]

        coin_id = self.SUPPORTED_COINS.get(symbol.upper())
        if not coin_id:
            return None

        try:
            session = await self._get_session()

            # 获取币种历史数据来推断活跃度
            url = f"https://api.coincap.io/v2/assets/{coin_id}/history"
            now = int(datetime.now().timestamp() * 1000)
            day_ago = now - (24 * 60 * 60 * 1000)

            params = {
                'interval': 'h1',
                'start': day_ago,
                'end': now
            }

            async with session.get(url, params=params) as response:
                if response.status != 200:
                    return None

                data = await response.json()
                history = data.get('data', [])

                if not history:
                    return None

                # 计算活跃度（价格波动幅度）
                prices = [float(h['priceUsd']) for h in history]
                price_change = max(prices) - min(prices) if prices else 0
                velocity = price_change / prices[0] * 100 if prices else 0

                # 获取当前价格
                current_price = await self.get_price_coincap(symbol)

                flow = OnChainFlow(
                    symbol=symbol.upper(),
                    exchange_inflow_0=0,  # CoinCap 不直接提供
                    exchange_outflow_24h=0,
                    net_flow=0,
                    active_addresses=int(velocity * 100000),  # 估算
                    large_transactions=int(velocity * 100),    # 估算
                    velocity=velocity,
                    timestamp=datetime.now()
                )

                self._set_cache(cache_key, flow)
                return flow

        except Exception as e:
            logger.error(f"获取链上数据失败: {e}")
            return None

    # ========== 多交易所价格对比 ==========

    async def get_multi_exchange_prices(self, symbol: str) -> List[ExchangePrice]:
        """
        获取多交易所价格（防止插针）
        使用 Binance API（免费）
        """
        cache_key = f"multi_price_{symbol}"
        if self._is_cache_valid(cache_key):
            return self._cache[cache_key][0]

        prices = []

        # Binance 价格
        try:
            session = await self._get_session()
            symbol_usdt = f"{symbol.upper()}USDT"

            # 获取 ticker 数据
            url = f"https://api.binance.com/api/v3/ticker/bookTicker"
            params = {'symbol': symbol_usdt}

            async with session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    bid = float(data.get('bidPrice', 0))
                    ask = float(data.get('askPrice', 0))
                    spread = (ask - bid) / ask * 100 if ask else 0

                    # 获取 24h 成交量
                    url24 = "https://api.binance.com/api/v3/ticker/24hr"
                    async with session.get(url24, params={'symbol': symbol_usdt}) as r24:
                        if r24.status == 200:
                            d24 = await r24.json()
                            volume = float(d24.get('quoteVolume', 0))
                        else:
                            volume = 0

                    prices.append(ExchangePrice(
                        exchange='Binance',
                        symbol=symbol_usdt,
                        price=(bid + ask) / 2,
                        bid=bid,
                        ask=ask,
                        spread_pct=spread,
                        volume_24h=volume,
                        timestamp=datetime.now()
                    ))

        except Exception as e:
            logger.error(f"获取 Binance 价格失败: {e}")

        # Bybit 价格
        try:
            url = f"https://api.bybit.com/v5/market/tickers"
            params = {
                'category': 'spot',
                'symbol': f"{symbol.upper()}USDT"
            }

            session = await self._get_session()
            async with session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    if data.get('list'):
                        item = data['list'][0]
                        bid = float(item.get('bid1Price', 0))
                        ask = float(item.get('ask1Price', 0))
                        spread = (ask - bid) / ask * 100 if ask else 0
                        volume = float(item.get('volume24h', 0))

                        prices.append(ExchangePrice(
                            exchange='Bybit',
                            symbol=f"{symbol.upper()}USDT",
                            price=(bid + ask) / 2,
                            bid=bid,
                            ask=ask,
                            spread_pct=spread,
                            volume_24h=volume,
                            timestamp=datetime.now()
                        ))

        except Exception as e:
            logger.error(f"获取 Bybit 价格失败: {e}")

        # OKX 价格
        try:
            url = f"https://www.okx.com/api/v5/market/ticker"
            params = {'instId': f"{symbol.upper()}-USDT"}

            session = await self._get_session()
            async with session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    if data.get('data'):
                        item = data['data'][0]
                        bid = float(item.get('bidPx', 0))
                        ask = float(item.get('askPx', 0))
                        spread = (ask - bid) / ask * 100 if ask else 0
                        volume = float(item.get('vol24h', 0))

                        prices.append(ExchangePrice(
                            exchange='OKX',
                            symbol=f"{symbol.upper()}USDT",
                            price=(bid + bid) / 2,
                            bid=bid,
                            ask=ask,
                            spread_pct=spread,
                            volume_24h=volume,
                            timestamp=datetime.now()
                        ))

        except Exception as e:
            logger.error(f"获取 OKX 价格失败: {e}")

        if prices:
            self._set_cache(cache_key, prices)

        return prices

    def detect_price_anomaly(self, prices: List[ExchangePrice]) -> Dict:
        """
        检测价格异常（插针）
        返回: {is_anomaly: bool, max_diff_pct: float, exchanges: []}
        """
        if len(prices) < 2:
            return {'is_anomaly': False, 'max_diff_pct': 0, 'exchanges': []}

        price_values = [p.price for p in prices]
        avg_price = sum(price_values) / len(price_values)
        max_diff = max(abs(p - avg_price) / avg_price * 100 for p in price_values)

        # 如果某个交易所价格偏离平均值超过 0.5%，认为是异常
        is_anomaly = max_diff > 0.5

        return {
            'is_anomaly': is_anomaly,
            'max_diff_pct': max_diff,
            'exchanges': [p.exchange for p in prices if abs(p.price - avg_price) / avg_price * 100 > 0.5],
            'avg_price': avg_price,
            'prices': [{'exchange': p.exchange, 'price': p.price} for p in prices]
        }

    # ========== 综合行情获取 ==========

    async def get_market_snapshot(self, symbol: str) -> Dict:
        """
        获取市场快照 - 综合所有免费数据
        """
        snapshot = {
            'symbol': symbol,
            'timestamp': datetime.now().isoformat(),
            'prices': {},
            'onchain': {},
            'anomaly': {},
            'signals': []
        }

        # 1. 获取 CoinCap 价格
        coincap_price = await self.get_price_coincap(symbol)
        if coincap_price:
            snapshot['prices']['CoinCap'] = {
                'price': coincap_price.price_usd,
                'change_24h': coincap_price.change_24h_pct,
                'volume_24h': coincap_price.volume_24h
            }

        # 2. 获取多交易所价格
        multi_prices = await self.get_multi_exchange_prices(symbol)
        for p in multi_prices:
            snapshot['prices'][p.exchange] = {
                'price': p.price,
                'bid': p.bid,
                'ask': p.ask,
                'spread': p.spread_pct,
                'volume': p.volume_24h
            }

        # 3. 检测异常
        if multi_prices:
            snapshot['anomaly'] = self.detect_price_anomaly(multi_prices)

        # 4. 生成信号
        signals = []

        # 价格信号
        if coincap_price:
            if coincap_price.change_24h_pct > 5:
                signals.append({'type': 'price_surge', 'value': coincap_price.change_24h_pct})
            elif coincap_price.change_24h_pct < -5:
                signals.append({'type': 'price_dump', 'value': coincap_price.change_24h_pct})

        # 异常信号
        if snapshot['anomaly'].get('is_anomaly'):
            signals.append({
                'type': 'price_anomaly',
                'value': snapshot['anomaly'].get('max_diff_pct'),
                'exchanges': snapshot['anomaly'].get('exchanges', [])
            })

        # 流动性信号
        if multi_prices:
            total_volume = sum(p.volume_24h for p in multi_prices)
            if total_volume > 100_000_000:  # 1亿以上
                signals.append({'type': 'high_liquidity', 'value': total_volume})

        snapshot['signals'] = signals

        return snapshot


# 全局实例
_free_data_source: Optional[FreeDataSource] = None


async def get_free_data_source() -> FreeDataSource:
    """获取免费数据源实例"""
    global _free_data_source
    if _free_data_source is None:
        _free_data_source = FreeDataSource()
    return _free_data_source


async def close_free_data_source():
    """关闭数据源"""
    global _free_data_source
    if _free_data_source:
        await _free_data_source.close()
        _free_data_source = None


# ========== 测试 ==========

if __name__ == '__main__':
    async def test():
        source = FreeDataSource()

        # 测试获取 BTC 价格
        print("=== BTC 价格 (CoinCap) ===")
        btc = await source.get_price_coincap('BTC')
        if btc:
            print(f"价格: ${btc.price_usd:,.2f}")
            print(f"24h涨跌: {btc.change_24h_pct:.2f}%")

        # 测试多交易所价格
        print("\n=== 多交易所价格对比 ===")
        prices = await source.get_multi_exchange_prices('BTC')
        for p in prices:
            print(f"{p.exchange}: ${p.price:,.2f} (spread: {p.spread_pct:.3f}%)")

        # 测试异常检测
        print("\n=== 异常检测 ===")
        anomaly = source.detect_price_anomaly(prices)
        print(f"是否异常: {anomaly['is_anomaly']}")
        print(f"最大偏差: {anomaly['max_diff_pct']:.3f}%")

        # 测试综合快照
        print("\n=== 市场快照 ===")
        snapshot = await source.get_market_snapshot('ETH')
        print(f"信号数量: {len(snapshot['signals'])}")
        for sig in snapshot['signals']:
            print(f"  - {sig}")

        await source.close()

    asyncio.run(test())
