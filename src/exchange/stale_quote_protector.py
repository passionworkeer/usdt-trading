"""
v7.0 数据陈旧保护器（Stale Quote Protector）

毫秒级防割机制，拒绝使用过期数据交易
"""
import asyncio
import logging
from typing import Optional, Dict, Callable
from datetime import datetime, timezone
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class LatencyCheck:
    """延迟检查结果"""
    event_time: int  # 事件时间（毫秒）
    local_time: int  # 本地时间（毫秒）
    latency_ms: float  # 延迟（毫秒）
    is_stale: bool  # 是否陈旧
    reason: str  # 原因


class StaleQuoteProtector:
    """
    数据陈旧保护器

    功能：
    1. 检测 WebSocket 数据延迟
    2. 如果延迟 > 100ms → 进入静默锁定模式
    3. 抛弃所有过期行情
    4. 宁可变成瞎子，绝不拿过期情报开火

    延迟计算：
    Latency = Local_Time - Event_Time

    阈值：
    - < 100ms：正常
    - 100-200ms：警告
    - > 200ms：严重陈旧，静默锁定

    触发场景：
    - Windows 系统卡顿
    - 网络延迟突增
    - WebSocket 消息堆积
    - 币安服务器推送延迟
    """

    # 延迟阈值（毫秒）
    LATENCY_WARNING_MS = 100  # 警告阈值
    LATENCY_CRITICAL_MS = 200  # 严重阈值
    LATENCY_MAX_MS = 500  # 最大阈值

    def __init__(
        self,
        latency_warning_ms: float = 100,
        latency_critical_ms: float = 200,
        latency_max_ms: float = 500,
    ):
        """
        初始化数据陈旧保护器

        Args:
            latency_warning_ms: 警告阈值（毫秒）
            latency_critical_ms: 严重阈值（毫秒）
            latency_max_ms: 最大阈值（毫秒）
        """
        self.latency_warning_ms = latency_warning_ms
        self.latency_critical_ms = latency_critical_ms
        self.latency_max_ms = latency_max_ms

        # 运行状态
        self.is_locked = False  # 静默锁定模式
        self.lock_reason = ""

        # 统计信息
        self.check_count = 0
        self.stale_count = 0
        self.lock_count = 0
        self.total_latency_ms = 0.0
        self.max_latency_ms = 0.0

        # 回调函数
        self.on_lock_callback: Optional[Callable] = None
        self.on_unlock_callback: Optional[Callable] = None

        logger.info("数据陈旧保护器初始化:")
        logger.info(f"   警告阈值: {latency_warning_ms} ms")
        logger.info(f"   严重阈值: {latency_critical_ms} ms")
        logger.info(f"   最大阈值: {latency_max_ms} ms")

    def check_latency(
        self,
        event_time: int,  # 毫秒时间戳
        symbol: str = None,
    ) -> LatencyCheck:
        """
        检查延迟

        Args:
            event_time: 事件时间（毫秒）
            symbol: 交易对（可选，用于日志）

        Returns:
            延迟检查结果
        """
        # 获取本地时间
        local_time = int(datetime.now(timezone.utc).timestamp() * 1000)

        # 计算延迟
        latency_ms = local_time - event_time

        # 更新统计
        self.check_count += 1
        self.total_latency_ms += latency_ms
        self.max_latency_ms = max(self.max_latency_ms, latency_ms)

        # 判断是否陈旧
        is_stale = False
        reason = ""

        if latency_ms > self.latency_max_ms:
            # 严重陈旧
            is_stale = True
            reason = f"🚨 严重陈旧: {latency_ms:.1f} ms > {self.latency_max_ms} ms"

            self.stale_count += 1

            logger.critical(f"\n{'='*60}")
            logger.critical(f"🚨 数据陈旧检测！")
            logger.critical(f"{'='*60}")
            logger.critical(f"   交易对: {symbol if symbol else 'N/A'}")
            logger.critical(f"   延迟: {latency_ms:.1f} ms")
            logger.critical(f"   事件时间: {datetime.fromtimestamp(event_time / 1000, tz=timezone.utc).isoformat()}")
            logger.critical(f"   本地时间: {datetime.fromtimestamp(local_time / 1000, tz=timezone.utc).isoformat()}")
            logger.critical(f"   ⚠️ 系统进入静默锁定模式")
            logger.critical(f"{'='*60}\n")

            # 进入静默锁定
            self._enter_lock_mode(f"数据陈旧: {latency_ms:.1f} ms")

        elif latency_ms > self.latency_critical_ms:
            # 严重警告
            reason = f"⚠️ 严重延迟: {latency_ms:.1f} ms > {self.latency_critical_ms} ms"

            logger.warning(f"⚠️ {symbol if symbol else 'N/A'} 严重延迟: {latency_ms:.1f} ms")

            # 如果连续严重延迟，也进入锁定
            if not self.is_locked:
                self._enter_lock_mode(f"连续严重延迟: {latency_ms:.1f} ms")

        elif latency_ms > self.latency_warning_ms:
            # 警告
            reason = f"⚡ 延迟警告: {latency_ms:.1f} ms > {self.latency_warning_ms} ms"

            logger.info(f"⚡ {symbol if symbol else 'N/A'} 延迟警告: {latency_ms:.1f} ms")

        else:
            # 正常
            reason = f"✅ 延迟正常: {latency_ms:.1f} ms"

            # 如果之前是锁定状态，现在恢复正常
            if self.is_locked:
                self._exit_lock_mode()

        return LatencyCheck(
            event_time=event_time,
            local_time=local_time,
            latency_ms=latency_ms,
            is_stale=is_stale,
            reason=reason,
        )

    def _enter_lock_mode(self, reason: str) -> None:
        """
        进入静默锁定模式

        Args:
            reason: 原因
        """
        if self.is_locked:
            return

        self.is_locked = True
        self.lock_reason = reason
        self.lock_count += 1

        logger.critical(f"🔒 进入静默锁定模式")
        logger.critical(f"   原因: {reason}")
        logger.critical(f"   行为: 抛弃所有行情，停止交易")

        # 触发回调
        if self.on_lock_callback:
            asyncio.create_task(self.on_lock_callback(reason))

    def _exit_lock_mode(self) -> None:
        """退出静默锁定模式"""
        if not self.is_locked:
            return

        logger.info(f"🔓 退出静默锁定模式")
        logger.info(f"   延迟已恢复正常")

        self.is_locked = False
        self.lock_reason = ""

        # 触发回调
        if self.on_unlock_callback:
            asyncio.create_task(self.on_unlock_callback())

    def should_trade(self) -> bool:
        """
        检查是否允许交易

        Returns:
            是否允许交易
        """
        if self.is_locked:
            logger.warning(f"⛔ 静默锁定中，禁止交易: {self.lock_reason}")
            return False

        return True

    def get_stats(self) -> dict:
        """获取统计信息"""
        avg_latency = self.total_latency_ms / self.check_count if self.check_count > 0 else 0

        return {
            'is_locked': self.is_locked,
            'lock_reason': self.lock_reason,
            'check_count': self.check_count,
            'stale_count': self.stale_count,
            'lock_count': self.lock_count,
            'avg_latency_ms': avg_latency,
            'max_latency_ms': self.max_latency_ms,
            'stale_rate': self.stale_count / self.check_count if self.check_count > 0 else 0,
        }


# 全局实例
_stale_quote_protector: Optional[StaleQuoteProtector] = None


def get_stale_quote_protector() -> StaleQuoteProtector:
    """获取全局数据陈旧保护器实例"""
    global _stale_quote_protector
    if _stale_quote_protector is None:
        _stale_quote_protector = StaleQuoteProtector()
    return _stale_quote_protector


if __name__ == '__main__':
    # 测试代码
    import time

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - [%(name)s] - %(levelname)s - %(message)s'
    )

    protector = StaleQuoteProtector()

    # 测试正常延迟
    event_time = int(datetime.now(timezone.utc).timestamp() * 1000)
    result = protector.check_latency(event_time, 'BTCUSDT')
    print(f"\n延迟检查:")
    print(f"  延迟: {result.latency_ms:.1f} ms")
    print(f"  陈旧: {result.is_stale}")
    print(f"  原因: {result.reason}")

    # 测试陈旧数据（模拟 300ms 延迟）
    event_time_old = int((datetime.now(timezone.utc).timestamp() - 0.3) * 1000)
    result = protector.check_latency(event_time_old, 'ETHUSDT')
    print(f"\n延迟检查:")
    print(f"  延迟: {result.latency_ms:.1f} ms")
    print(f"  陈旧: {result.is_stale}")
    print(f"  原因: {result.reason}")

    # 检查是否允许交易
    print(f"\n允许交易: {protector.should_trade()}")

    # 打印统计
    print("\n统计信息:")
    print(protector.get_stats())
