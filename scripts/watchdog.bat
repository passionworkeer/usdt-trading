@echo off
REM ============================================
REM v6.0 Windows 守护进程 - 自动崩溃重启
REM ============================================

REM 禁止系统休眠（调用 PowerShell）
powercfg -change -standby-timeout-ac 0
powercfg -change -monitor-timeout-ac 0
powercfg -change -hibernate-timeout-ac 0

REM 禁止网卡节能（需要管理员权限）
powershell -Command "Get-NetAdapter | ForEach-Object { Set-NetAdapterPowerManagement -Name $_.Name -WakeOnMagicPacket Enabled -WakeOnPattern Enabled }"

REM 日志目录
if not exist "logs" mkdir logs

REM 无限循环重启
:RESTART
echo [%DATE% %TIME%] 狙击手启动中... >> logs\watchdog.log
echo ========================================== >> logs\watchdog.log

REM 启动主程序
python scripts\sniper_trader.py

REM 崩溃后记录
echo [%DATE% %TIME%] ⚠️ 进程异常退出，10秒后重启... >> logs\watchdog.log
timeout /t 10 /nobreak
goto RESTART
