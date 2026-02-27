#!/usr/bin/env python3
"""
MTF 三重共振历史回测脚本
模拟 200U 账户，过去 3 个月的表现
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
    """交易记录"""
    entry_time: datetime
    exit_time: Optional[datetime]
    symbol: str
    direction: int  # 1=多, -1=空
    entry_price: float
    exit_price: Optional[float]
    stop_loss: float
    take_profit: float
    position_size: float  # 仓位大小（USDT）
    pnl: Optional[float] = None  # 盈亏
    pnl_pct: Optional[float] = None  # 盈亏百分比
    status: str = "open"  # open/closed/liquidated


class SimpleBacktester:
    """简化版 MTF 回测器"""

    def __init__(self, initial_capital: float = 200.0):
        self.initial_capital = initial_capital
        self.capital = initial_capital
        self.trades: List[Trade] = []
        self.current_trade: Optional[Trade] = None
        self.session = None

    async def _get_session(self):
        """获取或创建 session"""
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession(
                connector=ProxyConnector.from_url('http://127.0.0.1:7890')
            )
        return self.session

    async def close(self):
        """关闭 session"""
        if self.session and not self.session.closed:
            await self.session.close()

    async def fetch_klines(self, symbol: str, interval: str, limit: int = 500) -> pd.DataFrame:
        """获取历史K线"""
        url = "https://fapi.binance.com/fapi/v1/klines"
        params = {
            'symbol': symbol,
            'interval': interval,
            'limit': min(limit, 1000)  # Binance 最大 1000
        }

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
        """检查4H趋势"""
        ema20 = df_4h['close'].ewm(span=20).mean().iloc[-1]
        ema50 = df_4h['close'].ewm(span=50).mean().iloc[-1]
        current_price = df_4h['close'].iloc[-1]

        if ema20 > ema50 * 1.005 and current_price > ema20:  # 明显多头
            return 1, "4H bullish"
        elif ema20 < ema50 * 0.995 and current_price < ema20:  # 明显空头
            return -1, "4H bearish"
        else:
            return 0, "4H unclear"

    def check_15m_volume(self, df_15m: pd.DataFrame) -> Tuple[int, str, Optional[float]]:
        """检查15m放量"""
        avg_volume = df_15m['volume'].iloc[-50:-1].mean()
        current_volume = df_15m['volume'].iloc[-1]
        volume_ratio = current_volume / avg_volume if avg_volume > 0 else 0

        current_price = df_15m['close'].iloc[-1]
        prev_price = df_15m['close'].iloc[-2]
        price_change = (current_price - prev_price) / prev_price

        # 计算ATR
        tr = np.maximum(
            df_15m['high'] - df_15m['low'],
            np.maximum(
                abs(df_15m['high'] - df_15m['close'].shift(1)),
                abs(df_15m['low'] - df_15m['close'].shift(1))
            )
        )
        atr = tr.iloc[-14:].mean()

        if volume_ratio >= 2.0 and price_change > 0.005:  # 放量上涨
            return 1, f"15m volume up {volume_ratio:.1f}x", atr
        elif volume_ratio >= 2.0 and price_change < -0.005:  # 放量下跌
            return -1, f"15m volume down {volume_ratio:.1f}x", atr
        else:
            return 0, f"15m no signal ({volume_ratio:.1f}x)", atr

    def calculate_risk_reward(self, entry_price: float, direction: int, atr: float) -> Tuple[float, float, float]:
        """计算止损止盈"""
        # ATR 止损（2倍ATR）
        if direction == 1:  # 做多
            stop_loss = entry_price - atr * 2
            take_profit = entry_price + atr * 4  # 风报比 2:1
        else:  # 做空
            stop_loss = entry_price + atr * 2
            take_profit = entry_price - atr * 4

        risk = abs(entry_price - stop_loss)
        reward = abs(take_profit - entry_price)
        rr_ratio = reward / risk if risk > 0 else 0

        return stop_loss, take_profit, rr_ratio

    async def backtest_symbol(self, symbol: str, days: int = 90) -> Dict:
        """回测单个币种"""
        print(f"\n{'='*60}")
        print(f"Backtesting {symbol} (last {days} days)")
        print(f"{'='*60}")

        # 获取数据
        print("Fetching data...")
        df_4h = await self.fetch_klines(symbol, '4h', limit=500)
        df_15m = await self.fetch_klines(symbol, '15m', limit=1000)

        print(f"4H data: {len(df_4h)} candles")
        print(f"15m data: {len(df_15m)} candles")

        # 重置状态
        self.capital = self.initial_capital
        self.trades = []
        self.current_trade = None

        # 遍历历史数据（从最早开始）
        # 每4小时检查一次（对应一根4H K线）
        signals_found = 0

        for i in range(100, len(df_4h)):  # 留够历史数据
            current_time = df_4h.iloc[i]['timestamp']
            current_price = df_4h.iloc[i]['close']

            # 如果有持仓，检查是否触发止损/止盈
            if self.current_trade and self.current_trade.status == "open":
                # 找到对应的15m K线
                mask = (df_15m['timestamp'] >= self.current_trade.entry_time) & (df_15m['timestamp'] <= current_time)
                relevant_15m = df_15m[mask]

                for _, row in relevant_15m.iterrows():
                    high = row['high']
                    low = row['low']

                    # 检查止损
                    if self.current_trade.direction == 1:  # 多头
                        if low <= self.current_trade.stop_loss:
                            self._close_trade(self.current_trade, self.current_trade.stop_loss, row['timestamp'], "stop_loss")
                            break
                        elif high >= self.current_trade.take_profit:
                            self._close_trade(self.current_trade, self.current_trade.take_profit, row['timestamp'], "take_profit")
                            break
                    else:  # 空头
                        if high >= self.current_trade.stop_loss:
                            self._close_trade(self.current_trade, self.current_trade.stop_loss, row['timestamp'], "stop_loss")
                            break
                        elif low <= self.current_trade.take_profit:
                            self._close_trade(self.current_trade, self.current_trade.take_profit, row['timestamp'], "take_profit")
                            break

            # 如果没有持仓，检查信号
            if not self.current_trade or self.current_trade.status != "open":
                # 检查4H趋势
                df_4h_slice = df_4h.iloc[:i+1]
                trend_4h, trend_reason = self.check_4h_trend(df_4h_slice)

                if trend_4h != 0:  # 有趋势
                    # 找到对应的15m数据
                    current_4h_time = df_4h.iloc[i]['timestamp']
                    prev_4h_time = df_4h.iloc[i-1]['timestamp']

                    mask = (df_15m['timestamp'] > prev_4h_time) & (df_15m['timestamp'] <= current_4h_time)
                    df_15m_in_4h = df_15m[mask]

                    if len(df_15m_in_4h) > 0:
                        # 检查15m放量
                        df_15m_slice = df_15m[df_15m['timestamp'] <= current_4h_time]
                        volume_15m, volume_reason, atr = self.check_15m_volume(df_15m_slice)

                        # 三重共振（简化版：趋势+放量，跳过资金费率）
                        if trend_4h == volume_15m and volume_15m != 0:
                            signals_found += 1

                            # 计算入场价、止损、止盈
                            entry_price = df_15m_in_4h.iloc[-1]['close']
                            stop_loss, take_profit, rr_ratio = self.calculate_risk_reward(
                                entry_price, volume_15m, atr
                            )

                            # 检查风报比
                            if rr_ratio >= 2.0:
                                # 开仓（全仓）
                                position_size = self.capital

                                self.current_trade = Trade(
                                    entry_time=current_4h_time,
                                    exit_time=None,
                                    symbol=symbol,
                                    direction=volume_15m,
                                    entry_price=entry_price,
                                    exit_price=None,
                                    stop_loss=stop_loss,
                                    take_profit=take_profit,
                                    position_size=position_size,
                                    status="open"
                                )

                                self.trades.append(self.current_trade)

        # 关闭最后未平仓的订单
        if self.current_trade and self.current_trade.status == "open":
            last_price = df_4h.iloc[-1]['close']
            last_time = df_4h.iloc[-1]['timestamp']
            self._close_trade(self.current_trade, last_price, last_time, "end_of_data")

        # 计算统计
        return self._calculate_stats(symbol, signals_found)

    def _close_trade(self, trade: Trade, exit_price: float, exit_time: datetime, reason: str):
        """关闭交易"""
        trade.exit_price = exit_price
        trade.exit_time = exit_time
        trade.status = reason

        # 计算盈亏
        if trade.direction == 1:  # 多头
            pnl_pct = (exit_price - trade.entry_price) / trade.entry_price
        else:  # 空头
            pnl_pct = (trade.entry_price - exit_price) / trade.entry_price

        # 扣除手续费（0.05% taker）
        pnl_pct -= 0.0005 * 2  # 开仓+平仓

        trade.pnl_pct = pnl_pct
        trade.pnl = trade.position_size * pnl_pct

        # 更新资金
        self.capital += trade.pnl

    def _calculate_stats(self, symbol: str, signals_found: int) -> Dict:
        """计算统计信息"""
        if not self.trades:
            return {
                'symbol': symbol,
                'signals_found': signals_found,
                'trades': 0,
                'final_capital': self.capital,
                'total_return': 0,
                'win_rate': 0,
            }

        wins = [t for t in self.trades if t.pnl and t.pnl > 0]
        losses = [t for t in self.trades if t.pnl and t.pnl <= 0]

        total_return = (self.capital - self.initial_capital) / self.initial_capital * 100

        stats = {
            'symbol': symbol,
            'signals_found': signals_found,
            'trades': len(self.trades),
            'wins': len(wins),
            'losses': len(losses),
            'win_rate': len(wins) / len(self.trades) * 100 if self.trades else 0,
            'final_capital': self.capital,
            'total_return': total_return,
            'trades_list': self.trades
        }

        return stats

    def print_results(self, stats: Dict):
        """打印结果"""
        print(f"\n{'='*60}")
        print(f"BACKTEST RESULTS: {stats['symbol']}")
        print(f"{'='*60}")
        print(f"Initial Capital: ${self.initial_capital:.2f}")
        print(f"Final Capital: ${stats['final_capital']:.2f}")
        print(f"Total Return: {stats['total_return']:.2f}%")
        print(f"")
        print(f"Signals Found: {stats['signals_found']}")
        print(f"Trades Taken: {stats['trades']}")
        if stats['trades'] > 0:
            print(f"Wins: {stats['wins']} | Losses: {stats['losses']}")
            print(f"Win Rate: {stats['win_rate']:.1f}%")

            print(f"\n{'='*60}")
            print("TRADE LOG:")
            print(f"{'='*60}")
            for i, trade in enumerate(stats['trades_list'], 1):
                direction = "LONG" if trade.direction == 1 else "SHORT"
                pnl_str = f"${trade.pnl:.2f} ({trade.pnl_pct*100:.2f}%)" if trade.pnl else "N/A"
                exit_p = trade.exit_price if trade.exit_price else 0
                print(f"{i}. {trade.entry_time.strftime('%Y-%m-%d %H:%M')} | {direction} | "
                      f"Entry: ${trade.entry_price:.2f} | Exit: ${exit_p:.2f} | "
                      f"PnL: {pnl_str}")


async def main():
    """主函数"""
    backtester = SimpleBacktester(initial_capital=200.0)

    # 回测多个币种
    symbols = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT']

    results = []
    try:
        for symbol in symbols:
            try:
                stats = await backtester.backtest_symbol(symbol, days=90)
                results.append(stats)
                backtester.print_results(stats)
            except Exception as e:
                print(f"Error backtesting {symbol}: {e}")
    finally:
        await backtester.close()

    # 总结
    print(f"\n{'='*60}")
    print("PORTFOLIO SUMMARY")
    print(f"{'='*60}")
    total_capital = sum(s['final_capital'] for s in results)
    print(f"Total Capital (combined): ${total_capital:.2f}")
    for stats in results:
        print(f"  {stats['symbol']}: ${stats['final_capital']:.2f} ({stats['total_return']:.2f}%)")


if __name__ == '__main__':
    asyncio.run(main())
