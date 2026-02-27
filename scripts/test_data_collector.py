"""
手动测试市场数据收集器

用法:
    python scripts/test_data_collector.py

需要设置环境变量:
    - ANTHROPIC_API_KEY (可选，用于测试 AI 分析)
"""
import asyncio
import logging
import os
import sys

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


async def main():
    """主测试函数"""
    from src.ai.data.collector import MarketDataCollector
    from src.ai.provider.claude import ClaudeProvider
    from src.ai.context import AIAnalysisContext

    symbol = "BTC/USDT"

    logger.info(f"开始测试数据收集器: {symbol}")

    # 1. 测试数据收集
    async with MarketDataCollector() as collector:
        context = await collector.collect(symbol)

        if context is None:
            logger.error("数据收集失败")
            return

        logger.info("=" * 60)
        logger.info("收集到的数据:")
        logger.info("=" * 60)

        # 打印 K 线信息
        for interval, kline in context.klines.items():
            logger.info(f"\n{interval} 周期:")
            logger.info(f"  当前价格: ${kline.current_price:,.2f}")
            logger.info(f"  数据量: {len(kline.df)} 根K线")

        # 打印指标信息
        for interval, ind in context.indicators.items():
            logger.info(f"\n{interval} 指标:")
            if ind.rsi_14:
                logger.info(f"  RSI(14): {ind.rsi_14:.2f}")
            if ind.ema_9:
                logger.info(f"  EMA9: ${ind.ema_9:,.2f}")
            if ind.macd_histogram is not None:
                logger.info(f"  MACD Histogram: {ind.macd_histogram:+.4f}")
            if ind.bb_position is not None:
                logger.info(f"  BB位置: {ind.bb_position * 100:.1f}%")

        # 打印形态信息
        for interval, patterns in context.patterns.items():
            logger.info(f"\n{interval} 形态:")
            for p in patterns:
                logger.info(f"  - {p.name} (置信度: {p.confidence * 100:.0f}%)")

        # 打印宏观数据
        if context.macro_data:
            logger.info("\n宏观数据:")
            macro = context.macro_data
            if macro.funding_rate is not None:
                logger.info(f"  资金费率: {macro.funding_rate:+.4%}")
            if macro.oi_current:
                logger.info(f"  OI: {macro.oi_current:,.0f}")
            if macro.oi_change_1h is not None:
                logger.info(f"  OI变化(1h): {macro.oi_change_1h:+.1f}%")
            if macro.long_short_ratio:
                logger.info(f"  多空比: {macro.long_short_ratio:.2f}")

        # 2. 测试提示词生成
        logger.info("\n" + "=" * 60)
        logger.info("生成的提示词:")
        logger.info("=" * 60)
        prompt_data = context.to_prompt_data()
        logger.info(prompt_data[:2000])  # 打印前2000字符

        # 3. 测试 AI 分析（如果配置了 API Key）
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if api_key:
            logger.info("\n" + "=" * 60)
            logger.info("测试 AI 分析...")
            logger.info("=" * 60)

            provider = ClaudeProvider({"api_key": api_key})
            provider.initialize()

            try:
                decision = await provider.analyze(context)

                logger.info(f"\nAI 决策:")
                logger.info(f"  操作: {decision.action.value}")
                logger.info(f"  证据数量: {decision.evidence_count}")
                logger.info(f"  证据链:")
                for i, evidence in enumerate(decision.evidence_chain, 1):
                    logger.info(f"    {i}. {evidence}")
                logger.info(f"  否决: {decision.veto_flag}")
                logger.info(f"  入场价: ${decision.entry_price:,.2f}")
                logger.info(f"  止损价: ${decision.stop_loss:,.2f}")
                logger.info(f"  止盈价: ${decision.take_profit:,.2f}")
                logger.info(f"  仓位: ${decision.position_size:.2f}")
                logger.info(f"  理由: {decision.reasoning}")
            except Exception as e:
                logger.error(f"AI 分析失败: {e}")
        else:
            logger.warning("\n未配置 ANTHROPIC_API_KEY，跳过 AI 分析测试")

    logger.info("\n测试完成!")


if __name__ == '__main__':
    asyncio.run(main())
