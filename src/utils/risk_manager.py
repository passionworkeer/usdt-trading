"""
风险管理增强模块 (Risk Management Enhanced)

提供仓位管理、相关性分析、风险控制功能
"""
import logging
import math
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class RiskLevel(Enum):
    """风险等级"""
    VERY_LOW = 0.2   # 非常低
    LOW = 0.3        # 低
    MEDIUM = 0.4     # 中等
    HIGH = 0.5       # 高
    VERY_HIGH = 0.6  # 非常高


@dataclass
class PositionSize:
    """仓位大小"""
    symbol: str
    quantity: float
    entry_price: float
    value_usdt: float  # 仓位价值 (USDT)
    risk_pct: float    # 风险比例 (%)


@dataclass
class CorrelationPair:
    """相关性交易对"""
    symbol_a: str
    symbol_b: str
    correlation: float  # 相关系数 (-1 to 1)


class PositionManager:
    """
    仓位管理器

    功能：
    1. 动态仓位计算
    2. 风险敞口管理
    3. 分散化控制
    """

    # 各风险等级的最大仓位比例
    MAX_POSITION_BY_RISK = {
        RiskLevel.VERY_LOW: 0.40,  # 40% 仓位
        RiskLevel.LOW: 0.30,        # 30% 仓位
        RiskLevel.MEDIUM: 0.20,     # 20% 仓位
        RiskLevel.HIGH: 0.15,      # 15% 仓位
        RiskLevel.VERY_HIGH: 0.10, # 10% 仓位
    }

    def __init__(
        self,
        total_capital: float = 200.0,
        max_total_risk: float = 0.25,  # 最大总风险 25%
        risk_level: RiskLevel = RiskLevel.LOW
    ):
        """
        初始化仓位管理器

        Args:
            total_capital: 总资金 (USDT)
            max_total_risk: 最大总风险比例
            risk_level: 风险等级
        """
        self.total_capital = total_capital
        self.max_total_risk = max_total_risk
        self.risk_level = risk_level
        self.current_positions: Dict[str, PositionSize] = {}
        self.position_history: List[Dict] = []

    def calculate_position_size(
        self,
        symbol: str,
        entry_price: float,
        stop_loss_pct: float,
        risk_reward_ratio: float = 2.0
    ) -> Tuple[float, float]:
        """
        计算仓位大小

        Args:
            symbol: 交易对
            entry_price: 入场价格
           止损比例 (%)
        risk_reward_ratio: 风险回报比

        Returns:
            (仓位数量, 仓位价值 USDT)
        """
        # 获取单笔最大风险金额
        max_position_value = self.total_capital * self.max_total_risk * self.max_position_by_level

        # 根据止损比例计算仓位
        # 风险金额 = 仓位价值 * 止损比例
        # 仓位价值 = 风险金额 / 止损比例
        if stop_loss_pct > 0:
            position_value = (self.total_capital * self.max_total_risk) / stop_loss_pct * 100
            position_value = min(position_value, max_position_value)
        else:
            position_value = max_position_value

        # 计算数量
        quantity = position_value / entry_price

        return quantity, position_value

    @property
    def max_position_by_level(self) -> float:
        """获取当前风险等级的最大仓位比例"""
        return self.MAX_POSITION_BY_RISK[self.risk_level]

    def add_position(self, position: PositionSize):
        """添加仓位"""
        self.current_positions[position.symbol] = position
        self.position_history.append({
            'symbol': position.symbol,
            'value': position.value_usdt,
            'action': 'open',
            'total_exposure': self.get_total_exposure()
        })
        logger.info(f"✅ 添加仓位: {position.symbol}, 价值: {position.value_usdt:.2f} USDT")

    def close_position(self, symbol: str):
        """平仓"""
        if symbol in self.current_positions:
            position = self.current_positions.pop(symbol)
            self.position_history.append({
                'symbol': symbol,
                'value': position.value_usdt,
                'action': 'close',
                'total_exposure': self.get_total_exposure()
            })
            logger.info(f"✅ 平仓: {symbol}")

    def get_total_exposure(self) -> float:
        """获取总风险敞口"""
        return sum(p.value_usdt for p in self.current_positions.values())

    def get_total_exposure_pct(self) -> float:
        """获取总风险敞口比例"""
        return self.get_total_exposure() / self.total_capital * 100

    def can_open_position(self, symbol: str, value: float) -> Tuple[bool, str]:
        """
        检查是否可以开仓

        Args:
            symbol: 交易对
            value: 仓位价值

        Returns:
            (是否可以开仓, 原因)
        """
        total_exposure = self.get_total_exposure() + value

        # 检查总敞口
        if total_exposure > self.total_capital * self.max_total_risk * 1.5:
            return False, f"总风险敞口超限: {total_exposure/self.total_capital*100:.1f}%"

        # 检查单币种敞口
        if symbol in self.current_positions:
            current_value = self.current_positions[symbol].value_usdt
            new_value = current_value + value
            if new_value > self.total_capital * self.max_position_by_level:
                return False, f"单币种敞口超限: {new_value/self.total_capital*100:.1f}%"

        return True, "可以开仓"

    def rebalance(self) -> List[str]:
        """
        仓位再平衡

        Returns:
            需要平仓的交易对列表
        """
        to_close = []
        total_exposure = self.get_total_exposure()

        if total_exposure > self.total_capital * self.max_total_risk:
            # 需要减仓
            for symbol, position in list(self.current_positions.items()):
                if total_exposure > self.total_capital * self.max_total_risk * 0.8:
                    to_close.append(symbol)
                    self.close_position(symbol)
                    total_exposure = self.get_total_exposure()

        return to_close


class CorrelationAnalyzer:
    """
    相关性分析器

    功能：
    1. 计算交易对相关性
    2. 提供分散化建议
    3. 避免过度集中
    """

    # 预定义的高相关性交易对（避免同时持有）
    HIGH_CORRELATION_PAIRS = {
        ('BTC/USDT', 'ETH/USDT'): 0.8,
        ('BTC/USDT', 'BNB/USDT'): 0.7,
        ('ETH/USDT', 'SOL/USDT'): 0.65,
        ('XRP/USDT', 'ADA/USDT'): 0.75,
    }

    def __init__(self):
        """初始化相关性分析器"""
        self.correlation_cache: Dict[Tuple[str, str], float] = {}

    def check_correlation_risk(self, symbols: List[str]) -> Tuple[bool, List[str]]:
        """
        检查相关性风险

        Args:
            symbols: 交易对列表

        Returns:
            (是否有风险, 警告列表)
        """
        warnings = []

        # 检查预定义的高相关性交易对
        for i, sym_a in enumerate(symbols):
            for sym_b in symbols[i+1:]:
                key = (sym_a, sym_b)
                reverse_key = (sym_b, sym_a)

                corr = self.HIGH_CORRELATION_PAIRS.get(key) or self.HIGH_CORRELATION_PAIRS.get(reverse_key)

                if corr and corr > 0.7:
                    warnings.append(f"⚠️ {sym_a} 和 {sym_b} 相关性高 ({corr:.0%})")

        return len(warnings) > 0, warnings

    def get_diversification_score(self, symbols: List[str]) -> float:
        """
        获取分散化分数

        Args:
            symbols: 交易对列表

        Returns:
            分散化分数 (0-100)
        """
        if len(symbols) <= 1:
            return 0

        # 基础分数：交易对数量
        base_score = min(len(symbols) / 5 * 40, 40)

        # 相关性惩罚
        correlation_penalty = 0
        for i, sym_a in enumerate(symbols):
            for sym_b in symbols[i+1:]:
                key = (sym_a, sym_b)
                reverse_key = (sym_b, sym_a)
                corr = self.HIGH_CORRELATION_PAIRS.get(key) or self.HIGH_CORRELATION_PAIRS.get(reverse_key)
                if corr:
                    correlation_penalty += corr * 10

        diversification_score = max(0, base_score - correlation_penalty + 60)
        return min(100, diversification_score)


class RiskManager:
    """
    综合风险管理器

    整合仓位管理和相关性分析
    """

    def __init__(
        self,
        total_capital: float = 200.0,
        risk_level: RiskLevel = RiskLevel.LOW
    ):
        """初始化风险管理器"""
        self.position_manager = PositionManager(total_capital, risk_level=risk_level)
        self.correlation_analyzer = CorrelationAnalyzer()

    def validate_new_position(
        self,
        symbol: str,
        entry_price: float,
        stop_loss_pct: float,
        existing_symbols: List[str]
    ) -> Tuple[bool, str, Optional[float]]:
        """
        验证新仓位

        Args:
            symbol: 交易对
            entry_price: 入场价格
            止损比例
            existing_symbols: 现有持仓交易对

        Returns:
            (是否允许, 原因, 建议仓位价值)
        """
        # 计算仓位
        quantity, position_value = self.position_manager.calculate_position_size(
            symbol, entry_price, stop_loss_pct
        )

        # 检查仓位限制
        can_open, reason = self.position_manager.can_open_position(symbol, position_value)
        if not can_open:
            return False, reason, None

        # 检查相关性风险
        all_symbols = existing_symbols + [symbol]
        has_correlation_risk, warnings = self.correlation_analyzer.check_correlation_risk(all_symbols)

        if has_correlation_risk:
            return True, "; ".join(warnings), position_value

        return True, "可以开仓", position_value

    def get_risk_report(self) -> str:
        """
        获取风险报告

        Returns:
            格式化的风险报告
        """
        pm = self.position_manager
        ca = self.correlation_analyzer

        symbols = list(pm.current_positions.keys())
        div_score = ca.get_diversification_score(symbols)

        report = f"""
{'='*50}
🛡️ 风险管理报告
{'='*50}

💰 仓位状态:
- 总敞口: {pm.get_total_exposure():.2f} USDT ({pm.get_total_exposure_pct():.1f}%)
- 持仓数量: {len(pm.current_positions)}
- 最大单笔: {pm.max_position_by_level*100:.0f}%

📊 分散化:
- 分散化分数: {div_score:.0f}/100
- 持仓交易对: {', '.join(symbols) if symbols else '无'}

⚠️ 相关性检查:
"""
        if symbols:
            has_risk, warnings = ca.check_correlation_risk(symbols)
            if warnings:
                for w in warnings:
                    report += f"  {w}\n"
            else:
                report += "  ✅ 无高相关性风险\n"

        report += f"{'='*50}\n"
        return report


# 全局风险管理器实例
_global_risk_manager: Optional[RiskManager] = None


def get_risk_manager(
    total_capital: float = 200.0,
    risk_level: RiskLevel = RiskLevel.LOW
) -> RiskManager:
    """获取全局风险管理器"""
    global _global_risk_manager
    if _global_risk_manager is None:
        _global_risk_manager = RiskManager(total_capital, risk_level)
    return _global_risk_manager
