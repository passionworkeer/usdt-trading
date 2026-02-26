# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Sniper Trading System** - A military-grade, ultra-low-frequency, high-confidence cryptocurrency trading system designed for small capital (200 USDT) on Binance Futures.

**Current Version**: v9.0 (MCP AI Trading System with Pluggable Architecture)

## Common Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Run the trading system
python scripts/sniper_trader.py

# Run all tests
pytest

# Run specific test file
pytest tests/test_trading_engine.py -v

# Run tests with coverage
pytest --cov=src --cov-report=html
```

## Architecture

### High-Level Design

The system uses a **dual-track AI architecture**:

1. **Macro Track (Hourly)**: Asynchronous market sentiment analysis via Twitter/News scraper → NLT Translator → Claude Macro Oracle → Memory cache
2. **Micro Track (Trigger Moment)**: MTF triple resonance detection → Trigger price lock → AI micro approval (3-5s) → Slippage hard-lock → Execution

### Core Modules

| Module | Purpose |
|--------|---------|
| `src/orchestrator/trading_engine.py` | Main control loop - dispatches all components |
| `src/ai/provider/` | Pluggable AI engines (Claude, OpenClaw) |
| `src/ai/strategy/` | Signal pool and strategy selector |
| `src/exchange/` | Binance API integration, order execution |
| `src/quantitative/` | MTF resonance lock, screener |
| `src/monitoring/` | Redis state broadcast, monitoring daemon |
| `src/risk/` | Evidence-based risk controller |
| `src/storage/` | Database for trade records |

### Key Data Flow

```
Tick (every 5 min)
    ↓
Signal Pool collects signals
    ↓
AI Strategy Selector (evidence-based decision)
    ↓
Risk Controller validation
    ↓
Exchange Executor (Binance API)
    ↓
Review System (record & analyze)
```

### Trading Flow

```
MTF Triple Resonance Trigger
    ↓
Macro Ban Check (hourly cache)
    ↓
AI Micro Approval (3-5s)
    ↓
Lock Trigger Price
    ↓
Slippage Check (0.5% threshold, 5s timeout)
    ↓
Execute Trade / Abort
```

## Key Configuration

Environment variables (see `.env.example`):
- `BINANCE_API_KEY`, `BINANCE_API_SECRET` - Exchange credentials
- `ANTHROPIC_API_KEY` - Claude API key (v8.0+)
- `DRY_RUN=true` - Enable simulation mode (always start with this)
- `ENABLE_AI_AGENT=true` - Enable AI decision engine

## Testing

- Tests are in `tests/` directory
- Use `pytest` with async support (`asyncio_mode = auto`)
- Key test files: `test_trading_engine.py`, `test_decision_engine.py`, `test_slippage_hardlock.py`

## Recent Changes

- **v9.0**: MCP AI trading system with pluggable AI architecture
- **v8.0**: Dual-track AI agent (macro + micro)
- **v7.3**: Process isolation with Redis Pub/Sub
