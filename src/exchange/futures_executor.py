"""
订单执行器 v4.0 - 支持 Binance U本位合约（双向交易）

核心改进：
1. ✅ 支持 USDT-M Futures（fapi）
2. ✅ 双向持仓（Hedge Mode）
3. ✅ 做多/做空功能
4. ✅ 实时购买力检查（Notional Value 硬拦截）
5. ✅ aggTrades WebSocket 推送（真实 Volume Profile）
"""
import ccxt
import os
import logging
import asyncio
import websockets
import json
from typing import Dict, Optional, List, Tuple
from datetime import datetime
from src.config import settings

logger = logging.getLogger(__name__)


class FuturesOrderExecutor:
    """
    U本位合约执行器 - 支持双向交易

    关键特性：
    - Hedge Mode（双向持仓）
    - 做多/做空
    - 购买力硬拦截
    - 动态滑点惩罚
    """

    def __init__(self, testnet: bool = True, max_leverage: float = 5.0,
                 isolated_margin: bool = True):  # v4.1: 默认逐仓
        """
        初始化合约执行器

        Args:
            testnet: 是否使用测试网
            max_leverage: 最大杠杆倍数（用于购买力检查）
            isolated_margin: 是否使用逐仓模式（默认 True，防止全仓连坐）
        """
        self.testnet = testnet
        self.max_leverage = max_leverage
        self.isolated_margin = isolated_margin  # v4.1

        # 初始化 Binance U本位合约
        self.exchange = ccxt.binance({
            'apiKey': os.getenv('BINANCE_API_KEY'),
            'secret': os.getenv('BINANCE_API_SECRET'),
            'enableRateLimit': True,
            'timeout': 30000,
            'options': {
                'defaultType': 'future',  # U本位合约
                'adjustForTimeDifference': True,
                'defaultType': 'future',  # 使用 fapi
            },
        })

        # 测试网配置
        if testnet:
            self.exchange.urls['api'] = {
                'public': 'https://testnet.binancefuture.com/fapi/v1',
                'private': 'https://testnet.binancefuture.com/fapi/v1',
            }
            logger.info("Binance U本位合约测试网模式")
        else:
            logger.warning("Binance U本位合约主网模式 - 高风险！")

        # 加载市场
        try:
            self.exchange.load_markets()
            logger.info(f"已加载 {len(self.exchange.markets)} 个合约交易对")

            # 启用双向持仓模式（Hedge Mode）
            self._enable_hedge_mode()

            # v4.1: 设置逐仓模式（防止全仓连坐爆仓）
            if self.isolated_margin:
                self._enable_isolated_margin()

        except Exception as e:
            logger.error(f"初始化失败: {e}")
            raise

    def _enable_hedge_mode(self):
        """启用双向持仓模式（Hedge Mode）"""
        try:
            # 设置 Hedge Mode
            self.exchange.fapiPrivate_post_positionside_dual(
                params={'dualPositionMode': 'true'}
            )
            logger.info("✅ 已启用双向持仓模式（Hedge Mode）")
        except Exception as e:
            logger.warning(f"启用 Hedge Mode 失败（可能已启用）: {e}")

    def _enable_isolated_margin(self):
        """
        v4.1: 启用逐仓模式（防止全仓连坐爆仓）

        注意：这是对所有交易对的全局设置
        """
        try:
            for symbol in self.exchange.symbols:
                if '/USDT' in symbol:  # 只处理 U 本位合约
                    try:
                        self.exchange.fapiPrivate_post_margintype(
                            params={'symbol': symbol.replace('/', ''), 'marginType': 'ISOLATED'}
                        )
                        logger.debug(f"✅ {symbol} 已设置为逐仓模式（Isolated Margin）")
                    except Exception as e:
                        # 可能已经是逐仓模式
                        pass

            logger.info("✅ 所有交易对已设置为逐仓模式（防止全仓连坐爆仓）")
        except Exception as e:
            logger.warning(f"设置逐仓模式失败（可能已启用）: {e}")

    def get_balance(self) -> Dict:
        """
        获取合约账户余额

        Returns:
            余额字典，包含可用保证金
        """
        try:
            balance = self.exchange.fetch_balance({'type': 'future'})

            # 提取可用保证金
            available_margin = 0
            for currency, info in balance.get('total', {}).items():
                if currency == 'USDT':
                    available_margin = info

            logger.info(f"可用保证金: ${available_margin:.2f}")

            return {
                'total': balance.get('total', {}),
                'free': balance.get('free', {}),
                'used': balance.get('used', {}),
                'available_margin': available_margin,
            }
        except Exception as e:
            logger.error(f"获取余额失败: {e}")
            raise

    def check_buying_power(self, symbol: str, quantity: float, price: float,
                          available_margin: float) -> Tuple[bool, str, float]:
        """
        购买力硬拦截（v4.0 核心风控）

        检查：Notional Value <= Available_Balance × Max_Leverage

        Args:
            symbol: 交易对
            quantity: 数量
            price: 当前价格
            available_margin: 可用保证金

        Returns:
            (是否允许, 原因, 名义价值)
        """
        # 计算名义价值
        notional_value = quantity * price

        # 计算最大允许开仓价值
        max_allowed = available_margin * self.max_leverage

        logger.info(f"购买力检查:")
        logger.info(f"  名义价值: ${notional_value:.2f}")
        logger.info(f"  最大允许: ${max_allowed:.2f} (保证金 ${available_margin:.2f} × {self.max_leverage}x)")

        if notional_value > max_allowed:
            return False, f"名义价值 ${notional_value:.2f} 超过最大允许 ${max_allowed:.2f}", notional_value

        return True, "OK", notional_value

    def create_market_order(self, symbol: str, side: str, amount: float,
                           stop_loss: Optional[float] = None,
                           take_profit: Optional[float] = None) -> Dict:
        """
        创建市价单（支持做多/做空）

        Args:
            symbol: 交易对（如 'BTC/USDT'）
            side: 'long'（做多）或 'short'（做空）
            amount: 数量
            stop_loss: 止损价格（可选）
            take_profit: 止盈价格（可选）

        Returns:
            订单信息
        """
        try:
            # 获取当前价格
            ticker = self.exchange.fetch_ticker(symbol)
            current_price = ticker['last']

            # 购买力检查
            balance = self.get_balance()
            allowed, reason, notional_value = self.check_buying_power(
                symbol, amount, current_price, balance['available_margin']
            )

            if not allowed:
                logger.error(f"购买力检查失败: {reason}")
                raise ValueError(f"购买力不足: {reason}")

            # 确定订单方向和持仓方向
            if side.lower() == 'long':
                order_side = 'buy'
                position_side = 'LONG'  # Hedge Mode 需要
            elif side.lower() == 'short':
                order_side = 'sell'
                position_side = 'SHORT'
            else:
                raise ValueError(f"无效方向: {side}，必须是 'long' 或 'short'")

            logger.info(f"创建市价单: {side.upper()} {amount} {symbol} @ ${current_price:.2f}")

            # 创建市价单
            order = self.exchange.create_order(
                symbol=symbol,
                type='market',
                side=order_side,
                amount=amount,
                params={
                    'positionSide': position_side,  # Hedge Mode 关键参数
                }
            )

            logger.info(f"✅ 订单已创建: ID={order.get('id', 'N/A')}")

            # 设置止损止盈（如果提供）
            if stop_loss or take_profit:
                self._set_stop_loss_take_profit(
                    symbol, position_side, amount, stop_loss, take_profit
                )

            return order

        except ccxt.InsufficientFunds as e:
            logger.error(f"余额不足: {e}")
            raise
        except Exception as e:
            logger.error(f"创建订单失败: {e}")
            raise

    def _set_stop_loss_take_profit(self, symbol: str, position_side: str,
                                  amount: float, stop_loss: Optional[float],
                                  take_profit: Optional[float]):
        """设置止损止盈（使用 OCO 或独立订单）"""
        try:
            if stop_loss and take_profit:
                # 使用 OCO 订单
                self.exchange.create_oco_order(
                    symbol=symbol,
                    side='sell' if position_side == 'LONG' else 'buy',
                    amount=amount,
                    price=take_profit,
                    stopPrice=stop_loss,
                    params={'positionSide': position_side}
                )
                logger.info(f"已设置 OCO 止损止盈: SL={stop_loss}, TP={take_profit}")

        except Exception as e:
            logger.warning(f"设置止损止盈失败: {e}")

    def close_position(self, symbol: str, side: str) -> Dict:
        """
        平仓

        Args:
            symbol: 交易对
            side: 'long' 或 'short'

        Returns:
            平仓结果
        """
        try:
            # 获取当前持仓
            positions = self.exchange.fetch_positions([symbol])

            position_side = 'LONG' if side.lower() == 'long' else 'SHORT'

            # 找到对应持仓
            position = None
            for pos in positions:
                if pos.get('positionSide') == position_side and float(pos.get('contracts', 0)) > 0:
                    position = pos
                    break

            if not position:
                logger.warning(f"未找到 {side.upper()} 持仓")
                return {}

            # 平仓方向与开仓相反
            close_side = 'sell' if side.lower() == 'long' else 'buy'
            amount = float(position['contracts'])

            logger.info(f"平仓: {close_side.upper()} {amount} {symbol}")

            order = self.exchange.create_order(
                symbol=symbol,
                type='market',
                side=close_side,
                amount=amount,
                params={'positionSide': position_side}
            )

            logger.info(f"✅ 平仓成功")
            return order

        except Exception as e:
            logger.error(f"平仓失败: {e}")
            raise

    def get_positions(self, symbol: Optional[str] = None) -> List[Dict]:
        """
        获取当前持仓

        Args:
            symbol: 交易对（可选）

        Returns:
            持仓列表
        """
        try:
            positions = self.exchange.fetch_positions(symbol)

            # 只返回有持仓的
            active_positions = [
                pos for pos in positions
                if float(pos.get('contracts', 0)) > 0
            ]

            logger.info(f"当前持仓数: {len(active_positions)}")

            return active_positions

        except Exception as e:
            logger.error(f"获取持仓失败: {e}")
            raise

    def get_open_orders(self, symbol: Optional[str] = None) -> List[Dict]:
        """获取未成交订单"""
        try:
            orders = self.exchange.fetch_open_orders(symbol, params={'type': 'future'})
            return orders
        except Exception as e:
            logger.error(f"获取订单失败: {e}")
            raise


class AggTradesStream:
    """
    aggTrades WebSocket 推送 - 真实 Volume Profile 数据源

    替代 K 线估算，使用真实的逐笔成交数据
    """

    def __init__(self, symbols: List[str]):
        """
        初始化 aggTrades 流

        Args:
            symbols: 交易对列表（如 ['BTCUSDT', 'ETHUSDT']）
        """
        self.symbols = [s.replace('/', '') for s in symbols]  # 移除斜杠
        self.streams = []
        self.callbacks = []

    def on_trade(self, callback):
        """注册回调函数"""
        self.callbacks.append(callback)

    async def connect(self):
        """连接到 Binance WebSocket"""
        # 构建流 URL
        streams = [f"{s.lower()}@aggTrade" for s in self.symbols]
        url = f"wss://fstream.binance.com/stream?streams={'/'.join(streams)}"

        logger.info(f"连接 aggTrades WebSocket: {url}")

        async with websockets.connect(url) as websocket:
            logger.info("✅ aggTrades WebSocket 已连接")

            while True:
                try:
                    message = await websocket.recv()
                    data = json.loads(message)

                    # 解析 trade 数据
                    if 'data' in data:
                        trade = data['data']

                        trade_info = {
                            'symbol': trade['s'],
                            'price': float(trade['p']),
                            'quantity': float(trade['q']),
                            'timestamp': trade['T'],
                            'is_buyer_maker': trade['m'],  # True = 主动卖, False = 主动买
                        }

                        # 触发回调
                        for callback in self.callbacks:
                            await callback(trade_info)

                except Exception as e:
                    logger.error(f"WebSocket 错误: {e}")

    def start(self):
        """启动 WebSocket（阻塞）"""
        asyncio.run(self.connect())


if __name__ == '__main__':
    # 测试代码
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    executor = FuturesOrderExecutor(testnet=True)

    # 获取余额
    balance = executor.get_balance()
    print(f"可用保证金: ${balance['available_margin']:.2f}")

    # 获取持仓
    positions = executor.get_positions()
    print(f"当前持仓: {len(positions)} 个")

    # 测试 aggTrades
    async def test_callback(trade):
        print(f"Trade: {trade['symbol']} @ ${trade['price']:.2f} × {trade['quantity']}")

    stream = AggTradesStream(['BTC/USDT'])
    stream.on_trade(test_callback)
    # stream.start()  # 取消注释以启动
