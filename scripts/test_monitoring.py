#!/usr/bin/env python3
"""
v7.2 监控面板测试脚本

模拟交易数据，测试监控面板功能
"""
import asyncio
import random
import logging
from datetime import datetime, timezone

from src.monitoring.monitoring_collector import MonitoringCollector
from src.monitoring.monitoring_server import MonitoringServer
from src.exchange.sniper_position_manager import (
    SniperPositionManager,
    SniperPosition,
    Side,
    PositionStatus,
)
from src.exchange.exchange_info_manager import BinanceExchangeInfo

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - [%(name)s] - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def test_monitoring():
    """测试监控面板"""
    logger.info("🧪 启动监控面板测试...")

    # 初始化组件
    exchange_info = BinanceExchangeInfo(testnet=True)
    position_manager = SniperPositionManager(exchange_info)

    # 创建模拟仓位
    position = SniperPosition(
        symbol='BTC/USDT',
        side=Side.LONG,
        entry_price=50000.0,
        quantity=0.01,
        leverage=20,
        stop_loss_price=47500.0,
        take_profit_price=60000.0,
        trailing_stop_price=52000.0,
        entry_time=datetime.now(timezone.utc),
    )
    position_manager.open_position(position)

    # 创建监控采集器
    collector = MonitoringCollector(
        position_manager=position_manager,
        obi_interceptor=None,
        ws_pool=None,
    )

    # 创建监控服务器
    server = MonitoringServer(
        collector=collector,
        port=8765,
    )

    logger.info("📊 监控面板: http://localhost:8765")
    logger.info("🧪 模拟数据生成中...")

    # 模拟数据更新
    current_price = 50000.0

    try:
        while True:
            # 模拟价格波动
            price_change = random.uniform(-200, 200)
            current_price += price_change

            # 更新价格缓存
            await collector.update_price_cache('BTC/USDT', current_price)

            # 随机生成事件
            if random.random() < 0.1:  # 10% 概率
                event_type = random.choice(['open', 'close', 'warning'])
                event = {
                    'type': event_type,
                    'symbol': 'BTC/USDT',
                    'message': f"模拟事件 {event_type}: 价格 ${current_price:.2f}",
                }
                server.add_event(event)

            # 打印当前状态
            pnl = collector.calculate_pnl(
                position.entry_price,
                current_price,
                position.quantity,
                position.side,
                position.leverage,
            )
            roe = collector.calculate_roe(
                position.entry_price,
                current_price,
                position.side,
                position.leverage,
            )

            logger.info(
                f"价格: ${current_price:.2f} | "
                f"盈亏: ${pnl:+.2f} | "
                f"ROE: {roe*100:+.2f}%"
            )

            await asyncio.sleep(2)

    except KeyboardInterrupt:
        logger.info("测试结束")
        server.stop()


if __name__ == '__main__':
    asyncio.run(test_monitoring())
