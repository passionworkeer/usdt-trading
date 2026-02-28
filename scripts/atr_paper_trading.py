#!/usr/bin/env python3
"""
ATR 趋势策略 - 纸面交易跟踪
模拟 200U 资金的交易过程
"""
import asyncio
import pandas as pd
import numpy as np
import aiohttp
from aiohttp_socks import ProxyConnector
from datetime import datetime
import json
import os

SYMBOLS = ['BTCUSDT', 'SOLUSDT']
POSITION_SIZE = 100  # 每个币种 100U
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


class ATRPaperTrader:
    def __init__(self):
        self.connector = ProxyConnector.from_url('http://127.0.0.1:7890')
        self.session = None
        self.capital = SHARED_CAPITAL
        self.positions = {}  # {symbol: position_dict}
        self.trades = []
        self.daily_losses = {}

        self.load_state()

    def load_state(self):
        """加载之前的状态"""
        if os.path.exists(STATE_FILE):
            try:
                with open(STATE_FILE, 'r') as f:
                    state = json.load(f)
                    self.capital = state.get('capital', SHARED_CAPITAL)
                    self.positions = state.get('positions', {})
                    self.trades = state.get('trades', [])
                    self.daily_losses = state.get('daily_losses', {})
                print(f"Loaded state: capital=${self.capital:.2f}, positions={len(self.positions)}, trades={len(self.trades)}")
            except:
                pass

    def save_state(self):
        """保存状态"""
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

    async def fetch_klines(self, symbol: str, interval: str = '4h', limit: int = 200) -> pd.DataFrame:
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

    def calculate_atr(self, df: pd.DataFrame, period: int = 14) -> pd.Series:
        high = df['h']
        low = df['l']
        close = df['c']

        tr1 = high - low
        tr2 = abs(high - close.shift(1))
        tr3 = abs(low - close.shift(1))
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

        atr = tr.rolling(window=period).mean()
        return atr

    def check_entry_signal(self, df: pd.DataFrame):
        """检查是否有入场信号"""
        i = len(df) - 1

        if i < ENTRY_LOOKBACK + VOLATILITY_LOOKBACK:
            return None

        # 计算ATR
        df = df.copy()
        df['atr'] = self.calculate_atr(df, ATR_PERIOD)
        df['atr_pct'] = df['atr'] / df['c'] * 100

        current = df.iloc[i]
        price = current['c']
        atr = current['atr']
        atr_pct = current['atr_pct']

        # 波动率过滤器
        avg_atr = df['atr'].iloc[i-VOLATILITY_LOOKBACK:i].mean()
        if atr < avg_atr * VOLATILITY_THRESHOLD:
            return None

        # 趋势突破
        high_20 = df['h'].iloc[i-ENTRY_LOOKBACK:i].max()
        low_20 = df['l'].iloc[i-ENTRY_LOOKBACK:i].min()

        if price > high_20:
            # 做多信号
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
            # 做空信号
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

    def check_exit(self, df: pd.DataFrame, pos: dict):
        """检查是否需要平仓"""
        i = len(df) - 1

        # 使用K线的高低点判断是否触及止损/止盈
        high = df.iloc[i]['h']
        low = df.iloc[i]['l']

        if pos['side'] == 'LONG':
            # 检查止损
            if low <= pos['stop']:
                return {'exit': pos['stop'], 'reason': 'stop_loss'}
            # 检查止盈（目标位）
            if high >= pos['target']:
                return {'exit': pos['target'], 'reason': 'take_profit'}
            # 检查10日反向突破
            if i >= EXIT_LOOKBACK:
                low_10 = df['l'].iloc[i-EXIT_LOOKBACK:i].min()
                if low <= low_10:
                    return {'exit': low, 'reason': 'exit_breakout'}
        else:
            # 做空
            if high >= pos['stop']:
                return {'exit': pos['stop'], 'reason': 'stop_loss'}
            if low <= pos['target']:
                return {'exit': pos['target'], 'reason': 'take_profit'}
            if i >= EXIT_LOOKBACK:
                high_10 = df['h'].iloc[i-EXIT_LOOKBACK:i].max()
                if high >= high_10:
                    return {'exit': high, 'reason': 'exit_breakout'}

        return None

    async def run(self):
        """运行纸面交易检查"""
        print("=" * 60)
        print(f"ATR Paper Trading Check - {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        print(f"Capital: ${self.capital:.2f}")
        print("=" * 60)

        # 检查现有持仓
        for symbol in SYMBOLS:
            if symbol in self.positions:
                df = await self.fetch_klines(symbol, '4h', 50)
                pos = self.positions[symbol]
                exit_info = self.check_exit(df, pos)

                if exit_info:
                    # 平仓
                    self.close_position(symbol, exit_info['exit'], exit_info['reason'], df)

        # 检查新信号
        for symbol in SYMBOLS:
            if symbol in self.positions:
                continue  # 已有持仓

            # 检查当日亏损
            today = datetime.now().strftime('%Y-%m-%d')
            today_loss = self.daily_losses.get(today, 0)
            if today_loss >= 30:
                print(f"\n{symbol}: Daily loss limit reached, skipping")
                continue

            df = await self.fetch_klines(symbol, '4h', 200)
            signal = self.check_entry_signal(df)

            if signal:
                # 开仓
                self.open_position(symbol, signal, df)

        # 保存状态
        self.save_state()

        # 打印当前状态
        print(f"\nCurrent Positions:")
        if self.positions:
            for symbol, pos in self.positions.items():
                print(f"  {symbol}: {pos['side']} @ ${pos['entry']:.2f}, "
                      f"stop=${pos['stop']:.2f}, target=${pos['target']:.2f}")
        else:
            print("  None")

        print(f"\nCapital: ${self.capital:.2f}")

        if self.session:
            await self.session.close()

    def open_position(self, symbol: str, signal: dict, df: pd.DataFrame):
        """开仓"""
        lev = signal['leverage']
        entry = signal['entry']

        # 计算手续费
        notional = POSITION_SIZE * lev
        fee = notional * FEE_RATE

        self.positions[symbol] = {
            'side': signal['side'],
            'entry': entry,
            'stop': signal['stop'],
            'target': signal['target'],
            'leverage': lev,
            'notional': notional,
            'open_time': datetime.now().isoformat(),
            'open_price': entry
        }

        print(f"\n*** OPEN {signal['side']} {symbol} ***")
        print(f"    Entry: ${entry:.2f}")
        print(f"    Stop: ${signal['stop']:.2f}")
        print(f"    Target: ${signal['target']:.2f}")
        print(f"    Leverage: {lev}x")
        print(f"    Fee: ${fee:.2f}")

    def close_position(self, symbol: str, exit_price: float, reason: str, df: pd.DataFrame):
        """平仓"""
        pos = self.positions[symbol]
        lev = pos['leverage']
        entry = pos['entry']
        notional = POSITION_SIZE * lev

        # 开仓手续费
        open_fee = notional * FEE_RATE
        # 平仓手续费
        close_fee = notional * FEE_RATE

        # 计算盈亏
        if pos['side'] == 'LONG':
            raw_pnl = (exit_price - entry) / entry * POSITION_SIZE * lev
        else:
            raw_pnl = (entry - exit_price) / entry * POSITION_SIZE * lev

        pnl = raw_pnl - open_fee - close_fee
        self.capital += pnl

        # 记录交易
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
            'reason': reason
        }
        self.trades.append(trade)

        # 更新当日亏损
        if pnl < 0:
            today = datetime.now().strftime('%Y-%m-%d')
            self.daily_losses[today] = self.daily_losses.get(today, 0) + abs(pnl)

        print(f"\n*** CLOSE {pos['side']} {symbol} ***")
        print(f"    Entry: ${entry:.2f} -> Exit: ${exit_price:.2f}")
        print(f"    PnL: ${pnl:.2f} ({reason})")
        print(f"    Capital now: ${self.capital:.2f}")

        del self.positions[symbol]


async def main():
    trader = ATRPaperTrader()
    await trader.run()

    # 生成交易记录
    if trader.trades:
        print("\n" + "=" * 60)
        print("Trade History")
        print("=" * 60)
        for t in trader.trades:
            print(f"{t['symbol']} {t['side']}: ${t['entry']:.2f} -> ${t['exit']:.2f}, PnL: ${t['pnl']:+.2f}")


if __name__ == '__main__':
    asyncio.run(main())
