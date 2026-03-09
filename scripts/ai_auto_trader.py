#!/usr/bin/env python3
"""
AI 自主交易系统 v1.0 - 极简版
从 Binance 获取数据，AI 自主分析决策，自动执行交易
"""
import asyncio
import os
import sys
from pathlib import Path
from datetime import datetime
import json

# 设置代理（从 .env 加载）
from pathlib import Path
from dotenv import load_dotenv
project_root = Path(__file__).parent.parent
dotenv_path = project_root / '.env'
if dotenv_path.exists():
    load_dotenv(dotenv_path)

PROXY = os.environ.get("HTTPS_PROXY") or os.environ.get("HTTP_PROXY") or os.environ.get("ALL_PROXY")
if PROXY:
    os.environ['HTTP_PROXY'] = PROXY
    os.environ['HTTPS_PROXY'] = PROXY
    print(f"Using proxy: {PROXY}")

import ccxt
import numpy as np

# ============ 配置 ============
SYMBOLS = ['BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'BNB/USDT', 'XRP/USDT']
TIMEFRAMES = ['1h', '4h']  # 主要分析周期
CAPITAL = 200  # 初始资金 USDT
DRY_RUN = True  # 模拟模式
LEVERAGE = 5   # 默认杠杆

# 交易配置
MAX_POSITION_PCT = 0.5  # 最多使用 50% 资金
STOP_LOSS_PCT = 0.15   # 止损 15%
TAKE_PROFIT_PCT = 0.50 # 止盈 50%

# ============ 交易所连接 ============
class ExchangeClient:
    def __init__(self):
        # 代理配置
        ccxt_options = {
            'enableRateLimit': True,
            'options': {'defaultType': 'future'},
        }
        if PROXY:
            proxy_host = PROXY.replace('http://', '').replace('https://', '')
            ccxt_options['httpsProxy'] = f'http://{proxy_host}'
            print(f"CCXT using proxy: http://{proxy_host}")

        self.exchange = ccxt.binance(ccxt_options)

    def fetch_ohlcv(self, symbol, timeframe='1h', limit=200):
        """获取K线数据"""
        try:
            ohlcv = self.exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
            return self._parse_ohlcv(ohlcv)
        except Exception as e:
            print(f"获取 {symbol} 数据失败: {e}")
            return None

    def _parse_ohlcv(self, ohlcv):
        """解析K线数据"""
        df = {
            'time': [x[0] for x in ohlcv],
            'open': [x[1] for x in ohlcv],
            'high': [x[2] for x in ohlcv],
            'low': [x[3] for x in ohlcv],
            'close': [x[4] for x in ohlcv],
            'volume': [x[5] for x in ohlcv],
        }
        return df

    def fetch_ticker(self, symbol):
        """获取当前价格"""
        try:
            ticker = self.exchange.fetch_ticker(symbol)
            return {
                'price': ticker['last'],
                'volume': ticker['baseVolume'],
                'change': ticker.get('percentage', 0),
            }
        except Exception as e:
            print(f"获取 {symbol} 价格失败: {e}")
            return None


# ============ 技术指标计算 ============
class TechnicalIndicators:
    @staticmethod
    def ema(data, period):
        """指数移动平均"""
        if len(data) < period:
            return None
        ema_array = []
        multiplier = 2 / (period + 1)
        ema = sum(data[:period]) / period
        ema_array.extend([ema] * period)
        for i in range(period, len(data)):
            ema = (data[i] - ema) * multiplier + ema
            ema_array.append(ema)
        return ema_array

    @staticmethod
    def rsi(data, period=14):
        """RSI 相对强弱指标"""
        if len(data) < period + 1:
            return None
        deltas = np.diff(data)
        gains = np.where(deltas > 0, deltas, 0)
        losses = np.where(deltas < 0, -deltas, 0)
        avg_gain = np.mean(gains[:period])
        avg_loss = np.mean(losses[:period])
        rs = avg_gain / avg_loss if avg_loss != 0 else 100
        rsi = 100 - (100 / (1 + rs))
        return rsi

    @staticmethod
    def atr(high, low, close, period=14):
        """ATR 平均真实波幅"""
        if len(high) < period + 1:
            return None
        tr = []
        for i in range(1, len(high)):
            h_l = high[i] - low[i]
            h_c = abs(high[i] - close[i-1])
            l_c = abs(low[i] - close[i-1])
            tr.append(max(h_l, h_c, l_c))
        return np.mean(tr[-period:])

    @staticmethod
    def volume_ma(volume, period=20):
        """成交量移动平均"""
        if len(volume) < period:
            return None
        return np.mean(volume[-period:])

    @staticmethod
    def macd(data, fast=12, slow=26, signal=9):
        """MACD 指标"""
        if len(data) < slow:
            return None
        ema_fast = TechnicalIndicators.ema(data, fast)
        ema_slow = TechnicalIndicators.ema(data, slow)
        if ema_fast is None or ema_slow is None:
            return None
        macd_line = [ema_fast[i] - ema_slow[i] for i in range(len(ema_fast))]
        signal_line = TechnicalIndicators.ema(macd_line, signal)
        if signal_line is None:
            return None
        histogram = macd_line[-1] - signal_line[-1]
        return {
            'macd': macd_line[-1],
            'signal': signal_line[-1],
            'histogram': histogram
        }


# ============ AI 决策引擎 ============
class AIDecisionEngine:
    """AI 自主分析决策引擎"""

    def __init__(self):
        self.indicators = TechnicalIndicators()

    def analyze(self, symbol, data_1h, data_4h, current_price, ticker):
        """
        AI 分析决策
        返回: {
            'action': 'BUY' / 'SELL' / 'HOLD' / 'CLOSE_LONG' / 'CLOSE_SHORT',
            'side': 'LONG' / 'SHORT' / None,
            'leverage': int,
            'confidence': float,  # 0-1 信心指数
            'reason': str,       # 决策原因
            'details': dict      # 详细分析数据
        }
        """
        if data_1h is None or data_4h is None:
            return {'action': 'HOLD', 'reason': '数据获取失败'}

        close = np.array(data_1h['close'])
        high = np.array(data_1h['high'])
        low = np.array(data_1h['low'])
        volume = np.array(data_1h['volume'])

        close_4h = np.array(data_4h['close'])
        high_4h = np.array(data_4h['high'])
        volume_4h = np.array(data_4h['volume'])

        # ============ 技术指标计算 ============
        # EMA
        ema_20_1h = self.indicators.ema(close.tolist(), 20)
        ema_50_1h = self.indicators.ema(close.tolist(), 50)
        ema_20_4h = self.indicators.ema(close_4h.tolist(), 20)
        ema_200_4h = self.indicators.ema(close_4h.tolist(), 200)

        # RSI
        rsi_1h = self.indicators.rsi(close.tolist(), 14)
        rsi_4h = self.indicators.rsi(close_4h.tolist(), 14)

        # ATR
        atr_1h = self.indicators.atr(high, low, close, 14)
        atr_4h = self.indicators.atr(high_4h, np.array(data_4h['low']), close_4h, 14)

        # 成交量
        vol_ma_1h = self.indicators.volume_ma(volume, 20)
        vol_ma_4h = self.indicators.volume_ma(volume_4h, 20)
        vol_ratio_1h = volume[-1] / vol_ma_1h if vol_ma_1h else 1
        vol_ratio_4h = volume_4h[-1] / vol_ma_4h if vol_ma_4h else 1

        # MACD
        macd_1h = self.indicators.macd(close.tolist())
        macd_4h = self.indicators.macd(close_4h.tolist())

        # ============ AI 分析判断 ============
        score = 0  # 正分=多头，负分=空头
        reasons = []

        # 1. 趋势分析 (4h EMA)
        if ema_20_4h and ema_200_4h:
            if close_4h[-1] > ema_20_4h[-1] > ema_200_4h[-1]:
                score += 2
                reasons.append("4h趋势向上(价格>EMA20>EMA200)")
            elif close_4h[-1] < ema_20_4h[-1] < ema_200_4h[-1]:
                score -= 2
                reasons.append("4h趋势向下(价格<EMA20<EMA200)")
            elif close_4h[-1] > ema_200_4h[-1]:
                score += 1
                reasons.append("4h价格在EMA200上方")

        # 2. 动量分析 (RSI)
        if rsi_1h and rsi_4h:
            if rsi_1h > 50 and rsi_4h > 50:
                score += 1
                reasons.append(f"RSI健康(rsi_1h={rsi_1h:.1f}, rsi_4h={rsi_4h:.1f})")
            elif rsi_1h < 50 or rsi_4h < 50:
                score -= 0.5
                reasons.append(f"RSI偏弱(rsi_1h={rsi_1h:.1f}, rsi_4h={rsi_4h:.1f})")

            # 超卖反弹机会
            if 30 < rsi_1h < 40:
                score += 1
                reasons.append("1h RSI超卖，可能反弹")
            # 超买回调风险
            elif rsi_1h > 70:
                score -= 1
                reasons.append("1h RSI超买，注意回调")

        # 3. 成交量分析
        if vol_ratio_1h > 1.5:
            score += 1
            reasons.append(f"1h成交量放大({vol_ratio_1h:.1f}倍)")
        if vol_ratio_4h > 1.5:
            score += 1
            reasons.append(f"4h成交量放大({vol_ratio_4h:.1f}倍)")

        # 4. MACD 分析
        if macd_1h and macd_4h:
            if macd_1h['histogram'] > 0 and macd_4h['histogram'] > 0:
                score += 1.5
                reasons.append("MACD双周期金叉")
            elif macd_1h['histogram'] < 0 and macd_4h['histogram'] < 0:
                score -= 1.5
                reasons.append("MACD双周期死叉")

        # 5. 波动性分析
        if atr_4h:
            price = current_price
            volatility = atr_4h / price
            if volatility > 0.03:
                reasons.append(f"波动性较高({volatility*100:.1f}%)")

        # ============ 最终决策 ============
        confidence = min(abs(score) / 5, 1.0)  # 最大信心度

        details = {
            'price': current_price,
            'ema_20_4h': ema_20_4h[-1] if ema_20_4h else None,
            'ema_200_4h': ema_200_4h[-1] if ema_200_4h else None,
            'rsi_1h': rsi_1h,
            'rsi_4h': rsi_4h,
            'vol_ratio_1h': vol_ratio_1h,
            'vol_ratio_4h': vol_ratio_4h,
            'macd_1h': macd_1h['histogram'] if macd_1h else 0,
            'macd_4h': macd_4h['histogram'] if macd_4h else 0,
            'atr_4h': atr_4h,
            'volatility': atr_4h / current_price if atr_4h else 0,
            'score': score,
        }

        # 决策逻辑
        if score >= 3 and confidence >= 0.6:
            # 根据波动性调整杠杆
            vol = details['volatility']
            lev = 5 if vol < 0.03 else (3 if vol < 0.05 else 2)

            return {
                'action': 'BUY',
                'side': 'LONG',
                'leverage': lev,
                'confidence': confidence,
                'reason': f"做多信号 ({'+'.join(reasons[:3])})",
                'details': details
            }
        elif score <= -3 and confidence >= 0.6:
            vol = details['volatility']
            lev = 5 if vol < 0.03 else (3 if vol < 0.05 else 2)

            return {
                'action': 'SELL',
                'side': 'SHORT',
                'leverage': lev,
                'confidence': confidence,
                'reason': f"做空信号 ({'+'.join(reasons[:3])})",
                'details': details
            }
        else:
            return {
                'action': 'HOLD',
                'side': None,
                'leverage': 0,
                'confidence': confidence,
                'reason': f"观望 (score={score}, {'+'.join(reasons[:2]) if reasons else '无明确信号'})",
                'details': details
            }


# ============ 交易执行 ============
class TradingExecutor:
    def __init__(self, exchange, dry_run=True):
        self.exchange = exchange
        self.dry_run = dry_run
        self.position = None  # 当前持仓

    def open_position(self, symbol, side, leverage, entry_price, quantity):
        """开仓"""
        if self.dry_run:
            self.position = {
                'symbol': symbol,
                'side': side,
                'entry_price': entry_price,
                'quantity': quantity,
                'leverage': leverage,
                'stop_loss': entry_price * (1 - STOP_LOSS_PCT) if side == 'LONG' else entry_price * (1 + STOP_LOSS_PCT),
                'take_profit': entry_price * (1 + TAKE_PROFIT_PCT) if side == 'LONG' else entry_price * (1 - TAKE_PROFIT_PCT),
            }
            print(f"\n🧪 [DRY-RUN] 模拟开仓: {symbol} {side} x{leverage}")
            print(f"   入场价: ${entry_price:.2f}")
            print(f"   数量: {quantity}")
            print(f"   止损: ${self.position['stop_loss']:.2f}")
            print(f"   止盈: ${self.position['take_profit']:.2f}")
            return True
        else:
            # 实盘下单逻辑
            pass

    def close_position(self, symbol, exit_price):
        """平仓"""
        if self.position:
            pnl = 0
            if self.position['side'] == 'LONG':
                pnl = (exit_price - self.position['entry_price']) * self.position['quantity']
            else:
                pnl = (self.position['entry_price'] - exit_price) * self.position['quantity']

            print(f"\n🧪 [DRY-RUN] 模拟平仓: {symbol}")
            print(f"   平仓价: ${exit_price:.2f}")
            print(f"   盈亏: ${pnl:.2f}")

            self.position = None
            return pnl
        return 0

    def check_position_exit(self, current_price):
        """检查是否需要止损/止盈"""
        if not self.position:
            return None

        sl = self.position['stop_loss']
        tp = self.position['take_profit']

        if self.position['side'] == 'LONG':
            if current_price <= sl:
                return 'STOP_LOSS'
            elif current_price >= tp:
                return 'TAKE_PROFIT'
        else:
            if current_price >= sl:
                return 'STOP_LOSS'
            elif current_price <= tp:
                return 'TAKE_PROFIT'

        return None


# ============ 主程序 ============
def load_existing_position():
    """从 sniper_state.json 加载现有持仓"""
    state_file = Path(__file__).parent.parent / 'state' / 'sniper_state.json'
    if state_file.exists():
        try:
            with open(state_file, 'r', encoding='utf-8') as f:
                state = json.load(f)
            if state.get('positions'):
                pos = state['positions'][0]
                return {
                    'symbol': pos['symbol'],
                    'side': pos['side'],
                    'entry_price': pos['entry_price'],
                    'stop_loss': pos.get('stop_loss_price'),
                    'take_profit': pos.get('take_profit_price'),
                }
        except Exception as e:
            print(f"读取持仓状态失败: {e}")
    return None


async def main():
    print("=" * 60)
    print("🤖 AI 自主交易系统 v1.0")
    print("=" * 60)

    # 初始化
    exchange = ExchangeClient()
    ai = AIDecisionEngine()
    executor = TradingExecutor(exchange, dry_run=DRY_RUN)

    # 从状态文件加载已有持仓
    existing_pos = load_existing_position()
    if existing_pos:
        # 使用已有持仓
        executor.position = existing_pos
        print(f"\n📊 检测到已有持仓: {existing_pos['symbol']} {existing_pos['side']}")
        print(f"   入场价: ${existing_pos['entry_price']:.2f}")

    # 检查持仓状态
    if executor.position:
        print(f"\n📊 当前持仓: {executor.position['symbol']} {executor.position['side']}")
        print(f"   入场价: ${executor.position['entry_price']:.2f}")

    # 扫描所有币种
    print("\n" + "=" * 60)
    print("📊 市场分析")
    print("=" * 60)

    signals = []

    for symbol in SYMBOLS:
        print(f"\n🔍 分析 {symbol}...")

        # 获取数据
        data_1h = exchange.fetch_ohlcv(symbol, '1h', 200)
        data_4h = exchange.fetch_ohlcv(symbol, '4h', 200)
        ticker = exchange.fetch_ticker(symbol)

        if not data_1h or not data_4h or not ticker:
            print(f"   ❌ 数据获取失败，跳过")
            continue

        current_price = ticker['price']

        # AI 分析
        decision = ai.analyze(symbol, data_1h, data_4h, current_price, ticker)

        # 打印分析结果
        details = decision['details']
        print(f"   价格: ${current_price:.2f} (涨跌: {ticker['change']:+.2f}%)")
        print(f"   RSI: 1h={details['rsi_1h']:.1f}, 4h={details['rsi_4h']:.1f}")
        print(f"   成交量: 1h={details['vol_ratio_1h']:.1f}x, 4h={details['vol_ratio_4h']:.1f}x")
        print(f"   波动性: {details['volatility']*100:.2f}%")
        print(f"   AI评分: {details['score']:+.1f}")
        print(f"   ➡️  决策: {decision['action']} ({decision['reason']})")

        # 收集信号
        if decision['action'] in ['BUY', 'SELL']:
            signals.append((symbol, decision))

    # 执行交易
    print("\n" + "=" * 60)
    print("🎯 交易决策")
    print("=" * 60)

    # 检查是否需要平仓
    if executor.position:
        for symbol, data in [(executor.position['symbol'], None)]:
            ticker = exchange.fetch_ticker(symbol)
            if ticker:
                current_price = ticker['price']
                exit_reason = executor.check_position_exit(current_price)
                if exit_reason:
                    print(f"\n⚠️ 触发 {exit_reason}，自动平仓!")
                    pnl = executor.close_position(symbol, current_price)
                    print(f"   盈亏: ${pnl:.2f}")

    # 检查开仓信号
    if not executor.position and signals:
        # 过滤反向信号
        filtered_signals = []
        for symbol, decision in signals:
            if existing_pos:
                # 如果已有持仓是 LONG，忽略 SELL 信号
                if existing_pos['side'] == 'LONG' and decision['action'] == 'SELL':
                    print(f"   ⏭️  忽略 {symbol} 做空信号 (已有 {existing_pos['side']} 持仓)")
                    continue
                # 如果已有持仓是 SHORT，忽略 BUY 信号
                elif existing_pos['side'] == 'SHORT' and decision['action'] == 'BUY':
                    print(f"   ⏭️  忽略 {symbol} 做多信号 (已有 {existing_pos['side']} 持仓)")
                    continue
            filtered_signals.append((symbol, decision))

        if not filtered_signals:
            print("\n⏸️  所有信号被过滤（与现有持仓方向冲突）")
            print("=" * 60)
            return

        # 按信心度排序，选择最确定的
        filtered_signals.sort(key=lambda x: x[1]['confidence'], reverse=True)
        symbol, decision = filtered_signals[0]

        if decision['confidence'] >= 0.6:
            # 计算仓位
            quantity = (CAPITAL * MAX_POSITION_PCT * decision['leverage']) / current_price

            print(f"\n✅ 执行开仓: {symbol} {decision['side']} x{decision['leverage']}")
            print(f"   信心度: {decision['confidence']*100:.0f}%")
            print(f"   原因: {decision['reason']}")

            executor.open_position(
                symbol,
                decision['side'],
                decision['leverage'],
                current_price,
                quantity
            )
        else:
            print(f"\n⏸️  有信号但信心度不足，保持观望")

    elif not executor.position:
        print("\n⏸️  无交易信号，保持观望")

    print("\n" + "=" * 60)
    print(f"✅ 扫描完成 | 模式: {'DRY-RUN' if DRY_RUN else 'LIVE'}")
    print("=" * 60)


if __name__ == '__main__':
    asyncio.run(main())
