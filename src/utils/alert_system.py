"""
告警系统 (Alert System)

多渠道告警通知系统
"""
import os
import asyncio
import logging
from typing import Dict, List, Optional, Callable
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime
import aiohttp

logger = logging.getLogger(__name__)


class AlertPriority(Enum):
    """告警优先级"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class AlertChannel(Enum):
    """告警渠道"""
    TELEGRAM = "telegram"
    DISCORD = "discord"
    EMAIL = "email"
    SMS = "sms"
    WEBHOOK = "webhook"


@dataclass
class Alert:
    """告警对象"""
    priority: AlertPriority
    title: str
    message: str
    channel: AlertChannel = AlertChannel.TELEGRAM
    metadata: Dict = field(default_factory=dict)
    retry_count: int = 3


class AlertManager:
    """
    告警管理器

    支持多渠道告警：
    - Telegram
    - Discord
    - Email
    - SMS
    - Webhook
    """

    def __init__(self):
        """初始化告警管理器"""
        self.session: Optional[aiohttp.ClientSession] = None

        # Telegram 配置
        self.telegram_token = os.getenv('TELEGRAM_BOT_TOKEN')
        self.telegram_chat_id = os.getenv('TELEGRAM_CHAT_ID')
        self.telegram_enabled = bool(self.telegram_token and self.telegram_chat_id)

        # Discord 配置
        self.discord_webhook = os.getenv('DISCORD_WEBHOOK_URL')
        self.discord_enabled = bool(self.discord_webhook)

        # Email 配置
        self.smtp_host = os.getenv('SMTP_HOST')
        self.smtp_port = int(os.getenv('SMTP_PORT', '587'))
        self.smtp_user = os.getenv('SMTP_USER')
        self.smtp_password = os.getenv('SMTP_PASSWORD')
        self.email_from = os.getenv('EMAIL_FROM', 'trading@example.com')
        self.email_to = os.getenv('EMAIL_TO')
        self.email_enabled = bool(self.smtp_host and self.smtp_user and self.email_to)

        # SMS 配置 (Twilio)
        self.twilio_sid = os.getenv('TWILIO_ACCOUNT_SID')
        self.twilio_token = os.getenv('TWILIO_AUTH_TOKEN')
        self.twilio_phone = os.getenv('TWILIO_PHONE_NUMBER')
        self.sms_to = os.getenv('SMS_TO')
        self.sms_enabled = bool(self.twilio_sid and self.twilio_token and self.twilio_phone and self.sms_to)

        # 自定义 Webhook
        self.custom_webhooks: Dict[str, str] = {}
        for key in os.environ:
            if key.startswith('WEBHOOK_'):
                self.custom_webhooks[key] = os.getenv(key)

        # 告警回调
        self.callbacks: List[Callable] = []

        # 告警历史
        self.alert_history: List[Alert] = []

        # 统计
        self.stats = {
            'total': 0,
            'sent': 0,
            'failed': 0,
            'by_channel': {},
            'by_priority': {}
        }

        # 优先级 Emoji
        self.priority_emoji = {
            AlertPriority.LOW: 'ℹ️',
            AlertPriority.MEDIUM: '⚠️',
            AlertPriority.HIGH: '🔶',
            AlertPriority.CRITICAL: '🚨'
        }

        # 渠道 Emoji
        self.channel_emoji = {
            AlertChannel.TELEGRAM: '📱',
            AlertChannel.DISCORD: '💬',
            AlertChannel.EMAIL: '📧',
            AlertChannel.SMS: '📱',
            AlertChannel.WEBHOOK: '🔗'
        }

        self._log_config_status()

    def _log_config_status(self):
        """记录配置状态"""
        logger.info("告警渠道配置状态:")
        logger.info(f"  Telegram: {'✅' if self.telegram_enabled else '❌'}")
        logger.info(f"  Discord: {'✅' if self.discord_enabled else '❌'}")
        logger.info(f"  Email: {'✅' if self.email_enabled else '❌'}")
        logger.info(f"  SMS: {'✅' if self.sms_enabled else '❌'}")
        logger.info(f"  Custom Webhooks: {len(self.custom_webhooks)}")

    async def _get_session(self) -> aiohttp.ClientSession:
        """获取 HTTP Session"""
        if not self.session:
            self.session = aiohttp.ClientSession()
        return self.session

    async def close(self):
        """关闭 Session"""
        if self.session:
            await self.session.close()

    def register_callback(self, callback: Callable):
        """注册告警回调"""
        self.callbacks.append(callback)
        logger.info(f"✅ 已注册告警回调: {callback.__name__}")

    async def send_alert(
        self,
        priority: AlertPriority,
        title: str,
        message: str,
        channels: Optional[List[AlertChannel]] = None,
        **metadata
    ) -> bool:
        """
        发送告警

        Args:
            priority: 优先级
            title: 标题
            message: 消息
            channels: 渠道列表
            **metadata: 附加数据

        Returns:
            是否发送成功
        """
        # 创建告警对象
        alert = Alert(
            priority=priority,
            title=title,
            message=message,
            metadata=metadata
        )

        self.alert_history.append(alert)
        self.stats['total'] += 1

        # 默认发送到所有启用的渠道
        if channels is None:
            channels = self._get_default_channels()

        # 发送到各个渠道
        success = False
        for channel in channels:
            try:
                if channel == AlertChannel.TELEGRAM and self.telegram_enabled:
                    if await self._send_telegram(alert):
                        success = True

                elif channel == AlertChannel.DISCORD and self.discord_enabled:
                    if await self._send_discord(alert):
                        success = True

                elif channel == AlertChannel.EMAIL and self.email_enabled:
                    if await self._send_email(alert):
                        success = True

                elif channel == AlertChannel.SMS and self.sms_enabled:
                    if await self._send_sms(alert):
                        success = True

                elif channel == AlertChannel.WEBHOOK:
                    if await self._send_webhook(alert):
                        success = True

            except Exception as e:
                logger.error(f"发送告警失败 ({channel.value}): {e}")
                self.stats['failed'] += 1

        # 执行回调
        if self.callbacks:
            for callback in self.callbacks:
                try:
                    if asyncio.iscoroutinefunction(callback):
                        await callback(alert)
                    else:
                        callback(alert)
                except Exception as e:
                    logger.error(f"执行告警回调失败: {e}")

        # 更新统计
        if success:
            self.stats['sent'] += 1
        else:
            self.stats['failed'] += 1

        channel_key = ','.join([c.value for c in channels])
        self.stats['by_channel'][channel_key] = self.stats['by_channel'].get(channel_key, 0) + 1

        priority_key = priority.value
        self.stats['by_priority'][priority_key] = self.stats['by_priority'].get(priority_key, 0) + 1

        return success

    def _get_default_channels(self) -> List[AlertChannel]:
        """获取默认渠道"""
        channels = []
        if self.telegram_enabled:
            channels.append(AlertChannel.TELEGRAM)
        if self.discord_enabled:
            channels.append(AlertChannel.DISCORD)
        if self.email_enabled:
            channels.append(AlertChannel.EMAIL)
        return channels

    async def _send_telegram(self, alert: Alert) -> bool:
        """发送 Telegram 告警"""
        emoji = self.priority_emoji.get(alert.priority, '')

        text = f"""
{emoji} *{alert.title}*

{alert.message}
"""

        url = f"https://api.telegram.org/bot{self.telegram_token}/sendMessage"
        data = {
            'chat_id': self.telegram_chat_id,
            'text': text,
            'parse_mode': 'Markdown'
        }

        async with self.session.post(url, json=data) as response:
            return response.status == 200

    async def _send_discord(self, alert: Alert) -> bool:
        """发送 Discord 告警"""
        emoji = self.priority_emoji.get(alert.priority, '')

        # Discord 颜色 (优先级)
        colors = {
            AlertPriority.LOW: 3447003,      # 蓝色
            AlertPriority.MEDIUM: 16776960, # 黄色
            AlertPriority.HIGH: 15105570,   # 橙色
            AlertPriority.CRITICAL: 15158332 # 红色
        }

        embed = {
            'title': f"{emoji} {alert.title}",
            'description': alert.message,
            'color': colors.get(alert.priority, 0),
            'timestamp': datetime.now().isoformat(),
            'footer': {'text': 'Sniper Trading System'}
        }

        # 添加字段
        if alert.metadata:
            fields = []
            for key, value in alert.metadata.items():
                fields.append({'name': key, 'value': str(value), 'inline': True})
            embed['fields'] = fields

        data = {'embeds': [embed]}

        async with self.session.post(self.discord_webhook, json=data) as response:
            return response.status in [200, 204]

    async def _send_email(self, alert: Alert) -> bool:
        """发送 Email 告警"""
        import smtplib
        from email.mime.text import MIMEText
        from email.mime.multipart import MIMEMultipart

        emoji = self.priority_emoji.get(alert.priority, '')

        msg = MIMEMultipart('alternative')
        msg['Subject'] = f"{emoji} {alert.title}"
        msg['From'] = self.email_from
        msg['To'] = self.email_to

        # Plain text
        text_content = f"{alert.title}\n\n{alert.message}"
        msg.attach(MIMEText(text_content, 'plain'))

        # HTML
        html_content = f"""
        <html>
        <body>
            <h2>{emoji} {alert.title}</h2>
            <p>{alert.message}</p>
            <hr>
            <small>Sniper Trading System</small>
        </body>
        </html>
        """
        msg.attach(MIMEText(html_content, 'html'))

        # 发送
        with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
            server.starttls()
            server.login(self.smtp_user, self.smtp_password)
            server.send_message(msg)

        return True

    async def _send_sms(self, alert: Alert) -> bool:
        """发送 SMS 告警"""
        # Twilio SMS
        emoji = self.priority_emoji.get(alert.priority, '')

        url = f"https://api.twilio.com/2010-04-01/Accounts/{self.twilio_sid}/Messages.json"
        auth = aiohttp.BasicAuth(self.twilio_sid, self.twilio_token)

        data = {
            'From': self.twilio_phone,
            'To': self.sms_to,
            'Body': f"{emoji} {alert.title}: {alert.message}"
        }

        async with self.session.post(url, data=data, auth=auth) as response:
            return response.status == 201

    async def _send_webhook(self, alert: Alert) -> bool:
        """发送 Webhook 告警"""
        emoji = self.priority_emoji.get(alert.priority, '')

        payload = {
            'priority': alert.priority.value,
            'title': alert.title,
            'message': alert.message,
            'emoji': emoji,
            'timestamp': datetime.now().isoformat(),
            'metadata': alert.metadata
        }

        # 发送到所有自定义 Webhook
        results = []
        for name, url in self.custom_webhooks.items():
            try:
                async with self.session.post(url, json=payload) as response:
                    results.append(response.status in [200, 201, 204])
            except Exception as e:
                logger.error(f"发送 Webhook 失败 ({name}): {e}")
                results.append(False)

        return any(results)

    # 便捷方法
    async def alert_critical(self, title: str, message: str, **metadata):
        """发送严重告警"""
        return await self.send_alert(AlertPriority.CRITICAL, title, message, **metadata)

    async def alert_high(self, title: str, message: str, **metadata):
        """发送高优先级告警"""
        return await self.send_alert(AlertPriority.HIGH, title, message, **metadata)

    async def alert_medium(self, title: str, message: str, **metadata):
        """发送中等告警"""
        return await self.send_alert(AlertPriority.MEDIUM, title, message, **metadata)

    async def alert_low(self, title: str, message: str, **metadata):
        """发送低优先级告警"""
        return await self.send_alert(AlertPriority.LOW, title, message, **metadata)

    def get_stats(self) -> Dict:
        """获取统计信息"""
        return {
            **self.stats,
            'history_count': len(self.alert_history),
            'enabled_channels': {
                'telegram': self.telegram_enabled,
                'discord': self.discord_enabled,
                'email': self.email_enabled,
                'sms': self.sms_enabled,
                'custom_webhooks': len(self.custom_webhooks)
            }
        }


# 全局告警管理器
_alert_manager: Optional[AlertManager] = None


def get_alert_manager() -> AlertManager:
    """获取全局告警管理器"""
    global _alert_manager
    if _alert_manager is None:
        _alert_manager = AlertManager()
    return _alert_manager
