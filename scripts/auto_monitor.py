#!/usr/bin/env python3
"""
自动交易监控系统
- 每分钟检查持仓
- 达到止盈/止损自动平仓
- 实时推送盈亏状态
"""

import requests
import json
import os
import sys
from datetime import datetime

# 代理配置
PROXIES = {'http': 'http://127.0.0.1:7890', 'https': 'http://127.0.0.1:7890'}

# 配置文件路径
STATE_FILE = 'scripts/paper_trading_state.json'
LOG_FILE = 'scripts/trading_monitor.log'

def log(msg):
    """日志记录"""
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    line = f"[{timestamp}] {msg}"
    print(line)
    with open(LOG_FILE, 'a', encoding='utf-8') as f:
        f.write(line + '\n')

def load_positions():
    """加载持仓"""
    if not os.path.exists(STATE_FILE):
        return {}
    with open(STATE_FILE, 'r') as f:
        state = json.load(f)
    return state.get('positions', {})

def get_price(symbol):
    """获取实时价格"""
    try:
        r = requests.get(
            'https://fapi.binance.com/fapi/v1/ticker/24hr',
            params={'symbol': symbol},
            proxies=PROXIES,
            timeout=5
        )
        return float(r.json()['lastPrice'])
    except Exception as e:
        log(f"获取价格失败: {e}")
        return None

def check_position(pos, symbol):
    """检查持仓状态"""
    entry = pos['entry_price']
    sl = pos.get('stop_loss', entry * 0.96)
    tp = pos.get('take_profit', entry * 1.06)
    leverage = pos.get('leverage', 10)
    capital = pos.get('capital', 200)

    current = get_price(symbol)
    if not current:
        return None

    notional = capital * leverage
    pnl = notional * (current - entry) / entry
    pnl_pct = (current - entry) / entry * 100

    return {
        'current': current,
        'entry': entry,
        'sl': sl,
        'tp': tp,
        'pnl': pnl,
        'pnl_pct': pnl_pct,
        'leverage': leverage
    }

def should_close(status):
    """判断是否需要平仓"""
    current = status['current']
    sl = status['sl']
    tp = status['tp']

    if current <= sl:
        return 'STOP_LOSS', current
    if current >= tp:
        return 'TAKE_PROFIT', current
    return None, current

def update_state(positions):
    """更新状态文件"""
    state = {
        'capital': 200.0,
        'positions': positions,
        'trades': [],
        'daily_losses': {},
        'last_update': datetime.now().isoformat()
    }
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f, indent=2)

def monitor_loop():
    """主监控循环"""
    log("=== 监控系统启动 ===")

    while True:
        try:
            positions = load_positions()

            if not positions:
                log("无持仓，等待信号...")
            else:
                for symbol_key, pos in positions.items():
                    symbol = pos.get('symbol', symbol_key + 'USDT')
                    status = check_position(pos, symbol)

                    if status:
                        action, price = should_close(status)

                        if action:
                            log(f"[{action}] {symbol_key} @ {price:.2f}")
                            log(f"Profit: +{status['pnl']:.2f} ({status['pnl_pct']:.1f}%)")

                            # Close position and record
                            pos['status'] = 'CLOSED'
                            pos['close_price'] = price
                            pos['close_time'] = datetime.now().isoformat()
                            pos['pnl'] = status['pnl']

                            # Clear position
                            del positions[symbol_key]
                            update_state(positions)

                            log(f"Auto closed, profit +{status['pnl']:.2f}")
                        else:
                            log(f"{symbol_key}: {status['current']:.2f} | PnL: +{status['pnl']:.2f} ({status['pnl_pct']:+.1f}%) | SL: {status['sl']:.2f} TP: {status['tp']:.2f}")

            import time
            time.sleep(60)  # 每分钟检查

        except KeyboardInterrupt:
            log("监控停止")
            break
        except Exception as e:
            log(f"错误: {e}")
            import time
            time.sleep(10)

if __name__ == '__main__':
    # 如果带参数运行单次检查
    if len(sys.argv) > 1 and sys.argv[1] == '--once':
        positions = load_positions()
        for symbol_key, pos in positions.items():
            symbol = pos.get('symbol', symbol_key + 'USDT')
            status = check_position(pos, symbol)
            if status:
                action, price = should_close(status)
                if action:
                    print(f"{action} @ {price}")
                else:
                    print(f"{symbol_key}: {status['current']:.2f} PnL: {status['pnl_pct']:+.1f}%")
    else:
        monitor_loop()
