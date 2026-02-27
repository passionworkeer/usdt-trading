"""
信号池 - 管理多个策略并收集交易信号
"""
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Any, Protocol, runtime_checkable

from src.ai.models import TradingSignal, ActionType, SignalStrength

logger = logging.getLogger(__name__)


class StrategyType(Enum):
    """策略类型"""
    TECHNICAL = "technical"
    FUNDAMENTAL = "fundamental"
    SENTIMENT = "sentiment"
    QUANTITATIVE = "quantitative"
    COMPOSITE = "composite"


@dataclass
class MarketData:
    """市场数据"""
    symbol: str
    timestamp: datetime
    current_price: float
    volume_24h: Optional[float] = None
    price_history: List[float] = field(default_factory=list)
    indicators: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class Strategy(Protocol):
    """策略协议"""

    @property
    def name(self) -> str:
        """策略名称"""
        ...

    @property
    def strategy_type(self) -> StrategyType:
        """策略类型"""
        ...

    @property
    def priority(self) -> int:
        """优先级（数字越小优先级越高）"""
        ...

    async def generate_signal(self, market_data: MarketData) -> Optional[TradingSignal]:
        """生成交易信号"""
        ...

    async def health_check(self) -> bool:
        """健康检查"""
        ...


class BaseStrategy(ABC):
    """策略基类"""

    def __init__(
        self,
        name: str,
        strategy_type: StrategyType,
        priority: int = 100,
        config: Optional[Dict[str, Any]] = None
    ):
        self._name = name
        self._strategy_type = strategy_type
        self._priority = priority
        self._config = config or {}
        self._enabled = True
        self._last_error: Optional[str] = None

    @property
    def name(self) -> str:
        return self._name

    @property
    def strategy_type(self) -> StrategyType:
        return self._strategy_type

    @property
    def priority(self) -> int:
        return self._priority

    @property
    def enabled(self) -> bool:
        return self._enabled

    @enabled.setter
    def enabled(self, value: bool):
        self._enabled = value

    @property
    def last_error(self) -> Optional[str]:
        return self._last_error

    @abstractmethod
    async def generate_signal(self, market_data: MarketData) -> Optional[TradingSignal]:
        """生成交易信号（子类实现）"""
        pass

    async def health_check(self) -> bool:
        """默认健康检查"""
        return self._enabled and self._last_error is None

    def _create_signal(
        self,
        symbol: str,
        action: ActionType,
        strength: SignalStrength,
        evidence_count: int,
        evidence_chain: List[str],
        metadata: Optional[Dict[str, Any]] = None
    ) -> TradingSignal:
        """创建交易信号"""
        return TradingSignal(
            symbol=symbol,
            timestamp=datetime.now(),
            signal_type=action,
            strength=strength,
            evidence_count=evidence_count,
            evidence_chain=evidence_chain,
            source=self._name,
            metadata=metadata or {}
        )


class SignalPool:
    """
    信号池 - 管理多个策略并收集交易信号

    功能：
    - 注册/注销策略
    - 并发收集所有策略的信号
    - 按信号强度排序
    - 信号去重和过滤
    """

    def __init__(self):
        self._strategies: Dict[str, Strategy] = {}
        self._stats = {
            'total_signals': 0,
            'signals_by_strategy': {},
            'signals_by_symbol': {},
        }
        self._logger = logging.getLogger(__name__)

    @property
    def strategy_count(self) -> int:
        """获取策略数量"""
        return len(self._strategies)

    @property
    def strategy_names(self) -> List[str]:
        """获取所有策略名称"""
        return list(self._strategies.keys())

    def register_strategy(self, strategy: Strategy) -> bool:
        """
        注册策略

        Args:
            strategy: 策略实例

        Returns:
            是否成功
        """
        name = strategy.name

        if name in self._strategies:
            self._logger.warning(f"策略 '{name}' 已存在，将被覆盖")

        self._strategies[name] = strategy
        self._stats['signals_by_strategy'][name] = 0

        self._logger.info(f"已注册策略: {name} (类型: {strategy.strategy_type.value}, 优先级: {strategy.priority})")
        return True

    def unregister_strategy(self, name: str) -> bool:
        """
        注销策略

        Args:
            name: 策略名称

        Returns:
            是否成功
        """
        if name not in self._strategies:
            self._logger.warning(f"策略 '{name}' 不存在")
            return False

        del self._strategies[name]
        if name in self._stats['signals_by_strategy']:
            del self._stats['signals_by_strategy'][name]

        self._logger.info(f"已注销策略: {name}")
        return True

    def get_strategy(self, name: str) -> Optional[Strategy]:
        """
        获取策略

        Args:
            name: 策略名称

        Returns:
            策略实例或 None
        """
        return self._strategies.get(name)

    def get_enabled_strategies(self) -> List[Strategy]:
        """
        获取所有启用的策略

        Returns:
            启用的策略列表
        """
        return [
            s for s in self._strategies.values()
            if getattr(s, 'enabled', True)
        ]

    async def collect_signals(self, market_data: MarketData) -> List[TradingSignal]:
        """
        收集所有策略的信号

        并发收集所有启用的策略的信号，并按信号强度排序。

        Args:
            market_data: 市场数据

        Returns:
            交易信号列表（按强度降序）
        """
        import asyncio

        strategies = self.get_enabled_strategies()
        signals: List[TradingSignal] = []

        # 并发收集信号
        async def collect_from_strategy(strategy: Strategy) -> Optional[TradingSignal]:
            try:
                signal = await strategy.generate_signal(market_data)
                if signal:
                    self._stats['total_signals'] += 1
                    self._stats['signals_by_strategy'][strategy.name] += 1
                    self._stats['signals_by_symbol'][market_data.symbol] = \
                        self._stats['signals_by_symbol'].get(market_data.symbol, 0) + 1
                return signal
            except Exception as e:
                self._logger.error(f"策略 '{strategy.name}' 生成信号失败: {e}")
                return None

        # 并发执行
        results = await asyncio.gather(*[
            collect_from_strategy(s) for s in strategies
        ])

        # 收集有效信号
        for signal in results:
            if signal is not None:
                signals.append(signal)

        # 按信号强度排序（强 > 中 > 弱），然后按证据数量
        strength_order = {
            SignalStrength.STRONG: 3,
            SignalStrength.MODERATE: 2,
            SignalStrength.WEAK: 1,
        }
        signals.sort(
            key=lambda x: (strength_order.get(x.strength, 0), x.evidence_count),
            reverse=True
        )

        self._logger.info(
            f"信号收集完成: {market_data.symbol} | "
            f"策略数: {len(strategies)} | "
            f"有效信号: {len(signals)}"
        )

        return signals

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return self._stats.copy()

    def reset_stats(self) -> None:
        """重置统计信息"""
        self._stats = {
            'total_signals': 0,
            'signals_by_strategy': {name: 0 for name in self._strategies},
            'signals_by_symbol': {},
        }
        self._logger.info("信号池统计已重置")
