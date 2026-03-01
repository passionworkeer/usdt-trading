"""
策略选择器 - 基于 AI Provider 和证据链风控的策略选择

废除 confidence 浮点数玄学，改用结构化证据链进行决策。
"""
import logging
from typing import List, Optional, Dict, Any
from dataclasses import dataclass
from datetime import datetime

from src.ai.models import TradingSignal, ActionType, SignalStrength
from src.ai.provider.base import MarketContext, EvidenceBasedDecision
from src.ai.provider.manager import AIProviderManager
from src.risk.evidence_controller import EvidenceBasedRiskController
from src.data_sources import get_funding_source

logger = logging.getLogger(__name__)


@dataclass
class StrategyDecision:
    """策略决策结果"""
    action: ActionType
    evidence_count: int
    evidence_chain: List[str]
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
            self.evidence_count >= 2
        )


class StrategySelector:
    """
    策略选择器

    功能：
    - 接收多个交易信号
    - 调用 AI Provider 获取证据链决策
    - 使用证据链风控验证决策
    - 返回最终交易决策

    废除 confidence 浮点数，改用证据链验证：
    - 证据数量必须 >= 2
    - veto_flag 必须为 False
    - 价格参数必须合理
    """

    def __init__(
        self,
        provider_manager: AIProviderManager,
        risk_controller: EvidenceBasedRiskController,
        min_evidence_count: int = 2,
        max_signals: int = 10
    ):
        """
        初始化策略选择器

        Args:
            provider_manager: AI Provider 管理器
            risk_controller: 证据链风控控制器
            min_evidence_count: 最小证据数量要求（默认 2）
            max_signals: 最大信号数量
        """
        self.provider_manager = provider_manager
        self.risk_controller = risk_controller
        self.min_evidence_count = min_evidence_count
        self.max_signals = max_signals
        self._stats = {
            'total_selections': 0,
            'risk_rejected': 0,
            'accepted': 0,
            'errors': 0,
        }
        self._logger = logging.getLogger(__name__)
        self._funding_source = None

    async def _enhance_with_funding_data(self, context: MarketContext) -> MarketContext:
        """
        增强市场上下文 - 添加资金费率数据

        Args:
            context: 原始市场上下文

        Returns:
            增强后的上下文
        """
        try:
            # 懒加载 funding source
            if self._funding_source is None:
                self._funding_source = await get_funding_source()

            # 获取资金费率数据
            funding_data = await self._funding_source.get_comprehensive_funding(context.symbol)

            if not funding_data:
                return context

            # 增强 indicators
            enhanced_indicators = dict(context.indicators)
            enhanced_indicators['funding_rate'] = funding_data.get('funding_rate', 0)
            enhanced_indicators['funding_sentiment'] = funding_data.get('sentiment', 'neutral')
            enhanced_indicators['funding_score'] = funding_data.get('sentiment_score', 0.5)

            # 多空比
            ls = funding_data.get('long_short', {})
            if ls:
                enhanced_indicators['long_ratio'] = ls.get('long_ratio', 50)
                enhanced_indicators['short_ratio'] = ls.get('short_ratio', 50)

            # 吃单多空比
            taker = funding_data.get('taker_ratio', {})
            if taker:
                enhanced_indicators['taker_long_ratio'] = taker.get('long_buy_ratio', 1)

            # 资金费率信号
            signals = funding_data.get('signals', [])
            if signals:
                enhanced_indicators['funding_signals'] = [
                    {'type': s.get('type'), 'message': s.get('message')}
                    for s in signals
                ]

            self._logger.debug(
                f"资金费率数据已注入: {context.symbol}, "
                f"费率={funding_data.get('funding_rate', 0):.4f}%, "
                f"情绪={funding_data.get('sentiment')}"
            )

            # 创建新的 MarketContext
            return MarketContext(
                symbol=context.symbol,
                current_price=context.current_price,
                price_history=context.price_history,
                volume_24h=context.volume_24h,
                market_cap=context.market_cap,
                indicators=enhanced_indicators,
                news_sentiment=context.news_sentiment,
                timestamp=context.timestamp
            )

        except Exception as e:
            self._logger.warning(f"获取资金费率数据失败: {e}")
            return context

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
            # 0. 增强市场上下文 - 添加资金费率数据
            market_context = await self._enhance_with_funding_data(market_context)

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

            # 3. 检查证据数量（最低要求）
            if decision.evidence_count < 2:
                self._logger.warning(
                    f"证据数量不足 ({decision.evidence_count} < 2)，决策被拒绝"
                )
                return None

            self._stats['accepted'] += 1
            self._logger.info(
                f"决策已接受: action={decision.action}, "
                f"evidence_count={decision.evidence_count}, "
                f"veto_flag={decision.veto_flag}"
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
