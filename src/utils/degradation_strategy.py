"""
降级策略模块（Degradation Strategy）

P1-17: 当交易所不健康时采取的降级措施

策略类型：
1. 只读模式：停止交易，继续监控
2. 降低频率：减少 API 调用频率
3. 紧急平仓：立即平掉所有仓位
4. 等待恢复：暂停操作，等待交易所恢复
"""
import logging
import asyncio
from typing import Dict, Optional, List
from enum import Enum
from dataclasses import dataclass

logger = logging.getLogger(__name__)


class DegradationLevel(Enum):
    """降级级别"""
    NORMAL = "normal"  # 正常运行
    READ_ONLY = "read_only"  # 只读模式（停止新开仓）
    REDUCED_FREQUENCY = "reduced_frequency"  # 降低频率
    EMERGENCY_CLOSE = "emergency_close"  # 紧急平仓
    PAUSED = "paused"  # 完全暂停


@dataclass
class DegradationAction:
    """降级动作"""
    level: DegradationLevel
    description: str
    allow_new_positions: bool = False
    allow_monitoring: bool = True
    allow_close_positions: bool = True
    check_interval_multiplier: float = 1.0  # 检查间隔倍数


class DegradationStrategy:
    """
    降级策略管理器

    根据交易所健康状态自动调整运行策略
    """

    # 降级策略配置
    STRATEGIES: Dict[str, DegradationAction] = {
        'HEALTHY': DegradationAction(
            level=DegradationLevel.NORMAL,
            description="正常运行",
            allow_new_positions=True,
            allow_monitoring=True,
            allow_close_positions=True,
            check_interval_multiplier=1.0,
        ),
        'DEGRADED': DegradationAction(
            level=DegradationLevel.REDUCED_FREQUENCY,
            description="交易所延迟较高，降低 API 调用频率",
            allow_new_positions=True,  # 仍允许开仓，但更谨慎
            allow_monitoring=True,
            allow_close_positions=True,
            check_interval_multiplier=2.0,  # 检查间隔加倍
        ),
        'UNHEALTHY': DegradationAction(
            level=DegradationLevel.READ_ONLY,
            description="交易所不健康，停止新开仓，只监控和平仓",
            allow_new_positions=False,  # 禁止新开仓
            allow_monitoring=True,
            allow_close_positions=True,  # 允许平仓止损
            check_interval_multiplier=3.0,  # 检查间隔增加
        ),
        'CRITICAL': DegradationAction(
            level=DegradationLevel.EMERGENCY_CLOSE,
            description="交易所严重故障，考虑紧急平仓",
            allow_new_positions=False,
            allow_monitoring=True,
            allow_close_positions=True,  # 允许平仓
            check_interval_multiplier=5.0,  # 检查间隔大幅增加
        ),
    }

    def __init__(self):
        """初始化降级策略管理器"""
        self.current_level = DegradationLevel.NORMAL
        self.current_action = self.STRATEGIES['HEALTHY']
        self.level_history: List[tuple] = []  # (timestamp, level, reason)

        logger.info("✅ 降级策略管理器已初始化")

    def update_strategy(self, health_status: str) -> DegradationAction:
        """
        根据健康状态更新降级策略

        Args:
            health_status: 健康状态字符串 (HEALTHY, DEGRADED, UNHEALTHY, CRITICAL)

        Returns:
            当前降级动作
        """
        # 获取对应的策略
        new_action = self.STRATEGIES.get(
            health_status,
            self.STRATEGIES['HEALTHY']
        )

        # 检查是否需要更新
        if new_action.level != self.current_level:
            old_level = self.current_level
            self.current_level = new_action.level
            self.current_action = new_action

            # 记录历史
            self.level_history.append((
                asyncio.get_event_loop().time(),
                new_action.level,
                new_action.description
            ))

            # 发出警告
            logger.warning(f"⚠️ 降级策略变更: {old_level.value} → {new_action.level.value}")
            logger.warning(f"   原因: {new_action.description}")

        return self.current_action

    def can_open_position(self) -> bool:
        """是否允许开新仓"""
        return self.current_action.allow_new_positions

    def can_monitor(self) -> bool:
        """是否允许监控"""
        return self.current_action.allow_monitoring

    def can_close_position(self) -> bool:
        """是否允许平仓"""
        return self.current_action.allow_close_positions

    def get_check_interval_multiplier(self) -> float:
        """获取检查间隔倍数"""
        return self.current_action.check_interval_multiplier

    def should_emergency_close(self) -> bool:
        """是否应该执行紧急平仓"""
        return (
            self.current_level == DegradationLevel.EMERGENCY_CLOSE and
            self.current_action.allow_close_positions
        )

    def get_status_summary(self) -> Dict:
        """
        获取状态摘要（用于监控面板）

        Returns:
            状态摘要字典
        """
        return {
            'level': self.current_level.value,
            'description': self.current_action.description,
            'allow_new_positions': self.current_action.allow_new_positions,
            'allow_monitoring': self.current_action.allow_monitoring,
            'allow_close_positions': self.current_action.allow_close_positions,
            'check_interval_multiplier': self.current_action.check_interval_multiplier,
            'level_changes_count': len(self.level_history),
        }

    def reset(self) -> None:
        """重置到正常状态"""
        self.current_level = DegradationLevel.NORMAL
        self.current_action = self.STRATEGIES['HEALTHY']
        logger.info("🔄 降级策略已重置到正常状态")


class EmergencyHandler:
    """
    紧情况处理器

    处理交易所严重故障时的紧急操作
    """

    def __init__(self, position_manager, alerter):
        """
        初始化紧急处理器

        Args:
            position_manager: 仓位管理器
            alerter: 预警器
        """
        self.position_manager = position_manager
        self.alerter = alerter
        self.emergency_close_triggered = False

        logger.info("✅ 紧急情况处理器已初始化")

    async def handle_critical_failure(
        self,
        reason: str,
        force_close: bool = False
    ) -> Optional[str]:
        """
        处理严重故障

        Args:
            reason: 故障原因
            force_close: 是否强制平仓

        Returns:
            处理结果消息
        """
        logger.error(f"🚨 严重故障: {reason}")

        # 检查是否有持仓
        positions = self.position_manager.positions
        if not positions:
            logger.info("✅ 无持仓，跳过紧急平仓")
            return "无持仓，无需平仓"

        # 发送紧急预警
        await self.alerter.alert_system_warning(
            title="🚨 交易所严重故障",
            message=f"原因: {reason}\n"
                   f"持仓数量: {len(positions)}\n"
                   f"强制平仓: {'是' if force_close else '否'}"
        )

        if not force_close:
            logger.warning("⚠️ 不强制平仓，保持持仓")
            return "保持现有持仓"

        # 执行紧急平仓
        logger.critical("🚨 执行紧急平仓...")
        close_results = []

        for symbol, position in positions.items():
            try:
                # 市价平仓
                result = await self._emergency_close_position(position)
                close_results.append(result)
            except Exception as e:
                logger.error(f"❌ 紧急平仓失败 {symbol}: {e}")
                close_results.append(f"❌ {symbol} 平仓失败: {e}")

        self.emergency_close_triggered = True

        result_msg = f"🚨 紧急平仓完成\n" + "\n".join(close_results)
        logger.critical(result_msg)

        return result_msg

    async def _emergency_close_position(self, position) -> str:
        """
        紧急平仓单个仓位

        Args:
            position: 仓位对象

        Returns:
            平仓结果
        """
        symbol = position.symbol
        side = 'sell' if position.side.value == 'LONG' else 'buy'

        try:
            # 市价平仓
            order = self.position_manager.exchange_info.exchange.create_market_order(
                symbol=symbol,
                side=side,
                amount=position.quantity,
            )

            if order.get('status') == 'filled':
                # 记录平仓
                self.position_manager.close_position(
                    symbol=symbol,
                    price=float(order.get('average', position.entry_price)),
                    reason='EMERGENCY'
                )

                logger.critical(f"✅ 紧急平仓成功: {symbol}")
                return f"✅ {symbol} 紧急平仓成功"

            else:
                logger.error(f"❌ 紧急平仓订单未成交: {symbol}")
                return f"❌ {symbol} 订单未成交"

        except Exception as e:
            logger.error(f"❌ 紧急平仓失败 {symbol}: {e}")
            raise
