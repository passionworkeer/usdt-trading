"""
v7.2 实时监控 WebSocket 服务（Real-Time Monitoring WebSocket Server）

为 Web 监控面板提供实时数据推送
"""
import asyncio
import logging
from typing import Set, Dict, Any
from datetime import datetime, timezone
import json

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
import uvicorn

from .monitoring_collector import MonitoringCollector

logger = logging.getLogger(__name__)


class ConnectionManager:
    """WebSocket 连接管理器"""

    def __init__(self):
        self.active_connections: Set[WebSocket] = set()

    async def connect(self, websocket: WebSocket):
        """接受新连接"""
        await websocket.accept()
        self.active_connections.add(websocket)
        logger.info(f"📊 新监控连接，当前连接数: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        """断开连接"""
        self.active_connections.discard(websocket)
        logger.info(f"📊 监控连接断开，当前连接数: {len(self.active_connections)}")

    async def broadcast(self, message: str):
        """广播消息到所有连接"""
        disconnected = set()

        for connection in self.active_connections:
            try:
                await connection.send_text(message)
            except Exception as e:
                logger.error(f"广播消息失败: {e}")
                disconnected.add(connection)

        # 移除断开的连接
        for connection in disconnected:
            self.disconnect(connection)


class MonitoringServer:
    """
    监控服务器

    功能：
    1. 提供 WebSocket 实时数据推送
    2. 提供 Web 监控面板页面
    3. 1 秒频率推送完整状态
    """

    def __init__(
        self,
        collector: MonitoringCollector,
        host: str = "0.0.0.0",
        port: int = 8765,
    ):
        """
        初始化监控服务器

        Args:
            collector: 监控数据采集器
            host: 监听地址
            port: 监听端口
        """
        self.collector = collector
        self.host = host
        self.port = port

        # FastAPI 应用
        self.app = FastAPI(title="Sniper Trading Monitor")

        # WebSocket 连接管理器
        self.manager = ConnectionManager()

        # 运行状态
        self.running = False

        # 事件日志缓存（最近 1000 条）
        self.event_log: list = []
        self.max_event_log = 1000

        # 注册路由
        self._setup_routes()

        logger.info(f"📊 监控服务器初始化完成: http://{host}:{port}")

    def _setup_routes(self):
        """设置路由"""

        @self.app.get("/", response_class=HTMLResponse)
        async def get_dashboard():
            """返回监控面板页面"""
            return self._get_dashboard_html()

        @self.app.websocket("/ws")
        async def websocket_endpoint(websocket: WebSocket):
            """WebSocket 端点"""
            await self.manager.connect(websocket)

            try:
                # 发送初始数据
                initial_data = await self.collector.collect_all()
                await websocket.send_json(initial_data)

                # 发送历史事件日志
                await websocket.send_json({
                    'type': 'event_log',
                    'events': self.event_log[-100:],  # 最近 100 条
                })

                # 保持连接（等待客户端消息或断开）
                while True:
                    # 等待客户端消息（用于心跳）
                    data = await websocket.receive_text()

                    # 处理心跳
                    if data == "ping":
                        await websocket.send_text("pong")

            except WebSocketDisconnect:
                self.manager.disconnect(websocket)
            except Exception as e:
                logger.error(f"WebSocket 错误: {e}")
                self.manager.disconnect(websocket)

        @self.app.get("/api/events")
        async def get_events():
            """获取事件日志"""
            return {
                'events': self.event_log[-100:],
                'total': len(self.event_log),
            }

        @self.app.get("/api/stats")
        async def get_stats():
            """获取当前统计"""
            return await self.collector.collect_all()

    def add_event(self, event: Dict[str, Any]):
        """
        添加事件到日志

        Args:
            event: 事件数据
        """
        event['timestamp'] = datetime.now(timezone.utc).isoformat()
        self.event_log.append(event)

        # 限制日志大小
        if len(self.event_log) > self.max_event_log:
            self.event_log.pop(0)

        # 异步广播事件
        asyncio.create_task(self._broadcast_event(event))

    async def _broadcast_event(self, event: Dict[str, Any]):
        """广播事件到所有连接"""
        try:
            message = json.dumps({
                'type': 'event',
                'event': event,
            })
            await self.manager.broadcast(message)
        except Exception as e:
            logger.error(f"广播事件失败: {e}")

    async def monitoring_loop(self):
        """监控数据推送循环"""
        logger.info("📊 监控数据推送循环启动")

        while self.running:
            try:
                # 采集数据
                data = await self.collector.collect_all()

                # 广播到所有连接
                message = json.dumps(data)
                await self.manager.broadcast(message)

            except Exception as e:
                logger.error(f"监控数据推送失败: {e}", exc_info=True)

            # 1 秒更新频率
            await asyncio.sleep(1)

        logger.info("📊 监控数据推送循环停止")

    async def start(self):
        """启动监控服务器"""
        logger.info(f"🚀 启动监控服务器: http://{self.host}:{self.port}")

        self.running = True

        # 启动监控循环（后台任务）
        asyncio.create_task(self.monitoring_loop())

        # 启动 HTTP 服务器
        config = uvicorn.Config(
            self.app,
            host=self.host,
            port=self.port,
            log_level="warning",  # 减少 uvicorn 日志
        )
        server = uvicorn.Server(config)
        await server.serve()

    def stop(self):
        """停止监控服务器"""
        logger.info("🛑 停止监控服务器")
        self.running = False

    def _get_dashboard_html(self) -> str:
        """返回监控面板 HTML"""
        return """<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Sniper Trading Monitor</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            color: #e0e0e0;
            padding: 20px;
        }

        .container {
            max-width: 1800px;
            margin: 0 auto;
        }

        h1 {
            text-align: center;
            color: #00d4ff;
            margin-bottom: 30px;
            font-size: 2.5em;
            text-shadow: 0 0 10px rgba(0, 212, 255, 0.5);
        }

        .dashboard {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(400px, 1fr));
            gap: 20px;
        }

        .card {
            background: rgba(255, 255, 255, 0.05);
            border-radius: 15px;
            padding: 20px;
            box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3);
            backdrop-filter: blur(10px);
            border: 1px solid rgba(255, 255, 255, 0.1);
        }

        .card h2 {
            color: #00d4ff;
            margin-bottom: 15px;
            font-size: 1.3em;
            display: flex;
            align-items: center;
            gap: 10px;
        }

        .card h2 .icon {
            font-size: 1.5em;
        }

        /* 仓位卡片 */
        .position {
            background: rgba(0, 212, 255, 0.05);
            border-left: 4px solid #00d4ff;
            padding: 15px;
            margin-bottom: 15px;
            border-radius: 8px;
        }

        .position-header {
            display: flex;
            justify-content: space-between;
            margin-bottom: 10px;
            font-weight: bold;
        }

        .position-symbol {
            font-size: 1.3em;
            color: #00d4ff;
        }

        .position-side {
            padding: 4px 12px;
            border-radius: 20px;
            font-weight: bold;
        }

        .position-side.LONG {
            background: rgba(46, 213, 115, 0.2);
            color: #2ed573;
        }

        .position-side.SHORT {
            background: rgba(255, 71, 87, 0.2);
            color: #ff4757;
        }

        .position-details {
            display: grid;
            grid-template-columns: repeat(2, 1fr);
            gap: 10px;
            font-size: 0.95em;
        }

        .position-details .label {
            color: #888;
        }

        .position-details .value {
            font-weight: bold;
        }

        .pnl.positive {
            color: #2ed573;
        }

        .pnl.negative {
            color: #ff4757;
        }

        /* 统计卡片 */
        .stats-grid {
            display: grid;
            grid-template-columns: repeat(2, 1fr);
            gap: 15px;
        }

        .stat-item {
            text-align: center;
            padding: 15px;
            background: rgba(0, 212, 255, 0.05);
            border-radius: 10px;
        }

        .stat-value {
            font-size: 2em;
            font-weight: bold;
            color: #00d4ff;
            margin-bottom: 5px;
        }

        .stat-label {
            color: #888;
            font-size: 0.9em;
        }

        /* WebSocket 状态 */
        .status-indicator {
            display: flex;
            align-items: center;
            gap: 10px;
            margin-bottom: 15px;
        }

        .status-dot {
            width: 12px;
            height: 12px;
            border-radius: 50%;
            background: #ff4757;
            animation: pulse 2s infinite;
        }

        .status-dot.connected {
            background: #2ed573;
        }

        @keyframes pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.5; }
        }

        /* 事件日志 */
        .event-log {
            max-height: 400px;
            overflow-y: auto;
            background: rgba(0, 0, 0, 0.3);
            border-radius: 8px;
            padding: 10px;
        }

        .event-item {
            padding: 10px;
            margin-bottom: 8px;
            border-radius: 5px;
            background: rgba(255, 255, 255, 0.03);
            border-left: 3px solid #00d4ff;
            font-size: 0.9em;
        }

        .event-item.open {
            border-left-color: #2ed573;
        }

        .event-item.close {
            border-left-color: #ff4757;
        }

        .event-item.warning {
            border-left-color: #ffa502;
        }

        .event-time {
            color: #888;
            font-size: 0.85em;
            margin-bottom: 5px;
        }

        /* 系统健康 */
        .health-bar {
            height: 20px;
            background: rgba(255, 255, 255, 0.1);
            border-radius: 10px;
            overflow: hidden;
            margin: 10px 0;
        }

        .health-fill {
            height: 100%;
            background: linear-gradient(90deg, #2ed573 0%, #ffa502 70%, #ff4757 90%);
            transition: width 0.3s;
        }

        /* 连接状态 */
        .connection-status {
            position: fixed;
            top: 20px;
            right: 20px;
            padding: 10px 20px;
            background: rgba(255, 71, 87, 0.2);
            border: 1px solid #ff4757;
            border-radius: 20px;
            font-weight: bold;
            z-index: 1000;
        }

        .connection-status.connected {
            background: rgba(46, 213, 115, 0.2);
            border-color: #2ed573;
            color: #2ed573;
        }

        .connection-status.disconnected {
            color: #ff4757;
        }

        /* 滚动条美化 */
        ::-webkit-scrollbar {
            width: 8px;
        }

        ::-webkit-scrollbar-track {
            background: rgba(255, 255, 255, 0.05);
        }

        ::-webkit-scrollbar-thumb {
            background: rgba(0, 212, 255, 0.3);
            border-radius: 4px;
        }

        ::-webkit-scrollbar-thumb:hover {
            background: rgba(0, 212, 255, 0.5);
        }
    </style>
</head>
<body>
    <div class="connection-status disconnected" id="connectionStatus">
        ⚠️ Disconnected
    </div>

    <div class="container">
        <h1>🎯 Sniper Trading Monitor</h1>

        <div class="dashboard">
            <!-- 当前持仓 -->
            <div class="card">
                <h2><span class="icon">📊</span> Current Positions</h2>
                <div id="positionsContainer">
                    <p style="color: #888;">No positions</p>
                </div>
            </div>

            <!-- 交易统计 -->
            <div class="card">
                <h2><span class="icon">📈</span> Trading Statistics</h2>
                <div class="stats-grid">
                    <div class="stat-item">
                        <div class="stat-value" id="totalTrades">0</div>
                        <div class="stat-label">Total Trades</div>
                    </div>
                    <div class="stat-item">
                        <div class="stat-value" id="winRate">0%</div>
                        <div class="stat-label">Win Rate</div>
                    </div>
                    <div class="stat-item">
                        <div class="stat-value" id="totalPnl">$0</div>
                        <div class="stat-label">Total P&L</div>
                    </div>
                    <div class="stat-item">
                        <div class="stat-value" id="avgPnl">$0</div>
                        <div class="stat-label">Avg P&L</div>
                    </div>
                </div>
            </div>

            <!-- WebSocket 状态 -->
            <div class="card">
                <h2><span class="icon">🔌</span> WebSocket Status</h2>
                <div class="status-indicator">
                    <div class="status-dot" id="wsStatusDot"></div>
                    <span id="wsStatusText">Disconnected</span>
                </div>
                <div class="stats-grid">
                    <div class="stat-item">
                        <div class="stat-value" id="wsConnections">0</div>
                        <div class="stat-label">Connections</div>
                    </div>
                    <div class="stat-item">
                        <div class="stat-value" id="wsMessages">0</div>
                        <div class="stat-label">Messages</div>
                    </div>
                    <div class="stat-item">
                        <div class="stat-value" id="wsSubscriptions">0</div>
                        <div class="stat-label">Subscriptions</div>
                    </div>
                    <div class="stat-item">
                        <div class="stat-value" id="wsErrors">0</div>
                        <div class="stat-label">Errors</div>
                    </div>
                </div>
            </div>

            <!-- OBI 统计 -->
            <div class="card">
                <h2><span class="icon">⚖️</span> OBI Interceptor</h2>
                <div class="stats-grid">
                    <div class="stat-item">
                        <div class="stat-value" id="obiUpdates">0</div>
                        <div class="stat-label">Updates</div>
                    </div>
                    <div class="stat-item">
                        <div class="stat-value" id="obiRejects">0</div>
                        <div class="stat-label">Rejects</div>
                    </div>
                    <div class="stat-item">
                        <div class="stat-value" id="obiRejectRate">0%</div>
                        <div class="stat-label">Reject Rate</div>
                    </div>
                    <div class="stat-item">
                        <div class="stat-value" id="obiSymbols">0</div>
                        <div class="stat-label">Symbols</div>
                    </div>
                </div>
            </div>

            <!-- 系统健康 -->
            <div class="card">
                <h2><span class="icon">💻</span> System Health</h2>
                <div>
                    <div class="label">CPU Usage</div>
                    <div class="health-bar">
                        <div class="health-fill" id="cpuBar" style="width: 0%"></div>
                    </div>
                    <div class="value" id="cpuValue">0%</div>
                </div>
                <div>
                    <div class="label">Memory Usage</div>
                    <div class="health-bar">
                        <div class="health-fill" id="memoryBar" style="width: 0%"></div>
                    </div>
                    <div class="value" id="memoryValue">0%</div>
                </div>
                <div>
                    <div class="label">Disk Usage</div>
                    <div class="health-bar">
                        <div class="health-fill" id="diskBar" style="width: 0%"></div>
                    </div>
                    <div class="value" id="diskValue">0%</div>
                </div>
            </div>

            <!-- 事件日志 -->
            <div class="card" style="grid-column: span 2;">
                <h2><span class="icon">📜</span> Event Log</h2>
                <div class="event-log" id="eventLog">
                    <p style="color: #888;">No events yet</p>
                </div>
            </div>
        </div>
    </div>

    <script>
        let ws;
        let reconnectAttempts = 0;
        const maxReconnectAttempts = 10;

        function connect() {
            const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
            ws = new WebSocket(`${protocol}//${window.location.host}/ws`);

            ws.onopen = () => {
                console.log('Connected to monitoring server');
                document.getElementById('connectionStatus').className = 'connection-status connected';
                document.getElementById('connectionStatus').textContent = '✅ Connected';
                reconnectAttempts = 0;
            };

            ws.onmessage = (event) => {
                const data = JSON.parse(event.data);
                handleData(data);
            };

            ws.onclose = () => {
                console.log('Disconnected from monitoring server');
                document.getElementById('connectionStatus').className = 'connection-status disconnected';
                document.getElementById('connectionStatus').textContent = '⚠️ Disconnected';

                // 自动重连
                if (reconnectAttempts < maxReconnectAttempts) {
                    reconnectAttempts++;
                    console.log(`Reconnecting in ${reconnectAttempts} seconds...`);
                    setTimeout(connect, reconnectAttempts * 1000);
                }
            };

            ws.onerror = (error) => {
                console.error('WebSocket error:', error);
            };
        }

        function handleData(data) {
            if (data.type === 'event') {
                addEvent(data.event);
                return;
            }

            if (data.type === 'event_log') {
                data.events.forEach(event => addEvent(event, false));
                return;
            }

            // 更新仓位
            if (data.positions) {
                updatePositions(data.positions);
            }

            // 更新交易统计
            if (data.trading_stats) {
                updateTradingStats(data.trading_stats);
            }

            // 更新 WebSocket 状态
            if (data.websocket) {
                updateWebSocketStatus(data.websocket);
            }

            // 更新 OBI 统计
            if (data.obi) {
                updateObiStats(data.obi);
            }

            // 更新系统健康
            if (data.system_health) {
                updateSystemHealth(data.system_health);
            }
        }

        function updatePositions(data) {
            const container = document.getElementById('positionsContainer');

            if (!data.positions || data.positions.length === 0) {
                container.innerHTML = '<p style="color: #888;">No positions</p>';
                return;
            }

            container.innerHTML = data.positions.map(pos => `
                <div class="position">
                    <div class="position-header">
                        <span class="position-symbol">${pos.symbol}</span>
                        <span class="position-side ${pos.side}">${pos.side} ${pos.leverage}x</span>
                    </div>
                    <div class="position-details">
                        <div>
                            <span class="label">Entry: </span>
                            <span class="value">$${pos.entry_price.toFixed(2)}</span>
                        </div>
                        <div>
                            <span class="label">Current: </span>
                            <span class="value">$${pos.current_price.toFixed(2)}</span>
                        </div>
                        <div>
                            <span class="label">P&L: </span>
                            <span class="value pnl ${pos.pnl >= 0 ? 'positive' : 'negative'}">
                                $${pos.pnl.toFixed(2)}
                            </span>
                        </div>
                        <div>
                            <span class="label">ROE: </span>
                            <span class="value pnl ${pos.roe >= 0 ? 'positive' : 'negative'}">
                                ${(pos.roe * 100).toFixed(2)}%
                            </span>
                        </div>
                        <div>
                            <span class="label">Stop Loss: </span>
                            <span class="value">$${pos.stop_loss_price.toFixed(2)}</span>
                        </div>
                        <div>
                            <span class="label">Holding: </span>
                            <span class="value">${formatDuration(pos.holding_duration)}</span>
                        </div>
                    </div>
                </div>
            `).join('');
        }

        function updateTradingStats(stats) {
            document.getElementById('totalTrades').textContent = stats.total_trades || 0;
            document.getElementById('winRate').textContent = ((stats.win_rate || 0) * 100).toFixed(1) + '%';
            document.getElementById('totalPnl').textContent = '$' + (stats.total_pnl || 0).toFixed(2);
            document.getElementById('avgPnl').textContent = '$' + (stats.avg_pnl || 0).toFixed(2);
        }

        function updateWebSocketStatus(ws) {
            const dot = document.getElementById('wsStatusDot');
            const text = document.getElementById('wsStatusText');

            if (ws.running) {
                dot.classList.add('connected');
                text.textContent = 'Connected';
            } else {
                dot.classList.remove('connected');
                text.textContent = 'Disconnected';
            }

            document.getElementById('wsConnections').textContent = ws.total_connections || 0;
            document.getElementById('wsMessages').textContent = ws.total_messages || 0;
            document.getElementById('wsSubscriptions').textContent = ws.total_subscriptions || 0;
            document.getElementById('wsErrors').textContent = ws.total_errors || 0;
        }

        function updateObiStats(obi) {
            document.getElementById('obiUpdates').textContent = obi.update_count || 0;
            document.getElementById('obiRejects').textContent = obi.reject_count || 0;
            document.getElementById('obiRejectRate').textContent = ((obi.reject_rate || 0) * 100).toFixed(1) + '%';
            document.getElementById('obiSymbols').textContent = (obi.symbols_tracked || []).length;
        }

        function updateSystemHealth(health) {
            if (health.error) return;

            document.getElementById('cpuBar').style.width = health.cpu_percent + '%';
            document.getElementById('cpuValue').textContent = health.cpu_percent.toFixed(1) + '%';

            document.getElementById('memoryBar').style.width = health.memory_percent + '%';
            document.getElementById('memoryValue').textContent = health.memory_percent.toFixed(1) + '%';

            document.getElementById('diskBar').style.width = health.disk_percent + '%';
            document.getElementById('diskValue').textContent = health.disk_percent.toFixed(1) + '%';
        }

        function addEvent(event, prepend = true) {
            const log = document.getElementById('eventLog');

            // 移除 "No events yet" 提示
            if (log.querySelector('p')) {
                log.innerHTML = '';
            }

            const eventDiv = document.createElement('div');
            eventDiv.className = `event-item ${event.type || ''}`;

            const time = new Date(event.timestamp).toLocaleTimeString();
            eventDiv.innerHTML = `
                <div class="event-time">${time}</div>
                <div>${event.message || JSON.stringify(event)}</div>
            `;

            if (prepend) {
                log.insertBefore(eventDiv, log.firstChild);

                // 限制显示数量
                while (log.children.length > 100) {
                    log.removeChild(log.lastChild);
                }
            } else {
                log.appendChild(eventDiv);
            }
        }

        function formatDuration(seconds) {
            const hours = Math.floor(seconds / 3600);
            const minutes = Math.floor((seconds % 3600) / 60);
            const secs = Math.floor(seconds % 60);

            if (hours > 0) {
                return `${hours}h ${minutes}m`;
            } else if (minutes > 0) {
                return `${minutes}m ${secs}s`;
            } else {
                return `${secs}s`;
            }
        }

        // 启动连接
        connect();

        // 心跳
        setInterval(() => {
            if (ws && ws.readyState === WebSocket.OPEN) {
                ws.send('ping');
            }
        }, 30000);
    </script>
</body>
</html>"""
