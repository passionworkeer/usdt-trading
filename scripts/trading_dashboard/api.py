#!/usr/bin/env python3
"""
MTF v9.0 交易监控面板后端

提供API：
- /api/market/<symbol> - 获取市场数据和信号
- /api/account - 获取账户状态
- /api/signals - 获取当前信号
- /api/trades - 获取交易历史
"""
import asyncio
import os
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
from dataclasses import dataclass

import aiohttp
from aiohttp_socks import ProxyConnector
import pandas as pd
import numpy as np
from fastapi import FastAPI, WebSocket
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
import uvicorn
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ============== 配置 ==============
SYMBOLS = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'BNBUSDT']
POSITION_SIZE = 20  # 每次仓位
CAPITAL = 200.0

# ============== 数据类 ==============
@dataclass
class Trade:
    """交易记录"""
    id: int
    time: str
    symbol: str
    side: str  # LONG / SHORT
    entry: float
    exit: Optional[float]
    pnl: Optional[float]
    status: str  # OPEN / CLOSED

@dataclass
class Position:
    """持仓"""
    symbol: str
    side: str
    entry_price: float
    quantity: float
    unrealized_pnl: float

# ============== 市场分析器 ==============
# ============== 数据目录 ==============
DATA_DIR = Path(__file__).parent / "data"


class MarketAnalyzer:
    """市场分析器"""

    def __init__(self):
        self.connector = None
        self.session = None
        self._cache = {}  # 内存缓存

    async def _get_connector(self):
        if self.connector is None:
            self.connector = ProxyConnector.from_url('http://127.0.0.1:7890')
        return self.connector

    async def _get_session(self):
        if self.session is None:
            connector = await self._get_connector()
            self.session = aiohttp.ClientSession(connector=connector)
        return self.session

    def load_local_data(self, symbol: str, interval: str = '4h') -> list:
        """从本地文件加载K线数据"""
        cache_key = f"{symbol}_{interval}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        file_path = DATA_DIR / f"{symbol}_{interval}.json"
        if file_path.exists():
            with open(file_path, 'r') as f:
                data = json.load(f)
            self._cache[cache_key] = data
            return data
        return None

    async def fetch_klines(self, symbol: str, interval: str = '4h', limit: int = 100) -> pd.DataFrame:
        """获取K线数据 - 优先从本地加载"""
        # 尝试从本地加载
        local_data = self.load_local_data(symbol, interval)
        if local_data:
            # 转换为DataFrame
            df = pd.DataFrame(local_data)
            df.columns = ['t', 'o', 'h', 'l', 'c', 'v']
            df['time'] = pd.to_datetime(df['t'], unit='s')
            for col in ['o', 'h', 'l', 'c', 'v']:
                df[col] = df[col].astype(float)
            return df

        # 本地没有则请求API
        url = "https://fapi.binance.com/fapi/v1/klines"
        session = await self._get_session()
        async with session.get(url, params={'symbol': symbol, 'interval': interval, 'limit': limit},
                              timeout=aiohttp.ClientTimeout(total=30)) as resp:
            data = await resp.json()

        df = pd.DataFrame(data, columns=['t', 'o', 'h', 'l', 'c', 'v', 'ct', 'qv', 'n', 'tbb', 'tbq', 'i'])
        df['time'] = pd.to_datetime(df['t'], unit='ms')
        for col in ['o', 'h', 'l', 'c', 'v']:
            df[col] = df[col].astype(float)
        return df

    def analyze(self, df: pd.DataFrame) -> Dict:
        """分析市场"""
        if len(df) < 50:
            return {'trend': 'unknown', 'signal': 'WAIT'}

        # 均线
        df['ma20'] = df['c'].rolling(20).mean()
        df['ma50'] = df['c'].rolling(50).mean()

        current = df.iloc[-1]
        price = current['c']
        ma20 = df['ma20'].iloc[-1]
        ma50 = df['ma50'].iloc[-1]
        ma20_5ago = df['ma20'].iloc[-5]
        ma50_5ago = df['ma50'].iloc[-5]

        # 趋势判断
        if ma20 > ma50 * 1.01 and ma20 > ma20_5ago:
            trend = 'bull'
        elif ma20 < ma50 * 0.99 and ma20 < ma20_5ago:
            trend = 'bear'
        else:
            trend = 'range'

        # 信号
        if trend == 'bull':
            signal = 'LONG'
            entry = price * 1.02
            stop = price * 0.95
            target = price * 1.10
        elif trend == 'bear':
            signal = 'SHORT'
            entry = ma20 * 1.02
            stop = price * 1.05
            target = price * 0.90
        else:
            signal = 'WAIT'
            entry = price
            stop = price * 0.98
            target = price * 1.02

        # 波动率
        volatility = df['c'].pct_change().rolling(20).std().iloc[-1]

        return {
            'symbol': df.iloc[0]['symbol'] if 'symbol' in df.columns else 'UNKNOWN',
            'price': price,
            'ma20': ma20,
            'ma50': ma50,
            'trend': trend,
            'signal': signal,
            'entry': entry,
            'stop_loss': stop,
            'take_profit': target,
            'volatility': volatility
        }

    async def get_symbol_data(self, symbol: str, interval: str = '4h') -> Dict:
        """获取单个币种数据"""
        df = await self.fetch_klines(symbol, interval=interval)
        analysis = self.analyze(df)

        # 转换为前端格式
        candles = []
        for _, row in df.iterrows():
            candles.append({
                'time': int(row['t']),
                'open': row['o'],
                'high': row['h'],
                'low': row['l'],
                'close': row['c'],
                'volume': row['v']
            })

        # 均线数据
        df['ma20'] = df['c'].rolling(20).mean()
        df['ma50'] = df['c'].rolling(50).mean()

        ma20_line = []
        ma50_line = []
        for i, row in df.iterrows():
            if not pd.isna(row['ma20']):
                ma20_line.append({'time': int(row['t']), 'value': row['ma20']})
            if not pd.isna(row['ma50']):
                ma50_line.append({'time': int(row['t']), 'value': row['ma50']})

        return {
            'candles': candles[-200:],  # 最近200根
            'ma20': ma20_line[-200:],
            'ma50': ma50_line[-200:],
            'analysis': analysis
        }

    async def close(self):
        if self.session:
            await self.session.close()


# ============== 交易管理器 ==============
class TradeManager:
    """交易管理器"""

    def __init__(self, initial_capital: float = 200.0):
        self.capital = initial_capital
        self.positions: Dict[str, Position] = {}
        self.trades: List[Trade] = []
        self.trade_id = 0

    def get_account(self) -> Dict:
        """获取账户状态"""
        total_pnl = sum(t.pnl for t in self.trades if t.pnl is not None)
        open_positions = len(self.positions)

        return {
            'balance': self.capital,
            'total_pnl': total_pnl,
            'total_pnl_pct': (total_pnl / self.capital) * 100,
            'open_positions': open_positions,
            'closed_trades': len([t for t in self.trades if t.status == 'CLOSED'])
        }

    def get_positions(self) -> List[Dict]:
        """获取持仓"""
        return [
            {
                'symbol': p.symbol,
                'side': p.side,
                'entry': p.entry_price,
                'quantity': p.quantity,
                'pnl': p.unrealized_pnl
            }
            for p in self.positions.values()
        ]

    def get_trades(self, limit: int = 20) -> List[Dict]:
        """获取交易历史"""
        return [
            {
                'id': t.id,
                'time': t.time,
                'symbol': t.symbol,
                'side': t.side,
                'entry': t.entry,
                'exit': t.exit,
                'pnl': t.pnl,
                'status': t.status
            }
            for t in self.trades[-limit:]
        ]


# ============== FastAPI 应用 ==============
app = FastAPI(title="MTF Trading Dashboard")

analyzer = MarketAnalyzer()
trade_manager = TradeManager(CAPITAL)


@app.get("/api/market/{symbol}")
async def get_market_data(symbol: str, interval: str = '4h'):
    """获取市场数据"""
    if symbol not in SYMBOLS:
        return {'error': 'Invalid symbol'}

    data = await analyzer.get_symbol_data(symbol, interval=interval)
    return data


@app.get("/api/signals")
async def get_signals():
    """获取所有信号"""
    signals = []
    for symbol in SYMBOLS:
        data = await analyzer.get_symbol_data(symbol)
        signals.append(data['analysis'])
    return signals


@app.get("/api/account")
async def get_account():
    """获取账户状态"""
    return trade_manager.get_account()


@app.get("/api/positions")
async def get_positions():
    """获取持仓"""
    return trade_manager.get_positions()


@app.get("/api/trades")
async def get_trades(limit: int = 20):
    """获取交易历史"""
    return trade_manager.get_trades(limit)


@app.get("/api/backtest")
async def get_backtest():
    """获取回测结果"""
    results_file = Path(__file__).parent.parent / "backtest_results.json"
    if results_file.exists():
        with open(results_file, 'r') as f:
            return json.load(f)
    return []


@app.get("/")
async def get_dashboard():
    """主页"""
    with open(Path(__file__).parent / "templates" / "dashboard.html", "r", encoding="utf-8") as f:
        return HTMLResponse(f.read())


# ============== 启动 ==============
if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent))

    from dotenv import load_dotenv
    load_dotenv()

    print("="*60)
    print("MTF Trading Dashboard")
    print("="*60)
    print("Open http://localhost:8888 in your browser")
    print("="*60)

    uvicorn.run(app, host="0.0.0.0", port=8888)
