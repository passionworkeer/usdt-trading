"""
真实历史数据回测脚本

从 Binance API 获取真实数据进行分析
"""
import asyncio
import logging
import sys
import os
from pathlib import Path
from datetime import datetime

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


async def run_real_backtest():
    """运行真实数据回测"""
    from src.ai.data.collector import MarketDataCollector

    symbol = "BTC/USDT"

    logger.info("=" * 60)
    logger.info(f"开始真实历史数据回测: {symbol}")
    logger.info("=" * 60)

    # 检查 API Key
    api_key = os.environ.get("BINANCE_API_KEY")
    if not api_key:
        logger.error("未设置 BINANCE_API_KEY 环境变量")
        return

    logger.info(f"✅ 使用 Binance API Key: {api_key[:10]}...")

    # 1. 收集真实市场数据
    logger.info("\n【步骤 1】从 Binance 获取真实数据...")
    async with MarketDataCollector() as collector:
        context = await collector.collect(symbol)

        if context is None or not context.klines:
            logger.error("无法获取市场数据，请检查网络连接")
            return

        logger.info(f"✅ 成功获取数据:")
        logger.info(f"  - K线周期: {list(context.klines.keys())}")

        # 显示每个周期的数据
        for interval, kline in context.klines.items():
            ind = context.indicators.get(interval)
            logger.info(f"\n  {interval} 周期:")
            logger.info(f"    价格: ${kline.current_price:,.2f}")
            logger.info(f"    K线数: {len(kline.df)}")
            if ind:
                logger.info(f"    RSI: {ind.rsi_14:.1f}" if ind.rsi_14 else "    RSI: N/A")
                logger.info(f"    EMA9: ${ind.ema_9:,.0f}" if ind.ema_9 else "    EMA9: N/A")
                logger.info(f"    EMA21: ${ind.ema_21:,.0f}" if ind.ema_21 else "    EMA21: N/A")

        # 2. 显示形态
        if context.patterns:
            logger.info("\n【步骤 2】识别到的 K 线形态:")
            for interval, patterns in context.patterns.items():
                for p in patterns:
                    logger.info(f"  {interval}: {p.name} (置信度 {p.confidence * 100:.0f}%)")
        else:
            logger.info("\n【步骤 2】未识别到明显形态")

        # 3. 显示宏观数据
        if context.macro_data:
            logger.info("\n【步骤 3】宏观市场数据:")
            m = context.macro_data
            if m.funding_rate is not None:
                logger.info(f"  资金费率: {m.funding_rate:+.4%}")
            if m.oi_current:
                logger.info(f"  OI: {m.oi_current:,.0f}")
            if m.oi_change_1h is not None:
                logger.info(f"  OI变化(1h): {m.oi_change_1h:+.1f}%")
            if m.oi_change_4h is not None:
                logger.info(f"  OI变化(4h): {m.oi_change_4h:+.1f}%")
            if m.long_short_ratio:
                logger.info(f"  多空比: {m.long_short_ratio:.2f}")
        else:
            logger.info("\n【步骤 3】无宏观数据")

        # 4. 生成 AI 提示词
        logger.info("\n【步骤 4】生成 AI 分析提示词...")
        prompt = context.to_prompt_data()
        logger.info(f"提示词长度: {len(prompt)} 字符")

        logger.info("\n" + "=" * 60)
        logger.info("AI 分析提示词:")
        logger.info("=" * 60)
        logger.info(prompt)
        logger.info("=" * 60)

        # 5. 如果有 Claude API，进行 AI 分析
        claude_key = os.environ.get("ANTHROPIC_API_KEY")
        if claude_key:
            logger.info("\n【步骤 5】调用 Claude AI 分析...")
            try:
                from src.ai.provider.claude import ClaudeProvider

                provider = ClaudeProvider({"api_key": claude_key})
                provider.initialize()

                decision = await provider.analyze(context)

                logger.info(f"\n✅ AI 决策结果:")
                logger.info(f"  操作: {decision.action.value}")
                logger.info(f"  证据数量: {decision.evidence_count}")
                logger.info(f"  否决: {decision.veto_flag}")
                logger.info(f"  入场价: ${decision.entry_price:,.2f}")
                logger.info(f"  止损价: ${decision.stop_loss:,.2f}")
                logger.info(f"  止盈价: ${decision.take_profit:,.2f}")
                logger.info(f"  仓位: ${decision.position_size:.2f}")
                logger.info(f"\n  证据链:")
                for i, e in enumerate(decision.evidence_chain, 1):
                    logger.info(f"    {i}. {e}")
                logger.info(f"\n  理由: {decision.reasoning}")

            except Exception as e:
                logger.error(f"AI 分析失败: {e}")
        else:
            logger.info("\n【步骤 5】跳过 AI 分析（未设置 ANTHROPIC_API_KEY）")

    logger.info("\n" + "=" * 60)
    logger.info("回测完成!")
    logger.info("=" * 60)


if __name__ == '__main__':
    asyncio.run(run_real_backtest())
