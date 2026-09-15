#!/usr/bin/env python3
"""
test_model_router.py — 多模型路由单元测试。

测试覆盖：
- ModelRouter 初始化与配置管理
- Provider 切换
- TASK_MODEL_MAP 路由
- 用量统计
- 连接测试
"""
import sys
import os
import json
import tempfile
import shutil
import time

BACKEND = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend")
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)

from model_router import ModelRouter, AIClientException


def _make_temp_config():
    """创建临时 ai_config.json"""
    tmp = tempfile.mkdtemp()
    config_dir = os.path.join(tmp, "data")
    os.makedirs(config_dir)
    config_path = os.path.join(config_dir, "ai_config.json")
    config = {
        "provider": "deepseek",
        "deepseek": {
            "api_key": "",
            "base_url": "https://api.deepseek.com",
            "model": "deepseek-v4-flash",
            "temperature": 0.7,
            "max_tokens": 8192,
        },
    }
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f)
    return tmp, config_path


def test_router_init():
    """ModelRouter 初始化正常。"""
    tmp, config_path = _make_temp_config()
    try:
        router = ModelRouter(config_path=config_path)
        assert router.get_provider() == "deepseek"
        assert router.config["deepseek"]["model"] == "deepseek-v4-flash"
        assert "ollama" in router.config  # 自动填充默认值
        print("  ✓ ModelRouter: 初始化 + 默认值填充")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_router_provider_switch():
    """Provider 切换正常。"""
    tmp, config_path = _make_temp_config()
    try:
        router = ModelRouter(config_path=config_path)
        router.set_provider("openai")
        assert router.get_provider() == "openai"
        # 重新读取配置确认持久化
        with open(config_path, "r", encoding="utf-8") as f:
            saved = json.load(f)
        assert saved["provider"] == "openai" or saved.get("provider") == "openai"
        print("  ✓ ModelRouter: Provider 切换")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_router_task_model_map():
    """TASK_MODEL_MAP 路由正确。"""
    tmp, config_path = _make_temp_config()
    try:
        router = ModelRouter(config_path=config_path)
        model = router.get_model_for_task("architecture")
        assert model is not None
        # architecture 任务在 deepseek provider 下应为 deepseek-v4
        assert "deepseek" in model
        model2 = router.get_model_for_task("chat")
        assert model2 is not None
        print(f"  ✓ ModelRouter: TASK_MODEL_MAP (architecture={model}, chat={model2})")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_router_all_providers_tasks():
    """所有 provider + task_type 组合不崩溃。"""
    tmp, config_path = _make_temp_config()
    try:
        router = ModelRouter(config_path=config_path)
        for provider in ["deepseek", "ollama", "openai", "doubao", "kimi"]:
            router.config["provider"] = provider
            for task in ["architecture", "writing", "check", "summary", "chat"]:
                model = router.get_model_for_task(task)
                assert isinstance(model, str)
                assert len(model) > 0
        print("  ✓ ModelRouter: 全 Provider × Task 路由不崩溃")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_router_usage_stats():
    """用量统计格式正确。"""
    tmp, config_path = _make_temp_config()
    try:
        router = ModelRouter(config_path=config_path)
        stats = router.get_usage_stats()
        assert "total_calls" in stats
        assert "total_tokens" in stats
        assert "total_cost_cny" in stats
        assert "by_day" in stats
        assert stats["total_calls"] == 0
        print("  ✓ ModelRouter: 用量统计格式")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _inject_usage(router, total_tokens, timestamp=None, provider="deepseek", model="m"):
    """直接注入用量条目（避免真实 AI 调用）"""
    router.usage_log.append({
        "timestamp": timestamp or time.strftime("%Y-%m-%d %H:%M:%S"),
        "provider": provider,
        "model": model,
        "task": "test",
        "prompt_tokens": total_tokens // 2,
        "completion_tokens": total_tokens - total_tokens // 2,
        "total_tokens": total_tokens,
        "cost_cny": 0.0,
    })


def test_quota_unlimited_by_default():
    """未配置 monthly_quota_tokens 时为 unlimited。"""
    tmp, config_path = _make_temp_config()
    try:
        router = ModelRouter(config_path=config_path)
        _inject_usage(router, 1000)
        monthly = router.get_usage_stats()["monthly"]
        assert monthly["level"] == "unlimited"
        assert monthly["quota_tokens"] == 0
        assert monthly["used_tokens"] == 1000
        print("  ✓ ModelRouter: 配额缺省 unlimited")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_quota_levels():
    """ok / warning(≥80%) / exceeded(≥100%) 三档边界。"""
    tmp, config_path = _make_temp_config()
    try:
        router = ModelRouter(config_path=config_path)
        router.config["monthly_quota_tokens"] = 10000
        ts = time.strftime("%Y-%m-01 00:00:00")  # 当月
        for used, expect in [(5000, "ok"), (8000, "warning"), (10000, "exceeded"), (12000, "exceeded")]:
            router.usage_log.clear()
            _inject_usage(router, used, timestamp=ts)
            monthly = router.get_usage_stats()["monthly"]
            assert monthly["level"] == expect, f"used={used}: {monthly['level']} != {expect}"
        # 百分比计算
        router.usage_log.clear()
        _inject_usage(router, 2500, timestamp=ts)
        assert router.get_usage_stats()["monthly"]["used_pct"] == 25.0
        print("  ✓ ModelRouter: 配额三档边界 + 百分比")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_quota_only_counts_current_month():
    """跨月记录不计入本月配额。"""
    tmp, config_path = _make_temp_config()
    try:
        router = ModelRouter(config_path=config_path)
        router.config["monthly_quota_tokens"] = 10000
        _inject_usage(router, 9000, timestamp="2020-01-01 00:00:00")  # 旧月
        _inject_usage(router, 1000)  # 本月
        monthly = router.get_usage_stats()["monthly"]
        assert monthly["used_tokens"] == 1000
        assert monthly["level"] == "ok"
        print("  ✓ ModelRouter: 跨月记录过滤")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_router_generate_safe():
    """generate_safe 无连接时返回失败但无误。"""
    tmp, config_path = _make_temp_config()
    try:
        router = ModelRouter(config_path=config_path)
        ok, result = router.generate_safe("测试")
        # 无API Key时，deepseek会返回错误，但不应崩溃
        assert isinstance(ok, bool)
        assert isinstance(result, str)
        print(f"  ✓ ModelRouter: generate_safe 不崩溃 (ok={ok})")
    finally:
        router.close()
        shutil.rmtree(tmp, ignore_errors=True)


def test_router_generate_safe_empty_is_failure():
    """generate_safe：空返回/错误前缀必须判为失败（401 被吞成空串不得误报成功）。"""
    tmp, config_path = _make_temp_config()
    try:
        router = ModelRouter(config_path=config_path)
        router.generate = lambda prompt, **kw: ""
        ok, msg = router.generate_safe("测试")
        assert ok is False and "空内容" in msg, "空返回应判为失败"
        router.generate = lambda prompt, **kw: "[错误] 认证失败"
        ok, msg = router.generate_safe("测试")
        assert ok is False, "错误前缀应判为失败"
        router.generate = lambda prompt, **kw: "正常回复"
        ok, msg = router.generate_safe("测试")
        assert ok is True and msg == "正常回复"
        print("  ✓ ModelRouter: generate_safe 空返回/错误前缀均判失败")
    finally:
        router.close()
        shutil.rmtree(tmp, ignore_errors=True)


def test_router_http_error_status_not_swallowed():
    """HTTP 非 200 必须报错，不得吞成空串（历史 bug：401 被吞空串误判成功）。

    直接测 _openai_compatible / _openai_compatible_messages 底层，
    绕过 generate 的 3 次重试 sleep。流式与非流式分支均覆盖。
    """
    tmp, config_path = _make_temp_config()

    class _FakePostResp:
        status_code = 401
        text = '{"error": "auth failed"}'

        def json(self):
            return json.loads(self.text)

    class _FakeStreamResp:
        status_code = 401

        def read(self):
            return b'{"error": "auth failed"}'

        def iter_lines(self):
            return iter([])

    class _FakeStreamCtx:
        def __enter__(self):
            return _FakeStreamResp()

        def __exit__(self, *a):
            return False

    class _FakeClient:
        def post(self, *a, **k):
            return _FakePostResp()

        def stream(self, *a, **k):
            return _FakeStreamCtx()

        def close(self):
            pass

    try:
        router = ModelRouter(config_path=config_path)
        router._client = _FakeClient()
        cfg = {"api_key": "sk-" + "x" * 40, "base_url": "http://fake",
               "model": "m", "temperature": 0.7, "max_tokens": 100}

        # 非流式 × 两个入口
        r1 = router._openai_compatible("测试", cfg)
        r2 = router._openai_compatible_messages([{"role": "user", "content": "测试"}], cfg)
        # 流式 × 两个入口
        r3 = router._openai_compatible("测试", cfg, on_chunk=lambda t: None)
        r4 = router._openai_compatible_messages([{"role": "user", "content": "测试"}], cfg, on_chunk=lambda t: None)
        for i, r in enumerate([r1, r2, r3, r4], 1):
            assert isinstance(r, str) and r.startswith("[生成失败"), f"入口{i}: 401 未报失败: {r!r}"
            assert "401" in r, f"入口{i}: 错误信息缺状态码: {r!r}"
        print("  ✓ ModelRouter: HTTP 401 四入口均显式报错（不吞空串）")
    finally:
        router.close()
        shutil.rmtree(tmp, ignore_errors=True)


def test_router_chat_signature_compat():
    """ModelRouter.chat 必须接受 ai_client.chat 兼容层的全部参数（含 on_chunk）。

    历史 bug：chat() 缺 on_chunk 参数导致反外部检测重写/深度去AI味
    全部招 TypeError 静默失败。
    """
    import inspect
    from model_router import ModelRouter
    sig = inspect.signature(ModelRouter.chat)
    for param in ("system_prompt", "user_prompt", "temperature", "max_tokens", "task", "on_chunk"):
        assert param in sig.parameters, f"ModelRouter.chat 缺参数 {param}（与 ai_client.chat 兼容层不匹配）"
    print("  ✓ ModelRouter.chat 签名与兼容层一致")


def test_router_close():
    """close 正常关闭。"""
    tmp, config_path = _make_temp_config()
    try:
        router = ModelRouter(config_path=config_path)
        router.close()  # 不应崩溃
        print("  ✓ ModelRouter: close 正常")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_router_exception():
    """AIClientException 构造正常。"""
    exc = AIClientException("测试错误", "api_error")
    assert exc.error_type == "api_error"
    assert str(exc) == "测试错误"
    print("  ✓ ModelRouter: AIClientException 正常")


if __name__ == "__main__":
    print("=" * 50)
    print("  多模型路由单元测试")
    print("=" * 50)
    print()

    tests = [
        test_router_init,
        test_router_provider_switch,
        test_router_task_model_map,
        test_router_all_providers_tasks,
        test_router_usage_stats,
        test_quota_unlimited_by_default,
        test_quota_levels,
        test_quota_only_counts_current_month,
        test_router_generate_safe,
        test_router_generate_safe_empty_is_failure,
        test_router_http_error_status_not_swallowed,
        test_router_chat_signature_compat,
        test_router_close,
        test_router_exception,
    ]

    passed = 0
    failed = 0
    for t in tests:
        try:
            t()
            passed += 1
        except Exception as e:
            print(f"  ✗ {t.__name__}: {e}")
            import traceback
            traceback.print_exc()
            failed += 1

    print()
    print(f"结果: {passed}/{len(tests)} 通过", end="")
    if failed:
        print(f", {failed} 失败", end="")
    print()
    sys.exit(0 if failed == 0 else 1)
