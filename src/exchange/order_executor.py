"""
订单执行器 - 基于 CCXT 的 Binance 交易
"""
import ccxt
import os
import logging
from typing import Dict, Optional, List
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


class OrderExecutor:
    """订单执行器 - 支持 Binance 现货交易"""

    def __init__(self, testnet: bool = True):
        """
        初始化订单执行器

        Args:
            testnet: 是否使用测试网
        """
        self.testnet = testnet

        # 初始化 Binance 交易所
        self.exchange = ccxt.binance({
            'apiKey': os.getenv('BINANCE_API_KEY'),
            'secret': os.getenv('BINANCE_API_SECRET'),
            'enableRateLimit': True,  # 自动限流
            'timeout': 30000,  # 30 秒超时
            'options': {
                'defaultType': 'spot',  # 现货交易
                'adjustForTimeDifference': True,  # 自动时间同步
            },
        })

        # 测试网模式
        if testnet:
            self.exchange.set_sandbox_mode(True)
            logger.info("Binance 测试网模式已启用")
        else:
            logger.warning("Binance 主网模式 - 请谨慎操作！")

        # 加载市场数据
        try:
            self.exchange.load_markets()
            logger.info(f"已加载 {len(self.exchange.markets)} 个交易对")
        except Exception as e:
            logger.error(f"加载市场数据失败: {e}")
            raise

    def get_ticker(self, symbol: str) -> Dict:
        """
        获取交易对价格信息

        Args:
            symbol: 交易对，如 'BTC/USDT'

        Returns:
            价格信息字典
        """
        try:
            ticker = self.exchange.fetch_ticker(symbol)
            return {
                'symbol': symbol,
                'last': ticker['last'],
                'bid': ticker['bid'],
                'ask': ticker['ask'],
                'volume': ticker['baseVolume'],
                'change': ticker['change'],
                'percentage': ticker['percentage'],
                'timestamp': ticker['timestamp'],
            }
        except Exception as e:
            logger.error(f"获取 {symbol} 价格失败: {e}")
            raise

    def get_balance(self) -> Dict:
        """
        获取账户余额

        Returns:
            余额字典
        """
        try:
            balance = self.exchange.fetch_balance()
            return balance
        except Exception as e:
            logger.error(f"获取余额失败: {e}")
            raise

    def create_market_buy_order(self, symbol: str, amount: float) -> Dict:
        """
        创建市价买单

        Args:
            symbol: 交易对
            amount: 买入数量

        Returns:
            订单信息
        """
        try:
            logger.info(f"创建市价买单: {symbol} 数量={amount}")
            order = self.exchange.create_market_buy_order(symbol, amount)
            logger.info(f"订单已创建: ID={order['id']}")
            return order
        except ccxt.InsufficientFunds as e:
            logger.error(f"余额不足: {e}")
            raise
        except ccxt.NetworkError as e:
            logger.error(f"网络错误: {e}")
            raise
        except Exception as e:
            logger.error(f"创建买单失败: {e}")
            raise

    def create_market_sell_order(self, symbol: str, amount: float) -> Dict:
        """
        创建市价卖单

        Args:
            symbol: 交易对
            amount: 卖出数量

        Returns:
            订单信息
        """
        try:
            logger.info(f"创建市价卖单: {symbol} 数量={amount}")
            order = self.exchange.create_market_sell_order(symbol, amount)
            logger.info(f"订单已创建: ID={order['id']}")
            return order
        except Exception as e:
            logger.error(f"创建卖单失败: {e}")
            raise

    def create_limit_buy_order(self, symbol: str, amount: float, price: float) -> Dict:
        """
        创建限价买单

        Args:
            symbol: 交易对
            amount: 买入数量
            price: 限价

        Returns:
            订单信息
        """
        try:
            logger.info(f"创建限价买单: {symbol} 数量={amount} 价格={price}")
            order = self.exchange.create_limit_buy_order(symbol, amount, price)
            logger.info(f"订单已创建: ID={order['id']}")
            return order
        except Exception as e:
            logger.error(f"创建限价买单失败: {e}")
            raise

    def create_limit_sell_order(self, symbol: str, amount: float, price: float) -> Dict:
        """
        创建限价卖单

        Args:
            symbol: 交易对
            amount: 卖出数量
            price: 限价

        Returns:
            订单信息
        """
        try:
            logger.info(f"创建限价卖单: {symbol} 数量={amount} 价格={price}")
            order = self.exchange.create_limit_sell_order(symbol, amount, price)
            logger.info(f"订单已创建: ID={order['id']}")
            return order
        except Exception as e:
            logger.error(f"创建限价卖单失败: {e}")
            raise

    def create_oco_order(self, symbol: str, side: str, amount: float,
                        take_profit_price: float, stop_loss_price: float,
                        stop_loss_limit_price: Optional[float] = None) -> Dict:
        """
        创建 OCO 订单（One-Cancels-Other：止盈止损二选一）

        Args:
            symbol: 交易对
            side: 'buy' or 'sell'
            amount: 数量
            take_profit_price: 止盈价格
            stop_loss_price: 止损触发价格
            stop_loss_limit_price: 止损限价（可选）

        Returns:
            订单信息
        """
        try:
            logger.info(f"创建 OCO 订单: {symbol} {side} 数量={amount}")
            logger.info(f"  止盈: {take_profit_price}")
            logger.info(f"  止损触发: {stop_loss_price}")

            order = self.exchange.create_oco_order(
                symbol=symbol,
                side=side,
                amount=amount,
                price=take_profit_price,  # 限单价（止盈）
                stopPrice=stop_loss_price,  # 止损触发价
                stopLimitPrice=stop_loss_limit_price or stop_loss_price * 0.99,  # 止损限价
            )

            logger.info(f"OCO 订单已创建: ID={order.get('id', 'N/A')}")
            return order

        except Exception as e:
            logger.error(f"创建 OCO 订单失败: {e}")
            raise

    def cancel_order(self, order_id: str, symbol: str) -> Dict:
        """
        取消订单

        Args:
            order_id: 订单 ID
            symbol: 交易对

        Returns:
            取消结果
        """
        try:
            logger.info(f"取消订单: {order_id} ({symbol})")
            result = self.exchange.cancel_order(order_id, symbol)
            logger.info(f"订单已取消")
            return result
        except Exception as e:
            logger.error(f"取消订单失败: {e}")
            raise

    def cancel_all_orders(self, symbol: Optional[str] = None) -> List[Dict]:
        """
        取消所有订单

        Args:
            symbol: 交易对（可选，不指定则取消所有）

        Returns:
            取消结果列表
        """
        try:
            logger.info(f"取消所有订单" + (f" ({symbol})" if symbol else ""))
            result = self.exchange.cancel_all_orders(symbol)
            logger.info(f"已取消 {len(result)} 个订单")
            return result
        except Exception as e:
            logger.error(f"取消订单失败: {e}")
            raise

    def get_open_orders(self, symbol: Optional[str] = None) -> List[Dict]:
        """
        获取未成交订单

        Args:
            symbol: 交易对（可选）

        Returns:
            订单列表
        """
        try:
            orders = self.exchange.fetch_open_orders(symbol)
            logger.info(f"未成交订单数: {len(orders)}")
            return orders
        except Exception as e:
            logger.error(f"获取订单失败: {e}")
            raise

    def get_order(self, order_id: str, symbol: str) -> Dict:
        """
        查询订单状态

        Args:
            order_id: 订单 ID
            symbol: 交易对

        Returns:
            订单信息
        """
        try:
            order = self.exchange.fetch_order(order_id, symbol)
            return order
        except Exception as e:
            logger.error(f"查询订单失败: {e}")
            raise

    def get_markets(self) -> Dict:
        """
        获取所有交易对信息

        Returns:
            交易对字典
        """
        return self.exchange.markets

    def check_symbol_exists(self, symbol: str) -> bool:
        """
        检查交易对是否存在

        Args:
            symbol: 交易对

        Returns:
            是否存在
        """
        return symbol in self.exchange.markets

    def get_trade_fee(self, symbol: str, amount: float, price: float,
                     side: str = 'buy') -> Dict:
        """
        计算交易手续费

        Args:
            symbol: 交易对
            amount: 数量
            price: 价格
            side: 买卖方向

        Returns:
            手续费信息
        """
        try:
            fee = self.exchange.calculate_fee(symbol, 'market', side, amount, price, {})
            return fee
        except Exception as e:
            logger.warning(f"计算手续费失败: {e}")
            # 返回默认费率 0.1%
            return {
                'rate': 0.001,
                'cost': amount * price * 0.001,
                'currency': symbol.split('/')[1]
            }


if __name__ == '__main__':
    # 测试代码
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    executor = OrderExecutor(testnet=True)

    # 获取价格
    ticker = executor.get_ticker('BTC/USDT')
    print(f"BTC/USDT 价格: {ticker['last']}")

    # 获取余额
    balance = executor.get_balance()
    print(f"USDT 余额: {balance.get('USDT', {}).get('free', 0)}")
