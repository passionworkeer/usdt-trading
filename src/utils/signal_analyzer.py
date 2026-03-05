"""
信号分析系统 (Signal Analyzer)

记录和分析交易信号质量
"""
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from dataclasses import dataclass, field, asdict
from pathlib import Path
from collections import defaultdict
from enum import Enum

logger = logging.getLogger(__name__)


class SignalSource(Enum):
    """信号来源"""
    MTF_RESONANCE = "mtf_resonance"  # MTF 三重共振
    TECHNICAL = "technical"          # 技术指标
    AI_DECISION = "ai_decision"      # AI 决策
    MANUAL = "manual"                 # 手动


class SignalAction(Enum):
    """信号动作"""
    BUY = "buy"
    SELL = "sell"
    HOLD = "hold"
    CLOSE = "close"


class SignalQuality(Enum):
    """信号质量"""
    EXCELLENT = "excellent"  # 优秀
    GOOD = "good"            # 良好
    FAIR = "fair"           # 一般
    POOR = "poor"           # 较差


@dataclass
class SignalRecord:
    """信号记录"""
    timestamp: str
    symbol: str
    source: str
    action: str
    price: float
    confidence: float  # 置信度 0-100
    reasons: List[str] = field(default_factory=list)
    indicators: Dict = field(default_factory=dict)
    # 执行结果（后续填充）
    executed: bool = False
    executed_price: Optional[float] = None
    pnl: Optional[float] = None
    pnl_pct: Optional[float] = None
    close_timestamp: Optional[str] = None
    close_reason: Optional[str] = None
    holding_hours: Optional[float] = None


class SignalAnalyzer:
    """
    信号分析器

    功能：
    1. 记录交易信号
    2. 分析信号质量
    3. 统计信号胜率
    4. 优化信号参数
    """

    def __init__(self, data_dir: str = "state"):
        """
        初始化信号分析器

        Args:
            data_dir: 数据目录
        """
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.signals_file = self.data_dir / "signal_history.json"
        self.signals: List[SignalRecord] = []
        self.load_signals()

    def load_signals(self):
        """从文件加载信号记录"""
        if self.signals_file.exists():
            try:
                with open(self.signals_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.signals = [SignalRecord(**s) for s in data]
                logger.info(f"✅ 已加载 {len(self.signals)} 条信号记录")
            except Exception as e:
                logger.warning(f"加载信号记录失败: {e}")
                self.signals = []

    def save_signals(self):
        """保存信号记录"""
        try:
            with open(self.signals_file, 'w', encoding='utf-8') as f:
                json.dump([asdict(s) for s in self.signals], f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"保存信号记录失败: {e}")

    def record_signal(
        self,
        symbol: str,
        source: SignalSource,
        action: SignalAction,
        price: float,
        confidence: float,
        reasons: List[str],
        indicators: Optional[Dict] = None
    ) -> SignalRecord:
        """
        记录信号

        Args:
            symbol: 交易对
            source: 信号来源
            action: 信号动作
            price: 价格
            confidence: 置信度
            reasons: 原因
            indicators: 技术指标

        Returns:
            信号记录
        """
        signal = SignalRecord(
            timestamp=datetime.now().isoformat(),
            symbol=symbol,
            source=source.value,
            action=action.value,
            price=price,
            confidence=confidence,
            reasons=reasons,
            indicators=indicators or {}
        )

        self.signals.append(signal)
        self.save_signals()

        logger.info(f"📝 记录信号: {symbol} {action.value} @ ${price:.2f} (置信度: {confidence:.0f}%)")
        return signal

    def update_execution(
        self,
        signal: SignalRecord,
        executed: bool,
        executed_price: Optional[float] = None
    ):
        """更新信号执行结果"""
        signal.executed = executed
        signal.executed_price = executed_price
        self.save_signals()

    def update_close(
        self,
        signal: SignalRecord,
        pnl: float,
        pnl_pct: float,
        close_reason: str
    ):
        """更新平仓结果"""
        signal.pnl = pnl
        signal.pnl_pct = pnl_pct
        signal.close_reason = close_reason
        signal.close_timestamp = datetime.now().isoformat()

        # 计算持仓时间
        try:
            entry_time = datetime.fromisoformat(signal.timestamp)
            close_time = datetime.fromisoformat(signal.close_timestamp)
            signal.holding_hours = (close_time - entry_time).total_seconds() / 3600
        except:
            pass

        self.save_signals()

    def get_signal_stats(self, days: int = 30) -> Dict:
        """
        获取信号统计

        Args:
            days: 统计天数

        Returns:
            统计结果
        """
        cutoff = datetime.now() - timedelta(days=days)
        recent_signals = [
            s for s in self.signals
            if datetime.fromisoformat(s.timestamp) >= cutoff
        ]

        if not recent_signals:
            return {
                'total_signals': 0,
                'executed_signals': 0,
                'execution_rate': 0,
                'win_rate': 0,
                'avg_pnl': 0,
                'best_signal': None,
                'worst_signal': None
            }

        executed = [s for s in recent_signals if s.executed]
        closed = [s for s in executed if s.pnl is not None]
        wins = [s for s in closed if s.pnl > 0]

        stats = {
            'total_signals': len(recent_signals),
            'executed_signals': len(executed),
            'execution_rate': len(executed) / len(recent_signals) * 100 if recent_signals else 0,
            'closed_signals': len(closed),
            'winning_signals': len(wins),
            'win_rate': len(wins) / len(closed) * 100 if closed else 0,
            'avg_pnl': sum(s.pnl for s in closed) / len(closed) if closed else 0,
            'total_pnl': sum(s.pnl for s in closed),
        }

        # 最佳/最差信号
        if closed:
            best = max(closed, key=lambda s: s.pnl)
            worst = min(closed, key=lambda s: s.pnl)
            stats['best_signal'] = {
                'symbol': best.symbol,
                'action': best.action,
                'pnl': best.pnl,
                'pnl_pct': best.pnl_pct
            }
            stats['worst_signal'] = {
                'symbol': worst.symbol,
                'action': worst.action,
                'pnl': worst.pnl,
                'pnl_pct': worst.pnl_pct
            }

        return stats

    def get_source_stats(self) -> Dict:
        """获取各来源信号统计"""
        source_stats = defaultdict(lambda: {
            'total': 0, 'executed': 0, 'wins': 0, 'total_pnl': 0
        })

        for signal in self.signals:
            stats = source_stats[signal.source]
            stats['total'] += 1
            if signal.executed:
                stats['executed'] += 1
                if signal.pnl and signal.pnl > 0:
                    stats['wins'] += 1
                if signal.pnl:
                    stats['total_pnl'] += signal.pnl

        return dict(source_stats)

    def get_symbol_stats(self) -> Dict:
        """获取各交易对信号统计"""
        symbol_stats = defaultdict(lambda: {
            'total': 0, 'executed': 0, 'wins': 0, 'total_pnl': 0
        })

        for signal in self.signals:
            stats = symbol_stats[signal.symbol]
            stats['total'] += 1
            if signal.executed:
                stats['executed'] += 1
                if signal.pnl and signal.pnl > 0:
                    stats['wins'] += 1
                if signal.pnl:
                    stats['total_pnl'] += signal.pnl

        return dict(symbol_stats)

    def get_confidence_analysis(self) -> Dict:
        """置信度分析"""
        if not self.signals:
            return {}

        executed = [s for s in self.signals if s.executed and s.pnl is not None]
        if not executed:
            return {}

        # 按置信度分组
        confidence_ranges = {
            'high_80_100': [],
            'medium_60_80': [],
            'low_0_60': []
        }

        for s in executed:
            if s.confidence >= 80:
                confidence_ranges['high_80_100'].append(s)
            elif s.confidence >= 60:
                confidence_ranges['medium_60_80'].append(s)
            else:
                confidence_ranges['low_0_60'].append(s)

        analysis = {}
        for range_name, signals in confidence_ranges.items():
            if signals:
                wins = sum(1 for s in signals if s.pnl > 0)
                analysis[range_name] = {
                    'count': len(signals),
                    'win_rate': wins / len(signals) * 100,
                    'avg_pnl': sum(s.pnl for s in signals) / len(signals)
                }

        return analysis

    def generate_report(self, days: int = 30) -> str:
        """生成分析报告"""
        stats = self.get_signal_stats(days)
        source_stats = self.get_source_stats()
        symbol_stats = self.get_symbol_stats()
        confidence_analysis = self.get_confidence_analysis()

        report = f"""
{'='*60}
📊 信号分析报告 (最近 {days} 天)
{'='*60}

📈 总体统计:
- 总信号数: {stats.get('total_signals', 0)}
- 执行信号数: {stats.get('executed_signals', 0)}
- 执行率: {stats.get('execution_rate', 0):.1f}%
- 胜率: {stats.get('win_rate', 0):.1f}%
- 平均盈亏: ${stats.get('avg_pnl', 0):+.2f}
- 总盈亏: ${stats.get('total_pnl', 0):+.2f}
"""

        # 最佳/最差信号
        if stats.get('best_signal'):
            best = stats['best_signal']
            report += f"""
🏆 最佳信号:
- {best['symbol']} {best['action']} PnL: ${best['pnl']:+.2f} ({best['pnl_pct']:+.2f}%)
"""
        if stats.get('worst_signal'):
            worst = stats['worst_signal']
            report += f"""
📉 最差信号:
- {worst['symbol']} {worst['action']} PnL: ${worst['pnl']:+.2f} ({worst['pnl_pct']:+.2f}%)
"""

        # 交易对分析
        if symbol_stats:
            report += f"""
📊 交易对分析:
"""
            for symbol, data in sorted(symbol_stats.items(), key=lambda x: x[1]['total_pnl'], reverse=True):
                win_rate = data['wins'] / data['executed'] * 100 if data['executed'] else 0
                report += f"  {symbol}: {data['total']} 信号, 胜率: {win_rate:.1f}%, PnL: ${data['total_pnl']:+.2f}\n"

        # 置信度分析
        if confidence_analysis:
            report += f"""
🎯 置信度分析:
"""
            for range_name, data in confidence_analysis.items():
                report += f"  {range_name}: {data['count']} 信号, 胜率: {data['win_rate']:.1f}%, 平均: ${data['avg_pnl']:+.2f}\n"

        report += f"{'='*60}\n"
        return report


# 全局信号分析器实例
_global_analyzer: Optional[SignalAnalyzer] = None


def get_signal_analyzer() -> SignalAnalyzer:
    """获取全局信号分析器"""
    global _global_analyzer
    if _global_analyzer is None:
        _global_analyzer = SignalAnalyzer()
    return _global_analyzer
