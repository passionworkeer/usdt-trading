"""
OpenClaw AI Provider

调用 OpenClaw HTTP API 进行市场分析和决策。
支持结构化证据链返回，用于风险控制系统。
"""
import asyncio
import logging
from typing import Any, Dict, Optional

import aiohttp

from .base import (
    AIBaseProvider,
    ActionType,
    EvidenceBasedDecision,
    MarketContext,
    ReviewReport,
    TradeResult,
)

logger = logging.getLogger(__name__)


class OpenClawProviderError(Exception):
    """OpenClaw Provider 错误基类"""
    pass


class OpenClawAPIError(OpenClawProviderError):
    """OpenClaw API 错误"""
    def __init__(self, message: str, status_code: Optional[int] = None, response_data: Optional[Dict] = None):
        super().__init__(message)
        self.status_code = status_code
        self.response_data = response_data


class OpenClawTimeoutError(OpenClawProviderError):
    """OpenClaw 请求超时错误"""
    pass


class OpenClawProvider(AIBaseProvider):
    """
    OpenClaw AI Provider

    通过 HTTP API 调用 OpenClaw 服务进行市场分析和决策。
    支持健康检查、超时重试、错误处理等功能。

    Attributes:
        endpoint: OpenClaw 服务端点 URL
        api_key: API 密钥（可选）
        timeout: 请求超时时间（秒）
        session: aiohttp ClientSession
    """

    def __init__(
        self,
        endpoint: str,
        api_key: Optional[str] = None,
        timeout: float = 30.0,
        config: Optional[Dict[str, Any]] = None,
    ):
        """
        初始化 OpenClaw Provider

        Args:
            endpoint: OpenClaw 服务端点 URL
            api_key: API 密钥（可选）
            timeout: 请求超时时间（秒）
            config: 额外配置
        """
        super().__init__(config)
        self.endpoint = endpoint.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout
        self._session: Optional[aiohttp.ClientSession] = None
        self._version = "1.0.0"

    @property
    def name(self) -> str:
        """Provider 名称"""
        return "openclaw"

    @property
    def version(self) -> str:
        """Provider 版本"""
        return self._version

    def _get_session(self) -> aiohttp.ClientSession:
        """获取或创建 aiohttp ClientSession"""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=self.timeout),
                headers=self._get_default_headers(),
            )
        return self._session

    def _get_default_headers(self) -> Dict[str, str]:
        """获取默认 HTTP 头"""
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": f"OpenClawProvider/{self._version}",
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def _do_initialize(self) -> bool:
        """
        实际初始化逻辑

        Returns:
            是否成功
        """
        try:
            # 创建 session
            _ = self._get_session()
            logger.info(f"OpenClawProvider 初始化成功: {self.endpoint}")
            return True
        except Exception as e:
            self._set_error(f"初始化失败: {str(e)}")
            logger.error(f"OpenClawProvider 初始化失败: {e}")
            return False

    async def _make_request(
        self,
        method: str,
        path: str,
        data: Optional[Dict] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """
        发送 HTTP 请求

        Args:
            method: HTTP 方法
            path: API 路径
            data: 请求体数据
            **kwargs: 额外参数

        Returns:
            响应数据

        Raises:
            OpenClawAPIError: API 错误
            OpenClawTimeoutError: 超时错误
        """
        session = self._get_session()
        url = f"{self.endpoint}{path}"

        try:
            async with session.request(
                method=method,
                url=url,
                json=data,
                **kwargs,
            ) as response:
                response_data = await response.json()

                if response.status >= 400:
                    raise OpenClawAPIError(
                        f"API 错误: {response.status}",
                        status_code=response.status,
                        response_data=response_data,
                    )

                return response_data

        except asyncio.TimeoutError as e:
            raise OpenClawTimeoutError(f"请求超时: {url}") from e
        except aiohttp.ClientError as e:
            raise OpenClawAPIError(f"HTTP 请求失败: {str(e)}") from e

    async def analyze(self, context: MarketContext) -> EvidenceBasedDecision:
        """
        分析市场并返回基于证据的决策

        Args:
            context: 市场上下文

        Returns:
            基于证据的决策

        Raises:
            OpenClawAPIError: API 调用错误
            OpenClawTimeoutError: 超时错误
        """
        if not self.is_initialized:
            raise OpenClawProviderError("Provider 未初始化，请先调用 initialize()")

        try:
            # 调用 OpenClaw API
            response_data = await self._make_request(
                method="POST",
                path="/api/analyze",
                data=context.to_dict(),
            )

            # 解析响应数据
            decision = self._parse_decision_response(response_data, context.current_price)

            logger.info(
                f"OpenClaw 分析完成: action={decision.action}, "
                f"evidence_count={decision.evidence_count}, "
                f"veto_flag={decision.veto_flag}"
            )

            return decision

        except OpenClawProviderError:
            raise
        except Exception as e:
            logger.error(f"OpenClaw 分析失败: {e}")
            raise OpenClawAPIError(f"分析失败: {str(e)}") from e

    def _parse_decision_response(self, data: Dict[str, Any], current_price: float = 0.0) -> EvidenceBasedDecision:
        """
        解析 OpenClaw API 响应数据

        Args:
            data: API 响应数据
            current_price: 当前价格（用于默认值）

        Returns:
            EvidenceBasedDecision 对象
        """
        # 解析动作类型
        action_str = data.get("action", "HOLD").upper()
        try:
            action = ActionType(action_str.lower())
        except ValueError:
            action = ActionType.HOLD

        # 解析证据链
        evidence_chain = data.get("evidence_chain", [])
        if isinstance(evidence_chain, list):
            # 确保所有证据都是字符串
            evidence_chain = [str(e) for e in evidence_chain]
        else:
            evidence_chain = []

        evidence_count = len(evidence_chain)

        # 解析 veto_flag
        veto_flag = bool(data.get("veto_flag", False))

        # 解析价格参数
        entry_price = float(data.get("entry_price", current_price or data.get("current_price", 0)))
        stop_loss = float(data.get("stop_loss", entry_price * 0.98))
        take_profit = float(data.get("take_profit", entry_price * 1.04))
        position_size = float(data.get("position_size", 0.0))

        # 构建决策对象
        decision = EvidenceBasedDecision(
            action=action,
            evidence_count=evidence_count,
            evidence_chain=evidence_chain,
            veto_flag=veto_flag,
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            position_size=position_size,
            reasoning=data.get("reasoning", ""),
            metadata=data.get("metadata", {}),
        )

        return decision

    async def review(self, trade: TradeResult) -> ReviewReport:
        """
        复盘交易

        Args:
            trade: 交易结果

        Returns:
            复盘报告

        Note:
            OpenClaw 基础 provider 不实现复盘功能，
            需要子类覆盖此方法或使用专门的复盘 provider。
        """
        # 基础实现：返回空复盘报告
        # 子类应覆盖此方法以提供实际的复盘功能
        from .base import ReviewFinding  # 避免循环导入

        report = ReviewReport(
            trade_id=f"{trade.symbol}_{trade.entry_time.isoformat()}",
            overall_assessment="OpenClaw 基础 Provider 不支持复盘功能，请使用专门的复盘 Provider",
            findings=[
                ReviewFinding(
                    category="capability",
                    severity="info",
                    description="当前 Provider 未实现复盘功能",
                    recommendation="请继承 OpenClawProvider 并覆盖 review 方法",
                )
            ],
            lessons_learned=[],
            improvements=[],
            score=0.0,
        )

        logger.warning(f"OpenClawProvider 复盘功能未实现: {trade.symbol}")
        return report

    async def health_check(self) -> bool:
        """
        健康检查

        通过 ping 端点验证 OpenClaw 服务是否可用。

        Returns:
            服务是否健康
        """
        try:
            # 尝试调用 ping 端点
            response_data = await self._make_request(
                method="GET",
                path="/api/ping",
            )

            # 检查响应是否包含预期的成功标记
            if response_data.get("status") == "ok" or "pong" in response_data.get("message", "").lower():
                logger.debug(f"OpenClaw 健康检查通过: {self.endpoint}")
                return True

            logger.warning(f"OpenClaw 健康检查异常响应: {response_data}")
            return False

        except OpenClawTimeoutError:
            logger.error(f"OpenClaw 健康检查超时: {self.endpoint}")
            return False
        except OpenClawAPIError as e:
            logger.error(f"OpenClaw 健康检查失败: {e.status_code} - {e}")
            return False
        except Exception as e:
            logger.error(f"OpenClaw 健康检查异常: {e}")
            return False

    async def close(self) -> None:
        """关闭 Provider，释放资源"""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None
            logger.info("OpenClawProvider 会话已关闭")

    def __del__(self):
        """析构函数，确保资源释放"""
        if self._session and not self._session.closed:
            # 使用 asyncio 关闭 session
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    loop.create_task(self._session.close())
                else:
                    loop.run_until_complete(self._session.close())
            except Exception:
                pass  # 忽略关闭时的错误
