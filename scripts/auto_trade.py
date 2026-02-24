"""
自动交易主脚本
"""
#!/usr/bin/env python3
import sys
import os
import time
import signal
import logging
from pathlib import Path
from typing import Dict, Optional
from datetime import datetime

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv

from src.exchange.order_executor import OrderExecutor
from src.exchange.risk_manager import RiskManager, RiskConfig
from src.utils.logger import setup_logger

# 加载环境变量
load_dotenv()

# 设置日志
log_level = os.getenv('LOG_LEVEL', 'INFO')
log_file = os.getenv('LOG_FILE', 'logs/auto_trade.log')
logger = setup_logger('auto_trade', log_file, log_level)


class AutoTrader:
    """自动交易器"""

    def __init__(self, testnet: bool = True, dry_run: bool = False):
        """
        初始化自动交易器

        Args:
            testnet: 是否使用测试网
            dry_run: 是否模拟运行（不下单）
        """
        self.testnet = testnet
        self.dry_run = dry_run
        self.running = True

        # 初始化组件
        logger.info("初始化自动交易器...")
        logger.info(f"  测试网模式: {testnet}")
        logger.info(f"  模拟运行: {dry_run}")

        # 订单执行器
        self.executor = OrderExecutor(testnet=testnet)

        # 风险控制器
        self.risk_manager = RiskManager(config=RiskConfig(
            max_position_size=float(os.getenv('MAX_POSITION_SIZE', '1000')),
            max_daily_loss=float(os.getenv('MAX_DAILY_LOSS', '500')),
            max_open_positions=int(os.getenv('MAX_OPEN_POSITIONS', '5')),
        ))

        # 注册信号处理
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

        logger.info("自动交易器初始化完成")

    def _signal_handler(self, signum, frame):
        """处理中断信号"""
        logger.info(f"收到信号 {signum}，准备停止...")
        self.running = False

    def get_account_info(self) -> Dict:
        """
        获取账户信息

        Returns:
            账户信息字典
        """
        try:
            balance = self.executor.get_balance()
            open_orders = self.executor.get_open_orders()

            return {
                'balance': balance,
                'open_orders_count': len(open_orders),
                'open_orders': open_orders,
            }
        except Exception as e:
            logger.error(f"获取账户信息失败: {e}")
            return {}

    def process_signal(self, signal: Dict) -> Optional[Dict]:
        """
        处理单个交易信号

        Args:
            signal: 信号字典，包含 symbol, action, amount 等

        Returns:
            订单信息（如果执行成功）
        """
        symbol = signal.get('symbol')
        action = signal.get('action', '').upper()
        amount = signal.get('amount', 0)

        logger.info(f"处理信号: {action} {amount} {symbol}")

        # 验证信号
        if not symbol or not action or amount <= 0:
            logger.warning("信号参数无效，跳过")
            return None

        if action not in ['BUY', 'SELL']:
            logger.warning(f"未知的动作: {action}")
            return None

        try:
            # 获取当前价格
            ticker = self.executor.get_ticker(symbol)
            price = ticker['last']
            logger.info(f"当前价格: {symbol} = {price}")

            # 获取账户信息
            balance = self.executor.get_balance()
            open_orders = self.executor.get_open_orders(symbol)

            # 风控检查
            allowed, reason = self.risk_manager.pre_trade_check(
                symbol, amount, price, balance, len(open_orders)
            )

            if not allowed:
                logger.warning(f"风控检查失败: {reason}")
                return None

            # 模拟运行模式
            if self.dry_run:
                logger.info(f"[模拟] 执行 {action} {amount} {symbol} @ {price}")
                return {'status': 'dry_run', 'symbol': symbol, 'action': action, 'amount': amount, 'price': price}

            # 执行交易
            order = None
            if action == 'BUY':
                order = self.executor.create_market_buy_order(symbol, amount)

                # 设置止损止盈
                stop_loss_price = self.risk_manager.get_stop_loss_price(price)
                take_profit_price = self.risk_manager.get_take_profit_price(price)

                logger.info(f"设置止损止盈: SL={stop_loss_price:.2f}, TP={take_profit_price:.2f}")

                try:
                    self.executor.create_oco_order(
                        symbol=symbol,
                        side='sell',
                        amount=amount,
                        take_profit_price=take_profit_price,
                        stop_loss_price=stop_loss_price
                    )
                except Exception as e:
                    logger.warning(f"创建 OCO 订单失败（继续）: {e}")

            elif action == 'SELL':
                order = self.executor.create_market_sell_order(symbol, amount)

            if order:
                # 记录交易
                self.risk_manager.record_trade(symbol, action, amount, price)
                logger.info(f"订单执行成功: ID={order.get('id')}")

            return order

        except Exception as e:
            logger.error(f"处理信号失败: {e}")
            return None

    def run_demo_strategy(self):
        """
        运行演示策略

        演示策略：每5分钟检查一次 BTC/USDT 价格，
        如果价格下跌超过 1% 则买入
        """
        logger.info("运行演示策略...")

        symbol = 'BTC/USDT'
        last_price = None

        while self.running:
            try:
                # 获取当前价格
                ticker = self.executor.get_ticker(symbol)
                current_price = ticker['last']

                logger.info(f"{symbol} 价格: {current_price}")

                # 如果有历史价格，检查变化
                if last_price:
                    change_pct = ((current_price - last_price) / last_price) * 100
                    logger.info(f"价格变化: {change_pct:+.2f}%")

                    # 演示策略：价格下跌超过 1% 时买入
                    if change_pct < -1.0:
                        logger.info(f"触发买入信号: 价格下跌 {change_pct:.2f}%")

                        signal = {
                            'symbol': symbol,
                            'action': 'BUY',
                            'amount': 0.001,  # 买入 0.001 BTC
                        }
                        self.process_signal(signal)

                last_price = current_price

                # 打印账户状态
                account_info = self.get_account_info()
                logger.info(f"未成交订单: {account_info.get('open_orders_count', 0)}")
                logger.info(f"日盈亏: {self.risk_manager.daily_pnl:+.2f} USD")

            except Exception as e:
                logger.error(f"策略执行错误: {e}")

            # 每 5 分钟检查一次
            for _ in range(300):
                if not self.running:
                    break
                time.sleep(1)

    def run(self):
        """主循环"""
        logger.info("=" * 60)
        logger.info("自动交易器启动")
        logger.info("=" * 60)

        try:
            # 打印初始账户信息
            account_info = self.get_account_info()
            logger.info(f"账户信息: {account_info.get('open_orders_count', 0)} 个未成交订单")

            # 运行演示策略
            self.run_demo_strategy()

        except KeyboardInterrupt:
            logger.info("收到中断信号")
        except Exception as e:
            logger.error(f"运行时错误: {e}", exc_info=True)
        finally:
            logger.info("自动交易器停止")


def main():
    """主函数"""
    # 读取配置
    testnet = os.getenv('BINANCE_TESTNET', 'true').lower() == 'true'
    dry_run = os.getenv('DRY_RUN', 'false').lower() == 'true'

    # 创建交易器
    trader = AutoTrader(testnet=testnet, dry_run=dry_run)

    # 运行
    trader.run()


if __name__ == '__main__':
    main()
