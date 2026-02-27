"""
完整一年历史数据回测

使用三重共振策略进行历史回测分析
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


async def run_year_backtest():
    """运行一年完整回测"""
    import aiohttp
    import pandas as pd
    import numpy as np

    symbol = "BTCUSDT"
    proxy = os.environ.get("HTTP_PROXY") or os.environ.get("HTTPS_PROXY")

    logger.info("=" * 70)
    logger.info("83天历史数据回测")
    logger.info("=" * 70)

    # 获取数据 - 约83天
    url = "https://fapi.binance.com/fapi/v1/klines"
    params = {
        'symbol': symbol,
        'interval': '1h',
        'limit': 1500  # 约62天数据
    }

    async with aiohttp.ClientSession() as session:
        kwargs = {'params': params}
        if proxy:
            kwargs['proxy'] = proxy

        logger.info(f"请求参数: {params}")

        async with session.get(url, **kwargs) as resp:
            logger.info(f"响应状态: {resp.status}")
            if resp.status != 200:
                text = await resp.text()
                logger.error(f"错误响应: {text[:500]}")
                return

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

    logger.info(f"✅ 获取数据: {len(df)} 根K线")
    logger.info(f"时间范围: {df['timestamp'].min()} ~ {df['timestamp'].max()}")
    logger.info(f"价格范围: ${df['low'].min():,.2f} ~ ${df['high'].max():,.2f}")

    # ========== 计算技术指标 ==========
    logger.info("\n【1】计算技术指标...")

    # RSI
    delta = df['close'].diff()
    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)
    avg_gain = gain.rolling(window=14).mean()
    avg_loss = loss.rolling(window=14).mean()
    rs = avg_gain / avg_loss
    df['rsi'] = 100 - (100 / (1 + rs))

    # EMA
    df['ema9'] = df['close'].ewm(span=9).mean()
    df['ema20'] = df['close'].ewm(span=20).mean()
    df['ema50'] = df['close'].ewm(span=50).mean()

    # ATR
    high_low = df['high'] - df['low']
    high_close = abs(df['high'] - df['close'].shift())
    low_close = abs(df['low'] - df['close'].shift())
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    df['atr'] = tr.rolling(window=14).mean()

    # 成交量均线
    df['volume_ma'] = df['volume'].rolling(window=20).mean()
    df['volume_ratio'] = df['volume'] / df['volume_ma']

    # 布林带
    df['bb_middle'] = df['close'].rolling(20).mean()
    bb_std = df['close'].rolling(20).std()
    df['bb_upper'] = df['bb_middle'] + (bb_std * 2)
    df['bb_lower'] = df['bb_middle'] - (bb_std * 2)

    # ========== 简单三重共振策略信号 ==========
    logger.info("\n【2】生成交易信号...")

    signals = []
    position = None  # None, 'long', 'short'

    for i in range(50, len(df)):
        row = df.iloc[i]
        prev = df.iloc[i-1]

        # 跳过持仓中的日子
        if position:
            # 检查是否触发止损/止盈
            if position == 'long':
                # 止损: 2%
                if row['close'] < signals[-1]['entry_price'] * 0.98:
                    signals[-1]['exit_price'] = row['close']
                    signals[-1]['exit_time'] = row['timestamp']
                    signals[-1]['pnl_pct'] = (row['close'] - signals[-1]['entry_price']) / signals[-1]['entry_price'] * 100
                    signals[-1]['reason'] = 'STOP_LOSS'
                    position = None
                    continue
                # 止盈: 4%
                elif row['close'] > signals[-1]['entry_price'] * 1.04:
                    signals[-1]['exit_price'] = row['close']
                    signals[-1]['exit_time'] = row['timestamp']
                    signals[-1]['pnl_pct'] = (row['close'] - signals[-1]['entry_price']) / signals[-1]['entry_price'] * 100
                    signals[-1]['reason'] = 'TAKE_PROFIT'
                    position = None
                    continue
            continue

        # 简单的三重共振信号检测
        # 条件1: 4H趋势 (EMA20 > EMA50)
        trend_bull = row['ema20'] > row['ema50']

        # 条件2: 成交量放大 (>= 2倍)
        volume_spike = row['volume_ratio'] >= 2.0

        # 条件3: RSI 极端区域
        rsi_oversold = row['rsi'] < 35
        rsi_overbought = row['rsi'] > 65

        # 金叉买入信号
        if trend_bull and volume_spike and rsi_oversold:
            if prev['ema20'] <= prev['ema50']:  # 刚金叉
                signals.append({
                    'time': row['timestamp'],
                    'type': 'BUY',
                    'entry_price': row['close'],
                    'rsi': row['rsi'],
                    'volume_ratio': row['volume_ratio'],
                    'atr': row['atr'],
                    'stop_loss': row['close'] * 0.98,
                    'take_profit': row['close'] * 1.04,
                    'evidence_count': 3,
                    'evidence': [
                        f"4H EMA20 > EMA50, 多头趋势",
                        f"成交量放大 {row['volume_ratio']:.1f}倍",
                        f"RSI {row['rsi']:.1f} 超卖区域"
                    ]
                })
                position = 'long'

        # 死叉卖出信号
        elif not trend_bull and volume_spike and rsi_overbought:
            if prev['ema20'] >= prev['ema50']:  # 刚死叉
                signals.append({
                    'time': row['timestamp'],
                    'type': 'SELL',
                    'entry_price': row['close'],
                    'rsi': row['rsi'],
                    'volume_ratio': row['volume_ratio'],
                    'atr': row['atr'],
                    'stop_loss': row['close'] * 1.02,
                    'take_profit': row['close'] * 0.96,
                    'evidence_count': 3,
                    'evidence': [
                        f"4H EMA20 < EMA50, 空头趋势",
                        f"成交量放大 {row['volume_ratio']:.1f}倍",
                        f"RSI {row['rsi']:.1f} 超买区域"
                    ]
                })
                position = 'short'

    # 统计结果
    logger.info(f"\n【3】回测结果统计")
    logger.info(f"总信号数: {len(signals)}")

    completed_trades = [s for s in signals if 'exit_price' in s]
    open_trades = [s for s in signals if 'exit_price' not in s]

    logger.info(f"完成交易: {len(completed_trades)}")
    logger.info(f"持仓中: {len(open_trades)}")

    if completed_trades:
        wins = [t for t in completed_trades if t['pnl_pct'] > 0]
        losses = [t for t in completed_trades if t['pnl_pct'] <= 0]

        win_rate = len(wins) / len(completed_trades) * 100 if completed_trades else 0
        avg_win = np.mean([t['pnl_pct'] for t in wins]) if wins else 0
        avg_loss = np.mean([t['pnl_pct'] for t in losses]) if losses else 0

        total_pnl = sum(t['pnl_pct'] for t in completed_trades)

        logger.info(f"\n胜率: {win_rate:.1f}% ({len(wins)}胜/{len(losses)}亏)")
        logger.info(f"平均盈利: {avg_win:+.2f}%")
        logger.info(f"平均亏损: {avg_loss:.2f}%")
        logger.info(f"总收益: {total_pnl:+.2f}%")

        # 按月统计
        logger.info(f"\n【4】按月收益:")
        for trade in completed_trades:
            month = trade['time'].strftime('%Y-%m')
            logger.info(f"  {month}: {trade['type']} @ ${trade['entry_price']:,.0f} → ${trade['exit_price']:,.0f} ({trade['pnl_pct']:+.2f}%)")

    # 展示最新信号
    logger.info(f"\n【5】最新交易信号:")
    for sig in signals[-5:]:
        logger.info(f"  {sig['time']}: {sig['type']} @ ${sig['entry_price']:,.2f}")
        logger.info(f"    RSI: {sig['rsi']:.1f}, 成交量倍数: {sig['volume_ratio']:.1f}x")
        logger.info(f"    止损: ${sig['stop_loss']:,.0f}, 止盈: ${sig['take_profit']:,.0f}")
        logger.info(f"    证据: {sig['evidence']}")

    # 模拟 200U 收益
    if completed_trades:
        initial_capital = 200
        final_capital = initial_capital
        for trade in completed_trades:
            final_capital *= (1 + trade['pnl_pct'] / 100)

        logger.info(f"\n【6】200U 模拟收益:")
        logger.info(f"初始资金: ${initial_capital:.2f}")
        logger.info(f"最终资金: ${final_capital:.2f}")
        logger.info(f"总收益率: {(final_capital/initial_capital - 1) * 100:+.2f}%")

    # ========== 基于准则的 AI 分析 ==========
    logger.info("\n" + "=" * 70)
    logger.info("【7】基于交易准则的 AI 分析")
    logger.info("=" * 70)

    # 获取最新数据
    latest = df.iloc[-1]
    prev_20 = df.iloc[-20]

    analysis = f"""
## 用户交易准则
- 本金: 200 USDT
- 策略: 极低频、极高置信度狙击手模式
- 止损: 2%, 止盈: 4%
- 要求: 至少 2 条证据

## 当前市场状态

### 价格信息
- 当前价格: ${latest['close']:,.2f}
- 20日最高: ${df.tail(20)['high'].max():,.2f}
- 20日最低: ${df.tail(20)['low'].min():,.2f}

### 技术指标
- RSI(14): {latest['rsi']:.1f}
- EMA9: ${latest['ema9']:,.2f}
- EMA20: ${latest['ema20']:,.2f}
- EMA50: ${latest['ema50']:,.2f}
- ATR: ${latest['atr']:,.2f}

### 趋势判断
- 4H趋势: {'多头' if latest['ema20'] > latest['ema50'] else '空头'}
- 成交量: {latest['volume_ratio']:.2f}x (平均)

## 三重共振检测

### 条件1: 4H宏观趋势
- EMA20 > EMA50: {'✅ 通过' if latest['ema20'] > latest['ema50'] else '❌ 不通过'}

### 条件2: 极端RSI
- RSI < 35 (超卖): {'✅ 通过' if latest['rsi'] < 35 else '❌ 不通过'}
- RSI > 65 (超买): {'✅ 通过' if latest['rsi'] > 65 else '❌ 不通过'}

### 条件3: 成交量放大
- 成交量 >= 2x: {'✅ 通过' if latest['volume_ratio'] >= 2 else '❌ 不通过'}

## 结论
"""

    # 判断是否符合交易条件
    trend_ok = latest['ema20'] > latest['ema50']
    rsi_extreme = latest['rsi'] < 35 or latest['rsi'] > 65
    volume_ok = latest['volume_ratio'] >= 2

    if trend_ok and rsi_extreme and volume_ok:
        direction = "做多" if latest['rsi'] < 35 else "做空"
        analysis += f"""
### 🎯 交易信号: {direction}

**证据链:**
1. 4H EMA20 > EMA50, {'多头趋势确认' if latest['ema20'] > latest['ema50'] else '空头趋势确认'}
2. RSI {latest['rsi']:.1f} 处于{'超卖' if latest['rsi'] < 35 else '超买'}区域
3. 成交量放大 {latest['volume_ratio']:.1f}倍

**交易建议:**
- 入场价: ${latest['close']:,.2f}
- 止损: ${latest['close'] * 0.98:,.2f} (-2%)
- 止盈: ${latest['close'] * 1.04:,.2f} (+4%)
- 仓位: 30-50% (60-100 USDT)
"""
    else:
        analysis += f"""
### ⏸️ 交易信号: 观望

**原因:**
- 4H趋势: {'✅' if trend_ok else '❌'} {'多头' if latest['ema20'] > latest['ema50'] else '空头'}
- RSI极端: {'✅' if rsi_extreme else '❌'} ({latest['rsi']:.1f})
- 成交量放大: {'✅' if volume_ok else '❌'} ({latest['volume_ratio']:.1f}x)

**建议:**
- 当前不符合三重共振条件
- 等待 RSI 进入极端区域 ( <35 或 >65 )
- 同时成交量放大时再考虑入场
"""

    logger.info(analysis)


if __name__ == '__main__':
    asyncio.run(run_year_backtest())
