"""
风险控制器 - 交易前检查和持续监控
"""
import os
import logging
from typing import Dict, Tuple, Optional
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from dotenv import load_dotenv

load_dotenv()

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
