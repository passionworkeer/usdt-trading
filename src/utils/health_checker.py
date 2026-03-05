"""
交易所健康检查器（Exchange Health Checker）

P1-17: 实现黑盒事件应对（交易所宕机、网络故障等）

功能：
1. REST API 健康检查
2. WebSocket 连接检查
3. 交易权限验证
4. 订单簿流动性检查
5. 延迟监控
"""
import logging
import asyncio
import time
from typing import Dict, List, Optional
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from functools import partial

logger = logging.getLogger(__name__)


class HealthStatus(Enum):
    """健康状态"""
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"  # 部分功能降级
    UNHEALTHY = "UNHEALTHY"  # 不健康
    CRITICAL = "CRITICAL"  # 严重故障


@dataclass
class HealthCheckResult:
    """健康检查结果"""
    status: HealthStatus
    timestamp: datetime
    details: Dict[str, bool]
    latency_ms: Dict[str, float]
    errors: List[str]

    def is_healthy(self) -> bool:
        """是否健康（允许部分降级）"""
        return self.status in [HealthStatus.HEALTHY, HealthStatus.DEGRADED]

    def can_trade(self) -> bool:
        """是否允许交易"""
        return self.status == HealthStatus.HEALTHY


class ExchangeHealthChecker:
    """
    交易所健康检查器

    检查项：
    1. REST API 可用性
    2. 交易权限
    3. 订单簿流动性
    4. API 延迟
    """

    def __init__(self, exchange, test_symbols: Optional[List[str]] = None):
        """
        初始化健康检查器

        Args:
            exchange: CCXT exchange 实例
            test_symbols: 用于测试流动性的交易对列表
        """
        self.exchange = exchange

        # 默认测试交易对（高流动性）
        self.test_symbols = test_symbols or ['BTC/USDT', 'ETH/USDT']

        # 健康状态缓存
        self.last_check: Optional[HealthCheckResult] = None
        self.check_interval = 30  # 秒

        # 延迟阈值（毫秒）
        self.latency_thresholds = {
            'rest_api': 1000,  # REST API 超过 1s 警告
            'order_book': 500,  # 订单簿超过 500ms 警告
        }

        logger.info("✅ 交易所健康检查器已初始化")

    async def _safe_exchange_call(self, method_name: str, *args, **kwargs):
        """
        安全地调用 exchange 方法（自动处理同步/异步）

        Args:
            method_name: 方法名
            *args: 位置参数
            **kwargs: 关键字参数

        Returns:
            方法返回值
        """
        method = getattr(self.exchange, method_name)
        if asyncio.iscoroutinefunction(method):
            # 异步方法，直接 await
            return await method(*args, **kwargs)
        else:
            # 同步方法，在线程池中执行以避免阻塞
            loop = asyncio.get_event_loop()
            # 使用 partial 绑定关键字参数
            if kwargs:
                func = partial(method, *args, **kwargs)
                return await loop.run_in_executor(None, func)
            else:
                return await loop.run_in_executor(None, method, *args)

    async def health_check(self) -> HealthCheckResult:
        """
        执行完整的健康检查

        Returns:
            HealthCheckResult 对象
        """
        details = {}
        latency_ms = {}
        errors = []

        logger.debug("🔍 开始交易所健康检查...")

        # 1. REST API 检查
        rest_healthy, rest_latency, rest_error = await self._check_rest_api()
        details['rest_api'] = rest_healthy
        latency_ms['rest_api'] = rest_latency
        if rest_error:
            errors.append(rest_error)

        # 2. 交易权限检查
        trade_healthy, trade_latency, trade_error = await self._check_trading_permission()
        details['trading_allowed'] = trade_healthy
        latency_ms['trading'] = trade_latency
        if trade_error:
            errors.append(trade_error)

        # 3. 订单簿流动性检查
        ob_healthy, ob_latency, ob_error = await self._check_order_book_liquidity()
        details['order_book'] = ob_healthy
        latency_ms['order_book'] = ob_latency
        if ob_error:
            errors.append(ob_error)

        # 4. 判断整体健康状态
        status = self._determine_status(details, latency_ms)

        # 构建结果
        result = HealthCheckResult(
            status=status,
            timestamp=datetime.now(),
            details=details,
            latency_ms=latency_ms,
            errors=errors
        )

        # 缓存结果
        self.last_check = result

        # 日志输出
        self._log_health_result(result)

        return result

    async def _check_rest_api(self) -> tuple[bool, float, Optional[str]]:
        """
        检查 REST API 可用性

        Returns:
            (是否健康, 延迟ms, 错误信息)
        """
        try:
            start_time = time.time()

            # 尝试获取服务器时间（最轻量的 API 调用）
            if hasattr(self.exchange, 'fetch_time'):
                await self._safe_exchange_call('fetch_time')
            else:
                # fallback: 获取 ticker
                await self._safe_exchange_call('fetch_ticker', self.test_symbols[0])

            latency = (time.time() - start_time) * 1000

            # 检查延迟
            if latency > self.latency_thresholds['rest_api']:
                return False, latency, f"REST API 延迟过高: {latency:.0f}ms"

            return True, latency, None

        except Exception as e:
            error_msg = f"REST API 不可用: {str(e)}"
            logger.error(error_msg)
            return False, 0, error_msg

    async def _check_trading_permission(self) -> tuple[bool, float, Optional[str]]:
        """
        检查交易权限

        Returns:
            (是否允许交易, 延迟ms, 错误信息)
        """
        try:
            start_time = time.time()

            # 尝试获取账户余额
            await self._safe_exchange_call('fetch_balance')

            latency = (time.time() - start_time) * 1000

            return True, latency, None

        except Exception as e:
            error_msg = f"交易权限检查失败: {str(e)}"
            logger.error(error_msg)
            return False, 0, error_msg

    async def _check_order_book_liquidity(self) -> tuple[bool, float, Optional[str]]:
        """
        检查订单簿流动性

        Returns:
            (流动性健康, 延迟ms, 错误信息)
        """
        try:
            start_time = time.time()

            # 获取订单簿（只获取少量数据）
            symbol = self.test_symbols[0]
            order_book = await self._safe_exchange_call('fetch_order_book', symbol, limit=5)

            latency = (time.time() - start_time) * 1000

            # 检查买卖盘是否有足够的深度
            has_bids = len(order_book.get('bids', [])) > 0
            has_asks = len(order_book.get('asks', [])) > 0

            if not has_bids or not has_asks:
                return False, latency, f"订单簿流动性不足 (bids: {has_bids}, asks: {has_asks})"

            # 检查延迟
            if latency > self.latency_thresholds['order_book']:
                return False, latency, f"订单簿延迟过高: {latency:.0f}ms"

            return True, latency, None

        except Exception as e:
            error_msg = f"订单簿检查失败: {str(e)}"
            logger.error(error_msg)
            return False, 0, error_msg

    def _determine_status(self, details: Dict[str, bool], latency_ms: Dict[str, float]) -> HealthStatus:
        """
        根据检查结果确定整体健康状态

        Args:
            details: 各项检查结果
            latency_ms: 各项延迟

        Returns:
            HealthStatus 枚举值
        """
        # CRITICAL: REST API 不可用
        if not details.get('rest_api', False):
            return HealthStatus.CRITICAL

        # CRITICAL: 交易权限不可用
        if not details.get('trading_allowed', False):
            return HealthStatus.CRITICAL

        # UNHEALTHY: 订单簿流动性不足
        if not details.get('order_book', False):
            return HealthStatus.UNHEALTHY

        # DEGRADED: 延迟过高但功能正常
        high_latency = any(
            latency > threshold
            for key, latency in latency_ms.items()
            if key in self.latency_thresholds
            if latency > self.latency_thresholds[key]
        )
        if high_latency:
            return HealthStatus.DEGRADED

        # 全部正常
        return HealthStatus.HEALTHY

    def _log_health_result(self, result: HealthCheckResult) -> None:
        """记录健康检查结果"""
        status_emoji = {
            HealthStatus.HEALTHY: "✅",
            HealthStatus.DEGRADED: "⚠️",
            HealthStatus.UNHEALTHY: "❌",
            HealthStatus.CRITICAL: "🚨",
        }

        emoji = status_emoji.get(result.status, "❓")

        logger.info(f"{emoji} 交易所健康检查: {result.status.value}")

        # 详细信息
        for key, value in result.details.items():
            status_icon = "✅" if value else "❌"
            latency = result.latency_ms.get(key, 0)
            logger.info(f"  {status_icon} {key}: {value} ({latency:.0f}ms)")

        # 错误信息
        for error in result.errors:
            logger.warning(f"  ⚠️ {error}")

    def get_status_summary(self) -> Dict:
        """
        获取健康状态摘要（用于监控面板）

        Returns:
            状态摘要字典
        """
        if self.last_check is None:
            return {
                'status': 'UNKNOWN',
                'timestamp': None,
                'can_trade': False,
            }

        return {
            'status': self.last_check.status.value,
            'timestamp': self.last_check.timestamp.isoformat(),
            'can_trade': self.last_check.can_trade(),
            'details': self.last_check.details,
            'latency_ms': self.last_check.latency_ms,
            'errors': self.last_check.errors,
        }
