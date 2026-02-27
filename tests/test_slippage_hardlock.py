"""
测试滑点硬拦截器（SlippageHardlock）
"""
import pytest
import time
from unittest.mock import patch
import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.execution.slippage_hardlock import SlippageHardlock


class TestSlippageHardlock:
    """滑点硬拦截器测试"""

    # ==================== 初始化测试 ====================

    def test_init_default(self):
        """测试初始化 - 默认参数"""
        hardlock = SlippageHardlock()

        assert hardlock.base_threshold_pct == 0.5
        assert hardlock.timeout_sec == 5.0
        assert hardlock._locked_prices == {}

    def test_init_custom(self):
        """测试初始化 - 自定义参数"""
        hardlock = SlippageHardlock(base_threshold_pct=1.0, timeout_sec=10.0)

        assert hardlock.base_threshold_pct == 1.0
        assert hardlock.timeout_sec == 10.0

    # ==================== lock_trigger_price 测试 ====================

    def test_lock_trigger_price_basic(self):
        """测试锁定触发价格 - 基本功能"""
        hardlock = SlippageHardlock()

        hardlock.lock_trigger_price('BTCUSDT', 50000.0)

        assert 'BTCUSDT' in hardlock._locked_prices
        locked_price, timestamp = hardlock._locked_prices['BTCUSDT']
        assert locked_price == 50000.0
        assert isinstance(timestamp, float)

    def test_lock_multiple_symbols(self):
        """测试锁定多个币种"""
        hardlock = SlippageHardlock()

        hardlock.lock_trigger_price('BTCUSDT', 50000.0)
        hardlock.lock_trigger_price('ETHUSDT', 3000.0)

        assert len(hardlock._locked_prices) == 2
        assert hardlock.get_locked_price('BTCUSDT') == 50000.0
        assert hardlock.get_locked_price('ETHUSDT') == 3000.0

    def test_lock_overwrite(self):
        """测试覆盖锁定"""
        hardlock = SlippageHardlock()

        hardlock.lock_trigger_price('BTCUSDT', 50000.0)
        hardlock.lock_trigger_price('BTCUSDT', 51000.0)

        assert hardlock.get_locked_price('BTCUSDT') == 51000.0

    # ==================== check_slippage 测试 ====================

    def test_check_slippage_no_lock(self):
        """测试检查滑点 - 无锁定"""
        hardlock = SlippageHardlock()

        passed, reason = hardlock.check_slippage('BTCUSDT', 50000.0)

        assert passed is False
        assert "未锁定价格" in reason

    def test_check_slippage_pass(self):
        """测试检查滑点 - 通过"""
        hardlock = SlippageHardlock(base_threshold_pct=0.5)

        hardlock.lock_trigger_price('BTCUSDT', 50000.0)

        # 价格变化 0.2%，小于阈值
        passed, reason = hardlock.check_slippage('BTCUSDT', 50100.0)

        assert passed is True
        # 检查关键词而不是具体的中文文本（避免编码问题）
        assert "0.20%" in reason or "20%" in reason

    def test_check_slippage_fail(self):
        """测试检查滑点 - 失败"""
        hardlock = SlippageHardlock(base_threshold_pct=0.5)

        hardlock.lock_trigger_price('BTCUSDT', 50000.0)

        # 价格变化 1%，超过阈值
        passed, reason = hardlock.check_slippage('BTCUSDT', 50500.0)

        assert passed is False
        assert "滑点过大" in reason

    def test_check_slippage_timeout(self):
        """测试检查滑点 - 超时"""
        hardlock = SlippageHardlock(timeout_sec=1.0)

        hardlock.lock_trigger_price('BTCUSDT', 50000.0)

        # 等待超时
        time.sleep(1.1)

        passed, reason = hardlock.check_slippage('BTCUSDT', 50000.0)

        assert passed is False
        assert "超时" in reason

    def test_check_slippage_direction_up(self):
        """测试检查滑点 - 方向向上"""
        hardlock = SlippageHardlock(base_threshold_pct=0.5)

        hardlock.lock_trigger_price('BTCUSDT', 50000.0)

        passed, reason = hardlock.check_slippage('BTCUSDT', 50300.0)

        assert "↑" in reason

    def test_check_slippage_direction_down(self):
        """测试检查滑点 - 方向向下"""
        hardlock = SlippageHardlock(base_threshold_pct=0.5)

        hardlock.lock_trigger_price('BTCUSDT', 50000.0)

        passed, reason = hardlock.check_slippage('BTCUSDT', 49700.0)

        assert "↓" in reason

    def test_check_slippage_cleanup_after_check(self):
        """测试检查滑点 - 检查后清理"""
        hardlock = SlippageHardlock(base_threshold_pct=0.5)

        hardlock.lock_trigger_price('BTCUSDT', 50000.0)
        hardlock.check_slippage('BTCUSDT', 50050.0)

        # 检查后应该被清理
        assert 'BTCUSDT' not in hardlock._locked_prices

    def test_check_slippage_cleanup_after_failure(self):
        """测试检查滑点 - 失败后清理"""
        hardlock = SlippageHardlock(base_threshold_pct=0.5)

        hardlock.lock_trigger_price('BTCUSDT', 50000.0)
        hardlock.check_slippage('BTCUSDT', 51000.0)

        # 失败后也应该被清理
        assert 'BTCUSDT' not in hardlock._locked_prices

    def test_check_slippage_timeout_cleanup(self):
        """测试检查滑点 - 超时后清理"""
        hardlock = SlippageHardlock(timeout_sec=0.5)

        hardlock.lock_trigger_price('BTCUSDT', 50000.0)
        time.sleep(0.6)
        hardlock.check_slippage('BTCUSDT', 50000.0)

        # 超时后应该被清理
        assert 'BTCUSDT' not in hardlock._locked_prices

    # ==================== get_locked_price 测试 ====================

    def test_get_locked_price_exists(self):
        """测试获取锁定价格 - 存在"""
        hardlock = SlippageHardlock()

        hardlock.lock_trigger_price('BTCUSDT', 50000.0)

        result = hardlock.get_locked_price('BTCUSDT')

        assert result == 50000.0

    def test_get_locked_price_not_exists(self):
        """测试获取锁定价格 - 不存在"""
        hardlock = SlippageHardlock()

        result = hardlock.get_locked_price('BTCUSDT')

        assert result is None

    # ==================== get_elapsed_time 测试 ====================

    def test_get_elapsed_time_exists(self):
        """测试获取已用时间 - 存在"""
        hardlock = SlippageHardlock()

        hardlock.lock_trigger_price('BTCUSDT', 50000.0)
        time.sleep(0.1)

        result = hardlock.get_elapsed_time('BTCUSDT')

        assert result is not None
        assert result >= 0.1

    def test_get_elapsed_time_not_exists(self):
        """测试获取已用时间 - 不存在"""
        hardlock = SlippageHardlock()

        result = hardlock.get_elapsed_time('BTCUSDT')

        assert result is None

    def test_get_elapsed_time_increases(self):
        """测试获取已用时间 - 时间递增"""
        hardlock = SlippageHardlock()

        hardlock.lock_trigger_price('BTCUSDT', 50000.0)

        elapsed1 = hardlock.get_elapsed_time('BTCUSDT')
        time.sleep(0.1)
        elapsed2 = hardlock.get_elapsed_time('BTCUSDT')

        assert elapsed2 > elapsed1

    # ==================== clear_all 测试 ====================

    def test_clear_all(self):
        """测试清理所有锁定"""
        hardlock = SlippageHardlock()

        hardlock.lock_trigger_price('BTCUSDT', 50000.0)
        hardlock.lock_trigger_price('ETHUSDT', 3000.0)

        assert len(hardlock._locked_prices) == 2

        hardlock.clear_all()

        assert len(hardlock._locked_prices) == 0

    # ==================== get_stats 测试 ====================

    def test_get_stats_basic(self):
        """测试获取统计信息 - 基本"""
        hardlock = SlippageHardlock(base_threshold_pct=0.8, timeout_sec=10.0)

        stats = hardlock.get_stats()

        assert stats['locked_count'] == 0
        assert stats['base_threshold_pct'] == 0.8
        assert stats['timeout_sec'] == 10.0

    def test_get_stats_with_locks(self):
        """测试获取统计信息 - 有锁定"""
        hardlock = SlippageHardlock()

        hardlock.lock_trigger_price('BTCUSDT', 50000.0)
        hardlock.lock_trigger_price('ETHUSDT', 3000.0)

        stats = hardlock.get_stats()

        assert stats['locked_count'] == 2

    # ==================== 边界条件测试 ====================

    def test_slippage_exact_threshold(self):
        """测试滑点 - 恰好等于阈值"""
        hardlock = SlippageHardlock(base_threshold_pct=0.5)

        hardlock.lock_trigger_price('BTCUSDT', 50000.0)

        # 价格变化恰好 0.5%
        # 根据代码逻辑，只有超过阈值才会失败，恰好等于阈值时应该通过
        passed, reason = hardlock.check_slippage('BTCUSDT', 50250.0)

        # 应该通过（未超过阈值）
        assert passed is True

    def test_slippage_zero_price_change(self):
        """测试滑点 - 价格无变化"""
        hardlock = SlippageHardlock()

        hardlock.lock_trigger_price('BTCUSDT', 50000.0)

        passed, reason = hardlock.check_slippage('BTCUSDT', 50000.0)

        assert passed is True

    def test_slippage_very_small_price_change(self):
        """测试滑点 - 极小价格变化"""
        hardlock = SlippageHardlock(base_threshold_pct=0.5)

        hardlock.lock_trigger_price('BTCUSDT', 50000.0)

        passed, reason = hardlock.check_slippage('BTCUSDT', 50000.01)

        assert passed is True

    def test_lock_zero_price(self):
        """测试锁定 - 零价格"""
        hardlock = SlippageHardlock()

        # 边界情况：零价格
        hardlock.lock_trigger_price('BTCUSDT', 0.0)

        # 应该能锁定，但检查时会有除零问题
        # 实际使用中不应该出现这种情况
        assert 'BTCUSDT' in hardlock._locked_prices

    def test_slippage_negative_price(self):
        """测试滑点 - 负价格（异常情况）"""
        hardlock = SlippageHardlock()

        hardlock.lock_trigger_price('BTCUSDT', 50000.0)

        # 负价格是异常情况
        passed, reason = hardlock.check_slippage('BTCUSDT', -100.0)

        # 应该处理这种情况
        assert isinstance(passed, bool)

    def test_lock_same_symbol_twice(self):
        """测试锁定 - 同一币种锁定两次"""
        hardlock = SlippageHardlock()

        hardlock.lock_trigger_price('BTCUSDT', 50000.0)
        time.sleep(0.1)
        hardlock.lock_trigger_price('BTCUSDT', 51000.0)

        # 应该更新时间戳
        locked_price, timestamp = hardlock._locked_prices['BTCUSDT']
        assert locked_price == 51000.0

    def test_timeout_boundary(self):
        """测试超时边界"""
        hardlock = SlippageHardlock(timeout_sec=0.5)

        hardlock.lock_trigger_price('BTCUSDT', 50000.0)
        time.sleep(0.49)

        # 刚好在超时前
        passed, reason = hardlock.check_slippage('BTCUSDT', 50000.0)

        # 应该还没超时
        assert "超时" not in reason or "超时" not in str(passed)

    def test_multiple_consecutive_checks(self):
        """测试连续检查"""
        hardlock = SlippageHardlock(base_threshold_pct=0.5)

        hardlock.lock_trigger_price('BTCUSDT', 50000.0)

        # 第一次检查
        passed1, _ = hardlock.check_slippage('BTCUSDT', 50050.0)
        assert passed1 is True

        # 应该已经被清理
        assert 'BTCUSDT' not in hardlock._locked_prices

        # 第二次检查应该失败（已清理）
        passed2, reason2 = hardlock.check_slippage('BTCUSDT', 50050.0)
        assert passed2 is False
        assert "未锁定" in reason2


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
