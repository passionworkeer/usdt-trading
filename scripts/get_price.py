import requests
import json

proxies = {'http': 'http://127.0.0.1:7890', 'https': 'http://127.0.0.1:7890'}

# BTC
btc = requests.get('https://api.binance.com/api/v3/ticker/24hr?symbol=BTCUSDT', proxies=proxies, timeout=10).json()
# ETH
eth = requests.get('https://api.binance.com/api/v3/ticker/24hr?symbol=ETHUSDT', proxies=proxies, timeout=10).json()
# SOL
sol = requests.get('https://api.binance.com/api/v3/ticker/24hr?symbol=SOLUSDT', proxies=proxies, timeout=10).json()

print(f"BTC: ${btc['lastPrice']} ({btc['priceChangePercent']}%)")
print(f"ETH: ${eth['lastPrice']} ({eth['priceChangePercent']}%)")
print(f"SOL: ${sol['lastPrice']} ({sol['priceChangePercent']}%)")
