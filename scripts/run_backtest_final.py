#!/usr/bin/env python3
"""
4h K线版 - 但用高低点触发止损（更精确）
"""
import asyncio
import json
from pathlib import Path
import pandas as pd
import numpy as np
import aiohttp
from aiohttp_socks import ProxyConnector

SYMBOLS = ['BTCUSDT', 'SOLUSDT']
POSITION_SIZE = 100

START_DATE = '2026-01-01'
END_DATE = '2026-02-28'

SHARED_CAPITAL = 200.0
MAX_LEVERAGE = 10
FEE_RATE = 0.0005

COOLDOWN_PERIOD = 4
LOW_CONFIDENCE_THRESHOLD = 50
CONFIRMATION_WAIT = 2


class Backtester:
    def __init__(self):
        self.connector = ProxyConnector.from_url('http://127.0.0.1:7890')
        self.session = None
        self.last_stop_loss = {}

    async def _get_session(self):
        if self.session is None:
            self.session = aiohttp.ClientSession(connector=self.connector)
        return self.session

    async def fetch_klines(self, symbol: str, interval: str = '4h', limit: int = 1500) -> pd.DataFrame:
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
        current = df.iloc[i]
        ma20 = current['ma20']
        ma50 = current['ma50']
        ma20_5ago = df['ma20'].iloc[i-5] if i >= 5 else ma20
        ma50_5ago = df['ma50'].iloc[i-5] if i >= 5 else ma50

        if ma50 > 0:
            ma_distance_pct = abs(ma20 - ma50) / ma50 * 100
        else:
            ma_distance_pct = 0

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

        recent = df.iloc[max(0, i-20):i]
        if len(recent) > 1:
            volatility = recent['c'].pct_change().std()
        else:
            volatility = 0.02

        confidence = min(100, ma_distance_pct * 10 + trend_score * 20)

        vol_multiplier = 1.0
        if volatility > 0.05:
            vol_multiplier = 0.3
        elif volatility > 0.03:
            vol_multiplier = 0.5

        if confidence >= 80:
            leverage = 10
        elif confidence >= 60:
            leverage = 8
        elif confidence >= 40:
            leverage = 5
        elif confidence >= 20:
            leverage = 3
        else:
            leverage = 0

        leverage = int(leverage * vol_multiplier)
        leverage = max(0, min(MAX_LEVERAGE, leverage))

        return confidence, leverage, trend, volatility

    def check_cooldown(self, symbol: str, current_idx: int, side: str) -> bool:
        if symbol not in self.last_stop_loss:
            return False
        last_stop = self.last_stop_loss[symbol]
        if last_stop['side'] == side:
            periods_since_stop = current_idx - last_stop['idx']
            if periods_since_stop < COOLDOWN_PERIOD:
                return True
        return False

    def check_low_confidence_confirmation(self, df: pd.DataFrame, i: int, trend: str, confidence: float) -> bool:
        if confidence >= LOW_CONFIDENCE_THRESHOLD:
            return True
        if i < CONFIRMATION_WAIT:
            return False
        for j in range(i - CONFIRMATION_WAIT, i):
            _, _, past_trend, _ = self.calculate_confidence(df, j)
            if 'bull' in trend and 'bull' not in past_trend:
                return False
            if 'bear' in trend and 'bear' not in past_trend:
                return False
        return True

    def check_stop_by_high_low(self, df: pd.DataFrame, entry_idx: int, side: str,
                               entry_price: float, stop: float, target: float) -> dict:
        """
        检查是否触及止损止盈 - 用高低点而非收盘价
        """
        # 检查接下来几根K线
        check_limit = min(entry_idx + 10, len(df))

        for i in range(entry_idx + 1, check_limit):
            candle = df.iloc[i]

            if side == 'LONG':
                # 止损：最低点跌到止损价
                if candle['l'] <= stop:
                    return {'triggered': True, 'exit_price': stop, 'reason': 'stop'}
                # 止盈：最高点涨到止盈价
                if candle['h'] >= target:
                    return {'triggered': True, 'exit_price': target, 'reason': 'target'}
            else:  # SHORT
                # 止损：最高点涨到止损价
                if candle['h'] >= stop:
                    return {'triggered': True, 'exit_price': stop, 'reason': 'stop'}
                # 止盈：最低点跌到止盈价
                if candle['l'] <= target:
                    return {'triggered': True, 'exit_price': target, 'reason': 'target'}

        return {'triggered': False}

    async def run_backtest(self):
        print(f"Running 4h with high-low stop-loss...")

        dfs = {}
        for symbol in SYMBOLS:
            print(f"  Fetching {symbol}...")
            df = await self.fetch_klines(symbol, '4h', 1500)
            df['ma20'] = df['c'].rolling(20).mean()
            df['ma50'] = df['c'].rolling(50).mean()
            df = df[(df['time'] >= START_DATE) & (df['time'] <= END_DATE)]
            dfs[symbol] = df
            print(f"    {symbol}: {len(df)} candles")

        min_len = min(len(df) for df in dfs.values())

        capital = SHARED_CAPITAL
        all_trades = []
        positions = {}

        print(f"\nSimulating...")

        for i in range(50, min_len):
            timestamp = dfs['BTCUSDT'].iloc[i]['time']

            for symbol in SYMBOLS:
                df = dfs[symbol]
                current = df.iloc[i]
                price = current['c']

                confidence, leverage, trend, volatility = self.calculate_confidence(df, i)

                # 平仓检查 - 用高低点
                if symbol in positions:
                    pos = positions[symbol]
                    lev = pos['leverage']
                    notional_value = POSITION_SIZE * lev

                    result = self.check_stop_by_high_low(
                        df, pos['entry_idx'], pos['side'],
                        pos['entry'], pos['stop'], pos['target']
                    )

                    if result['triggered']:
                        exit_price = result['exit_price']
                        raw_pnl = (exit_price - pos['entry']) / pos['entry'] * POSITION_SIZE * lev if pos['side'] == 'LONG' \
                            else (pos['entry'] - exit_price) / pos['entry'] * POSITION_SIZE * lev

                        open_fee = pos['notional_value'] * FEE_RATE
                        close_fee = notional_value * FEE_RATE
                        pnl = raw_pnl - open_fee - close_fee

                        capital += pnl
                        pos['exit'] = exit_price
                        pos['pnl'] = pnl
                        pos['raw_pnl'] = raw_pnl
                        pos['fees'] = open_fee + close_fee
                        pos['exit_time'] = str(timestamp)
                        pos['exit_reason'] = result['reason']
                        all_trades.append(pos)

                        if pnl < 0:
                            self.last_stop_loss[symbol] = {'idx': i, 'side': pos['side']}

                        del positions[symbol]

                # 开仓检查
                if symbol not in positions and capital >= POSITION_SIZE and leverage > 0:
                    if trend in ['strong_bull', 'bull', 'strong_bear', 'bear']:
                        side = 'LONG' if 'bull' in trend else 'SHORT'

                        if self.check_cooldown(symbol, i, side):
                            continue

                        if not self.check_low_confidence_confirmation(df, i, trend, confidence):
                            continue

                        if leverage >= 10:
                            stop_pct = 0.02
                        elif leverage >= 5:
                            stop_pct = 0.03
                        else:
                            stop_pct = 0.05

                        target_pct = stop_pct * 2

                        if side == 'LONG':
                            stop = price * (1 - stop_pct)
                            target = price * (1 + target_pct)
                        else:
                            stop = price * (1 + stop_pct)
                            target = price * (1 - target_pct)

                        notional_value = POSITION_SIZE * leverage

                        positions[symbol] = {
                            'symbol': symbol,
                            'side': side,
                            'entry': price,
                            'stop': stop,
                            'target': target,
                            'leverage': leverage,
                            'confidence': confidence,
                            'stop_pct': stop_pct,
                            'notional_value': notional_value,
                            'entry_time': str(timestamp),
                            'entry_idx': i,
                            'exit': None,
                            'pnl': None,
                            'status': 'OPEN'
                        }

        # 平最后持仓
        for symbol, pos in positions.items():
            df = dfs[symbol]
            pos['exit'] = df.iloc[-1]['c']
            pos['exit_time'] = str(df.iloc[-1]['time'])
            lev = pos['leverage']
            notional_value = POSITION_SIZE * lev
            open_fee = pos['notional_value'] * FEE_RATE
            close_fee = notional_value * FEE_RATE

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

        results = []
        for symbol in SYMBOLS:
            symbol_trades = [t for t in all_trades if t['symbol'] == symbol]
            symbol_wins = [t for t in symbol_trades if t.get('pnl', 0) > 0]

            results.append({
                'symbol': symbol,
                'initial_capital': POSITION_SIZE,
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

        return results, capital


async def analyze_consecutive_losses(trades):
    sorted_trades = sorted(trades, key=lambda x: x['entry_time'])
    max_consecutive = 0
    current_consecutive = 0
    max_loss = 0

    for t in sorted_trades:
        pnl = t.get('pnl', 0)
        if pnl < 0:
            current_consecutive += 1
            max_consecutive = max(max_consecutive, current_consecutive)
        else:
            current_consecutive = 0

    return max_consecutive, abs(min([t.get('pnl', 0) for t in trades] or [0]))


async def analyze_worst_case(trades):
    worst_period = [t for t in trades if '2026-02-01' <= t.get('entry_time', '') <= '2026-02-07']
    losses = [t for t in worst_period if t.get('pnl', 0) < 0]
    return len(losses), sum(t.get('pnl', 0) for t in losses)


async def generate_report(results, capital):
    total_trades = sum(r['total_trades'] for r in results)
    total_wins = sum(r['wins'] for r in results)
    total_fees = sum(sum(t.get('fees', 0) for t in r['trades']) for r in results)
    profit = capital - SHARED_CAPITAL

    all_trades = []
    for r in results:
        all_trades.extend(r['trades'])

    btc_trades = [t for t in all_trades if t['symbol'] == 'BTCUSDT']
    sol_trades = [t for t in all_trades if t['symbol'] == 'SOLUSDT']

    btc_max, btc_loss = await analyze_consecutive_losses(btc_trades)
    sol_max, sol_loss = await analyze_consecutive_losses(sol_trades)
    worst_count, worst_loss = await analyze_worst_case(all_trades)

    md = f"""# MTF 智能交易系统 - 交割单
## 2026年1月1日 ~ 2026年2月28日

### 策略参数
- **交易币种**: BTCUSDT, SOLUSDT
- **K线周期**: 4小时（信号判断 + 止损执行）
- **止损触发**: 检查K线最高/最低点（更精确）
- **保证金**: 每个币种100U，共200U
- **最大杠杆**: 10x
- **止损**: 10倍2%，5倍3%
- **止盈**: 止损的2倍
- **手续费**: 0.05% (名义价值)
- **冷却期**: 4根4小时K线
- **低置信度确认**: <50%需2根K线确认

### 汇总
| 指标 | 数值 |
|------|------|
| 初始本金 | ${SHARED_CAPITAL:.2f} |
| 最终资金 | ${capital:.2f} |
| 净收益 | ${profit:+.2f} ({profit/SHARED_CAPITAL*100:+.1f}%) |
| 总交易 | {total_trades}笔 |
| 胜率 | {total_wins}/{total_trades} ({total_wins/total_trades*100:.0f}%) |
| 手续费 | ${total_fees:.2f} |

---

## 交易详情
"""

    for symbol_data in results:
        symbol = symbol_data['symbol']
        trades = symbol_data['trades']
        if not trades:
            continue

        md += f"\n### {symbol} ({len(trades)}笔)\n\n"
        md += "| # | 时间 | 方向 | 入场价 | 出场价 | 杠杆 | 置信度 | 盈亏 |\n"
        md += "|---|------|------|--------|--------|------|--------|------|\n"

        for idx, t in enumerate(sorted(trades, key=lambda x: x['entry_time']), 1):
            side_text = "做多" if t['side'] == 'LONG' else "做空"
            pnl = t.get('pnl', 0)
            pnl_text = f"**${pnl:+.2f}**" if pnl != 0 else "-"
            exit_price = f"{t.get('exit', 0):.2f}" if t.get('exit') else "持仓中"
            md += f"| {idx} | {t['entry_time'][:16]} | {side_text} | {t['entry']:.2f} | {exit_price} | {t['leverage']}x | {t.get('confidence', 0):.0f}% | {pnl_text} |\n"

        symbol_profit = sum(t['pnl'] for t in trades)
        symbol_wins = sum(1 for t in trades if t.get('pnl', 0) > 0)
        md += f"\n**{symbol}小结**: ${symbol_profit:+.2f} ({symbol_wins}胜{len(trades)-symbol_wins}负)\n\n---\n"

    sorted_by_pnl = sorted([t for t in all_trades if 'pnl' in t], key=lambda x: x['pnl'], reverse=True)

    md += "\n## 关键交易\n\n### 最赚钱5笔\n| # | 币种 | 时间 | 方向 | 盈亏 |\n|---|------|------|------|------|\n"
    for idx, t in enumerate(sorted_by_pnl[:5], 1):
        side = "做多" if t['side'] == 'LONG' else "做空"
        md += f"| {idx} | {t['symbol'].replace('USDT','')} | {t['entry_time'][:16]} | {side} | ${t['pnl']:+.2f} |\n"

    md += "\n### 亏损最大5笔\n| # | 币种 | 时间 | 方向 | 盈亏 |\n|---|------|------|------|------|\n"
    for idx, t in enumerate(sorted_by_pnl[-5:][::-1], 1):
        side = "做多" if t['side'] == 'LONG' else "做空"
        md += f"| {idx} | {t['symbol'].replace('USDT','')} | {t['entry_time'][:16]} | {side} | ${t['pnl']:+.2f} |\n"

    md += f"""

---

## 风险分析

### 最大连续亏损
| 币种 | 笔数 | 金额 |
|------|------|------|
| BTC | {btc_max}笔 | ${btc_loss:.2f} |
| SOL | {sol_max}笔 | ${sol_loss:.2f} |

### 2月初最坏情况
- 止损数: {worst_count}笔
- 累计: ${worst_loss:.2f}
"""

    output_file = Path(__file__).parent / "trading_record_final.md"
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(md)

    print(f"\nReport: {output_file}")


async def main():
    bt = Backtester()

    print("="*60)
    print("4h + High-Low Stop-Loss Backtest")
    print(f"Capital: {SHARED_CAPITAL}U")
    print("="*60)

    results, capital = await bt.run_backtest()

    total_trades = sum(r['total_trades'] for r in results)
    wins = sum(r['wins'] for r in results)
    total_fees = sum(sum(t.get('fees', 0) for t in r['trades']) for r in results)
    profit = capital - SHARED_CAPITAL

    print("\n" + "="*60)
    print(f"Final: ${capital:.2f}")
    print(f"Profit: ${profit:.2f} ({profit/200*100:+.1f}%)")
    print(f"Trades: {total_trades}, Win rate: {wins}/{total_trades} ({wins/total_trades*100:.0f}%)")
    print(f"Fees: ${total_fees:.2f}")
    print("="*60)

    await generate_report(results, capital)

    if bt.session:
        await bt.session.close()


if __name__ == '__main__':
    asyncio.run(main())
