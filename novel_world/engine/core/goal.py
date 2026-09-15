# -*- coding: utf-8 -*-
"""
目标数据模型 — 项目唯一真实定义（统一版）

本模块是 backend + novel_world/engine 的单一 Goal 数据源。
合并了 scheduler 端的丰富模型与 backend 端的轻量接口，通过属性保持向后兼容。

此模块定义 Goal、GoalStatus、GoalLevel 作为整个项目的唯一来源。
backend.character.Goal 已改为从此处 re-export，不得再独立维护。

调度器 (goal_scheduler.py) 也已改为从此处导入 Goal / GoalStatus / GoalLevel。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Dict, List, Optional


class GoalStatus(Enum):
    """
    目标状态枚举

    PENDING:    待执行 - 目标已创建，等待开始执行
    EXECUTING:  执行中 - 目标正在被执行
    COMPLETED:  已完成 - 目标已达成
    DEFERRED:   已延迟 - 目标因故推迟到下一个 tick
    ABANDONED:  已放弃 - 目标被永久放弃

    向后兼容（旧 progress 字符串映射）：
        \"未开始\"  → PENDING
        \"进行中\"  → EXECUTING
        \"受阻\"    → DEFERRED
        \"已完成\"  → COMPLETED
        \"已放弃\"  → ABANDONED
    """

    PENDING = "pending"
    EXECUTING = "executing"
    COMPLETED = "completed"
    DEFERRED = "deferred"
    ABANDONED = "abandoned"

    @classmethod
    def from_progress(cls, progress: str) -> "GoalStatus":
        """从旧 progress 字符串转换"""
        name = _PROGRESS_MAP.get(progress, "PENDING")
        return cls[name]

    def to_progress(self) -> str:
        """转为旧 progress 字符串"""
        return _STATUS_TO_PROGRESS.get(self.name, "未开始")


# module-level progress <-> status mapping (cannot live inside enum; _ prefix still makes them members in 3.11)
_PROGRESS_MAP = {
    "未开始": "PENDING",
    "进行中": "EXECUTING",
    "受阻": "DEFERRED",
    "已完成": "COMPLETED",
    "已放弃": "ABANDONED",
}
_STATUS_TO_PROGRESS = {
    "PENDING": "未开始",
    "EXECUTING": "进行中",
    "DEFERRED": "受阻",
    "COMPLETED": "已完成",
    "ABANDONED": "已放弃",
}


class GoalLevel(Enum):
    """
    目标层级枚举

    DAILY:     日常目标 - 当前 tick 或当天需要完成的小目标
    STAGE:     阶段目标 - 需要多个日常目标来达成的中期目标
    ULTIMATE:  终极目标 - 角色的最终追求，需要多个阶段目标来达成
    """
    DAILY = "daily"
    STAGE = "stage"
    ULTIMATE = "ultimate"


@dataclass
class Goal:
    """
    目标数据结构 — 统一版

    同时满足：
    - backend 层轻量使用：Goal(description=..., priority=5)
    - scheduler 层完整生命周期：含层级/延迟/失败分支/备选池

    Attributes:
        # ── 通用字段 ──
        content:       目标描述文本（原名 description，现为兼容属性）
        priority:      语义优先级 1-10，越大越重要
        weight:        调度权重。3.0=主线 / 2.0=长期 / 1.0=普通 / 0.5=临时
        status:        目标状态 (GoalStatus 枚举)

        # ── scheduler 扩展字段 ──
        id:            目标唯一标识（格式: goal_{tick:04d}_{index:03d}）
        level:         目标层级 (GoalLevel 枚举)
        character_name:所属角色名
        parent_goal_id:父目标 ID
        child_goal_ids:子目标 ID 列表
        backup_pool:   备选目标描述列表（失败时生成替代）
        defer_count:   已被延迟的次数
        defer_threshold:触发失败处理的延迟阈值
        created_tick:  创建时的 tick
        completed_tick:完成时的 tick
        failed_branch: 失败处理分支（downgrade/reroute/abandon）
        reason_changed: 目标变更/放弃原因（backward compat）
        metadata:      扩展元数据
    """

    # ── 通用字段 ──
    content: str = ""
    priority: int = 5                        # 1-10 语义优先级 (backward compat)
    weight: float = 1.0                      # 调度权重
    status: GoalStatus = GoalStatus.PENDING

    # ── scheduler 扩展字段 ──
    id: str = ""
    level: GoalLevel = GoalLevel.DAILY
    character_name: str = ""
    parent_goal_id: Optional[str] = None
    child_goal_ids: List[str] = field(default_factory=list)
    backup_pool: List[str] = field(default_factory=list)
    defer_count: int = 0
    defer_threshold: int = 3
    created_tick: int = 0
    completed_tick: Optional[int] = None
    failed_branch: Optional[str] = None
    reason_changed: str = ""                 # backward compat
    metadata: Dict = field(default_factory=dict)

    # ── 向后兼容属性 ──

    @property
    def description(self) -> str:
        """向后兼容：等价于 content"""
        return self.content

    @description.setter
    def description(self, value: str):
        self.content = value

    @property
    def progress(self) -> str:
        """向后兼容：status 的字符串表示"""
        return self.status.to_progress()

    @progress.setter
    def progress(self, value: str):
        self.status = GoalStatus.from_progress(value)

    # ── 便利方法 ──

    def to_dict(self) -> dict:
        """序列化为字典（含 backward compat 字段）"""
        return {
            "id": self.id,
            "content": self.content,
            "description": self.content,
            "priority": self.priority,
            "weight": self.weight,
            "status": self.status.value,
            "progress": self.progress,
            "level": self.level.value,
            "character_name": self.character_name,
            "parent_goal_id": self.parent_goal_id,
            "child_goal_ids": list(self.child_goal_ids),
            "backup_pool": list(self.backup_pool),
            "defer_count": self.defer_count,
            "defer_threshold": self.defer_threshold,
            "created_tick": self.created_tick,
            "completed_tick": self.completed_tick,
            "failed_branch": self.failed_branch,
            "reason_changed": self.reason_changed,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Goal":
        """从字典反序列化（兼容调度器）"""
        data = dict(data)
        # 处理枚举类型
        if isinstance(data.get("level"), str):
            data["level"] = GoalLevel(data["level"])
        if isinstance(data.get("status"), str):
            data["status"] = GoalStatus(data["status"])
        # backward compat: old field names
        if "content" not in data and "description" in data:
            data["content"] = data.pop("description")
        if "status" not in data and "progress" in data:
            data["status"] = GoalStatus.from_progress(data.pop("progress"))
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})

    def is_active(self) -> bool:
        """目标是否仍在进行中（未完成且未放弃）"""
        return self.status not in (GoalStatus.COMPLETED, GoalStatus.ABANDONED)

    def is_pending(self) -> bool:
        """目标是否待执行"""
        return self.status == GoalStatus.PENDING

    def mark_completed(self, tick: int = 0):
        """标记为已完成"""
        self.status = GoalStatus.COMPLETED
        if tick:
            self.completed_tick = tick

    def mark_abandoned(self, reason: str = "", tick: int = 0):
        """标记为已放弃"""
        self.status = GoalStatus.ABANDONED
        self.reason_changed = reason
        if tick:
            self.completed_tick = tick

    def defer(self):
        """延迟一次，若超过阈值则返回建议处理分支 ('downgrade'/'reroute'/'abandon'/None)"""
        self.defer_count += 1
        self.status = GoalStatus.DEFERRED
        if self.defer_count >= self.defer_threshold:
            # 简单策略：次数越多分支越严重
            if self.defer_count >= self.defer_threshold * 2:
                return "abandon"
            elif self.defer_count >= self.defer_threshold:
                return "reroute"
        return None

    def __repr__(self) -> str:
        return (
            f"Goal(id={self.id!r}, content={self.content[:30]!r}, "
            f"level={self.level.name}, status={self.status.name})"
        )
