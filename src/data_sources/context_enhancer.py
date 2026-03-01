"""
市场上下文增强器
在 AI 决策前自动注入资金费率、多空比等数据
"""
import logging
from typing import Dict, Any, Optional
from datetime import datetime

from src.data_sources import (
    get_funding_source,
    get_free_data_source,
)
from src.models import MarketContext

logger = logging.getLogger(__name__)


async def enhance_market_context(context: MarketContext) -> MarketContext:
    """
    增强市场上下文 - 在 AI 决策前注入资金费率数据

    Args:
        context: 原始市场上下文

    Returns:
        增强后的市场上下文
    """
    symbol = context.symbol

    try:
        # 获取资金费率数据
        funding_source = await get_funding_source()
        funding_data = await funding_source.get_comprehensive_funding(symbol)

        if funding_data:
            # 将资金费率数据注入到 indicators 中
            enhanced_indicators = dict(context.indicators)

            # 添加资金费率
            enhanced_indicators['funding_rate'] = funding_data.get('funding_rate', 0)
            enhanced_indicators['funding_sentiment'] = funding_data.get('sentiment', 'neutral')
            enhanced_indicators['funding_score'] = funding_data.get('sentiment_score', 0.5)
            enhanced_indicators['next_funding_time'] = funding_data.get('next_funding_time')

            # 添加多空比
            ls = funding_data.get('long_short', {})
            if ls:
                enhanced_indicators['long_ratio'] = ls.get('long_ratio', 50)
                enhanced_indicators['short_ratio'] = ls.get('short_ratio', 50)

            # 添加吃单多空比
            taker = funding_data.get('taker_ratio', {})
            if taker:
                enhanced_indicators['taker_long_ratio'] = taker.get('long_buy_ratio', 1)

            # 添加资金费率信号
            funding_signals = funding_data.get('signals', [])
            if funding_signals:
                enhanced_indicators['funding_signals'] = [
                    {'type': s.get('type'), 'message': s.get('message')}
                    for s in funding_signals
                ]

            # 计算综合信号
            signals = []

            # 极端多空信号
            if funding_data.get('sentiment') == 'bullish':
                signals.append('bullish_funding')
            elif funding_data.get('sentiment') == 'bearish':
                signals.append('bearish_funding')

            # 资金费率极端值
            fr = funding_data.get('funding_rate', 0)
            if fr > 0.1:  # 高资金费率 = 多头市场
                signals.append('high_funding_long')
            elif fr < -0.1:
                signals.append('high_funding_short')

            enhanced_indicators['enhanced_signals'] = signals

            logger.info(
                f"市场上下文已增强: {symbol}, "
                f"资金费率={fr:.4f}%, "
                f"情绪={funding_data.get('sentiment')}"
            )

            # 创建新的 MarketContext（因为是 frozen 的）
            return MarketContext(
                symbol=context.symbol,
                current_price=context.current_price,
                price_history=context.price_history,
                volume_24h=context.volume_24h,
                market_cap=context.market_cap,
                indicators=enhanced_indicators,
                news_sentiment=context.news_sentiment,
                timestamp=context.timestamp
            )

    except Exception as e:
        logger.error(f"增强市场上下文失败: {e}")

    # 如果失败，返回原始上下文
    return context


def get_funding_summary(context: MarketContext) -> Dict[str, Any]:
    """
    从 MarketContext 中提取资金费率摘要

    Args:
        context: 市场上下文

    Returns:
        资金费率摘要字典
    """
    ind = context.indicators

    return {
        'funding_rate': ind.get('funding_rate', 0),
        'funding_sentiment': ind.get('funding_sentiment', 'neutral'),
        'funding_score': ind.get('funding_score', 0.5),
        'long_ratio': ind.get('long_ratio'),
        'short_ratio': ind.get('short_ratio'),
        'taker_long_ratio': ind.get('taker_long_ratio'),
        'enhanced_signals': ind.get('enhanced_signals', []),
        'funding_signals': ind.get('funding_signals', [])
    }


def should_follow_funding_signal(context: MarketContext) -> Optional[str]:
    """
    判断是否应该跟随资金费率信号

    Returns:
        'buy', 'sell', 或 None（无信号）
    """
    summary = get_funding_summary(context)
    signals = summary.get('enhanced_signals', [])

    # 优先检查极端信号
    if 'high_funding_long' in signals:
        return 'sell'  # 高资金费率做空（做空资金费率收益）
    elif 'high_funding_short' in signals:
        return 'buy'   # 高资金费率做多

    # 检查情绪
    sentiment = summary.get('funding_sentiment', 'neutral')
    score = summary.get('funding_score', 0.5)

    if sentiment == 'bullish' and score > 0.6:
        return 'buy'
    elif sentiment == 'bearish' and score < 0.4:
        return 'sell'

    return None


# ========== 测试 ==========

if __name__ == '__main__':
    import asyncio
    from src.models import MarketContext

    async def test():
        # 创建测试上下文
        context = MarketContext(
            symbol='BTC',
            current_price=50000,
            indicators={}
        )

        # 增强上下文
        enhanced = await enhance_market_context(context)

        print("=== 原始上下文 ===")
        print(f"indicators: {context.indicators}")

        print("\n=== 增强后 ===")
        print(f"funding_rate: {enhanced.indicators.get('funding_rate')}")
        print(f"funding_sentiment: {enhanced.indicators.get('funding_sentiment')}")
        print(f"enhanced_signals: {enhanced.indicators.get('enhanced_signals')}")

        print("\n=== 摘要 ===")
        summary = get_funding_summary(enhanced)
        print(summary)

        print("\n=== 信号判断 ===")
        signal = should_follow_funding_signal(enhanced)
        print(f"建议: {signal}")

    asyncio.run(test())
