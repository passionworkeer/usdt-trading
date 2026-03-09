#!/usr/bin/env python3
"""
模拟交易系统 - 使用真实Binance数据
记录交易日志，虚拟200U资金
"""
import os
import requests
import random
import time
from datetime import datetime
from pathlib import Path

# 设置代理环境变量
os.environ['http_proxy'] = 'http://127.0.0.1:7890'
os.environ['https_proxy'] = 'http://127.0.0.1:7890'

# ============ 配置 ============
INITIAL_CAPITAL = 200  # 虚拟起始资金 USDT
TRADE_LOG = Path("E:/Desktop/usdt/sim_trades.md")

# 持仓状态
position = None  # {'symbol': 'BTC', 'side': 'LONG', 'entry': 67000, 'qty': 0.01}
capital = INITIAL_CAPITAL

def get_price(symbol: str) -> float:
    """获取真实价格"""
    time.sleep(0.5)
    try:
        url = f"https://api.binance.com/api/v3/ticker/price?symbol={symbol}USDT"
        r = requests.get(url, timeout=20)
        return float(r.json()['price'])
    except Exception as e:
        print(f"Error {symbol}: {e}")
        return None

def get_rsi(symbol: str) -> float:
    """获取RSI（模拟）"""
    # 简化：随机RSI
    return random.uniform(20, 80)

def check_signal(symbol: str) -> str:
    """简单的信号生成"""
    rsi = get_rsi(symbol)
    # 30%概率出信号
    if random.random() < 0.3:
        if rsi < 45:
            return "LONG"
        elif rsi > 55:
            return "SHORT"
    return "HOLD"

def open_trade(symbol: str, side: str, price: float, qty: float):
    """开仓"""
    global position, capital
    cost = price * qty
    
    if cost > capital * 0.5:
        qty = (capital * 0.5) / price  # 最多用50%仓位
    
    position = {
        'symbol': symbol,
        'side': side,
        'entry': price,
        'qty': qty,
        'entry_time': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    log_trade(f"OPEN: {symbol} {side} @ ${price:.2f} x {qty:.4f}")

def close_trade(exit_price: float, reason: str = "TP/SL"):
    """平仓"""
    global position, capital
    
    if not position:
        return
    
    pnl = 0
    if position['side'] == 'LONG':
        pnl = (exit_price - position['entry']) * position['qty']
    else:
        pnl = (position['entry'] - exit_price) * position['qty']
    
    capital += pnl
    
    log_trade(f"CLOSE: {position['symbol']} {reason} @ ${exit_price:.2f}")
    log_trade(f"PnL: {'+' if pnl >= 0 else ''}{pnl:.2f} USDT | Balance: {capital:.2f}")
    
    position = None

def log_trade(msg: str):
    """记录交易"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"### {timestamp} - {msg}\n"
    
    with open(TRADE_LOG, 'a', encoding='utf-8') as f:
        f.write(line)
    
    print(line.strip())

def run_scan():
    """运行一次扫描"""
    global position
    
    symbols = ['BTC', 'ETH', 'SOL', 'BNB']  # XRP有时API不支持
    
    for symbol in symbols:
        price = get_price(symbol)
        signal = check_signal(symbol)
        
        print(f"{symbol}: ${price:.2f} | Signal: {signal}")
        
        # 如果有持仓，检查是否平仓
        if position and position['symbol'] == symbol:
            if position['side'] == 'LONG':
                if price >= position['entry'] * 1.03:
                    close_trade(price, "TP 3%")
                elif price <= position['entry'] * 0.97:
                    close_trade(price, "SL 3%")
            else:
                if price <= position['entry'] * 0.97:
                    close_trade(price, "TP 3%")
                elif price >= position['entry'] * 1.03:
                    close_trade(price, "SL 3%")
        
        # 如果没有持仓，检查是否开仓
        if not position and signal != "HOLD":
            qty = 0.002 if symbol == 'BTC' else 0.05
            open_trade(symbol, signal, price, qty)
    
    if position:
        print(f"\n=== POSITION: {position['symbol']} {position['side']} @ ${position['entry']:.2f}")
    else:
        print(f"\n=== NO POSITION | Balance: {capital:.2f} USDT")

# ============ 主程序 ============
if __name__ == "__main__":
    # 初始化日志（如果不存在）
    if not TRADE_LOG.exists():
        with open(TRADE_LOG, 'w', encoding='utf-8') as f:
            f.write(f"# Sim Trade Log (Initial: {INITIAL_CAPITAL} USDT)\n\n")
    
    print(f"=== Sim Trade System Started | Initial: {INITIAL_CAPITAL} USDT ===\n")
    
    run_scan()
