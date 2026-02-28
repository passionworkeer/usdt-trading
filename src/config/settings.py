"""
统一配置模块 - 使用单例模式确保 .env 只加载一次

使用方式：
    from src.config import settings

    # 获取配置值
    api_key = settings.BINANCE_API_KEY
    dry_run = settings.DRY_RUN

    # 使用 os.getenv 的方式仍然兼容
    import os
    value = os.getenv('BINANCE_API_KEY')  # 仍然可用
"""
import os
import logging
from pathlib import Path
from typing import Optional, Any
from dataclasses import dataclass, field

# 单例标志
_config_instance: Optional['Settings'] = None
_env_loaded: bool = False


def _ensure_env_loaded():
    """
    确保环境变量只加载一次（单例模式）
    使用延迟加载，只在首次访问配置时加载
    """
    global _env_loaded
    if not _env_loaded:
        from dotenv import load_dotenv
        # 查找 .env 文件
        env_path = Path(__file__).parent.parent.parent / '.env'
        if env_path.exists():
            load_dotenv(env_path)
            logging.getLogger(__name__).info(f"环境变量已加载: {env_path}")
        else:
            # 尝试项目根目录
            env_path = Path.cwd() / '.env'
            if env_path.exists():
                load_dotenv(env_path)
                logging.getLogger(__name__).info(f"环境变量已加载: {env_path}")
        _env_loaded = True


@dataclass
class Settings:
    """
    集中管理所有配置项

    配置项分类：
    - Binance API
    - 交易参数
    - AI Agent
    - 通知配置
    - 高级参数
    """

    # ==================== Binance API ====================
    BINANCE_API_KEY: str = field(default='')
    BINANCE_API_SECRET: str = field(default='')
    BINANCE_TESTNET: bool = field(default=True)

    # ==================== 交易参数 ====================
    CAPITAL: float = field(default=200.0)
    DRY_RUN: bool = field(default=True)

    # ==================== AI Agent ====================
    ENABLE_AI_AGENT: bool = field(default=True)
    ANTHROPIC_API_KEY: str = field(default='')
    TWITTER_BEARER_TOKEN: str = field(default='')

    # ==================== 通知配置 ====================
    TELEGRAM_BOT_TOKEN: str = field(default='')
    TELEGRAM_CHAT_ID: str = field(default='')
    DISCORD_WEBHOOK_URL: str = field(default='')

    # ==================== 高级参数 ====================
    CHECK_INTERVAL: int = field(default=15)
    LOG_LEVEL: str = field(default='INFO')

    # ==================== 风控参数 ====================
    MAX_POSITION_SIZE: float = field(default=1000.0)
    MAX_DAILY_LOSS: float = field(default=500.0)
    MAX_OPEN_POSITIONS: int = field(default=5)
    DEFAULT_STOP_LOSS_PCT: float = field(default=-5.0)
    DEFAULT_TAKE_PROFIT_PCT: float = field(default=15.0)
    MAX_TRADES_PER_DAY: int = field(default=20)
    MIN_TRADE_INTERVAL: int = field(default=60)

    # ==================== 滑点控制 ====================
    MAX_SLIPPAGE_PCT: float = field(default=0.5)
    SLIPPAGE_CHECK_TIMEOUT: int = field(default=5)

    def __post_init__(self):
        """从环境变量加载配置值"""
        # Binance API
        self.BINANCE_API_KEY = os.getenv('BINANCE_API_KEY', self.BINANCE_API_KEY)
        self.BINANCE_API_SECRET = os.getenv('BINANCE_API_SECRET', self.BINANCE_API_SECRET)
        self.BINANCE_TESTNET = os.getenv('BINANCE_TESTNET', 'true').lower() == 'true'

        # 交易参数
        self.CAPITAL = float(os.getenv('CAPITAL', str(self.CAPITAL)))
        self.DRY_RUN = os.getenv('DRY_RUN', 'true').lower() == 'true'

        # AI Agent
        self.ENABLE_AI_AGENT = os.getenv('ENABLE_AI_AGENT', 'true').lower() == 'true'
        self.ANTHROPIC_API_KEY = os.getenv('ANTHROPIC_API_KEY', self.ANTHROPIC_API_KEY)
        self.TWITTER_BEARER_TOKEN = os.getenv('TWITTER_BEARER_TOKEN', self.TWITTER_BEARER_TOKEN)

        # 通知配置
        self.TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', self.TELEGRAM_BOT_TOKEN)
        self.TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID', self.TELEGRAM_CHAT_ID)
        self.DISCORD_WEBHOOK_URL = os.getenv('DISCORD_WEBHOOK_URL', self.DISCORD_WEBHOOK_URL)

        # 高级参数
        self.CHECK_INTERVAL = int(os.getenv('CHECK_INTERVAL', str(self.CHECK_INTERVAL)))
        self.LOG_LEVEL = os.getenv('LOG_LEVEL', self.LOG_LEVEL)

        # 风控参数
        self.MAX_POSITION_SIZE = float(os.getenv('MAX_POSITION_SIZE', str(self.MAX_POSITION_SIZE)))
        self.MAX_DAILY_LOSS = float(os.getenv('MAX_DAILY_LOSS', str(self.MAX_DAILY_LOSS)))
        self.MAX_OPEN_POSITIONS = int(os.getenv('MAX_OPEN_POSITIONS', str(self.MAX_OPEN_POSITIONS)))
        self.DEFAULT_STOP_LOSS_PCT = float(os.getenv('DEFAULT_STOP_LOSS_PCT', str(self.DEFAULT_STOP_LOSS_PCT)))
        self.DEFAULT_TAKE_PROFIT_PCT = float(os.getenv('DEFAULT_TAKE_PROFIT_PCT', str(self.DEFAULT_TAKE_PROFIT_PCT)))
        self.MAX_TRADES_PER_DAY = int(os.getenv('MAX_TRADES_PER_DAY', str(self.MAX_TRADES_PER_DAY)))
        self.MIN_TRADE_INTERVAL = int(os.getenv('MIN_TRADE_INTERVAL', str(self.MIN_TRADE_INTERVAL)))

        # 滑点控制
        self.MAX_SLIPPAGE_PCT = float(os.getenv('MAX_SLIPPAGE_PCT', str(self.MAX_SLIPPAGE_PCT)))
        self.SLIPPAGE_CHECK_TIMEOUT = int(os.getenv('SLIPPAGE_CHECK_TIMEOUT', str(self.SLIPPAGE_CHECK_TIMEOUT)))

    def get(self, key: str, default: Any = None) -> Any:
        """
        获取配置值，支持动态访问

        Args:
            key: 环境变量名称
            default: 默认值

        Returns:
            配置值
        """
        return os.getenv(key, default)

    def __getitem__(self, key: str) -> Any:
        """支持 settings['KEY'] 方式访问"""
        return os.getenv(key)

    def __contains__(self, key: str) -> bool:
        """支持 'KEY' in settings 方式检查"""
        return key in os.environ


def get_settings() -> Settings:
    """
    获取配置单例

    Returns:
        Settings 实例
    """
    global _config_instance
    if _config_instance is None:
        _ensure_env_loaded()
        _config_instance = Settings()
    return _config_instance


# 创建全局配置实例（延迟加载）
settings = property(lambda self: get_settings())

# 为了兼容 from src.config import settings 的使用方式
class _SettingsProxy:
    """代理类，支持延迟加载和属性访问"""
    _instance: Optional[Settings] = None

    def __getattr__(self, name: str) -> Any:
        if self._instance is None:
            self._instance = get_settings()
        return getattr(self._instance, name)

    def __getitem__(self, key: str) -> Any:
        if self._instance is None:
            self._instance = get_settings()
        return self._instance.get(key)

    def __contains__(self, key: str) -> bool:
        if self._instance is None:
            self._instance = get_settings()
        return key in self._instance

    def get(self, key: str, default: Any = None) -> Any:
        if self._instance is None:
            self._instance = get_settings()
        return self._instance.get(key, default)


# 全局配置实例
settings = _SettingsProxy()
