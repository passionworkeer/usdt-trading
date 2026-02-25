"""
v6.1 资金费结算静默期（Funding Settlement Blackout Window）

防止在资金费结算前开仓导致巨额费用扣除
"""
import logging
from datetime import datetime, timezone, timedelta
from typing import Tuple

logger = logging.getLogger(__name__)


class FundingSettlementGuard:
    """
    资金费结算守护者

    币安合约资金费率每 8 小时结算一次：
    - 00:00 UTC
    - 08:00 UTC
    - 16:00 UTC

    如果在结算前 15 分钟内开仓，会瞬间支付巨额资金费
    """

    # 资金费结算时间（UTC）
    SETTLEMENT_TIMES = [
        (0, 0),   # 00:00 UTC
        (8, 0),   # 08:00 UTC
        (16, 0),  # 16:00 UTC
    ]

    # 静默期时长（分钟）
    BLACKOUT_WINDOW_MINUTES = 15

    def __init__(self, blackout_minutes: int = 15):
        """
        初始化资金费结算守护者

        Args:
            blackout_minutes: 静默期时长（分钟）
        """
        self.blackout_minutes = blackout_minutes

        logger.info(f"✅ 资金费结算守护者已初始化")
        logger.info(f"   静默期: 结算前 {blackout_minutes} 分钟")
        logger.info(f"   结算时间: 00:00, 08:00, 16:00 UTC")

    def get_next_settlement_time(self, now: datetime) -> datetime:
        """
        获取下一次结算时间

        Args:
            now: 当前时间（UTC）

        Returns:
            下一次结算时间（UTC）
        """
        # 转换为 UTC
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        else:
            now = now.astimezone(timezone.utc)

        # 获取当前时间的小时和分钟
        current_hour = now.hour
        current_minute = now.minute

        # 检查每个结算时间
        for settlement_hour, settlement_minute in self.SETTLEMENT_TIMES:
            settlement_time = now.replace(
                hour=settlement_hour,
                minute=settlement_minute,
                second=0,
                microsecond=0
            )

            # 如果结算时间还没到，那就是下一次
            if (settlement_time.hour > current_hour or
                (settlement_time.hour == current_hour and
                 settlement_time.minute > current_minute)):
                return settlement_time

        # 如果所有结算时间都过了，下一次就是明天的 00:00
        next_day = now + timedelta(days=1)
        return next_day.replace(
            hour=0,
            minute=0,
            second=0,
            microsecond=0
        )

    def is_in_blackout_window(self, now: datetime = None) -> Tuple[bool, str]:
        """
        检查是否在静默期内

        Args:
            now: 当前时间（UTC），默认使用当前系统时间

        Returns:
            (是否在静默期, 原因)
        """
        if now is None:
            now = datetime.now(timezone.utc)

        # 转换为 UTC
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        else:
            now = now.astimezone(timezone.utc)

        # 获取下一次结算时间
        next_settlement = self.get_next_settlement_time(now)

        # 计算距离结算的时间
        time_to_settlement = next_settlement - now
        minutes_to_settlement = time_to_settlement.total_seconds() / 60

        # 检查是否在静默期内
        if minutes_to_settlement <= self.blackout_minutes:
            reason = (
                f"⛔ 静默期触发：距离 {next_settlement.strftime('%H:%M')} UTC "
                f"资金费结算仅剩 {minutes_to_settlement:.1f} 分钟 "
                f"(阈值: {self.blackout_minutes} 分钟)"
            )
            logger.critical(reason)
            return True, reason

        return False, f"✅ 不在静默期，距离下次结算 {minutes_to_settlement:.1f} 分钟"

    def check_can_open_position(
        self,
        symbol: str = None,
        now: datetime = None
    ) -> Tuple[bool, str]:
        """
        检查是否允许开仓

        Args:
            symbol: 交易对（可选，用于日志）
            now: 当前时间（UTC），默认使用当前系统时间

        Returns:
            (是否允许开仓, 原因)
        """
        in_blackout, reason = self.is_in_blackout_window(now)

        if in_blackout:
            symbol_str = f"{symbol} " if symbol else ""
            logger.critical(f"🚨 {symbol_str}禁止开仓：{reason}")
            return False, reason

        return True, reason

    def get_time_to_next_settlement(self, now: datetime = None) -> timedelta:
        """
        获取距离下次结算的时间

        Args:
            now: 当前时间（UTC），默认使用当前系统时间

        Returns:
            距离下次结算的时间差
        """
        if now is None:
            now = datetime.now(timezone.utc)

        # 转换为 UTC
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        else:
            now = now.astimezone(timezone.utc)

        next_settlement = self.get_next_settlement_time(now)
        return next_settlement - now


# 全局实例
_funding_guard = None


def get_funding_guard() -> FundingSettlementGuard:
    """获取全局资金费结算守护者实例"""
    global _funding_guard
    if _funding_guard is None:
        _funding_guard = FundingSettlementGuard()
    return _funding_guard


if __name__ == '__main__':
    # 测试代码
    import asyncio
    from datetime import timezone, timedelta

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - [%(name)s] - %(levelname)s - %(message)s'
    )

    guard = FundingSettlementGuard()

    # 测试不同时间点
    test_cases = [
        datetime(2026, 2, 25, 7, 50, 0, tzinfo=timezone.utc),  # 距离 08:00 还有 10 分钟
        datetime(2026, 2, 25, 7, 46, 0, tzinfo=timezone.utc),  # 距离 08:00 还有 14 分钟
        datetime(2026, 2, 25, 7, 55, 0, tzinfo=timezone.utc),  # 距离 08:00 还有 5 分钟
        datetime(2026, 2, 25, 10, 0, 0, tzinfo=timezone.utc),  # 距离 16:00 还有 6 小时
    ]

    for test_time in test_cases:
        print(f"\n测试时间: {test_time.strftime('%Y-%m-%d %H:%M:%S UTC')}")

        in_blackout, reason = guard.is_in_blackout_window(test_time)
        print(f"静默期: {in_blackout}")
        print(f"原因: {reason}")

        can_open, reason = guard.check_can_open_position("BTCUSDT", test_time)
        print(f"允许开仓: {can_open}")

        time_to_settlement = guard.get_time_to_next_settlement(test_time)
        print(f"距离下次结算: {time_to_settlement}")
