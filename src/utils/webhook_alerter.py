"""
v5.3: Webhook 预警系统（Telegram / Discord）

关键节点推送：
1. 🎯 发现三重共振，开始挂单等待回踩
2. 💥 挂单成交 / 动量追入成交
3. ⏱️ 触发 12 小时时间止损 / 触发被动强平缓冲退出
4. 💰 触发 ROE 移动止盈，完成猎杀
"""
import logging
import os
import asyncio
from typing import Optional, Dict
from dataclasses import dataclass
from enum import Enum
import aiohttp

logger = logging.getLogger(__name__)


class AlertType(Enum):
    """预警类型"""
    RESONANCE_LOCKED = "RESONANCE_LOCKED"  # 三重共振锁定
    ORDER_FILLED = "ORDER_FILLED"  # 订单成交（挂单/动量追入）
    STOP_LOSS = "STOP_LOSS"  # 爆仓线止损
    TIME_STOP = "TIME_STOP"  # 12 小时时间止损
    TRAILING_STOP = "TRAILING_STOP"  # 移动止盈完成
    EMERGENCY_CLOSE = "EMERGENCY_CLOSE"  # 紧急平仓
    SYSTEM_WARNING = "SYSTEM_WARNING"  # 系统警告


@dataclass
class AlertMessage:
    """预警消息"""
    alert_type: AlertType
    symbol: str
    side: str  # 'LONG' or 'SHORT'
    message: str
    details: Optional[Dict] = None


class WebhookAlerter:
    """
    v5.3 Webhook 预警器（Telegram / Discord）

    支持多个预警渠道：
    - Telegram Bot API
    - Discord Webhook
    """

    def __init__(self):
        """初始化预警器"""
        self.session: Optional[aiohttp.ClientSession] = None

        # 从环境变量读取配置
        self.telegram_bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
        self.telegram_chat_id = os.getenv('TELEGRAM_CHAT_ID')
        self.discord_webhook_url = os.getenv('DISCORD_WEBHOOK_URL')

        # 检查配置
        self.telegram_enabled = bool(self.telegram_bot_token and self.telegram_chat_id)
        self.discord_enabled = bool(self.discord_webhook_url)

        if self.telegram_enabled:
            logger.info(f"✅ Telegram 预警已启用 (Chat ID: {self.telegram_chat_id})")
        else:
            logger.info("⚠️ Telegram 预警未配置")

        if self.discord_enabled:
            logger.info("✅ Discord 预警已启用")
        else:
            logger.info("⚠️ Discord 预警未配置")

    async def init_session(self):
        """初始化 HTTP session"""
        if not self.session:
            self.session = aiohttp.ClientSession()

    async def close(self):
        """关闭 session"""
        if self.session:
            await self.session.close()
            self.session = None

    def format_message(self, alert: AlertMessage) -> str:
        """
        格式化预警消息

        Args:
            alert: 预警消息对象

        Returns:
            格式化后的消息
        """
        # 表情符号映射
        emojis = {
            AlertType.RESONANCE_LOCKED: "🎯",
            AlertType.ORDER_FILLED: "💥",
            AlertType.STOP_LOSS: "🛑",
            AlertType.TIME_STOP: "⏱️",
            AlertType.TRAILING_STOP: "💰",
            AlertType.EMERGENCY_CLOSE: "🚨",
            AlertType.SYSTEM_WARNING: "⚠️",
        }

        emoji = emojis.get(alert.alert_type, "📊")

        # 构建消息
        lines = [
            f"{emoji} *{alert.alert_type.value}*",
            f"",
            f"🪙 `{alert.symbol}`",
            f"📊 {alert.side}",
            f"",
            f"{alert.message}",
        ]

        # 添加详情
        if alert.details:
            lines.append(f"")
            lines.append(f"*详情:*")
            for key, value in alert.details.items():
                lines.append(f"  `{key}`: {value}")

        # 添加时间戳
        from datetime import datetime
        lines.append(f"")
        lines.append(f"⏰ `{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}`")

        return "\n".join(lines)

    async def send_telegram(self, message: str) -> bool:
        """
        发送 Telegram 消息

        Args:
            message: 消息内容（Markdown 格式）

        Returns:
            是否发送成功
        """
        if not self.telegram_enabled:
            return False

        await self.init_session()

        url = f"https://api.telegram.org/bot{self.telegram_bot_token}/sendMessage"

        data = {
            'chat_id': self.telegram_chat_id,
            'text': message,
            'parse_mode': 'Markdown',
        }

        try:
            async with self.session.post(url, json=data) as response:
                if response.status == 200:
                    logger.info(f"✅ Telegram 消息发送成功")
                    return True
                else:
                    error_text = await response.text()
                    logger.error(f"❌ Telegram 发送失败: {response.status} - {error_text}")
                    return False

        except Exception as e:
            logger.error(f"❌ Telegram 发送异常: {e}")
            return False

    async def send_discord(self, message: str) -> bool:
        """
        发送 Discord 消息

        Args:
            message: 消息内容

        Returns:
            是否发送成功
        """
        if not self.discord_enabled:
            return False

        await self.init_session()

        # Discord 不支持 Markdown，需要转换
        # 简单转换：去除 Markdown 特殊字符
        clean_message = message.replace('*', '').replace('`', '')

        data = {
            'content': clean_message,
        }

        try:
            async with self.session.post(self.discord_webhook_url, json=data) as response:
                if response.status in [200, 204]:
                    logger.info(f"✅ Discord 消息发送成功")
                    return True
                else:
                    error_text = await response.text()
                    logger.error(f"❌ Discord 发送失败: {response.status} - {error_text}")
                    return False

        except Exception as e:
            logger.error(f"❌ Discord 发送异常: {e}")
            return False

    async def send_alert(self, alert: AlertMessage) -> bool:
        """
        发送预警（所有已配置的渠道）

        Args:
            alert: 预警消息对象

        Returns:
            是否至少有一个渠道发送成功
        """
        # 格式化消息
        message = self.format_message(alert)

        logger.info(f"📢 发送预警: {alert.alert_type.value} - {alert.symbol}")
        logger.debug(f"消息内容:\n{message}")

        # 并发发送到所有渠道
        results = await asyncio.gather(
            self.send_telegram(message),
            self.send_discord(message),
            return_exceptions=True
        )

        # 检查是否至少有一个成功
        success = any(r is True for r in results if not isinstance(r, Exception))

        if not success:
            logger.warning(f"⚠️ 所有预警渠道均发送失败")

        return success

    async def alert_resonance_locked(
        self,
        symbol: str,
        side: str,
        confidence: float,
        reasons: list,
        entry_price: Optional[float] = None,
        vwap: Optional[float] = None
    ) -> bool:
        """
        预警：三重共振锁定

        Args:
            symbol: 交易对
            side: 'LONG' or 'SHORT'
            confidence: 置信度
            reasons: 共振原因
            entry_price: 突破价格
            vwap: VWAP 回踩价

        Returns:
            是否发送成功
        """
        message = f"*三重共振已锁定！* 置信度: {confidence:.0%}\n"
        message += "\n".join([f"  • {r}" for r in reasons])

        details = {
            "置信度": f"{confidence:.0%}",
        }

        if entry_price:
            details["突破价"] = f"${entry_price:.2f}"

        if vwap:
            details["等待回踩"] = f"${vwap:.2f}"

        alert = AlertMessage(
            alert_type=AlertType.RESONANCE_LOCKED,
            symbol=symbol,
            side=side,
            message=message,
            details=details
        )

        return await self.send_alert(alert)

    async def alert_order_filled(
        self,
        symbol: str,
        side: str,
        entry_price: float,
        quantity: float,
        leverage: int,
        stop_loss: float,
        take_profit: float,
        fill_type: str = "LIMIT"  # LIMIT / MARKET_MOMENTUM
    ) -> bool:
        """
        预警：订单成交

        Args:
            symbol: 交易对
            side: 'LONG' or 'SHORT'
            entry_price: 成交价格
            quantity: 数量
            leverage: 杠杆
            stop_loss: 止损价（爆仓线）
            take_profit: 止盈价
            fill_type: 成交类型（限价成交 / 动量追入）

        Returns:
            是否发送成功
        """
        message = f"*订单成交！* ({fill_type})"

        alert = AlertMessage(
            alert_type=AlertType.ORDER_FILLED,
            symbol=symbol,
            side=side,
            message=message,
            details={
                "成交价": f"${entry_price:.2f}",
                "数量": f"{quantity:.6f}",
                "杠杆": f"{leverage}x",
                "止损价": f"${stop_loss:.2f}",
                "止盈价": f"${take_profit:.2f}",
            }
        )

        return await self.send_alert(alert)

    async def alert_stop_loss(
        self,
        symbol: str,
        side: str,
        entry_price: float,
        exit_price: float,
        pnl: float,
        reason: str = "爆仓线止损"
    ) -> bool:
        """
        预警：触发止损

        Args:
            symbol: 交易对
            side: 'LONG' or 'SHORT'
            entry_price: 入场价
            exit_price: 出场价
            pnl: 盈亏
            reason: 原因

        Returns:
            是否发送成功
        """
        message = f"*{reason}*"

        alert = AlertMessage(
            alert_type=AlertType.STOP_LOSS,
            symbol=symbol,
            side=side,
            message=message,
            details={
                "入场价": f"${entry_price:.2f}",
                "出场价": f"${exit_price:.2f}",
                "盈亏": f"${pnl:+.2f}",
            }
        )

        return await self.send_alert(alert)

    async def alert_time_stop(
        self,
        symbol: str,
        side: str,
        holding_hours: float,
        roe: float
    ) -> bool:
        """
        预警：12 小时时间止损

        Args:
            symbol: 交易对
            side: 'LONG' or 'SHORT'
            holding_hours: 持仓时间（小时）
            roe: 当前 ROE

        Returns:
            是否发送成功
        """
        message = f"*12 小时时间止损触发！* 持仓 {holding_hours:.1f}h，ROE {roe:.1%}"

        alert = AlertMessage(
            alert_type=AlertType.TIME_STOP,
            symbol=symbol,
            side=side,
            message=message,
            details={
                "持仓时间": f"{holding_hours:.1f}h",
                "当前 ROE": f"{roe:.1%}",
            }
        )

        return await self.send_alert(alert)

    async def alert_trailing_stop(
        self,
        symbol: str,
        side: str,
        entry_price: float,
        exit_price: float,
        pnl: float,
        roe: float
    ) -> bool:
        """
        预警：移动止盈完成

        Args:
            symbol: 交易对
            side: 'LONG' or 'SHORT'
            entry_price: 入场价
            exit_price: 出场价
            pnl: 盈亏
            roe: 最终 ROE

        Returns:
            是否发送成功
        """
        message = f"*移动止盈完成！* 锁定 ROE {roe:.1%}"

        alert = AlertMessage(
            alert_type=AlertType.TRAILING_STOP,
            symbol=symbol,
            side=side,
            message=message,
            details={
                "入场价": f"${entry_price:.2f}",
                "出场价": f"${exit_price:.2f}",
                "盈亏": f"${pnl:+.2f}",
                "最终 ROE": f"{roe:.1%}",
            }
        )

        return await self.send_alert(alert)

    async def alert_emergency_close(
        self,
        symbol: str,
        side: str,
        reason: str
    ) -> bool:
        """
        预警：紧急平仓

        Args:
            symbol: 交易对
            side: 'LONG' or 'SHORT'
            reason: 紧急原因

        Returns:
            是否发送成功
        """
        message = f"*紧急平仓！* {reason}"

        alert = AlertMessage(
            alert_type=AlertType.EMERGENCY_CLOSE,
            symbol=symbol,
            side=side,
            message=message,
            details={
                "原因": reason,
            }
        )

        return await self.send_alert(alert)

    async def alert_system_warning(
        self,
        title: str,
        message: str
    ) -> bool:
        """
        预警：系统警告

        Args:
            title: 警告标题
            message: 警告消息

        Returns:
            是否发送成功
        """
        alert = AlertMessage(
            alert_type=AlertType.SYSTEM_WARNING,
            symbol="",
            side="",
            message=f"{title}\n{message}",
            details={
                "title": title,
                "message": message,
            }
        )

        return await self.send_alert(alert)


# 全局单例
_alerter_instance: Optional[WebhookAlerter] = None


def get_alerter() -> WebhookAlerter:
    """获取全局预警器实例"""
    global _alerter_instance
    if _alerter_instance is None:
        _alerter_instance = WebhookAlerter()
    return _alerter_instance


if __name__ == '__main__':
    """测试预警系统"""
    import logging
    from datetime import datetime

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    async def test_alerts():
        alerter = WebhookAlerter()

        # 测试三重共振预警
        await alerter.alert_resonance_locked(
            symbol="BTC/USDT",
            side="LONG",
            confidence=1.0,
            reasons=[
                "4H 多头趋势：EMA20 > EMA50",
                "极度负费率：-0.08% + ΔOI 激增 8%",
                "15m 放量上涨：成交量 3.5x 平均",
            ],
            entry_price=50000.0,
            vwap=49800.0
        )

        # 测试订单成交预警
        await alerter.alert_order_filled(
            symbol="BTC/USDT",
            side="LONG",
            entry_price=49800.0,
            quantity=0.004,
            leverage=50,
            stop_loss=48900.0,
            take_profit=54900.0,
            fill_type="LIMIT"
        )

        # 测试移动止盈预警
        await alerter.alert_trailing_stop(
            symbol="BTC/USDT",
            side="LONG",
            entry_price=49800.0,
            exit_price=54000.0,
            pnl=16.8,
            roe=0.85
        )

        await alerter.close()

    asyncio.run(test_alerts())
