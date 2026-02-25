#!/usr/bin/env python3
"""
v7.2 监控面板启动脚本

启动实时监控面板
"""
import os
import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv

load_dotenv()

import asyncio
import logging

from src.monitoring.monitoring_collector import MonitoringCollector
from src.monitoring.monitoring_server import MonitoringServer
from src.exchange.sniper_position_manager import SniperPositionManager
from src.exchange.exchange_info_manager import BinanceExchangeInfo

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - [%(name)s] - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def main():
    """主函数"""
    # 读取配置
    testnet = os.getenv('BINANCE_TESTNET', 'true').lower() == 'true'
    monitoring_port = int(os.getenv('MONITORING_PORT', '8765'))

    # 初始化组件
    logger.info("初始化监控面板...")
    exchange_info = BinanceExchangeInfo(testnet=testnet)
    position_manager = SniperPositionManager(exchange_info)

    # 创建监控采集器
    collector = MonitoringCollector(
        position_manager=position_manager,
        obi_interceptor=None,
        ws_pool=None,
    )

    # 创建监控服务器
    server = MonitoringServer(
        collector=collector,
        port=monitoring_port,
    )

    logger.info(f"📊 监控面板启动: http://localhost:{monitoring_port}")

    # 启动服务器
    try:
        await server.start()
    except KeyboardInterrupt:
        logger.info("收到中断信号")
        server.stop()


if __name__ == '__main__':
    asyncio.run(main())
