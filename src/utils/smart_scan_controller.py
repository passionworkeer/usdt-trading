"""
智能扫描控制器 (Smart Scan Controller)

根据市场条件动态调整扫描频率
"""
import asyncio
import logging
from typing import Dict, Optional
from datetime import datetime, timedelta
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class MarketCondition(Enum):
    """市场条件"""
    LOW_VOLATILITY = "low_volatility"      # 低波动率
    NORMAL = "normal"                       # 正常
    HIGH_VOLATILITY = "high_volatility"     # 高波动率
    EXTREME = "extreme"                     # 极端波动
    LOW_VOLUME = "low_volume"               # 低成交量


@dataclass
class ScanConfig:
    """扫描配置"""
    interval_seconds: int       # 扫描间隔
    max_interval_seconds: int   # 最大间隔
    min_interval_seconds: int   # 最小间隔
    volatility_threshold: float # 波动率阈值


class SmartScanController:
    """
    智能扫描控制器

    根据市场条件自动调整扫描频率：
    - 低波动期 → 降低扫描频率（节省资源）
    - 高波动期 → 提高扫描频率（抓住机会）
    - 极端波动 → 最高频率（风险管理）
    - 低成交量 → 降低频率（避免噪音）
    """

    # 默认配置
    DEFAULT_CONFIG = ScanConfig(
        interval_seconds=180,       # 默认 3 分钟
        max_interval_seconds=600,   # 最大 10 分钟
        min_interval_seconds=30,    # 最小 30 秒
        volatility_threshold=0.02   # 2% 波动率阈值
    )

    # 市场条件对应的扫描间隔乘数
    INTERVAL_MULTIPLIERS = {
        MarketCondition.LOW_VOLATILITY: 2.0,   # 低波动：2倍间隔
        MarketCondition.NORMAL: 1.0,           # 正常：1倍
        MarketCondition.HIGH_VOLATILITY: 0.5,  # 高波动：0.5倍
        MarketCondition.EXTREME: 0.25,        # 极端：0.25倍
        MarketCondition.LOW_VOLUME: 1.5,       # 低成交量：1.5倍
    }

    def __init__(self, config: Optional[ScanConfig] = None):
        """初始化"""
        self.config = config or self.DEFAULT_CONFIG
        self.current_interval = self.config.interval_seconds
        self.current_condition = MarketCondition.NORMAL

        # 统计
        self.stats = {
            'total_scans': 0,
            'condition_changes': 0,
            'intervals_used': [],
        }

        # 最近的市场数据缓存
        self._last_volatility: Optional[float] = None
        self._last_volume_ratio: Optional[float] = None
        self._last_update: Optional[datetime] = None

    def calculate_volatility(
        self,
        high_prices: list,
        low_prices: list,
        close_prices: list
    ) -> float:
        """
        计算波动率 (True Range / Close)

        Args:
            high_prices: 最高价列表
            low_prices: 最低价列表
            close_prices: 收盘价列表

        Returns:
            波动率 (0.0 - 1.0)
        """
        if len(high_prices) < 2:
            return 0.0

        # 计算 True Range
        true_ranges = []
        for i in range(1, len(close_prices)):
            tr = max(
                high_prices[i] - low_prices[i],
                abs(high_prices[i] - close_prices[i-1]),
                abs(low_prices[i] - close_prices[i-1])
            )
            true_ranges.append(tr / close_prices[i])

        # 返回平均波动率
        return sum(true_ranges) / len(true_ranges) if true_ranges else 0.0

    def detect_market_condition(
        self,
        volatility: float,
        volume_ratio: float,
        funding_rate: Optional[float] = None
    ) -> MarketCondition:
        """
        检测市场条件

        Args:
            volatility: 波动率 (0.0 - 1.0)
            volume_ratio: 成交量比率 (相对于平均)
            funding_rate: 资金费率（可选）

        Returns:
            市场条件
        """
        # 更新缓存
        self._last_volatility = volatility
        self._last_volume_ratio = volume_ratio
        self._last_update = datetime.now()

        # 检测极端波动
        if volatility > self.config.volatility_threshold * 3:
            return MarketCondition.EXTREME

        # 检测高波动
        if volatility > self.config.volatility_threshold * 2:
            return MarketCondition.HIGH_VOLATILITY

        # 检测低成交量
        if volume_ratio < 0.5:
            return MarketCondition.LOW_VOLUME

        # 检测低波动
        if volatility < self.config.volatility_threshold * 0.5:
            return MarketCondition.LOW_VOLATILITY

        return MarketCondition.NORMAL

    def calculate_next_interval(
        self,
        market_condition: MarketCondition,
        manual_override: bool = False
    ) -> int:
        """
        计算下次扫描间隔

        Args:
            market_condition: 当前市场条件
            manual_override: 是否手动覆盖

        Returns:
            扫描间隔（秒）
        """
        # 获取乘数
        multiplier = self.INTERVAL_MULTIPLIERS.get(
            market_condition,
            1.0
        )

        # 计算新间隔
        new_interval = int(
            self.config.interval_seconds * multiplier
        )

        # 限制范围
        new_interval = max(
            self.config.min_interval_seconds,
            min(new_interval, self.config.max_interval_seconds)
        )

        # 记录变化
        if new_interval != self.current_interval:
            logger.info(
                f"📊 扫描间隔调整: {self.current_interval}s → {new_interval}s "
                f"({market_condition.value})"
            )
            self.stats['condition_changes'] += 1
            self.current_condition = market_condition

        self.current_interval = new_interval
        self.stats['total_scans'] += 1
        self.stats['intervals_used'].append(new_interval)

        return new_interval

    def get_scan_interval(
        self,
        volatility: Optional[float] = None,
        volume_ratio: Optional[float] = None,
        funding_rate: Optional[float] = None,
        force_condition: Optional[MarketCondition] = None
    ) -> int:
        """
        获取扫描间隔（简化接口）

        Args:
            volatility: 波动率（可选）
            volume_ratio: 成交量比率（可选）
            funding_rate: 资金费率（可选）
            force_condition: 强制市场条件（可选）

        Returns:
            扫描间隔（秒）
        """
        # 如果有强制条件，直接使用
        if force_condition:
            return self.calculate_next_interval(force_condition)

        # 如果缺少数据，使用正常条件
        if volatility is None or volume_ratio is None:
            return self.calculate_next_interval(MarketCondition.NORMAL)

        # 检测市场条件
        condition = self.detect_market_condition(
            volatility,
            volume_ratio,
            funding_rate
        )

        return self.calculate_next_interval(condition)

    def get_stats(self) -> Dict:
        """获取统计信息"""
        intervals = self.stats['intervals_used']
        avg_interval = (
            sum(intervals) / len(intervals)
            if intervals else self.current_interval
        )

        return {
            'current_interval': self.current_interval,
            'current_condition': self.current_condition.value,
            'total_scans': self.stats['total_scans'],
            'condition_changes': self.stats['condition_changes'],
            'avg_interval': round(avg_interval, 1),
            'last_volatility': self._last_volatility,
            'last_volume_ratio': self._last_volume_ratio,
        }

    def reset_stats(self):
        """重置统计"""
        self.stats = {
            'total_scans': 0,
            'condition_changes': 0,
            'intervals_used': [],
        }


# 全局实例
_smart_scan: Optional[SmartScanController] = None


def get_smart_scan(config: Optional[ScanConfig] = None) -> SmartScanController:
    """获取全局智能扫描控制器"""
    global _smart_scan
    if _smart_scan is None:
        _smart_scan = SmartScanController(config)
    return _smart_scan
