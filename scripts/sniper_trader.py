#!/usr/bin/env python3
"""
v8.0 狙击手模式主交易脚本（Sniper Mode Trading Service）

针对 200 USDT 超小资金的极低频、极高置信度交易系统：
- MTF 三重共振锁开仓
- AI Agent 双轨架构（宏观大局观 + 微观审批）
- 自然语言数据翻译器
- 外部情报嗅探器（Twitter + 新闻）
- 5秒滑点硬拦截
- 高杠杆孤注一掷（50% 资金）
- 移动止盈追求 1:5 盈亏比
- 把爆仓线当止损线
- Dry-Run 模式支持
- Telegram/Discord 实时预警
"""
import asyncio
import logging
import os
import sys
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, Optional, Tuple, Any
from enum import Enum

# 设置代理环境变量（在导入其他模块之前）
PROXY = os.environ.get("HTTPS_PROXY") or os.environ.get("HTTP_PROXY") or os.environ.get("ALL_PROXY")
if not PROXY:
    # 从 .env 加载代理设置
    from dotenv import load_dotenv
    project_root = Path(__file__).parent.parent
    dotenv_path = project_root / '.env'
    if dotenv_path.exists():
        load_dotenv(dotenv_path)
        PROXY = os.environ.get("HTTPS_PROXY") or os.environ.get("HTTP_PROXY") or os.environ.get("ALL_PROXY")

if PROXY:
    os.environ['HTTP_PROXY'] = PROXY
    os.environ['HTTPS_PROXY'] = PROXY
    os.environ['ALL_PROXY'] = PROXY
    print(f"Using proxy: {PROXY}")

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv

from src.exchange.exchange_info_manager import BinanceExchangeInfo
from src.exchange.sniper_position_manager import (
    SniperPositionManager,
    Side,
    CloseReason
)
from src.quantitative.mtf_resonance_lock import MTFResonanceLock, MTFSignal
from src.utils.webhook_alerter import WebhookAlerter, get_alerter
from src.utils.api_retry import exponential_backoff_retry, classify_binance_error
# P1-17: 健康检查和熔断器
from src.utils.health_checker import ExchangeHealthChecker, HealthStatus
from src.utils.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerManager,
    CircuitBreakerOpenError,
    CircuitBreakerConfig
)
from src.utils.degradation_strategy import (
    DegradationStrategy,
    DegradationLevel,
    EmergencyHandler
)


def validate_config() -> None:
    """
    P0-4 修复：启动时验证必需的配置项

    Raises:
        RuntimeError: 缺少必需的环境变量时抛出
    """
    errors = []

    # Binance API 配置（可选，允许空值用于公开端点）
    api_key = os.getenv('BINANCE_API_KEY', '')
    api_secret = os.getenv('BINANCE_API_SECRET', '')

    # 检查 AI Agent 配置（如果启用）
    if os.getenv('ENABLE_AI_AGENT', 'false').lower() == 'true':
        anthropic_key = os.getenv('ANTHROPIC_API_KEY')
        if not anthropic_key or anthropic_key == 'your_anthropic_api_key':
            errors.append("❌ ENABLE_AI_AGENT=true 但缺少 ANTHROPIC_API_KEY")

    # 如果有错误，抛出异常
    if errors:
        error_msg = "\n".join(errors) + "\n\n请检查 .env 文件配置！"
        raise RuntimeError(error_msg)

    # 提示 API 配置状态
    if api_key and api_secret:
        logger.info("✅ Binance API 已配置（可进行交易）")
    else:
        logger.info("⚠️ Binance API 未配置（仅使用公开端点，仅获取行情）")

    logger.info("✅ 配置验证通过")
from src.monitoring.state_broadcaster import StateBroadcaster

# v8.0 AI Agent 组件
from src.ai.decision_engine import ClaudeDecisionEngine
from src.ai.nlt_translator import NLTDataTranslator
from src.ai.macro_oracle import MacroOracle
from src.intelligence.web_scraper import IntelligenceSniffer
from src.execution.slippage_hardlock import SlippageHardlock

load_dotenv()

# 确保 logs 目录存在
Path('logs').mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - [%(name)s] - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/sniper_trader.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


def update_trading_log(scan_time: str, status: str, positions: Dict, signal: Optional[str] = None, no_trade_reason: str = "") -> None:
    """
    更新交易日志文档

    Args:
        scan_time: 扫描时间
        status: 系统状态
        positions: 持仓情况
        signal: 交易信号 (如果有)
        no_trade_reason: 不交易原因 (如果没有交易)
    """
    log_file = Path(__file__).parent.parent / "TRADING_LOG.md"

    # 格式化持仓信息
    position_info = ""
    if positions:
        for sym, pos in positions.items():
            entry = pos.get('entry', 0)
            side = pos.get('side', 'UNKNOWN')
            position_info += f"\n- **{sym}**: {side} (入场价 ${entry:.2f})"
    else:
        position_info = "\n- 无持仓"

    # 格式化交易信号
    if signal:
        trade_info = f"\n- **交易信号**: {signal}"
    else:
        trade_info = f"\n- **交易信号**: 无新信号\n- **不交易原因**: {no_trade_reason}"

    # 构建新的日志条目
    new_entry = f"""### {scan_time} - 扫描结果
- **状态**: {status}
- **持仓情况**:{position_info}
{trade_info}

"""

    try:
        if log_file.exists():
            # 读取现有内容
            content = log_file.read_text(encoding='utf-8')

            # 找到 "## 2026-XX-XX" 部分的开头
            today = datetime.now().strftime("%Y-%m-%d")
            header = f"## {today}"

            if header in content:
                # 在今天的日期下面插入新条目
                parts = content.split(header, 1)
                content = parts[0] + header + "\n" + new_entry + parts[1]
            else:
                # 添加新的日期部分
                content = content.strip() + f"\n\n{header}\n\n{new_entry}"
        else:
            # 创建新文件
            today = datetime.now().strftime("%Y-%m-%d")
            content = f"""# 交易日志 (Trading Log)

## {today}

{new_entry}
"""

        log_file.write_text(content, encoding='utf-8')
    except Exception as e:
        logger.warning(f"更新交易日志失败: {e}")


class DryRunMode(Enum):
    """Dry-Run 模式"""
    ENABLED = "DRY_RUN"
    DISABLED = "LIVE"


class SniperTrader:
    """
    v5.3 狙击手交易器（军工级战备版）

    核心理念：
    - 极低频（一周 1-2 次）
    - 极高置信度（三重共振）
    - 高杠杆孤注一掷（50% 资金）
    - 1:5 盈亏比（移动止盈）
    - 动态波动率安全垫
    - 订单生命周期 + 动量代偿
    - Dry-Run 模式支持
    - Telegram/Discord 实时预警
    """

    def __init__(
        self,
        testnet: bool = True,
        dry_run: bool = True,
        capital: float = 200.0,
        enable_broadcaster: bool = True,
        enable_ai_agent: bool = True,  # v8.0 新增
    ) -> None:
        """
        初始化狙击手交易器

        Args:
            testnet: 是否测试网
            dry_run: 是否启用 Dry-Run 模式
            capital: 总资金（USDT）
            enable_broadcaster: 是否启用状态广播（Redis Pub/Sub）
            enable_ai_agent: 是否启用 AI Agent（v8.0）
        """
        # P0-4: 配置验证（最先执行）
        validate_config()

        self.testnet = testnet
        self.dry_run = dry_run
        self.capital = capital
        self.enable_broadcaster = enable_broadcaster
        self.enable_ai_agent = enable_ai_agent  # v8.0

        # 初始化组件
        logger.info("初始化 v8.0 狙击手交易器...")
        self.exchange_info = BinanceExchangeInfo(testnet=testnet)
        self.position_manager = SniperPositionManager(self.exchange_info)
        self.mtf_lock = MTFResonanceLock()
        self.alerter = get_alerter()

        # v8.0 AI Agent 组件
        if self.enable_ai_agent:
            logger.info("初始化 AI Agent 组件...")
            self.decision_engine = ClaudeDecisionEngine()

            # P0-4 修复：检查 AI 客户端是否成功初始化
            if not self.decision_engine.client:
                raise RuntimeError(
                    "❌ ENABLE_AI_AGENT=true 但 Claude AI 客户端初始化失败！\n"
                    "可能原因：\n"
                    "1. ANTHROPIC_API_KEY 未设置或无效\n"
                    "2. anthropic 库未安装（运行: pip install anthropic）\n"
                    "3. API 额度不足\n\n"
                    "解决方案：\n"
                    "- 检查 .env 文件中的 ANTHROPIC_API_KEY\n"
                    "- 或设置 ENABLE_AI_AGENT=false 禁用 AI Agent"
                )

            self.translator = NLTDataTranslator()
            self.scraper = IntelligenceSniffer(
                twitter_bearer_token=os.getenv('TWITTER_BEARER_TOKEN')
            )
            self.macro_oracle = MacroOracle(self.decision_engine)
            self.slippage_guard = SlippageHardlock(
                threshold_pct=0.5,
                timeout_sec=5.0
            )
            logger.info("🤖 AI Agent 组件已启动")
        else:
            self.decision_engine = None
            self.translator = None
            self.scraper = None
            self.macro_oracle = None
            self.slippage_guard = None

        # 监控的交易对（减少到3个以提高扫描速度）
        self.watch_symbols = [
            'BTC/USDT', 'ETH/USDT', 'SOL/USDT',   # 主流币
        ]

        # 运行状态
        self.running = True

        # P0-2 修复：挂单追踪 + 并发锁保护
        self.pending_orders: Dict[str, Dict] = {}
        self._pending_lock = asyncio.Lock()  # 并发锁

        # P1-17: 初始化健康检查器和熔断器
        self.health_checker = ExchangeHealthChecker(self.exchange_info.exchange)
        self.circuit_breaker_manager = CircuitBreakerManager()

        # 创建交易熔断器（3次失败后触发，冷却5分钟）
        self.trading_breaker = self.circuit_breaker_manager.create_breaker(
            name="trading",
            config=CircuitBreakerConfig(
                failure_threshold=3,
                success_threshold=2,
                cooldown_seconds=300,  # 5分钟
            )
        )

        # 创建订单簿熔断器
        self.orderbook_breaker = self.circuit_breaker_manager.create_breaker(
            name="orderbook",
            config=CircuitBreakerConfig(
                failure_threshold=5,
                success_threshold=3,
                cooldown_seconds=60,  # 1分钟
            )
        )

        # P1-17: 初始化降级策略
        self.degradation_strategy = DegradationStrategy()
        self.emergency_handler = EmergencyHandler(self.position_manager, self.alerter)

        logger.info("🛡️ P1-17: 健康检查器、熔断器和降级策略已初始化")

        # 初始化状态广播器（进程间通信，非阻塞）
        self.state_broadcaster = None

        if self.enable_broadcaster:
            logger.info("初始化状态广播器...")
            self.state_broadcaster = StateBroadcaster()
            logger.info("📡 状态广播器已启动（Redis Pub/Sub）")

        # 打印配置
        self._print_config()

        # P1-14: 尝试从崩溃恢复
        self.load_state()

    def _print_config(self) -> None:
        """打印配置信息"""
        logger.info(f"\n{'='*60}")
        logger.info(f"🎯 v8.0 狙击手交易器已初始化")
        logger.info(f"{'='*60}")
        logger.info(f"  测试网: {'是' if self.testnet else '否（主网！）'}")
        logger.info(f"  模式: {'🧪 DRY-RUN（模拟）' if self.dry_run else '🔴 LIVE（实盘！）'}")
        logger.info(f"  资金: ${self.capital} USDT")
        logger.info(f"  监控交易对: {', '.join(self.watch_symbols)}")
        logger.info(f"  订单 TTL: 1 小时")
        logger.info(f"  动量代偿: 5 分钟内创新高/低 → 市价追入")
        if self.enable_ai_agent:
            logger.info(f"  AI Agent: 🤖 已启用（宏观大局观 + 微观审批 + 滑点硬拦截）")
        if self.enable_broadcaster:
            logger.info(f"  状态广播: Redis Pub/Sub（独立进程监控）")
        logger.info(f"{'='*60}\n")

    # ==================== P1-14: 状态持久化和崩溃恢复 ====================

    # 状态文件路径
    STATE_FILE = Path('state/sniper_state.json')
    STATE_VERSION = 1  # 状态文件版本号，用于兼容性检查

    def save_state(self) -> None:
        """
        P1-14: 保存交易状态到磁盘

        持久化内容：
        - positions: 当前持仓信息
        - closed_positions: 已平仓历史（用于统计）
        - pending_orders: 挂单信息
        - trade_count: 交易次数
        - daily_pnl: 当日盈亏
        - last_update: 最后更新时间

        调用时机：
        - 开仓后
        - 平仓后
        - 挂单创建/撤销后
        - 主循环每次迭代结束
        """
        try:
            # 确保 state 目录存在
            self.STATE_FILE.parent.mkdir(parents=True, exist_ok=True)

            # 序列化持仓信息
            positions_data = []
            for symbol, pos in self.position_manager.positions.items():
                pos_dict = {
                    'symbol': pos.symbol,
                    'side': pos.side.value,
                    'entry_price': pos.entry_price,
                    'quantity': pos.quantity,
                    'leverage': pos.leverage,
                    'stop_loss_price': pos.stop_loss_price,
                    'take_profit_price': pos.take_profit_price,
                    'trailing_stop_price': pos.trailing_stop_price,
                    'entry_time': pos.entry_time.isoformat() if pos.entry_time else None,
                    'pnl': pos.pnl,
                    'status': pos.status.value if hasattr(pos.status, 'value') else str(pos.status),
                }
                positions_data.append(pos_dict)

            # 序列化已平仓历史（最多保留最近 100 条）
            closed_positions_data = []
            for pos in self.position_manager.closed_positions[-100:]:
                pos_dict = {
                    'symbol': pos.symbol,
                    'side': pos.side.value,
                    'entry_price': pos.entry_price,
                    'quantity': pos.quantity,
                    'leverage': pos.leverage,
                    'stop_loss_price': pos.stop_loss_price,
                    'take_profit_price': pos.take_profit_price,
                    'trailing_stop_price': pos.trailing_stop_price,
                    'entry_time': pos.entry_time.isoformat() if pos.entry_time else None,
                    'pnl': pos.pnl,
                    'status': pos.status.value if hasattr(pos.status, 'value') else str(pos.status),
                }
                closed_positions_data.append(pos_dict)

            # 序列化挂单信息
            pending_orders_data = []
            for symbol, order in self.pending_orders.items():
                signal = order.get('signal')
                order_dict = {
                    'symbol': symbol,
                    'timestamp': order['timestamp'].isoformat(),
                    'side': order['side'].value,
                    'vwap': order['vwap'],
                    'breakthrough_price': order['breakthrough_price'],
                    # 保存信号的关键信息（不保存整个对象）
                    'signal_confidence': getattr(signal, 'confidence', 0),
                    'signal_locked': getattr(signal, 'is_locked', False),
                }
                pending_orders_data.append(order_dict)

            # 获取交易统计
            stats = self.position_manager.get_trading_statistics()

            # 构建完整状态
            state = {
                'version': self.STATE_VERSION,
                'positions': positions_data,
                'closed_positions': closed_positions_data,
                'pending_orders': pending_orders_data,
                'trade_count': stats['total_trades'],
                'daily_pnl': stats['total_pnl'],
                'last_update': datetime.now().isoformat(),
                'config': {
                    'capital': self.capital,
                    'testnet': self.testnet,
                    'dry_run': self.dry_run,
                }
            }

            # 原子写入：先写临时文件，再重命名
            temp_file = self.STATE_FILE.with_suffix('.tmp')
            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(state, f, indent=2, ensure_ascii=False)

            # 重命名临时文件为正式文件
            temp_file.replace(self.STATE_FILE)

            logger.debug(f"💾 状态已保存: {len(positions_data)} 持仓, {len(pending_orders_data)} 挂单")

        except Exception as e:
            logger.error(f"❌ 状态保存失败: {e}", exc_info=True)

    def load_state(self) -> bool:
        """
        P1-14: 从磁盘加载交易状态（崩溃恢复）

        Returns:
            是否成功加载状态
        """
        try:
            if not self.STATE_FILE.exists():
                logger.info("📂 未找到状态文件，从头开始")
                return False

            with open(self.STATE_FILE, 'r', encoding='utf-8') as f:
                state = json.load(f)

            # 版本兼容性检查
            if state.get('version', 0) != self.STATE_VERSION:
                logger.warning(
                    f"⚠️ 状态文件版本不匹配（文件: {state.get('version')}, 当前: {self.STATE_VERSION}），"
                    f"跳过恢复"
                )
                return False

            # 配置一致性检查
            saved_config = state.get('config', {})
            if saved_config.get('capital') != self.capital:
                logger.warning(
                    f"⚠️ 资金配置已变更（保存: {saved_config.get('capital')}, 当前: {self.capital}），"
                    f"跳过恢复"
                )
                return False

            last_update = state.get('last_update', 'Unknown')
            logger.info(f"📂 发现状态文件，最后更新: {last_update}")

            # 恢复持仓
            positions_data = state.get('positions', [])
            restored_positions = 0
            for pos_dict in positions_data:
                try:
                    from src.exchange.sniper_position_manager import (
                        SniperPosition, Side, PositionStatus
                    )

                    # 重建 SniperPosition 对象
                    position = SniperPosition(
                        symbol=pos_dict['symbol'],
                        side=Side(pos_dict['side']),
                        entry_price=pos_dict['entry_price'],
                        quantity=pos_dict['quantity'],
                        leverage=pos_dict['leverage'],
                        stop_loss_price=pos_dict['stop_loss_price'],
                        take_profit_price=pos_dict['take_profit_price'],
                        trailing_stop_price=pos_dict.get('trailing_stop_price'),
                        entry_time=datetime.fromisoformat(pos_dict['entry_time']) if pos_dict.get('entry_time') else datetime.now(),
                        pnl=pos_dict.get('pnl', 0),
                        status=PositionStatus(pos_dict.get('status', 'OPEN')),
                    )

                    # 添加到仓位管理器
                    self.position_manager.positions[position.symbol] = position
                    restored_positions += 1

                except Exception as e:
                    logger.error(f"恢复持仓失败: {pos_dict.get('symbol')} - {e}")
                    continue

            if restored_positions > 0:
                logger.info(f"✅ 恢复 {restored_positions} 个持仓")

            # 恢复已平仓历史
            closed_positions_data = state.get('closed_positions', [])
            restored_closed = 0
            for pos_dict in closed_positions_data:
                try:
                    from src.exchange.sniper_position_manager import (
                        SniperPosition, Side, PositionStatus
                    )

                    position = SniperPosition(
                        symbol=pos_dict['symbol'],
                        side=Side(pos_dict['side']),
                        entry_price=pos_dict['entry_price'],
                        quantity=pos_dict['quantity'],
                        leverage=pos_dict['leverage'],
                        stop_loss_price=pos_dict['stop_loss_price'],
                        take_profit_price=pos_dict['take_profit_price'],
                        trailing_stop_price=pos_dict.get('trailing_stop_price'),
                        entry_time=datetime.fromisoformat(pos_dict['entry_time']) if pos_dict.get('entry_time') else datetime.now(),
                        pnl=pos_dict.get('pnl', 0),
                        status=PositionStatus(pos_dict.get('status', 'CLOSED')),
                    )

                    self.position_manager.closed_positions.append(position)
                    restored_closed += 1

                except Exception as e:
                    logger.error(f"恢复历史持仓失败: {pos_dict.get('symbol')} - {e}")
                    continue

            if restored_closed > 0:
                logger.info(f"✅ 恢复 {restored_closed} 条历史记录")

            # 恢复挂单（注意：挂单有时间限制，需要检查是否过期）
            pending_orders_data = state.get('pending_orders', [])
            restored_orders = 0
            expired_orders = 0
            for order_dict in pending_orders_data:
                try:
                    order_time = datetime.fromisoformat(order_dict['timestamp'])
                    holding_duration = datetime.now() - order_time
                    holding_minutes = holding_duration.total_seconds() / 60

                    # 检查是否超时（超过 1 小时的挂单不再恢复）
                    if holding_minutes > 60:
                        logger.warning(
                            f"⏰ 挂单 {order_dict['symbol']} 已超时 "
                            f"({holding_minutes:.0f} 分钟)，跳过恢复"
                        )
                        expired_orders += 1
                        continue

                    # 重建 MTFSignal 对象（简化版，只保留必要信息）
                    from src.quantitative.mtf_resonance_lock import MTFSignal
                    signal = MTFSignal(
                        signal=1 if order_dict['side'] == 'LONG' else -1,
                        confidence=order_dict.get('signal_confidence', 0.8),
                        reasons=['从崩溃恢复'],
                        is_locked=order_dict.get('signal_locked', True),
                        wait_for_pullback=True,
                        suggested_entry_price=order_dict['vwap'],
                        breakthrough_price=order_dict['breakthrough_price'],
                    )

                    # 恢复挂单
                    self.pending_orders[order_dict['symbol']] = {
                        'signal': signal,
                        'timestamp': order_time,
                        'side': Side(order_dict['side']),
                        'vwap': order_dict['vwap'],
                        'breakthrough_price': order_dict['breakthrough_price'],
                    }
                    restored_orders += 1

                except Exception as e:
                    logger.error(f"恢复挂单失败: {order_dict.get('symbol')} - {e}")
                    continue

            if restored_orders > 0:
                logger.info(f"✅ 恢复 {restored_orders} 个挂单")
            if expired_orders > 0:
                logger.info(f"⏰ {expired_orders} 个挂单已过期，跳过恢复")

            # 打印恢复摘要
            stats = self.position_manager.get_trading_statistics()
            logger.info(f"\n{'='*60}")
            logger.info(f"🔄 崩溃恢复完成")
            logger.info(f"{'='*60}")
            logger.info(f"  持仓: {restored_positions}")
            logger.info(f"  历史: {restored_closed}")
            logger.info(f"  挂单: {restored_orders} (过期: {expired_orders})")
            logger.info(f"  交易次数: {stats['total_trades']}")
            logger.info(f"  总盈亏: ${stats['total_pnl']:+.2f}")
            logger.info(f"{'='*60}\n")

            return True

        except json.JSONDecodeError as e:
            logger.error(f"❌ 状态文件解析失败: {e}")
            return False
        except Exception as e:
            logger.error(f"❌ 状态加载失败: {e}", exc_info=True)
            return False

    async def check_and_trade(self, symbol: str) -> Optional[str]:
        """
        检查并执行交易（v8.0 AI Agent + 订单生命周期 + 动量代偿 + Dry-Run）

        流程：
        0. P1-17: 健康检查和熔断器检查
        1. MTF 三重共振检查
        2. 如果锁定，发送预警
        3. v8.0: AI Agent 宏观禁令检查
        4. v8.0: AI Agent 微观审批（3-5秒思考）
        5. v8.0: 滑点硬拦截（0.5%阈值）
        6. 检查是否允许开仓
        7. 判断是否需要等待回踩
        8. 如果需要回踩，挂单等待（TTL 1 小时）
        9. 监控动量：5 分钟内创新高/低 → 市价追入
        10. 执行开仓（或模拟）

        Args:
            symbol: 交易对

        Returns:
            交易结果消息
        """
        # P1-17: 0. 健康检查和熔断器检查
        health_result = await self.health_checker.health_check()

        # 记录健康状态
        if self.state_broadcaster:
            await self.state_broadcaster.broadcast_stats(
                self.health_checker.get_status_summary()
            )

        # 检查是否健康 - 即使不健康也继续交易（因为市场数据已加载）
        if not health_result.is_healthy():
            status_emoji = {
                HealthStatus.UNHEALTHY: "⚠️",
                HealthStatus.CRITICAL: "🚨",
            }.get(health_result.status, "⚠️")

            logger.warning(
                f"{status_emoji} 交易所状态: {health_result.status.value}，但继续交易（市场数据已加载）"
            )
            # 不再跳过交易，继续执行

        # P1-17: 检查交易熔断器
        if not self.trading_breaker.check():
            logger.warning(
                f"🚫 交易熔断器开启，跳过 {symbol} 交易机会"
            )

            # 发送熔断器预警
            await self.alerter.alert_system_warning(
                title="交易熔断器已触发",
                message=f"连续失败 {self.trading_breaker.failure_count} 次，冷却期中"
            )

            return "🚫 交易熔断器已触发"

        # 1. MTF 三重共振检查
        signal = await self.mtf_lock.check_triple_resonance(symbol)

        # 2. 如果无信号或未锁定，跳过
        if signal.signal == 0 or not signal.is_locked:
            # 记录为什么没有信号
            no_signal_reason = signal.reasons[0] if signal.reasons else "无明确原因"
            logger.info(f"【{symbol}】无交易信号: {no_signal_reason} | RSI:{signal.rsi if hasattr(signal, 'rsi') else 'N/A'}")
            return None

        # 3. 发送三重共振预警
        side_str = 'LONG' if signal.signal == 1 else 'SHORT'
        await self.alerter.alert_resonance_locked(
            symbol=symbol,
            side=side_str,
            confidence=signal.confidence,
            reasons=signal.reasons,
            entry_price=signal.breakthrough_price,
            vwap=signal.suggested_entry_price
        )

        # 4. v8.0: 更新宏观大局观（每小时）
        if self.enable_ai_agent:
            await self._update_macro_state_if_needed()

            # 5. v8.0: 检查宏观禁令
            if not self._check_macro_ban(symbol, side_str):
                logger.warning(f"🚫 {symbol} {side_str} 被宏观大局观禁止")
                return f"🚫 {symbol} {side_str} 被宏观大局观禁止"

        # 6. 获取当前价格
        ticker = self.exchange_info.exchange.fetch_ticker(symbol)
        current_price = ticker['last']

        # 7. v8.0: AI Agent 微观审批（如果启用）
        if self.enable_ai_agent:
            approved, ai_reason = await self._ai_micro_approval(
                symbol, signal, current_price
            )
            if not approved:
                logger.warning(f"🤖 AI 审批拒绝: {ai_reason}")
                return f"🤖 AI 审批拒绝: {ai_reason}"

        # 异步广播价格更新（非阻塞）
        if self.state_broadcaster:
            await self.state_broadcaster.broadcast_price(symbol, current_price)

        # 8. 检查是否允许开仓
        can_open, reason = self.position_manager.can_open_position(symbol)
        if not can_open:
            logger.warning(f"无法开仓 {symbol}: {reason}")
            return None

        # 9. 判断是否需要等待回踩
        if signal.wait_for_pullback and signal.suggested_entry_price:
            # P0-2 修复：使用异步锁保护挂单写入
            async with self._pending_lock:
                self.pending_orders[symbol] = {
                    'signal': signal,
                    'timestamp': datetime.now(),
                    'side': Side.LONG if signal.signal == 1 else Side.SHORT,
                    'vwap': signal.suggested_entry_price,
                    'breakthrough_price': signal.breakthrough_price,
                }

            # P1-14: 保存状态（挂单创建）
            self.save_state()

            logger.info(f"📝 {symbol} 挂单等待回踩 VWAP ${signal.suggested_entry_price:.2f}")

            return f"📝 挂单等待 {symbol} 回踩 VWAP ${signal.suggested_entry_price:.2f}"

        # 10. 不需要回踩，直接市价开仓
        side = Side.LONG if signal.signal == 1 else Side.SHORT
        position = self.position_manager.calculate_sniper_position(
            symbol=symbol,
            capital=self.capital,
            side=side,
            entry_price=current_price,
            exchange=self.exchange_info.exchange
        )

        if not position:
            logger.error(f"❌ 仓位计算失败: {symbol}")
            return None

        # 11. v8.0: 滑点检查（AI 思考期间价格是否偏离）
        if self.enable_ai_agent:
            try:
                latest_price = self.exchange_info.exchange.fetch_ticker(symbol)['last']
                passed, slippage_reason = self.slippage_guard.check_slippage(
                    symbol, latest_price, exchange=self.exchange_info.exchange
                )
                if not passed:
                    logger.warning(f"🚨 {slippage_reason}")
                    return f"🚨 {slippage_reason}"
            except Exception as e:
                error_msg = f"❌ P1-8: 滑点检查失败 - 无法获取 {symbol} 当前价格: {e}"
                logger.error(error_msg)
                return error_msg

        # 12. 执行开仓（或模拟）
        return await self._execute_open_position(position, current_price, "MARKET")

    async def _execute_open_position(
        self,
        position,
        execution_price: float,
        fill_type: str
    ) -> Optional[str]:
        """
        执行开仓（支持 Dry-Run）

        Args:
            position: 仓位对象
            execution_price: 成交价格
            fill_type: 成交类型（MARKET / LIMIT / MARKET_MOMENTUM）

        Returns:
            交易结果消息
        """
        symbol = position.symbol
        side_str = position.side.value

        # Dry-Run 模式
        if self.dry_run:
            logger.critical(f"🧪 [DRY-RUN] 模拟开仓：{symbol} {side_str} @ ${execution_price:.2f}")
            logger.critical(f"   杠杆: {position.leverage}x")
            logger.critical(f"   数量: {position.quantity:.6f}")
            logger.critical(f"   止损价: ${position.stop_loss_price:.2f}")
            logger.critical(f"   止盈价: ${position.take_profit_price:.2f}")
            logger.critical(f"   类型: {fill_type}")

            # 模拟开仓（不实际调用 API）
            self.position_manager.open_position(position)

            # P1-14: 保存状态
            self.save_state()

            # 异步广播开仓事件（非阻塞）
            if self.state_broadcaster:
                await self.state_broadcaster.broadcast_event({
                    'type': 'open',
                    'symbol': symbol,
                    'side': side_str,
                    'price': execution_price,
                    'message': f"🧪 [DRY-RUN] 模拟开仓 {symbol} {side_str} @ ${execution_price:.2f}",
                })

            return f"🧪 [DRY-RUN] 模拟开仓 {symbol} {side_str} @ ${execution_price:.2f}"

        # 实盘模式
        logger.critical(f"🔴 [LIVE] 实盘开仓：{symbol} {side_str} @ ${execution_price:.2f}")

        # P0-1 修复：实现真实下单逻辑
        try:
            # P1-17: 熔断器保护的 API 调用
            if not self.trading_breaker.check():
                error_msg = f"🚫 交易熔断器开启，拒绝下单 {symbol}"
                logger.error(error_msg)

                # 发送预警
                await self.alerter.alert_system_warning(
                    title="交易被熔断器拦截",
                    message=f"{symbol} {side_str}\n连续失败 {self.trading_breaker.failure_count} 次"
                )

                return error_msg

            # 1. 调用 Binance API 下单
            side = 'buy' if signal.signal == 1 else 'sell'

            try:
                if fill_type == 'market':
                    # 市价单
                    order = self.exchange_info.exchange.create_market_order(
                        symbol=symbol,
                        side=side,
                        amount=position.quantity,
                        params={
                            'leverage': position.leverage,
                        }
                    )
                else:
                    # 限价单
                    order = self.exchange_info.exchange.create_limit_order(
                        symbol=symbol,
                        side=side,
                        amount=position.quantity,
                        price=execution_price,
                        params={
                            'leverage': position.leverage,
                            'timeInForce': 'GTC',  # Good Till Cancel
                        }
                    )

                # P1-17: 订单成功，记录熔断器成功
                self.trading_breaker.on_success()

            except Exception as api_error:
                # P1-17: API 调用失败，记录熔断器失败
                self.trading_breaker.on_failure()
                raise api_error

            # 2. 验证订单是否成功
            if not order or order.get('status') not in ['filled', 'open']:
                error_msg = f"❌ 订单下单失败：{order}"
                logger.error(error_msg)
                return error_msg

            # 3. 更新持仓信息
            if order.get('status') == 'filled':
                # 市价单立即成交
                position.entry_price = float(order.get('average', execution_price))
                position.order_id = order.get('id')
                logger.info(f"✅ 订单已成交：{order.get('id')} @ ${position.entry_price:.2f}")
            else:
                # 限价单挂单中
                position.order_id = order.get('id')
                logger.info(f"⏳ 限价单已挂单：{order.get('id')} @ ${execution_price:.2f}")

            # 4. 记录到仓位管理器
            self.position_manager.open_position(position)

            # P1-14: 保存状态
            self.save_state()

        except Exception as e:
            error_msg = f"❌ 实盘下单异常：{e}"
            logger.error(error_msg, exc_info=True)
            # 发送错误预警
            await self.alerter.alert_error(symbol, f"下单失败: {e}")
            return error_msg

        # 异步广播开仓事件（非阻塞）
        if self.state_broadcaster:
            await self.state_broadcaster.broadcast_event({
                'type': 'open',
                'symbol': symbol,
                'side': side_str,
                'price': execution_price,
                'message': f"🎯 [LIVE] 实盘开仓 {symbol} {side_str} @ ${execution_price:.2f}",
            })

        # 发送订单成交预警
        await self.alerter.alert_order_filled(
            symbol=symbol,
            side=side_str,
            entry_price=execution_price,
            quantity=position.quantity,
            leverage=position.leverage,
            stop_loss=position.stop_loss_price,
            take_profit=position.take_profit_price,
            fill_type=fill_type
        )

        return f"🎯 已开仓 {symbol} {side_str} @ ${execution_price:.2f}"

    @exponential_backoff_retry(max_retries=3, base_delay=2.0)
    async def check_pending_orders(self) -> None:
        """
        P0-2 修复：使用异步锁保护挂单检查
        检查挂单状态（生命周期 + 动量代偿）

        逻辑：
        1. 检查挂单 TTL（超时 1 小时 → 撤销）
        2. 检查动量代偿（5 分钟内创新高/低 → 市价追入）
        3. 检查价格回踩（价格触及 VWAP → 限价成交）
        """
        # P0-2: 使用异步锁保护整个检查过程
        async with self._pending_lock:
            if not self.pending_orders:
                return

            # 创建副本，避免在迭代期间修改
            orders_to_check = list(self.pending_orders.items())

        # 在锁外执行耗时操作，减少锁持有时间
        for symbol, order in orders_to_check:
            signal = order['signal']
            order_time = order['timestamp']
            vwap = order['vwap']
            breakthrough_price = order['breakthrough_price']
            side = order['side']

            # 获取当前价格
            try:
                ticker = self.exchange_info.exchange.fetch_ticker(symbol)
                current_price = ticker['last']
            except Exception as e:
                logger.error(f"获取 {symbol} 价格失败: {e}")
                continue

            # 1. 检查 TTL（超时 1 小时）
            holding_duration = datetime.now() - order_time
            holding_minutes = holding_duration.total_seconds() / 60

            if holding_minutes > 60:
                # P0-2: 使用锁保护删除操作
                async with self._pending_lock:
                    if symbol in self.pending_orders:
                        del self.pending_orders[symbol]
                # P1-14: 保存状态（挂单超时撤销）
                self.save_state()
                logger.warning(f"⏰ {symbol} 挂单超时 1 小时，已撤销")
                continue

            # 2. 检查动量代偿（5 分钟内创新高/低）
            if holding_minutes <= 5:
                if side == Side.LONG and current_price > breakthrough_price:
                    # 做多创新高 → 市价追入
                    logger.critical(f"🚀 {symbol} 动量代偿触发！价格 ${current_price:.2f} > 突破价 ${breakthrough_price:.2f}")

                    position = self.position_manager.calculate_sniper_position(
                        symbol=symbol,
                        capital=self.capital,
                        side=side,
                        entry_price=current_price,
                        exchange=self.exchange_info.exchange
                    )

                    if position:
                        await self._execute_open_position(position, current_price, "MARKET_MOMENTUM")
                        async with self._pending_lock:
                            if symbol in self.pending_orders:
                                del self.pending_orders[symbol]
                        # P1-14: 保存状态（动量代偿成交）
                        self.save_state()
                        continue

                elif side == Side.SHORT and current_price < breakthrough_price:
                    # 做空创新低 → 市价追入
                    logger.critical(f"🚀 {symbol} 动量代偿触发！价格 ${current_price:.2f} < 突破价 ${breakthrough_price:.2f}")

                    position = self.position_manager.calculate_sniper_position(
                        symbol=symbol,
                        capital=self.capital,
                        side=side,
                        entry_price=current_price,
                        exchange=self.exchange_info.exchange
                    )

                    if position:
                        await self._execute_open_position(position, current_price, "MARKET_MOMENTUM")
                        async with self._pending_lock:
                            if symbol in self.pending_orders:
                                del self.pending_orders[symbol]
                        # P1-14: 保存状态（动量代偿成交）
                        self.save_state()
                        continue

            # 3. 检查价格回踩（触及 VWAP → 限价成交）
            if side == Side.LONG and current_price <= vwap:
                # 做多回踩到 VWAP → 成交
                logger.info(f"✅ {symbol} 回踩到 VWAP ${vwap:.2f}")

                position = self.position_manager.calculate_sniper_position(
                    symbol=symbol,
                    capital=self.capital,
                    side=side,
                    entry_price=vwap,
                    exchange=self.exchange_info.exchange
                )

                if position:
                    await self._execute_open_position(position, vwap, "LIMIT")
                    async with self._pending_lock:
                        if symbol in self.pending_orders:
                            del self.pending_orders[symbol]
                    # P1-14: 保存状态（VWAP 限价成交）
                    self.save_state()
                    continue

            elif side == Side.SHORT and current_price >= vwap:
                # 做空回踩到 VWAP → 成交
                logger.info(f"✅ {symbol} 回踩到 VWAP ${vwap:.2f}")

                position = self.position_manager.calculate_sniper_position(
                    symbol=symbol,
                    capital=self.capital,
                    side=side,
                    entry_price=vwap,
                    exchange=self.exchange_info.exchange
                )

                if position:
                    await self._execute_open_position(position, vwap, "LIMIT")
                    async with self._pending_lock:
                        if symbol in self.pending_orders:
                            del self.pending_orders[symbol]
                    # P1-14: 保存状态（VWAP 限价成交）
                    self.save_state()
                    continue

    async def update_positions(self) -> None:
        """更新仓位（移动止盈、止损检查 + 预警）"""
        if not self.position_manager.positions:
            return

        # 获取所有持仓的当前价格
        prices = {}
        for symbol in self.position_manager.positions.keys():
            try:
                ticker = self.exchange_info.exchange.fetch_ticker(symbol)
                prices[symbol] = ticker['last']

                # 异步广播价格更新（非阻塞）
                if self.state_broadcaster:
                    await self.state_broadcaster.broadcast_price(symbol, prices[symbol])

            except Exception as e:
                logger.error(f"获取 {symbol} 价格失败: {e}")
                continue

        # 1. 检查紧急平仓（达到爆仓线）
        emergency_close, reason = self.position_manager.should_emergency_close_all(prices)
        if emergency_close:
            logger.critical(f"🚨 紧急平仓触发！{reason}")

            for symbol, exit_price in prices.items():
                position = self.position_manager.positions.get(symbol)
                if position:
                    self.position_manager.close_position(symbol, exit_price, CloseReason.STOP_LOSS)

                    # P1-14: 保存状态
                    self.save_state()

                    # 发送预警
                    await self.alerter.alert_stop_loss(
                        symbol=symbol,
                        side=position.side.value,
                        entry_price=position.entry_price,
                        exit_price=exit_price,
                        pnl=position.pnl,
                    )
            return

        # 2. 检查每个仓位的平仓条件
        for symbol, current_price in prices.items():
            should_close, reason, close_reason = self.position_manager.should_close_position(symbol, current_price)

            if should_close:
                position = self.position_manager.positions.get(symbol)
                if not position:
                    continue

                # 平仓
                closed_position = self.position_manager.close_position(symbol, current_price, close_reason)

                if closed_position:
                    # P1-14: 保存状态
                    self.save_state()

                    # 异步广播平仓事件（非阻塞）
                    if self.state_broadcaster:
                        await self.state_broadcaster.broadcast_event({
                            'type': 'close',
                            'symbol': symbol,
                            'side': position.side.value,
                            'entry_price': position.entry_price,
                            'exit_price': current_price,
                            'pnl': position.pnl,
                            'reason': close_reason.value,
                            'message': f"✅ 平仓 {symbol} {position.side.value} @ ${current_price:.2f} | P&L: ${position.pnl:+.2f}",
                        })

                    # 根据平仓原因发送不同预警
                    if close_reason == CloseReason.TIME_STOP:
                        holding_duration = datetime.now() - position.entry_time
                        holding_hours = holding_duration.total_seconds() / 3600
                        roe = self.position_manager.calculate_roe(position, current_price)

                        await self.alerter.alert_time_stop(
                            symbol=symbol,
                            side=position.side.value,
                            holding_hours=holding_hours,
                            roe=roe
                        )

                    elif close_reason == CloseReason.TRAILING_STOP:
                        roe = self.position_manager.calculate_roe(position, current_price)

                        await self.alerter.alert_trailing_stop(
                            symbol=symbol,
                            side=position.side.value,
                            entry_price=position.entry_price,
                            exit_price=current_price,
                            pnl=position.pnl,
                            roe=roe
                        )

                continue

            # 3. 更新移动止盈
            self.position_manager.update_trailing_stop(symbol, current_price)

        # 4. 打印当前盈亏
        total_pnl, total_pnl_pct = self.position_manager.get_total_unrealized_pnl(prices)
        if total_pnl != 0:
            logger.info(f"💰 当前盈亏: ${total_pnl:+.2f} ({total_pnl_pct:+.2%})")

    async def run(self, check_interval_minutes: int = 3) -> None:
        """
        主循环（极低频 + 挂单管理）

        策略：
        - 每 N 分钟检查一次 MTF 三重共振
        - 每次循环检查挂单状态
        - 平时只更新移动止盈
        - 一天最多 1-2 次开仓机会

        Args:
            check_interval_minutes: 检查间隔（分钟）
        """
        logger.info("\n" + "="*60)
        logger.info(f"🎯 v7.3 终极防弹狙击手模式启动")
        logger.info(f"{'🧪 DRY-RUN 模式' if self.dry_run else '🔴 LIVE 实盘模式'}")
        logger.info("="*60 + "\n")

        check_interval = check_interval_minutes * 60  # 转换为秒

        # P1-17: 健康检查间隔（更频繁的检查）
        health_check_interval = 60  # 每分钟检查一次
        last_health_check = 0

        while self.running:
            try:
                current_time = asyncio.get_event_loop().time()
                logger.info(f"\n⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} - 开始扫描")

                # P1-17: 定期健康检查
                if current_time - last_health_check >= health_check_interval:
                    health_result = await self.health_checker.health_check()

                    # 更新降级策略
                    degradation_action = self.degradation_strategy.update_strategy(
                        health_result.status.value
                    )

                    # 广播健康状态
                    if self.state_broadcaster:
                        await self.state_broadcaster.broadcast_stats(
                            self.health_checker.get_status_summary()
                        )

                    # 如果不健康，发送警告
                    if not health_result.is_healthy():
                        await self.alerter.alert_system_warning(
                            title=f"交易所健康检查: {health_result.status.value}",
                            message=f"错误: {', '.join(health_result.errors)}\n"
                                   f"降级策略: {degradation_action.description}"
                        )

                    # P1-17: 检查是否需要紧急平仓
                    if self.degradation_strategy.should_emergency_close():
                        logger.critical("🚨 检测到严重故障，执行紧急平仓策略")
                        await self.emergency_handler.handle_critical_failure(
                            reason="交易所严重不健康",
                            force_close=True
                        )

                    last_health_check = current_time

                # P1-17: 检查降级策略是否允许开仓
                if not self.degradation_strategy.can_open_position():
                    logger.warning("⚠️ 降级策略禁止新开仓，跳过交易扫描")
                    # 但仍然需要更新持仓和检查挂单

                # 1. 更新仓位
                await self.update_positions()

                # 2. 检查挂单状态
                await self.check_pending_orders()

                # P1-17: 检查降级策略是否允许开仓
                if not self.degradation_strategy.can_open_position():
                    logger.warning("⚠️ 降级策略禁止新开仓，跳过交易扫描")
                    # 但仍然需要更新持仓和检查挂单
                else:
                    # 3. 检查是否可以开新仓
                    if len(self.position_manager.positions) < self.position_manager.max_positions:
                        no_signal_reasons = []  # 收集所有无信号原因
                        for symbol in self.watch_symbols:
                            message = await self.check_and_trade(symbol)

                            if message:
                                logger.critical(message)
                                break  # 最多开一个仓
                            else:
                                # 获取该币种的无信号原因
                                # 由于 check_and_trade 返回 None，我们从日志中获取
                                pass

                        # 汇总无信号原因
                        if no_signal_reasons:
                            no_trade_reason = "; ".join(no_signal_reasons[:3])  # 最多显示3个

                # 4. 打印统计
                stats = self.position_manager.get_trading_statistics()
                if stats['total_trades'] > 0:
                    logger.info(
                        f"📊 交易统计: {stats['total_trades']} 笔 | "
                        f"胜率 {stats['win_rate']:.0%} | "
                        f"总盈亏 ${stats['total_pnl']:+.2f}"
                    )

                # 打印挂单状态
                if self.pending_orders:
                    logger.info(f"📝 挂单中: {', '.join(self.pending_orders.keys())}")

                # 记录本次扫描结果到日志
                current_time = datetime.now().strftime("%H:%M:%S")
                trade_made = len(self.position_manager.positions) > 0  # 有持仓=可能交易了

                # 检查是否有新开仓（简单判断：如果有持仓但不在上次扫描的列表中）
                # 这里简化为：检查本次是否有交易信号触发
                # 由于交易后会 break，我们通过检查是否完成了整个 symbol 循环来判断
                # 这里简单处理：没有 pending_orders 且有持仓=可能开仓了
                has_position = len(self.position_manager.positions) > 0

                # 更新交易日志
                if trade_made:
                    # 有持仓/交易
                    positions_info = {}
                    for sym, pos in self.position_manager.positions.items():
                        positions_info[sym] = {
                            'side': pos.get('side', 'UNKNOWN'),
                            'entry': pos.get('entry', 0)
                        }
                    update_trading_log(
                        scan_time=current_time,
                        status="正常运行 - 有持仓",
                        positions=positions_info,
                        signal="持仓中，继续持有"
                    )
                else:
                    # 无持仓，无交易
                    no_trade_reason = "未满足开仓条件，请查看日志了解详情"
                    update_trading_log(
                        scan_time=current_time,
                        status="正常运行",
                        positions={},
                        no_trade_reason=no_trade_reason
                    )

                # P1-14: 定期保存状态（每次循环结束）
                self.save_state()

                logger.info(f"⏰ 下次扫描: {check_interval // 60} 分钟后\n")

                await asyncio.sleep(check_interval)

            except KeyboardInterrupt:
                logger.info("\n收到中断信号")
                break
            except Exception as e:
                logger.error(f"主循环异常: {e}", exc_info=True)
                await asyncio.sleep(60)  # 异常后等待 1 分钟

        logger.info("🛑 狙击手交易器已停止")

    async def close(self) -> None:
        """清理资源"""
        logger.info("清理资源...")

        # P1-14: 关闭前保存状态
        self.save_state()

        # v8.0: 关闭 Web Scraper
        if self.scraper:
            self.scraper.close()
            logger.info("🔍 Web Scraper 已关闭")

        # 关闭状态广播器
        if self.state_broadcaster:
            await self.state_broadcaster.close()
            logger.info("📡 状态广播器已关闭")

        await self.mtf_lock.close()
        await self.alerter.close()

    # ==================== v8.0 AI Agent 辅助方法 ====================

    async def _update_macro_state_if_needed(self) -> None:
        """
        更新宏观大局观（每小时）

        注意：MacroOracle 内部管理缓存和时间检查逻辑，
        这里只需调用生成方法，无需存储返回值。
        """
        if not self.macro_oracle:
            return

        logger.info("🔄 触发宏观大局观更新...")

        # 抓取外部情报
        intelligence = {
            'tweets': await self.scraper.scrape_twitter_sentiment(
                self.watch_symbols[0].replace('/', ''), limit=50
            ),
            'news': await self.scraper.scrape_macro_news(limit=10)
        }

        # MacroOracle 会检查是否需要更新
        # 如果距离上次更新不足 1 小时，会返回缓存的值
        await self.macro_oracle.generate_macro_state(intelligence)

    def _check_macro_ban(self, symbol: str, side_str: str) -> bool:
        """
        检查宏观禁令

        从 MacroOracle 获取缓存的宏观状态（单一数据源）。
        """
        if not self.macro_oracle:
            return True  # AI Agent 未启用，默认允许

        # 从 MacroOracle 获取缓存的宏观状态
        macro_state = self.macro_oracle.get_cached_state()

        if not macro_state:
            return True  # 没有宏观状态，默认允许

        # 检查禁令
        if side_str.upper() in macro_state.trading_bans:
            logger.warning(
                f"🚫 {symbol} {side_str} 被宏观禁令阻止 "
                f"(原因: {macro_state.reasoning})"
            )
            return False

        return True

    async def _ai_micro_approval(
        self,
        symbol: str,
        signal: MTFSignal,
        current_price: float
    ) -> Tuple[bool, str]:
        """
        AI 微观审批（3-5秒思考）

        Args:
            symbol: 交易对
            signal: MTF 信号
            current_price: 当前价格

        Returns:
            (是否通过, 原因)
        """
        if not self.decision_engine:
            return True, "AI Agent 未启用"

        try:
            # 1. 锁定触发价格（滑点保护）
            self.slippage_guard.lock_trigger_price(symbol, current_price)

            # 2. 翻译微观数据成自然语言
            micro_snapshot = {
                'symbol': symbol,
                'price': current_price,
                'funding_rate': getattr(signal, 'funding_rate', 0),
                'obi': getattr(signal, 'obi', 0),
                'volume_15m': getattr(signal, 'volume_15m', 0),
                'avg_volume_15m': getattr(signal, 'avg_volume_15m', 0),
                'ema_distance': getattr(signal, 'ema_distance', 0),
            }
            micro_report = self.translator.translate_micro_snapshot(micro_snapshot)

            # 3. 翻译宏观状态
            macro_report = ""
            if self.macro_oracle:
                macro_state = self.macro_oracle.get_cached_state()
                if macro_state:
                    macro_report = self.translator.translate_macro_state(
                        macro_state.__dict__
                    )

            # 4. 请求 AI 确认
            logger.info(f"🤖 请求 AI 审批: {symbol}...")
            decision = await self.decision_engine.analyze_market(
                symbol=symbol,
                price=current_price,
                price_history=[],  # TODO: 从历史数据获取
                market_data={
                    'micro_report': micro_report,
                    'macro_report': macro_report,
                    'mtf_signal': {
                        'side': 'LONG' if signal.signal == 1 else 'SHORT',
                        'confidence': signal.confidence,
                        'reasons': signal.reasons,
                    }
                }
            )

            # 5. 判断 AI 决策
            if decision.action == 'hold':
                return False, f"AI 建议持有（置信度: {decision.confidence:.2f}）"
            elif decision.action == 'buy' and signal.signal == -1:
                return False, "AI 建议买入，但 MTF 信号为做空，冲突"
            elif decision.action == 'sell' and signal.signal == 1:
                return False, "AI 建议卖出，但 MTF 信号为做多，冲突"
            elif decision.confidence < 0.6:
                return False, f"AI 置信度过低 ({decision.confidence:.2f} < 0.6)"
            else:
                logger.info(
                    f"✅ AI 审批通过: {decision.action} "
                    f"(置信度: {decision.confidence:.2f})"
                )
                return True, f"AI 审批通过（{decision.reasoning}）"

        except Exception as e:
            logger.error(f"AI 审批失败: {e}")
            # 失败时保守处理：允许通过（不影响交易）
            return True, f"AI 审批异常，默认通过（{e}）"


def main():
    """主函数"""
    # 从环境变量读取配置
    testnet = os.getenv('BINANCE_TESTNET', 'true').lower() == 'true'
    dry_run = os.getenv('DRY_RUN', 'true').lower() == 'true'
    capital = float(os.getenv('CAPITAL', '200'))

    # 主网模式确认
    if not testnet:
        logger.critical("⚠️⚠️⚠️ 主网模式！将使用真实资金！⚠️⚠️⚠️")
        # 自动确认用于测试（实际交易时请手动确认）
        confirm = os.getenv('AUTO_CONFIRM', 'yes')
        if confirm.lower() != 'yes':
            confirm = input("确认继续？(yes/no): ")
            if confirm.lower() != 'yes':
                logger.info("已取消")
                return

    # 实盘模式确认
    if not dry_run:
        logger.critical("⚠️⚠️⚠️ LIVE 实盘模式！将使用真实资金下单！⚠️⚠️⚠️")
        # 自动确认用于测试（实际交易时请手动确认）
        confirm = os.getenv('AUTO_CONFIRM', 'yes')
        if confirm.lower() != 'yes':
            confirm = input("确认继续？(yes/no): ")
            if confirm.lower() != 'yes':
                logger.info("已取消")
                return

    trader = SniperTrader(
        testnet=testnet,
        dry_run=dry_run,
        capital=capital,
        enable_ai_agent=os.getenv('ENABLE_AI_AGENT', 'true').lower() == 'true',
        enable_broadcaster=False,  # 禁用 Redis 广播，避免延迟
    )

    try:
        asyncio.run(trader.run())
    except KeyboardInterrupt:
        logger.info("\n收到中断信号")
    finally:
        asyncio.run(trader.close())


if __name__ == '__main__':
    main()
