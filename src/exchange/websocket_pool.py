"""
v6.0 WebSocket 连接池 - 自动重连 + 心跳检测

解决币安 WebSocket 24小时强制断线问题
"""
import asyncio
import json
import logging
import time
from typing import Callable, Optional, Dict, Any, Set
from datetime import datetime

import websockets
from websockets.exceptions import ConnectionClosed, ConnectionClosedError

logger = logging.getLogger(__name__)


class BinanceWebSocketClient:
    """
    币安 WebSocket 客户端（带自动重连）

    功能：
    1. 自动重连（指数退避）
    2. 心跳检测（3秒超时）
    3. 订阅管理
    4. 数据回调
    """

    # WebSocket 端点
    BASE_URL = "wss://fstream.binance.com/ws"
    TESTNET_URL = "wss://stream.binancefuture.com/ws"

    def __init__(
        self,
        testnet: bool = False,
        on_message: Optional[Callable[[Dict], None]] = None,
        on_error: Optional[Callable[[Exception], None]] = None,
        ping_interval: float = 30.0,  # 币安要求每30秒发送一次 ping
        ping_timeout: float = 10.0,   # ping 超时时间
        max_reconnect_delay: float = 60.0,  # 最大重连延迟
    ):
        self.testnet = testnet
        self.on_message = on_message
        self.on_error = on_error

        self.ping_interval = ping_interval
        self.ping_timeout = ping_timeout
        self.max_reconnect_delay = max_reconnect_delay

        # WebSocket 连接
        self.ws: Optional[websockets.WebSocketClientProtocol] = None
        self.url = self.TESTNET_URL if testnet else self.BASE_URL

        # 订阅管理
        self.subscriptions: Set[str] = set()

        # 运行状态
        self.running = False
        self.reconnecting = False

        # 心跳检测
        self.last_ping_time = 0.0
        self.last_pong_time = 0.0
        self.heartbeat_task: Optional[asyncio.Task] = None

        # 统计信息
        self.connect_count = 0
        self.reconnect_count = 0
        self.message_count = 0
        self.error_count = 0

        logger.info(f"WebSocket 客户端初始化: {self.url}")

    async def connect(self) -> bool:
        """
        建立 WebSocket 连接

        Returns:
            是否连接成功
        """
        try:
            logger.info("🔌 WebSocket 连接中...")

            # 建立 WebSocket 连接
            self.ws = await websockets.connect(
                self.url,
                ping_interval=self.ping_interval,
                ping_timeout=self.ping_timeout,
                close_timeout=10.0,
            )

            self.connect_count += 1
            logger.info(f"✅ WebSocket 连接成功 (#{self.connect_count})")

            # 恢复之前的订阅
            if self.subscriptions:
                await self._resubscribe()

            # 启动心跳检测
            self.heartbeat_task = asyncio.create_task(self._heartbeat_monitor())

            return True

        except Exception as e:
            logger.error(f"❌ WebSocket 连接失败: {e}")
            self.error_count += 1

            if self.on_error:
                self.on_error(e)

            return False

    async def disconnect(self) -> None:
        """断开 WebSocket 连接"""
        self.running = False

        if self.heartbeat_task:
            self.heartbeat_task.cancel()
            try:
                await self.heartbeat_task
            except asyncio.CancelledError:
                pass

        if self.ws:
            await self.ws.close()
            logger.info("🔌 WebSocket 已断开")

    async def subscribe(self, stream: str) -> None:
        """
        订阅数据流

        Args:
            stream: 数据流名称（如 "btcusdt@aggTrade"）
        """
        if stream in self.subscriptions:
            logger.debug(f"已订阅 {stream}，跳过")
            return

        self.subscriptions.add(stream)

        # 构造订阅消息
        message = {
            "method": "SUBSCRIBE",
            "params": [stream],
            "id": len(self.subscriptions)
        }

        await self._send(message)
        logger.info(f"📡 订阅: {stream}")

    async def unsubscribe(self, stream: str) -> None:
        """
        取消订阅

        Args:
            stream: 数据流名称
        """
        if stream not in self.subscriptions:
            return

        self.subscriptions.remove(stream)

        message = {
            "method": "UNSUBSCRIBE",
            "params": [stream],
            "id": len(self.subscriptions)
        }

        await self._send(message)
        logger.info(f"📡 取消订阅: {stream}")

    async def _resubscribe(self) -> None:
        """重连后恢复所有订阅"""
        logger.info(f"📡 恢复 {len(self.subscriptions)} 个订阅...")

        for stream in self.subscriptions:
            message = {
                "method": "SUBSCRIBE",
                "params": [stream],
                "id": len(self.subscriptions)
            }
            await self._send(message)

        logger.info(f"✅ 订阅已恢复")

    async def _send(self, message: Dict) -> None:
        """
        发送消息到 WebSocket

        Args:
            message: 消息字典
        """
        if not self.ws:
            logger.warning("WebSocket 未连接，无法发送消息")
            return

        try:
            await self.ws.send(json.dumps(message))
        except Exception as e:
            logger.error(f"发送消息失败: {e}")
            raise

    async def _heartbeat_monitor(self) -> None:
        """
        心跳检测任务

        检查：
        1. 最后一次 pong 时间（如果超过 3 秒，判定为断线）
        2. WebSocket 连接状态
        """
        try:
            while self.running:
                await asyncio.sleep(1.0)

                # 检查 pong 超时（3秒）
                if self.last_pong_time > 0:
                    elapsed = time.time() - self.last_pong_time
                    if elapsed > 3.0:
                        logger.warning(f"⚠️ 心跳超时: {elapsed:.1f} 秒无响应")
                        # 触发重连
                        await self._reconnect()
                        return

                # 检查 WebSocket 连接
                if self.ws and self.ws.closed:
                    logger.warning("⚠️ WebSocket 连接已关闭")
                    await self._reconnect()
                    return

        except asyncio.CancelledError:
            logger.debug("心跳检测任务已取消")
        except Exception as e:
            logger.error(f"❌ 心跳检测异常: {e}")

    async def _reconnect(self) -> None:
        """
        自动重连（指数退避）

        退避公式: delay = min(max_delay, base_delay * 2 ** attempt)
        """
        if self.reconnecting:
            logger.debug("已在重连中，跳过")
            return

        self.reconnecting = True
        self.reconnect_count += 1

        attempt = 0
        base_delay = 1.0

        while attempt < 10:  # 最多尝试 10 次
            delay = min(self.max_reconnect_delay, base_delay * (2 ** attempt))

            logger.warning(f"🔄 重连中... (尝试 {attempt + 1}/10, {delay:.1f} 秒后)")

            await asyncio.sleep(delay)

            # 断开旧连接
            try:
                if self.ws:
                    await self.ws.close()
            except Exception:
                pass

            # 尝试重新连接
            success = await self.connect()

            if success:
                logger.info(f"✅ 重连成功")
                self.reconnecting = False
                return

            attempt += 1

        # 重连失败
        logger.error("❌ 重连失败，已达到最大尝试次数")
        self.reconnecting = False

        if self.on_error:
            self.on_error(Exception("WebSocket 重连失败"))

    async def run(self) -> None:
        """
        运行 WebSocket 客户端（主循环）

        处理：
        1. 接收消息
        2. 心跳检测
        3. 自动重连
        """
        self.running = True

        # 首次连接
        if not await self.connect():
            logger.error("首次连接失败，退出")
            return

        try:
            # 主循环
            async for message in self.ws:
                if not self.running:
                    break

                # 更新心跳时间
                self.last_pong_time = time.time()

                # 解析消息
                try:
                    data = json.loads(message)

                    # 更新计数器
                    self.message_count += 1

                    # 调用回调
                    if self.on_message:
                        await self.on_message(data)

                except json.JSONDecodeError as e:
                    logger.error(f"消息解析失败: {e}")
                    self.error_count += 1
                except Exception as e:
                    logger.error(f"消息处理失败: {e}")
                    self.error_count += 1

        except ConnectionClosed as e:
            logger.warning(f"⚠️ 连接已关闭: {e}")

            if self.running:
                await self._reconnect()

        except Exception as e:
            logger.error(f"❌ WebSocket 异常: {e}")

            if self.on_error:
                self.on_error(e)

            if self.running:
                await self._reconnect()

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            "connect_count": self.connect_count,
            "reconnect_count": self.reconnect_count,
            "message_count": self.message_count,
            "error_count": self.error_count,
            "subscriptions": list(self.subscriptions),
            "running": self.running,
            "reconnecting": self.reconnecting,
        }


class BinanceWebSocketPool:
    """
    WebSocket 连接池

    用途：
    1. 管理多个 WebSocket 连接
    2. 分发订阅到不同连接（负载均衡）
    3. 统一重连管理
    """

    def __init__(
        self,
        testnet: bool = False,
        pool_size: int = 3,  # 连接池大小
        on_message: Optional[Callable[[str, Dict], None]] = None,
        on_error: Optional[Callable[[Exception], None]] = None,
    ):
        self.testnet = testnet
        self.pool_size = pool_size
        self.on_message = on_message
        self.on_error = on_error

        # 连接池
        self.connections: list[BinanceWebSocketClient] = []

        # 订阅映射 (stream -> connection_index)
        self.subscription_map: Dict[str, int] = {}

        # 运行状态
        self.running = False

        logger.info(f"WebSocket 连接池初始化: {pool_size} 个连接")

    async def start(self) -> None:
        """启动连接池"""
        self.running = True

        logger.info(f"🚀 启动 WebSocket 连接池 ({self.pool_size} 个连接)...")

        # 创建连接
        for i in range(self.pool_size):
            client = BinanceWebSocketClient(
                testnet=self.testnet,
                on_message=lambda data, idx=i: self._on_message_wrapper(idx, data),
                on_error=self._on_error_wrapper,
            )

            self.connections.append(client)

            # 启动客户端
            asyncio.create_task(client.run())

        logger.info("✅ WebSocket 连接池已启动")

    async def stop(self) -> None:
        """停止连接池"""
        self.running = False

        logger.info("🛑 停止 WebSocket 连接池...")

        for client in self.connections:
            await client.disconnect()

        self.connections.clear()
        self.subscription_map.clear()

        logger.info("✅ WebSocket 连接池已停止")

    async def subscribe(self, stream: str) -> None:
        """
        订阅数据流（自动分配到负载最少的连接）

        Args:
            stream: 数据流名称
        """
        if not self.connections:
            logger.error("连接池为空，无法订阅")
            return

        # 找到订阅数最少的连接
        min_subscriptions = float('inf')
        target_index = 0

        for i, client in enumerate(self.connections):
            subscriptions = len(client.subscriptions)
            if subscriptions < min_subscriptions:
                min_subscriptions = subscriptions
                target_index = i

        # 订阅
        await self.connections[target_index].subscribe(stream)

        # 记录映射
        self.subscription_map[stream] = target_index

        logger.debug(f"订阅 {stream} -> 连接 #{target_index + 1}")

    async def _on_message_wrapper(self, connection_index: int, data: Dict) -> None:
        """
        消息回调包装器

        Args:
            connection_index: 连接索引
            data: 消息数据
        """
        if self.on_message:
            await self.on_message(f"connection_{connection_index}", data)

    async def _on_error_wrapper(self, error: Exception) -> None:
        """错误回调包装器"""
        if self.on_error:
            await self.on_error(error)

    def get_pool_stats(self) -> list[Dict]:
        """获取连接池统计信息"""
        return [client.get_stats() for client in self.connections]


if __name__ == '__main__':
    # 测试代码
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - [%(name)s] - %(levelname)s - %(message)s'
    )

    async def test_websocket():
        """测试 WebSocket 客户端"""
        client = BinanceWebSocketClient(testnet=True)

        # 订阅 aggTrade
        await client.subscribe("btcusdt@aggTrade")

        # 消息回调
        async def on_message(data):
            print(f"收到消息: {json.dumps(data, indent=2)}")

        client.on_message = on_message

        # 运行 30 秒
        await asyncio.sleep(30)

        # 断开连接
        await client.disconnect()

        # 打印统计
        print("\n统计信息:")
        print(json.dumps(client.get_stats(), indent=2))

    asyncio.run(test_websocket())
