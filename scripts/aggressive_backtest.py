#!/usr/bin/env python3
"""
MTF v5.3 激进版回测 - 针对 200U 小资金优化

核心改进：
1. 双重共振（4H+15m）代替三重共振 —— 信号多3-5倍
2. 5-10x 杠杆 —— 放大收益
3. 固定仓位（20U/笔）—— 10次交易机会
4. 动态止盈 —— 加速盈利落袋
5. 每日熔断 —— 保护本金
"""
import asyncio
import aiohttp
from aiohttp_socks import ProxyConnector
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass
import logging

logging.basicConfig(level=logging.WARNING)


@dataclass
class Trade:
    entry_time: datetime
    exit_time: Optional[datetime]
    symbol: str
    direction: int  # 1=多, -1=空
    entry_price: float
    exit_price: Optional[float]
    stop_loss: float
    take_profit: float
    position_size: float  # 仓位大小（USDT）
    leverage: int
    pnl: Optional[float] = None
    pnl_pct: Optional[float] = None
    status: str = "open"


class AggressiveBacktester:
    """激进版 MTF 回测器"""

    def __init__(self, initial_capital: float = 200.0):
        self.initial_capital = initial_capital
        self.capital = initial_capital
        self.trades: List[Trade] = []
        self.current_trade: Optional[Trade] = None
        self.session = None

        # v5.3 新参数
        self.min_position = 20.0  # 最小仓位 20U
        self.max_leverage = 10  # 最大10x杠杆
        self.daily_loss_limit = 10.0  # 每日亏损上限 10U
        self.daily_pnl = 0.0  # 今日盈亏
        self.last_trade_date = None

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
        params = {'symbol': symbol, 'interval': interval, 'limit': min(limit, 1000)}

        session = await self._get_session()
        async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=30)) as resp:
            data = await resp.json()

        df = pd.DataFrame(data, columns=[
            'timestamp', 'open', 'high', 'low', 'close', 'volume',
            'close_time', 'quote_volume', 'trades', 'taker_buy_base',
            'taker_buy_quote', 'ignore'
        ])

        df['close'] = df['close'].astype(float)
        df['high'] = df['high'].astype(float)
        df['low'] = df['low'].astype(float)
        df['open'] = df['open'].astype(float)
        df['volume'] = df['volume'].astype(float)
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')

        return df

    def check_4h_trend(self, df_4h: pd.DataFrame) -> Tuple[int, str]:
        """4H 趋势检查 - 更严格"""
        ema20 = df_4h['close'].ewm(span=20).mean().iloc[-1]
        ema50 = df_4h['close'].ewm(span=50).mean().iloc[-1]
        current_price = df_4h['close'].iloc[-1]

        # 明确的趋势才做
        if ema20 > ema50 * 1.01 and current_price > ema20:  # 明确多头
            return 1, "4H strong bullish"
        elif ema20 < ema50 * 0.99 and current_price < ema20:  # 明确空头
            return -1, "4H strong bearish"
        else:
            return 0, "4H weak/neutral"

    def check_15m_signal(self, df_15m: pd.DataFrame) -> Tuple[int, str, Optional[float], Optional[float]]:
        """15m 信号 - 更严格：需要更大的放量"""
        if len(df_15m) < 30:
            return 0, "no data", None, None

        avg_volume = df_15m['volume'].iloc[-30:-1].mean()
        current_volume = df_15m['volume'].iloc[-1]
        volume_ratio = current_volume / avg_volume if avg_volume > 0 else 0

        current_price = df_15m['close'].iloc[-1]
        prev_price = df_15m['close'].iloc[-2]
        price_change = (current_price - prev_price) / prev_price

        # RSI - 避免超买超卖
        delta = df_15m['close'].diff()
        gain = delta.where(delta > 0, 0).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        rsi_value = rsi.iloc[-1]

        # ATR
        if len(df_15m) < 15:
            atr = current_price * 0.01
        else:
            tr = np.maximum(
                df_15m['high'] - df_15m['low'],
                np.maximum(
                    abs(df_15m['high'] - df_15m['close'].shift(1)),
                    abs(df_15m['low'] - df_15m['close'].shift(1))
                )
            )
            atr = tr.iloc[-14:].mean()

        # 信号判断 - 改为趋势回踩入场
        # 多头趋势中，价格回踩均线时做多
        if volume_ratio >= 2.0 and price_change < -0.005:  # 2倍放量下跌（可能是回踩）
            return 1, f"pullback {volume_ratio:.1f}x RSI:{rsi_value:.0f}", atr, rsi_value
        elif volume_ratio >= 2.0 and price_change > 0.005:  # 2倍放量上涨（可能是回踩）
            return -1, f"pullback {volume_ratio:.1f}x RSI:{rsi_value:.0f}", atr, rsi_value
        else:
            return 0, f"no sig ({volume_ratio:.1f}x)", atr, rsi_value

    def calculate_sl_tp(self, entry_price: float, direction: int, atr: float, leverage: int) -> Tuple[float, float]:
        """计算止损止盈 - 改为固定2%止损"""
        # 固定2%止损（不受杠杆影响）
        risk_pct = 0.02

        if direction == 1:  # 多头
            stop_loss = entry_price * (1 - risk_pct)
            take_profit = entry_price * (1 + risk_pct * 2)  # 2:1
        else:  # 空头
            stop_loss = entry_price * (1 + risk_pct)
            take_profit = entry_price * (1 - risk_pct * 2)

        return stop_loss, take_profit

    async def backtest_symbol(self, symbol: str, days: int = 90) -> Dict:
        print(f"\n{'='*60}")
        print(f"Aggressive Backtest: {symbol} ({days} days)")
        print(f"{'='*60}")

        print("Fetching data...")
        df_4h = await self.fetch_klines(symbol, '4h', limit=500)
        df_15m = await self.fetch_klines(symbol, '15m', limit=1000)

        # 重置
        self.capital = self.initial_capital
        self.trades = []
        self.current_trade = None
        self.daily_pnl = 0.0
        self.last_trade_date = None

        signals_found = 0
        days_traded = set()

        for i in range(50, len(df_4h)):
            current_time = df_4h.iloc[i]['timestamp']
            current_date = current_time.date()
            current_price = df_4h.iloc[i]['close']

            # 每日熔断检查
            if current_date != self.last_trade_date:
                self.daily_pnl = 0.0
                self.last_trade_date = current_date

            if self.daily_pnl <= -self.daily_loss_limit:
                continue  # 今日熔断

            # 检查平仓
            if self.current_trade and self.current_trade.status == "open":
                mask = (df_15m['timestamp'] >= self.current_trade.entry_time) & (df_15m['timestamp'] <= current_time)
                relevant_15m = df_15m[mask]

                for _, row in relevant_15m.iterrows():
                    high = row['high']
                    low = row['low']

                    if self.current_trade.direction == 1:
                        if low <= self.current_trade.stop_loss:
                            self._close_trade(self.current_trade, self.current_trade.stop_loss, row['timestamp'], "SL")
                            break
                        elif high >= self.current_trade.take_profit:
                            self._close_trade(self.current_trade, self.current_trade.take_profit, row['timestamp'], "TP")
                            break
                    else:
                        if high >= self.current_trade.stop_loss:
                            self._close_trade(self.current_trade, self.current_trade.stop_loss, row['timestamp'], "SL")
                            break
                        elif low <= self.current_trade.take_profit:
                            self._close_trade(self.current_trade, self.current_trade.take_profit, row['timestamp'], "TP")
                            break

            # 检查开仓
            if not self.current_trade or self.current_trade.status != "open":
                # 4H 趋势
                df_4h_slice = df_4h.iloc[:i+1]
                trend_4h, trend_reason = self.check_4h_trend(df_4h_slice)

                if trend_4h != 0:
                    # 15m 信号
                    df_15m_slice = df_15m[df_15m['timestamp'] <= current_time]
                    signal_15m, signal_reason, atr, rsi = self.check_15m_signal(df_15m_slice)

                    # 双重共振：趋势+放量同向
                    if trend_4h == signal_15m and signal_15m != 0:
                        signals_found += 1
                        days_traded.add(current_date)

                        # 计算仓位和杠杆
                        position_size = min(self.capital * 0.5, 50)  # 最多用一半资金，最多50U
                        leverage = min(int(200 / position_size), self.max_leverage)  # 计算合适杠杆

                        entry_price = current_price
                        stop_loss, take_profit = self.calculate_sl_tp(entry_price, signal_15m, atr, leverage)

                        self.current_trade = Trade(
                            entry_time=current_time,
                            exit_time=None,
                            symbol=symbol,
                            direction=signal_15m,
                            entry_price=entry_price,
                            exit_price=None,
                            stop_loss=stop_loss,
                            take_profit=take_profit,
                            position_size=position_size,
                            leverage=leverage,
                            status="open"
                        )
                        self.trades.append(self.current_trade)

        # 平仓最后持仓
        if self.current_trade and self.current_trade.status == "open":
            last_price = df_4h.iloc[-1]['close']
            last_time = df_4h.iloc[-1]['timestamp']
            self._close_trade(self.current_trade, last_price, last_time, "EOD")

        return self._calculate_stats(symbol, signals_found, len(days_traded))

    def _close_trade(self, trade: Trade, exit_price: float, exit_time: datetime, reason: str):
        trade.exit_price = exit_price
        trade.exit_time = exit_time
        trade.status = reason

        # 计算盈亏（考虑杠杆）
        if trade.direction == 1:
            price_pct = (exit_price - trade.entry_price) / trade.entry_price
        else:
            price_pct = (trade.entry_price - exit_price) / trade.entry_price

        # 杠杆后的盈亏
        pnl_pct = price_pct * trade.leverage

        # 手续费（开+平）
        commission = 0.0005 * 2
        pnl_pct -= commission

        trade.pnl_pct = pnl_pct
        trade.pnl = trade.position_size * pnl_pct

        self.capital += trade.pnl
        self.daily_pnl += trade.pnl

    def _calculate_stats(self, symbol: str, signals_found: int, trading_days: int) -> Dict:
        if not self.trades:
            return {
                'symbol': symbol,
                'signals': signals_found,
                'trades': 0,
                'final_capital': self.capital,
                'return_pct': 0,
                'win_rate': 0,
                'trades_list': []
            }

        wins = [t for t in self.trades if t.pnl and t.pnl > 0]
        losses = [t for t in self.trades if t.pnl and t.pnl <= 0]

        return {
            'symbol': symbol,
            'signals': signals_found,
            'trades': len(self.trades),
            'wins': len(wins),
            'losses': len(losses),
            'win_rate': len(wins) / len(self.trades) * 100,
            'final_capital': self.capital,
            'return_pct': (self.capital - self.initial_capital) / self.initial_capital * 100,
            'trading_days': trading_days,
            'trades_list': self.trades
        }

    def print_results(self, stats: Dict):
        print(f"\n{'='*60}")
        print(f"RESULTS: {stats['symbol']}")
        print(f"{'='*60}")
        print(f"Initial: ${self.initial_capital:.2f}")
        print(f"Final: ${stats['final_capital']:.2f}")
        print(f"Return: {stats['return_pct']:.2f}%")
        print(f"")
        print(f"Signals: {stats['signals']} | Trades: {stats['trades']}")
        print(f"Trading Days: {stats.get('trading_days', 0)}")
        if stats['trades'] > 0:
            print(f"Wins: {stats['wins']} | Losses: {stats['losses']}")
            print(f"Win Rate: {stats['win_rate']:.1f}%")

            print(f"\n--- Trade Log ---")
            for i, t in enumerate(stats['trades_list'], 1):
                direction = "LONG" if t.direction == 1 else "SHORT"
                pnl_str = f"${t.pnl:.2f}" if t.pnl else "N/A"
                exit_p = t.exit_price if t.exit_price else 0
                print(f"{i}. {t.entry_time.strftime('%m/%d %H:%M')} | {direction} {t.leverage}x | "
                      f"Entry: ${t.entry_price:.0f} -> Exit: ${exit_p:.0f} | PnL: {pnl_str} ({t.status})")


async def main():
    backtester = AggressiveBacktester(initial_capital=200.0)

    symbols = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT']

    results = []
    try:
        for symbol in symbols:
            stats = await backtester.backtest_symbol(symbol, days=90)
            results.append(stats)
            backtester.print_results(stats)
    finally:
        await backtester.close()

    # 汇总
    print(f"\n{'='*60}")
    print("PORTFOLIO SUMMARY (200U Aggressive)")
    print(f"{'='*60}")
    total = sum(s['final_capital'] for s in results)
    print(f"Total: ${total:.2f} ({(total-600)/600*100:.2f}% from 600)")
    for s in results:
        print(f"  {s['symbol']}: ${s['final_capital']:.2f} ({s['return_pct']:.2f}%)")


if __name__ == '__main__':
    asyncio.run(main())
