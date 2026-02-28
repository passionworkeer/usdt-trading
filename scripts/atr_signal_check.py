#!/usr/bin/env python3
"""
ATR 趋势策略 - 实时信号检测
用于纸面交易信号生成
"""
import asyncio
import pandas as pd
import numpy as np
import aiohttp
from aiohttp_socks import ProxyConnector
from datetime import datetime, timedelta
import json

SYMBOLS = ['BTCUSDT', 'SOLUSDT']

# ATR参数
ATR_PERIOD = 14
VOLATILITY_LOOKBACK = 20
ENTRY_LOOKBACK = 20
EXIT_LOOKBACK = 10
ATR_MULTIPLE = 3
VOLATILITY_THRESHOLD = 1.2


class ATRSignalChecker:
    def __init__(self):
        self.connector = ProxyConnector.from_url('http://127.0.0.1:7890')
        self.session = None

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

    def check_signals(self, df: pd.DataFrame):
        """检查当前是否有交易信号"""
        signals = []
        i = len(df) - 1  # 最新一根K线

        if i < ENTRY_LOOKBACK + VOLATILITY_LOOKBACK:
            return signals

        # 计算ATR
        df['atr'] = self.calculate_atr(df, ATR_PERIOD)
        df['atr_pct'] = df['atr'] / df['c'] * 100

        current = df.iloc[i]
        price = current['c']
        atr = current['atr']
        atr_pct = current['atr_pct']

        # 1. 波动率过滤器
        avg_atr = df['atr'].iloc[i-VOLATILITY_LOOKBACK:i].mean()
        volatility_ok = atr > avg_atr * VOLATILITY_THRESHOLD

        # 2. 趋势突破确认
        high_20 = df['h'].iloc[i-ENTRY_LOOKBACK:i].max()
        low_20 = df['l'].iloc[i-ENTRY_LOOKBACK:i].min()

        # 检查是否有持仓（需要读取外部状态）
        # 这里只生成开仓信号

        # 检查做多信号
        if price > high_20 and volatility_ok:
            atr_stop = atr * ATR_MULTIPLE
            stop_price = price - atr_stop
            target = price + atr_stop * 2

            # 杠杆计算
            if atr_pct > 5:
                leverage = 3
            elif atr_pct > 3:
                leverage = 5
            else:
                leverage = 10
            leverage = min(10, leverage)

            signals.append({
                'type': 'LONG',
                'price': price,
                'stop': stop_price,
                'target': target,
                'leverage': leverage,
                'atr_pct': atr_pct,
                'reason': f'Price broke 20-day high {high_20:.2f}, ATR {atr_pct:.1f}% > threshold'
            })

        # 检查做空信号
        elif price < low_20 and volatility_ok:
            atr_stop = atr * ATR_MULTIPLE
            stop_price = price + atr_stop
            target = price - atr_stop * 2

            if atr_pct > 5:
                leverage = 3
            elif atr_pct > 3:
                leverage = 5
            else:
                leverage = 10
            leverage = min(10, leverage)

            signals.append({
                'type': 'SHORT',
                'price': price,
                'stop': stop_price,
                'target': target,
                'leverage': leverage,
                'atr_pct': atr_pct,
                'reason': f'Price broke 20-day low {low_20:.2f}, ATR {atr_pct:.1f}% > threshold'
            })

        return signals

    async def check_all(self):
        results = {}
        for symbol in SYMBOLS:
            df = await self.fetch_klines(symbol, '4h', 200)
            signals = self.check_signals(df)
            results[symbol] = {
                'price': df.iloc[-1]['c'],
                'time': str(df.iloc[-1]['time']),
                'signals': signals
            }
        return results


async def main():
    checker = ATRSignalChecker()
    results = await checker.check_all()

    print("=" * 60)
    print(f"ATR Signal Check - {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 60)

    for symbol, data in results.items():
        print(f"\n{symbol}:")
        print(f"  Current Price: ${data['price']:.2f}")
        print(f"  Last Update: {data['time']}")

        if data['signals']:
            for sig in data['signals']:
                print(f"  *** SIGNAL: {sig['type']} ***")
                print(f"      Entry: ${sig['price']:.2f}")
                print(f"      Stop: ${sig['stop']:.2f}")
                print(f"      Target: ${sig['target']:.2f}")
                print(f"      Leverage: {sig['leverage']}x")
                print(f"      Reason: {sig['reason']}")
        else:
            print(f"  No signal (waiting for breakout)")

    if checker.session:
        await checker.session.close()


if __name__ == '__main__':
    asyncio.run(main())
