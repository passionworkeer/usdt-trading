"""
资金费率监控 + 逐仓保证金管理 v4.1

核心功能：
1. ✅ 实时监控资金费率（每 8 小时结算）
2. ✅ 资金费率作为反向信号（极度正费率 → 做空）
3. ✅ 逐仓模式（Isolated Margin）
4. ✅ 动态保证金追加/扣减
"""
import logging
import asyncio
import aiohttp
import numpy as np
from typing import Dict, Optional, List
from datetime import datetime, timedelta
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class FundingRate:
    """资金费率数据"""
    symbol: str
    funding_rate: float  # 当前费率（小数）
    funding_time: datetime  # 下次结算时间
    mark_price: float  # 标记价格
    index_price: float  # 指数价格


class FundingRateMonitor:
    """
    资金费率监控器

    功能：
    1. 获取实时资金费率
    2. 计算资金费率成本（复利收割）
    3. 资金费率作为反向信号
    """

    def __init__(self):
        """初始化资金费率监控器"""
        self.funding_rates: Dict[str, FundingRate] = {}
        self.session: Optional[aiohttp.ClientSession] = None

        # 历史资金费率（用于计算趋势）
        self.funding_rate_history: Dict[str, List[float]] = {}

    async def init_session(self):
        """初始化 HTTP session"""
        if not self.session:
            self.session = aiohttp.ClientSession()

    async def fetch_funding_rate(self, symbol: str) -> Optional[FundingRate]:
        """
        获取资金费率（异步）

        Args:
            symbol: 交易对

        Returns:
            资金费率数据
        """
        await self.init_session()

        url = "https://fapi.binance.com/fapi/v1/premiumIndex"
        params = {'symbol': symbol.replace('/', '')}

        try:
            async with self.session.get(url, params=params) as response:
                data = await response.json()

                if response.status == 200:
                    funding_rate = FundingRate(
                        symbol=symbol,
                        funding_rate=float(data['lastFundingRate']),
                        funding_time=datetime.fromtimestamp(data['nextFundingTime'] / 1000),
                        mark_price=float(data['markPrice']),
                        index_price=float(data['indexPrice']),
                    )

                    self.funding_rates[symbol] = funding_rate

                    # 更新历史
                    if symbol not in self.funding_rate_history:
                        self.funding_rate_history[symbol] = []

                    self.funding_rate_history[symbol].append(funding_rate.funding_rate)

                    # 保留最近 30 个费率（约 10 天）
                    if len(self.funding_rate_history[symbol]) > 30:
                        self.funding_rate_history[symbol] = self.funding_rate_history[symbol][-30:]

                    return funding_rate
                else:
                    logger.error(f"获取资金费率失败: {data}")
                    return None

        except Exception as e:
            logger.error(f"获取资金费率异常: {e}")
            return None

    def calculate_funding_cost(self, symbol: str, position_value: float,
                              holding_hours: float) -> float:
        """
        计算资金费率成本（复利收割）

        公式：
        Funding Cost = Position Value × Funding Rate × (Holding Hours / 8)

        Args:
            symbol: 交易对
            position_value: 持仓价值（USDT）
            holding_hours: 持仓时间（小时）

        Returns:
            资金费率成本（USDT）
        """
        if symbol not in self.funding_rates:
            return 0

        funding_rate = self.funding_rates[symbol].funding_rate

        # 每 8 小时结算一次
        settlements = holding_hours / 8

        # 资金费率成本
        cost = position_value * funding_rate * settlements

        return cost

    def get_funding_rate_signal(self, symbol: str) -> Dict:
        """
        资金费率作为反向信号

        逻辑：
        - 极度正费率（> 0.1%）→ 多头极度拥挤 → 做空信号
        - 极度负费率（< -0.1%）→ 空头极度拥挤 → 做多信号

        Args:
            symbol: 交易对

        Returns:
            信号字典
        """
        if symbol not in self.funding_rates:
            return {'signal': 0, 'reason': '无数据'}

        current_rate = self.funding_rates[symbol].funding_rate

        # 计算历史均值
        if symbol in self.funding_rate_history and len(self.funding_rate_history[symbol]) > 0:
            avg_rate = np.mean(self.funding_rate_history[symbol])
        else:
            avg_rate = 0

        # 信号逻辑
        signal = 0
        reason = ""

        if current_rate > 0.001:  # 0.1%
            signal = -1  # 做空
            reason = f"极度正费率 {current_rate:.4%}（均值 {avg_rate:.4%}）→ 多头拥挤 → 做空"
        elif current_rate < -0.001:  # -0.1%
            signal = 1  # 做多
            reason = f"极度负费率 {current_rate:.4%}（均值 {avg_rate:.4%}）→ 空头拥挤 → 做多"
        else:
            signal = 0
            reason = f"正常费率 {current_rate:.4%}"

        return {
            'signal': signal,
            'strength': abs(current_rate) * 10,  # 费率越大，信号越强
            'reason': reason,
            'funding_rate': current_rate,
            'avg_rate': avg_rate,
        }

    async def close(self):
        """关闭 session"""
        if self.session:
            await self.session.close()


class IsolatedMarginManager:
    """
    逐仓保证金管理器（防止全仓连坐爆仓）

    功能：
    1. 设置逐仓模式
    2. 动态追加/扣减保证金
    3. 监控单个仓位风险
    """

    def __init__(self, api_key: str, api_secret: str, testnet: bool = True):
        """
        初始化逐仓保证金管理器

        Args:
            api_key: API Key
            api_secret: API Secret
            testnet: 是否测试网
        """
        self.api_key = api_key
        self.api_secret = api_secret
        self.testnet = testnet

        # 基础 URL
        if testnet:
            self.base_url = "https://testnet.binancefuture.com/fapi/v1"
        else:
            self.base_url = "https://fapi.binance.com/fapi/v1"

        self.session: Optional[aiohttp.ClientSession] = None

    async def init_session(self):
        """初始化 session"""
        if not self.session:
            self.session = aiohttp.ClientSession(
                headers={'X-MBX-APIKEY': self.api_key}
            )

    async def set_isolated_margin(self, symbol: str) -> Dict:
        """
        设置逐仓模式（v4.1: 防止全仓连坐爆仓）

        Args:
            symbol: 交易对

        Returns:
            设置结果
        """
        await self.init_session()

        params = {
            'symbol': symbol.replace('/', ''),
            'marginType': 'ISOLATED',  # 逐仓模式
            'timestamp': int(datetime.now().timestamp() * 1000),
        }

        try:
            async with self.session.post(
                f"{self.base_url}/marginType",
                params=params
            ) as response:
                result = await response.json()

                if response.status == 200:
                    logger.info(f"✅ {symbol} 已设置为逐仓模式（Isolated Margin）")
                    return result
                else:
                    # 可能已经是逐仓模式
                    logger.warning(f"设置逐仓失败（可能已是逐仓）: {result}")
                    return result

        except Exception as e:
            logger.error(f"设置逐仓异常: {e}")
            raise

    async def adjust_margin(self, symbol: str, amount: float, position_side: str = 'LONG') -> Dict:
        """
        调整保证金（动态追加/扣减）

        Args:
            symbol: 交易对
            amount: 保证金数量（正数=追加，负数=扣减）
            position_side: 'LONG' 或 'SHORT'

        Returns:
            调整结果
        """
        await self.init_session()

        params = {
            'symbol': symbol.replace('/', ''),
            'amount': abs(amount),
            'type': 1 if amount > 0 else 2,  # 1=追加, 2=扣减
            'positionSide': position_side,
            'timestamp': int(datetime.now().timestamp() * 1000),
        }

        try:
            async with self.session.post(
                f"{self.base_url}/positionMargin",
                params=params
            ) as response:
                result = await response.json()

                if response.status == 200:
                    action = "追加" if amount > 0 else "扣减"
                    logger.info(f"✅ {symbol} {position_side} {action}保证金 {abs(amount):.2f} USDT")
                    return result
                else:
                    logger.error(f"调整保证金失败: {result}")
                    raise Exception(f"调整保证金失败: {result}")

        except Exception as e:
            logger.error(f"调整保证金异常: {e}")
            raise

    async def get_position_margin_ratio(self, symbol: str, position_side: str = 'LONG') -> Optional[float]:
        """
        获取仓位保证金率

        Args:
            symbol: 交易对
            position_side: 'LONG' 或 'SHORT'

        Returns:
            保证金率（0-1，越小风险越高）
        """
        await self.init_session()

        params = {
            'symbol': symbol.replace('/', ''),
            'timestamp': int(datetime.now().timestamp() * 1000),
        }

        try:
            async with self.session.get(
                f"{self.base_url}/positionRisk",
                params=params
            ) as response:
                positions = await response.json()

                for pos in positions:
                    if pos.get('positionSide') == position_side and pos.get('symbol') == symbol.replace('/', ''):
                        # 计算保证金率
                        margin_balance = float(pos.get('marginBalance', 0))
                        maint_margin = float(pos.get('maintMargin', 0))

                        if margin_balance > 0:
                            ratio = (margin_balance - maint_margin) / margin_balance
                            return ratio

                return None

        except Exception as e:
            logger.error(f"获取保证金率异常: {e}")
            return None

    async def auto_top_up_margin(self, symbol: str, position_side: str = 'LONG',
                                min_ratio: float = 0.3, top_up_amount: float = 100):
        """
        自动追加保证金（防止爆仓）

        Args:
            symbol: 交易对
            position_side: 'LONG' 或 'SHORT'
            min_ratio: 最小保证金率阈值
            top_up_amount: 追加金额
        """
        ratio = await self.get_position_margin_ratio(symbol, position_side)

        if ratio is not None and ratio < min_ratio:
            logger.warning(f"⚠️ {symbol} {position_side} 保证金率过低: {ratio:.2%}")
            logger.warning(f"   自动追加保证金: {top_up_amount} USDT")

            await self.adjust_margin(symbol, top_up_amount, position_side)

    async def close(self):
        """关闭 session"""
        if self.session:
            await self.session.close()


if __name__ == '__main__':
    # 测试代码
    import os
    from dotenv import load_dotenv

    load_dotenv()

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    async def test_funding_rate():
        """测试资金费率监控"""
        monitor = FundingRateMonitor()

        # 获取 BTC 资金费率
        funding_rate = await monitor.fetch_funding_rate('BTC/USDT')

        if funding_rate:
            print(f"\nBTC/USDT 资金费率:")
            print(f"  当前费率: {funding_rate.funding_rate:.4%}")
            print(f"  下次结算: {funding_rate.funding_time}")
            print(f"  标记价格: ${funding_rate.mark_price:.2f}")
            print(f"  指数价格: ${funding_rate.index_price:.2f}")

            # 计算资金费率成本
            position_value = 10000  # 1 万美元仓位
            holding_hours = 24  # 持仓 24 小时
            cost = monitor.calculate_funding_cost('BTC/USDT', position_value, holding_hours)

            print(f"\n持仓 {holding_hours} 小时资金费率成本: ${cost:.2f}")

            # 获取信号
            signal = monitor.get_funding_rate_signal('BTC/USDT')
            print(f"\n资金费率信号:")
            print(f"  信号: {signal['signal']}")
            print(f"  强度: {signal['strength']:.2f}")
            print(f"  原因: {signal['reason']}")

        await monitor.close()

    # 运行测试
    asyncio.run(test_funding_rate())
