"""
测试交易策略
"""
import pytest
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.strategies.trading_strategies import (
    RSIStrategy, MovingAverageCrossStrategy, BollingerBandsStrategy,
    VolumeBreakoutStrategy, StrategyManager
)


class TestRSIStrategy:
    """RSI 策略测试"""

    def test_oversold_buy_signal(self):
        """测试超卖买入信号"""
        strategy = RSIStrategy(oversold=30, overbought=70)

        # 创建下跌的价格序列（模拟超卖）
        prices = [100] * 7 + [90, 85, 80, 78, 76, 75, 74, 73]

        signal = strategy.analyze('TEST/USDT', 73, prices)

        assert signal.symbol == 'TEST/USDT'
        assert signal.strategy == 'RSI Strategy'
        assert 'rsi' in signal.indicators

    def test_overbought_sell_signal(self):
        """测试超买卖出信号"""
        strategy = RSIStrategy(oversold=30, overbought=70)

        # 创建上涨的价格序列（模拟超买）
        prices = [100] * 7 + [110, 115, 120, 125, 130, 135, 140, 145]

        signal = strategy.analyze('TEST/USDT', 145, prices)

        assert signal.indicators['rsi'] is not None

    def test_insufficient_data(self):
        """测试数据不足"""
        strategy = RSIStrategy()
        prices = [100, 101]

        signal = strategy.analyze('TEST/USDT', 101, prices)

        assert signal.action == 'hold'

    def test_disable_strategy(self):
        """测试禁用策略"""
        strategy = RSIStrategy()
        strategy.disable()

        prices = [100] * 20
        signal = strategy.analyze('TEST/USDT', 100, prices)

        assert signal.action == 'hold'
        assert 'disabled' in signal.reasoning.lower()


class TestMovingAverageCrossStrategy:
    """MA 交叉策略测试"""

    def test_bullish_cross(self):
        """测试看涨交叉"""
        strategy = MovingAverageCrossStrategy(short_period=5, long_period=10)

        # 短期均线在上方
        prices = list(range(90, 110))  # 上涨趋势

        signal = strategy.analyze('TEST/USDT', 109, prices)

        assert signal.action in ['buy', 'hold']
        assert 'short_ma' in signal.indicators
        assert 'long_ma' in signal.indicators

    def test_bearish_cross(self):
        """测试看跌交叉"""
        strategy = MovingAverageCrossStrategy(short_period=5, long_period=10)

        # 短期均线在下方
        prices = list(range(110, 90, -1))  # 下跌趋势

        signal = strategy.analyze('TEST/USDT', 91, prices)

        assert signal.action in ['sell', 'hold']


class TestBollingerBandsStrategy:
    """布林带策略测试"""

    def test_lower_band_bounce(self):
        """测试下轨反弹"""
        strategy = BollingerBandsStrategy(period=20, std_dev=2.0)

        # 价格触及下轨
        prices = [100 + (i % 5) for i in range(20)] + [95]

        signal = strategy.analyze('TEST/USDT', 95, prices)

        assert 'bb_upper' in signal.indicators
        assert 'bb_lower' in signal.indicators

    def test_upper_band_reversal(self):
        """测试上轨反转"""
        strategy = BollingerBandsStrategy(period=20, std_dev=2.0)

        # 价格触及上轨
        prices = [100 + (i % 5) for i in range(20)] + [110]

        signal = strategy.analyze('TEST/USDT', 110, prices)

        assert signal.indicators['bb_upper'] is not None


class TestVolumeBreakoutStrategy:
    """成交量突破策略测试"""

    def test_volume_breakout_up(self):
        """测试放量上涨"""
        strategy = VolumeBreakoutStrategy(volume_threshold=2.0)

        prices = [100] * 10 + [103]
        volume = 2000
        avg_volume = 500

        signal = strategy.analyze('TEST/USDT', 103, prices, volume=volume, avg_volume=avg_volume)

        assert signal.action in ['buy', 'hold']
        assert 'volume_ratio' in signal.indicators

    def test_volume_breakout_down(self):
        """测试放量下跌"""
        strategy = VolumeBreakoutStrategy(volume_threshold=2.0)

        prices = [100] * 10 + [97]
        volume = 2000
        avg_volume = 500

        signal = strategy.analyze('TEST/USDT', 97, prices, volume=volume, avg_volume=avg_volume)

        assert signal.action in ['sell', 'hold']


class TestStrategyManager:
    """策略管理器测试"""

    def test_add_strategy(self):
        """测试添加策略"""
        manager = StrategyManager()
        strategy = RSIStrategy()

        manager.add_strategy(strategy, weight=1.0)

        assert 'RSI Strategy' in manager.strategies
        assert manager.weights['RSI Strategy'] == 1.0

    def test_remove_strategy(self):
        """测试移除策略"""
        manager = StrategyManager()
        strategy = RSIStrategy()

        manager.add_strategy(strategy)
        manager.remove_strategy('RSI Strategy')

        assert 'RSI Strategy' not in manager.strategies

    def test_analyze_all(self):
        """测试综合分析"""
        manager = StrategyManager()
        manager.add_strategy(RSIStrategy(), weight=1.0)
        manager.add_strategy(MovingAverageCrossStrategy(), weight=0.8)

        prices = [100 + i for i in range(30)]

        combined, signals = manager.analyze_all('TEST/USDT', 129, prices)

        assert combined.symbol == 'TEST/USDT'
        assert combined.strategy == 'Combined'
        assert len(signals) == 2

    def test_create_default_strategies(self):
        """测试默认策略组合"""
        manager = StrategyManager()
        manager.add_strategy(RSIStrategy())
        manager.add_strategy(MovingAverageCrossStrategy())
        manager.add_strategy(BollingerBandsStrategy())

        assert len(manager.strategies) == 3


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
