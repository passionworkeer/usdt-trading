"""
临时回测分析脚本
"""
import asyncio
import aiohttp
import pandas as pd
import numpy as np
import os


def calculate_rsi(prices, period=14):
    """计算 RSI"""
    delta = prices.diff()
    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)

    avg_gain = gain.rolling(window=period).mean()
    avg_loss = loss.rolling(window=period).mean()

    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi


async def run_backtest_analysis():
    """运行完整回测分析"""
    url = 'https://fapi.binance.com/fapi/v1/klines'
    proxy = os.environ.get('HTTP_PROXY') or os.environ.get('HTTPS_PROXY')

    async with aiohttp.ClientSession() as session:
        # 获取720根1小时K线
        params = {
            'symbol': 'BTCUSDT',
            'interval': '1h',
            'limit': 720
        }
        kwargs = {'params': params}
        if proxy:
            kwargs['proxy'] = proxy

        async with session.get(url, **kwargs) as resp:
            if resp.status != 200:
                print(f"API 请求失败: {resp.status}")
                return

            data = await resp.json()
            df = pd.DataFrame(data, columns=[
                'timestamp', 'open', 'high', 'low', 'close', 'volume',
                'close_time', 'quote_volume', 'trades', 'taker_buy_base',
                'taker_buy_quote', 'ignore'
            ])

            for col in ['open', 'high', 'low', 'close', 'volume']:
                df[col] = pd.to_numeric(df[col])

            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')

            print('=' * 70)
            print('历史数据摘要 (30天)')
            print('=' * 70)
            print(f'数据条数: {len(df)}')
            print(f'时间范围: {df["timestamp"].min()} ~ {df["timestamp"].max()}')
            print(f'价格范围: ${df["low"].min():,.2f} ~ ${df["high"].max():,.2f}')
            print(f'最新价格: ${df["close"].iloc[-1]:,.2f}')
            print(f'期间收益: {((df["close"].iloc[-1] - df["close"].iloc[0]) / df["close"].iloc[0] * 100):+.2f}%')
            print()

            # 计算EMA指标
            df['ema20'] = df['close'].ewm(span=20).mean()
            df['ema50'] = df['close'].ewm(span=50).mean()
            df['rsi'] = calculate_rsi(df['close'])

            # 生成信号
            signals = []
            for i in range(50, len(df)):
                row = df.iloc[i]
                prev_row = df.iloc[i-1]

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

            print('=' * 70)
            print('EMA策略信号统计')
            print('=' * 70)
            print(f'总信号数: {len(signals)}')
            buy_signals = [s for s in signals if s['type'] == 'BUY']
            sell_signals = [s for s in signals if s['type'] == 'SELL']
            print(f'买入信号: {len(buy_signals)}')
            print(f'卖出信号: {len(sell_signals)}')
            print()

            print('=' * 70)
            print('所有信号详情')
            print('=' * 70)
            for sig in signals:
                print(f"{sig['time']}: {sig['type']} @ ${sig['price']:,.2f} (RSI: {sig['rsi']:.1f})")
            print()

            # 模拟回测
            print('=' * 70)
            print('模拟回测分析')
            print('=' * 70)

            initial_capital = 10000
            capital = initial_capital
            position = 0
            trades = []
            slippage = 0.002  # 0.2% 滑点
            commission = 0.0005  # 0.05% 手续费

            # 配对交易
            for i in range(len(signals)):
                if signals[i]['type'] == 'BUY' and position == 0:
                    # 买入（考虑滑点和手续费）
                    buy_price = signals[i]['price'] * (1 + slippage)
                    position = (capital / buy_price) * (1 - commission)
                    capital = 0
                    trades.append({
                        'entry_time': signals[i]['time'],
                        'entry_price': signals[i]['price'],
                        'entry_price_real': buy_price,
                        'type': 'BUY'
                    })
                elif signals[i]['type'] == 'SELL' and position > 0:
                    # 卖出
                    sell_price = signals[i]['price'] * (1 - slippage)
                    capital = position * sell_price * (1 - commission)
                    trades[-1].update({
                        'exit_time': signals[i]['time'],
                        'exit_price': signals[i]['price'],
                        'exit_price_real': sell_price,
                        'pnl': (sell_price - trades[-1]['entry_price_real']) / trades[-1]['entry_price_real'],
                        'type': 'SELL'
                    })
                    position = 0

            # 计算结果
            completed_trades = [t for t in trades if 'exit_price' in t]

            if completed_trades:
                total_pnl = sum(t['pnl'] for t in completed_trades)
                win_trades = [t for t in completed_trades if t['pnl'] > 0]
                lose_trades = [t for t in completed_trades if t['pnl'] <= 0]

                win_rate = len(win_trades) / len(completed_trades)
                profit_factor = sum(t['pnl'] for t in win_trades) / abs(sum(t['pnl'] for t in lose_trades)) if lose_trades else float('inf')

                print(f'完成交易数: {len(completed_trades)}')
                print(f'盈利交易: {len(win_trades)}')
                print(f'亏损交易: {len(lose_trades)}')
                print(f'胜率: {win_rate:.2%}')
                print(f'盈亏比: {profit_factor:.2f}')
                print(f'总收益率: {total_pnl:.2%}')
                print(f'最终资金: ${initial_capital * (1 + total_pnl):,.2f}')
                print()

                print('=' * 70)
                print('每笔交易详情')
                print('=' * 70)
                for i, t in enumerate(completed_trades):
                    print(f"交易{i+1}: {t['entry_time'].strftime('%Y-%m-%d %H:%M')}买入@${t['entry_price']:,.0f} -> {t['exit_time'].strftime('%Y-%m-%d %H:%M')}卖出@${t['exit_price']:,.0f}, 收益率: {t['pnl']:+.2%}")

                # 最终持仓分析
                print()
                print('=' * 70)
                print('当前市场状态分析')
                print('=' * 70)
                latest = df.iloc[-1]
                print(f"最新价格: ${latest['close']:,.2f}")
                print(f"EMA20: ${latest['ema20']:,.2f}")
                print(f"EMA50: ${latest['ema50']:,.2f}")
                print(f"RSI: {latest['rsi']:.1f}")

                if latest['ema20'] > latest['ema50']:
                    print("趋势: 多头（EMA20 > EMA50）")
                    print("建议: 持有多单或等待卖出信号")
                else:
                    print("趋势: 空头（EMA20 < EMA50）")
                    print("建议: 空仓或等待买入信号")

                if latest['rsi'] > 70:
                    print("RSI 警告: 超买区域")
                elif latest['rsi'] < 30:
                    print("RSI 警告: 超卖区域")
                else:
                    print("RSI: 正常区域")


if __name__ == '__main__':
    asyncio.run(run_backtest_analysis())
