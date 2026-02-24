#!/usr/bin/env python3
"""
增强版 AI 交易服务
整合：多策略 + 社交媒体情绪 + 新闻 + 鲸鱼追踪 + AI 分析
"""
import sys
import os
import time
import signal
import logging
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime
from collections import deque

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv

from src.exchange.order_executor import OrderExecutor
from src.exchange.risk_manager import RiskManager, RiskConfig
from src.monitoring.price_monitor import PriceMonitor, PriceData
from src.ai.decision_engine import ClaudeDecisionEngine, TechnicalIndicators
from src.strategies.trading_strategies import (
    StrategyManager, RSIStrategy, MovingAverageCrossStrategy,
    BollingerBandsStrategy, VolumeBreakoutStrategy, create_default_strategies
)
from src.data_sources.market_intelligence import DataAggregator
from src.utils.logger import setup_logger

load_dotenv()

log_level = os.getenv('LOG_LEVEL', 'INFO')
log_file = os.getenv('LOG_FILE', 'logs/enhanced_trading.log')
logger = setup_logger('enhanced_trading', log_file, log_level)


class EnhancedTradingService:
    """增强版交易服务 - 多因素决策"""

    def __init__(self, config: Optional[Dict] = None):
        self.config = config or self._load_config()
        self.running = False

        logger.info("=" * 70)
        logger.info("增强版 AI 交易服务初始化")
        logger.info("=" * 70)

        # 核心组件
        self.executor = OrderExecutor(testnet=self.config.get('testnet', True))
        self.risk_manager = RiskManager(config=RiskConfig(
            max_position_size=self.config.get('max_position_size', 1000),
            max_daily_loss=self.config.get('max_daily_loss', 500),
            max_open_positions=self.config.get('max_open_positions', 5),
        ))

        # 价格监控
        self.price_monitor = PriceMonitor(
            executor=self.executor,
            check_interval=self.config.get('check_interval', 300)
        )

        # 交易策略
        self.strategy_manager = create_default_strategies()

        # 数据聚合器（Twitter + 新闻 + 鲸鱼）
        self.data_aggregator = DataAggregator()

        # AI 决策引擎
        self.ai_engine = ClaudeDecisionEngine()

        # 技术指标
        self.indicators = TechnicalIndicators()

        # 历史记录
        self.decision_history: deque = deque(maxlen=1000)
        self.trade_history: deque = deque(maxlen=500)

        # 统计
        self.stats = {
            'analyses_performed': 0,
            'trades_executed': 0,
            'trades_rejected': 0,
            'profitable_trades': 0,
            'total_pnl': 0.0,
        }

        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

        logger.info("增强版交易服务初始化完成")
        logger.info(f"策略数: {len(self.strategy_manager.strategies)}")
        logger.info(f"数据源: Twitter, News, Whale Alert")

    def _load_config(self) -> Dict:
        return {
            'testnet': os.getenv('BINANCE_TESTNET', 'true').lower() == 'true',
            'max_position_size': float(os.getenv('MAX_POSITION_SIZE', '1000')),
            'max_daily_loss': float(os.getenv('MAX_DAILY_LOSS', '500')),
            'max_open_positions': int(os.getenv('MAX_OPEN_POSITIONS', '5')),
            'monitor_symbols': os.getenv('MONITOR_SYMBOLS', 'BTC/USDT,ETH/USDT').split(','),
            'check_interval': int(os.getenv('CHECK_INTERVAL', '300')),
            'enable_ai': os.getenv('ENABLE_AI', 'true').lower() == 'true',
            'auto_trade': os.getenv('AUTO_TRADE', 'false').lower() == 'true',
            'enable_twitter': os.getenv('ENABLE_TWITTER', 'true').lower() == 'true',
            'enable_news': os.getenv('ENABLE_NEWS', 'true').lower() == 'true',
            'enable_whale': os.getenv('ENABLE_WHALE', 'true').lower() == 'true',
            'min_confidence': float(os.getenv('MIN_CONFIDENCE', '0.7')),
            'strategy_weights': {
                'rsi': 1.0,
                'ma_cross': 0.8,
                'bollinger': 0.9,
                'volume': 0.7,
            },
        }

    def _signal_handler(self, signum, frame):
        logger.info(f"收到信号 {signum}")
        self.stop()

    def _on_price_update(self, price_data: PriceData):
        """价格更新回调"""
        logger.debug(f"价格更新: {price_data.symbol} = ${price_data.price:,.2f}")

        if self.config.get('auto_trade'):
            self._comprehensive_analysis(price_data)

    def _comprehensive_analysis(self, price_data: PriceData):
        """
        综合分析 - 整合所有因素

        分析维度：
        1. 技术指标（RSI, MA, BB, 成交量）
        2. 价格走势和形态
        3. 社交媒体情绪（Twitter/X）
        4. 新闻情绪
        5. 鲸鱼活动
        6. AI 深度分析
        """
        symbol = price_data.symbol
        price = price_data.price

        logger.info("=" * 60)
        logger.info(f"综合分析: {symbol} @ ${price:,.2f}")
        logger.info("=" * 60)

        # 1. 获取价格历史
        price_history = self.price_monitor.get_price_history(symbol, limit=100)

        if len(price_history) < 20:
            logger.warning("历史数据不足，跳过分析")
            return

        # 2. 技术分析（多策略）
        logger.info("📊 技术分析...")
        combined_signal, individual_signals = self.strategy_manager.analyze_all(
            symbol=symbol,
            price=price,
            price_history=price_history,
            volume=price_data.volume
        )

        logger.info(f"  综合信号: {combined_signal.action.upper()} (强度: {combined_signal.strength:.2f})")
        logger.info(f"  原因: {combined_signal.reasoning}")

        for signal in individual_signals:
            logger.info(f"  [{signal.strategy}] {signal.action} ({signal.strength:.2f}): {signal.reasoning}")

        # 3. 市场情报分析
        logger.info("📱 市场情报...")

        market_data = {}
        try:
            market_data = self.data_aggregator.get_comprehensive_data(symbol)

            twitter_score = market_data['twitter_sentiment']['score']
            news_score = market_data['news_sentiment']['score']
            whale_net_flow = market_data['whale_activity']['net_flow']
            overall_sentiment = market_data['overall_sentiment']

            logger.info(f"  Twitter 情绪: {twitter_score:.2f} ({'看涨' if twitter_score > 0.5 else '看跌'})")
            logger.info(f"  新闻情绪: {news_score:.2f}")
            logger.info(f"  鲸鱼净流向: ${whale_net_flow:,.0f} ({'流出交易所=看涨' if whale_net_flow > 0 else '流入交易所=看跌'})")
            logger.info(f"  综合情绪: {overall_sentiment.upper()} (置信度: {market_data['confidence']:.2f})")

        except Exception as e:
            logger.error(f"获取市场情报失败: {e}")

        # 4. AI 深度分析
        ai_decision = None
        if self.config.get('enable_ai'):
            logger.info("🤖 AI 深度分析...")

            ai_decision = self.ai_engine.analyze_market(
                symbol=symbol,
                price=price,
                price_history=price_history,
                market_data={
                    'technical_signal': combined_signal.action,
                    'technical_strength': combined_signal.strength,
                    'social_sentiment': market_data.get('twitter_sentiment', {}),
                    'news_sentiment': market_data.get('news_sentiment', {}),
                    'whale_activity': market_data.get('whale_activity', {}),
                    'overall_sentiment': market_data.get('overall_sentiment', 'neutral'),
                    'indicators': combined_signal.indicators,
                }
            )

            logger.info(f"  AI 决策: {ai_decision.action.upper()}")
            logger.info(f"  置信度: {ai_decision.confidence:.2f}")
            logger.info(f"  风险等级: {ai_decision.risk_level}")
            logger.info(f"  分析: {ai_decision.reasoning}")

        # 5. 最终决策
        final_decision = self._make_final_decision(
            combined_signal=combined_signal,
            market_data=market_data,
            ai_decision=ai_decision
        )

        logger.info("=" * 60)
        logger.info(f"最终决策: {final_decision['action'].upper()}")
        logger.info(f"决策强度: {final_decision['strength']:.2f}")
        logger.info(f"决策理由: {final_decision['reasoning']}")
        logger.info("=" * 60)

        # 记录决策
        self.decision_history.append({
            'timestamp': datetime.now().isoformat(),
            'symbol': symbol,
            'price': price,
            'decision': final_decision,
            'technical': combined_signal.action,
            'sentiment': market_data.get('overall_sentiment', 'neutral'),
            'ai': ai_decision.action if ai_decision else 'none',
        })

        self.stats['analyses_performed'] += 1

        # 6. 执行交易
        if self._should_execute(final_decision):
            self._execute_trade(symbol, price, final_decision)

    def _make_final_decision(self, combined_signal, market_data: Dict,
                            ai_decision) -> Dict:
        """
        做出最终决策

        权重分配：
        - 技术分析: 30%
        - 市场情绪: 25%
        - 鲸鱼活动: 15%
        - AI 分析: 30%
        """
        # 初始化评分
        buy_score = 0
        sell_score = 0

        # 1. 技术分析权重
        if combined_signal.action == 'buy':
            buy_score += combined_signal.strength * 0.30
        elif combined_signal.action == 'sell':
            sell_score += combined_signal.strength * 0.30

        # 2. 市场情绪权重
        sentiment_score = market_data.get('overall_score', 0.5)
        if sentiment_score > 0.55:
            buy_score += (sentiment_score - 0.5) * 0.50  # 0.25 max
        elif sentiment_score < 0.45:
            sell_score += (0.5 - sentiment_score) * 0.50

        # 3. 鲸鱼活动权重
        whale_net_flow = market_data.get('whale_activity', {}).get('net_flow', 0)
        total_whale_volume = market_data.get('whale_activity', {}).get('total_volume_usd', 1)
        if total_whale_volume > 0:
            flow_ratio = whale_net_flow / total_whale_volume
            if flow_ratio > 0.1:  # 净流出（看涨）
                buy_score += min(0.15, flow_ratio)
            elif flow_ratio < -0.1:  # 净流入（看跌）
                sell_score += min(0.15, abs(flow_ratio))

        # 4. AI 分析权重
        if ai_decision and ai_decision.action != 'hold':
            if ai_decision.action == 'buy':
                buy_score += ai_decision.confidence * 0.30
            elif ai_decision.action == 'sell':
                sell_score += ai_decision.confidence * 0.30

        # 决策逻辑
        if buy_score > sell_score and buy_score > 0.5:
            action = 'buy'
            strength = buy_score
            reasoning = f"技术{'看涨' if combined_signal.action == 'buy' else '中性'}, 情绪{market_data.get('overall_sentiment', 'neutral')}, AI {ai_decision.action if ai_decision else 'N/A'}"
        elif sell_score > buy_score and sell_score > 0.5:
            action = 'sell'
            strength = sell_score
            reasoning = f"技术{'看跌' if combined_signal.action == 'sell' else '中性'}, 情绪{market_data.get('overall_sentiment', 'neutral')}, AI {ai_decision.action if ai_decision else 'N/A'}"
        else:
            action = 'hold'
            strength = max(buy_score, sell_score)
            reasoning = f"信号不明确 (买:{buy_score:.2f}, 卖:{sell_score:.2f})"

        # 确定交易参数
        suggested_amount = None
        stop_loss = None
        take_profit = None

        if ai_decision and action != 'hold':
            suggested_amount = ai_decision.suggested_amount
            stop_loss = ai_decision.stop_loss_pct
            take_profit = ai_decision.take_profit_pct

        # 默认值
        if stop_loss is None:
            stop_loss = -5
        if take_profit is None:
            take_profit = 15

        return {
            'action': action,
            'strength': strength,
            'reasoning': reasoning,
            'buy_score': buy_score,
            'sell_score': sell_score,
            'suggested_amount': suggested_amount,
            'stop_loss_pct': stop_loss,
            'take_profit_pct': take_profit,
        }

    def _should_execute(self, decision: Dict) -> bool:
        """判断是否应该执行交易"""
        if decision['action'] == 'hold':
            return False

        min_strength = self.config.get('min_confidence', 0.7)

        if decision['strength'] < min_strength:
            logger.info(f"决策强度不足 ({decision['strength']:.2f} < {min_strength})")
            return False

        return True

    def _execute_trade(self, symbol: str, price: float, decision: Dict):
        """执行交易"""
        try:
            balance = self.executor.get_balance()
            open_orders = self.executor.get_open_orders(symbol)

            # 计算交易量
            amount_usd = decision['suggested_amount'] or self.config.get('max_position_size', 1000)
            amount = amount_usd / price

            # 风控检查
            allowed, reason = self.risk_manager.pre_trade_check(
                symbol, amount, price, balance, len(open_orders)
            )

            if not allowed:
                logger.warning(f"风控拒绝: {reason}")
                self.stats['trades_rejected'] += 1
                return

            # 执行交易
            action = decision['action']

            if action == 'buy':
                logger.info(f"💰 执行买入: {amount:.6f} {symbol} @ ${price:,.2f}")

                order = self.executor.create_market_buy_order(symbol, amount)
                logger.info(f"✅ 订单已创建: {order.get('id')}")

                # 设置止损止盈
                sl_price = price * (1 + decision['stop_loss_pct'] / 100)
                tp_price = price * (1 + decision['take_profit_pct'] / 100)

                try:
                    self.executor.create_oco_order(
                        symbol=symbol,
                        side='sell',
                        amount=amount,
                        take_profit_price=tp_price,
                        stop_loss_price=sl_price
                    )
                    logger.info(f"🎯 止损止盈已设置: SL=${sl_price:,.2f}, TP=${tp_price:,.2f}")
                except Exception as e:
                    logger.warning(f"OCO 订单失败: {e}")

                self.risk_manager.record_trade(symbol, 'BUY', amount, price)
                self.stats['trades_executed'] += 1

            elif action == 'sell':
                logger.info(f"💸 执行卖出: {amount:.6f} {symbol} @ ${price:,.2f}")

                order = self.executor.create_market_sell_order(symbol, amount)
                logger.info(f"✅ 订单已创建: {order.get('id')}")

                self.risk_manager.record_trade(symbol, 'SELL', amount, price)
                self.stats['trades_executed'] += 1

            # 记录交易
            self.trade_history.append({
                'timestamp': datetime.now().isoformat(),
                'symbol': symbol,
                'action': action,
                'amount': amount,
                'price': price,
                'decision': decision,
            })

        except Exception as e:
            logger.error(f"交易执行失败: {e}")
            self.stats['trades_rejected'] += 1

    def start(self, symbols: Optional[List[str]] = None):
        """启动服务"""
        symbols = symbols or self.config.get('monitor_symbols', ['BTC/USDT'])

        logger.info("=" * 70)
        logger.info("🚀 启动增强版 AI 交易服务")
        logger.info("=" * 70)
        logger.info(f"监控: {symbols}")
        logger.info(f"自动交易: {self.config.get('auto_trade', False)}")
        logger.info(f"AI 分析: {self.config.get('enable_ai', True)}")
        logger.info(f"测试网: {self.config.get('testnet', True)}")

        self.running = True

        self.price_monitor.set_symbols(symbols)
        self.price_monitor.add_price_callback(self._on_price_update)
        self.price_monitor.start()

        logger.info("服务已启动，按 Ctrl+C 停止")
        logger.info("=" * 70)

        try:
            while self.running:
                time.sleep(60)
                self._print_status()
        except KeyboardInterrupt:
            logger.info("收到中断信号")
        finally:
            self.stop()

    def stop(self):
        """停止服务"""
        if not self.running:
            return

        logger.info("停止服务...")
        self.running = False
        self.price_monitor.stop()
        self._print_final_report()
        logger.info("服务已停止")

    def _print_status(self):
        """打印状态"""
        risk_stats = self.risk_manager.get_stats()

        logger.info("-" * 60)
        logger.info(f"📊 服务状态")
        logger.info(f"  分析次数: {self.stats['analyses_performed']}")
        logger.info(f"  执行交易: {self.stats['trades_executed']}")
        logger.info(f"  拒绝交易: {self.stats['trades_rejected']}")
        logger.info(f"  日盈亏: {risk_stats['daily_pnl']:+.2f} USD")
        logger.info("-" * 60)

    def _print_final_report(self):
        """打印最终报告"""
        logger.info("=" * 70)
        logger.info("📋 服务报告")
        logger.info("=" * 70)
        logger.info(f"总分析次数: {self.stats['analyses_performed']}")
        logger.info(f"总执行交易: {self.stats['trades_executed']}")
        logger.info(f"总拒绝交易: {self.stats['trades_rejected']}")
        logger.info(f"决策历史: {len(self.decision_history)} 条")
        logger.info(f"交易历史: {len(self.trade_history)} 条")
        logger.info("=" * 70)


def main():
    import argparse

    parser = argparse.ArgumentParser(description='Enhanced AI Trading Service')
    parser.add_argument('--symbols', nargs='+', help='Trading pairs')
    parser.add_argument('--auto-trade', action='store_true', help='Enable auto trading')
    parser.add_argument('--testnet', action='store_true', default=True, help='Use testnet')
    parser.add_argument('--no-ai', action='store_true', help='Disable AI')

    args = parser.parse_args()

    config = {
        'testnet': args.testnet,
        'auto_trade': args.auto_trade,
        'enable_ai': not args.no_ai,
    }

    service = EnhancedTradingService(config=config)
    service.start(symbols=args.symbols)


if __name__ == '__main__':
    main()
