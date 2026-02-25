"""
证据链风控控制器单元测试
"""
import pytest
from src.risk.evidence_controller import (
    EvidenceBasedDecision,
    EvidenceBasedRiskController,
    ActionType,
    ValidationResult,
)


class TestEvidenceBasedDecision:
    """测试决策数据类"""

    def test_create_decision(self):
        """测试创建决策对象"""
        decision = EvidenceBasedDecision(
            action="long",
            evidence_count=3,
            evidence_chain=["趋势向上", "成交量放大", "突破阻力位"],
            veto_flag=False,
            entry_price=50000.0,
            stop_loss=48000.0,
            take_profit=55000.0,
            position_size=1000.0,
            symbol="BTC/USDT"
        )

        assert decision.action == "long"
        assert decision.evidence_count == 3
        assert len(decision.evidence_chain) == 3
        assert decision.veto_flag is False
        assert decision.entry_price == 50000.0

    def test_auto_fix_evidence_count(self):
        """测试自动修正证据数量"""
        decision = EvidenceBasedDecision(
            action="long",
            evidence_count=5,  # 故意设置错误
            evidence_chain=["趋势向上", "成交量放大"],  # 实际只有2个
            veto_flag=False,
            entry_price=50000.0,
            stop_loss=48000.0,
            take_profit=55000.0,
            position_size=1000.0
        )

        # __post_init__ 应该自动修正
        assert decision.evidence_count == 2

    def test_optional_fields(self):
        """测试可选字段"""
        decision = EvidenceBasedDecision(
            action="hold",
            evidence_count=1,
            evidence_chain=["市场不明朗"],
            veto_flag=False,
            entry_price=0.0,
            stop_loss=0.0,
            take_profit=0.0,
            position_size=0.0
        )

        assert decision.symbol is None
        assert decision.metadata == {}


class TestEvidenceBasedRiskController:
    """测试证据链风控控制器"""

    @pytest.fixture
    def controller(self):
        """创建控制器实例"""
        return EvidenceBasedRiskController(
            min_evidence_count=2,
            max_evidence_count=5,
            allow_veto_override=False
        )

    @pytest.fixture
    def valid_long_decision(self):
        """有效的做多决策"""
        return EvidenceBasedDecision(
            action="long",
            evidence_count=3,
            evidence_chain=["趋势向上", "成交量放大", "突破阻力位"],
            veto_flag=False,
            entry_price=50000.0,
            stop_loss=48000.0,
            take_profit=55000.0,
            position_size=1000.0,
            symbol="BTC/USDT"
        )

    @pytest.fixture
    def valid_short_decision(self):
        """有效的做空决策"""
        return EvidenceBasedDecision(
            action="short",
            evidence_count=3,
            evidence_chain=["趋势向下", "成交量放大", "跌破支撑位"],
            veto_flag=False,
            entry_price=50000.0,
            stop_loss=52000.0,
            take_profit=45000.0,
            position_size=1000.0,
            symbol="BTC/USDT"
        )

    def test_validate_pass(self, controller, valid_long_decision):
        """测试验证通过"""
        passed, reason = controller.validate(valid_long_decision)
        assert passed is True
        assert reason == "通过"

    def test_validate_insufficient_evidence(self, controller):
        """测试证据不足"""
        decision = EvidenceBasedDecision(
            action="long",
            evidence_count=1,
            evidence_chain=["趋势向上"],
            veto_flag=False,
            entry_price=50000.0,
            stop_loss=48000.0,
            take_profit=55000.0,
            position_size=1000.0
        )
        passed, reason = controller.validate(decision)
        assert passed is False
        assert "证据不足" in reason

    def test_validate_too_many_evidence(self, controller):
        """测试证据过多"""
        decision = EvidenceBasedDecision(
            action="long",
            evidence_count=6,
            evidence_chain=[f"证据{i}" for i in range(6)],
            veto_flag=False,
            entry_price=50000.0,
            stop_loss=48000.0,
            take_profit=55000.0,
            position_size=1000.0
        )
        passed, reason = controller.validate(decision)
        assert passed is False
        assert "证据过多" in reason

    def test_validate_veto_flag(self, controller):
        """测试否决标记"""
        decision = EvidenceBasedDecision(
            action="long",
            evidence_count=3,
            evidence_chain=["趋势向上", "成交量放大", "突破阻力位"],
            veto_flag=True,  # 存在否决标记
            entry_price=50000.0,
            stop_loss=48000.0,
            take_profit=55000.0,
            position_size=1000.0
        )
        passed, reason = controller.validate(decision)
        assert passed is False
        assert "否决" in reason

    def test_validate_long_price_logic(self, controller):
        """测试做多价格逻辑验证"""
        # 错误的做多：止损 > 入场
        decision = EvidenceBasedDecision(
            action="long",
            evidence_count=3,
            evidence_chain=["趋势向上", "成交量放大", "突破阻力位"],
            veto_flag=False,
            entry_price=50000.0,
            stop_loss=52000.0,  # 错误：止损高于入场
            take_profit=55000.0,
            position_size=1000.0
        )
        passed, reason = controller.validate(decision)
        assert passed is False
        assert "价格逻辑错误" in reason or "止损" in reason

    def test_validate_short_price_logic(self, controller, valid_short_decision):
        """测试做空价格逻辑验证"""
        passed, reason = controller.validate(valid_short_decision)
        assert passed is True

        # 错误的做空：止盈 > 入场
        bad_decision = EvidenceBasedDecision(
            action="short",
            evidence_count=3,
            evidence_chain=["趋势向下", "成交量放大", "跌破支撑位"],
            veto_flag=False,
            entry_price=50000.0,
            stop_loss=52000.0,
            take_profit=52000.0,  # 错误：止盈高于入场
            position_size=1000.0
        )
        passed, reason = controller.validate(bad_decision)
        assert passed is False

    def test_validate_position_size(self, controller):
        """测试仓位大小验证"""
        decision = EvidenceBasedDecision(
            action="long",
            evidence_count=3,
            evidence_chain=["趋势向上", "成交量放大", "突破阻力位"],
            veto_flag=False,
            entry_price=50000.0,
            stop_loss=48000.0,
            take_profit=55000.0,
            position_size=-1000.0  # 错误：负数仓位
        )
        passed, reason = controller.validate(decision)
        assert passed is False
        assert "仓位" in reason or "正数" in reason

    def test_validate_close_action(self, controller):
        """测试平仓动作验证"""
        decision = EvidenceBasedDecision(
            action="close",
            evidence_count=2,
            evidence_chain=["触及止损", "趋势反转"],
            veto_flag=False,
            entry_price=0.0,  # close 不需要价格
            stop_loss=0.0,
            take_profit=0.0,
            position_size=0.0
        )
        passed, reason = controller.validate(decision)
        assert passed is True

    def test_build_prompt_for_ai(self, controller, valid_long_decision):
        """测试生成 AI 提示词"""
        prompt = controller.build_prompt_for_ai(valid_long_decision)

        assert "证据链风控验证请求" in prompt
        assert valid_long_decision.action in prompt
        assert str(valid_long_decision.entry_price) in prompt
        assert "趋势向上" in prompt
        assert "验证规则" in prompt

    def test_stats_tracking(self, controller, valid_long_decision):
        """测试统计追踪"""
        # 初始状态
        stats = controller.get_stats()
        assert stats['stats']['total_validated'] == 0
        assert stats['stats']['passed'] == 0

        # 验证通过
        controller.validate(valid_long_decision)
        stats = controller.get_stats()
        assert stats['stats']['total_validated'] == 1
        assert stats['stats']['passed'] == 1
        assert stats['pass_rate'] == 100.0

    def test_rejection_reasons_tracking(self, controller):
        """测试拒绝原因追踪"""
        # 创建一个必然被拒绝的决策
        bad_decision = EvidenceBasedDecision(
            action="long",
            evidence_count=0,  # 证据不足
            evidence_chain=[],
            veto_flag=False,
            entry_price=50000.0,
            stop_loss=48000.0,
            take_profit=55000.0,
            position_size=1000.0
        )

        controller.validate(bad_decision)
        stats = controller.get_stats()

        assert stats['stats']['rejected'] == 1
        assert '证据不足' in str(stats['stats']['rejection_reasons'])

    def test_reset_stats(self, controller, valid_long_decision):
        """测试重置统计"""
        controller.validate(valid_long_decision)
        controller.reset_stats()

        stats = controller.get_stats()
        assert stats['stats']['total_validated'] == 0
        assert stats['stats']['passed'] == 0
        assert stats['stats']['rejected'] == 0

    def test_veto_override(self):
        """测试否决标记覆盖"""
        controller = EvidenceBasedRiskController(
            allow_veto_override=True
        )

        decision = EvidenceBasedDecision(
            action="long",
            evidence_count=3,
            evidence_chain=["趋势向上", "成交量放大", "突破阻力位"],
            veto_flag=True,  # 存在否决标记
            entry_price=50000.0,
            stop_loss=48000.0,
            take_profit=55000.0,
            position_size=1000.0
        )

        # 允许覆盖否决标记时，应该通过
        passed, reason = controller.validate(decision)
        assert passed is True


class TestEdgeCases:
    """测试边界情况"""

    def test_zero_prices(self):
        """测试零价格"""
        controller = EvidenceBasedRiskController()

        decision = EvidenceBasedDecision(
            action="long",
            evidence_count=2,
            evidence_chain=["趋势向上", "成交量放大"],
            veto_flag=False,
            entry_price=0.0,
            stop_loss=0.0,
            take_profit=0.0,
            position_size=1000.0
        )

        passed, reason = controller.validate(decision)
        assert passed is False

    def test_equal_prices_long(self):
        """测试相等价格（做多）"""
        controller = EvidenceBasedRiskController()

        # 止损等于入场价
        decision = EvidenceBasedDecision(
            action="long",
            evidence_count=2,
            evidence_chain=["趋势向上", "成交量放大"],
            veto_flag=False,
            entry_price=50000.0,
            stop_loss=50000.0,  # 等于入场价
            take_profit=55000.0,
            position_size=1000.0
        )

        passed, reason = controller.validate(decision)
        assert passed is False

    def test_very_small_position(self):
        """测试极小仓位"""
        controller = EvidenceBasedRiskController()

        decision = EvidenceBasedDecision(
            action="long",
            evidence_count=2,
            evidence_chain=["趋势向上", "成交量放大"],
            veto_flag=False,
            entry_price=50000.0,
            stop_loss=48000.0,
            take_profit=55000.0,
            position_size=0.0001  # 极小仓位
        )

        # 只要是正数就应该通过
        passed, reason = controller.validate(decision)
        assert passed is True

    def test_exact_min_evidence(self):
        """测试刚好满足最小证据数"""
        controller = EvidenceBasedRiskController(min_evidence_count=2)

        decision = EvidenceBasedDecision(
            action="long",
            evidence_count=2,
            evidence_chain=["趋势向上", "成交量放大"],
            veto_flag=False,
            entry_price=50000.0,
            stop_loss=48000.0,
            take_profit=55000.0,
            position_size=1000.0
        )

        passed, reason = controller.validate(decision)
        assert passed is True

    def test_exact_max_evidence(self):
        """测试刚好达到最大证据数"""
        controller = EvidenceBasedRiskController(min_evidence_count=2, max_evidence_count=3)

        decision = EvidenceBasedDecision(
            action="long",
            evidence_count=3,
            evidence_chain=["趋势向上", "成交量放大", "突破阻力位"],
            veto_flag=False,
            entry_price=50000.0,
            stop_loss=48000.0,
            take_profit=55000.0,
            position_size=1000.0
        )

        passed, reason = controller.validate(decision)
        assert passed is True


class TestBuildPrompt:
    """测试生成 AI 提示词"""

    @pytest.fixture
    def controller(self):
        return EvidenceBasedRiskController()

    @pytest.fixture
    def sample_decision(self):
        return EvidenceBasedDecision(
            action="long",
            evidence_count=3,
            evidence_chain=["趋势向上", "成交量放大", "突破阻力位"],
            veto_flag=False,
            entry_price=50000.0,
            stop_loss=48000.0,
            take_profit=55000.0,
            position_size=1000.0,
            symbol="BTC/USDT",
            metadata={"confidence": 0.85, "source": "AI模型"}
        )

    def test_prompt_contains_key_info(self, controller, sample_decision):
        """测试提示词包含关键信息"""
        prompt = controller.build_prompt_for_ai(sample_decision)

        assert "证据链风控验证请求" in prompt
        assert sample_decision.action in prompt
        assert sample_decision.symbol in prompt
        assert str(sample_decision.entry_price) in prompt
        assert "趋势向上" in prompt
        assert "成交量放大" in prompt
        assert "突破阻力位" in prompt

    def test_prompt_contains_rules(self, controller, sample_decision):
        """测试提示词包含验证规则"""
        prompt = controller.build_prompt_for_ai(sample_decision)

        assert "验证规则" in prompt
        assert "证据数量" in prompt
        assert "否决标记" in prompt
        assert "价格参数" in prompt

    def test_prompt_structure(self, controller, sample_decision):
        """测试提示词结构完整性"""
        prompt = controller.build_prompt_for_ai(sample_decision)

        # 检查分隔符
        assert "=" * 60 in prompt

        # 检查各部分标题
        sections = ["决策信息", "价格参数", "证据链", "风控配置", "验证规则"]
        for section in sections:
            assert section in prompt, f"缺少章节: {section}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
