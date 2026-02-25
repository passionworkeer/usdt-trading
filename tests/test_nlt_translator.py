"""
测试自然语言数据翻译器（NLTDataTranslator）
"""
import pytest
import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.ai.nlt_translator import NLTDataTranslator


class TestNLTDataTranslator:
    """自然语言数据翻译器测试"""

    def test_init(self):
        """测试初始化"""
        translator = NLTDataTranslator()
        assert translator.last_report_time is None

    # ==================== translate_micro_snapshot ====================

    def test_translate_micro_snapshot_basic(self):
        """测试微观数据翻译 - 基本功能"""
        translator = NLTDataTranslator()
        snapshot = {
            "symbol": "BTCUSDT",
            "price": 95000,
            "funding_rate": 0.0008,
            "obi": -0.6,
            "volume_15m": 1200000,
            "avg_volume_15m": 800000,
            "ema_distance": 0.02
        }

        report = translator.translate_micro_snapshot(snapshot)

        assert "技术面报告" in report
        assert "95,000" in report
        assert "资金费率" in report
        assert "盘口失衡率" in report

    def test_translate_micro_snapshot_with_all_fields(self):
        """测试微观数据翻译 - 所有字段"""
        translator = NLTDataTranslator()
        snapshot = {
            "symbol": "ETHUSDT",
            "price": 3500,
            "funding_rate": 0.01,
            "obi": 0.8,
            "volume_15m": 500000,
            "avg_volume_15m": 200000,
            "ema_distance": -0.01
        }

        report = translator.translate_micro_snapshot(snapshot)

        assert "3,500" in report
        assert "资金费率" in report
        assert "冰山买单" in report  # OBI > 0.7

    def test_translate_micro_snapshot_empty_snapshot(self):
        """测试微观数据翻译 - 空快照"""
        translator = NLTDataTranslator()
        snapshot = {}

        report = translator.translate_micro_snapshot(snapshot)

        assert "技术面报告" in report
        assert "当前价格" in report

    def test_translate_micro_snapshot_missing_optional_fields(self):
        """测试微观数据翻译 - 缺少可选字段"""
        translator = NLTDataTranslator()
        snapshot = {
            "symbol": "BTCUSDT",
            "price": 95000,
            "funding_rate": 0.0001,
            "obi": 0.0,
            "ema_distance": 0.0
        }

        report = translator.translate_micro_snapshot(snapshot)

        assert "技术面报告" in report
        assert "95,000" in report

    # ==================== translate_macro_state ====================

    def test_translate_macro_state_basic(self):
        """测试宏观状态翻译 - 基本功能"""
        translator = NLTDataTranslator()
        macro_state = {
            'global_sentiment': 'panic',
            'dominant_narrative': '监管恐慌',
            'trading_bans': ['LONG'],
            'recommended_stance': 'defensive',
            'reasoning': 'SEC 对交易所采取行动'
        }

        report = translator.translate_macro_state(macro_state)

        assert "宏观大局观" in report
        assert "恐慌" in report
        assert "监管恐慌" in report
        assert "禁止做多" in report
        assert "防御性" in report

    def test_translate_macro_state_euphoric(self):
        """测试宏观状态翻译 - 极度贪婪"""
        translator = NLTDataTranslator()
        macro_state = {
            'global_sentiment': 'euphoric',
            'dominant_narrative': 'ETF行情',
            'trading_bans': [],
            'recommended_stance': 'aggressive',
            'reasoning': '机构入场'
        }

        report = translator.translate_macro_state(macro_state)

        assert "过度贪婪" in report
        assert "ETF行情" in report
        assert "激进" in report

    def test_translate_macro_state_neutral(self):
        """测试宏观状态翻译 - 中性"""
        translator = NLTDataTranslator()
        macro_state = {
            'global_sentiment': 'neutral',
            'dominant_narrative': '震荡整理',
            'trading_bans': [],
            'recommended_stance': 'neutral',
            'reasoning': ''
        }

        report = translator.translate_macro_state(macro_state)

        assert "平稳" in report
        assert "震荡整理" in report

    def test_translate_macro_state_empty(self):
        """测试宏观状态翻译 - 空状态"""
        translator = NLTDataTranslator()

        report = translator.translate_macro_state({})

        assert "宏观大局观" in report
        assert "暂无数据" in report

    def test_translate_macro_state_none(self):
        """测试宏观状态翻译 - None"""
        translator = NLTDataTranslator()

        report = translator.translate_macro_state(None)

        assert "暂无数据" in report

    def test_translate_macro_state_short_ban(self):
        """测试宏观状态翻译 - 做空禁令"""
        translator = NLTDataTranslator()
        macro_state = {
            'global_sentiment': 'euphoric',
            'dominant_narrative': 'FOMO',
            'trading_bans': ['SHORT'],
            'recommended_stance': 'defensive',
            'reasoning': '过度拥挤'
        }

        report = translator.translate_macro_state(macro_state)

        assert "禁止做空" in report

    # ==================== translate_twitter_sentiment ====================

    def test_translate_twitter_sentiment_basic(self):
        """测试 Twitter 情绪翻译 - 基本功能"""
        translator = NLTDataTranslator()
        tweets = [
            {'text': 'BTC to the moon!', 'likes': 100},
            {'text': 'Bullish on Bitcoin', 'likes': 50},
            {'text': 'Buying the dip', 'likes': 30}
        ]

        report = translator.translate_twitter_sentiment(tweets)

        assert "Twitter 情绪" in report
        assert "3 条推文" in report
        assert "贪婪" in report

    def test_translate_twitter_sentiment_bearish(self):
        """测试 Twitter 情绪翻译 - 看跌"""
        translator = NLTDataTranslator()
        tweets = [
            {'text': 'BTC crash incoming', 'likes': 100},
            {'text': 'Bear market continues', 'likes': 50},
            {'text': 'Selling everything', 'likes': 30}
        ]

        report = translator.translate_twitter_sentiment(tweets)

        assert "恐慌" in report

    def test_translate_twitter_sentiment_neutral(self):
        """测试 Twitter 情绪翻译 - 分歧"""
        translator = NLTDataTranslator()
        tweets = [
            {'text': 'BTC to the moon!', 'likes': 100},
            {'text': 'BTC crash incoming', 'likes': 100}
        ]

        report = translator.translate_twitter_sentiment(tweets)

        assert "分歧" in report

    def test_translate_twitter_sentiment_empty(self):
        """测试 Twitter 情绪翻译 - 空列表"""
        translator = NLTDataTranslator()

        report = translator.translate_twitter_sentiment([])

        assert "暂无数据" in report

    def test_translate_twitter_sentiment_high_likes(self):
        """测试 Twitter 情绪翻译 - 高赞推文"""
        translator = NLTDataTranslator()
        tweets = [
            {'text': 'Important news about Bitcoin!', 'likes': 1000},
            {'text': 'Regular tweet', 'likes': 10}
        ]

        report = translator.translate_twitter_sentiment(tweets)

        assert "1000 likes" in report

    # ==================== translate_news_headlines ====================

    def test_translate_news_headlines_basic(self):
        """测试新闻标题翻译 - 基本功能"""
        translator = NLTDataTranslator()
        news = [
            {'title': 'SEC sues Binance', 'source': 'CoinDesk'},
            {'title': 'Bitcoin ETF approved', 'source': 'Bloomberg'}
        ]

        report = translator.translate_news_headlines(news)

        assert "宏观新闻" in report
        assert "CoinDesk" in report
        assert "SEC sues Binance" in report
        assert "Bloomberg" in report

    def test_translate_news_headlines_empty(self):
        """测试新闻标题翻译 - 空列表"""
        translator = NLTDataTranslator()

        report = translator.translate_news_headlines([])

        assert "暂无重要新闻" in report

    def test_translate_news_headlines_limit(self):
        """测试新闻标题翻译 - 限制数量"""
        translator = NLTDataTranslator()
        news = [
            {'title': f'News {i}', 'source': 'Source'}
            for i in range(10)
        ]

        report = translator.translate_news_headlines(news)

        # 应该只包含前 5 条
        assert "News 0" in report
        assert "News 4" in report

    # ==================== 私有方法测试 ====================

    def test_interpret_funding_rate_high_positive(self):
        """测试资金费率解读 - 极高正数"""
        translator = NLTDataTranslator()

        result = translator._interpret_funding_rate(0.08)

        assert "极高拥挤区" in result
        assert "多头过度贪婪" in result

    def test_interpret_funding_rate_moderate_positive(self):
        """测试资金费率解读 - 温和正数"""
        translator = NLTDataTranslator()

        result = translator._interpret_funding_rate(0.02)

        assert "温和多头" in result

    def test_interpret_funding_rate_neutral(self):
        """测试资金费率解读 - 接近零"""
        translator = NLTDataTranslator()

        result = translator._interpret_funding_rate(0.005)

        assert "中性偏多" in result

    def test_interpret_funding_rate_negative(self):
        """测试资金费率解读 - 负数"""
        translator = NLTDataTranslator()

        result = translator._interpret_funding_rate(-0.08)

        assert "极度恐慌" in result or "空头拥挤" in result

    def test_interpret_obi_strong_buy(self):
        """测试 OBI 解读 - 强劲买盘"""
        translator = NLTDataTranslator()

        result = translator._interpret_obi(0.8)

        assert "冰山买单" in result or "巨量" in result

    def test_interpret_obi_strong_sell(self):
        """测试 OBI 解读 - 强劲卖盘"""
        translator = NLTDataTranslator()

        result = translator._interpret_obi(-0.8)

        assert "冰山卖单" in result or "巨量" in result

    def test_interpret_obi_neutral(self):
        """测试 OBI 解读 - 中性"""
        translator = NLTDataTranslator()

        result = translator._interpret_obi(0.0)

        assert "均衡" in result

    def test_interpret_volume_high(self):
        """测试成交量解读 - 放量"""
        translator = NLTDataTranslator()

        result = translator._interpret_volume(3000000, 1000000)

        assert "巨量" in result or "放量" in result

    def test_interpret_volume_low(self):
        """测试成交量解读 - 正常"""
        translator = NLTDataTranslator()

        result = translator._interpret_volume(1000000, 1000000)

        assert result is None

    def test_interpret_volume_zero_avg(self):
        """测试成交量解读 - 零平均量"""
        translator = NLTDataTranslator()

        result = translator._interpret_volume(1000000, 0)

        assert result is None

    def test_interpret_ema_distance_close(self):
        """测试 EMA 距离解读 - 接近"""
        translator = NLTDataTranslator()

        result = translator._interpret_ema_distance(0.5)

        assert "完美回踩" in result or "紧贴" in result

    def test_interpret_ema_distance_far_above(self):
        """测试 EMA 距离解读 - 远高于"""
        translator = NLTDataTranslator()

        result = translator._interpret_ema_distance(6.0)

        assert "追高" in result or "偏离" in result

    def test_interpret_ema_distance_far_below(self):
        """测试 EMA 距离解读 - 远低于"""
        translator = NLTDataTranslator()

        result = translator._interpret_ema_distance(-6.0)

        assert "超跌" in result or "反弹" in result


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
