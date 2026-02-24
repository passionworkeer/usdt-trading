#!/usr/bin/env python3
"""
专业交易系统服务

重构版特性：
✓ 动态权重决策（根据市场状态调整）
✓ AI 解耦（本地毫秒级响应）
✓ ATR 动态仓位管理
✓ 相关性矩阵（避免同质化仓位）
✓ 专业策略（BB Squeeze + Volume Profile）
✓ 完整回测框架
"""

import sys
import os
import time
import logging
import argparse
from pathlib import Path
from datetime import datetime
from typing import Dict, List

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.quantitative.professional_trading_system import (
    ProfessionalTradingService,
    MarketStateClassifier,
    DynamicDecisionEngine,
    ATRPositionSizer,
    CorrelationManager,
    LocalSignalGenerator,
    BacktestEngine,
)
from src.exchange.order_executor import OrderExecutor
from src.exchange.risk_manager import RiskManager, RiskConfig
from src.utils.logger import setup_logger


# 配置日志
logger = setup_logger('professional_trading', 'logs/professional_trading.log')


class ProfessionalTradingBot:
    """专业交易机器人"""

    def __init__(self, symbols: List[str], auto_trade: bool = False, config: Dict = None):
        self.symbols = symbols
        self.auto_trade = auto_trade
        self.config = config or self._load_config()

        # 初始化专业交易服务
        self.service = ProfessionalTradingService(config=self.config)

        # 价格历史存储
        self.price_history: Dict[str, List[float]] = {symbol: [] for symbol in symbols}
        self.volume_history: Dict[str, List[float]] = {symbol: [] for symbol in symbols}

        # 市场状态历史
        self.market_state_history: Dict[str, List] = {symbol: [] for symbol in symbols}

        # 交易统计
        self.stats = {
            'analysis_count': 0,
            'trade_executed': 0,
            'trade_rejected': 0,
            'signals_by_type': {'buy': 0, 'sell': 0, 'hold': 0},
        }

        self.running = False

        logger.info("=" * 60)
        logger.info("专业交易系统已启动（重构版 v3.0）")
        logger.info("=" * 60)
        logger.info(f"监控交易对: {', '.join(symbols)}")
        logger.info(f"自动交易: {'启用 ⚠️' if auto_trade else '禁用（仅分析）'}")
        logger.info(f"测试网: {self.config.get('testnet', True)}")
        logger.info("=" * 60)
        logger.info("✓ 动态权重系统")
        logger.info("✓ AI 解耦（本地实时决策）")
        logger.info("✓ ATR 动态仓位")
        logger.info("✓ 相关性矩阵")
        logger.info("✓ 专业策略（BB Squeeze + Volume Profile）")
        logger.info("=" * 60)

    def _load_config(self) -> Dict:
        """加载配置"""
        return {
            'testnet': os.getenv('BINANCE_TESTNET', 'true').lower() == 'true',
            'max_position_size': float(os.getenv('MAX_POSITION_SIZE', '1000')),
            'max_daily_loss': float(os.getenv('MAX_DAILY_LOSS', '500')),
            'max_open_positions': int(os.getenv('MAX_OPEN_POSITIONS', '5')),
            'min_confidence': float(os.getenv('MIN_CONFIDENCE', '0.7')),
            'atr_risk_per_trade': float(os.getenv('ATR_RISK_PER_TRADE', '0.02')),
            'account_capital': float(os.getenv('ACCOUNT_CAPITAL', '10000')),
            'correlation_threshold': float(os.getenv('CORRELATION_THRESHOLD', '0.7')),
            'check_interval': int(os.getenv('CHECK_INTERVAL', '60')),
        }

    def fetch_market_data(self, symbol: str) -> tuple:
        """获取市场数据"""
        try:
            ticker = self.service.executor.get_ticker(symbol)
            current_price = float(ticker['last'])

            # 获取 K 线数据（用于历史）
            ohlcv = self.service.executor.exchange.fetch_ohlcv(symbol, '1h', limit=100)
            closes = [candle[4] for candle in ohlcv]
            volumes = [candle[5] for candle in ohlcv]

            return current_price, closes, volumes
        except Exception as e:
            logger.error(f"获取 {symbol} 市场数据失败: {e}")
            return None, [], []

    def analyze_symbol(self, symbol: str):
        """分析单个交易对"""
        try:
            # 获取市场数据
            price, price_history, volume_history = self.fetch_market_data(symbol)

            if price is None:
                return

            # 更新历史数据
            self.price_history[symbol] = price_history
            self.volume_history[symbol] = volume_history

            logger.info("=" * 60)
            logger.info(f"专业分析: {symbol} @ ${price:,.2f}")
            logger.info("=" * 60)

            # 1. 市场状态分类
            market_state = self.service.market_state_classifier.classify(price_history, volume_history)
            self.market_state_history[symbol].append(market_state)

            logger.info(f"📊 市场状态: {market_state.regime.upper()}")
            logger.info(f"   强度: {market_state.strength:.2f}")
            logger.info(f"   ADX: {market_state.adx:.2f}")
            logger.info(f"   波动率: {market_state.volatility:.2%}")
            logger.info(f"   成交量比率: {market_state.volume_ratio:.2f}x")

            # 2. 动态权重
            dynamic_engine = DynamicDecisionEngine()
            weights = dynamic_engine.get_weights(market_state)
            active_strategies = dynamic_engine.get_active_strategies(market_state)

            logger.info(f"🎯 动态权重分配:")
            logger.info(f"   技术分析: {weights.technical:.0%}")
            logger.info(f"   市场情报: {weights.sentiment:.0%}")
            logger.info(f"   AI 分析: {weights.ai:.0%}")
            logger.info(f"   激活策略: {', '.join(active_strategies)}")

            # 3. 本地信号生成（毫秒级响应）
            signal = self.service.signal_generator.generate_signal(
                symbol=symbol,
                price=price,
                price_history=price_history,
                volume_history=volume_history,
            )

            logger.info(f"⚡ 本地信号:")
            logger.info(f"   动作: {signal['action'].upper()}")
            logger.info(f"   强度: {signal['strength']:.2f}")
            logger.info(f"   置信度: {signal['confidence']:.2f}")
            logger.info(f"   理由: {signal['reasoning']}")

            # 更新统计
            self.stats['analysis_count'] += 1
            self.stats['signals_by_type'][signal['action']] += 1

            # 4. ATR 动态仓位计算
            atr = self.service._calculate_atr(price_history)
            risk_per_trade = self.config.get('atr_risk_per_trade', 0.02)
            capital = self.config.get('account_capital', 10000)

            if signal['action'] != 'hold':
                position_size = (capital * risk_per_trade) / atr if atr > 0 else 0
                logger.info(f"💰 ATR 仓位管理:")
                logger.info(f"   ATR: ${atr:.2f}")
                logger.info(f"   风险/交易: {risk_per_trade:.1%}")
                logger.info(f"   建议仓位: ${position_size:.2f}")
                logger.info(f"   建议数量: {position_size / price:.6f} {symbol.split('/')[0]}")

                signal['position_size_usd'] = position_size
                signal['amount'] = position_size / price

            # 5. 相关性检查
            existing_positions = list(self.service.risk_manager.positions.keys())
            correlation_allowed, correlation_reason = self.service.correlation_manager.check_position_allowed(
                symbol, existing_positions
            )

            logger.info(f"🔗 相关性检查:")
            logger.info(f"   结果: {'✅ 通过' if correlation_allowed else '❌ 拒绝'}")
            logger.info(f"   原因: {correlation_reason}")

            # 6. 综合决策
            should_trade = (
                signal['action'] != 'hold' and
                signal['strength'] >= self.config.get('min_confidence', 0.7) and
                correlation_allowed
            )

            logger.info("=" * 60)
            if should_trade:
                logger.info(f"🎯 最终决策: {signal['action'].upper()}")
                logger.info(f"   信号强度: {signal['strength']:.2f} >= {self.config.get('min_confidence', 0.7)}")
                logger.info(f"   理由: {signal['reasoning']}")

                # 执行交易（如果启用）
                if self.auto_trade:
                    self._execute_trade(symbol, signal, price)
                else:
                    logger.info("   [仅分析模式，未执行交易]")
            else:
                logger.info(f"🚫 最终决策: HOLD")
                if signal['action'] != 'hold':
                    logger.info(f"   原因: 信号强度不足或相关性检查失败")
                self.stats['trade_rejected'] += 1

            logger.info("=" * 60)

        except Exception as e:
            logger.error(f"分析 {symbol} 时出错: {e}", exc_info=True)

    def _execute_trade(self, symbol: str, signal: Dict, price: float):
        """执行交易"""
        try:
            amount = signal.get('amount', 0)

            # 风控检查
            balance = self.service.executor.get_balance()
            allowed, reason = self.service.risk_manager.pre_trade_check(
                symbol,
                amount,
                price,
                balance,
                len(self.service.risk_manager.positions),
            )

            if not allowed:
                logger.warning(f"风控拒绝: {reason}")
                self.stats['trade_rejected'] += 1
                return

            # 执行订单
            if signal['action'] == 'buy':
                order = self.service.executor.create_market_buy_order(symbol, amount)
                logger.info(f"✅ 买入订单已创建: {order['id']}")

                # 设置止损止盈
                stop_loss = price * 0.95
                take_profit = price * 1.15
                self.service.executor.create_order_with_stops(
                    symbol, 'sell', amount, stop_loss, take_profit
                )
                logger.info(f"🎯 止损止盈: SL=${stop_loss:.2f}, TP=${take_profit:.2f}")

            elif signal['action'] == 'sell':
                order = self.service.executor.create_market_sell_order(symbol, amount)
                logger.info(f"✅ 卖出订单已创建: {order['id']}")

            self.stats['trade_executed'] += 1

        except Exception as e:
            logger.error(f"执行交易失败: {e}")
            self.stats['trade_rejected'] += 1

    def print_stats(self):
        """打印统计信息"""
        logger.info("-" * 60)
        logger.info("📊 服务状态")
        logger.info(f"   分析次数: {self.stats['analysis_count']}")
        logger.info(f"   执行交易: {self.stats['trade_executed']}")
        logger.info(f"   拒绝交易: {self.stats['trade_rejected']}")
        logger.info(f"   信号统计: Buy={self.stats['signals_by_type']['buy']}, "
                   f"Sell={self.stats['signals_by_type']['sell']}, "
                   f"Hold={self.stats['signals_by_type']['hold']}")
        logger.info("-" * 60)

    def run(self):
        """主循环"""
        self.running = True

        try:
            while self.running:
                # 检查紧急停止
                if os.path.exists('.emergency_stop'):
                    logger.critical("🚨 紧急停止文件已触发，服务停止！")
                    break

                # 分析所有交易对
                for symbol in self.symbols:
                    self.analyze_symbol(symbol)

                # 打印统计
                self.print_stats()

                # 等待下一次检查
                interval = self.config.get('check_interval', 60)
                logger.info(f"⏰ 等待 {interval} 秒后进行下一次检查...")
                time.sleep(interval)

        except KeyboardInterrupt:
            logger.info("\n收到中断信号，正在停止...")
        finally:
            self.running = False
            logger.info("专业交易服务已停止")


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='专业交易系统（重构版）')
    parser.add_argument('--symbols', nargs='+', default=['BTC/USDT'],
                       help='要监控的交易对（默认: BTC/USDT）')
    parser.add_argument('--auto-trade', action='store_true',
                       help='启用自动交易（⚠️ 谨慎使用）')

    args = parser.parse_args()

    # 检查配置
    if not os.getenv('BINANCE_API_KEY') or not os.getenv('BINANCE_API_SECRET'):
        logger.error("❌ 缺少 API 配置！请在 .env 文件中设置 BINANCE_API_KEY 和 BINANCE_API_SECRET")
        return

    # 创建并运行交易机器人
    bot = ProfessionalTradingBot(
        symbols=args.symbols,
        auto_trade=args.auto_trade,
    )

    try:
        bot.run()
    except Exception as e:
        logger.critical(f"致命错误: {e}", exc_info=True)


if __name__ == '__main__':
    main()
