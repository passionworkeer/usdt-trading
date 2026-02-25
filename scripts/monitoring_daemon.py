#!/usr/bin/env python3
"""
v7.3 独立监控守护进程（Independent Monitoring Daemon）

进程级隔离架构：
- 核心交易进程：只负责交易逻辑和 Redis Pub/Sub 广播
- 监控守护进程：订阅 Redis，处理 WebSocket/HTTP（独立进程）

安全访问：
- 默认绑定 127.0.0.1（仅本地访问）
- 生产环境必须通过 SSH 隧道访问
- 禁止公网直接访问

启动方式：
    python scripts/monitoring_daemon.py

访问方式（SSH 隧道）：
    # 本地端口转发
    ssh -L 8765:127.0.0.1:8765 user@trading-server

    # 浏览器访问
    http://localhost:8765
"""
import asyncio
import json
import logging
import os
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Set

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

try:
    import redis.asyncio as redis
    from fastapi import FastAPI, WebSocket, WebSocketDisconnect
    from fastapi.responses import HTMLResponse
    import uvicorn
except ImportError as e:
    raise ImportError(f"请安装依赖: pip install redis fastapi uvicorn\n{e}")

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - [%(name)s] - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/monitoring_daemon.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# FastAPI 应用
app = FastAPI(title="Sniper Trading Monitor (Isolated Process)")

# WebSocket 连接管理器
class ConnectionManager:
    def __init__(self):
        self.active_connections: Set[WebSocket] = set()

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.add(websocket)
        logger.info(f"WebSocket 客户端连接: {len(self.active_connections)} 个")

    def disconnect(self, websocket: WebSocket):
        self.active_connections.discard(websocket)
        logger.info(f"WebSocket 客户端断开: {len(self.active_connections)} 个")

    async def broadcast(self, message: str):
        """广播消息到所有客户端"""
        for connection in list(self.active_connections):
            try:
                await connection.send_text(message)
            except Exception as e:
                logger.debug(f"发送消息失败: {e}")
                self.active_connections.discard(connection)


manager = ConnectionManager()

# 状态缓存（用于新客户端初始化）
state_cache = {
    'positions': {},
    'events': [],
    'stats': {},
}


# HTML 监控面板（嵌入式）
HTML_DASHBOARD = """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>v7.3 监控面板（进程隔离）</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Consolas', monospace;
            background: #0a0e17;
            color: #d1d5db;
            padding: 20px;
        }
        .warning-banner {
            background: #dc2626;
            color: white;
            padding: 15px;
            border-radius: 8px;
            margin-bottom: 20px;
            text-align: center;
        }
        .status-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 20px;
        }
        .card {
            background: #1e293b;
            padding: 20px;
            border-radius: 8px;
            border: 1px solid #334155;
        }
        .card h3 {
            color: #60a5fa;
            margin-bottom: 15px;
        }
        .event-log {
            max-height: 400px;
            overflow-y: auto;
        }
        .event-item {
            padding: 10px;
            border-left: 3px solid #3b82f6;
            margin-bottom: 10px;
            background: #0f172a;
        }
    </style>
</head>
<body>
    <div class="warning-banner">
        ⚠️ 监控进程已隔离 - 核心交易引擎不受影响
    </div>

    <div class="status-grid">
        <div class="card">
            <h3>📡 Redis 连接</h3>
            <div id="redis-status">未连接</div>
        </div>

        <div class="card">
            <h3>📊 仓位状态</h3>
            <div id="positions">加载中...</div>
        </div>

        <div class="card">
            <h3>📜 事件日志</h3>
            <div class="event-log" id="events"></div>
        </div>
    </div>

    <script>
        const ws = new WebSocket('ws://127.0.0.1:8765/ws');

        ws.onopen = () => {
            console.log('WebSocket 已连接');
            document.getElementById('redis-status').innerHTML = '✅ 已连接';
        };

        ws.onmessage = (event) => {
            const data = JSON.parse(event.data);

            if (data.type === 'init') {
                // 初始化状态
                console.log('收到初始状态:', data);
            } else if (data.channel === 'price') {
                // 价格更新
                console.log('价格更新:', data);
            } else if (data.channel === 'event') {
                // 交易事件
                addEvent(data);
            } else if (data.channel === 'position') {
                // 仓位更新
                updatePosition(data);
            }
        };

        ws.onclose = () => {
            document.getElementById('redis-status').innerHTML = '❌ 已断开';
        };

        function addEvent(event) {
            const eventDiv = document.createElement('div');
            eventDiv.className = 'event-item';
            eventDiv.innerHTML = `
                <strong>${event.timestamp}</strong><br>
                ${event.message}
            `;
            document.getElementById('events').prepend(eventDiv);
        }

        function updatePosition(position) {
            document.getElementById('positions').innerHTML = `
                <p>交易对: ${position.symbol}</p>
                <p>方向: ${position.side}</p>
                <p>价格: ${position.price}</p>
            `;
        }
    </script>
</body>
</html>
"""


@app.get("/", response_class=HTMLResponse)
async def dashboard():
    """监控面板（仅 127.0.0.1 访问）"""
    return HTML_DASHBOARD


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket 实时推送"""
    await manager.connect(websocket)

    try:
        # 发送初始状态
        await websocket.send_text(json.dumps({
            'type': 'init',
            'data': state_cache
        }))

        # 保持连接（心跳）
        while True:
            data = await websocket.receive_text()
            # 忽略客户端消息（仅推送模式）
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"WebSocket 异常: {e}")
        manager.disconnect(websocket)


async def redis_subscriber(redis_url: str, channel_prefix: str):
    """
    Redis 订阅器（后台任务）

    订阅所有频道并广播到 WebSocket
    """
    try:
        r = await redis.from_url(redis_url, encoding="utf-8", decode_responses=True)
        pubsub = r.pubsub()

        # 订阅所有频道
        channels = [
            f"{channel_prefix}:price",
            f"{channel_prefix}:event",
            f"{channel_prefix}:position",
            f"{channel_prefix}:stats",
        ]
        await pubsub.subscribe(*channels)

        logger.info(f"✅ Redis 订阅成功: {channels}")

        # 监听消息
        async for message in pubsub.listen():
            if message['type'] == 'message':
                channel = message['channel']
                data = json.loads(message['data'])

                # 广播到所有 WebSocket 客户端
                await manager.broadcast(json.dumps({
                    'channel': channel.split(':')[-1],
                    **data
                }))

                # 更新状态缓存
                if 'event' in channel:
                    state_cache['events'].append(data)
                    state_cache['events'] = state_cache['events'][-100:]  # 保留最近 100 条

    except Exception as e:
        logger.error(f"Redis 订阅异常: {e}", exc_info=True)


async def main():
    """主函数"""
    # 配置
    redis_url = os.getenv('REDIS_URL', 'redis://localhost:6379/0')
    channel_prefix = os.getenv('CHANNEL_PREFIX', 'sniper:v7.3')
    host = os.getenv('MONITORING_HOST', '127.0.0.1')  # 默认仅本地访问
    port = int(os.getenv('MONITORING_PORT', '8765'))

    logger.info("="*60)
    logger.info("🚀 v7.3 监控守护进程启动")
    logger.info("="*60)
    logger.info(f"  Redis: {redis_url}")
    logger.info(f"  Host: {host}")
    logger.info(f"  Port: {port}")
    logger.info(f"  访问: http://{host}:{port}")
    logger.info("="*60)

    # 启动 Redis 订阅器（后台任务）
    asyncio.create_task(redis_subscriber(redis_url, channel_prefix))

    # 启动 FastAPI 服务器
    config = uvicorn.Config(
        app,
        host=host,
        port=port,
        log_level="warning",  # 减少 uvicorn 日志
    )
    server = uvicorn.Server(config)
    await server.serve()


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("\n收到中断信号，关闭监控守护进程...")
