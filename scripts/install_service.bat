@echo off
REM ============================================
REM v6.0 Windows 服务注册脚本（使用 NSSM）
REM ============================================
REM 安装 NSSM: https://nssm.cc/download
REM ============================================

set SERVICENAME=OpenClawSniperTrader
set SCRIPT_DIR=%~dp0
set PYTHON_EXE=%SCRIPT_DIR%\venv\Scripts\python.exe
set MAIN_SCRIPT=%SCRIPT_DIR%\scripts\sniper_trader.py

echo ============================================
echo v6.0 Windows 服务注册器
echo ============================================
echo.

REM 检查管理员权限
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo ❌ 错误：需要管理员权限！
    echo 请右键点击此脚本，选择"以管理员身份运行"
    pause
    exit /b 1
)

REM 检查 NSSM 是否安装
where nssm >nul 2>&1
if %errorLevel% neq 0 (
    echo ❌ 错误：未找到 NSSM！
    echo 请下载 NSSM: https://nssm.cc/download
    echo 解压后将 nssm.exe 放入 PATH 环境变量
    pause
    exit /b 1
)

REM 检查 Python 虚拟环境
if not exist "%PYTHON_EXE%" (
    echo ❌ 错误：未找到虚拟环境！
    echo 请先运行: python -m venv venv
    echo 然后运行: venv\Scripts\activate
    echo 最后运行: pip install -r requirements.txt
    pause
    exit /b 1
)

echo ✅ 检查通过，开始注册服务...
echo.

REM 删除旧服务（如果存在）
nssm stop %SERVICENAME% >nul 2>&1
nssm remove %SERVICENAME% confirm >nul 2>&1

REM 安装新服务
nssm install %SERVICENAME% "%PYTHON_EXE%" "%MAIN_SCRIPT%"
nssm set %SERVICENAME% AppDirectory "%SCRIPT_DIR%"
nssm set %SERVICENAME% DisplayName "OpenClaw Sniper Trader v6.0"
nssm set %SERVICENAME% Description "v6.0 掠夺者模式 - 全景流动性雷达狙击手"
nssm set %SERVICENAME% Start SERVICE_AUTO_START
nssm set %SERVICENAME% AppRestartDelay 10000

REM 配置日志重定向
nssm set %SERVICENAME% stdout "%SCRIPT_DIR%\logs\service_out.log"
nssm set %SERVICENAME% stderr "%SCRIPT_DIR%\logs\service_err.log"

REM 配置环境变量
nssm set %SERVICENAME% AppEnvironmentExtra "PYTHONUNBUFFERED=1"

REM 配置服务重启策略
nssm set %SERVICENAME% AppThrottle 1500
nssm set %SERVICENAME% AppRestartDelay 10000
nssm set %SERVICENAME% AppExit Default Restart
nssm set %SERVICENAME% AppRestartDelay 10000

REM 配置服务依赖
nssm set %SERVICENAME% DependOnService Tcpip

echo.
echo ✅ 服务注册成功！
echo.
echo 常用命令:
echo   启动服务: nssm start %SERVICENAME%
echo   停止服务: nssm stop %SERVICENAME%
echo   重启服务: nssm restart %SERVICENAME%
echo   查看状态: nssm status %SERVICENAME%
echo   查看日志: type logs\service_out.log
echo   删除服务: nssm remove %SERVICENAME% confirm
echo.
pause
