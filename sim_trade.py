#!/usr/bin/env python3
"""
Simple Sim Trade - 完全离线版本
使用固定价格数据 + 随机信号
"""
import random
import json
from datetime import datetime
from pathlib import Path

# 配置
INITIAL_CAPITAL = 200
TRADE_LOG = Path("E:/Desktop/usdt/sim_trades.md")
STATE_FILE = Path("E:/Desktop/usdt/sim_state.json")

# 固定价格（最后已知）
PRICES = {'BTC': 66600, 'ETH': 1960, 'SOL': 138, 'BNB': 620}

def load_state():
    if STATE_FILE.exists():
        with open(STATE_FILE, 'r') as f:
            return json.load(f)
    return {'position': None, 'capital': INITIAL_CAPITAL}

def save_state(state):
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f)

def get_price(symbol):
    base = PRICES.get(symbol, 1000)
    return base * random.uniform(0.99, 1.01)

def check_signal():
    if random.random() < 0.25:
        return random.choice(['LONG', 'SHORT'])
    return 'HOLD'

def log(msg, trade_log):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(trade_log, 'a', encoding='utf-8') as f:
        f.write(f"### {ts} - {msg}\n")
    print(f"### {ts} - {msg}")

def run():
    state = load_state()
    position = state.get('position')
    capital = state.get('capital', INITIAL_CAPITAL)
    
    print(f"=== Sim Trade (Offline) ===")
    print(f"Balance: ${capital:.2f}")
    if position:
        print(f"Position: {position['symbol']} {position['side']} @ ${position['entry']:.2f}")
    print()
    
    for symbol in ['BTC', 'ETH', 'SOL', 'BNB']:
        price = get_price(symbol)
        signal = check_signal()
        
        print(f"{symbol}: ${price:.2f} | {signal}")
        
        # 平仓检查
        if position and position['symbol'] == symbol:
            pnl = 0
            closed = False
            reason = ""
            
            if position['side'] == 'LONG':
                if price >= position['entry'] * 1.03:
                    pnl = (price - position['entry']) * position['qty']
                    closed = True
                    reason = "TP"
                elif price <= position['entry'] * 0.97:
                    pnl = (price - position['entry']) * position['qty']
                    closed = True
                    reason = "SL"
            else:
                if price <= position['entry'] * 0.97:
                    pnl = (position['entry'] - price) * position['qty']
                    closed = True
                    reason = "TP"
                elif price >= position['entry'] * 1.03:
                    pnl = (position['entry'] - price) * position['qty']
                    closed = True
                    reason = "SL"
            
            if closed:
                capital += pnl
                log(f"CLOSE {reason}: {symbol} @ ${price:.2f} | PnL: {pnl:+.2f} | Bal: ${capital:.2f}", TRADE_LOG)
                position = None
    
    # 开仓（只有空仓时才开）
    if not position:
        for symbol in ['BTC', 'ETH', 'SOL', 'BNB']:
            price = get_price(symbol)
            signal = check_signal()
            if signal != 'HOLD':
                qty = 0.002 if symbol == 'BTC' else 0.05
                position = {'symbol': symbol, 'side': signal, 'entry': price, 'qty': qty}
                log(f"OPEN: {symbol} {signal} @ ${price:.2f} x {qty}", TRADE_LOG)
                break
    
    # 保存状态
    state = {'position': position, 'capital': capital}
    save_state(state)
    
    print()
    if position:
        print(f"POS: {position['symbol']} {position['side']} @ ${position['entry']:.2f}")
    else:
        print(f"NO POS | Balance: ${capital:.2f}")

if __name__ == "__main__":
    run()
