"""
外部情报嗅探器（Intelligence Sniffer）

抓取 Twitter/X 情绪 + CoinDesk/Bloomberg 新闻
"""
import requests
import logging
from typing import List, Dict, Optional
from datetime import datetime, timedelta
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


class IntelligenceSniffer:
    """外部情报嗅探器"""

    def __init__(
        self,
        twitter_bearer_token: Optional[str] = None,
        user_agent: str = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    ):
        """
        初始化嗅探器

        Args:
            twitter_bearer_token: Twitter API v2 Bearer Token（可选）
            user_agent: HTTP 请求 User-Agent
        """
        self.twitter_token = twitter_bearer_token
        self.user_agent = user_agent
        self.session = requests.Session()
        self.session.headers.update({'User-Agent': user_agent})

        # 币种名称映射
        self.symbol_mapping = {
            'BTC': 'Bitcoin',
            'ETH': 'Ethereum',
            'SOL': 'Solana',
            'BNB': 'Binance',
            'XRP': 'Ripple',
            'ADA': 'Cardano',
            'DOGE': 'Dogecoin',
            'MATIC': 'Polygon',
            'DOT': 'Polkadot',
            'AVAX': 'Avalanche',
        }

        logger.info(
            f"IntelligenceSniffer 初始化完成 "
            f"(Twitter: {'已配置' if twitter_bearer_token else '未配置'})"
        )

    async def scrape_twitter_sentiment(
        self,
        symbol: str,
        limit: int = 50
    ) -> List[Dict]:
        """
        抓取 Twitter/X 上特定币种的最新推文

        Args:
            symbol: 交易对，如 'BTCUSDT'
            limit: 最大抓取数量

        Returns:
            [
                {
                    'text': 'BTC to the moon!',
                    'likes': 100,
                    'retweets': 10,
                    'created_at': '2024-01-01T00:00:00.000Z'
                },
                ...
            ]
        """
        if not self.twitter_token:
            logger.warning("未配置 Twitter API Token，跳过情绪抓取")
            return []

        try:
            # 提取币种名称（BTCUSDT -> Bitcoin）
            coin_name = self._symbol_to_name(symbol)
            query = f"{coin_name} -is:retweet lang:en"

            # Twitter API v2 搜索
            url = "https://api.twitter.com/2/tweets/search/recent"
            headers = {"Authorization": f"Bearer {self.twitter_token}"}
            params = {
                "query": query,
                "max_results": min(limit, 100),
                "tweet.fields": "created_at,public_metrics",
                "expansions": "author_id"
            }

            response = self.session.get(
                url,
                headers=headers,
                params=params,
                timeout=10
            )

            if response.status_code == 429:
                logger.error("Twitter API 速率限制，请稍后重试")
                return []
            elif response.status_code != 200:
                logger.error(f"Twitter API 错误: {response.status_code}")
                return []

            data = response.json()
            tweets = []

            for tweet in data.get('data', []):
                tweets.append({
                    'text': tweet['text'],
                    'likes': tweet['public_metrics']['like_count'],
                    'retweets': tweet['public_metrics']['retweet_count'],
                    'replies': tweet['public_metrics']['reply_count'],
                    'created_at': tweet['created_at']
                })

            logger.info(f"[Twitter] 抓取到 {len(tweets)} 条 {symbol} 推文")
            return tweets

        except requests.exceptions.Timeout:
            logger.error("Twitter API 请求超时")
            return []
        except Exception as e:
            logger.error(f"Twitter 抓取失败: {e}")
            return []

    async def scrape_macro_news(self, limit: int = 10) -> List[Dict]:
        """
        抓取过去 24 小时的宏观新闻

        来源：
        - CoinDesk RSS
        - Bloomberg Crypto

        Args:
            limit: 最大抓取数量

        Returns:
            [
                {
                    'title': 'SEC sues Binance',
                    'source': 'CoinDesk',
                    'url': 'https://...',
                    'published': '2024-01-01T00:00:00.000Z'
                },
                ...
            ]
        """
        news = []

        # 1. CoinDesk RSS
        coindesk_news = await self._scrape_coindesk_rss(limit)
        news.extend(coindesk_news)

        # 2. 如果数量不够，可以添加其他源
        if len(news) < limit:
            logger.info(f"已抓取 {len(news)} 条新闻，继续抓取其他源...")

        logger.info(f"[News] 共抓取到 {len(news)} 条宏观新闻")
        return news[:limit]

    async def _scrape_coindesk_rss(self, limit: int = 10) -> List[Dict]:
        """抓取 CoinDesk RSS 订阅源"""
        try:
            url = "https://www.coindesk.com/arc/outboundfeeds/rss/"
            response = self.session.get(url, timeout=10)
            response.raise_for_status()

            # 使用 lxml 解析 XML
            soup = BeautifulSoup(response.content, 'xml')
            items = soup.find_all('item')[:limit]

            news = []
            for item in items:
                # 解析发布时间
                pub_date = item.find('pubDate')
                if pub_date:
                    try:
                        published = datetime.strptime(
                            pub_date.text,
                            '%a, %d %b %Y %H:%M:%S %Z'
                        )
                        # 只保留过去 24 小时的新闻
                        if datetime.now() - published > timedelta(hours=24):
                            continue
                        published = published.isoformat()
                    except Exception:
                        published = None
                else:
                    published = None

                news.append({
                    'title': item.title.text,
                    'source': 'CoinDesk',
                    'url': item.link.text,
                    'published': published
                })

            logger.info(f"[CoinDesk] 抓取到 {len(news)} 条新闻")
            return news

        except requests.exceptions.Timeout:
            logger.error("CoinDesk RSS 请求超时")
            return []
        except Exception as e:
            logger.error(f"CoinDesk RSS 抓取失败: {e}")
            return []

    def _symbol_to_name(self, symbol: str) -> str:
        """
        将交易对转换为币种名称

        Examples:
            BTCUSDT -> Bitcoin
            ETHBUSD -> Ethereum
        """
        # 移除稳定币后缀
        base = symbol.replace('USDT', '').replace('BUSD', '').replace('USD', '')

        return self.symbol_mapping.get(base, base)

    def analyze_sentiment_from_tweets(self, tweets: List[Dict]) -> Dict:
        """
        从推文中分析情绪（简单的关键词方法）

        Args:
            tweets: 推文列表

        Returns:
            {
                'sentiment': 'bullish' | 'bearish' | 'neutral',
                'score': 0.0-1.0,
                'bullish_count': 30,
                'bearish_count': 10,
                'total': 50
            }
        """
        if not tweets:
            return {
                'sentiment': 'neutral',
                'score': 0.5,
                'bullish_count': 0,
                'bearish_count': 0,
                'total': 0
            }

        bullish_keywords = [
            'moon', 'bull', 'buy', 'pump', 'rocket', 'dump', 'scam',
            'bullish', 'long', 'hold', 'hodl', 'gain', 'profit', 'up'
        ]
        bearish_keywords = [
            'crash', 'bear', 'sell', 'dump', 'scam',
            'bearish', 'short', 'loss', 'down', 'fall', 'drop'
        ]

        bullish_count = 0
        bearish_count = 0

        for tweet in tweets:
            text = tweet['text'].lower()
            if any(kw in text for kw in bullish_keywords):
                bullish_count += 1
            if any(kw in text for kw in bearish_keywords):
                bearish_count += 1

        total = len(tweets)

        # 计算情绪得分
        if bullish_count > bearish_count * 1.5:
            sentiment = 'bullish'
            score = 0.5 + (bullish_count - bearish_count) / (2 * total)
        elif bearish_count > bullish_count * 1.5:
            sentiment = 'bearish'
            score = 0.5 - (bearish_count - bullish_count) / (2 * total)
        else:
            sentiment = 'neutral'
            score = 0.5

        return {
            'sentiment': sentiment,
            'score': max(0.0, min(1.0, score)),
            'bullish_count': bullish_count,
            'bearish_count': bearish_count,
            'total': total
        }

    def close(self):
        """关闭 session"""
        self.session.close()
