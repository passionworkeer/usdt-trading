"""
专业情绪分析器（VADER）

使用 VADER (Valence Aware Dictionary and sEntiment Reasoner) 进行情绪分析
- 专门针对社交媒体文本优化
- 支持表情符号、俚语、网络用语
- 返回复合情绪分数（-1 到 1）

引用: Hutto, C.J. & Gilbert, E.E. (2014). VADER: A Parsimonious Rule-based Model for
      Sentiment Analysis of Social Media Text. Eighth International Conference on
      Weblogs and Social Media (ICWSM-14). Ann Arbor, MI, June 2014.
"""
import logging
from typing import Dict, List

from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

logger = logging.getLogger(__name__)


class SentimentAnalyzer:
    """专业情绪分析器（VADER）"""

    def __init__(self):
        """初始化 VADER 分析器"""
        self.analyzer = SentimentIntensityAnalyzer()
        logger.info("VADER 情绪分析器初始化完成")

    def analyze(self, text: str) -> Dict:
        """
        分析单条文本的情绪

        Args:
            text: 待分析的文本

        Returns:
            {
                'polarity': 'positive' | 'neutral' | 'negative',
                'score': -1 到 1 的复合分数,
                'positive': 正面情绪占比,
                'negative': 负面情绪占比,
                'neutral': 中性情绪占比
            }
        """
        scores = self.analyzer.polarity_scores(text)
        compound = scores['compound']

        # VADER 标准阈值
        # compound >= 0.05: positive
        # compound <= -0.05: negative
        # -0.05 < compound < 0.05: neutral
        if compound >= 0.05:
            polarity = 'positive'
        elif compound <= -0.05:
            polarity = 'negative'
        else:
            polarity = 'neutral'

        return {
            'polarity': polarity,
            'score': compound,
            'positive': scores['pos'],
            'negative': scores['neg'],
            'neutral': scores['neu']
        }

    def analyze_batch(self, texts: List[str]) -> Dict:
        """
        批量分析多条文本，返回总体情绪

        Args:
            texts: 文本列表

        Returns:
            {
                'overall': 'positive' | 'neutral' | 'negative',
                'avg_score': 平均复合分数,
                'positive_pct': 正面文本占比,
                'negative_pct': 负面文本占比,
                'count': 分析的文本数量
            }
        """
        if not texts:
            return {
                'overall': 'neutral',
                'avg_score': 0.0,
                'positive_pct': 0.0,
                'negative_pct': 0.0,
                'count': 0
            }

        results = [self.analyze(t) for t in texts]

        avg_score = sum(r['score'] for r in results) / len(results)
        positive_count = sum(1 for r in results if r['polarity'] == 'positive')
        negative_count = sum(1 for r in results if r['polarity'] == 'negative')

        if avg_score >= 0.05:
            overall = 'positive'
        elif avg_score <= -0.05:
            overall = 'negative'
        else:
            overall = 'neutral'

        return {
            'overall': overall,
            'avg_score': avg_score,
            'positive_pct': positive_count / len(results),
            'negative_pct': negative_count / len(results),
            'count': len(results)
        }

    def get_sentiment_label(self, score: float) -> str:
        """
        将分数转换为中文情绪标签

        Args:
            score: -1 到 1 的复合分数

        Returns:
            中文情绪描述
        """
        if score >= 0.5:
            return "极度贪婪"
        elif score >= 0.2:
            return "贪婪"
        elif score >= 0.05:
            return "偏多"
        elif score >= -0.05:
            return "中性"
        elif score >= -0.2:
            return "偏空"
        elif score >= -0.5:
            return "恐慌"
        else:
            return "极度恐慌"
