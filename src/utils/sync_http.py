"""
同步 HTTP 客户端（当 aiohttp 不可用时使用）
"""
import logging
import urllib.request
import urllib.error
import json
from typing import Optional, Dict, Any
import os

logger = logging.getLogger(__name__)


class SyncHTTPClient:
    """同步 HTTP 客户端（使用标准库）"""

    def __init__(self):
        self._setup_proxy()

    def _setup_proxy(self):
        """设置代理"""
        self.proxy = os.environ.get('HTTP_PROXY') or os.environ.get('HTTPS_PROXY')
        if self.proxy:
            logger.info(f"使用代理: {self.proxy}")

    def get(self, url: str, params: Optional[Dict] = None, timeout: int = 30) -> Dict[str, Any]:
        """
        发送 GET 请求

        Args:
            url: 请求 URL
            params: 查询参数
            timeout: 超时时间（秒）

        Returns:
            响应 JSON
        """
        try:
            # 构建完整 URL
            if params:
                query_string = '&'.join(f"{k}={v}" for k, v in params.items())
                url = f"{url}?{query_string}"

            # 创建请求
            request = urllib.request.Request(url)
            request.add_header('User-Agent', 'Mozilla/5.0')

            # 设置代理
            if self.proxy:
                request.set_proxy(self.proxy, 'https')

            # 发送请求
            with urllib.request.urlopen(request, timeout=timeout) as response:
                data = response.read().decode('utf-8')
                return json.loads(data)

        except urllib.error.HTTPError as e:
            logger.error(f"HTTP错误: {e.code} - {e.reason}")
            raise
        except urllib.error.URLError as e:
            logger.error(f"连接错误: {e.reason}")
            raise
        except Exception as e:
            logger.error(f"请求失败: {e}")
            raise

    async def async_get(self, url: str, params: Optional[Dict] = None, timeout: int = 30):
        """异步包装（兼容现有接口）"""
        # 在事件循环中运行同步代码
        import asyncio
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.get, url, params, timeout)


# 创建全局客户端
_sync_client = None


def get_sync_client() -> SyncHTTPClient:
    """获取同步客户端"""
    global _sync_client
    if _sync_client is None:
        _sync_client = SyncHTTPClient()
    return _sync_client
