#!/usr/bin/env python3
"""
MTF v6.0 极简趋势策略 - 只做突破
- 20日高点突破做多
- 20日低点突破做空
- 2%止损，4%止盈
- 每次20U仓位
"""
import asyncio
import aiohttp
from aiohttp_socks import ProxyConnector
import pandas as pd
import numpy as np
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass
import logging

logging.basicConfig(level=logging.WARNING)


@dataclass
class Trade:
    entry_time: any
    exit_time: any
    symbol: str
    direction: int
    entry_price: float
    exit_price: Optional[float]
    stop_loss: float
    take_profit: float
    position_size: float
    pnl: Optional[float] = None
    status: str = "open"


class SimpleTrendBacktester:
    def __init__(self, initial_capital: float = 200.0):
        self.initial_capital = initial_capital
        self.capital = initial_capital
        self.trades: List[Trade] = []
        self.session = None
        self.position_size = 20.0  # 固定20U

    async def _get_session(self):
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession(
                connector=ProxyConnector.from_url('http://127.0.0.1:7890')
            )
        return self.session

    async def close(self):
        if self.session and not self.session.closed:
            await self.session.close()

    async def fetch_klines(self, symbol: str, interval: str, limit: int = 500) -> pd.DataFrame:
        url = "https://fapi.binance.com/fapi/v1/klines"
        session = await self._get_session()
        async with session.get(url, params={'symbol': symbol, 'interval': interval, 'limit': limit},
                              timeout=aiohttp.ClientTimeout(total=30)) as resp:
            data = await resp.json()

        df = pd.DataFrame(data, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume', 'ct', 'qv', 't', 'tbb', 'tbq', 'i'])
        df['close'] = df['close'].astype(float)
        df['high'] = df['high'].astype(float)
        df['low'] = df['low'].astype(float)
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        return df

    async def backtest_symbol(self, symbol: str) -> Dict:
        print(f"\n{'='*50}\nBacktesting {symbol}\n{'='*50}")

        df = await self.fetch_klines(symbol, '1h', limit=500)
        print(f"Data: {len(df)} candles")

        self.capital = self.initial_capital
        self.trades = []
        trade = None

        # 20日高低点
        for i in range(21, len(df)):
            current = df.iloc[i]
            current_price = current['close']

            # 过去20日高低点
            prev20 = df.iloc[i-20:i]
            high20 = prev20['high'].max()
            low20 = prev20['low'].min()

            # 检查平仓
            if trade and trade.status == "open":
                if trade.direction == 1:  # 多头
                    if current['low'] <= trade.stop_loss:
                        self._close_trade(trade, trade.stop_loss, current['timestamp'], "SL")
                        trade = None
                    elif current['high'] >= trade.take_profit:
                        self._close_trade(trade, trade.take_profit, current['timestamp'], "TP")
                        trade = None
                else:  # 空头
                    if current['high'] >= trade.stop_loss:
                        self._close_trade(trade, trade.stop_loss, current['timestamp'], "SL")
                        trade = None
                    elif current['low'] <= trade.take_profit:
                        self._close_trade(trade, trade.take_profit, current['timestamp'], "TP")
                        trade = None

            # 检查开仓 - 突破20日高点做多，跌破20日低点做空
            if not trade:
                if current_price > high20:  # 突破高点做多
                    trade = Trade(
                        entry_time=current['timestamp'],
                        exit_time=None,
                        symbol=symbol,
                        direction=1,
                        entry_price=current_price,
                        exit_price=None,
                        stop_loss=current_price * 0.98,  # 2%止损
                        take_profit=current_price * 1.04,  # 4%止盈
                        position_size=self.position_size,
                        status="open"
                    )
                    self.trades.append(trade)
                elif current_price < low20:  # 突破低点做空
                    trade = Trade(
                        entry_time=current['timestamp'],
                        exit_time=None,
                        symbol=symbol,
                        direction=-1,
                        entry_price=current_price,
                        exit_price=None,
                        stop_loss=current_price * 1.02,  # 2%止损
                        take_profit=current_price * 0.96,  # 4%止盈
                        position_size=self.position_size,
                        status="open"
                    )
                    self.trades.append(trade)

        # 平最后持仓
        if trade and trade.status == "open":
            self._close_trade(trade, df.iloc[-1]['close'], df.iloc[-1]['timestamp'], "EOD")

        wins = [t for t in self.trades if t.pnl and t.pnl > 0]
        losses = [t for t in self.trades if t.pnl and t.pnl <= 0]

        return {
            'symbol': symbol,
            'trades': len(self.trades),
            'wins': len(wins),
            'losses': len(losses),
            'win_rate': len(wins) / len(self.trades) * 100 if self.trades else 0,
            'final_capital': self.capital,
            'return_pct': (self.capital - self.initial_capital) / self.initial_capital * 100,
            'trades_list': self.trades
        }

    def _close_trade(self, trade: Trade, exit_price: float, exit_time, reason: str):
        trade.exit_price = exit_price
        trade.exit_time = exit_time
        trade.status = reason

        if trade.direction == 1:
            pnl_pct = (exit_price - trade.entry_price) / trade.entry_price
        else:
            pnl_pct = (trade.entry_price - exit_price) / trade.entry_price

        # 扣除手续费
        pnl_pct -= 0.001

        trade.pnl = trade.position_size * pnl_pct
        self.capital += trade.pnl

    def print_results(self, stats: Dict):
        print(f"\nResults: {stats['symbol']}")
        print(f"Initial: ${self.initial_capital:.2f}")
        print(f"Final: ${stats['final_capital']:.2f} ({stats['return_pct']:.2f}%)")
        print(f"Trades: {stats['trades']} | Wins: {stats['wins']} | Losses: {stats['losses']}")
        print(f"Win Rate: {stats['win_rate']:.1f}%")

        for i, t in enumerate(stats['trades_list'], 1):
            direction = "LONG" if t.direction == 1 else "SHORT"
            pnl_str = f"${t.pnl:.2f}" if t.pnl else "N/A"
            print(f"  {i}. {t.entry_time.strftime('%m/%d')} | {direction} | "
                  f"Entry: ${t.entry_price:.0f} -> Exit: ${t.exit_price:.0f} | PnL: {pnl_str} ({t.status})")


async def main():
    backtester = SimpleTrendBacktester(initial_capital=200.0)

    symbols = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT']
    results = []

    try:
        for symbol in symbols:
            stats = await backtester.backtest_symbol(symbol)
            results.append(stats)
            backtester.print_results(stats)
    finally:
        await backtester.close()

    print(f"\n{'='*50}")
    print("PORTFOLIO SUMMARY")
    print(f"{'='*50}")
    total = sum(s['final_capital'] for s in results)
    print(f"Total: ${total:.2f} ({(total-600)/600*100:.2f}%)")
    for s in results:
        print(f"  {s['symbol']}: ${s['final_capital']:.2f}")


if __name__ == '__main__':
    asyncio.run(main())
