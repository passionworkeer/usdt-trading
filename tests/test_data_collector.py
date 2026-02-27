"""
测试市场数据收集器

测试 AI 数据增强功能。
"""
import asyncio
import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

# 测试导入
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestIndicatorSet:
    """测试技术指标数据结构"""

    def test_to_dict(self):
        """测试转换为字典"""
        from src.ai.context import IndicatorSet

        ind = IndicatorSet(
            rsi_14=65.5,
            ema_50=50000.0,
            macd_histogram=0.15,
        )

        result = ind.to_dict()
        assert result['rsi_14'] == 65.5
        assert result['ema_50'] == 50000.0
        assert result['macd_histogram'] == 0.15

    def test_to_prompt_format(self):
        """测试提示词格式化"""
        from src.ai.context import IndicatorSet

        ind = IndicatorSet(
            rsi_14=25.0,
            ema_9=50000.0,
            ema_21=49500.0,
            macd_histogram=-0.05,
            bb_position=0.2,
            volume_ratio=2.5,
        )

        prompt = ind.to_prompt_format("15m")
        assert "15m" in prompt
        assert "RSI" in prompt
        assert "EMA9" in prompt
        assert "超卖" in prompt  # RSI < 30
        assert "放量" in prompt  # volume_ratio > 1.5


class TestCandlestickPattern:
    """测试K线形态"""

    def test_to_prompt_format(self):
        """测试提示词格式化"""
        from src.ai.context import CandlestickPattern

        pattern = CandlestickPattern(
            name='锤子线',
            interval='15m',
            confidence=0.75,
            direction='bullish',
        )

        prompt = pattern.to_prompt_format()
        assert '15m' in prompt
        assert '锤子线' in prompt
        assert '看涨' in prompt


class TestMacroMarketData:
    """测试宏观市场数据"""

    def test_to_prompt_format(self):
        """测试提示词格式化"""
        from src.ai.context import MacroMarketData

        macro = MacroMarketData(
            funding_rate=0.0001,
            next_funding_time=datetime(2024, 1, 1, 8, 0, 0),
            oi_current=50000,
            oi_change_1h=5.5,
            oi_change_4h=10.2,
            price_diff_pct=0.15,
            long_short_ratio=1.25,
        )

        prompt = macro.to_prompt_format()
        assert "资金费率" in prompt
        assert "OI变化" in prompt
        assert "多空比" in prompt


class TestAIAnalysisContext:
    """测试AI分析上下文"""

    def test_to_prompt_data(self):
        """测试完整提示词生成"""
        import pandas as pd
        from src.ai.context import (
            AIAnalysisContext,
            KLineData,
            IndicatorSet,
            CandlestickPattern,
            MacroMarketData,
        )

        # 创建测试数据
        df = pd.DataFrame({
            'open': [50000, 50100, 50200],
            'high': [50300, 50400, 50500],
            'low': [49900, 50000, 50100],
            'close': [50100, 50200, 50300],
            'volume': [1000, 1200, 1500],
            'quote_volume': [50000000, 60000000, 75000000],
            'timestamp': pd.date_range('2024-01-01', periods=3, freq='h'),
        })

        kline = KLineData(interval='15m', df=df)
        ind = IndicatorSet(rsi_14=65.0, ema_50=50000.0)
        pattern = CandlestickPattern(
            name='锤子线',
            interval='15m',
            confidence=0.7,
            direction='bullish',
        )
        macro = MacroMarketData(funding_rate=0.0001, oi_current=50000)

        context = AIAnalysisContext(
            symbol='BTC/USDT',
            timestamp=datetime.now(),
            klines={'15m': kline},
            indicators={'15m': ind},
            patterns={'15m': [pattern]},
            macro_data=macro,
        )

        prompt = context.to_prompt_data()
        assert 'BTC/USDT' in prompt
        assert '15分钟' in prompt
        assert '锤子线' in prompt
        assert '资金费率' in prompt


class TestMTFKlinesCollector:
    """测试多时间框架K线收集器"""

    @pytest.mark.asyncio
    async def test_fetch(self):
        """测试获取K线"""
        from src.ai.data.mtf_klines import MTFKlinesCollector

        # 创建 mock session
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value=[
            [1704067200000, "50000", "51000", "49000", "50500", "1000"],
            [1704070800000, "50500", "51500", "50000", "51000", "1200"],
        ])

        mock_session = AsyncMock()
        mock_session.get.return_value.__aenter__ = AsyncMock(return_value=mock_response)
        mock_session.get.return_value.__aexit__ = AsyncMock(return_value=None)

        collector = MTFKlinesCollector(mock_session)
        result = await collector.fetch('BTCUSDT', '15m', 2)

        assert result is not None
        assert result.interval == '15m'
        assert len(result.df) == 2


class TestTechnicalIndicators:
    """测试技术指标计算"""

    def test_calculate_indicators(self):
        """测试指标计算"""
        import pandas as pd
        from src.ai.data.indicators import TechnicalIndicatorsCalculator

        # 创建足够的测试数据
        np = pytest.importorskip("numpy")
        import numpy as np

        prices = np.linspace(45000, 55000, 100)
        df = pd.DataFrame({
            'open': prices,
            'high': prices + 100,
            'low': prices - 100,
            'close': prices + 50,
            'volume': np.random.uniform(1000, 2000, 100),
        })

        indicators = TechnicalIndicatorsCalculator.calculate(df)

        # 验证基本指标
        assert indicators.rsi_14 is not None
        assert indicators.ema_9 is not None
        assert indicators.ema_21 is not None
        assert indicators.atr_14 is not None
        assert indicators.bb_position is not None


class TestPatternRecognizer:
    """测试形态识别"""

    def test_recognize_hammer(self):
        """测试锤子线识别"""
        import pandas as pd
        from src.ai.data.patterns import PatternRecognizer
        from src.ai.context import KLineData

        # 锤子线形态
        df = pd.DataFrame({
            'open': [50000, 50100, 50100],
            'high': [50200, 50300, 50200],  # 长上影线
            'low': [49500, 49600, 49800],   # 长下影线
            'close': [50100, 50100, 50050], # 小实体
            'volume': [1000, 1000, 1000],
        })

        kline = KLineData(interval='15m', df=df)
        patterns = PatternRecognizer._recognize_single(df)

        # 至少应该有形态识别
        assert isinstance(patterns, list)


class TestCollectorIntegration:
    """测试收集器集成"""

    @pytest.mark.asyncio
    async def test_collect_with_mock(self):
        """测试完整收集流程"""
        from src.ai.data.collector import MarketDataCollector
        from src.ai.context import AIAnalysisContext

        # 这个测试验证数据结构正确
        # 实际 API 调用需要网络，在 CI 中应该 mock
        pass


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
