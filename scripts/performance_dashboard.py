#!/usr/bin/env python3
"""
性能监控仪表板 (Performance Dashboard)

实时显示交易系统性能指标
"""
import asyncio
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, Any

# ANSI 颜色代码
class Colors:
    RESET = '\033[0m'
    RED = '\033[91m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    MAGENTA = '\033[95m'
    CYAN = '\033[96m'
    WHITE = '\033[97m'
    BOLD = '\033[1m'


def print_header(title: str):
    """打印标题"""
    print(f"\n{Colors.BOLD}{Colors.CYAN}{'='*70}{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.CYAN}{title.center(70)}{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.CYAN}{'='*70}{Colors.RESET}\n")


def print_metric(label: str, value: str, unit: str = "", color: str = Colors.WHITE):
    """打印指标"""
    print(f"{Colors.WHITE}{label:<30}: {color}{value}{unit}{Colors.RESET}")


def print_bar(label: str, value: float, max_value: float = 100, width: int = 30):
    """打印进度条"""
    percentage = min(value / max_value, 1.0)
    filled = int(percentage * width)

    # 选择颜色
    if percentage < 0.5:
        color = Colors.GREEN
    elif percentage < 0.8:
        color = Colors.YELLOW
    else:
        color = Colors.RED

    bar = '█' * filled + '░' * (width - filled)
    print(f"{Colors.WHITE}{label:<30}: {color}[{bar}]{Colors.RESET} {value:.1f}%")


def load_performance_data() -> Dict[str, Any]:
    """加载性能数据"""
    report_file = Path('logs/performance_report.json')
    if not report_file.exists():
        return {}

    with open(report_file, 'r', encoding='utf-8') as f:
        return json.load(f)


def format_uptime(seconds: float) -> str:
    """格式化运行时间"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def display_dashboard():
    """显示性能仪表板"""
    # 清屏
    print('\033[2J\033[H', end='')

    print_header("🎯 Sniper Trading System - 性能监控仪表板")

    data = load_performance_data()
    if not data:
        print(f"{Colors.YELLOW}⚠️  暂无性能数据{Colors.RESET}")
        return

    # 运行时间
    uptime = format_uptime(data.get('uptime_seconds', 0))
    print_metric("⏱️  运行时间", uptime, "")
    print_metric("📅 更新时间", data.get('timestamp', 'N/A'), "")
    print()

    # 系统资源
    print_header("📊 系统资源")
    system_stats = data.get('system_stats', {})
    print_bar("CPU 使用率", system_stats.get('cpu_avg', 0))
    print_bar("内存使用率", system_stats.get('memory_avg', 0))
    print()

    # 交易统计
    print_header("💹 交易统计")
    print_metric("信号总数", str(data.get('signal_count', 0)), "")
    print_metric("交易次数", str(data.get('trade_count', 0)), "")
    print()

    # 延迟统计
    print_header("⚡ 延迟统计")
    latency_stats = data.get('latency_stats', {})
    for operation, stats in sorted(latency_stats.items()):
        avg = stats.get('avg', 0)
        count = stats.get('count', 0)

        # 选择颜色
        if avg < 100:
            color = Colors.GREEN
        elif avg < 500:
            color = Colors.YELLOW
        else:
            color = Colors.RED

        print_metric(
            f"  {operation}",
            f"{avg:.1f}ms",
            f" ({count} 次)",
            color
        )
    print()

    # 最近指标趋势
    print_header("📈 最近趋势 (最近10次)")
    recent = data.get('recent_metrics', [])[-10:]
    if recent:
        cpu_values = [m['cpu_percent'] for m in recent]
        mem_values = [m['memory_percent'] for m in recent]

        print(f"  CPU:  {min(cpu_values):.1f}% → {max(cpu_values):.1f}%")
        print(f"  内存: {min(mem_values):.1f}% → {max(mem_values):.1f}%")
    print()

    # 性能警告
    alerts = []
    if system_stats.get('cpu_avg', 0) > 80:
        alerts.append("⚠️  CPU 使用率过高")
    if system_stats.get('memory_avg', 0) > 80:
        alerts.append("⚠️  内存使用率过高")

    for operation, stats in latency_stats.items():
        if stats.get('avg', 0) > 1000:
            alerts.append(f"⚠️  {operation} 延迟过高")

    if alerts:
        print_header("⚠️  性能警告")
        for alert in alerts:
            print(f"{Colors.RED}{alert}{Colors.RESET}")
        print()

    print(f"{Colors.CYAN}按 Ctrl+C 退出{Colors.RESET}")


async def monitor_dashboard(interval: int = 5):
    """
    监控仪表板（自动刷新）

    Args:
        interval: 刷新间隔（秒）
    """
    try:
        while True:
            display_dashboard()
            await asyncio.sleep(interval)
    except KeyboardInterrupt:
        print(f"\n{Colors.YELLOW}监控已停止{Colors.RESET}")


if __name__ == '__main__':
    print(f"{Colors.GREEN}启动性能监控仪表板...{Colors.RESET}\n")
    asyncio.run(monitor_dashboard(interval=5))
