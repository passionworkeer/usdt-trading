"""
Redis 缓存系统 (Redis Cache)

高性能缓存层，用于：
- K线数据缓存
- 实时价格缓存
- API 响应缓存
- 会话状态缓存
"""
import asyncio
import json
import logging
from typing import Any, Optional, List, Dict
from datetime import datetime, timedelta
from functools import wraps

try:
    import redis.asyncio as redis
except ImportError:
    redis = None

logger = logging.getLogger(__name__)


class RedisCacheError(Exception):
    """Redis 缓存异常"""
    pass


class RedisCache:
    """
    Redis 缓存管理器

    功能：
    - 键值缓存（支持 TTL）
    - 列表缓存（K线数据）
    - 哈希缓存（复杂对象）
    - 缓存前缀隔离
    - 自动重连
    - 降级处理（Redis 不可用时使用内存缓存）
    """

    DEFAULT_TTL = 300  # 默认 5 分钟

    def __init__(
        self,
        redis_url: str = "redis://localhost:6379/0",
        prefix: str = "sniper:cache",
        enable_fallback: bool = True,
        max_retries: int = 3,
    ):
        """
        初始化 Redis 缓存

        Args:
            redis_url: Redis 连接 URL
            prefix: 缓存键前缀（用于环境隔离）
            enable_fallback: 是否启用内存降级
            max_retries: 最大重试次数
        """
        self.redis_url = redis_url
        self.prefix = prefix
        self.enable_fallback = enable_fallback
        self.max_retries = max_retries

        # Redis 连接
        self._redis: Optional[redis.Redis] = None
        self._is_connected = False

        # 内存降级缓存
        self._memory_cache: Dict[str, tuple[Any, datetime]] = {}
        self._memory_ttl = 60  # 内存缓存 60 秒

        # 缓存统计
        self.stats = {
            'hits': 0,
            'misses': 0,
            'errors': 0,
            'fallbacks': 0,
        }

    def _make_key(self, key: str) -> str:
        """生成带前缀的缓存键"""
        return f"{self.prefix}:{key}"

    async def connect(self) -> bool:
        """连接 Redis"""
        if not redis:
            logger.warning("redis 包未安装，使用内存缓存")
            return False

        try:
            self._redis = await redis.from_url(
                self.redis_url,
                encoding="utf-8",
                decode_responses=True,
                max_connections=10,
            )
            await self._redis.ping()
            self._is_connected = True
            logger.info(f"✅ Redis 缓存连接成功: {self.redis_url}")
            return True
        except Exception as e:
            logger.warning(f"⚠️ Redis 连接失败: {e}，启用内存缓存")
            self._is_connected = False
            return False

    async def close(self):
        """关闭连接"""
        if self._redis:
            await self._redis.close()
            self._is_connected = False

    def _get_from_memory(self, key: str) -> Optional[Any]:
        """从内存缓存获取"""
        if key in self._memory_cache:
            value, expire_at = self._memory_cache[key]
            if datetime.now() < expire_at:
                self.stats['fallbacks'] += 1
                return value
            else:
                del self._memory_cache[key]
        return None

    def _set_to_memory(self, key: str, value: Any, ttl: int):
        """设置内存缓存"""
        expire_at = datetime.now() + timedelta(seconds=ttl)
        self._memory_cache[key] = (value, expire_at)

        # 清理过期缓存
        now = datetime.now()
        self._memory_cache = {
            k: v for k, v in self._memory_cache.items()
            if now < v[1]
        }

    # ========== 基础缓存操作 ==========

    async def get(self, key: str) -> Optional[Any]:
        """
        获取缓存值

        Args:
            key: 缓存键

        Returns:
            缓存值，不存在返回 None
        """
        redis_key = self._make_key(key)

        # 尝试 Redis
        if self._is_connected and self._redis:
            try:
                value = await self._redis.get(redis_key)
                if value is not None:
                    self.stats['hits'] += 1
                    return json.loads(value)
            except Exception as e:
                self.stats['errors'] += 1
                logger.debug(f"Redis get 失败: {e}")

        # 降级到内存
        if self.enable_fallback:
            return self._get_from_memory(key)

        self.stats['misses'] += 1
        return None

    async def set(
        self,
        key: str,
        value: Any,
        ttl: int = DEFAULT_TTL
    ) -> bool:
        """
        设置缓存值

        Args:
            key: 缓存键
            value: 缓存值
            ttl: 过期时间（秒）

        Returns:
            是否设置成功
        """
        redis_key = self._make_key(key)

        # 序列化
        try:
            serialized = json.dumps(value, default=str)
        except Exception as e:
            logger.error(f"缓存值序列化失败: {e}")
            return False

        # 写入 Redis
        if self._is_connected and self._redis:
            try:
                await self._redis.setex(redis_key, ttl, serialized)
                return True
            except Exception as e:
                self.stats['errors'] += 1
                logger.debug(f"Redis set 失败: {e}")

        # 降级到内存
        if self.enable_fallback:
            self._set_to_memory(key, value, min(ttl, self._memory_ttl))
            return True

        return False

    async def delete(self, key: str) -> bool:
        """删除缓存"""
        redis_key = self._make_key(key)

        if self._is_connected and self._redis:
            try:
                await self._redis.delete(redis_key)
            except Exception as e:
                logger.debug(f"Redis delete 失败: {e}")

        # 清理内存缓存
        if key in self._memory_cache:
            del self._memory_cache[key]

        return True

    async def exists(self, key: str) -> bool:
        """检查键是否存在"""
        redis_key = self._make_key(key)

        if self._is_connected and self._redis:
            try:
                return await self._redis.exists(redis_key) > 0
            except Exception:
                pass

        return key in self._memory_cache

    async def expire(self, key: str, ttl: int) -> bool:
        """设置键的过期时间"""
        redis_key = self._make_key(key)

        if self._is_connected and self._redis:
            try:
                return await self._redis.expire(redis_key, ttl)
            except Exception:
                pass

        return False

    # ========== 列表缓存（K线数据） ==========

    async def push_klines(
        self,
        symbol: str,
        timeframe: str,
        klines: List[Dict],
        max_size: int = 500
    ) -> bool:
        """
        缓存 K 线数据

        Args:
            symbol: 交易对
            timeframe: 时间周期
            klines: K线数据列表
            max_size: 最大缓存数量

        Returns:
            是否成功
        """
        key = f"klines:{symbol}:{timeframe}"
        return await self.set(key, klines[:max_size], ttl=60)

    async def get_klines(
        self,
        symbol: str,
        timeframe: str
    ) -> Optional[List[Dict]]:
        """获取缓存的 K 线数据"""
        key = f"klines:{symbol}:{timeframe}"
        return await self.get(key)

    # ========== 价格缓存 ==========

    async def set_price(self, symbol: str, price: float) -> bool:
        """缓存实时价格（10秒TTL）"""
        key = f"price:{symbol}"
        return await self.set(key, price, ttl=10)

    async def get_price(self, symbol: str) -> Optional[float]:
        """获取缓存的价格"""
        key = f"price:{symbol}"
        return await self.get(key)

    async def set_prices(self, prices: Dict[str, float]) -> bool:
        """批量缓存价格"""
        tasks = [self.set_price(symbol, price) for symbol, price in prices.items()]
        await asyncio.gather(*tasks, return_exceptions=True)
        return True

    async def get_prices(self, symbols: List[str]) -> Dict[str, Optional[float]]:
        """批量获取价格"""
        tasks = [self.get_price(symbol) for symbol in symbols]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        return {
            symbol: result if isinstance(result, (int, float)) else None
            for symbol, result in zip(symbols, results)
        }

    # ========== 哈希缓存 ==========

    async def hset(
        self,
        name: str,
        key: str,
        value: Any,
        ttl: int = DEFAULT_TTL
    ) -> bool:
        """设置哈希字段"""
        redis_key = self._make_key(name)

        try:
            serialized = json.dumps(value, default=str)
        except Exception:
            return False

        if self._is_connected and self._redis:
            try:
                pipe = self._redis.pipeline()
                pipe.hset(redis_key, key, serialized)
                pipe.expire(redis_key, ttl)
                await pipe.execute()
                return True
            except Exception:
                pass

        return False

    async def hget(self, name: str, key: str) -> Optional[Any]:
        """获取哈希字段"""
        redis_key = self._make_key(name)

        if self._is_connected and self._redis:
            try:
                value = await self._redis.hget(redis_key, key)
                if value:
                    return json.loads(value)
            except Exception:
                pass

        return None

    async def hgetall(self, name: str) -> Dict[str, Any]:
        """获取所有哈希字段"""
        redis_key = self._make_key(name)

        if self._is_connected and self._redis:
            try:
                data = await self._redis.hgetall(redis_key)
                return {k: json.loads(v) for k, v in data.items()}
            except Exception:
                pass

        return {}

    # ========== 缓存统计 ==========

    def get_stats(self) -> Dict:
        """获取缓存统计"""
        total = self.stats['hits'] + self.stats['misses']
        hit_rate = (
            self.stats['hits'] / total * 100
            if total > 0 else 0
        )

        return {
            **self.stats,
            'total_requests': total,
            'hit_rate': round(hit_rate, 2),
            'is_connected': self._is_connected,
            'memory_cache_size': len(self._memory_cache),
        }

    def reset_stats(self):
        """重置统计"""
        self.stats = {
            'hits': 0,
            'misses': 0,
            'errors': 0,
            'fallbacks': 0,
        }

    # ========== 缓存装饰器 ==========

    def cached(self, key_func=None, ttl: int = DEFAULT_TTL):
        """
        缓存装饰器

        Usage:
            @cache.cached(key_func=lambda x, y: f"{x}:{y}")
            async def fetch_data(x, y):
                ...
        """
        def decorator(func):
            @wraps(func)
            async def wrapper(*args, **kwargs):
                # 生成缓存键
                if key_func:
                    cache_key = key_func(*args, **kwargs)
                else:
                    cache_key = f"{func.__name__}:{str(args)}:{str(kwargs)}"

                # 尝试获取缓存
                cached_value = await self.get(cache_key)
                if cached_value is not None:
                    return cached_value

                # 执行函数
                if asyncio.iscoroutinefunction(func):
                    result = await func(*args, **kwargs)
                else:
                    result = func(*args, **kwargs)

                # 缓存结果
                await self.set(cache_key, result, ttl=ttl)

                return result
            return wrapper
        return decorator


# 全局缓存实例
_cache: Optional[RedisCache] = None


def get_cache(
    redis_url: str = None,
    prefix: str = "sniper:cache"
) -> RedisCache:
    """获取全局缓存实例"""
    global _cache

    if _cache is None:
        import os
        url = redis_url or os.getenv('REDIS_URL', 'redis://localhost:6379/0')
        _cache = RedisCache(redis_url=url, prefix=prefix)

    return _cache


async def init_cache() -> RedisCache:
    """初始化缓存并连接"""
    cache = get_cache()
    await cache.connect()
    return cache
