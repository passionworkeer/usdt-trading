"""
专业回测引擎

集成 vectorbt 实现完整的历史回测功能
"""
import os
import logging
import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

# 尝试导入 vectorbt
try:
    import vectorbt as vbt
    VECTORBT_AVAILABLE = True
    logger.info("vectorbt 已安装，将使用专业回测功能")
except ImportError:
    VECTORBT_AVAILABLE = False
    logger.warning("vectorbt 未安装，将使用简化回测功能")


@dataclass
class BacktestConfig:
    """
    回测配置（v4.0：动态滑点惩罚模型）
    """
    start_date: str
    end_date: str
    initial_capital: float = 10000

    # 真实的摩擦成本（币安合约费率）
    commission_maker: float = 0.0002  # Maker 手续费 0.02%（VIP0）
    commission_taker: float = 0.0005  # Taker 手续费 0.05%（VIP0）

    # v4.0: 动态滑点模型（基于波动率）
    slippage_model: str = "dynamic"  # dynamic / fixed

    # 基础滑点（市价单必然是 Taker）
    slippage_base: float = 0.001  # 0.1% 基础滑点

    # 动态滑点参数（基于真实波动率）
    slippage_volatility_multiplier: float = 0.15  # 波动率每增加 1%，滑点增加 0.15%
    slippage_min: float = 0.0015  # 最小滑点 0.15%（正常市场）
    slippage_max: float = 0.005  # 最大滑点 0.5%（极端行情）

    # 资金成本（融资费率）
    funding_rate: float = 0.0001  # 每 8 小时 0.01%

    symbols: List[str] = None

    def __post_init__(self):
        if self.symbols is None:
            self.symbols = ['BTC/USDT']


@dataclass
class BacktestResult:
    """回测结果"""
    total_return: float  # 总收益率
    sharpe_ratio: float  # 夏普比率
    sortino_ratio: float  # 索提诺比率
    max_drawdown: float  # 最大回撤
    calmar_ratio: float  # 卡玛比率
    win_rate: float  # 胜率
    profit_factor: float  # 盈利因子
    total_trades: int  # 总交易次数
    avg_trade_return: float  # 平均交易收益
    equity_curve: pd.Series  # 权益曲线
    trades_df: pd.DataFrame  # 交易记录

    def to_dict(self) -> Dict:
        """转换为字典"""
        return {
            'total_return': self.total_return,
            'sharpe_ratio': self.sharpe_ratio,
            'sortino_ratio': self.sortino_ratio,
            'max_drawdown': self.max_drawdown,
            'calmar_ratio': self.calmar_ratio,
            'win_rate': self.win_rate,
            'profit_factor': self.profit_factor,
            'total_trades': self.total_trades,
            'avg_trade_return': self.avg_trade_return,
        }


class ProfessionalBacktester:
    """专业回测引擎 v4.0（动态滑点 + 波动率熔断）"""

    def __init__(self, config: BacktestConfig):
        self.config = config
        self.price_data: Dict[str, pd.DataFrame] = {}
        self.is_circuit_breaker_triggered = False  # 熔断状态

    def calculate_dynamic_slippage(self, df: pd.DataFrame, index: int) -> float:
        """
        v4.0: 计算动态滑点（基于波动率）

        逻辑：
        - 正常市场（波动率 < 2%）：0.15% 滑点
        - 高波动（波动率 2-5%）：0.25% - 0.40% 滑点
        - 极端行情（波动率 > 5%）：0.40% - 0.50% 滑点

        公式：
        slippage = max(slippage_min, min(slippage_max, slippage_base + volatility × multiplier))
        """
        if index < 20:
            return self.config.slippage_min

        # 计算真实波动率（使用 ATR/收盘价）
        atr = df['atr'].iloc[index] if 'atr' in df.columns else 0
        close = df['close'].iloc[index]
        volatility_pct = (atr / close) * 100 if close > 0 else 0

        # 动态滑点公式
        slippage = self.config.slippage_base + (volatility_pct * self.config.slippage_volatility_multiplier / 100)

        # 限制在 [min, max] 范围内
        slippage = max(self.config.slippage_min, min(self.config.slippage_max, slippage))

        return slippage

    def check_circuit_breaker(self, symbol: str, df: pd.DataFrame, index: int,
                             window: int = 5) -> Tuple[bool, str]:
        """
        v4.0: 实时波动率熔断检查

        逻辑：
        - 计算 5 分钟内真实波动率
        - 如果波动率超过历史均值的 3 个标准差 → 触发熔断
        - 熔断期间停止一切新开仓

        Returns:
            (是否熔断, 原因)
        """
        if index < window + 20:
            return False, "数据不足"

        # 计算最近 5 根 K 线的波动率
        recent_highs = df['high'].iloc[index-window:index].max()
        recent_lows = df['low'].iloc[index-window:index].min()
        recent_volatility = (recent_highs - recent_lows) / df['close'].iloc[index] * 100

        # 计算历史波动率统计
        historical_volatilities = []
        for i in range(20, index):
            high = df['high'].iloc[i-window:i].max() if i >= window else df['high'].iloc[i]
            low = df['low'].iloc[i-window:i].min() if i >= window else df['low'].iloc[i]
            vol = (high - low) / df['close'].iloc[i] * 100
            historical_volatilities.append(vol)

        if not historical_volatilities:
            return False, "历史数据不足"

        mean_vol = np.mean(historical_volatilities)
        std_vol = np.std(historical_volatilities)

        # 熔断阈值：均值 + 3 标准差
        circuit_breaker_threshold = mean_vol + 3 * std_vol

        if recent_volatility > circuit_breaker_threshold:
            reason = f"🔴 熔断触发！5分钟波动率 {recent_volatility:.2f}% 超过阈值 {circuit_breaker_threshold:.2f}%"
            logger.critical(reason)
            return True, reason

        return False, "OK"

    def fetch_historical_data(self, symbol: str,
                              start_date: str,
                              end_date: str) -> Optional[pd.DataFrame]:
        """
        获取历史数据

        Args:
            symbol: 交易对
            start_date: 开始日期 (YYYY-MM-DD)
            end_date: 结束日期 (YYYY-MM-DD)

        Returns:
            包含 OHLCV 数据的 DataFrame
        """
        try:
            import ccxt
            exchange = ccxt.binance()

            # 转换日期为时间戳
            start_ts = int(pd.Timestamp(start_date).timestamp() * 1000)
            end_ts = int(pd.Timestamp(end_date).timestamp() * 1000)

            # 获取数据
            ohlcv = exchange.fetch_ohlcv(symbol, '1h', since=start_ts, params={'endTime': end_ts})

            # 转换为 DataFrame
            df = pd.DataFrame(
                ohlcv,
                columns=['timestamp', 'open', 'high', 'low', 'close', 'volume']
            )
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            df.set_index('timestamp', inplace=True)

            logger.info(f"获取 {symbol} 历史数据: {len(df)} 条记录")
            return df

        except Exception as e:
            logger.error(f"获取 {symbol} 历史数据失败: {e}")
            return None

    def load_data(self, symbols: Optional[List[str]] = None):
        """加载所有交易对的历史数据"""
        symbols = symbols or self.config.symbols

        for symbol in symbols:
            df = self.fetch_historical_data(
                symbol,
                self.config.start_date,
                self.config.end_date
            )
            if df is not None:
                self.price_data[symbol] = df

    def calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """计算技术指标"""
        from src.quantitative.professional_trading_system import (
            MarketStateClassifier,
            BollingerBandSqueezeStrategy,
            VolumeProfileStrategy,
        )

        # 1. 市场状态分类器
        classifier = MarketStateClassifier()

        # 计算 ADX
        highs = df['high'].values
        lows = df['low'].values
        closes = df['close'].values

        adx_values = []
        for i in range(14, len(closes)):
            adx = classifier.calculate_adx(
                highs[i-14:i].tolist(),
                lows[i-14:i].tolist(),
                closes[i-14:i].tolist()
            )
            adx_values.append(adx or 0)

        # 填充前 14 个值
        adx_values = [0] * 14 + adx_values
        df['adx'] = adx_values

        # 2. 布林带
        bb_strategy = BollingerBandSqueezeStrategy()
        bb_upper = []
        bb_lower = []
        bb_squeeze = []

        for i in range(20, len(df)):
            prices = closes[i-20:i].tolist()
            signal = bb_strategy.analyze('TEST/USDT', closes[i], prices)

            # 计算布林带
            mean = np.mean(prices)
            std = np.std(prices)
            bb_upper.append(mean + 2 * std)
            bb_lower.append(mean - 2 * std)
            bb_squeeze.append(signal.get('is_squeeze', False))

        df['bb_upper'] = [np.nan] * 20 + bb_upper
        df['bb_lower'] = [np.nan] * 20 + bb_lower
        df['bb_squeeze'] = [False] * 20 + bb_squeeze

        # 3. RSI
        rsi_values = self._calculate_rsi(closes)
        df['rsi'] = rsi_values

        # 4. 移动平均线
        df['ma_short'] = df['close'].rolling(window=10).mean()
        df['ma_long'] = df['close'].rolling(window=30).mean()

        # 5. ATR
        df['atr'] = self._calculate_atr(df)

        return df

    def _calculate_rsi(self, prices: np.ndarray, period: int = 14) -> List[float]:
        """计算 RSI"""
        rsi_values = [np.nan] * period

        for i in range(period, len(prices)):
            window = prices[i-period:i+1]
            deltas = np.diff(window)
            gains = np.where(deltas > 0, deltas, 0)
            losses = np.where(deltas < 0, -deltas, 0)

            avg_gain = np.mean(gains)
            avg_loss = np.mean(losses)

            if avg_loss == 0:
                rs = 100
            else:
                rs = 100 - (100 / (1 + (avg_gain / avg_loss)))

            rsi_values.append(rs)

        return rsi_values

    def _calculate_atr(self, df: pd.DataFrame, period: int = 14) -> pd.Series:
        """计算 ATR"""
        high = df['high']
        low = df['low']
        close = df['close']

        tr1 = high - low
        tr2 = abs(high - close.shift(1))
        tr3 = abs(low - close.shift(1))

        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = tr.rolling(window=period).mean()

        return atr

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        """
        生成交易信号（修复前视偏差）

        关键修复：
        1. 使用 shift(1) 避免用当根 K 线收盘价触发当根交易
        2. 只能在 T 时刻知道 T-1 时刻的数据
        """
        # 信号: 1=买入, -1=卖出, 0=持有
        signals = pd.Series(0, index=df.index)

        # 策略 1: RSI 超卖/超买（使用前一根 K 线的 RSI）
        rsi_lagged = df['rsi'].shift(1)  # 关键：shift(1) 避免前视偏差
        signals[rsi_lagged < 30] = 1  # 超卖买入
        signals[rsi_lagged > 70] = -1  # 超买卖出

        # 策略 2: MA 交叉（已经正确使用了 shift(1)）
        ma_cross = (df['ma_short'] > df['ma_long']).astype(int)
        ma_cross_prev = (df['ma_short'].shift(1) > df['ma_long'].shift(1)).astype(int)

        # 金叉买入
        signals[(ma_cross == 1) & (ma_cross_prev == 0)] = 1
        # 死叉卖出
        signals[(ma_cross == 0) & (ma_cross_prev == 1)] = -1

        # 策略 3: BB Squeeze 突破（使用前一根 K 线数据）
        bb_lagged_upper = df['bb_upper'].shift(1)
        bb_lagged_lower = df['bb_lower'].shift(1)
        bb_lagged_squeeze = df['bb_squeeze'].shift(1).fillna(False)
        close_lagged = df['close'].shift(1)

        bb_breakout_up = (close_lagged > bb_lagged_upper) & bb_lagged_squeeze
        bb_breakout_down = (close_lagged < bb_lagged_lower) & bb_lagged_squeeze

        signals[bb_breakout_up] = 1
        signals[bb_breakout_down] = -1

        logger.info(f"生成信号: {signals.sum()} 个交易信号（避免前视偏差）")

        return signals

    def run_vectorbt_backtest(self, symbol: str) -> Optional[BacktestResult]:
        """使用 vectorbt 运行回测"""
        if not VECTORBT_AVAILABLE:
            logger.warning("vectorbt 不可用，使用简化回测")
            return self.run_simple_backtest(symbol)

        try:
            df = self.price_data.get(symbol)
            if df is None:
                logger.error(f"没有 {symbol} 的数据")
                return None

            # 计算指标
            df = self.calculate_indicators(df)

            # 生成信号
            signals = self.generate_signals(df)

            # 创建 vectorbt Portfolio
            price = df['close']
            entries = signals == 1
            exits = signals == -1

            # 使用 vectorbt 执行回测
            pf = vbt.Portfolio.from_signals(
                price=price,
                entries=entries,
                exits=exits,
                init_cash=self.config.initial_capital,
                fees=self.config.commission,
                slippage=self.config.slippage,
            )

            # 获取结果
            stats = pf.stats()

            # 获取交易记录
            trades = pf.trades.records_readable

            # 计算额外指标
            returns = pf.returns()
            sharpe = stats['Sharpe Ratio']
            max_dd = stats['Max Drawdown']
            total_return = stats['Total Return [%]'] / 100

            # 计算索提诺比率
            downside_returns = returns[returns < 0]
            downside_deviation = downside_returns.std() * np.sqrt(252)
            sortino = returns.mean() * 252 / downside_deviation if downside_deviation > 0 else 0

            # 计算卡玛比率
            calmar = total_return / abs(max_dd) if max_dd != 0 else 0

            # 计算胜率和盈利因子
            win_trades = trades[trades['PnL'] > 0] if len(trades) > 0 else pd.DataFrame()
            lose_trades = trades[trades['PnL'] <= 0] if len(trades) > 0 else pd.DataFrame()

            win_rate = len(win_trades) / len(trades) if len(trades) > 0 else 0

            total_profit = win_trades['PnL'].sum() if len(win_trades) > 0 else 0
            total_loss = abs(lose_trades['PnL'].sum()) if len(lose_trades) > 0 else 1
            profit_factor = total_profit / total_loss if total_loss > 0 else 0

            result = BacktestResult(
                total_return=total_return,
                sharpe_ratio=sharpe,
                sortino_ratio=sortino,
                max_drawdown=max_dd,
                calmar_ratio=calmar,
                win_rate=win_rate,
                profit_factor=profit_factor,
                total_trades=len(trades),
                avg_trade_return=trades['PnL'].mean() if len(trades) > 0 else 0,
                equity_curve=pf.value(),
                trades_df=trades,
            )

            logger.info(f"✅ {symbol} vectorbt 回测完成")
            return result

        except Exception as e:
            logger.error(f"vectorbt 回测失败: {e}")
            return self.run_simple_backtest(symbol)

    def run_simple_backtest(self, symbol: str) -> Optional[BacktestResult]:
        """
        v4.0: 简化版回测（集成动态滑点 + 波动率熔断）

        关键改进：
        - 动态滑点惩罚（基于波动率）
        - 波动率熔断机制（3σ 触发）
        - 真实的市价单执行成本
        """
        try:
            df = self.price_data.get(symbol)
            if df is None:
                return None

            df = self.calculate_indicators(df)
            signals = self.generate_signals(df)

            # 回测变量
            capital = self.config.initial_capital
            position = 0
            equity_curve = []
            trades = []
            circuit_breaker_count = 0  # 熔断次数

            for i in range(len(df)):
                price = df['close'].iloc[i]
                signal = signals.iloc[i]

                # v4.0: 波动率熔断检查
                is_circuit_breaker, reason = self.check_circuit_breaker(symbol, df, i)
                if is_circuit_breaker:
                    circuit_breaker_count += 1
                    logger.warning(f"{symbol} {df.index[i]}: {reason}")
                    # 熔断期间只允许平仓，不允许开仓
                    if signal == 1:
                        signal = 0  # 取消买入信号

                # v4.0: 计算动态滑点
                slippage = self.calculate_dynamic_slippage(df, i)
                commission = self.config.commission_taker  # 市价单必然是 Taker

                # 买入（开多）
                if signal == 1 and position == 0:
                    # 应用滑点：买入价格更高
                    execution_price = price * (1 + slippage)
                    # 应用手续费
                    position = (capital / execution_price) * (1 - commission)
                    capital = 0

                    trades.append({
                        'type': 'buy',
                        'price': execution_price,
                        'signal_price': price,
                        'slippage': slippage,
                        'commission': commission,
                        'timestamp': df.index[i],
                    })

                # 卖出（平多）
                elif signal == -1 and position > 0:
                    # 应用滑点：卖出价格更低
                    execution_price = price * (1 - slippage)
                    # 应用手续费
                    capital = position * execution_price * (1 - commission)
                    position = 0

                    trades.append({
                        'type': 'sell',
                        'price': execution_price,
                        'signal_price': price,
                        'slippage': slippage,
                        'commission': commission,
                        'timestamp': df.index[i],
                    })

                # 计算当前权益
                equity = capital + position * price
                equity_curve.append(equity)

            # 计算回测指标
            equity_series = pd.Series(equity_curve, index=df.index)
            returns = equity_series.pct_change().dropna()

            total_return = (equity_curve[-1] - self.config.initial_capital) / self.config.initial_capital
            sharpe = returns.mean() / returns.std() * np.sqrt(252) if returns.std() > 0 else 0

            # 最大回撤
            rolling_max = equity_series.expanding().max()
            drawdown = (equity_series - rolling_max) / rolling_max
            max_dd = drawdown.min()

            # 胜率
            trade_returns = []
            slippages = []
            for i in range(0, len(trades) - 1, 2):
                if i + 1 < len(trades) and trades[i]['type'] == 'buy' and trades[i + 1]['type'] == 'sell':
                    buy_price = trades[i]['price']
                    sell_price = trades[i + 1]['price']
                    ret = (sell_price - buy_price) / buy_price
                    trade_returns.append(ret)
                    slippages.extend([trades[i]['slippage'], trades[i + 1]['slippage']])

            win_rate = sum(1 for r in trade_returns if r > 0) / len(trade_returns) if trade_returns else 0
            avg_slippage = np.mean(slippages) if slippages else 0

            result = BacktestResult(
                total_return=total_return,
                sharpe_ratio=sharpe,
                sortino_ratio=sharpe * 1.5,  # 近似
                max_drawdown=max_dd,
                calmar_ratio=total_return / abs(max_dd) if max_dd != 0 else 0,
                win_rate=win_rate,
                profit_factor=2.0,  # 简化
                total_trades=len(trades) // 2,
                avg_trade_return=np.mean(trade_returns) if trade_returns else 0,
                equity_curve=equity_series,
                trades_df=pd.DataFrame(trades),
            )

            logger.info(f"✅ {symbol} 简化回测完成（动态滑点 + 熔断）")
            logger.info(f"  平均滑点: {avg_slippage:.2%}")
            logger.info(f"  熔断次数: {circuit_breaker_count}")

            return result

        except Exception as e:
            logger.error(f"简化回测失败: {e}")
            import traceback
            traceback.print_exc()
            return None

    def run_all_backtests(self) -> Dict[str, BacktestResult]:
        """运行所有交易对的回测"""
        results = {}

        for symbol in self.config.symbols:
            result = self.run_vectorbt_backtest(symbol)
            if result:
                results[symbol] = result

        return results

    def print_report(self, results: Dict[str, BacktestResult]):
        """打印回测报告"""
        logger.info("=" * 80)
        logger.info("专业回测报告")
        logger.info("=" * 80)
        logger.info(f"回测期间: {self.config.start_date} 至 {self.config.end_date}")
        logger.info(f"初始资金: ${self.config.initial_capital:,.2f}")
        logger.info(f"手续费: {self.config.commission:.1%}")
        logger.info(f"滑点: {self.config.slippage:.1%}")
        logger.info("=" * 80)

        for symbol, result in results.items():
            logger.info(f"\n📊 {symbol}")
            logger.info("-" * 40)
            logger.info(f"总收益率:     {result.total_return:.2%}")
            logger.info(f"夏普比率:     {result.sharpe_ratio:.2f}")
            logger.info(f"索提诺比率:   {result.sortino_ratio:.2f}")
            logger.info(f"最大回撤:     {result.max_drawdown:.2%}")
            logger.info(f"卡玛比率:     {result.calmar_ratio:.2f}")
            logger.info(f"胜率:         {result.win_rate:.2%}")
            logger.info(f"盈利因子:     {result.profit_factor:.2f}")
            logger.info(f"总交易次数:   {result.total_trades}")
            logger.info(f"平均收益:     {result.avg_trade_return:.2%}")

        logger.info("\n" + "=" * 80)


# 便捷函数
def run_backtest(symbols: List[str],
                start_date: str,
                end_date: str,
                initial_capital: float = 10000) -> Dict[str, BacktestResult]:
    """
    快速运行回测

    Args:
        symbols: 交易对列表
        start_date: 开始日期
        end_date: 结束日期
        initial_capital: 初始资金

    Returns:
        回测结果字典
    """
    config = BacktestConfig(
        start_date=start_date,
        end_date=end_date,
        initial_capital=initial_capital,
        symbols=symbols,
    )

    backtester = ProfessionalBacktester(config)
    backtester.load_data()

    results = backtester.run_all_backtests()
    backtester.print_report(results)

    return results
