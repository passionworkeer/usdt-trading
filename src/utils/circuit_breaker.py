"""
熔断器模式实现（Circuit Breaker Pattern）

P1-17: 实现黑盒事件应对 - 连续失败后暂停交易

状态转换：
- CLOSED (关闭) → 正常状态，允许请求通过
- OPEN (开启) → 熔断状态，拒绝请求
- HALF_OPEN (半开) → 尝试恢复，允许少量请求通过

使用场景：
1. 交易所 API 连续失败
2. 网络连接不稳定
3. 订单提交失败率过高
"""
import logging
import time
import asyncio
from typing import Optional, Callable, Any
from dataclasses import dataclass
from enum import Enum
from functools import wraps

logger = logging.getLogger(__name__)


class CircuitState(Enum):
    """熔断器状态"""
    CLOSED = "closed"  # 关闭：正常工作
    OPEN = "open"  # 开启：熔断中，拒绝请求
    HALF_OPEN = "half_open"  # 半开：尝试恢复


@dataclass
class CircuitBreakerConfig:
    """熔断器配置"""
    failure_threshold: int = 3  # 连续失败阈值
    success_threshold: int = 2  # 半开状态连续成功次数
    cooldown_seconds: int = 300  # 冷却时间（秒）
    timeout_seconds: int = 30  # 请求超时时间

    # 滑动窗口配置
    window_size: int = 60  # 统计窗口（秒）
    min_requests: int = 5  # 最小请求数


class CircuitBreakerError(Exception):
    """熔断器异常"""
    pass


class CircuitBreakerOpenError(CircuitBreakerError):
    """熔断器开启异常"""
    pass


class CircuitBreaker:
    """
    熔断器实现

    功能：
    1. 连续失败达到阈值后触发熔断
    2. 熔断期间拒绝请求
    3. 冷却时间后进入半开状态
    4. 半开状态连续成功后恢复
    """

    def __init__(
        self,
        name: str,
        config: Optional[CircuitBreakerConfig] = None,
    ):
        """
        初始化熔断器

        Args:
            name: 熔断器名称（用于日志）
            config: 熔断器配置
        """
        self.name = name
        self.config = config or CircuitBreakerConfig()

        # 状态
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time: Optional[float] = None
        self.last_success_time: Optional[float] = None

        # 统计信息
        self.total_requests = 0
        self.total_failures = 0
        self.total_successes = 0

        logger.info(
            f"✅ 熔断器 '{name}' 已初始化 "
            f"(阈值: {self.config.failure_threshold}, 冷却: {self.config.cooldown_seconds}s)"
        )

    def check(self) -> bool:
        """
        检查是否允许执行请求

        Returns:
            True: 允许执行
            False: 拒绝执行（熔断中）
        """
        # CLOSED: 正常工作
        if self.state == CircuitState.CLOSED:
            return True

        # OPEN: 熔断中
        if self.state == CircuitState.OPEN:
            # 检查是否可以进入半开状态
            if self._should_attempt_reset():
                self.state = CircuitState.HALF_OPEN
                self.success_count = 0
                logger.info(f"🔄 熔断器 '{self.name}' 进入半开状态，尝试恢复...")
                return True

            logger.warning(f"🚫 熔断器 '{self.name}' 仍处于开启状态")
            return False

        # HALF_OPEN: 允许尝试
        return True

    def on_success(self) -> None:
        """请求成功时调用"""
        self.total_successes += 1
        self.last_success_time = time.time()

        if self.state == CircuitState.HALF_OPEN:
            self.success_count += 1

            # 连续成功达到阈值，恢复到关闭状态
            if self.success_count >= self.config.success_threshold:
                self.state = CircuitState.CLOSED
                self.failure_count = 0
                logger.info(
                    f"✅ 熔断器 '{self.name}' 已恢复到关闭状态 "
                    f"(连续成功 {self.success_count} 次)"
                )

        elif self.state == CircuitState.CLOSED:
            # 重置失败计数
            self.failure_count = 0

    def on_failure(self) -> None:
        """请求失败时调用"""
        self.total_failures += 1
        self.failure_count += 1
        self.last_failure_time = time.time()

        # 检查是否需要触发熔断
        if self.failure_count >= self.config.failure_threshold:
            if self.state != CircuitState.OPEN:
                self.state = CircuitState.OPEN
                logger.error(
                    f"🚨 熔断器 '{self.name}' 触发！"
                    f"连续失败 {self.failure_count} 次，进入冷却期 ({self.config.cooldown_seconds}s)"
                )

    def _should_attempt_reset(self) -> bool:
        """
        检查是否应该尝试重置

        Returns:
            True: 可以尝试重置
            False: 继续熔断
        """
        if self.last_failure_time is None:
            return True

        elapsed = time.time() - self.last_failure_time
        return elapsed >= self.config.cooldown_seconds

    def reset(self) -> None:
        """手动重置熔断器"""
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time = None
        logger.info(f"🔄 熔断器 '{self.name}' 已手动重置")

    def get_state(self) -> CircuitState:
        """获取当前状态"""
        return self.state

    def get_stats(self) -> dict:
        """
        获取统计信息

        Returns:
            统计信息字典
        """
        return {
            'name': self.name,
            'state': self.state.value,
            'failure_count': self.failure_count,
            'success_count': self.success_count,
            'total_requests': self.total_requests,
            'total_failures': self.total_failures,
            'total_successes': self.total_successes,
            'failure_rate': self.total_failures / self.total_requests if self.total_requests > 0 else 0,
            'last_failure_time': self.last_failure_time,
            'last_success_time': self.last_success_time,
        }


def circuit_breaker_protected(
    breaker: CircuitBreaker,
    error_exceptions: tuple = (Exception,),
):
    """
    熔断器装饰器

    用法：
        @circuit_breaker_protected(my_breaker)
        async def my_function():
            ...

    Args:
        breaker: 熔断器实例
        error_exceptions: 触发失败的异常类型
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def async_wrapper(*args, **kwargs) -> Any:
            breaker.total_requests += 1

            # 检查熔断器状态
            if not breaker.check():
                raise CircuitBreakerOpenError(
                    f"熔断器 '{breaker.name}' 处于开启状态，请求被拒绝"
                )

            try:
                # 执行函数
                result = await func(*args, **kwargs)

                # 成功
                breaker.on_success()
                return result

            except error_exceptions as e:
                # 失败
                breaker.on_failure()
                raise

        @wraps(func)
        def sync_wrapper(*args, **kwargs) -> Any:
            breaker.total_requests += 1

            # 检查熔断器状态
            if not breaker.check():
                raise CircuitBreakerOpenError(
                    f"熔断器 '{breaker.name}' 处于开启状态，请求被拒绝"
                )

            try:
                # 执行函数
                result = func(*args, **kwargs)

                # 成功
                breaker.on_success()
                return result

            except error_exceptions as e:
                # 失败
                breaker.on_failure()
                raise

        # 根据函数类型返回相应的包装器
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper

    return decorator


class CircuitBreakerManager:
    """
    熔断器管理器

    管理多个熔断器实例
    """

    def __init__(self):
        """初始化管理器"""
        self.breakers: dict[str, CircuitBreaker] = {}

    def create_breaker(
        self,
        name: str,
        config: Optional[CircuitBreakerConfig] = None,
    ) -> CircuitBreaker:
        """
        创建或获取熔断器

        Args:
            name: 熔断器名称
            config: 熔断器配置

        Returns:
            CircuitBreaker 实例
        """
        if name not in self.breakers:
            self.breakers[name] = CircuitBreaker(name, config)

        return self.breakers[name]

    def get_breaker(self, name: str) -> Optional[CircuitBreaker]:
        """
        获取熔断器

        Args:
            name: 熔断器名称

        Returns:
            CircuitBreaker 实例或 None
        """
        return self.breakers.get(name)

    def get_all_stats(self) -> dict:
        """
        获取所有熔断器的统计信息

        Returns:
            统计信息字典
        """
        return {
            name: breaker.get_stats()
            for name, breaker in self.breakers.items()
        }

    def reset_all(self) -> None:
        """重置所有熔断器"""
        for breaker in self.breakers.values():
            breaker.reset()
        logger.info("🔄 所有熔断器已重置")
