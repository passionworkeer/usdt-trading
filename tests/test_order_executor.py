"""
测试订单执行器
"""
import pytest
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.exchange.order_executor import OrderExecutor


class TestOrderExecutor:
    """订单执行器测试"""

    def test_init_testnet(self):
        """测试测试网初始化"""
        executor = OrderExecutor(testnet=True)
        assert executor.testnet is True
        assert executor.exchange is not None

    def test_get_ticker(self):
        """测试获取价格"""
        executor = OrderExecutor(testnet=True)
        ticker = executor.get_ticker('BTC/USDT')

        assert ticker is not None
        assert ticker['symbol'] == 'BTC/USDT'
        assert ticker['last'] > 0

    def test_get_balance(self):
        """测试获取余额 - 使用 mock"""
        with patch.object(OrderExecutor, '__init__', lambda self, testnet=True: None):
            executor = OrderExecutor(testnet=True)
            # Mock exchange 对象
            executor.exchange = MagicMock()
            executor.exchange.fetch_balance = MagicMock(return_value={
                'USDT': {'free': 1000.0, 'used': 0.0, 'total': 1000.0},
                'BTC': {'free': 0.1, 'used': 0.0, 'total': 0.1}
            })

            balance = executor.get_balance()

            assert balance is not None
            assert isinstance(balance, dict)
            assert 'USDT' in balance
            assert balance['USDT']['free'] == 1000.0

    def test_check_symbol_exists(self):
        """测试交易对检查"""
        executor = OrderExecutor(testnet=True)

        assert executor.check_symbol_exists('BTC/USDT') is True
        assert executor.check_symbol_exists('INVALID/PAIR') is False

    def test_get_trade_fee(self):
        """测试手续费计算"""
        executor = OrderExecutor(testnet=True)
        fee = executor.get_trade_fee('BTC/USDT', 0.01, 50000, 'buy')

        assert fee is not None
        assert 'rate' in fee
        assert 'cost' in fee


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
