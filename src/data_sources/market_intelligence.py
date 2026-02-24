"""
数据源模块 - 抓取市场情报
包括：Twitter/X 情绪、加密新闻、链上数据、鲸鱼追踪
"""
import os
import re
import json
import time
import logging
import hashlib
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from abc import ABC, abstractmethod
from collections import deque

logger = logging.getLogger(__name__)


@dataclass
class NewsItem:
    """新闻条目"""
    title: str
    source: str
    url: str
    timestamp: datetime
    sentiment: str = 'neutral'  # 'bullish', 'bearish', 'neutral'
    relevance: float = 0.5  # 0.0 - 1.0
    content: str = ''
    keywords: List[str] = field(default_factory=list)


@dataclass
class Tweet:
    """推文数据"""
    id: str
    text: str
    author: str
    timestamp: datetime
    likes: int = 0
    retweets: int = 0
    replies: int = 0
    sentiment: str = 'neutral'
    keywords: List[str] = field(default_factory=list)


@dataclass
class WhaleAlert:
    """鲸鱼警报"""
    tx_hash: str
    symbol: str
    amount: float
    amount_usd: float
    from_address: str
    to_address: str
    timestamp: datetime
    tx_type: str  # 'transfer', 'exchange_inflow', 'exchange_outflow'


class DataSourceBase(ABC):
    """数据源基类"""

    def __init__(self, name: str):
        self.name = name
        self.enabled = True
        self.last_fetch = None
        self.cache_duration = 300  # 5 分钟缓存

    @abstractmethod
    def fetch(self, **kwargs) -> List:
        """获取数据"""
        pass

    def should_fetch(self) -> bool:
        """判断是否应该获取新数据"""
        if not self.last_fetch:
            return True
        return (datetime.now() - self.last_fetch).total_seconds() > self.cache_duration

    def enable(self):
        self.enabled = True
        logger.info(f"数据源 {self.name} 已启用")

    def disable(self):
        self.enabled = False
        logger.info(f"数据源 {self.name} 已禁用")


class TwitterSentimentSource(DataSourceBase):
    """Twitter/X 情绪数据源"""

    # 加密货币相关账号（示例）
    CRYPTO_INFLUENCERS = [
        'elonmusk', 'VitalikButerin', 'APompliano', 'novogratz',
        'RaoulGMI', '100trillionUSD', 'glassnode', 'whale_alert'
    ]

    # 看涨关键词
    BULLISH_KEYWORDS = [
        'moon', 'bull', 'bullish', 'buy', 'pump', 'surge', 'rally',
        'breakout', 'all-time high', 'ath', 'gains', 'profit',
        'accumulate', 'hodl', 'diamond hands'
    ]

    # 看跌关键词
    BEARISH_KEYWORDS = [
        'dump', 'crash', 'bear', 'bearish', 'sell', 'rekt', 'blood',
        'correction', 'bubble', 'collapse', 'scam', 'rug pull',
        'dead cat', 'sell off', 'panic'
    ]

    def __init__(self, bearer_token: Optional[str] = None):
        super().__init__("Twitter Sentiment")
        self.bearer_token = bearer_token or os.getenv('TWITTER_BEARER_TOKEN')
        self.tweets_cache: deque = deque(maxlen=1000)
        self.session = None

        if self.bearer_token:
            logger.info("Twitter API 已配置")
        else:
            logger.warning("Twitter API 未配置，将使用模拟数据")

    def _analyze_sentiment(self, text: str) -> Tuple[str, List[str]]:
        """分析文本情绪"""
        text_lower = text.lower()
        bullish_count = 0
        bearish_count = 0
        found_keywords = []

        for keyword in self.BULLISH_KEYWORDS:
            if keyword.lower() in text_lower:
                bullish_count += 1
                found_keywords.append(f'+{keyword}')

        for keyword in self.BEARISH_KEYWORDS:
            if keyword.lower() in text_lower:
                bearish_count += 1
                found_keywords.append(f'-{keyword}')

        if bullish_count > bearish_count:
            return 'bullish', found_keywords
        elif bearish_count > bullish_count:
            return 'bearish', found_keywords
        else:
            return 'neutral', found_keywords

    def _mock_tweets(self, symbol: str) -> List[Tweet]:
        """生成模拟推文（用于测试）"""
        mock_data = [
            f"${symbol.split('/')[0]} looking strong! Accumulating more #crypto #bullish",
            f"Just sold my {symbol}, expecting a correction #trading",
            f"{symbol} breaking out! Moon incoming! #HODL",
            f"Whale alert: Large {symbol} transfer detected",
            f"Technical analysis: {symbol} forming bullish pattern",
        ]

        tweets = []
        for i, text in enumerate(mock_data):
            sentiment, keywords = self._analyze_sentiment(text)
            tweet = Tweet(
                id=f"mock_{i}",
                text=text,
                author=f"crypto_trader_{i}",
                timestamp=datetime.now() - timedelta(minutes=i * 5),
                likes=100 + i * 50,
                retweets=20 + i * 10,
                sentiment=sentiment,
                keywords=keywords
            )
            tweets.append(tweet)

        return tweets

    def fetch(self, symbol: str, limit: int = 50) -> List[Tweet]:
        """
        获取推文

        Args:
            symbol: 交易对（如 BTC/USDT）
            limit: 数量限制

        Returns:
            推文列表
        """
        if not self.enabled:
            return []

        if not self.bearer_token:
            # 使用模拟数据
            logger.debug(f"使用模拟 Twitter 数据: {symbol}")
            return self._mock_tweets(symbol)

        try:
            # 实际 API 调用（需要 requests 库）
            import requests

            base_currency = symbol.split('/')[0]
            query = f"${base_currency} OR #{base_currency}"

            # Twitter API v2 搜索
            # 注意：实际使用需要 Twitter API 认证
            url = "https://api.twitter.com/2/tweets/search/recent"
            headers = {"Authorization": f"Bearer {self.bearer_token}"}
            params = {
                "query": query,
                "max_results": min(limit, 100),
                "tweet.fields": "created_at,public_metrics,author_id"
            }

            response = requests.get(url, headers=headers, params=params)

            if response.status_code != 200:
                logger.error(f"Twitter API 错误: {response.status_code}")
                return self._mock_tweets(symbol)

            data = response.json()
            tweets = []

            for tweet_data in data.get('data', []):
                text = tweet_data.get('text', '')
                sentiment, keywords = self._analyze_sentiment(text)

                metrics = tweet_data.get('public_metrics', {})

                tweet = Tweet(
                    id=tweet_data['id'],
                    text=text,
                    author=tweet_data.get('author_id', 'unknown'),
                    timestamp=datetime.fromisoformat(tweet_data['created_at'].replace('Z', '+00:00')),
                    likes=metrics.get('like_count', 0),
                    retweets=metrics.get('retweet_count', 0),
                    replies=metrics.get('reply_count', 0),
                    sentiment=sentiment,
                    keywords=keywords
                )
                tweets.append(tweet)

            self.last_fetch = datetime.now()
            logger.info(f"获取 {len(tweets)} 条推文: {symbol}")

            return tweets

        except Exception as e:
            logger.error(f"获取 Twitter 数据失败: {e}")
            return self._mock_tweets(symbol)

    def get_sentiment_score(self, symbol: str) -> Dict:
        """
        获取情绪评分

        Returns:
            {
                'score': 0.0-1.0,  # 0.5 = neutral
                'bullish_ratio': 0.0-1.0,
                'bearish_ratio': 0.0-1.0,
                'tweet_count': int,
                'avg_engagement': float
            }
        """
        tweets = self.fetch(symbol)

        if not tweets:
            return {'score': 0.5, 'bullish_ratio': 0, 'bearish_ratio': 0, 'tweet_count': 0, 'avg_engagement': 0}

        bullish = sum(1 for t in tweets if t.sentiment == 'bullish')
        bearish = sum(1 for t in tweets if t.sentiment == 'bearish')
        total = len(tweets)

        bullish_ratio = bullish / total
        bearish_ratio = bearish / total

        # 计算综合情绪评分（0 = 极度看跌, 0.5 = 中性, 1 = 极度看涨）
        score = 0.5 + (bullish_ratio - bearish_ratio) * 0.5

        # 计算平均互动量
        avg_engagement = sum(t.likes + t.retweets for t in tweets) / total

        return {
            'score': score,
            'bullish_ratio': bullish_ratio,
            'bearish_ratio': bearish_ratio,
            'neutral_ratio': 1 - bullish_ratio - bearish_ratio,
            'tweet_count': total,
            'avg_engagement': avg_engagement,
            'sample_tweets': [{'text': t.text[:100], 'sentiment': t.sentiment} for t in tweets[:5]]
        }


class CryptoNewsSource(DataSourceBase):
    """加密货币新闻数据源"""

    # 新闻来源
    NEWS_SOURCES = [
        'coindesk.com',
        'cointelegraph.com',
        'decrypt.co',
        'theblockcrypto.com',
        'cryptonews.net',
    ]

    # 重要关键词
    IMPORTANT_KEYWORDS = [
        'bitcoin', 'ethereum', 'cryptocurrency', 'blockchain',
        'regulation', 'sec', 'adoption', 'etf', 'institutional',
        'defi', 'nft', 'web3', 'upgrade', 'fork', 'listing'
    ]

    def __init__(self, news_api_key: Optional[str] = None):
        super().__init__("Crypto News")
        self.news_api_key = news_api_key or os.getenv('NEWS_API_KEY')
        self.news_cache: deque = deque(maxlen=500)

        if self.news_api_key:
            logger.info("News API 已配置")
        else:
            logger.warning("News API 未配置，将使用模拟数据")

    def _mock_news(self, symbol: str) -> List[NewsItem]:
        """生成模拟新闻"""
        base_currency = symbol.split('/')[0]

        mock_data = [
            {
                'title': f'{base_currency} Shows Strong Momentum as Institutional Interest Grows',
                'source': 'CoinDesk',
                'sentiment': 'bullish',
            },
            {
                'title': f'Regulators Eye {base_currency} as Market Volatility Continues',
                'source': 'Cointelegraph',
                'sentiment': 'bearish',
            },
            {
                'title': f'Major Exchange Announces {base_currency} Trading Pairs',
                'source': 'Decrypt',
                'sentiment': 'bullish',
            },
            {
                'title': f'Whale Alert: Large {base_currency} Movement Detected',
                'source': 'CryptoNews',
                'sentiment': 'neutral',
            },
        ]

        news_items = []
        for i, item in enumerate(mock_data):
            news = NewsItem(
                title=item['title'],
                source=item['source'],
                url=f"https://example.com/news/{i}",
                timestamp=datetime.now() - timedelta(hours=i),
                sentiment=item['sentiment'],
                keywords=[base_currency.lower(), 'crypto', 'trading']
            )
            news_items.append(news)

        return news_items

    def fetch(self, symbol: str, limit: int = 20) -> List[NewsItem]:
        """获取新闻"""
        if not self.enabled:
            return []

        if not self.news_api_key:
            return self._mock_news(symbol)

        try:
            import requests

            base_currency = symbol.split('/')[0]

            # NewsAPI 查询
            url = "https://newsapi.org/v2/everything"
            params = {
                'q': f'{base_currency} OR cryptocurrency',
                'sortBy': 'publishedAt',
                'pageSize': limit,
                'apiKey': self.news_api_key,
                'language': 'en'
            }

            response = requests.get(url, params=params)

            if response.status_code != 200:
                logger.error(f"News API 错误: {response.status_code}")
                return self._mock_news(symbol)

            data = response.json()
            news_items = []

            for article in data.get('articles', []):
                # 简单的情绪分析
                title = article.get('title', '')
                sentiment = self._analyze_news_sentiment(title)

                news = NewsItem(
                    title=title,
                    source=article.get('source', {}).get('name', 'Unknown'),
                    url=article.get('url', ''),
                    timestamp=datetime.fromisoformat(article['publishedAt'].replace('Z', '+00:00')),
                    sentiment=sentiment,
                    content=article.get('description', ''),
                )
                news_items.append(news)

            self.last_fetch = datetime.now()
            logger.info(f"获取 {len(news_items)} 条新闻: {symbol}")

            return news_items

        except Exception as e:
            logger.error(f"获取新闻失败: {e}")
            return self._mock_news(symbol)

    def _analyze_news_sentiment(self, text: str) -> str:
        """分析新闻情绪"""
        text_lower = text.lower()

        bullish_words = ['surge', 'rally', 'gain', 'rise', 'bull', 'adopt', 'approve', 'launch']
        bearish_words = ['crash', 'dump', 'fall', 'bear', 'ban', 'reject', 'hack', 'scam']

        bullish = sum(1 for w in bullish_words if w in text_lower)
        bearish = sum(1 for w in bearish_words if w in text_lower)

        if bullish > bearish:
            return 'bullish'
        elif bearish > bullish:
            return 'bearish'
        return 'neutral'


class WhaleAlertSource(DataSourceBase):
    """鲸鱼警报数据源"""

    def __init__(self, whale_alert_key: Optional[str] = None):
        super().__init__("Whale Alert")
        self.api_key = whale_alert_key or os.getenv('WHALE_ALERT_API_KEY')
        self.alerts_cache: deque = deque(maxlen=500)

        # 大额阈值（USD）
        self.large_transfer_threshold = 1000000  # $1M

    def _mock_whale_alerts(self, symbol: str) -> List[WhaleAlert]:
        """生成模拟鲸鱼警报"""
        base_currency = symbol.split('/')[0]

        mock_data = [
            {
                'amount': 500,
                'amount_usd': 25000000,
                'tx_type': 'exchange_outflow',
            },
            {
                'amount': 1200,
                'amount_usd': 60000000,
                'tx_type': 'transfer',
            },
            {
                'amount': 300,
                'amount_usd': 15000000,
                'tx_type': 'exchange_inflow',
            },
        ]

        alerts = []
        for i, data in enumerate(mock_data):
            alert = WhaleAlert(
                tx_hash=f"0x{''.join(['a'] + ['b'] * 63)}",
                symbol=base_currency,
                amount=data['amount'],
                amount_usd=data['amount_usd'],
                from_address="0x" + "1" * 40,
                to_address="0x" + "2" * 40,
                timestamp=datetime.now() - timedelta(minutes=i * 15),
                tx_type=data['tx_type']
            )
            alerts.append(alert)

        return alerts

    def fetch(self, symbol: str, limit: int = 20) -> List[WhaleAlert]:
        """获取鲸鱼警报"""
        if not self.enabled:
            return []

        if not self.api_key:
            return self._mock_whale_alerts(symbol)

        try:
            import requests

            base_currency = symbol.split('/')[0]

            # Whale Alert API
            url = "https://api.whale-alert.io/v1/transactions"
            params = {
                'api_key': self.api_key,
                'min': self.large_transfer_threshold,
                'limit': limit,
            }

            # 注意：实际实现需要根据 Whale Alert API 文档调整
            response = requests.get(url, params=params)

            if response.status_code != 200:
                return self._mock_whale_alerts(symbol)

            data = response.json()
            alerts = []

            for tx in data.get('transactions', []):
                if tx.get('symbol', '').upper() != base_currency:
                    continue

                alert = WhaleAlert(
                    tx_hash=tx.get('hash', ''),
                    symbol=base_currency,
                    amount=tx.get('amount', 0),
                    amount_usd=tx.get('amount_usd', 0),
                    from_address=tx.get('from', {}).get('address', ''),
                    to_address=tx.get('to', {}).get('address', ''),
                    timestamp=datetime.fromtimestamp(tx.get('timestamp', 0)),
                    tx_type=tx.get('transaction_type', 'transfer')
                )
                alerts.append(alert)

            self.last_fetch = datetime.now()
            return alerts

        except Exception as e:
            logger.error(f"获取鲸鱼警报失败: {e}")
            return self._mock_whale_alerts(symbol)

    def get_whale_activity_summary(self, symbol: str) -> Dict:
        """获取鲸鱼活动摘要"""
        alerts = self.fetch(symbol)

        if not alerts:
            return {'total_volume_usd': 0, 'exchange_inflow': 0, 'exchange_outflow': 0}

        total_volume = sum(a.amount_usd for a in alerts)
        exchange_inflow = sum(a.amount_usd for a in alerts if a.tx_type == 'exchange_inflow')
        exchange_outflow = sum(a.amount_usd for a in alerts if a.tx_type == 'exchange_outflow')

        return {
            'total_volume_usd': total_volume,
            'exchange_inflow': exchange_inflow,
            'exchange_outflow': exchange_outflow,
            'net_flow': exchange_outflow - exchange_inflow,
            'alert_count': len(alerts),
            'avg_transaction_size': total_volume / len(alerts) if alerts else 0
        }


class DataAggregator:
    """数据聚合器 - 整合所有数据源"""

    def __init__(self):
        self.twitter = TwitterSentimentSource()
        self.news = CryptoNewsSource()
        self.whales = WhaleAlertSource()

        logger.info("数据聚合器已初始化")

    def get_comprehensive_data(self, symbol: str) -> Dict:
        """
        获取综合市场数据

        Returns:
            {
                'symbol': str,
                'twitter_sentiment': {...},
                'news_sentiment': {...},
                'whale_activity': {...},
                'overall_sentiment': str,
                'confidence': float
            }
        """
        logger.info(f"获取综合数据: {symbol}")

        # 获取各类数据
        twitter_sentiment = self.twitter.get_sentiment_score(symbol)
        news = self.news.fetch(symbol)
        whale_activity = self.whales.get_whale_activity_summary(symbol)

        # 计算新闻情绪
        news_bullish = sum(1 for n in news if n.sentiment == 'bullish')
        news_bearish = sum(1 for n in news if n.sentiment == 'bearish')
        news_total = len(news)
        news_sentiment_score = 0.5 if news_total == 0 else 0.5 + (news_bullish - news_bearish) / news_total * 0.5

        # 计算鲸鱼活动情绪
        # 净流出 = 看涨（从交易所提走）
        whale_score = 0.5
        if whale_activity['total_volume_usd'] > 0:
            net_flow_ratio = whale_activity['net_flow'] / whale_activity['total_volume_usd']
            whale_score = 0.5 + net_flow_ratio * 0.3

        # 综合情绪计算
        overall_score = (
            twitter_sentiment['score'] * 0.4 +
            news_sentiment_score * 0.3 +
            whale_score * 0.3
        )

        if overall_score > 0.65:
            overall_sentiment = 'bullish'
        elif overall_score < 0.35:
            overall_sentiment = 'bearish'
        else:
            overall_sentiment = 'neutral'

        confidence = min(1.0, abs(overall_score - 0.5) * 2)

        return {
            'symbol': symbol,
            'timestamp': datetime.now().isoformat(),
            'twitter_sentiment': twitter_sentiment,
            'news_sentiment': {
                'score': news_sentiment_score,
                'bullish_count': news_bullish,
                'bearish_count': news_bearish,
                'total_count': news_total,
                'headlines': [{'title': n.title, 'sentiment': n.sentiment} for n in news[:5]]
            },
            'whale_activity': whale_activity,
            'overall_sentiment': overall_sentiment,
            'overall_score': overall_score,
            'confidence': confidence,
        }
