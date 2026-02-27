"""
复盘系统 - ReviewSystem

提供交易复盘、学习报告生成和交易记录管理功能。
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from src.storage.database import TradingDatabase, Trade, Review
from src.ai.provider.base import TradeResult, ReviewReport, ReviewFinding
from src.ai.provider.manager import AIProviderManager

logger = logging.getLogger(__name__)


@dataclass
class LearningReport:
    """学习报告数据类"""
    total_trades: int = 0
    win_rate: float = 0.0
    avg_pnl: float = 0.0
    by_strategy: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    recommendations: List[str] = field(default_factory=list)
    generated_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'total_trades': self.total_trades,
            'win_rate': self.win_rate,
            'avg_pnl': self.avg_pnl,
            'by_strategy': self.by_strategy,
            'recommendations': self.recommendations,
            'generated_at': self.generated_at.isoformat() if isinstance(self.generated_at, datetime) else self.generated_at,
        }


class ReviewSystem:
    """
    复盘系统

    功能：
    - 记录交易到数据库
    - 生成单笔交易的复盘报告
    - 生成学习报告（基于 SQL 聚合统计）
    """

    def __init__(self, database: TradingDatabase, provider_manager: AIProviderManager):
        """
        初始化复盘系统

        Args:
            database: 交易数据库实例
            provider_manager: AI Provider 管理器
        """
        self.database = database
        self.provider_manager = provider_manager
        self._initialized = False

    async def initialize(self) -> None:
        """初始化复盘系统"""
        if self._initialized:
            return

        await self.database.initialize()
        self._initialized = True
        logger.info("ReviewSystem initialized")

    async def record_trade(self, trade: TradeResult) -> int:
        """
        记录交易到数据库

        Args:
            trade: 交易结果对象

        Returns:
            保存的交易记录 ID
        """
        await self.initialize()

        # 将 TradeResult 转换为 Trade 数据类
        trade_record = Trade(
            symbol=trade.symbol,
            side=trade.action.value.upper(),
            quantity=trade.quantity,
            price=trade.entry_price,
            pnl=trade.pnl or 0.0,
            fee=0.0,  # 可以从 metadata 中提取
            strategy=trade.metadata.get('strategy', ''),
            signal_strength=trade.metadata.get('signal_strength', 0.0),
            execution_time_ms=0,
            metadata=trade.metadata
        )

        trade_id = await self.database.save_trade(trade_record)
        logger.info(f"Trade recorded: {trade.symbol} (ID: {trade_id})")
        return trade_id

    async def generate_review(self, order_id: str) -> ReviewReport:
        """
        生成单笔交易的复盘报告

        Args:
            order_id: 交易订单 ID (作为字符串传入，内部转换为 int)

        Returns:
            复盘报告对象
        """
        await self.initialize()

        # 获取交易数据
        trade_id = int(order_id)
        trade = await self.database.get_trade(trade_id)

        if trade is None:
            raise ValueError(f"Trade not found: {order_id}")

        # 将 Trade 转换为 TradeResult 用于 AI review
        trade_result = self._trade_to_trade_result(trade)

        # 调用 AI 生成复盘
        provider = self.provider_manager.get_active()
        report = await provider.review(trade_result)

        # 确保报告的 trade_id 与请求的 order_id 一致
        report.trade_id = order_id

        # 保存复盘报告到数据库
        review_record = Review(
            trade_id=trade_id,
            review_type='trade',
            summary=report.overall_assessment,
            strengths='; '.join(report.lessons_learned),
            weaknesses='; '.join([f.description for f in report.findings if f.severity in ('error', 'critical')]),
            improvements='; '.join(report.improvements),
            market_conditions=trade.metadata.get('market_conditions', ''),
            emotion_analysis='',
            metadata={
                'score': report.score,
                'findings_count': len(report.findings),
                'order_id': order_id
            }
        )
        await self.database.save_review(review_record)

        logger.info(f"Review generated for trade {order_id} (score: {report.score})")
        return report

    async def generate_learning_report(self, days: int = 30) -> LearningReport:
        """
        生成学习报告 - 使用 SQL 聚合在数据库层完成
        绝不用 Python 循环算！

        Args:
            days: 统计天数

        Returns:
            学习报告对象
        """
        await self.initialize()

        # 使用 SQL 聚合获取统计数据
        stats = await self.database.get_statistics(days)

        # 获取按策略的统计（使用 SQL 分别查询）
        by_strategy = await self._get_strategy_statistics(days)

        # 生成建议
        recommendations = self._generate_recommendations(stats, by_strategy)

        return LearningReport(
            total_trades=stats.total_trades,
            win_rate=stats.win_rate,
            avg_pnl=stats.avg_pnl,
            by_strategy=by_strategy,
            recommendations=recommendations
        )

    async def _get_strategy_statistics(self, days: int) -> Dict[str, Dict[str, Any]]:
        """
        获取各策略的统计数据
        使用 SQL 聚合，不在 Python 中循环
        """
        # 查询所有不同的策略
        strategies = await self._get_unique_strategies(days)

        # 并行获取各策略的统计
        by_strategy = {}
        for strategy in strategies:
            stats = await self.database.get_statistics(days, strategy=strategy)
            by_strategy[strategy] = {
                'total_trades': stats.total_trades,
                'win_rate': stats.win_rate,
                'avg_pnl': stats.avg_pnl,
                'total_pnl': stats.total_pnl,
                'profit_factor': stats.profit_factor,
            }

        return by_strategy

    async def _get_unique_strategies(self, days: int) -> List[str]:
        """获取指定天数内的所有唯一策略名称"""
        import aiosqlite

        async with aiosqlite.connect(self.database.db_path) as db:
            cursor = await db.execute(
                f"""
                SELECT DISTINCT strategy FROM trades
                WHERE created_at >= datetime('now', '-{days} days')
                AND strategy IS NOT NULL AND strategy != ''
                """
            )
            rows = await cursor.fetchall()
            return [row[0] for row in rows if row[0]]

    def _generate_recommendations(
        self,
        stats,
        by_strategy: Dict[str, Dict[str, Any]]
    ) -> List[str]:
        """
        基于统计数据生成建议
        """
        recommendations = []

        # 基于胜率的建议
        if stats.win_rate < 0.4:
            recommendations.append("胜率较低，建议审视入场信号质量，减少交易频率")
        elif stats.win_rate > 0.6:
            recommendations.append("胜率表现良好，可以尝试适当增加仓位")

        # 基于盈亏比的建议
        if stats.profit_factor < 1.0:
            recommendations.append("盈亏比小于1，建议严格止损，让利润奔跑")
        elif stats.profit_factor > 2.0:
            recommendations.append("盈亏比优秀，保持当前的止盈止损策略")

        # 基于平均盈亏的建议
        if stats.avg_pnl < 0:
            recommendations.append("平均交易亏损，建议暂停交易，复盘策略")

        # 基于策略对比的建议
        if by_strategy:
            best_strategy = max(by_strategy.items(), key=lambda x: x[1]['win_rate'])
            worst_strategy = min(by_strategy.items(), key=lambda x: x[1]['win_rate'])

            if best_strategy[1]['win_rate'] - worst_strategy[1]['win_rate'] > 0.2:
                recommendations.append(
                    f"策略表现差异较大，{best_strategy[0]}胜率{best_strategy[1]['win_rate']:.1%}，"
                    f"建议增加{best_strategy[0]}的权重"
                )

        # 基于交易量的建议
        if stats.total_trades < 10:
            recommendations.append("样本数量较少，统计结果可能不够稳定")

        return recommendations

    def _trade_to_trade_result(self, trade: Trade) -> TradeResult:
        """
        将数据库 Trade 对象转换为 TradeResult
        """
        from src.ai.provider.base import ActionType

        # 解析 action
        action = ActionType.BUY if trade.side == "BUY" else ActionType.SELL

        # 确定是否是已平仓交易
        status = "closed" if trade.pnl != 0 else "open"

        return TradeResult(
            symbol=trade.symbol,
            action=action,
            entry_price=trade.price,
            exit_price=None,  # 可以从 metadata 提取
            quantity=trade.quantity,
            pnl=trade.pnl,
            pnl_pct=None,  # 可以计算
            entry_time=datetime.fromisoformat(trade.created_at) if trade.created_at else datetime.now(),
            exit_time=None,
            status=status,
            metadata={
                **trade.metadata,
                'trade_id': trade.id,
                'strategy': trade.strategy,
                'signal_strength': trade.signal_strength,
            }
        )

    async def __aenter__(self):
        """异步上下文管理器入口"""
        await self.initialize()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """异步上下文管理器出口"""
        pass  # 数据库连接由 TradingDatabase 管理
