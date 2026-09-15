# -*- coding: utf-8 -*-
"""
角色泳道管理器 - 管理每个角色的独立时间线和生命周期

核心概念：
- LifecycleStage: 角色生命周期阶段（待激活/活跃/休眠/封印/死亡）
- ActionRecord: 角色行为记录（单次行动的完整描述）
- CharacterSwimlane: 角色泳道（单个角色的完整生命周期数据）
- SwimlaneManager: 泳道管理器（所有角色泳道的统一管理入口）

与 VectorMemory 的关系：
  当角色进入休眠时，其状态快照存入 VectorMemory（SNAPSHOT 类型）
  当角色被唤醒时，从 VectorMemory 重新加载状态

与 WorldTimeline 的关系：
  SwimlaneManager 引用 WorldTimeline 来确定当前 tick，
  以便正确管理角色的入场/出场时机

设计原则：
- 每个角色有独立的泳道，互不干扰
- 泳道记录角色的完整行动历史
- 生命周期转换自动触发状态保存/恢复
- 支持独立运行（不依赖外部引用时也能工作）
"""
import json, time
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Dict, List, Optional, Any


class LifecycleStage(Enum):
    """
    角色生命周期阶段枚举

    PENDING:   待激活 - 角色已注册但尚未进入叙事
    ACTIVE:    活跃   - 角色正在参与当前 tick 的叙事
    SLEEPING:  休眠   - 角色暂时退出叙事，状态已保存到 VectorMemory
    SEALED:    封印   - 角色被强制封印，不可被引用或交互
    DEAD:      死亡   - 角色已死亡，永久退出叙事
    """
    PENDING = "pending"
    ACTIVE = "active"
    SLEEPING = "sleeping"
    SEALED = "sealed"
    DEAD = "dead"


@dataclass
class ActionRecord:
    """
    角色行为记录 - 单次行动的完整描述

    记录角色在某个 tick 中采取的完整行动链：
    做了什么 -> 选择了什么 -> 结果如何 -> 付出了什么代价 -> 服务于哪个目标

    Attributes:
        tick: 发生该行动的 tick 编号
        action: 具体行动描述（角色做了什么）
        choice: 选择描述（面临的关键选择）
        outcome: 结果描述（行动的后果）
        cost: 代价描述（为行动付出的成本）
        goal_progress: 目标进度（此行动服务于哪个目标）
    """
    tick: int = 0
    action: str = ""
    choice: str = ""
    outcome: str = ""
    cost: str = ""
    goal_progress: str = ""

    def to_dict(self) -> dict:
        """序列化为字典"""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "ActionRecord":
        """从字典反序列化"""
        return cls(**data)


@dataclass
class CharacterSwimlane:
    """
    角色泳道 - 单个角色的完整生命周期数据

    每个角色的泳道包含：
    - 生命周期信息（阶段、入场/出场 tick）
    - 当前状态快照（境界、健康、心绪、持有物等）
    - 完整的行动历史记录
    - 休眠时需要恢复的记忆 ID 列表

    Attributes:
        character_name: 角色名称
        lifecycle: 当前生命周期阶段
        entry_tick: 进入当前阶段的 tick
        exit_tick: 离开当前阶段的 tick（0=尚未离开）
        sleep_start_tick: 进入休眠的 tick（用于计算休眠时长）
        daily_goals: 当前 tick 的小目标列表
        state_snapshot: 角色状态快照字典（realm, health, emotion, possessions 等）
        action_log: 行动记录列表
        memories_to_awaken: 唤醒时需要从 VectorMemory 重新加载的记忆 ID 列表
    """
    character_name: str = ""
    lifecycle: LifecycleStage = LifecycleStage.ACTIVE
    entry_tick: int = 0
    exit_tick: int = 0
    sleep_start_tick: int = 0
    daily_goals: List[str] = field(default_factory=list)
    state_snapshot: Dict = field(default_factory=dict)
    action_log: List[ActionRecord] = field(default_factory=list)
    memories_to_awaken: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        """序列化为字典"""
        return {
            "character_name": self.character_name,
            "lifecycle": self.lifecycle.value,
            "entry_tick": self.entry_tick,
            "exit_tick": self.exit_tick,
            "sleep_start_tick": self.sleep_start_tick,
            "daily_goals": self.daily_goals,
            "state_snapshot": self.state_snapshot,
            "action_log": [a.to_dict() for a in self.action_log],
            "memories_to_awaken": self.memories_to_awaken,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "CharacterSwimlane":
        """从字典反序列化"""
        data = dict(data)
        # 处理枚举
        if isinstance(data.get("lifecycle"), str):
            data["lifecycle"] = LifecycleStage(data["lifecycle"])
        # 处理 ActionRecord 列表
        if "action_log" in data and isinstance(data["action_log"], list):
            data["action_log"] = [
                ActionRecord.from_dict(a) if isinstance(a, dict) else a
                for a in data["action_log"]
            ]
        return cls(**data)


class SwimlaneManager:
    """
    角色泳道管理器 - 所有角色泳道的统一管理入口

    核心职责：
    1. 管理所有角色的注册、生命周期转换
    2. 角色休眠时保存状态到 VectorMemory
    3. 角色唤醒时从 VectorMemory 恢复状态
    4. 记录每个角色的完整行动历史
    5. 提供活跃角色查询接口

    设计为可独立工作：不设置 timeline 和 vector_memory 引用时，
    休眠/唤醒操作将跳过向量存储部分，仅管理本地数据。

    使用方式：
        sm = SwimlaneManager()
        sm.register_character("林逸", entry_tick=1)
        sm.sleep_character("林逸", tick=10)
        sm.awaken_character("林逸", tick=15)
    """

    def __init__(self):
        """初始化泳道管理器"""
        self.swimlanes: Dict[str, CharacterSwimlane] = {}
        self.timeline = None          # WorldTimeline 引用（可选）
        self.vector_memory = None     # VectorMemory 引用（可选）
        self.truth_ledger = None      # TruthLedger 引用（可选，状态变更时同步）

    # ─── 引用设置 ───

    def set_timeline(self, tl):
        """
        设置 WorldTimeline 引用

        Args:
            tl: WorldTimeline 实例
        """
        self.timeline = tl

    def set_vector_memory(self, vm):
        """
        设置 VectorMemory 引用

        Args:
            vm: VectorMemory 实例
        """
        self.vector_memory = vm

    def set_truth_ledger(self, ledger):
        """
        设置 TruthLedger 引用（生命周期变更时自动同步角色状态）

        Args:
            ledger: TruthLedger 实例
        """
        self.truth_ledger = ledger

    # ─── 角色注册 ───

    def register_character(self, name: str, entry_tick: int = 0) -> CharacterSwimlane:
        """
        注册一个新角色，创建其泳道

        如果角色已存在，返回现有泳道。
        新角色默认为 ACTIVE 状态。

        Args:
            name: 角色名称
            entry_tick: 进入叙事的 tick 编号

        Returns:
            CharacterSwimlane 实例
        """
        if name in self.swimlanes:
            return self.swimlanes[name]

        swimlane = CharacterSwimlane(
            character_name=name,
            lifecycle=LifecycleStage.ACTIVE,
            entry_tick=entry_tick,
        )
        self.swimlanes[name] = swimlane
        return swimlane

    # ─── 生命周期管理 ───

    def update_lifecycle(self, name: str, stage: LifecycleStage, tick: int):
        """
        更新角色的生命周期阶段

        自动记录进入/退出 tick，处理阶段转换逻辑。

        Args:
            name: 角色名称
            stage: 新的生命周期阶段
            tick: 当前 tick 编号
        """
        swimlane = self.swimlanes.get(name)
        if swimlane is None:
            print(f"[SwimlaneManager] 警告: 角色 '{name}' 未注册，无法更新生命周期")
            return

        old_stage = swimlane.lifecycle
        swimlane.exit_tick = tick          # 记录离开旧阶段的 tick
        swimlane.lifecycle = stage
        swimlane.entry_tick = tick        # 记录进入新阶段的 tick

        # 如果进入休眠阶段，记录休眠开始 tick
        if stage == LifecycleStage.SLEEPING:
            swimlane.sleep_start_tick = tick

        # 同步到 TruthLedger
        if self.truth_ledger is not None:
            try:
                is_alive = stage != LifecycleStage.DEAD
                self.truth_ledger.update_character(
                    name,
                    chapter=tick,
                    lifecycle_stage=stage.value,
                    is_alive=is_alive,
                )
            except Exception as e:
                print(f"[SwimlaneManager] 同步 TruthLedger 失败: {e}")

        print(f"[SwimlaneManager] 角色 '{name}': {old_stage.value} -> {stage.value} (tick={tick})")

    def sleep_character(self, name: str, tick: int):
        """
        休眠角色 - 保存状态快照到 VectorMemory，标记为 SLEEPING

        流程：
        1. 将当前状态快照保存到 VectorMemory（SNAPSHOT 类型）
        2. 记录返回的记忆 ID，以便唤醒时恢复
        3. 更新生命周期为 SLEEPING

        Args:
            name: 角色名称
            tick: 当前 tick 编号
        """
        swimlane = self.swimlanes.get(name)
        if swimlane is None:
            print(f"[SwimlaneManager] 警告: 角色 '{name}' 未注册，无法休眠")
            return

        # 保存状态快照到 VectorMemory
        if self.vector_memory is not None:
            try:
                from engine.storage.vector_memory import MemoryType
                # 将状态快照作为记忆保存
                snapshot_content = (
                    f"角色 '{name}' 休眠快照 (tick={tick})\n"
                    f"状态: {swimlane.state_snapshot}"
                )
                memory_id = self.vector_memory.add_memory(
                    content=snapshot_content,
                    memory_type=MemoryType.SNAPSHOT,
                    importance=0.8,
                    metadata={
                        "character_id": name,
                        "tick": tick,
                        "snapshot_data": swimlane.state_snapshot,
                    }
                )
                swimlane.memories_to_awaken.append(memory_id)
                print(f"[SwimlaneManager] 角色 '{name}' 状态已保存到 VectorMemory: {memory_id}")
            except Exception as e:
                print(f"[SwimlaneManager] 保存到 VectorMemory 失败: {e}")

        # 更新生命周期
        self.update_lifecycle(name, LifecycleStage.SLEEPING, tick)

    def awaken_character(self, name: str, tick: int):
        """
        唤醒角色 - 从 VectorMemory 重新加载状态，标记为 ACTIVE

        流程：
        1. 从 VectorMemory 中搜索角色的 SNAPSHOT 记忆
        2. 恢复状态快照
        3. 更新生命周期为 ACTIVE

        Args:
            name: 角色名称
            tick: 当前 tick 编号
        """
        swimlane = self.swimlanes.get(name)
        if swimlane is None:
            print(f"[SwimlaneManager] 警告: 角色 '{name}' 未注册，无法唤醒")
            return

        # 从 VectorMemory 恢复状态
        if self.vector_memory is not None and swimlane.memories_to_awaken:
            try:
                # 搜索该角色最近的快照
                results = self.vector_memory.search(
                    query=f"角色 '{name}' 状态快照",
                    k=1,
                )
                if results:
                    entry, sim = results[0]
                    # 尝试从 metadata 中恢复状态
                    snapshot_data = entry.metadata.get("snapshot_data", {})
                    if snapshot_data:
                        swimlane.state_snapshot = snapshot_data
                        print(f"[SwimlaneManager] 角色 '{name}' 状态已从 VectorMemory 恢复")
                else:
                    print(f"[SwimlaneManager] 未找到角色 '{name}' 的快照记忆")
            except Exception as e:
                print(f"[SwimlaneManager] 从 VectorMemory 恢复失败: {e}")

        # 更新生命周期
        self.update_lifecycle(name, LifecycleStage.ACTIVE, tick)

    def kill_character(self, name: str, tick: int):
        """
        死亡角色 - 永久标记为 DEAD

        Args:
            name: 角色名称
            tick: 当前 tick 编号
        """
        self.update_lifecycle(name, LifecycleStage.DEAD, tick)

    # ─── 查询 ───

    def get_active_swimlanes(self, tick: int = 0) -> List[CharacterSwimlane]:
        """
        获取所有处于 ACTIVE 状态的角色泳道

        Args:
            tick: 查询时的 tick 编号（用于日志记录）

        Returns:
            ACTIVE 状态的 CharacterSwimlane 列表
        """
        return [
            s for s in self.swimlanes.values()
            if s.lifecycle == LifecycleStage.ACTIVE
        ]

    def get_characters_for_tick(self, tick: int) -> List[CharacterSwimlane]:
        """
        获取在指定 tick 应该活跃的角色列表

        判断逻辑：
        - ACTIVE 状态且 entry_tick <= tick 的角色
        - 排除 DEAD 和 SEALED 角色
        - 如果设置了 timeline，还会考虑 timeline 中的 active_characters

        Args:
            tick: tick 编号

        Returns:
            应该在当前 tick 活跃的 CharacterSwimlane 列表
        """
        active = []
        for name, swimlane in self.swimlanes.items():
            # 跳过死亡和封印的角色
            if swimlane.lifecycle in (LifecycleStage.DEAD, LifecycleStage.SEALED):
                continue
            # 跳过尚未激活的角色
            if swimlane.lifecycle == LifecycleStage.PENDING and swimlane.entry_tick > tick:
                continue
            # ACTIVE 或已到达激活时间的 PENDING 角色
            if swimlane.lifecycle == LifecycleStage.ACTIVE:
                active.append(swimlane)
            elif (swimlane.lifecycle == LifecycleStage.PENDING
                  and swimlane.entry_tick <= tick):
                active.append(swimlane)

        # 如果设置了 timeline，以 timeline 的 active_characters 为准进行交叉验证
        if self.timeline is not None:
            current = self.timeline.get_current_tick()
            if current is not None:
                tl_names = set(current.active_characters)
                active = [s for s in active if s.character_name in tl_names]

        return active

    def get_active_characters(self, tick: int = 0) -> List[str]:
        """获取指定 tick 活跃角色的名称列表（便捷方法）

        Args:
            tick: tick 编号

        Returns:
            角色名称列表
        """
        return [s.character_name for s in self.get_characters_for_tick(tick)]

    # ─── 状态管理 ───

    def take_snapshot(self, name: str, tick: int, state_dict: Dict):
        """
        保存角色当前状态快照

        将状态保存到 VectorMemory 并更新本地 swimlane 的 state_snapshot。

        Args:
            name: 角色名称
            tick: 当前 tick 编号
            state_dict: 状态字典（realm, health, emotion, possessions 等）
        """
        swimlane = self.swimlanes.get(name)
        if swimlane is None:
            return

        # 更新本地快照
        swimlane.state_snapshot = dict(state_dict)

        # 同步到 VectorMemory
        if self.vector_memory is not None:
            try:
                from engine.storage.vector_memory import MemoryType
                content = f"角色 '{name}' 状态快照 (tick={tick})"
                self.vector_memory.add_memory(
                    content=content,
                    memory_type=MemoryType.SNAPSHOT,
                    importance=0.7,
                    metadata={
                        "character_id": name,
                        "tick": tick,
                        "snapshot_data": state_dict,
                    }
                )
            except Exception as e:
                print(f"[SwimlaneManager] 快照保存失败: {e}")

    def log_action(self, name: str, tick: int, action: str,
                  choice: str = "", outcome: str = "",
                  cost: str = "", goal_progress: str = ""):
        """
        记录角色行为

        将一次行动的完整信息追加到角色的行动日志中。

        Args:
            name: 角色名称
            tick: 发生行动的 tick 编号
            action: 具体行动描述
            choice: 选择描述
            outcome: 结果描述
            cost: 代价描述
            goal_progress: 目标进度
        """
        swimlane = self.swimlanes.get(name)
        if swimlane is None:
            print(f"[SwimlaneManager] 警告: 角色 '{name}' 未注册，无法记录行为")
            return

        record = ActionRecord(
            tick=tick,
            action=action,
            choice=choice,
            outcome=outcome,
            cost=cost,
            goal_progress=goal_progress,
        )
        swimlane.action_log.append(record)

    def get_action_history(self, name: str, recent_ticks: int = 10) -> List[ActionRecord]:
        """
        获取角色最近的行动记录

        Args:
            name: 角色名称
            recent_ticks: 返回最近 N 条记录

        Returns:
            ActionRecord 列表（按时间倒序，最新的在前）
        """
        swimlane = self.swimlanes.get(name)
        if swimlane is None:
            return []
        # 返回最近 N 条，倒序
        return list(reversed(swimlane.action_log[-recent_ticks:]))

    # ─── 序列化 ───

    def to_dict(self) -> dict:
        """序列化为字典"""
        return {
            "swimlanes": {
                name: s.to_dict()
                for name, s in self.swimlanes.items()
            }
        }

    @classmethod
    def from_dict(cls, data: dict) -> "SwimlaneManager":
        """从字典反序列化"""
        sm = cls()
        for name, sd in data.get("swimlanes", {}).items():
            sm.swimlanes[name] = CharacterSwimlane.from_dict(sd)
        return sm

    # ─── 统计 ───

    def get_stats(self) -> Dict:
        """返回泳道管理器统计信息"""
        # 各阶段角色数
        stage_counts = {}
        for s in self.swimlanes.values():
            stage = s.lifecycle.value
            stage_counts[stage] = stage_counts.get(stage, 0) + 1

        # 总行动记录数
        total_actions = sum(len(s.action_log) for s in self.swimlanes.values())

        # 休眠中的角色数
        sleeping = sum(
            1 for s in self.swimlanes.values()
            if s.lifecycle == LifecycleStage.SLEEPING
        )

        return {
            "total_characters": len(self.swimlanes),
            "lifecycle_distribution": stage_counts,
            "active_characters": stage_counts.get("active", 0),
            "sleeping_characters": sleeping,
            "dead_characters": stage_counts.get("dead", 0),
            "total_action_records": total_actions,
            "has_timeline": self.timeline is not None,
            "has_vector_memory": self.vector_memory is not None,
        }
