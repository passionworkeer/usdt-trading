"""
宏观大局观生成器（Macro Oracle）

每小时生成宏观大局观，包括市场情绪、主叙事、交易禁令等
"""
import json
import logging
from typing import Dict, Optional
from datetime import datetime, timedelta
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class MacroState:
    """宏观状态"""
    global_sentiment: str  # 'panic' | 'neutral' | 'euphoric'
    dominant_narrative: str
    trading_bans: list  # ['LONG'] | ['SHORT'] | []
    recommended_stance: str  # 'defensive' | 'neutral' | 'aggressive'
    reasoning: str
    timestamp: datetime


class MacroOracle:
    """宏观大局观生成器"""

    def __init__(self, decision_engine):
        """
        初始化宏观大局观生成器

        Args:
            decision_engine: ClaudeDecisionEngine 实例
        """
        self.engine = decision_engine
        self.last_macro_state: Optional[MacroState] = None
        self.last_update_time: Optional[datetime] = None
        self.update_interval = timedelta(hours=1)  # 每小时更新

    async def generate_macro_state(
        self,
        intelligence: Dict,
        force_update: bool = False
    ) -> MacroState:
        """
        生成宏观大局观（每小时调用一次）

        Args:
            intelligence: {
                'tweets': [...],
                'news': [...]
            }
            force_update: 强制更新（忽略时间间隔）

        Returns:
            MacroState 对象
        """
        # 检查是否需要更新
        if not force_update and self._should_skip_update():
            logger.info("距离上次更新不足 1 小时，跳过宏观大局观更新")
            return self.last_macro_state

        # 检查 AI 客户端是否可用
        if not self.engine.client:
            logger.warning("Claude 客户端未初始化，返回默认宏观状态")
            return self._get_default_state()

        try:
            # 构建 prompt
            prompt = self._build_macro_prompt(intelligence)

            # 调用 Claude
            logger.info("请求 Claude 生成宏观大局观...")
            response = self.engine.client.messages.create(
                model="claude-sonnet-4-5-20250514",
                max_tokens=1000,
                messages=[{"role": "user", "content": prompt}]
            )

            # 解析响应
            content = response.content[0].text
            result = self._parse_response(content)

            # P1-7: 验证 trading_bans 类型，只接受 'LONG' 和 'SHORT'
            valid_bans = {'LONG', 'SHORT'}
            trading_bans = result.get('trading_bans', [])
            trading_bans = [b.upper() for b in trading_bans if b.upper() in valid_bans]

            # 创建 MacroState
            macro_state = MacroState(
                global_sentiment=result.get('global_sentiment', 'neutral'),
                dominant_narrative=result.get('dominant_narrative', ''),
                trading_bans=trading_bans,
                recommended_stance=result.get('recommended_stance', 'neutral'),
                reasoning=result.get('reasoning', ''),
                timestamp=datetime.now()
            )

            # 缓存
            self.last_macro_state = macro_state
            self.last_update_time = datetime.now()

            logger.info(
                f"宏观大局观更新: {macro_state.global_sentiment} | "
                f"叙事: {macro_state.dominant_narrative} | "
                f"禁令: {macro_state.trading_bans}"
            )

            return macro_state

        except json.JSONDecodeError as e:
            logger.error(f"解析 Claude 响应失败: {e}")
            return self._get_default_state()
        except Exception as e:
            logger.error(f"生成宏观大局观失败: {e}")
            return self._get_default_state()

    def _should_skip_update(self) -> bool:
        """检查是否应该跳过更新"""
        if self.last_update_time is None:
            return False

        elapsed = datetime.now() - self.last_update_time
        return elapsed < self.update_interval

    def _build_macro_prompt(self, intelligence: Dict) -> str:
        """构建宏观分析 prompt"""

        tweets = intelligence.get('tweets', [])
        news = intelligence.get('news', [])

        # 提取推文样本
        tweet_sample = "\n".join([
            f"- {t['text'][:100]}... ({t.get('likes', 0)} likes)"
            for t in tweets[:10]
        ]) if tweets else "无数据"

        # 提取新闻标题
        news_sample = "\n".join([
            f"- {n['title']} ({n['source']})"
            for n in news[:10]
        ]) if news else "无数据"

        prompt = f"""你是一位资深的加密货币宏观分析师。请分析当前的市场情绪和宏观叙事。

## Twitter 情绪（过去 1 小时）
{tweet_sample}

## 宏观新闻（过去 24 小时）
{news_sample}

## 你的任务
基于以上信息，生成一个宏观大局观报告，格式如下：

```json
{{
    "global_sentiment": "panic" | "neutral" | "euphoric",
    "dominant_narrative": "一句话描述当前市场主叙事（10字以内）",
    "trading_bans": ["LONG"] 或 ["SHORT"] 或 [],
    "recommended_stance": "defensive" | "neutral" | "aggressive",
    "reasoning": "50 字以内的核心逻辑"
}}
```

## 判断标准
- **panic**: 大量负面新闻（监管、黑客、交易所倒闭），推特恐慌情绪蔓延
  → trading_bans: ["LONG"], recommended_stance: "defensive"
- **euphoric**: FOMO 情绪严重，过度贪婪，价格短期暴涨
  → trading_bans: [], recommended_stance: "defensive"  (不追高)
- **neutral**: 情绪平稳，没有极端事件
  → trading_bans: [], recommended_stance: "neutral"

## 重要提示
1. 只有在极端情况下才设置交易禁令
2. reasoning 必须简洁（50 字以内）
3. dominant_narrative 必须简洁（10 字以内）

只返回 JSON，不要其他文本。
"""
        return prompt

    def _parse_response(self, content: str) -> Dict:
        """解析 Claude 响应"""
        # 提取 JSON
        if '```json' in content:
            json_str = content.split('```json')[1].split('```')[0].strip()
        elif '```' in content:
            json_str = content.split('```')[1].split('```')[0].strip()
        else:
            json_str = content.strip()

        result = json.loads(json_str)

        # 验证字段
        valid_sentiments = ['panic', 'neutral', 'euphoric']
        valid_stances = ['defensive', 'neutral', 'aggressive']

        if result.get('global_sentiment') not in valid_sentiments:
            result['global_sentiment'] = 'neutral'

        if result.get('recommended_stance') not in valid_stances:
            result['recommended_stance'] = 'neutral'

        if not isinstance(result.get('trading_bans'), list):
            result['trading_bans'] = []

        return result

    def _get_default_state(self) -> MacroState:
        """获取默认宏观状态"""
        return MacroState(
            global_sentiment='neutral',
            dominant_narrative='无明确叙事',
            trading_bans=[],
            recommended_stance='neutral',
            reasoning='暂无数据，默认中性立场',
            timestamp=datetime.now()
        )

    def get_cached_state(self) -> Optional[MacroState]:
        """获取缓存的宏观状态"""
        return self.last_macro_state

    def is_trading_allowed(self, direction: str) -> bool:
        """
        检查某个方向的交易是否被允许

        Args:
            direction: 'LONG' | 'SHORT'

        Returns:
            是否允许
        """
        if not self.last_macro_state:
            return True  # 没有宏观状态，默认允许

        return direction.upper() not in self.last_macro_state.trading_bans
