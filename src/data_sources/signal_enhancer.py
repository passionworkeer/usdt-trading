"""
市场信号增强器
在 AI 决策前自动注入免费的市场数据
包括：资金费率、多空比、多交易所价格验证
"""
import asyncio
import logging
from typing import Dict, Any, Optional
from datetime import datetime

from src.data_sources import (
    get_market_aggregator,
    MarketAggregator,
    get_funding_source,
    FundingRateSource,
    get_free_data_source,
    FreeDataSource,
)

logger = logging.getLogger(__name__)


class SignalEnhancer:
    """
    信号增强器
    为 AI 决策提供额外的市场信号
    """

    def __init__(self):
        self.aggregator: Optional[MarketAggregator] = None
        self.funding_source: Optional[FundingRateSource] = None
        self.price_source: Optional[FreeDataSource] = None

    async def initialize(self):
        """初始化数据源"""
        self.aggregator = await get_market_aggregator()
        self.funding_source = await get_funding_source()
        self.price_source = await get_free_data_source()
        logger.info("信号增强器已初始化")

    async def enhance_context(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        增强市场上下文

        在 AI 决策之前，添加额外的数据：
        1. 资金费率 & 多空比
        2. 多交易所价格验证
        3. 综合信号建议
        """
        symbol = context.get('symbol', '')
        if not symbol:
            return context

        logger.info(f"增强信号: {symbol}")

        # 获取综合分析数据
        try:
            analysis = await self.aggregator.get_full_analysis(symbol)

            # 添加到 context 中
            enhanced = context.copy()

            # 1. 添加资金费率数据
            if analysis.get('funding'):
                funding = analysis['funding']
                enhanced['funding_rate'] = funding.get('funding_rate', 0)
                enhanced['funding_sentiment'] = funding.get('sentiment', 'neutral')
                enhanced['funding_score'] = funding.get('sentiment_score', 0.5)
                enhanced['funding_signals'] = funding.get('signals', [])

            # 2. 添加价格数据
            if analysis.get('price'):
                price = analysis['price']
                enhanced['price_change_24h'] = price.get('change_24h', 0)
                enhanced['volume_24h'] = price.get('volume_24h', 0)

            # 3. 添加异常检测
            if analysis.get('anomaly'):
                anomaly = analysis['anomaly']
                enhanced['price_anomaly'] = anomaly.get('is_anomaly', False)
                enhanced['price_diff_pct'] = anomaly.get('max_diff_pct', 0)

            # 4. 添加综合建议
            if analysis.get('recommendation'):
                rec = analysis['recommendation']
                enhanced['market_recommendation'] = rec.get('action', 'neutral')
                enhanced['market_confidence'] = rec.get('confidence', 0.3)
                enhanced['market_summary'] = rec.get('summary', '')

            # 5. 添加交易信号
            enhanced['enhanced_signals'] = analysis.get('signals', [])

            # 6. 添加时间戳
            enhanced['signal_enhanced_at'] = datetime.now().isoformat()

            logger.info(
                f"信号增强完成: {symbol}, "
                f"资金费率={enhanced.get('funding_rate', 0):.4f}%, "
                f"建议={enhanced.get('market_recommendation', 'N/A')}"
            )

            return enhanced

        except Exception as e:
            logger.error(f"信号增强失败: {e}")
            return context

    async def get_quick_signals(self, symbol: str) -> Dict[str, Any]:
        """
        快速获取信号（不依赖完整上下文）
        """
        try:
            analysis = await self.aggregator.get_full_analysis(symbol)
            return {
                'symbol': symbol,
                'funding_rate': analysis.get('funding', {}).get('funding_rate', 0),
                'sentiment': analysis.get('funding', {}).get('sentiment', 'neutral'),
                'recommendation': analysis.get('recommendation', {}).get('action', 'neutral'),
                'confidence': analysis.get('recommendation', {}).get('confidence', 0),
                'anomaly': analysis.get('anomaly', {}).get('is_anomaly', False),
                'signals': analysis.get('signals', []),
            }
        except Exception as e:
            logger.error(f"快速信号获取失败: {e}")
            return {}

    async def scan_and_notify(self) -> Dict[str, Any]:
        """
        扫描全市场机会并返回
        """
        try:
            opportunities = await self.aggregator.scan_opportunities()
            return opportunities
        except Exception as e:
            logger.error(f"市场扫描失败: {e}")
            return {'opportunities': [], 'total_scanned': 0}

    async def close(self):
        """关闭连接"""
        if self.aggregator:
            await self.aggregator.close()


# 全局实例
_enhancer: Optional[SignalEnhancer] = None


async def get_signal_enhancer() -> SignalEnhancer:
    """获取信号增强器实例"""
    global _enhancer
    if _enhancer is None:
        _enhancer = SignalEnhancer()
        await _enhancer.initialize()
    return _enhancer


# ========== 快速使用函数 ==========

async def quick_funding_check(symbol: str) -> str:
    """
    快速检查资金费率

    Returns:
        'buy', 'sell', 或 'neutral'
    """
    try:
        funding_source = await get_funding_source()
        funding = await funding_source.get_comprehensive_funding(symbol)

        if not funding:
            return 'neutral'

        sentiment = funding.get('sentiment', 'neutral')

        # 根据资金费率给出建议
        funding_rate = funding.get('funding_rate', 0)

        # 极端情况
        if funding.get('signals'):
            for sig in funding['signals']:
                sig_type = sig.get('type', '')
                if sig_type in ['extreme_long', 'high_funding_long']:
                    return 'sell'  # 极端多头=可能反转
                elif sig_type in ['extreme_short', 'high_funding_short']:
                    return 'buy'   # 极端空头=可能反转

        # 正常情况：根据情绪
        if sentiment == 'bullish':
            return 'buy'
        elif sentiment == 'bearish':
            return 'sell'
        return 'neutral'

    except Exception as e:
        logger.error(f"资金费率检查失败: {e}")
        return 'neutral'


async def check_price_anomaly(symbol: str) -> Optional[Dict]:
    """
    检查价格是否异常（插针）
    """
    try:
        price_source = await get_free_data_source()
        prices = await price_source.get_multi_exchange_prices(symbol)

        if not prices or len(prices) < 2:
            return None

        return price_source.detect_price_anomaly(prices)

    except Exception as e:
        logger.error(f"价格异常检查失败: {e}")
        return None


# ========== 测试 ==========

if __name__ == '__main__':
    async def test():
        enhancer = SignalEnhancer()
        await enhancer.initialize()

        # 测试信号增强
        print("=== BTC 信号增强 ===")
        context = {'symbol': 'BTC', 'current_price': 50000}
        enhanced = await enhancer.enhance_context(context)
        print(f"资金费率: {enhanced.get('funding_rate', 0):.4f}%")
        print(f"建议: {enhanced.get('market_recommendation')}")
        print(f"置信度: {enhanced.get('market_confidence', 0):.2f}")

        # 测试快速检查
        print("\n=== 快速资金费率检查 ===")
        action = await quick_funding_check('ETH')
        print(f"ETH 建议: {action}")

        # 测试价格异常
        print("\n=== 价格异常检查 ===")
        anomaly = await check_price_anomaly('BTC')
        if anomaly:
            print(f"是否异常: {anomaly['is_anomaly']}")
            print(f"偏差: {anomaly['max_diff_pct']:.3f}%")

        # 测试市场扫描
        print("\n=== 市场机会扫描 ===")
        ops = await enhancer.scan_and_notify()
        for op in ops.get('opportunities', [])[:3]:
            print(f"{op['symbol']}: 分数={op['score']}, 资金费={op['funding_rate']:.3f}%")

        await enhancer.close()

    asyncio.run(test())
