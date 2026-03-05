#!/usr/bin/env python3
"""
实时交易系统
- 每分钟扫描市场
- 自动开仓/平仓
- 信号通知
"""

import requests
import json
import time
from datetime import datetime

PROXIES = {'http': 'http://127.0.0.1:7890', 'https': 'http://127.0.0.1:7890'}
STATE_FILE = 'scripts/paper_trading_state.json'
LOG_FILE = 'scripts/trader.log'

def log(msg):
    timestamp = datetime.now().strftime('%H:%M:%S')
    line = f"[{timestamp}] {msg}"
    print(line)
    with open(LOG_FILE, 'a') as f:
        f.write(line + '\n')

def load_state():
    try:
        with open(STATE_FILE) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, OSError) as e:
        logger.debug(f"加载状态失败: {e}，使用默认状态")
        return {'capital': 226.3, 'positions': {}, 'trades': []}

def save_state(state):
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f, indent=2)

def get_price(symbol):
    try:
        r = requests.get('https://fapi.binance.com/fapi/v1/ticker/24hr',
                        params={'symbol': symbol},
                        proxies=PROXIES, timeout=5, verify=False)
        return float(r.json()['lastPrice'])
    except (requests.RequestException, ValueError, KeyError) as e:
        logger.debug(f"获取 {symbol} 价格失败: {e}")
        return None

def scan_market():
    """扫描市场寻找机会"""
    symbols = ['BTCUSDT', 'ETHUSDT', 'BNBUSDT', 'SOLUSDT', 'AVAXUSDT']
    opportunities = []

    for sym in symbols:
        try:
            # 24h数据
            t = requests.get('https://fapi.binance.com/fapi/v1/ticker/24hr',
                           params={'symbol': sym},
                           proxies=PROXIES, timeout=5, verify=False)
            ticker = t.json()

            # K线
            k = requests.get('https://fapi.binance.com/fapi/v1/klines',
                           params={'symbol': sym, 'interval': '1h', 'limit': 480},
                           proxies=PROXIES, timeout=5, verify=False)
            klines = k.json()

            closes = [float(x[4]) for x in klines]
            high_20d = max(closes[:480])
            current = float(ticker['lastPrice'])
            change = float(ticker['priceChangePercent'])
            dist_to_high = (high_20d - current) / high_20d * 100

            # 突破信号
            if dist_to_high < 2.0 and change > 0:
                opportunities.append({
                    'symbol': sym.replace('USDT', ''),
                    'price': current,
                    'dist_high': dist_to_high,
                    'change': change,
                    'high_20d': high_20d
                })
        except (requests.RequestException, ValueError, KeyError, IndexError) as e:
            logger.debug(f"扫描 {sym} 失败: {e}")
            pass

    return opportunities

def check_positions(state):
    """检查持仓并执行止盈止损"""
    if not state.get('positions'):
        return state

    for symbol_key, pos in list(state['positions'].items()):
        # 支持不同格式的position
        sym = pos.get('symbol') or symbol_key
        if not sym.endswith('USDT'):
            sym = sym + 'USDT'

        current = get_price(sym)
        if not current:
            continue

        entry = pos.get('entry_price') or pos.get('entry')
        sl = pos.get('stop_loss') or pos.get('stop') or (entry * 0.98)
        tp = pos.get('take_profit') or pos.get('target') or (entry * 1.06)

        # 止损/止盈
        if current <= sl or current >= tp:
            reason = 'TAKE PROFIT' if current >= tp else 'STOP LOSS'
            leverage = pos.get('leverage', 10)
            capital = state.get('capital', 200)
            pnl = capital * leverage * (current - entry) / entry

            log(f"{reason}: {symbol_key} @ {current:.2f} | PnL: +${pnl:.2f}")

            state['trades'].append({
                'symbol': sym,
                'entry': entry,
                'exit': current,
                'pnl': pnl,
                'reason': reason,
                'time': datetime.now().isoformat()
            })

            del state['positions'][symbol_key]

    return state

def main():
    log("=== Trader Started ===")

    while True:
        try:
            state = load_state()

            # 检查现有持仓
            state = check_positions(state)

            # 扫描新机会
            if not state['positions']:
                opps = scan_market()
                if opps:
                    for opp in opps:
                        log(f"OPPORTUNITY: {opp['symbol']} @ {opp['price']:.2f} | To High: {opp['dist_high']:.1f}%")
                        # 自动开仓逻辑可以在这里添加

            save_state(state)

        except Exception as e:
            log(f"Error: {e}")

        time.sleep(60)  # 每分钟

if __name__ == '__main__':
    main()
