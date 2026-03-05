"""
配置验证系统 (Configuration Validator)

启动时验证所有配置和依赖
"""
import os
import sys
import logging
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class CheckStatus(Enum):
    """检查状态"""
    PASS = "pass"
    WARNING = "warning"
    FAIL = "fail"


@dataclass
class CheckResult:
    """检查结果"""
    name: str
    status: CheckStatus
    message: str
    details: Optional[Dict] = None


class ConfigValidator:
    """
    配置验证器

    启动时检查：
    1. 环境变量
    2. 依赖包
    3. 网络连接
    4. 配置文件
    """

    # 必需的环境变量
    REQUIRED_ENV_VARS = [
        'BINANCE_API_KEY',
        'BINANCE_API_SECRET',
    ]

    # 可选的环境变量
    OPTIONAL_ENV_VARS = [
        'ANTHROPIC_API_KEY',
        'TELEGRAM_BOT_TOKEN',
        'TELEGRAM_CHAT_ID',
        'DISCORD_WEBHOOK_URL',
    ]

    # 必需的核心依赖
    REQUIRED_PACKAGES = [
        'ccxt',
        'aiohttp',
        'pandas',
        'numpy',
    ]

    def __init__(self):
        """初始化验证器"""
        self.results: List[CheckResult] = []

    def check_all(self) -> bool:
        """
        执行所有检查

        Returns:
            是否全部通过
        """
        self.results = []

        # 执行各项检查
        self.check_env_vars()
        self.check_python_version()
        self.check_dependencies()
        self.check_proxy()
        self.check_data_directories()

        # 打印结果
        self._print_results()

        # 返回是否通过
        failed = [r for r in self.results if r.status == CheckStatus.FAIL]
        return len(failed) == 0

    def check_env_vars(self):
        """检查环境变量"""
        # 检查必需变量
        for var in self.REQUIRED_ENV_VARS:
            value = os.getenv(var)
            if value:
                # 检查是否为空字符串
                if value.strip():
                    self.results.append(CheckResult(
                        name=f"ENV:{var}",
                        status=CheckStatus.PASS,
                        message=f"✓ {var} 已配置"
                    ))
                else:
                    self.results.append(CheckResult(
                        name=f"ENV:{var}",
                        status=CheckStatus.WARNING,
                        message=f"⚠ {var} 为空字符串"
                    ))
            else:
                self.results.append(CheckResult(
                    name=f"ENV:{var}",
                    status=CheckStatus.WARNING,
                    message=f"⚠ {var} 未设置 (可选)"
                ))

        # 检查可选变量
        for var in self.OPTIONAL_ENV_VARS:
            value = os.getenv(var)
            if value and value.strip():
                self.results.append(CheckResult(
                    name=f"ENV:{var}",
                    status=CheckStatus.PASS,
                    message=f"✓ {var} 已配置"
                ))

    def check_python_version(self):
        """检查 Python 版本"""
        version = sys.version_info
        required_major = 3
        required_minor = 8

        if version.major >= required_major and version.minor >= required_minor:
            self.results.append(CheckResult(
                name="PYTHON_VERSION",
                status=CheckStatus.PASS,
                message=f"✓ Python {version.major}.{version.minor}.{version.micro}"
            ))
        else:
            self.results.append(CheckResult(
                name="PYTHON_VERSION",
                status=CheckStatus.FAIL,
                message=f"✗ Python 版本过低: {version.major}.{version.minor}.{version.micro} (需要 >= 3.8)"
            ))

    def check_dependencies(self):
        """检查依赖包"""
        for package in self.REQUIRED_PACKAGES:
            try:
                __import__(package)
                self.results.append(CheckResult(
                    name=f"PKG:{package}",
                    status=CheckStatus.PASS,
                    message=f"✓ {package} 已安装"
                ))
            except ImportError:
                self.results.append(CheckResult(
                    name=f"PKG:{package}",
                    status=CheckStatus.FAIL,
                    message=f"✗ {package} 未安装 (pip install {package})"
                ))

    def check_proxy(self):
        """检查代理配置"""
        proxy = os.getenv('HTTP_PROXY') or os.getenv('HTTPS_PROXY') or os.getenv('ALL_PROXY')
        if proxy:
            self.results.append(CheckResult(
                name="PROXY",
                status=CheckStatus.PASS,
                message=f"✓ 代理已配置: {proxy}",
                details={'proxy': proxy}
            ))
        else:
            self.results.append(CheckResult(
                name="PROXY",
                status=CheckStatus.WARNING,
                message="⚠ 未配置代理，可能无法访问 Binance"
            ))

    def check_data_directories(self):
        """检查数据目录"""
        directories = ['logs', 'cache', 'state', 'data']

        for dir_name in directories:
            path = os.path.join(os.getcwd(), dir_name)
            if os.path.exists(path):
                if os.access(path, os.W_OK):
                    self.results.append(CheckResult(
                        name=f"DIR:{dir_name}",
                        status=CheckStatus.PASS,
                        message=f"✓ {dir_name}/ 目录存在"
                    ))
                else:
                    self.results.append(CheckResult(
                        name=f"DIR:{dir_name}",
                        status=CheckStatus.WARNING,
                        message=f"⚠ {dir_name}/ 目录不可写"
                    ))
            else:
                # 尝试创建
                try:
                    os.makedirs(path, exist_ok=True)
                    self.results.append(CheckResult(
                        name=f"DIR:{dir_name}",
                        status=CheckStatus.PASS,
                        message=f"✓ {dir_name}/ 目录已创建"
                    ))
                except Exception as e:
                    self.results.append(CheckResult(
                        name=f"DIR:{dir_name}",
                        status=CheckStatus.FAIL,
                        message=f"✗ {dir_name}/ 目录创建失败: {e}"
                    ))

    def _print_results(self):
        """打印检查结果"""
        print("\n" + "=" * 60)
        print("🔍 配置验证结果")
        print("=" * 60)

        # 按状态分组
        passed = [r for r in self.results if r.status == CheckStatus.PASS]
        warnings = [r for r in self.results if r.status == CheckStatus.WARNING]
        failed = [r for r in self.results if r.status == CheckStatus.FAIL]

        # 打印失败项
        if failed:
            print("\n❌ 失败:")
            for r in failed:
                print(f"  {r.message}")

        # 打印警告项
        if warnings:
            print("\n⚠️ 警告:")
            for r in warnings:
                print(f"  {r.message}")

        # 打印通过项
        if passed:
            print("\n✅ 通过:")
            for r in passed[:5]:  # 只显示前5个
                print(f"  {r.message}")
            if len(passed) > 5:
                print(f"  ... 还有 {len(passed) - 5} 项")

        # 总结
        print("\n" + "-" * 60)
        print(f"总计: {len(passed)} 通过, {len(warnings)} 警告, {len(failed)} 失败")
        print("=" * 60 + "\n")

    def get_failed_checks(self) -> List[CheckResult]:
        """获取失败的检查"""
        return [r for r in self.results if r.status == CheckStatus.FAIL]

    def get_warnings(self) -> List[CheckResult]:
        """获取警告"""
        return [r for r in self.results if r.status == CheckStatus.WARNING]


def validate_startup() -> bool:
    """
    启动时验证配置

    Returns:
        是否通过验证
    """
    validator = ConfigValidator()
    return validator.check_all()
