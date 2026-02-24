#!/usr/bin/env python3
"""
持续运行的 AI 交易服务
整合：价格监控 + AI 决策 + 自动交易 + 风险控制
"""
import sys
import os
import time
import signal
import logging
import json
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv

from src.exchange.order_executor import OrderExecutor
from src.exchange.risk_manager import RiskManager, RiskConfig
from src.monitoring.price_monitor import PriceMonitor, PriceData
from src.ai.decision_engine import ClaudeDecisionEngine, TechnicalIndicators
from src.utils.logger import setup_logger

load_dotenv()

# 设置日志
log_level = os.getenv('LOG_LEVEL', 'INFO')
log_file = os.getenv('LOG_FILE', 'logs/trading_service.log')
logger = setup_logger('trading_service', log_file, log_level)


class TradingService:
    """持续运行的 AI 交易服务"""

    def __init__(self, config: Optional[Dict] = None):
        """
        初始化交易服务

        Args:
            config: 配置字典（可选）
        """
        self.config = config or self._load_config_from_env()
        self.running = False

        # 初始化组件
        logger.info("=" * 60)
        logger.info("初始化 AI 交易服务")
        logger.info("=" * 60)

        # 订单执行器
        self.executor = OrderExecutor(
            testnet=self.config.get('testnet', True)
        )

        # 风险控制器
        self.risk_manager = RiskManager(config=RiskConfig(
            max_position_size=self.config.get('max_position_size', 1000),
            max_daily_loss=self.config.get('max_daily_loss', 500),
            max_open_positions=self.config.get('max_open_positions', 5),
            default_stop_loss_pct=self.config.get('default_stop_loss_pct', -5),
            default_take_profit_pct=self.config.get('default_take_profit_pct', 15),
        ))

        # 价格监控器
        self.price_monitor = PriceMonitor(
            executor=self.executor,
            check_interval=self.config.get('check_interval', 300)
        )

        # AI 决策引擎
        self.ai_engine = ClaudeDecisionEngine()

        # 技术指标计算器
        self.indicators = TechnicalIndicators()

        # 统计
        self.stats = {
            'decisions_made': 0,
            'trades_executed': 0,
            'trades_rejected': 0,
            'ai_calls': 0,
            'errors': 0,
        }

        # 注册信号处理
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

        logger.info("交易服务初始化完成")

    def _load_config_from_env(self) -> Dict:
        """从环境变量加载配置"""
        return {
            'testnet': os.getenv('BINANCE_TESTNET', 'true').lower() == 'true',
            'max_position_size': float(os.getenv('MAX_POSITION_SIZE', '1000')),
            'max_daily_loss': float(os.getenv('MAX_DAILY_LOSS', '500')),
            'max_open_positions': int(os.getenv('MAX_OPEN_POSITIONS', '5')),
            'default_stop_loss_pct': float(os.getenv('DEFAULT_STOP_LOSS_PCT', '-5')),
            'default_take_profit_pct': float(os.getenv('DEFAULT_TAKE_PROFIT_PCT', '15')),
            'monitor_symbols': os.getenv('MONITOR_SYMBOLS', 'BTC/USDT,ETH/USDT').split(','),
            'check_interval': int(os.getenv('CHECK_INTERVAL', '300')),
            'enable_ai': os.getenv('ENABLE_AI', 'true').lower() == 'true',
            'auto_trade': os.getenv('AUTO_TRADE', 'false').lower() == 'true',
            'min_confidence': float(os.getenv('MIN_CONFIDENCE', '0.7')),
        }

    def _signal_handler(self, signum, frame):
        """处理中断信号"""
        logger.info(f"收到信号 {signum}，准备停止...")
        self.stop()

    def _on_price_update(self, price_data: PriceData):
        """
        价格更新回调

        Args:
            price_data: 价格数据
        """
        logger.debug(f"价格更新: {price_data.symbol} = {price_data.price}")

        # 如果启用了自动交易，进行 AI 分析
        if self.config.get('auto_trade') and self.config.get('enable_ai'):
            self._analyze_and_trade(price_data)

    def _analyze_and_trade(self, price_data: PriceData):
        """
        AI 分析并执行交易

        Args:
            price_data: 价格数据
        """
        symbol = price_data.symbol
        price = price_data.price

        # 获取价格历史
        price_history = self.price_monitor.get_price_history(symbol, limit=100)

        if len(price_history) < 10:
            logger.debug(f"历史数据不足，跳过分析: {symbol}")
            return

        try:
            # 计算技术指标
            rsi = self.indicators.calculate_rsi(price_history)
            sma_20 = self.indicators.calculate_sma(price_history, 20)
            trend = self.indicators.detect_trend(price_history)

            market_data = {
                'rsi': rsi,
                'sma_20': sma_20,
                'trend': trend,
                'volume': price_data.volume,
                'change_24h': price_data.change_24h,
            }

            # 调用 AI 决策
            decision = self.ai_engine.analyze_market(
                symbol=symbol,
                price=price,
                price_history=price_history,
                market_data=market_data
            )

            self.stats['decisions_made'] += 1

            logger.info(f"AI 决策: {symbol} -> {decision.action} "
                       f"(置信度: {decision.confidence:.2f}, 风险: {decision.risk_level})")
            logger.info(f"  原因: {decision.reasoning}")

            # 判断是否执行
            if not self.ai_engine.should_execute_trade(
                decision, self.config.get('min_confidence', 0.7)
            ):
                logger.info(f"不满足执行条件，跳过")
                self.stats['trades_rejected'] += 1
                return

            # 执行交易
            self._execute_decision(symbol, price, decision)

        except Exception as e:
            logger.error(f"AI 分析失败: {e}")
            self.stats['errors'] += 1

    def _execute_decision(self, symbol: str, price: float, decision):
        """
        执行交易决策

        Args:
            symbol: 交易对
            price: 当前价格
            decision: 交易决策
        """
        try:
            # 获取账户信息
            balance = self.executor.get_balance()
            open_orders = self.executor.get_open_orders(symbol)

            # 确定交易金额
            amount_usd = decision.suggested_amount or self.config.get('max_position_size', 100)
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
            if decision.action == 'buy':
                logger.info(f"执行买入: {symbol} 数量={amount:.6f}")

                order = self.executor.create_market_buy_order(symbol, amount)
                logger.info(f"订单已创建: {order.get('id')}")

                # 设置止损止盈
                stop_loss_pct = decision.stop_loss_pct or -5
                take_profit_pct = decision.take_profit_pct or 15

                stop_loss = price * (1 + stop_loss_pct / 100)
                take_profit = price * (1 + take_profit_pct / 100)

                try:
                    self.executor.create_oco_order(
                        symbol=symbol,
                        side='sell',
                        amount=amount,
                        take_profit_price=take_profit,
                        stop_loss_price=stop_loss
                    )
                    logger.info(f"止损止盈已设置: SL={stop_loss:.2f}, TP={take_profit:.2f}")
                except Exception as e:
                    logger.warning(f"OCO 订单失败: {e}")

                # 记录交易
                self.risk_manager.record_trade(symbol, 'BUY', amount, price)
                self.stats['trades_executed'] += 1

            elif decision.action == 'sell':
                logger.info(f"执行卖出: {symbol} 数量={amount:.6f}")

                order = self.executor.create_market_sell_order(symbol, amount)
                logger.info(f"订单已创建: {order.get('id')}")

                self.risk_manager.record_trade(symbol, 'SELL', amount, price)
                self.stats['trades_executed'] += 1

        except Exception as e:
            logger.error(f"交易执行失败: {e}")
            self.stats['errors'] += 1

    def start(self, symbols: Optional[List[str]] = None):
        """
        启动交易服务

        Args:
            symbols: 监控的交易对列表（可选）
        """
        symbols = symbols or self.config.get('monitor_symbols', ['BTC/USDT'])

        logger.info("=" * 60)
        logger.info("启动 AI 交易服务")
        logger.info("=" * 60)
        logger.info(f"监控交易对: {symbols}")
        logger.info(f"自动交易: {self.config.get('auto_trade', False)}")
        logger.info(f"AI 决策: {self.config.get('enable_ai', True)}")
        logger.info(f"测试网模式: {self.config.get('testnet', True)}")

        self.running = True

        # 设置监控交易对
        self.price_monitor.set_symbols(symbols)

        # 添加价格更新回调
        self.price_monitor.add_price_callback(self._on_price_update)

        # 启动价格监控
        self.price_monitor.start()

        logger.info("交易服务已启动，按 Ctrl+C 停止")

        # 主循环
        try:
            while self.running:
                # 每 60 秒打印一次状态
                time.sleep(60)
                self._print_status()

        except KeyboardInterrupt:
            logger.info("收到中断信号")
        finally:
            self.stop()

    def stop(self):
        """停止交易服务"""
        if not self.running:
            return

        logger.info("停止交易服务...")
        self.running = False
        self.price_monitor.stop()
        self._print_final_report()
        logger.info("交易服务已停止")

    def _print_status(self):
        """打印当前状态"""
        risk_stats = self.risk_manager.get_stats()
        monitor_stats = self.price_monitor.get_stats()

        logger.info("-" * 40)
        logger.info(f"服务状态:")
        logger.info(f"  决策次数: {self.stats['decisions_made']}")
        logger.info(f"  执行交易: {self.stats['trades_executed']}")
        logger.info(f"  拒绝交易: {self.stats['trades_rejected']}")
        logger.info(f"  日盈亏: {risk_stats['daily_pnl']:+.2f} USD")
        logger.info(f"  监控状态: {monitor_stats['monitored_symbols']}")
        logger.info("-" * 40)

    def _print_final_report(self):
        """打印最终报告"""
        logger.info("=" * 60)
        logger.info("交易服务报告")
        logger.info("=" * 60)
        logger.info(f"总决策次数: {self.stats['decisions_made']}")
        logger.info(f"总执行交易: {self.stats['trades_executed']}")
        logger.info(f"总拒绝交易: {self.stats['trades_rejected']}")
        logger.info(f"总错误次数: {self.stats['errors']}")
        logger.info("=" * 60)


def main():
    """主函数"""
    # 从命令行参数读取交易对
    import argparse

    parser = argparse.ArgumentParser(description='AI Trading Service')
    parser.add_argument('--symbols', nargs='+', default=None,
                       help='Trading pairs to monitor (e.g., BTC/USDT ETH/USDT)')
    parser.add_argument('--auto-trade', action='store_true',
                       help='Enable automatic trading')
    parser.add_argument('--testnet', action='store_true', default=True,
                       help='Use testnet (default: True)')
    parser.add_argument('--no-ai', action='store_true',
                       help='Disable AI decisions')

    args = parser.parse_args()

    # 配置
    config = {
        'testnet': args.testnet,
        'auto_trade': args.auto_trade or os.getenv('AUTO_TRADE', 'false').lower() == 'true',
        'enable_ai': not args.no_ai,
    }

    # 创建并启动服务
    service = TradingService(config=config)
    service.start(symbols=args.symbols)


if __name__ == '__main__':
    main()
