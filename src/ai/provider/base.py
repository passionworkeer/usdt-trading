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
                "close": ActionType.HOLD,  # close position is a form of hold/neutral
            }
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
    metadata: Dict[str, Any] = field(default_factory=dict)

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
            'metadata': self.metadata,
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
