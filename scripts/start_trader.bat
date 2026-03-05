@echo off
REM 实时交易系统启动器

echo Starting Sniper Trader...
cd /d "%~dp0"
D:\anaconda\python.exe scripts\trader.py
pause
