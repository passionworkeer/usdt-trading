"""
v5.3: API 异常处理与指数退避重试机制

针对 Binance API 的异常处理：
- Rate Limit Exceeded (429)
- Timeout / Connection Reset
- Server Error (500, 502, 503)
- 指数退避重试机制
"""
import logging
import asyncio
import functools
from typing import Callable, Any, Optional
from enum import Enum

logger = logging.getLogger(__name__)


class RetryStrategy(Enum):
    """重试策略"""
    EXPONENTIAL = "exponential"  # 指数退避
    LINEAR = "linear"  # 线性退避
    FIXED = "fixed"  # 固定间隔


def exponential_backoff_retry(
    max_retries: int = 5,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    exponential_base: float = 2.0,
    exceptions: tuple = (Exception,)
):
    """
    指数退避重试装饰器

    公式：delay = min(max_delay, base_delay * exponential_base ** attempt)

    示例：
    - 第 1 次重试：1s
    - 第 2 次重试：2s
    - 第 3 次重试：4s
    - 第 4 次重试：8s
    - 第 5 次重试：16s

    Args:
        max_retries: 最大重试次数
        base_delay: 基础延迟（秒）
        max_delay: 最大延迟（秒）
        exponential_base: 指数基数
        exceptions: 需要捕获的异常类型

    Usage:
        @exponential_backoff_retry(max_retries=5, base_delay=1.0)
        async def fetch_ticker(symbol: str):
            return await exchange.fetch_ticker(symbol)
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs) -> Any:
            last_exception = None

            for attempt in range(max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e

                    if attempt == max_retries:
                        # 最后一次重试失败
                        logger.critical(f"🔴 {func.__name__} 重试 {max_retries} 次后仍然失败: {e}")
                        raise

                    # 计算延迟
                    delay = min(max_delay, base_delay * (exponential_base ** attempt))

                    logger.warning(
                        f"⚠️ {func.__name__} 失败 (尝试 {attempt + 1}/{max_retries + 1}): {e}\n"
                        f"   等待 {delay:.1f}s 后重试..."
                    )

                    await asyncio.sleep(delay)

            raise last_exception

        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs) -> Any:
            last_exception = None

            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e

                    if attempt == max_retries:
                        logger.critical(f"🔴 {func.__name__} 重试 {max_retries} 次后仍然失败: {e}")
                        raise

                    delay = min(max_delay, base_delay * (exponential_base ** attempt))

                    logger.warning(
                        f"⚠️ {func.__name__} 失败 (尝试 {attempt + 1}/{max_retries + 1}): {e}\n"
                        f"   等待 {delay:.1f}s 后重试..."
                    )

                    import time
                    time.sleep(delay)

            raise last_exception

        # 判断是异步还是同步函数
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper

    return decorator


class BinanceAPIError(Exception):
    """Binance API 错误基类"""
    def __init__(self, message: str, code: Optional[int] = None, response: Optional[dict] = None):
        self.message = message
        self.code = code
        self.response = response
        super().__init__(self.message)


class RateLimitError(BinanceAPIError):
    """Rate Limit 超限 (429)"""
    pass


class TimeoutError(BinanceAPIError):
    """请求超时"""
    pass


class ConnectionError(BinanceAPIError):
    """连接错误"""
    pass


class ServerError(BinanceAPIError):
    """服务器错误 (500, 502, 503)"""
    pass


def classify_binance_error(error: Exception) -> BinanceAPIError:
    """
    分类 Binance API 错误

    Args:
        error: 原始异常

    Returns:
        分类后的 BinanceAPIError
    """
    error_str = str(error).lower()

    # Rate Limit
    if '429' in error_str or 'rate limit' in error_str or 'too many requests' in error_str:
        return RateLimitError(f"Rate Limit 超限: {error}")

    # Timeout
    if 'timeout' in error_str or 'timed out' in error_str:
        return TimeoutError(f"请求超时: {error}")

    # Connection
    if 'connection' in error_str or 'network' in error_str or 'reset' in error_str:
        return ConnectionError(f"连接错误: {error}")

    # Server Error
    if '500' in error_str or '502' in error_str or '503' in error_str or 'server error' in error_str:
        return ServerError(f"服务器错误: {error}")

    # 默认
    return BinanceAPIError(f"未知错误: {error}")


if __name__ == '__main__':
    """测试指数退避重试"""
    import random

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    @exponential_backoff_retry(max_retries=5, base_delay=1.0, exceptions=(ValueError,))
    async def unstable_api_call():
        """模拟不稳定的 API 调用"""
        if random.random() < 0.7:  # 70% 失败率
            raise ValueError("模拟 API 错误")
        return "Success!"

    async def test_retry():
        try:
            result = await unstable_api_call()
            print(f"✅ 结果: {result}")
        except Exception as e:
            print(f"❌ 最终失败: {e}")

    asyncio.run(test_retry())
