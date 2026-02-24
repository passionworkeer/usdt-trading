"""
交易策略模块 - 多种策略实现
"""
import logging
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from abc import ABC, abstractmethod
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class TradingSignal:
    """交易信号"""
    symbol: str
    action: str  # 'buy', 'sell', 'hold'
    strength: float  # 0.0 - 1.0
    strategy: str
    reasoning: str
    indicators: Dict
    timestamp: datetime = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()


class BaseStrategy(ABC):
    """策略基类"""

    def __init__(self, name: str):
        self.name = name
        self.enabled = True

    @abstractmethod
    def analyze(self, symbol: str, price: float, price_history: List[float],
                volume: float = 0, **kwargs) -> TradingSignal:
        """分析市场并生成信号"""
        pass

    def enable(self):
        """启用策略"""
        self.enabled = True
        logger.info(f"策略 {self.name} 已启用")

    def disable(self):
        """禁用策略"""
        self.enabled = False
        logger.info(f"策略 {self.name} 已禁用")


class RSIStrategy(BaseStrategy):
    """RSI 超买超卖策略"""

    def __init__(self, oversold: float = 30, overbought: float = 70,
                 period: int = 14):
        super().__init__("RSI Strategy")
        self.oversold = oversold
        self.overbought = overbought
        self.period = period

    def _calculate_rsi(self, prices: List[float]) -> Optional[float]:
        """计算 RSI"""
        if len(prices) < self.period + 1:
            return None

        gains = []
        losses = []

        for i in range(1, len(prices)):
            change = prices[i] - prices[i - 1]
            if change > 0:
                gains.append(change)
                losses.append(0)
            else:
                gains.append(0)
                losses.append(abs(change))

        if len(gains) < self.period:
            return None

        avg_gain = sum(gains[-self.period:]) / self.period
        avg_loss = sum(losses[-self.period:]) / self.period

        if avg_loss == 0:
            return 100

        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        return rsi

    def analyze(self, symbol: str, price: float, price_history: List[float],
                volume: float = 0, **kwargs) -> TradingSignal:
        """RSI 分析"""
        if not self.enabled:
            return TradingSignal(symbol, 'hold', 0, self.name, 'Strategy disabled', {})

        rsi = self._calculate_rsi(price_history)

        if rsi is None:
            return TradingSignal(symbol, 'hold', 0, self.name, 'Insufficient data', {})

        action = 'hold'
        strength = 0
        reasoning = f'RSI: {rsi:.2f}'

        if rsi <= self.oversold:
            # 超卖 - 买入信号
            action = 'buy'
            strength = (self.oversold - rsi) / self.oversold
            strength = min(1.0, max(0.3, strength))
            reasoning += f' - Oversold (< {self.oversold})'

        elif rsi >= self.overbought:
            # 超买 - 卖出信号
            action = 'sell'
            strength = (rsi - self.overbought) / (100 - self.overbought)
            strength = min(1.0, max(0.3, strength))
            reasoning += f' - Overbought (> {self.overbought})'

        else:
            reasoning += ' - Neutral zone'

        return TradingSignal(
            symbol=symbol,
            action=action,
            strength=strength,
            strategy=self.name,
            reasoning=reasoning,
            indicators={'rsi': rsi}
        )


class MovingAverageCrossStrategy(BaseStrategy):
    """移动平均线交叉策略"""

    def __init__(self, short_period: int = 10, long_period: int = 30):
        super().__init__("MA Cross Strategy")
        self.short_period = short_period
        self.long_period = long_period
        self.last_signal = None

    def _calculate_sma(self, prices: List[float], period: int) -> Optional[float]:
        """计算简单移动平均"""
        if len(prices) < period:
            return None
        return sum(prices[-period:]) / period

    def analyze(self, symbol: str, price: float, price_history: List[float],
                volume: float = 0, **kwargs) -> TradingSignal:
        """MA 交叉分析"""
        if not self.enabled:
            return TradingSignal(symbol, 'hold', 0, self.name, 'Strategy disabled', {})

        short_ma = self._calculate_sma(price_history, self.short_period)
        long_ma = self._calculate_sma(price_history, self.long_period)

        if short_ma is None or long_ma is None:
            return TradingSignal(symbol, 'hold', 0, self.name, 'Insufficient data', {})

        action = 'hold'
        strength = 0
        reasoning = f'Short MA: {short_ma:.2f}, Long MA: {long_ma:.2f}'

        # 计算交叉情况
        cross_ratio = (short_ma - long_ma) / long_ma

        if cross_ratio > 0.02:  # 短期均线在上方 2% 以上
            action = 'buy'
            strength = min(1.0, cross_ratio * 10)
            reasoning += ' - Bullish (short MA above long MA)'

        elif cross_ratio < -0.02:  # 短期均线在下方 2% 以下
            action = 'sell'
            strength = min(1.0, abs(cross_ratio) * 10)
            reasoning += ' - Bearish (short MA below long MA)'

        else:
            reasoning += ' - Neutral (MAs close)'

        return TradingSignal(
            symbol=symbol,
            action=action,
            strength=strength,
            strategy=self.name,
            reasoning=reasoning,
            indicators={
                'short_ma': short_ma,
                'long_ma': long_ma,
                'cross_ratio': cross_ratio
            }
        )


class BollingerBandsStrategy(BaseStrategy):
    """布林带策略"""

    def __init__(self, period: int = 20, std_dev: float = 2.0):
        super().__init__("Bollinger Bands Strategy")
        self.period = period
        self.std_dev = std_dev

    def _calculate_bollinger(self, prices: List[float]) -> Tuple[Optional[float], Optional[float], Optional[float]]:
        """计算布林带"""
        if len(prices) < self.period:
            return None, None, None

        recent = prices[-self.period:]
        sma = sum(recent) / self.period

        variance = sum((p - sma) ** 2 for p in recent) / self.period
        std = variance ** 0.5

        upper = sma + (self.std_dev * std)
        lower = sma - (self.std_dev * std)

        return upper, sma, lower

    def analyze(self, symbol: str, price: float, price_history: List[float],
                volume: float = 0, **kwargs) -> TradingSignal:
        """布林带分析"""
        if not self.enabled:
            return TradingSignal(symbol, 'hold', 0, self.name, 'Strategy disabled', {})

        upper, middle, lower = self._calculate_bollinger(price_history)

        if upper is None:
            return TradingSignal(symbol, 'hold', 0, self.name, 'Insufficient data', {})

        action = 'hold'
        strength = 0
        reasoning = f'BB: Upper={upper:.2f}, Middle={middle:.2f}, Lower={lower:.2f}'

        # 计算价格在布林带中的位置
        bb_position = (price - lower) / (upper - lower) if upper != lower else 0.5

        if price <= lower:
            # 价格触及下轨 - 买入信号
            action = 'buy'
            strength = 0.8
            reasoning += f' - Price at lower band (potential bounce)'

        elif price >= upper:
            # 价格触及上轨 - 卖出信号
            action = 'sell'
            strength = 0.8
            reasoning += f' - Price at upper band (potential reversal)'

        elif bb_position < 0.2:
            # 接近下轨
            action = 'buy'
            strength = 0.5
            reasoning += f' - Near lower band'

        elif bb_position > 0.8:
            # 接近上轨
            action = 'sell'
            strength = 0.5
            reasoning += f' - Near upper band'

        else:
            reasoning += f' - Within bands'

        return TradingSignal(
            symbol=symbol,
            action=action,
            strength=strength,
            strategy=self.name,
            reasoning=reasoning,
            indicators={
                'bb_upper': upper,
                'bb_middle': middle,
                'bb_lower': lower,
                'bb_position': bb_position
            }
        )


class VolumeBreakoutStrategy(BaseStrategy):
    """成交量突破策略"""

    def __init__(self, volume_threshold: float = 2.0, price_threshold: float = 0.03):
        super().__init__("Volume Breakout Strategy")
        self.volume_threshold = volume_threshold
        self.price_threshold = price_threshold

    def analyze(self, symbol: str, price: float, price_history: List[float],
                volume: float = 0, avg_volume: float = 0, **kwargs) -> TradingSignal:
        """成交量突破分析"""
        if not self.enabled:
            return TradingSignal(symbol, 'hold', 0, self.name, 'Strategy disabled', {})

        if len(price_history) < 2 or avg_volume == 0:
            return TradingSignal(symbol, 'hold', 0, self.name, 'Insufficient data', {})

        action = 'hold'
        strength = 0
        reasoning = f'Volume: {volume:.0f}, Avg: {avg_volume:.0f}'

        # 计算价格变化
        price_change = (price - price_history[-2]) / price_history[-2] if len(price_history) >= 2 else 0

        # 计算成交量比
        volume_ratio = volume / avg_volume if avg_volume > 0 else 0

        if volume_ratio >= self.volume_threshold and price_change > self.price_threshold:
            # 放量上涨 - 买入信号
            action = 'buy'
            strength = min(1.0, volume_ratio / self.volume_threshold * 0.5)
            reasoning += f' - Volume breakout UP ({volume_ratio:.2f}x avg, +{price_change*100:.2f}%)'

        elif volume_ratio >= self.volume_threshold and price_change < -self.price_threshold:
            # 放量下跌 - 卖出信号
            action = 'sell'
            strength = min(1.0, volume_ratio / self.volume_threshold * 0.5)
            reasoning += f' - Volume breakout DOWN ({volume_ratio:.2f}x avg, {price_change*100:.2f}%)'

        else:
            reasoning += f' - Normal volume ({volume_ratio:.2f}x)'

        return TradingSignal(
            symbol=symbol,
            action=action,
            strength=strength,
            strategy=self.name,
            reasoning=reasoning,
            indicators={
                'volume_ratio': volume_ratio,
                'price_change_pct': price_change * 100
            }
        )


class GridTradingStrategy(BaseStrategy):
    """网格交易策略"""

    def __init__(self, grid_size: int = 10, grid_spacing: float = 0.02):
        super().__init__("Grid Trading Strategy")
        self.grid_size = grid_size
        self.grid_spacing = grid_spacing
        self.grid_levels = []

    def setup_grid(self, base_price: float):
        """设置网格"""
        self.grid_levels = []
        for i in range(-self.grid_size // 2, self.grid_size // 2 + 1):
            level = base_price * (1 + i * self.grid_spacing)
            self.grid_levels.append(level)
        logger.info(f"网格已设置: {len(self.grid_levels)} 个级别, 间距 {self.grid_spacing*100}%")

    def analyze(self, symbol: str, price: float, price_history: List[float],
                volume: float = 0, **kwargs) -> TradingSignal:
        """网格交易分析"""
        if not self.enabled:
            return TradingSignal(symbol, 'hold', 0, self.name, 'Strategy disabled', {})

        if not self.grid_levels:
            self.setup_grid(price)

        action = 'hold'
        strength = 0
        reasoning = f'Price: {price:.2f}'

        # 找到最近的网格级别
        closest_level = min(self.grid_levels, key=lambda x: abs(x - price))
        distance_pct = abs(price - closest_level) / closest_level

        if price < closest_level and distance_pct < self.grid_spacing * 0.5:
            # 价格低于网格线 - 买入
            action = 'buy'
            strength = 0.6
            reasoning += f' - Below grid level {closest_level:.2f}'

        elif price > closest_level and distance_pct < self.grid_spacing * 0.5:
            # 价格高于网格线 - 卖出
            action = 'sell'
            strength = 0.6
            reasoning += f' - Above grid level {closest_level:.2f}'

        return TradingSignal(
            symbol=symbol,
            action=action,
            strength=strength,
            strategy=self.name,
            reasoning=reasoning,
            indicators={
                'closest_grid_level': closest_level,
                'grid_distance_pct': distance_pct * 100
            }
        )


class StrategyManager:
    """策略管理器 - 整合多个策略"""

    def __init__(self):
        self.strategies: Dict[str, BaseStrategy] = {}
        self.weights: Dict[str, float] = {}

    def add_strategy(self, strategy: BaseStrategy, weight: float = 1.0):
        """添加策略"""
        self.strategies[strategy.name] = strategy
        self.weights[strategy.name] = weight
        logger.info(f"添加策略: {strategy.name} (权重: {weight})")

    def remove_strategy(self, name: str):
        """移除策略"""
        if name in self.strategies:
            del self.strategies[name]
            del self.weights[name]
            logger.info(f"移除策略: {name}")

    def analyze_all(self, symbol: str, price: float, price_history: List[float],
                    **kwargs) -> Tuple[TradingSignal, List[TradingSignal]]:
        """
        运行所有策略分析

        Returns:
            (综合信号, 各策略信号列表)
        """
        signals = []

        for name, strategy in self.strategies.items():
            if strategy.enabled:
                signal = strategy.analyze(symbol, price, price_history, **kwargs)
                signals.append(signal)

        if not signals:
            return TradingSignal(symbol, 'hold', 0, 'Combined', 'No active strategies', {}), []

        # 加权投票
        buy_score = 0
        sell_score = 0
        total_weight = 0
        combined_indicators = {}

        for signal in signals:
            weight = self.weights.get(signal.strategy, 1.0)
            total_weight += weight

            if signal.action == 'buy':
                buy_score += signal.strength * weight
            elif signal.action == 'sell':
                sell_score += signal.strength * weight

            combined_indicators[signal.strategy] = {
                'action': signal.action,
                'strength': signal.strength
            }

        # 计算综合信号
        buy_score /= total_weight
        sell_score /= total_weight

        if buy_score > sell_score and buy_score > 0.3:
            action = 'buy'
            strength = buy_score
            reasoning = f'Combined: {buy_score:.2f} buy vs {sell_score:.2f} sell'
        elif sell_score > buy_score and sell_score > 0.3:
            action = 'sell'
            strength = sell_score
            reasoning = f'Combined: {sell_score:.2f} sell vs {buy_score:.2f} buy'
        else:
            action = 'hold'
            strength = 0
            reasoning = f'No clear signal: {buy_score:.2f} buy vs {sell_score:.2f} sell'

        combined_signal = TradingSignal(
            symbol=symbol,
            action=action,
            strength=strength,
            strategy='Combined',
            reasoning=reasoning,
            indicators=combined_indicators
        )

        return combined_signal, signals


# 预设策略组合
def create_default_strategies() -> StrategyManager:
    """创建默认策略组合"""
    manager = StrategyManager()

    # RSI 策略
    manager.add_strategy(RSIStrategy(oversold=30, overbought=70), weight=1.0)

    # MA 交叉策略
    manager.add_strategy(MovingAverageCrossStrategy(short_period=10, long_period=30), weight=0.8)

    # 布林带策略
    manager.add_strategy(BollingerBandsStrategy(period=20, std_dev=2.0), weight=0.9)

    # 成交量突破策略
    manager.add_strategy(VolumeBreakoutStrategy(volume_threshold=2.0, price_threshold=0.03), weight=0.7)

    return manager
