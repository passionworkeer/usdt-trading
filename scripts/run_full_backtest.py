"""
完整历史回测脚本

获取更长时间范围的历史数据，进行完整回测
"""
import asyncio
import logging
import sys
import os
from pathlib import Path
from datetime import datetime, timedelta

sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


async def run_full_backtest():
    """运行完整回测"""
    from src.ai.data.collector import MarketDataCollector

    symbol = "BTC/USDT"

    logger.info("=" * 70)
    logger.info(f"完整历史数据回测: {symbol}")
    logger.info("=" * 70)

    # 检查 API Key
    api_key = os.environ.get("BINANCE_API_KEY")
    if not api_key:
        logger.error("未设置 BINANCE_API_KEY")
        return

    logger.info(f"✅ Binance API: {api_key[:10]}...")

    # 获取数据
    async with MarketDataCollector() as collector:
        logger.info("\n【1】获取实时数据...")
        context = await collector.collect(symbol)

        if not context or not context.klines:
            logger.error("无法获取数据")
            return

        logger.info(f"✅ 实时数据获取成功")
        for interval, kline in context.klines.items():
            logger.info(f"  {interval}: ${kline.current_price:,.2f}")

        # 获取历史数据用于回测
        logger.info("\n【2】获取历史K线数据用于回测分析...")

        # 获取更长时间范围的数据
        import aiohttp
        import pandas as pd

        # 获取 1 个月的 1 小时数据用于策略回测
        url = "https://fapi.binance.com/fapi/v1/klines"
        proxy = os.environ.get("HTTP_PROXY") or os.environ.get("HTTPS_PROXY")

        async with aiohttp.ClientSession() as session:
            params = {
                'symbol': 'BTCUSDT',
                'interval': '1h',
                'limit': 720  # 30天 * 24小时
            }
            kwargs = {'params': params}
            if proxy:
                kwargs['proxy'] = proxy

            async with session.get(url, **kwargs) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    df = pd.DataFrame(data, columns=[
                        'timestamp', 'open', 'high', 'low', 'close', 'volume',
                        'close_time', 'quote_volume', 'trades', 'taker_buy_base',
                        'taker_buy_quote', 'ignore'
                    ])

                    # 转换类型
                    for col in ['open', 'high', 'low', 'close', 'volume']:
                        df[col] = pd.to_numeric(df[col])

                    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')

                    logger.info(f"✅ 获取历史数据: {len(df)} 根K线")
                    logger.info(f"  时间范围: {df['timestamp'].min()} ~ {df['timestamp'].max()}")
                    logger.info(f"  价格范围: ${df['low'].min():,.2f} ~ ${df['high'].max():,.2f}")

                    # 计算一些基本统计
                    logger.info(f"\n【3】历史数据分析:")
                    logger.info(f"  最高价: ${df['high'].max():,.2f}")
                    logger.info(f"  最低价: ${df['low'].min():,.2f}")
                    logger.info(f"  平均成交量: {df['volume'].mean():,.0f} BTC")

                    # 计算简单收益
                    returns = (df['close'].iloc[-1] - df['close'].iloc[0]) / df['close'].iloc[0] * 100
                    logger.info(f"  期间收益: {returns:+.2f}%")

                    # 简单的技术分析
                    df['rsi'] = calculate_rsi(df['close'])
                    df['ema20'] = df['close'].ewm(span=20).mean()
                    df['ema50'] = df['close'].ewm(span=50).mean()

                    # 生成信号
                    signals = []
                    for i in range(50, len(df)):
                        row = df.iloc[i]
                        prev_row = df.iloc[i-1]

                        # 简单金叉/死叉信号
                        if prev_row['ema20'] <= prev_row['ema50'] and row['ema20'] > row['ema50']:
                            signals.append({
                                'time': row['timestamp'],
                                'type': 'BUY',
                                'price': row['close'],
                                'rsi': row['rsi']
                            })
                        elif prev_row['ema20'] >= prev_row['ema50'] and row['ema20'] < row['ema50']:
                            signals.append({
                                'time': row['timestamp'],
                                'type': 'SELL',
                                'price': row['close'],
                                'rsi': row['rsi']
                            })

                    logger.info(f"\n【4】策略信号统计:")
                    logger.info(f"  总信号数: {len(signals)}")
                    buy_signals = [s for s in signals if s['type'] == 'BUY']
                    sell_signals = [s for s in signals if s['type'] == 'SELL']
                    logger.info(f"  买入信号: {len(buy_signals)}")
                    logger.info(f"  卖出信号: {len(sell_signals)}")

                    if signals:
                        logger.info(f"\n【5】最近信号:")
                        for sig in signals[-5:]:
                            logger.info(f"  {sig['time']}: {sig['type']} @ ${sig['price']:,.2f} (RSI: {sig['rsi']:.1f})")

        # 生成完整的 AI 分析上下文
        logger.info(f"\n【6】生成AI分析上下文...")
        prompt = context.to_prompt_data()
        logger.info(f"提示词长度: {len(prompt)} 字符")

        logger.info(f"\n" + "=" * 70)
        logger.info("完整分析数据:")
        logger.info("=" * 70)
        logger.info(prompt)
        logger.info("=" * 70)

    logger.info(f"\n✅ 回测数据收集完成!")
    logger.info(f"\n接下来可以:")
    logger.info(f"  1. 将历史数据保存到本地进行更详细的回测")
    logger.info(f"  2. 使用 AI 分析选择最佳入场点")
    logger.info(f"  3. 模拟执行交易并计算收益")


def calculate_rsi(prices, period=14):
    """计算 RSI"""
    import numpy as np
    delta = prices.diff()
    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)

    avg_gain = gain.rolling(window=period).mean()
    avg_loss = loss.rolling(window=period).mean()

    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi


if __name__ == '__main__':
    asyncio.run(run_full_backtest())
