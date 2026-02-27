"""
基于结构化证据链的风控系统

废除浮点数 confidence，改用结构化证据链进行决策验证
"""
import logging
import os
from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass, field

import yaml

from src.ai.provider.base import ActionType, EvidenceBasedDecision

logger = logging.getLogger(__name__)

# 默认配置值
DEFAULT_MIN_EVIDENCE_COUNT = 2
DEFAULT_MAX_EVIDENCE_COUNT = 10
DEFAULT_ALLOW_VETO_OVERRIDE = False


def _load_config() -> Dict[str, Any]:
    """加载配置文件"""
    config_path = os.environ.get("TRADING_CONFIG_PATH", "config/trading_config.yaml")
    default_config = {
        "risk_control": {
            "min_evidence_count": 2,
            "max_evidence_count": 10,
            "allow_veto_override": False,
        },
        "price_validation": {
            "min_position_size": 0.001,
            "max_position_size_ratio": 1.0,
            "default_stop_loss_pct": 0.02,
            "default_take_profit_pct": 0.04,
        },
    }

    try:
        if os.path.exists(config_path):
            with open(config_path, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f)
                if config:
                    # 合并配置，文件配置覆盖默认配置
                    for key in default_config:
                        if key in config:
                            default_config[key].update(config[key])
                    logger.info(f"已加载交易配置: {config_path}")
                return default_config
    except Exception as e:
        logger.warning(f"加载配置文件失败，使用默认配置: {e}")

    return default_config


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
        min_evidence_count: Optional[int] = None,
        max_evidence_count: Optional[int] = None,
        allow_veto_override: Optional[bool] = None,
        config: Optional[Dict[str, Any]] = None,
    ):
        """
        初始化证据链风控器

        Args:
            min_evidence_count: 最小证据数量要求（默认从配置读取）
            max_evidence_count: 最大证据数量限制（默认从配置读取）
            allow_veto_override: 是否允许覆盖否决标记（默认从配置读取）
            config: 可选的配置字典，覆盖从文件加载的配置
        """
        # 加载配置（优先使用传入的 config，否则从文件加载）
        loaded_config = config if config is not None else _load_config()
        risk_config = loaded_config.get("risk_control", {})

        # 设置参数（传入值 > 配置值 > 默认值）
        self.min_evidence_count = min_evidence_count if min_evidence_count is not None else risk_config.get("min_evidence_count", 2)
        self.max_evidence_count = max_evidence_count if max_evidence_count is not None else risk_config.get("max_evidence_count", 10)
        self.allow_veto_override = allow_veto_override if allow_veto_override is not None else risk_config.get("allow_veto_override", False)

        self.stats = {
            'total_validated': 0,
            'passed': 0,
            'rejected': 0,
            'rejection_reasons': {}
        }

        logger.info(
            f"EvidenceBasedRiskController 已初始化: "
            f"min_evidence={self.min_evidence_count}, "
            f"max_evidence={self.max_evidence_count}, "
            f"allow_veto_override={self.allow_veto_override}"
        )

    def _normalize_action(self, action: Any) -> str:
        """
        标准化交易动作

        支持以下格式:
        - long/Long → buy
        - short/Short → sell
        - buy/Buy → buy
        - sell/Sell → sell
        - close/Close → close (平仓，不验证价格)
        - hold/Hold → hold

        Args:
            action: 原始动作（str 或 ActionType）

        Returns:
            标准化后的动作 (buy/sell/close/hold)
        """
        if hasattr(action, 'value'):
            action = action.value

        action_str = str(action).lower()

        # 映射表
        action_map = {
            'long': 'buy',
            'short': 'sell',
            'buy': 'buy',
            'sell': 'sell',
            'close': 'close',  # 平仓单独处理
            'hold': 'hold',
        }

        return action_map.get(action_str, 'hold')

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

        # 4. 检查仓位大小（hold/close 操作可以为 0）
        action = self._normalize_action(decision.action)
        if action not in ['hold', 'close'] and decision.position_size <= 0:
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
        - buy/long: 止损 < 入场 < 止盈
        - sell/short/close: 止盈 < 入场 < 止损
        - hold/close: 不验证
        """
        action = self._normalize_action(decision.action)

        # hold 和 close 操作不需要价格验证
        if action in ['hold', 'close']:
            return True, "无需验证价格"

        entry = decision.entry_price
        stop = decision.stop_loss
        take = decision.take_profit

        # 检查价格是否为零（可能是未初始化）
        if entry == 0:
            return False, "入场价格不能为零"
        if stop == 0:
            return False, "止损价格不能为零"
        if take == 0:
            return False, "止盈价格不能为零"

        # 基本检查：所有价格必须为正数
        if entry < 0 or stop < 0 or take < 0:
            return False, "价格必须为正数"

        if action == 'buy':
            # 做多：止损 < 入场 < 止盈
            if not (stop < entry < take):
                return False, f"做多价格逻辑错误: 止损({stop}) < 入场({entry}) < 止盈({take}) 不满足"

        elif action == 'sell':
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
            "     - buy: 止损 < 入场 < 止盈",
            "     - sell: 止盈 < 入场 < 止损",
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
