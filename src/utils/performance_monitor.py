"""
性能监控模块 (Performance Monitor)

提供交易系统性能指标采集、分析和报告功能
"""
import time
import psutil
import logging
from datetime import datetime
from typing import Dict, List, Optional
from dataclasses import dataclass, field
from collections import deque
from pathlib import Path
import json

logger = logging.getLogger(__name__)


@dataclass
class PerformanceMetrics:
    """性能指标数据类"""
    timestamp: float
    cpu_percent: float
    memory_percent: float
    memory_mb: float
    latency_ms: Dict[str, float] = field(default_factory=dict)
    signal_count: int = 0
    trade_count: int = 0


class PerformanceMonitor:
    """
    性能监控器

    功能：
    1. 系统资源监控（CPU、内存）
    2. 交易延迟监控
    3. 信号生成统计
    4. 性能报告生成
    """

    def __init__(self, max_history: int = 1000):
        """
        初始化性能监控器

        Args:
            max_history: 最大历史记录数
        """
        self.max_history = max_history
        self.metrics_history: deque = deque(maxlen=max_history)
        self.start_time = time.time()

        # 延迟统计
        self.latency_samples: Dict[str, deque] = {}

        # 信号统计
        self.signal_count = 0
        self.trade_count = 0

        logger.info("✅ 性能监控器已初始化")

    def record_metrics(
        self,
        latency_ms: Optional[Dict[str, float]] = None,
        signal_increment: int = 0,
        trade_increment: int = 0
    ) -> PerformanceMetrics:
        """
        记录当前性能指标

        Args:
            latency_ms: 延迟数据（各个操作的毫秒数）
            signal_increment: 信号增量
            trade_increment: 交易增量

        Returns:
            当前性能指标
        """
        # 系统资源监控
        cpu_percent = psutil.cpu_percent(interval=0.1)
        memory_info = psutil.virtual_memory()
        memory_mb = memory_info.used / (1024 * 1024)

        # 更新统计
        self.signal_count += signal_increment
        self.trade_count += trade_increment

        # 记录延迟
        if latency_ms:
            for key, value in latency_ms.items():
                if key not in self.latency_samples:
                    self.latency_samples[key] = deque(maxlen=100)
                self.latency_samples[key].append(value)

        # 创建指标对象
        metrics = PerformanceMetrics(
            timestamp=time.time(),
            cpu_percent=cpu_percent,
            memory_percent=memory_info.percent,
            memory_mb=memory_mb,
            latency_ms=latency_ms or {},
            signal_count=self.signal_count,
            trade_count=self.trade_count
        )

        self.metrics_history.append(metrics)
        return metrics

    def get_latency_stats(self, operation: str) -> Dict[str, float]:
        """
        获取操作的延迟统计

        Args:
            operation: 操作名称

        Returns:
            延迟统计（最小、最大、平均、中位数）
        """
        if operation not in self.latency_samples or not self.latency_samples[operation]:
            return {
                'min': 0,
                'max': 0,
                'avg': 0,
                'median': 0,
                'count': 0
            }

        samples = list(self.latency_samples[operation])
        samples_sorted = sorted(samples)

        return {
            'min': samples_sorted[0],
            'max': samples_sorted[-1],
            'avg': sum(samples) / len(samples),
            'median': samples_sorted[len(samples_sorted) // 2],
            'count': len(samples)
        }

    def get_system_stats(self) -> Dict[str, float]:
        """
        获取系统资源统计

        Returns:
            系统资源统计
        """
        if not self.metrics_history:
            return {}

        metrics = list(self.metrics_history)

        return {
            'cpu_avg': sum(m.cpu_percent for m in metrics) / len(metrics),
            'cpu_max': max(m.cpu_percent for m in metrics),
            'memory_avg': sum(m.memory_percent for m in metrics) / len(metrics),
            'memory_max': max(m.memory_percent for m in metrics),
            'uptime_seconds': time.time() - self.start_time
        }

    def generate_report(self) -> str:
        """
        生成性能报告

        Returns:
            格式化的性能报告
        """
        system_stats = self.get_system_stats()

        report = f"""
{'='*60}
性能监控报告 (Performance Report)
{'='*60}

运行时间: {system_stats.get('uptime_seconds', 0) / 3600:.2f} 小时

系统资源:
- CPU 平均: {system_stats.get('cpu_avg', 0):.1f}% (最大: {system_stats.get('cpu_max', 0):.1f}%)
- 内存平均: {system_stats.get('memory_avg', 0):.1f}% (最大: {system_stats.get('memory_max', 0):.1f}%)

交易统计:
- 信号总数: {self.signal_count}
- 交易次数: {self.trade_count}

延迟统计:
"""

        # 添加延迟统计
        for operation in sorted(self.latency_samples.keys()):
            stats = self.get_latency_stats(operation)
            report += f"- {operation}: {stats['avg']:.1f}ms (min: {stats['min']:.1f}ms, max: {stats['max']:.1f}ms, count: {stats['count']})\n"

        report += f"{'='*60}\n"
        return report

    def save_report(self, filepath: Optional[Path] = None) -> Path:
        """
        保存性能报告到文件

        Args:
            filepath: 保存路径（默认：logs/performance_report.json）

        Returns:
            保存的文件路径
        """
        if filepath is None:
            filepath = Path('logs/performance_report.json')

        # 确保目录存在
        filepath.parent.mkdir(parents=True, exist_ok=True)

        # 准备数据
        data = {
            'timestamp': datetime.now().isoformat(),
            'uptime_seconds': time.time() - self.start_time,
            'system_stats': self.get_system_stats(),
            'signal_count': self.signal_count,
            'trade_count': self.trade_count,
            'latency_stats': {
                op: self.get_latency_stats(op)
                for op in self.latency_samples.keys()
            },
            'recent_metrics': [
                {
                    'timestamp': m.timestamp,
                    'cpu_percent': m.cpu_percent,
                    'memory_percent': m.memory_percent,
                    'latency_ms': m.latency_ms
                }
                for m in list(self.metrics_history)[-100:]  # 最近100条
            ]
        }

        # 保存到文件
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        logger.info(f"✅ 性能报告已保存: {filepath}")
        return filepath

    def get_current_metrics(self) -> PerformanceMetrics:
        """
        获取当前性能指标

        Returns:
            最新的性能指标
        """
        return self.metrics_history[-1] if self.metrics_history else self.record_metrics()

    def check_performance_alerts(self) -> List[str]:
        """
        检查性能警告

        Returns:
            警告列表
        """
        alerts = []
        metrics = self.get_current_metrics()

        # CPU 警告
        if metrics.cpu_percent > 80:
            alerts.append(f"⚠️ CPU 使用率过高: {metrics.cpu_percent:.1f}%")

        # 内存警告
        if metrics.memory_percent > 80:
            alerts.append(f"⚠️ 内存使用率过高: {metrics.memory_percent:.1f}%")

        # 延迟警告
        for operation, samples in self.latency_samples.items():
            if samples:
                avg_latency = sum(samples) / len(samples)
                if avg_latency > 1000:  # 超过1秒
                    alerts.append(f"⚠️ {operation} 延迟过高: {avg_latency:.0f}ms")

        return alerts


# 全局性能监控器实例
_global_monitor: Optional[PerformanceMonitor] = None


def get_performance_monitor() -> PerformanceMonitor:
    """
    获取全局性能监控器实例

    Returns:
        性能监控器实例
    """
    global _global_monitor
    if _global_monitor is None:
        _global_monitor = PerformanceMonitor()
    return _global_monitor
