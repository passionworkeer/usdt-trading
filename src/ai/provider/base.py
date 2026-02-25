"""
AI Provider 抽象基类和数据模型

定义可插拔 AI Provider 接口层，支持多模型切换和统一管理。
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable


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


@dataclass
class MarketContext:
    """市场上下文数据"""
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


@dataclass
class Evidence:
    """证据项"""
    source: str  # 证据来源（如 technical, fundamental, sentiment）
    metric: str  # 指标名称
    value: Any   # 指标值
    weight: float = 1.0  # 权重
    confidence: float = 1.0  # 对此证据的置信度
    description: str = ""  # 描述


@dataclass
class EvidenceChain:
    """证据链"""
    evidences: List[Evidence] = field(default_factory=list)
    timestamp: datetime = field(default_factory=datetime.now)

    def add_evidence(self, evidence: Evidence) -> None:
        """添加证据"""
        self.evidences.append(evidence)

    def get_total_weight(self) -> float:
        """获取总权重"""
        return sum(e.weight * e.confidence for e in self.evidences)

    def get_by_source(self, source: str) -> List[Evidence]:
        """按来源获取证据"""
        return [e for e in self.evidences if e.source == source]


@dataclass
class EvidenceBasedDecision:
    """基于证据的决策"""
    action: ActionType
    confidence: float  # 0.0 - 1.0
    reasoning: str
    evidence_chain: EvidenceChain = field(default_factory=EvidenceChain)
    suggested_amount: Optional[float] = None
    stop_loss_pct: Optional[float] = None
    take_profit_pct: Optional[float] = None
    risk_level: RiskLevel = RiskLevel.MEDIUM
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)

    def __post_init__(self):
        """验证数据"""
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(f"Confidence must be between 0.0 and 1.0, got {self.confidence}")

    @property
    def confidence_level(self) -> ConfidenceLevel:
        """获取置信度等级"""
        return ConfidenceLevel.from_score(self.confidence)

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'action': self.action.value,
            'confidence': self.confidence,
            'reasoning': self.reasoning,
            'suggested_amount': self.suggested_amount,
            'stop_loss_pct': self.stop_loss_pct,
            'take_profit_pct': self.take_profit_pct,
            'risk_level': self.risk_level.value,
            'metadata': self.metadata,
            'timestamp': self.timestamp.isoformat() if isinstance(self.timestamp, datetime) else self.timestamp,
        }


@dataclass
class TradeResult:
    """交易结果"""
    symbol: str
    action: ActionType
    entry_price: float
    exit_price: Optional[float] = None
    quantity: float = 0.0
    pnl: Optional[float] = None  # 盈亏金额
    pnl_pct: Optional[float] = None  # 盈亏百分比
    entry_time: datetime = field(default_factory=datetime.now)
    exit_time: Optional[datetime] = None
    status: str = "open"  # open, closed, cancelled
    metadata: Dict[str, Any] = field(default_factory=dict)

    def close(self, exit_price: float, exit_time: Optional[datetime] = None) -> None:
        """关闭交易"""
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


@dataclass
class ReviewFinding:
    """复盘发现"""
    category: str  # decision_quality, timing, risk_management, execution
    severity: str  # info, warning, error, critical
    description: str
    recommendation: str
    evidence: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ReviewReport:
    """复盘报告"""
    trade_id: str
    overall_assessment: str
    findings: List[ReviewFinding] = field(default_factory=list)
    lessons_learned: List[str] = field(default_factory=list)
    improvements: List[str] = field(default_factory=list)
    score: float = 0.0  # 0-100
    timestamp: datetime = field(default_factory=datetime.now)

    def add_finding(self, finding: ReviewFinding) -> None:
        """添加发现"""
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
        }


@runtime_checkable
class AIProvider(Protocol):
    """AI Provider 协议（用于类型检查）"""

    @property
    def name(self) -> str:
        """Provider 名称"""
        ...

    @property
    def version(self) -> str:
        """Provider 版本"""
        ...

    async def analyze(self, context: MarketContext) -> EvidenceBasedDecision:
        """分析市场并返回决策"""
        ...

    async def review(self, trade: TradeResult) -> ReviewReport:
        """复盘交易"""
        ...

    async def health_check(self) -> bool:
        """健康检查"""
        ...


class AIBaseProvider(ABC):
    """AI Provider 抽象基类"""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        初始化 Provider

        Args:
            config: Provider 配置
        """
        self._config = config or {}
        self._initialized = False
        self._last_error: Optional[str] = None

    @property
    @abstractmethod
    def name(self) -> str:
        """Provider 名称"""
        pass

    @property
    @abstractmethod
    def version(self) -> str:
        """Provider 版本"""
        pass

    @property
    def config(self) -> Dict[str, Any]:
        """获取配置"""
        return self._config.copy()

    @property
    def is_initialized(self) -> bool:
        """是否已初始化"""
        return self._initialized

    @property
    def last_error(self) -> Optional[str]:
        """获取最后错误"""
        return self._last_error

    def initialize(self) -> bool:
        """
        初始化 Provider

        Returns:
            是否成功
        """
        try:
            self._initialized = self._do_initialize()
            return self._initialized
        except Exception as e:
            self._last_error = f"初始化失败: {str(e)}"
            self._initialized = False
            return False

    @abstractmethod
    def _do_initialize(self) -> bool:
        """
        实际初始化逻辑（子类实现）

        Returns:
            是否成功
        """
        pass

    @abstractmethod
    async def analyze(self, context: MarketContext) -> EvidenceBasedDecision:
        """
        分析市场并返回基于证据的决策

        Args:
            context: 市场上下文

        Returns:
            基于证据的决策
        """
        pass

    @abstractmethod
    async def review(self, trade: TradeResult) -> ReviewReport:
        """
        复盘交易

        Args:
            trade: 交易结果

        Returns:
            复盘报告
        """
        pass

    @abstractmethod
    async def health_check(self) -> bool:
        """
        健康检查

        Returns:
            是否健康
        """
        pass

    def get_capabilities(self) -> Dict[str, Any]:
        """
        获取 Provider 能力

        Returns:
            能力描述
        """
        return {
            'name': self.name,
            'version': self.version,
            'supports_streaming': False,
            'supports_batch': False,
            'max_context_length': None,
        }

    def _set_error(self, error: str) -> None:
        """设置错误信息"""
        self._last_error = error
