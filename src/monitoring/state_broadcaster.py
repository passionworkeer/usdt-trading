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


class StateBroadcaster:
    """
    状态广播器（核心交易进程使用）

    功能：
    - 将交易状态异步发布到 Redis Pub/Sub
    - 非阻塞设计，不影响交易主循环
    - 支持价格、事件、统计数据广播
    """

    def __init__(
        self,
        redis_url: str = "redis://localhost:6379/0",
        channel_prefix: str = "sniper:v7.3",
    ):
        """
        初始化状态广播器

        Args:
            redis_url: Redis 连接 URL
            channel_prefix: 频道前缀（用于环境隔离）
        """
        self.redis_url = redis_url
        self.channel_prefix = channel_prefix

        # Redis 连接（延迟初始化）
        self._redis: Optional[redis.Redis] = None

        # 频道名称
        self.CHANNEL_PRICE = f"{channel_prefix}:price"
        self.CHANNEL_EVENT = f"{channel_prefix}:event"
        self.CHANNEL_STATS = f"{channel_prefix}:stats"
        self.CHANNEL_POSITION = f"{channel_prefix}:position"

    async def _get_redis(self) -> redis.Redis:
        """延迟初始化 Redis 连接"""
        if self._redis is None:
            try:
                self._redis = await redis.from_url(
                    self.redis_url,
                    encoding="utf-8",
                    decode_responses=True,
                )
                # 测试连接
                await self._redis.ping()
                logger.info(f"✅ Redis 连接成功: {self.redis_url}")
            except Exception as e:
                logger.warning(f"⚠️ Redis 连接失败: {e}")
                logger.warning("   状态广播将禁用（不影响交易核心功能）")
                self._redis = None

        return self._redis

    async def broadcast_price(self, symbol: str, price: float) -> None:
        """
        广播价格更新（非阻塞）

        Args:
            symbol: 交易对
            price: 当前价格
        """
        r = await self._get_redis()
        if not r:
            return

        try:
            message = {
                'timestamp': datetime.now().isoformat(),
                'symbol': symbol,
                'price': price,
            }
            # Fire and forget（不等待发布结果）
            await r.publish(self.CHANNEL_PRICE, json.dumps(message))
        except Exception as e:
            logger.debug(f"价格广播失败: {e}")

    async def broadcast_event(self, event: Dict[str, Any]) -> None:
        """
        广播交易事件（非阻塞）

        Args:
            event: 事件字典（type, symbol, side, price, message 等）
        """
        r = await self._get_redis()
        if not r:
            return

        try:
            event['timestamp'] = datetime.now().isoformat()
            # Fire and forget
            await r.publish(self.CHANNEL_EVENT, json.dumps(event))
        except Exception as e:
            logger.debug(f"事件广播失败: {e}")

    async def broadcast_position(self, position_data: Dict[str, Any]) -> None:
        """
        广播仓位状态（非阻塞）

        Args:
            position_data: 仓位数据
        """
        r = await self._get_redis()
        if not r:
            return

        try:
            position_data['timestamp'] = datetime.now().isoformat()
            # Fire and forget
            await r.publish(self.CHANNEL_POSITION, json.dumps(position_data))
        except Exception as e:
            logger.debug(f"仓位广播失败: {e}")

    async def broadcast_stats(self, stats: Dict[str, Any]) -> None:
        """
        广播交易统计（非阻塞）

        Args:
            stats: 统计数据
        """
        r = await self._get_redis()
        if not r:
            return

        try:
            stats['timestamp'] = datetime.now().isoformat()
            # Fire and forget
            await r.publish(self.CHANNEL_STATS, json.dumps(stats))
        except Exception as e:
            logger.debug(f"统计广播失败: {e}")

    async def close(self) -> None:
        """关闭连接"""
        if self._redis:
            try:
                await self._redis.close()
                logger.info("Redis 连接已关闭")
            except Exception as e:
                logger.debug(f"关闭 Redis 连接失败: {e}")
