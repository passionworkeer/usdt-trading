"""
交易日志系统 (Trading Logger)

提供结构化的交易日志记录
"""
import json
import logging
from datetime import datetime
from typing import Dict, List, Optional, Any
from pathlib import Path
from dataclasses import dataclass, field, asdict
from enum import Enum
import traceback

logger = logging.getLogger(__name__)


class LogLevel(Enum):
    """日志级别"""
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class TradeEvent(Enum):
    """交易事件"""
    # 扫描事件
    SCAN_START = "SCAN_START"
    SCAN_COMPLETE = "SCAN_COMPLETE"
    SIGNAL_DETECTED = "SIGNAL_DETECTED"
    SIGNAL_REJECTED = "SIGNAL_REJECTED"

    # 执行事件
    ORDER_PLACED = "ORDER_PLACED"
    ORDER_FILLED = "ORDER_FILLED"
    ORDER_CANCELLED = "ORDER_CANCELLED"
    ORDER_FAILED = "ORDER_FAILED"

    # 仓位事件
    POSITION_OPENED = "POSITION_OPENED"
    POSITION_UPDATED = "POSITION_UPDATED"
    POSITION_CLOSED = "POSITION_CLOSED"

    # 风险事件
    STOP_LOSS_TRIGGERED = "STOP_LOSS_TRIGGERED"
    TAKE_PROFIT_TRIGGERED = "TAKE_PROFIT_TRIGGERED"
    TIME_STOP_TRIGGERED = "TIME_STOP_TRIGGERED"
    EMERGENCY_CLOSE = "EMERGENCY_CLOSE"

    # 系统事件
    HEALTH_CHECK = "HEALTH_CHECK"
    API_ERROR = "API_ERROR"
    SYSTEM_ERROR = "SYSTEM_ERROR"


@dataclass
class TradeLogEntry:
    """交易日志条目"""
    timestamp: str
    event: str
    level: str
    message: str
    symbol: Optional[str] = None
    data: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    traceback: Optional[str] = None


class TradingLogger:
    """
    交易日志记录器

    功能：
    1. 结构化日志记录
    2. 分类筛选
    3. 日志统计
    4. 报告生成
    """

    def __init__(self, log_dir: str = "logs"):
        """
        初始化交易日志

        Args:
            log_dir: 日志目录
        """
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)

        # 按事件类型分类的日志文件
        self.log_files = {
            'trades': self.log_dir / "trades.log",
            'signals': self.log_dir / "signals.log",
            'errors': self.log_dir / "errors.log",
            'system': self.log_dir / "system.log",
            'all': self.log_dir / "trading.log"
        }

        # 初始化日志统计
        self.stats = {
            'total_logs': 0,
            'by_event': {},
            'by_level': {},
            'by_symbol': {}
        }

    def _get_log_file(self, event: TradeEvent) -> Path:
        """获取对应事件类型的日志文件"""
        # 交易事件
        if event in [TradeEvent.ORDER_PLACED, TradeEvent.ORDER_FILLED,
                     TradeEvent.ORDER_CANCELLED, TradeEvent.ORDER_FAILED,
                     TradeEvent.POSITION_OPENED, TradeEvent.POSITION_CLOSED]:
            return self.log_files['trades']

        # 信号事件
        if event in [TradeEvent.SIGNAL_DETECTED, TradeEvent.SIGNAL_REJECTED]:
            return self.log_files['signals']

        # 错误事件
        if event in [TradeEvent.API_ERROR, TradeEvent.SYSTEM_ERROR]:
            return self.log_files['errors']

        # 其他为系统事件
        return self.log_files['system']

    def _update_stats(self, entry: TradeLogEntry):
        """更新统计信息"""
        self.stats['total_logs'] += 1

        # 按事件类型统计
        event = entry.event
        self.stats['by_event'][event] = self.stats['by_event'].get(event, 0) + 1

        # 按级别统计
        level = entry.level
        self.stats['by_level'][level] = self.stats['by_level'].get(level, 0) + 1

        # 按交易对统计
        if entry.symbol:
            self.stats['by_symbol'][entry.symbol] = \
                self.stats['by_symbol'].get(entry.symbol, 0) + 1

    def log(
        self,
        event: TradeEvent,
        level: LogLevel,
        message: str,
        symbol: Optional[str] = None,
        data: Optional[Dict] = None,
        error: Optional[Exception] = None
    ):
        """
        记录日志

        Args:
            event: 交易事件
            level: 日志级别
            message: 日志消息
            symbol: 交易对
            data: 附加数据
            error: 异常对象
        """
        # 创建日志条目
        entry = TradeLogEntry(
            timestamp=datetime.now().isoformat(),
            event=event.value,
            level=level.value,
            message=message,
            symbol=symbol,
            data=data or {},
            error=str(error) if error else None,
            traceback=traceback.format_exc() if error else None
        )

        # 更新统计
        self._update_stats(entry)

        # 转换为 JSON 行
        log_line = json.dumps(asdict(entry), ensure_ascii=False)

        # 写入所有日志文件
        with open(self.log_files['all'], 'a', encoding='utf-8') as f:
            f.write(log_line + '\n')

        # 写入分类日志文件
        with open(self._get_log_file(event), 'a', encoding='utf-8') as f:
            f.write(log_line + '\n')

        # 输出到标准日志
        log_method = getattr(logger, level.value.lower(), logger.info)
        log_method(f"[{event.value}] {message}")

    # 便捷方法
    def log_scan_start(self, symbols: List[str]):
        """记录扫描开始"""
        self.log(TradeEvent.SCAN_START, LogLevel.INFO, f"开始扫描 {len(symbols)} 个交易对",
                  data={'symbols': symbols})

    def log_scan_complete(self, symbols: List[str], signal_count: int):
        """记录扫描完成"""
        self.log(TradeEvent.SCAN_COMPLETE, LogLevel.INFO, f"扫描完成，发现 {signal_count} 个信号",
                  data={'symbols': symbols, 'signal_count': signal_count})

    def log_signal_detected(self, symbol: str, action: str, confidence: float, reasons: List[str]):
        """记录检测到信号"""
        self.log(TradeEvent.SIGNAL_DETECTED, LogLevel.INFO, f"检测到信号: {symbol} {action}",
                  symbol=symbol, data={'action': action, 'confidence': confidence, 'reasons': reasons})

    def log_signal_rejected(self, symbol: str, reason: str):
        """记录信号被拒绝"""
        self.log(TradeEvent.SIGNAL_REJECTED, LogLevel.INFO, f"信号被拒绝: {symbol} - {reason}",
                  symbol=symbol, data={'reason': reason})

    def log_order_placed(self, symbol: str, order_type: str, quantity: float, price: float):
        """记录订单下单"""
        self.log(TradeEvent.ORDER_PLACED, LogLevel.INFO, f"订单已下单: {symbol}",
                  symbol=symbol, data={'order_type': order_type, 'quantity': quantity, 'price': price})

    def log_order_filled(self, symbol: str, quantity: float, price: float, pnl: Optional[float] = None):
        """记录订单成交"""
        data = {'quantity': quantity, 'price': price}
        if pnl is not None:
            data['pnl'] = pnl
        self.log(TradeEvent.ORDER_FILLED, LogLevel.INFO, f"订单成交: {symbol}", symbol=symbol, data=data)

    def log_order_failed(self, symbol: str, error: Exception):
        """记录订单失败"""
        self.log(TradeEvent.ORDER_FAILED, LogLevel.ERROR, f"订单失败: {symbol}",
                  symbol=symbol, error=error)

    def log_position_opened(self, symbol: str, side: str, quantity: float, entry_price: float):
        """记录开仓"""
        self.log(TradeEvent.POSITION_OPENED, LogLevel.INFO, f"仓位开启: {symbol} {side}",
                  symbol=symbol, data={'side': side, 'quantity': quantity, 'entry_price': entry_price})

    def log_position_closed(self, symbol: str, side: str, pnl: float, pnl_pct: float, close_reason: str):
        """记录平仓"""
        self.log(TradeEvent.POSITION_CLOSED, LogLevel.INFO, f"仓位平仓: {symbol} {side} PnL: {pnl:+.2f}",
                  symbol=symbol, data={'side': side, 'pnl': pnl, 'pnl_pct': pnl_pct, 'close_reason': close_reason})

    def log_stop_loss(self, symbol: str, entry_price: float, exit_price: float, pnl: float):
        """记录止损"""
        self.log(TradeEvent.STOP_LOSS_TRIGGERED, LogLevel.WARNING, f"触发止损: {symbol}",
                  symbol=symbol, data={'entry_price': entry_price, 'exit_price': exit_price, 'pnl': pnl})

    def log_take_profit(self, symbol: str, entry_price: float, exit_price: float, pnl: float):
        """记录止盈"""
        self.log(TradeEvent.TAKE_PROFIT_TRIGGERED, LogLevel.INFO, f"触发止盈: {symbol}",
                  symbol=symbol, data={'entry_price': entry_price, 'exit_price': exit_price, 'pnl': pnl})

    def log_api_error(self, error: Exception, context: Dict):
        """记录 API 错误"""
        self.log(TradeEvent.API_ERROR, LogLevel.ERROR, f"API 错误: {str(error)}",
                  error=error, data=context)

    def log_system_error(self, error: Exception, context: Dict):
        """记录系统错误"""
        self.log(TradeEvent.SYSTEM_ERROR, LogLevel.CRITICAL, f"系统错误: {str(error)}",
                  error=error, data=context)

    def get_stats(self) -> Dict:
        """获取日志统计"""
        return self.stats

    def generate_report(self) -> str:
        """生成日志报告"""
        stats = self.stats

        report = f"""
{'='*60}
📋 交易日志报告
{'='*60}

总日志条数: {stats['total_logs']}

按事件类型:
"""
        for event, count in sorted(stats['by_event'].items(), key=lambda x: x[1], reverse=True):
            report += f"  {event}: {count}\n"

        report += f"""
按级别:
"""
        for level, count in sorted(stats['by_level'].items(), key=lambda x: x[1], reverse=True):
            report += f"  {level}: {count}\n"

        if stats['by_symbol']:
            report += f"""
按交易对:
"""
            for symbol, count in sorted(stats['by_symbol'].items(), key=lambda x: x[1], reverse=True):
                report += f"  {symbol}: {count}\n"

        report += f"{'='*60}\n"
        return report


# 全局日志器实例
_global_logger: Optional[TradingLogger] = None


def get_trading_logger() -> TradingLogger:
    """获取全局交易日志器"""
    global _global_logger
    if _global_logger is None:
        _global_logger = TradingLogger()
    return _global_logger
