"""
v6.1 时间同步管理器（Time Sync Manager）

解决 Windows 本地时间不准导致的 Timestamp Drift 问题
"""
import asyncio
import logging
from typing import Optional
from datetime import datetime, timezone, timedelta

import aiohttp

logger = logging.getLogger(__name__)


class TimeSyncManager:
    """
    时间同步管理器

    功能：
    1. 系统启动时同步时间
    2. 每隔 1 小时自动同步
    3. 计算本地时间与服务器时间的偏移
    4. 每次发签名时自动修正时间戳

    币安要求：
    - 时间戳误差不能超过 1000ms
    - 否则报错：Timestamp for this request is outside of the recvWindow
    """

    # 币安时间服务端点
    BINANCE_TIME_URL = "https://fapi.binance.com/fapi/v1/time"
    BINANCE_TESTNET_TIME_URL = "https://stream.binancefuture.com/fapi/v1/time"

    # 同步间隔（秒）
    SYNC_INTERVAL = 3600  # 1 小时

    # 时间偏移阈值（毫秒）
    MAX_OFFSET_MS = 1000

    def __init__(self, testnet: bool = False):
        """
        初始化时间同步管理器

        Args:
            testnet: 是否测试网
        """
        self.testnet = testnet

        # 时间偏移（毫秒）
        self.time_offset_ms: int = 0

        # 同步状态
        self.last_sync_time: Optional[datetime] = None
        self.sync_count = 0

        # 运行状态
        self.running = False
        self.sync_task: Optional[asyncio.Task] = None

        logger.info(f"时间同步管理器初始化:")
        logger.info(f"   服务端点: {'Testnet' if testnet else 'Mainnet'}")
        logger.info(f"   同步间隔: {self.SYNC_INTERVAL} 秒")
        logger.info(f"   最大偏移: {self.MAX_OFFSET_MS} ms")

    async def get_server_time(self) -> Optional[int]:
        """
        获取服务器时间戳（毫秒）

        Returns:
            服务器时间戳（毫秒）
        """
        url = self.BINANCE_TESTNET_TIME_URL if self.testnet else self.BINANCE_TIME_URL

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=5) as response:
                    if response.status == 200:
                        data = await response.json()
                        server_time_ms = data.get('serverTime')
                        return server_time_ms
                    else:
                        logger.error(f"获取服务器时间失败: HTTP {response.status}")
                        return None

        except Exception as e:
            logger.error(f"获取服务器时间异常: {e}")
            return None

    async def sync_time(self) -> bool:
        """
        同步时间

        Returns:
            是否成功
        """
        logger.info("🕐 开始时间同步...")

        # 获取服务器时间
        server_time_ms = await self.get_server_time()
        if server_time_ms is None:
            logger.error("❌ 时间同步失败：无法获取服务器时间")
            return False

        # 获取本地时间
        local_time_ms = int(datetime.now(timezone.utc).timestamp() * 1000)

        # 计算偏移
        self.time_offset_ms = server_time_ms - local_time_ms

        # 检查偏移是否在可接受范围内
        if abs(self.time_offset_ms) > self.MAX_OFFSET_MS:
            logger.warning(
                f"⚠️ 时间偏移过大: {self.time_offset_ms} ms "
                f"(阈值: {self.MAX_OFFSET_MS} ms)"
            )
            logger.warning(
                f"   本地时间: {datetime.fromtimestamp(local_time_ms / 1000, tz=timezone.utc).isoformat()}"
            )
            logger.warning(
                f"   服务器时间: {datetime.fromtimestamp(server_time_ms / 1000, tz=timezone.utc).isoformat()}"
            )
            logger.warning(
                f"   建议同步 Windows 系统时间！"
            )
        else:
            logger.info(f"✅ 时间偏移: {self.time_offset_ms} ms（可接受）")

        # 更新同步时间
        self.last_sync_time = datetime.now(timezone.utc)
        self.sync_count += 1

        logger.info(f"🕐 时间同步完成 (第 {self.sync_count} 次)")

        return True

    def get_timestamp(self) -> int:
        """
        获取修正后的时间戳（毫秒）

        Returns:
            修正后的时间戳（毫秒）
        """
        local_time_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
        corrected_time_ms = local_time_ms + self.time_offset_ms
        return corrected_time_ms

    async def start_auto_sync(self) -> None:
        """启动自动同步"""
        self.running = True

        logger.info("启动自动时间同步...")

        # 首次同步
        await self.sync_time()

        # 定期同步
        async def sync_loop():
            while self.running:
                await asyncio.sleep(self.SYNC_INTERVAL)
                await self.sync_time()

        self.sync_task = asyncio.create_task(sync_loop())

        logger.info(f"✅ 自动时间同步已启动（间隔: {self.SYNC_INTERVAL} 秒）")

    async def stop_auto_sync(self) -> None:
        """停止自动同步"""
        self.running = False

        if self.sync_task:
            self.sync_task.cancel()
            try:
                await self.sync_task
            except asyncio.CancelledError:
                pass

        logger.info("自动时间同步已停止")

    def get_stats(self) -> dict:
        """获取统计信息"""
        return {
            'time_offset_ms': self.time_offset_ms,
            'last_sync_time': self.last_sync_time.isoformat() if self.last_sync_time else None,
            'sync_count': self.sync_count,
            'running': self.running,
        }


# 全局实例
_time_sync_manager: Optional[TimeSyncManager] = None


def get_time_sync_manager(testnet: bool = False) -> TimeSyncManager:
    """获取全局时间同步管理器实例"""
    global _time_sync_manager
    if _time_sync_manager is None:
        _time_sync_manager = TimeSyncManager(testnet=testnet)
    return _time_sync_manager


async def ensure_time_sync() -> None:
    """确保时间已同步"""
    manager = get_time_sync_manager()
    if not manager.running:
        await manager.start_auto_sync()


if __name__ == '__main__':
    # 测试代码
    import asyncio
    from datetime import timezone, timedelta

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - [%(name)s] - %(levelname)s - %(message)s'
    )

    async def test_time_sync():
        manager = TimeSyncManager(testnet=True)

        # 测试同步
        success = await manager.sync_time()
        print(f"同步结果: {success}")

        # 测试获取时间戳
        timestamp = manager.get_timestamp()
        print(f"修正后时间戳: {timestamp}")

        # 打印统计
        print("\n统计信息:")
        print(manager.get_stats())

        # 测试自动同步
        print("\n启动自动同步（10秒后停止）...")
        await manager.start_auto_sync()

        await asyncio.sleep(10)

        await manager.stop_auto_sync()

    asyncio.run(test_time_sync())
