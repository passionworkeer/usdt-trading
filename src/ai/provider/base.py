"""
AI Provider 抽象基类和数据模型

定义可插拔 AI Provider 接口层，支持多模型切换和统一管理。

注意: 核心数据模型已移至 src.models 包。
此模块保留用于向后兼容性和 Provider 协议定义。
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable

# 从统一模型导入
from src.models import (
    ActionType,
    ConfidenceLevel,
    Evidence,
    EvidenceBasedDecision,
    EvidenceChain,
    MarketContext,
    ReviewFinding,
    ReviewReport,
    RiskLevel,
    TradeResult,
)

# 为了向后兼容，在此处重新导出
__all__ = [
    "ActionType",
    "ConfidenceLevel",
    "RiskLevel",
    "Evidence",
    "EvidenceChain",
    "EvidenceBasedDecision",
    "MarketContext",
    "TradeResult",
    "ReviewFinding",
    "ReviewReport",
    "AIProvider",
    "AIBaseProvider",
]


# 以下是内部使用的数据类，保留在此处以保持模块完整性


@runtime_checkable
class AIProvider(Protocol):
    """AI Provider 协议（用于类型检查）"""

    @property
    def name(self) -> str:
        """Provider 名称"""
        ...

    @property
    def version(self) -> str:
        """Provider 版本"""
        ...

    async def analyze(self, context: MarketContext) -> EvidenceBasedDecision:
        """分析市场并返回决策"""
        ...

    async def review(self, trade: TradeResult) -> ReviewReport:
        """复盘交易"""
        ...

    async def health_check(self) -> bool:
        """健康检查"""
        ...


class AIBaseProvider(ABC):
    """AI Provider 抽象基类"""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        初始化 Provider

        Args:
            config: Provider 配置
        """
        self._config = config or {}
        self._initialized = False
        self._last_error: Optional[str] = None

    @property
    @abstractmethod
    def name(self) -> str:
        """Provider 名称"""
        pass

    @property
    @abstractmethod
    def version(self) -> str:
        """Provider 版本"""
        pass

    @property
    def config(self) -> Dict[str, Any]:
        """获取配置"""
        return self._config.copy()

    @property
    def is_initialized(self) -> bool:
        """是否已初始化"""
        return self._initialized

    @property
    def last_error(self) -> Optional[str]:
        """获取最后错误"""
        return self._last_error

    def initialize(self) -> bool:
        """
        初始化 Provider

        Returns:
            是否成功
        """
        try:
            self._initialized = self._do_initialize()
            return self._initialized
        except Exception as e:
            self._last_error = f"初始化失败: {str(e)}"
            self._initialized = False
            return False

    @abstractmethod
    def _do_initialize(self) -> bool:
        """
        实际初始化逻辑（子类实现）

        Returns:
            是否成功
        """
        pass

    @abstractmethod
    async def analyze(self, context: MarketContext) -> EvidenceBasedDecision:
        """
        分析市场并返回基于证据的决策

        Args:
            context: 市场上下文

        Returns:
            基于证据的决策
        """
        pass

    @abstractmethod
    async def review(self, trade: TradeResult) -> ReviewReport:
        """
        复盘交易

        Args:
            trade: 交易结果

        Returns:
            复盘报告
        """
        pass

    @abstractmethod
    async def health_check(self) -> bool:
        """
        健康检查

        Returns:
            是否健康
        """
        pass

    def get_capabilities(self) -> Dict[str, Any]:
        """
        获取 Provider 能力

        Returns:
            能力描述
        """
        return {
            'name': self.name,
            'version': self.version,
            'supports_streaming': False,
            'supports_batch': False,
            'max_context_length': None,
        }

    def _set_error(self, error: str) -> None:
        """设置错误信息"""
        self._last_error = error
