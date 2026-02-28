#!/usr/bin/env python3
"""
ATR 趋势策略 - 自动纸面交易
每4小时自动检查一次，无需人工干预
"""
import asyncio
import pandas as pd
import numpy as np
import aiohttp
from aiohttp_socks import ProxyConnector
from datetime import datetime
import json
import os
import time

SYMBOLS = ['BTCUSDT', 'SOLUSDT']
POSITION_SIZE = 100
SHARED_CAPITAL = 200.0
FEE_RATE = 0.0005

# ATR参数
ATR_PERIOD = 14
VOLATILITY_LOOKBACK = 20
ENTRY_LOOKBACK = 20
EXIT_LOOKBACK = 10
ATR_MULTIPLE = 3
VOLATILITY_THRESHOLD = 1.2

# 状态文件
STATE_FILE = 'scripts/paper_trading_state.json'
LOG_FILE = 'scripts/paper_trading.log'
RECORD_FILE = 'scripts/paper_trading_record.md'  # 交割单

# 检查间隔（秒）
CHECK_INTERVAL = 30 * 60  # 30分钟


class ATRAutoTrader:
    def __init__(self):
        self.connector = ProxyConnector.from_url('http://127.0.0.1:7890')
        self.session = None
        self.capital = SHARED_CAPITAL
        self.positions = {}
        self.trades = []
        self.daily_losses = {}

        self.load_state()

    def log(self, message):
        """记录日志"""
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        log_line = f"[{timestamp}] {message}"
        print(log_line)
        with open(LOG_FILE, 'a', encoding='utf-8') as f:
            f.write(log_line + '\n')

    def load_state(self):
        if os.path.exists(STATE_FILE):
            try:
                with open(STATE_FILE, 'r') as f:
                    state = json.load(f)
                    self.capital = state.get('capital', SHARED_CAPITAL)
                    self.positions = state.get('positions', {})
                    self.trades = state.get('trades', [])
                    self.daily_losses = state.get('daily_losses', {})
                self.log(f"Loaded state: capital=${self.capital:.2f}")
            except:
                pass

    def save_state(self):
        state = {
            'capital': self.capital,
            'positions': self.positions,
            'trades': self.trades,
            'daily_losses': self.daily_losses,
            'last_update': datetime.now().isoformat()
        }
        with open(STATE_FILE, 'w') as f:
            json.dump(state, f, indent=2)

    async def _get_session(self):
        if self.session is None:
            self.session = aiohttp.ClientSession(connector=self.connector)
        return self.session

    async def fetch_klines(self, symbol: str, interval: str = '4h', limit: int = 200):
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

    def calculate_atr(self, df, period=14):
        high = df['h']
        low = df['l']
        close = df['c']

        tr1 = high - low
        tr2 = abs(high - close.shift(1))
        tr3 = abs(low - close.shift(1))
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

        atr = tr.rolling(window=period).mean()
        return atr

    def check_entry_signal(self, df):
        i = len(df) - 1

        if i < ENTRY_LOOKBACK + VOLATILITY_LOOKBACK:
            return None

        df = df.copy()
        df['atr'] = self.calculate_atr(df, ATR_PERIOD)
        df['atr_pct'] = df['atr'] / df['c'] * 100

        current = df.iloc[i]
        price = current['c']
        atr = current['atr']
        atr_pct = current['atr_pct']

        avg_atr = df['atr'].iloc[i-VOLATILITY_LOOKBACK:i].mean()
        if atr < avg_atr * VOLATILITY_THRESHOLD:
            return None

        high_20 = df['h'].iloc[i-ENTRY_LOOKBACK:i].max()
        low_20 = df['l'].iloc[i-ENTRY_LOOKBACK:i].min()

        if price > high_20:
            atr_stop = atr * ATR_MULTIPLE
            leverage = 10 if atr_pct < 3 else (5 if atr_pct < 5 else 3)
            return {
                'side': 'LONG',
                'entry': price,
                'stop': price - atr_stop,
                'target': price + atr_stop * 2,
                'leverage': leverage
            }
        elif price < low_20:
            atr_stop = atr * ATR_MULTIPLE
            leverage = 10 if atr_pct < 3 else (5 if atr_pct < 5 else 3)
            return {
                'side': 'SHORT',
                'entry': price,
                'stop': price + atr_stop,
                'target': price - atr_stop * 2,
                'leverage': leverage
            }

        return None

    def check_exit(self, df, pos):
        i = len(df) - 1

        high = df.iloc[i]['h']
        low = df.iloc[i]['l']

        if pos['side'] == 'LONG':
            if low <= pos['stop']:
                return {'exit': pos['stop'], 'reason': 'stop_loss'}
            if high >= pos['target']:
                return {'exit': pos['target'], 'reason': 'take_profit'}
            if i >= EXIT_LOOKBACK:
                low_10 = df['l'].iloc[i-EXIT_LOOKBACK:i].min()
                if low <= low_10:
                    return {'exit': low, 'reason': 'exit_breakout'}
        else:
            if high >= pos['stop']:
                return {'exit': pos['stop'], 'reason': 'stop_loss'}
            if low <= pos['target']:
                return {'exit': pos['target'], 'reason': 'take_profit'}
            if i >= EXIT_LOOKBACK:
                high_10 = df['h'].iloc[i-EXIT_LOOKBACK:i].max()
                if high >= high_10:
                    return {'exit': high, 'reason': 'exit_breakout'}

        return None

    def open_position(self, symbol, signal):
        lev = signal['leverage']
        entry = signal['entry']
        notional = POSITION_SIZE * lev
        fee = notional * FEE_RATE

        # 计算入场原因
        df = asyncio.get_event_loop().run_until_complete(self.fetch_klines(symbol, '4h', 200)) if hasattr(self, '_last_df') else None
        entry_reason = f"价格突破20日{'高' if signal['side'] == 'LONG' else '低'}点，ATR波动率过滤器通过"

        self.positions[symbol] = {
            'side': signal['side'],
            'entry': entry,
            'stop': signal['stop'],
            'target': signal['target'],
            'leverage': lev,
            'notional': notional,
            'open_time': datetime.now().isoformat(),
            'entry_reason': entry_reason
        }

        self.log(f"*** OPEN {signal['side']} {symbol} ***")
        self.log(f"    Entry: ${entry:.2f}, Stop: ${signal['stop']:.2f}, Target: ${signal['target']:.2f}")
        self.log(f"    Leverage: {lev}x")
        self.log(f"    Reason: {entry_reason}")

    def close_position(self, symbol, exit_price, reason):
        pos = self.positions[symbol]
        lev = pos['leverage']
        entry = pos['entry']
        notional = POSITION_SIZE * lev

        open_fee = notional * FEE_RATE
        close_fee = notional * FEE_RATE

        if pos['side'] == 'LONG':
            raw_pnl = (exit_price - entry) / entry * POSITION_SIZE * lev
        else:
            raw_pnl = (entry - exit_price) / entry * POSITION_SIZE * lev

        pnl = raw_pnl - open_fee - close_fee
        self.capital += pnl

        # 生成平仓原因
        exit_reason_map = {
            'stop_loss': '触及3倍ATR止损',
            'take_profit': '触及止盈目标（止损的2倍）',
            'exit_breakout': '10日反向突破离场'
        }
        exit_reason = exit_reason_map.get(reason, reason)

        trade = {
            'symbol': symbol,
            'side': pos['side'],
            'entry': entry,
            'exit': exit_price,
            'leverage': lev,
            'pnl': pnl,
            'fees': open_fee + close_fee,
            'open_time': pos['open_time'],
            'close_time': datetime.now().isoformat(),
            'reason': reason,
            'entry_reason': pos.get('entry_reason', 'N/A'),
            'exit_reason': exit_reason
        }
        self.trades.append(trade)

        if pnl < 0:
            today = datetime.now().strftime('%Y-%m-%d')
            self.daily_losses[today] = self.daily_losses.get(today, 0) + abs(pnl)

        self.log(f"*** CLOSE {pos['side']} {symbol} ***")
        self.log(f"    {entry:.2f} -> {exit_price:.2f}, PnL: ${pnl:+.2f} ({reason})")
        self.log(f"    Capital: ${self.capital:.2f}")

        del self.positions[symbol]

        # 更新交割单
        self.generate_record()

    def generate_record(self):
        """生成交割单 Markdown"""
        if not self.trades:
            return

        md = f"""# ATR 趋势策略 - 纸面交易交割单
## 开始时间: {self.trades[0]['open_time'][:10] if self.trades else 'N/A'}

### 策略参数
- **交易币种**: BTCUSDT, SOLUSDT
- **K线周期**: 4小时
- **ATR止损**: 3倍
- **杠杆管理**: ATR<3%:10x, 3-5%:5x, >5%:3x
- **手续费**: 0.05%

### 汇总
| 指标 | 数值 |
|------|------|
| 初始本金 | $200.00 |
| 当前资金 | ${self.capital:.2f} |
| 净收益 | ${self.capital - 200:.2f} ({(self.capital - 200) / 200 * 100:+.1f}%) |
| 总交易 | {len(self.trades)}笔 |
| 胜率 | {sum(1 for t in self.trades if t['pnl'] > 0)}/{len(self.trades)} ({sum(1 for t in self.trades if t['pnl'] > 0) / len(self.trades) * 100:.0f}%) |
| 手续费 | ${sum(t['fees'] for t in self.trades):.2f} |

---

## 交易详情

"""

        # 按币种分组
        for symbol in SYMBOLS:
            symbol_trades = [t for t in self.trades if t['symbol'] == symbol]
            if not symbol_trades:
                continue

            symbol_profit = sum(t['pnl'] for t in symbol_trades)
            symbol_wins = sum(1 for t in symbol_trades if t['pnl'] > 0)

            md += f"### {symbol} ({len(symbol_trades)}笔)\n\n"
            md += "| # | 开仓时间 | 方向 | 入场价 | 出场价 | 杠杆 | 盈亏 | 开仓原因 | 平仓原因 |\n"
            md += "|---|----------|------|--------|--------|------|------|----------|----------|\n"

            for idx, t in enumerate(symbol_trades, 1):
                side = "做多" if t['side'] == 'LONG' else "做空"
                md += f"| {idx} | {t['open_time'][:16]} | {side} | ${t['entry']:.2f} | ${t['exit']:.2f} | {t['leverage']}x | **${t['pnl']:+.2f}** | {t.get('entry_reason', 'N/A')} | {t.get('exit_reason', t['reason'])} |\n"

            md += f"\n**{symbol}小结**: ${symbol_profit:+.2f} ({symbol_wins}胜{len(symbol_trades)-symbol_wins}负)\n\n"
            md += "---\n\n"

        # 当前持仓
        if self.positions:
            md += "## 当前持仓\n\n"
            md += "| 币种 | 方向 | 入场价 | 止损 | 止盈 | 杠杆 | 开仓原因 |\n"
            md += "|------|------|--------|------|------|------|----------|\n"
            for symbol, pos in self.positions.items():
                side = "做多" if pos['side'] == 'LONG' else "做空"
                md += f"| {symbol} | {side} | ${pos['entry']:.2f} | ${pos['stop']:.2f} | ${pos['target']:.2f} | {pos['leverage']}x | {pos.get('entry_reason', 'N/A')} |\n"

        with open(RECORD_FILE, 'w', encoding='utf-8') as f:
            f.write(md)

        self.log(f"Trading record updated: {RECORD_FILE}")

    async def check_and_trade(self):
        """检查并执行交易"""
        self.log("=" * 60)
        self.log(f"Checking signals...")

        # 检查现有持仓
        for symbol in SYMBOLS:
            if symbol in self.positions:
                try:
                    df = await self.fetch_klines(symbol, '4h', 50)
                    pos = self.positions[symbol]
                    exit_info = self.check_exit(df, pos)

                    if exit_info:
                        self.close_position(symbol, exit_info['exit'], exit_info['reason'])
                except Exception as e:
                    self.log(f"Error checking {symbol} position: {e}")

        # 检查新信号
        for symbol in SYMBOLS:
            if symbol in self.positions:
                continue

            today = datetime.now().strftime('%Y-%m-%d')
            today_loss = self.daily_losses.get(today, 0)
            if today_loss >= 30:
                self.log(f"{symbol}: Daily loss limit reached")
                continue

            try:
                df = await self.fetch_klines(symbol, '4h', 200)
                signal = self.check_entry_signal(df)

                if signal:
                    self.open_position(symbol, signal)
            except Exception as e:
                self.log(f"Error checking {symbol} signal: {e}")

        self.save_state()

        if self.positions:
            self.log(f"Current positions: {list(self.positions.keys())}")
        else:
            self.log("No open positions")

        self.log(f"Capital: ${self.capital:.2f}")

    async def run_forever(self):
        """持续运行"""
        self.log("=" * 60)
        self.log("ATR Auto Paper Trading Started")
        self.log(f"Initial Capital: ${self.capital:.2f}")
        self.log(f"Check Interval: {CHECK_INTERVAL/60:.0f} minutes")
        self.log("=" * 60)

        while True:
            try:
                await self.check_and_trade()
            except Exception as e:
                self.log(f"Error in check cycle: {e}")

            self.log(f"Sleeping for {CHECK_INTERVAL/60:.0f} minutes...")
            await asyncio.sleep(CHECK_INTERVAL)

    async def cleanup(self):
        if self.session:
            await self.session.close()


async def main():
    trader = ATRAutoTrader()
    try:
        await trader.run_forever()
    except KeyboardInterrupt:
        trader.log("Stopped by user")
    finally:
        await trader.cleanup()


if __name__ == '__main__':
    asyncio.run(main())
