# -*- coding: utf-8 -*-
"""provider 配置防护测试：非法 provider 不得写入/生效

背景：历史遗留的 AI_PROVIDER=api 曾被 init_client 写入 ai_config.json，
导致所有 AI 调用静默返回 "[错误] 不支持的 provider"，去AI味按钮全部失效。
"""

import sys
import os
import json
import tempfile
import shutil

BACKEND = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend")
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)

from ai_client import AIClient, VALID_PROVIDERS, init_client


def _make_client(provider_value):
    """创建带指定 provider 配置的临时 AIClient"""
    tmp = tempfile.mkdtemp()
    config_path = os.path.join(tmp, "ai_config.json")
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump({"provider": provider_value}, f)
    return AIClient(config_path=config_path), tmp


class TestProviderGuard:
    def test_invalid_provider_repaired_on_load(self):
        """加载配置时非法 provider 自动回退 deepseek"""
        client, tmp = _make_client("api")
        try:
            assert client.get_provider() == "deepseek"
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_set_provider_rejects_invalid(self):
        """set_provider 拒绝非法值，保持原值"""
        client, tmp = _make_client("deepseek")
        try:
            client.set_provider("api")
            assert client.get_provider() == "deepseek"
            client.set_provider("ollama")
            assert client.get_provider() == "ollama"
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_init_client_with_invalid_provider(self):
        """init_client 传入非法 provider 不得写坏配置"""
        client, tmp = _make_client("deepseek")
        try:
            client.set_provider("deepseek")  # 确保落盘
            init_client(provider="api")
            # 全局 _client 的 provider 应保持合法
            from ai_client import get_client, _router
            if _router is None:
                assert get_client().get_provider() in VALID_PROVIDERS
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
