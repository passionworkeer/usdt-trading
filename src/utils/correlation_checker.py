"""
P2-22: 相关性检查器（Correlation Checker）

防止过度集中风险 - 检查新仓位与现有仓位的相关性
"""
import logging
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class Position:
    """简化的仓位数据结构"""
    symbol: str
    notional: float  # 名义价值（USDT）
    side: str  # 'LONG' or 'SHORT'
    leverage: int = 1
    entry_price: float = 0.0
    quantity: float = 0.0

    @classmethod
    def from_sniper_position(cls, sniper_pos) -> 'Position':
        """从 SniperPosition 转换"""
        notional = sniper_pos.quantity * sniper_pos.entry_price
        return cls(
            symbol=sniper_pos.symbol,
            notional=notional,
            side=sniper_pos.side.value,
            leverage=sniper_pos.leverage,
            entry_price=sniper_pos.entry_price,
            quantity=sniper_pos.quantity,
        )


@dataclass
class CorrelationCheckResult:
    """相关性检查结果"""
    allowed: bool
    current_exposure: float
    total_correlation: float
    combined_exposure: float
    risk_level: str  # 'low', 'medium', 'high'
    warnings: List[str]
    details: Dict[str, Any]


class CorrelationChecker:
    """
    相关性检查器 - 防止过度集中

    核心功能：
    1. 检查新仓位与现有仓位的相关性
    2. 计算总暴露风险
    3. 评估集中度风险
    """

    # 主要交易对与 BTC 的相关性矩阵（静态示例）
    # 范围: 0.0 (无相关) - 1.0 (完全正相关) - -1.0 (完全负相关)
    CORRELATION_MATRIX: Dict[str, Dict[str, float]] = {
        # Layer 1 / 主要币种
        'BTCUSDT': {
            'ETHUSDT': 0.85,
            'BNBUSDT': 0.75,
            'SOLUSDT': 0.70,
            'XRPUSDT': 0.65,
            'ADAUSDT': 0.60,
            'DOGEUSDT': 0.55,
            'AVAXUSDT': 0.68,
            'MATICUSDT': 0.65,
        },
        'ETHUSDT': {
            'BTCUSDT': 0.85,
            'BNBUSDT': 0.78,
            'SOLUSDT': 0.72,
            'AVAXUSDT': 0.75,
            'MATICUSDT': 0.70,
            'ARBUSDT': 0.80,  # L2 与 ETH 高相关
            'OPUSDT': 0.78,
        },
        # DeFi 相关
        'UNIUSDT': {
            'AAVEUSDT': 0.75,
            'MKRUSDT': 0.70,
            'COMPUSDT': 0.72,
            'CRVUSDT': 0.68,
        },
        # Meme 币相关
        'DOGEUSDT': {
            'SHIBUSDT': 0.85,
            'PEPEUSDT': 0.70,
            'FLOKIUSDT': 0.68,
        },
        # Layer 2 相关
        'ARBUSDT': {
            'OPUSDT': 0.82,
            'MATICUSDT': 0.70,
        },
    }

    # 默认相关性（当没有明确数据时）
    DEFAULT_CORRELATION = 0.5

    # 风险等级阈值
    RISK_THRESHOLDS = {
        'low': 0.5,
        'medium': 0.7,
        'high': 0.85,
    }

    def __init__(
        self,
        max_total_exposure: float = 0.8,
        max_single_correlation: float = 0.9,
        warning_threshold: float = 0.7,
    ):
        """
        初始化相关性检查器

        Args:
            max_total_exposure: 最大总暴露比例（相对于账户权益）
            max_single_correlation: 单一交易对最大相关性
            warning_threshold: 警告阈值
        """
        self.max_total_exposure = max_total_exposure
        self.max_single_correlation = max_single_correlation
        self.warning_threshold = warning_threshold

        logger.info("📊 相关性检查器已初始化")
        logger.info(f"  最大总暴露: {max_total_exposure:.0%}")
        logger.info(f"  单一最大相关性: {max_single_correlation:.2f}")
        logger.info(f"  警告阈值: {warning_threshold:.2f}")

    def get_correlation(self, symbol1: str, symbol2: str) -> float:
        """
        获取两个交易对之间的相关性

        Args:
            symbol1: 交易对1
            symbol2: 交易对2

        Returns:
            相关系数 (-1.0 到 1.0)
        """
        if symbol1 == symbol2:
            return 1.0

        # 查找相关性矩阵
        corr = self.CORRELATION_MATRIX.get(symbol1, {}).get(symbol2)
        if corr is not None:
            return corr

        # 反向查找
        corr = self.CORRELATION_MATRIX.get(symbol2, {}).get(symbol1)
        if corr is not None:
            return corr

        # 默认相关性
        return self.DEFAULT_CORRELATION

    def check_new_position(
        self,
        symbol: str,
        positions: List[Position],
        estimated_notional: float,
        account_equity: float,
    ) -> CorrelationCheckResult:
        """
        检查新仓位是否会导致过度集中

        Args:
            symbol: 新仓位交易对
            positions: 现有仓位列表
            estimated_notional: 新仓位估计名义价值
            account_equity: 账户权益

        Returns:
            CorrelationCheckResult: 检查结果
        """
        warnings: List[str] = []
        details: Dict[str, Any] = {
            'symbol': symbol,
            'estimated_notional': estimated_notional,
            'existing_positions': len(positions),
            'correlations': {},
        }

        # 计算当前总暴露
        current_exposure = sum(p.notional for p in positions)
        details['current_exposure'] = current_exposure

        # 计算加权相关性
        total_weighted_correlation = 0.0
        max_single_corr = 0.0
        max_corr_symbol = ''

        for pos in positions:
            corr = self.get_correlation(symbol, pos.symbol)
            details['correlations'][pos.symbol] = corr

            # 加权相关性 = 相关性 * 仓位权重
            weight = pos.notional / current_exposure if current_exposure > 0 else 0
            weighted_corr = corr * weight
            total_weighted_correlation += weighted_corr

            # 跟踪最大单一相关性
            if abs(corr) > abs(max_single_corr):
                max_single_corr = corr
                max_corr_symbol = pos.symbol

            # 检查单一相关性警告
            if abs(corr) > self.max_single_correlation:
                warnings.append(
                    f"高相关性警告: {symbol} vs {pos.symbol} = {corr:.2f}"
                )

        details['max_single_correlation'] = max_single_corr
        details['max_corr_symbol'] = max_corr_symbol

        # 计算组合暴露
        combined_exposure = current_exposure + estimated_notional
        exposure_ratio = combined_exposure / account_equity if account_equity > 0 else float('inf')
        details['combined_exposure'] = combined_exposure
        details['exposure_ratio'] = exposure_ratio

        # 确定风险等级
        if abs(total_weighted_correlation) >= self.RISK_THRESHOLDS['high']:
            risk_level = 'high'
        elif abs(total_weighted_correlation) >= self.RISK_THRESHOLDS['medium']:
            risk_level = 'medium'
        else:
            risk_level = 'low'

        details['total_weighted_correlation'] = total_weighted_correlation

        # 检查是否超过阈值
        allowed = True

        if exposure_ratio > self.max_total_exposure:
            allowed = False
            warnings.append(
                f"暴露超限: {exposure_ratio:.1%} > {self.max_total_exposure:.0%}"
            )

        if abs(total_weighted_correlation) > self.warning_threshold:
            warnings.append(
                f"高集中度风险: 加权相关性 = {total_weighted_correlation:.2f}"
            )

        # 同向持仓检查
        same_direction_exposure = sum(
            p.notional for p in positions
            if self._is_same_direction(symbol, p.side)
        )
        details['same_direction_exposure'] = same_direction_exposure

        if same_direction_exposure > account_equity * 0.6:
            warnings.append(
                f"同向持仓集中: {same_direction_exposure:.0f} USDT"
            )

        result = CorrelationCheckResult(
            allowed=allowed,
            current_exposure=current_exposure,
            total_correlation=total_weighted_correlation,
            combined_exposure=combined_exposure,
            risk_level=risk_level,
            warnings=warnings,
            details=details,
        )

        self._log_result(result)

        return result

    def _is_same_direction(self, new_symbol: str, existing_side: str) -> bool:
        """判断是否同向（简化版，实际应根据交易策略判断）"""
        # 这里简化处理：假设所有 LONG 都是同向
        return existing_side == 'LONG'

    def _log_result(self, result: CorrelationCheckResult) -> None:
        """记录检查结果"""
        status = "✅ 允许" if result.allowed else "❌ 拒绝"
        logger.info(f"\n{'='*60}")
        logger.info(f"🔍 相关性检查结果: {status}")
        logger.info(f"{'='*60}")
        logger.info(f"当前暴露: ${result.current_exposure:.2f}")
        logger.info(f"加权相关性: {result.total_correlation:.2f}")
        logger.info(f"组合暴露: ${result.combined_exposure:.2f}")
        logger.info(f"风险等级: {result.risk_level.upper()}")

        if result.warnings:
            logger.warning(f"警告 ({len(result.warnings)}):")
            for warning in result.warnings:
                logger.warning(f"  ⚠️ {warning}")

        if result.details.get('correlations'):
            logger.info("相关性详情:")
            for sym, corr in result.details['correlations'].items():
                logger.info(f"  {sym}: {corr:.2f}")

        logger.info(f"{'='*60}\n")

    def get_portfolio_concentration(
        self,
        positions: List[Position],
    ) -> Dict[str, Any]:
        """
        计算投资组合集中度

        Args:
            positions: 仓位列表

        Returns:
            集中度分析结果
        """
        if not positions:
            return {
                'total_notional': 0,
                'concentration_score': 0,
                'top_positions': [],
                'correlation_clusters': [],
            }

        # 计算总名义价值
        total_notional = sum(p.notional for p in positions)

        # 计算每个仓位的权重
        weights = {
            p.symbol: p.notional / total_notional
            for p in positions
        }

        # 找出最大仓位
        sorted_positions = sorted(
            positions,
            key=lambda p: p.notional,
            reverse=True
        )
        top_positions = [
            {
                'symbol': p.symbol,
                'notional': p.notional,
                'weight': weights[p.symbol],
            }
            for p in sorted_positions[:5]
        ]

        # 计算集中度分数（赫芬达尔指数）
        hhi = sum(w ** 2 for w in weights.values())

        # 识别相关性集群
        clusters = self._identify_correlation_clusters(positions)

        return {
            'total_notional': total_notional,
            'concentration_score': hhi,
            'top_positions': top_positions,
            'correlation_clusters': clusters,
            'num_positions': len(positions),
        }

    def _identify_correlation_clusters(
        self,
        positions: List[Position],
        threshold: float = 0.7,
    ) -> List[Dict[str, Any]]:
        """
        识别高相关性集群

        Args:
            positions: 仓位列表
            threshold: 相关性阈值

        Returns:
            相关性集群列表
        """
        if len(positions) < 2:
            return []

        clusters = []
        processed = set()

        for i, pos1 in enumerate(positions):
            if pos1.symbol in processed:
                continue

            cluster_members = [pos1.symbol]
            cluster_notional = pos1.notional

            for j, pos2 in enumerate(positions):
                if i == j or pos2.symbol in processed:
                    continue

                corr = self.get_correlation(pos1.symbol, pos2.symbol)
                if abs(corr) >= threshold:
                    cluster_members.append(pos2.symbol)
                    cluster_notional += pos2.notional

            if len(cluster_members) > 1:
                clusters.append({
                    'members': cluster_members,
                    'total_notional': cluster_notional,
                    'avg_correlation': sum(
                        self.get_correlation(pos1.symbol, m)
                        for m in cluster_members
                        if m != pos1.symbol
                    ) / (len(cluster_members) - 1) if len(cluster_members) > 1 else 0,
                })
                processed.update(cluster_members)

        return clusters

    def update_correlation_matrix(
        self,
        symbol1: str,
        symbol2: str,
        correlation: float,
    ) -> None:
        """
        更新相关性矩阵

        Args:
            symbol1: 交易对1
            symbol2: 交易对2
            correlation: 相关系数
        """
        if symbol1 not in self.CORRELATION_MATRIX:
            self.CORRELATION_MATRIX[symbol1] = {}

        self.CORRELATION_MATRIX[symbol1][symbol2] = correlation
        logger.info(f"更新相关性: {symbol1} - {symbol2} = {correlation:.2f}")


# 便捷函数
def check_position_correlation(
    symbol: str,
    positions: List[Position],
    estimated_notional: float,
    account_equity: float,
) -> CorrelationCheckResult:
    """
    便捷函数：检查仓位相关性

    Args:
        symbol: 新仓位交易对
        positions: 现有仓位列表
        estimated_notional: 新仓位估计名义价值
        account_equity: 账户权益

    Returns:
        CorrelationCheckResult: 检查结果
    """
    checker = CorrelationChecker()
    return checker.check_new_position(
        symbol,
        positions,
        estimated_notional,
        account_equity,
    )


if __name__ == '__main__':
    """测试相关性检查器"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # 创建测试仓位
    test_positions = [
        Position(symbol='BTCUSDT', notional=500, side='LONG'),
        Position(symbol='ETHUSDT', notional=300, side='LONG'),
    ]

    checker = CorrelationChecker()

    # 测试1: 检查高相关性的 SOL
    print("\n测试1: 检查 SOLUSDT (与 BTC/ETH 高相关)")
    result1 = checker.check_new_position(
        symbol='SOLUSDT',
        positions=test_positions,
        estimated_notional=200,
        account_equity=1000,
    )
    print(f"结果: 允许={result1.allowed}, 风险={result1.risk_level}")

    # 测试2: 检查低相关性的 DOGE
    print("\n测试2: 检查 DOGEUSDT (与 BTC 中等相关)")
    result2 = checker.check_new_position(
        symbol='DOGEUSDT',
        positions=test_positions,
        estimated_notional=200,
        account_equity=1000,
    )
    print(f"结果: 允许={result2.allowed}, 风险={result2.risk_level}")

    # 测试3: 获取投资组合集中度
    print("\n测试3: 投资组合集中度分析")
    concentration = checker.get_portfolio_concentration(test_positions)
    print(f"总名义价值: ${concentration['total_notional']:.2f}")
    print(f"集中度分数 (HHI): {concentration['concentration_score']:.4f}")
    print(f"最大仓位: {concentration['top_positions']}")
