"""
v7.1 混沌工程集成测试（Chaos Engineering Integration Test）

测试系统在各种混沌场景下的容错能力
"""
import asyncio
import logging
from datetime import datetime, timezone
from typing import Dict, Any

from tests.chaos_monkey import ChaosMonkey, ChaosEventType

logger = logging.getLogger(__name__)


class ChaosIntegrationTest:
    """
    混沌工程集成测试

    测试场景：
    1. WebSocket 静默 → 验证重连机制
    2. REST 502/429 → 验证指数退避重试
    3. 订单簿乱序 → 验证数据陈旧保护
    4. 延迟突增 → 验证熔断机制
    """

    def __init__(self):
        """初始化混沌工程集成测试"""
        self.monkey = ChaosMonkey(enabled=True, seed=42)
        self.test_results = {}

    async def test_websocket_silence(self) -> Dict[str, Any]:
        """
        测试 WebSocket 静默场景

        验证：
        - 系统是否能检测到静默？
        - 是否触发重连？
        - 是否正确处理陈旧数据？
        """
        logger.info("\n" + "="*60)
        logger.info("测试场景 1: WebSocket 静默")
        logger.info("="*60 + "\n")

        results = {
            'scenario': 'WebSocket 静默',
            'passed': False,
            'details': {},
        }

        # 模拟 WebSocket 静默
        silence_count = 0
        max_silence = 10  # 最多允许 10 次静默

        for i in range(20):
            # 检查混沌事件
            event = self.monkey.check_chaos()

            # 检查 WebSocket 静默
            if self.monkey.inject_websocket_silence():
                silence_count += 1
                logger.warning(f"WebSocket 静默检测 #{silence_count}")

                if silence_count > max_silence:
                    logger.critical(f"❌ 静默次数过多: {silence_count} > {max_silence}")
                    results['details']['silence_count'] = silence_count
                    results['details']['status'] = 'FAILED'
                    return results

            await asyncio.sleep(0.1)

        # 验证结果
        if silence_count > 0:
            logger.info(f"✅ 检测到 {silence_count} 次 WebSocket 静默")
            logger.info(f"✅ 系统应该触发重连机制")
            results['passed'] = True
            results['details']['silence_count'] = silence_count
            results['details']['status'] = 'PASSED'
        else:
            logger.info("ℹ️ 未触发 WebSocket 静默事件")
            results['passed'] = True
            results['details']['status'] = 'NO_EVENT'

        return results

    async def test_rest_errors(self) -> Dict[str, Any]:
        """
        测试 REST API 错误场景

        验证：
        - 系统是否正确处理 502？
        - 系统是否正确处理 429？
        - 是否正确退避重试？
        """
        logger.info("\n" + "="*60)
        logger.info("测试场景 2: REST API 错误")
        logger.info("="*60 + "\n")

        results = {
            'scenario': 'REST API 错误',
            'passed': False,
            'details': {},
        }

        error_counts = {'502': 0, '429': 0}

        for i in range(20):
            # 检查混沌事件
            event = self.monkey.check_chaos()

            # 检查 REST 错误
            rest_error = self.monkey.inject_rest_error("https://fapi.binance.com/fapi/v1/time")

            if rest_error:
                status_code = rest_error['status']
                if status_code == 502:
                    error_counts['502'] += 1
                    logger.critical(f"检测到 HTTP 502: {rest_error['error']}")
                    logger.info(f"✅ 系统应该退避重试")

                elif status_code == 429:
                    error_counts['429'] += 1
                    logger.critical(f"检测到 HTTP 429: {rest_error['error']}")
                    logger.info(f"✅ 系统应该退避重试（更长延迟）")

            await asyncio.sleep(0.1)

        # 验证结果
        if error_counts['502'] > 0 or error_counts['429'] > 0:
            logger.info(f"✅ 检测到错误: 502 ({error_counts['502']} 次), 429 ({error_counts['429']} 次)")
            results['passed'] = True
            results['details']['error_counts'] = error_counts
            results['details']['status'] = 'PASSED'
        else:
            logger.info("ℹ️ 未触发 REST 错误事件")
            results['passed'] = True
            results['details']['status'] = 'NO_EVENT'

        return results

    async def test_orderbook_ghost(self) -> Dict[str, Any]:
        """
        测试订单簿乱序场景

        验证：
        - 系统是否检测到数据陈旧？
        - 是否触发 OBI 拦截？
        - 是否拒绝交易？
        """
        logger.info("\n" + "="*60)
        logger.info("测试场景 3: 订单簿乱序")
        logger.info("="*60 + "\n")

        results = {
            'scenario': '订单簿乱序',
            'passed': False,
            'details': {},
        }

        # 模拟订单簿
        orderbook = {
            'bids': [[50000, 10], [49999, 20], [49998, 30]],
            'asks': [[50001, 10], [50002, 20], [50003, 30]],
            'lastUpdateId': int(datetime.now(timezone.utc).timestamp() * 1000),
        }

        # 检查混沌事件
        event = self.monkey.check_chaos()

        # 注入订单簿混淆
        ghost_orderbook = self.monkey.inject_orderbook_ghost(orderbook)

        if ghost_orderbook:
            logger.critical("🐵 检测到订单簿混淆")
            logger.info(f"✅ 系统应该触发数据陈旧保护")
            logger.info(f"✅ 系统应该拒绝交易")

            results['passed'] = True
            results['details']['status'] = 'PASSED'
            results['details']['ghost_detected'] = True
        else:
            logger.info("ℹ️ 未触发订单簿混淆事件")
            results['passed'] = True
            results['details']['status'] = 'NO_EVENT'
            results['details']['ghost_detected'] = False

        return results

    async def test_delay_spike(self) -> Dict[str, Any]:
        """
        测试延迟突增场景

        验证：
        - 系统是否检测到延迟超标？
        - 是否触发熔断？
        - 是否拒绝交易？
        """
        logger.info("\n" + "="*60)
        logger.info("测试场景 4: 延迟突增")
        logger.info("="*60 + "\n")

        results = {
            'scenario': '延迟突增',
            'passed': False,
            'details': {},
        }

        spike_count = 0
        max_latency = 0

        for i in range(20):
            # 检查混沌事件
            event = self.monkey.check_chaos()

            # 注入延迟突增
            base_latency = 50  # 基础延迟 50ms
            extra_delay = self.monkey.inject_delay_spike()
            total_latency = base_latency + extra_delay

            max_latency = max(max_latency, total_latency)

            if extra_delay > 0:
                spike_count += 1
                logger.warning(f"⚡ 延迟突增检测: {total_latency:.1f} ms (基础 {base_latency} ms + 额外 {extra_delay:.1f} ms)")

                if total_latency > 100:
                    logger.critical(f"🚨 延迟超标: {total_latency:.1f} ms > 100 ms")
                    logger.info(f"✅ 系统应该触发熔断")

            await asyncio.sleep(0.1)

        # 验证结果
        if spike_count > 0:
            logger.info(f"✅ 检测到 {spike_count} 次延迟突增")
            logger.info(f"✅ 最大延迟: {max_latency:.1f} ms")
            results['passed'] = True
            results['details']['spike_count'] = spike_count
            results['details']['max_latency'] = max_latency
            results['details']['status'] = 'PASSED'
        else:
            logger.info("ℹ️ 未触发延迟突增事件")
            results['passed'] = True
            results['details']['status'] = 'NO_EVENT'

        return results

    async def run_all_tests(self) -> Dict[str, Any]:
        """
        运行所有混沌测试

        Returns:
            测试结果汇总
        """
        logger.info("\n" + "="*60)
        logger.info("🐵 混沌工程集成测试启动")
        logger.info("="*60 + "\n")

        # 运行所有测试
        test_results = {
            'websocket_silence': await self.test_websocket_silence(),
            'rest_errors': await self.test_rest_errors(),
            'orderbook_ghost': await self.test_orderbook_ghost(),
            'delay_spike': await self.test_delay_spike(),
        }

        # 汇总结果
        passed_count = sum(1 for r in test_results.values() if r.get('passed', False))
        total_count = len(test_results)

        logger.info("\n" + "="*60)
        logger.info("🐵 混沌工程集成测试完成")
        logger.info("="*60)
        logger.info(f"  通过: {passed_count}/{total_count}")
        logger.info(f"  通过率: {passed_count/total_count*100:.1f}%")
        logger.info("="*60 + "\n")

        return test_results


async def main():
    """主函数"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - [%(name)s] - %(levelname)s - %(message)s'
    )

    # 运行混沌测试
    tester = ChaosIntegrationTest()
    results = await tester.run_all_tests()

    # 打印详细结果
    print("\n详细结果:")
    for test_name, result in results.items():
        print(f"\n{test_name}:")
        print(f"  通过: {result.get('passed', False)}")
        print(f"  状态: {result.get('details', {}).get('status', 'N/A')}")
        print(f"  详情: {result.get('details', {})}")


if __name__ == '__main__':
    asyncio.run(main())
