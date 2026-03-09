"""
智能资金检测模块

检测大户/聪明钱的操作痕迹：
- 大额订单检测
- 聪明钱指标
- 订单簿分析
- 现货-期货套利机会
- 资金流向分析
- 机构行为识别
"""
import logging
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)


class FlowDirection(Enum):
    """资金流向"""
    INFLOW = 1    # 资金流入
    OUTFLOW = -1  # 资金流出
    NEUTRAL = 0   # 中
class SmartMoneySignal:
    """性


@dataclass智能资金信号"""
    signal_type: str
    strength: float  # 0-1
    reason: str
    metadata: Dict = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


class SmartMoneyDetector:
    """
    智能资金检测器

    检测大户和机构的操作痕迹
    """

    def __init__(self, large_order_threshold: float = 10000):
        """
        初始化

        Args:
            large_order_threshold: 大额订单阈值 (USDT)
        """
        self.large_order_threshold = large_order_threshold

    def detect_large_orders(self, df: pd.DataFrame,
                           volume_col: str = 'volume',
                           price_col: str = 'close') -> pd.DataFrame:
        """
        检测大额订单

        Args:
            df: 包含成交量的 DataFrame
            volume_col: 成交量列名
            price_col: 价格列名

        Returns:
            包含大额订单标记的 DataFrame
        """
        result = df.copy()

        # 计算平均成交量
        result['avg_volume'] = result[volume_col].rolling(window=20).mean()
        result['volume_std'] = result[volume_col].rolling(window=20).std()

        # 成交量异常检测 (超过均值 2 倍标准差)
        result['volume_zscore'] = (result[volume_col] - result['avg_volume']) / result['volume_std']
        result['large_order'] = result['volume_zscore'] > 2

        # 大额订单金额
        result['order_amount'] = result[volume_col] * result[price_col]
        result['large_amount'] = result['order_amount'] > self.large_order_threshold

        return result

    def calculate_flow_indicator(self, df: pd.DataFrame) -> pd.Series:
        """
        计算资金流向指标

        使用成交量加权价格变化
        """
        # 价格变化
        price_change = df['close'].diff()

        # 成交量加权
        volume = df['volume']

        # 资金流向 = 价格变化 * 成交量
        flow = price_change * volume

        # 平滑
        flow_ma = flow.rolling(window=20).mean()

        # 归一化
        flow_normalized = (flow - flow_ma) / flow_ma.abs()

        return flow_normalized

    def detect_accumulation(self, df: pd.DataFrame) -> SmartMoneySignal:
        """
        检测吸筹阶段

        特征：
        - 价格横盘
        - 成交量放大
        - 收盘价在中上部
        """
        recent = df.tail(20)

        # 价格波动性
        price_range = (recent['high'] - recent['low']) / recent['close']
        low_volatility = price_range.mean() < 0.03

        # 成交量趋势
        volume_trend = recent['volume'].diff().tail(10).mean()
        increasing_volume = volume_trend > 0

        # 价格位置
        current_price = df['close'].iloc[-1]
        price_position = (current_price - recent['low'].iloc[-1]) / (recent['high'].iloc[-1] - recent['low'].iloc[-1])
        high_position = price_position > 0.5

        if low_volatility and increasing_volume and high_position:
            strength = (price_position + 0.3) / 1.3
            return SmartMoneySignal(
                signal_type="accumulation",
                strength=strength,
                reason="Smart money accumulation detected",
                metadata={'price_position': price_position}
            )

        return SmartMoneySignal(
            signal_type="none",
            strength=0,
            reason="No accumulation detected"
        )

    def detect_distribution(self, df: pd.DataFrame) -> SmartMoneySignal:
        """
        检测派发阶段

        特征：
        - 价格横盘
        - 成交量放大
        - 收盘价在中下部
        """
        recent = df.tail(20)

        # 价格波动性
        price_range = (recent['high'] - recent['low']) / recent['close']
        low_volatility = price_range.mean() < 0.03

        # 成交量趋势
        volume_trend = recent['volume'].diff().tail(10).mean()
        increasing_volume = volume_trend > 0

        # 价格位置
        current_price = df['close'].iloc[-1]
        price_position = (current_price - recent['low'].iloc[-1]) / (recent['high'].iloc[-1] - recent['low'].iloc[-1])
        low_position = price_position < 0.5

        if low_volatility and increasing_volume and low_position:
            strength = (1 - price_position + 0.3) / 1.3
            return SmartMoneySignal(
                signal_type="distribution",
                strength=strength,
                reason="Smart money distribution detected",
                metadata={'price_position': price_position}
            )

        return SmartMoneySignal(
            signal_type="none",
            strength=0,
            reason="No distribution detected"
        )

    def analyze_volume_price_trend(self, df: pd.DataFrame) -> Dict:
        """
        分析价量趋势关系

        Returns:
            包含趋势分析的字典
        """
        recent = df.tail(30)

        # 价格趋势
        price_change = (recent['close'].iloc[-1] - recent['close'].iloc[0]) / recent['close'].iloc[0]

        # 成交量趋势
        volume_change = (recent['volume'].iloc[-1] - recent['volume'].iloc[0]) / recent['volume'].iloc[0]

        # 判断
        if price_change > 0.05 and volume_change > 0.2:
            trend = "strong_uptrend"
            interpretation = "Bullish: Price rising with increasing volume"
        elif price_change > 0.05 and volume_change < 0:
            trend = "weak_uptrend"
            interpretation = "Caution: Price rising but volume declining"
        elif price_change < -0.05 and volume_change > 0.2:
            trend = "strong_downtrend"
            interpretation = "Bearish: Price falling with increasing volume"
        elif price_change < -0.05 and volume_change < 0:
            trend = "weak_downtrend"
            interpretation = "Potential reversal: Price falling with decreasing volume"
        else:
            trend = "sideways"
            interpretation = "Neutral: Price in consolidation"

        return {
            'trend': trend,
            'interpretation': interpretation,
            'price_change': price_change,
            'volume_change': volume_change,
        }


class OrderBookAnalyzer:
    """
    订单簿分析器

    分析订单簿深度的变化
    """

    def __init__(self):
        pass

    def calculate_imbalance(self, bids: List[float], asks: List[float]) -> float:
        """
        计算订单簿不平衡度

        Args:
            bids: 买单价格列表
            asks: 卖单价格列表

        Returns:
            不平衡度 (-1 到 1)
            - 正值 = 买方压力
            - 负值 = 卖方压力
        """
        bid_volume = sum(bids) if bids else 0
        ask_volume = sum(asks) if asks else 0

        total = bid_volume + ask_volume

        if total == 0:
            return 0

        return (bid_volume - ask_volume) / total

    def detect_order_book_sweep(self,
                              bid_levels: List[float],
                              ask_levels: List[float],
                              threshold: float = 0.1) -> bool:
        """
        检测订单簿扫单

        Args:
            bid_levels: 买单深度
            ask_levels: 卖单深度
            threshold: 阈值

        Returns:
            是否检测到扫单
        """
        if not bid_levels or not ask_levels:
            return False

        # 计算不平衡度
        imbalance = self.calculate_imbalance(bid_levels, ask_levels)

        # 极端不平衡 = 可能的扫单
        return abs(imbalance) > threshold


class ArbitrageDetector:
    """
    套利机会检测器

    检测现货-期货套利机会
    """

    def __init__(self):
        pass

    def detect_spot_futures_arbitrage(self,
                                     spot_price: float,
                                     futures_price: float,
                                     risk_free_rate: float = 0.05,
                                     days_to_expiry: int = 7) -> Dict:
        """
        检测现货-期货套利机会

        Args:
            spot_price: 现货价格
            futures_price: 期货价格
            risk_free_rate: 无风险利率
            days_to_expiry: 到期天数

        Returns:
            套利分析结果
        """
        # 计算理论期货价格 (简化)
        days_per_year = 365
        time_value = risk_free_rate * days_to_expiry / days_per_year
        fair_futures_price = spot_price * (1 + time_value)

        # 实际价差
        price_diff = futures_price - spot_price
        fair_diff = fair_futures_price - spot_price

        # 溢价率
        premium = (price_diff / spot_price) * (days_per_year / days_to_expiry)

        # 判断套利机会
        if premium > 0.02:  # 2% 年化
            opportunity = "contango"  # 期货溢价，可以做多现货空期货
            expected_return = premium
        elif premium < -0.02:
            opportunity = "backwardation"  # 现货溢价，可以空现货多期货
            expected_return = abs(premium)
        else:
            opportunity = "none"
            expected_return = 0

        return {
            'opportunity': opportunity,
            'spot_price': spot_price,
            'futures_price': futures_price,
            'fair_futures_price': fair_futures_price,
            'premium_annualized': premium * 100,  # 转换为百分比
            'expected_return': expected_return * 100,
            'days_to_expiry': days_to_expiry,
        }

    def detect_funding_arbitrage(self,
                                funding_rate: float,
                                premium: float,
                                threshold: float = 0.005) -> Dict:
        """
        检测资金费率套利机会

        Args:
            funding_rate: 资金费率 (如 0.01% = 0.0001)
            premium: 溢价
            threshold: 阈值

        Returns:
            套利分析结果
        """
        net_rate = funding_rate - premium

        if net_rate > threshold:
            opportunity = "long_futures"  # 多期货收利息
            expected_annual = net_rate * 365
        elif net_rate < -threshold:
            opportunity = "short_futures"  # 空期货收利息
            expected_annual = abs(net_rate) * 365
        else:
            opportunity = "none"
            expected_annual = 0

        return {
            'opportunity': opportunity,
            'funding_rate': funding_rate,
            'premium': premium,
            'net_rate': net_rate,
            'expected_annual_return': expected_annual * 100,
        }


class InstitutionalActivityDetector:
    """
    机构活动检测器

    检测机构级别的操作
    """

    def __init__(self, large_trade_threshold: float = 50000):
        """
        Args:
            large_trade_threshold: 大额交易阈值 (USDT)
        """
        self.threshold = large_trade_threshold

    def detect_block_trades(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        检测大额区块交易

        基于成交量异常和价格变动
        """
        result = df.copy()

        # 计算每小时成交量
        hourly_vol = result['volume'].rolling(window=1).sum()  # 假设是小时数据

        # 计算金额
        hourly_amount = hourly_vol * result['close']

        # 标记大额交易
        result['block_trade'] = hourly_amount > self.threshold

        # 计算大额交易方向 (基于价格变动)
        result['price_change'] = result['close'].diff()
        result['block_direction'] = result.apply(
            lambda x: 'buy' if x['block_trade'] and x['price_change'] > 0
                     else ('sell' if x['block_trade'] and x['price_change'] < 0 else 'none'),
            axis=1
        )

        return result

    def calculate_whale_ratio(self, df: pd.DataFrame, window: int = 20) -> pd.Series:
        """
        计算大户比率

        大户交易量 / 总交易量
        """
        # 使用成交量标准差来估算大户交易
        vol_ma = df['volume'].rolling(window=window).mean()
        vol_std = df['volume'].rolling(window=window).std()

        # 假设超过 2 个标准差的交易为大户交易
        threshold = vol_ma + 2 * vol_std
        whale_volume = df['volume'][df['volume'] > threshold].sum()

        # 大户比率
        total_volume = df['volume'].sum()

        if total_volume == 0:
            return pd.Series(0, index=df.index)

        return whale_volume / total_volume

    def detect_hidden_liquidity(self, df: pd.DataFrame) -> SmartMoneySignal:
        """
        检测隐藏流动性

        特征：
        - 价格快速变动但成交量较低
        - 可能有隐藏大单
        """
        recent = df.tail(10)

        # 价格变动率
        price_velocity = recent['close'].diff().abs().mean()

        # 成交量
        avg_volume = recent['volume'].mean()

        # 低成交量高波动 = 可能隐藏流动性
        if avg_volume < df['volume'].rolling(20).mean().iloc[-1] * 0.5:
            if price_velocity > df['close'].rolling(20).mean().iloc[-1] * 0.01:
                return SmartMoneySignal(
                    signal_type="hidden_liquidity",
                    strength=0.7,
                    reason="Possible hidden liquidity execution",
                    metadata={'price_velocity': price_velocity}
                )

        return SmartMoneySignal(
            signal_type="none",
            strength=0,
            reason="No hidden liquidity detected"
        )


def create_smart_money_detector(threshold: float = 10000) -> SmartMoneyDetector:
    """创建智能资金检测器"""
    return SmartMoneyDetector(threshold)


def create_order_book_analyzer() -> OrderBookAnalyzer:
    """创建订单簿分析器"""
    return OrderBookAnalyzer()


def create_arbitrage_detector() -> ArbitrageDetector:
    """创建套利检测器"""
    return ArbitrageDetector()


def create_institutional_detector(threshold: float = 50000) -> InstitutionalActivityDetector:
    """创建机构活动检测器"""
    return InstitutionalActivityDetector(threshold)
