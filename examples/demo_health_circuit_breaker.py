#!/usr/bin/env python3
"""
P1-17: 健康检查和熔断器使用示例

演示如何使用健康检查器和熔断器保护交易所 API 调用
"""
import asyncio
import logging
from pathlib import Path
import sys

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.utils.circuit_breaker import CircuitBreaker, CircuitBreakerConfig
from src.utils.degradation_strategy import DegradationStrategy

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def demo_circuit_breaker():
    """演示熔断器工作流程"""
    logger.info("="*60)
    logger.info("熔断器演示")
    logger.info("="*60)

    # 创建熔断器（3次失败触发，冷却10秒）
    breaker = CircuitBreaker(
        name="demo",
        config=CircuitBreakerConfig(
            failure_threshold=3,
            success_threshold=2,
            cooldown_seconds=10,
        )
    )

    # 模拟 API 调用
    async def protected_api_call(should_fail=False):
        """受熔断器保护的 API 调用"""
        if not breaker.check():
            logger.warning("🚫 熔断器开启，拒绝请求")
            return None

        try:
            if should_fail:
                raise Exception("API 调用失败")

            # 模拟成功
            logger.info("✅ API 调用成功")
            breaker.on_success()
            return True

        except Exception as e:
            logger.error(f"❌ {e}")
            breaker.on_failure()
            return False

    # 1. 模拟连续失败
    logger.info("\n场景 1: 连续失败触发熔断")
    for i in range(4):
        logger.info(f"\n请求 {i+1}:")
        await protected_api_call(should_fail=True)
        logger.info(f"熔断器状态: {breaker.get_state().value}")

    # 2. 尝试在熔断期间调用
    logger.info("\n场景 2: 熔断期间尝试调用")
    await protected_api_call(should_fail=False)

    # 3. 等待冷却
    logger.info("\n场景 3: 等待冷却时间（10秒）...")
    await asyncio.sleep(11)

    # 4. 冷却后恢复
    logger.info("\n场景 4: 冷却后尝试恢复")
    for i in range(3):
        logger.info(f"\n请求 {i+1}:")
        await protected_api_call(should_fail=False)
        logger.info(f"熔断器状态: {breaker.get_state().value}")


async def demo_degradation_strategy():
    """演示降级策略"""
    logger.info("\n" + "="*60)
    logger.info("降级策略演示")
    logger.info("="*60)

    strategy = DegradationStrategy()

    # 模拟不同的健康状态
    scenarios = [
        ("HEALTHY", "交易所完全正常"),
        ("DEGRADED", "交易所延迟较高"),
        ("UNHEALTHY", "交易所部分功能异常"),
        ("CRITICAL", "交易所严重故障"),
    ]

    for status, description in scenarios:
        logger.info(f"\n场景: {description}")
        action = strategy.update_strategy(status)

        logger.info(f"  降级级别: {action.level.value}")
        logger.info(f"  描述: {action.description}")
        logger.info(f"  允许开仓: {'✅' if action.allow_new_positions else '❌'}")
        logger.info(f"  检查间隔倍数: {action.check_interval_multiplier}x")

        # 模拟决策
        if strategy.can_open_position():
            logger.info("  决策: 继续交易")
        else:
            logger.info("  决策: 暂停交易")


async def main():
    """运行演示"""
    logger.info("\n" + "="*60)
    logger.info("P1-17: 健康检查和熔断器使用示例")
    logger.info("="*60)

    # 演示熔断器
    await demo_circuit_breaker()

    # 演示降级策略
    await demo_degradation_strategy()

    logger.info("\n" + "="*60)
    logger.info("演示完成")
    logger.info("="*60)


if __name__ == '__main__':
    asyncio.run(main())
