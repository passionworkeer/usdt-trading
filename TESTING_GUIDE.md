===========================================
快速安装和测试指南
===========================================

## 当前问题

Python 环境未正确安装或配置。检测到的情况:
- 注册表显示曾安装 Python 3.10 和 3.13
- 但可执行文件路径无效 (可能已卸载)
- 需要重新安装 Python

## 解决方案

### 方案 1: 安装 Python (推荐)

1. 下载 Python
   访问: https://www.python.org/downloads/
   推荐版本: Python 3.11.x 或 3.12.x (稳定版)

2. 安装时选择
   ✅ Add Python to PATH
   ✅ Install for all users (可选)
   ✅ pip
   ✅ tcl/tk and IDLE (可选)

3. 验证安装
   打开 PowerShell 或 CMD:
   ```powershell
   python --version
   pip --version
   ```

4. 安装项目依赖
   ```powershell
   cd E:\desktop\usdt
   pip install -r requirements_updated.txt
   ```

5. 运行测试
   ```powershell
   # 方法 1: 使用脚本
   python run_tests.py

   # 方法 2: 直接使用 pytest
   pytest -v

   # 方法 3: 带覆盖率
   pytest --cov=src --cov-report=html
   ```

### 方案 2: 使用虚拟环境 (最佳实践)

1. 创建虚拟环境
   ```powershell
   cd E:\desktop\usdt
   python -m venv venv
   ```

2. 激活虚拟环境
   ```powershell
   # Windows (PowerShell)
   venv\Scripts\Activate.ps1

   # Windows (CMD)
   venv\Scripts\activate.bat

   # Git Bash
   source venv/Scripts/activate
   ```

3. 安装依赖
   ```powershell
   pip install -r requirements_updated.txt
   ```

4. 运行测试
   ```powershell
   pytest -v
   ```

### 方案 3: 使用 uv (快速)

1. 安装 uv
   ```powershell
   pip install uv
   ```

2. 创建虚拟环境并安装依赖
   ```powershell
   cd E:\desktop\usdt
   uv venv
   uv pip install -r requirements_updated.txt
   ```

3. 激活虚拟环境
   ```powershell
   venv\Scripts\Activate.ps1
   ```

4. 运行测试
   ```powershell
   pytest -v
   ```

## 测试命令速查

```powershell
# 基础运行
pytest

# 详细输出
pytest -v

# 显示测试进度和失败详情
pytest -v --tb=short

# 只运行特定测试文件
pytest tests/test_database.py

# 只运行特定测试类
pytest tests/test_database.py::TestTradingDatabase

# 只运行特定测试方法
pytest tests/test_database.py::TestTradingDatabase::test_save_trade

# 生成覆盖率报告 (终端)
pytest --cov=src --cov-report=term-missing

# 生成覆盖率报告 (HTML)
pytest --cov=src --cov-report=html

# 查看 HTML 报告
start htmlcov\index.html

# 并行运行测试 (需要 pytest-xdist)
pytest -n auto

# 失败时重试 (需要 pytest-rerunfailures)
pytest --reruns 2

# 只运行快速测试
pytest -m "not slow"

# 只运行集成测试
pytest -m integration

# 显示所有跳过的测试
pytest -v --collect-only -q

# 生成 JUnit XML 报告 (用于 CI/CD)
pytest --junitxml=test-results.xml
```

## 预期测试结果

基于静态分析，预期结果:
- 总测试数: 452
- 预期通过: ~440 (97%)
- 预期失败: ~5 (1%)
- 预期跳过: ~7 (2%)
- 预期覆盖率: 75-85%

可能失败的测试:
1. 需要 API keys 的测试 (Binance, Claude)
2. 需要网络连接的测试
3. 需要外部服务的测试 (Redis, OpenClaw)

## 故障排除

### 问题 1: Python 命令未找到
解决方案:
- 确认 Python 已安装
- 检查 PATH 环境变量
- 重启终端或 PowerShell

### 问题 2: pip 命令未找到
解决方案:
```powershell
python -m pip --version
python -m pip install -r requirements_updated.txt
```

### 问题 3: pytest 命令未找到
解决方案:
```powershell
python -m pytest -v
```

### 问题 4: 模块导入错误
解决方案:
- 确认已激活虚拟环境
- 重新安装依赖
- 检查 PYTHONPATH 设置

### 问题 5: 测试失败 - API keys
解决方案:
- 复制 .env.example 为 .env
- 填写必要的 API keys
- 或者跳过这些测试: pytest -m "not integration"

### 问题 6: 测试失败 - 数据库
解决方案:
- 确认 aiosqlite 已安装
- 检查数据库文件权限
- 清理临时数据库文件

## 下一步

1. 安装 Python
2. 运行: pip install -r requirements_updated.txt
3. 运行: pytest -v
4. 检查失败的测试
5. 根据错误信息修复问题
6. 重新运行测试直到全部通过

## 文件清单

已创建的文件:
- test_results.txt (测试执行报告)
- test_analysis.txt (测试静态分析)
- requirements_updated.txt (更新的依赖列表)
- run_tests.py (测试运行脚本)
- TESTING_GUIDE.md (本文件)

## 联系支持

如有问题，请提供:
1. Python 版本 (python --version)
2. 依赖列表 (pip list)
3. 完整的错误信息
4. 测试输出日志

===========================================
