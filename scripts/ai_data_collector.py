#!/usr/bin/env python3
"""
AI 自主交易系统 v2.0 - 数据采集模式
只负责获取数据，写入报告，等 Claude 来分析
"""
import os
import sys
from pathlib import Path
from datetime import datetime
import json

# 代理设置
from dotenv import load_dotenv
project_root = Path(__file__).parent.parent
dotenv_path = project_root / '.env'
if dotenv_path.exists():
    load_dotenv(dotenv_path)

PROXY = os.environ.get("HTTPS_PROXY") or os.environ.get("HTTP_PROXY")
if PROXY:
    os.environ['HTTP_PROXY'] = PROXY
    os.environ['HTTPS_PROXY'] = PROXY
    print(f"Using proxy: {PROXY}")

import ccxt
import numpy as np

# ============ 配置 ============
SYMBOLS = ['BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'BNB/USDT', 'XRP/USDT']

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

def macd_hist(data, fast=12, slow=26):
    if len(data) < slow: return 0
    ef = ema(data, fast)
    es = ema(data, slow)
    if ef is None or es is None: return 0
    macd_line = [ef[i] - es[i] for i in range(len(ef))]
    # 简化 signal
    return macd_line[-1] - np.mean(macd_line[-9:]) if len(macd_line) >= 9 else 0

# ============ 主程序 ============
def main():
    # 加载持仓
    state_file = Path(__file__).parent.parent / 'state' / 'sniper_state.json'
    existing_pos = None
    if state_file.exists():
        try:
            with open(state_file, 'r', encoding='utf-8') as f:
                state = json.load(f)
            if state.get('positions'):
                pos = state['positions'][0]
                existing_pos = {
                    'symbol': pos['symbol'],
                    'side': pos['side'],
                    'entry_price': pos['entry_price'],
                }
        except: pass

    # 初始化交易所
    ccxt_options = {'enableRateLimit': True, 'options': {'defaultType': 'future'}}
    proxy_clean = ''
    if PROXY:
        proxy_clean = PROXY.replace('http://', '').replace('https://', '')
        ccxt_options['httpsProxy'] = f'http://{proxy_clean}'
        print(f"CCXT using proxy: http://{proxy_clean}")

    exchange = ccxt.binance(ccxt_options)

    # 收集数据
    market_data = {}
    report_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    for symbol in SYMBOLS:
        try:
            # 获取数据
            print(f"Fetching {symbol}...", end=" ")
            ohlcv_1h = exchange.fetch_ohlcv(symbol, '1h', limit=200)
            ohlcv_4h = exchange.fetch_ohlcv(symbol, '4h', limit=300)  # 需要更多数据给 EMA200
            ticker = exchange.fetch_ticker(symbol)
            print("OK")

            if not ohlcv_1h or not ohlcv_4h or not ticker:
                print(f"✗ {symbol}: Missing data")
                continue

            # 解析
            try:
                close_1h = np.array([x[4] for x in ohlcv_1h])
                high_1h = np.array([x[2] for x in ohlcv_1h])
                low_1h = np.array([x[3] for x in ohlcv_1h])
                volume_1h = np.array([x[5] for x in ohlcv_1h])

                close_4h = np.array([x[4] for x in ohlcv_4h])
                volume_4h = np.array([x[5] for x in ohlcv_4h])
            except Exception as e:
                print(f"✗ {symbol}: Parse error: {e}")
                continue

            # 计算指标
            try:
                ema_20_1h = ema(close_1h.tolist(), 20)
                ema_50_1h = ema(close_1h.tolist(), 50)
                ema_20_4h = ema(close_4h.tolist(), 20)
                ema_200_4h = ema(close_4h.tolist(), 200)

                rsi_1h = rsi_func(close_1h.tolist(), 14)
                rsi_4h = rsi_func(close_4h.tolist(), 14)

                vol_ma_1h = np.mean(volume_1h[-20:])
                vol_ratio_1h = volume_1h[-1] / vol_ma_1h if vol_ma_1h else 1

                atr_1h = atr_func(high_1h, low_1h, close_1h, 14)
                volatility = (atr_1h / ticker['last']) * 100 if atr_1h else 0

                macd_1h = macd_hist(close_1h.tolist())

                # 4h 趋势
                trend_4h = "多头" if close_4h[-1] > ema_20_4h[-1] > ema_200_4h[-1] else \
                           "空头" if close_4h[-1] < ema_20_4h[-1] < ema_200_4h[-1] else "震荡"

                market_data[symbol] = {
                    'price': ticker['last'],
                    'change_24h': ticker.get('percentage', 0),
                    'trend_4h': trend_4h,
                    'ema_20_1h': ema_20_1h[-1] if ema_20_1h else None,
                    'ema_50_1h': ema_50_1h[-1] if ema_50_1h else None,
                    'ema_200_4h': ema_200_4h[-1] if ema_200_4h else None,
                    'rsi_1h': round(rsi_1h, 1) if rsi_1h else None,
                    'rsi_4h': round(rsi_4h, 1) if rsi_4h else None,
                    'vol_ratio_1h': round(vol_ratio_1h, 2),
                    'volatility': round(volatility, 2),
                    'macd_1h': round(macd_1h, 2),
                }
                print(f"✓ {symbol}: ${ticker['last']:.2f} | 趋势:{trend_4h} | RSI:{rsi_1h:.0f}/{rsi_4h:.0f}")
            except Exception as e2:
                print(f"✗ {symbol} calc error: {e2}")
                import traceback
                traceback.print_exc()
                continue

        except Exception as e:
            print(f"✗ {symbol}: {e}")

    # 写入报告
    report = {
        'time': report_time,
        'existing_position': existing_pos,
        'market': market_data,
    }

    report_file = Path(__file__).parent.parent / 'ai_memory' / 'market_report.json'
    with open(report_file, 'w', encoding='utf-8') as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    print(f"\n📊 市场报告已写入: {report_file}")

    # 生成 Markdown 格式的报告（方便我阅读）
    md_report = f"""# 📊 市场分析报告 - {report_time}

## 现有持仓
"""
    if existing_pos:
        md_report += f"- **{existing_pos['symbol']}** {existing_pos['side']} @ ${existing_pos['entry_price']:.2f}\n"
    else:
        md_report += "- 无持仓\n"

    md_report += "\n## 市场数据\n\n"
    md_report += "| 币种 | 价格 | 24h涨跌 | 4h趋势 | RSI(1h/4h) | 成交量 | 波动率 |\n"
    md_report += "|:-----|-----:|--------:|:------:|------------:|-------:|-------:|\n"

    for symbol, data in market_data.items():
        md_report += f"| {symbol} | ${data['price']:.2f} | {data['change_24h']:+.2f}% | {data['trend_4h']} | {data['rsi_1h']}/{data['rsi_4h']} | {data['vol_ratio_1h']}x | {data['volatility']}% |\n"

    md_report += f"""

## 关键观察
- BTC 当前在 ${market_data.get('BTC/USDT', {}).get('price', 0):.2f}
- 市场普遍下跌，波动率 {market_data.get('BTC/USDT', {}).get('volatility', 0)}%
- 4h 周期趋势判断请参考上方表格

---
*请 Claude 分析以上数据，给出交易建议*
"""

    md_file = Path(__file__).parent.parent / 'ai_memory' / 'market_report.md'
    with open(md_file, 'w', encoding='utf-8') as f:
        f.write(md_report)

    print(f"📝 Markdown 报告: {md_file}")

if __name__ == '__main__':
    main()
