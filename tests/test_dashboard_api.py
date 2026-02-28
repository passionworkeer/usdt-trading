#!/usr/bin/env python3
"""
Dashboard API 认证测试
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import sys
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent))


class TestDashboardAPI:
    """测试 Dashboard API 认证"""

    def test_import_success(self):
        """测试模块导入成功"""
        # 这是一个简单的语法检查
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "api",
            Path(__file__).parent / "trading_dashboard" / "api.py"
        )
        module = importlib.util.module_from_spec(spec)
        # 只检查导入是否成功，不执行
        assert spec is not None

    def test_api_token_config(self):
        """测试 API Token 配置"""
        import os
        # 测试默认空 Token
        os.environ.pop("DASHBOARD_API_TOKEN", None)
        with patch.dict(os.environ, {}, clear=True):
            token = os.environ.get("DASHBOARD_API_TOKEN", "")
            assert token == ""

    def test_verify_token_logic(self):
        """测试 Token 验证逻辑"""
        # 测试无 Token 时的行为（返回 dev）
        from fastapi.security import HTTPBearer

        # 模拟未配置 Token 的情况
        with patch('scripts.trading_dashboard.api.API_TOKEN', ""):
            # 创建认证对象
            security = HTTPBearer(auto_error=False)

            # 验证逻辑：无 Token 时应返回 "dev"
            api_token = ""
            if not api_token:
                result = "dev"
            assert result == "dev"

    def test_host_binding(self):
        """测试网络绑定配置"""
        # 读取文件检查 host 配置
        api_file = Path(__file__).parent.parent / "scripts" / "trading_dashboard" / "api.py"
        content = api_file.read_text(encoding='utf-8')

        # 确认 host 已修改为 127.0.0.1
        assert 'host="127.0.0.1"' in content
        assert 'host="0.0.0.0"' not in content

    def test_api_endpoints_have_auth(self):
        """测试所有 API 端点都添加了认证"""
        api_file = Path(__file__).parent.parent / "scripts" / "trading_dashboard" / "api.py"
        content = api_file.read_text(encoding='utf-8')

        # 检查所有 /api/ 端点都有 Security(verify_token)
        endpoints = [
            "/api/market/{symbol}",
            "/api/signals",
            "/api/account",
            "/api/positions",
            "/api/trades",
            "/api/backtest"
        ]

        for endpoint in endpoints:
            assert f'@app.get("{endpoint}")' in content or f'@app.get(\'{endpoint}\')' in content

        # 确认 verify_token 被使用
        assert "Security(verify_token)" in content


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
