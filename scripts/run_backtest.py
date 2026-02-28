#!/usr/bin/env python3
"""
智能杠杆回测引擎 - 根据市场情况动态调整杠杆
"""
import asyncio
import json
from pathlib import Path
import pandas as pd
import numpy as np
import aiohttp
from aiohttp_socks import ProxyConnector
from datetime import datetime

SYMBOLS = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'BNBUSDT']
POSITION_SIZE = 20  # 每次20U

# 回测时间范围 - 地狱难度测试
TEST_PERIODS = [
    ('2025-10-01', '2025-12-31', '2025年Q4'),
    ('2025-06-01', '2025-09-30', '2025年夏季'),
    ('2024-08-01', '2024-08-31', '2024年8月'),
]

# 共用本金
SHARED_CAPITAL = 200.0

# 杠杆和止损设置（保守版）
MAX_LEVERAGE = 10  # 最大10倍杠杆
STOP_LOSS_PCT = {
    10: 0.03,   # 10倍杠杆，3%止损 = 本金30%风险
    5: 0.05,    # 5倍杠杆，5%止损 = 本金25%风险
}

# 手续费率 (taker 0.05% 单边，0.1%来回)
FEE_RATE = 0.0005


class Backtester:
    def __init__(self):
        self.connector = ProxyConnector.from_url('http://127.0.0.1:7890')
        self.session = None
        self.results = {}

    async def _get_session(self):
        if self.session is None:
            self.session = aiohttp.ClientSession(connector=self.connector)
        return self.session

    async def fetch_klines(self, symbol: str, interval: str = '4h', limit: int = 500) -> pd.DataFrame:
        url = "https://fapi.binance.com/fapi/v1/klines"
        session = await self._get_session()
        async with session.get(url, params={'symbol': symbol, 'interval': interval, 'limit': limit},
                              timeout=aiohttp.ClientTimeout(total=30)) as resp:
            data = await resp.json()

        df = pd.DataFrame(data, columns=['t', 'o', 'h', 'l', 'c', 'v', 'ct', 'qv', 'n', 'tbb', 'tbq', 'i'])
        df['time'] = pd.to_datetime(df['t'], unit='ms')
        for col in ['o', 'h', 'l', 'c', 'v']:
            df[col] = df[col].astype(float)
        return df

    def calculate_confidence(self, df: pd.DataFrame, i: int) -> tuple:
        """
        根据市场情况计算信号强度和推荐杠杆
        返回: (confidence_score, recommended_leverage)
        """
        current = df.iloc[i]
        price = current['c']
        ma20 = current['ma20']
        ma50 = current['ma50']
        ma20_5ago = df['ma20'].iloc[i-5] if i >= 5 else ma20
        ma50_5ago = df['ma50'].iloc[i-5] if i >= 5 else ma50

        # 1. 趋势强度 (MA20与MA50的距离)
        if ma50 > 0:
            ma_distance_pct = abs(ma20 - ma50) / ma50 * 100
        else:
            ma_distance_pct = 0

        # 2. 趋势方向和动量
        if ma20 > ma50 * 1.02 and ma20 > ma20_5ago:
            trend = 'strong_bull'
            trend_score = 2
        elif ma20 > ma50 * 1.01 and ma20 > ma20_5ago:
            trend = 'bull'
            trend_score = 1.5
        elif ma20 < ma50 * 0.98 and ma20 < ma20_5ago:
            trend = 'strong_bear'
            trend_score = 2
        elif ma20 < ma50 * 0.99 and ma20 < ma20_5ago:
            trend = 'bear'
            trend_score = 1.5
        else:
            trend = 'range'
            trend_score = 0.5

        # 3. 波动率 (最近20根K线的波动)
        recent = df.iloc[max(0, i-20):i]
        if len(recent) > 1:
            volatility = recent['c'].pct_change().std()
        else:
            volatility = 0.02

        # 4. 计算置信度分数 (0-100)
        confidence = min(100, ma_distance_pct * 10 + trend_score * 20)

        # 波动率调整：波动越大，杠杆越低
        vol_multiplier = 1.0
        if volatility > 0.05:  # 高波动
            vol_multiplier = 0.3
        elif volatility > 0.03:  # 中波动
            vol_multiplier = 0.5
        elif volatility < 0.02:  # 低波动
            vol_multiplier = 1.0

        # 5. 根据置信度确定杠杆 (保守版，最大10倍)
        if confidence >= 80:
            leverage = 10  # 强信号
        elif confidence >= 60:
            leverage = 8   # 中强信号
        elif confidence >= 40:
            leverage = 5   # 中等信号
        elif confidence >= 20:
            leverage = 3   # 弱信号
        else:
            leverage = 0   # 不做

        # 应用波动率调整
        leverage = int(leverage * vol_multiplier)
        leverage = max(0, min(MAX_LEVERAGE, leverage))  # 限制在0-10之间，0=不做

        return confidence, leverage, trend, volatility

    async def run_backtest(self, symbol: str, shared_capital: float) -> dict:
        """运行回测 - 共用本金模式"""
        # 多获取一些历史数据用于计算均线
        df = await self.fetch_klines(symbol, limit=1500)
        df['ma20'] = df['c'].rolling(20).mean()
        df['ma50'] = df['c'].rolling(50).mean()

        # 过滤只保留2026年1月-2月的数据
        df = df[(df['time'] >= START_DATE) & (df['time'] <= END_DATE)]
        print(f"    {symbol}: 使用 {len(df)} 根K线 ({START_DATE} ~ {END_DATE})")

        # 需要足够的数据计算均线
        if len(df) < 60:
            print(f"    {symbol}: 数据不足，跳过")
            return {
                'symbol': symbol,
                'initial_capital': shared_capital,
                'final_capital': shared_capital,
                'profit': 0,
                'profit_pct': 0,
                'total_trades': 0,
                'wins': 0,
                'losses': 0,
                'win_rate': 0,
                'avg_leverage': 0,
                'trades': []
            }

        # 模拟交易 - 使用共享本金
        capital = shared_capital
        trades = []
        positions = []

        for i in range(50, len(df)):
            current = df.iloc[i]
            price = current['c']

            # 获取置信度和推荐杠杆
            confidence, leverage, trend, volatility = self.calculate_confidence(df, i)

            # 平仓检查
            for pos in positions[:]:
                lev = pos.get('leverage', 5)
                open_fee = pos.get('open_fee', 0)

                if pos['side'] == 'LONG':
                    if price <= pos['stop'] or price >= pos['target']:
                        # 计算盈亏 (扣除手续费)
                        raw_pnl = (price - pos['entry']) / pos['entry'] * POSITION_SIZE * lev
                        close_fee = POSITION_SIZE * FEE_RATE  # 平仓手续费（按保证金算）
                        pnl = raw_pnl - open_fee - close_fee
                        capital += pnl
                        pos['exit'] = price
                        pos['pnl'] = pnl
                        pos['raw_pnl'] = raw_pnl
                        pos['fees'] = open_fee + close_fee
                        pos['exit_time'] = str(current['time'])
                        trades.append(pos)
                        positions.remove(pos)
                else:  # SHORT
                    if price >= pos['stop'] or price <= pos['target']:
                        raw_pnl = (pos['entry'] - price) / pos['entry'] * POSITION_SIZE * lev
                        close_fee = price * lev * POSITION_SIZE * FEE_RATE
                        pnl = raw_pnl - open_fee - close_fee
                        capital += pnl
                        pos['exit'] = price
                        pos['pnl'] = pnl
                        pos['raw_pnl'] = raw_pnl
                        pos['fees'] = open_fee + close_fee
                        pos['exit_time'] = str(current['time'])
                        trades.append(pos)
                        positions.remove(pos)
                        pos['exit_time'] = str(current['time'])
                        trades.append(pos)
                        positions.remove(pos)

            # 开仓检查 - 每个币种最多一个仓位
            symbol_has_position = any(p['symbol'] == symbol for p in positions)
            if not symbol_has_position and capital >= POSITION_SIZE and leverage > 0:
                if trend in ['strong_bull', 'bull', 'strong_bear', 'bear']:
                    # 根据杠杆计算止损比例
                    if leverage >= 10:
                        stop_pct = 0.02  # 10倍杠杆，2%止损
                    elif leverage >= 5:
                        stop_pct = 0.03  # 5-9倍杠杆，3%止损
                    else:
                        stop_pct = 0.05  # 5倍以下，5%止损

                    target_pct = stop_pct * 2  # 止盈是止损的2倍

                    if 'bull' in trend:
                        side = 'LONG'
                        stop = price * (1 - stop_pct)
                        target = price * (1 + target_pct)
                    else:
                        side = 'SHORT'
                        stop = price * (1 + stop_pct)
                        target = price * (1 - target_pct)

                    # 开仓手续费
                    open_fee = POSITION_SIZE * FEE_RATE  # 开仓手续费（按保证金算）

                    positions.append({
                        'symbol': symbol,
                        'side': side,
                        'entry': price,
                        'stop': stop,
                        'target': target,
                        'leverage': leverage,
                        'confidence': confidence,
                        'stop_pct': stop_pct,
                        'open_fee': open_fee,
                        'entry_time': str(current['time']),
                        'exit': None,
                        'pnl': None,
                        'status': 'OPEN'
                    })

        # 平掉最后持仓
        for pos in positions:
            pos['exit'] = df.iloc[-1]['c']
            pos['exit_time'] = str(df.iloc[-1]['time'])
            lev = pos.get('leverage', 20)

            if pos['side'] == 'LONG':
                pnl = (pos['exit'] - pos['entry']) / pos['entry'] * POSITION_SIZE * lev
            else:
                pnl = (pos['entry'] - pos['exit']) / pos['entry'] * POSITION_SIZE * lev
            pos['pnl'] = pnl
            capital += pnl
            trades.append(pos)

        wins = [t for t in trades if t['pnl'] > 0]
        avg_leverage = np.mean([t.get('leverage', 20) for t in trades]) if trades else 0

        return {
            'symbol': symbol,
            'initial_capital': shared_capital,
            'final_capital': capital,
            'profit': capital - shared_capital,
            'profit_pct': (capital - shared_capital) / shared_capital * 100,
            'total_trades': len(trades),
            'wins': len(wins),
            'losses': len(trades) - len(wins),
            'win_rate': len(wins) / len(trades) * 100 if trades else 0,
            'avg_leverage': avg_leverage,
            'trades': trades
        }

    async def run_all_trades_together(self):
        """所有币种同时交易 - 共用200U本金"""
        print(f"Running smart leverage backtest (4币种同时交易，共享200U)...")

        # 同时获取所有币种数据
        dfs = {}
        for symbol in SYMBOLS:
            print(f"  获取 {symbol} 数据...")
            df = await self.fetch_klines(symbol, limit=1500)
            df['ma20'] = df['c'].rolling(20).mean()
            df['ma50'] = df['c'].rolling(50).mean()
            df = df[(df['time'] >= START_DATE) & (df['time'] <= END_DATE)]
            dfs[symbol] = df
            print(f"    {symbol}: {len(df)} 根K线")

        # 找到最短的时间序列
        min_len = min(len(df) for df in dfs.values())

        # 模拟交易 - 共用本金
        capital = SHARED_CAPITAL
        all_trades = []
        positions = {}  # symbol -> position

        print(f"\n开始模拟交易...")

        # 从第50根K线开始（需要足够数据计算均线）
        for i in range(50, min_len):
            # 获取当前时间点
            timestamp = dfs['BTCUSDT'].iloc[i]['time']

            # 每个币种逐一处理
            for symbol in SYMBOLS:
                df = dfs[symbol]
                current = df.iloc[i]
                price = current['c']

                # 获取置信度和推荐杠杆
                confidence, leverage, trend, volatility = self.calculate_confidence(df, i)

                # 平仓检查
                if symbol in positions:
                    pos = positions[symbol]
                    lev = pos['leverage']

                    if pos['side'] == 'LONG':
                        if price <= pos['stop'] or price >= pos['target']:
                            pnl = (price - pos['entry']) / pos['entry'] * POSITION_SIZE * lev
                            capital += pnl
                            pos['exit'] = price
                            pos['pnl'] = pnl
                            pos['exit_time'] = str(timestamp)
                            all_trades.append(pos)
                            del positions[symbol]
                    else:  # SHORT
                        if price >= pos['stop'] or price <= pos['target']:
                            pnl = (pos['entry'] - price) / pos['entry'] * POSITION_SIZE * lev
                            capital += pnl
                            pos['exit'] = price
                            pos['pnl'] = pnl
                            pos['exit_time'] = str(timestamp)
                            all_trades.append(pos)
                            del positions[symbol]

                # 开仓检查 - 如果没有持仓且有钱
                if symbol not in positions and capital >= POSITION_SIZE:
                    if trend in ['strong_bull', 'bull', 'strong_bear', 'bear']:
                        if 'bull' in trend:
                            side = 'LONG'
                            stop = price * 0.95
                            target = price * 1.10
                        else:
                            side = 'SHORT'
                            stop = price * 1.05
                            target = price * 0.90

                        positions[symbol] = {
                            'symbol': symbol,
                            'side': side,
                            'entry': price,
                            'stop': stop,
                            'target': target,
                            'leverage': leverage,
                            'confidence': confidence,
                            'entry_time': str(timestamp),
                            'exit': None,
                            'pnl': None,
                            'status': 'OPEN'
                        }

        # 平掉所有最后持仓
        for symbol, pos in positions.items():
            df = dfs[symbol]
            pos['exit'] = df.iloc[-1]['c']
            pos['exit_time'] = str(df.iloc[-1]['time'])
            lev = pos['leverage']
            open_fee = pos.get('open_fee', 0)
            close_fee = POSITION_SIZE * FEE_RATE  # 平仓手续费

            if pos['side'] == 'LONG':
                raw_pnl = (pos['exit'] - pos['entry']) / pos['entry'] * POSITION_SIZE * lev
            else:
                raw_pnl = (pos['entry'] - pos['exit']) / pos['entry'] * POSITION_SIZE * lev

            pnl = raw_pnl - open_fee - close_fee
            pos['pnl'] = pnl
            pos['raw_pnl'] = raw_pnl
            pos['fees'] = open_fee + close_fee
            capital += pnl
            all_trades.append(pos)

        # 按币种统计
        wins = [t for t in all_trades if t['pnl'] > 0]
        total_trades = len(all_trades)
        win_rate = len(wins) / total_trades * 100 if total_trades > 0 else 0
        avg_leverage = np.mean([t['leverage'] for t in all_trades]) if all_trades else 0

        # 按币种分组
        results = []
        for symbol in SYMBOLS:
            symbol_trades = [t for t in all_trades if t['symbol'] == symbol]
            symbol_wins = [t for t in symbol_trades if t['pnl'] > 0]
            symbol_profit = sum(t['pnl'] for t in symbol_trades)

            results.append({
                'symbol': symbol,
                'initial_capital': SHARED_CAPITAL,
                'final_capital': capital,
                'profit': capital - SHARED_CAPITAL,
                'profit_pct': (capital - SHARED_CAPITAL) / SHARED_CAPITAL * 100,
                'total_trades': len(symbol_trades),
                'wins': len(symbol_wins),
                'losses': len(symbol_trades) - len(symbol_wins),
                'win_rate': len(symbol_wins) / len(symbol_trades) * 100 if symbol_trades else 0,
                'avg_leverage': np.mean([t['leverage'] for t in symbol_trades]) if symbol_trades else 0,
                'trades': symbol_trades
            })

        # 保存结果
        output_file = Path(__file__).parent / "backtest_results.json"
        with open(output_file, 'w') as f:
            json.dump(results, f, indent=2)

        print(f"\nFinal Capital: ${capital:.2f}")
        print(f"Total Profit: ${capital - SHARED_CAPITAL:.2f}")

        return results


async def run_period(bt, start_date, end_date, period_name):
    """运行单个时间段的回测"""
    global START_DATE, END_DATE
    START_DATE = start_date
    END_DATE = end_date

    print(f"\n{'='*60}")
    print(f"测试区间: {period_name} ({start_date} ~ {end_date})")
    print("="*60)

    results = await bt.run_all_trades_together()

    if not results:
        print("无交易数据")
        return None

    final = results[0]['final_capital']
    total_trades = sum(r['total_trades'] for r in results)
    wins = sum(r['wins'] for r in results)
    total_fees = sum(sum(t.get('fees', 0) for t in r['trades']) for r in results)

    print(f"\n--- {period_name} 结果 ---")
    print(f"总交易: {total_trades} 笔")
    print(f"胜率: {wins/total_trades*100:.0f}%" if total_trades > 0 else "胜率: N/A")
    print(f"手续费总计: ${total_fees:.2f}")
    print(f"最终资金: ${final:.2f}")
    print(f"收益: ${final - SHARED_CAPITAL:.2f} ({(final - SHARED_CAPITAL) / SHARED_CAPITAL * 100:+.1f}%)")

    return {
        'period': period_name,
        'start': start_date,
        'end': end_date,
        'final_capital': final,
        'profit': final - SHARED_CAPITAL,
        'profit_pct': (final - SHARED_CAPITAL) / SHARED_CAPITAL * 100,
        'total_trades': total_trades,
        'win_rate': wins/total_trades*100 if total_trades > 0 else 0,
        'total_fees': total_fees
    }


async def main():
    # 只跑2026年1-2月，保存详细记录
    bt = Backtester()
    global START_DATE, END_DATE
    START_DATE = '2026-01-01'
    END_DATE = '2026-02-28'

    print("="*60)
    print("MTF 智能交易系统 - 保守版回测")
    print(f"最大杠杆: {MAX_LEVERAGE}x | 手续费: {FEE_RATE*100}%")
    print(f"测试区间: {START_DATE} ~ {END_DATE}")
    print("="*60)

    results = await bt.run_all_trades_together()

    # 保存详细结果
    output_file = Path(__file__).parent / "backtest_results.json"
    with open(output_file, 'w') as f:
        json.dump(results, f, indent=2)
    print(f"\n结果已保存到: {output_file}")

    # 打印汇总
    final = results[0]['final_capital'] if results else SHARED_CAPITAL
    total_trades = sum(r['total_trades'] for r in results)
    wins = sum(r['wins'] for r in results)
    total_fees = sum(sum(t.get('fees', 0) for t in r['trades']) for r in results)

    print("\n" + "="*60)
    print("回测结果汇总")
    print("="*60)
    print(f"初始本金: ${SHARED_CAPITAL}")
    print(f"最终资金: ${final:.2f}")
    print(f"总收益: ${final - SHARED_CAPITAL:.2f} ({(final - SHARED_CAPITAL) / SHARED_CAPITAL * 100:+.1f}%)")
    print(f"总交易: {total_trades} 笔")
    print(f"胜率: {wins/total_trades*100:.0f}%" if total_trades > 0 else "胜率: N/A")
    print(f"手续费: ${total_fees:.2f}")


if __name__ == '__main__':
    asyncio.run(main())
