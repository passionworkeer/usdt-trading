"""
回测引擎测试
"""
import pytest
import sys
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime, timedelta

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.quantitative.backtest_engine import (
    BacktestConfig,
    BacktestResult,
    ProfessionalBacktester,
    run_backtest,
)


class TestBacktestConfig:
    """回测配置测试"""

    def test_default_config(self):
        """测试默认配置（v4.0: 合约费率）"""
        config = BacktestConfig(
            start_date='2024-01-01',
            end_date='2024-12-31'
        )

        assert config.initial_capital == 10000
        assert config.commission_maker == 0.0002  # v4.0: 合约 Maker 0.02%
        assert config.commission_taker == 0.0005  # v4.0: 合约 Taker 0.05%
        assert config.symbols == ['BTC/USDT']
        assert config.slippage_model == 'dynamic'  # v4.0: 动态滑点
        assert config.slippage_min == 0.0015  # v4.0: 最小滑点 0.15%

    def test_custom_config(self):
        """测试自定义配置"""
        config = BacktestConfig(
            start_date='2024-01-01',
            end_date='2024-12-31',
            initial_capital=50000,
            symbols=['BTC/USDT', 'ETH/USDT'],
        )

        assert config.initial_capital == 50000
        assert len(config.symbols) == 2


class TestProfessionalBacktester:
    """专业回测引擎测试"""

    @pytest.fixture
    def sample_data(self):
        """创建样本数据"""
        dates = pd.date_range(start='2024-01-01', periods=100, freq='1h')
        np.random.seed(42)

        df = pd.DataFrame({
            'timestamp': dates,
            'open': 50000 + np.random.randn(100) * 500,
            'high': 50500 + np.random.randn(100) * 500,
            'low': 49500 + np.random.randn(100) * 500,
            'close': 50000 + np.random.randn(100) * 500,
            'volume': 1000 + np.random.randn(100) * 100,
        })
        df.set_index('timestamp', inplace=True)

        return df

    @pytest.fixture
    def backtester(self):
        """创建回测器"""
        config = BacktestConfig(
            start_date='2024-01-01',
            end_date='2024-12-31',
            initial_capital=10000,
        )
        return ProfessionalBacktester(config)

    def test_calculate_indicators(self, backtester, sample_data):
        """测试指标计算"""
        df = backtester.calculate_indicators(sample_data)

        # 检查指标是否已计算
        assert 'adx' in df.columns
        assert 'bb_upper' in df.columns
        assert 'bb_lower' in df.columns
        assert 'rsi' in df.columns
        assert 'ma_short' in df.columns
        assert 'ma_long' in df.columns
        assert 'atr' in df.columns

    def test_generate_signals(self, backtester, sample_data):
        """测试信号生成"""
        df = backtester.calculate_indicators(sample_data)
        signals = backtester.generate_signals(df)

        assert isinstance(signals, pd.Series)
        assert len(signals) == len(df)
        assert set(signals.unique()).issubset({-1, 0, 1})

    def test_run_simple_backtest(self, backtester, sample_data):
        """测试简化回测"""
        # 手动设置数据
        backtester.price_data['BTC/USDT'] = sample_data

        result = backtester.run_simple_backtest('BTC/USDT')

        assert result is not None
        assert isinstance(result, BacktestResult)
        assert isinstance(result.equity_curve, pd.Series)
        assert result.total_trades >= 0

    def test_calculate_rsi(self, backtester):
        """测试 RSI 计算"""
        prices = np.array([100, 101, 102, 101, 100, 99, 98, 99, 100, 101, 102, 103, 104, 105, 106])

        rsi = backtester._calculate_rsi(prices)

        assert len(rsi) == len(prices)
        # RSI 应该在 0-100 之间
        assert all(0 <= x <= 100 or np.isnan(x) for x in rsi if not np.isnan(x))

    def test_calculate_atr(self, backtester, sample_data):
        """测试 ATR 计算"""
        atr = backtester._calculate_atr(sample_data)

        assert isinstance(atr, pd.Series)
        assert len(atr) == len(sample_data)
        # ATR 应该是正数
        assert atr.dropna().min() > 0


class TestBacktestResult:
    """回测结果测试"""

    def test_to_dict(self):
        """测试转换为字典"""
        result = BacktestResult(
            total_return=0.15,
            sharpe_ratio=1.5,
            sortino_ratio=2.0,
            max_drawdown=-0.1,
            calmar_ratio=1.5,
            win_rate=0.6,
            profit_factor=2.0,
            total_trades=100,
            avg_trade_return=0.01,
            equity_curve=pd.Series([10000, 10100, 10200]),
            trades_df=pd.DataFrame(),
        )

        result_dict = result.to_dict()

        assert 'total_return' in result_dict
        assert result_dict['total_return'] == 0.15
        assert 'sharpe_ratio' in result_dict


class TestIntegration:
    """集成测试"""

    def test_full_backtest_workflow(self):
        """测试完整回测流程"""
        # 创建模拟数据
        dates = pd.date_range(start='2024-01-01', periods=500, freq='1h')
        np.random.seed(42)

        # 创建趋势数据（上涨）
        trend = np.linspace(50000, 55000, 500)
        noise = np.random.randn(500) * 500

        df = pd.DataFrame({
            'timestamp': dates,
            'open': trend + noise,
            'high': trend + noise + 200,
            'low': trend + noise - 200,
            'close': trend + noise,
            'volume': 1000 + np.random.randn(500) * 100,
        })
        df.set_index('timestamp', inplace=True)

        # 创建回测器
        config = BacktestConfig(
            start_date='2024-01-01',
            end_date='2024-12-31',
            initial_capital=10000,
        )
        backtester = ProfessionalBacktester(config)
        backtester.price_data['BTC/USDT'] = df

        # 运行回测
        result = backtester.run_simple_backtest('BTC/USDT')

        assert result is not None
        assert isinstance(result, BacktestResult)
        assert len(result.equity_curve) == len(df)
        assert result.total_trades >= 0

        # 验证结果合理性
        assert -1 <= result.max_drawdown <= 0  # 回撤应该是负数
        assert 0 <= result.win_rate <= 1  # 胜率应该在 0-1 之间


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
