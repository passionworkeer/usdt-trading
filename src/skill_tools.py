"""
Skill 工具实现 - OpenClaw 插件接口

提供加密货币交易功能，复用现有的 OrderExecutor、ClaudeProvider 和 MarketDataCollector。
"""
import os
import logging
from typing import Dict, Optional, Any, List
from datetime import datetime

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


# ==================== 全局状态 ====================

class SkillState:
    """Skill 工具的全局状态"""

    def __init__(self):
        self.order_executor: Optional[Any] = None
        self.claude_provider: Optional[Any] = None
        self.data_collector: Optional[Any] = None
        self.is_initialized: bool = False


# 全局状态单例
_state = SkillState()


# ==================== 工具函数 ====================

async def crypto_init(api_key: str, api_secret: str, testnet: bool = True) -> dict:
    """
    初始化交易所连接

    Args:
        api_key: Binance API key
        api_secret: Binance API secret
        testnet: 是否使用测试网 (默认 True)

    Returns:
        初始化结果字典
    """
    try:
        # 设置环境变量供 OrderExecutor 使用
        os.environ['BINANCE_API_KEY'] = api_key
        os.environ['BINANCE_API_SECRET'] = api_secret

        # 延迟导入避免循环依赖
        from src.exchange.order_executor import OrderExecutor

        # 创建 OrderExecutor 实例
        _state.order_executor = OrderExecutor(testnet=testnet)
        _state.is_initialized = True

        # 获取账户信息验证连接
        balance = _state.order_executor.get_balance()
        usdt_balance = balance.get('USDT', {}).get('free', 0)

        logger.info(f"交易所初始化成功: testnet={testnet}, USDT余额=${usdt_balance}")

        return {
            'success': True,
            'message': f"成功连接到 Binance {'测试网' if testnet else '主网'}",
            'testnet': testnet,
            'balance': {
                'USDT': usdt_balance
            }
        }

    except Exception as e:
        logger.error(f"交易所初始化失败: {e}")
        return {
            'success': False,
            'error': str(e),
            'message': f"初始化失败: {str(e)}"
        }


async def crypto_get_price(symbol: str) -> dict:
    """
    获取当前价格

    Args:
        symbol: 交易对 (如 'BTC/USDT')

    Returns:
        价格信息字典
    """
    try:
        if not _state.order_executor:
            return {
                'success': False,
                'error': '交易所未初始化，请先调用 crypto_init',
                'message': '请先初始化交易所连接'
            }

        # 标准化交易对格式
        symbol = _normalize_symbol(symbol)

        ticker = _state.order_executor.get_ticker(symbol)

        return {
            'success': True,
            'symbol': symbol,
            'price': ticker['last'],
            'bid': ticker['bid'],
            'ask': ticker['ask'],
            'volume_24h': ticker.get('volume'),
            'change_24h_pct': ticker.get('percentage'),
            'timestamp': ticker.get('timestamp'),
        }

    except Exception as e:
        logger.error(f"获取价格失败: {e}")
        return {
            'success': False,
            'error': str(e),
            'message': f"获取价格失败: {str(e)}"
        }


async def crypto_get_balance() -> dict:
    """
    获取账户余额

    Returns:
        余额信息字典
    """
    try:
        if not _state.order_executor:
            return {
                'success': False,
                'error': '交易所未初始化，请先调用 crypto_init',
                'message': '请先初始化交易所连接'
            }

        balance = _state.order_executor.get_balance()

        # 提取有余额的资产
        assets = {}
        for asset, info in balance.items():
            if isinstance(info, dict) and info.get('free', 0) > 0:
                assets[asset] = {
                    'free': info.get('free', 0),
                    'used': info.get('used', 0),
                    'total': info.get('total', 0)
                }

        return {
            'success': True,
            'assets': assets,
            'total_usd_value': assets.get('USDT', {}).get('total', 0)
        }

    except Exception as e:
        logger.error(f"获取余额失败: {e}")
        return {
            'success': False,
            'error': str(e),
            'message': f"获取余额失败: {str(e)}"
        }


async def crypto_get_positions(symbol: Optional[str] = None) -> dict:
    """
    获取持仓

    Args:
        symbol: 可选的交易对过滤

    Returns:
        持仓信息字典
    """
    try:
        if not _state.order_executor:
            return {
                'success': False,
                'error': '交易所未初始化，请先调用 crypto_init',
                'message': '请先初始化交易所连接'
            }

        # 获取未成交订单
        open_orders = _state.order_executor.get_open_orders(symbol)

        # 获取余额确定持仓
        balance = _state.order_executor.get_balance()

        # 获取交易对信息
        positions = []
        if symbol:
            symbol = _normalize_symbol(symbol)
            base_asset = symbol.split('/')[0]

            if base_asset in balance and balance[base_asset].get('free', 0) > 0:
                # 获取当前价格
                try:
                    ticker = _state.order_executor.get_ticker(symbol)
                    current_price = ticker['last']
                except:
                    current_price = None

                positions.append({
                    'symbol': symbol,
                    'asset': base_asset,
                    'amount': balance[base_asset]['free'],
                    'value': balance[base_asset]['free'] * current_price if current_price else None,
                    'side': 'long'
                })

        return {
            'success': True,
            'positions': positions,
            'open_orders': [
                {
                    'id': order['id'],
                    'symbol': order['symbol'],
                    'side': order['side'],
                    'amount': order['amount'],
                    'price': order.get('price'),
                    'type': order['type'],
                    'status': order['status']
                }
                for order in open_orders
            ]
        }

    except Exception as e:
        logger.error(f"获取持仓失败: {e}")
        return {
            'success': False,
            'error': str(e),
            'message': f"获取持仓失败: {str(e)}"
        }


async def crypto_buy(
    symbol: str,
    amount: float,
    price: Optional[float] = None,
    stop_loss: Optional[float] = None,
    take_profit: Optional[float] = None,
    amount_usd: Optional[float] = None
) -> dict:
    """
    买入

    Args:
        symbol: 交易对 (如 'BTC/USDT')
        amount: 买入数量 (基准货币)
        price: 限价 (可选，为 None 则市价单)
        stop_loss: 止损价格 (可选)
        take_profit: 止盈价格 (可选)
        amount_usd: USD 金额 (可选，用于市价单自动计算数量)

    Returns:
        订单结果字典
    """
    try:
        if not _state.order_executor:
            return {
                'success': False,
                'error': '交易所未初始化，请先调用 crypto_init',
                'message': '请先初始化交易所连接'
            }

        # 标准化交易对格式
        symbol = _normalize_symbol(symbol)

        # 如果提供了 USD 金额，计算数量
        if amount_usd and not amount:
            ticker = _state.order_executor.get_ticker(symbol)
            amount = amount_usd / ticker['last']

        # 执行订单
        if price:
            # 限价单
            order = _state.order_executor.create_limit_buy_order(symbol, amount, price)
            order_type = 'limit'
        else:
            # 市价单
            order = _state.order_executor.create_market_buy_order(symbol, amount)
            order_type = 'market'

        # 如果提供了止损/止盈，创建 OCO 订单
        if stop_loss and take_profit:
            try:
                # 先取消刚创建的订单，然后用 OCO 订单替代
                _state.order_executor.cancel_order(order['id'], symbol)

                oco_order = _state.order_executor.create_oco_order(
                    symbol=symbol,
                    side='buy',
                    amount=amount,
                    take_profit_price=take_profit,
                    stop_loss_price=stop_loss,
                )

                return {
                    'success': True,
                    'order_id': oco_order.get('id'),
                    'type': 'oco',
                    'side': 'buy',
                    'symbol': symbol,
                    'amount': amount,
                    'stop_loss': stop_loss,
                    'take_profit': take_profit,
                    'message': f'OCO 订单已创建: 买入 {amount} {symbol.split("/")[0]}, 止损 ${stop_loss}, 止盈 ${take_profit}'
                }
            except Exception as e:
                logger.warning(f"创建 OCO 订单失败，使用普通订单: {e}")

        return {
            'success': True,
            'order_id': order['id'],
            'type': order_type,
            'side': 'buy',
            'symbol': symbol,
            'amount': amount,
            'price': price or 'market',
            'message': f"{'限价' if order_type == 'limit' else '市价'}买入订单已创建: {amount} {symbol}"
        }

    except Exception as e:
        logger.error(f"买入失败: {e}")
        return {
            'success': False,
            'error': str(e),
            'message': f"买入失败: {str(e)}"
        }


async def crypto_sell(
    symbol: str,
    amount: float,
    price: Optional[float] = None,
    stop_loss: Optional[float] = None,
    take_profit: Optional[float] = None,
    amount_usd: Optional[float] = None
) -> dict:
    """
    卖出

    Args:
        symbol: 交易对 (如 'BTC/USDT')
        amount: 卖出数量 (基准货币)
        price: 限价 (可选，为 None 则市价单)
        stop_loss: 止损价格 (可选)
        take_profit: 止盈价格 (可选)
        amount_usd: USD 金额 (可选，用于市价单自动计算数量)

    Returns:
        订单结果字典
    """
    try:
        if not _state.order_executor:
            return {
                'success': False,
                'error': '交易所未初始化，请先调用 crypto_init',
                'message': '请先初始化交易所连接'
            }

        # 标准化交易对格式
        symbol = _normalize_symbol(symbol)

        # 如果提供了 USD 金额，计算数量
        if amount_usd and not amount:
            ticker = _state.order_executor.get_ticker(symbol)
            amount = amount_usd / ticker['last']

        # 执行订单
        if price:
            # 限价单
            order = _state.order_executor.create_limit_sell_order(symbol, amount, price)
            order_type = 'limit'
        else:
            # 市价单
            order = _state.order_executor.create_market_sell_order(symbol, amount)
            order_type = 'market'

        # 如果提供了止损/止盈，创建 OCO 订单
        if stop_loss and take_profit:
            try:
                # 先取消刚创建的订单，然后用 OCO 订单替代
                _state.order_executor.cancel_order(order['id'], symbol)

                oco_order = _state.order_executor.create_oco_order(
                    symbol=symbol,
                    side='sell',
                    amount=amount,
                    take_profit_price=take_profit,
                    stop_loss_price=stop_loss,
                )

                return {
                    'success': True,
                    'order_id': oco_order.get('id'),
                    'type': 'oco',
                    'side': 'sell',
                    'symbol': symbol,
                    'amount': amount,
                    'stop_loss': stop_loss,
                    'take_profit': take_profit,
                    'message': f'OCO 订单已创建: 卖出 {amount} {symbol.split("/")[0]}, 止损 ${stop_loss}, 止盈 ${take_profit}'
                }
            except Exception as e:
                logger.warning(f"创建 OCO 订单失败，使用普通订单: {e}")

        return {
            'success': True,
            'order_id': order['id'],
            'type': order_type,
            'side': 'sell',
            'symbol': symbol,
            'amount': amount,
            'price': price or 'market',
            'message': f"{'限价' if order_type == 'limit' else '市价'}卖出订单已创建: {amount} {symbol}"
        }

    except Exception as e:
        logger.error(f"卖出失败: {e}")
        return {
            'success': False,
            'error': str(e),
            'message': f"卖出失败: {str(e)}"
        }


async def crypto_analyze(symbol: str) -> dict:
    """
    AI 市场分析 - 使用新实现的数据收集器

    Args:
        symbol: 交易对 (如 'BTC/USDT')

    Returns:
        分析结果字典
    """
    try:
        # 标准化交易对格式
        symbol = _normalize_symbol(symbol)

        # 初始化 Claude Provider (如果还没有)
        if not _state.claude_provider:
            from src.ai.provider.claude import ClaudeProvider
            _state.claude_provider = ClaudeProvider()

        # 初始化数据收集器 (如果还没有)
        if not _state.data_collector:
            from src.ai.data.collector import MarketDataCollector
            _state.data_collector = MarketDataCollector()

        # 收集市场数据
        logger.info(f"开始收集 {symbol} 的市场数据...")
        context = await _state.data_collector.collect(symbol)

        if not context:
            return {
                'success': False,
                'error': '数据收集失败',
                'message': '无法获取市场数据'
            }

        # 使用 Claude 分析
        logger.info(f"开始 AI 分析 {symbol}...")
        decision = await _state.claude_provider.analyze(context)

        # 提取分析结果
        return {
            'success': True,
            'symbol': symbol,
            'action': decision.action.value,
            'confidence': decision.evidence_count,
            'evidence_chain': decision.evidence_chain,
            'veto_flag': decision.veto_flag,
            'veto_reason': decision.reasoning if decision.veto_flag else None,
            'entry_price': decision.entry_price,
            'stop_loss': decision.stop_loss,
            'take_profit': decision.take_profit,
            'position_size': decision.position_size,
            'reasoning': decision.reasoning,
            'analysis': {
                'timestamp': context.timestamp.isoformat(),
                'current_price': context.klines.get('15m').current_price if '15m' in context.klines else None,
                'intervals': list(context.klines.keys()),
            }
        }

    except Exception as e:
        logger.error(f"AI 分析失败: {e}")
        return {
            'success': False,
            'error': str(e),
            'message': f"AI 分析失败: {str(e)}"
        }


async def crypto_close_position(symbol: str) -> dict:
    """
    平仓

    Args:
        symbol: 交易对 (如 'BTC/USDT')

    Returns:
        平仓结果字典
    """
    try:
        if not _state.order_executor:
            return {
                'success': False,
                'error': '交易所未初始化，请先调用 crypto_init',
                'message': '请先初始化交易所连接'
            }

        # 标准化交易对格式
        symbol = _normalize_symbol(symbol)

        # 获取持仓
        balance = _state.order_executor.get_balance()
        base_asset = symbol.split('/')[0]

        if base_asset not in balance or balance[base_asset].get('free', 0) <= 0:
            return {
                'success': False,
                'error': '无持仓',
                'message': f'{base_asset} 没有持仓'
            }

        amount = balance[base_asset]['free']

        # 获取当前价格
        ticker = _state.order_executor.get_ticker(symbol)
        current_price = ticker['last']

        # 市价卖出平仓
        order = _state.order_executor.create_market_sell_order(symbol, amount)

        # 计算收益
        # 注意：这里简化计算，实际情况需要根据入场价计算
        return {
            'success': True,
            'order_id': order['id'],
            'symbol': symbol,
            'amount': amount,
            'price': current_price,
            'message': f'成功平仓: 卖出 {amount} {base_asset} @ ${current_price}'
        }

    except Exception as e:
        logger.error(f"平仓失败: {e}")
        return {
            'success': False,
            'error': str(e),
            'message': f"平仓失败: {str(e)}"
        }


# ==================== 辅助函数 ====================

def _normalize_symbol(symbol: str) -> str:
    """
    标准化交易对格式

    Args:
        symbol: 交易对字符串

    Returns:
        标准化的交易对格式 (如 'BTC/USDT')
    """
    # 如果已经有斜杠，直接返回
    if '/' in symbol:
        return symbol.upper()

    # 尝试添加 USDT 后缀
    if not symbol.endswith('USDT'):
        symbol = symbol + 'USDT'

    return symbol.upper()


# ==================== 工具注册表 ====================

# 工具函数映射表
SKILL_TOOLS = {
    'crypto_init': crypto_init,
    'crypto_get_price': crypto_get_price,
    'crypto_get_balance': crypto_get_balance,
    'crypto_get_positions': crypto_get_positions,
    'crypto_buy': crypto_buy,
    'crypto_sell': crypto_sell,
    'crypto_analyze': crypto_analyze,
    'crypto_close_position': crypto_close_position,
}


async def execute_skill_tool(tool_name: str, **kwargs) -> dict:
    """
    执行 Skill 工具

    Args:
        tool_name: 工具名称
        **kwargs: 工具参数

    Returns:
        执行结果字典
    """
    tool_func = SKILL_TOOLS.get(tool_name)

    if not tool_func:
        return {
            'success': False,
            'error': f'未知的工具: {tool_name}',
            'message': f'工具 {tool_name} 不存在'
        }

    try:
        result = await tool_func(**kwargs)
        return result
    except Exception as e:
        logger.error(f"执行工具 {tool_name} 失败: {e}")
        return {
            'success': False,
            'error': str(e),
            'message': f"执行失败: {str(e)}"
        }


# ==================== 便捷函数 ====================

def get_state() -> Dict[str, Any]:
    """获取当前状态"""
    return {
        'is_initialized': _state.is_initialized,
        'has_executor': _state.order_executor is not None,
        'has_claude': _state.claude_provider is not None,
        'has_collector': _state.data_collector is not None,
    }


def reset_state():
    """重置状态（用于测试）"""
    global _state
    _state = SkillState()
    logger.info("Skill 工具状态已重置")
