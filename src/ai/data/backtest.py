"""
回测引擎模块

提供完整的回测功能：
- 历史数据回测
- 策略信号生成
- 资金管理模拟
- 性能指标计算
- 策略对比分析

参考: qlib backtest 模块
"""
import logging
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)


class PositionSide(Enum):
    """持仓方向"""
    LONG = 1
    SHORT = -1
    FLAT = 0


@dataclass
class Trade:
    """交易记录"""
    timestamp: datetime
    side: PositionSide
    entry_price: float
    exit_price: float = 0.0
    quantity: float = 0.0
    pnl: float = 0.0
    pnl_pct: float = 0.0
    commission: float = 0.0
    reason: str = ""


@dataclass
class Position:
    """持仓"""
    side: PositionSide
    entry_price: float
    quantity: float
    entry_time: datetime
    stop_loss: float = 0.0
    take_profit: float = 0.0


@dataclass
class BacktestResult:
    """回测结果"""
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    win_rate: float = 0.0
    total_pnl: float = 0.0
    total_pnl_pct: float = 0.0
    max_drawdown: float = 0.0
    max_drawdown_pct: float = 0.0
    sharpe_ratio: float = 0.0
    sortino_ratio: float = 0.0
    calmar_ratio: float = 0.0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    profit_factor: float = 0.0
    trades: List[Trade] = field(default_factory=list)
    equity_curve: pd.Series = None
    returns: pd.Series = None


class BacktestEngine:
    """
    回测引擎

    支持：
    - 多空交易
    - 止损止盈
    - 手续费计算
    - 滑点模拟
    - 资金管理
    """

    def __init__(self,
                 initial_capital: float = 10000,
                 commission_rate: float = 0.0004,
                 slippage: float = 0.0005,
                 leverage: float = 1.0):
        """
        初始化回测引擎

        Args:
            initial_capital: 初始资金
            commission_rate: 手续费率 (Binance futures Maker 0.02%)
            slippage: 滑点率
            leverage: 杠杆倍数
        """
        self.initial_capital = initial_capital
        self.commission_rate = commission_rate
        self.slippage = slippage
        self.leverage = leverage

        self.capital = initial_capital
        self.position: Optional[Position] = None
        self.trades: List[Trade] = []
        self.equity_curve: List[float] = [initial_capital]

    def reset(self):
        """重置状态"""
        self.capital = self.initial_capital
        self.position = None
        self.trades = []
        self.equity_curve = [self.initial_capital]

    def open_position(self, timestamp: datetime, side: PositionSide,
                     price: float, quantity: float,
                     stop_loss: float = 0.0, take_profit: float = 0.0) -> bool:
        """
        开仓

        Args:
            timestamp: 时间戳
            side: 持仓方向
            price: 开仓价格
            quantity: 仓位数量
            stop_loss: 止损价格
            take_profit: 止盈价格

        Returns:
            是否成功
        """
        if self.position is not None:
            logger.warning(f"Already in position, cannot open new position")
            return False

        # 计算实际成交价格（考虑滑点）
        if side == PositionSide.LONG:
            execution_price = price * (1 + self.slippage)
        else:
            execution_price = price * (1 - self.slippage)

        # 计算手续费
        notional = execution_price * quantity
        commission = notional * self.commission_rate

        # 检查资金
        required = notional / self.leverage
        if required > self.capital:
            logger.warning(f"Insufficient capital: {required} > {self.capital}")
            return False

        # 扣除手续费
        self.capital -= commission

        # 创建持仓
        self.position = Position(
            side=side,
            entry_price=execution_price,
            quantity=quantity,
            entry_time=timestamp,
            stop_loss=stop_loss,
            take_profit=take_profit
        )

        logger.info(f"Opened {side.name} position at {execution_price}, qty={quantity}")
        return True

    def close_position(self, timestamp: datetime, price: float,
                       reason: str = "") -> bool:
        """
        平仓

        Args:
            timestamp: 时间戳
            price: 平仓价格
            reason: 平仓原因

        Returns:
            是否成功
        """
        if self.position is None:
            logger.warning("No position to close")
            return False

        # 计算实际成交价格（考虑滑点）
        if self.position.side == PositionSide.LONG:
            execution_price = price * (1 - self.slippage)
        else:
            execution_price = price * (1 + self.slippage)

        # 计算盈亏
        if self.position.side == PositionSide.LONG:
            pnl = (execution_price - self.position.entry_price) * self.position.quantity
        else:
            pnl = (self.position.entry_price - execution_price) * self.position.quantity

        # 计算手续费
        notional = execution_price * self.position.quantity
        commission = notional * self.commission_rate

        # 更新资金
        self.capital += pnl - commission

        # 记录交易
        trade = Trade(
            timestamp=timestamp,
            side=self.position.side,
            entry_price=self.position.entry_price,
            exit_price=execution_price,
            quantity=self.position.quantity,
            pnl=pnl - commission,
            pnl_pct=pnl / (self.position.entry_price * self.position.quantity) * 100,
            commission=commission,
            reason=reason
        )
        self.trades.append(trade)

        logger.info(f"Closed {self.position.side.name} position at {execution_price}, PnL={pnl:.2f}")

        self.position = None
        return True

    def check_stops(self, current_time: datetime, current_price: float) -> Optional[str]:
        """检查是否触发止损止盈"""
        if self.position is None:
            return None

        triggered = None

        # 检查止损
        if self.position.stop_loss > 0:
            if self.position.side == PositionSide.LONG:
                if current_price <= self.position.stop_loss:
                    triggered = "stop_loss"
            else:
                if current_price >= self.position.stop_loss:
                    triggered = "stop_loss"

        # 检查止盈
        if triggered is None and self.position.take_profit > 0:
            if self.position.side == PositionSide.LONG:
                if current_price >= self.position.take_profit:
                    triggered = "take_profit"
            else:
                if current_price <= self.position.take_profit:
                    triggered = "take_profit"

        if triggered:
            self.close_position(current_time, current_price, triggered)

        return triggered

    def update_equity(self):
        """更新权益曲线"""
        if self.position is not None:
            # 估算当前权益（未实现盈亏）
            # 这里简化处理，不计算未实现盈亏
            self.equity_curve.append(self.capital)
        else:
            self.equity_curve.append(self.capital)

    def get_result(self) -> BacktestResult:
        """获取回测结果"""
        if not self.trades:
            return BacktestResult()

        wins = [t for t in self.trades if t.pnl > 0]
        losses = [t for t in self.trades if t.pnl <= 0]

        total_wins = sum(t.pnl for t in wins)
        total_losses = abs(sum(t.pnl for t in losses))

        # 计算权益曲线
        equity = pd.Series(self.equity_curve)

        # 计算收益率序列
        returns = equity.pct_change().dropna()

        # 计算最大回撤
        cummax = equity.cummax()
        drawdown = (equity - cummax) / cummax
        max_drawdown = drawdown.min()
        max_drawdown_pct = max_drawdown * 100

        # 计算夏普比率
        if returns.std() > 0:
            sharpe_ratio = returns.mean() / returns.std() * np.sqrt(252 * 24)  # 假设小时数据
        else:
            sharpe_ratio = 0

        # 计算索提诺比率
        downside_returns = returns[returns < 0]
        if len(downside_returns) > 0 and downside_returns.std() > 0:
            sortino_ratio = returns.mean() / downside_returns.std() * np.sqrt(252 * 24)
        else:
            sortino_ratio = 0

        # 计算卡尔玛比率 (年化收益 / 最大回撤)
        if max_drawdown != 0:
            total_return = (self.capital - self.initial_capital) / self.initial_capital
            # 假设数据是小时级别的
            hours = len(self.equity_curve)
            years = hours / (24 * 365)
            annualized_return = (1 + total_return) ** (1 / years) - 1 if years > 0 else 0
            calmar_ratio = annualized_return / abs(max_drawdown)
        else:
            calmar_ratio = 0

        return BacktestResult(
            total_trades=len(self.trades),
            winning_trades=len(wins),
            losing_trades=len(losses),
            win_rate=len(wins) / len(self.trades) * 100 if self.trades else 0,
            total_pnl=self.capital - self.initial_capital,
            total_pnl_pct=(self.capital - self.initial_capital) / self.initial_capital * 100,
            max_drawdown=max_drawdown,
            max_drawdown_pct=max_drawdown_pct,
            sharpe_ratio=sharpe_ratio,
            sortino_ratio=sortino_ratio,
            calmar_ratio=calmar_ratio,
            avg_win=total_wins / len(wins) if wins else 0,
            avg_loss=total_losses / len(losses) if losses else 0,
            profit_factor=total_wins / total_losses if total_losses > 0 else float('inf'),
            trades=self.trades,
            equity_curve=equity,
            returns=returns
        )


class StrategyBacktester:
    """策略回测器"""

    def __init__(self, engine: BacktestEngine):
        self.engine = engine

    def run(self, df: pd.DataFrame,
            signals: pd.DataFrame,
            position_size: float = 0.1,
            stop_loss_pct: float = 0.02,
            take_profit_pct: float = 0.06) -> BacktestResult:
        """
        运行回测

        Args:
            df: OHLCV 数据
            signals: 信号 DataFrame，需包含 'signal' 列 (1=buy, -1=sell, 0=hold)
            position_size: 仓位大小 (占总资金比例)
            stop_loss_pct: 止损百分比
            take_profit_pct: 止盈百分比

        Returns:
            回测结果
        """
        self.engine.reset()

        for i in range(len(df)):
            current_time = df.index[i]
            current_price = df.iloc[i]['close']

            # 检查止损止盈
            self.engine.check_stops(current_time, current_price)

            # 获取信号
            if i < len(signals):
                signal = signals.iloc[i]['signal']
            else:
                signal = 0

            # 执行交易
            if signal == 1 and self.engine.position is None:
                # 买入信号
                quantity = (self.engine.capital * position_size * self.engine.leverage) / current_price
                stop_loss = current_price * (1 - stop_loss_pct)
                take_profit = current_price * (1 + take_profit_pct)

                self.engine.open_position(
                    current_time, PositionSide.LONG, current_price,
                    quantity, stop_loss, take_profit
                )

            elif signal == -1 and self.engine.position is not None:
                # 卖出信号
                self.engine.close_position(current_time, current_price, "signal")

            # 更新权益
            self.engine.update_equity()

        # 平掉最后持仓
        if self.engine.position is not None:
            final_price = df.iloc[-1]['close']
            self.engine.close_position(df.index[-1], final_price, "end")

        return self.engine.get_result()

    def run_advanced_strategy(self, df: pd.DataFrame,
                             strategy,
                             position_size: float = 0.1) -> BacktestResult:
        """
        使用高级策略运行回测

        Args:
            df: OHLCV 数据
            strategy: 策略实例 (需有 analyze 方法)
            position_size: 仓位大小

        Returns:
            回测结果
        """
        self.engine.reset()

        for i in range(len(df)):
            if i < 50:  # 预热期
                self.engine.update_equity()
                continue

            current_time = df.index[i]
            current_price = df.iloc[i]['close']
            current_df = df.iloc[:i+1]

            # 检查止损止盈
            self.engine.check_stops(current_time, current_price)

            # 获取策略信号
            try:
                signal = strategy.analyze(current_df)
            except Exception as e:
                logger.error(f"Strategy error: {e}")
                self.engine.update_equity()
                continue

            # 执行交易
            if signal.signal_type.value == 1 and self.engine.position is None:
                quantity = (self.engine.capital * position_size * self.engine.leverage) / current_price

                sl = signal.stop_loss if signal.stop_loss else current_price * 0.98
                tp = signal.take_profit if signal.take_profit else current_price * 1.06

                self.engine.open_position(
                    current_time, PositionSide.LONG, current_price,
                    quantity, sl, tp
                )

            elif signal.signal_type.value == -1 and self.engine.position is not None:
                self.engine.close_position(current_time, current_price, signal.reason)

            # 更新权益
            self.engine.update_equity()

        # 平掉最后持仓
        if self.engine.position is not None:
            final_price = df.iloc[-1]['close']
            self.engine.close_position(df.index[-1], final_price, "end")

        return self.engine.get_result()


def create_engine(initial_capital: float = 10000,
                 commission_rate: float = 0.0004,
                 slippage: float = 0.0005,
                 leverage: float = 1.0) -> BacktestEngine:
    """创建回测引擎"""
    return BacktestEngine(initial_capital, commission_rate, slippage, leverage)


def run_strategy_backtest(df: pd.DataFrame,
                          strategy,
                          initial_capital: float = 10000,
                          position_size: float = 0.1) -> BacktestResult:
    """
    快速运行策略回测

    Args:
        df: OHLCV 数据
        strategy: 策略实例
        initial_capital: 初始资金
        position_size: 仓位大小

    Returns:
        回测结果
    """
    engine = create_engine(initial_capital)
    tester = StrategyBacktester(engine)
    return tester.run_advanced_strategy(df, strategy, position_size)


def compare_strategies(df: pd.DataFrame,
                      strategies: Dict[str, Any],
                      initial_capital: float = 10000) -> pd.DataFrame:
    """
    对比多个策略

    Args:
        df: OHLCV 数据
        strategies: 策略字典 {name: strategy_instance}
        initial_capital: 初始资金

    Returns:
        对比结果 DataFrame
    """
    results = []

    for name, strategy in strategies.items():
        logger.info(f"Backtesting strategy: {name}")
        result = run_strategy_backtest(df, strategy, initial_capital)

        results.append({
            'strategy': name,
            'total_trades': result.total_trades,
            'win_rate': result.win_rate,
            'total_pnl_pct': result.total_pnl_pct,
            'max_drawdown_pct': result.max_drawdown_pct,
            'sharpe_ratio': result.sharpe_ratio,
            'sortino_ratio': result.sortino_ratio,
            'profit_factor': result.profit_factor,
        })

    return pd.DataFrame(results)
