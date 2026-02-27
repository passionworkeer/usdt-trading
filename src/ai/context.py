"""
AI 分析上下文数据结构

定义传递给 AI 的完整市场数据格式。
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Any, Optional

import pandas as pd


@dataclass
class IndicatorSet:
    """技术指标集合"""
    # 趋势指标
    ema_9: Optional[float] = None
    ema_21: Optional[float] = None
    ema_50: Optional[float] = None
    ema_200: Optional[float] = None
    sma_20: Optional[float] = None
    vwap: Optional[float] = None

    # 动量指标
    rsi_14: Optional[float] = None
    macd: Optional[float] = None
    macd_signal: Optional[float] = None
    macd_histogram: Optional[float] = None
    stochastic_k: Optional[float] = None
    stochastic_d: Optional[float] = None

    # 波动指标
    atr_14: Optional[float] = None
    bb_upper: Optional[float] = None
    bb_lower: Optional[float] = None
    bb_middle: Optional[float] = None
    bb_position: Optional[float] = None  # 布林带位置 (0-1)

    # 成交量指标
    obv: Optional[float] = None
    volume_ratio: Optional[float] = None  # 当前成交量 / 平均成交量

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            'ema_9': self.ema_9,
            'ema_21': self.ema_21,
            'ema_50': self.ema_50,
            'ema_200': self.ema_200,
            'sma_20': self.sma_20,
            'vwap': self.vwap,
            'rsi_14': self.rsi_14,
            'macd': self.macd,
            'macd_signal': self.macd_signal,
            'macd_histogram': self.macd_histogram,
            'stochastic_k': self.stochastic_k,
            'stochastic_d': self.stochastic_d,
            'atr_14': self.atr_14,
            'bb_upper': self.bb_upper,
            'bb_lower': self.bb_lower,
            'bb_middle': self.bb_middle,
            'bb_position': self.bb_position,
            'obv': self.obv,
            'volume_ratio': self.volume_ratio,
        }

    def to_prompt_format(self, interval: str = "") -> str:
        """转换为提示词格式"""
        lines = []

        # 趋势指标
        if self.ema_9:
            lines.append(f"EMA9: ${self.ema_9:.2f}")
        if self.ema_21:
            lines.append(f"EMA21: ${self.ema_21:.2f}")
        if self.ema_50:
            lines.append(f"EMA50: ${self.ema_50:.2f}")
        if self.ema_200:
            lines.append(f"EMA200: ${self.ema_200:.2f}")
        if self.vwap:
            lines.append(f"VWAP: ${self.vwap:.2f}")

        # 动量指标
        if self.rsi_14:
            rsi_status = "超卖" if self.rsi_14 < 30 else "超买" if self.rsi_14 > 70 else "中性"
            lines.append(f"RSI(14): {self.rsi_14:.1f} ({rsi_status})")

        if self.macd_histogram is not None:
            cross = "金叉" if self.macd_histogram > 0 else "死叉"
            lines.append(f"MACD: {cross} (histogram: {self.macd_histogram:+.4f})")

        # 波动指标
        if self.atr_14:
            lines.append(f"ATR: ${self.atr_14:.2f}")
        if self.bb_upper and self.bb_lower:
            lines.append(f"布林带: ${self.bb_lower:.2f}-${self.bb_upper:.2f}")
        if self.bb_position is not None:
            lines.append(f"布林带位置: {self.bb_position * 100:.1f}%")

        # 成交量指标
        if self.volume_ratio:
            vol_status = "放量" if self.volume_ratio > 1.5 else "缩量" if self.volume_ratio < 0.5 else "正常"
            lines.append(f"成交量倍数: {self.volume_ratio:.2f}x ({vol_status})")

        prefix = f"### {interval} 周期\n" if interval else ""
        return prefix + "\n".join(f"- {line}" for line in lines) if lines else (prefix + "无数据")


@dataclass
class CandlestickPattern:
    """K线形态"""
    name: str  # 形态名称
    interval: str  # 时间周期
    confidence: float  # 置信度 (0-1)
    direction: str  # "bullish", "bearish", "neutral"
    description: str = ""  # 描述

    def to_prompt_format(self) -> str:
        direction_text = {"bullish": "看涨", "bearish": "看跌", "neutral": "中性"}.get(self.direction, "中性")
        return f"- {self.interval}: {self.name} (置信度 {self.confidence * 100:.0f}%, {direction_text})"


@dataclass
class MacroMarketData:
    """宏观市场数据"""
    # 资金费率
    funding_rate: Optional[float] = None
    next_funding_time: Optional[datetime] = None

    # Open Interest
    oi_current: Optional[float] = None
    oi_change_1h: Optional[float] = None  # 1小时变化率
    oi_change_4h: Optional[float] = None  # 4小时变化率

    # 价格数据
    mark_price: Optional[float] = None
    index_price: Optional[float] = None
    price_diff_pct: Optional[float] = None  # 标记价格 vs 指数价格 差异

    # 成交量
    volume_24h: Optional[float] = None
    quote_volume_24h: Optional[float] = None

    # 多空比
    long_short_ratio: Optional[float] = None
    long_ratio: Optional[float] = None
    short_ratio: Optional[float] = None

    def to_prompt_format(self) -> str:
        lines = []

        # 资金费率
        if self.funding_rate is not None:
            lines.append(f"资金费率: {self.funding_rate:+.4%}")
            if self.next_funding_time:
                time_str = self.next_funding_time.strftime("%H:%M")
                lines[0] += f" (下次 {time_str})"

        # OI 变化
        if self.oi_current:
            lines.append(f"OI: {self.oi_current:,.0f}")
        if self.oi_change_1h is not None:
            sign = "+" if self.oi_change_1h > 0 else ""
            lines.append(f"OI变化: {sign}{self.oi_change_1h:.1f}% (1h)")
        if self.oi_change_4h is not None:
            sign = "+" if self.oi_change_4h > 0 else ""
            if "(1h)" in lines[-1]:
                lines[-1] += f", {sign}{self.oi_change_4h:.1f}% (4h)"
            else:
                lines.append(f"OI变化: {sign}{self.oi_change_4h:.1f}% (4h)")

        # 价格差异
        if self.price_diff_pct is not None:
            sign = "+" if self.price_diff_pct > 0 else ""
            lines.append(f"价格差异: {sign}{self.price_diff_pct:.2f}% (标记 vs 指数)")

        # 多空比
        if self.long_short_ratio:
            lines.append(f"多空比: {self.long_short_ratio:.2f}")
        if self.long_ratio:
            lines.append(f"多头: {self.long_ratio * 100:.1f}%")
        if self.short_ratio:
            lines.append(f"空头: {self.short_ratio * 100:.1f}%")

        return "\n".join(f"- {line}" for line in lines) if lines else "- 无数据"


@dataclass
class KLineData:
    """K线数据"""
    interval: str  # 时间周期: 15m, 1h, 4h, 1d
    df: pd.DataFrame  # K线数据 DataFrame

    @property
    def current_price(self) -> float:
        """当前价格"""
        return float(self.df.iloc[-1]['close'])

    @property
    def prices(self) -> List[float]:
        """价格列表"""
        return self.df['close'].tolist()

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'interval': self.interval,
            'current_price': self.current_price,
            'prices': self.prices[-20:],  # 只保留最近20个
        }


@dataclass
class AIAnalysisContext:
    """
    AI 分析上下文 - 完整的增强市场数据

    这是传给 AI 进行分析的数据结构，包含：
    - 多时间框架 K 线数据
    - 预计算的技术指标
    - K 线形态识别结果
    - 宏观市场数据
    """
    symbol: str
    timestamp: datetime

    # 多时间框架 K 线
    klines: Dict[str, KLineData] = field(default_factory=dict)

    # 技术指标 (按周期)
    indicators: Dict[str, IndicatorSet] = field(default_factory=dict)

    # K 线形态 (按周期)
    patterns: Dict[str, List[CandlestickPattern]] = field(default_factory=dict)

    # 宏观数据
    macro_data: Optional[MacroMarketData] = None

    def to_prompt_data(self) -> str:
        """转换为提示词格式"""
        lines = []

        # 标题
        lines.append(f"## 市场数据")
        lines.append(f"- 交易对: {self.symbol}")
        lines.append(f"- 当前时间: {self.timestamp.strftime('%Y-%m-%d %H:%M:%S')}")

        # 多时间框架分析
        lines.append("")
        lines.append("## 多时间框架分析")

        # 15分钟 (精准入场)
        if '15m' in self.klines:
            kline_15m = self.klines['15m']
            ind_15m = self.indicators.get('15m', IndicatorSet())
            lines.append(f"### 15分钟周期（精准入场）")
            lines.append(f"- 价格: ${kline_15m.current_price:,.2f}")
            lines.append(ind_15m.to_prompt_format())

        # 4小时 (中期趋势)
        if '4h' in self.klines:
            kline_4h = self.klines['4h']
            ind_4h = self.indicators.get('4h', IndicatorSet())
            lines.append(f"### 4小时周期（中期趋势）")

            # 趋势判断
            trend = "多头"
            if ind_4h.ema_50 and ind_4h.ema_200:
                if ind_4h.ema_50 < ind_4h.ema_200:
                    trend = "空头"
            lines.append(f"- EMA50: ${ind_4h.ema_50:,.2f} (趋势: {trend})")

            if ind_4h.rsi_14:
                lines.append(f"- RSI: {ind_4h.rsi_14:.1f}")

        # 1天 (长期趋势)
        if '1d' in self.klines:
            ind_1d = self.indicators.get('1d', IndicatorSet())
            lines.append(f"### 1天周期（长期趋势）")

            trend = "多头"
            if ind_1d.ema_50 and ind_1d.ema_200:
                if ind_1d.ema_50 < ind_1d.ema_200:
                    trend = "空头"
            elif ind_1d.ema_200:
                lines.append(f"- EMA200: ${ind_1d.ema_200:,.2f}")
            lines.append(f"- 趋势: {trend}")

        # 技术指标汇总
        lines.append("")
        lines.append("## 技术指标汇总")

        # 找一个有数据的周期显示汇总
        main_ind = None
        for interval in ['15m', '1h', '4h']:
            if interval in self.indicators:
                main_ind = self.indicators[interval]
                break

        if main_ind:
            if main_ind.rsi_14:
                status = "超卖" if main_ind.rsi_14 < 30 else "超买" if main_ind.rsi_14 > 70 else "中性"
                lines.append(f"- RSI(14): {main_ind.rsi_14:.1f} ({status})")
            if main_ind.macd_histogram is not None:
                cross = "金叉" if main_ind.macd_histogram > 0 else "死叉"
                lines.append(f"- MACD: {cross} (histogram: {main_ind.macd_histogram:+.4f})")
            if main_ind.atr_14 and main_ind.bb_upper and main_ind.bb_lower:
                lines.append(f"- ATR: ${main_ind.atr_14:.2f}, 布林带: ${main_ind.bb_lower:,.0f}-${main_ind.bb_upper:,.0f}")

        # K线形态
        lines.append("")
        lines.append("## K线形态")
        all_patterns = []
        for interval, patterns in self.patterns.items():
            all_patterns.extend(patterns)

        if all_patterns:
            for pattern in all_patterns:
                lines.append(pattern.to_prompt_format())
        else:
            lines.append("- 未识别到明显形态")

        # 宏观数据
        lines.append("")
        lines.append("## 宏观数据")
        if self.macro_data:
            lines.append(self.macro_data.to_prompt_format())
        else:
            lines.append("- 无宏观数据")

        return "\n".join(lines)
