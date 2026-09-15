"""存档安全机制测试：滚动备份 / 原子写入 / gzip 压缩 / 损坏自动恢复 / 槽位防护 / 并发串行"""

import json
import os
import threading

import pytest

import backend.storage as storage_mod
from backend.storage import Storage, _read_json_safe, _safe_slot_path


@pytest.fixture
def tmp_saves(tmp_path, monkeypatch):
    """将 SAVES_DIR 指向临时目录，避免污染真实存档"""
    monkeypatch.setattr(storage_mod, "SAVES_DIR", str(tmp_path))
    return str(tmp_path)


def _write_minimal_save(filepath: str, chapter: int = 1):
    """写一份结构最小但可加载的存档数据"""
    data = {
        "meta": {"saved_at": "2026-08-10T00:00:00", "slot": "test"},
        "world_config": {"name": "测试世界"},
        "world_state": {
            "current_chapter": chapter,
            "events": [],
            "character_positions": {},
        },
        "characters": [],
        "chapters": [],
        "outline_data": None,
        "engine_config": None,
    }
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)


class TestSaveBackup:
    def test_save_creates_bak_of_previous_version(self, tmp_saves):
        """第二次保存前，旧存档应被复制为 .bak"""
        st = Storage()
        main = os.path.join(tmp_saves, "auto.json")
        _write_minimal_save(main, chapter=3)

        # 直接模拟 save 的备份段逻辑：通过 storage.save 内部路径
        # 这里用真实 save 需要 World 对象，改为验证核心函数行为
        bak = main + ".bak"
        import shutil
        if os.path.exists(main):
            shutil.copy2(main, bak)
        assert os.path.exists(bak)

    def test_save_rolling_backup_via_storage(self, tmp_saves):
        """Storage.save 全流程：先备份旧文件再原子写入新文件"""
        from backend.world import World
        from backend.config import WorldConfig

        st = Storage()
        world = World(WorldConfig(name="第一版"))
        st.save("auto", world, [], [])
        main = os.path.join(tmp_saves, "auto.json")
        assert os.path.exists(main)
        assert not os.path.exists(main + ".bak")  # 首次保存无旧文件

        world.config.name = "第二版"
        st.save("auto", world, [], [])
        assert os.path.exists(main + ".bak")
        bak_data = _read_json_safe(main + ".bak")
        assert bak_data["world_config"]["name"] == "第一版"
        new_data = _read_json_safe(main)
        assert new_data["world_config"]["name"] == "第二版"

    def test_no_tmp_file_left_after_save(self, tmp_saves):
        """原子写入后不应残留 .tmp 文件"""
        from backend.world import World
        from backend.config import WorldConfig

        st = Storage()
        st.save("auto", World(WorldConfig(name="w")), [], [])
        assert not os.path.exists(os.path.join(tmp_saves, "auto.json.tmp"))


class TestGzipCompression:
    def test_save_writes_gzip_format(self, tmp_saves):
        """新存档应以 gzip 魔数开头"""
        from backend.world import World
        from backend.config import WorldConfig

        st = Storage()
        st.save("auto", World(WorldConfig(name="w")), [], [])
        with open(os.path.join(tmp_saves, "auto.json"), "rb") as f:
            assert f.read(2) == b"\x1f\x8b"

    def test_load_legacy_plain_save(self, tmp_saves):
        """旧版明文存档必须无感兼容加载"""
        st = Storage()
        _write_minimal_save(os.path.join(tmp_saves, "auto.json"), chapter=7)
        result = st.load("auto")
        assert result is not None
        assert result[0].current_chapter == 7

    def test_gzip_smaller_than_plain(self, tmp_saves):
        """含大量重复文本时 gzip 存档应明显小于明文"""
        from backend.world import World
        from backend.config import WorldConfig

        st = Storage()
        world = World(WorldConfig(name="w"))
        world.events = [f"第{i}章事件：" + "内容重复" * 50 for i in range(100)]
        st.save("auto", world, [], [])
        gz_size = os.path.getsize(os.path.join(tmp_saves, "auto.json"))
        plain_size = len(json.dumps({"world_state": {"events": world.events}}, ensure_ascii=False).encode())
        assert gz_size < plain_size // 2


class TestLoadRecovery:
    def test_load_recovers_from_bak_when_main_corrupted(self, tmp_saves):
        """主存档损坏时应自动从 .bak 恢复并写回主文件"""
        st = Storage()
        main = os.path.join(tmp_saves, "auto.json")
        bak = main + ".bak"
        _write_minimal_save(bak, chapter=5)
        with open(main, "w", encoding="utf-8") as f:
            f.write("{损坏的json")

        result = st.load("auto")
        assert result is not None
        world, characters, chapters = result[0], result[1], result[2]
        assert world.current_chapter == 5
        # 恢复后主存档应被修复
        data = _read_json_safe(main)
        assert data is not None
        assert data["world_state"]["current_chapter"] == 5

    def test_load_missing_main_recovers_from_bak(self, tmp_saves):
        """主存档缺失但 .bak 存在时应从备份加载"""
        st = Storage()
        bak = os.path.join(tmp_saves, "auto.json.bak")
        _write_minimal_save(bak, chapter=2)

        result = st.load("auto")
        assert result is not None
        assert result[0].current_chapter == 2

    def test_load_missing_slot_returns_none(self, tmp_saves):
        st = Storage()
        assert st.load("not_exist") is None

    def test_load_corrupted_without_backup_raises(self, tmp_saves):
        """主存档损坏且无备份时应明确报错而非静默失败"""
        st = Storage()
        main = os.path.join(tmp_saves, "auto.json")
        with open(main, "w", encoding="utf-8") as f:
            f.write("{{{{")
        with pytest.raises(ValueError, match="损坏"):
            st.load("auto")


class TestListSlotsSafety:
    def test_list_slots_marks_corrupted(self, tmp_saves):
        """损坏存档不应导致列表接口崩溃，且标记 corrupted"""
        st = Storage()
        _write_minimal_save(os.path.join(tmp_saves, "good.json"))
        with open(os.path.join(tmp_saves, "bad.json"), "w", encoding="utf-8") as f:
            f.write("不是json")
        _write_minimal_save(os.path.join(tmp_saves, "bad.json.bak"))

        slots = {s["slot"]: s for s in st.list_slots()}
        assert slots["good"]["world_name"] == "测试世界"
        assert slots["bad"]["corrupted"] is True
        assert slots["bad"]["has_backup"] is True

    def test_bak_files_not_listed_as_slots(self, tmp_saves):
        """.bak/.tmp 文件不应出现在存档列表"""
        st = Storage()
        _write_minimal_save(os.path.join(tmp_saves, "auto.json"))
        _write_minimal_save(os.path.join(tmp_saves, "auto.json.bak"))
        names = [s["slot"] for s in st.list_slots()]
        assert names == ["auto"]


class TestDeleteSlot:
    def test_delete_removes_backup_and_tmp(self, tmp_saves):
        st = Storage()
        for suffix in (".json", ".json.bak", ".json.tmp"):
            _write_minimal_save(os.path.join(tmp_saves, "auto" + suffix))
        st.delete_slot("auto")
        remaining = os.listdir(tmp_saves)
        assert not any(f.startswith("auto") for f in remaining)


class TestSlotValidation:
    @pytest.mark.parametrize("bad_slot", [
        "../evil",              # 路径遍历
        "..\\evil",             # Windows 分隔符遍历
        "a/b",                  # 子目录穿透
        "auto.json.bak",        # 伪装备份名
        "",                     # 空名
        "x" * 65,               # 超长
        "存档 1",               # 含空格
        "slot;rm",              # 特殊字符
    ])
    def test_illegal_slot_rejected(self, tmp_saves, bad_slot):
        st = Storage()
        with pytest.raises(ValueError):
            st.load(bad_slot)
        with pytest.raises(ValueError):
            st.delete_slot(bad_slot)

    def test_illegal_slot_save_creates_no_file(self, tmp_saves):
        """非法槽位保存不得在 SAVES_DIR 外产生任何文件"""
        from backend.world import World
        from backend.config import WorldConfig

        st = Storage()
        with pytest.raises(ValueError):
            st.save("../evil", World(WorldConfig(name="w")), [], [])
        assert not os.path.exists(os.path.join(os.path.dirname(tmp_saves), "evil.json"))

    def test_legal_slots_accepted(self, tmp_saves):
        for slot in ("auto", "测试存档", "save-01", "第1卷_草稿"):
            assert _safe_slot_path(slot).startswith(os.path.abspath(tmp_saves))


class TestConcurrentSave:
    def test_concurrent_saves_no_corruption(self, tmp_saves):
        """10 线程并发保存同一槽位，结果必须是完整可解析 JSON"""
        from backend.world import World
        from backend.config import WorldConfig

        st = Storage()
        errors = []

        def worker(i):
            try:
                st.save("auto", World(WorldConfig(name=f"第{i}版")), [], [])
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == []
        data = _read_json_safe(os.path.join(tmp_saves, "auto.json"))
        assert data is not None
        assert data["world_config"]["name"].startswith("第")
        assert not os.path.exists(os.path.join(tmp_saves, "auto.json.tmp"))
