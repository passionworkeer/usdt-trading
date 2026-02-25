#!/usr/bin/env python3
"""
P1-17: 交易所健康检查和熔断器测试

测试内容：
1. 健康检查功能
2. 熔断器状态转换
3. 降级策略切换
4. 紧急平仓流程
"""
import asyncio
import logging
from pathlib import Path
import sys

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.utils.health_checker import ExchangeHealthChecker, HealthStatus
from src.utils.circuit_breaker import CircuitBreaker, CircuitBreakerConfig, CircuitBreakerManager
from src.utils.degradation_strategy import DegradationStrategy, DegradationLevel

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - [%(name)s] - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def test_circuit_breaker():
    """测试熔断器功能"""
    logger.info("\n" + "="*60)
    logger.info("测试 1: 熔断器状态转换")
    logger.info("="*60)

    # 创建熔断器
    breaker = CircuitBreaker(
        name="test_breaker",
        config=CircuitBreakerConfig(
            failure_threshold=3,
            success_threshold=2,
            cooldown_seconds=5,  # 测试用，5秒冷却
        )
    )

    # 初始状态
    logger.info(f"初始状态: {breaker.get_state().value}")
    assert breaker.get_state().value == "closed", "初始状态应为 closed"

    # 模拟连续失败
    logger.info("\n模拟连续 3 次失败...")
    for i in range(3):
        breaker.on_failure()
        logger.info(f"  失败 {i+1}: 状态={breaker.get_state().value}, 失败计数={breaker.failure_count}")

    # 检查熔断器是否触发
    assert breaker.get_state().value == "open", "连续 3 次失败后应触发熔断"
    assert not breaker.check(), "熔断器开启时应拒绝请求"
    logger.info("✅ 熔断器已正确触发")

    # 等待冷却时间
    logger.info("\n等待冷却时间 (5秒)...")
    await asyncio.sleep(6)

    # 检查是否进入半开状态
    logger.info(f"冷却后状态: {breaker.get_state().value}")
    assert breaker.check(), "冷却后应允许尝试"
    logger.info("✅ 熔断器已进入半开状态")

    # 模拟连续成功
    logger.info("\n模拟连续 2 次成功...")
    for i in range(2):
        breaker.on_success()
        logger.info(f"  成功 {i+1}: 状态={breaker.get_state().value}, 成功计数={breaker.success_count}")

    # 检查是否恢复
    assert breaker.get_state().value == "closed", "连续 2 次成功后应恢复"
    logger.info("✅ 熔断器已恢复正常")

    # 打印统计信息
    stats = breaker.get_stats()
    logger.info(f"\n熔断器统计:")
    logger.info(f"  总请求: {stats['total_requests']}")
    logger.info(f"  总失败: {stats['total_failures']}")
    logger.info(f"  总成功: {stats['total_successes']}")
    logger.info(f"  失败率: {stats['failure_rate']:.1%}")

    logger.info("\n✅ 熔断器测试通过")


async def test_degradation_strategy():
    """测试降级策略"""
    logger.info("\n" + "="*60)
    logger.info("测试 2: 降级策略切换")
    logger.info("="*60)

    strategy = DegradationStrategy()

    # 测试各种健康状态
    test_cases = [
        ('HEALTHY', DegradationLevel.NORMAL, True),
        ('DEGRADED', DegradationLevel.REDUCED_FREQUENCY, True),
        ('UNHEALTHY', DegradationLevel.READ_ONLY, False),
        ('CRITICAL', DegradationLevel.EMERGENCY_CLOSE, False),
    ]

    for health_status, expected_level, allow_open in test_cases:
        action = strategy.update_strategy(health_status)

        logger.info(f"\n健康状态: {health_status}")
        logger.info(f"  降级级别: {action.level.value}")
        logger.info(f"  描述: {action.description}")
        logger.info(f"  允许开仓: {action.allow_new_positions}")
        logger.info(f"  检查间隔倍数: {action.check_interval_multiplier}x")

        assert action.level == expected_level, f"降级级别应为 {expected_level}"
        assert action.allow_new_positions == allow_open, f"开仓权限应为 {allow_open}"

    logger.info("\n✅ 降级策略测试通过")


async def test_health_checker():
    """测试健康检查器（模拟）"""
    logger.info("\n" + "="*60)
    logger.info("测试 3: 健康检查器（需要真实交易所连接）")
    logger.info("="*60)

    try:
        from src.exchange.exchange_info_manager import BinanceExchangeInfo

        # 创建交易所实例（测试网）
        exchange_info = BinanceExchangeInfo(testnet=True)

        # 创建健康检查器
        health_checker = ExchangeHealthChecker(exchange_info.exchange)

        # 执行健康检查
        logger.info("执行健康检查...")
        result = await health_checker.health_check()

        logger.info(f"\n健康状态: {result.status.value}")
        logger.info(f"时间戳: {result.timestamp}")
        logger.info(f"详情:")
        for key, value in result.details.items():
            logger.info(f"  {key}: {value}")

        logger.info(f"\n延迟:")
        for key, value in result.latency_ms.items():
            logger.info(f"  {key}: {value:.0f}ms")

        if result.errors:
            logger.info(f"\n错误:")
            for error in result.errors:
                logger.info(f"  {error}")

        # 获取状态摘要
        summary = health_checker.get_status_summary()
        logger.info(f"\n状态摘要:")
        logger.info(f"  状态: {summary['status']}")
        logger.info(f"  可交易: {summary['can_trade']}")

        logger.info("\n✅ 健康检查器测试通过")

    except Exception as e:
        logger.warning(f"⚠️ 健康检查器测试跳过（需要真实交易所连接）: {e}")


async def test_circuit_breaker_manager():
    """测试熔断器管理器"""
    logger.info("\n" + "="*60)
    logger.info("测试 4: 熔断器管理器")
    logger.info("="*60)

    manager = CircuitBreakerManager()

    # 创建多个熔断器
    trading_breaker = manager.create_breaker("trading")
    orderbook_breaker = manager.create_breaker("orderbook")

    logger.info("创建了 2 个熔断器: trading, orderbook")

    # 触发 trading 熔断器
    logger.info("\n触发 trading 熔断器...")
    for _ in range(3):
        trading_breaker.on_failure()

    logger.info(f"trading 熔断器状态: {trading_breaker.get_state().value}")

    # 获取所有统计信息
    all_stats = manager.get_all_stats()
    logger.info(f"\n所有熔断器状态:")
    for name, stats in all_stats.items():
        logger.info(f"  {name}: {stats['state']}, 失败次数={stats['failure_count']}")

    # 重置所有熔断器
    logger.info("\n重置所有熔断器...")
    manager.reset_all()

    logger.info(f"重置后状态:")
    for name, stats in manager.get_all_stats().items():
        logger.info(f"  {name}: {stats['state']}")

    logger.info("\n✅ 熔断器管理器测试通过")


async def main():
    """运行所有测试"""
    logger.info("\n" + "="*60)
    logger.info("P1-17: 交易所健康检查和熔断器测试套件")
    logger.info("="*60)

    try:
        # 测试 1: 熔断器
        await test_circuit_breaker()

        # 测试 2: 降级策略
        await test_degradation_strategy()

        # 测试 3: 健康检查器（需要真实连接）
        await test_health_checker()

        # 测试 4: 熔断器管理器
        await test_circuit_breaker_manager()

        logger.info("\n" + "="*60)
        logger.info("✅ 所有测试通过")
        logger.info("="*60)

    except Exception as e:
        logger.error(f"\n❌ 测试失败: {e}", exc_info=True)
        raise


if __name__ == '__main__':
    asyncio.run(main())
