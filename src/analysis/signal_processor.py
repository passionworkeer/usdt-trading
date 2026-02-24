"""
信号处理器 - 模拟信号源
"""
import logging
from typing import Dict, List, Optional
from datetime import datetime
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


class SignalSource(ABC):
    """信号源抽象基类"""

    @abstractmethod
    def get_signals(self) -> List[Dict]:
        """获取信号列表"""
        pass


class MockSignalSource(SignalSource):
    """模拟信号源（用于测试）"""

    def __init__(self):
        self.signals: List[Dict] = []

    def add_signal(self, symbol: str, action: str, amount: float,
                  price: Optional[float] = None, score: int = 5):
        """
        添加模拟信号

        Args:
            symbol: 交易对
            action: 动作 (BUY/SELL)
            amount: 数量
            price: 价格（可选）
            score: 信号评分 (1-5)
        """
        signal = {
            'symbol': symbol,
            'action': action.upper(),
            'amount': amount,
            'price': price,
            'score': score,
            'timestamp': datetime.now().isoformat(),
        }
        self.signals.append(signal)
        logger.debug(f"添加模拟信号: {signal}")

    def get_signals(self) -> List[Dict]:
        """获取所有信号并清空"""
        signals = self.signals.copy()
        self.signals.clear()
        return signals

    def clear(self):
        """清空信号"""
        self.signals.clear()


class ConfluenceAnalyzer:
    """Confluence 分析器 - 多源信号打分"""

    def __init__(self, min_score: int = 4):
        """
        初始化分析器

        Args:
            min_score: 最低执行评分 (1-5)
        """
        self.min_score = min_score

    def analyze(self, signal: Dict, market_data: Optional[Dict] = None) -> int:
        """
        分析信号并评分

        Args:
            signal: 信号字典
            market_data: 市场数据（可选）

        Returns:
            评分 (1-5)
        """
        score = signal.get('score', 3)

        # 如果有市场数据，进行额外分析
        if market_data:
            # 技术指标加分
            if market_data.get('rsi_oversold'):
                score += 1
            if market_data.get('macd_bullish'):
                score += 1
            if market_data.get('volume_surge'):
                score += 1

            # 风险减分
            if market_data.get('high_volatility'):
                score -= 1

        # 限制评分范围
        score = max(1, min(5, score))

        logger.info(f"信号评分: {score}/5 ({signal['symbol']} {signal['action']})")
        return score

    def should_execute(self, score: int) -> bool:
        """
        判断是否应该执行交易

        Args:
            score: 评分

        Returns:
            是否执行
        """
        return score >= self.min_score


class TradingBot:
    """交易机器人 - 整合所有组件"""

    def __init__(self, executor, risk_manager, signal_source: SignalSource,
                 analyzer: Optional[ConfluenceAnalyzer] = None):
        """
        初始化交易机器人

        Args:
            executor: 订单执行器
            risk_manager: 风险控制器
            signal_source: 信号源
            analyzer: Confluence 分析器（可选）
        """
        self.executor = executor
        self.risk_manager = risk_manager
        self.signal_source = signal_source
        self.analyzer = analyzer or ConfluenceAnalyzer(min_score=4)

        self.processed_count = 0
        self.executed_count = 0
        self.rejected_count = 0

        logger.info("交易机器人已初始化")

    def process_signals(self, dry_run: bool = False) -> Dict:
        """
        处理所有信号

        Args:
            dry_run: 是否模拟运行

        Returns:
            处理结果统计
        """
        signals = self.signal_source.get_signals()

        results = {
            'processed': 0,
            'executed': 0,
            'rejected': 0,
            'orders': [],
        }

        for signal in signals:
            self.processed_count += 1
            results['processed'] += 1

            try:
                # 分析信号
                score = self.analyzer.analyze(signal)

                if not self.analyzer.should_execute(score):
                    logger.info(f"信号评分过低 ({score})，跳过")
                    self.rejected_count += 1
                    results['rejected'] += 1
                    continue

                # 获取价格和账户信息
                symbol = signal['symbol']
                ticker = self.executor.get_ticker(symbol)
                price = ticker['last']

                balance = self.executor.get_balance()
                open_orders = self.executor.get_open_orders(symbol)

                # 风控检查
                allowed, reason = self.risk_manager.pre_trade_check(
                    symbol, signal['amount'], price, balance, len(open_orders)
                )

                if not allowed:
                    logger.warning(f"风控拒绝: {reason}")
                    self.rejected_count += 1
                    results['rejected'] += 1
                    continue

                # 执行交易
                if dry_run:
                    logger.info(f"[模拟] 执行: {signal['action']} {signal['amount']} {symbol}")
                    order = {'status': 'dry_run', 'symbol': symbol, **signal}
                else:
                    order = self._execute_order(signal, price)

                if order:
                    self.executed_count += 1
                    results['executed'] += 1
                    results['orders'].append(order)

                    # 记录交易
                    self.risk_manager.record_trade(
                        symbol, signal['action'], signal['amount'], price
                    )

            except Exception as e:
                logger.error(f"处理信号失败: {e}")
                results['rejected'] += 1

        return results

    def _execute_order(self, signal: Dict, price: float) -> Optional[Dict]:
        """执行订单"""
        symbol = signal['symbol']
        action = signal['action']
        amount = signal['amount']

        try:
            if action == 'BUY':
                order = self.executor.create_market_buy_order(symbol, amount)

                # 设置止损止盈
                stop_loss = self.risk_manager.get_stop_loss_price(price)
                take_profit = self.risk_manager.get_take_profit_price(price)

                try:
                    self.executor.create_oco_order(
                        symbol, 'sell', amount, take_profit, stop_loss
                    )
                except Exception as e:
                    logger.warning(f"OCO 订单失败: {e}")

                return order

            elif action == 'SELL':
                return self.executor.create_market_sell_order(symbol, amount)

        except Exception as e:
            logger.error(f"执行订单失败: {e}")
            return None

    def get_stats(self) -> Dict:
        """获取统计信息"""
        return {
            'processed': self.processed_count,
            'executed': self.executed_count,
            'rejected': self.rejected_count,
            'execution_rate': (
                self.executed_count / self.processed_count * 100
                if self.processed_count > 0 else 0
            ),
            'risk_stats': self.risk_manager.get_stats(),
        }
