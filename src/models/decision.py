"""
统一的数据模型定义

此模块包含项目中所有核心数据模型的统一定义。
所有类都是不可变的数据类，以确保数据一致性和线程安全。

主要模型:
    - EvidenceBasedDecision: 基于证据的交易决策
    - ActionType: 交易动作类型
    - MarketContext: 市场上下文
    - TradeResult: 交易结果
    - 等等
"""
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional


class ActionType(Enum):
    """交易动作类型"""
    BUY = "buy"
    SELL = "sell"
    HOLD = "hold"


class RiskLevel(Enum):
    """风险等级"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ConfidenceLevel(Enum):
    """置信度等级"""
    VERY_LOW = (0.0, 0.3)
    LOW = (0.3, 0.5)
    MEDIUM = (0.5, 0.7)
    HIGH = (0.7, 0.85)
    VERY_HIGH = (0.85, 1.0)

    def __init__(self, min_val: float, max_val: float):
        self.min_val = min_val
        self.max_val = max_val

    @classmethod
    def from_score(cls, score: float) -> "ConfidenceLevel":
        """从分数获取置信度等级"""
        for level in cls:
            if level.min_val <= score < level.max_val:
                return level
        return cls.VERY_HIGH


class SignalStrength(str, Enum):
    """信号强度等级"""
    STRONG = "STRONG"
    MODERATE = "MODERATE"
    WEAK = "WEAK"


class MarketRegime(str, Enum):
    """市场状态分类"""
    TRENDING_UP = "TRENDING_UP"
    TRENDING_DOWN = "TRENDING_DOWN"
    RANGING = "RANGING"
    VOLATILE = "VOLATILE"
    UNKNOWN = "UNKNOWN"


class TradeOutcome(str, Enum):
    """交易结果分类"""
    WIN = "WIN"
    LOSS = "LOSS"
    BREAKEVEN = "BREAKEVEN"
    OPEN = "OPEN"
    CANCELLED = "CANCELLED"


@dataclass(frozen=True)
class MarketContext:
    """
    市场上下文数据

    Attributes:
        symbol: 交易对符号
        current_price: 当前价格
        price_history: 价格历史
        volume_24h: 24小时成交量
        market_cap: 市值
        indicators: 技术指标字典
        news_sentiment: 新闻情绪
        timestamp: 时间戳
    """
    symbol: str
    current_price: float
    price_history: List[float] = field(default_factory=list)
    volume_24h: Optional[float] = None
    market_cap: Optional[float] = None
    indicators: Dict[str, Any] = field(default_factory=dict)
    news_sentiment: Optional[float] = None
    timestamp: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'symbol': self.symbol,
            'current_price': self.current_price,
            'price_history': self.price_history,
            'volume_24h': self.volume_24h,
            'market_cap': self.market_cap,
            'indicators': self.indicators,
            'news_sentiment': self.news_sentiment,
            'timestamp': self.timestamp.isoformat() if isinstance(self.timestamp, datetime) else self.timestamp,
        }


@dataclass(frozen=True)
class Evidence:
    """
    证据项

    Attributes:
        source: 证据来源（如 technical, fundamental, sentiment）
        metric: 指标名称
        value: 指标值
        weight: 权重
        confidence: 对此证据的置信度
        description: 描述
    """
    source: str
    metric: str
    value: Any
    weight: float = 1.0
    confidence: float = 1.0
    description: str = ""


@dataclass
class EvidenceChain:
    """
    证据链

    Attributes:
        evidences: 证据列表
        timestamp: 时间戳
    """
    evidences: List[Evidence] = field(default_factory=list)
    timestamp: datetime = field(default_factory=datetime.now)

    def add_evidence(self, evidence: Evidence) -> "EvidenceChain":
        """
        添加证据

        为了向后兼容，此方法直接修改对象并返回 self。

        Args:
            evidence: 要添加的证据

        Returns:
            self
        """
        self.evidences.append(evidence)
        return self

    def get_total_weight(self) -> float:
        """获取总权重"""
        return sum(e.weight * e.confidence for e in self.evidences)

    def get_by_source(self, source: str) -> List[Evidence]:
        """按来源获取证据"""
        return [e for e in self.evidences if e.source == source]


@dataclass(frozen=True)
class EvidenceBasedDecision:
    """
    基于证据的决策 - 符合证据链风控要求

    废除 confidence 浮点数，改用结构化证据链。
    所有字段必须明确，不允许模糊的置信度。

    Attributes:
        action: 交易动作 (buy/sell/hold)
        evidence_count: 证据数量（必须与 evidence_chain 长度一致）
        evidence_chain: 证据链列表，每项是一个具体的可验证证据
        veto_flag: 否决标记，True 表示存在危险信号，阻止交易
        entry_price: 入场价格
        stop_loss: 止损价格
        take_profit: 止盈价格
        position_size: 仓位大小 (USDT)
        symbol: 交易对 (可选)
        reasoning: 分析理由（可选）
        metadata: 额外元数据
        timestamp: 决策时间
    """
    action: ActionType
    evidence_count: int
    evidence_chain: List[str]
    veto_flag: bool
    entry_price: float
    stop_loss: float
    take_profit: float
    position_size: float
    symbol: Optional[str] = None
    reasoning: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)

    def __post_init__(self):
        """验证数据并自动修正"""
        # Convert action string to ActionType enum if needed
        if isinstance(self.action, str):
            action_map = {
                "buy": ActionType.BUY,
                "long": ActionType.BUY,
                "sell": ActionType.SELL,
                "short": ActionType.SELL,
                "hold": ActionType.HOLD,
                "pass": ActionType.HOLD,
                "close": ActionType.HOLD,
            }
            # Use object.__setattr__ because dataclass is frozen
            object.__setattr__(self, 'action', action_map.get(self.action.lower(), ActionType.HOLD))

        # Auto-fix evidence_count to match evidence_chain length
        if self.evidence_count != len(self.evidence_chain):
            object.__setattr__(self, 'evidence_count', len(self.evidence_chain))

        # Validate other fields
        if self.evidence_count < 0:
            raise ValueError(f"evidence_count must be non-negative, got {self.evidence_count}")
        if self.position_size < 0:
            raise ValueError(f"position_size must be non-negative, got {self.position_size}")

    @property
    def is_valid(self) -> bool:
        """检查决策是否有效（未被否决且有证据）"""
        return not self.veto_flag and self.evidence_count > 0

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'action': self.action.value,
            'evidence_count': self.evidence_count,
            'evidence_chain': self.evidence_chain,
            'veto_flag': self.veto_flag,
            'entry_price': self.entry_price,
            'stop_loss': self.stop_loss,
            'take_profit': self.take_profit,
            'position_size': self.position_size,
            'symbol': self.symbol,
            'reasoning': self.reasoning,
            'metadata': self.metadata,
            'timestamp': self.timestamp.isoformat() if isinstance(self.timestamp, datetime) else self.timestamp,
        }


@dataclass
class TradeResult:
    """
    交易结果

    Attributes:
        symbol: 交易对
        action: 交易动作
        entry_price: 入场价格
        exit_price: 出场价格
        quantity: 数量
        pnl: 盈亏金额
        pnl_pct: 盈亏百分比
        entry_time: 入场时间
        exit_time: 出场时间
        status: 状态 (open, closed, cancelled)
        metadata: 额外数据
    """
    symbol: str
    action: ActionType
    entry_price: float
    exit_price: Optional[float] = None
    quantity: float = 0.0
    pnl: Optional[float] = None
    pnl_pct: Optional[float] = None
    entry_time: datetime = field(default_factory=datetime.now)
    exit_time: Optional[datetime] = None
    status: str = "open"
    metadata: Dict[str, Any] = field(default_factory=dict)

    def close(self, exit_price: float, exit_time: Optional[datetime] = None) -> None:
        """
        关闭交易（向后兼容的变异模式）

        Args:
            exit_price: 出场价格
            exit_time: 出场时间
        """
        self.exit_price = exit_price
        self.exit_time = exit_time or datetime.now()
        self.status = "closed"

        # 计算盈亏
        if self.action == ActionType.BUY:
            self.pnl = (exit_price - self.entry_price) * self.quantity
            self.pnl_pct = (exit_price - self.entry_price) / self.entry_price * 100
        else:  # SELL
            self.pnl = (self.entry_price - exit_price) * self.quantity
            self.pnl_pct = (self.entry_price - exit_price) / self.entry_price * 100

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'symbol': self.symbol,
            'action': self.action.value,
            'entry_price': self.entry_price,
            'exit_price': self.exit_price,
            'quantity': self.quantity,
            'pnl': self.pnl,
            'pnl_pct': self.pnl_pct,
            'entry_time': self.entry_time.isoformat() if isinstance(self.entry_time, datetime) else self.entry_time,
            'exit_time': self.exit_time.isoformat() if isinstance(self.exit_time, datetime) else self.exit_time,
            'status': self.status,
            'metadata': self.metadata,
        }


@dataclass(frozen=True)
class ReviewFinding:
    """
    复盘发现

    Attributes:
        category: 类别 (decision_quality, timing, risk_management, execution)
        severity: 严重程度 (info, warning, error, critical)
        description: 描述
        recommendation: 建议
        evidence: 证据
    """
    category: str
    severity: str
    description: str
    recommendation: str
    evidence: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ReviewReport:
    """
    复盘报告

    Attributes:
        trade_id: 交易ID
        overall_assessment: 总体评估
        findings: 发现列表
        lessons_learned: 经验教训
        improvements: 改进建议
        score: 评分 (0-100)
        timestamp: 时间戳
        metadata: 额外数据
    """
    trade_id: str
    overall_assessment: str
    findings: List[ReviewFinding] = field(default_factory=list)
    lessons_learned: List[str] = field(default_factory=list)
    improvements: List[str] = field(default_factory=list)
    score: float = 0.0
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def add_finding(self, finding: ReviewFinding) -> None:
        """添加发现（向后兼容的变异模式）"""
        self.findings.append(finding)

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'trade_id': self.trade_id,
            'overall_assessment': self.overall_assessment,
            'findings': [
                {
                    'category': f.category,
                    'severity': f.severity,
                    'description': f.description,
                    'recommendation': f.recommendation,
                    'evidence': f.evidence,
                }
                for f in self.findings
            ],
            'lessons_learned': self.lessons_learned,
            'improvements': self.improvements,
            'score': self.score,
            'timestamp': self.timestamp.isoformat() if isinstance(self.timestamp, datetime) else self.timestamp,
            'metadata': self.metadata,
        }


# 导出所有类和枚举
__all__ = [
    # Enums
    "ActionType",
    "RiskLevel",
    "ConfidenceLevel",
    "SignalStrength",
    "MarketRegime",
    "TradeOutcome",
    # Data Classes
    "MarketContext",
    "Evidence",
    "EvidenceChain",
    "EvidenceBasedDecision",
    "TradeResult",
    "ReviewFinding",
    "ReviewReport",
    "TradingSignal",
    "LearningReport",
]


@dataclass(frozen=True)
class TradingSignal:
    """
    交易信号

    Attributes:
        symbol: 交易对符号 (如 "BTC/USDT")
        timestamp: 信号生成时间
        signal_type: 信号类型 (BUY, SELL, HOLD)
        strength: 信号强度 (STRONG, MODERATE, WEAK)
        evidence_count: 支持此信号的证据数量
        evidence_chain: 证据描述列表
        source: 生成信号的组件
        metadata: 额外信号数据
    """
    symbol: str
    timestamp: datetime
    signal_type: ActionType
    strength: SignalStrength
    evidence_count: int
    evidence_chain: List[str]
    source: str
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        """验证信号数据"""
        if self.evidence_count < 0:
            raise ValueError("evidence_count must be non-negative")
        if self.evidence_count != len(self.evidence_chain):
            raise ValueError("evidence_count must match length of evidence_chain")

    def is_actionable(self) -> bool:
        """检查信号是否足够强以采取行动"""
        return (
            self.signal_type != ActionType.HOLD
            and self.strength in (SignalStrength.STRONG, SignalStrength.MODERATE)
            and self.evidence_count >= 2
        )


@dataclass(frozen=True)
class LearningReport:
    """
    学习和改进报告

    Attributes:
        report_id: 报告唯一标识符
        generated_at: 报告生成时间
        period_start: 学习周期开始时间
        period_end: 学习周期结束时间
        model_performance: 模型准确率指标
        feature_importance: 特征重要性排序
        learned_patterns: 识别的显著模式
        strategy_adjustments: 建议的策略修改
        risk_parameter_updates: 建议的风险参数更新
        failure_analysis: 失败交易分析
        success_analysis: 成功交易分析
        recommendations: 可操作的建议
        confidence_scores: 每项建议的置信度
    """
    report_id: str
    generated_at: datetime
    period_start: datetime
    period_end: datetime
    model_performance: Dict[str, float] = field(default_factory=dict)
    feature_importance: Dict[str, float] = field(default_factory=dict)
    learned_patterns: List[str] = field(default_factory=list)
    strategy_adjustments: List[str] = field(default_factory=list)
    risk_parameter_updates: Dict[str, Any] = field(default_factory=dict)
    failure_analysis: Dict[str, Any] = field(default_factory=dict)
    success_analysis: Dict[str, Any] = field(default_factory=dict)
    recommendations: List[str] = field(default_factory=list)
    confidence_scores: Dict[str, float] = field(default_factory=dict)

    def __post_init__(self):
        """验证学习报告数据"""
        for key, score in self.confidence_scores.items():
            if not 0 <= score <= 1:
                raise ValueError(f"confidence score for {key} must be between 0 and 1")

    def get_top_recommendations(self, n: int = 5) -> List[str]:
        """获取按置信度排序的前 N 条建议"""
        scored_recs = [
            (rec, self.confidence_scores.get(rec, 0.0))
            for rec in self.recommendations
        ]
        scored_recs.sort(key=lambda x: x[1], reverse=True)
        return [rec for rec, _ in scored_recs[:n]]

    def improvement_rate(self) -> float:
        """计算模型性能改进率"""
        if not self.model_performance:
            return 0.0

        accuracies = list(self.model_performance.values())
        if len(accuracies) < 2:
            return 0.0

        return (accuracies[-1] - accuracies[0]) / len(accuracies)
