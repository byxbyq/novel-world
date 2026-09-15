#!/usr/bin/env python3
"""
test_chat_api.py — 聊天式剧情讨论 API 端点聚焦测试（api/chat_api.py）。

通过 exec 注入命名空间的方式加载 chat_api.py（与 app.py 相同的装配机制），
使用 FakeEngine/FakeModelRouter 隔离真实引擎与 AI 调用。

历史 bug 回归：
- /api/chat/confirm 曾是死接口（前端确认卡"确认"按钮 404 被静默吞掉），
  现必须存在并对已知操作返回 ok、未知操作返回 400。
- /api/chat/undo 空栈必须返回 noop 而非 500。
"""
import os
import sys
import json
import threading

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import pytest
from flask import Flask, request, jsonify
from types import SimpleNamespace

API_FILE = os.path.join(PROJECT_ROOT, "api", "chat_api.py")
with open(API_FILE, "r", encoding="utf-8") as f:
    CHAT_API_SRC = f.read()


# ── 测试替身 ──

class FakeEngine:
    """隔离真实引擎：只提供 chat_api 读取的状态字段"""

    def __init__(self):
        self.world = None
        self.chapters = []
        self.outline_data = None
        self._characters = []
        self.config = SimpleNamespace(total_chapters=10)


class FakeModelRouter:
    """隔离真实 AI：返回固定文本，记录调用"""

    def __init__(self):
        self.calls = []
        self.reply = "这是讨论回复，没有函数调用"

    def chat_with_messages(self, messages, **kw):
        self.calls.append({"messages": messages, "kw": kw})
        return self.reply


def build_client():
    """装配干净 Flask app 并 exec chat_api.py（复用 app.py 的注入方式）"""
    app = Flask(__name__)
    engine = FakeEngine()
    router = FakeModelRouter()
    ns = {
        "app": app,
        "request": request,
        "jsonify": jsonify,
        "engine": engine,
        "model_router": router,
        "_engine_lock": threading.Lock(),
    }
    exec(compile(CHAT_API_SRC, API_FILE, "exec"), ns)
    app.config["TESTING"] = True
    return app.test_client(), ns


@pytest.fixture
def ctx():
    client, ns = build_client()
    return SimpleNamespace(client=client, ns=ns)


# ── /api/chat/confirm（历史死接口回归） ──

def test_chat_confirm_known_name_ok(ctx):
    """"确认"按钮对 FUNCTION_SPECS 中的已知操作返回 ok（不再 404）。"""
    spec_names = [f["name"] for f in ctx.ns["FUNCTION_SPECS"]]
    assert spec_names, "FUNCTION_SPECS 不应为空"
    for name in spec_names:
        r = ctx.client.post("/api/chat/confirm", json={"name": name})
        assert r.status_code == 200, f"confirm({name}) 返回 {r.status_code}"
        assert r.get_json()["status"] == "ok"


def test_chat_confirm_unknown_name_400(ctx):
    r = ctx.client.post("/api/chat/confirm", json={"name": "不存在操作"})
    assert r.status_code == 400
    assert "未知操作" in r.get_json()["error"]


def test_chat_confirm_empty_body_ok(ctx):
    """无 name 时视为通用确认回执，不报错。"""
    r = ctx.client.post("/api/chat/confirm", json={})
    assert r.status_code == 200
    assert r.get_json()["status"] == "ok"


# ── /api/chat/undo ──

def test_chat_undo_empty_stack_noop(ctx):
    r = ctx.client.post("/api/chat/undo")
    assert r.status_code == 200
    assert r.get_json()["status"] == "noop"


def test_chat_undo_pops_snapshot(ctx):
    ctx.ns["_rollback_stack"].push({"characters": []})
    r = ctx.client.post("/api/chat/undo")
    data = r.get_json()
    assert r.status_code == 200
    assert data["status"] == "ok"
    assert data["remaining_undo_count"] == 0
    assert len(ctx.ns["_rollback_stack"]) == 0


# ── /api/chat 与 /api/chat/history 基础路径 ──

def test_chat_empty_message_400(ctx):
    r = ctx.client.post("/api/chat", json={"message": "  "})
    assert r.status_code == 400


def test_chat_history_returns_list(ctx):
    r = ctx.client.get("/api/chat/history")
    assert r.status_code == 200
    assert isinstance(r.get_json()["history"], list)


# ── 世界设定：函数注册与调度路由 ──

def test_edit_world_settings_spec_registered(ctx):
    specs = {f["name"]: f for f in ctx.ns["FUNCTION_SPECS"]}
    assert "edit_world_settings" in specs
    assert specs["edit_world_settings"]["side_effect"] is True
    assert "edit_world_settings" in ctx.ns["SIDE_EFFECT_FUNCTIONS"]


def test_call_internal_api_world_settings_routing(ctx):
    """get/edit_world_settings 应路由到 /api/world-config。

    历史 bug：get_world_settings 曾指向不存在的 /api/world-settings。
    """
    recorded = {}

    @ctx.ns["app"].route("/api/world-config", methods=["GET", "PUT"])
    def _stub_world_config():
        recorded["method"] = request.method
        recorded["json"] = request.get_json(silent=True)
        return jsonify({"status": "ok", "config": {"name": "桩世界"}})

    result = ctx.ns["_call_internal_api"]("get_world_settings", {})
    assert recorded["method"] == "GET"
    assert result["config"]["name"] == "桩世界"

    ctx.ns["_call_internal_api"]("edit_world_settings", {"main_objective": "新主线"})
    assert recorded["method"] == "PUT"
    assert recorded["json"] == {"main_objective": "新主线"}


# ── 回滚快照覆盖世界设定 ──

def test_snapshot_restore_covers_world_config(ctx):
    from backend.config import WorldConfig
    from backend.world import World

    ctx.ns["engine"].world = World(WorldConfig(
        name="原世界", main_objective="原主线", rules=["规则甲"],
    ))
    ctx.ns["_save_snapshot"]()

    # 模拟 edit_world_settings 修改
    wc = ctx.ns["engine"].world.config
    wc.name = "改后世界"
    wc.main_objective = "改后主线"
    wc.rules = ["规则乙"]

    snapshot = ctx.ns["_rollback_stack"].pop()
    msg = ctx.ns["_restore_snapshot"](snapshot)
    assert "回滚" in msg
    wc = ctx.ns["engine"].world.config
    assert wc.name == "原世界"
    assert wc.main_objective == "原主线"
    assert wc.rules == ["规则甲"]

