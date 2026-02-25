"""
v7.1 混沌工程：交易所断网模拟器（Chaos Monkey - Mock Exchange Injector）

永远不要相信币安的 API
"""
import asyncio
import random
import logging
from typing import Optional, Dict, Any, Callable
from datetime import datetime, timezone
from dataclasses import dataclass
from enum import Enum
import json

logger = logging.getLogger(__name__)


class ChaosEventType(Enum):
    """混沌事件类型"""
    WEBSOCKET_SILENCE = "WEBSOCKET_SILENCE"  # WebSocket 突然静默
    REST_502 = "REST_502"  # HTTP 502 Bad Gateway
    REST_429 = "REST_429"  # HTTP 429 Too Many Requests
    ORDERBOOK_GHOST = "ORDERBOOK_GHOST"  # 订单簿乱序/跳空
    DELAY_SPIKE = "DELAY_SPIKE"  # 延迟突增


@dataclass
class ChaosEvent:
    """混沌事件"""
    event_type: ChaosEventType
    probability: float  # 触发概率（0-1）
    duration: float  # 持续时间（秒）
    impact: str  # 影响描述


class ChaosMonkey:
    """
    混沌猴子：交易所断网模拟器

    功能：
    1. 随机模拟交易所服务器抽风
    2. 测试系统的容错能力
    3. 验证熔断和重试机制

    模拟场景：
    - WebSocket 突然静默（不发心跳）
    - REST API 随机返回 HTTP 502/429
    - 订单簿数据乱序或跳空（2 秒）
    - 延迟突增（200-500ms）

    测试目标：
    - 系统是否能优雅退避重试？
    - 是否正确触发熔断？
    - 是否直接崩溃？
    """

    # 混沌事件配置
    CHAOS_EVENTS = [
        ChaosEvent(
            event_type=ChaosEventType.WEBSOCKET_SILENCE,
            probability=0.05,  # 5% 概率
            duration=5.0,  # 持续 5 秒
            impact="WebSocket 突然停止发送数据"
        ),
        ChaosEvent(
            event_type=ChaosEventType.REST_502,
            probability=0.10,  # 10% 概率
            duration=2.0,  # 持续 2 秒
            impact="REST API 返回 502 Bad Gateway"
        ),
        ChaosEvent(
            event_type=ChaosEventType.REST_429,
            probability=0.05,  # 5% 概率
            duration=10.0,  # 持续 10 秒
            impact="REST API 返回 429 Too Many Requests"
        ),
        ChaosEvent(
            event_type=ChaosEventType.ORDERBOOK_GHOST,
            probability=0.03,  # 3% 概率
            duration=2.0,  # 持续 2 秒
            impact="订单簿数据乱序或跳空"
        ),
        ChaosEvent(
            event_type=ChaosEventType.DELAY_SPIKE,
            probability=0.15,  # 15% 概率
            duration=3.0,  # 持续 3 秒
            impact="延迟突增 200-500ms"
        ),
    ]

    def __init__(
        self,
        enabled: bool = True,
        seed: Optional[int] = None,
    ):
        """
        初始化混沌猴子

        Args:
            enabled: 是否启用混沌测试
            seed: 随机种子（用于复现测试）
        """
        self.enabled = enabled

        # 随机数生成器
        if seed is not None:
            random.seed(seed)
            self.rng = random.Random(seed)
        else:
            self.rng = random

        # 当前活跃的混沌事件
        self.active_events: Dict[ChaosEventType, ChaosEvent] = {}

        # 统计信息
        self.total_checks = 0
        self.triggered_count = 0
        self.event_counts = {event_type: 0 for event_type in ChaosEventType}

        # 回调函数
        self.on_event_trigger: Optional[Callable] = None
        self.on_event_end: Optional[Callable] = None

        logger.info(f"混沌猴子初始化: {'启用' if enabled else '禁用'}")
        if seed:
            logger.info(f"  随机种子: {seed}")

    def check_chaos(self) -> Optional[ChaosEvent]:
        """
        检查是否触发混沌事件

        Returns:
            触发的混沌事件，或 None
        """
        if not self.enabled:
            return None

        self.total_checks += 1

        # 检查每个混沌事件
        for event in self.CHAOS_EVENTS:
            # 随机判定是否触发
            if self.rng.random() < event.probability:
                # 触发事件
                self.active_events[event.event_type] = event
                self.triggered_count += 1
                self.event_counts[event.event_type] += 1

                logger.critical(f"\n{'='*60}")
                logger.critical(f"🐵 混沌猴子触发: {event.event_type.value}")
                logger.critical(f"{'='*60}")
                logger.critical(f"   影响: {event.impact}")
                logger.critical(f"   持续: {event.duration} 秒")
                logger.critical(f"{'='*60}\n")

                # 触发回调
                if self.on_event_trigger:
                    asyncio.create_task(self.on_event_trigger(event))

                # 启动事件结束定时器
                asyncio.create_task(self._end_event_after_duration(event))

                return event

        return None

    async def _end_event_after_duration(self, event: ChaosEvent) -> None:
        """
        事件结束定时器

        Args:
            event: 混沌事件
        """
        await asyncio.sleep(event.duration)

        # 移除事件
        if event.event_type in self.active_events:
            del self.active_events[event.event_type]

        logger.info(f"✅ 混沌事件结束: {event.event_type.value}")

        # 触发回调
        if self.on_event_end:
            await self.on_event_end(event)

    def is_event_active(self, event_type: ChaosEventType) -> bool:
        """
        检查事件是否活跃

        Args:
            event_type: 事件类型

        Returns:
            是否活跃
        """
        return event_type in self.active_events

    def inject_websocket_silence(self) -> bool:
        """
        注入 WebSocket 静默

        Returns:
            是否注入成功
        """
        if not self.enabled:
            return False

        if self.is_event_active(ChaosEventType.WEBSOCKET_SILENCE):
            logger.warning("🐵 WebSocket 静默注入：停止发送数据")
            return True

        return False

    def inject_rest_error(self, url: str) -> Optional[Dict]:
        """
        注入 REST API 错误

        Args:
            url: 请求 URL

        Returns:
            错误响应，或 None
        """
        if not self.enabled:
            return None

        # 检查是否触发 502
        if self.is_event_active(ChaosEventType.REST_502):
            logger.critical("🐵 注入 HTTP 502 Bad Gateway")
            return {
                'status': 502,
                'error': 'Bad Gateway',
                'message': 'Chaos Monkey injected error',
            }

        # 检查是否触发 429
        if self.is_event_active(ChaosEventType.REST_429):
            logger.critical("🐵 注入 HTTP 429 Too Many Requests")
            return {
                'status': 429,
                'error': 'Too Many Requests',
                'message': 'Chaos Monkey injected error',
            }

        return None

    def inject_orderbook_ghost(self, orderbook: Dict) -> Optional[Dict]:
        """
        注入订单簿乱序/跳空

        Args:
            orderbook: 原始订单簿

        Returns:
            混淆后的订单簿，或 None
        """
        if not self.enabled:
            return None

        if not self.is_event_active(ChaosEventType.ORDERBOOK_GHOST):
            return None

        logger.critical("🐵 注入订单簿乱序/跳空")

        # 随机选择一种混淆方式
        ghost_type = self.rng.choice(['shuffle', 'gap', 'stale'])

        if ghost_type == 'shuffle':
            # 打乱订单簿顺序
            orderbook['bids'] = self.rng.sample(orderbook['bids'], len(orderbook['bids']))
            orderbook['asks'] = self.rng.sample(orderbook['asks'], len(orderbook['asks']))

        elif ghost_type == 'gap':
            # 价格跳空（±10%）
            gap_factor = 1.0 + self.rng.choice([0.1, -0.1])
            orderbook['bids'] = [[float(bid[0]) * gap_factor, float(bid[1])] for bid in orderbook['bids']]
            orderbook['asks'] = [[float(ask[0]) * gap_factor, float(ask[1])] for ask in orderbook['asks']]

        elif ghost_type == 'stale':
            # 陈旧数据（时间戳回退 10 秒）
            stale_time = int((datetime.now(timezone.utc).timestamp() - 10) * 1000)
            orderbook['lastUpdateId'] = stale_time

        return orderbook

    def inject_delay_spike(self) -> float:
        """
        注入延迟突增

        Returns:
            额外延迟（毫秒）
        """
        if not self.enabled:
            return 0.0

        if not self.is_event_active(ChaosEventType.DELAY_SPIKE):
            return 0.0

        # 随机延迟 200-500ms
        extra_delay = self.rng.uniform(200, 500)

        logger.warning(f"🐵 注入延迟突增: +{extra_delay:.1f} ms")

        # 模拟延迟
        asyncio.sleep(extra_delay / 1000)

        return extra_delay

    def get_stats(self) -> Dict:
        """获取统计信息"""
        return {
            'enabled': self.enabled,
            'total_checks': self.total_checks,
            'triggered_count': self.triggered_count,
            'trigger_rate': self.triggered_count / self.total_checks if self.total_checks > 0 else 0,
            'event_counts': {k.value: v for k, v in self.event_counts.items()},
            'active_events': [e.value for e in self.active_events.keys()],
        }


# 全局实例
_chaos_monkey: Optional[ChaosMonkey] = None


def get_chaos_monkey(enabled: bool = True, seed: Optional[int] = None) -> ChaosMonkey:
    """获取全局混沌猴子实例"""
    global _chaos_monkey
    if _chaos_monkey is None:
        _chaos_monkey = ChaosMonkey(enabled=enabled, seed=seed)
    return _chaos_monkey


async def run_chaos_test(
    duration_seconds: int = 60,
    seed: Optional[int] = 42,
) -> Dict:
    """
    运行混沌测试

    Args:
        duration_seconds: 测试时长（秒）
        seed: 随机种子

    Returns:
        测试结果
    """
    logger.info(f"\n{'='*60}")
    logger.info(f"🐵 混沌测试启动")
    logger.info(f"{'='*60}")
    logger.info(f"  测试时长: {duration_seconds} 秒")
    logger.info(f"  随机种子: {seed}")
    logger.info(f"{'='*60}\n")

    # 初始化混沌猴子
    monkey = ChaosMonkey(enabled=True, seed=seed)

    # 模拟交易循环
    start_time = datetime.now()
    check_count = 0

    while (datetime.now() - start_time).total_seconds() < duration_seconds:
        check_count += 1

        # 检查混沌事件
        event = monkey.check_chaos()

        if event:
            logger.critical(f"第 {check_count} 次检查触发混沌事件: {event.event_type.value}")

        # 模拟 WebSocket 接收
        if monkey.inject_websocket_silence():
            logger.warning("WebSocket 静默中，无数据")

        # 模拟 REST 请求
        rest_error = monkey.inject_rest_error("https://fapi.binance.com/fapi/v1/time")
        if rest_error:
            logger.critical(f"REST 请求失败: {rest_error}")

        # 模拟延迟
        extra_delay = monkey.inject_delay_spike()
        if extra_delay > 0:
            logger.warning(f"总延迟: {100 + extra_delay:.1f} ms")

        # 模拟正常延迟
        await asyncio.sleep(0.1)

    # 打印统计
    stats = monkey.get_stats()

    logger.info(f"\n{'='*60}")
    logger.info(f"🐵 混沌测试完成")
    logger.info(f"{'='*60}")
    logger.info(f"  总检查次数: {stats['total_checks']}")
    logger.info(f"  触发次数: {stats['triggered_count']}")
    logger.info(f"  触发率: {stats['trigger_rate']:.2%}")
    logger.info(f"  事件分布:")
    for event_type, count in stats['event_counts'].items():
        logger.info(f"    {event_type}: {count} 次")
    logger.info(f"{'='*60}\n")

    return stats


if __name__ == '__main__':
    # 测试代码
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - [%(name)s] - %(levelname)s - %(message)s'
    )

    # 运行混沌测试
    asyncio.run(run_chaos_test(duration_seconds=30, seed=42))
