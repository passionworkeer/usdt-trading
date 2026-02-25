"""
v5.0: Binance exchangeInfo 精度处理器

解决超小资金（200 USDT）的 MIN_NOTIONAL 拦截死局：
- 实时获取交易对的 precision、limits、MIN_NOTIONAL
- 动态计算最小可开仓数量
- 确保订单始终符合 exchange 规则
"""
import logging
import ccxt
import os
import asyncio
from typing import Dict, Optional, Tuple
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


@dataclass
class SymbolInfo:
    """交易对精度信息"""
    symbol: str
    base_asset: str  # BTC
    quote_asset: str  # USDT

    # 数量精度
    quantity_precision: int  # BTC 数量小数位
    min_quantity: float  # 最小数量
    max_quantity: float  # 最大数量
    step_size: float  # 数量步长

    # 价格精度
    price_precision: int  # 价格小数位
    min_price: float  # 最小价格
    max_price: float  # 最大价格
    tick_size: float  # 价格步长

    # 名义价值限制
    min_notional: float  # 最小名义价值（USDT）- 200U 的核心障碍
    max_notional: float  # 最大名义价值

    # 杠杆限制
    max_leverage: int  # 最大杠杆倍数


class BinanceExchangeInfo:
    """
    Binance exchangeInfo 管理器

    功能：
    1. 实时获取交易对规则
    2. 计算符合 MIN_NOTIONAL 的最小开仓量
    3. 数量和价格标准化（符合 step_size、tick_size）
    4. 针对 200U 超小资金优化
    """

    def __init__(self, testnet: bool = True):
        """
        初始化 exchangeInfo 管理器

        Args:
            testnet: 是否测试网
        """
        self.testnet = testnet
        self.symbol_info_cache: Dict[str, SymbolInfo] = {}

        # 初始化 CCXT
        self.exchange = ccxt.binance({
            'apiKey': os.getenv('BINANCE_API_KEY'),
            'secret': os.getenv('BINANCE_API_SECRET'),
            'enableRateLimit': True,
            'options': {
                'defaultType': 'future',
                # v6.1: 禁用 CCXT 的默认时间同步，使用我们自己的
                'adjustForTimeDifference': False,  # 我们自己管理时间偏移
            },
        })

        if testnet:
            self.exchange.urls['api'] = {
                'public': 'https://testnet.binancefuture.com/fapi/v1',
                'private': 'https://testnet.binancefuture.com/fapi/v1',
            }

        # 加载市场
        self.exchange.load_markets()
        logger.info(f"✅ 已加载 {len(self.exchange.markets)} 个交易对规则")

        # v6.1: 初始化时间同步管理器
        self.time_sync_manager = None

    def fetch_symbol_info(self, symbol: str) -> SymbolInfo:
        """
        获取交易对精度信息（带缓存）

        Args:
            symbol: 交易对（如 'BTC/USDT'）

        Returns:
            SymbolInfo 对象
        """
        # 检查缓存
        if symbol in self.symbol_info_cache:
            return self.symbol_info_cache[symbol]

        # 从 CCXT markets 获取
        market = self.exchange.market(symbol)

        # 解析信息
        info = SymbolInfo(
            symbol=symbol,
            base_asset=market['base'],
            quote_asset=market['quote'],

            # 数量精度
            quantity_precision=market['precision']['amount'],
            min_quantity=float(market['limits']['amount']['min']),
            max_quantity=float(market['limits']['amount']['max']),
            step_size=float(market['precision']['amount']) if isinstance(market['precision']['amount'], float) else 10 ** -market['precision']['amount'],

            # 价格精度
            price_precision=market['precision']['price'],
            min_price=float(market['limits']['price']['min']),
            max_price=float(market['limits']['price']['max']),
            tick_size=float(market['precision']['price']) if isinstance(market['precision']['price'], float) else 10 ** -market['precision']['price'],

            # 名义价值限制
            min_notional=float(market['limits']['cost']['min']),  # 关键！200U 的生死线
            max_notional=float(market['limits']['cost']['max']),

            # 杠杆
            max_leverage=market.get('info', {}).get('maxLeverage', 125),  # Binance 合约最大 125x
        )

        # 缓存
        self.symbol_info_cache[symbol] = info

        logger.info(f"✅ 获取 {symbol} 精度信息:")
        logger.info(f"  MIN_NOTIONAL: ${info.min_notional:.2f} USDT")
        logger.info(f"  数量步长: {info.step_size}")
        logger.info(f"  价格步长: {info.tick_size}")
        logger.info(f"  最大杠杆: {info.max_leverage}x")

        return info

    def round_quantity(self, symbol: str, quantity: float) -> float:
        """
        标准化数量（符合 step_size）

        Args:
            symbol: 交易对
            quantity: 原始数量

        Returns:
            标准化后的数量
        """
        info = self.fetch_symbol_info(symbol)

        # 向下取整到 step_size
        rounded = int(quantity / info.step_size) * info.step_size

        # 确保不小于 min_quantity
        if rounded < info.min_quantity:
            rounded = info.min_quantity

        # 确保不大于 max_quantity
        if rounded > info.max_quantity:
            rounded = info.max_quantity

        return rounded

    def round_price(self, symbol: str, price: float) -> float:
        """
        标准化价格（符合 tick_size）

        Args:
            symbol: 交易对
            price: 原始价格

        Returns:
            标准化后的价格
        """
        info = self.fetch_symbol_info(symbol)

        # 向下取整到 tick_size
        rounded = int(price / info.tick_size) * info.tick_size

        # 确保在 [min_price, max_price] 范围内
        if rounded < info.min_price:
            rounded = info.min_price
        if rounded > info.max_price:
            rounded = info.max_price

        return rounded

    def calculate_min_quantity_for_capital(self, symbol: str, capital: float,
                                          leverage: int = 20) -> Tuple[float, float, bool]:
        """
        v5.0 核心：根据资金计算最小可开仓数量

        问题：
        - 200 USDT 资金很小
        - BTC 价格 50000 USDT
        - MIN_NOTIONAL 通常是 5-10 USDT

        策略：
        1. 计算最大可用名义价值 = capital × leverage
        2. 计算最小数量满足 MIN_NOTIONAL
        3. 如果资金不足，降低杠杆或无法交易

        Args:
            symbol: 交易对
            capital: 可用资金（USDT）
            leverage: 杠杆倍数

        Returns:
            (数量, 杠杆, 是否可行)
        """
        info = self.fetch_symbol_info(symbol)

        # 获取当前价格
        ticker = self.exchange.fetch_ticker(symbol)
        current_price = ticker['last']

        # P0-3 修复：删除自动杠杆提升逻辑，添加硬杠杆上限
        MAX_ALLOWED_LEVERAGE = 5  # 硬杠杆上限，可从配置读取

        # 如果请求的杠杆超过上限，降低到上限
        if leverage > MAX_ALLOWED_LEVERAGE:
            logger.warning(f"⚠️ 请求杠杆 {leverage}x 超过安全上限 {MAX_ALLOWED_LEVERAGE}x，已自动降低")
            leverage = MAX_ALLOWED_LEVERAGE

        # 计算最大可用名义价值
        max_notional = capital * leverage

        # 检查：最大名义价值是否满足 MIN_NOTIONAL
        if max_notional < info.min_notional:
            # P0-3: 不再自动提高杠杆，直接拒绝交易
            logger.error(
                f"❌ 资金不足！${capital:.2f} 使用 {leverage}x 杠杆无法满足 MIN_NOTIONAL ${info.min_notional:.2f}"
            )
            logger.error(
                f"💡 建议：1) 增加资金至 ${info.min_notional / leverage:.2f}+"
                f" 2) 选择最小名义价值更低的交易对"
            )
            return 0, 0, False

        # 计算数量（向下取整到 step_size）
        quantity = max_notional / current_price
        quantity = self.round_quantity(symbol, quantity)

        # 验证名义价值
        notional_value = quantity * current_price
        if notional_value < info.min_notional:
            logger.error(f"❌ 计算失败：名义价值 ${notional_value:.2f} < MIN_NOTIONAL ${info.min_notional:.2f}")
            return 0, 0, False

        logger.info(f"✅ {symbol} 最小开仓计算:")
        logger.info(f"  资金: ${capital:.2f}")
        logger.info(f"  杠杆: {leverage}x")
        logger.info(f"  数量: {quantity:.6f} {info.base_asset}")
        logger.info(f"  名义价值: ${notional_value:.2f}")
        logger.info(f"  MIN_NOTIONAL: ${info.min_notional:.2f} ✅")

        return quantity, leverage, True

    def suggest_optimal_leverage(self, symbol: str, capital: float,
                                 position_ratio: float = 0.5) -> int:
        """
        v5.0: 建议最优杠杆（针对 200U 超小资金）

        策略：
        - 200U 资金，用 50%（100U）开仓
        - 针对不同币种自动调整杠杆
        - 确保满足 MIN_NOTIONAL

        Args:
            symbol: 交易对
            capital: 总资金
            position_ratio: 开仓比例（默认 50%）

        Returns:
            建议杠杆倍数
        """
        position_capital = capital * position_ratio
        info = self.fetch_symbol_info(symbol)

        # 从低杠杆开始尝试
        for leverage in range(5, info.max_leverage + 1, 5):
            quantity, _, feasible = self.calculate_min_quantity_for_capital(
                symbol, position_capital, leverage
            )
            if feasible:
                logger.info(f"✅ {symbol} 建议杠杆: {leverage}x（使用 {position_ratio*100:.0f}% 资金）")
                return leverage

        # 如果都不行，返回最大杠杆
        logger.warning(f"⚠️ {symbol} 即使 {info.max_leverage}x 杠杆也勉强，建议选择更低价格的币种")
        return info.max_leverage

    def validate_order(self, symbol: str, quantity: float, price: float) -> Tuple[bool, str]:
        """
        验证订单是否符合 exchange 规则

        Args:
            symbol: 交易对
            quantity: 数量
            price: 价格

        Returns:
            (是否有效, 错误信息)
        """
        info = self.fetch_symbol_info(symbol)

        # 检查数量
        if quantity < info.min_quantity:
            return False, f"数量 {quantity} < 最小数量 {info.min_quantity}"
        if quantity > info.max_quantity:
            return False, f"数量 {quantity} > 最大数量 {info.max_quantity}"

        # 检查价格
        if price < info.min_price:
            return False, f"价格 {price} < 最小价格 {info.min_price}"
        if price > info.max_price:
            return False, f"价格 {price} > 最大价格 {info.max_price}"

        # 检查名义价值
        notional = quantity * price
        if notional < info.min_notional:
            return False, f"名义价值 ${notional:.2f} < MIN_NOTIONAL ${info.min_notional:.2f}"
        if notional > info.max_notional:
            return False, f"名义价值 ${notional:.2f} > 最大名义价值 ${info.max_notional:.2f}"

        return True, "OK"

    def close(self):
        """关闭连接"""
        pass

    async def health_check(self) -> Dict[str, bool]:
        """
        P1-17: 检查交易所服务健康状态

        检查项：
        1. REST API 可用性
        2. 交易权限
        3. 订单簿流动性

        Returns:
            健康检查结果字典
        """
        results = {
            'rest_api': False,
            'websocket': False,  # CCXT 不直接支持 WebSocket，此处占位
            'order_book': False,
            'trading_allowed': False
        }

        try:
            # 1. 测试 REST API
            try:
                self.exchange.fetch_ticker('BTC/USDT')
                results['rest_api'] = True
                logger.debug("✅ REST API 健康检查通过")
            except Exception as e:
                logger.error(f"❌ REST API 健康检查失败: {e}")

            # 2. 测试交易权限
            try:
                self.exchange.fetch_balance()
                results['trading_allowed'] = True
                logger.debug("✅ 交易权限检查通过")
            except Exception as e:
                logger.error(f"❌ 交易权限检查失败: {e}")

            # 3. 测试订单簿
            try:
                ob = self.exchange.fetch_order_book('BTC/USDT', limit=5)
                has_liquidity = len(ob['bids']) > 0 and len(ob['asks']) > 0
                results['order_book'] = has_liquidity
                if has_liquidity:
                    logger.debug("✅ 订单簿流动性检查通过")
                else:
                    logger.warning("⚠️ 订单簿流动性不足")
            except Exception as e:
                logger.error(f"❌ 订单簿检查失败: {e}")

            # WebSocket 标记为不支持（CCXT 使用 REST API）
            results['websocket'] = False

        except Exception as e:
            logger.error(f"❌ 交易所健康检查失败: {e}")

        return results

    def is_healthy(self) -> bool:
        """
        快速检查交易所是否健康

        Returns:
            True: 健康且允许交易
            False: 不健康或无法交易
        """
        # 关键检查：REST API 和交易权限必须正常
        try:
            # 快速检查：获取服务器时间
            if hasattr(self.exchange, 'fetch_time'):
                self.exchange.fetch_time()
            else:
                # fallback: 获取 ticker
                self.exchange.fetch_ticker('BTC/USDT')

            # 检查交易权限
            self.exchange.fetch_balance()

            return True
        except Exception as e:
            logger.warning(f"⚠️ 交易所健康检查失败: {e}")
            return False


if __name__ == '__main__':
    """测试：200 USDT 能否开 BTC/USDT 仓位"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # 创建 exchangeInfo 管理器
    info_manager = BinanceExchangeInfo(testnet=True)

    # 测试 200 USDT
    capital = 200  # USDT

    print(f"\n{'='*60}")
    print(f"v5.0 狙击手模式 - 200 USDT 最小开仓测试")
    print(f"{'='*60}\n")

    # 测试 BTC/USDT
    print(f"【BTC/USDT】")
    quantity, leverage, feasible = info_manager.calculate_min_quantity_for_capital(
        'BTC/USDT', capital, leverage=20
    )

    if feasible:
        print(f"✅ 可行！")
        print(f"  杠杆: {leverage}x")
        print(f"  数量: {quantity:.6f} BTC")
        print(f"  名义价值: ${quantity * 50000:.2f} USDT")  # 假设 BTC 50000
    else:
        print(f"❌ 不可行！资金不足")

        # 尝试建议杠杆
        suggested = info_manager.suggest_optimal_leverage('BTC/USDT', capital)
        print(f"💡 建议杠杆: {suggested}x")

    # 测试 ETH/USDT（更便宜）
    print(f"\n【ETH/USDT】")
    quantity, leverage, feasible = info_manager.calculate_min_quantity_for_capital(
        'ETH/USDT', capital, leverage=20
    )

    if feasible:
        print(f"✅ 可行！")
        print(f"  杠杆: {leverage}x")
        print(f"  数量: {quantity:.6f} ETH")
        print(f"  名义价值: ${quantity * 3000:.2f} USDT")  # 假设 ETH 3000
    else:
        print(f"❌ 不可行！资金不足")

    # 验证订单
    print(f"\n{'='*60}")
    print(f"订单验证测试")
    print(f"{'='*60}\n")

    valid, reason = info_manager.validate_order('BTC/USDT', 0.001, 50000)
    print(f"BTC/USDT 0.001 BTC @ $50000: {'✅' if valid else '❌'} {reason}")
