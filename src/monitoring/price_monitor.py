"""
实时价格监控服务 - WebSocket 和定时轮询
"""
import asyncio
import logging
import threading
import time
from typing import Dict, List, Optional, Callable, Set
from dataclasses import dataclass, field
from datetime import datetime
from collections import deque

logger = logging.getLogger(__name__)


@dataclass
class PriceData:
    """价格数据"""
    symbol: str
    price: float
    timestamp: datetime
    volume: float = 0
    change_24h: float = 0
    high_24h: float = 0
    low_24h: float = 0


@dataclass
class PriceAlert:
    """价格警报"""
    symbol: str
    condition: str  # 'above', 'below', 'change_up', 'change_down'
    target: float
    callback: Callable
    triggered: bool = False


class PriceMonitor:
    """实时价格监控器"""

    def __init__(self, executor, check_interval: int = 60):
        """
        初始化价格监控器

        Args:
            executor: 订单执行器
            check_interval: 检查间隔（秒）
        """
        self.executor = executor
        self.check_interval = check_interval

        self.monitored_symbols: Set[str] = set()
        self.price_history: Dict[str, deque] = {}  # 价格历史
        self.current_prices: Dict[str, PriceData] = {}
        self.alerts: List[PriceAlert] = []

        self.running = False
        self.monitor_thread: Optional[threading.Thread] = None
        self.callbacks: List[Callable] = []

        self.history_max_length = 1000  # 保留最近 1000 个价格点

        logger.info(f"价格监控器已初始化，检查间隔: {check_interval}秒")

    def add_symbol(self, symbol: str):
        """添加监控的交易对"""
        if symbol not in self.monitored_symbols:
            self.monitored_symbols.add(symbol)
            self.price_history[symbol] = deque(maxlen=self.history_max_length)
            logger.info(f"添加监控: {symbol}")

    def remove_symbol(self, symbol: str):
        """移除监控的交易对"""
        if symbol in self.monitored_symbols:
            self.monitored_symbols.remove(symbol)
            if symbol in self.price_history:
                del self.price_history[symbol]
            logger.info(f"移除监控: {symbol}")

    def set_symbols(self, symbols: List[str]):
        """设置监控的交易对列表"""
        self.monitored_symbols = set(symbols)
        for symbol in symbols:
            if symbol not in self.price_history:
                self.price_history[symbol] = deque(maxlen=self.history_max_length)

        # 清理不需要的历史
        for symbol in list(self.price_history.keys()):
            if symbol not in self.monitored_symbols:
                del self.price_history[symbol]

        logger.info(f"设置监控列表: {symbols}")

    def add_price_callback(self, callback: Callable):
        """
        添加价格更新回调

        Args:
            callback: 回调函数，接收 PriceData 参数
        """
        self.callbacks.append(callback)

    def add_alert(self, symbol: str, condition: str, target: float,
                  callback: Callable) -> PriceAlert:
        """
        添加价格警报

        Args:
            symbol: 交易对
            condition: 条件 ('above', 'below', 'change_up', 'change_down')
            target: 目标值
            callback: 触发回调

        Returns:
            警报对象
        """
        alert = PriceAlert(
            symbol=symbol,
            condition=condition,
            target=target,
            callback=callback
        )
        self.alerts.append(alert)
        logger.info(f"添加价格警报: {symbol} {condition} {target}")
        return alert

    def remove_alert(self, alert: PriceAlert):
        """移除警报"""
        if alert in self.alerts:
            self.alerts.remove(alert)

    def _check_alerts(self, price_data: PriceData):
        """检查价格警报"""
        for alert in self.alerts:
            if alert.triggered or alert.symbol != price_data.symbol:
                continue

            triggered = False

            if alert.condition == 'above' and price_data.price >= alert.target:
                triggered = True
            elif alert.condition == 'below' and price_data.price <= alert.target:
                triggered = True
            elif alert.condition == 'change_up':
                # 检查涨幅
                if len(self.price_history[alert.symbol]) > 1:
                    prev_price = self.price_history[alert.symbol][-2]
                    change_pct = (price_data.price - prev_price) / prev_price * 100
                    if change_pct >= alert.target:
                        triggered = True
            elif alert.condition == 'change_down':
                # 检查跌幅
                if len(self.price_history[alert.symbol]) > 1:
                    prev_price = self.price_history[alert.symbol][-2]
                    change_pct = (price_data.price - prev_price) / prev_price * 100
                    if change_pct <= -alert.target:
                        triggered = True

            if triggered:
                alert.triggered = True
                logger.info(f"警报触发: {alert.symbol} {alert.condition} {alert.target}")
                try:
                    alert.callback(price_data, alert)
                except Exception as e:
                    logger.error(f"警报回调失败: {e}")

    def _notify_callbacks(self, price_data: PriceData):
        """通知所有回调"""
        for callback in self.callbacks:
            try:
                callback(price_data)
            except Exception as e:
                logger.error(f"回调执行失败: {e}")

    def _fetch_prices(self):
        """获取所有监控交易对的价格"""
        for symbol in self.monitored_symbols:
            try:
                ticker = self.executor.get_ticker(symbol)

                price_data = PriceData(
                    symbol=symbol,
                    price=ticker['last'],
                    timestamp=datetime.now(),
                    volume=ticker.get('volume', 0),
                    change_24h=ticker.get('percentage', 0),
                    high_24h=ticker.get('high', ticker['last']),
                    low_24h=ticker.get('low', ticker['last']),
                )

                # 更新当前价格
                self.current_prices[symbol] = price_data

                # 添加到历史
                self.price_history[symbol].append(price_data.price)

                # 检查警报
                self._check_alerts(price_data)

                # 通知回调
                self._notify_callbacks(price_data)

                logger.debug(f"{symbol}: {price_data.price} ({price_data.change_24h:+.2f}%)")

            except Exception as e:
                logger.error(f"获取 {symbol} 价格失败: {e}")

    def _monitor_loop(self):
        """监控循环"""
        logger.info("价格监控循环开始")

        while self.running:
            try:
                self._fetch_prices()
            except Exception as e:
                logger.error(f"监控循环错误: {e}")

            # 分段睡眠，以便更快响应停止
            for _ in range(self.check_interval):
                if not self.running:
                    break
                time.sleep(1)

        logger.info("价格监控循环结束")

    def start(self):
        """启动监控"""
        if self.running:
            logger.warning("监控已在运行")
            return

        self.running = True
        self.monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.monitor_thread.start()
        logger.info("价格监控已启动")

    def stop(self):
        """停止监控"""
        if not self.running:
            return

        logger.info("停止价格监控...")
        self.running = False

        if self.monitor_thread:
            self.monitor_thread.join(timeout=5)
            self.monitor_thread = None

        logger.info("价格监控已停止")

    def get_current_price(self, symbol: str) -> Optional[float]:
        """获取当前价格"""
        if symbol in self.current_prices:
            return self.current_prices[symbol].price
        return None

    def get_price_history(self, symbol: str, limit: int = 100) -> List[float]:
        """获取价格历史"""
        if symbol not in self.price_history:
            return []

        history = list(self.price_history[symbol])
        return history[-limit:]

    def get_stats(self) -> Dict:
        """获取监控统计"""
        return {
            'running': self.running,
            'monitored_symbols': list(self.monitored_symbols),
            'alerts_count': len(self.alerts),
            'callbacks_count': len(self.callbacks),
            'last_update': max(
                (p.timestamp for p in self.current_prices.values()),
                default=None
            ),
        }


class WebSocketPriceMonitor(PriceMonitor):
    """基于 WebSocket 的实时价格监控（高级版本）"""

    def __init__(self, executor, check_interval: int = 60):
        super().__init__(executor, check_interval)
        self.ws = None
        self.ws_thread = None
        # 注意：完整的 WebSocket 实现需要额外的库（如 websockets）
        # 这里提供框架，实际 WebSocket 连接需要额外实现

    def start_websocket(self):
        """启动 WebSocket 连接"""
        # TODO: 实现 WebSocket 连接
        logger.warning("WebSocket 监控尚未实现，使用轮询模式")
        self.start()

    def stop_websocket(self):
        """停止 WebSocket 连接"""
        self.stop()
