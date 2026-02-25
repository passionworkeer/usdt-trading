"""
v6.1 工具模块
"""

# API 重试
from .api_retry import (
    exponential_backoff_retry,
    classify_binance_error,
    BinanceAPIError,
    RateLimitError,
    TimeoutError as BinanceTimeoutError,
    ConnectionError as BinanceConnectionError,
    ServerError,
)

# 预警系统
from .webhook_alerter import (
    WebhookAlerter,
    AlertType,
    AlertMessage,
    get_alerter,
)

# Session 管理（v6.0 新增）
from .session_manager import (
    GlobalSessionManager,
    get_session_manager,
    close_session_manager,
)

# 系统锁（v6.0 新增）
from .system_lock import (
    WindowsSystemLock,
    get_system_lock,
    disable_network_power_saving,
)

# 时间同步管理器（v6.1 新增）
from .time_sync_manager import (
    TimeSyncManager,
    get_time_sync_manager,
    ensure_time_sync,
)

__all__ = [
    # API 重试
    'exponential_backoff_retry',
    'classify_binance_error',
    'BinanceAPIError',
    'RateLimitError',
    'BinanceTimeoutError',
    'BinanceConnectionError',
    'ServerError',
    # 预警
    'WebhookAlerter',
    'AlertType',
    'AlertMessage',
    'get_alerter',
    # Session 管理
    'GlobalSessionManager',
    'get_session_manager',
    'close_session_manager',
    # 系统锁
    'WindowsSystemLock',
    'get_system_lock',
    'disable_network_power_saving',
    # 时间同步
    'TimeSyncManager',
    'get_time_sync_manager',
    'ensure_time_sync',
]
