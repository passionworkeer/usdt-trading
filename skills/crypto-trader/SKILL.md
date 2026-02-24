# Crypto Trader Skill

AI-powered cryptocurrency trading skill for OpenClaw with Binance integration.

## Features

- 🔄 **Real-time Price Monitoring** - WebSocket-based price updates
- 🤖 **AI-Driven Decisions** - Claude API for intelligent trading decisions
- 📊 **Technical Analysis** - RSI, MACD, and more indicators
- 🛡️ **Advanced Risk Management** - Stop-loss, take-profit, position limits
- 📈 **Confluence Analysis** - Multi-source signal scoring
- 💬 **Natural Language Commands** - Trade via chat commands

## Quick Start

### 1. Initialize Exchange

```
Initialize Binance connection with my API credentials
```

### 2. Check Market

```
What's the current price of BTC/USDT?
Show me the market analysis for ETH/USDT
```

### 3. Execute Trades

```
Buy $100 worth of BTC at market price
Sell 0.5 ETH when price hits $3000
```

### 4. Manage Positions

```
Show my open positions
Set stop loss for BTC at $45000
Close all positions
```

### 5. AI Analysis

```
Analyze BTC/USDT and suggest a trading strategy
Should I buy ETH now?
What's the market sentiment?
```

## Available Tools

| Tool | Description |
|------|-------------|
| `crypto_init` | Initialize exchange connection |
| `crypto_get_price` | Get current price for a symbol |
| `crypto_get_balance` | Get account balance |
| `crypto_get_positions` | Get open positions |
| `crypto_buy` | Execute a buy order |
| `crypto_sell` | Execute a sell order |
| `crypto_set_stop_loss` | Set stop-loss for a position |
| `crypto_set_take_profit` | Set take-profit for a position |
| `crypto_close_position` | Close a position |
| `crypto_analyze` | AI-powered market analysis |
| `crypto_get_sentiment` | Get market sentiment |
| `crypto_start_monitor` | Start real-time monitoring |
| `crypto_stop_monitor` | Stop monitoring |

## Risk Management

The skill includes comprehensive risk controls:

- **Position Limits**: Maximum position size in USD
- **Daily Loss Limits**: Automatic trading halt on excessive losses
- **Concurrent Positions**: Limit number of open positions
- **Stop-Loss/Take-Profit**: Automatic risk management per trade

## Safety First

⚠️ **Important Safety Guidelines**:

1. **Test First**: Always test on Binance testnet
2. **IP Whitelist**: Enable IP whitelist on your API keys
3. **No Withdrawal**: Never enable withdrawal permissions
4. **Start Small**: Begin with small amounts
5. **Monitor**: Always monitor your positions

## Configuration

Set these environment variables:

```bash
BINANCE_API_KEY=your_key
BINANCE_API_SECRET=your_secret
BINANCE_TESTNET=true  # Use testnet for safety
ANTHROPIC_API_KEY=your_claude_key  # Optional, for AI features
```

## Examples

### Example 1: Simple Buy

```
Buy $500 of BTC at market price with 5% stop loss and 15% take profit
```

### Example 2: AI Analysis

```
Analyze the current market conditions for ETH/USDT and suggest whether I should buy, sell, or hold
```

### Example 3: Position Management

```
Show all my open positions and their current P&L
```

### Example 4: Automated Trading

```
Start monitoring BTC/USDT and automatically execute trades based on your AI analysis with a maximum position of $1000
```

## Support

For issues or questions, check the logs in `logs/crypto-trader.log`.
