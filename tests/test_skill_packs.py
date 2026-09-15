#!/usr/bin/env python3
"""
test_skill_packs.py — 技能包系统单元测试。

测试覆盖：
- SkillPack 数据模型
- SkillPackManager CRUD
- novel_distill 蒸馏
- _sanitize_filename 消毒
"""
import sys
import os
import tempfile
import shutil

BACKEND = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend")
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)

from skill_packs import SkillPackManager, SkillPack, novel_distill, _sanitize_filename


def test_skill_pack_model():
    """SkillPack 数据模型构造正常。"""
    pack = SkillPack(
        id="test_001",
        name="测试技能",
        type="technique",
        description="用于测试的技能包",
        content="这是技能内容",
    )
    assert pack.id == "test_001"
    assert pack.name == "测试技能"
    assert pack.type == "technique"
    assert pack.created_at
    assert pack.updated_at
    d = pack.to_dict()
    assert d["id"] == "test_001"
    print("  ✓ SkillPack: 数据模型正常")


def test_manager_import_skill():
    """导入技能包并持久化。"""
    tmp = tempfile.mkdtemp()
    try:
        mgr = SkillPackManager(skills_dir=tmp)
        pack = mgr.import_skill({
            "id": "test_001",
            "name": "测试技能",
            "type": "technique",
            "description": "用于测试",
            "content": "技能内容正文",
        })
        assert pack.id == "test_001"
        assert os.path.exists(os.path.join(tmp, "test_001.json"))
        print("  ✓ SkillPackManager: 导入并持久化")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_manager_list_skills():
    """列出全部技能包。"""
    tmp = tempfile.mkdtemp()
    try:
        mgr = SkillPackManager(skills_dir=tmp)
        mgr.import_skill({"id": "a", "name": "A", "type": "technique",
                           "description": "d", "content": "c"})
        mgr.import_skill({"id": "b", "name": "B", "type": "character",
                           "description": "d", "content": "c"})
        skills = mgr.list_skills()
        assert len(skills) == 2
        print("  ✓ SkillPackManager: list_skills 正常")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_manager_search_skills():
    """按关键词搜索。"""
    tmp = tempfile.mkdtemp()
    try:
        mgr = SkillPackManager(skills_dir=tmp)
        mgr.import_skill({"id": "001", "name": "武侠打斗", "type": "technique",
                           "description": "武侠战斗描写", "content": "c"})
        mgr.import_skill({"id": "002", "name": "言情告白", "type": "technique",
                           "description": "感情戏", "content": "c"})
        results = mgr.search_skills(keyword="武侠")
        assert len(results) == 1
        assert results[0].name == "武侠打斗"
        print("  ✓ SkillPackManager: 关键词搜索")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_manager_search_by_type():
    """按类型过滤。"""
    tmp = tempfile.mkdtemp()
    try:
        mgr = SkillPackManager(skills_dir=tmp)
        mgr.import_skill({"id": "001", "name": "T", "type": "technique",
                           "description": "d", "content": "c"})
        mgr.import_skill({"id": "002", "name": "C", "type": "character",
                           "description": "d", "content": "c"})
        results = mgr.search_skills(skill_type="character")
        assert len(results) == 1
        assert results[0].type == "character"
        print("  ✓ SkillPackManager: 按类型过滤")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_manager_get_skill():
    """按 ID 获取。"""
    tmp = tempfile.mkdtemp()
    try:
        mgr = SkillPackManager(skills_dir=tmp)
        mgr.import_skill({"id": "001", "name": "T", "type": "technique",
                           "description": "d", "content": "c"})
        pack = mgr.get_skill("001")
        assert pack is not None
        assert pack.id == "001"
        assert mgr.get_skill("不存在") is None
        print("  ✓ SkillPackManager: get_skill")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_manager_delete_skill():
    """删除技能包。"""
    tmp = tempfile.mkdtemp()
    try:
        mgr = SkillPackManager(skills_dir=tmp)
        mgr.import_skill({"id": "001", "name": "T", "type": "technique",
                           "description": "d", "content": "c"})
        assert mgr.delete_skill("001") is True
        assert mgr.get_skill("001") is None
        assert mgr.delete_skill("不存在的") is False
        print("  ✓ SkillPackManager: delete_skill")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_manager_missing_field():
    """缺少必填字段应抛出 ValueError。"""
    tmp = tempfile.mkdtemp()
    try:
        mgr = SkillPackManager(skills_dir=tmp)
        try:
            mgr.import_skill({"id": "x", "name": "x"})
            assert False, "应抛出 ValueError"
        except ValueError:
            pass
        print("  ✓ SkillPackManager: 缺少必填字段抛出异常")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_novel_distill_markdown():
    """从 Markdown 小说蒸馏技能包。"""
    text = """
## 伏笔埋设技法
**说明**: 在平淡叙事中埋下伏笔
**用法**: 在看似无关的细节中植入关键信息，避免直接点明

## 悬念控制
描述: 通过延时满足制造悬念
示例: 先给出异常现象，延迟到2-3章后揭示原因
"""
    skills = novel_distill(text, skill_type="technique")
    assert len(skills) >= 2
    # 第一个技能
    assert skills[0]["type"] == "technique"
    assert "伏笔" in skills[0]["name"]
    assert skills[0]["id"].startswith("distill_")
    print(f"  ✓ novel_distill: 蒸馏 {len(skills)} 个技能包")


def test_novel_distill_empty():
    """空文本返回空列表。"""
    assert novel_distill("") == []
    assert novel_distill("没有标题的文本") == []
    print("  ✓ novel_distill: 空文本返回空")


def test_sanitize_filename():
    """文件名消毒。"""
    assert _sanitize_filename("正常文件名") == "正常文件名"
    assert _sanitize_filename("包含<>:\"|?*特殊字符") == "包含特殊字符"
    assert _sanitize_filename("a/b\\c") == "abc"
    assert _sanitize_filename("") == "unnamed"
    assert _sanitize_filename("   ") == "unnamed"
    print("  ✓ sanitize_filename: 消毒正常")


if __name__ == "__main__":
    print("=" * 50)
    print("  技能包系统单元测试")
    print("=" * 50)
    print()

    tests = [
        test_skill_pack_model,
        test_manager_import_skill,
        test_manager_list_skills,
        test_manager_search_skills,
        test_manager_search_by_type,
        test_manager_get_skill,
        test_manager_delete_skill,
        test_manager_missing_field,
        test_novel_distill_markdown,
        test_novel_distill_empty,
        test_sanitize_filename,
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
