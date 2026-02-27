"""
交易引擎主循环 - Python 交易大脑 (Orchestrator)

这是系统的核心控制模块，拥有绝对控制权，负责调度所有模块执行交易流程。
"""
import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Protocol, Tuple, runtime_checkable

from src.ai.models import TradingSignal
from src.ai.provider.base import EvidenceBasedDecision, TradeResult
from src.ai.provider.manager import AIProviderManager
from src.risk.evidence_controller import EvidenceBasedRiskController


logger = logging.getLogger(__name__)


# ============================================================================
# Protocol 定义 - 组件接口
# ============================================================================

@runtime_checkable
class SignalPool(Protocol):
    """信号池协议"""

    async def collect_signals(self) -> List[TradingSignal]:
        """收集所有策略的信号"""
        ...


@runtime_checkable
class StrategySelector(Protocol):
    """策略选择器协议"""

    async def select(self, signals: List[TradingSignal]) -> Optional[EvidenceBasedDecision]:
        """基于信号选择策略并生成决策"""
        ...


@runtime_checkable
class ExchangeExecutor(Protocol):
    """交易所执行器协议"""

    async def execute(self, decision: EvidenceBasedDecision) -> TradeResult:
        """执行交易决策"""
        ...


@runtime_checkable
class ReviewSystem(Protocol):
    """复盘系统协议"""

    async def record_trade(self, trade: TradeResult) -> None:
        """记录交易结果"""
        ...


# ============================================================================
# 交易引擎
# ============================================================================

@dataclass
class EngineStats:
    """引擎统计信息"""
    start_time: Optional[datetime] = None
    tick_count: int = 0
    signal_count: int = 0
    decision_count: int = 0
    trade_count: int = 0
    error_count: int = 0
    last_tick_time: Optional[datetime] = None


class TradingEngine:
    """
    Python 交易大脑 (Orchestrator)

    - 拥有绝对控制权
    - while True 主循环
    - 调度所有模块
    """

    def __init__(
        self,
        signal_pool: SignalPool,
        strategy_selector: StrategySelector,
        risk_controller: EvidenceBasedRiskController,
        exchange_executor: ExchangeExecutor,
        review_system: ReviewSystem,
        config: Dict[str, Any]
    ):
        """
        初始化交易引擎

        Args:
            signal_pool: 信号池，用于收集各策略信号
            strategy_selector: 策略选择器，AI 决策模块
            risk_controller: 风控控制器，验证决策
            exchange_executor: 交易所执行器，执行交易
            review_system: 复盘系统，记录交易
            config: 引擎配置
        """
        self.signal_pool = signal_pool
        self.strategy_selector = strategy_selector
        self.risk_controller = risk_controller
        self.exchange_executor = exchange_executor
        self.review_system = review_system
        self.config = config

        self._running = False
        self._shutdown_event = asyncio.Event()
        self._stats = EngineStats()

        logger.info("TradingEngine 初始化完成")
        logger.info(f"  - Tick 间隔: {config.get('tick_interval', 300)} 秒")
        logger.info(f"  - Dry run: {config.get('dry_run', True)}")

    @property
    def is_running(self) -> bool:
        """引擎是否在运行"""
        return self._running

    @property
    def stats(self) -> EngineStats:
        """获取统计信息"""
        return self._stats

    async def run(self) -> None:
        """
        主循环

        无限循环执行交易流程，直到收到关闭信号。
        """
        self._running = True
        self._stats.start_time = datetime.now()

        logger.info("=" * 60)
        logger.info("交易引擎启动")
        logger.info("=" * 60)

        try:
            while self._running and not self._shutdown_event.is_set():
                try:
                    await self._tick()
                    self._stats.tick_count += 1
                    self._stats.last_tick_time = datetime.now()

                except Exception as e:
                    self._stats.error_count += 1
                    logger.error(f"Tick error: {e}", exc_info=True)

                # 等待下次循环 (默认 5 分钟)
                try:
                    await asyncio.wait_for(
                        self._shutdown_event.wait(),
                        timeout=self.config.get('tick_interval', 300)
                    )
                except asyncio.TimeoutError:
                    pass  # 正常超时，继续循环

        finally:
            self._running = False
            logger.info("=" * 60)
            logger.info("交易引擎停止")
            logger.info(f"运行统计: {self._get_stats_summary()}")
            logger.info("=" * 60)

    async def _tick(self) -> None:
        """
        单次交易循环

        执行完整的交易流程：
        1. 信号池收集信号
        2. AI 决策
        3. 风控验证
        4. 执行交易
        5. 记录复盘
        """
        logger.debug("-" * 40)
        logger.debug("开始新 tick")

        # 1. 策略池收集信号
        try:
            signals = await self.signal_pool.collect_signals()
        except Exception as e:
            logger.error(f"信号收集失败: {e}")
            return

        if not signals:
            logger.debug("无信号，跳过")
            return

        self._stats.signal_count += len(signals)
        logger.info(f"收集到 {len(signals)} 个信号")

        # 2. AI 决策 (证据链)
        try:
            decision = await self.strategy_selector.select(signals)
        except Exception as e:
            logger.error(f"AI 决策失败: {e}")
            return

        if not decision:
            logger.info("AI 决策未通过")
            return

        self._stats.decision_count += 1
        logger.info(
            f"AI 决策: {decision.action} "
            f"(证据数: {decision.evidence_count})"
        )

        # 3. 证据链风控验证
        is_valid, reason = self.risk_controller.validate(decision)
        if not is_valid:
            logger.warning(f"风控拦截: {reason}")
            return

        logger.info("风控验证通过")

        # 4. 执行交易
        try:
            trade_result = await self.exchange_executor.execute(decision)
            self._stats.trade_count += 1
            logger.info(f"交易执行成功: {trade_result.trade_id}")
        except Exception as e:
            logger.error(f"交易执行失败: {e}")
            return

        # 5. 记录复盘
        try:
            await self.review_system.record_trade(trade_result)
            logger.info("复盘记录完成")
        except Exception as e:
            logger.error(f"复盘记录失败: {e}")
            # 复盘失败不影响交易结果

    async def shutdown(self) -> None:
        """
        优雅关闭

        设置关闭标志，等待当前 tick 完成后退出主循环。
        """
        logger.info("正在关闭交易引擎...")
        self._running = False
        self._shutdown_event.set()

    def _get_stats_summary(self) -> str:
        """获取统计摘要"""
        if not self._stats.start_time:
            return "未启动"

        duration = datetime.now() - self._stats.start_time
        return (
            f"运行时长={duration}, "
            f"Tick数={self._stats.tick_count}, "
            f"信号数={self._stats.signal_count}, "
            f"决策数={self._stats.decision_count}, "
            f"交易数={self._stats.trade_count}, "
            f"错误数={self._stats.error_count}"
        )

    def __repr__(self) -> str:
        status = "running" if self._running else "stopped"
        return f"TradingEngine(status={status}, trades={self._stats.trade_count})"


# ============================================================================
# 便捷函数
# ============================================================================

def create_trading_engine(
    signal_pool: SignalPool,
    strategy_selector: StrategySelector,
    risk_controller: EvidenceBasedRiskController,
    exchange_executor: ExchangeExecutor,
    review_system: ReviewSystem,
    tick_interval: int = 300,
    dry_run: bool = True,
    **kwargs
) -> TradingEngine:
    """
    创建交易引擎的便捷函数

    Args:
        signal_pool: 信号池
        strategy_selector: 策略选择器
        risk_controller: 风控控制器
        exchange_executor: 交易所执行器
        review_system: 复盘系统
        tick_interval: Tick 间隔（秒）
        dry_run: 是否模拟运行
        **kwargs: 其他配置

    Returns:
        配置好的交易引擎实例
    """
    config = {
        'tick_interval': tick_interval,
        'dry_run': dry_run,
        **kwargs
    }

    return TradingEngine(
        signal_pool=signal_pool,
        strategy_selector=strategy_selector,
        risk_controller=risk_controller,
        exchange_executor=exchange_executor,
        review_system=review_system,
        config=config
    )
