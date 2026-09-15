#!/usr/bin/env python3
"""
test_e2e_flow.py — 主流程端到端冒烟（真实 Flask app + 真实引擎，隔离存档目录）。

历史教训：此前没有一条测试真实走通"init → state → 章节操作 → save/load"，
所有 bug 都是用户实际使用时才炸（走一步修一步）。本测试用真实 app.py 装配，
仅把存档目录重定向到临时目录，不调用任何真实 AI。

覆盖：
- /api/init 初始化世界与角色（纯本地，不触发 AI）
- /api/state 返回已初始化状态且字段齐全
- /api/chapters 返回 narrative 字段（前后端字段契约回归）
- /api/chapter/<index> 删除后章节号连续重排（跳号 bug 回归）
- /api/save + /api/load 存档往返一致性
- /api/load 不存在的槽位返回 404
"""
import os
import sys
import shutil
import tempfile

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import pytest

# ── 存档目录隔离：必须在 import app 之前重定向，防止污染用户真实存档 ──
_TMP_SAVES = tempfile.mkdtemp(prefix="e2e_saves_")

import backend.storage as _bstorage
import novel_world.engine.core.storage as _nstorage
from pathlib import Path

_bstorage.SAVES_DIR = _TMP_SAVES
_nstorage.SAVE_DIR = Path(_TMP_SAVES)
os.environ["NOVEL_WORLD_SAVE_DIR"] = _TMP_SAVES

import app as app_module  # noqa: E402

app = app_module.app
engine = app_module.engine

INIT_PAYLOAD = {
    "world": {"name": "E2E测试世界", "genre": "玄幻", "era": "古代",
              "description": "端到端冒烟测试"},
    "characters": [
        {"name": "测试主角", "gender": "男", "age": 18,
         "short_term_goals": ["活下去"], "long_term_goal": "登顶"},
    ],
    "engine_config": {"total_chapters": 5, "ticks_per_chapter": 2},
}


@pytest.fixture(scope="module")
def client():
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


@pytest.fixture(scope="module", autouse=True)
def cleanup():
    yield
    shutil.rmtree(_TMP_SAVES, ignore_errors=True)
    os.environ.pop("NOVEL_WORLD_SAVE_DIR", None)


def test_01_init(client):
    r = client.post("/api/init", json=INIT_PAYLOAD)
    assert r.status_code == 200, r.get_data(as_text=True)[:300]
    assert engine.world is not None
    assert len(engine._characters) == 1


def test_02_state_initialized(client):
    r = client.get("/api/state")
    data = r.get_json()
    assert data["status"] == "ok"
    state = data["state"]
    assert state["world"]["name"] == "E2E测试世界"
    assert state["engine"]["total_chapters"] == 5
    assert state["characters"][0]["name"] == "测试主角"


def test_03_chapters_contract(client):
    """章节列表字段契约：narrative/chapter/title（前端依赖）"""
    # 直接种 3 章（不触发 AI）
    engine.chapters.clear()
    for i in range(1, 4):
        engine.chapters.append({
            "chapter": i, "title": f"标题{i}", "narrative": f"正文{i}" * 30,
        })
    r = client.get("/api/chapters")
    chs = r.get_json()["chapters"]
    assert len(chs) == 3
    for i, ch in enumerate(chs, 1):
        assert ch["chapter"] == i
        assert ch["narrative"], "narrative 字段必须存在且非空"


def test_04_delete_renumbers_contiguous(client):
    """删除中间章节后编号必须连续重排（跳号 bug 回归）"""
    r = client.delete("/api/chapter/1")  # 删除第2章（索引1）
    assert r.status_code == 200
    nums = [c["chapter"] for c in engine.chapters]
    assert nums == [1, 2], f"删除后编号应连续重排，实际 {nums}"


def test_05_save_load_roundtrip(client):
    r = client.post("/api/save", json={"slot": "e2e_slot"})
    assert r.status_code == 200 and r.get_json()["status"] == "ok"

    # 破坏内存状态再从存档恢复
    engine.chapters.append({"chapter": 99, "title": "脏数据", "narrative": "x"})
    r = client.post("/api/load/e2e_slot")
    assert r.status_code == 200
    assert r.get_json()["status"] == "ok"
    nums = [c["chapter"] for c in engine.chapters]
    assert 99 not in nums, "load 后应恢复到存档状态"
    assert nums == [1, 2]


def test_06_load_missing_slot_404(client):
    r = client.post("/api/load/不存在的槽位xyz")
    assert r.status_code == 404


def test_07_saves_listed(client):
    r = client.get("/api/saves")
    slots = [s["slot"] for s in r.get_json()["saves"]]
    assert "e2e_slot" in slots
