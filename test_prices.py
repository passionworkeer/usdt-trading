#!/usr/bin/env python3
"""快速价格获取"""
import os
os.environ['http_proxy'] = 'http://127.0.0.1:7890'
os.environ['https_proxy'] = 'http://127.0.0.1:7890'

import requests
import time

symbols = ['BTC', 'ETH', 'SOL', 'BNB']
for s in symbols:
    time.sleep(0.5)
    try:
        r = requests.get(f'https://api.binance.com/api/v3/ticker/price?symbol={s}USDT', timeout=20)
        print(f"{s}: ${r.json()['price']}")
    except Exception as e:
        print(f"{s}: Error - {e}")
