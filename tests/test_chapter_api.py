#!/usr/bin/env python3
"""
test_chapter_api.py — 章节 API 端点聚焦测试（api/chapter_api.py）。

通过 exec 注入命名空间的方式加载 chapter_api.py（与 app.py 相同的装配机制），
使用 FakeEngine 隔离真实引擎/AI 调用，仅验证端点的关键行为路径：
- /api/init 初始化世界与角色、应用引擎配置、清除旧大纲并自动保存
- /api/chapter 生成章节（标题推导、大纲上下文注入、API Key 校验、异常映射）
- /api/state 初始化状态判断
- /api/chapters 空标题从大纲回填
- /api/add-character 运行时添加角色（校验 + 双层角色注册）
- /api/guide-plot 情节引导（注入事件 / 添加目标 / 修改角色）
- /api/chapter/<index> 删除（重新编号）、编辑、版本历史与回滚
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

from backend.config import WorldConfig, CharacterConfig
from backend.world import World
from backend.character import CharacterAgent
from backend.outline_system import OutlineManager

API_FILE = os.path.join(PROJECT_ROOT, "api", "chapter_api.py")
with open(API_FILE, "r", encoding="utf-8") as f:
    CHAPTER_API_SRC = f.read()


# ── 测试替身 ──

class FakeNWWorld:
    def __init__(self):
        self.map_size = (10, 10)
        self.characters = []

    def add_character(self, ch):
        self.characters.append(ch)


class FakeEngine:
    """隔离真实引擎：只记录调用，不做 AI/推演"""

    def __init__(self):
        self.world = None
        self.chapters = []
        self.outline_data = None
        self._characters = []
        self.current_chapter_events = []
        self._nw_world = None
        self._nw_characters = []
        self.config = SimpleNamespace(total_chapters=10, ticks_per_chapter=5)
        self.init_calls = []
        self.run_chapter_calls = []
        self.saved = []
        self.state = {"chapter": 0}
        self.run_chapter_error = None

    def init_game(self, world, characters):
        self.world = world
        self._characters = characters
        self.init_calls.append((world, characters))

    def get_state(self):
        return self.state

    def save(self, slot):
        self.saved.append(slot)

    def run_chapter(self, title="", outline_context=""):
        self.run_chapter_calls.append({"title": title, "outline_context": outline_context})
        if self.run_chapter_error is not None:
            raise self.run_chapter_error
        chapter = {
            "chapter": len(self.chapters) + 1,
            "title": title,
            "narrative": f"{title}正文",
        }
        self.chapters.append(chapter)
        return chapter


def build_client():
    """装配一个干净的 Flask app 并 exec chapter_api.py（复用 app.py 的注入方式）"""
    app = Flask(__name__)
    engine = FakeEngine()
    ns = {
        "app": app,
        "_engine_lock": threading.Lock(),
        "request": request,
        "jsonify": jsonify,
        "os": os,
        "json": json,
        "WorldConfig": WorldConfig,
        "World": World,
        "CharacterConfig": CharacterConfig,
        "CharacterAgent": CharacterAgent,
        "engine": engine,
        "_outlines": {},
        "outline_manager": OutlineManager(),
        "_branch_chapters": {},
        "_active_branch": "main",
        "_chapter_versions": {},
    }
    exec(compile(CHAPTER_API_SRC, API_FILE, "exec"), ns)
    app.config["TESTING"] = True
    return app.test_client(), engine, ns


INIT_PAYLOAD = {
    "world": {"name": "测试世界", "genre": "玄幻", "era": "古代"},
    "characters": [
        {"name": "林凡", "gender": "男", "age": 18,
         "short_term_goals": ["初始目标"], "long_term_goal": "成为强者"},
    ],
    "engine_config": {"total_chapters": 20, "ticks_per_chapter": 3},
}


@pytest.fixture
def client(monkeypatch):
    c, engine, ns = build_client()
    return SimpleNamespace(client=c, engine=engine, ns=ns, monkeypatch=monkeypatch)


def _init(client, payload=None):
    return client.client.post("/api/init", json=payload or INIT_PAYLOAD)


# ── /api/init ──

def test_init_sets_up_world_and_characters(client):
    resp = _init(client)
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["status"] == "ok"
    engine = client.engine
    assert engine.world is not None
    assert engine.world.config.name == "测试世界"
    assert len(engine._characters) == 1
    assert engine._characters[0].name == "林凡"
    # 引擎配置被应用
    assert engine.config.total_chapters == 20
    assert engine.config.ticks_per_chapter == 3
    # 旧大纲被清除 + 自动保存
    assert engine.outline_data is None
    assert client.ns["_outlines"]["auto"] is None
    assert "auto" in engine.saved


# ── /api/state ──

def test_state_not_initialized(client):
    resp = client.client.get("/api/state")
    assert resp.get_json()["status"] == "not_initialized"


def test_state_ok_after_init(client):
    _init(client)
    resp = client.client.get("/api/state")
    data = resp.get_json()
    assert data["status"] == "ok"
    assert "state" in data


# ── /api/chapter 前置校验 ──

def test_chapter_requires_init(client, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    resp = client.client.post("/api/chapter", json={})
    assert resp.status_code == 400
    assert "未初始化" in resp.get_json()["error"]


def test_chapter_requires_valid_api_key(client, monkeypatch):
    _init(client)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    resp = client.client.post("/api/chapter", json={})
    assert resp.status_code == 401
    assert "API Key" in resp.get_json()["error"]


def test_chapter_rejects_placeholder_api_key(client, monkeypatch):
    _init(client)
    monkeypatch.setenv("OPENAI_API_KEY", "your_api_key_here")
    resp = client.client.post("/api/chapter", json={})
    assert resp.status_code == 401


# ── /api/chapter 生成行为 ──

def test_chapter_generates_with_explicit_title(client, monkeypatch):
    _init(client)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    resp = client.client.post("/api/chapter", json={"title": "风起云涌"})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["status"] == "ok"
    assert data["chapter"]["title"] == "风起云涌"
    assert len(client.engine.chapters) == 1
    assert client.engine.run_chapter_calls[0]["title"] == "风起云涌"


def test_chapter_title_derived_from_outline(client, monkeypatch):
    _init(client)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    # 设置 AI 格式大纲：第 1 章规划标题为"初入江湖"
    client.engine.outline_data = {"volumes": [
        {"name": "第一卷", "theme": "崛起", "chapters": [
            {"title": "初入江湖", "summary": "主角下山历练"},
            {"title": "初露锋芒", "summary": "比武扬名"},
        ]},
    ]}
    resp = client.client.post("/api/chapter", json={"title": ""})
    assert resp.status_code == 200
    assert client.engine.run_chapter_calls[0]["title"] == "初入江湖"


def test_chapter_title_fallback_to_number(client, monkeypatch):
    _init(client)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    resp = client.client.post("/api/chapter", json={"title": ""})
    assert resp.status_code == 200
    # 无大纲时回退为 "第N章"
    assert client.engine.run_chapter_calls[0]["title"] == "第1章"


def test_chapter_injects_outline_context(client, monkeypatch):
    _init(client)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    engine = client.engine
    # AI 格式大纲（章节规划）
    engine.outline_data = {"volumes": [
        {"name": "第一卷", "theme": "崛起", "chapters": [
            {"title": "初入江湖", "summary": "主角下山历练"},
            {"title": "初露锋芒", "summary": "比武扬名"},
        ]},
    ]}
    # OutlineManager 卷纲（卷主题/关键事件），章节 1、2 归入第 1 卷
    client.ns["outline_manager"].set_volumes([{
        "index": 0, "title": "第一卷", "start_chapter": 1, "end_chapter": 2,
        "outline": {"theme": "崛起", "summary": "主角崛起",
                    "key_events": ["下山"], "character_arcs": ["成长"]},
    }])
    resp = client.client.post("/api/chapter", json={"title": ""})
    assert resp.status_code == 200
    ctx = engine.run_chapter_calls[0]["outline_context"]
    assert "【卷主题】崛起" in ctx
    assert "【本章规划标题】初入江湖" in ctx
    assert "【本章规划内容】主角下山历练" in ctx
    # 附上下一章走向，便于衔接
    assert "【下一章走向】比武扬名" in ctx


def test_chapter_maps_exception_to_500(client, monkeypatch):
    _init(client)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    client.engine.run_chapter_error = RuntimeError("模型调用超时")
    resp = client.client.post("/api/chapter", json={})
    assert resp.status_code == 500
    assert "模型调用超时" in resp.get_json()["error"]


def test_chapter_maps_auth_error_to_401(client, monkeypatch):
    _init(client)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    client.engine.run_chapter_error = RuntimeError("invalid api key provided")
    resp = client.client.post("/api/chapter", json={})
    assert resp.status_code == 401


# ── /api/chapters 标题回填 ──

def test_chapters_backfills_empty_title(client):
    _init(client)
    client.engine.chapters = [{"chapter": 1, "title": "", "narrative": "正文"}]
    client.engine.outline_data = {"volumes": [
        {"name": "第一卷", "theme": "崛起", "chapters": [
            {"title": "初入江湖", "summary": "s"},
        ]},
    ]}
    resp = client.client.get("/api/chapters")
    chs = resp.get_json()["chapters"]
    assert chs[0]["title"] == "初入江湖"


# ── /api/add-character ──

def test_add_character_requires_init(client):
    resp = client.client.post("/api/add-character", json={"name": "新人"})
    assert resp.status_code == 400


def test_add_character_requires_name(client):
    _init(client)
    resp = client.client.post("/api/add-character", json={"name": ""})
    assert resp.status_code == 400


def test_add_character_rejects_duplicate(client):
    _init(client)
    resp = client.client.post("/api/add-character", json={"name": "林凡"})
    assert resp.status_code == 400
    assert "已存在" in resp.get_json()["error"]


def test_add_character_success(client):
    _init(client)
    client.engine._nw_world = FakeNWWorld()
    resp = client.client.post("/api/add-character",
                              json={"name": "苏婉", "gender": "女", "age": 17})
    assert resp.status_code == 200
    assert resp.get_json()["status"] == "ok"
    # backend 层角色已注册
    assert any(c.name == "苏婉" for c in client.engine._characters)
    # novel_world 层角色已注册
    assert any(c.name == "苏婉" for c in client.engine._nw_characters)


# ── /api/guide-plot ──

def test_guide_plot_inject_event(client):
    _init(client)
    resp = client.client.post("/api/guide-plot",
                              json={"type": "inject_event", "description": "天降流星"})
    assert resp.status_code == 200
    assert client.engine.current_chapter_events == ["天降流星"]
    # 世界事件与角色记忆都已写入
    assert client.engine.world.events[-1]["description"] == "天降流星"
    char = client.engine._characters[0]
    assert any("天降流星" in m["content"] for m in char.memory)


def test_guide_plot_inject_event_requires_description(client):
    _init(client)
    resp = client.client.post("/api/guide-plot", json={"type": "inject_event"})
    assert resp.status_code == 400


def test_guide_plot_add_goal(client):
    _init(client)
    resp = client.client.post("/api/guide-plot",
                              json={"type": "add_goal", "name": "林凡", "goal": "寻找神器"})
    assert resp.status_code == 200
    char = client.engine._characters[0]
    assert any(g.content == "寻找神器" for g in char.short_term_goals)


def test_guide_plot_add_goal_unknown_character(client):
    _init(client)
    resp = client.client.post("/api/guide-plot",
                              json={"type": "add_goal", "name": "不存在", "goal": "x"})
    assert resp.status_code == 404


def test_guide_plot_modify_character_mood(client):
    _init(client)
    resp = client.client.post("/api/guide-plot",
                              json={"type": "modify_character", "name": "林凡",
                                    "field": "mood", "value": "愤怒"})
    assert resp.status_code == 200
    assert client.engine._characters[0].current_mood == "愤怒"


def test_guide_plot_modify_character_position(client):
    _init(client)
    resp = client.client.post("/api/guide-plot",
                              json={"type": "modify_character", "name": "林凡",
                                    "field": "position", "value": "青云山"})
    assert resp.status_code == 200
    assert client.engine.world.get_character_position("林凡") == "青云山"


def test_guide_plot_unsupported_type(client):
    _init(client)
    resp = client.client.post("/api/guide-plot", json={"type": "unknown"})
    assert resp.status_code == 400


# ── /api/chapter/<index> 删除 / 编辑 ──

def _seed_chapters(engine, n):
    engine.chapters = [
        {"chapter": i + 1, "title": f"第{i+1}章", "narrative": f"正文{i+1}"}
        for i in range(n)
    ]


def test_delete_chapter_renumbers(client):
    _init(client)
    _seed_chapters(client.engine, 3)
    resp = client.client.delete("/api/chapter/1")
    assert resp.status_code == 200
    assert resp.get_json()["removed_title"] == "第2章"
    chs = client.engine.chapters
    assert len(chs) == 2
    # 删除后重新编号为连续的 1、2
    assert [c["chapter"] for c in chs] == [1, 2]
    assert [c["title"] for c in chs] == ["第1章", "第3章"]


def test_delete_chapter_out_of_range(client):
    _init(client)
    _seed_chapters(client.engine, 1)
    resp = client.client.delete("/api/chapter/5")
    assert resp.status_code == 404


def test_edit_chapter_title_and_narrative(client):
    _init(client)
    _seed_chapters(client.engine, 1)
    resp = client.client.put("/api/chapter/0",
                             json={"title": "新标题", "narrative": "新正文"})
    assert resp.status_code == 200
    ch = client.engine.chapters[0]
    assert ch["title"] == "新标题"
    assert ch["narrative"] == "新正文"


def test_edit_chapter_out_of_range(client):
    _init(client)
    _seed_chapters(client.engine, 1)
    resp = client.client.put("/api/chapter/9", json={"title": "x"})
    assert resp.status_code == 404


# ── 版本历史 / 回滚 ──

def test_version_history_save_and_get(client):
    _init(client)
    _seed_chapters(client.engine, 1)
    r1 = client.client.post("/api/chapter/0/history")
    assert r1.status_code == 200
    assert r1.get_json()["version_count"] == 1
    # 再次保存生成第 2 个版本
    r2 = client.client.post("/api/chapter/0/history")
    assert r2.get_json()["version_count"] == 2
    hist = client.client.get("/api/chapter/0/history").get_json()
    assert len(hist["versions"]) == 2


def test_version_history_caps_at_10(client):
    _init(client)
    _seed_chapters(client.engine, 1)
    for _ in range(12):
        client.client.post("/api/chapter/0/history")
    hist = client.client.get("/api/chapter/0/history").get_json()
    assert len(hist["versions"]) == 10


def test_rollback_restores_previous_version(client):
    _init(client)
    _seed_chapters(client.engine, 1)   # narrative = "正文1"
    # 保存当前版本（正文1）
    client.client.post("/api/chapter/0/history")
    # 修改为新正文
    client.client.put("/api/chapter/0", json={"narrative": "新正文"})
    # 回滚应恢复到保存的"正文1"
    resp = client.client.post("/api/chapter/0/rollback")
    assert resp.status_code == 200
    assert client.engine.chapters[0]["narrative"] == "正文1"


def test_rollback_without_history(client):
    _init(client)
    _seed_chapters(client.engine, 1)
    resp = client.client.post("/api/chapter/0/rollback")
    assert resp.status_code == 400
    assert "没有历史版本" in resp.get_json()["error"]
