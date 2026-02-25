"""
AI 决策引擎 - 使用 Claude API 进行交易决策
"""
import os
import json
import logging
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


@dataclass
class TradingDecision:
    """交易决策"""
    action: str  # 'buy', 'sell', 'hold'
    confidence: float  # 0.0 - 1.0
    reasoning: str
    suggested_amount: Optional[float] = None
    stop_loss_pct: Optional[float] = None
    take_profit_pct: Optional[float] = None
    risk_level: str = 'medium'  # 'low', 'medium', 'high'
    indicators: Dict[str, Any] = None


class ClaudeDecisionEngine:
    """Claude AI 决策引擎"""

    def __init__(self, api_key: Optional[str] = None):
        """
        初始化决策引擎

        Args:
            api_key: Anthropic API key（可选，默认从环境变量读取）
        """
        self.api_key = api_key or os.getenv('ANTHROPIC_API_KEY')
        self.client = None

        if self.api_key:
            try:
                import anthropic
                self.client = anthropic.Anthropic(api_key=self.api_key)
                logger.info("Claude AI 决策引擎已初始化")
            except ImportError:
                logger.warning("anthropic 库未安装，AI 功能将禁用")
                logger.warning("安装: pip install anthropic")
        else:
            logger.warning("未配置 ANTHROPIC_API_KEY，AI 功能将禁用")

    def _build_analysis_prompt(self, symbol: str, price: float,
                               price_history: List[float],
                               market_data: Optional[Dict] = None) -> str:
        """构建分析提示词"""
        # 计算基本统计
        price_change_1h = 0
        price_change_24h = 0

        if len(price_history) >= 2:
            price_change_1h = ((price - price_history[-2]) / price_history[-2]) * 100

        if len(price_history) >= 24:
            price_change_24h = ((price - price_history[-24]) / price_history[-24]) * 100

        prompt = f"""You are an expert cryptocurrency trading analyst. Analyze the following market data and provide a trading recommendation.

## Market Data
- **Symbol**: {symbol}
- **Current Price**: ${price:,.2f}
- **1H Change**: {price_change_1h:+.2f}%
- **24H Change**: {price_change_24h:+.2f}%
- **Recent Prices**: {price_history[-10:] if len(price_history) >= 10 else price_history}

## Additional Market Context
{json.dumps(market_data, indent=2) if market_data else 'No additional data available'}

## Your Task
Based on this data, provide a trading recommendation in the following JSON format:

```json
{{
    "action": "buy" | "sell" | "hold",
    "confidence": 0.0-1.0,
    "reasoning": "Brief explanation of your recommendation",
    "suggested_amount_usd": <amount in USD or null>,
    "stop_loss_pct": <negative percentage, e.g., -5>,
    "take_profit_pct": <positive percentage, e.g., 15>,
    "risk_level": "low" | "medium" | "high",
    "key_factors": ["factor1", "factor2", ...]
}}
```

## Important Guidelines
1. Be conservative - when in doubt, recommend "hold"
2. Consider risk management - always suggest stop-loss
3. Base decisions on data, not speculation
4. Factor in recent price movements and volatility
5. Provide clear, concise reasoning

Respond ONLY with the JSON, no additional text.
"""
        return prompt

    def _calculate_technical_indicators(self, price_history: List[float],
                                       market_data: Optional[Dict] = None) -> Dict:
        """计算技术指标用于降级决策"""
        indicators = {
            'trend': 'neutral',
            'volume_ratio': 1.0,
            'price_momentum': 0.0,
            'volatility': None,
            'rsi': None
        }

        if len(price_history) >= 30:
            # 检测趋势
            indicators['trend'] = TechnicalIndicators.detect_trend(price_history)
            indicators['rsi'] = TechnicalIndicators.calculate_rsi(price_history)
            indicators['volatility'] = TechnicalIndicators.calculate_volatility(price_history)

            # 价格动量
            if len(price_history) >= 5:
                momentum = (price_history[-1] - price_history[-5]) / price_history[-5] * 100
                indicators['price_momentum'] = momentum

        # 从市场数据中提取成交量比率
        if market_data:
            indicators['volume_ratio'] = market_data.get('volume_ratio', 1.0)
            # 如果有成交量数据，计算成交量比率
            if 'volume' in market_data and 'avg_volume' in market_data:
                if market_data['avg_volume'] > 0:
                    indicators['volume_ratio'] = market_data['volume'] / market_data['avg_volume']

        return indicators

    def _conservative_fallback(self, symbol: str, price: float,
                               price_history: List[float],
                               market_data: Optional[Dict] = None) -> TradingDecision:
        """
        AI 失败时的保守技术分析降级方案

        使用保守的技术分析规则，只在趋势明确且放量时才给出交易建议
        """
        logger.warning(f"AI 不可用，使用保守技术分析降级方案: {symbol}")

        indicators = self._calculate_technical_indicators(price_history, market_data)
        trend = indicators['trend']
        volume_ratio = indicators['volume_ratio']
        rsi = indicators.get('rsi')
        volatility = indicators.get('volatility')
        price_momentum = indicators['price_momentum']

        # 保守决策逻辑
        # 买入条件：上升趋势 + 放量 + RSI未超买
        if trend == 'bullish' and volume_ratio > 2.0:
            # RSI 额外检查
            if rsi is None or rsi < 70:
                reasoning_parts = [
                    'AI 不可用，基于保守技术分析',
                    f'趋势: {trend}',
                    f'成交量比率: {volume_ratio:.2f}x (放量)',
                ]
                if rsi is not None:
                    reasoning_parts.append(f'RSI: {rsi:.1f} (未超买)')
                if volatility is not None:
                    reasoning_parts.append(f'波动率: {volatility:.2f}')

                return TradingDecision(
                    action='buy',
                    confidence=0.5,  # 中等置信度
                    reasoning=', '.join(reasoning_parts),
                    risk_level='medium',
                    stop_loss_pct=-5.0,
                    take_profit_pct=15.0,
                    indicators=indicators
                )

        # 卖出条件：下降趋势 + 放量
        elif trend == 'bearish' and volume_ratio > 2.0:
            reasoning_parts = [
                'AI 不可用，基于保守技术分析',
                f'趋势: {trend}',
                f'成交量比率: {volume_ratio:.2f}x (放量)',
            ]
            if rsi is not None:
                reasoning_parts.append(f'RSI: {rsi:.1f}')
            if price_momentum != 0:
                reasoning_parts.append(f'价格动量: {price_momentum:+.2f}%')

            return TradingDecision(
                action='sell',
                confidence=0.5,
                reasoning=', '.join(reasoning_parts),
                risk_level='medium',
                stop_loss_pct=-5.0,
                take_profit_pct=15.0,
                indicators=indicators
            )

        # 默认持有：市场条件不明确
        else:
            reasoning_parts = [
                'AI 不可用，市场条件不明确，保守持有',
            ]
            if trend != 'neutral':
                reasoning_parts.append(f'趋势: {trend}')
            if volume_ratio <= 2.0:
                reasoning_parts.append(f'成交量比率: {volume_ratio:.2f}x (未放量)')
            else:
                reasoning_parts.append(f'成交量比率: {volume_ratio:.2f}x')
            if rsi is not None:
                reasoning_parts.append(f'RSI: {rsi:.1f}')

            return TradingDecision(
                action='hold',
                confidence=0.7,  # 高置信度持币
                reasoning=', '.join(reasoning_parts),
                risk_level='low',
                indicators=indicators
            )

    def analyze_market(self, symbol: str, price: float,
                      price_history: List[float],
                      market_data: Optional[Dict] = None) -> TradingDecision:
        """
        分析市场并给出交易建议

        Args:
            symbol: 交易对
            price: 当前价格
            price_history: 价格历史
            market_data: 额外市场数据

        Returns:
            交易决策
        """
        if not self.client:
            logger.warning("Claude 客户端未初始化，使用保守技术分析降级方案")
            return self._conservative_fallback(symbol, price, price_history, market_data)

        try:
            prompt = self._build_analysis_prompt(symbol, price, price_history, market_data)

            logger.info(f"请求 Claude 分析: {symbol}")

            response = self.client.messages.create(
                model="claude-sonnet-4-5-20250514",
                max_tokens=1000,
                messages=[{
                    "role": "user",
                    "content": prompt
                }]
            )

            # 解析响应
            content = response.content[0].text

            # 提取 JSON
            if '```json' in content:
                json_str = content.split('```json')[1].split('```')[0].strip()
            elif '```' in content:
                json_str = content.split('```')[1].split('```')[0].strip()
            else:
                json_str = content.strip()

            result = json.loads(json_str)

            decision = TradingDecision(
                action=result.get('action', 'hold'),
                confidence=result.get('confidence', 0.5),
                reasoning=result.get('reasoning', ''),
                suggested_amount=result.get('suggested_amount_usd'),
                stop_loss_pct=result.get('stop_loss_pct', -5),
                take_profit_pct=result.get('take_profit_pct', 15),
                risk_level=result.get('risk_level', 'medium'),
                indicators={'key_factors': result.get('key_factors', [])}
            )

            logger.info(f"Claude 决策: {decision.action} (置信度: {decision.confidence:.2f})")
            logger.info(f"原因: {decision.reasoning}")

            return decision

        except json.JSONDecodeError as e:
            logger.error(f"解析 Claude 响应失败: {e}")
            logger.error(f"原始响应内容: {content[:500] if 'content' in locals() else 'N/A'}")
            return self._conservative_fallback(symbol, price, price_history, market_data)
        except Exception as e:
            logger.error(f"Claude API 调用失败: {e}")
            return self._conservative_fallback(symbol, price, price_history, market_data)

    def should_execute_trade(self, decision: TradingDecision,
                            min_confidence: float = 0.7) -> bool:
        """
        判断是否应该执行交易

        Args:
            decision: 交易决策
            min_confidence: 最低置信度

        Returns:
            是否执行
        """
        if decision.action == 'hold':
            return False

        if decision.confidence < min_confidence:
            logger.info(f"置信度过低 ({decision.confidence:.2f} < {min_confidence})，跳过")
            return False

        if decision.risk_level == 'high':
            logger.warning("高风险决策，建议人工确认")

        return True

    def get_sentiment(self, symbol: str, news: Optional[List[str]] = None) -> Dict:
        """
        获取市场情绪（简化版）

        Args:
            symbol: 交易对
            news: 相关新闻（可选）

        Returns:
            情绪分析结果
        """
        if not self.client:
            return {'sentiment': 'neutral', 'score': 0.5}

        try:
            prompt = f"""Analyze the market sentiment for {symbol}.

Recent news (if available):
{chr(10).join(news) if news else 'No news available'}

Provide a sentiment analysis in this JSON format:
{{
    "sentiment": "bullish" | "bearish" | "neutral",
    "score": 0.0-1.0,
    "key_drivers": ["driver1", "driver2", ...]
}}

Respond ONLY with JSON.
"""

            response = self.client.messages.create(
                model="claude-sonnet-4-5-20250514",
                max_tokens=500,
                messages=[{"role": "user", "content": prompt}]
            )

            content = response.content[0].text

            if '```json' in content:
                json_str = content.split('```json')[1].split('```')[0].strip()
            else:
                json_str = content.strip()

            result = json.loads(json_str)
            return result

        except Exception as e:
            logger.error(f"情绪分析失败: {e}")
            return {'sentiment': 'neutral', 'score': 0.5}


# 简化的技术指标计算（不依赖外部库）
class TechnicalIndicators:
    """技术指标计算器"""

    @staticmethod
    def calculate_sma(prices: List[float], period: int) -> Optional[float]:
        """计算简单移动平均"""
        if len(prices) < period:
            return None
        return sum(prices[-period:]) / period

    @staticmethod
    def calculate_ema(prices: List[float], period: int) -> Optional[float]:
        """计算指数移动平均"""
        if len(prices) < period:
            return None

        multiplier = 2 / (period + 1)
        ema = sum(prices[:period]) / period  # 初始 SMA

        for price in prices[period:]:
            ema = (price - ema) * multiplier + ema

        return ema

    @staticmethod
    def calculate_rsi(prices: List[float], period: int = 14) -> Optional[float]:
        """计算 RSI"""
        if len(prices) < period + 1:
            return None

        gains = []
        losses = []

        for i in range(1, len(prices)):
            change = prices[i] - prices[i - 1]
            if change > 0:
                gains.append(change)
                losses.append(0)
            else:
                gains.append(0)
                losses.append(abs(change))

        if len(gains) < period:
            return None

        avg_gain = sum(gains[-period:]) / period
        avg_loss = sum(losses[-period:]) / period

        if avg_loss == 0:
            return 100

        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))

        return rsi

    @staticmethod
    def detect_trend(prices: List[float], short_period: int = 10,
                     long_period: int = 30) -> str:
        """检测趋势"""
        if len(prices) < long_period:
            return 'unknown'

        short_ma = sum(prices[-short_period:]) / short_period
        long_ma = sum(prices[-long_period:]) / long_period

        if short_ma > long_ma * 1.02:
            return 'bullish'
        elif short_ma < long_ma * 0.98:
            return 'bearish'
        else:
            return 'neutral'

    @staticmethod
    def calculate_volatility(prices: List[float], period: int = 20) -> Optional[float]:
        """计算波动率（标准差）"""
        if len(prices) < period:
            return None

        recent = prices[-period:]
        mean = sum(recent) / period
        variance = sum((p - mean) ** 2 for p in recent) / period
        return variance ** 0.5
