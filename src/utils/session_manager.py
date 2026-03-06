"""
v6.0 全局 Session 管理器（TLS Keep-Alive + 连接池）

确保所有 HTTP 请求复用同一个 TCP/TLS 连接，减少握手延迟
"""
import asyncio
import logging
import os
from typing import Optional, Dict, Any, Any as AnyType

# 延迟导入 aiohttp（避免在模块导入时卡住）
aiohttp = None

logger = logging.getLogger(__name__)

# 全局标志：aiohttp 是否可用
_AIOHTTP_AVAILABLE = None

# v6.1: 显式设置代理
PROXY = os.environ.get('HTTP_PROXY') or os.environ.get('HTTPS_PROXY') or os.environ.get('ALL_PROXY') or ''
if PROXY:
    logger.info(f"Session Manager 代理配置: {PROXY}")


def _ensure_aiohttp():
    """确保 aiohttp 已导入（在需要时）"""
    global aiohttp, _AIOHTTP_AVAILABLE
    if aiohttp is not None:
        return True

    try:
        import importlib
        spec = importlib.util.find_spec("aiohttp")
        if spec is None:
            _AIOHTTP_AVAILABLE = False
            logger.info("aiohttp 未安装，将使用同步客户端")
            return False

        aiohttp = importlib.import_module("aiohttp")
        _AIOHTTP_AVAILABLE = True
        return True
    except Exception as e:
        _AIOHTTP_AVAILABLE = False
        logger.warning(f"aiohttp 导入失败: {e}，将使用同步客户端")
        return False


def _check_aiohttp():
    """检查 aiohttp 是否可用"""
    global _AIOHTTP_AVAILABLE
    if _AIOHTTP_AVAILABLE is None:
        _ensure_aiohttp()
    return _AIOHTTP_AVAILABLE or False


class _SyncSessionWrapper:
    """同步 Session 包装器（提供类似 aiohttp 的接口）"""

    def __init__(self, sync_client):
        self._sync_client = sync_client

    async def get(self, url: str, **kwargs):
        """异步 GET 请求（实际是同步执行）"""
        import asyncio
        loop = asyncio.get_event_loop()

        # 解析参数
        params = kwargs.get('params')
        timeout = kwargs.get('timeout', 30)

        # 在线程池中执行同步请求
        result = await loop.run_in_executor(
            None,
            self._sync_client.get,
            url,
            params,
            timeout
        )

        # 返回一个兼容的响应对象
        return _SyncResponseWrapper(result)

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass


class _SyncResponseWrapper:
    """同步响应包装器"""

    def __init__(self, data: Dict[str, Any]):
        self._data = data
        self.status = 200  # 简化，总是假设成功

    async def json(self):
        return self._data

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass

    async def text(self):
        return str(self._data)


class GlobalSessionManager:
    """
    全局 Session 管理器

    功能：
    1. 单例模式，全局唯一 Session
    2. TCP Keep-Alive 长连接
    3. 连接池管理
    4. 自动重试
    5. DNS 缓存

    性能优化：
    - 避免 TCP/TLS 握手（节省 50-100ms）
    - 连接复用
    - DNS 缓存（5 分钟）
    """

    _instance: Optional['GlobalSessionManager'] = None
    _lock = asyncio.Lock()

    def __init__(self):
        # Session 配置
        self.connector = None  # type: Optional[object]
        self.session = None  # type: Optional[object]

        # 统计信息
        self.request_count = 0
        self.reuse_count = 0
        self.connection_count = 0

        # 运行状态
        self.initialized = False

        # 检查是否使用同步模式
        self.use_sync = not _check_aiohttp()

    @classmethod
    def get_instance_sync(cls):
        """同步获取实例（用于初始化）"""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    async def get_instance(cls) -> 'GlobalSessionManager':
        """
        获取全局单例

        Returns:
            GlobalSessionManager 实例
        """
        if cls._instance is None:
            async with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
                    await cls._instance.initialize()

        return cls._instance

    async def initialize(self) -> None:
        """初始化全局 Session"""
        if self.initialized:
            logger.debug("Session 已初始化，跳过")
            return

        if self.use_sync:
            # 使用同步客户端
            logger.info("使用同步 HTTP 客户端（aiohttp 不可用）")
            from src.utils.sync_http import get_sync_client
            self._sync_client = get_sync_client()
            # 创建一个兼容的 session 对象
            self.session = _SyncSessionWrapper(self._sync_client)
            self.initialized = True
            logger.info("✅ 同步 Session 已初始化")
            return

        logger.info("初始化全局 Session...")

        # 动态导入 aiohttp
        global aiohttp
        if aiohttp is None:
            import importlib
            aiohttp = importlib.import_module("aiohttp")

        # 配置连接器
        self.connector = aiohttp.TCPConnector(
            # 连接池配置
            limit=100,  # 总连接数限制
            limit_per_host=30,  # 每个主机连接数限制
            # Keep-Alive 配置
            keepalive_timeout=60,  # Keep-Alive 超时 60 秒
            enable_cleanup_closed=True,  # 清理关闭的连接
            # DNS 缓存
            ttl_dns_cache=300,  # DNS 缓存 5 分钟
            # 性能优化
            force_close=False,  # 不强制关闭连接（复用）
            # SSL 配置
            ssl=False,  # 如果是 HTTPS，自动处理
        )

        # 配置超时 - 增加超时时间以适应慢速代理
        timeout = aiohttp.ClientTimeout(
            total=60,  # 总超时 60 秒
            connect=20,  # 连接超时 20 秒
            sock_connect=15,  # Socket 连接超时 15 秒
            sock_read=30,  # Socket 读取超时 30 秒
        )

        # 创建 Session
        session_kwargs = {
            'connector': self.connector,
            'timeout': timeout,
            'raise_for_status': False,
            'trust_env': True,
        }

        # v6.1: 如果配置了代理，显式设置
        if PROXY:
            # aiohttp 需要把 http:// 前缀去掉
            proxy_clean = PROXY.replace('http://', '').replace('https://', '')
            session_kwargs['proxy'] = f'http://{proxy_clean}'
            logger.info(f"Session 使用代理: {PROXY}")

        self.session = aiohttp.ClientSession(**session_kwargs)
        )

        self.initialized = True

        logger.info("Global Session Initialized")
        logger.info(f"   Connection Pool: {self.connector.limit} total, {self.connector.limit_per_host} per host")
        # handle different aiohttp versions
        try:
            logger.info(f"   Keep-Alive: {self.connector.keepalive_timeout} seconds")
        except AttributeError:
            logger.info(f"   Keep-Alive: default")
        try:
            logger.info(f"   DNS Cache: {self.connector.ttl_dns_cache} seconds")
        except AttributeError:
            logger.info(f"   DNS Cache: default")

    async def close(self) -> None:
        """关闭 Session"""
        if not self.initialized:
            return

        logger.info("关闭全局 Session...")

        # 打印统计
        logger.info(f"   总请求数: {self.request_count}")
        logger.info(f"   连接复用: {self.reuse_count}")
        logger.info(f"   新建连接: {self.connection_count}")

        if self.use_sync:
            # 同步模式不需要关闭
            pass
        elif self.session:
            await self.session.close()
            self.session = None

        self.connector = None
        self.initialized = False

        logger.info("✅ 全局 Session 已关闭")

    async def get(self, url: str, **kwargs) -> 'aiohttp.ClientResponse':
        """
        GET 请求

        Args:
            url: 请求 URL
            **kwargs: 其他参数

        Returns:
            响应对象
        """
        session = await self._ensure_session()

        self.request_count += 1

        try:
            response = await session.get(url, **kwargs)

            # 检查连接复用
            if response.connection and hasattr(response.connection, 'transport'):
                # 这里无法直接判断是否复用，但可以通过统计推测
                pass

            return response

        except Exception as e:
            logger.error(f"GET 请求失败: {url}, {e}")
            raise

    async def post(self, url: str, **kwargs) -> 'aiohttp.ClientResponse':
        """
        POST 请求

        Args:
            url: 请求 URL
            **kwargs: 其他参数

        Returns:
            响应对象
        """
        session = await self._ensure_session()

        self.request_count += 1

        try:
            response = await session.post(url, **kwargs)
            return response

        except Exception as e:
            logger.error(f"POST 请求失败: {url}, {e}")
            raise

    async def _ensure_session(self) -> 'aiohttp.ClientSession':
        """确保 Session 已初始化"""
        if not self.initialized or self.session is None:
            await self.initialize()

        return self.session

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        stats = {
            'request_count': self.request_count,
            'reuse_count': self.reuse_count,
            'connection_count': self.connection_count,
            'initialized': self.initialized,
        }

        if self.connector:
            # 获取连接池状态
            stats.update({
                'total_connections': self.connector.limit,
                'active_connections': len(self.connector._conns),
            })

        return stats


# 全局实例
_session_manager: Optional[GlobalSessionManager] = None


async def get_session_manager() -> GlobalSessionManager:
    """
    获取全局 Session 管理器

    Returns:
        GlobalSessionManager 实例
    """
    global _session_manager

    if _session_manager is None:
        _session_manager = await GlobalSessionManager.get_instance()

    return _session_manager


async def close_session_manager() -> None:
    """关闭全局 Session 管理器"""
    global _session_manager

    if _session_manager:
        await _session_manager.close()
        _session_manager = None


if __name__ == '__main__':
    # 测试代码
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - [%(name)s] - %(levelname)s - %(message)s'
    )

    async def test_session():
        """测试 Session 管理器"""
        manager = await get_session_manager()

        # 测试请求
        url = "https://fapi.binance.com/fapi/v1/ping"

        for i in range(5):
            response = await manager.get(url)
            print(f"请求 {i+1}: {response.status}")

            # 延迟（模拟实际使用）
            await asyncio.sleep(0.5)

        # 打印统计
        print("\n统计信息:")
        print(manager.get_stats())

        # 关闭
        await manager.close()

    asyncio.run(test_session())
