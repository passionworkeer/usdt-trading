# Crypto Trading Strategy

## Network Configuration

**Important**: Always use proxy for API calls
```python
proxies = {'http': 'http://127.0.0.1:7890', 'https': 'http://127.0.0.1:7890'}
requests.get(url, proxies=proxies, verify=False, timeout=10)
```

## Core Strategy: Breakout Trading

### Entry Conditions

1. **Strong Coin Screening**: Find coins that resist market downturn
   - Market down 2-4%, target coin only down <1%
   - Shows institutional buying

2. **Breakout Signal**:
   - Price within 1-2% of 20-day high
   - Ready to break through

3. **Position Setup**:
   - Entry: Just below resistance (wait for breakout)
   - Leverage: 20x (for 200U capital)
   - Stop Loss: 2-3% below entry (below recent low)
   - Take Profit: 5-10% above entry

### Risk Management

1. **Initial Stop**: Below entry price
2. **Trail Stop**: Once in profit, move SL to entry (break-even)
3. **Partial Close**: Close 50% when trend weakens
4. **Final Stop**: Let remaining position run to target

### Profit Calculation

```python
# Position: 200U × 20x leverage = 4000U notional
# Quantity = 4000 / entry_price
# Profit = notional × (current - entry) / entry
```

## Example: BNB Trade

- Entry: $625 (20-day high $630, distance 1.3%)
- Market: Down 2-4%, BNB only down 0.84%
- Leverage: 20x, Position: 6.4 BNB
- Initial SL: $615 (-1.6%)
- TP: $680 (+8.8%)

**Result**:
- High: $650 (+80% ROI)
- Partial close at $633: Locked +$27
- Remaining: Break-even at $625

## Execution Script

Check price and profit:
```python
import requests
import urllib3
urllib3.disable_warnings()

proxies = {'http': 'http://127.0.0.1:7890', 'https': 'http://127.0.0.1:7890'}
r = requests.get('https://fapi.binance.com/fapi/v1/ticker/24hr',
                 params={'symbol': 'BNBUSDT'},
                 proxies=proxies, verify=False, timeout=10)
current = float(r.json()['lastPrice'])
```

## State File

`scripts/paper_trading_state.json`:
```json
{
  "capital": 200.0,
  "positions": {
    "BNB": {
      "entry_price": 625.0,
      "quantity": 3.2,
      "leverage": 20,
      "stop_loss": 625.0,
      "take_profit": 680.0,
      "status": "OPEN"
    }
  }
}
```
