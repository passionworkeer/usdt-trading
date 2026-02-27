"""
回测演示 - 使用模拟数据

不需要网络连接，使用模拟数据进行演示
"""
import asyncio
import logging
import sys
from pathlib import Path
from datetime import datetime, timedelta

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


def create_mock_klines():
    """创建模拟 K 线数据"""
    import pandas as pd
    import numpy as np

    # 创建 100 根 15 分钟 K 线
    dates = pd.date_range(start='2024-01-01', periods=100, freq='15min')

    # 模拟 BTC 价格走势
    np.random.seed(42)
    base_price = 67500
    trend = np.cumsum(np.random.randn(100) * 50)  # 随机游走
    prices = base_price + trend

    # 生成 OHLCV 数据
    data = {
        'timestamp': dates,
        'open': prices - np.random.uniform(0, 100, 100),
        'high': prices + np.random.uniform(0, 200, 100),
        'low': prices - np.random.uniform(0, 200, 100),
        'close': prices,
        'volume': np.random.uniform(500, 2000, 100),
    }

    df = pd.DataFrame(data)
    return df


def create_mock_indicators():
    """创建模拟指标"""
    from src.ai.context import IndicatorSet

    return IndicatorSet(
        rsi_14=58.5,
        ema_9=67450.0,
        ema_21=67300.0,
        ema_50=67000.0,
        ema_200=65000.0,
        macd=150.0,
        macd_signal=100.0,
        macd_histogram=50.0,
        atr_14=450.0,
        bb_upper=69000.0,
        bb_middle=67500.0,
        bb_lower=66000.0,
        bb_position=0.65,
        volume_ratio=1.8,
    )


def create_mock_macro():
    """创建模拟宏观数据"""
    from src.ai.context import MacroMarketData

    return MacroMarketData(
        funding_rate=0.0001,
        oi_current=52000,
        oi_change_1h=5.2,
        oi_change_4h=8.7,
        mark_price=67500,
        index_price=67450,
        price_diff_pct=0.07,
        long_short_ratio=1.25,
        long_ratio=0.55,
        short_ratio=0.45,
    )


async def run_demo():
    """运行演示"""
    from src.ai.context import (
        AIAnalysisContext,
        KLineData,
        CandlestickPattern,
    )
    from src.ai.data.indicators import TechnicalIndicatorsCalculator
    from src.ai.data.patterns import PatternRecognizer

    symbol = "BTC/USDT"

    logger.info("=" * 60)
    logger.info(f"开始回测演示 (模拟数据): {symbol}")
    logger.info("=" * 60)

    # 1. 创建模拟 K 线数据
    logger.info("\n【步骤 1】生成模拟 K 线数据...")

    # 创建 15 分钟 K 线
    df_15m = create_mock_klines()
    kline_15m = KLineData(interval='15m', df=df_15m)

    # 创建 4 小时 K 线（复制 15m 数据作为示例）
    kline_4h = KLineData(interval='4h', df=df_15m.copy())

    # 创建 1 天 K 线
    kline_1d = KLineData(interval='1d', df=df_15m.copy())

    klines = {
        '15m': kline_15m,
        '4h': kline_4h,
        '1d': kline_1d,
    }

    logger.info(f"✅ 生成 K 线数据:")
    for interval, k in klines.items():
        logger.info(f"  - {interval}: 价格 ${k.current_price:,.2f}, {len(k.df)} 根")

    # 2. 计算技术指标
    logger.info("\n【步骤 2】计算技术指标...")
    indicators = TechnicalIndicatorsCalculator.calculate_all(klines)

    logger.info(f"✅ 计算指标:")
    for interval, ind in indicators.items():
        logger.info(f"  - {interval}: RSI={ind.rsi_14:.1f}, EMA9=${ind.ema_9:,.0f}")

    # 3. 识别形态
    logger.info("\n【步骤 3】识别 K 线形态...")
    patterns = PatternRecognizer.recognize(klines)

    logger.info(f"✅ 识别形态:")
    for interval, pats in patterns.items():
        for p in pats:
            logger.info(f"  - {interval}: {p.name} (置信度 {p.confidence * 100:.0f}%)")

    # 4. 创建宏观数据
    logger.info("\n【步骤 4】宏观市场数据...")
    macro_data = create_mock_macro()
    logger.info(f"✅ 资金费率: {macro_data.funding_rate:+.4%}")
    logger.info(f"✅ OI变化: 1h={macro_data.oi_change_1h:+.1f}%, 4h={macro_data.oi_change_4h:+.1f}%")
    logger.info(f"✅ 多空比: {macro_data.long_short_ratio:.2f}")

    # 5. 构建 AI 上下文
    logger.info("\n【步骤 5】构建 AI 分析上下文...")
    context = AIAnalysisContext(
        symbol=symbol,
        timestamp=datetime.now(),
        klines=klines,
        indicators=indicators,
        patterns=patterns,
        macro_data=macro_data,
    )

    logger.info(f"✅ 上下文构建完成:")
    logger.info(f"  - K线周期: {list(context.klines.keys())}")
    logger.info(f"  - 指标周期: {list(context.indicators.keys())}")
    logger.info(f"  - 形态数量: {sum(len(p) for p in context.patterns.values())}")

    # 6. 生成提示词
    logger.info("\n【步骤 6】生成 AI 分析提示词...")
    prompt = context.to_prompt_data()
    logger.info(f"✅ 提示词长度: {len(prompt)} 字符")

    logger.info(f"\n完整提示词:")
    logger.info("-" * 60)
    logger.info(prompt)
    logger.info("-" * 60)

    # 7. 模拟 AI 决策
    logger.info("\n【步骤 7】模拟 AI 决策...")

    # 基于当前数据生成模拟决策
    ind = indicators.get('15m')
    if ind:
        # 简单决策逻辑
        if ind.rsi_14 < 30:
            action = "buy"
            reasoning = "RSI 超卖，反弹机会"
        elif ind.rsi_14 > 70:
            action = "sell"
            reasoning = "RSI 超买，回调风险"
        elif ind.macd_histogram and ind.macd_histogram > 0:
            action = "buy"
            reasoning = "MACD 金叉，多头信号"
        else:
            action = "hold"
            reasoning = "无明确信号，观望"

        logger.info(f"\n✅ 模拟 AI 决策结果:")
        logger.info(f"  操作: {action.upper()}")
        logger.info(f"  入场价: ${ind.ema_9:,.2f}")
        logger.info(f"  止损价: ${ind.ema_9 * 0.98:,.2f}")
        logger.info(f"  止盈价: ${ind.ema_9 * 1.04:,.2f}")
        logger.info(f"  理由: {reasoning}")

        # 生成证据链
        evidence_chain = []
        if ind.rsi_14:
            evidence_chain.append(f"RSI(14)={ind.rsi_14:.1f}，{'超卖区域' if ind.rsi_14 < 30 else '超买区域' if ind.rsi_14 > 70 else '中性区域'}")
        if ind.macd_histogram:
            evidence_chain.append(f"MACD {'金叉' if ind.macd_histogram > 0 else '死叉'}，{'多头' if ind.macd_histogram > 0 else '空头'}信号")
        if ind.bb_position is not None:
            evidence_chain.append(f"布林带位置 {ind.bb_position * 100:.0f}%")

        logger.info(f"\n  证据链:")
        for i, e in enumerate(evidence_chain, 1):
            logger.info(f"    {i}. {e}")

    logger.info("\n" + "=" * 60)
    logger.info("回测演示完成!")
    logger.info("=" * 60)


if __name__ == '__main__':
    asyncio.run(run_demo())
