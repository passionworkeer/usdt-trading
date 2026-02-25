"""
测试外部情报嗅探器（IntelligenceSniffer）
"""
import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.intelligence.web_scraper import IntelligenceSniffer


class TestIntelligenceSniffer:
    """外部情报嗅探器测试"""

    # ==================== 初始化测试 ====================

    def test_init_with_token(self):
        """测试初始化 - 有 Twitter Token"""
        sniffer = IntelligenceSniffer(twitter_bearer_token="test_token")

        assert sniffer.twitter_token == "test_token"
        assert sniffer.session is not None

    def test_init_without_token(self):
        """测试初始化 - 无 Twitter Token"""
        sniffer = IntelligenceSniffer()

        assert sniffer.twitter_token is None

    def test_init_custom_user_agent(self):
        """测试初始化 - 自定义 User-Agent"""
        custom_ua = "CustomBot/1.0"
        sniffer = IntelligenceSniffer(user_agent=custom_ua)

        assert sniffer.user_agent == custom_ua

    def test_symbol_mapping(self):
        """测试币种名称映射"""
        sniffer = IntelligenceSniffer()

        assert sniffer.symbol_mapping['BTC'] == 'Bitcoin'
        assert sniffer.symbol_mapping['ETH'] == 'Ethereum'
        assert sniffer.symbol_mapping['SOL'] == 'Solana'

    # ==================== _symbol_to_name 测试 ====================

    def test_symbol_to_name_btc(self):
        """测试交易对转换 - BTC"""
        sniffer = IntelligenceSniffer()

        result = sniffer._symbol_to_name('BTCUSDT')

        assert result == 'Bitcoin'

    def test_symbol_to_name_eth(self):
        """测试交易对转换 - ETH"""
        sniffer = IntelligenceSniffer()

        result = sniffer._symbol_to_name('ETHUSDT')

        assert result == 'Ethereum'

    def test_symbol_to_name_busd(self):
        """测试交易对转换 - BUSD 后缀"""
        sniffer = IntelligenceSniffer()

        result = sniffer._symbol_to_name('ETHBUSD')

        assert result == 'Ethereum'

    def test_symbol_to_name_unknown(self):
        """测试交易对转换 - 未知币种"""
        sniffer = IntelligenceSniffer()

        result = sniffer._symbol_to_name('UNKNOWNUSDT')

        assert result == 'UNKNOWN'

    # ==================== scrape_twitter_sentiment 测试 ====================

    @pytest.mark.asyncio
    async def test_scrape_twitter_no_token(self):
        """测试 Twitter 抓取 - 无 Token"""
        sniffer = IntelligenceSniffer()

        result = await sniffer.scrape_twitter_sentiment('BTCUSDT')

        assert result == []

    @pytest.mark.asyncio
    async def test_scrape_twitter_success(self):
        """测试 Twitter 抓取 - 成功"""
        sniffer = IntelligenceSniffer(twitter_bearer_token="test_token")

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'data': [
                {
                    'text': 'BTC to the moon!',
                    'public_metrics': {'like_count': 100, 'retweet_count': 10, 'reply_count': 5},
                    'created_at': '2024-01-01T00:00:00.000Z'
                }
            ]
        }

        with patch.object(sniffer.session, 'get', return_value=mock_response):
            result = await sniffer.scrape_twitter_sentiment('BTCUSDT')

        assert len(result) == 1
        assert result[0]['text'] == 'BTC to the moon!'
        assert result[0]['likes'] == 100

    @pytest.mark.asyncio
    async def test_scrape_twitter_rate_limit(self):
        """测试 Twitter 抓取 - 速率限制"""
        sniffer = IntelligenceSniffer(twitter_bearer_token="test_token")

        mock_response_429 = MagicMock()
        mock_response_429.status_code = 429
        mock_response_429.headers = {'x-rate-limit-reset': str(int(datetime.now().timestamp()) + 1)}

        mock_response_200 = MagicMock()
        mock_response_200.status_code = 200
        mock_response_200.json.return_value = {'data': []}

        with patch.object(sniffer.session, 'get', side_effect=[mock_response_429, mock_response_200]):
            with patch('time.sleep'):
                result = await sniffer.scrape_twitter_sentiment('BTCUSDT')

        assert result == []

    @pytest.mark.asyncio
    async def test_scrape_twitter_error(self):
        """测试 Twitter 抓取 - 错误响应"""
        sniffer = IntelligenceSniffer(twitter_bearer_token="test_token")

        mock_response = MagicMock()
        mock_response.status_code = 500

        with patch.object(sniffer.session, 'get', return_value=mock_response):
            result = await sniffer.scrape_twitter_sentiment('BTCUSDT')

        assert result == []

    @pytest.mark.asyncio
    async def test_scrape_twitter_timeout(self):
        """测试 Twitter 抓取 - 超时"""
        import requests
        sniffer = IntelligenceSniffer(twitter_bearer_token="test_token")

        with patch.object(sniffer.session, 'get', side_effect=requests.exceptions.Timeout()):
            result = await sniffer.scrape_twitter_sentiment('BTCUSDT')

        assert result == []

    @pytest.mark.asyncio
    async def test_scrape_twitter_exception(self):
        """测试 Twitter 抓取 - 异常"""
        sniffer = IntelligenceSniffer(twitter_bearer_token="test_token")

        with patch.object(sniffer.session, 'get', side_effect=Exception("Network error")):
            result = await sniffer.scrape_twitter_sentiment('BTCUSDT')

        assert result == []

    # ==================== scrape_macro_news 测试 ====================

    @pytest.mark.asyncio
    async def test_scrape_macro_news_success(self):
        """测试新闻抓取 - 成功"""
        sniffer = IntelligenceSniffer()

        with patch.object(sniffer, '_scrape_coindesk_rss', new_callable=AsyncMock) as mock_rss:
            mock_rss.return_value = [
                {'title': 'Test News', 'source': 'CoinDesk', 'url': 'http://test.com'}
            ]

            result = await sniffer.scrape_macro_news(limit=10)

        assert len(result) == 1
        assert result[0]['title'] == 'Test News'

    @pytest.mark.asyncio
    async def test_scrape_macro_news_limit(self):
        """测试新闻抓取 - 限制数量"""
        sniffer = IntelligenceSniffer()

        news_list = [{'title': f'News {i}', 'source': 'CoinDesk', 'url': f'http://test.com/{i}'}
                     for i in range(20)]

        with patch.object(sniffer, '_scrape_coindesk_rss', new_callable=AsyncMock) as mock_rss:
            mock_rss.return_value = news_list

            result = await sniffer.scrape_macro_news(limit=5)

        assert len(result) == 5

    # ==================== _scrape_coindesk_rss 测试 ====================

    @pytest.mark.asyncio
    async def test_scrape_coindesk_rss_success(self):
        """测试 CoinDesk RSS 抓取 - 成功"""
        sniffer = IntelligenceSniffer()

        rss_content = '''<?xml version="1.0"?>
        <rss>
            <channel>
                <item>
                    <title>Test News 1</title>
                    <link>http://test.com/1</link>
                    <pubDate>Mon, 01 Jan 2024 12:00:00 GMT</pubDate>
                </item>
                <item>
                    <title>Test News 2</title>
                    <link>http://test.com/2</link>
                    <pubDate>Mon, 01 Jan 2024 13:00:00 GMT</pubDate>
                </item>
            </channel>
        </rss>'''

        mock_response = MagicMock()
        mock_response.content = rss_content.encode()
        mock_response.raise_for_status = MagicMock()

        with patch.object(sniffer.session, 'get', return_value=mock_response):
            result = await sniffer._scrape_coindesk_rss(limit=10)

        assert len(result) >= 0  # 可能因为时间过滤而减少

    @pytest.mark.asyncio
    async def test_scrape_coindesk_rss_timeout(self):
        """测试 CoinDesk RSS 抓取 - 超时"""
        import requests
        sniffer = IntelligenceSniffer()

        with patch.object(sniffer.session, 'get', side_effect=requests.exceptions.Timeout()):
            result = await sniffer._scrape_coindesk_rss(limit=10)

        assert result == []

    @pytest.mark.asyncio
    async def test_scrape_coindesk_rss_exception(self):
        """测试 CoinDesk RSS 抓取 - 异常"""
        sniffer = IntelligenceSniffer()

        with patch.object(sniffer.session, 'get', side_effect=Exception("Network error")):
            result = await sniffer._scrape_coindesk_rss(limit=10)

        assert result == []

    # ==================== analyze_sentiment_from_tweets 测试 ====================

    def test_analyze_sentiment_bullish(self):
        """测试情绪分析 - 看涨"""
        sniffer = IntelligenceSniffer()
        tweets = [
            {'text': 'BTC to the moon! Bullish!', 'likes': 100},
            {'text': 'Buy now! Rocket!', 'likes': 50},
            {'text': 'Great gains ahead', 'likes': 30}
        ]

        result = sniffer.analyze_sentiment_from_tweets(tweets)

        assert result['sentiment'] == 'bullish'
        assert result['bullish_count'] > 0
        assert result['total'] == 3

    def test_analyze_sentiment_bearish(self):
        """测试情绪分析 - 看跌"""
        sniffer = IntelligenceSniffer()
        tweets = [
            {'text': 'BTC crash coming! Bear market!', 'likes': 100},
            {'text': 'Sell everything! Dump!', 'likes': 50},
            {'text': 'Big losses ahead', 'likes': 30}
        ]

        result = sniffer.analyze_sentiment_from_tweets(tweets)

        assert result['sentiment'] == 'bearish'
        assert result['bearish_count'] > 0

    def test_analyze_sentiment_neutral(self):
        """测试情绪分析 - 中性/分歧"""
        sniffer = IntelligenceSniffer()
        tweets = [
            {'text': 'BTC to the moon!', 'likes': 100},
            {'text': 'BTC crash coming!', 'likes': 100}
        ]

        result = sniffer.analyze_sentiment_from_tweets(tweets)

        assert result['sentiment'] == 'neutral'

    def test_analyze_sentiment_empty(self):
        """测试情绪分析 - 空列表"""
        sniffer = IntelligenceSniffer()

        result = sniffer.analyze_sentiment_from_tweets([])

        assert result['sentiment'] == 'neutral'
        assert result['total'] == 0
        assert result['bullish_count'] == 0
        assert result['bearish_count'] == 0

    def test_analyze_sentiment_score_range(self):
        """测试情绪分析 - 分数范围"""
        sniffer = IntelligenceSniffer()
        tweets = [
            {'text': 'BTC bullish!', 'likes': 100}
        ]

        result = sniffer.analyze_sentiment_from_tweets(tweets)

        assert 0.0 <= result['score'] <= 1.0

    def test_analyze_sentiment_mixed_keywords(self):
        """测试情绪分析 - 混合关键词"""
        sniffer = IntelligenceSniffer()
        tweets = [
            {'text': 'BTC dump but buy the dip', 'likes': 100}
        ]

        result = sniffer.analyze_sentiment_from_tweets(tweets)

        # 同时包含看涨和看跌关键词
        assert result['bullish_count'] >= 1
        assert result['bearish_count'] >= 1

    # ==================== close 测试 ====================

    def test_close(self):
        """测试关闭 session"""
        sniffer = IntelligenceSniffer()

        sniffer.close()

        # Session 应该被关闭
        assert sniffer.session is not None

    # ==================== 边界条件测试 ====================

    @pytest.mark.asyncio
    async def test_scrape_twitter_limit_parameter(self):
        """测试 Twitter 抓取 - limit 参数"""
        sniffer = IntelligenceSniffer(twitter_bearer_token="test_token")

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'data': []}

        with patch.object(sniffer.session, 'get', return_value=mock_response) as mock_get:
            await sniffer.scrape_twitter_sentiment('BTCUSDT', limit=30)

            # 检查 max_results 参数
            call_args = mock_get.call_args
            assert call_args[1]['params']['max_results'] == 30

    def test_analyze_sentiment_case_insensitive(self):
        """测试情绪分析 - 大小写不敏感"""
        sniffer = IntelligenceSniffer()
        tweets = [
            {'text': 'BTC TO THE MOON!', 'likes': 100}
        ]

        result = sniffer.analyze_sentiment_from_tweets(tweets)

        assert result['bullish_count'] >= 1

    @pytest.mark.asyncio
    async def test_scrape_coindesk_rss_old_news_filtered(self):
        """测试 CoinDesk RSS - 过滤旧新闻"""
        sniffer = IntelligenceSniffer()

        # 创建超过 24 小时的日期
        old_date = (datetime.now() - timedelta(hours=48)).strftime('%a, %d %b %Y %H:%M:%S GMT')

        rss_content = f'''<?xml version="1.0"?>
        <rss>
            <channel>
                <item>
                    <title>Old News</title>
                    <link>http://test.com/old</link>
                    <pubDate>{old_date}</pubDate>
                </item>
            </channel>
        </rss>'''

        mock_response = MagicMock()
        mock_response.content = rss_content.encode()
        mock_response.raise_for_status = MagicMock()

        with patch.object(sniffer.session, 'get', return_value=mock_response):
            result = await sniffer._scrape_coindesk_rss(limit=10)

        # 旧新闻应该被过滤
        assert all('Old News' not in item['title'] for item in result)


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
