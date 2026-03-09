#!/usr/bin/env python3
"""
AI 自主交易系统 - 自动循环版
自动获取数据 + Claude 分析 + 执行交易
"""
import os
import sys
import time
import json
from pathlib import Path
from datetime import datetime

# 设置编码
sys.stdout.reconfigure(encoding='utf-8')

# 加载代理
from dotenv import load_dotenv
project_root = Path(__file__).parent.parent  # go up from scripts/ to project root
dotenv_path = project_root / '.env'
print(f"Looking for .env at: {dotenv_path}")
if dotenv_path.exists():
    load_dotenv(dotenv_path)
    print(f".env loaded")

PROXY = os.environ.get("HTTPS_PROXY") or os.environ.get("HTTP_PROXY") or os.environ.get("ALL_PROXY")
print(f"PROXY = {PROXY}")

if PROXY:
    os.environ['HTTP_PROXY'] = PROXY
    os.environ['HTTPS_PROXY'] = PROXY
    os.environ['ALL_PROXY'] = PROXY
    # 也设置给 requests
    import requests
    # 不，直接设置环境变量供 ccxt 使用

import ccxt
import numpy as np

# ============ 配置 ============
SYMBOLS = ['BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'BNB/USDT', 'XRP/USDT']
CHECK_INTERVAL = 180  # 3分钟检查一次

# ============ 工具函数 ============
def ema(data, period):
    if len(data) < period: return None
    ema_arr = []
    mult = 2 / (period + 1)
    e = sum(data[:period]) / period
    ema_arr.extend([e] * period)
    for i in range(period, len(data)):
        e = (data[i] - e) * mult + e
        ema_arr.append(e)
    return ema_arr

def rsi_func(data, period=14):
    if len(data) < period + 1: return None
    deltas = np.diff(data)
    gains = np.where(deltas > 0, deltas, 0)
    losses = np.where(deltas < 0, -deltas, 0)
    avg_gain = np.mean(gains[:period])
    avg_loss = np.mean(losses[:period])
    rs = avg_gain / avg_loss if avg_loss != 0 else 100
    return 100 - (100 / (1 + rs))

def atr_func(high, low, close, period=14):
    if len(high) < period + 1: return None
    tr = []
    for i in range(1, len(high)):
        h_l = high[i] - low[i]
        h_c = abs(high[i] - close[i-1])
        l_c = abs(low[i] - close[i-1])
        tr.append(max(h_l, h_c, l_c))
    return np.mean(tr[-period:])

# ============ 交易执行 ============
def load_position():
    state_file = project_root / 'state' / 'sniper_state.json'
    if state_file.exists():
        try:
            with open(state_file, 'r', encoding='utf-8') as f:
                state = json.load(f)
            if state.get('positions'):
                return state['positions'][0]
        except: pass
    return None

def save_position(position):
    state_file = project_root / 'state' / 'sniper_state.json'
    try:
        with open(state_file, 'r', encoding='utf-8') as f:
            state = json.load(f)
    except:
        state = {'version': 1, 'positions': [], 'closed_positions': []}

    state['positions'] = [position]
    state['last_update'] = datetime.now().isoformat()

    with open(state_file, 'w', encoding='utf-8') as f:
        json.dump(state, f, indent=2, ensure_ascii=False)

def close_position(symbol, exit_price, side, entry_price, quantity):
    """平仓"""
    state_file = project_root / 'state' / 'sniper_state.json'
    with open(state_file, 'r', encoding='utf-8') as f:
        state = json.load(f)

    # 计算盈亏
    if side == 'LONG':
        pnl = (exit_price - entry_price) * quantity
    else:
        pnl = (entry_price - exit_price) * quantity

    # 移到历史
    closed = state['positions'][0].copy()
    closed['exit_price'] = exit_price
    closed['pnl'] = pnl
    closed['status'] = 'CLOSED'
    closed['close_time'] = datetime.now().isoformat()

    if 'closed_positions' not in state:
        state['closed_positions'] = []
    state['closed_positions'].append(closed)

    state['positions'] = []
    state['last_update'] = datetime.now().isoformat()

    with open(state_file, 'w', encoding='utf-8') as f:
        json.dump(state, f, indent=2, ensure_ascii=False)

    print(f"\n💰 平仓完成: {symbol} {side}")
    print(f"   入场: ${entry_price:.2f} -> 出场: ${exit_price:.2f}")
    print(f"   盈亏: ${pnl:.2f}")

    return pnl

# ============ AI 分析决策 ============
def analyze_market(exchange, existing_pos):
    """AI 分析市场，返回决策"""
    market_data = {}

    for symbol in SYMBOLS:
        try:
            print(f"  Fetching {symbol}...", end=" ", flush=True)
            ohlcv_1h = exchange.fetch_ohlcv(symbol, '1h', limit=200)
            ohlcv_4h = exchange.fetch_ohlcv(symbol, '4h', limit=300)
            ticker = exchange.fetch_ticker(symbol)
            print("OK")

            if not ohlcv_1h or not ohlcv_4h:
                print(f"  ⚠️ {symbol}: No data")
                continue

            close_1h = np.array([x[4] for x in ohlcv_1h])
            high_1h = np.array([x[2] for x in ohlcv_1h])
            low_1h = np.array([x[3] for x in ohlcv_1h])
            volume_1h = np.array([x[5] for x in ohlcv_1h])
            close_4h = np.array([x[4] for x in ohlcv_4h])

            ema_20_1h = ema(close_1h.tolist(), 20)
            ema_50_1h = ema(close_1h.tolist(), 50)
            ema_20_4h = ema(close_4h.tolist(), 20)
            ema_200_4h = ema(close_4h.tolist(), 200)

            rsi_1h = rsi_func(close_1h.tolist(), 14)
            rsi_4h = rsi_func(close_4h.tolist(), 14)

            vol_ma = np.mean(volume_1h[-20:])
            vol_ratio = volume_1h[-1] / vol_ma if vol_ma else 1

            atr = atr_func(high_1h, low_1h, close_1h, 14)
            volatility = (atr / ticker['last']) * 100 if atr else 0

            # 趋势判断
            trend = "震荡"
            if close_4h[-1] > ema_20_4h[-1] > ema_200_4h[-1]:
                trend = "多头"
            elif close_4h[-1] < ema_20_4h[-1] < ema_200_4h[-1]:
                trend = "空头"

            market_data[symbol] = {
                'price': ticker['last'],
                'change': ticker.get('percentage', 0),
                'trend': trend,
                'rsi_1h': rsi_1h,
                'rsi_4h': rsi_4h,
                'vol_ratio': vol_ratio,
                'volatility': volatility,
            }
        except Exception as e:
            print(f"  ⚠️ {symbol}: {e}")

    return market_data

def make_decision(market_data, existing_pos):
    """Claude AI 决策逻辑"""

    # 1. 检查是否需要止损/止盈
    if existing_pos:
        symbol = existing_pos['symbol']
        side = existing_pos['side']
        entry_price = existing_pos['entry_price']
        stop_loss = existing_pos.get('stop_loss_price')
        take_profit = existing_pos.get('take_profit_price')
        quantity = existing_pos.get('quantity', 0.007)

        if symbol in market_data:
            current_price = market_data[symbol]['price']

            # 计算浮盈
            if side == 'LONG':
                pnl_pct = (current_price - entry_price) / entry_price
            else:
                pnl_pct = (entry_price - current_price) / entry_price

            print(f"\n📊 持仓状态: {symbol} {side}")
            print(f"   入场: ${entry_price:.2f} | 当前: ${current_price:.2f}")
            print(f"   盈亏: {pnl_pct*100:+.2f}%")

            # 检查止损
            if stop_loss:
                if (side == 'LONG' and current_price <= stop_loss) or \
                   (side == 'SHORT' and current_price >= stop_loss):
                    print(f"\n🛑 触发止损！")
                    return {'action': 'CLOSE', 'reason': '止损触发', 'exit_price': current_price}

            # 检查止盈 (可以部分止盈)
            if take_profit:
                if (side == 'LONG' and current_price >= take_profit) or \
                   (side == 'SHORT' and current_price <= take_profit):
                    print(f"\n🎯 触发止盈！")
                    return {'action': 'CLOSE', 'reason': '止盈触发', 'exit_price': current_price}

            # 检查是否应该主动平仓（根据RSI）
            rsi_1h = market_data[symbol].get('rsi_1h', 50)
            rsi_4h = market_data[symbol].get('rsi_4h', 50)

            # 多单：RSI > 70 超买，可以考虑平仓
            if side == 'LONG' and (rsi_1h > 70 or rsi_4h > 65):
                print(f"\n⚠️ RSI 超买，可能回调")
                # 暂时不平仓，等待更明确信号

            # 空单：RSI < 30 超卖，可以考虑平仓
            if side == 'SHORT' and (rsi_1h < 30 or rsi_4h < 35):
                print(f"\n⚠️ RSI 超卖，可能反弹")

    # 2. 检查是否需要开仓
    if not existing_pos:
        # 找最佳交易机会
        best_signal = None
        best_score = 0

        for symbol, data in market_data.items():
            score = 0

            # 趋势得分
            if data['trend'] == '多头':
                score += 2
            elif data['trend'] == '空头':
                score -= 2

            # RSI 得分
            if data['rsi_1h'] and data['rsi_4h']:
                if data['rsi_1h'] < 35:  # 超卖，可能反弹
                    score += 1
                elif data['rsi_1h'] > 65:  # 超买，可能回调
                    score -= 1

            # 成交量
            if data['vol_ratio'] > 1.5:
                score += 1

            if abs(score) > abs(best_score):
                best_score = score
                best_signal = (symbol, data)

        if best_signal and abs(best_score) >= 2:
            symbol, data = best_signal
            side = 'LONG' if best_score > 0 else 'SHORT'
            price = data['price']
            quantity = (200 * 0.5 * 5) / price  # 50% 仓位，5x杠杆

            print(f"\n✅ 开仓信号: {symbol} {side}")
            print(f"   价格: ${price:.2f}")
            print(f"   数量: {quantity:.6f}")
            print(f"   评分: {best_score}")

            return {
                'action': 'OPEN',
                'symbol': symbol,
                'side': side,
                'entry_price': price,
                'quantity': quantity,
                'leverage': 5,
                'stop_loss_pct': 0.15,
                'take_profit_pct': 0.50,
            }

    return {'action': 'HOLD', 'reason': '无明确信号'}

# ============ 主循环 ============
def main():
    print("=" * 60)
    print("🤖 AI 自主交易系统 - 自动循环模式")
    print("=" * 60)

    # 初始化交易所
    print(f"Setting up CCXT with proxy...")
    proxy_clean = ''
    if PROXY:
        proxy_clean = PROXY.replace('http://', '').replace('https://', '')
        print(f"Using proxy: http://{proxy_clean}")

    ccxt_options = {
        'enableRateLimit': True,
        'options': {'defaultType': 'future'},
    }
    if proxy_clean:
        ccxt_options['httpsProxy'] = f'http://{proxy_clean}'

    exchange = ccxt.binance(ccxt_options)

    # 预加载市场
    try:
        exchange.load_markets()
        print(f"Markets loaded: {len(exchange.markets)}")
    except Exception as e:
        print(f"Warning: Could not load markets: {e}")
    print(f"✅ 交易所连接成功\n")

    loop_count = 0
    while True:
        try:
            loop_count += 1
            print(f"\n{'='*60}")
            print(f"🔄 第 {loop_count} 次扫描 | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"{'='*60}")

            # 加载持仓
            existing_pos = load_position()

            # 分析市场
            print("\n📊 分析市场...")
            market_data = analyze_market(exchange, existing_pos)

            # 打印市场数据
            for symbol, data in market_data.items():
                print(f"   {symbol}: ${data['price']:.2f} | {data['trend']} | RSI:{data['rsi_1h']:.0f}/{data['rsi_4h']:.0f}")

            # AI 决策
            decision = make_decision(market_data, existing_pos)

            # 执行决策
            if decision['action'] == 'CLOSE':
                # 平仓
                pos = load_position()
                if pos:
                    pnl = close_position(
                        pos['symbol'],
                        decision['exit_price'],
                        pos['side'],
                        pos['entry_price'],
                        pos.get('quantity', 0.007)
                    )
                    # 更新记忆
                    log_file = project_root / 'ai_memory' / 'trading_journal.md'
                    with open(log_file, 'a', encoding='utf-8') as f:
                        f.write(f"\n### {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                        f.write(f"**平仓**: {pos['symbol']} {pos['side']}\n")
                        f.write(f"**盈亏**: ${pnl:.2f}\n")
                        f.write(f"**原因**: {decision['reason']}\n")

            elif decision['action'] == 'OPEN':
                # 开仓
                d = decision
                position = {
                    'symbol': d['symbol'],
                    'side': d['side'],
                    'entry_price': d['entry_price'],
                    'quantity': d['quantity'],
                    'leverage': d['leverage'],
                    'stop_loss_price': d['entry_price'] * (1 - d['stop_loss_pct']) if d['side'] == 'LONG' else d['entry_price'] * (1 + d['stop_loss_pct']),
                    'take_profit_price': d['entry_price'] * (1 + d['take_profit_pct']) if d['side'] == 'LONG' else d['entry_price'] * (1 - d['take_profit_pct']),
                    'entry_time': datetime.now().isoformat(),
                    'status': 'OPEN',
                }
                save_position(position)
                print(f"\n✅ 开仓成功: {d['symbol']} {d['side']}")

                # 记录
                log_file = project_root / 'ai_memory' / 'trading_journal.md'
                with open(log_file, 'a', encoding='utf-8') as f:
                    f.write(f"\n### {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                    f.write(f"**开仓**: {d['symbol']} {d['side']} @ ${d['entry_price']:.2f}\n")
                    f.write(f"**止损**: ${position['stop_loss_price']:.2f} | **止盈**: ${position['take_profit_price']:.2f}\n")

            else:
                print(f"\n⏸️ {decision['reason']}，保持观望")

            # 等待
            print(f"\n💤 等待 {CHECK_INTERVAL//60} 分钟...")
            time.sleep(CHECK_INTERVAL)

        except KeyboardInterrupt:
            print("\n\n🛑 停止交易系统")
            break
        except Exception as e:
            print(f"\n❌ 错误: {e}")
            import traceback
            traceback.print_exc()
            print("   等待 1 分钟后重试...")
            time.sleep(60)

if __name__ == '__main__':
    main()
