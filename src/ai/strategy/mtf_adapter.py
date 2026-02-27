"""
MTF 策略适配器 - 将现有 MTF 策略适配为 SignalPool 可识别的 Strategy 接口
"""
import logging
from typing import Optional, Any, Dict
from datetime import datetime

from src.ai.models import TradingSignal, ActionType, SignalStrength
from src.ai.strategy.pool import BaseStrategy, StrategyType, MarketData
from src.quantitative.mtf_resonance_lock import MTFResonanceLock, MTFSignal

logger = logging.getLogger(__name__)


class MTFStrategyAdapter(BaseStrategy):
    """
    MTF 策略适配器

    将现有的 MTFResonanceLock 策略适配为 SignalPool 可识别的 Strategy 接口。

    功能：
    - 包装现有的 MTFResonanceLock
    - 将 MTFSignal 转换为 TradingSignal
    - 提供统一的 Strategy 接口
    """

    def __init__(
        self,
        priority: int = 10,
        config: Optional[Dict[str, Any]] = None
    ):
        """
        初始化 MTF 策略适配器

        Args:
            priority: 策略优先级（数字越小优先级越高）
            config: 配置字典
        """
        super().__init__(
            name="MTFResonanceLock",
            strategy_type=StrategyType.TECHNICAL,
            priority=priority,
            config=config
        )
        self._mtf_lock: Optional[MTFResonanceLock] = None
        self._initialized = False

    async def _ensure_initialized(self):
        """确保 MTF 锁已初始化"""
        if not self._initialized:
            self._mtf_lock = MTFResonanceLock()
            self._initialized = True
            logger.info("MTF 策略适配器已初始化")

    async def generate_signal(self, market_data: MarketData) -> Optional[TradingSignal]:
        """
        生成交易信号

        Args:
            market_data: 市场数据

        Returns:
            交易信号或 None
        """
        try:
            await self._ensure_initialized()

            if not self._mtf_lock:
                self._last_error = "MTF 锁未初始化"
                return None

            # 调用 MTF 共振锁获取信号
            mtf_signal: MTFSignal = await self._mtf_lock.check_triple_resonance(market_data.symbol)

            if not mtf_signal.is_locked:
                # 未锁定，无信号
                return None

            # 转换 MTF 信号为 TradingSignal
            return self._convert_mtf_signal(mtf_signal)

        except Exception as e:
            self._last_error = f"生成信号失败: {str(e)}"
            logger.error(f"MTF 策略适配器生成信号失败: {e}")
            return None

    def _convert_mtf_signal(self, mtf_signal: MTFSignal) -> TradingSignal:
        """
        将 MTF 信号转换为 TradingSignal

        Args:
            mtf_signal: MTF 信号

        Returns:
            交易信号
        """
        # 映射信号方向
        if mtf_signal.signal == 1:
            action = ActionType.BUY
        elif mtf_signal.signal == -1:
            action = ActionType.SELL
        else:
            action = ActionType.PASS

        # 构建证据链
        evidence_chain = []
        if mtf_signal.is_locked:
            evidence_chain.append(f"MTF三重共振锁定 (方向={'做多' if action == ActionType.BUY else '做空'})")
        if mtf_signal.breakthrough_price:
            evidence_chain.append(f"突破价格: {mtf_signal.breakthrough_price:.4f}")
        if mtf_signal.breakthrough_vwap:
            evidence_chain.append("VWAP突破确认")
        if mtf_signal.reasons:
            evidence_chain.extend(mtf_signal.reasons[:2])  # 最多取2个理由

        # 如果没有证据链，返回 None
        if not evidence_chain:
            return None

        # 根据实际证据数量确定 strength 和 evidence_count
        evidence_count = len(evidence_chain)
        if evidence_count >= 4:
            strength = SignalStrength.STRONG
        elif evidence_count >= 2:
            strength = SignalStrength.MODERATE
        else:
            strength = SignalStrength.WEAK

        # 构建元数据
        metadata = {
            'mtf_is_locked': mtf_signal.is_locked,
            'mtf_reasons': mtf_signal.reasons,
            'breakthrough_price': mtf_signal.breakthrough_price,
            'breakthrough_vwap': mtf_signal.breakthrough_vwap,
            'suggested_entry_price': mtf_signal.suggested_entry_price,
            'wait_for_pullback': mtf_signal.wait_for_pullback,
            'original_confidence': mtf_signal.confidence,  # 保留原始 confidence 用于调试
        }

        return TradingSignal(
            symbol=mtf_signal.symbol,
            timestamp=mtf_signal.timestamp,
            signal_type=action,
            strength=strength,
            evidence_count=evidence_count,
            evidence_chain=evidence_chain,
            source=self._name,
            metadata=metadata
        )

    async def health_check(self) -> bool:
        """健康检查"""
        try:
            await self._ensure_initialized()
            return self._mtf_lock is not None
        except Exception as e:
            self._last_error = f"健康检查失败: {str(e)}"
            return False

    async def close(self):
        """关闭适配器"""
        if self._mtf_lock:
            await self._mtf_lock.close()
            self._mtf_lock = None
            self._initialized = False
            logger.info("MTF 策略适配器已关闭")
