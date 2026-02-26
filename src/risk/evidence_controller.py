"""
基于结构化证据链的风控系统

废除浮点数 confidence，改用结构化证据链进行决策验证
"""
import logging
from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class ActionType(Enum):
    """交易动作类型"""
    LONG = "long"
    SHORT = "short"
    CLOSE = "close"
    HOLD = "hold"


@dataclass
class EvidenceBasedDecision:
    """
    基于证据的决策数据类

    Attributes:
        action: 交易动作 (long/short/close/hold)
        evidence_count: 证据数量
        evidence_chain: 证据链列表，每项是一个证据描述
        veto_flag: 否决标记，True 表示存在否决条件
        entry_price: 入场价格
        stop_loss: 止损价格
        take_profit: 止盈价格
        position_size: 仓位大小
        symbol: 交易对 (可选)
        metadata: 额外元数据 (可选)
    """
    action: str
    evidence_count: int
    evidence_chain: List[str]
    veto_flag: bool
    entry_price: float
    stop_loss: float
    take_profit: float
    position_size: float
    symbol: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        """验证数据一致性"""
        if self.evidence_count != len(self.evidence_chain):
            logger.warning(
                f"证据数量不匹配: evidence_count={self.evidence_count}, "
                f"实际证据链长度={len(self.evidence_chain)}"
            )
            self.evidence_count = len(self.evidence_chain)


@dataclass
class ValidationResult:
    """验证结果"""
    passed: bool
    reason: str
    details: Dict[str, Any] = field(default_factory=dict)


class EvidenceBasedRiskController:
    """
    基于证据链的风险控制器

    核心逻辑：
    1. 废除浮点数 confidence，改用结构化证据链
    2. 证据数量必须达到最低阈值
    3. 存在否决标记时阻止交易
    4. 价格参数必须合理（止损 < 入场 < 止盈）
    """

    def __init__(
        self,
        min_evidence_count: int = 2,
        max_evidence_count: int = 10,
        allow_veto_override: bool = False
    ):
        """
        初始化证据链风控器

        Args:
            min_evidence_count: 最小证据数量要求（默认 2）
            max_evidence_count: 最大证据数量限制（默认 10）
            allow_veto_override: 是否允许覆盖否决标记（默认 False）
        """
        self.min_evidence_count = min_evidence_count
        self.max_evidence_count = max_evidence_count
        self.allow_veto_override = allow_veto_override
        self.stats = {
            'total_validated': 0,
            'passed': 0,
            'rejected': 0,
            'rejection_reasons': {}
        }

        logger.info(
            f"EvidenceBasedRiskController 已初始化: "
            f"min_evidence={min_evidence_count}, "
            f"allow_veto_override={allow_veto_override}"
        )

    def validate(self, decision: EvidenceBasedDecision) -> Tuple[bool, str]:
        """
        验证决策是否通过风控检查

        Args:
            decision: 基于证据的决策对象

        Returns:
            (是否通过, 原因)
        """
        self.stats['total_validated'] += 1

        # 1. 检查证据数量
        if decision.evidence_count < self.min_evidence_count:
            reason = f"证据不足: {decision.evidence_count} < {self.min_evidence_count}"
            self._record_rejection(reason)
            return False, reason

        if decision.evidence_count > self.max_evidence_count:
            reason = f"证据过多: {decision.evidence_count} > {self.max_evidence_count}"
            self._record_rejection(reason)
            return False, reason

        # 2. 检查否决标记
        if decision.veto_flag and not self.allow_veto_override:
            reason = "存在否决标记，交易被阻止"
            self._record_rejection(reason)
            return False, reason

        # 3. 检查价格参数合理性
        valid, reason = self._validate_prices(decision)
        if not valid:
            self._record_rejection(reason)
            return False, reason

        # 4. 检查仓位大小（close/hold 操作可以为 0）
        action = decision.action.lower()
        if action not in ['close', 'hold'] and decision.position_size <= 0:
            reason = "仓位大小必须为正数"
            self._record_rejection(reason)
            return False, reason

        # 所有检查通过
        self.stats['passed'] += 1
        logger.info(f"决策验证通过: {decision.action} | 证据数={decision.evidence_count}")
        return True, "通过"

    def _validate_prices(self, decision: EvidenceBasedDecision) -> Tuple[bool, str]:
        """
        验证价格参数的合理性

        根据不同的 action 类型验证价格逻辑：
        - long: 止损 < 入场 < 止盈
        - short: 止盈 < 入场 < 止损
        - close/hold: 不验证
        """
        action = decision.action.lower()

        if action in ['close', 'hold']:
            return True, "无需验证价格"

        entry = decision.entry_price
        stop = decision.stop_loss
        take = decision.take_profit

        # 基本检查：所有价格必须为正
        if entry <= 0 or stop <= 0 or take <= 0:
            return False, "价格必须为正数"

        if action == 'long':
            # 做多：止损 < 入场 < 止盈
            if not (stop < entry < take):
                return False, f"做多价格逻辑错误: 止损({stop}) < 入场({entry}) < 止盈({take}) 不满足"

        elif action == 'short':
            # 做空：止盈 < 入场 < 止损
            if not (take < entry < stop):
                return False, f"做空价格逻辑错误: 止盈({take}) < 入场({entry}) < 止损({stop}) 不满足"

        return True, "价格参数合理"

    def _record_rejection(self, reason: str):
        """记录拒绝原因"""
        self.stats['rejected'] += 1
        self.stats['rejection_reasons'][reason] = self.stats['rejection_reasons'].get(reason, 0) + 1
        logger.warning(f"决策被拒绝: {reason}")

    def build_prompt_for_ai(self, decision: EvidenceBasedDecision) -> str:
        """
        为 AI 生成结构化的验证提示词

        生成的提示词包含：
        - 决策的基本信息
        - 证据链详情
        - 风控参数
        - 验证规则说明

        Returns:
            结构化提示词字符串
        """
        lines = [
            "=" * 60,
            "证据链风控验证请求",
            "=" * 60,
            "",
            "【决策信息】",
            f"  动作: {decision.action}",
            f"  交易对: {decision.symbol or 'N/A'}",
            f"  否决标记: {decision.veto_flag}",
            "",
            "【价格参数】",
            f"  入场价格: {decision.entry_price}",
            f"  止损价格: {decision.stop_loss}",
            f"  止盈价格: {decision.take_profit}",
            f"  仓位大小: {decision.position_size}",
            "",
            "【证据链】",
            f"  证据数量: {decision.evidence_count}",
            "  证据列表:",
        ]

        for i, evidence in enumerate(decision.evidence_chain, 1):
            lines.append(f"    {i}. {evidence}")

        lines.extend([
            "",
            "【风控配置】",
            f"  最小证据数: {self.min_evidence_count}",
            f"  最大证据数: {self.max_evidence_count}",
            f"  允许覆盖否决: {self.allow_veto_override}",
            "",
            "【验证规则】",
            "  1. 证据数量必须 >= 最小证据数",
            "  2. 存在否决标记时阻止交易（除非允许覆盖）",
            "  3. 价格参数必须合理:",
            "     - 做多: 止损 < 入场 < 止盈",
            "     - 做空: 止盈 < 入场 < 止损",
            "  4. 仓位大小必须为正数",
            "",
            "请验证以上决策是否符合所有风控规则。",
            "=" * 60,
        ])

        return "\n".join(lines)

    def get_stats(self) -> Dict:
        """获取控制器统计信息"""
        return {
            'config': {
                'min_evidence_count': self.min_evidence_count,
                'max_evidence_count': self.max_evidence_count,
                'allow_veto_override': self.allow_veto_override,
            },
            'stats': self.stats.copy(),
            'pass_rate': (
                self.stats['passed'] / self.stats['total_validated'] * 100
                if self.stats['total_validated'] > 0 else 0
            )
        }

    def reset_stats(self):
        """重置统计数据"""
        self.stats = {
            'total_validated': 0,
            'passed': 0,
            'rejected': 0,
            'rejection_reasons': {}
        }
        logger.info("证据链风控统计已重置")
