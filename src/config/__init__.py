"""
统一配置模块

使用单例模式确保 .env 文件只加载一次，避免重复加载导致的性能问题。

基本用法：
    from src.config import settings

    # 使用属性方式访问
    api_key = settings.BINANCE_API_KEY
    dry_run = settings.DRY_RUN

向后兼容用法：
    import os
    api_key = os.getenv('BINANCE_API_KEY')  # 仍然可用

环境变量加载时机：
    - 首次访问 settings 对象时自动加载
    - 只加载一次，无论导入多少次
"""
from src.config.settings import settings, Settings, get_settings

__all__ = ['settings', 'Settings', 'get_settings']
