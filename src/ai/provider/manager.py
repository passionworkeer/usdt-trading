"""
AI Provider 管理器

管理多个 AI Provider 实例，支持注册、切换和健康检查。
"""
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Type

from .base import (
    AIProvider,
    AIBaseProvider,
    MarketContext,
    EvidenceBasedDecision,
    TradeResult,
    ReviewReport,
)


logger = logging.getLogger(__name__)


class ProviderStatus(Enum):
    """Provider 状态"""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


@dataclass
class ProviderInfo:
    """Provider 信息"""
    name: str
    version: str
    status: ProviderStatus = ProviderStatus.UNKNOWN
    last_check: Optional[datetime] = None
    error_count: int = 0
    success_count: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)


class AIProviderError(Exception):
    """AI Provider 错误"""
    pass


class ProviderNotFoundError(AIProviderError):
    """Provider 未找到"""
    pass


class NoActiveProviderError(AIProviderError):
    """没有活动的 Provider"""
    pass


class AIProviderManager:
    """
    AI Provider 管理器

    功能：
    - 注册/注销 Provider
    - 设置/切换活动 Provider
    - 健康检查
    - 故障转移
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        初始化管理器

        Args:
            config: 管理器配置
        """
        self._providers: Dict[str, AIBaseProvider] = {}
        self._provider_info: Dict[str, ProviderInfo] = {}
        self._active_provider: Optional[str] = None
        self._config = config or {}
        self._fallback_order: List[str] = []

    @property
    def active_provider_name(self) -> Optional[str]:
        """获取活动 Provider 名称"""
        return self._active_provider

    @property
    def provider_count(self) -> int:
        """获取 Provider 数量"""
        return len(self._providers)

    @property
    def provider_names(self) -> List[str]:
        """获取所有 Provider 名称"""
        return list(self._providers.keys())

    def register(
        self,
        provider: AIBaseProvider,
        set_active: bool = False,
        initialize: bool = True,
    ) -> bool:
        """
        注册 Provider

        Args:
            provider: Provider 实例
            set_active: 是否设为活动
            initialize: 是否初始化

        Returns:
            是否成功
        """
        name = provider.name

        if name in self._providers:
            logger.warning(f"Provider '{name}' 已存在，将被覆盖")

        # 初始化 Provider
        if initialize:
            if not provider.initialize():
                logger.error(f"Provider '{name}' 初始化失败: {provider.last_error}")
                return False

        # 注册 Provider
        self._providers[name] = provider
        self._provider_info[name] = ProviderInfo(
            name=name,
            version=provider.version,
            status=ProviderStatus.UNKNOWN,
        )

        logger.info(f"已注册 Provider: {name} (v{provider.version})")

        # 设为活动
        if set_active or self._active_provider is None:
            self.set_active(name)

        return True

    def unregister(self, name: str) -> bool:
        """
        注销 Provider

        Args:
            name: Provider 名称

        Returns:
            是否成功
        """
        if name not in self._providers:
            logger.warning(f"Provider '{name}' 不存在")
            return False

        del self._providers[name]
        del self._provider_info[name]

        # 从故障转移列表中移除
        if name in self._fallback_order:
            self._fallback_order.remove(name)

        # 如果是活动 Provider，需要切换
        if self._active_provider == name:
            self._active_provider = None
            # 尝试切换到其他 Provider
            if self._fallback_order:
                self.set_active(self._fallback_order[0])
            elif self._providers:
                self.set_active(list(self._providers.keys())[0])

        logger.info(f"已注销 Provider: {name}")
        return True

    def set_active(self, name: str) -> bool:
        """
        设置活动 Provider

        Args:
            name: Provider 名称

        Returns:
            是否成功
        """
        if name not in self._providers:
            raise ProviderNotFoundError(f"Provider '{name}' 不存在")

        self._active_provider = name

        # 添加到故障转移列表（如果不存在）
        if name not in self._fallback_order:
            self._fallback_order.append(name)
        else:
            # 移到列表开头
            self._fallback_order.remove(name)
            self._fallback_order.insert(0, name)

        logger.info(f"已设置活动 Provider: {name}")
        return True

    def get_active(self) -> AIBaseProvider:
        """
        获取活动 Provider

        Returns:
            活动 Provider

        Raises:
            NoActiveProviderError: 没有活动的 Provider
        """
        if self._active_provider is None:
            raise NoActiveProviderError("没有活动的 Provider")

        return self._providers[self._active_provider]

    def get_provider(self, name: str) -> AIBaseProvider:
        """
        获取指定 Provider

        Args:
            name: Provider 名称

        Returns:
            Provider 实例

        Raises:
            ProviderNotFoundError: Provider 不存在
        """
        if name not in self._providers:
            raise ProviderNotFoundError(f"Provider '{name}' 不存在")

        return self._providers[name]

    def get_provider_info(self, name: str) -> ProviderInfo:
        """
        获取 Provider 信息

        Args:
            name: Provider 名称

        Returns:
            Provider 信息
        """
        if name not in self._provider_info:
            raise ProviderNotFoundError(f"Provider '{name}' 不存在")

        return self._provider_info[name]

    async def health_check(self, name: Optional[str] = None) -> ProviderStatus:
        """
        健康检查

        Args:
            name: Provider 名称（None 表示活动 Provider）

        Returns:
            Provider 状态
        """
        if name is None:
            if self._active_provider is None:
                return ProviderStatus.UNKNOWN
            name = self._active_provider

        if name not in self._providers:
            return ProviderStatus.UNKNOWN

        provider = self._providers[name]
        info = self._provider_info[name]

        try:
            is_healthy = await provider.health_check()
            info.status = ProviderStatus.HEALTHY if is_healthy else ProviderStatus.UNHEALTHY
            info.last_check = datetime.now()

            if is_healthy:
                info.success_count += 1
            else:
                info.error_count += 1

        except Exception as e:
            logger.error(f"Provider '{name}' 健康检查失败: {e}")
            info.status = ProviderStatus.UNHEALTHY
            info.last_check = datetime.now()
            info.error_count += 1

        return info.status

    async def health_check_all(self) -> Dict[str, ProviderStatus]:
        """
        检查所有 Provider 健康状态

        Returns:
            所有 Provider 的健康状态
        """
        results = {}

        for name in self._providers:
            results[name] = await self.health_check(name)

        return results

    async def analyze_with_fallback(
        self,
        context: MarketContext,
    ) -> EvidenceBasedDecision:
        """
        带故障转移的分析

        按故障转移顺序尝试 Provider，直到成功。

        Args:
            context: 市场上下文

        Returns:
            决策结果

        Raises:
            AIProviderError: 所有 Provider 都失败
        """
        errors = []

        for name in self._fallback_order:
            if name not in self._providers:
                continue

            provider = self._providers[name]
            info = self._provider_info[name]

            try:
                result = await provider.analyze(context)
                info.success_count += 1
                return result

            except Exception as e:
                logger.warning(f"Provider '{name}' 分析失败: {e}")
                info.error_count += 1
                errors.append(f"{name}: {str(e)}")

        raise AIProviderError(f"所有 Provider 都失败: {'; '.join(errors)}")

    async def analyze(self, context: MarketContext) -> EvidenceBasedDecision:
        """
        使用活动 Provider 分析

        Args:
            context: 市场上下文

        Returns:
            决策结果
        """
        provider = self.get_active()
        info = self._provider_info[self._active_provider]

        try:
            result = await provider.analyze(context)
            info.success_count += 1
            return result

        except Exception as e:
            info.error_count += 1
            raise

    async def review(self, trade: TradeResult) -> ReviewReport:
        """
        使用活动 Provider 复盘

        Args:
            trade: 交易结果

        Returns:
            复盘报告
        """
        provider = self.get_active()
        info = self._provider_info[self._active_provider]

        try:
            result = await provider.review(trade)
            info.success_count += 1
            return result

        except Exception as e:
            info.error_count += 1
            raise

    def set_fallback_order(self, order: List[str]) -> None:
        """
        设置故障转移顺序

        Args:
            order: Provider 名称列表（按优先级排序）
        """
        # 验证所有名称都存在
        for name in order:
            if name not in self._providers:
                raise ProviderNotFoundError(f"Provider '{name}' 不存在")

        self._fallback_order = order.copy()
        logger.info(f"已设置故障转移顺序: {order}")

    def get_statistics(self) -> Dict[str, Any]:
        """
        获取统计信息

        Returns:
            统计信息
        """
        return {
            'total_providers': len(self._providers),
            'active_provider': self._active_provider,
            'providers': {
                name: {
                    'version': info.version,
                    'status': info.status.value,
                    'last_check': info.last_check.isoformat() if info.last_check else None,
                    'error_count': info.error_count,
                    'success_count': info.success_count,
                }
                for name, info in self._provider_info.items()
            },
            'fallback_order': self._fallback_order.copy(),
        }

    def __repr__(self) -> str:
        return f"AIProviderManager(providers={self.provider_names}, active={self._active_provider})"
