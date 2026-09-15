#!/usr/bin/env python3
"""
test_dm_state.py — DM 状态机（DMController）聚焦测试。

测试覆盖（关键行为路径）：
- 状态转换合法性：IDLE → RUNNING ⇄ PAUSED → STOPPED
- 每章完成后自动暂停，等待用户确认（核心推演节奏）
- step_once 单步推进一章后回到 PAUSED
- stop 中断推演、reset 复位
- run_chapter 异常时回退 IDLE 并记录 last_error
- 从已生成章节数续写（进度不归零）
- DM 干预指令执行（modify_character/inject_event/force_move/add_goal）与干预日志
- 质量问题队列 add_issue / resolve_issue（含 pause 自动暂停）
"""
import os
import sys
import time
import types

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import pytest

from novel_world.engine.dm_state import DMController, DMState, InterruptedError


def wait_until(cond, timeout=5.0):
    """轮询等待条件成立（用于后台推演线程同步）"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if cond():
            return True
        time.sleep(0.01)
    return False


# ── 测试替身 ──

class FakeBackendWorld:
    def __init__(self, current_chapter=0):
        self.current_chapter = current_chapter
        self.positions = {}

    def set_character_position(self, name, loc):
        self.positions[name] = loc


class FakeChar:
    def __init__(self, name):
        self.name = name
        self.long_term_goal = types.SimpleNamespace(description="原目标")
        self.config = types.SimpleNamespace(personality="原性格")
        self.current_location = "青石镇"
        self.current_mood = "平静"
        self.added_goals = []

    def add_goal(self, description, priority=5):
        self.added_goals.append({"description": description, "priority": priority})


class FakeDMEngine:
    """模拟 EngineAdapter 中 DMController 依赖的接口"""

    def __init__(self, total_chapters=2, ticks_per_chapter=4):
        self.config = types.SimpleNamespace(
            total_chapters=total_chapters, ticks_per_chapter=ticks_per_chapter
        )
        self._backend_world = None
        self._nw_characters = []
        self.run_calls = []
        self.fail_on_call = None      # 第 N 次 run_chapter 时抛异常
        self.characters = {}
        self.injected_events = []

    def run_chapter(self, title, dm_controller=None):
        self.run_calls.append({"title": title, "dm_controller": dm_controller})
        if self.fail_on_call == len(self.run_calls):
            raise RuntimeError("推演异常")
        n = len(self.run_calls)
        return {"chapter": n, "title": title or f"第{n}章", "narrative": f"正文{n}"}

    def get_character(self, name):
        if name not in self.characters:
            raise KeyError(f"角色不存在: {name}")
        return self.characters[name]

    def inject_world_event(self, cmd):
        self.injected_events.append(cmd)


@pytest.fixture
def engine():
    return FakeDMEngine(total_chapters=3)


@pytest.fixture
def dm(engine):
    return DMController(engine)


# ── 状态转换 ──

def test_initial_state_is_idle(dm):
    """初始状态为 IDLE，进度与错误均为空。"""
    assert dm.state == DMState.IDLE
    state = dm.get_state()
    assert state["dm_state"] == "idle"
    assert state["current_chapter"] == 0
    assert state["has_result"] is False
    assert state["last_error"] is None


def test_invalid_transitions_from_idle(dm):
    """IDLE 状态下 pause/resume/step_once 均应拒绝。"""
    assert dm.pause() is False
    assert dm.resume() is False
    assert dm.step_once() is False
    assert dm.state == DMState.IDLE


def test_start_transitions_to_running_and_double_start_rejected(dm):
    """start 只能从 IDLE 发起；RUNNING 期间重复 start 被拒绝。"""
    assert dm.start("测试") is True
    # start 内同步置为 RUNNING，第二次 start 必然失败
    assert dm.start("再次启动") is False
    dm.stop()


def test_stop_from_any_state_and_reset(dm):
    """stop 在任意状态都成功；reset 将 STOPPED 复位为 IDLE 并清零进度。"""
    assert dm.stop() is True
    assert dm.state == DMState.STOPPED
    # STOPPED 后不能再 start / pause / resume
    assert dm.start() is False
    assert dm.pause() is False
    assert dm.resume() is False

    dm.current_tick = 5
    dm.current_chapter = 2
    dm.last_error = "旧错误"
    dm.reset()
    assert dm.state == DMState.IDLE
    assert dm.current_tick == 0
    assert dm.current_chapter == 0
    assert dm.last_error is None


def test_checkpoint_raises_after_stop(dm):
    """STOPPED 后检查点应抛出 InterruptedError。"""
    dm.stop()
    with pytest.raises(InterruptedError):
        dm._checkpoint()


# ── 推演主循环行为 ──

def test_run_pauses_after_each_chapter(dm, engine):
    """核心行为：每章完成后自动暂停，用户 resume 才继续下一章。"""
    assert dm.start("") is True

    # 第 1 章完成后自动暂停
    assert wait_until(lambda: dm.state == DMState.PAUSED and dm.current_chapter == 1)
    assert len(engine.run_calls) == 1
    assert dm.latest_chapter["chapter"] == 1

    # resume 后生成第 2 章，再次自动暂停
    assert dm.resume() is True
    assert wait_until(lambda: dm.state == DMState.PAUSED and dm.current_chapter == 2)
    assert len(engine.run_calls) == 2

    # 继续到第 3 章（total_chapters=3），完成后仍按"每章必暂停"等待确认
    assert dm.resume() is True
    assert wait_until(lambda: dm.state == DMState.PAUSED and dm.current_chapter == 3)
    assert len(engine.run_calls) == 3
    assert dm.latest_chapter["chapter"] == 3

    # 全部章节完成后再次继续 → 循环收尾回到 IDLE
    assert dm.resume() is True
    assert wait_until(lambda: dm.state == DMState.IDLE)
    assert dm.current_chapter == 3

    # get_state 应携带最新章节信息
    state = dm.get_state()
    assert state["dm_state"] == "idle"
    assert state["has_result"] is True
    assert state["chapter_number"] == 3
    assert state["total_chapters"] == 3


def test_pause_blocks_until_resume(dm, engine):
    """RUNNING 中 pause 生效：第 1 章完成后保持暂停，resume 才推进。"""
    dm.start("")
    assert wait_until(lambda: dm.state == DMState.PAUSED and dm.current_chapter == 1)

    # 暂停期间不应继续生成章节
    time.sleep(0.1)
    assert len(engine.run_calls) == 1
    assert dm.pause() is False        # 已暂停，重复 pause 拒绝
    assert dm.step_once() is True     # PAUSED 下允许单步

    # 单步执行第 2 章后应自动回到 PAUSED
    assert wait_until(lambda: dm.state == DMState.PAUSED and dm.current_chapter == 2)
    assert len(engine.run_calls) == 2

    dm.stop()


def test_stop_interrupts_running_loop(dm, engine):
    """stop 应终止后台推演循环。"""
    dm.start("")
    assert wait_until(lambda: dm.state == DMState.PAUSED and dm.current_chapter == 1)

    assert dm.stop() is True
    assert wait_until(lambda: dm.state == DMState.STOPPED)
    time.sleep(0.1)
    assert len(engine.run_calls) == 1   # 未继续生成第 2 章


def test_run_chapter_exception_falls_back_to_idle(dm, engine):
    """run_chapter 抛异常时：记录 last_error 并回到 IDLE（而非卡死）。"""
    engine.fail_on_call = 1
    dm.start("")
    assert wait_until(lambda: dm.state == DMState.IDLE and dm.last_error is not None)
    assert dm.last_error == "推演异常"
    assert dm.get_state()["last_error"] == "推演异常"


def test_start_continues_from_existing_chapters():
    """start 从已生成章节数续写，进度不归零重复计数。"""
    engine = FakeDMEngine(total_chapters=5)
    engine._backend_world = FakeBackendWorld(current_chapter=3)
    dm = DMController(engine)

    dm.start("")
    # 只需再生成 2 章（第4、5章）即完成，且每章完成后暂停
    assert wait_until(lambda: dm.state == DMState.PAUSED and dm.current_chapter == 4)
    assert dm.resume() is True
    assert wait_until(lambda: dm.state == DMState.PAUSED and dm.current_chapter == 5)
    # 末章确认后收尾回到 IDLE
    assert dm.resume() is True
    assert wait_until(lambda: dm.state == DMState.IDLE)
    assert len(engine.run_calls) == 2


# ── DM 干预指令 ──

def test_execute_modify_character_fields(dm, engine):
    """modify_character：支持 mood/target/personality/position 字段。"""
    char = FakeChar("林凡")
    engine.characters["林凡"] = char
    engine._backend_world = FakeBackendWorld()

    r = dm.execute_command({"type": "modify_character", "name": "林凡",
                            "field": "mood", "value": "愤怒"})
    assert r["success"] is True and char.current_mood == "愤怒"

    r = dm.execute_command({"type": "modify_character", "name": "林凡",
                            "field": "target", "value": "复仇"})
    assert r["success"] is True and char.long_term_goal.description == "复仇"

    r = dm.execute_command({"type": "modify_character", "name": "林凡",
                            "field": "personality", "value": "冷酷"})
    assert r["success"] is True and char.config.personality == "冷酷"

    r = dm.execute_command({"type": "modify_character", "name": "林凡",
                            "field": "position", "value": "青云山"})
    assert r["success"] is True
    assert char.current_location == "青云山"
    assert engine._backend_world.positions["林凡"] == "青云山"

    # 不支持的字段
    r = dm.execute_command({"type": "modify_character", "name": "林凡",
                            "field": "age", "value": 30})
    assert r["success"] is False


def test_execute_inject_event(dm, engine):
    """inject_event：转发到引擎并记入干预日志。"""
    cmd = {"type": "inject_event", "description": "天降异象"}
    r = dm.execute_command(cmd)
    assert r["success"] is True
    assert engine.injected_events == [cmd]


def test_execute_force_move(dm, engine):
    """force_move：支持坐标元组与中文括号字符串两种位置格式。"""
    char = FakeChar("林凡")
    engine.characters["林凡"] = char
    nw_char = types.SimpleNamespace(name="林凡", pos=(0, 0))
    engine._nw_characters = [nw_char]

    r = dm.execute_command({"type": "force_move", "name": "林凡", "position": (3, 4)})
    assert r["success"] is True
    assert char.current_location == (3, 4)
    assert nw_char.pos == (3, 4)

    r = dm.execute_command({"type": "force_move", "name": "林凡", "position": "（5,6）"})
    assert r["success"] is True
    assert nw_char.pos == (5, 6)


def test_execute_add_goal_weight_clamped(dm, engine):
    """add_goal：weight 映射到 1-10 的 priority 并做边界钳制。"""
    char = FakeChar("林凡")
    engine.characters["林凡"] = char

    dm.execute_command({"type": "add_goal", "name": "林凡", "goal": "寻宝", "weight": 3.0})
    dm.execute_command({"type": "add_goal", "name": "林凡", "goal": "小憩", "weight": 0.1})
    assert char.added_goals[0] == {"description": "寻宝", "priority": 10}  # 3.0*5=15 → 钳到10
    assert char.added_goals[1] == {"description": "小憩", "priority": 1}   # 0.1*5=0 → 钳到1


def test_execute_unknown_or_failing_command(dm, engine):
    """未知指令类型与执行异常都应返回 success=False（不抛出）。"""
    r = dm.execute_command({"type": "destroy_world"})
    assert r["success"] is False and "不支持" in r["error"]

    r = dm.execute_command({"type": "inject_event"})  # 缺少 description 仍可执行（默认空串）
    assert r["success"] is True

    r = dm.execute_command({"type": "modify_character", "name": "不存在",
                            "field": "mood", "value": "x"})
    assert r["success"] is False and r["error"]


def test_intervention_log_context_and_clear(dm, engine):
    """干预日志：记录指令、格式化为 prompt 上下文、可清空。"""
    assert dm.get_intervention_context() == ""

    dm.current_tick = 7
    dm.execute_command({"type": "inject_event", "description": "妖兽袭村"})
    char = FakeChar("林凡")
    engine.characters["林凡"] = char
    dm.execute_command({"type": "modify_character", "name": "林凡",
                        "field": "mood", "value": "紧张"})

    ctx = dm.get_intervention_context()
    assert "DM 干预记录" in ctx
    assert "妖兽袭村" in ctx
    assert "林凡" in ctx and "mood" in ctx

    dm.clear_interventions()
    assert dm.get_intervention_context() == ""


# ── 质量问题队列 ──

def test_issue_lifecycle(dm):
    """add_issue → pending → resolve 的完整生命周期。"""
    issue_id = dm.add_issue({
        "source": "timeline_checker",
        "severity": "blocker",
        "message": "时间线冲突：角色出现在两地",
    })
    assert issue_id

    issues = dm.get_pending_issues()
    assert len(issues) == 1
    entry = issues[0]
    assert entry["id"] == issue_id
    assert entry["type"] == "timeline_checker"
    assert entry["severity"] == "blocker"
    assert entry["status"] == "pending"

    # 不支持的动作被拒绝，状态不变
    assert dm.resolve_issue(issue_id, "delete_everything") is False
    assert dm.get_pending_issues()[0]["status"] == "pending"

    # 正常处理
    assert dm.resolve_issue(issue_id, "fix", resolved_by="tester") is True
    entry = dm.get_pending_issues()[0]
    assert entry["status"] == "resolved"
    assert entry["resolved_action"] == "fix"
    assert entry["resolved_by"] == "tester"
    assert entry["timestamp"]

    # 未知 id
    assert dm.resolve_issue("不存在", "fix") is False


def test_resolve_issue_with_pause_stops_running(dm):
    """action=pause 时，RUNNING 中的推演应被暂停。"""
    dm.state = DMState.RUNNING
    dm._resume_event.set()
    issue_id = dm.add_issue({"source": "power_check", "message": "战力越级"})

    assert dm.resolve_issue(issue_id, "pause") is True
    assert dm.state == DMState.PAUSED
    assert not dm._resume_event.is_set()
