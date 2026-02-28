"""
Futures Executor 测试

测试 Binance Futures 交易执行器的核心功能
"""

import pytest
from unittest.mock import Mock, MagicMock, patch
from src.exchange.futures_executor import FuturesOrderExecutor


class TestFuturesOrderExecutor:
    """测试 FuturesOrderExecutor 类"""

    @pytest.fixture
    def executor(self):
        """创建测试用的执行器"""
        with patch('ccxt.binance') as mock_binance:
            mock_exchange = MagicMock()
            # 配置 fetch_balance 返回正确的格式
            mock_exchange.fetch_balance.return_value = {
                'USDT': {'free': 1000.0, 'used': 100.0, 'total': 1100.0},
                'total': {'USDT': 1100.0},
                'free': {'USDT': 1000.0}
            }
            mock_exchange.fapiPrivateGetPositionSideDual.return_value = {'dualSidePosition': True}
            mock_binance.return_value = mock_exchange

            executor = FuturesOrderExecutor(testnet=True, max_leverage=5.0)
            return executor

    def test_initialization(self, executor):
        """测试初始化"""
        assert executor.max_leverage == 5.0
        assert executor.testnet is True
        assert executor.exchange is not None

    def test_get_balance(self, executor):
        """测试获取余额"""
        balance = executor.get_balance()

        assert balance is not None
        assert 'available_margin' in balance

    def test_check_buying_power_sufficient(self, executor):
        """测试购买力检查（充足）"""
        result, reason, available = executor.check_buying_power(
            symbol="BTCUSDT",
            quantity=0.01,
            price=50000.0,
            available_margin=10000.0
        )

        assert result is True

    def test_check_buying_power_insufficient(self, executor):
        """测试购买力检查（不足）"""
        # 请求购买力超过可用余额
        result, reason, available = executor.check_buying_power(
            symbol="BTCUSDT",
            quantity=1.0,  # 大额数量
            price=50000.0,
            available_margin=1000.0
        )

        assert result is False

    def test_get_positions(self, executor):
        """测试获取持仓"""
        executor.exchange.fetch_positions.return_value = [
            {
                'symbol': 'BTCUSDT',
                'side': 'long',
                'contracts': 0.01,
                'entryPrice': 50000.0,
                'unrealizedPnl': 100.0
            },
            {
                'symbol': 'ETHUSDT',
                'side': 'short',
                'contracts': 0.1,
                'entryPrice': 3000.0,
                'unrealizedPnl': -50.0
            }
        ]

        positions = executor.get_positions()

        assert len(positions) == 2
        assert positions[0]['symbol'] == 'BTCUSDT'
        assert positions[1]['symbol'] == 'ETHUSDT'

    def test_get_positions_with_symbol_filter(self, executor):
        """测试获取指定币种的持仓"""
        executor.exchange.fetch_positions.return_value = [
            {
                'symbol': 'BTCUSDT',
                'side': 'long',
                'contracts': 0.01
            }
        ]

        positions = executor.get_positions(symbol="BTCUSDT")

        assert len(positions) == 1
        assert positions[0]['symbol'] == 'BTCUSDT'

    def test_get_open_orders(self, executor):
        """测试获取挂单"""
        executor.exchange.fetch_open_orders.return_value = [
            {
                'id': 'order1',
                'symbol': 'BTCUSDT',
                'type': 'limit',
                'side': 'buy',
                'price': 49000.0,
                'amount': 0.01,
                'status': 'open'
            }
        ]

        orders = executor.get_open_orders()

        assert len(orders) == 1
        assert orders[0]['symbol'] == 'BTCUSDT'

    def test_max_leverage_configuration(self):
        """测试最大杠杆配置"""
        with patch('ccxt.binance') as mock_binance:
            mock_exchange = MagicMock()
            mock_exchange.fapiPrivateGetPositionSideDual.return_value = {'dualSidePosition': True}
            mock_binance.return_value = mock_exchange

            executor = FuturesOrderExecutor(testnet=True, max_leverage=20.0)
            assert executor.max_leverage == 20.0
