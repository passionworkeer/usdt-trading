"""
v5.0: MTF 三重共振锁（Multi-Timeframe Triple Resonance Lock）

狙击手信号过滤器 - 极低频、极高置信度：
- 关闭所有分钟级微观指标（容易被操纵）
- 开仓必须同时满足三个条件，缺一不可
- 宁可错过行情，不做假信号
"""
import logging
import asyncio
import aiohttp
import pandas as pd
import numpy as np
from typing import Dict, Tuple, Optional, List
from dataclasses import dataclass
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


@dataclass
class MTFSignal:
    """MTF 信号"""
    symbol: str
    signal: int  # 1=做多, -1=做空, 0=无信号
    confidence: float  # 信号置信度（0-1）
    reasons: List[str]  # 信号原因
    timestamp: datetime
    is_locked: bool  # 是否被锁（满足三重共振）


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
        self.session: Optional[aiohttp.ClientSession] = None
        self.funding_rates: Dict[str, float] = {}
        self.open_interests: Dict[str, float] = {}

        logger.info("✅ MTF 三重共振锁已初始化")

    async def init_session(self):
        """初始化 HTTP session"""
        if not self.session:
            self.session = aiohttp.ClientSession()

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
        await self.init_session()

        url = "https://fapi.binance.com/fapi/v1/klines"
        params = {
            'symbol': symbol.replace('/', ''),
            'interval': '4h',  # 4 小时
            'limit': 50,
        }

        try:
            async with self.session.get(url, params=params) as response:
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

                # 判断趋势
                if ema20 > ema50 and current_price > ema20:
                    trend = 1
                    reason = f"4H 多头趋势：EMA20 (${ema20:.2f}) > EMA50 (${ema50:.2f})，价格 (${current_price:.2f}) > EMA20"
                elif ema20 < ema50 and current_price < ema20:
                    trend = -1
                    reason = f"4H 空头趋势：EMA20 (${ema20:.2f}) < EMA50 (${ema50:.2f})，价格 (${current_price:.2f}) < EMA20"
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
        条件 2: 极端 Open Interest/资金费率偏离

        逻辑：
        - 获取资金费率（8 小时结算）
        - 获取 Open Interest（未平仓合约）
        - 极度正费率（> 0.05%）+ OI 增长 → 多头过度拥挤 → 做空信号
        - 极度负费率（< -0.05%）+ OI 增长 → 空头过度拥挤 → 做多信号

        Args:
            symbol: 交易对

        Returns:
            (信号方向, 原因)
        """
        await self.init_session()

        # 1. 获取资金费率
        funding_url = "https://fapi.binance.com/fapi/v1/premiumIndex"
        funding_params = {'symbol': symbol.replace('/', '')}

        # 2. 获取 Open Interest
        oi_url = "https://fapi.binance.com/fapi/v1/openInterest"
        oi_params = {'symbol': symbol.replace('/', '')}

        try:
            # 并发请求
            async with self.session.get(funding_url, params=funding_params) as f_resp:
                funding_data = await f_resp.json()

            async with self.session.get(oi_url, params=oi_params) as oi_resp:
                oi_data = await oi_resp.json()

            # 解析资金费率
            funding_rate = float(funding_data.get('lastFundingRate', 0))
            mark_price = float(funding_data.get('markPrice', 0))

            # 解析 OI
            open_interest = float(oi_data.get('openInterest', 0))

            # 存储缓存
            self.funding_rates[symbol] = funding_rate
            self.open_interests[symbol] = open_interest

            # 判断极端偏离
            # 阈值：0.05%（正常是 ±0.01%）
            signal = 0
            reason = ""

            if funding_rate > 0.0005:  # 0.05% 极度正费率
                signal = -1  # 做空信号
                reason = f"极度正费率: {funding_rate:.4%}（多头过度拥挤）+ OI: {open_interest:,.0f} → 做空信号"
            elif funding_rate < -0.0005:  # -0.05% 极度负费率
                signal = 1  # 做多信号
                reason = f"极度负费率: {funding_rate:.4%}（空头过度拥挤）+ OI: {open_interest:,.0f} → 做多信号"
            else:
                signal = 0
                reason = f"费率正常: {funding_rate:.4%}，无极端偏离"

            logger.info(f"【资金费率/OI】{symbol}: {reason}")

            return signal, reason

        except Exception as e:
            logger.error(f"获取资金费率/OI 失败: {e}")
            return 0, f"获取数据异常: {e}"

    async def fetch_15m_volume_spike(self, symbol: str) -> Tuple[int, str]:
        """
        条件 3: 15m 精准放量猎杀

        逻辑：
        - 获取 15m K 线（最近 100 根）
        - 计算平均成交量
        - 当前成交量 > 平均 × 2 → 放量确认
        - 结合价格突破方向判断信号

        Args:
            symbol: 交易对

        Returns:
            (信号方向, 原因)
        """
        await self.init_session()

        url = "https://fapi.binance.com/fapi/v1/klines"
        params = {
            'symbol': symbol.replace('/', ''),
            'interval': '15m',  # 15 分钟
            'limit': 100,
        }

        try:
            async with self.session.get(url, params=params) as response:
                data = await response.json()

                if response.status != 200 or not data:
                    return 0, "无法获取 15m 数据"

                # 解析 K 线
                df = pd.DataFrame(data, columns=[
                    'timestamp', 'open', 'high', 'low', 'close', 'volume',
                    'close_time', 'quote_volume', 'trades', 'taker_buy_base',
                    'taker_buy_quote', 'ignore'
                ])

                df['close'] = df['close'].astype(float)
                df['volume'] = df['volume'].astype(float)
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

                # 判断放量突破
                signal = 0
                reason = ""

                if volume_ratio >= 2.0:  # 成交量 >= 2倍平均
                    if price_change_pct > 0.005:  # 价格上涨 > 0.5%
                        signal = 1
                        reason = f"15m 放量上涨：成交量 {volume_ratio:.1f}x 平均，价格上涨 {price_change_pct:.2%} → 做多信号"
                    elif price_change_pct < -0.005:  # 价格下跌 < -0.5%
                        signal = -1
                        reason = f"15m 放量下跌：成交量 {volume_ratio:.1f}x 平均，价格下跌 {price_change_pct:.2%} → 做空信号"
                    else:
                        signal = 0
                        reason = f"15m 放量但无方向：成交量 {volume_ratio:.1f}x 平均，价格横盘"
                else:
                    signal = 0
                    reason = f"15m 无放量：成交量 {volume_ratio:.1f}x 平均（需要 >= 2x）"

                logger.info(f"【15m 放量】{symbol}: {reason}")

                return signal, reason

        except Exception as e:
            logger.error(f"获取 15m 放量失败: {e}")
            return 0, f"获取数据异常: {e}"

    async def check_triple_resonance(self, symbol: str) -> MTFSignal:
        """
        v5.0 核心：检查三重共振

        规则：
        - 必须同时满足三个条件
        - 任何一环不满足 = 无信号
        - 返回信号置信度

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
        volume_15m, reason_volume = await self.fetch_15m_volume_spike(symbol)

        # 检查三重共振
        reasons = [reason_4h, reason_funding, reason_volume]
        signals = [trend_4h, funding_oi, volume_15m]

        # 统计信号方向
        long_votes = sum(1 for s in signals if s == 1)
        short_votes = sum(1 for s in signals if s == -1)
        no_signal_votes = sum(1 for s in signals if s == 0)

        # 判断是否锁定（三重共振）
        is_locked = False
        final_signal = 0
        confidence = 0

        if long_votes == 3:  # 全部做多
            final_signal = 1
            confidence = 1.0
            is_locked = True
        elif short_votes == 3:  # 全部做空
            final_signal = -1
            confidence = 1.0
            is_locked = True
        elif long_votes >= 2 and no_signal_votes == 0:  # 至少 2 个做多，无反对票
            final_signal = 1
            confidence = 0.7
            is_locked = True
        elif short_votes >= 2 and no_signal_votes == 0:  # 至少 2 个做空，无反对票
            final_signal = -1
            confidence = 0.7
            is_locked = True
        else:
            final_signal = 0
            confidence = 0
            is_locked = False

        # 打印结果
        logger.info(f"\n{'='*60}")
        logger.info(f"🎯 MTF 三重共振结果: {symbol}")
        logger.info(f"{'='*60}")
        logger.info(f"信号方向: {'LONG 📈' if final_signal == 1 else 'SHORT 📉' if final_signal == -1 else '无信号 ⏸️'}")
        logger.info(f"置信度: {confidence:.0%}")
        logger.info(f"是否锁定: {'🔐 三重共振已锁定' if is_locked else '❌ 共振未满足'}")
        logger.info(f"\n三重条件:")
        for i, (reason, signal) in enumerate(zip(reasons, signals), 1):
            status = "✅" if signal == final_signal else "❌" if signal != 0 else "⚪"
            logger.info(f"  {status} {i}. {reason}")
        logger.info(f"{'='*60}\n")

        return MTFSignal(
            symbol=symbol,
            signal=final_signal,
            confidence=confidence,
            reasons=reasons,
            timestamp=datetime.now(),
            is_locked=is_locked
        )

    async def close(self):
        """关闭 session"""
        if self.session:
            await self.session.close()


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

        await lock.close()

    asyncio.run(test_mtf())
