#!/usr/bin/env python3
"""
测试运行脚本
自动检查依赖并运行测试套件
"""

import subprocess
import sys
from pathlib import Path


def check_python_version():
    """检查 Python 版本"""
    version = sys.version_info
    print(f"Python 版本: {version.major}.{version.minor}.{version.micro}")

    if version.major < 3 or (version.major == 3 and version.minor < 11):
        print("❌ 需要 Python 3.11 或更高版本")
        return False

    print("✅ Python 版本符合要求")
    return True


def check_dependencies():
    """检查必需的依赖"""
    required = [
        "pytest",
        "pytest-cov",
        "pytest-asyncio",
        "aiosqlite",
        "aiohttp",
    ]

    missing = []
    for package in required:
        try:
            __import__(package.replace("-", "_"))
            print(f"✅ {package} 已安装")
        except ImportError:
            print(f"❌ {package} 未安装")
            missing.append(package)

    return missing


def install_dependencies():
    """安装缺失的依赖"""
    print("\n正在安装依赖...")
    try:
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "-r", "requirements.txt"],
            check=True,
        )
        print("✅ 依赖安装完成")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ 依赖安装失败: {e}")
        return False


def run_tests(verbose=True, coverage=True, parallel=False):
    """运行测试"""
    cmd = [sys.executable, "-m", "pytest"]

    if verbose:
        cmd.append("-v")

    if coverage:
        cmd.extend(["--cov=src", "--cov-report=term-missing"])

    if parallel:
        cmd.extend(["-n", "auto"])

    cmd.append("tests/")

    print(f"\n运行命令: {' '.join(cmd)}")
    print("=" * 60)

    try:
        result = subprocess.run(cmd, check=False)
        return result.returncode == 0
    except Exception as e:
        print(f"❌ 测试运行失败: {e}")
        return False


def main():
    """主函数"""
    print("=" * 60)
    print("测试运行脚本")
    print("=" * 60)

    # 检查 Python 版本
    if not check_python_version():
        sys.exit(1)

    # 检查依赖
    print("\n检查依赖...")
    missing = check_dependencies()

    if missing:
        print(f"\n缺失依赖: {', '.join(missing)}")
        response = input("是否安装缺失的依赖? (y/n): ")

        if response.lower() == "y":
            if not install_dependencies():
                sys.exit(1)
        else:
            print("❌ 请先安装缺失的依赖")
            sys.exit(1)

    # 运行测试
    print("\n" + "=" * 60)
    print("开始运行测试...")
    print("=" * 60)

    success = run_tests(verbose=True, coverage=True, parallel=False)

    if success:
        print("\n✅ 所有测试通过!")
        sys.exit(0)
    else:
        print("\n❌ 部分测试失败")
        sys.exit(1)


if __name__ == "__main__":
    main()
