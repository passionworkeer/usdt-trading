#!/bin/bash
# 设置Windows定时任务

TASK_NAME="SniperTrader"

# 创建定时任务 (每5分钟运行一次)
schtasks /create /tn "$TASK_NAME" /tr "D:\anaconda\python.exe E:\desktop\usdt\scripts\trader.py" /sc minute /mo 5 /f 2>/dev/null

echo "Task scheduled: $TASK_NAME (every 5 min)"
echo ""
echo "Commands:"
echo "  Start:  schtasks /run /tn $TASK_NAME"
echo "  Stop:   schtasks /end /tn $TASK_NAME"
echo "  Delete: schtasks /delete /tn $TASK_NAME"
