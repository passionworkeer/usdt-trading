#!/usr/bin/env python3
"""
简化版价格获取 - 直接使用环境变量代理
"""
import os
import sys

# 加载代理配置
from pathlib import Path
from dotenv import load_dotenv

project_root = Path(__file__).parent
dotenv_path = project_root / '.env'
if dotenv_path.exists():
    load_dotenv(dotenv_path)

# 设置代理
PROXY = os.environ.get("HTTPS_PROXY") or os.environ.get("HTTP_PROXY")
if PROXY:
    os.environ['http_proxy'] = PROXY
    os.environ['https_proxy'] = PROXY
    os.environ['HTTP_PROXY'] = PROXY
    os.environ['HTTPS_PROXY'] = PROXY
    print(f"Using proxy: {PROXY}")
else:
    print("No proxy configured!")

import ccxt
b = ccxt.binance({'enableRateLimit': True, 'timeout': 30000})

symbols = ['BTC/USDT', 'ETH/USDT', 'SOL/USDT']
for sym in symbols:
    try:
        ticker = b.fetch_ticker(sym)
        print(f"{sym}: ${ticker['last']} (24h: {ticker['percentage']}%)")
    except Exception as e:
        print(f"{sym}: Error - {e}")
