#!/usr/bin/env python3
"""
test_world_config_api.py — 世界设定中途编辑 API 聚焦测试（api/generate_api.py）。

验证开局后初始世界设定可修改：
- /api/world-config GET 返回当前世界设定；未初始化时 400
- /api/world-config PUT 更新字段（名称空值校验、列表字段清洗）
- 主线目标变化时触发角色目标权重重新校准；未变化时不触发
- 存档 save/load 往返保留 main_objective 与 perspective（防止刷新后回退）

装配方式与 app.py 一致：exec 注入共享命名空间，FakeEngine 隔离真实引擎/AI 调用。
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

import backend.storage as storage_mod
from backend.config import WorldConfig
from backend.world import World

API_FILE = os.path.join(PROJECT_ROOT, "api", "generate_api.py")
with open(API_FILE, "r", encoding="utf-8") as f:
    GENERATE_API_SRC = f.read()


class FakeEngine:
    """隔离真实引擎：只记录目标校准调用，不做 AI 请求"""

    def __init__(self):
        self.world = None
        self.align_calls = 0
        self.config = SimpleNamespace(
            total_chapters=10,
            ticks_per_chapter=5,
            auto_pause_between_chapters=True,
            end_behavior="stop",
            expected_ending="",
        )

    def align_goals_to_main_objective(self):
        self.align_calls += 1


def build_client():
    """装配干净 Flask app 并 exec generate_api.py（复用 app.py 注入方式）"""
    app = Flask(__name__)
    engine = FakeEngine()
    ns = {
        "app": app,
        "_engine_lock": threading.Lock(),
        "request": request,
        "jsonify": jsonify,
        "os": os,
        "json": json,
        "engine": engine,
    }
    exec(compile(GENERATE_API_SRC, API_FILE, "exec"), ns)
    app.config["TESTING"] = True
    return app.test_client(), engine


def _make_world(**kwargs):
    cfg = WorldConfig(
        name=kwargs.get("name", "测试世界"),
        genre=kwargs.get("genre", "玄幻"),
        era=kwargs.get("era", "古代"),
        description=kwargs.get("description", "初始描述"),
        rules=kwargs.get("rules", ["规则一"]),
        key_locations=kwargs.get("key_locations", ["青云宗"]),
        current_situation=kwargs.get("current_situation", "初始局势"),
        tone=kwargs.get("tone", "史诗冒险"),
        main_objective=kwargs.get("main_objective", "旧主线"),
        perspective=kwargs.get("perspective", "third"),
    )
    return World(cfg)


@pytest.fixture
def client():
    c, engine = build_client()
    return SimpleNamespace(client=c, engine=engine)


# ── GET /api/world-config ──

def test_get_world_config_requires_init(client):
    resp = client.client.get("/api/world-config")
    assert resp.status_code == 400
    assert "初始化" in resp.get_json()["error"]


def test_get_world_config_returns_all_fields(client):
    client.engine.world = _make_world()
    resp = client.client.get("/api/world-config")
    assert resp.status_code == 200
    cfg = resp.get_json()["config"]
    assert cfg["name"] == "测试世界"
    assert cfg["genre"] == "玄幻"
    assert cfg["era"] == "古代"
    assert cfg["description"] == "初始描述"
    assert cfg["rules"] == ["规则一"]
    assert cfg["key_locations"] == ["青云宗"]
    assert cfg["current_situation"] == "初始局势"
    assert cfg["tone"] == "史诗冒险"
    assert cfg["main_objective"] == "旧主线"
    assert cfg["perspective"] == "third"


# ── PUT /api/world-config ──

def test_put_world_config_requires_init(client):
    resp = client.client.put("/api/world-config", json={"name": "新名字"})
    assert resp.status_code == 400


def test_put_updates_fields_without_realign(client):
    client.engine.world = _make_world()
    resp = client.client.put("/api/world-config", json={
        "name": "修正后的世界",
        "genre": "科幻",
        "era": "未来",
        "description": "新描述",
        "rules": ["新规则一", "", " 新规则二 "],
        "key_locations": ["星港", ""],
        "current_situation": "新局势",
        "tone": "黑暗残酷",
        "perspective": "first",
        "main_objective": "旧主线",  # 未变化
    })
    assert resp.status_code == 200
    wc = client.engine.world.config
    assert wc.name == "修正后的世界"
    assert wc.genre == "科幻"
    assert wc.era == "未来"
    assert wc.description == "新描述"
    assert wc.rules == ["新规则一", "新规则二"]  # 空行被过滤
    assert wc.key_locations == ["星港"]
    assert wc.current_situation == "新局势"
    assert wc.tone == "黑暗残酷"
    assert wc.perspective == "first"
    assert client.engine.align_calls == 0  # 主线未变，不触发校准


def test_put_rejects_empty_name(client):
    client.engine.world = _make_world()
    resp = client.client.put("/api/world-config", json={"name": "   "})
    assert resp.status_code == 400
    assert client.engine.world.config.name == "测试世界"  # 未被污染


def test_put_main_objective_change_triggers_realign(client):
    client.engine.world = _make_world(main_objective="旧主线")
    resp = client.client.put("/api/world-config", json={"main_objective": "新主线目标"})
    assert resp.status_code == 200
    assert client.engine.world.config.main_objective == "新主线目标"
    assert client.engine.align_calls == 1


def test_put_main_objective_unchanged_no_realign(client):
    client.engine.world = _make_world(main_objective="不变的主线")
    resp = client.client.put("/api/world-config", json={"main_objective": "不变的主线"})
    assert resp.status_code == 200
    assert client.engine.align_calls == 0


def test_put_realign_failure_does_not_block_save(client):
    client.engine.world = _make_world(main_objective="旧主线")

    def _broken():
        raise RuntimeError("AI 校准失败")

    client.engine.align_goals_to_main_objective = _broken
    resp = client.client.put("/api/world-config", json={"main_objective": "新主线"})
    assert resp.status_code == 200
    assert client.engine.world.config.main_objective == "新主线"


# ── 存档往返：main_objective / perspective 持久化 ──

def test_save_load_roundtrip_preserves_main_objective_and_perspective(tmp_path, monkeypatch):
    monkeypatch.setattr(storage_mod, "SAVES_DIR", str(tmp_path))
    st = storage_mod.Storage()
    world = _make_world(main_objective="坚持住的主线", perspective="first")
    st.save("auto", world, [], [])

    loaded = st.load("auto")
    assert loaded is not None
    loaded_world = loaded[0]
    assert loaded_world.config.main_objective == "坚持住的主线"
    assert loaded_world.config.perspective == "first"


def test_load_legacy_save_without_new_fields(tmp_path, monkeypatch):
    """旧存档缺 main_objective/perspective 字段时应回退默认值而非报错"""
    monkeypatch.setattr(storage_mod, "SAVES_DIR", str(tmp_path))
    data = {
        "meta": {"saved_at": "2026-08-10T00:00:00", "slot": "auto"},
        "world_config": {"name": "旧存档"},
        "world_state": {"current_chapter": 1, "events": [], "character_positions": {}},
        "characters": [],
        "chapters": [],
        "outline_data": None,
        "engine_config": None,
    }
    with open(os.path.join(str(tmp_path), "auto.json"), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)

    st = storage_mod.Storage()
    loaded = st.load("auto")
    assert loaded is not None
    assert loaded[0].config.name == "旧存档"
    assert loaded[0].config.main_objective == ""
    assert loaded[0].config.perspective == "third"
