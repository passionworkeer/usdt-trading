"""
测试 Claude Provider

测试覆盖：
- 初始化
- 分析功能
- 复盘功能
- 健康检查
- 响应解析
- 错误处理
"""
import json
import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from src.ai.provider import (
    ActionType,
    RiskLevel,
    MarketContext,
    EvidenceBasedDecision,
    TradeResult,
    ReviewReport,
    ClaudeProvider,
)


# ==================== Fixtures ====================


@pytest.fixture
def mock_api_key():
    """Mock API Key"""
    return "sk-test-api-key-12345"


@pytest.fixture
def provider(mock_api_key):
    """创建 Provider 实例"""
    provider = ClaudeProvider(api_key=mock_api_key)
    provider.initialize()
    return provider


@pytest.fixture
def market_context():
    """创建市场上下文"""
    return MarketContext(
        symbol="BTCUSDT",
        current_price=50000.0,
        price_history=[49000, 49500, 49800, 50000],
        volume_24h=1000000.0,
        market_cap=900000000000.0,
        indicators={
            "rsi": 65.0,
            "macd": 150.5,
            "ema_20": 49800.0,
        },
        news_sentiment=0.6,
    )


@pytest.fixture
def trade_result():
    """创建交易结果"""
    return TradeResult(
        symbol="BTCUSDT",
        action=ActionType.BUY,
        entry_price=50000.0,
        exit_price=52000.0,
        quantity=0.1,
        pnl=200.0,
        pnl_pct=4.0,
        status="closed",
    )


# ==================== 初始化测试 ====================


class TestClaudeProviderInit:
    """测试初始化"""

    def test_init_with_api_key(self, mock_api_key):
        """测试使用 API Key 初始化"""
        provider = ClaudeProvider(api_key=mock_api_key)

        assert provider.name == "claude"
        assert provider.version == "1.0.0"
        assert provider._api_key == mock_api_key

    def test_init_with_env_var(self, mock_api_key, monkeypatch):
        """测试从环境变量读取 API Key"""
        monkeypatch.setenv("ANTHROPIC_API_KEY", mock_api_key)

        provider = ClaudeProvider()
        assert provider._api_key == mock_api_key

    def test_init_without_api_key(self):
        """测试没有 API Key 时的初始化"""
        provider = ClaudeProvider()

        # 初始化应该失败
        result = provider.initialize()

        assert result is False
        assert "API Key" in provider.last_error

    def test_default_model(self, mock_api_key):
        """测试默认模型"""
        provider = ClaudeProvider(api_key=mock_api_key)
        assert provider._model == "claude-sonnet-4-6"

    def test_custom_model(self, mock_api_key):
        """测试自定义模型"""
        provider = ClaudeProvider(api_key=mock_api_key, model="claude-opus-4-6")
        assert provider._model == "claude-opus-4-6"

    def test_get_capabilities(self, provider):
        """测试获取能力"""
        capabilities = provider.get_capabilities()

        assert capabilities["name"] == "claude"
        assert capabilities["version"] == "1.0.0"
        assert capabilities["supports_streaming"] is False


# ==================== 分析测试 ====================


class TestClaudeProviderAnalyze:
    """测试分析功能"""

    @pytest.mark.asyncio
    async def test_analyze_buy_signal(self, provider, market_context):
        """测试买入信号分析"""
        mock_response = MagicMock()
        mock_response.content = [
            MagicMock(text=json.dumps({
                "action": "buy",
                "confidence": 0.8,
                "reasoning": "技术指标显示上涨趋势",
                "risk_level": "medium",
                "evidence_chain": [
                    {
                        "source": "technical",
                        "metric": "rsi",
                        "value": 65,
                        "weight": 0.8,
                        "confidence": 0.9,
                        "description": "RSI 显示有上涨空间"
                    },
                    {
                        "source": "technical",
                        "metric": "macd",
                        "value": 150.5,
                        "weight": 0.7,
                        "confidence": 0.85,
                        "description": "MACD 金叉"
                    }
                ],
                "stop_loss_pct": 2.0,
                "take_profit_pct": 5.0
            }))
        ]

        with patch.object(provider._client.messages, 'create', new_callable=AsyncMock) as mock_create:
            mock_create.return_value = mock_response

            decision = await provider.analyze(market_context)

            assert decision.action == ActionType.BUY
            assert decision.confidence == 0.8
            assert decision.risk_level == RiskLevel.MEDIUM
            assert len(decision.evidence_chain.evidences) == 2
            assert decision.stop_loss_pct == 2.0
            assert decision.take_profit_pct == 5.0

    @pytest.mark.asyncio
    async def test_analyze_sell_signal(self, provider, market_context):
        """测试卖出信号分析"""
        mock_response = MagicMock()
        mock_response.content = [
            MagicMock(text=json.dumps({
                "action": "sell",
                "confidence": 0.7,
                "reasoning": "技术指标显示下跌趋势",
                "risk_level": "high",
                "evidence_chain": [
                    {
                        "source": "technical",
                        "metric": "rsi",
                        "value": 80,
                        "weight": 0.9,
                        "confidence": 0.85,
                        "description": "RSI 超买"
                    }
                ]
            }))
        ]

        with patch.object(provider._client.messages, 'create', new_callable=AsyncMock) as mock_create:
            mock_create.return_value = mock_response

            decision = await provider.analyze(market_context)

            assert decision.action == ActionType.SELL
            assert decision.confidence == 0.7
            assert decision.risk_level == RiskLevel.HIGH

    @pytest.mark.asyncio
    async def test_analyze_hold_signal(self, provider, market_context):
        """测试观望信号分析"""
        mock_response = MagicMock()
        mock_response.content = [
            MagicMock(text=json.dumps({
                "action": "hold",
                "confidence": 0.5,
                "reasoning": "市场方向不明确",
                "risk_level": "low",
                "evidence_chain": []
            }))
        ]

        with patch.object(provider._client.messages, 'create', new_callable=AsyncMock) as mock_create:
            mock_create.return_value = mock_response

            decision = await provider.analyze(market_context)

            assert decision.action == ActionType.HOLD
            assert decision.confidence == 0.5

    @pytest.mark.asyncio
    async def test_analyze_with_markdown_json(self, provider, market_context):
        """测试解析 Markdown 包裹的 JSON"""
        mock_response = MagicMock()
        mock_response.content = [
            MagicMock(text='''```json
{
    "action": "buy",
    "confidence": 0.75,
    "reasoning": "测试",
    "risk_level": "medium",
    "evidence_chain": []
}
```''')
        ]

        with patch.object(provider._client.messages, 'create', new_callable=AsyncMock) as mock_create:
            mock_create.return_value = mock_response

            decision = await provider.analyze(market_context)

            assert decision.action == ActionType.BUY
            assert decision.confidence == 0.75

    @pytest.mark.asyncio
    async def test_analyze_invalid_json(self, provider, market_context):
        """测试无效 JSON 响应"""
        mock_response = MagicMock()
        mock_response.content = [
            MagicMock(text="这不是有效的 JSON")
        ]

        with patch.object(provider._client.messages, 'create', new_callable=AsyncMock) as mock_create:
            mock_create.return_value = mock_response

            decision = await provider.analyze(market_context)

            # 应该返回后备决策
            assert decision.action == ActionType.HOLD
            assert decision.confidence == 0.0
            assert decision.metadata.get("fallback") is True

    @pytest.mark.asyncio
    async def test_analyze_without_initialization(self, market_context):
        """测试未初始化时的分析"""
        provider = ClaudeProvider()  # 不初始化

        with pytest.raises(RuntimeError, match="未初始化"):
            await provider.analyze(market_context)


# ==================== 复盘测试 ====================


class TestClaudeProviderReview:
    """测试复盘功能"""

    @pytest.mark.asyncio
    async def test_review_successful_trade(self, provider, trade_result):
        """测试成功交易的复盘"""
        mock_response = MagicMock()
        mock_response.content = [
            MagicMock(text=json.dumps({
                "overall_assessment": "交易执行良好",
                "score": 85.0,
                "findings": [
                    {
                        "category": "decision_quality",
                        "severity": "info",
                        "description": "入场时机准确",
                        "recommendation": "继续保持",
                        "evidence": {}
                    }
                ],
                "lessons_learned": ["技术指标确认很重要"],
                "improvements": ["考虑增加仓位管理"]
            }))
        ]

        with patch.object(provider._client.messages, 'create', new_callable=AsyncMock) as mock_create:
            mock_create.return_value = mock_response

            report = await provider.review(trade_result)

            assert report.trade_id == "BTCUSDT"
            assert report.score == 85.0
            assert len(report.findings) == 1
            assert len(report.lessons_learned) == 1

    @pytest.mark.asyncio
    async def test_review_failed_trade(self, provider):
        """测试失败交易的复盘"""
        failed_trade = TradeResult(
            symbol="BTCUSDT",
            action=ActionType.BUY,
            entry_price=50000.0,
            exit_price=48000.0,
            quantity=0.1,
            pnl=-200.0,
            pnl_pct=-4.0,
            status="closed",
        )

        mock_response = MagicMock()
        mock_response.content = [
            MagicMock(text=json.dumps({
                "overall_assessment": "止损不及时",
                "score": 40.0,
                "findings": [
                    {
                        "category": "risk_management",
                        "severity": "error",
                        "description": "未设置止损",
                        "recommendation": "每次交易必须设置止损",
                        "evidence": {}
                    }
                ],
                "lessons_learned": ["风险管理是第一要务"],
                "improvements": ["严格执行止损策略"]
            }))
        ]

        with patch.object(provider._client.messages, 'create', new_callable=AsyncMock) as mock_create:
            mock_create.return_value = mock_response

            report = await provider.review(failed_trade)

            assert report.score == 40.0
            assert report.findings[0].severity == "error"


# ==================== 健康检查测试 ====================


class TestClaudeProviderHealthCheck:
    """测试健康检查"""

    @pytest.mark.asyncio
    async def test_health_check_healthy(self, provider):
        """测试健康状态"""
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="pong")]

        with patch.object(provider._client.messages, 'create', new_callable=AsyncMock) as mock_create:
            mock_create.return_value = mock_response

            is_healthy = await provider.health_check()

            assert is_healthy is True

    @pytest.mark.asyncio
    async def test_health_check_unhealthy(self, mock_api_key):
        """测试不健康状态"""
        provider = ClaudeProvider(api_key=mock_api_key)
        provider.initialize()

        with patch.object(provider._client.messages, 'create', new_callable=AsyncMock) as mock_create:
            mock_create.side_effect = Exception("API Error")

            is_healthy = await provider.health_check()

            assert is_healthy is False

    @pytest.mark.asyncio
    async def test_health_check_without_client(self):
        """测试未初始化时的健康检查"""
        provider = ClaudeProvider()  # 不初始化

        is_healthy = await provider.health_check()

        assert is_healthy is False


# ==================== 辅助方法测试 ====================


class TestClaudeProviderHelpers:
    """测试辅助方法"""

    def test_extract_json_from_markdown_block(self, provider):
        """测试从 Markdown 块提取 JSON"""
        text = '''```json
{"key": "value"}
```'''
        result = provider._extract_json(text)
        assert result == '{"key": "value"}'

    def test_extract_json_from_code_block(self, provider):
        """测试从代码块提取 JSON"""
        text = '''```
{"key": "value"}
```'''
        result = provider._extract_json(text)
        assert result == '{"key": "value"}'

    def test_extract_json_from_raw_text(self, provider):
        """测试从原始文本提取 JSON"""
        text = 'Some text {"key": "value"} more text'
        result = provider._extract_json(text)
        assert result == '{"key": "value"}'

    def test_parse_action(self, provider):
        """测试解析动作"""
        assert provider._parse_action("buy") == ActionType.BUY
        assert provider._parse_action("BUY") == ActionType.BUY
        assert provider._parse_action("sell") == ActionType.SELL
        assert provider._parse_action("hold") == ActionType.HOLD
        assert provider._parse_action("unknown") == ActionType.HOLD

    def test_parse_risk_level(self, provider):
        """测试解析风险等级"""
        assert provider._parse_risk_level("low") == RiskLevel.LOW
        assert provider._parse_risk_level("medium") == RiskLevel.MEDIUM
        assert provider._parse_risk_level("high") == RiskLevel.HIGH
        assert provider._parse_risk_level("unknown") == RiskLevel.MEDIUM

    def test_format_indicators(self, provider):
        """测试格式化指标"""
        indicators = {
            "rsi": 65.5,
            "macd": 150.12345,
            "signal": "buy"
        }
        result = provider._format_indicators(indicators)

        assert "rsi: 65.5000" in result
        assert "macd: 150.1235" in result
        assert "signal: buy" in result

    def test_format_price_history(self, provider):
        """测试格式化价格历史"""
        prices = [49000, 49500, 50000]
        result = provider._format_price_history(prices)

        assert "49000.00" in result
        assert "49500.00" in result
        assert "50000.00" in result

    def test_format_price_history_truncate(self, provider):
        """测试价格历史截断"""
        prices = list(range(40000, 50000, 100))  # 100个价格点
        result = provider._format_price_history(prices)

        # 只保留最近10个
        parts = result.split(", ")
        assert len(parts) <= 10

    def test_create_fallback_decision(self, provider, market_context):
        """测试创建后备决策"""
        decision = provider._create_fallback_decision(market_context, "Test error")

        assert decision.action == ActionType.HOLD
        assert decision.confidence == 0.0
        assert decision.metadata.get("fallback") is True
        assert "Test error" in decision.metadata.get("error", "")


# ==================== 证据链测试 ====================


class TestEvidenceChain:
    """测试证据链解析"""

    @pytest.mark.asyncio
    async def test_evidence_chain_parsing(self, provider, market_context):
        """测试证据链解析"""
        mock_response = MagicMock()
        mock_response.content = [
            MagicMock(text=json.dumps({
                "action": "buy",
                "confidence": 0.8,
                "reasoning": "多重证据支持",
                "risk_level": "medium",
                "evidence_chain": [
                    {
                        "source": "technical",
                        "metric": "rsi",
                        "value": 65,
                        "weight": 0.8,
                        "confidence": 0.9,
                        "description": "RSI 有上涨空间"
                    },
                    {
                        "source": "fundamental",
                        "metric": "market_cap",
                        "value": "900B",
                        "weight": 0.6,
                        "confidence": 0.7,
                        "description": "市值稳定"
                    },
                    {
                        "source": "sentiment",
                        "metric": "news",
                        "value": 0.6,
                        "weight": 0.5,
                        "confidence": 0.6,
                        "description": "新闻情绪偏正面"
                    }
                ]
            }))
        ]

        with patch.object(provider._client.messages, 'create', new_callable=AsyncMock) as mock_create:
            mock_create.return_value = mock_response

            decision = await provider.analyze(market_context)

            chain = decision.evidence_chain
            assert len(chain.evidences) == 3

            # 检查证据链方法
            assert chain.get_total_weight() > 0

            # 按来源筛选
            technical = chain.get_by_source("technical")
            assert len(technical) == 1
            assert technical[0].metric == "rsi"


# ==================== 集成测试 ====================


class TestClaudeProviderIntegration:
    """集成测试（需要真实 API Key）"""

    @pytest.mark.skip(reason="需要真实 API Key")
    @pytest.mark.asyncio
    async def test_real_analyze(self):
        """真实 API 测试"""
        import os

        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            pytest.skip("需要设置 ANTHROPIC_API_KEY 环境变量")

        provider = ClaudeProvider(api_key=api_key)
        provider.initialize()

        context = MarketContext(
            symbol="BTCUSDT",
            current_price=50000.0,
            price_history=[49000, 49500, 50000],
            indicators={"rsi": 65.0},
        )

        decision = await provider.analyze(context)

        assert decision.action in [ActionType.BUY, ActionType.SELL, ActionType.HOLD]
        assert 0.0 <= decision.confidence <= 1.0


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
