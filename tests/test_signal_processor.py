"""
测试信号处理器
"""
import pytest
import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.analysis.signal_processor import (
    MockSignalSource, ConfluenceAnalyzer, TradingBot
)


class TestMockSignalSource:
    """模拟信号源测试"""

    def test_add_signal(self):
        """测试添加信号"""
        source = MockSignalSource()
        source.add_signal('BTC/USDT', 'BUY', 0.01)

        signals = source.get_signals()
        assert len(signals) == 1
        assert signals[0]['symbol'] == 'BTC/USDT'
        assert signals[0]['action'] == 'BUY'
        assert signals[0]['amount'] == 0.01

    def test_get_signals_clears_buffer(self):
        """测试获取信号后清空"""
        source = MockSignalSource()
        source.add_signal('BTC/USDT', 'BUY', 0.01)

        signals1 = source.get_signals()
        assert len(signals1) == 1

        signals2 = source.get_signals()
        assert len(signals2) == 0

    def test_clear(self):
        """测试清空信号"""
        source = MockSignalSource()
        source.add_signal('BTC/USDT', 'BUY', 0.01)
        source.add_signal('ETH/USDT', 'SELL', 0.1)

        source.clear()
        signals = source.get_signals()
        assert len(signals) == 0

    def test_signal_score(self):
        """测试信号评分"""
        source = MockSignalSource()
        source.add_signal('BTC/USDT', 'BUY', 0.01, score=5)

        signals = source.get_signals()
        assert signals[0]['score'] == 5


class TestConfluenceAnalyzer:
    """Confluence 分析器测试"""

    def test_analyze_base_score(self):
        """测试基础评分"""
        analyzer = ConfluenceAnalyzer()
        signal = {'symbol': 'BTC/USDT', 'action': 'BUY', 'amount': 0.01, 'score': 4}

        score = analyzer.analyze(signal)
        assert score == 4

    def test_analyze_with_market_data(self):
        """测试带市场数据的分析"""
        analyzer = ConfluenceAnalyzer()
        signal = {'symbol': 'BTC/USDT', 'action': 'BUY', 'amount': 0.01, 'score': 3}
        market_data = {
            'rsi_oversold': True,
            'macd_bullish': True,
            'volume_surge': False,
            'high_volatility': False,
        }

        score = analyzer.analyze(signal, market_data)
        # 基础 3 + RSI 1 + MACD 1 = 5
        assert score == 5

    def test_analyze_with_volatility_penalty(self):
        """测试高波动惩罚"""
        analyzer = ConfluenceAnalyzer()
        signal = {'symbol': 'BTC/USDT', 'action': 'BUY', 'amount': 0.01, 'score': 4}
        market_data = {
            'high_volatility': True,
        }

        score = analyzer.analyze(signal, market_data)
        # 基础 4 - 1 = 3
        assert score == 3

    def test_should_execute(self):
        """测试执行判断"""
        analyzer = ConfluenceAnalyzer(min_score=4)

        assert analyzer.should_execute(5) is True
        assert analyzer.should_execute(4) is True
        assert analyzer.should_execute(3) is False
        assert analyzer.should_execute(2) is False

    def test_score_range_limit(self):
        """测试评分范围限制"""
        analyzer = ConfluenceAnalyzer()

        # 测试上限
        signal_high = {'symbol': 'BTC/USDT', 'action': 'BUY', 'amount': 0.01, 'score': 10}
        score = analyzer.analyze(signal_high)
        assert score <= 5

        # 测试下限
        signal_low = {'symbol': 'BTC/USDT', 'action': 'BUY', 'amount': 0.01, 'score': 0}
        score = analyzer.analyze(signal_low)
        assert score >= 1


class TestTradingBot:
    """交易机器人测试"""

    def test_process_signals_dry_run(self):
        """测试模拟处理信号"""
        from unittest.mock import Mock
        from src.exchange.risk_manager import RiskManager, RiskConfig

        # 创建模拟组件
        mock_executor = Mock()
        mock_executor.get_ticker.return_value = {'last': 50000}
        mock_executor.get_balance.return_value = {'USDT': {'free': 10000}}
        mock_executor.get_open_orders.return_value = []

        risk_manager = RiskManager(config=RiskConfig(max_position_size=1000))
        signal_source = MockSignalSource()

        # 添加高评分信号
        signal_source.add_signal('BTC/USDT', 'BUY', 0.01, score=5)

        # 创建交易机器人
        bot = TradingBot(
            executor=mock_executor,
            risk_manager=risk_manager,
            signal_source=signal_source,
            analyzer=ConfluenceAnalyzer(min_score=4)
        )

        # 处理信号（模拟模式）
        results = bot.process_signals(dry_run=True)

        assert results['processed'] == 1
        assert results['executed'] == 1
        assert results['rejected'] == 0

    def test_process_signals_low_score_rejected(self):
        """测试低评分信号被拒绝"""
        from unittest.mock import Mock
        from src.exchange.risk_manager import RiskManager, RiskConfig

        mock_executor = Mock()
        mock_executor.get_ticker.return_value = {'last': 50000}
        mock_executor.get_balance.return_value = {'USDT': {'free': 10000}}
        mock_executor.get_open_orders.return_value = []

        risk_manager = RiskManager(config=RiskConfig(max_position_size=1000))
        signal_source = MockSignalSource()

        # 添加低评分信号
        signal_source.add_signal('BTC/USDT', 'BUY', 0.01, score=2)

        bot = TradingBot(
            executor=mock_executor,
            risk_manager=risk_manager,
            signal_source=signal_source,
            analyzer=ConfluenceAnalyzer(min_score=4)
        )

        results = bot.process_signals(dry_run=True)

        assert results['processed'] == 1
        assert results['executed'] == 0
        assert results['rejected'] == 1

    def test_get_stats(self):
        """测试获取统计信息"""
        from unittest.mock import Mock
        from src.exchange.risk_manager import RiskManager, RiskConfig

        mock_executor = Mock()
        risk_manager = RiskManager()
        signal_source = MockSignalSource()

        bot = TradingBot(
            executor=mock_executor,
            risk_manager=risk_manager,
            signal_source=signal_source,
        )

        stats = bot.get_stats()

        assert 'processed' in stats
        assert 'executed' in stats
        assert 'rejected' in stats
        assert 'execution_rate' in stats
        assert 'risk_stats' in stats


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
