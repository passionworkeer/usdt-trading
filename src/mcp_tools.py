"""
MCP 工具定义 - OpenClaw 接口
"""
import json
from typing import Dict, List, Optional, Any
from dataclasses import dataclass


@dataclass
class MCPTool:
    """MCP 工具定义"""
    name: str
    description: str
    input_schema: Dict[str, Any]

    def to_dict(self) -> Dict:
        return {
            'name': self.name,
            'description': self.description,
            'inputSchema': self.input_schema,
        }


# 定义所有 MCP 工具
MCP_TOOLS = [
    # 交易所管理
    MCPTool(
        name='crypto_init',
        description='Initialize connection to Binance exchange with API credentials',
        input_schema={
            'type': 'object',
            'properties': {
                'apiKey': {
                    'type': 'string',
                    'description': 'Binance API key',
                },
                'apiSecret': {
                    'type': 'string',
                    'description': 'Binance API secret',
                },
                'testnet': {
                    'type': 'boolean',
                    'description': 'Use testnet (recommended for testing)',
                    'default': True,
                },
            },
            'required': ['apiKey', 'apiSecret'],
        },
    ),

    # 市场数据
    MCPTool(
        name='crypto_get_price',
        description='Get current price for a trading pair',
        input_schema={
            'type': 'object',
            'properties': {
                'symbol': {
                    'type': 'string',
                    'description': 'Trading pair (e.g., BTC/USDT)',
                },
            },
            'required': ['symbol'],
        },
    ),

    MCPTool(
        name='crypto_get_klines',
        description='Get candlestick/kline data for technical analysis',
        input_schema={
            'type': 'object',
            'properties': {
                'symbol': {
                    'type': 'string',
                    'description': 'Trading pair',
                },
                'interval': {
                    'type': 'string',
                    'description': 'Kline interval (1m, 5m, 15m, 1h, 4h, 1d)',
                    'default': '1h',
                },
                'limit': {
                    'type': 'number',
                    'description': 'Number of candles',
                    'default': 100,
                },
            },
            'required': ['symbol'],
        },
    ),

    # 账户管理
    MCPTool(
        name='crypto_get_balance',
        description='Get account balance for all assets',
        input_schema={
            'type': 'object',
            'properties': {},
        },
    ),

    MCPTool(
        name='crypto_get_positions',
        description='Get all open positions and orders',
        input_schema={
            'type': 'object',
            'properties': {
                'symbol': {
                    'type': 'string',
                    'description': 'Filter by symbol (optional)',
                },
            },
        },
    ),

    # 交易执行
    MCPTool(
        name='crypto_buy',
        description='Execute a buy order (market or limit)',
        input_schema={
            'type': 'object',
            'properties': {
                'symbol': {
                    'type': 'string',
                    'description': 'Trading pair to buy',
                },
                'amount': {
                    'type': 'number',
                    'description': 'Amount to buy (in base currency)',
                },
                'amountUsd': {
                    'type': 'number',
                    'description': 'Amount to buy in USD (alternative to amount)',
                },
                'price': {
                    'type': 'number',
                    'description': 'Limit price (if omitted, market order)',
                },
                'stopLoss': {
                    'type': 'number',
                    'description': 'Stop loss percentage (e.g., -5 for 5% stop loss)',
                },
                'takeProfit': {
                    'type': 'number',
                    'description': 'Take profit percentage (e.g., 15 for 15% profit)',
                },
            },
            'required': ['symbol'],
        },
    ),

    MCPTool(
        name='crypto_sell',
        description='Execute a sell order (market or limit)',
        input_schema={
            'type': 'object',
            'properties': {
                'symbol': {
                    'type': 'string',
                    'description': 'Trading pair to sell',
                },
                'amount': {
                    'type': 'number',
                    'description': 'Amount to sell (in base currency)',
                },
                'amountUsd': {
                    'type': 'number',
                    'description': 'Amount to sell in USD',
                },
                'price': {
                    'type': 'number',
                    'description': 'Limit price (if omitted, market order)',
                },
            },
            'required': ['symbol'],
        },
    ),

    MCPTool(
        name='crypto_cancel_order',
        description='Cancel an open order',
        input_schema={
            'type': 'object',
            'properties': {
                'orderId': {
                    'type': 'string',
                    'description': 'Order ID to cancel',
                },
                'symbol': {
                    'type': 'string',
                    'description': 'Trading pair',
                },
            },
            'required': ['orderId', 'symbol'],
        },
    ),

    # 风险管理
    MCPTool(
        name='crypto_set_stop_loss',
        description='Set or update stop loss for a position',
        input_schema={
            'type': 'object',
            'properties': {
                'symbol': {
                    'type': 'string',
                    'description': 'Trading pair',
                },
                'percentage': {
                    'type': 'number',
                    'description': 'Stop loss percentage (e.g., -5)',
                },
                'price': {
                    'type': 'number',
                    'description': 'Stop loss price (alternative to percentage)',
                },
            },
            'required': ['symbol'],
        },
    ),

    MCPTool(
        name='crypto_set_take_profit',
        description='Set or update take profit for a position',
        input_schema={
            'type': 'object',
            'properties': {
                'symbol': {
                    'type': 'string',
                    'description': 'Trading pair',
                },
                'percentage': {
                    'type': 'number',
                    'description': 'Take profit percentage (e.g., 15)',
                },
                'price': {
                    'type': 'number',
                    'description': 'Take profit price',
                },
            },
            'required': ['symbol'],
        },
    ),

    MCPTool(
        name='crypto_close_position',
        description='Close an open position immediately',
        input_schema={
            'type': 'object',
            'properties': {
                'symbol': {
                    'type': 'string',
                    'description': 'Trading pair to close',
                },
            },
            'required': ['symbol'],
        },
    ),

    MCPTool(
        name='crypto_close_all',
        description='Close all open positions',
        input_schema={
            'type': 'object',
            'properties': {},
        },
    ),

    # AI 分析
    MCPTool(
        name='crypto_analyze',
        description='AI-powered market analysis using Claude. Analyzes technical indicators, patterns, and provides trading recommendations.',
        input_schema={
            'type': 'object',
            'properties': {
                'symbol': {
                    'type': 'string',
                    'description': 'Trading pair to analyze',
                },
                'timeframe': {
                    'type': 'string',
                    'description': 'Analysis timeframe (short, medium, long)',
                    'default': 'medium',
                },
                'includeIndicators': {
                    'type': 'array',
                    'items': {'type': 'string'},
                    'description': 'Technical indicators to include (RSI, MACD, BB, etc.)',
                },
            },
            'required': ['symbol'],
        },
    ),

    MCPTool(
        name='crypto_get_sentiment',
        description='Get market sentiment analysis from multiple sources',
        input_schema={
            'type': 'object',
            'properties': {
                'symbol': {
                    'type': 'string',
                    'description': 'Trading pair (optional, gets overall market if omitted)',
                },
            },
        },
    ),

    MCPTool(
        name='crypto_should_trade',
        description='Ask AI whether to buy, sell, or hold based on current market conditions',
        input_schema={
            'type': 'object',
            'properties': {
                'symbol': {
                    'type': 'string',
                    'description': 'Trading pair to analyze',
                },
                'action': {
                    'type': 'string',
                    'enum': ['buy', 'sell', 'hold'],
                    'description': 'Intended action',
                },
                'amount': {
                    'type': 'number',
                    'description': 'Intended trade amount in USD',
                },
            },
            'required': ['symbol', 'action'],
        },
    ),

    # 监控
    MCPTool(
        name='crypto_start_monitor',
        description='Start real-time price monitoring for one or more symbols',
        input_schema={
            'type': 'object',
            'properties': {
                'symbols': {
                    'type': 'array',
                    'items': {'type': 'string'},
                    'description': 'Trading pairs to monitor',
                },
                'interval': {
                    'type': 'number',
                    'description': 'Check interval in seconds',
                    'default': 300,
                },
                'autoTrade': {
                    'type': 'boolean',
                    'description': 'Enable AI-driven automatic trading',
                    'default': false,
                },
            },
            'required': ['symbols'],
        },
    ),

    MCPTool(
        name='crypto_stop_monitor',
        description='Stop real-time monitoring',
        input_schema={
            'type': 'object',
            'properties': {},
        },
    ),

    MCPTool(
        name='crypto_get_status',
        description='Get current trading status: positions, P&L, monitoring status',
        input_schema={
            'type': 'object',
            'properties': {},
        },
    ),

    # 配置
    MCPTool(
        name='crypto_set_config',
        description='Update risk management configuration',
        input_schema={
            'type': 'object',
            'properties': {
                'maxPositionSize': {
                    'type': 'number',
                    'description': 'Maximum position size in USD',
                },
                'maxDailyLoss': {
                    'type': 'number',
                    'description': 'Maximum daily loss in USD',
                },
                'maxOpenPositions': {
                    'type': 'number',
                    'description': 'Maximum concurrent positions',
                },
                'defaultStopLoss': {
                    'type': 'number',
                    'description': 'Default stop loss percentage',
                },
                'defaultTakeProfit': {
                    'type': 'number',
                    'description': 'Default take profit percentage',
                },
            },
        },
    ),
]


def get_tool_definitions() -> List[Dict]:
    """获取所有工具定义"""
    return [tool.to_dict() for tool in MCP_TOOLS]


def get_tool_by_name(name: str) -> Optional[MCPTool]:
    """根据名称获取工具"""
    for tool in MCP_TOOLS:
        if tool.name == name:
            return tool
    return None


if __name__ == '__main__':
    # 输出所有工具定义
    print(json.dumps(get_tool_definitions(), indent=2))
