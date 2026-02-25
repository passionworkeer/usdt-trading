@echo off
REM MCP AI 交易系统 - 完整测试脚本

echo ========================================
echo MCP AI Trading System - Test Suite
echo ========================================
echo.

REM 检查 Python
py --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found. Please install Python 3.11+
    exit /b 1
)

echo [1/4] Installing dependencies...
pip install -r requirements.txt
pip install pytest pytest-asyncio pytest-cov aiosqlite anthropic aiohttp

echo.
echo [2/4] Running Unit Tests...
py -m pytest tests/test_evidence_controller.py tests/test_database.py tests/test_provider_manager.py tests/test_claude_provider.py tests/test_openclaw_provider.py tests/test_strategy_pool.py tests/test_review_system.py tests/test_trading_engine.py -v --tb=short

if errorlevel 1 (
    echo [ERROR] Unit tests failed!
    exit /b 1
)

echo.
echo [3/4] Running E2E Tests...
py -m pytest tests/ -v --tb=short

if errorlevel 1 (
    echo [ERROR] E2E tests failed!
    exit /b 1
)

echo.
echo [4/4] Running Smoke Tests...
py -m pytest tests/ -v -k "smoke" --tb=short

if errorlevel 1 (
    echo [ERROR] Smoke tests failed!
    exit /b 1
)

echo.
echo ========================================
echo All tests passed!
echo ========================================
