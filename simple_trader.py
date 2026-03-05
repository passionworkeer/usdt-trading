#!/usr/bin/env python
"""
优化版交易机器人 - 多重确认信号生成器
包含: RSI + MACD + 布林带 + 动量 + 趋势判断
信号要求: 至少2个指标同时满足才触发交易
"""
import asyncio
import logging
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from collections import deque
import math

# 基础配置
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - [%(name)s] - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/simple_trader.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# 添加路径
sys.path.insert(0, str(Path(__file__).parent))


class MACDCalculator:
    """MACD 指标计算器 (5, 13, 5) - 快速版"""

    def __init__(self, fast: int = 5, slow: int = 13, signal: int = 5):
        self.fast = fast
        self.slow = slow
        self.signal = signal
        self.prices = deque(maxlen=slow + 1)
        self.ema_fast = None
        self.ema_slow = None
        self.ema_signal = None
        self.macd_history = deque(maxlen=signal + 1)

    def calculate(self, price: float) -> dict:
        """计算 MACD 返回 dict"""
        self.prices.append(price)

        if len(self.prices) < self.slow:
            return {'macd': 0, 'signal': 0, 'histogram': 0, 'ready': False}

        # 计算 EMA
        prices = list(self.prices)

        # 快速 EMA
        if self.ema_fast is None:
            self.ema_fast = sum(prices[-self.fast:]) / self.fast
        else:
            self.ema_fast = (price * 2 / (self.fast + 1)) + self.ema_fast * (1 - 2 / (self.fast + 1))

        # 慢速 EMA
        if self.ema_slow is None:
            self.ema_slow = sum(prices[-self.slow:]) / self.slow
        else:
            self.ema_slow = (price * 2 / (self.slow + 1)) + self.ema_slow * (1 - 2 / (self.slow + 1))

        macd = self.ema_fast - self.ema_slow

        # Signal 线
        self.macd_history.append(macd)
        if len(self.macd_history) < self.signal:
            self.ema_signal = macd
        else:
            if self.ema_signal is None:
                self.ema_signal = sum(self.macd_history) / len(self.macd_history)
            else:
                self.ema_signal = (macd * 2 / (self.signal + 1)) + self.ema_signal * (1 - 2 / (self.signal + 1))

        histogram = macd - self.ema_signal if self.ema_signal else 0

        return {
            'macd': macd,
            'signal': self.ema_signal,
            'histogram': histogram,
            'ready': len(self.macd_history) >= self.signal
        }


class BollingerBandsCalculator:
    """布林带计算器 (10期快速版)"""

    def __init__(self, period: int = 10, std_dev: float = 2.0):
        self.period = period
        self.std_dev = std_dev
        self.prices = deque(maxlen=period + 1)

    def calculate(self, price: float) -> dict:
        """计算布林带返回 dict"""
        self.prices.append(price)

        if len(self.prices) < self.period:
            return {'upper': 0, 'middle': 0, 'lower': 0, 'bandwidth': 0, 'position': 0.5, 'ready': False}

        price_list = list(self.prices)
        middle = sum(price_list) / self.period

        # 计算标准差
        variance = sum((p - middle) ** 2 for p in price_list) / self.period
        std = math.sqrt(variance)

        upper = middle + self.std_dev * std
        lower = middle - self.std_dev * std
        bandwidth = (upper - lower) / middle if middle > 0 else 0

        # 价格位置 (0-1, 0=下轨, 1=上轨)
        if upper != lower:
            position = (price - lower) / (upper - lower)
        else:
            position = 0.5

        return {
            'upper': upper,
            'middle': middle,
            'lower': lower,
            'bandwidth': bandwidth,
            'position': position,
            'ready': True
        }


class RSICalculator:
    """RSI 指标计算器"""

    def __init__(self, period: int = 14):
        self.period = period
        self.prices = deque(maxlen=period + 1)

    def calculate(self, price: float) -> float:
        """计算 RSI"""
        self.prices.append(price)
        if len(self.prices) < self.period + 1:
            return 50  # 数据不足，返回中性值

        gains = 0
        losses = 0

        for i in range(1, len(self.prices)):
            change = self.prices[i] - self.prices[i - 1]
            if change > 0:
                gains += change
            else:
                losses += abs(change)

        avg_gain = gains / self.period
        avg_loss = losses / self.period

        if avg_loss == 0:
            return 100
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        return rsi


class SimpleSignalGenerator:
    """优化版信号生成器 - MACD + 布林带 + RSI + 动量 多重确认"""

    def __init__(self):
        self.last_prices = {}
        self.price_history = {}
        self.rsi_calculators = {}
        self.macd_calculators = {}
        self.bb_calculators = {}
        self._price_cache = {}  # 价格缓存

    def set_price_cache(self, cache: dict):
        """设置价格缓存（仅当不为空时更新）"""
        if cache:  # 只有当缓存不为空时才更新
            self._price_cache = cache

    def get_rsi(self, symbol: str, price: float) -> float:
        """获取 RSI (7周期，更快生效)"""
        if symbol not in self.rsi_calculators:
            self.rsi_calculators[symbol] = RSICalculator(7)  # 改为7周期
        return self.rsi_calculators[symbol].calculate(price)

    def get_macd(self, symbol: str, price: float) -> dict:
        """获取 MACD"""
        if symbol not in self.macd_calculators:
            self.macd_calculators[symbol] = MACDCalculator()
        return self.macd_calculators[symbol].calculate(price)

    def get_bollinger_bands(self, symbol: str, price: float) -> dict:
        """获取布林带"""
        if symbol not in self.bb_calculators:
            self.bb_calculators[symbol] = BollingerBandsCalculator()
        return self.bb_calculators[symbol].calculate(price)

    def calculate_momentum(self, symbol: str, price: float) -> float:
        """计算动量（多周期变化）"""
        if symbol not in self.price_history:
            self.price_history[symbol] = deque(maxlen=5)
        self.price_history[symbol].append(price)

        history = list(self.price_history[symbol])
        if len(history) < 2:
            return 0

        return (history[-1] - history[0]) / history[0]

    def check_trend(self, macd: dict, bb: dict) -> str:
        """判断趋势方向"""
        if not macd.get('ready') or not bb.get('ready'):
            return 'unknown'

        # MACD 金叉/死叉
        macd_bullish = macd['histogram'] > 0
        macd_bearish = macd['histogram'] < 0

        # 布林带位置
        bb_position = bb['position']

        if bb_position < 0.2 and macd_bullish:
            return 'bullish_reversal'  # 接近下轨 + MACD 转正 = 潜在反弹
        elif bb_position > 0.8 and macd_bearish:
            return 'bearish_reversal'  # 接近上轨 + MACD 转负 = 潜在反转
        elif bb_position > 0.5 and macd_bullish:
            return 'uptrend'
        elif bb_position < 0.5 and macd_bearish:
            return 'downtrend'
        else:
            return 'neutral'

    def generate_signal(self, symbol: str, external_price: dict = None) -> dict:
        """生成信号（多重确认: 至少2个指标同时满足）"""
        import time

        if external_price and 'price' in external_price:
            price = external_price['price']
            if symbol in self.last_prices:
                last_price = self.last_prices[symbol]
                change = (price - last_price) / last_price
            else:
                change = 0
            self.last_prices[symbol] = price
        else:
            now = int(time.time())
            seed = now % 3600
            price_base = {'BTC/USDT': 67000, 'ETH/USDT': 3500, 'SOL/USDT': 170}.get(symbol, 100)
            change = (seed % 100 - 50) / 10000
            price = price_base * (1 + change)
            self.last_prices[symbol] = price

        # 计算所有技术指标
        rsi = self.get_rsi(symbol, price)
        momentum = self.calculate_momentum(symbol, price)
        macd = self.get_macd(symbol, price)
        bb = self.get_bollinger_bands(symbol, price)
        trend = self.check_trend(macd, bb)

        # 多重确认信号
        signal = 0
        confirmations = []  # 确认的指标列表

        # 做多条件 (至少2个确认)
        long_conditions = {
            'RSI超卖': rsi < 35,
            'MACD金叉': macd.get('ready') and macd['histogram'] > 0,
            'BB下轨': bb.get('ready') and bb['position'] < 0.25,
            '动量正向': momentum > 0.002,
            '趋势反转': trend in ['bullish_reversal', 'uptrend'],
        }

        # 做空条件 (至少2个确认)
        short_conditions = {
            'RSI超买': rsi > 65,
            'MACD死叉': macd.get('ready') and macd['histogram'] < 0,
            'BB上轨': bb.get('ready') and bb['position'] > 0.75,
            '动量负向': momentum < -0.002,
            '趋势反转': trend in ['bearish_reversal', 'downtrend'],
        }

        # 统计确认数
        long_confirms = sum(1 for v in long_conditions.values() if v)
        short_confirms = sum(1 for v in short_conditions.values() if v)

        if long_confirms >= 2:
            signal = 1
            confirmations = [k for k, v in long_conditions.items() if v]
        elif short_confirms >= 2:
            signal = -1
            confirmations = [k for k, v in short_conditions.items() if v]

        # 构建原因描述
        if signal == 1:
            reason = f"做多 [{', '.join(confirmations)}]"
        elif signal == -1:
            reason = f"做空 [{', '.join(confirmations)}]"
        else:
            # 显示各指标状态
            status = []
            if rsi < 35: status.append(f"RSI低({rsi:.1f})")
            elif rsi > 65: status.append(f"RSI高({rsi:.1f})")
            if macd.get('ready'):
                status.append(f"MACD{'+' if macd['histogram']>0 else '-'}")
            if bb.get('ready'):
                status.append(f"BB{int(bb['position']*100)}%")
            reason = f"观望 [{', '.join(status) if status else '指标不足'}]"

        return {
            'symbol': symbol,
            'signal': signal,
            'price': price,
            'change': change,
            'rsi': rsi,
            'momentum': momentum,
            'macd': macd.get('macd', 0),
            'macd_signal': macd.get('signal', 0),
            'macd_histogram': macd.get('histogram', 0),
            'bb_upper': bb.get('upper', 0),
            'bb_middle': bb.get('middle', 0),
            'bb_lower': bb.get('lower', 0),
            'bb_position': bb.get('position', 0.5),
            'trend': trend,
            'confirmations': confirmations,
            'confirm_count': len(confirmations),
            'reason': reason,
            'timestamp': datetime.now()
        }

    def get_all_prices(self) -> dict:
        """批量获取所有价格（带重试机制）"""
        import urllib.request
        import json
        import time
        import ssl

        # 尝试多个 API
        apis = [
            # Binance API (更可靠)
            ("https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT", "BTC/USDT"),
            ("https://api.binance.com/api/v3/ticker/price?symbol=ETHUSDT", "ETH/USDT"),
            ("https://api.binance.com/api/v3/ticker/price?symbol=SOLUSDT", "SOL/USDT"),
        ]

        result = {}

        for url, symbol in apis:
            for attempt in range(3):  # 最多重试3次
                try:
                    # 创建 SSL 上下文
                    ctx = ssl.create_default_context()
                    ctx.check_hostname = False
                    ctx.verify_mode = ssl.CERT_NONE

                    request = urllib.request.Request(url)
                    request.add_header('User-Agent', 'Mozilla/5.0')

                    with urllib.request.urlopen(request, timeout=15, context=ctx) as response:
                        data = json.loads(response.read())

                    if 'price' in data:
                        result[symbol] = {
                            'symbol': symbol,
                            'price': float(data['price']),
                            'timestamp': datetime.now()
                        }
                        break  # 成功获取，跳出重试循环

                except Exception as e:
                    if attempt < 2:
                        wait_time = (attempt + 1) * 3  # 3, 6 秒
                        logger.warning(f"获取 {symbol} 失败，{wait_time}秒后重试...")
                        time.sleep(wait_time)
                    else:
                        logger.warning(f"获取 {symbol} 最终失败: {e}")

        if result:
            return result
        else:
            # 如果 Binance 全部失败，尝试 CoinGecko
            logger.warning("Binance API 失败，尝试 CoinGecko...")

            try:
                coin_ids = 'bitcoin,ethereum,solana'
                url = f"https://api.coingecko.com/api/v3/simple/price?ids={coin_ids}&vs_currencies=usd"

                time.sleep(2)  # 延迟避免限流

                ctx = ssl.create_default_context()
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE

                request = urllib.request.Request(url)
                request.add_header('User-Agent', 'Mozilla/5.0')

                with urllib.request.urlopen(request, timeout=10, context=ctx) as response:
                    data = json.loads(response.read())

                price_map = {
                    'bitcoin': 'BTC/USDT',
                    'ethereum': 'ETH/USDT',
                    'solana': 'SOL/USDT'
                }

                for coin_id, symbol in price_map.items():
                    if coin_id in data:
                        result[symbol] = {
                            'symbol': symbol,
                            'price': data[coin_id]['usd'],
                            'timestamp': datetime.now()
                        }

            except Exception as e:
                logger.warning(f"CoinGecko 也失败: {e}")

        return result

    def get_price_from_external(self, symbol: str) -> dict:
        """从外部 API 获取价格（单个，已弃用，推荐用 get_all_prices）"""
        # 使用缓存的价格
        return self._price_cache.get(symbol)


class SimpleTrader:
    """简化版交易机器人"""

    def __init__(self):
        self.running = True
        self.signals = SimpleSignalGenerator()
        self.positions = {}

        # 交易配置
        self.symbols = ['BTC/USDT', 'ETH/USDT', 'SOL/USDT']
        self.scan_interval = 300  # 5 分钟（减少 API 调用）

        # 风控配置
        self.stop_loss_pct = 0.02  # 止损 2%
        self.take_profit_pct = 0.04  # 止盈 4%
        self.max_position_size = 0.3  # 最大单仓 30%

        # 统计数据
        self.stats = {
            'total_scans': 0,
            'total_signals': 0,
            'long_signals': 0,
            'short_signals': 0,
            'total_trades': 0,
            'win_trades': 0,
            'loss_trades': 0,
            'total_pnl': 0.0,
            'start_time': datetime.now()
        }

        # 启动画面
        self.print_banner()

    def print_banner(self):
        """打印启动画面"""
        banner = """
╔════════════════════════════════════════════════════════════╗
║         🤖 Sniper Trading Bot v9.0 - Enhanced              ║
║        ──────────────────────────────────────────            ║
║  多重指标: RSI + MACD + 布林带 + 动量 + 趋势                ║
║  信号确认: 至少2个指标同时满足                              ║
║  风控系统: 自动止损/止盈 + 仓位管理                        ║
╚════════════════════════════════════════════════════════════╝
"""
        logger.info(banner)
        logger.info(f"📊 监控交易对: {', '.join(self.symbols)}")
        logger.info(f"⏱️ 扫描间隔: {self.scan_interval // 60} 分钟")
        logger.info(f"💰 模式: DRY_RUN (模拟交易)")
        logger.info(f"🛡️ 风控参数:")
        logger.info(f"   └─ 止损: {self.stop_loss_pct*100}%")
        logger.info(f"   └─ 止盈: {self.take_profit_pct*100}%")
        logger.info(f"   └─ 最大仓位: {self.max_position_size*100}%")
        logger.info("="*60)

    def calculate_signal_strength(self, signal: dict) -> float:
        """计算信号强度 (0-100)"""
        strength = 0

        # 基础分: 确认数量
        confirm_count = signal.get('confirm_count', 0)
        strength += confirm_count * 20  # 每个确认 20 分

        # RSI 分数
        rsi = signal.get('rsi', 50)
        if signal['signal'] == 1:  # 做多
            if rsi < 30:
                strength += 25  # RSI超卖
            elif rsi < 40:
                strength += 15
        else:  # 做空
            if rsi > 70:
                strength += 25  # RSI超买
            elif rsi > 60:
                strength += 15

        # MACD 分数
        macd_hist = signal.get('macd_histogram', 0)
        if abs(macd_hist) > 100:
            strength += 15
        elif abs(macd_hist) > 50:
            strength += 10
        elif abs(macd_hist) > 20:
            strength += 5

        # 布林带位置
        bb_pos = signal.get('bb_position', 0.5)
        if signal['signal'] == 1:  # 做多
            if bb_pos < 0.2:
                strength += 15  # 接近下轨
            elif bb_pos < 0.3:
                strength += 10
        else:  # 做空
            if bb_pos > 0.8:
                strength += 15  # 接近上轨
            elif bb_pos > 0.7:
                strength += 10

        # 趋势确认
        trend = signal.get('trend', 'unknown')
        if signal['signal'] == 1 and trend in ['uptrend', 'bullish_reversal']:
            strength += 10
        elif signal['signal'] == -1 and trend in ['downtrend', 'bearish_reversal']:
            strength += 10

        return min(strength, 100)  # 最高 100 分

    def calculate_position_size(self, signal: dict) -> float:
        """根据信号强度计算仓位大小"""
        strength = self.calculate_signal_strength(signal)

        # 基础仓位 10% + 强度加成
        base_size = 0.10
        strength_bonus = (strength / 100) * 0.20  # 最高加 20%

        position_size = base_size + strength_bonus
        return min(position_size, self.max_position_size)

    def check_positions(self, current_prices: dict):
        """检查持仓状态（止损/止盈）"""
        closed_positions = []

        for symbol, position in list(self.positions.items()):
            if symbol not in current_prices:
                continue

            entry_price = position['entry_price']
            current_price = current_prices[symbol]['price']
            side = position['side']

            if side == 1:  # 做多
                pnl_pct = (current_price - entry_price) / entry_price
            else:  # 做空
                pnl_pct = (entry_price - current_price) / entry_price

            # 检查止损
            if pnl_pct <= -self.stop_loss_pct:
                logger.warning(f"🔴 止损触发: {symbol} | 亏损: {pnl_pct*100:.2f}%")
                self.stats['loss_trades'] += 1
                self.stats['total_pnl'] += pnl_pct
                closed_positions.append(symbol)

            # 检查止盈
            elif pnl_pct >= self.take_profit_pct:
                logger.info(f"🟢 止盈触发: {symbol} | 盈利: {pnl_pct*100:.2f}%")
                self.stats['win_trades'] += 1
                self.stats['total_pnl'] += pnl_pct
                closed_positions.append(symbol)

        # 关闭持仓
        for symbol in closed_positions:
            del self.positions[symbol]
            self.stats['total_trades'] += 1

        return closed_positions

    def get_positions_summary(self) -> str:
        """获取持仓摘要"""
        if not self.positions:
            return "无持仓"

        summary = []
        for symbol, pos in self.positions.items():
            side = "做多 📈" if pos['side'] == 1 else "做空 📉"
            duration = datetime.now() - pos['time']
            mins = int(duration.total_seconds() // 60)
            strength = pos.get('strength', 50)
            size = pos.get('size', 0.1) * 100
            stars = '⭐' * (strength // 20)
            summary.append(f"{symbol} {side} ${pos['entry_price']:.2f} | {size:.0f}%仓位 | {strength:.0f}/100{stars} | {mins}分钟")
        return " | ".join(summary)

    def print_stats(self):
        """打印统计信息"""
        runtime = datetime.now() - self.stats['start_time']
        hours = int(runtime.total_seconds() // 3600)
        minutes = int((runtime.total_seconds() % 3600) // 60)

        logger.info("="*50)
        logger.info("📈 运行统计")
        logger.info("="*50)
        logger.info(f"⏱️ 运行时间: {hours}小时 {minutes}分钟")
        logger.info(f"🔍 总扫描次数: {self.stats['total_scans']}")
        logger.info(f"🎯 总信号数: {self.stats['total_signals']}")
        logger.info(f"📈 做多信号: {self.stats['long_signals']}")
        logger.info(f"📉 做空信号: {self.stats['short_signals']}")
        if self.stats['total_scans'] > 0:
            signal_rate = self.stats['total_signals'] / self.stats['total_scans'] * 100
            logger.info(f"📊 信号率: {signal_rate:.1f}%")

        # 交易统计
        logger.info("-"*50)
        logger.info("💼 交易统计")
        logger.info("-"*50)
        logger.info(f"📊 总交易数: {self.stats['total_trades']}")
        logger.info(f"🟢 盈利: {self.stats['win_trades']}")
        logger.info(f"🔴 亏损: {self.stats['loss_trades']}")
        if self.stats['total_trades'] > 0:
            win_rate = self.stats['win_trades'] / self.stats['total_trades'] * 100
            logger.info(f"🏆 胜率: {win_rate:.1f}%")
            logger.info(f"💵 总盈亏: {self.stats['total_pnl']*100:.2f}%")
            avg_pnl = self.stats['total_pnl'] / self.stats['total_trades'] * 100
            logger.info(f"📊 平均盈亏: {avg_pnl:.2f}%")

        # 持仓状态
        logger.info("-"*50)
        logger.info(f"📦 当前持仓: {self.get_positions_summary()}")
        logger.info("="*50)

    async def scan_and_trade(self):
        """扫描并交易"""
        self.stats['total_scans'] += 1

        # 批量获取所有价格（减少 API 调用）
        price_cache = self.signals.get_all_prices()
        self.signals.set_price_cache(price_cache)

        # 检查现有持仓（止损/止盈）
        closed = self.check_positions(price_cache)
        if closed:
            logger.info(f"📋 已关闭持仓: {', '.join(closed)}")

        for symbol in self.symbols:
            # 从缓存获取价格
            external_data = self.signals.get_price_from_external(symbol)

            if external_data:
                logger.info(f"【{symbol}】外部价格: ${external_data['price']:.2f}")

            # 生成信号（传入外部价格用于计算真实变化）
            signal_data = self.signals.generate_signal(symbol, external_data)

            # 构建指标详情
            bb_info = ""
            if signal_data.get('bb_upper', 0) > 0:
                bb_info = f" | BB[{signal_data.get('bb_position', 0)*100:.0f}%]"

            macd_info = ""
            if signal_data.get('macd_histogram', 0) != 0:
                macd_info = f" | MACD{'+' if signal_data['macd_histogram']>0 else ''}{signal_data['macd_histogram']:.2f}"

            trend_info = ""
            if signal_data.get('trend', 'unknown') != 'unknown':
                trend_info = f" | 趋势:{signal_data['trend']}"

            # 记录详细信息
            logger.info(
                f"【{symbol}】{signal_data['reason']} | "
                f"RSI:{signal_data['rsi']:.1f}{bb_info}{macd_info}{trend_info}"
            )

            # 如果有信号且没有该品种的持仓
            if signal_data['signal'] != 0 and symbol not in self.positions:
                logger.critical(f"🎯 确认数: {signal_data.get('confirm_count', 0)}个")
                await self.execute_trade(signal_data)
                break  # 一次只开一个仓

    async def execute_trade(self, signal: dict):
        """执行交易（模拟）"""
        self.stats['total_signals'] += 1
        if signal['signal'] == 1:
            self.stats['long_signals'] += 1
        else:
            self.stats['short_signals'] += 1

        # 计算信号强度和仓位
        strength = self.calculate_signal_strength(signal)
        position_size = self.calculate_position_size(signal)

        action = "做多 📈" if signal['signal'] == 1 else "做空 📉"
        logger.critical(f"🎯 交易信号: {signal['symbol']} {action}")
        logger.critical(f"   价格: ${signal['price']:.2f}")
        logger.critical(f"   原因: {signal['reason']}")
        logger.critical(f"   强度: {strength:.0f}/100 ⭐{'*' * (strength//20)}")
        logger.critical(f"   仓位: {position_size*100:.1f}%")

        # 模拟开仓
        self.positions[signal['symbol']] = {
            'entry_price': signal['price'],
            'side': signal['signal'],
            'size': position_size,
            'strength': strength,
            'time': datetime.now()
        }

        # 更新日志
        self.update_trading_log(signal)

    def update_trading_log(self, signal: dict):
        """更新交易日志"""
        log_file = Path(__file__).parent / "TRADING_LOG.md"

        action = "做多" if signal['signal'] == 1 else "做空"
        new_entry = f"""### {datetime.now().strftime('%H:%M:%S')} - 交易信号
- **状态**: 检测到信号
- **交易信号**: {signal['symbol']} {action}
- **价格**: ${signal['price']:.2f}
- **原因**: {signal['reason']}
- **RSI**: {signal.get('rsi', 0):.1f}
- **MACD**: {signal.get('macd_histogram', 0):.2f}
- **BB位置**: {signal.get('bb_position', 0.5)*100:.0f}%

"""

        try:
            # 尝试读取现有内容，如果失败则重新创建
            try:
                if log_file.exists():
                    content = log_file.read_text(encoding='utf-8')
                else:
                    content = ""
            except:
                # 编码问题，重新创建文件
                content = ""

            today = datetime.now().strftime("%Y-%m-%d")
            header = f"## {today}"

            if header in content:
                parts = content.split(header, 1)
                content = parts[0] + header + "\n" + new_entry + parts[1]
            else:
                if not content.startswith("#"):
                    content = "# 交易日志 (Trading Log)\n\n"
                content += header + "\n" + new_entry

            log_file.write_text(content, encoding='utf-8')
            logger.info("✅ 交易日志已更新")
        except Exception as e:
            logger.error(f"❌ 更新日志失败: {e}")
            # 备份到新文件
            backup_file = log_file.parent / f"TRADING_LOG_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
            try:
                backup_file.write_text(new_entry, encoding='utf-8')
                logger.info(f"✅ 备份日志已保存: {backup_file.name}")
            except:
                pass

    async def run(self):
        """主循环"""
        logger.info("="*50)
        logger.info("开始扫描...")
        logger.info("="*50)

        scan_count = 0
        stats_interval = 12  # 每12次扫描输出一次统计（1小时）

        while self.running:
            try:
                await self.scan_and_trade()

                scan_count += 1
                if scan_count % stats_interval == 0:
                    self.print_stats()

                logger.info(f"⏰ 下次扫描: {self.scan_interval // 60} 分钟后\n")
                await asyncio.sleep(self.scan_interval)

            except KeyboardInterrupt:
                logger.info("\n收到停止信号")
                self.print_stats()
                break
            except Exception as e:
                logger.error(f"扫描异常: {e}")
                await asyncio.sleep(60)

        logger.info("🛑 交易机器人已停止")


async def main():
    """主函数"""
    trader = SimpleTrader()
    await trader.run()


if __name__ == '__main__':
    asyncio.run(main())
