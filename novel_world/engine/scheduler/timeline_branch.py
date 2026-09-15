# -*- coding: utf-8 -*-
"""
时序回溯分支存档 - 支持在世界时间轴的任意 tick 创建分支

核心职责：
  1. 在关键节点创建世界状态快照（WorldTimeline + SwimlaneManager + TruthLedger 的完整序列化）
  2. 支持从快照恢复世界状态（回溯）
  3. 支持从任意 tick 创建分支，在分支上独立推进时间线
  4. 管理分支树，记录分支间的父子关系

设计原则：
  - 快照是深拷贝，不引用原始对象
  - 快照只保存可序列化的数据（to_dict()）
  - 回溯操作不删除原时间线，而是创建新分支
  - 分支树可持久化到磁盘

与现有模块的关系：
  - WorldTimeline: 提供 tick 列表，快照时序列化
  - SwimlaneManager: 提供角色泳道，快照时序列化
  - TruthLedger: 提供真相账本，快照时序列化
  - GoalScheduler: 提供目标树，快照时序列化
"""
import os
import json
import uuid
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional


@dataclass
class BranchNode:
    """
    分支节点 - 分支树中的一个节点

    Attributes:
        id: 分支 ID
        parent_id: 父分支 ID（根分支为 None）
        branch_point_tick: 从父分支的哪个 tick 分出
        created_at: 创建时间戳
        description: 分支描述
        is_active: 是否为当前活跃分支
        tick_range: 该分支的 tick 范围 [start, end]
    """
    id: str = ""
    parent_id: Optional[str] = None
    branch_point_tick: int = 0
    created_at: str = ""
    description: str = ""
    is_active: bool = False
    tick_range: List[int] = field(default_factory=lambda: [0, 0])

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "BranchNode":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class WorldSnapshot:
    """
    世界状态快照 - 某一时刻的完整世界状态

    包含：
    - WorldTimeline 的序列化数据
    - SwimlaneManager 的序列化数据
    - TruthLedger 的序列化数据（可选）
    - GoalScheduler 的序列化数据（可选）
    - CausalCollisionScheduler 的碰撞历史（可选）

    快照是纯数据，不包含对象引用。
    """
    id: str = ""
    tick: int = 0
    chapter: int = 0
    branch_id: str = ""
    created_at: str = ""
    description: str = ""

    # 引擎模块的序列化数据
    timeline_data: dict = field(default_factory=dict)
    swimlane_data: dict = field(default_factory=dict)
    truth_ledger_data: Optional[dict] = None
    goal_scheduler_data: Optional[dict] = None
    collision_history: List[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "WorldSnapshot":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


class TimelineBranch:
    """
    时序回溯分支管理器

    使用方式：
        tb = TimelineBranch()
        tb.set_timeline(timeline)
        tb.set_swimlane_manager(sm)

        # 在 tick=5 创建快照
        tb.create_snapshot(tick=5, description="第一卷结束")

        # 从 tick=3 创建分支
        new_branch = tb.create_branch(
            parent_branch_id="main",
            branch_point_tick=3,
            description="如果主角选择离开宗门"
        )

        # 回溯到某个快照
        tb.restore_snapshot(snapshot_id="snap_xxx")

        # 持久化到磁盘
        tb.save_to_dir("/path/to/branches")
    """

    def __init__(self):
        self.timeline = None
        self.swimlane_manager = None
        self.truth_ledger = None
        self.goal_scheduler = None
        self.collision_scheduler = None

        self.snapshots: Dict[str, WorldSnapshot] = {}
        self.branches: Dict[str, BranchNode] = {}
        self.active_branch_id: str = ""

        # 初始化主分支
        main = BranchNode(
            id="main",
            parent_id=None,
            branch_point_tick=0,
            is_active=True,
            tick_range=[0, 0],
        )
        self.branches["main"] = main
        self.active_branch_id = "main"

    # ─── 引用设置 ───

    def set_timeline(self, tl):
        self.timeline = tl

    def set_swimlane_manager(self, sm):
        self.swimlane_manager = sm

    def set_truth_ledger(self, ledger):
        self.truth_ledger = ledger

    def set_goal_scheduler(self, gs):
        self.goal_scheduler = gs

    def set_collision_scheduler(self, cs):
        self.collision_scheduler = cs

    # ─── 快照管理 ───

    def create_snapshot(self, tick: int, description: str = "") -> str:
        """
        在指定 tick 创建世界状态快照

        Args:
            tick: 快照对应的 tick
            description: 快照描述

        Returns:
            快照 ID
        """
        snap_id = f"snap_{uuid.uuid4().hex[:8]}"

        snapshot = WorldSnapshot(
            id=snap_id,
            tick=tick,
            chapter=self._get_current_chapter(),
            branch_id=self.active_branch_id,
            created_at=self._now(),
            description=description,
        )

        # 序列化各模块
        if self.timeline is not None:
            snapshot.timeline_data = self.timeline.to_dict()

        if self.swimlane_manager is not None:
            snapshot.swimlane_data = self.swimlane_manager.to_dict()

        if self.truth_ledger is not None:
            try:
                snapshot.truth_ledger_data = self.truth_ledger.to_dict()
            except Exception:
                pass

        if self.goal_scheduler is not None:
            try:
                snapshot.goal_scheduler_data = self.goal_scheduler.to_dict()
            except Exception:
                pass

        if self.collision_scheduler is not None:
            try:
                snapshot.collision_history = [
                    c.to_dict() if hasattr(c, 'to_dict') else c
                    for c in self.collision_scheduler.collision_history
                ]
            except Exception:
                pass

        self.snapshots[snap_id] = snapshot

        # 更新分支的 tick 范围
        branch = self.branches.get(self.active_branch_id)
        if branch:
            branch.tick_range[1] = max(branch.tick_range[1], tick)

        return snap_id

    def restore_snapshot(self, snapshot_id: str) -> bool:
        """
        从快照恢复世界状态

        注意：恢复操作不会覆盖当前时间线，而是将快照数据
        反序列化到引用的模块中。

        Args:
            snapshot_id: 快照 ID

        Returns:
            是否恢复成功
        """
        snapshot = self.snapshots.get(snapshot_id)
        if snapshot is None:
            return False

        # 恢复 Timeline
        if self.timeline is not None and snapshot.timeline_data:
            try:
                self.timeline._restore_from_dict(snapshot.timeline_data)
            except AttributeError:
                # 如果没有 _restore_from_dict 方法，尝试直接赋值
                pass

        # 恢复 SwimlaneManager
        if self.swimlane_manager is not None and snapshot.swimlane_data:
            try:
                self.swimlane_manager._restore_from_dict(snapshot.swimlane_data)
            except AttributeError:
                pass

        # 恢复 TruthLedger
        if self.truth_ledger is not None and snapshot.truth_ledger_data:
            try:
                self.truth_ledger._restore_from_dict(snapshot.truth_ledger_data)
            except AttributeError:
                pass

        # 恢复 GoalScheduler
        if self.goal_scheduler is not None and snapshot.goal_scheduler_data:
            try:
                self.goal_scheduler._restore_from_dict(snapshot.goal_scheduler_data)
            except AttributeError:
                pass

        # 恢复 CollisionScheduler
        if self.collision_scheduler is not None and snapshot.collision_history:
            try:
                from .causal_collision_scheduler import CollisionRecord
                self.collision_scheduler.collision_history = [
                    CollisionRecord.from_dict(c) if isinstance(c, dict) else c
                    for c in snapshot.collision_history
                ]
            except Exception:
                pass

        return True

    # ─── 分支管理 ───

    def create_branch(self, parent_branch_id: str = None,
                      branch_point_tick: int = 0,
                      description: str = "") -> str:
        """
        从指定分支的某个 tick 创建新分支

        会自动创建一个快照作为分支起点。

        Args:
            parent_branch_id: 父分支 ID（默认为当前活跃分支）
            branch_point_tick: 从哪个 tick 分出
            description: 分支描述

        Returns:
            新分支 ID
        """
        if parent_branch_id is None:
            parent_branch_id = self.active_branch_id

        parent = self.branches.get(parent_branch_id)
        if parent is None:
            raise ValueError(f"父分支不存在: {parent_branch_id}")

        # 创建快照（在分支点）
        old_active = self.active_branch_id
        self.active_branch_id = parent_branch_id
        snap_id = self.create_snapshot(
            tick=branch_point_tick,
            description=f"分支点: {description}"
        )
        self.active_branch_id = old_active

        # 创建新分支
        branch_id = f"branch_{uuid.uuid4().hex[:8]}"
        new_branch = BranchNode(
            id=branch_id,
            parent_id=parent_branch_id,
            branch_point_tick=branch_point_tick,
            created_at=self._now(),
            description=description,
            is_active=False,
            tick_range=[branch_point_tick, branch_point_tick],
        )
        self.branches[branch_id] = new_branch

        return branch_id

    def switch_branch(self, branch_id: str) -> bool:
        """
        切换到指定分支

        会先将当前分支状态保存为快照，然后恢复目标分支的最新快照。

        Args:
            branch_id: 目标分支 ID

        Returns:
            是否切换成功
        """
        if branch_id not in self.branches:
            return False

        # 保存当前分支状态
        if self.timeline is not None:
            current_tick = self.timeline.current_tick
            self.create_snapshot(
                tick=current_tick,
                description=f"切换前自动快照 (branch={self.active_branch_id})"
            )

        # 标记分支状态
        self.branches[self.active_branch_id].is_active = False
        self.branches[branch_id].is_active = True
        self.active_branch_id = branch_id

        # 尝试恢复该分支最近的快照
        branch_snaps = [
            s for s in self.snapshots.values()
            if s.branch_id == branch_id
        ]
        if branch_snaps:
            latest = max(branch_snaps, key=lambda s: s.tick)
            self.restore_snapshot(latest.id)

        return True

    def get_branch_tree(self) -> Dict:
        """
        获取分支树结构

        Returns:
            嵌套的分支树字典
        """
        def build_node(branch_id: str) -> dict:
            branch = self.branches[branch_id]
            children = [
                build_node(bid) for bid, b in self.branches.items()
                if b.parent_id == branch_id
            ]
            snap_count = sum(
                1 for s in self.snapshots.values()
                if s.branch_id == branch_id
            )
            return {
                "id": branch.id,
                "description": branch.description,
                "branch_point_tick": branch.branch_point_tick,
                "tick_range": branch.tick_range,
                "is_active": branch.is_active,
                "snapshot_count": snap_count,
                "children": children,
            }

        return build_node("main")

    # ─── 查询 ───

    def get_snapshot(self, snapshot_id: str) -> Optional[WorldSnapshot]:
        """获取快照"""
        return self.snapshots.get(snapshot_id)

    def list_snapshots(self, branch_id: str = None) -> List[WorldSnapshot]:
        """列出快照（可按分支过滤）"""
        if branch_id:
            return [s for s in self.snapshots.values() if s.branch_id == branch_id]
        return list(self.snapshots.values())

    def list_branches(self) -> List[BranchNode]:
        """列出所有分支"""
        return list(self.branches.values())

    def get_active_branch(self) -> BranchNode:
        """获取当前活跃分支"""
        return self.branches[self.active_branch_id]

    # ─── 持久化 ───

    def save_to_dir(self, dir_path: str):
        """将分支和快照保存到目录"""
        os.makedirs(dir_path, exist_ok=True)

        data = {
            "branches": {bid: b.to_dict() for bid, b in self.branches.items()},
            "snapshots": {sid: s.to_dict() for sid, s in self.snapshots.items()},
            "active_branch_id": self.active_branch_id,
        }

        filepath = os.path.join(dir_path, "timeline_branches.json")
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def load_from_dir(self, dir_path: str) -> bool:
        """从目录加载分支和快照"""
        filepath = os.path.join(dir_path, "timeline_branches.json")
        if not os.path.exists(filepath):
            return False

        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)

        self.branches = {
            bid: BranchNode.from_dict(bd)
            for bid, bd in data.get("branches", {}).items()
        }
        self.snapshots = {
            sid: WorldSnapshot.from_dict(sd)
            for sid, sd in data.get("snapshots", {}).items()
        }
        self.active_branch_id = data.get("active_branch_id", "main")
        return True

    # ─── 序列化 ───

    def to_dict(self) -> dict:
        return {
            "branches": {bid: b.to_dict() for bid, b in self.branches.items()},
            "snapshots": {sid: s.to_dict() for sid, s in self.snapshots.items()},
            "active_branch_id": self.active_branch_id,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "TimelineBranch":
        tb = cls()
        tb.branches = {
            bid: BranchNode.from_dict(bd)
            for bid, bd in data.get("branches", {}).items()
        }
        tb.snapshots = {
            sid: WorldSnapshot.from_dict(sd)
            for sid, sd in data.get("snapshots", {}).items()
        }
        tb.active_branch_id = data.get("active_branch_id", "main")
        return tb

    # ─── 统计 ───

    def get_stats(self) -> Dict:
        return {
            "total_branches": len(self.branches),
            "total_snapshots": len(self.snapshots),
            "active_branch": self.active_branch_id,
            "has_timeline": self.timeline is not None,
            "has_swimlane_manager": self.swimlane_manager is not None,
            "has_truth_ledger": self.truth_ledger is not None,
            "has_goal_scheduler": self.goal_scheduler is not None,
            "has_collision_scheduler": self.collision_scheduler is not None,
        }

    # ─── 内部工具 ───

    def _get_current_chapter(self) -> int:
        if self.timeline is not None:
            tick = self.timeline.get_current_tick()
            if tick is not None:
                return tick.chapter
        return 0

    def _now(self) -> str:
        from datetime import datetime
        return datetime.now().isoformat()
