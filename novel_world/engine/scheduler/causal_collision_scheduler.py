# -*- coding: utf-8 -*-
"""
因果碰撞调度器 - 六轴增强版

整合六轴关系图、泳道管理器、世界时间轴和真相账本，
在每次 tick 推进时自动检测活跃角色之间的因果碰撞。

核心流程：
  1. 从 SwimlaneManager 获取当前 tick 的活跃角色
  2. 根据角色的目标/关系/状态在 SixAxisGraph 上激活对应节点
  3. 调用 detect_convergence() 检测碰撞
  4. 将碰撞结果记录到 TruthLedger 和 VectorMemory
  5. 返回碰撞事件供叙事层使用

与一期/二期模块的关系：
  - SixAxisGraph: 提供六轴碰撞检测算法
  - SwimlaneManager: 提供活跃角色列表和角色状态
  - WorldTimeline: 提供 tick/章节/场景上下文
  - TruthLedger: 碰撞事件持久化到时间线
  - VectorMemory: 碰撞事件存入向量记忆供后续检索
"""
import uuid
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Any, Tuple


@dataclass
class CollisionRecord:
    """
    碰撞记录 - 一次因果碰撞的完整数据

    Attributes:
        id: 碰撞记录唯一 ID
        tick: 发生碰撞的 tick
        chapter: 所属章节
        scene: 碰撞场景
        node_id: 碰撞汇聚节点（通常是角色名或地点）
        sources: 碰撞来源节点列表
        collision_type: 碰撞类型（causal_conflict/interest_competition 等）
        total_activation: 总激活值
        axis_breakdown: 各轴激活分值
        characters: 参与碰撞的角色列表
        description: 人类可读的碰撞描述
        narrative: AI 生成的叙事文本（可选）
        metadata: 扩展元数据
    """
    id: str = ""
    tick: int = 0
    chapter: int = 0
    scene: str = ""
    node_id: str = ""
    sources: List[str] = field(default_factory=list)
    collision_type: str = ""
    total_activation: float = 0.0
    axis_breakdown: Dict[str, float] = field(default_factory=dict)
    characters: List[str] = field(default_factory=list)
    description: str = ""
    narrative: str = ""
    rule_violations: List = field(default_factory=list)   # 规则守卫违规列表
    has_block_violation: bool = False                     # 是否有阻断级违规
    metadata: Dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "CollisionRecord":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


class CausalCollisionScheduler:
    """
    因果碰撞调度器 - 六轴增强版

    核心职责：
    1. 在 tick 推进时自动检测角色碰撞
    2. 根据角色目标/状态自动在六轴图上激活节点
    3. 将碰撞结果同步到 TruthLedger 和 VectorMemory
    4. 管理碰撞历史和统计

    使用方式：
        scheduler = CausalCollisionScheduler()
        scheduler.set_graph(graph)
        scheduler.set_swimlane_manager(sm)
        scheduler.set_timeline(timeline)
        scheduler.set_truth_ledger(ledger)
        scheduler.set_vector_memory(vm)

        # 每个 tick 调用
        collisions = scheduler.detect_at_tick(tick=5)
    """

    def __init__(self):
        """初始化碰撞调度器"""
        self.graph = None              # SixAxisGraph 引用
        self.swimlane_manager = None    # SwimlaneManager 引用
        self.timeline = None            # WorldTimeline 引用
        self.truth_ledger = None        # TruthLedger 引用
        self.vector_memory = None       # VectorMemory 引用
        self.rule_guard = None          # WorldRuleGuard 引用（碰撞叙事校验）

        self.collision_history: List[CollisionRecord] = []
        self._activation_cache: Dict[str, float] = {}  # 角色名 -> 激活值缓存

    # ─── 引用设置 ───

    def set_graph(self, graph):
        """设置 SixAxisGraph 引用"""
        self.graph = graph

    def set_swimlane_manager(self, sm):
        """设置 SwimlaneManager 引用"""
        self.swimlane_manager = sm

    def set_timeline(self, tl):
        """设置 WorldTimeline 引用"""
        self.timeline = tl

    def set_truth_ledger(self, ledger):
        """设置 TruthLedger 引用"""
        self.truth_ledger = ledger

    def set_vector_memory(self, vm):
        """设置 VectorMemory 引用"""
        self.vector_memory = vm

    def set_rule_guard(self, rg):
        """设置 WorldRuleGuard 引用（碰撞描述自动校验世界观规则）"""
        self.rule_guard = rg

    # ─── 核心：碰撞检测 ───

    def detect_at_tick(self, tick: int) -> List[CollisionRecord]:
        """
        在指定 tick 执行碰撞检测

        流程：
        1. 从 SwimlaneManager 获取活跃角色
        2. 计算每个角色的激活值（基于目标紧迫度、状态等）
        3. 在 SixAxisGraph 上执行碰撞检测
        4. 将结果转化为 CollisionRecord 并记录

        Args:
            tick: 当前 tick 编号

        Returns:
            检测到的碰撞记录列表
        """
        if self.graph is None or self.swimlane_manager is None:
            return []

        # 获取活跃角色
        active_swimlanes = self.swimlane_manager.get_characters_for_tick(tick)
        if len(active_swimlanes) < 2:
            return []

        # 计算激活值
        activated = self._compute_activations(active_swimlanes, tick)
        if len(activated) < 2:
            return []

        # 调用六轴图碰撞检测
        convergence_events = self.graph.detect_convergence(activated)

        if not convergence_events:
            return []

        # 获取当前 tick 的上下文
        chapter = 0
        scene = ""
        if self.timeline is not None:
            current = self.timeline.get_current_tick()
            if current is not None:
                chapter = current.chapter
                scene = current.scene

        # 转化为 CollisionRecord
        records = []
        for event in convergence_events:
            record = CollisionRecord(
                id=str(uuid.uuid4())[:8],
                tick=tick,
                chapter=chapter,
                scene=scene,
                node_id=event.node_id,
                sources=list(event.sources),
                collision_type=event.collision_type,
                total_activation=event.total_activation,
                axis_breakdown=dict(event.axis_breakdown),
                characters=self._extract_characters(event, activated),
                description=self._describe_collision(event),
            )
            records.append(record)
            self.collision_history.append(record)

        # 世界观规则守卫校验（碰撞描述自动过规则）
        if self.rule_guard is not None:
            for record in records:
                try:
                    violations = self.rule_guard.check_narrative(
                        record.description,
                        characters=record.characters,
                    )
                    record.rule_violations = violations
                    # 标记是否有阻断级违规
                    record.has_block_violation = self.rule_guard.should_block(violations)
                except Exception as e:
                    print(f"[CausalCollisionScheduler] 规则守卫校验失败: {e}")

        # 同步到 TruthLedger
        if self.truth_ledger is not None:
            self._sync_to_truth_ledger(records, chapter)

        # 同步到 VectorMemory
        if self.vector_memory is not None:
            self._sync_to_vector_memory(records, chapter, tick)

        return records

    def _compute_activations(self, active_swimlanes, tick: int) -> Dict[str, float]:
        """
        计算角色的激活值

        激活值基于：
        - 角色是否有正在执行的目标（有目标 = 高激活）
        - 角色的行动历史密度（最近行动多 = 高激活）
        - 角色状态快照中的情绪强度

        Args:
            active_swimlanes: 活跃角色泳道列表
            tick: 当前 tick

        Returns:
            {角色名: 激活值} 字典，激活值范围 0~1
        """
        activated = {}

        for swimlane in active_swimlanes:
            name = swimlane.character_name
            activation = 0.3  # 基础激活值

            # 有行动记录的角色激活更高
            recent_actions = swimlane.action_log[-5:] if swimlane.action_log else []
            if recent_actions:
                action_density = min(1.0, len(recent_actions) / 5.0)
                activation += 0.3 * action_density

            # 有目标的角色激活更高
            if swimlane.daily_goals:
                activation += 0.2

            # 状态快照中的情绪强度
            snapshot = swimlane.state_snapshot
            if snapshot:
                emotion = snapshot.get("emotion", "")
                # 激烈情绪提高激活
                intense_emotions = ["愤怒", "恐惧", "激动", "决意", "疯狂", "悲痛"]
                if any(e in emotion for e in intense_emotions):
                    activation += 0.2

            activated[name] = min(1.0, activation)

        self._activation_cache = dict(activated)
        return activated

    def _extract_characters(self, event, activated: Dict[str, float]) -> List[str]:
        """从碰撞事件中提取参与角色列表"""
        chars = set(event.sources)
        # 碰撞节点本身也可能是角色
        if event.node_id in activated:
            chars.add(event.node_id)
        return list(chars)

    def _describe_collision(self, event) -> str:
        """生成碰撞事件的人类可读描述"""
        type_map = {
            "causal_conflict": "因果冲突",
            "causal_cooperation": "因果合作",
            "interest_competition": "利益竞争",
            "interest_cooperation": "利益合作",
            "ideology_conflict": "理念冲突",
            "ideology_resonance": "理念共鸣",
            "hierarchy_suppress": "层级压制",
            "hierarchy_rebellion": "层级反抗",
            "interaction_conflict": "交互冲突",
            "interaction_harmony": "交互和谐",
            "temporal_encounter": "时序交汇",
            "multi_dimensional": "多维碰撞",
            "weak_encounter": "弱遭遇",
        }
        type_name = type_map.get(event.collision_type, event.collision_type)
        sources_str = "、".join(event.sources) if event.sources else "未知"
        return (
            f"[{type_name}] {sources_str} -> {event.node_id} "
            f"(激活值: {event.total_activation:.3f})"
        )

    def _sync_to_truth_ledger(self, records: List[CollisionRecord], chapter: int):
        """将碰撞记录同步到 TruthLedger"""
        for record in records:
            if self.truth_ledger is None:
                break
            try:
                self.truth_ledger.add_collision_event(
                    chapter=chapter,
                    event=record.description,
                    characters=record.characters,
                    location=record.scene,
                    importance="critical",
                )
            except Exception as e:
                print(f"[CausalCollisionScheduler] TruthLedger 同步失败: {e}")

    def _sync_to_vector_memory(self, records: List[CollisionRecord],
                                chapter: int, tick: int):
        """将碰撞记录同步到 VectorMemory"""
        try:
            from ..storage.vector_memory import MemoryType
        except ImportError:
            try:
                from engine.storage.vector_memory import MemoryType
            except ImportError:
                return

        for record in records:
            if self.vector_memory is None:
                break
            try:
                content = (
                    f"碰撞事件 (tick={tick}, 章节={chapter})\n"
                    f"类型: {record.collision_type}\n"
                    f"来源: {', '.join(record.sources)}\n"
                    f"汇聚: {record.node_id}\n"
                    f"描述: {record.description}"
                )
                self.vector_memory.add_memory(
                    content=content,
                    memory_type=MemoryType.COLLISION,
                    importance=min(1.0, record.total_activation),
                    metadata={
                        "chapter": chapter,
                        "tick": tick,
                        "collision_id": record.id,
                        "collision_type": record.collision_type,
                        "characters": record.characters,
                        "location": record.scene,
                    },
                )
            except Exception as e:
                print(f"[CausalCollisionScheduler] VectorMemory 同步失败: {e}")

    # ─── 碰撞查询 ───

    def get_collisions_for_tick(self, tick: int) -> List[CollisionRecord]:
        """获取指定 tick 的碰撞记录"""
        return [r for r in self.collision_history if r.tick == tick]

    def get_collisions_for_chapter(self, chapter: int) -> List[CollisionRecord]:
        """获取指定章节的所有碰撞记录"""
        return [r for r in self.collision_history if r.chapter == chapter]

    def get_recent_collisions(self, n: int = 10) -> List[CollisionRecord]:
        """获取最近 n 条碰撞记录"""
        return self.collision_history[-n:] if self.collision_history else []

    def get_collisions_by_type(self, collision_type: str) -> List[CollisionRecord]:
        """按碰撞类型筛选记录"""
        return [r for r in self.collision_history
                if r.collision_type == collision_type]

    # ─── 叙事生成 ───

    def set_narrative(self, collision_id: str, narrative: str):
        """为碰撞记录设置叙事文本"""
        for record in self.collision_history:
            if record.id == collision_id:
                record.narrative = narrative
                return True
        return False

    # ─── 序列化 ───

    def to_dict(self) -> dict:
        """序列化为字典"""
        return {
            "collision_history": [r.to_dict() for r in self.collision_history],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "CausalCollisionScheduler":
        """从字典反序列化"""
        scheduler = cls()
        for rd in data.get("collision_history", []):
            scheduler.collision_history.append(
                CollisionRecord.from_dict(rd)
            )
        return scheduler

    # ─── 统计 ───

    def get_stats(self) -> Dict:
        """返回碰撞调度器统计信息"""
        type_counts = {}
        for r in self.collision_history:
            t = r.collision_type
            type_counts[t] = type_counts.get(t, 0) + 1

        chapter_counts = {}
        for r in self.collision_history:
            ch = r.chapter
            chapter_counts[ch] = chapter_counts.get(ch, 0) + 1

        return {
            "total_collisions": len(self.collision_history),
            "type_distribution": type_counts,
            "chapter_distribution": chapter_counts,
            "has_graph": self.graph is not None,
            "has_swimlane_manager": self.swimlane_manager is not None,
            "has_timeline": self.timeline is not None,
            "has_truth_ledger": self.truth_ledger is not None,
            "has_vector_memory": self.vector_memory is not None,
            "last_activation_cache": dict(self._activation_cache),
        }
