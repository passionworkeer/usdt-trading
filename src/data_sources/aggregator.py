"""
综合数据聚合器 - 整合所有免费数据源
为 AI 决策提供全面的市场情报
"""
import asyncio
import logging
from typing import Dict, List, Optional
from datetime import datetime
from dataclasses import dataclass, field

from .free_data import FreeDataSource, get_free_data_source
from .funding_rate import FundingRateSource, get_funding_source

logger = logging.getLogger(__name__)


@dataclass
class TradingSignal:
    """交易信号"""
    signal_type: str           # 'buy', 'sell', 'strong_buy', 'strong_sell', 'neutral'
    strength: float            # 0-1 信号强度
    sources: List[str]         # 信号来源
    reasons: List[str]         # 原因
    metadata: Dict = field(default_factory=dict)


class MarketAggregator:
    """
    市场综合数据聚合器
    整合所有免费数据源，提供统一接口
    """

    def __init__(self):
        self.price_source: Optional[FreeDataSource] = None
        self.funding_source: Optional[FundingRateSource] = None

    async def initialize(self):
        """初始化所有数据源"""
        self.price_source = await get_free_data_source()
        self.funding_source = await get_funding_source()
        logger.info("市场数据聚合器已初始化")

    async def get_full_analysis(self, symbol: str) -> Dict:
        """
        获取完整的市场分析
        包括：价格、资金流向、多空情绪、信号
        """
        logger.info(f"获取完整市场分析: {symbol}")

        # 并发获取所有数据
        price_task = self.price_source.get_price(symbol)
        multi_price_task = self.price_source.get_multi_exchange_prices(symbol)
        funding_task = self.funding_source.get_comprehensive_funding(symbol)

        price_data, multi_prices, funding_data = await asyncio.gather(
            price_task, multi_price_task, funding_task
        )

        # 整合数据
        analysis = {
            'symbol': symbol,
            'timestamp': datetime.now().isoformat(),
            'price': {},
            'exchanges': {},
            'funding': {},
            'anomaly': {},
            'signals': [],
            'recommendation': {}
        }

        # 1. 价格数据
        if price_data:
            analysis['price'] = {
                'usd': price_data.price_usd,
                'change_24h': price_data.change_24h_pct,
                'volume_24h': price_data.volume_24h,
                'market_cap': price_data.market_cap
            }

        # 2. 多交易所数据
        if multi_prices:
            for p in multi_prices:
                analysis['exchanges'][p.exchange] = {
                    'price': p.price,
                    'spread': p.spread_pct,
                    'volume_24h': p.volume_24h
                }

            # 异常检测
            anomaly = self.price_source.detect_price_anomaly(multi_prices)
            analysis['anomaly'] = anomaly

            if anomaly['is_anomaly']:
                analysis['signals'].append({
                    'type': 'price_anomaly',
                    'strength': min(1.0, anomaly['max_diff_pct'] / 2),
                    'sources': ['multi_exchange'],
                    'reasons': [f"价格偏差 {anomaly['max_diff_pct']:.2f}%"]
                })

        # 3. 资金费率数据
        if funding_data:
            analysis['funding'] = funding_data

            # 添加资金费率信号
            for sig in funding_data.get('signals', []):
                signal_type = sig.get('type', '')

                # 转换为标准信号
                if 'extreme_long' in signal_type:
                    strength = 0.8
                    signal = 'sell'  # 极端多头=潜在反转
                elif 'extreme_short' in signal_type:
                    strength = 0.8
                    signal = 'buy'  # 极端空头=潜在反转
                elif 'high_funding_long' in signal_type:
                    strength = 0.5
                    signal = 'sell'
                elif 'high_funding_short' in signal_type:
                    strength = 0.5
                    signal = 'buy'
                elif 'taker_long' in signal_type:
                    strength = 0.6
                    signal = 'buy'
                elif 'taker_short' in signal_type:
                    strength = 0.6
                    signal = 'sell'
                else:
                    continue

                analysis['signals'].append({
                    'type': signal,
                    'strength': strength,
                    'sources': ['funding_rate'],
                    'reasons': [sig.get('message', '')],
                    'metadata': sig
                })

        # 4. 涨跌信号
        if price_data:
            change = price_data.change_24h_pct
            if change > 10:
                analysis['signals'].append({
                    'type': 'price_surge',
                    'strength': min(1.0, (change - 10) / 20 + 0.5),
                    'sources': ['price'],
                    'reasons': [f'24h涨幅 {change:.1f}%']
                })
            elif change < -10:
                analysis['signals'].append({
                    'type': 'price_dump',
                    'strength': min(1.0, (abs(change) - 10) / 20 + 0.5),
                    'sources': ['price'],
                    'reasons': [f'24h跌幅 {abs(change):.1f}%']
                })

        # 5. 计算综合信号
        analysis['recommendation'] = self._calculate_recommendation(analysis)

        return analysis

    def _calculate_recommendation(self, analysis: Dict) -> Dict:
        """计算综合建议"""
        signals = analysis.get('signals', [])

        if not signals:
            return {
                'action': 'neutral',
                'confidence': 0.3,
                'summary': '无明确信号'
            }

        # 统计信号
        buy_signals = [s for s in signals if 'buy' in s.get('type', '').lower()]
        sell_signals = [s for s in signals if 'sell' in s.get('type', '').lower()]

        # 计算加权分数
        buy_score = sum(s.get('strength', 0.5) for s in buy_signals)
        sell_score = sum(s.get('strength', 0.5) for s in sell_signals)

        # 净分数
        net_score = buy_score - sell_score

        # 置信度
        total_signals = len(signals)
        confidence = min(0.9, total_signals * 0.15)

        # 确定动作
        if net_score > 0.5:
            if net_score > 1.5:
                action = 'strong_buy'
            else:
                action = 'buy'
        elif net_score < -0.5:
            if net_score < -1.5:
                action = 'strong_sell'
            else:
                action = 'sell'
        else:
            action = 'neutral'

        # 生成摘要
        reasons = []
        for s in signals[:3]:
            reasons.extend(s.get('reasons', []))

        return {
            'action': action,
            'confidence': confidence,
            'net_score': net_score,
            'buy_signals': len(buy_signals),
            'sell_signals': len(sell_signals),
            'summary': '; '.join(reasons[:3]) if reasons else '综合多个信号'
        }

    async def scan_opportunities(self) -> Dict:
        """
        扫描全市场机会
        寻找高资金费率+技术面强势的币种
        """
        logger.info("扫描市场机会...")

        # 获取热门币种资金费率
        fundings = await self.funding_source.get_all_popular_funding()

        # 获取热门币种价格
        opportunities = []

        for f in fundings[:10]:  # 只看前10
            symbol = f.get('symbol', '').replace('USDT', '')

            # 获取价格数据
            price_data = await self.price_source.get_price(symbol)

            if not price_data:
                continue

            # 计算机会分数
            score = 0

            # 资金费率加分
            funding_rate = f.get('funding_rate', 0)
            if funding_rate > 0.1:
                score += 30
            elif funding_rate > 0.05:
                score += 20
            elif funding_rate > 0:
                score += 10

            # 价格动量加分
            change = price_data.change_24h_pct
            if change > 5:
                score += 20
            elif change > 0:
                score += 10

            # 多头情绪加分
            sentiment = f.get('sentiment', 'neutral')
            if sentiment == 'bullish':
                score += 15

            # 交易量加分
            if price_data.volume_24h > 1_000_000_000:  # 10亿+
                score += 10

            opportunities.append({
                'symbol': symbol,
                'funding_rate': funding_rate,
                'price': price_data.price_usd,
                'change_24h': change,
                'sentiment': sentiment,
                'volume_24h': price_data.volume_24h,
                'score': score,
                'annualized_funding': funding_rate * 24 * 365
            })

        # 按分数排序
        opportunities.sort(key=lambda x: x['score'], reverse=True)

        return {
            'timestamp': datetime.now().isoformat(),
            'opportunities': opportunities[:5],  # 返回前5
            'total_scanned': len(opportunities)
        }

    async def close(self):
        """关闭所有连接"""
        if self.price_source:
            await self.price_source.close()
        if self.funding_source:
            await self.funding_source.close()


# 全局实例
_market_aggregator: Optional[MarketAggregator] = None


async def get_market_aggregator() -> MarketAggregator:
    global _market_aggregator
    if _market_aggregator is None:
        _market_aggregator = MarketAggregator()
        await _market_aggregator.initialize()
    return _market_aggregator


# ========== 测试 ==========

if __name__ == '__main__':
    async def test():
        aggregator = MarketAggregator()
        await aggregator.initialize()

        # 测试完整分析
        print("=== BTC 完整分析 ===")
        btc_analysis = await aggregator.get_full_analysis('BTC')
        print(f"建议: {btc_analysis['recommendation']['action']}")
        print(f"置信度: {btc_analysis['recommendation']['confidence']:.2f}")
        print(f"信号数: {len(btc_analysis['signals'])}")

        # 测试机会扫描
        print("\n=== 市场机会扫描 ===")
        opportunities = await aggregator.scan_opportunities()
        for op in opportunities['opportunities']:
            print(f"{op['symbol']}: 分数={op['score']}, 资金费={op['funding_rate']:.3f}%")

        await aggregator.close()

    asyncio.run(test())
