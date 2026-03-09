#!/usr/bin/env python3
"""Test free data source with fallback"""
import sys
import os
sys.path.insert(0, 'E:/Desktop/usdt')

os.environ['HTTP_PROXY'] = 'http://127.0.0.1:7890'
os.environ['HTTPS_PROXY'] = 'http://127.0.0.1:7890'

import asyncio
from src.data_sources.free_data import FreeDataSource

# Fallback prices when network fails
FALLBACK = {
    'BTC': 66600,
    'ETH': 1960,
    'SOL': 138,
    'BNB': 620
}

async def main():
    print("=== Crypto Prices ===")
    fds = FreeDataSource()
    
    for sym in ['BTC', 'ETH', 'SOL', 'BNB']:
        try:
            data = await fds.get_price(sym)
            if data and data.price > 0:
                print(f"{sym}: ${data.price:.2f}")
            else:
                print(f"{sym}: ${FALLBACK[sym]} (fallback)")
        except Exception as e:
            print(f"{sym}: ${FALLBACK[sym]} (fallback - error: {type(e).__name__})")
    
    await fds.close()

if __name__ == "__main__":
    asyncio.run(main())
