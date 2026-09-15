"""碰撞引擎核心测试：目标对冲/目标-角色关联/感知对冲/权重排序/去重/序列化

全部离线运行（无 AI 客户端，叙事走模板降级）。
"""

import pytest

from novel_world.engine.collision.collision_engine import (
    CollisionEngine, CollisionEvent, EntryMotivation, EntryScene, ChapterTimeline,
)


class FakeWorld:
    """最小世界替身：仅提供地图尺寸与空地块"""

    def __init__(self, size=(50, 50)):
        self.map_size = size

    def get_tile(self, x, y):
        return None


class FakeChar:
    """最小角色替身"""

    def __init__(self, char_id, name, pos=(0, 0), goal="", skills=None, alive=True):
        self.id = char_id
        self.name = name
        self.pos = pos
        self.goal = goal
        self.skills = skills or []
        self.alive = alive


@pytest.fixture
def engine():
    """无 AI 客户端的碰撞引擎（叙事走模板降级）"""
    return CollisionEngine(world=FakeWorld())


class TestGoalCollision:
    def test_opposite_goals_trigger_collision(self, engine):
        """保护 vs 摧毁 → 目标对冲"""
        a = FakeChar("a", "林风", pos=(20, 0), goal="保护青云村")
        b = FakeChar("b", "血煞", pos=(24, 0), goal="摧毁青云村")
        event = engine.tick([a, b])
        assert event is not None
        assert event.collision_type == "目标对冲"
        assert "林风" in event.collision_reason or "血煞" in event.collision_reason

    def test_no_goal_no_collision_when_far(self, engine):
        """无目标且距离远 → 无碰撞"""
        a = FakeChar("a", "甲", pos=(0, 0))
        b = FakeChar("b", "乙", pos=(49, 49))
        assert engine.tick([a, b]) is None

    def test_goal_character_reference_high_weight(self, engine):
        """目标直接点名对方 → 目标-角色关联（最高权重）"""
        a = FakeChar("a", "叶凡", pos=(10, 0), goal="斩杀魔尊玄冥")
        b = FakeChar("b", "玄冥", pos=(14, 0), goal="吞噬叶凡魂魄")
        event = engine.tick([a, b])
        assert event is not None
        assert event.collision_subtype == "目标-角色关联"
        assert event.collision_weight >= 80

    def test_same_chapter_dedup_same_type(self, engine):
        """同章同对同类型碰撞只记录一次，第二次 tick 返回 None"""
        a = FakeChar("a", "林风", pos=(0, 0), goal="保护青云村")
        b = FakeChar("b", "血煞", pos=(49, 49), goal="摧毁青云村")
        first = engine.tick([a, b])
        assert first is not None
        # 保持距离避免接近碰撞，第二次同类型应被去重
        a.pos, b.pos = (0, 0), (49, 49)
        second = engine.tick([a, b])
        assert second is None
        assert len(engine.get_collision_history()) == 1


class TestGuardConditions:
    def test_empty_characters(self, engine):
        assert engine.tick([]) is None

    def test_single_character(self, engine):
        assert engine.tick([FakeChar("a", "独行侠")]) is None

    def test_dead_characters_excluded(self, engine):
        """存活角色不足两人 → 无碰撞"""
        a = FakeChar("a", "甲", goal="保护村子")
        b = FakeChar("b", "乙", goal="摧毁村子", alive=False)
        assert engine.tick([a, b]) is None


class TestPerceptionCollision:
    def test_perception_vs_stealth(self, engine):
        """感知技能 vs 隐匿技能 → 感知对冲"""
        a = FakeChar("a", "天眼者", pos=(10, 0), skills=["神识感知"])
        b = FakeChar("b", "影刺客", pos=(12, 0), skills=["隐匿遁形"])
        event = engine.tick([a, b])
        assert event is not None
        assert event.collision_type == "感知对冲"


class TestEventWeightAndNarrative:
    def test_narrative_template_without_ai(self, engine):
        """无 AI 客户端时叙事走模板，仍应非空"""
        a = FakeChar("a", "林风", pos=(20, 0), goal="保护青云村")
        b = FakeChar("b", "血煞", pos=(24, 0), goal="摧毁青云村")
        event = engine.tick([a, b])
        assert event.narrative.strip() != ""

    def test_stats_and_history(self, engine):
        a = FakeChar("a", "林风", pos=(20, 0), goal="保护青云村")
        b = FakeChar("b", "血煞", pos=(24, 0), goal="摧毁青云村")
        engine.tick([a, b])
        stats = engine.get_stats()
        assert stats["global_tick"] == 1
        assert stats["total_collisions"] == 1
        assert stats["collision_types"].get("目标对冲") == 1


class TestSerialization:
    def test_collision_event_roundtrip(self):
        ev = CollisionEvent(
            id="c1", tick=5,
            char_a_id="a", char_a_name="林风",
            char_b_id="b", char_b_name="血煞",
            collision_type="目标对冲",
            collision_subtype="目标-关键词",
            collision_reason="目标对立",
            collision_weight=50,
        )
        restored = CollisionEvent.from_dict(ev.to_dict())
        assert restored.char_a_name == "林风"
        assert restored.collision_type == "目标对冲"
        assert restored.collision_weight == 50

    def test_entry_scene_roundtrip(self):
        es = EntryScene(
            character_id="a", character_name="林风",
            entry_time=1, entry_motivation=EntryMotivation.GOAL_DRIVEN,
            private_purpose="复仇", independent_plot="暗线",
        )
        restored = EntryScene.from_dict(es.to_dict())
        assert restored.entry_motivation == EntryMotivation.GOAL_DRIVEN
        assert restored.private_purpose == "复仇"

    def test_chapter_timeline_roundtrip(self):
        tl = ChapterTimeline(chapter_num=3, prelude="风起", chapter_text="正文")
        restored = ChapterTimeline.from_dict(tl.to_dict())
        assert restored.chapter_num == 3
        assert restored.prelude == "风起"


class TestHistoryRingCap:
    def test_history_capped_at_max(self, engine):
        """碰撞历史环形上限：超出后只保留最近 N 条"""
        from novel_world.engine.collision import collision_engine as ce_mod
        cap = ce_mod._COLLISION_HISTORY_MAX
        for i in range(cap + 50):
            engine._record_history(CollisionEvent(id=f"e{i}"))
        assert len(engine._collision_history) == cap
        assert engine._collision_history[0].id == "e50"
        assert engine._collision_history[-1].id == f"e{cap + 49}"
        assert len(engine.get_collision_history()) == cap
