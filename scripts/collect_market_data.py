"""
完整市场数据收集与分析

收集多时间框架数据 + 技术指标 + 宏观数据，发送给 AI 分析
"""
import asyncio
import logging
import sys
import os
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


async def collect_market_data(symbol: str = "BTCUSDT"):
    """收集完整市场数据"""
    import aiohttp
    import pandas as pd
    import numpy as np

    proxy = os.environ.get("HTTP_PROXY") or os.environ.get("HTTPS_PROXY")
    base_url = "https://fapi.binance.com/fapi/v1"

    logger.info("=" * 70)
    logger.info(f"📊 完整市场数据收集: {symbol}")
    logger.info("=" * 70)

    async with aiohttp.ClientSession() as session:
        # 并发获取多个时间框架的数据
        tasks = [
            fetch_klines(session, base_url, symbol, "15m", 200, proxy),
            fetch_klines(session, base_url, symbol, "1h", 200, proxy),
            fetch_klines(session, base_url, symbol, "4h", 200, proxy),
            fetch_klines(session, base_url, symbol, "1d", 90, proxy),
            fetch_funding(session, base_url, symbol, proxy),
            fetch_oi_hist(session, base_url, symbol, proxy),
            fetch_ticker(session, base_url, symbol, proxy),
            fetch_long_short(session, base_url, symbol, proxy),
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        klines_15m = results[0]
        klines_1h = results[1]
        klines_4h = results[2]
        klines_1d = results[3]
        funding = results[4]
        oi_hist = results[5]
        ticker = results[6]
        long_short = results[7]

    # 处理 K 线数据
    data = {
        '15m': process_klines(klines_15m),
        '1h': process_klines(klines_1h),
        '4h': process_klines(klines_4h),
        '1d': process_klines(klines_1d),
    }

    # 计算技术指标
    indicators = {}
    for tf, df in data.items():
        if df is not None and len(df) > 0:
            indicators[tf] = calculate_indicators(df)

    # 宏观数据
    macro = {
        'funding_rate': funding.get('lastFundingRate') if funding else None,
        'mark_price': funding.get('markPrice') if funding else None,
        'index_price': funding.get('indexPrice') if funding else None,
        'oi_current': oi_hist[-1].get('openInterest') if oi_hist and len(oi_hist) > 0 else None,
        'oi_change_1h': calculate_oi_change(oi_hist, 12) if oi_hist and len(oi_hist) >= 12 else None,
        'oi_change_4h': calculate_oi_change(oi_hist, 48) if oi_hist and len(oi_hist) >= 48 else None,
        'volume_24h': ticker.get('volume') if ticker else None,
        'price_change_24h': ticker.get('priceChangePercent') if ticker else None,
        'long_short_ratio': long_short.get('longShortRatio') if long_short else None,
    }

    return data, indicators, macro


async def fetch_klines(session, base_url, symbol, interval, limit, proxy):
    """获取 K 线数据"""
    url = f"{base_url}/klines"
    params = {'symbol': symbol, 'interval': interval, 'limit': limit}

    kwargs = {'url': url, 'params': params}
    if proxy:
        kwargs['proxy'] = proxy

    try:
        async with session.get(**kwargs) as resp:
            if resp.status == 200:
                return await resp.json()
    except Exception as e:
        logger.warning(f"获取 {interval} K线失败: {e}")
    return None


async def fetch_funding(session, base_url, symbol, proxy):
    """获取资金费率"""
    url = f"{base_url}/premiumIndex"
    params = {'symbol': symbol}

    kwargs = {'url': url, 'params': params}
    if proxy:
        kwargs['proxy'] = proxy

    try:
        async with session.get(**kwargs) as resp:
            if resp.status == 200:
                return await resp.json()
    except Exception as e:
        logger.warning(f"获取资金费率失败: {e}")
    return None


async def fetch_oi_hist(session, base_url, symbol, proxy):
    """获取 OI 历史"""
    url = f"{base_url}/openInterestHist"
    params = {'symbol': symbol, 'period': '5m', 'limit': 60}

    kwargs = {'url': url, 'params': params}
    if proxy:
        kwargs['proxy'] = proxy

    try:
        async with session.get(**kwargs) as resp:
            if resp.status == 200:
                return await resp.json()
    except Exception as e:
        logger.warning(f"获取 OI 历史失败: {e}")
    return None


async def fetch_ticker(session, base_url, symbol, proxy):
    """获取 24h 行情"""
    url = f"{base_url}/ticker/24hr"
    params = {'symbol': symbol}

    kwargs = {'url': url, 'params': params}
    if proxy:
        kwargs['proxy'] = proxy

    try:
        async with session.get(**kwargs) as resp:
            if resp.status == 200:
                return await resp.json()
    except Exception as e:
        logger.warning(f"获取行情失败: {e}")
    return None


async def fetch_long_short(session, base_url, symbol, proxy):
    """获取多空比"""
    url = f"{base_url}/longShortRatio"
    params = {'symbol': symbol, 'period': '1h', 'limit': 1}

    kwargs = {'url': url, 'params': params}
    if proxy:
        kwargs['proxy'] = proxy

    try:
        async with session.get(**kwargs) as resp:
            if resp.status == 200:
                data = await resp.json()
                if isinstance(data, list) and len(data) > 0:
                    return data[-1]
    except Exception as e:
        logger.warning(f"获取多空比失败: {e}")
    return None


def process_klines(klines_data):
    """处理 K 线数据"""
    if not klines_data:
        return None

    import pandas as pd

    df = pd.DataFrame(klines_data, columns=[
        'timestamp', 'open', 'high', 'low', 'close', 'volume',
        'close_time', 'quote_volume', 'trades', 'taker_buy_base',
        'taker_buy_quote', 'ignore'
    ])

    for col in ['open', 'high', 'low', 'close', 'volume']:
        df[col] = pd.to_numeric(df[col])

    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    return df


def calculate_indicators(df):
    """计算技术指标"""
    import pandas as pd
    import numpy as np

    close = df['close']
    high = df['high']
    low = df['low']
    volume = df['volume']

    # RSI
    delta = close.diff()
    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)
    avg_gain = gain.rolling(window=14).mean()
    avg_loss = loss.rolling(window=14).mean()
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))

    # EMA
    ema9 = close.ewm(span=9).mean()
    ema20 = close.ewm(span=20).mean()
    ema50 = close.ewm(span=50).mean()

    # ATR
    high_low = high - low
    high_close = abs(high - close.shift())
    low_close = abs(low - close.shift())
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    atr = tr.rolling(window=14).mean()

    # 成交量均线
    volume_ma = volume.rolling(window=20).mean()
    volume_ratio = volume / volume_ma

    # MACD
    ema12 = close.ewm(span=12).mean()
    ema26 = close.ewm(span=26).mean()
    macd = ema12 - ema26
    signal = macd.ewm(span=9).mean()
    histogram = macd - signal

    # 布林带
    bb_middle = close.rolling(20).mean()
    bb_std = close.rolling(20).std()
    bb_upper = bb_middle + (bb_std * 2)
    bb_lower = bb_middle - (bb_std * 2)

    latest = df.iloc[-1]

    return {
        'current_price': float(latest['close']),
        'rsi': float(rsi.iloc[-1]) if not pd.isna(rsi.iloc[-1]) else None,
        'ema9': float(ema9.iloc[-1]),
        'ema20': float(ema20.iloc[-1]),
        'ema50': float(ema50.iloc[-1]),
        'atr': float(atr.iloc[-1]) if not pd.isna(atr.iloc[-1]) else None,
        'volume_ratio': float(volume_ratio.iloc[-1]) if not pd.isna(volume_ratio.iloc[-1]) else None,
        'macd': float(macd.iloc[-1]),
        'macd_signal': float(signal.iloc[-1]),
        'macd_histogram': float(histogram.iloc[-1]),
        'bb_upper': float(bb_upper.iloc[-1]) if not pd.isna(bb_upper.iloc[-1]) else None,
        'bb_middle': float(bb_middle.iloc[-1]) if not pd.isna(bb_middle.iloc[-1]) else None,
        'bb_lower': float(bb_lower.iloc[-1]) if not pd.isna(bb_lower.iloc[-1]) else None,
        'trend': 'bullish' if ema20.iloc[-1] > ema50.iloc[-1] else 'bearish',
    }


def calculate_oi_change(oi_hist, periods):
    """计算 OI 变化"""
    if not oi_hist or len(oi_hist) < periods:
        return None

    current = float(oi_hist[-1].get('openInterest', 0))
    past = float(oi_hist[-len(oi_hist) + periods - 1].get('openInterest', 0))

    if past > 0:
        return ((current - past) / past) * 100
    return None


def generate_analysis_prompt(symbol: str, data: dict, indicators: dict, macro: dict):
    """生成 AI 分析提示词"""

    # 最新价格
    latest_15m = indicators.get('15m', {})
    latest_1h = indicators.get('1h', {})
    latest_4h = indicators.get('4h', {})
    latest_1d = indicators.get('1d', {})

    prompt = f"""
# {symbol} 市场深度分析

## 你的交易准则
- 本金: 200 USDT
- 策略: 极低频、极高置信度狙击手模式
- 仓位: 20%-50% (40-100 USDT)
- 止损: 2%
- 止盈: 4%
- 最小证据数: 2 条

## 三重共振条件（参考，不是必须全部满足）

1. **4H 宏观趋势确认**
   - EMA20 > EMA50 → 多头
   - EMA20 < EMA50 → 空头

2. **极端 OI/资金费率偏离**
   - 资金费率 > 0.05% + ΔOI > 5% → 做空信号
   - 资金费率 < -0.05% + ΔOI > 5% → 做多信号

3. **15m 精准放量**
   - 成交量 >= 2 倍平均
   - 价格突破 > 0.5%

---

## 📊 多时间框架数据

### 15分钟周期（精准入场）
- 当前价格: ${latest_15m.get('current_price', 0):,.2f}
- EMA9: ${latest_15m.get('ema9', 0):,.2f}
- EMA20: ${latest_15m.get('ema20', 0):,.2f}
- RSI: {latest_15m.get('rsi', 0):.1f}
- 成交量倍数: {latest_15m.get('volume_ratio', 0):.2f}x
- MACD: {latest_15m.get('macd_histogram', 0):.4f} (histogram)
- 布林带: ${latest_15m.get('bb_lower', 0):,.0f} - ${latest_15m.get('bb_upper', 0):,.0f}

### 1小时周期（短期趋势）
- 当前价格: ${latest_1h.get('current_price', 0):,.2f}
- EMA9: ${latest_1h.get('ema9', 0):,.2f}
- EMA20: ${latest_1h.get('ema20', 0):,.2f}
- EMA50: ${latest_1h.get('ema50', 0):,.2f}
- RSI: {latest_1h.get('rsi', 0):.1f}
- 趋势: {latest_1h.get('trend', 'unknown')}
- ATR: ${latest_1h.get('atr', 0):,.2f}

### 4小时周期（中期趋势）
- 当前价格: ${latest_4h.get('current_price', 0):,.2f}
- EMA20: ${latest_4h.get('ema20', 0):,.2f}
- EMA50: ${latest_4h.get('ema50', 0):,.2f}
- RSI: {latest_4h.get('rsi', 0):.1f}
- 趋势: {latest_4h.get('trend', 'unknown')}

### 1天周期（长期趋势）
- 当前价格: ${latest_1d.get('current_price', 0):,.2f}
- EMA20: ${latest_1d.get('ema20', 0):,.2f}
- EMA50: ${latest_1d.get('ema50', 0):,.2f}
- RSI: {latest_1d.get('rsi', 0):.1f}
- 趋势: {latest_1d.get('trend', 'unknown')}

---

## 📈 宏观数据

- 资金费率: {macro.get('funding_rate', 0):.4f}%
- 标记价格: ${macro.get('mark_price', 0):,.2f}
- 指数价格: ${macro.get('index_price', 0):,.2f}
- OI 当前: {macro.get('oi_current', 0):,.0f} BTC
- OI 变化 (1h): {macro.get('oi_change_1h', 0):+.2f}%
- OI 变化 (4h): {macro.get('oi_change_4h', 0):+.2f}%
- 24h 成交量: {macro.get('volume_24h', 0):,.0f} BTC
- 24h 涨跌: {macro.get('price_change_24h', 0):+.2f}%
- 多空比: {macro.get('long_short_ratio', 1):.2f}

---

## 🎯 分析任务

请根据以上数据进行分析：

1. **趋势判断**: 多头还是空头？强度如何？

2. **技术信号**:
   - RSI 是否进入极端区域？
   - MACD 是否金叉/死叉？
   - 布林带位置如何？
   - 成交量是否放量？

3. **宏观信号**:
   - 资金费率是否极端？
   - OI 变化是否异常？
   - 多空比是否失衡？

4. **交易决策**:
   - 是否符合交易条件？
   - 做多还是做空？
   - 入场价、止损、止盈建议
   - 仓位建议（40-100 USDT）

5. **风险评估**:
   - 胜率估算
   - 风险收益比
   - 是否有足够的证据支持？

请给出明确的交易建议，或说明为什么当前不适合交易。
"""

    return prompt


async def main():
    """主函数"""
    # 收集数据
    data, indicators, macro = await collect_market_data("BTCUSDT")

    # 打印数据摘要
    logger.info("\n✅ 数据收集完成!")
    logger.info(f"\n📊 技术指标摘要:")

    for tf, ind in indicators.items():
        if ind:
            logger.info(f"\n{tf}:")
            logger.info(f"  价格: ${ind.get('current_price', 0):,.2f}")
            logger.info(f"  RSI: {ind.get('rsi', 0):.1f}")
            logger.info(f"  趋势: {ind.get('trend')}")
            logger.info(f"  成交量倍数: {ind.get('volume_ratio', 0):.2f}x")

    logger.info(f"\n📈 宏观数据:")
    logger.info(f"  资金费率: {macro.get('funding_rate', 0):.4f}%")
    logger.info(f"  OI变化(1h): {macro.get('oi_change_1h', 0):+.2f}%")
    logger.info(f"  OI变化(4h): {macro.get('oi_change_4h', 0):+.2f}%")
    logger.info(f"  多空比: {macro.get('long_short_ratio', 1):.2f}")

    # 生成分析提示词
    prompt = generate_analysis_prompt("BTCUSDT", data, indicators, macro)

    # 保存到文件，供 AI 分析
    output_file = Path(__file__).parent.parent / "temp_market_analysis.txt"
    output_file.write_text(prompt, encoding='utf-8')

    logger.info(f"\n✅ 分析数据已保存到: {output_file}")
    logger.info("\n" + "=" * 70)
    logger.info("📋 请查看上方数据，自行分析并给出交易建议")
    logger.info("=" * 70)

    # 打印完整提示词供查看
    print(prompt)


if __name__ == '__main__':
    asyncio.run(main())
