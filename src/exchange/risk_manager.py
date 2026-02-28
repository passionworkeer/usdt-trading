"""
风险控制器 - 交易前检查和持续监控
"""
import os
import logging
from typing import Dict, Tuple, Optional, List
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from src.config import settings

logger = logging.getLogger(__name__)


@dataclass
class RiskConfig:
    """风控配置"""
    max_position_size: float = 1000.0  # USD
    max_daily_loss: float = 500.0  # USD
    max_open_positions: int = 5
    default_stop_loss_pct: float = -5.0  # %
    default_take_profit_pct: float = 15.0  # %
    max_trades_per_day: int = 20
    min_trade_interval: int = 60  # 秒


class RiskManager:
    """风险控制器"""

    def __init__(self, config: Optional[RiskConfig] = None):
        """
        初始化风险控制器

        Args:
            config: 风控配置（可选）
        """
        self.config = config or RiskConfig(
            max_position_size=float(os.getenv('MAX_POSITION_SIZE', '1000')),
            max_daily_loss=float(os.getenv('MAX_DAILY_LOSS', '500')),
            max_open_positions=int(os.getenv('MAX_OPEN_POSITIONS', '5')),
        )

        # 统计数据
        self.daily_pnl = 0.0
        self.daily_trades = 0
        self.last_trade_time = None
        self.positions: Dict[str, Dict] = {}
        self.last_reset_date = datetime.now().date()

        logger.info(f"风险控制器已初始化:")
        logger.info(f"  最大仓位: {self.config.max_position_size} USD")
        logger.info(f"  日损失限制: {self.config.max_daily_loss} USD")
        logger.info(f"  最大并发仓位: {self.config.max_open_positions}")

    def _reset_daily_if_needed(self):
        """每天重置统计"""
        current_date = datetime.now().date()
        if current_date > self.last_reset_date:
            logger.info(f"重置日统计数据 ({current_date})")
            self.daily_pnl = 0.0
            self.daily_trades = 0
            self.last_reset_date = current_date

    def check_position_size(self, symbol: str, amount: float, price: float,
                           balance: Dict) -> Tuple[bool, str]:
        """
        检查仓位大小是否合理

        Args:
            symbol: 交易对
            amount: 数量
            price: 价格
            balance: 账户余额

        Returns:
            (是否通过, 原因)
        """
        position_value = amount * price

        # 检查最大仓位
        if position_value > self.config.max_position_size:
            return False, f"仓位大小 {position_value:.2f} USD 超过最大限制 {self.config.max_position_size} USD"

        # 检查余额
        quote_currency = symbol.split('/')[1]
        available = balance.get(quote_currency, {}).get('free', 0)

        if position_value > available:
            return False, f"{quote_currency} 余额不足: 需要 {position_value:.2f}, 可用 {available:.2f}"

        return True, "OK"

    def check_daily_loss(self) -> Tuple[bool, str]:
        """
        检查日损失是否超限

        Returns:
            (是否通过, 原因)
        """
        self._reset_daily_if_needed()

        if self.daily_pnl < -self.config.max_daily_loss:
            return False, f"日损失限制已达: {self.daily_pnl:.2f} USD < -{self.config.max_daily_loss} USD"

        return True, "OK"

    def check_open_positions(self, current_positions: int) -> Tuple[bool, str]:
        """
        检查并发仓位数量

        Args:
            current_positions: 当前未平仓数量

        Returns:
            (是否通过, 原因)
        """
        if current_positions >= self.config.max_open_positions:
            return False, f"并发仓位已达上限: {current_positions}/{self.config.max_open_positions}"

        return True, "OK"

    def check_trade_frequency(self) -> Tuple[bool, str]:
        """
        检查交易频率

        Returns:
            (是否通过, 原因)
        """
        self._reset_daily_if_needed()

        # 检查每日交易次数
        if self.daily_trades >= self.config.max_trades_per_day:
            return False, f"每日交易次数已达上限: {self.daily_trades}/{self.config.max_trades_per_day}"

        # 检查交易间隔
        if self.last_trade_time:
            elapsed = (datetime.now() - self.last_trade_time).total_seconds()
            if elapsed < self.config.min_trade_interval:
                return False, f"交易间隔过短: {elapsed:.0f}s < {self.config.min_trade_interval}s"

        return True, "OK"

    def check_emergency_stop(self) -> Tuple[bool, str]:
        """
        检查紧急停止标志

        Returns:
            (是否通过, 原因)
        """
        if os.path.exists('.emergency_stop'):
            return False, "紧急停止标志已触发！"

        return True, "OK"

    def pre_trade_check(self, symbol: str, amount: float, price: float,
                       balance: Dict, current_positions: int) -> Tuple[bool, str]:
        """
        综合交易前检查

        Args:
            symbol: 交易对
            amount: 数量
            price: 价格
            balance: 账户余额
            current_positions: 当前未平仓数量

        Returns:
            (是否通过, 原因)
        """
        checks = [
            ("紧急停止检查", self.check_emergency_stop()),
            ("仓位大小检查", self.check_position_size(symbol, amount, price, balance)),
            ("日损失检查", self.check_daily_loss()),
            ("并发仓位检查", self.check_open_positions(current_positions)),
            ("交易频率检查", self.check_trade_frequency()),
        ]

        for check_name, (allowed, reason) in checks:
            if not allowed:
                logger.warning(f"{check_name} 失败: {reason}")
                return False, reason
            logger.debug(f"{check_name} 通过")

        return True, "所有检查通过"

    def update_pnl(self, pnl: float):
        """
        更新盈亏

        Args:
            pnl: 盈亏金额
        """
        self._reset_daily_if_needed()
        self.daily_pnl += pnl
        logger.info(f"更新日盈亏: {pnl:+.2f} USD, 累计: {self.daily_pnl:+.2f} USD")

    def record_trade(self, symbol: str, side: str, amount: float, price: float):
        """
        记录交易

        Args:
            symbol: 交易对
            side: 买卖方向
            amount: 数量
            price: 价格
        """
        self._reset_daily_if_needed()
        self.daily_trades += 1
        self.last_trade_time = datetime.now()

        logger.info(f"记录交易 #{self.daily_trades}: {side} {amount} {symbol} @ {price}")

    def add_position(self, symbol: str, position: Dict):
        """
        添加仓位

        Args:
            symbol: 交易对
            position: 仓位信息
        """
        self.positions[symbol] = position
        logger.info(f"添加仓位: {symbol}")

    def remove_position(self, symbol: str):
        """
        移除仓位

        Args:
            symbol: 交易对
        """
        if symbol in self.positions:
            del self.positions[symbol]
            logger.info(f"移除仓位: {symbol}")

    def get_stop_loss_price(self, entry_price: float,
                           stop_loss_pct: Optional[float] = None) -> float:
        """
        计算止损价格

        Args:
            entry_price: 入场价格
            stop_loss_pct: 止损百分比（可选）

        Returns:
            止损价格
        """
        pct = stop_loss_pct or self.config.default_stop_loss_pct
        return entry_price * (1 + pct / 100)

    def get_take_profit_price(self, entry_price: float,
                             take_profit_pct: Optional[float] = None) -> float:
        """
        计算止盈价格

        Args:
            entry_price: 入场价格
            take_profit_pct: 止盈百分比（可选）

        Returns:
            止盈价格
        """
        pct = take_profit_pct or self.config.default_take_profit_pct
        return entry_price * (1 + pct / 100)

    def get_stats(self) -> Dict:
        """
        获取统计数据

        Returns:
            统计字典
        """
        self._reset_daily_if_needed()
        return {
            'daily_pnl': self.daily_pnl,
            'daily_trades': self.daily_trades,
            'open_positions': len(self.positions),
            'last_trade_time': self.last_trade_time.isoformat() if self.last_trade_time else None,
            'last_reset_date': self.last_reset_date.isoformat(),
        }


class DailyLossLimiter:
    """日损失百分比限制器"""

    def __init__(self, max_loss_pct: float = 0.10, initial_capital: float = 200):
        """
        Args:
            max_loss_pct: 最大日损失百分比（默认 10%）
            initial_capital: 初始资金
        """
        self.max_loss_pct = max_loss_pct
        self.initial_capital = initial_capital
        self.daily_high = initial_capital
        self.daily_start = initial_capital
        self.last_reset = datetime.now().date()

    def update(self, current_capital: float) -> Dict:
        """更新并检查损失限制"""
        today = datetime.now().date()

        # 新的一天，重置
        if today > self.last_reset:
            self.daily_start = current_capital
            self.daily_high = current_capital
            self.last_reset = today

        # 更新高点
        if current_capital > self.daily_high:
            self.daily_high = current_capital

        # 计算当日损失
        daily_loss = (self.daily_high - current_capital) / self.daily_high
        loss_pct = daily_loss * 100

        return {
            'allowed': loss_pct < (self.max_loss_pct * 100),
            'loss_pct': loss_pct,
            'max_allowed_pct': self.max_loss_pct * 100,
            'remaining_pct': max(0, (self.max_loss_pct * 100) - loss_pct)
        }

    def can_trade(self, current_capital: float) -> bool:
        """检查是否允许交易"""
        result = self.update(current_capital)
        return result['allowed']

    def reset(self, initial_capital: float):
        """
        重置限制器

        Args:
            initial_capital: 新的初始资金
        """
        self.initial_capital = initial_capital
        self.daily_start = initial_capital
        self.daily_high = initial_capital
        self.last_reset = datetime.now().date()


class TradingCooldown:
    """交易冷却期管理器"""

    def __init__(self, min_interval_seconds: int = 3600, loss_cooldown_seconds: int = 7200):
        """
        Args:
            min_interval_seconds: 最小交易间隔（默认 1 小时）
            loss_cooldown_seconds: 连续亏损后冷却时间（默认 2 小时）
        """
        self.min_interval = timedelta(seconds=min_interval_seconds)
        self.loss_cooldown = timedelta(seconds=loss_cooldown_seconds)
        self.last_trade_time: Optional[datetime] = None
        self.consecutive_losses = 0
        self.loss_cooldown_until: Optional[datetime] = None
        self.trade_history: List[Dict] = []

    def can_trade(self) -> bool:
        """检查是否可以交易"""
        now = datetime.now()

        # 检查亏损冷却
        if self.loss_cooldown_until and now < self.loss_cooldown_until:
            return False

        # 检查最小间隔
        if self.last_trade_time and (now - self.last_trade_time) < self.min_interval:
            return False

        return True

    def on_trade_result(self, profit: float) -> None:
        """记录交易结果"""
        self.last_trade_time = datetime.now()

        trade_record = {
            'timestamp': self.last_trade_time,
            'profit': profit,
            'consecutive_losses_before': self.consecutive_losses
        }
        self.trade_history.append(trade_record)

        if profit < 0:
            self.consecutive_losses += 1
            if self.consecutive_losses >= 3:
                self.loss_cooldown_until = datetime.now() + self.loss_cooldown
                logger.warning(
                    f"触发连续亏损冷却: 连续亏损 {self.consecutive_losses} 次, "
                    f"冷却至 {self.loss_cooldown_until.strftime('%Y-%m-%d %H:%M:%S')}"
                )
        else:
            self.consecutive_losses = 0
            logger.debug(f"交易盈利，重置连续亏损计数")

    def get_status(self) -> Dict:
        """获取冷却状态"""
        now = datetime.now()
        in_loss_cooldown = (
            self.loss_cooldown_until is not None and
            now < self.loss_cooldown_until
        )

        time_since_last_trade = None
        if self.last_trade_time:
            time_since_last_trade = (now - self.last_trade_time).total_seconds()

        remaining_cooldown = None
        if in_loss_cooldown:
            remaining_cooldown = (self.loss_cooldown_until - now).total_seconds()

        return {
            'can_trade': self.can_trade(),
            'in_loss_cooldown': in_loss_cooldown,
            'remaining_cooldown_seconds': remaining_cooldown,
            'consecutive_losses': self.consecutive_losses,
            'time_since_last_trade': time_since_last_trade,
            'min_interval_seconds': self.min_interval.total_seconds(),
        }

    def force_cooldown(self, duration_seconds: int) -> None:
        """
        强制进入冷却期

        Args:
            duration_seconds: 冷却时长（秒）
        """
        self.loss_cooldown_until = datetime.now() + timedelta(seconds=duration_seconds)
        logger.warning(f"强制进入冷却期至: {self.loss_cooldown_until.strftime('%Y-%m-%d %H:%M:%S')}")

    def reset(self) -> None:
        """重置冷却器"""
        self.last_trade_time = None
        self.consecutive_losses = 0
        self.loss_cooldown_until = None
        self.trade_history = []
        logger.info("交易冷却器已重置")


if __name__ == '__main__':
    # 测试代码
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    risk_manager = RiskManager()

    # 模拟交易前检查
    balance = {'USDT': {'free': 10000}}
    allowed, reason = risk_manager.pre_trade_check(
        'BTC/USDT', 0.01, 50000, balance, 0
    )
    print(f"检查结果: {allowed}, {reason}")
