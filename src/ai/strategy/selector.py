"""
策略选择器 - 基于 AI Provider 和风控的策略选择
"""
import logging
from typing import List, Optional, Dict, Any
from dataclasses import dataclass
from datetime import datetime

from src.ai.models import TradingSignal, ActionType, SignalStrength
from src.ai.provider.base import MarketContext, EvidenceBasedDecision
from src.ai.provider.manager import AIProviderManager
from src.risk.evidence_controller import EvidenceBasedRiskController

logger = logging.getLogger(__name__)


@dataclass
class StrategyDecision:
    """策略决策结果"""
    action: ActionType
    confidence: float
    reasoning: str
    selected_signals: List[TradingSignal]
    rejected_signals: List[TradingSignal]
    risk_validated: bool
    risk_reason: Optional[str] = None
    timestamp: datetime = datetime.now()

    def is_valid(self) -> bool:
        """检查决策是否有效"""
        return (
            self.risk_validated and
            self.action != ActionType.PASS and
            self.confidence > 0.5
        )


class StrategySelector:
    """
    策略选择器

    功能：
    - 接收多个交易信号
    - 调用 AI Provider 获取决策
    - 使用证据链风控验证决策
    - 返回最终交易决策
    """

    def __init__(
        self,
        provider_manager: AIProviderManager,
        risk_controller: EvidenceBasedRiskController,
        min_confidence: float = 0.6,
        max_signals: int = 10
    ):
        """
        初始化策略选择器

        Args:
            provider_manager: AI Provider 管理器
            risk_controller: 证据链风控控制器
            min_confidence: 最小置信度
            max_signals: 最大信号数量
        """
        self.provider_manager = provider_manager
        self.risk_controller = risk_controller
        self.min_confidence = min_confidence
        self.max_signals = max_signals
        self._stats = {
            'total_selections': 0,
            'risk_rejected': 0,
            'accepted': 0,
            'errors': 0,
        }
        self._logger = logging.getLogger(__name__)

    async def select(
        self,
        signals: List[TradingSignal],
        market_context: MarketContext
    ) -> Optional[EvidenceBasedDecision]:
        """
        从多个信号中选择并生成最终决策

        Args:
            signals: 交易信号列表
            market_context: 市场上下文

        Returns:
            基于证据的决策，如果风控不通过则返回 None
        """
        self._stats['total_selections'] += 1

        if not signals:
            self._logger.warning("没有可用的交易信号")
            return None

        # 限制信号数量
        if len(signals) > self.max_signals:
            self._logger.warning(f"信号数量超过限制 ({len(signals)} > {self.max_signals})，只取前 {self.max_signals} 个")
            signals = signals[:self.max_signals]

        try:
            # 1. 调用 AI Provider 获取决策
            provider = self.provider_manager.get_active()
            decision = await provider.analyze(market_context)

            if not decision:
                self._logger.warning("AI Provider 未返回决策")
                return None

            # 2. 调用证据链风控验证
            is_valid, reason = self.risk_controller.validate(decision)

            if not is_valid:
                self._stats['risk_rejected'] += 1
                self._logger.warning(f"决策未通过风控验证: {reason}")
                return None

            # 3. 检查置信度
            if decision.confidence < self.min_confidence:
                self._logger.warning(
                    f"决策置信度 ({decision.confidence:.2f}) 低于最小阈值 ({self.min_confidence:.2f})"
                )
                return None

            self._stats['accepted'] += 1
            self._logger.info(
                f"决策已接受: action={decision.action}, "
                f"confidence={decision.confidence:.2f}, "
                f"evidence_count={decision.evidence_count}"
            )

            return decision

        except Exception as e:
            self._stats['errors'] += 1
            self._logger.error(f"策略选择过程发生错误: {e}")
            return None

    def select_sync(
        self,
        signals: List[TradingSignal],
        market_context: MarketContext
    ) -> Optional[EvidenceBasedDecision]:
        """
        同步版本的选择方法（在异步环境中使用 run_until_complete）

        Args:
            signals: 交易信号列表
            market_context: 市场上下文

        Returns:
            基于证据的决策
        """
        import asyncio

        try:
            loop = asyncio.get_running_loop()
            # 如果在运行中的事件循环中，创建任务
            return asyncio.run_coroutine_threadsafe(
                self.select(signals, market_context),
                loop
            ).result()
        except RuntimeError:
            # 没有运行的事件循环
            return asyncio.run(self.select(signals, market_context))

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            **self._stats,
            'accept_rate': (
                self._stats['accepted'] / self._stats['total_selections'] * 100
                if self._stats['total_selections'] > 0 else 0
            ),
            'risk_rejection_rate': (
                self._stats['risk_rejected'] / self._stats['total_selections'] * 100
                if self._stats['total_selections'] > 0 else 0
            ),
        }

    def reset_stats(self) -> None:
        """重置统计信息"""
        self._stats = {
            'total_selections': 0,
            'risk_rejected': 0,
            'accepted': 0,
            'errors': 0,
        }
        self._logger.info("策略选择器统计已重置")
