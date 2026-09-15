# -*- coding: utf-8 -*-
"""
小说引擎统一门面 - NovelEngine

把所有模块（时间轴/泳道/目标/碰撞/一致性/规则守卫/分支）串起来，
提供一键初始化和统一的 advance_tick 流程。

使用方式：
    engine = NovelEngine()
    engine.init_with_defaults()
    engine.register_character("叶凡", entry_tick=0)
    engine.add_goal("叶凡", "修炼剑诀", GoalLevel.DAILY, tick=0)
    result = engine.advance_tick(scene="青云宗后山")
    print(result.collisions)
"""
import os
import json
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .scheduler import (
    WorldTimeline, SwimlaneManager, GoalScheduler, GoalLevel, GoalStatus,
    CausalCollisionScheduler, CollisionRecord,
    ConsistencyChecker, CheckLevel, ConsistencyIssue,
    WorldRuleGuard, GuardViolation,
    TimelineBranch,
)
from .graph.six_axis_graph import SixAxisGraph
from .memory.truth_ledger import TruthLedger
from .storage.vector_memory import VectorMemory


@dataclass
class TickResult:
    """单次 tick 推进的结果汇总"""
    tick_id: int = 0
    chapter: int = 0
    scene: str = ""
    new_goals: List = field(default_factory=list)
    deferred_goals: List[str] = field(default_factory=list)
    failed_goals: List[str] = field(default_factory=list)
    collisions: List[CollisionRecord] = field(default_factory=list)
    rule_violations: List[GuardViolation] = field(default_factory=list)
    consistency_issues: List[ConsistencyIssue] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "tick_id": self.tick_id,
            "chapter": self.chapter,
            "scene": self.scene,
            "new_goals_count": len(self.new_goals),
            "deferred_goals": self.deferred_goals,
            "failed_goals": self.failed_goals,
            "collisions_count": len(self.collisions),
            "collisions": [c.to_dict() for c in self.collisions],
            "rule_violations_count": len(self.rule_violations),
            "consistency_issues_count": len(self.consistency_issues),
            "has_error": any(i.level == CheckLevel.ERROR for i in self.consistency_issues),
        }


class NovelEngine:
    """小说引擎统一入口

    整合所有子模块，提供一站式的 tick 推进、角色管理、目标调度、
    碰撞检测、一致性校验和规则守卫能力。
    """

    def __init__(self):
        # 存储层
        self.graph: Optional[SixAxisGraph] = None
        self.truth_ledger: Optional[TruthLedger] = None
        self.vector_memory: Optional[VectorMemory] = None

        # 调度层
        self.timeline: Optional[WorldTimeline] = None
        self.swimlanes: Optional[SwimlaneManager] = None
        self.goals: Optional[GoalScheduler] = None

        # 管控层
        self.collision: Optional[CausalCollisionScheduler] = None
        self.consistency: Optional[ConsistencyChecker] = None
        self.rule_guard: Optional[WorldRuleGuard] = None

        # 四期
        self.branches: Optional[TimelineBranch] = None

        # 状态
        self._initialized = False
        self._project_dir: Optional[str] = None

    # ─── 初始化 ───

    def init_with_defaults(self, project_dir: str = None):
        """用默认配置初始化所有模块并串联依赖

        Args:
            project_dir: 项目目录（用于持久化，None 则仅内存运行）
        """
        self._project_dir = project_dir

        # 图
        self.graph = SixAxisGraph()

        # 存储（如果有项目目录则持久化）
        if project_dir:
            os.makedirs(project_dir, exist_ok=True)
            self.truth_ledger = TruthLedger(project_dir)
            vm_dir = os.path.join(project_dir, "vector_memory")
            self.vector_memory = VectorMemory(vm_dir)
        else:
            self.truth_ledger = None
            self.vector_memory = None

        # 调度层
        self.timeline = WorldTimeline()
        self.swimlanes = SwimlaneManager()
        self.goals = GoalScheduler()

        # 管控层
        self.collision = CausalCollisionScheduler()
        self.consistency = ConsistencyChecker()
        self.rule_guard = WorldRuleGuard()

        # 四期
        self.branches = TimelineBranch()

        # ─── 串联依赖 ───
        self.swimlanes.set_timeline(self.timeline)
        if self.vector_memory:
            self.swimlanes.set_vector_memory(self.vector_memory)

        self.goals.set_swimlane_manager(self.swimlanes)

        self.collision.set_graph(self.graph)
        self.collision.set_swimlane_manager(self.swimlanes)
        self.collision.set_timeline(self.timeline)
        if self.truth_ledger:
            self.collision.set_truth_ledger(self.truth_ledger)
        if self.vector_memory:
            self.collision.set_vector_memory(self.vector_memory)
        # 碰撞后自动过规则守卫
        self.collision.set_rule_guard(self.rule_guard)

        self.consistency.set_truth_ledger(self.truth_ledger)
        self.consistency.set_swimlane_manager(self.swimlanes)
        self.consistency.set_timeline(self.timeline)
        self.consistency.set_goal_scheduler(self.goals)
        self.consistency.set_graph(self.graph)
        self.consistency.set_rule_guard(self.rule_guard)

        if self.truth_ledger:
            self.rule_guard.set_truth_ledger(self.truth_ledger)

        self.branches.set_timeline(self.timeline)
        self.branches.set_swimlane_manager(self.swimlanes)
        self.branches.set_goal_scheduler(self.goals)
        self.branches.set_collision_scheduler(self.collision)
        if self.truth_ledger:
            self.branches.set_truth_ledger(self.truth_ledger)

        # 给 timeline 绑定引擎引用（用于 advance_tick 自动联动）
        self.timeline.set_engine(self)

        self._initialized = True
        return self

    # ─── 角色管理 ───

    def register_character(self, name: str, entry_tick: int = 0,
                           realm: str = "", location: str = ""):
        """注册一个角色（同时注册泳道和 TruthLedger）

        Args:
            name: 角色名
            entry_tick: 登场 tick
            realm: 境界/身份
            location: 初始位置
        """
        if not self._initialized:
            raise RuntimeError("引擎未初始化，请先调用 init_with_defaults()")

        # 泳道注册
        self.swimlanes.register_character(name, entry_tick=entry_tick)

        # TruthLedger 同步
        if self.truth_ledger:
            self.truth_ledger.update_character(
                name,
                chapter=0,
                lifecycle_stage="pending" if entry_tick > 0 else "active",
                realm=realm,
                location=location,
            )

        # 图节点（如果图里没有的话）
        if name not in self.graph.adj:
            pass  # 图节点按需添加，角色本身不自动加边

        return self

    # ─── 目标管理 ───

    def add_goal(self, character_name: str, content: str,
                 level: GoalLevel = GoalLevel.DAILY,
                 parent_goal_id: str = None,
                 backup_pool: List[str] = None,
                 tick: int = 0):
        """添加一个目标"""
        if not self._initialized:
            raise RuntimeError("引擎未初始化")
        return self.goals.add_goal(
            content=content, level=level,
            character_name=character_name,
            parent_goal_id=parent_goal_id,
            backup_pool=backup_pool,
            tick=tick,
        )

    def complete_goal(self, goal_id: str, tick: int = None):
        """完成一个目标"""
        if not self._initialized:
            raise RuntimeError("引擎未初始化")
        if tick is None:
            tick = self.timeline.current_tick
        return self.goals.complete_goal(goal_id, tick)

    # ─── 关系图操作 ───

    def add_relation(self, src: str, dst: str,
                     fb: float = 0.0, ud: float = 0.0, lr: float = 0.0,
                     sd: float = 0.0, io: float = 0.0, tm: float = 0.0,
                     weight: float = 1.0):
        """在六轴图上添加一条关系边"""
        if not self._initialized:
            raise RuntimeError("引擎未初始化")
        self.graph.add_edge(
            src=src, dst=dst,
            fb=fb, ud=ud, lr=lr, sd=sd, io=io, tm=tm,
            weight=weight,
        )
        return self

    # ─── 核心：tick 推进 ───

    def advance_tick(self, scene: str = None, time_marker: str = None,
                     active_characters: List[str] = None,
                     chapter: int = None) -> TickResult:
        """推进一个 tick，执行完整流程

        流程：
        1. 推进时间轴（创建新 tick）
        2. 推进所有活跃角色的目标（未完成则延迟）
        3. 碰撞检测
        4. 规则守卫校验碰撞叙事
        5. 一致性校验
        6. 保存状态（如果配置了持久化）

        Args:
            scene: 场景（None 则继承上一 tick）
            time_marker: 时间标记（None 则继承）
            active_characters: 活跃角色列表（None 则继承）
            chapter: 章节号（None 则继承）

        Returns:
            TickResult 汇总对象
        """
        if not self._initialized:
            raise RuntimeError("引擎未初始化，请先调用 init_with_defaults()")

        result = TickResult()

        # 1. 推进时间轴
        if len(self.timeline.ticks) == 0:
            # 第一个 tick
            self.timeline.add_tick(
                chapter=chapter or 0,
                scene=scene or "",
                time_marker=time_marker or "morning",
                active_characters=active_characters or [],
            )
        else:
            new_tick = self.timeline.advance_tick()
            if new_tick and scene:
                new_tick.scene = scene
            if new_tick and time_marker:
                new_tick.time_marker = time_marker
            if new_tick and active_characters:
                new_tick.active_characters = list(active_characters)
            if new_tick and chapter:
                new_tick.chapter = chapter

        current = self.timeline.get_current_tick()
        if current is None:
            return result

        result.tick_id = current.tick_id
        result.chapter = current.chapter
        result.scene = current.scene

        tick = current.tick_id

        # 2. 批量推进所有活跃角色的目标
        active_chars = self.swimlanes.get_active_characters(tick)
        all_new = []
        all_deferred = []
        all_failed = []
        for char_name in active_chars:
            summary = self.goals.tick_advance(char_name, tick)
            all_new.extend(summary.get("new_goals", []))
            all_deferred.extend(summary.get("deferred", []))
            all_failed.extend(summary.get("failed", []))

        result.new_goals = all_new
        result.deferred_goals = all_deferred
        result.failed_goals = all_failed

        # 3. 碰撞检测（含规则守卫，碰撞调度器内部会调用）
        collisions = self.collision.detect_at_tick(tick)
        result.collisions = collisions

        # 4. 收集规则守卫违规（碰撞调度器已检查，此处汇总）
        for col in collisions:
            if hasattr(col, 'rule_violations') and col.rule_violations:
                result.rule_violations.extend(col.rule_violations)

        # 5. 一致性校验
        issues = self.consistency.check_all()
        result.consistency_issues = issues

        # 6. 保存状态
        if self._project_dir:
            self.save_state()

        return result

    # ─── 状态持久化 ───

    def save_state(self):
        """保存所有模块状态到项目目录"""
        if not self._project_dir:
            return
        state_dir = os.path.join(self._project_dir, "engine_state")
        os.makedirs(state_dir, exist_ok=True)

        # 调度层
        with open(os.path.join(state_dir, "timeline.json"), "w", encoding="utf-8") as f:
            json.dump(self.timeline.to_dict(), f, ensure_ascii=False, indent=2)
        with open(os.path.join(state_dir, "swimlanes.json"), "w", encoding="utf-8") as f:
            json.dump(self.swimlanes.to_dict(), f, ensure_ascii=False, indent=2)
        with open(os.path.join(state_dir, "goals.json"), "w", encoding="utf-8") as f:
            json.dump(self.goals.to_dict(), f, ensure_ascii=False, indent=2)

        # 管控层
        with open(os.path.join(state_dir, "collision.json"), "w", encoding="utf-8") as f:
            json.dump(self.collision.to_dict(), f, ensure_ascii=False, indent=2)
        with open(os.path.join(state_dir, "consistency.json"), "w", encoding="utf-8") as f:
            json.dump(self.consistency.to_dict(), f, ensure_ascii=False, indent=2)
        with open(os.path.join(state_dir, "rule_guard.json"), "w", encoding="utf-8") as f:
            json.dump(self.rule_guard.to_dict(), f, ensure_ascii=False, indent=2)

        # 图
        with open(os.path.join(state_dir, "graph.json"), "w", encoding="utf-8") as f:
            json.dump(self.graph.to_dict(), f, ensure_ascii=False, indent=2)

        # 分支
        branch_dir = os.path.join(state_dir, "branches")
        self.branches.save_to_dir(branch_dir)

        # TruthLedger 和 VectorMemory 自己管理持久化

    def get_stats(self) -> dict:
        """获取引擎整体统计信息"""
        if not self._initialized:
            return {"initialized": False}
        return {
            "initialized": True,
            "timeline": self.timeline.get_stats(),
            "swimlanes": self.swimlanes.get_stats(),
            "goals": self.goals.get_stats(),
            "collision": self.collision.get_stats(),
            "consistency": self.consistency.get_stats(),
            "rule_guard": self.rule_guard.get_stats(),
            "branches": self.branches.get_stats(),
            "graph": self.graph.get_stats() if self.graph else {"nodes": 0, "edges": 0},
        }
