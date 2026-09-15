#!/usr/bin/env python3
"""
test_outline_api.py — 大纲管理聚焦测试（api/outline_api.py）。

通过 exec 注入命名空间加载 outline_api.py（与 app.py 相同的装配机制），
使用 FakeEngine + 假 chat 隔离真实引擎/AI 调用，验证关键行为路径：
- AI 格式 <-> OutlineManager 格式的归一化转换（兼容旧存档）
- GET /api/outline 未初始化拦截、格式归一化、outline_manager 重建
- PUT /api/outline 保存并同步双份数据
- 卷的添加/删除
- Markdown 大纲落盘保存
- _generate_outline_batch 的 JSON 解析/修复/分批提示
- /api/outline/generate 单批/分批编排、API Key 校验
- /api/outline/continue 续写扩容并重置终局锁
- /api/outline/summaries/regenerate 摘要回填
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

from backend.outline_system import OutlineManager
import backend.ai_client as ai_client_mod

API_FILE = os.path.join(PROJECT_ROOT, "api", "outline_api.py")
with open(API_FILE, "r", encoding="utf-8") as f:
    OUTLINE_API_SRC = f.read()


# ── 测试替身 ──

class FakeWorldConfig:
    def to_prompt_text(self):
        return "世界设定文本"


class FakeWorld:
    def __init__(self):
        self.config = FakeWorldConfig()


class FakeChar:
    def __init__(self, name):
        self.name = name
        self.config = SimpleNamespace(gender="男", age=20, identity="少年")
        self.long_term_goal = SimpleNamespace(description="成为强者")


class FakeOutlineEngine:
    def __init__(self, initialized=True):
        self.world = FakeWorld() if initialized else None
        self._characters = [FakeChar("林凡")] if initialized else []
        self.config = SimpleNamespace(total_chapters=5)
        self.chapters = []
        self.outline_data = None
        self._novel_finalized = True


def build_client(frontend_dir, initialized=True):
    app = Flask(__name__)
    engine = FakeOutlineEngine(initialized=initialized)
    ns = {
        "app": app,
        "_engine_lock": threading.Lock(),
        "request": request,
        "jsonify": jsonify,
        "os": os,
        "json": json,
        "engine": engine,
        "outline_manager": OutlineManager(),
        "FRONTEND_DIR": frontend_dir,
    }
    exec(compile(OUTLINE_API_SRC, API_FILE, "exec"), ns)
    app.config["TESTING"] = True
    return app.test_client(), engine, ns


def make_outline_json(num_volumes, chapters_per_volume, name_offset=0):
    """构造 AI 生成大纲的 JSON 响应"""
    volumes = []
    for vi in range(num_volumes):
        chapters = [
            {"title": f"c{vi}_{ci}", "summary": f"s{vi}_{ci}"}
            for ci in range(chapters_per_volume)
        ]
        volumes.append({
            "name": f"第{name_offset + vi + 1}卷",
            "theme": f"主题{vi + 1}",
            "chapters": chapters,
        })
    return json.dumps({"volumes": volumes}, ensure_ascii=False)


def fake_chat_factory(responses):
    """按顺序返回预设响应的 chat 替身"""
    calls = []

    def fake_chat(system_prompt=None, user_prompt=None, temperature=None,
                  max_tokens=None, task=None, **kwargs):
        calls.append({"user_prompt": user_prompt, "system_prompt": system_prompt})
        if not responses:
            raise AssertionError("chat 调用次数超出预设")
        return responses.pop(0)

    fake_chat.calls = calls
    return fake_chat


@pytest.fixture
def ctx(tmp_path, monkeypatch):
    frontend_dir = str(tmp_path / "frontend")
    os.makedirs(frontend_dir, exist_ok=True)
    client, engine, ns = build_client(frontend_dir)
    return SimpleNamespace(client=client, engine=engine, ns=ns,
                           tmp_path=tmp_path, monkeypatch=monkeypatch)


# ── 格式归一化工具函数 ──

def test_is_ai_format_volume(ctx):
    fn = ctx.ns["_is_ai_format_volume"]
    # AI 格式：chapters 为 dict 列表
    assert fn({"name": "卷一", "chapters": [{"title": "x"}]}) is True
    # AI 格式：只有 name，无 outline
    assert fn({"name": "卷一"}) is True
    # OutlineManager 格式：chapters 为章节号列表 + 有 outline
    assert fn({"title": "卷一", "outline": {"summary": "s"}, "chapters": [1, 2]}) is False
    # 非 dict
    assert fn("not a dict") is False


def test_om_volume_to_ai(ctx):
    fn = ctx.ns["_om_volume_to_ai"]
    om = {
        "title": "卷一", "start_chapter": 1, "end_chapter": 2,
        "outline": {"theme": "崛起", "summary": "概要",
                    "key_events": ["事件A", "事件B"], "character_arcs": []},
    }
    ai = fn(om)
    assert ai["name"] == "卷一"
    assert ai["theme"] == "崛起"
    assert [c["title"] for c in ai["chapters"]] == ["事件A", "事件B"]

    # outline 为字符串时作为 summary
    ai2 = fn({"title": "卷二", "outline": "纯文本概要"})
    assert ai2["theme"] == "纯文本概要"

    # 无 key_events 时用 start/end 推断章节数
    ai3 = fn({"title": "卷三", "start_chapter": 1, "end_chapter": 3, "outline": {}})
    assert len(ai3["chapters"]) == 3


def test_normalize_ai_volumes_mixed(ctx):
    fn = ctx.ns["_normalize_ai_volumes"]
    ai_vol = {"name": "卷一", "theme": "t", "chapters": [{"title": "a", "summary": "b"}]}
    om_vol = {"title": "卷二", "start_chapter": 2, "end_chapter": 2,
              "outline": {"theme": "t2", "key_events": ["事件X"]}}
    result = fn([ai_vol, om_vol, "garbage", None])
    assert len(result) == 2
    assert result[0]["name"] == "卷一"
    assert result[1]["name"] == "卷二"  # OM 格式被转为 AI 格式


def test_ai_to_om_volumes_cumulative_chapters(ctx):
    fn = ctx.ns["_ai_to_om_volumes"]
    volumes = [
        {"name": "卷一", "theme": "t1", "chapters": [{"title": "a"}, {"title": "b"}]},
        {"name": "卷二", "theme": "t2", "chapters": [{"title": "c"}, {"title": "d"}, {"title": "e"}]},
    ]
    om = fn(volumes)
    assert len(om) == 2
    assert (om[0]["start_chapter"], om[0]["end_chapter"]) == (1, 2)
    assert (om[1]["start_chapter"], om[1]["end_chapter"]) == (3, 5)
    assert om[0]["outline"]["key_events"] == ["a", "b"]
    assert om[1]["outline"]["theme"] == "t2"


# ── GET /api/outline ──

def test_get_outline_requires_init(tmp_path):
    client, engine, ns = build_client(str(tmp_path), initialized=False)
    resp = client.get("/api/outline")
    assert resp.status_code == 400
    assert "未初始化" in resp.get_json()["error"]


def test_get_outline_returns_normalized_and_rebuilds_manager(ctx):
    # engine.outline_data 为 AI 格式，但 outline_manager 为空（模拟重启后）
    ctx.engine.outline_data = {"volumes": [
        {"name": "卷一", "theme": "崛起", "chapters": [
            {"title": "c1", "summary": "s1"}, {"title": "c2", "summary": "s2"},
        ]},
    ]}
    resp = ctx.client.get("/api/outline")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["status"] == "ok"
    # outline_manager 从 outline_data 重建
    vols = ctx.ns["outline_manager"].get_volumes()
    assert len(vols) == 1
    assert vols[0]["title"] == "卷一"
    assert vols[0]["chapters"] == [1, 2]


def test_get_outline_normalizes_om_format(ctx):
    # 旧存档的 OutlineManager 格式应被归一化为 AI 格式返回
    ctx.engine.outline_data = {"volumes": [
        {"title": "卷一", "start_chapter": 1, "end_chapter": 2,
         "outline": {"theme": "崛起", "key_events": ["事件A", "事件B"]},
         "chapters": [1, 2]},
    ]}
    resp = ctx.client.get("/api/outline")
    assert resp.status_code == 200
    outline = resp.get_json()["outline"]
    # 归一化后 chapters 为 dict 列表（AI 格式）
    assert isinstance(outline["volumes"][0]["chapters"][0], dict)
    assert outline["volumes"][0]["chapters"][0]["title"] == "事件A"


# ── PUT /api/outline ──

def test_put_outline_stores_and_syncs(ctx):
    payload = {"volumes": [
        {"name": "卷一", "theme": "崛起", "chapters": [
            {"title": "c1", "summary": "s1"}, {"title": "c2", "summary": "s2"},
        ]},
    ]}
    resp = ctx.client.put("/api/outline", json=payload)
    assert resp.status_code == 200
    # engine.outline_data 存 AI 格式
    assert ctx.engine.outline_data["volumes"][0]["name"] == "卷一"
    # outline_manager 同步
    vols = ctx.ns["outline_manager"].get_volumes()
    assert len(vols) == 1
    assert vols[0]["chapters"] == [1, 2]


# ── 卷的添加 / 删除 ──

def test_add_volume_requires_title(ctx):
    resp = ctx.client.post("/api/outline/volume", json={"title": ""})
    assert resp.status_code == 400


def test_add_and_delete_volume(ctx):
    r1 = ctx.client.post("/api/outline/volume", json={"title": "序幕"})
    assert r1.status_code == 200
    idx = r1.get_json()["volume_index"]
    assert ctx.ns["outline_manager"].get_volumes()[idx]["title"] == "序幕"

    r2 = ctx.client.delete(f"/api/outline/volume/{idx}")
    assert r2.status_code == 200
    # 删除不存在的卷返回 400
    r3 = ctx.client.delete("/api/outline/volume/99")
    assert r3.status_code == 400


# ── Markdown 保存 ──

def test_save_outline_markdown(ctx):
    md = "# 大纲\n## 第一卷\n内容..."
    resp = ctx.client.post("/api/outline/save", json={"outline_markdown": md})
    assert resp.status_code == 200
    save_path = os.path.join(str(ctx.tmp_path), "saves", "outline_edited.md")
    assert os.path.exists(save_path)
    with open(save_path, "r", encoding="utf-8") as f:
        assert f.read() == md


# ── _generate_outline_batch ──

def test_generate_batch_parses_json(ctx):
    fn = ctx.ns["_generate_outline_batch"]
    resp_json = make_outline_json(2, 2)
    chat = fake_chat_factory([resp_json])
    vols = fn(chat, "世界", "角色", volume_count=2, chapters_per_volume=2)
    assert len(vols) == 2
    assert vols[0]["name"] == "第1卷"


def test_generate_batch_extracts_json_from_noise(ctx):
    """AI 常在 JSON 前后夹带说明文字，应能提取。"""
    fn = ctx.ns["_generate_outline_batch"]
    noisy = "好的，以下是大纲：\n" + make_outline_json(1, 1) + "\n希望满意！"
    chat = fake_chat_factory([noisy])
    vols = fn(chat, "世界", "角色", volume_count=1, chapters_per_volume=1)
    assert len(vols) == 1


def test_generate_batch_repairs_unclosed_brace(ctx):
    fn = ctx.ns["_generate_outline_batch"]
    # AI 漏掉最外层对象的闭合括号（尾部噪声不含括号），应自动补全后解析成功
    broken = ('{"volumes": [{"name": "卷一", "theme": "t", '
              '"chapters": [{"title": "c", "summary": "s"}]}], '
              '"meta": {"n": 1} 以上是大纲')
    chat = fake_chat_factory([broken])
    vols = fn(chat, "世界", "角色", volume_count=1, chapters_per_volume=1)
    assert len(vols) == 1
    assert vols[0]["name"] == "卷一"


def test_generate_batch_empty_response_raises(ctx):
    fn = ctx.ns["_generate_outline_batch"]
    chat = fake_chat_factory([""])
    with pytest.raises(RuntimeError):
        fn(chat, "世界", "角色", volume_count=1, chapters_per_volume=1)


def test_generate_batch_no_json_raises(ctx):
    fn = ctx.ns["_generate_outline_batch"]
    chat = fake_chat_factory(["这里没有任何JSON内容"])
    with pytest.raises(RuntimeError):
        fn(chat, "世界", "角色", volume_count=1, chapters_per_volume=1)


def test_generate_batch_final_flag_in_prompt(ctx):
    """最后一批应携带收束主线的提示；分批应携带卷号区间。"""
    fn = ctx.ns["_generate_outline_batch"]
    chat = fake_chat_factory([make_outline_json(2, 1)])
    fn(chat, "世界", "角色", volume_count=2, chapters_per_volume=1,
       start_volume=6, is_final_batch=True, total_volumes=7)
    prompt = chat.calls[0]["user_prompt"]
    assert "最后一批" in prompt
    assert "第6~7卷" in prompt


# ── POST /api/outline/generate ──

def test_generate_requires_api_key(ctx, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    resp = ctx.client.post("/api/outline/generate", json={})
    assert resp.status_code == 401


def test_generate_requires_init(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    client, engine, ns = build_client(str(tmp_path), initialized=False)
    resp = client.post("/api/outline/generate", json={})
    assert resp.status_code == 400


def test_generate_single_batch(ctx, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    chat = fake_chat_factory([make_outline_json(2, 2)])
    monkeypatch.setattr(ai_client_mod, "chat", chat)
    resp = ctx.client.post("/api/outline/generate",
                           json={"volume_count": 2, "chapters_per_volume": 2})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["status"] == "ok"
    assert len(ctx.engine.outline_data["volumes"]) == 2
    # outline_manager 被填充且章节区间正确
    vols = ctx.ns["outline_manager"].get_volumes()
    assert len(vols) == 2
    assert len(chat.calls) == 1


def test_generate_multi_batch_splits(ctx, monkeypatch):
    """>5 卷时应分批生成（5 + 2），第二批携带前文上下文。"""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    responses = [make_outline_json(5, 1, name_offset=0),
                 make_outline_json(2, 1, name_offset=5)]
    chat = fake_chat_factory(responses)
    monkeypatch.setattr(ai_client_mod, "chat", chat)
    resp = ctx.client.post("/api/outline/generate",
                           json={"volume_count": 7, "chapters_per_volume": 1})
    assert resp.status_code == 200
    assert len(chat.calls) == 2
    assert len(ctx.engine.outline_data["volumes"]) == 7
    # 第二批 prompt 应包含前文大纲以衔接
    assert "已有前文大纲" in chat.calls[1]["user_prompt"]


# ── POST /api/outline/continue ──

def test_continue_expands_and_resets_finalization(ctx, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    # 已有 1 卷、计划 5 章、已终局
    ctx.engine.outline_data = {"volumes": [
        {"name": "卷一", "theme": "t", "chapters": [{"title": "c1", "summary": "s1"}]},
    ]}
    ctx.engine.config.total_chapters = 5
    ctx.engine._novel_finalized = True

    chat = fake_chat_factory([make_outline_json(1, 3, name_offset=1)])
    monkeypatch.setattr(ai_client_mod, "chat", chat)
    resp = ctx.client.post("/api/outline/continue",
                           json={"volume_count": 1, "chapters_per_volume": 3})
    assert resp.status_code == 200
    data = resp.get_json()
    # total_chapters 扩容 5 + 3 = 8
    assert ctx.engine.config.total_chapters == 8
    assert data["total_chapters"] == 8
    # 终局锁被重置
    assert ctx.engine._novel_finalized is False
    assert data["novel_finalized"] is False
    # 卷被追加（原 1 卷 + 新 1 卷）
    assert len(ctx.engine.outline_data["volumes"]) == 2
    # 新卷章节区间从第 6 章开始
    new_vol = ctx.ns["outline_manager"].get_volumes()[-1]
    assert new_vol["chapters"][0] == 6


def test_continue_requires_api_key(ctx, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    resp = ctx.client.post("/api/outline/continue", json={})
    assert resp.status_code == 401


# ── POST /api/outline/summaries/regenerate ──

def test_regenerate_summaries_requires_outline(ctx, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    ctx.engine.outline_data = None
    resp = ctx.client.post("/api/outline/summaries/regenerate", json={})
    assert resp.status_code == 400


def test_regenerate_summaries_noop_when_complete(ctx, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    ctx.engine.outline_data = {"volumes": [
        {"name": "卷一", "theme": "t", "chapters": [
            {"title": "c1", "summary": "已有摘要"},
        ]},
    ]}
    resp = ctx.client.post("/api/outline/summaries/regenerate", json={})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["filled"] == 0
    assert "无需重建" in data["message"]


def test_regenerate_summaries_fills_missing(ctx, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    ctx.engine.outline_data = {"volumes": [
        {"name": "卷一", "theme": "t", "chapters": [
            {"title": "c1", "summary": ""},           # 待补写
            {"title": "c2", "summary": "已有摘要"},    # 保留
        ]},
    ]}
    chat = fake_chat_factory([
        json.dumps({"chapters": [{"title": "c1", "summary": "补写的摘要"}]},
                   ensure_ascii=False),
    ])
    monkeypatch.setattr(ai_client_mod, "chat", chat)
    resp = ctx.client.post("/api/outline/summaries/regenerate", json={})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["filled"] == 1
    chs = ctx.engine.outline_data["volumes"][0]["chapters"]
    assert chs[0]["summary"] == "补写的摘要"
    assert chs[1]["summary"] == "已有摘要"  # 已有摘要不被覆盖
