"""
OpenClaw Provider 单元测试

测试范围：
- 初始化与配置
- analyze 方法（正常调用、错误处理、超时）
- health_check 方法
- 响应解析
- 边界条件
"""
import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
import pytest

from src.ai.provider.base import (
    ActionType,
    Evidence,
    EvidenceChain,
    MarketContext,
    RiskLevel,
)
from src.ai.provider.openclaw import (
    OpenClawAPIError,
    OpenClawProvider,
    OpenClawProviderError,
    OpenClawTimeoutError,
)


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def sample_market_context():
    """创建示例市场上下文"""
    return MarketContext(
        symbol="BTC/USDT",
        current_price=50000.0,
        price_history=[48000.0, 49000.0, 50000.0],
        volume_24h=1000000000.0,
        indicators={"rsi": 65.0, "macd": 0.5},
        news_sentiment=0.7,
        timestamp=datetime.now(),
    )


@pytest.fixture
def sample_analyze_response():
    """创建示例分析响应数据"""
    return {
        "action": "buy",
        "confidence": 0.85,
        "reasoning": "技术指标和情绪分析均支持做多",
        "evidence_chain": [
            {
                "source": "technical",
                "metric": "rsi",
                "value": 65.0,
                "weight": 1.0,
                "confidence": 0.9,
                "description": "RSI 处于中等偏强区域",
            },
            {
                "source": "sentiment",
                "metric": "news_sentiment",
                "value": 0.7,
                "weight": 0.8,
                "confidence": 0.85,
                "description": "新闻情绪偏向积极",
            },
        ],
        "suggested_amount": 1000.0,
        "stop_loss_pct": 0.02,
        "take_profit_pct": 0.06,
        "risk_level": "medium",
        "metadata": {"model": "openclaw-v1"},
    }


@pytest.fixture
def mock_session():
    """创建模拟 aiohttp session"""
    session = AsyncMock(spec=aiohttp.ClientSession)
    return session


# =============================================================================
# 初始化测试
# =============================================================================


class TestOpenClawProviderInit:
    """测试 OpenClawProvider 初始化"""

    def test_init_with_required_params(self):
        """测试使用必需参数初始化"""
        provider = OpenClawProvider(endpoint="http://localhost:8080")

        assert provider.endpoint == "http://localhost:8080"
        assert provider.api_key is None
        assert provider.timeout == 30.0
        assert provider.name == "openclaw"

    def test_init_with_all_params(self):
        """测试使用所有参数初始化"""
        provider = OpenClawProvider(
            endpoint="http://api.openclaw.ai/",
            api_key="test-api-key",
            timeout=60.0,
            config={"retry_count": 3},
        )

        assert provider.endpoint == "http://api.openclaw.ai"
        assert provider.api_key == "test-api-key"
        assert provider.timeout == 60.0
        assert provider.config == {"retry_count": 3}

    def test_endpoint_trailing_slash_removed(self):
        """测试端点 URL 的尾部斜杠被移除"""
        provider = OpenClawProvider(endpoint="http://localhost:8080/")
        assert provider.endpoint == "http://localhost:8080"

    def test_get_default_headers_without_api_key(self):
        """测试无 API 密钥时的默认头"""
        provider = OpenClawProvider(endpoint="http://localhost:8080")
        headers = provider._get_default_headers()

        assert headers["Content-Type"] == "application/json"
        assert headers["Accept"] == "application/json"
        assert "User-Agent" in headers
        assert "Authorization" not in headers

    def test_get_default_headers_with_api_key(self):
        """测试有 API 密钥时的默认头"""
        provider = OpenClawProvider(
            endpoint="http://localhost:8080",
            api_key="secret-key",
        )
        headers = provider._get_default_headers()

        assert headers["Authorization"] == "Bearer secret-key"


# =============================================================================
# analyze 方法测试
# =============================================================================


class TestOpenClawProviderAnalyze:
    """测试 OpenClawProvider.analyze 方法"""

    @pytest.mark.asyncio
    async def test_analyze_success(self, sample_market_context, sample_analyze_response):
        """测试成功的分析调用"""
        provider = OpenClawProvider(endpoint="http://localhost:8080")
        provider._initialized = True

        # Mock _make_request
        provider._make_request = AsyncMock(return_value=sample_analyze_response)

        result = await provider.analyze(sample_market_context)

        assert isinstance(result, EvidenceBasedDecision)
        assert result.action == ActionType.BUY
        assert result.confidence == 0.85
        assert result.reasoning == "技术指标和情绪分析均支持做多"
        assert isinstance(result.evidence_chain, EvidenceChain)
        assert len(result.evidence_chain.evidences) == 2
        assert result.risk_level == RiskLevel.MEDIUM

        # 验证调用参数
        provider._make_request.assert_called_once()
        call_args = provider._make_request.call_args
        assert call_args.kwargs["method"] == "POST"
        assert call_args.kwargs["path"] == "/api/analyze"

    @pytest.mark.asyncio
    async def test_analyze_not_initialized(self, sample_market_context):
        """测试未初始化时调用 analyze"""
        provider = OpenClawProvider(endpoint="http://localhost:8080")

        with pytest.raises(OpenClawProviderError) as exc_info:
            await provider.analyze(sample_market_context)

        assert "未初始化" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_analyze_api_error(self, sample_market_context):
        """测试 API 错误处理"""
        provider = OpenClawProvider(endpoint="http://localhost:8080")
        provider._initialized = True

        # Mock _make_request 抛出 API 错误
        error = OpenClawAPIError("Internal Server Error", status_code=500)
        provider._make_request = AsyncMock(side_effect=error)

        with pytest.raises(OpenClawAPIError):
            await provider.analyze(sample_market_context)

    @pytest.mark.asyncio
    async def test_analyze_timeout(self, sample_market_context):
        """测试超时处理"""
        provider = OpenClawProvider(endpoint="http://localhost:8080")
        provider._initialized = True

        # Mock _make_request 抛出超时错误
        provider._make_request = AsyncMock(
            side_effect=OpenClawTimeoutError("Request timeout")
        )

        with pytest.raises(OpenClawTimeoutError):
            await provider.analyze(sample_market_context)


# =============================================================================
# 响应解析测试
# =============================================================================


class TestOpenClawProviderParseResponse:
    """测试响应解析逻辑"""

    def test_parse_decision_response_complete(self):
        """测试完整响应解析"""
        provider = OpenClawProvider(endpoint="http://localhost:8080")

        response_data = {
            "action": "sell",
            "confidence": 0.75,
            "reasoning": "技术回调信号",
            "evidence_chain": [
                {
                    "source": "technical",
                    "metric": "rsi",
                    "value": 75.0,
                    "weight": 1.0,
                    "confidence": 0.8,
                    "description": "RSI 超买",
                }
            ],
            "suggested_amount": 500.0,
            "stop_loss_pct": 0.03,
            "take_profit_pct": 0.04,
            "risk_level": "high",
            "metadata": {"model": "v2"},
        }

        decision = provider._parse_decision_response(response_data)

        assert decision.action == ActionType.SELL
        assert decision.confidence == 0.75
        assert decision.reasoning == "技术回调信号"
        assert decision.risk_level == RiskLevel.HIGH
        assert len(decision.evidence_chain.evidences) == 1

        evidence = decision.evidence_chain.evidences[0]
        assert evidence.source == "technical"
        assert evidence.metric == "rsi"
        assert evidence.value == 75.0

    def test_parse_decision_response_minimal(self):
        """测试最小响应解析"""
        provider = OpenClawProvider(endpoint="http://localhost:8080")

        response_data = {
            "action": "hold",
            "confidence": 0.5,
            "reasoning": "观望",
            "evidence_chain": [],
        }

        decision = provider._parse_decision_response(response_data)

        assert decision.action == ActionType.HOLD
        assert decision.confidence == 0.5
        assert decision.risk_level == RiskLevel.MEDIUM  # 默认值
        assert len(decision.evidence_chain.evidences) == 0

    def test_parse_decision_response_invalid_action(self):
        """测试无效动作类型处理"""
        provider = OpenClawProvider(endpoint="http://localhost:8080")

        response_data = {
            "action": "invalid_action",
            "confidence": 0.5,
            "reasoning": "test",
            "evidence_chain": [],
        }

        decision = provider._parse_decision_response(response_data)

        # 无效动作应默认转为 HOLD
        assert decision.action == ActionType.HOLD


# =============================================================================
# health_check 测试
# =============================================================================


class TestOpenClawProviderHealthCheck:
    """测试健康检查功能"""

    @pytest.mark.asyncio
    async def test_health_check_success(self):
        """测试健康检查成功"""
        provider = OpenClawProvider(endpoint="http://localhost:8080")

        # Mock _make_request 返回成功响应
        provider._make_request = AsyncMock(return_value={"status": "ok"})

        result = await provider.health_check()

        assert result is True
        provider._make_request.assert_called_once_with(method="GET", path="/api/ping")

    @pytest.mark.asyncio
    async def test_health_check_pong_response(self):
        """测试 pong 响应也视为健康"""
        provider = OpenClawProvider(endpoint="http://localhost:8080")

        provider._make_request = AsyncMock(return_value={"message": "pong"})

        result = await provider.health_check()

        assert result is True

    @pytest.mark.asyncio
    async def test_health_check_timeout(self):
        """测试健康检查超时"""
        provider = OpenClawProvider(endpoint="http://localhost:8080")

        provider._make_request = AsyncMock(side_effect=OpenClawTimeoutError("timeout"))

        result = await provider.health_check()

        assert result is False

    @pytest.mark.asyncio
    async def test_health_check_api_error(self):
        """测试健康检查 API 错误"""
        provider = OpenClawProvider(endpoint="http://localhost:8080")

        provider._make_request = AsyncMock(
            side_effect=OpenClawAPIError("server error", status_code=500)
        )

        result = await provider.health_check()

        assert result is False


# =============================================================================
# _make_request 测试
# =============================================================================


class TestOpenClawProviderMakeRequest:
    """测试 _make_request 方法"""

    @pytest.mark.asyncio
    async def test_make_request_success(self):
        """测试成功请求"""
        provider = OpenClawProvider(endpoint="http://localhost:8080")
        provider._initialized = True

        # Mock session 和 response
        mock_response = AsyncMock()
        mock_response.json = AsyncMock(return_value={"result": "success"})
        mock_response.status = 200

        mock_session = AsyncMock()
        mock_session.request = AsyncMock(return_value=mock_response)
        mock_session.closed = False

        provider._session = mock_session

        result = await provider._make_request("POST", "/api/test", data={"key": "value"})

        assert result == {"result": "success"}
        mock_session.request.assert_called_once()

    @pytest.mark.asyncio
    async def test_make_request_api_error(self):
        """测试 API 错误响应"""
        provider = OpenClawProvider(endpoint="http://localhost:8080")
        provider._initialized = True

        mock_response = AsyncMock()
        mock_response.json = AsyncMock(return_value={"error": "Internal Server Error"})
        mock_response.status = 500

        mock_session = AsyncMock()
        mock_session.request = AsyncMock(return_value=mock_response)
        mock_session.closed = False

        provider._session = mock_session

        with pytest.raises(OpenClawAPIError) as exc_info:
            await provider._make_request("GET", "/api/test")

        assert exc_info.value.status_code == 500
        assert exc_info.value.response_data == {"error": "Internal Server Error"}

    @pytest.mark.asyncio
    async def test_make_request_timeout(self):
        """测试请求超时"""
        provider = OpenClawProvider(endpoint="http://localhost:8080")
        provider._initialized = True

        mock_session = AsyncMock()
        mock_session.request = AsyncMock(side_effect=asyncio.TimeoutError())
        mock_session.closed = False

        provider._session = mock_session

        with pytest.raises(OpenClawTimeoutError):
            await provider._make_request("GET", "/api/test")

    @pytest.mark.asyncio
    async def test_make_request_client_error(self):
        """测试 HTTP 客户端错误"""
        provider = OpenClawProvider(endpoint="http://localhost:8080")
        provider._initialized = True

        mock_session = AsyncMock()
        mock_session.request = AsyncMock(
            side_effect=aiohttp.ClientError("Connection refused")
        )
        mock_session.closed = False

        provider._session = mock_session

        with pytest.raises(OpenClawAPIError) as exc_info:
            await provider._make_request("GET", "/api/test")

        assert "Connection refused" in str(exc_info.value)


# =============================================================================
# review 方法测试
# =============================================================================


class TestOpenClawProviderReview:
    """测试 review 方法"""

    @pytest.mark.asyncio
    async def test_review_not_implemented(self):
        """测试基础 provider 复盘方法返回未实现提示"""
        provider = OpenClawProvider(endpoint="http://localhost:8080")

        trade = TradeResult(
            symbol="BTC/USDT",
            action=ActionType.BUY,
            entry_price=50000.0,
            quantity=0.1,
        )

        result = await provider.review(trade)

        assert result.trade_id.startswith("BTC/USDT")
        assert "不支持复盘" in result.overall_assessment
        assert len(result.findings) == 1
        assert result.findings[0].category == "capability"


# =============================================================================
# close 方法测试
# =============================================================================


class TestOpenClawProviderClose:
    """测试 close 方法"""

    @pytest.mark.asyncio
    async def test_close_session(self):
        """测试关闭 session"""
        provider = OpenClawProvider(endpoint="http://localhost:8080")

        # 创建一个 mock session
        mock_session = AsyncMock()
        mock_session.closed = False
        provider._session = mock_session

        await provider.close()

        mock_session.close.assert_called_once()
        assert provider._session is None

    @pytest.mark.asyncio
    async def test_close_already_closed(self):
        """测试关闭已经关闭的 session"""
        provider = OpenClawProvider(endpoint="http://localhost:8080")

        # 创建一个已经关闭的 mock session
        mock_session = AsyncMock()
        mock_session.closed = True
        provider._session = mock_session

        await provider.close()

        # 不应该调用 close
        mock_session.close.assert_not_called()


# =============================================================================
# 集成测试
# =============================================================================


class TestOpenClawProviderIntegration:
    """集成测试"""

    @pytest.mark.asyncio
    async def test_full_workflow(self, sample_market_context, sample_analyze_response):
        """测试完整工作流"""
        provider = OpenClawProvider(
            endpoint="http://localhost:8080",
            api_key="test-key",
        )

        # 初始化
        with patch.object(provider, "_do_initialize", return_value=True):
            result = provider.initialize()
            assert result is True

        # Mock analyze 请求
        with patch.object(provider, "_make_request", new_callable=AsyncMock) as mock_request:
            mock_request.return_value = sample_analyze_response

            decision = await provider.analyze(sample_market_context)

            assert decision.action == ActionType.BUY
            assert decision.confidence == 0.85

        # 健康检查
        with patch.object(provider, "_make_request", new_callable=AsyncMock) as mock_request:
            mock_request.return_value = {"status": "ok"}

            health = await provider.health_check()
            assert health is True

        # 关闭
        await provider.close()
