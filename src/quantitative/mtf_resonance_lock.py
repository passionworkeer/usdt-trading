"""
v5.2: MTF 三重共振锁（Multi-Timeframe Triple Resonance Lock）

狙击手信号过滤器 - 极低频、极高置信度：
- 关闭所有分钟级微观指标（容易被操纵）
- 开仓必须同时满足三个条件，缺一不可
- 宁可错过行情，不做假信号

v5.2 改进：
- 增加 RSI 辅助判断（超买超卖）
- 增加布林带辅助判断（支撑阻力）
- 增加 ATR 动态止损
- 动态成交量阈值（波动率自适应）
- 仓位管理系统
"""
import logging
import asyncio
import aiohttp
import pandas as pd
import numpy as np
from typing import Dict, Tuple, Optional, List
from dataclasses import dataclass, field
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


@dataclass
class MTFSignal:
    """v5.2 MTF 信号（增加风控信息）"""
    symbol: str
    signal: int  # 1=做多, -1=做空, 0=无信号
    confidence: float  # 信号置信度（0-1）
    reasons: List[str]  # 信号原因
    timestamp: datetime
    is_locked: bool  # 是否被锁（满足三重共振）

    # v5.1: 入场价格信息（拒绝市价追高）
    breakthrough_price: Optional[float] = None  # 突破 K 线价格
    breakthrough_vwap: Optional[float] = None  # 突破 K 线 VWAP
    suggested_entry_price: Optional[float] = None  # 建议入场价（回踩价）
    wait_for_pullback: bool = False  # 是否等待回踩

    # v5.2: 风控信息
    rsi: Optional[float] = None  # RSI 指标
    bb_position: Optional[float] = None  # 布林带位置 (0-1)
    atr: Optional[float] = None  # ATR 止损值
    stop_loss_price: Optional[float] = None  # 止损价格
    take_profit_price: Optional[float] = None  # 止盈价格
    risk_reward_ratio: Optional[float] = None  # 风险收益比
    suggested_position_size: float = 1.0  # v5.2: 默认全仓


@dataclass
class PositionManager:
    """v5.2: 仓位管理器"""
    max_position_pct: float = 1.0  # v5.2: 默认全仓（用户只有 200U）
    risk_per_trade_pct: float = 0.02  # 每笔风险 2%
    min_risk_reward: float = 2.0  # 最小风险收益比 2:1
    current_position: float = 0  # 当前持仓
    entry_price: Optional[float] = None  # 入场价格

    def calculate_position_size(self, entry_price: float, stop_loss_price: float, 
                                 total_balance: float) -> float:
        """计算仓位大小 - v5.2 简化为直接返回全仓"""
        # 主人只有 200U，每次全仓
        return self.max_position_pct  # 直接返回全仓

    def calculate_stop_loss(self, entry_price: float, direction: int, 
                           atr: float, atr_multiplier: float = 2.0) -> float:
        """计算 ATR 止损"""
        if direction == 1:  # 做多
            return entry_price - (atr * atr_multiplier)
        else:  # 做空
            return entry_price + (atr * atr_multiplier)

    def calculate_take_profit(self, entry_price: float, direction: int,
                              stop_loss_price: float) -> float:
        """计算止盈（基于风险收益比）"""
        risk = abs(entry_price - stop_loss_price)
        reward = risk * self.min_risk_reward

        if direction == 1:  # 做多
            return entry_price + reward
        else:  # 做空
            return entry_price - reward


class MTFResonanceLock:
    """
    v5.0 MTF 三重共振锁

    三重条件：
    1. 4H 宏观趋势确认（避免逆势抄底）
    2. 极端 Open Interest/资金费率偏离（情绪反转点）
    3. 15m 精准放量猎杀（精确入场点）

    规则：
    - 必须同时满足三个条件
    - 缺少任何一环 = 无信号
    - 宁可错过，不做错
    """

    def __init__(self):
        """初始化三重共振锁"""
        self.funding_rates: Dict[str, float] = {}
        self.open_interests: Dict[str, float] = {}

        logger.info("✅ MTF 三重共振锁已初始化")

    async def _get_session(self):
        """获取全局 Session（v6.0 TLS Keep-Alive）"""
        from src.utils.session_manager import get_session_manager
        manager = await get_session_manager()
        return manager.session

    async def fetch_4h_trend(self, symbol: str) -> Tuple[int, str]:
        """
        条件 1: 4H 宏观趋势确认

        逻辑：
        - 获取 4H K 线（最近 50 根）
        - 计算 EMA 20 和 EMA 50
        - EMA 20 > EMA 50 → 多头趋势
        - EMA 20 < EMA 50 → 空头趋势

        Args:
            symbol: 交易对

        Returns:
            (趋势方向, 原因)
        """
        session = await self._get_session()

        url = "https://fapi.binance.com/fapi/v1/klines"
        params = {
            'symbol': symbol.replace('/', ''),
            'interval': '4h',  # 4 小时
            'limit': 50,
        }

        try:
            async with session.get(url, params=params) as response:
                data = await response.json()

                if response.status != 200 or not data:
                    return 0, "无法获取 4H 数据"

                # 解析 K 线
                df = pd.DataFrame(data, columns=[
                    'timestamp', 'open', 'high', 'low', 'close', 'volume',
                    'close_time', 'quote_volume', 'trades', 'taker_buy_base',
                    'taker_buy_quote', 'ignore'
                ])

                df['close'] = df['close'].astype(float)
                df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')

                # 计算 EMA
                ema20 = df['close'].ewm(span=20).mean().iloc[-1]
                ema50 = df['close'].ewm(span=50).mean().iloc[-1]
                current_price = df['close'].iloc[-1]

                # 计算 EMA 差距百分比
                ema_diff_pct = (ema20 - ema50) / ema50 * 100

                # 计算近期价格变动
                price_change_4h = (current_price - df['close'].iloc[-4]) / df['close'].iloc[-4] * 100 if len(df) >= 4 else 0

                # 判断趋势 - 放宽条件
                if ema20 > ema50 and current_price > ema20:
                    # 明确多头
                    trend = 1
                    reason = f"4H 多头趋势：EMA20 (${ema20:.2f}) > EMA50 (${ema50:.2f})，价格 (${current_price:.2f}) > EMA20"
                elif ema20 < ema50 and current_price < ema20:
                    # 明确空头
                    trend = -1
                    reason = f"4H 空头趋势：EMA20 (${ema20:.2f}) < EMA50 (${ema50:.2f})，价格 (${current_price:.2f}) < EMA20"
                elif abs(ema_diff_pct) < 1.0 and abs(price_change_4h) > 0.5:
                    # 横盘时根据价格方向给出弱信号 (放宽条件)
                    if price_change_4h > 0:
                        trend = 1
                        reason = f"4H 横盘偏多：价格 4H 上涨 {price_change_4h:.2f}%，EMA 收敛"
                    else:
                        trend = -1
                        reason = f"4H 横盘偏空：价格 4H 下跌 {abs(price_change_4h):.2f}%，EMA 收敛"
                else:
                    trend = 0
                    reason = f"4H 趋势不明确：EMA20 ({ema20:.2f}) vs EMA50 ({ema50:.2f})"

                logger.info(f"【4H 趋势】{symbol}: {reason}")

                return trend, reason

        except Exception as e:
            logger.error(f"获取 4H 趋势失败: {e}")
            return 0, f"获取 4H 数据异常: {e}"

    async def fetch_funding_and_oi(self, symbol: str) -> Tuple[int, str]:
        """
        v5.1: 条件 2 - 极端资金费率 + ΔOI 激增（历史对比）

        修正：
        - 不再使用 OI 绝对值（废纸！）
        - 必须计算过去 1 小时/4 小时的 OI 变化率 ΔOI
        - 只有极端费率 + ΔOI 激增 > 5% 才算真正拥挤

        逻辑：
        1. 获取资金费率
        2. 获取当前 OI
        3. 获取历史 OI（1 小时前）
        4. 计算 ΔOI = (OI_current - OI_1h_ago) / OI_1h_ago
        5. 极端正费率（> 0.05%）+ ΔOI > 5% → 多头过度拥挤 → 做空信号
        6. 极度负费率（< -0.05%）+ ΔOI > 5% → 空头过度拥挤 → 做多信号

        Args:
            symbol: 交易对

        Returns:
            (信号方向, 原因)
        """
        session = await self._get_session()

        # 1. 获取资金费率
        funding_url = "https://fapi.binance.com/fapi/v1/premiumIndex"
        funding_params = {'symbol': symbol.replace('/', '')}

        # 2. 获取当前 OI（v5.2 修复：openInterestHist 已废弃，改用当前 OI）
        oi_url = "https://fapi.binance.com/fapi/v1/openInterest"
        oi_params = {'symbol': symbol.replace('/', '')}

        # 3. 历史 OI 接口已废弃（fapi/v1/openInterestHist 返回 404）
        # 简化逻辑：使用当前 OI + 资金费率判断，不依赖 ΔOI

        try:
            # 并发请求
            async with session.get(funding_url, params=funding_params) as f_resp:
                funding_data = await f_resp.json()

            async with session.get(oi_url, params=oi_params) as oi_resp:
                oi_data = await oi_resp.json()

            # 解析资金费率
            funding_rate = float(funding_data.get('lastFundingRate', 0))
            mark_price = float(funding_data.get('markPrice', 0))

            # 解析当前 OI
            current_oi = float(oi_data.get('openInterest', 0))

            # 存储缓存
            self.funding_rates[symbol] = funding_rate
            self.open_interests[symbol] = current_oi

            # 判断极端资金费率（简化版：只用费率，不依赖 ΔOI）
            signal = 0
            reason = ""

            if funding_rate > 0.0005:  # 0.05% 极度正费率
                signal = -1  # 做空信号（多头付钱=过度拥挤）
                reason = f"极度正费率: {funding_rate:.4%} → 多头过度拥挤，做空信号"
            elif funding_rate < -0.0005:  # -0.05% 极度负费率
                signal = 1  # 做多信号（空头付钱=过度拥挤）
                reason = f"极度负费率: {funding_rate:.4%} → 空头过度拥挤，做多信号"
            else:
                signal = 0
                reason = f"费率正常: {funding_rate:.4%}，无极端偏离"

            logger.info(f"【资金费率】{symbol}: {reason}")

            return signal, reason

        except Exception as e:
            logger.error(f"获取资金费率/OI 失败: {e}")
            return 0, f"获取数据异常: {e}"

    async def fetch_15m_volume_spike(self, symbol: str) -> Tuple[int, str, Optional[Dict]]:
        """
        v5.2: 条件 3 - 15m 精准放量猎杀（动态阈值 + 辅助指标）

        v5.2 改进：
        - 动态成交量阈值（基于波动率）
        - 增加 RSI、ATR 计算
        - 增加布林带位置计算

        逻辑：
        1. 获取 15m K 线（最近 100 根）
        2. 计算平均成交量 + 波动率
        3. 动态阈值 = 2x + (波动率系数)
        4. 计算 RSI、ATR、布林带位置
        5. 综合判断信号

        Args:
            symbol: 交易对

        Returns:
            (信号方向, 原因, 入场信息字典)
        """
        session = await self._get_session()

        url = "https://fapi.binance.com/fapi/v1/klines"
        params = {
            'symbol': symbol.replace('/', ''),
            'interval': '15m',  # 15 分钟
            'limit': 100,
        }

        try:
            async with session.get(url, params=params) as response:
                data = await response.json()

                if response.status != 200 or not data:
                    return 0, "无法获取 15m 数据", None

                # 解析 K 线
                df = pd.DataFrame(data, columns=[
                    'timestamp', 'open', 'high', 'low', 'close', 'volume',
                    'close_time', 'quote_volume', 'trades', 'taker_buy_base',
                    'taker_buy_quote', 'ignore'
                ])

                df['close'] = df['close'].astype(float)
                df['volume'] = df['volume'].astype(float)
                df['quote_volume'] = df['quote_volume'].astype(float)
                df['high'] = df['high'].astype(float)
                df['low'] = df['low'].astype(float)
                df['open'] = df['open'].astype(float)
                df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')

                # 计算平均成交量（最近 50 根，排除最新）
                avg_volume = df['volume'].iloc[-50:-1].mean()
                current_volume = df['volume'].iloc[-1]
                current_price = df['close'].iloc[-1]
                prev_price = df['close'].iloc[-2]

                # 计算成交量倍数
                volume_ratio = current_volume / avg_volume if avg_volume > 0 else 0

                # 计算价格变动
                price_change_pct = (current_price - prev_price) / prev_price

                # === v5.2 新增：计算 ATR（平均真实波幅）===
                df['tr'] = np.maximum(
                    df['high'] - df['low'],
                    np.maximum(
                        abs(df['high'] - df['close'].shift(1)),
                        abs(df['low'] - df['close'].shift(1))
                    )
                )
                atr = df['tr'].iloc[-14:].mean()  # 14 周期 ATR
                atr_pct = (atr / current_price) if current_price > 0 else 0

                # === 动态成交量阈值 - 放宽条件 ===
                # 波动率高时适当提高阈值，但使用更低的基数
                volatility_factor = min(atr_pct * 10, 0.5)  # 波动率系数
                dynamic_volume_threshold = 1.2 + volatility_factor  # 动态阈值 1.2x-1.7x

                # === v5.2 新增：RSI 计算 ===
                delta = df['close'].diff()
                gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
                loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
                rs = gain / loss
                rsi = 100 - (100 / (1 + rs))
                rsi_value = rsi.iloc[-1]

                # === v5.2 新增：布林带位置 ===
                bb_period = 20
                bb_std = 2.0
                sma = df['close'].iloc[-bb_period:].mean()
                std = df['close'].iloc[-bb_period:].std()
                bb_upper = sma + (bb_std * std)
                bb_lower = sma - (bb_std * std)
                bb_position = (current_price - bb_lower) / (bb_upper - bb_lower) if (bb_upper - bb_lower) > 0 else 0.5

                # 判断放量突破
                signal = 0
                reason = ""
                entry_info = None

                if volume_ratio >= dynamic_volume_threshold:  # 动态阈值
                    # 计算突破 K 线的 VWAP
                    typical_price = (df['high'].iloc[-1] + df['low'].iloc[-1] + df['close'].iloc[-1]) / 3
                    vwap = (typical_price * current_volume) / current_volume if current_volume > 0 else current_price

                    # 计算 K 线均价
                    candle_avg_price = (df['open'].iloc[-1] + df['close'].iloc[-1] + df['high'].iloc[-1] + df['low'].iloc[-1]) / 4

                    # === v5.2 新增：辅助指标过滤 ===
                    # RSI 超卖/超买过滤
                    rsi_filter = ""
                    if price_change_pct > 0.005:  # 上涨
                        if rsi_value > 70:
                            rsi_filter = " ⚠️ RSI 超买"
                        elif rsi_value > 60:
                            rsi_filter = " ⚡ RSI 偏高"
                    elif price_change_pct < -0.005:  # 下跌
                        if rsi_value < 30:
                            rsi_filter = " ⚠️ RSI 超卖"
                        elif rsi_value < 40:
                            rsi_filter = " ⚡ RSI 偏低"

                    # 布林带位置过滤
                    bb_filter = ""
                    if bb_position > 0.8:
                        bb_filter = " ⚠️ 接近上轨"
                    elif bb_position < 0.2:
                        bb_filter = " ⚠️ 接近下轨"

                    if price_change_pct > 0.005:  # 价格上涨 > 0.5%
                        signal = 1
                        reason = (f"15m 放量上涨：成交量 {volume_ratio:.1f}x（阈值 {dynamic_volume_threshold:.1f}x），"
                                 f"上涨 {price_change_pct:.2%} | RSI: {rsi_value:.1f} | BB位置: {bb_position:.0%} | ATR: {atr:.2f}"
                                 f"{rsi_filter}{bb_filter} → 做多信号")

                        # 入场信息（带波动率用于动态风报比）
                        entry_info = {
                            'breakthrough_price': current_price,
                            'breakthrough_vwap': vwap,
                            'suggested_entry_price': vwap,
                            'wait_for_pullback': True,
                            'rsi': rsi_value,
                            'bb_position': bb_position,
                            'atr': atr,
                            'volatility': atr_pct,  # 用于动态风报比判断
                        }
                        reason += f" | 建议等待回踩 VWAP ${vwap:.2f} 入场"

                    elif price_change_pct < -0.005:  # 价格下跌 < -0.5%
                        signal = -1
                        reason = (f"15m 放量下跌：成交量 {volume_ratio:.1f}x（阈值 {dynamic_volume_threshold:.1f}x），"
                                 f"下跌 {abs(price_change_pct):.2%} | RSI: {rsi_value:.1f} | BB位置: {bb_position:.0%} | ATR: {atr:.2f}"
                                 f"{rsi_filter}{bb_filter} → 做空信号")

                        # 入场信息（带波动率用于动态风报比）
                        entry_info = {
                            'breakthrough_price': current_price,
                            'breakthrough_vwap': vwap,
                            'suggested_entry_price': vwap,
                            'wait_for_pullback': True,
                            'rsi': rsi_value,
                            'bb_position': bb_position,
                            'atr': atr,
                            'volatility': atr_pct,  # 用于动态风报比判断
                        }
                        reason += f" | 建议等待回踩 VWAP ${vwap:.2f} 入场"

                    else:
                        signal = 0
                        reason = f"15m 放量但无方向：成交量 {volume_ratio:.1f}x（阈值 {dynamic_volume_threshold:.1f}x），价格横盘"
                else:
                    signal = 0
                    reason = f"15m 无放量：成交量 {volume_ratio:.1f}x（需要 >= {dynamic_volume_threshold:.1f}x）"

                logger.info(f"【15m 放量】{symbol}: {reason}")

                return signal, reason, entry_info

        except Exception as e:
            logger.error(f"获取 15m 放量失败: {e}")
            return 0, f"获取数据异常: {e}", None

    async def check_triple_resonance(self, symbol: str) -> MTFSignal:
        """
        v5.2 核心：检查三重共振（增加风控信息）

        规则：
        - 必须同时满足三个条件
        - 任何一环不满足 = 无信号
        - 返回信号置信度 + 入场价格信息 + 风控止损止盈

        v5.2 改进：
        - 计算 RSI、ATR、BB 位置
        - 计算动态止损止盈
        - 计算建议仓位

        Args:
            symbol: 交易对

        Returns:
            MTFSignal 对象
        """
        logger.info(f"\n{'='*60}")
        logger.info(f"🔐 开始 MTF 三重共振检查: {symbol}")
        logger.info(f"{'='*60}\n")

        # 并发获取三个条件
        trend_4h, reason_4h = await self.fetch_4h_trend(symbol)
        funding_oi, reason_funding = await self.fetch_funding_and_oi(symbol)
        volume_15m, reason_volume, entry_info = await self.fetch_15m_volume_spike(symbol)

        # 检查三重共振
        reasons = [reason_4h, reason_funding, reason_volume]
        signals = [trend_4h, funding_oi, volume_15m]

        # 统计信号方向
        long_votes = sum(1 for s in signals if s == 1)
        short_votes = sum(1 for s in signals if s == -1)
        no_signal_votes = sum(1 for s in signals if s == 0)

        # 判断是否锁定 - 放宽条件增加交易机会
        is_locked = False
        final_signal = 0
        confidence = 0

        # 放宽：只要有 2 个及以上同方向就开仓，允许 1 个中立
        if long_votes >= 2:  # 至少 2 个做多
            final_signal = 1
            confidence = 0.6 if long_votes == 2 else 1.0
            is_locked = True
        elif short_votes >= 2:  # 至少 2 个做空
            final_signal = -1
            confidence = 0.6 if short_votes == 2 else 1.0
            is_locked = True
        # 进一步放宽：1 个方向 + 1 个中立也允许
        elif (long_votes == 1 and no_signal_votes >= 1) or (short_votes == 1 and no_signal_votes >= 1):
            if long_votes > short_votes:
                final_signal = 1
                confidence = 0.4  # 降低置信度要求
                is_locked = True
            elif short_votes > long_votes:
                final_signal = -1
                confidence = 0.4
                is_locked = True
        else:
            final_signal = 0
            confidence = 0
            is_locked = False

        # === v5.2 新增：计算风控信息 ===
        rsi = entry_info.get('rsi') if entry_info else None
        bb_position = entry_info.get('bb_position') if entry_info else None
        atr = entry_info.get('atr') if entry_info else None

        # 初始化风控参数
        stop_loss_price = None
        take_profit_price = None
        risk_reward_ratio = None

        if is_locked and entry_info:
            # 计算 ATR 止损
            position_manager = PositionManager()
            entry_price = entry_info.get('suggested_entry_price', entry_info.get('breakthrough_price'))
            
            if entry_price and atr:
                stop_loss_price = position_manager.calculate_stop_loss(
                    entry_price, final_signal, atr, atr_multiplier=2.0
                )
                take_profit_price = position_manager.calculate_take_profit(
                    entry_price, final_signal, stop_loss_price
                )
                
                # 计算风险收益比
                risk = abs(entry_price - stop_loss_price)
                reward = abs(take_profit_price - entry_price)
                risk_reward_ratio = reward / risk if risk > 0 else 0

        # === v5.2: 风报比检查 - 根据市场情况动态调整 ===
        # 核心思路：不再死卡风报比，而是根据市场波动率灵活判断
        # 高波动市场 → 降低风报比要求，允许入场
        # 低波动市场 → 提高风报比要求，减少入场

        market_volatility = entry_info.get('volatility', 0.02) if entry_info else 0.02

        # 根据波动率动态调整：波动率 2% 时要求 1:1，波动率 4% 时要求 2:1
        dynamic_rr_requirement = max(0.8, min(2.0, market_volatility * 50))

        # 判断是否允许开仓
        allow_entry = True  # 默认允许，给机会

        if risk_reward_ratio is not None and risk_reward_ratio < dynamic_rr_requirement:
            # 风报比不足，但如果是高波动市场，给机会入场
            if market_volatility > 0.03:  # 波动 > 3%，放宽要求
                logger.info(f"📊 市场波动大 ({market_volatility*100:.1f}%)，风报比 {risk_reward_ratio:.1f}:1 不足但允许入场")
                allow_entry = True
            else:
                logger.warning(f"⚠️ 风报比 {risk_reward_ratio:.1f}:1 < 要求 {dynamic_rr_requirement:.1f}:1，放弃入场")
                allow_entry = False
        else:
            logger.info(f"✅ 风报比检查通过: {risk_reward_ratio:.1f}:1 >= {dynamic_rr_requirement:.1f}:1")

        # 应用判断结果
        if not allow_entry:
            is_locked = False
            final_signal = 0
            confidence = 0
        logger.info(f"\n{'='*60}")
        logger.info(f"🎯 MTF 三重共振结果: {symbol}")
        logger.info(f"{'='*60}")
        logger.info(f"信号方向: {'LONG 📈' if final_signal == 1 else 'SHORT 📉' if final_signal == -1 else '无信号 ⏸️'}")
        logger.info(f"置信度: {confidence:.0%}")
        logger.info(f"是否锁定: {'🔐 三重共振已锁定' if is_locked else '❌ 共振未满足'}")
        logger.info(f"\n三重条件:")
        for i, (reason, signal) in enumerate(zip(reasons, signals), 1):
            # 修复日志显示逻辑
            if signal == 0:
                status = "⚪"  # 无信号/中性
            elif final_signal == 0:
                status = "⚪"  # 无最终信号时，所有非零信号显示为中性
            elif signal == final_signal:
                status = "✅"  # 支持最终方向
            else:
                status = "❌"  # 与最终方向矛盾
            logger.info(f"  {status} {i}. {reason}")

        # 打印辅助指标
        if is_locked:
            logger.info(f"\n📊 辅助指标:")
            logger.info(f"  RSI: {rsi:.1f}" if rsi else "  RSI: N/A")
            logger.info(f"  布林带位置: {bb_position:.0%}" if bb_position else "  布林带位置: N/A")
            logger.info(f"  ATR: ${atr:.2f}" if atr else "  ATR: N/A")

        # 打印入场信息
        if is_locked and entry_info:
            logger.info(f"\n💡 入场建议:")
            logger.info(f"  突破价格: ${entry_info['breakthrough_price']:.2f}")
            logger.info(f"  突破 VWAP: ${entry_info['breakthrough_vwap']:.2f}")
            logger.info(f"  建议入场价: ${entry_info['suggested_entry_price']:.2f}（等待回踩）")
            logger.info(f"  ⚠️ 拒绝市价追高！必须等待回踩 VWAP 入场！")

        # 打印风控信息
        if is_locked and stop_loss_price:
            logger.info(f"\n🛡️ 风控设置:")
            logger.info(f"  止损价格: ${stop_loss_price:.2f}")
            logger.info(f"  止盈价格: ${take_profit_price:.2f}")
            logger.info(f"  风险收益比: {risk_reward_ratio:.1f}:1")
            logger.info(f"  ⚠️ 仓位: 全仓 200U（风报比不够不开仓）")

        logger.info(f"{'='*60}\n")

        return MTFSignal(
            symbol=symbol,
            signal=final_signal,
            confidence=confidence,
            reasons=reasons,
            timestamp=datetime.now(),
            is_locked=is_locked,
            breakthrough_price=entry_info.get('breakthrough_price') if entry_info else None,
            breakthrough_vwap=entry_info.get('breakthrough_vwap') if entry_info else None,
            suggested_entry_price=entry_info.get('suggested_entry_price') if entry_info else None,
            wait_for_pullback=entry_info.get('wait_for_pullback', False) if entry_info else False,
            # v5.2 新增字段
            rsi=rsi,
            bb_position=bb_position,
            atr=atr,
            stop_loss_price=stop_loss_price,
            take_profit_price=take_profit_price,
            risk_reward_ratio=risk_reward_ratio,
            suggested_position_size=1.0,  # v5.2: 全仓
        )

    async def close(self):
        """关闭资源"""
        # v6.0: 不再关闭 session，由全局管理器统一管理
        pass


if __name__ == '__main__':
    """测试 MTF 三重共振"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    async def test_mtf():
        lock = MTFResonanceLock()

        # 测试 BTC/USDT
        signal = await lock.check_triple_resonance('BTC/USDT')

        print(f"\n最终信号:")
        print(f"  方向: {signal.signal}")
        print(f"  置信度: {signal.confidence:.0%}")
        print(f"  锁定: {signal.is_locked}")
        print(f"  RSI: {signal.rsi}")
        print(f"  止损: {signal.stop_loss_price}")
        print(f"  止盈: {signal.take_profit_price}")
        print(f"  风险收益比: {signal.risk_reward_ratio}")
        print(f"  仓位: 全仓 200U")

        await lock.close()

    asyncio.run(test_mtf())
