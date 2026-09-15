# -*- coding: utf-8 -*-
"""
scheduler 包 - 世界时间轴、角色泳道管理、目标调度、碰撞检测、一致性校验、规则守卫

本包提供小说引擎的调度层核心组件：

二期模块：
1. world_timeline - 世界时间轴（WorldTick, WorldTimeline）
2. swimlane_manager - 角色泳道管理器（LifecycleStage, ActionRecord, CharacterSwimlane, SwimlaneManager）
3. goal_scheduler - 目标调度器（GoalStatus, GoalLevel, Goal, GoalScheduler）

三期模块：
4. causal_collision_scheduler - 因果碰撞调度器（CollisionRecord, CausalCollisionScheduler）
5. consistency_checker - 全局一致性校验器（CheckLevel, ConsistencyIssue, ConsistencyChecker）
6. world_rule_guard - 世界观规则守卫层（GuardLevel, WorldRule, GuardViolation, WorldRuleGuard）
"""

# ─── 二期模块 ───

# 从 world_timeline 导出
from .world_timeline import WorldTick, WorldTimeline

# 从 swimlane_manager 导出
from .swimlane_manager import (
    LifecycleStage,
    ActionRecord,
    CharacterSwimlane,
    SwimlaneManager,
)

# 从 goal_scheduler 导出
from .goal_scheduler import (
    GoalStatus,
    GoalLevel,
    Goal,
    GoalScheduler,
)

# ─── 三期模块 ───

# 从 causal_collision_scheduler 导出
from .causal_collision_scheduler import (
    CollisionRecord,
    CausalCollisionScheduler,
)

# 从 consistency_checker 导出
from .consistency_checker import (
    CheckLevel,
    ConsistencyIssue,
    ConsistencyChecker,
)

# 从 world_rule_guard 导出
from .world_rule_guard import (
    GuardLevel,
    WorldRule,
    GuardViolation,
    WorldRuleGuard,
)

# ─── 四期模块 ───

# 从 timeline_branch 导出
from .timeline_branch import (
    BranchNode,
    WorldSnapshot,
    TimelineBranch,
)

# 从 timeline_tree 导出（分支剧情系统）
from .timeline_tree import (
    WorldState,
    Condition,
    ChapterResolution,
    TimelineTreeEngine,
)

__all__ = [
    # world_timeline
    "WorldTick",
    "WorldTimeline",
    # swimlane_manager
    "LifecycleStage",
    "ActionRecord",
    "CharacterSwimlane",
    "SwimlaneManager",
    # goal_scheduler
    "GoalStatus",
    "GoalLevel",
    "Goal",
    "GoalScheduler",
    # causal_collision_scheduler
    "CollisionRecord",
    "CausalCollisionScheduler",
    # consistency_checker
    "CheckLevel",
    "ConsistencyIssue",
    "ConsistencyChecker",
    # world_rule_guard
    "GuardLevel",
    "WorldRule",
    "GuardViolation",
    "WorldRuleGuard",
    # timeline_branch
    "BranchNode",
    "WorldSnapshot",
    "TimelineBranch",
    # timeline_tree
    "WorldState",
    "Condition",
    "ChapterResolution",
    "TimelineTreeEngine",
]
