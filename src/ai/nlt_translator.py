"""
自然语言数据翻译器（Natural Language Data Translator）

将冰冷的 JSON 数据翻译成结构化的自然语言报告，供 AI 理解
"""
import logging
from typing import Dict, Optional
from datetime import datetime

from .sentiment_analyzer import SentimentAnalyzer

logger = logging.getLogger(__name__)


class NLTDataTranslator:
    """自然语言数据翻译器"""

    def __init__(self):
        """初始化翻译器"""
        self.last_report_time = None
        # VADER 情绪分析器（v7.4 升级，P2-18）
        self.sentiment_analyzer = SentimentAnalyzer()
        logger.info("NLTDataTranslator 初始化完成，已加载 VADER 情绪分析器")

    def translate_micro_snapshot(self, snapshot: Dict) -> str:
        """
        将微观数据翻译成技术面报告

        Args:
            snapshot: {
                "symbol": "BTCUSDT",
                "price": 95000,
                "funding_rate": 0.0008,
                "obi": -0.6,
                "volume_15m": 1200000,
                "avg_volume_15m": 800000,
                "ema_distance": 0.02
            }

        Returns:
            "技术面报告：当前资金费率 0.08%（处于历史极高拥挤区，多头过度贪婪）。
             盘口失衡率 -0.6，上方存在冰山卖单压制。15分钟级别刚刚放量突破 EMA50，
             成交量放大至 120 万 USDT。价格偏离 EMA50 仅 2%，处于健康击球区。"
        """
        sections = []

        # 1. 资金费率解读
        funding = snapshot.get('funding_rate', 0) * 100
        funding_desc = self._interpret_funding_rate(funding)
        sections.append(funding_desc)

        # 2. 订单簿失衡
        obi = snapshot.get('obi', 0)
        obi_desc = self._interpret_obi(obi)
        sections.append(obi_desc)

        # 3. 成交量分析
        volume = snapshot.get('volume_15m', 0)
        avg_volume = snapshot.get('avg_volume_15m', volume)
        volume_desc = self._interpret_volume(volume, avg_volume)
        if volume_desc:
            sections.append(volume_desc)

        # 4. EMA 距离
        ema_dist = snapshot.get('ema_distance', 0) * 100
        ema_desc = self._interpret_ema_distance(ema_dist)
        sections.append(ema_desc)

        # 5. 价格位置
        price = snapshot.get('price', 0)
        symbol = snapshot.get('symbol', 'UNKNOWN')
        sections.insert(0, f"当前价格 ${price:,.2f}")

        report = "技术面报告：" + "；".join(sections) + "。"
        logger.debug(f"生成技术面报告: {report[:100]}...")

        return report

    def translate_macro_state(self, macro_state: Dict) -> str:
        """
        将宏观状态翻译成自然语言

        Args:
            macro_state: {
                'global_sentiment': 'panic',
                'dominant_narrative': '监管恐慌',
                'trading_bans': ['LONG'],
                'recommended_stance': 'defensive',
                'reasoning': 'SEC 对交易所采取行动'
            }

        Returns:
            "宏观大局观：当前市场情绪恐慌，主叙事为监管恐慌。
             建议防御性立场，禁止做多。核心逻辑：SEC 对交易所采取行动。"
        """
        if not macro_state:
            return "宏观大局观：暂无数据，默认中性立场。"

        sentiment = macro_state.get('global_sentiment', 'neutral')
        narrative = macro_state.get('dominant_narrative', '无明确叙事')
        bans = macro_state.get('trading_bans', [])
        stance = macro_state.get('recommended_stance', 'neutral')
        reasoning = macro_state.get('reasoning', '')

        # 情绪描述
        sentiment_map = {
            'panic': '市场恐慌情绪蔓延',
            'euphoric': '市场过度贪婪',
            'neutral': '市场情绪平稳'
        }
        sentiment_desc = sentiment_map.get(sentiment, '市场情绪不明')

        # 禁令描述
        ban_desc = ""
        if 'LONG' in bans:
            ban_desc = "，禁止做多"
        elif 'SHORT' in bans:
            ban_desc = "，禁止做空"

        # 立场描述
        stance_map = {
            'defensive': '防御性',
            'aggressive': '激进',
            'neutral': '中性'
        }
        stance_desc = stance_map.get(stance, '中性')

        report = (
            f"宏观大局观：{sentiment_desc}，当前主叙事为「{narrative}」。"
            f"建议{stance_desc}立场{ban_desc}。"
        )

        if reasoning:
            report += f"核心逻辑：{reasoning}。"

        return report

    def translate_twitter_sentiment(self, tweets: list) -> str:
        """
        将 Twitter 情绪翻译成自然语言

        Args:
            tweets: [
                {'text': 'BTC to the moon!', 'likes': 100},
                ...
            ]

        Returns:
            "Twitter 情绪：过去 1 小时共 50 条推文，整体情绪极度贪婪。
             高赞推文样本：'BTC to the moon!' (100 likes)"
        """
        if not tweets:
            return "Twitter 情绪：暂无数据。"

        # 使用 VADER 专业情绪分析（v7.4 升级，P2-18）
        texts = [tweet['text'] for tweet in tweets]
        batch_result = self.sentiment_analyzer.analyze_batch(texts)

        # 获取中文情绪标签
        sentiment_label = self.sentiment_analyzer.get_sentiment_label(
            batch_result['avg_score']
        )

        # 根据情绪强度调整描述
        avg_score = batch_result['avg_score']
        if avg_score >= 0.5:
            sentiment_desc = f"极度贪婪（VADER 分数: {avg_score:.2f}）"
        elif avg_score >= 0.2:
            sentiment_desc = f"贪婪（VADER 分数: {avg_score:.2f}）"
        elif avg_score >= 0.05:
            sentiment_desc = f"偏多（VADER 分数: {avg_score:.2f}）"
        elif avg_score >= -0.05:
            sentiment_desc = f"中性（VADER 分数: {avg_score:.2f}）"
        elif avg_score >= -0.2:
            sentiment_desc = f"偏空（VADER 分数: {avg_score:.2f}）"
        elif avg_score >= -0.5:
            sentiment_desc = f"恐慌（VADER 分数: {avg_score:.2f}）"
        else:
            sentiment_desc = f"极度恐慌（VADER 分数: {avg_score:.2f}）"

        # 提取高赞推文样本
        top_tweets = sorted(tweets, key=lambda x: x.get('likes', 0), reverse=True)[:3]
        samples = [
            f"'{t['text'][:50]}...' ({t.get('likes', 0)} likes)"
            for t in top_tweets
        ]

        report = (
            f"Twitter 情绪：过去 1 小时共 {batch_result['count']} 条推文，"
            f"整体情绪{sentiment_desc}。"
            f"正面占比 {batch_result['positive_pct']*100:.1f}%，"
            f"负面占比 {batch_result['negative_pct']*100:.1f}%。"
            f"高赞推文样本：" + " | ".join(samples)
        )

        logger.debug(f"Twitter 情绪分析完成: {sentiment_label}, 样本数: {len(tweets)}")

        return report

    def translate_news_headlines(self, news: list) -> str:
        """
        将新闻标题翻译成自然语言

        Args:
            news: [
                {'title': 'SEC sues Binance', 'source': 'CoinDesk'},
                ...
            ]

        Returns:
            "宏观新闻（24h）：CoinDesk - SEC sues Binance；Bloomberg - ..."
        """
        if not news:
            return "宏观新闻：暂无重要新闻。"

        headlines = [
            f"{n['source']} - {n['title']}"
            for n in news[:5]  # 只取前 5 条
        ]

        report = f"宏观新闻（24h）：" + "；".join(headlines)

        return report

    # ==================== 私有方法 ====================

    def _interpret_funding_rate(self, funding_pct: float) -> str:
        """解读资金费率"""
        if funding_pct > 0.05:
            return f"资金费率 {funding_pct:.2f}%（历史极高拥挤区，多头过度贪婪）"
        elif funding_pct > 0.01:
            return f"资金费率 {funding_pct:.2f}%（温和多头情绪）"
        elif funding_pct > 0:
            return f"资金费率 {funding_pct:.2f}%（中性偏多）"
        elif funding_pct > -0.01:
            return f"资金费率 {funding_pct:.2f}%（中性偏空）"
        elif funding_pct > -0.05:
            return f"资金费率 {funding_pct:.2f}%（温和空头情绪）"
        else:
            return f"资金费率 {funding_pct:.2f}%（极度恐慌，空头拥挤）"

    def _interpret_obi(self, obi: float) -> str:
        """解读订单簿失衡率"""
        if obi > 0.7:
            return f"盘口失衡率 +{obi:.1f}，巨量冰山买单支撑"
        elif obi > 0.5:
            return f"盘口失衡率 +{obi:.1f}，强劲买盘支撑"
        elif obi > 0.3:
            return f"盘口失衡率 +{obi:.1f}，买盘略占优势"
        elif obi > -0.3:
            return f"盘口失衡率 {obi:.1f}，买卖力量均衡"
        elif obi > -0.5:
            return f"盘口失衡率 {obi:.1f}，卖盘略占优势"
        elif obi > -0.7:
            return f"盘口失衡率 {obi:.1f}，上方冰山卖单压制明显"
        else:
            return f"盘口失衡率 {obi:.1f}，巨量冰山卖单压制"

    def _interpret_volume(self, volume: float, avg_volume: float) -> Optional[str]:
        """解读成交量"""
        if avg_volume == 0:
            return None

        ratio = volume / avg_volume

        if ratio > 3:
            return (
                f"15分钟级别巨量爆发，成交量达 {volume/1e6:.1f}M USDT "
                f"（平均 {avg_volume/1e6:.1f}M），主力资金强势进场"
            )
        elif ratio > 2:
            return (
                f"15分钟级别巨量突破，成交量 {volume/1e6:.1f}M USDT "
                f"（平均 {avg_volume/1e6:.1f}M），显著放量"
            )
        elif ratio > 1.5:
            return (
                f"15分钟级别放量，成交量 {volume/1e6:.1f}M USDT "
                f"（平均 {avg_volume/1e6:.1f}M）"
            )
        else:
            return None

    def _interpret_ema_distance(self, ema_dist_pct: float) -> str:
        """解读 EMA 距离"""
        if abs(ema_dist_pct) < 1:
            return f"价格紧贴 EMA50（偏离 {ema_dist_pct:+.1f}%），完美回踩击球区"
        elif abs(ema_dist_pct) < 3:
            return f"价格贴近 EMA50（偏离 {ema_dist_pct:+.1f}%），健康击球区"
        elif ema_dist_pct > 5:
            return f"价格大幅偏离 EMA50（+{ema_dist_pct:.1f}%），追高风险加大"
        elif ema_dist_pct < -5:
            return f"价格大幅低于 EMA50（{ema_dist_pct:.1f}%），超跌反弹机会"
        else:
            return f"价格偏离 EMA50 {ema_dist_pct:+.1f}%"
