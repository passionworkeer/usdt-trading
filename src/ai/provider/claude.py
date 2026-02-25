"""
Claude AI Provider

实现基于 Anthropic Claude API 的 AI Provider。
支持证据链分析和结构化决策输出。
"""
import json
import logging
import os
from typing import Any, Dict, List, Optional

import anthropic

from .base import (
    AIBaseProvider,
    MarketContext,
    EvidenceBasedDecision,
    TradeResult,
    ReviewReport,
    ActionType,
    RiskLevel,
    Evidence,
    EvidenceChain,
    ReviewFinding,
)


logger = logging.getLogger(__name__)


# Claude 模型常量
DEFAULT_MODEL = "claude-sonnet-4-6"
MAX_TOKENS = 4096


class ClaudeProvider(AIBaseProvider):
    """
    Claude AI Provider

    使用 Anthropic Claude API 进行市场分析和交易决策。
    返回结构化的证据链决策。
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        初始化 Claude Provider

        Args:
            config: Provider 配置，支持以下键：
                - api_key: Anthropic API Key（可从环境变量读取）
                - model: Claude 模型名称，默认 claude-sonnet-4-6
        """
        super().__init__(config)

        self._api_key = self._config.get("api_key") or os.environ.get("ANTHROPIC_API_KEY")
        self._model = self._config.get("model", DEFAULT_MODEL)
        self._client: Optional[anthropic.AsyncAnthropic] = None

    @property
    def name(self) -> str:
        """Provider 名称"""
        return "claude"

    @property
    def version(self) -> str:
        """Provider 版本"""
        return "1.0.0"

    def _do_initialize(self) -> bool:
        """
        初始化 Claude 客户端

        Returns:
            是否成功
        """
        if not self._api_key:
            self._set_error("缺少 API Key: 请设置 ANTHROPIC_API_KEY 环境变量或传入 api_key 参数")
            return False

        try:
            self._client = anthropic.AsyncAnthropic(api_key=self._api_key)
            logger.info(f"Claude Provider 初始化成功 (model: {self._model})")
            return True

        except Exception as e:
            self._set_error(f"初始化失败: {str(e)}")
            return False

    async def analyze(self, context: MarketContext) -> EvidenceBasedDecision:
        """
        分析市场并返回基于证据的决策

        Args:
            context: 市场上下文数据

        Returns:
            EvidenceBasedDecision: 基于证据的决策

        Raises:
            RuntimeError: API 调用失败
        """
        if not self._client:
            raise RuntimeError("Provider 未初始化")

        try:
            prompt = self._build_analysis_prompt(context)
            response = await self._client.messages.create(
                model=self._model,
                max_tokens=MAX_TOKENS,
                messages=[{"role": "user", "content": prompt}],
            )

            response_text = response.content[0].text
            return self._parse_analysis_response(response_text, context)

        except anthropic.APIError as e:
            logger.error(f"Claude API 错误: {e}")
            raise RuntimeError(f"Claude API 调用失败: {str(e)}")

        except Exception as e:
            logger.error(f"分析失败: {e}")
            raise

    async def review(self, trade: TradeResult) -> ReviewReport:
        """
        复盘交易

        Args:
            trade: 交易结果

        Returns:
            ReviewReport: 复盘报告
        """
        if not self._client:
            raise RuntimeError("Provider 未初始化")

        try:
            prompt = self._build_review_prompt(trade)
            response = await self._client.messages.create(
                model=self._model,
                max_tokens=MAX_TOKENS,
                messages=[{"role": "user", "content": prompt}],
            )

            response_text = response.content[0].text
            return self._parse_review_response(response_text, trade)

        except anthropic.APIError as e:
            logger.error(f"Claude API 错误: {e}")
            raise RuntimeError(f"Claude API 调用失败: {str(e)}")

        except Exception as e:
            logger.error(f"复盘失败: {e}")
            raise

    async def health_check(self) -> bool:
        """
        健康检查

        Returns:
            是否健康
        """
        if not self._client or not self._api_key:
            return False

        try:
            # 发送简单请求验证 API 可用性
            response = await self._client.messages.create(
                model=self._model,
                max_tokens=10,
                messages=[{"role": "user", "content": "ping"}],
            )
            return len(response.content) > 0

        except Exception as e:
            logger.warning(f"健康检查失败: {e}")
            return False

    def get_capabilities(self) -> Dict[str, Any]:
        """获取 Provider 能力"""
        return {
            "name": self.name,
            "version": self.version,
            "model": self._model,
            "supports_streaming": False,
            "supports_batch": False,
            "max_context_length": 200000,  # Claude 支持长上下文
        }

    # ==================== 私有方法 ====================

    def _build_analysis_prompt(self, context: MarketContext) -> str:
        """
        构建分析提示词

        Args:
            context: 市场上下文

        Returns:
            提示词字符串
        """
        indicators_str = self._format_indicators(context.indicators)
        price_history_str = self._format_price_history(context.price_history)

        return f"""你是一个专业的加密货币交易分析师。请基于以下市场数据进行分析并给出交易决策。

## 市场数据
- 交易对: {context.symbol}
- 当前价格: {context.current_price}
- 24小时成交量: {context.volume_24h or 'N/A'}
- 市值: {context.market_cap or 'N/A'}
- 新闻情绪: {context.news_sentiment or 'N/A'}

## 价格历史（最近10个数据点）
{price_history_str}

## 技术指标
{indicators_str}

## 分析要求

请按照以下 JSON 格式输出你的分析和决策：

```json
{{
  "action": "buy|sell|hold",
  "confidence": 0.0-1.0,
  "reasoning": "主要分析理由的简短总结",
  "risk_level": "low|medium|high",
  "evidence_chain": [
    {{
      "source": "technical|fundamental|sentiment|onchain",
      "metric": "指标名称",
      "value": "指标值",
      "weight": 0.0-1.0,
      "confidence": 0.0-1.0,
      "description": "证据描述"
    }}
  ],
  "suggested_amount": 建议交易金额（可选）,
  "stop_loss_pct": 止损百分比（可选，如 2.0 表示 2%）,
  "take_profit_pct": 止盈百分比（可选）
}}
```

### 证据链要求：
1. 至少提供 3 条证据
2. 每条证据必须有明确的来源、指标和描述
3. 权重和置信度要客观反映证据的重要性
4. 证据应涵盖技术面、基本面和情绪面

### 决策标准：
- action: buy（买入）、sell（卖出）或 hold（观望）
- confidence: 0.0-1.0，表示对决策的置信度
- risk_level: low（低风险）、medium（中等风险）、high（高风险）

请直接输出 JSON，不要包含其他解释。
"""

    def _build_review_prompt(self, trade: TradeResult) -> str:
        """
        构建复盘提示词

        Args:
            trade: 交易结果

        Returns:
            提示词字符串
        """
        pnl_status = "盈利" if trade.pnl and trade.pnl > 0 else "亏损" if trade.pnl else "未平仓"

        return f"""你是一个专业的交易复盘分析师。请对以下交易进行复盘分析。

## 交易信息
- 交易对: {trade.symbol}
- 方向: {trade.action.value}
- 入场价格: {trade.entry_price}
- 出场价格: {trade.exit_price or '未平仓'}
- 数量: {trade.quantity}
- 盈亏: {trade.pnl or 'N/A'} ({trade.pnl_pct or 'N/A'}%)
- 状态: {trade.status}
- 入场时间: {trade.entry_time}
- 出场时间: {trade.exit_time or '未平仓'}
- 当前状态: {pnl_status}

## 复盘要求

请按照以下 JSON 格式输出复盘报告：

```json
{{
  "overall_assessment": "整体评价（1-2句话）",
  "score": 0-100,
  "findings": [
    {{
      "category": "decision_quality|timing|risk_management|execution",
      "severity": "info|warning|error|critical",
      "description": "发现描述",
      "recommendation": "改进建议",
      "evidence": {{}}
    }}
  ],
  "lessons_learned": [
    "学到的教训1",
    "学到的教训2"
  ],
  "improvements": [
    "改进建议1",
    "改进建议2"
  ]
}}
```

### 分析维度：
1. **decision_quality**: 决策质量 - 入场时机和方向是否正确
2. **timing**: 时机把握 - 进出场时机是否合适
3. **risk_management**: 风险管理 - 止损止盈设置是否合理
4. **execution**: 执行质量 - 是否按计划执行

### 严重程度：
- info: 信息性发现
- warning: 需要注意
- error: 明显错误
- critical: 严重问题

请直接输出 JSON，不要包含其他解释。
"""

    def _parse_analysis_response(
        self,
        response_text: str,
        context: MarketContext,
    ) -> EvidenceBasedDecision:
        """
        解析分析响应

        Args:
            response_text: API 响应文本
            context: 市场上下文（用于默认值）

        Returns:
            EvidenceBasedDecision
        """
        try:
            # 提取 JSON
            json_str = self._extract_json(response_text)
            data = json.loads(json_str)

            # 解析 action
            action_str = data.get("action", "hold").lower()
            action = self._parse_action(action_str)

            # 解析 confidence
            confidence = float(data.get("confidence", 0.5))
            confidence = max(0.0, min(1.0, confidence))

            # 解析 risk_level
            risk_str = data.get("risk_level", "medium").lower()
            risk_level = self._parse_risk_level(risk_str)

            # 构建证据链
            evidence_chain = self._parse_evidence_chain(data.get("evidence_chain", []))

            return EvidenceBasedDecision(
                action=action,
                confidence=confidence,
                reasoning=data.get("reasoning", "无分析理由"),
                evidence_chain=evidence_chain,
                suggested_amount=data.get("suggested_amount"),
                stop_loss_pct=data.get("stop_loss_pct"),
                take_profit_pct=data.get("take_profit_pct"),
                risk_level=risk_level,
                metadata={
                    "model": self._model,
                    "symbol": context.symbol,
                    "raw_response": response_text[:500],  # 保留部分原始响应
                },
            )

        except json.JSONDecodeError as e:
            logger.error(f"JSON 解析失败: {e}")
            # 返回保守的默认决策
            return self._create_fallback_decision(context, str(e))

        except Exception as e:
            logger.error(f"解析响应失败: {e}")
            return self._create_fallback_decision(context, str(e))

    def _parse_review_response(
        self,
        response_text: str,
        trade: TradeResult,
    ) -> ReviewReport:
        """
        解析复盘响应

        Args:
            response_text: API 响应文本
            trade: 交易结果

        Returns:
            ReviewReport
        """
        try:
            json_str = self._extract_json(response_text)
            data = json.loads(json_str)

            # 解析 findings
            findings = []
            for f in data.get("findings", []):
                finding = ReviewFinding(
                    category=f.get("category", "decision_quality"),
                    severity=f.get("severity", "info"),
                    description=f.get("description", ""),
                    recommendation=f.get("recommendation", ""),
                    evidence=f.get("evidence", {}),
                )
                findings.append(finding)

            return ReviewReport(
                trade_id=trade.symbol,
                overall_assessment=data.get("overall_assessment", "无法解析复盘结果"),
                findings=findings,
                lessons_learned=data.get("lessons_learned", []),
                improvements=data.get("improvements", []),
                score=float(data.get("score", 0.0)),
                metadata={
                    "model": self._model,
                    "raw_response": response_text[:500],
                },
            )

        except json.JSONDecodeError as e:
            logger.error(f"JSON 解析失败: {e}")
            return self._create_fallback_review(trade, str(e))

        except Exception as e:
            logger.error(f"解析复盘响应失败: {e}")
            return self._create_fallback_review(trade, str(e))

    def _extract_json(self, text: str) -> str:
        """
        从文本中提取 JSON

        Args:
            text: 可能包含 JSON 的文本

        Returns:
            JSON 字符串
        """
        # 尝试提取 ```json ... ``` 块
        if "```json" in text:
            start = text.find("```json") + 7
            end = text.find("```", start)
            if end > start:
                return text[start:end].strip()

        # 尝试提取 ``` ... ``` 块
        if "```" in text:
            start = text.find("```") + 3
            end = text.find("```", start)
            if end > start:
                return text[start:end].strip()

        # 尝试提取 { ... } 块
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            return text[start : end + 1]

        return text

    def _parse_action(self, action_str: str) -> ActionType:
        """解析动作类型"""
        action_map = {
            "buy": ActionType.BUY,
            "sell": ActionType.SELL,
            "hold": ActionType.HOLD,
        }
        return action_map.get(action_str.lower(), ActionType.HOLD)

    def _parse_risk_level(self, risk_str: str) -> RiskLevel:
        """解析风险等级"""
        risk_map = {
            "low": RiskLevel.LOW,
            "medium": RiskLevel.MEDIUM,
            "high": RiskLevel.HIGH,
        }
        return risk_map.get(risk_str.lower(), RiskLevel.MEDIUM)

    def _parse_evidence_chain(self, evidence_list: List[Dict]) -> EvidenceChain:
        """
        解析证据链

        Args:
            evidence_list: 证据列表

        Returns:
            EvidenceChain
        """
        chain = EvidenceChain()

        for item in evidence_list:
            try:
                evidence = Evidence(
                    source=item.get("source", "unknown"),
                    metric=item.get("metric", "unknown"),
                    value=item.get("value", None),
                    weight=float(item.get("weight", 1.0)),
                    confidence=float(item.get("confidence", 1.0)),
                    description=item.get("description", ""),
                )
                chain.add_evidence(evidence)

            except Exception as e:
                logger.warning(f"解析证据失败: {e}, item: {item}")

        return chain

    def _format_indicators(self, indicators: Dict[str, Any]) -> str:
        """格式化技术指标"""
        if not indicators:
            return "无技术指标数据"

        lines = []
        for key, value in indicators.items():
            if isinstance(value, float):
                lines.append(f"- {key}: {value:.4f}")
            else:
                lines.append(f"- {key}: {value}")

        return "\n".join(lines)

    def _format_price_history(self, prices: List[float]) -> str:
        """格式化价格历史"""
        if not prices:
            return "无价格历史数据"

        # 只显示最近10个
        recent = prices[-10:] if len(prices) > 10 else prices
        return ", ".join(f"{p:.2f}" for p in recent)

    def _create_fallback_decision(
        self,
        context: MarketContext,
        error: str,
    ) -> EvidenceBasedDecision:
        """
        创建后备决策（当解析失败时）

        Args:
            context: 市场上下文
            error: 错误信息

        Returns:
            保守的默认决策
        """
        return EvidenceBasedDecision(
            action=ActionType.HOLD,
            confidence=0.0,
            reasoning=f"解析失败，建议观望: {error}",
            risk_level=RiskLevel.HIGH,
            metadata={
                "error": error,
                "symbol": context.symbol,
                "fallback": True,
            },
        )

    def _create_fallback_review(self, trade: TradeResult, error: str) -> ReviewReport:
        """
        创建后备复盘报告

        Args:
            trade: 交易结果
            error: 错误信息

        Returns:
            基本的复盘报告
        """
        return ReviewReport(
            trade_id=trade.symbol,
            overall_assessment=f"复盘解析失败: {error}",
            findings=[
                ReviewFinding(
                    category="execution",
                    severity="error",
                    description=f"无法解析 AI 复盘响应: {error}",
                    recommendation="请检查 API 响应格式",
                    evidence={"error": error},
                )
            ],
            lessons_learned=[],
            improvements=["改进 AI 响应解析逻辑"],
            score=0.0,
            metadata={"error": error, "fallback": True},
        )
