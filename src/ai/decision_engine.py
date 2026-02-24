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
            logger.warning("Claude 客户端未初始化，返回保守决策")
            return TradingDecision(
                action='hold',
                confidence=0.5,
                reasoning='AI analysis unavailable - defaulting to hold',
                risk_level='medium'
            )

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
            return TradingDecision(
                action='hold',
                confidence=0.3,
                reasoning='Failed to parse AI response',
                risk_level='high'
            )
        except Exception as e:
            logger.error(f"Claude API 调用失败: {e}")
            return TradingDecision(
                action='hold',
                confidence=0.3,
                reasoning=f'AI analysis failed: {str(e)}',
                risk_level='high'
            )

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
