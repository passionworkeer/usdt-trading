#!/usr/bin/env python3
"""
v7.3 状态广播器（State Broadcaster）

机构级架构设计：
- 进程级解耦：核心交易引擎只负责广播状态，不处理 HTTP/WebSocket
- 极低开销：Redis Pub/Sub 异步非阻塞，微秒级延迟
- 安全隔离：监控服务运行在独立进程，通过 SSH 隧道访问

使用场景：
1. 核心交易进程 → Redis Pub/Sub → 独立监控进程 → WebSocket → 浏览器
2. 多个监控进程可同时订阅（开发机、运维机）
3. 不影响交易主循环性能
"""
import asyncio
import json
import logging
from typing import Dict, Any, Optional
from datetime import datetime

try:
    import redis.asyncio as redis
except ImportError:
    raise ImportError("请安装 redis: pip install redis>=5.0.0")

logger = logging.getLogger(__name__)


class RedisConnectionError(Exception):
    """Redis 连接异常"""
    pass


class StateBroadcaster:
    """
    状态广播器（核心交易进程使用）

    功能：
    - 将交易状态异步发布到 Redis Pub/Sub
    - 非阻塞设计，不影响交易主循环
    - 支持价格、事件、统计数据广播
    - P1-10: 自动重连机制，确保连接可靠性
    """

    def __init__(
        self,
        redis_url: str = "redis://localhost:6379/0",
        channel_prefix: str = "sniper:v7.3",
        max_retries: int = 5,
        retry_delay: float = 2.0,
        heartbeat_interval: float = 30.0,
    ):
        """
        初始化状态广播器

        Args:
            redis_url: Redis 连接 URL
            channel_prefix: 频道前缀（用于环境隔离）
            max_retries: 最大重试次数
            retry_delay: 重试延迟（秒）
            heartbeat_interval: 心跳检测间隔（秒）
        """
        self.redis_url = redis_url
        self.channel_prefix = channel_prefix
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.heartbeat_interval = heartbeat_interval

        # Redis 连接（延迟初始化）
        self._redis: Optional[redis.Redis] = None
        self._is_connected = False
        self._connection_lock = asyncio.Lock()

        # 心跳任务
        self._heartbeat_task: Optional[asyncio.Task] = None

        # 频道名称
        self.CHANNEL_PRICE = f"{channel_prefix}:price"
        self.CHANNEL_EVENT = f"{channel_prefix}:event"
        self.CHANNEL_STATS = f"{channel_prefix}:stats"
        self.CHANNEL_POSITION = f"{channel_prefix}:position"

    async def _get_redis(self) -> Optional[redis.Redis]:
        """
        延迟初始化 Redis 连接（带自动重连）

        Returns:
            Redis 连接对象，失败返回 None
        """
        async with self._connection_lock:
            # 如果已连接，直接返回
            if self._is_connected and self._redis:
                return self._redis

            # 尝试连接
            for attempt in range(self.max_retries):
                try:
                    self._redis = await redis.from_url(
                        self.redis_url,
                        encoding="utf-8",
                        decode_responses=True,
                        # 连接池配置
                        max_connections=10,
                        socket_keepalive=True,
                        socket_keepalive_options={
                            1: 1,  # SOL_SOCKET
                            2: 10,  # TCP_KEEPIDLE (10秒)
                            3: 5,   # TCP_KEEPINTVL (5秒)
                            4: 3,   # TCP_KEEPCNT (3次)
                        },
                    )
                    # 测试连接
                    await self._redis.ping()
                    self._is_connected = True

                    # 启动心跳任务
                    if not self._heartbeat_task or self._heartbeat_task.done():
                        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())

                    logger.info(f"✅ Redis 连接成功: {self.redis_url}")
                    return self._redis

                except (redis.ConnectionError, redis.TimeoutError) as e:
                    wait_time = self.retry_delay * (2 ** attempt)  # 指数退避
                    logger.warning(
                        f"⚠️ Redis 连接失败 (尝试 {attempt + 1}/{self.max_retries}): {e}"
                    )
                    logger.warning(f"   {wait_time:.1f} 秒后重试...")

                    if attempt < self.max_retries - 1:
                        await asyncio.sleep(wait_time)
                    else:
                        logger.error("❌ Redis 连接失败，已达最大重试次数")
                        logger.warning("   状态广播将禁用（不影响交易核心功能）")
                        self._redis = None
                        self._is_connected = False
                        return None

                except Exception as e:
                    logger.error(f"❌ Redis 连接异常: {e}")
                    self._redis = None
                    self._is_connected = False
                    return None

        return self._redis

    async def _heartbeat_loop(self) -> None:
        """
        心跳检测循环

        定期检查连接状态，断线时自动重连
        """
        while self._is_connected:
            try:
                await asyncio.sleep(self.heartbeat_interval)

                if self._redis:
                    await self._redis.ping()
                    logger.debug("💓 Redis 心跳正常")

            except (redis.ConnectionError, redis.TimeoutError) as e:
                logger.warning(f"⚠️ Redis 心跳失败: {e}")
                self._is_connected = False

                # 尝试重连
                logger.info("🔄 尝试重新连接 Redis...")
                await self._get_redis()

                # 如果重连成功，继续心跳；否则退出
                if not self._is_connected:
                    logger.error("❌ Redis 重连失败，停止心跳")
                    break

            except asyncio.CancelledError:
                logger.info("心跳任务已取消")
                break
            except Exception as e:
                logger.error(f"心跳异常: {e}")
                await asyncio.sleep(self.heartbeat_interval)

    async def _publish_with_retry(
        self,
        channel: str,
        message: str,
        max_publish_retries: int = 3
    ) -> bool:
        """
        带重试的消息发布

        Args:
            channel: 频道名称
            message: 消息内容
            max_publish_retries: 最大发布重试次数

        Returns:
            是否发布成功
        """
        for attempt in range(max_publish_retries):
            try:
                r = await self._get_redis()
                if not r:
                    return False

                # Fire and forget（不等待发布结果）
                await r.publish(channel, message)
                return True

            except (redis.ConnectionError, redis.TimeoutError) as e:
                logger.warning(f"Redis 发布失败 (尝试 {attempt + 1}/{max_publish_retries}): {e}")
                self._is_connected = False

                if attempt < max_publish_retries - 1:
                    await asyncio.sleep(0.5)
                else:
                    logger.debug(f"发布失败，放弃: {channel}")
                    return False

            except Exception as e:
                logger.debug(f"发布异常: {e}")
                return False

        return False

    async def broadcast_price(self, symbol: str, price: float) -> None:
        """
        广播价格更新（非阻塞）

        Args:
            symbol: 交易对
            price: 当前价格
        """
        try:
            message = {
                'timestamp': datetime.now().isoformat(),
                'symbol': symbol,
                'price': price,
            }
            await self._publish_with_retry(self.CHANNEL_PRICE, json.dumps(message))
        except Exception as e:
            logger.debug(f"价格广播失败: {e}")

    async def broadcast_event(self, event: Dict[str, Any]) -> None:
        """
        广播交易事件（非阻塞）

        Args:
            event: 事件字典（type, symbol, side, price, message 等）
        """
        try:
            event['timestamp'] = datetime.now().isoformat()
            await self._publish_with_retry(self.CHANNEL_EVENT, json.dumps(event))
        except Exception as e:
            logger.debug(f"事件广播失败: {e}")

    async def broadcast_position(self, position_data: Dict[str, Any]) -> None:
        """
        广播仓位状态（非阻塞）

        Args:
            position_data: 仓位数据
        """
        try:
            position_data['timestamp'] = datetime.now().isoformat()
            await self._publish_with_retry(self.CHANNEL_POSITION, json.dumps(position_data))
        except Exception as e:
            logger.debug(f"仓位广播失败: {e}")

    async def broadcast_stats(self, stats: Dict[str, Any]) -> None:
        """
        广播交易统计（非阻塞）

        Args:
            stats: 统计数据
        """
        try:
            stats['timestamp'] = datetime.now().isoformat()
            await self._publish_with_retry(self.CHANNEL_STATS, json.dumps(stats))
        except Exception as e:
            logger.debug(f"统计广播失败: {e}")

    async def close(self) -> None:
        """关闭连接"""
        # 取消心跳任务
        if self._heartbeat_task and not self._heartbeat_task.done():
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass

        # 关闭 Redis 连接
        if self._redis:
            try:
                await self._redis.close()
                logger.info("Redis 连接已关闭")
            except Exception as e:
                logger.debug(f"关闭 Redis 连接失败: {e}")

        self._is_connected = False

    @property
    def is_connected(self) -> bool:
        """检查是否已连接"""
        return self._is_connected
