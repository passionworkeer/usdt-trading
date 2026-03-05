"""
日志工具
"""
import os
import sys
import logging
from logging.handlers import RotatingFileHandler
from datetime import datetime
from typing import Optional


class SafeConsoleHandler(logging.StreamHandler):
    """
    安全的控制台处理器，在 Windows 下能正确处理 Unicode 字符
    """

    def emit(self, record):
        try:
            msg = self.format(record)
            # 确保 msg 是字符串类型
            if not isinstance(msg, str):
                msg = str(msg)

            # 在 Windows 下处理 Unicode 编码问题
            if sys.platform == 'win32':
                # 尝试使用 UTF-8 编码输出
                try:
                    # 尝试直接写入（如果终端支持 UTF-8）
                    self.stream.write(msg + self.terminator)
                    self.flush()
                except UnicodeEncodeError:
                    # 回退到 ASCII 安全模式：移除或替换非 ASCII 字符
                    safe_msg = msg.encode('ascii', 'replace').decode('ascii')
                    self.stream.write(safe_msg + self.terminator)
                    self.flush()
            else:
                # 非 Windows 系统直接输出
                self.stream.write(msg + self.terminator)
                self.flush()

        except Exception:
            self.handleError(record)


def setup_logger(name: str,
                log_file: Optional[str] = None,
                level: str = 'INFO',
                max_bytes: int = 10 * 1024 * 1024,  # 10MB
                backup_count: int = 5) -> logging.Logger:
    """
    设置日志记录器

    Args:
        name: 日志记录器名称
        log_file: 日志文件路径
        level: 日志级别
        max_bytes: 最大文件大小
        backup_count: 备份文件数量

    Returns:
        配置好的日志记录器
    """
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, level.upper()))

    # 避免重复添加 handler
    if logger.handlers:
        return logger

    # 日志格式
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # 控制台处理器 - 使用安全的处理器处理 Unicode
    console_handler = SafeConsoleHandler()
    console_handler.setLevel(getattr(logging, level.upper()))
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # 文件处理器
    if log_file:
        # 确保目录存在
        log_dir = os.path.dirname(log_file)
        if log_dir and not os.path.exists(log_dir):
            os.makedirs(log_dir)

        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding='utf-8'
        )
        file_handler.setLevel(getattr(logging, level.upper()))
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger


def get_logger(name: str) -> logging.Logger:
    """
    获取已配置的日志记录器

    Args:
        name: 日志记录器名称

    Returns:
        日志记录器
    """
    return logging.getLogger(name)
