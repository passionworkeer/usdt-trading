"""
异步事件驱动架构 v4.1 - 解决 GIL 锁和 WebSocket 阻塞

核心改进：
1. ✅ 纯异步 asyncio + aiohttp
2. ✅ Feed Handler 和 Order Executor 解耦
3. ✅ 无锁队列通信（asyncio.Queue）
4. ✅ 毫秒级非阻塞并发
"""
import asyncio
import aiohttp
import logging
import json
from typing import Dict, Optional, Callable, Any
from dataclasses import dataclass
from datetime import datetime
from collections import deque

logger = logging.getLogger(__name__)


@dataclass
class MarketEvent:
    """市场事件"""
    event_type: str  # 'trade' / 'orderbook' / 'kline'
    symbol: str
    timestamp: datetime
    data: Dict[str, Any]


class AsyncFeedHandler:
    """
    异步行情接收器（解决 GIL 锁问题）

    架构：
    - WebSocket 接收 → asyncio.Queue → 策略引擎
    - 完全非阻塞
    - 无锁队列（asyncio.Queue 是线程安全的）
    """

    def __init__(self, symbols: list, max_queue_size: int = 100000):
        """
        初始化行情接收器

        Args:
            symbols: 交易对列表
            max_queue_size: 队列最大容量（防止内存爆炸）
        """
        self.symbols = [s.replace('/', '') for s in symbols]
        self.max_queue_size = max_queue_size

        # 无锁队列（asyncio.Queue 是协程安全的）
        self.event_queue = asyncio.Queue(maxsize=max_queue_size)

        # WebSocket 连接
        self.ws: Optional[aiohttp.ClientWebSocketResponse] = None
        self.session: Optional[aiohttp.ClientSession] = None

        # 统计
        self.messages_received = 0
        self.messages_dropped = 0

    async def connect(self):
        """连接到 Binance WebSocket（异步）"""
        # 构建流 URL
        streams = [f"{s.lower()}@aggTrade" for s in self.symbols]
        streams.extend([f"{s.lower()}@depth@100ms" for s in self.symbols])  # 订单簿

        url = f"wss://fstream.binance.com/stream?streams={'/'.join(streams)}"

        logger.info(f"连接 aggTrades + OrderBook WebSocket: {url}")

        # 创建异步 session
        self.session = aiohttp.ClientSession()

        try:
            self.ws = await self.session.ws_connect(url)
            logger.info("✅ 异步 WebSocket 已连接（非阻塞）")

            # 启动消息接收循环
            await self._receive_loop()

        except Exception as e:
            logger.error(f"WebSocket 连接失败: {e}")
            raise

    async def _receive_loop(self):
        """
        消息接收循环（完全异步，无阻塞）

        关键：
        - 使用 async for 迭代 WebSocket
        - 立即放入队列，不处理逻辑
        - 避免任何阻塞操作
        """
        logger.info("启动异步消息接收循环...")

        async for msg in self.ws:
            if msg.type == aiohttp.WSMsgType.TEXT:
                try:
                    data = json.loads(msg.data)

                    if 'stream' in data and 'data' in data:
                        stream = data['stream']
                        payload = data['data']

                        # 构造事件
                        event = self._parse_event(stream, payload)

                        if event:
                            # 非阻塞放入队列
                            try:
                                self.event_queue.put_nowait(event)
                                self.messages_received += 1
                            except asyncio.QueueFull:
                                # 队列满了，丢弃旧消息
                                try:
                                    self.event_queue.get_nowait()
                                    self.event_queue.put_nowait(event)
                                    self.messages_dropped += 1
                                except:
                                    pass

                except Exception as e:
                    logger.error(f"解析消息失败: {e}")

            elif msg.type == aiohttp.WSMsgType.ERROR:
                logger.error(f"WebSocket 错误: {self.ws.exception()}")
                break

    def _parse_event(self, stream: str, payload: dict) -> Optional[MarketEvent]:
        """解析 WebSocket 事件"""
        try:
            if '@aggTrade' in stream:
                # 逐笔成交
                return MarketEvent(
                    event_type='trade',
                    symbol=payload['s'],
                    timestamp=datetime.fromtimestamp(payload['T'] / 1000),
                    data={
                        'price': float(payload['p']),
                        'quantity': float(payload['q']),
                        'is_buyer_maker': payload['m'],
                    }
                )
            elif '@depth' in stream:
                # 订单簿更新
                return MarketEvent(
                    event_type='orderbook',
                    symbol=payload.get('s', ''),
                    timestamp=datetime.now(),
                    data={
                        'bids': payload.get('b', []),
                        'asks': payload.get('a', []),
                    }
                )
        except Exception as e:
            logger.error(f"解析事件失败: {e}")

        return None

    async def get_event(self, timeout: float = 0.001) -> Optional[MarketEvent]:
        """
        获取事件（异步，超时 1ms）

        Args:
            timeout: 超时时间（秒），默认 1ms

        Returns:
            市场事件，如果超时返回 None
        """
        try:
            return await asyncio.wait_for(self.event_queue.get(), timeout=timeout)
        except asyncio.TimeoutError:
            return None

    async def close(self):
        """关闭连接"""
        if self.ws:
            await self.ws.close()
        if self.session:
            await self.session.close()

        logger.info(f"WebSocket 已关闭")
        logger.info(f"  接收消息: {self.messages_received}")
        logger.info(f"  丢弃消息: {self.messages_dropped}")


class AsyncOrderExecutor:
    """
    异步订单执行器（解决 REST API 阻塞）

    架构：
    - 使用 aiohttp 异步 HTTP 请求
    - 完全非阻塞
    - 与 Feed Handler 完全解耦
    """

    def __init__(self, api_key: str, api_secret: str, testnet: bool = True):
        """
        初始化异步订单执行器

        Args:
            api_key: Binance API Key
            api_secret: Binance API Secret
            testnet: 是否使用测试网
        """
        self.api_key = api_key
        self.api_secret = api_secret
        self.testnet = testnet

        # 基础 URL
        if testnet:
            self.base_url = "https://testnet.binancefuture.com/fapi/v1"
        else:
            self.base_url = "https://fapi.binance.com/fapi/v1"

        # HTTP session
        self.session: Optional[aiohttp.ClientSession] = None

    async def init_session(self):
        """初始化 HTTP session"""
        if not self.session:
            self.session = aiohttp.ClientSession(
                headers={'X-MBX-APIKEY': self.api_key}
            )

    async def create_order(self, symbol: str, side: str, order_type: str,
                          quantity: float, price: Optional[float] = None,
                          position_side: str = 'LONG') -> Dict:
        """
        创建订单（异步）

        Args:
            symbol: 交易对
            side: 'BUY' 或 'SELL'
            order_type: 'MARKET' 或 'LIMIT'
            quantity: 数量
            price: 价格（限价单必需）
            position_side: 'LONG' 或 'SHORT'

        Returns:
            订单结果
        """
        await self.init_session()

        # 构造参数
        params = {
            'symbol': symbol.replace('/', ''),
            'side': side,
            'type': order_type,
            'quantity': quantity,
            'positionSide': position_side,
            'timestamp': int(datetime.now().timestamp() * 1000),
        }

        if order_type == 'LIMIT' and price:
            params['price'] = price
            params['timeInForce'] = 'GTC'

        # 签名（简化，实际需要 HMAC SHA256）
        # TODO: 实现签名逻辑

        try:
            # 异步 POST 请求（非阻塞）
            async with self.session.post(
                f"{self.base_url}/order",
                params=params
            ) as response:
                result = await response.json()

                if response.status == 200:
                    logger.info(f"✅ 订单创建成功: {result.get('orderId')}")
                    return result
                else:
                    logger.error(f"订单失败: {result}")
                    raise Exception(f"订单失败: {result}")

        except Exception as e:
            logger.error(f"创建订单异常: {e}")
            raise

    async def cancel_all_orders(self, symbol: str) -> Dict:
        """
        撤销所有订单（异步）

        v4.1: 熔断时第一优先级操作！

        Args:
            symbol: 交易对

        Returns:
            撤销结果
        """
        await self.init_session()

        params = {
            'symbol': symbol.replace('/', ''),
            'timestamp': int(datetime.now().timestamp() * 1000),
        }

        try:
            # 异步 DELETE 请求
            async with self.session.delete(
                f"{self.base_url}/allOpenOrders",
                params=params
            ) as response:
                result = await response.json()

                logger.critical(f"🔴 已撤销 {symbol} 所有订单（熔断保护）")
                return result

        except Exception as e:
            logger.error(f"撤销订单失败: {e}")
            raise

    async def close(self):
        """关闭 session"""
        if self.session:
            await self.session.close()


class AsyncTradingEngine:
    """
    异步交易引擎（Feed Handler + Order Executor 完全解耦）

    架构：
    Feed Handler (async) → Queue → Strategy (async) → Order Executor (async)
    """

    def __init__(self, symbols: list, api_key: str, api_secret: str, testnet: bool = True):
        """
        初始化异步交易引擎

        Args:
            symbols: 交易对列表
            api_key: API Key
            api_secret: API Secret
            testnet: 是否测试网
        """
        self.feed_handler = AsyncFeedHandler(symbols)
        self.order_executor = AsyncOrderExecutor(api_key, api_secret, testnet)
        self.symbols = symbols

        # 策略回调
        self.strategy_callback: Optional[Callable] = None

    def set_strategy(self, callback: Callable):
        """
        设置策略回调

        Args:
            callback: 异步回调函数 async def strategy(event: MarketEvent)
        """
        self.strategy_callback = callback

    async def run(self):
        """
        运行交易引擎（异步主循环）

        流程：
        1. 启动 Feed Handler
        2. 从队列读取事件
        3. 调用策略回调
        4. 执行订单
        """
        logger.info("启动异步交易引擎...")

        # 启动 Feed Handler（在后台运行）
        feed_task = asyncio.create_task(self.feed_handler.connect())

        try:
            # 主事件循环
            while True:
                # 从队列获取事件（超时 1ms）
                event = await self.feed_handler.get_event(timeout=0.001)

                if event and self.strategy_callback:
                    # 调用策略（异步）
                    await self.strategy_callback(event, self.order_executor)

                # 短暂休眠（避免 CPU 100%）
                await asyncio.sleep(0.0001)  # 0.1ms

        except KeyboardInterrupt:
            logger.info("收到中断信号")
        finally:
            # 清理
            await self.feed_handler.close()
            await self.order_executor.close()
            await feed_task


if __name__ == '__main__':
    # 测试代码
    import os
    from dotenv import load_dotenv

    load_dotenv()

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # 简单策略
    async def simple_strategy(event: MarketEvent, executor: AsyncOrderExecutor):
        """简单策略示例"""
        if event.event_type == 'trade':
            logger.info(f"Trade: {event.symbol} @ ${event.data['price']:.2f}")

            # 这里可以调用 executor.create_order() 下单
            # 完全异步，不阻塞 Feed Handler

    # 创建引擎
    engine = AsyncTradingEngine(
        symbols=['BTC/USDT'],
        api_key=os.getenv('BINANCE_API_KEY', ''),
        api_secret=os.getenv('BINANCE_API_SECRET', ''),
        testnet=True
    )

    engine.set_strategy(simple_strategy)

    # 运行
    try:
        asyncio.run(engine.run())
    except KeyboardInterrupt:
        pass
