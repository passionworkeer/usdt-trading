"""
测试宏观大局观生成器（MacroOracle）
"""
import pytest
import json
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.ai.macro_oracle import MacroOracle, MacroState


class TestMacroState:
    """宏观状态数据类测试"""

    def test_macro_state_creation(self):
        """测试创建 MacroState"""
        state = MacroState(
            global_sentiment='panic',
            dominant_narrative='监管恐慌',
            trading_bans=['LONG'],
            recommended_stance='defensive',
            reasoning='SEC 对交易所采取行动',
            timestamp=datetime.now()
        )

        assert state.global_sentiment == 'panic'
        assert state.dominant_narrative == '监管恐慌'
        assert state.trading_bans == ['LONG']
        assert state.recommended_stance == 'defensive'
        assert state.reasoning == 'SEC 对交易所采取行动'

    def test_macro_state_defaults(self):
        """测试 MacroState 默认值"""
        state = MacroState(
            global_sentiment='neutral',
            dominant_narrative='',
            trading_bans=[],
            recommended_stance='neutral',
            reasoning='',
            timestamp=datetime.now()
        )

        assert state.global_sentiment == 'neutral'
        assert state.trading_bans == []


class TestMacroOracle:
    """宏观大局观生成器测试"""

    @pytest.fixture
    def mock_decision_engine(self):
        """创建模拟决策引擎"""
        engine = MagicMock()
        engine.client = MagicMock()
        return engine

    @pytest.fixture
    def macro_oracle(self, mock_decision_engine):
        """创建 MacroOracle 实例"""
        return MacroOracle(mock_decision_engine)

    # ==================== 初始化测试 ====================

    def test_init(self, mock_decision_engine):
        """测试初始化"""
        oracle = MacroOracle(mock_decision_engine)

        assert oracle.engine == mock_decision_engine
        assert oracle.last_macro_state is None
        assert oracle.last_update_time is None
        assert oracle.update_interval == timedelta(hours=1)

    # ==================== generate_macro_state 测试 ====================

    @pytest.mark.asyncio
    async def test_generate_macro_state_basic(self, macro_oracle):
        """测试生成宏观状态 - 基本功能"""
        # 模拟 Claude 响应
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text=json.dumps({
            "global_sentiment": "panic",
            "dominant_narrative": "监管恐慌",
            "trading_bans": ["LONG"],
            "recommended_stance": "defensive",
            "reasoning": "SEC 对交易所采取行动"
        }))]

        macro_oracle.engine.client.messages.create = MagicMock(return_value=mock_response)

        intelligence = {
            'tweets': [{'text': 'Panic selling!', 'likes': 100}],
            'news': [{'title': 'SEC Action', 'source': 'CoinDesk'}]
        }

        result = await macro_oracle.generate_macro_state(intelligence)

        assert result.global_sentiment == 'panic'
        assert result.dominant_narrative == '监管恐慌'
        assert result.trading_bans == ['LONG']
        assert result.recommended_stance == 'defensive'

    @pytest.mark.asyncio
    async def test_generate_macro_state_no_client(self, macro_oracle):
        """测试生成宏观状态 - 客户端未初始化"""
        macro_oracle.engine.client = None

        intelligence = {'tweets': [], 'news': []}
        result = await macro_oracle.generate_macro_state(intelligence)

        assert result.global_sentiment == 'neutral'
        assert result.trading_bans == []

    @pytest.mark.asyncio
    async def test_generate_macro_state_skip_update(self, macro_oracle):
        """测试生成宏观状态 - 跳过更新（时间间隔不足）"""
        # 设置上次更新时间
        macro_oracle.last_update_time = datetime.now()
        macro_oracle.last_macro_state = MacroState(
            global_sentiment='panic',
            dominant_narrative='测试',
            trading_bans=[],
            recommended_stance='neutral',
            reasoning='测试',
            timestamp=datetime.now()
        )

        intelligence = {'tweets': [], 'news': []}
        result = await macro_oracle.generate_macro_state(intelligence)

        # 应该返回缓存的状态
        assert result.global_sentiment == 'panic'

    @pytest.mark.asyncio
    async def test_generate_macro_state_force_update(self, macro_oracle):
        """测试生成宏观状态 - 强制更新"""
        # 设置上次更新时间
        macro_oracle.last_update_time = datetime.now()
        macro_oracle.last_macro_state = MacroState(
            global_sentiment='panic',
            dominant_narrative='旧状态',
            trading_bans=[],
            recommended_stance='neutral',
            reasoning='旧',
            timestamp=datetime.now()
        )

        # 模拟 Claude 响应
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text=json.dumps({
            "global_sentiment": "euphoric",
            "dominant_narrative": "新状态",
            "trading_bans": [],
            "recommended_stance": "aggressive",
            "reasoning": "强制更新"
        }))]

        macro_oracle.engine.client.messages.create = MagicMock(return_value=mock_response)

        intelligence = {'tweets': [], 'news': []}
        result = await macro_oracle.generate_macro_state(intelligence, force_update=True)

        assert result.global_sentiment == 'euphoric'
        assert result.dominant_narrative == '新状态'

    @pytest.mark.asyncio
    async def test_generate_macro_state_json_decode_error(self, macro_oracle):
        """测试生成宏观状态 - JSON 解析错误"""
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="invalid json")]

        macro_oracle.engine.client.messages.create = MagicMock(return_value=mock_response)

        intelligence = {'tweets': [], 'news': []}
        result = await macro_oracle.generate_macro_state(intelligence)

        # 应该返回默认状态
        assert result.global_sentiment == 'neutral'

    @pytest.mark.asyncio
    async def test_generate_macro_state_api_error(self, macro_oracle):
        """测试生成宏观状态 - API 调用错误"""
        macro_oracle.engine.client.messages.create = MagicMock(
            side_effect=Exception("API Error")
        )

        intelligence = {'tweets': [], 'news': []}
        result = await macro_oracle.generate_macro_state(intelligence)

        assert result.global_sentiment == 'neutral'

    @pytest.mark.asyncio
    async def test_generate_macro_state_invalid_trading_bans(self, macro_oracle):
        """测试生成宏观状态 - 无效的交易禁令被过滤"""
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text=json.dumps({
            "global_sentiment": "neutral",
            "dominant_narrative": "测试",
            "trading_bans": ["LONG", "INVALID", "SHORT", "OTHER"],
            "recommended_stance": "neutral",
            "reasoning": "测试"
        }))]

        macro_oracle.engine.client.messages.create = MagicMock(return_value=mock_response)

        intelligence = {'tweets': [], 'news': []}
        result = await macro_oracle.generate_macro_state(intelligence)

        # 只保留有效的禁令
        assert 'LONG' in result.trading_bans
        assert 'SHORT' in result.trading_bans
        assert 'INVALID' not in result.trading_bans
        assert 'OTHER' not in result.trading_bans

    @pytest.mark.asyncio
    async def test_generate_macro_state_lowercase_bans(self, macro_oracle):
        """测试生成宏观状态 - 小写禁令被转换"""
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text=json.dumps({
            "global_sentiment": "neutral",
            "dominant_narrative": "测试",
            "trading_bans": ["long", "short"],
            "recommended_stance": "neutral",
            "reasoning": "测试"
        }))]

        macro_oracle.engine.client.messages.create = MagicMock(return_value=mock_response)

        intelligence = {'tweets': [], 'news': []}
        result = await macro_oracle.generate_macro_state(intelligence)

        assert 'LONG' in result.trading_bans
        assert 'SHORT' in result.trading_bans

    # ==================== _should_skip_update 测试 ====================

    def test_should_skip_update_no_previous(self, macro_oracle):
        """测试是否跳过更新 - 无上次更新"""
        assert macro_oracle._should_skip_update() is False

    def test_should_skip_update_recent(self, macro_oracle):
        """测试是否跳过更新 - 刚更新过"""
        macro_oracle.last_update_time = datetime.now()
        assert macro_oracle._should_skip_update() is True

    def test_should_skip_update_old(self, macro_oracle):
        """测试是否跳过更新 - 已过间隔"""
        macro_oracle.last_update_time = datetime.now() - timedelta(hours=2)
        assert macro_oracle._should_skip_update() is False

    # ==================== _build_macro_prompt 测试 ====================

    def test_build_macro_prompt_basic(self, macro_oracle):
        """测试构建宏观分析 prompt - 基本功能"""
        intelligence = {
            'tweets': [{'text': 'Test tweet', 'likes': 10}],
            'news': [{'title': 'Test news', 'source': 'Test'}]
        }

        prompt = macro_oracle._build_macro_prompt(intelligence)

        assert "Twitter 情绪" in prompt
        assert "宏观新闻" in prompt
        assert "Test tweet" in prompt
        assert "Test news" in prompt

    def test_build_macro_prompt_empty(self, macro_oracle):
        """测试构建宏观分析 prompt - 空数据"""
        intelligence = {'tweets': [], 'news': []}

        prompt = macro_oracle._build_macro_prompt(intelligence)

        assert "无数据" in prompt

    # ==================== _parse_response 测试 ====================

    def test_parse_response_json_block(self, macro_oracle):
        """测试解析响应 - JSON 代码块"""
        content = '''```json
{"global_sentiment": "panic", "dominant_narrative": "test", "trading_bans": [], "recommended_stance": "defensive", "reasoning": "test"}
```'''

        result = macro_oracle._parse_response(content)

        assert result['global_sentiment'] == 'panic'

    def test_parse_response_plain_json(self, macro_oracle):
        """测试解析响应 - 纯 JSON"""
        content = '{"global_sentiment": "neutral", "dominant_narrative": "test", "trading_bans": [], "recommended_stance": "neutral", "reasoning": "test"}'

        result = macro_oracle._parse_response(content)

        assert result['global_sentiment'] == 'neutral'

    def test_parse_response_invalid_sentiment(self, macro_oracle):
        """测试解析响应 - 无效情绪被重置"""
        content = '{"global_sentiment": "invalid", "dominant_narrative": "test", "trading_bans": [], "recommended_stance": "neutral", "reasoning": "test"}'

        result = macro_oracle._parse_response(content)

        assert result['global_sentiment'] == 'neutral'

    def test_parse_response_invalid_stance(self, macro_oracle):
        """测试解析响应 - 无效立场被重置"""
        content = '{"global_sentiment": "neutral", "dominant_narrative": "test", "trading_bans": [], "recommended_stance": "invalid", "reasoning": "test"}'

        result = macro_oracle._parse_response(content)

        assert result['recommended_stance'] == 'neutral'

    def test_parse_response_invalid_bans_not_list(self, macro_oracle):
        """测试解析响应 - 禁令不是列表"""
        content = '{"global_sentiment": "neutral", "dominant_narrative": "test", "trading_bans": "invalid", "recommended_stance": "neutral", "reasoning": "test"}'

        result = macro_oracle._parse_response(content)

        assert result['trading_bans'] == []

    # ==================== _get_default_state 测试 ====================

    def test_get_default_state(self, macro_oracle):
        """测试获取默认状态"""
        result = macro_oracle._get_default_state()

        assert result.global_sentiment == 'neutral'
        assert result.recommended_stance == 'neutral'
        assert result.trading_bans == []
        assert "暂无数据" in result.reasoning

    # ==================== get_cached_state 测试 ====================

    def test_get_cached_state_none(self, macro_oracle):
        """测试获取缓存状态 - 无缓存"""
        result = macro_oracle.get_cached_state()

        assert result is None

    def test_get_cached_state_exists(self, macro_oracle):
        """测试获取缓存状态 - 有缓存"""
        state = MacroState(
            global_sentiment='panic',
            dominant_narrative='test',
            trading_bans=[],
            recommended_stance='neutral',
            reasoning='test',
            timestamp=datetime.now()
        )
        macro_oracle.last_macro_state = state

        result = macro_oracle.get_cached_state()

        assert result.global_sentiment == 'panic'

    # ==================== is_trading_allowed 测试 ====================

    def test_is_trading_allowed_no_state(self, macro_oracle):
        """测试交易是否允许 - 无状态"""
        result = macro_oracle.is_trading_allowed('LONG')

        assert result is True

    def test_is_trading_allowed_no_ban(self, macro_oracle):
        """测试交易是否允许 - 无禁令"""
        macro_oracle.last_macro_state = MacroState(
            global_sentiment='neutral',
            dominant_narrative='test',
            trading_bans=[],
            recommended_stance='neutral',
            reasoning='test',
            timestamp=datetime.now()
        )

        result = macro_oracle.is_trading_allowed('LONG')

        assert result is True

    def test_is_trading_allowed_with_ban(self, macro_oracle):
        """测试交易是否允许 - 有禁令"""
        macro_oracle.last_macro_state = MacroState(
            global_sentiment='panic',
            dominant_narrative='test',
            trading_bans=['LONG'],
            recommended_stance='defensive',
            reasoning='test',
            timestamp=datetime.now()
        )

        result = macro_oracle.is_trading_allowed('LONG')

        assert result is False

    def test_is_trading_allowed_other_direction(self, macro_oracle):
        """测试交易是否允许 - 其他方向"""
        macro_oracle.last_macro_state = MacroState(
            global_sentiment='panic',
            dominant_narrative='test',
            trading_bans=['LONG'],
            recommended_stance='defensive',
            reasoning='test',
            timestamp=datetime.now()
        )

        result = macro_oracle.is_trading_allowed('SHORT')

        assert result is True

    def test_is_trading_allowed_lowercase(self, macro_oracle):
        """测试交易是否允许 - 小写方向"""
        macro_oracle.last_macro_state = MacroState(
            global_sentiment='panic',
            dominant_narrative='test',
            trading_bans=['LONG'],
            recommended_stance='defensive',
            reasoning='test',
            timestamp=datetime.now()
        )

        result = macro_oracle.is_trading_allowed('long')

        assert result is False


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
