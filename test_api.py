import ccxt

b = ccxt.binance({'enableRateLimit': True, 'timeout': 30000})
try:
    ticker = b.fetch_ticker('BTC/USDT')
    print(f"BTC price: ${ticker['last']}")
except Exception as e:
    print(f"Error: {e}")
