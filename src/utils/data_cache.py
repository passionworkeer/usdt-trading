"""
数据缓存模块 (Data Cache)

提供多层缓存功能，减少 API 调用
"""
import time
import hashlib
import json
import logging
from typing import Any, Optional, Dict, Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from functools import wraps
import asyncio

logger = logging.getLogger(__name__)


@dataclass
class CacheEntry:
    """缓存条目"""
    key: str
    value: Any
    timestamp: float
    ttl: float  # 生存时间 (秒)


class MemoryCache:
    """
    内存缓存

    特点：速度快，但进程重启后丢失
    """

    def __init__(self, default_ttl: float = 60.0):
        """
        初始化内存缓存

        Args:
            default_ttl: 默认生存时间 (秒)
        """
        self._cache: Dict[str, CacheEntry] = {}
        self.default_ttl = default_ttl
        self._hits = 0
        self._misses = 0

    def get(self, key: str) -> Optional[Any]:
        """获取缓存"""
        if key in self._cache:
            entry = self._cache[key]
            # 检查是否过期
            if time.time() - entry.timestamp < entry.ttl:
                self._hits += 1
                return entry.value
            else:
                # 删除过期条目
                del self._cache[key]
        self._misses += 1
        return None

    def set(self, key: str, value: Any, ttl: Optional[float] = None):
        """设置缓存"""
        self._cache[key] = CacheEntry(
            key=key,
            value=value,
            timestamp=time.time(),
            ttl=ttl or self.default_ttl
        )

    def delete(self, key: str):
        """删除缓存"""
        if key in self._cache:
            del self._cache[key]

    def clear(self):
        """清空缓存"""
        self._cache.clear()
        self._hits = 0
        self._misses = 0

    def get_stats(self) -> Dict:
        """获取缓存统计"""
        total = self._hits + self._misses
        hit_rate = self._hits / total * 100 if total > 0 else 0
        return {
            'hits': self._hits,
            'misses': self._misses,
            'hit_rate': hit_rate,
            'size': len(self._cache)
        }


class DiskCache:
    """
    磁盘缓存

    特点：持久化，但速度较慢
    """

    def __init__(self, cache_dir: str = "cache", default_ttl: float = 3600.0):
        """
        初始化磁盘缓存

        Args:
            cache_dir: 缓存目录
            default_ttl: 默认生存时间 (秒)
        """
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.default_ttl = default_ttl

    def _get_cache_path(self, key: str) -> Path:
        """获取缓存文件路径"""
        # 使用 hash 避免文件名过长
        key_hash = hashlib.md5(key.encode()).hexdigest()
        return self.cache_dir / f"{key_hash}.json"

    def get(self, key: str) -> Optional[Any]:
        """获取缓存"""
        cache_path = self._get_cache_path(key)
        if not cache_path.exists():
            return None

        try:
            with open(cache_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            # 检查是否过期
            if time.time() - data['timestamp'] < data['ttl']:
                return data['value']
            else:
                # 删除过期缓存
                cache_path.unlink()
                return None

        except Exception as e:
            logger.debug(f"读取缓存失败: {e}")
            return None

    def set(self, key: str, value: Any, ttl: Optional[float] = None):
        """设置缓存"""
        cache_path = self._get_cache_path(key)
        data = {
            'key': key,
            'value': value,
            'timestamp': time.time(),
            'ttl': ttl or self.default_ttl
        }

        try:
            with open(cache_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.warning(f"保存缓存失败: {e}")

    def delete(self, key: str):
        """删除缓存"""
        cache_path = self._get_cache_path(key)
        if cache_path.exists():
            cache_path.unlink()

    def clear(self):
        """清空缓存"""
        for cache_file in self.cache_dir.glob("*.json"):
            cache_file.unlink()

    def cleanup_expired(self):
        """清理过期缓存"""
        now = time.time()
        for cache_file in self.cache_dir.glob("*.json"):
            try:
                with open(cache_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                if now - data['timestamp'] >= data['ttl']:
                    cache_file.unlink()
            except:
                pass


class CacheManager:
    """
    缓存管理器

    整合内存缓存和磁盘缓存
    """

    def __init__(
        self,
        memory_ttl: float = 60.0,
        disk_ttl: float = 3600.0,
        cache_dir: str = "cache"
    ):
        """初始化缓存管理器"""
        self.memory_cache = MemoryCache(default_ttl=memory_ttl)
        self.disk_cache = DiskCache(default_ttl=disk_ttl, cache_dir=cache_dir)

    def get(self, key: str) -> Optional[Any]:
        """获取缓存（先从内存，再从磁盘）"""
        # 先从内存获取
        value = self.memory_cache.get(key)
        if value is not None:
            return value

        # 再从磁盘获取
        value = self.disk_cache.get(key)
        if value is not None:
            # 回填内存缓存
            self.memory_cache.set(key, value)
            return value

        return None

    def set(self, key: str, value: Any, memory_ttl: Optional[float] = None, disk_ttl: Optional[float] = None):
        """设置缓存"""
        # 同时设置内存和磁盘
        self.memory_cache.set(key, value, memory_ttl)
        self.disk_cache.set(key, value, disk_ttl)

    def delete(self, key: str):
        """删除缓存"""
        self.memory_cache.delete(key)
        self.disk_cache.delete(key)

    def clear(self):
        """清空缓存"""
        self.memory_cache.clear()
        self.disk_cache.clear()

    def get_stats(self) -> Dict:
        """获取缓存统计"""
        return {
            'memory': self.memory_cache.get_stats(),
            'disk_size': len(list(self.disk_cache.cache_dir.glob("*.json")))
        }


def cached(
    cache_manager: CacheManager,
    key_prefix: str = "",
    memory_ttl: float = 60.0,
    disk_ttl: float = 3600.0
):
    """
    缓存装饰器

    Args:
        cache_manager: 缓存管理器
        key_prefix: 缓存键前缀
        memory_ttl: 内存缓存生存时间
        disk_ttl: 磁盘缓存生存时间

    Usage:
        @cached(cache, key_prefix="klines")
        async def fetch_klines(symbol, interval):
            ...
    """
    def decorator(func: Callable):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            # 生成缓存键
            cache_key = f"{key_prefix}:{func.__name__}:{str(args)}:{str(kwargs)}"

            # 尝试从缓存获取
            cached_value = cache_manager.get(cache_key)
            if cached_value is not None:
                logger.debug(f"缓存命中: {cache_key}")
                return cached_value

            # 调用原函数
            result = await func(*args, **kwargs)

            # 存入缓存
            cache_manager.set(cache_key, result, memory_ttl, disk_ttl)

            return result

        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            # 生成缓存键
            cache_key = f"{key_prefix}:{func.__name__}:{str(args)}:{str(kwargs)}"

            # 尝试从缓存获取
            cached_value = cache_manager.get(cache_key)
            if cached_value is not None:
                logger.debug(f"缓存命中: {cache_key}")
                return cached_value

            # 调用原函数
            result = func(*args, **kwargs)

            # 存入缓存
            cache_manager.set(cache_key, result, memory_ttl, disk_ttl)

            return result

        # 根据函数类型返回对应的包装器
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper

    return decorator


# 全局缓存管理器实例
_global_cache: Optional[CacheManager] = None


def get_cache_manager() -> CacheManager:
    """获取全局缓存管理器"""
    global _global_cache
    if _global_cache is None:
        _global_cache = CacheManager()
    return _global_cache
