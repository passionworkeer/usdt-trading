"""
测试风险控制器
"""
import pytest
import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.exchange.risk_manager import RiskManager, RiskConfig


class TestRiskManager:
    """风险控制器测试"""

    def test_init(self):
        """测试初始化"""
        config = RiskConfig(
            max_position_size=1000,
            max_daily_loss=500,
            max_open_positions=5,
        )
        manager = RiskManager(config=config)

        assert manager.config.max_position_size == 1000
        assert manager.config.max_daily_loss == 500
        assert manager.config.max_open_positions == 5

    def test_check_position_size_ok(self):
        """测试仓位大小检查（正常情况）"""
        manager = RiskManager(config=RiskConfig(max_position_size=1000))
        balance = {'USDT': {'free': 10000}}

        allowed, reason = manager.check_position_size('BTC/USDT', 0.01, 50000, balance)
        assert allowed is True
        assert reason == "OK"

    def test_check_position_size_too_large(self):
        """测试仓位大小检查（超限）"""
        manager = RiskManager(config=RiskConfig(max_position_size=100))
        balance = {'USDT': {'free': 10000}}

        allowed, reason = manager.check_position_size('BTC/USDT', 0.01, 50000, balance)
        assert allowed is False
        assert "超过最大限制" in reason

    def test_check_position_size_insufficient_balance(self):
        """测试仓位大小检查（余额不足）"""
        manager = RiskManager(config=RiskConfig(max_position_size=10000))
        balance = {'USDT': {'free': 100}}

        allowed, reason = manager.check_position_size('BTC/USDT', 0.01, 50000, balance)
        assert allowed is False
        assert "余额不足" in reason

    def test_check_daily_loss_ok(self):
        """测试日损失检查（正常）"""
        manager = RiskManager(config=RiskConfig(max_daily_loss=500))

        allowed, reason = manager.check_daily_loss()
        assert allowed is True

    def test_check_daily_loss_exceeded(self):
        """测试日损失检查（超限）"""
        manager = RiskManager(config=RiskConfig(max_daily_loss=500))
        manager.update_pnl(-600)

        allowed, reason = manager.check_daily_loss()
        assert allowed is False
        assert "日损失限制已达" in reason

    def test_check_open_positions_ok(self):
        """测试并发仓位检查（正常）"""
        manager = RiskManager(config=RiskConfig(max_open_positions=5))

        allowed, reason = manager.check_open_positions(3)
        assert allowed is True

    def test_check_open_positions_exceeded(self):
        """测试并发仓位检查（超限）"""
        manager = RiskManager(config=RiskConfig(max_open_positions=5))

        allowed, reason = manager.check_open_positions(5)
        assert allowed is False
        assert "已达上限" in reason

    def test_pre_trade_check_all_pass(self):
        """测试综合检查（全部通过）"""
        manager = RiskManager(config=RiskConfig(
            max_position_size=1000,
            max_daily_loss=500,
            max_open_positions=5,
        ))
        balance = {'USDT': {'free': 10000}}

        allowed, reason = manager.pre_trade_check(
            'BTC/USDT', 0.01, 50000, balance, 2
        )
        assert allowed is True
        assert "通过" in reason

    def test_get_stop_loss_price(self):
        """测试止损价格计算"""
        manager = RiskManager(config=RiskConfig(default_stop_loss_pct=-5))

        stop_loss = manager.get_stop_loss_price(100)
        assert stop_loss == 95.0

    def test_get_take_profit_price(self):
        """测试止盈价格计算"""
        manager = RiskManager(config=RiskConfig(default_take_profit_pct=15))

        take_profit = manager.get_take_profit_price(100)
        assert abs(take_profit - 115.0) < 0.01  # 浮点数精度


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
