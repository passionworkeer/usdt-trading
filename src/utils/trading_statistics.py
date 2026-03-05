"""
交易统计分析模块 (Trading Statistics)

提供交易绩效分析、统计报告功能
"""
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from pathlib import Path
from collections import defaultdict
import statistics

logger = logging.getLogger(__name__)


@dataclass
class TradeRecord:
    """交易记录"""
    symbol: str
    side: str  # LONG / SHORT
    entry_price: float
    exit_price: float
    quantity: float
    entry_time: str
    exit_time: str
    pnl: float  # 盈亏 (USDT)
    pnl_pct: float  # 盈亏比例 (%)
    duration_hours: float  # 持仓时长 (小时)
    close_reason: str  # 平仓原因


@dataclass
class TradingStatistics:
    """交易统计"""
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    win_rate: float = 0.0  # 胜率 (%)
    total_pnl: float = 0.0  # 总盈亏 (USDT)
    avg_win: float = 0.0  # 平均盈利 (USDT)
    avg_loss: float = 0.0  # 平均亏损 (USDT)
    avg_duration_hours: float = 0.0  # 平均持仓时长 (小时)
    largest_win: float = 0.0  # 最大盈利 (USDT)
    largest_loss: float = 0.0  # 最大亏损 (USDT)
    avg_holding_hours: float = 0.0  # 平均持仓时间
    profit_factor: float = 0.0  # 盈利因子
    sharpe_ratio: float = 0.0  # 夏普比率


class TradingStatisticsAnalyzer:
    """
    交易统计分析器

    功能：
    1. 交易记录统计
    2. 绩效指标计算
    3. 趋势分析
    4. 报告生成
    """

    def __init__(self, data_dir: str = "state"):
        """
        初始化统计分析器

        Args:
            data_dir: 数据目录
        """
        self.data_dir = Path(data_dir)
        self.trades: List[TradeRecord] = []
        self.load_trades()

    def load_trades(self):
        """从文件加载交易记录"""
        trades_file = self.data_dir / "trades.json"
        if trades_file.exists():
            try:
                with open(trades_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.trades = [TradeRecord(**t) for t in data]
                logger.info(f"✅ 已加载 {len(self.trades)} 条交易记录")
            except Exception as e:
                logger.warning(f"加载交易记录失败: {e}")
                self.trades = []

    def save_trades(self):
        """保存交易记录"""
        trades_file = self.data_dir / "trades.json"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        try:
            with open(trades_file, 'w', encoding='utf-8') as f:
                json.dump([vars(t) for t in self.trades], f, indent=2, ensure_ascii=False)
            logger.info(f"✅ 已保存 {len(self.trades)} 条交易记录")
        except Exception as e:
            logger.error(f"保存交易记录失败: {e}")

    def add_trade(self, trade: TradeRecord):
        """添加交易记录"""
        self.trades.append(trade)
        self.save_trades()

    def calculate_statistics(self) -> TradingStatistics:
        """
        计算交易统计

        Returns:
            统计结果
        """
        if not self.trades:
            return TradingStatistics()

        winning_trades = [t for t in self.trades if t.pnl > 0]
        losing_trades = [t for t in self.trades if t.pnl <= 0]

        total_wins = sum(t.pnl for t in winning_trades)
        total_losses = abs(sum(t.pnl for t in losing_trades))

        stats = TradingStatistics(
            total_trades=len(self.trades),
            winning_trades=len(winning_trades),
            losing_trades=len(losing_trades),
            win_rate=len(winning_trades) / len(self.trades) * 100 if self.trades else 0,
            total_pnl=sum(t.pnl for t in self.trades),
            avg_win=statistics.mean([t.pnl for t in winning_trades]) if winning_trades else 0,
            avg_loss=statistics.mean([t.pnl for t in losing_trades]) if losing_trades else 0,
            largest_win=max([t.pnl for t in winning_trades]) if winning_trades else 0,
            largest_loss=min([t.pnl for t in losing_trades]) if losing_trades else 0,
            avg_holding_hours=statistics.mean([t.duration_hours for t in self.trades]) if self.trades else 0,
        )

        # 盈利因子
        if total_losses > 0:
            stats.profit_factor = total_wins / total_losses
        else:
            stats.profit_factor = float('inf') if total_wins > 0 else 0

        return stats

    def get_daily_stats(self, days: int = 7) -> Dict[str, Dict]:
        """
        获取每日统计

        Args:
            days: 天数

        Returns:
            每日统计数据
        """
        daily_stats = defaultdict(lambda: {'trades': 0, 'wins': 0, 'pnl': 0})

        cutoff = datetime.now() - timedelta(days=days)

        for trade in self.trades:
            try:
                trade_date = datetime.fromisoformat(trade.exit_time.split('T')[0])
                if trade_date >= cutoff:
                    date_key = trade_date.strftime('%Y-%m-%d')
                    daily_stats[date_key]['trades'] += 1
                    daily_stats[date_key]['pnl'] += trade.pnl
                    if trade.pnl > 0:
                        daily_stats[date_key]['wins'] += 1
            except:
                continue

        return dict(daily_stats)

    def get_symbol_stats(self) -> Dict[str, Dict]:
        """
        获取各交易对统计

        Returns:
            交易对统计数据
        """
        symbol_stats = defaultdict(lambda: {
            'trades': 0, 'wins': 0, 'pnl': 0, 'win_rate': 0
        })

        for trade in self.trades:
            stats = symbol_stats[trade.symbol]
            stats['trades'] += 1
            stats['pnl'] += trade.pnl
            if trade.pnl > 0:
                stats['wins'] += 1

        # 计算胜率
        for symbol, stats in symbol_stats.items():
            if stats['trades'] > 0:
                stats['win_rate'] = stats['wins'] / stats['trades'] * 100

        return dict(symbol_stats)

    def generate_report(self) -> str:
        """
        生成统计报告

        Returns:
            格式化的报告
        """
        stats = self.calculate_statistics()

        report = f"""
{'='*60}
📊 交易统计分析报告
{'='*60}

📅 统计周期: {len(self.trades)} 笔交易

💰 盈亏统计:
- 总盈亏: {stats.total_pnl:+.2f} USDT
- 盈利交易: {stats.winning_trades} 笔
- 亏损交易: {stats.losing_trades} 笔
- 胜率: {stats.win_rate:.1f}%

📈 绩效指标:
- 平均盈利: {stats.avg_win:+.2f} USDT
- 平均亏损: {stats.avg_loss:+.2f} USDT
- 最大盈利: {stats.largest_win:+.2f} USDT
- 最大亏损: {stats.largest_loss:.2f} USDT
- 盈利因子: {stats.profit_factor:.2f}

⏱️ 持仓统计:
- 平均持仓时间: {stats.avg_holding_hours:.1f} 小时
"""

        # 添加每日统计
        daily_stats = self.get_daily_stats(7)
        if daily_stats:
            report += f"""
📆 最近7天:
"""
            for date, data in sorted(daily_stats.items()):
                report += f"  {date}: {data['trades']} 笔, PnL: {data['pnl']:+.2f} USDT\n"

        # 添加交易对统计
        symbol_stats = self.get_symbol_stats()
        if symbol_stats:
            report += f"""
📊 交易对分析:
"""
            for symbol, data in sorted(symbol_stats.items(), key=lambda x: x[1]['pnl'], reverse=True):
                report += f"  {symbol}: {data['trades']} 笔, 胜率: {data['win_rate']:.1f}%, PnL: {data['pnl']:+.2f} USDT\n"

        report += f"{'='*60}\n"
        return report

    def save_report(self, filepath: Optional[Path] = None) -> Path:
        """
        保存报告到文件

        Args:
            filepath: 文件路径

        Returns:
            保存的文件路径
        """
        if filepath is None:
            filepath = Path('logs/trading_statistics.md')

        filepath.parent.mkdir(parents=True, exist_ok=True)

        stats = self.calculate_statistics()
        daily_stats = self.get_daily_stats(30)
        symbol_stats = self.get_symbol_stats()

        report_data = {
            'generated_at': datetime.now().isoformat(),
            'summary': {
                'total_trades': stats.total_trades,
                'winning_trades': stats.winning_trades,
                'losing_trades': stats.losing_trades,
                'win_rate': stats.win_rate,
                'total_pnl': stats.total_pnl,
                'profit_factor': stats.profit_factor,
            },
            'daily_stats': daily_stats,
            'symbol_stats': symbol_stats,
        }

        with open(filepath.with_suffix('.json'), 'w', encoding='utf-8') as f:
            json.dump(report_data, f, indent=2, ensure_ascii=False)

        # 保存 Markdown 报告
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(self.generate_report())

        logger.info(f"✅ 统计报告已保存: {filepath}")
        return filepath


# 全局统计分析器实例
_global_analyzer: Optional[TradingStatisticsAnalyzer] = None


def get_statistics_analyzer() -> TradingStatisticsAnalyzer:
    """获取全局统计分析器"""
    global _global_analyzer
    if _global_analyzer is None:
        _global_analyzer = TradingStatisticsAnalyzer()
    return _global_analyzer
