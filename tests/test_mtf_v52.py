"""
v5.2 MTF 三重共振测试
"""
import pytest
import asyncio
import sys
import os

# 添加 src 到路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


class TestMTFResonanceLock:
    """测试 MTF 三重共振锁"""

    @pytest.fixture
    def mtf_lock(self):
        """创建 MTF 锁实例"""
        from src.quantitative.mtf_resonance_lock import MTFResonanceLock
        return MTFResonanceLock()

    def test_mtf_signal_dataclass(self):
        """测试 MTFSignal 数据类"""
        from src.quantitative.mtf_resonance_lock import MTFSignal
        from datetime import datetime

        signal = MTFSignal(
            symbol='BTC/USDT',
            signal=1,
            confidence=0.8,
            reasons=['Test reason'],
            timestamp=datetime.now(),
            is_locked=True,
            breakthrough_price=50000.0,
            breakthrough_vwap=50100.0,
            suggested_entry_price=50100.0,
            wait_for_pullback=True,
            rsi=45.0,
            bb_position=0.5,
            atr=150.0,
            stop_loss_price=49500.0,
            take_profit_price=51300.0,
            risk_reward_ratio=2.4,
            suggested_position_size=1.0
        )

        assert signal.symbol == 'BTC/USDT'
        assert signal.signal == 1
        assert signal.rsi == 45.0
        assert signal.suggested_position_size == 1.0  # 全仓

    def test_position_manager_defaults(self):
        """测试仓位管理器默认参数"""
        from src.quantitative.mtf_resonance_lock import PositionManager

        pm = PositionManager()
        assert pm.max_position_pct == 1.0  # 全仓
        assert pm.min_risk_reward == 2.0  # 最小 2:1

    def test_calculate_stop_loss_long(self):
        """测试做多止损计算"""
        from src.quantitative.mtf_resonance_lock import PositionManager

        pm = PositionManager()
        entry = 50000
        atr = 500
        direction = 1  # 做多

        sl = pm.calculate_stop_loss(entry, direction, atr, atr_multiplier=2.0)
        assert sl == 49000  # 50000 - 500*2

    def test_calculate_stop_loss_short(self):
        """测试做空止损计算"""
        from src.quantitative.mtf_resonance_lock import PositionManager

        pm = PositionManager()
        entry = 50000
        atr = 500
        direction = -1  # 做空

        sl = pm.calculate_stop_loss(entry, direction, atr, atr_multiplier=2.0)
        assert sl == 51000  # 50000 + 500*2

    def test_calculate_take_profit(self):
        """测试止盈计算"""
        from src.quantitative.mtf_resonance_lock import PositionManager

        pm = PositionManager()
        entry = 50000
        direction = 1  # 做多
        stop_loss = 49000

        tp = pm.calculate_take_profit(entry, direction, stop_loss)
        # 止盈 = 50000 + (50000-49000)*2 = 52000
        assert tp == 52000

    @pytest.mark.asyncio
    async def test_fetch_4h_trend(self):
        """测试获取 4H 趋势"""
        from src.quantitative.mtf_resonance_lock import MTFResonanceLock

        lock = MTFResonanceLock()
        trend, reason = await lock.fetch_4h_trend('BTC/USDT')

        # 应该返回趋势值和原因
        assert trend in [-1, 0, 1]
        assert isinstance(reason, str)
        assert len(reason) > 0

    @pytest.mark.asyncio
    async def test_fetch_funding_and_oi(self):
        """测试获取资金费率和 OI"""
        from src.quantitative.mtf_resonance_lock import MTFResonanceLock

        lock = MTFResonanceLock()
        signal, reason = await lock.fetch_funding_and_oi('BTC/USDT')

        # 应该返回信号和原因
        assert signal in [-1, 0, 1]
        assert isinstance(reason, str)

    @pytest.mark.asyncio
    async def test_fetch_15m_volume_spike(self):
        """测试获取 15m 放量"""
        from src.quantitative.mtf_resonance_lock import MTFResonanceLock

        lock = MTFResonanceLock()
        signal, reason, entry_info = await lock.fetch_15m_volume_spike('BTC/USDT')

        # 应该返回信号、入场信息
        assert signal in [-1, 0, 1]
        assert isinstance(reason, str)

        # v5.2: 检查是否有 RSI、BB、ATR
        if entry_info:
            assert 'rsi' in entry_info
            assert 'bb_position' in entry_info
            assert 'atr' in entry_info

    @pytest.mark.asyncio
    async def test_check_triple_resonance(self):
        """测试三重共振检查"""
        from src.quantitative.mtf_resonance_lock import MTFResonanceLock

        lock = MTFResonanceLock()
        signal = await lock.check_triple_resonance('BTC/USDT')

        # 应该返回信号对象
        assert signal.symbol == 'BTC/USDT'
        assert signal.signal in [-1, 0, 1]
        assert signal.confidence >= 0

        # v5.2: 检查风控字段
        if signal.is_locked:
            # 如果锁定，应该有风控信息
            pass
        else:
            # 如果未锁定，检查原因
            print(f"未锁定原因: {signal.reasons}")


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
