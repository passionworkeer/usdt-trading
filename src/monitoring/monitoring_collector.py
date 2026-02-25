"""
v7.2 实时监控数据采集器（Real-Time Monitoring Data Collector）

为 Web 监控面板提供实时数据
"""
import asyncio
import logging
from typing import Dict, List, Any, Optional
from datetime import datetime, timezone
import psutil

from ..exchange.sniper_position_manager import SniperPositionManager, Side
from ..exchange.obi_interceptor import OrderBookImbalanceInterceptor
from ..exchange.websocket_pool import BinanceWebSocketPool
from ..utils.time_sync_manager import get_time_sync_manager

logger = logging.getLogger(__name__)


class MonitoringCollector:
    """
    监控数据采集器

    采集内容：
    1. 仓位和盈亏数据
    2. WebSocket 连接状态
    3. OBI 拦截统计
    4. 系统健康指标
    5. 交易统计
    """

    def __init__(
        self,
        position_manager: SniperPositionManager,
        obi_interceptor: Optional[OrderBookImbalanceInterceptor] = None,
        ws_pool: Optional[BinanceWebSocketPool] = None,
    ):
        """
        初始化监控数据采集器

        Args:
            position_manager: 仓位管理器
            obi_interceptor: OBI 拦截器
            ws_pool: WebSocket 连接池
        """
        self.position_manager = position_manager
        self.obi_interceptor = obi_interceptor
        self.ws_pool = ws_pool

        # 时间同步管理器
        self.time_sync = get_time_sync_manager()

        # 价格缓存（用于计算未实现盈亏）
        self.price_cache: Dict[str, float] = {}

        logger.info("📊 监控数据采集器初始化完成")

    async def update_price_cache(self, symbol: str, price: float) -> None:
        """
        更新价格缓存

        Args:
            symbol: 交易对
            price: 当前价格
        """
        self.price_cache[symbol] = price

    def calculate_pnl(
        self,
        entry_price: float,
        current_price: float,
        quantity: float,
        side: Side,
        leverage: int = 1,
    ) -> float:
        """
        计算未实现盈亏

        Args:
            entry_price: 入场价
            current_price: 当前价格
            quantity: 数量
            side: 方向
            leverage: 杠杆

        Returns:
            盈亏（USDT）
        """
        if side == Side.LONG:
            pnl = (current_price - entry_price) * quantity
        else:  # SHORT
            pnl = (entry_price - current_price) * quantity

        return pnl

    def calculate_roe(
        self,
        entry_price: float,
        current_price: float,
        side: Side,
        leverage: int = 1,
    ) -> float:
        """
        计算 ROE（Return on Equity）

        Args:
            entry_price: 入场价
            current_price: 当前价格
            side: 方向
            leverage: 杠杆

        Returns:
            ROE（百分比）
        """
        if side == Side.LONG:
            price_change_pct = (current_price - entry_price) / entry_price
        else:  # SHORT
            price_change_pct = (entry_price - current_price) / entry_price

        roe = price_change_pct * leverage
        return roe

    async def collect_positions_data(self) -> Dict[str, Any]:
        """
        采集仓位数据

        Returns:
            仓位数据字典
        """
        positions_data = []

        for symbol, position in self.position_manager.positions.items():
            # 获取当前价格
            current_price = self.price_cache.get(symbol, position.entry_price)

            # 计算盈亏
            pnl = self.calculate_pnl(
                position.entry_price,
                current_price,
                position.quantity,
                position.side,
                position.leverage,
            )

            # 计算 ROE
            roe = self.calculate_roe(
                position.entry_price,
                current_price,
                position.side,
                position.leverage,
            )

            # 计算持仓时间
            holding_duration = (datetime.now(timezone.utc) - position.entry_time).total_seconds()

            positions_data.append({
                'symbol': position.symbol,
                'side': position.side.value,
                'entry_price': position.entry_price,
                'current_price': current_price,
                'quantity': position.quantity,
                'leverage': position.leverage,
                'pnl': pnl,
                'roe': roe,
                'stop_loss_price': position.stop_loss_price,
                'take_profit_price': position.take_profit_price,
                'trailing_stop_price': position.trailing_stop_price,
                'entry_time': position.entry_time.isoformat(),
                'holding_duration': holding_duration,
                'status': position.status.value,
            })

        # 计算总未实现盈亏
        total_pnl = sum(p['pnl'] for p in positions_data)

        return {
            'positions': positions_data,
            'total_pnl': total_pnl,
            'position_count': len(positions_data),
        }

    async def collect_trading_stats(self) -> Dict[str, Any]:
        """
        采集交易统计

        Returns:
            交易统计数据
        """
        stats = self.position_manager.get_trading_statistics()

        return {
            'total_trades': stats.get('total_trades', 0),
            'win_rate': stats.get('win_rate', 0.0),
            'avg_pnl': stats.get('avg_pnl', 0.0),
            'total_pnl': stats.get('total_pnl', 0.0),
        }

    async def collect_websocket_stats(self) -> Dict[str, Any]:
        """
        采集 WebSocket 统计

        Returns:
            WebSocket 统计数据
        """
        if not self.ws_pool:
            return {
                'enabled': False,
                'message': 'WebSocket pool not initialized',
            }

        stats = self.ws_pool.get_pool_stats()

        return {
            'enabled': True,
            'running': stats.get('running', False),
            'total_connections': stats.get('total_connections', 0),
            'active_connections': stats.get('active_connections', 0),
            'total_subscriptions': stats.get('total_subscriptions', 0),
            'total_messages': stats.get('total_messages', 0),
            'total_errors': stats.get('total_errors', 0),
        }

    async def collect_obi_stats(self) -> Dict[str, Any]:
        """
        采集 OBI 统计

        Returns:
            OBI 统计数据
        """
        if not self.obi_interceptor:
            return {
                'enabled': False,
                'message': 'OBI interceptor not initialized',
            }

        stats = self.obi_interceptor.get_stats()

        return {
            'enabled': True,
            'update_count': stats.get('update_count', 0),
            'reject_count': stats.get('reject_count', 0),
            'reject_rate': stats.get('reject_count', 0) / max(stats.get('update_count', 1), 1),
            'symbols_tracked': stats.get('symbols_tracked', []),
        }

    async def collect_system_health(self) -> Dict[str, Any]:
        """
        采集系统健康指标

        Returns:
            系统健康数据
        """
        try:
            cpu_percent = psutil.cpu_percent(interval=0.1)
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage('.')

            return {
                'cpu_percent': cpu_percent,
                'memory_percent': memory.percent,
                'memory_used_gb': memory.used / (1024 ** 3),
                'memory_total_gb': memory.total / (1024 ** 3),
                'disk_percent': disk.percent,
                'disk_used_gb': disk.used / (1024 ** 3),
                'disk_total_gb': disk.total / (1024 ** 3),
            }
        except Exception as e:
            logger.error(f"采集系统健康指标失败: {e}")
            return {
                'error': str(e),
            }

    async def collect_time_sync_status(self) -> Dict[str, Any]:
        """
        采集时间同步状态

        Returns:
            时间同步状态
        """
        if not self.time_sync:
            return {
                'enabled': False,
                'message': 'Time sync manager not initialized',
            }

        return {
            'enabled': True,
            'time_offset_ms': self.time_sync.time_offset_ms,
            'last_sync_time': self.time_sync.last_sync_time.isoformat() if self.time_sync.last_sync_time else None,
        }

    async def collect_all(self) -> Dict[str, Any]:
        """
        采集所有监控数据

        Returns:
            完整监控数据
        """
        try:
            # 并发采集所有数据
            positions_task = self.collect_positions_data()
            trading_stats_task = self.collect_trading_stats()
            ws_stats_task = self.collect_websocket_stats()
            obi_stats_task = self.collect_obi_stats()
            system_health_task = self.collect_system_health()
            time_sync_task = self.collect_time_sync_status()

            (
                positions_data,
                trading_stats,
                ws_stats,
                obi_stats,
                system_health,
                time_sync_status,
            ) = await asyncio.gather(
                positions_task,
                trading_stats_task,
                ws_stats_task,
                obi_stats_task,
                system_health_task,
                time_sync_task,
            )

            return {
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'positions': positions_data,
                'trading_stats': trading_stats,
                'websocket': ws_stats,
                'obi': obi_stats,
                'system_health': system_health,
                'time_sync': time_sync_status,
            }

        except Exception as e:
            logger.error(f"采集监控数据失败: {e}", exc_info=True)
            return {
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'error': str(e),
            }
