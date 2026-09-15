# -*- coding: utf-8 -*-
"""
世界时间轴 - 以 tick 为最小时间单位的世界状态追踪系统

核心概念：
- WorldTick: 世界时间刻，记录某一刻的场景、活跃角色、世界事件
- WorldTimeline: 时间轴管理器，维护所有 tick 的有序列表

与 TruthLedger 的关系：
  TruthLedger 记录"已发生的不可变事实"，WorldTimeline 管理"正在推进的实时状态"
  当一个 tick 被标记为 immutable 时，其内容应同步写入 TruthLedger

设计原则：
- 每个 tick 对应叙事引擎的一个推进单位
- tick 按章节组织，支持章节内精确的时间标记
- 已完成的 tick 可被锁定为不可变（防止引擎回溯修改）
"""
import json, os, time
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional


@dataclass
class WorldTick:
    """
    世界时间刻 - 单个 tick 的完整状态快照

    每个 tick 记录了世界在某一刻的完整状态：
    - 属于哪个章节、哪个场景
    - 时间标记（一天中的时段）
    - 哪些角色处于活跃状态
    - 发生了哪些世界级别的事件（天气、灾难等）
    - 是否已被锁定为不可变

    Attributes:
        tick_id: 时间刻唯一标识（自增整数）
        chapter: 所属章节号（0 = 序章/前置）
        scene: 场景名称（地点/空间描述）
        time_marker: 时间标记（dawn/morning/noon/afternoon/dusk/night/midnight）
        active_characters: 该 tick 活跃的角色名列表
        world_events: 世界级事件列表（天气变化、自然灾害、战争爆发等）
        is_immutable: 是否已被锁定（不可修改）
    """
    tick_id: int = 0
    chapter: int = 0
    scene: str = ""
    time_marker: str = "morning"
    active_characters: List[str] = field(default_factory=list)
    world_events: List[str] = field(default_factory=list)
    is_immutable: bool = False

    def to_dict(self) -> dict:
        """序列化为字典"""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "WorldTick":
        """从字典反序列化"""
        return cls(**data)


class WorldTimeline:
    """
    世界时间轴 - 管理所有 WorldTick 的有序列表

    核心职责：
    1. 维护全局 tick 序列，确保时间线性推进
    2. 按章节索引 tick，支持章节级查询
    3. 管理当前 tick 指针（引擎推进位置）
    4. 支持 tick 锁定（不可变标记）
    5. 持久化到 world_timeline.json

    使用方式：
        tl = WorldTimeline()
        tl.add_tick(chapter=1, scene="天机阁", time_marker="dawn",
                    active_characters=["林逸"])
        tl.advance_tick()  # 推进到下一个 tick，继承前一个的场景和角色
    """

    def __init__(self):
        """初始化时间轴"""
        self.ticks: List[WorldTick] = []
        self.current_tick: int = 0           # 当前 tick 索引（0 = 未开始）
        self.chapter_tick_map: Dict[int, List[int]] = {}  # 章节 -> tick_id 列表
        self._engine = None                   # NovelEngine 引用（可选，用于联动钩子）
        self._on_advance_hooks: List = []     # tick 推进后的回调钩子列表

    def set_engine(self, engine):
        """设置引擎引用（用于 tick 推进后的自动联动）

        Args:
            engine: NovelEngine 实例
        """
        self._engine = engine

    def add_advance_hook(self, hook_fn):
        """添加 tick 推进后置钩子

        Args:
            hook_fn: 接受 (tick_id) 参数的回调函数
        """
        self._on_advance_hooks.append(hook_fn)

    # ─── 核心：添加与推进 ───

    def add_tick(self, chapter: int, scene: str, time_marker: str,
                 active_characters: List[str],
                 world_events: List[str] = None,
                 is_immutable: bool = False) -> WorldTick:
        """
        添加一个新的时间刻

        Args:
            chapter: 所属章节号
            scene: 场景名称
            time_marker: 时间标记
            active_characters: 活跃角色列表
            world_events: 世界事件列表（可选）
            is_immutable: 是否立即锁定

        Returns:
            新创建的 WorldTick 对象
        """
        # 生成 tick_id：在已有 tick 中找最大值 + 1
        if self.ticks:
            tick_id = max(t.tick_id for t in self.ticks) + 1
        else:
            tick_id = 1

        tick = WorldTick(
            tick_id=tick_id,
            chapter=chapter,
            scene=scene,
            time_marker=time_marker,
            active_characters=list(active_characters),
            world_events=list(world_events) if world_events else [],
            is_immutable=is_immutable,
        )
        self.ticks.append(tick)

        # 更新章节索引
        self.chapter_tick_map.setdefault(chapter, []).append(tick_id)

        # 更新当前指针到最后一个
        self.current_tick = len(self.ticks) - 1

        return tick

    def advance_tick(self) -> Optional[WorldTick]:
        """
        推进到下一个 tick，继承前一个 tick 的场景和活跃角色

        如果当前没有 tick，返回 None。
        新 tick 的章节、时间标记需要由外部设置（此处仅做骨架继承）。

        如果注册了 advance_hook，会在创建新 tick 后调用钩子，
        钩子可用于触发目标推进、碰撞检测等后续流程。
        （注意：钩子不应再次调用 advance_tick，否则会死循环）

        Returns:
            新创建的 WorldTick，或 None（无前置 tick 时）
        """
        prev = self.get_current_tick()
        if prev is None:
            return None

        # 基于前一个 tick 继承场景和角色
        new_tick = self.add_tick(
            chapter=prev.chapter,
            scene=prev.scene,
            time_marker=prev.time_marker,
            active_characters=list(prev.active_characters),
        )

        # 触发后置钩子
        if new_tick and self._on_advance_hooks:
            for hook in self._on_advance_hooks:
                try:
                    hook(new_tick.tick_id)
                except Exception as e:
                    print(f"[WorldTimeline] advance_hook 执行失败: {e}")

        return new_tick

    # ─── 查询 ───

    def get_tick(self, tick_id: int) -> Optional[WorldTick]:
        """
        根据 tick_id 获取时间刻

        Args:
            tick_id: 时间刻 ID

        Returns:
            WorldTick 对象，或 None
        """
        for t in self.ticks:
            if t.tick_id == tick_id:
                return t
        return None

    def get_ticks_for_chapter(self, chapter: int) -> List[WorldTick]:
        """
        获取指定章节的所有时间刻

        Args:
            chapter: 章节号

        Returns:
            WorldTick 列表（按 tick_id 升序）
        """
        tick_ids = self.chapter_tick_map.get(chapter, [])
        result = []
        for tid in tick_ids:
            t = self.get_tick(tid)
            if t is not None:
                result.append(t)
        return result

    def get_current_tick(self) -> Optional[WorldTick]:
        """
        获取当前 tick

        Returns:
            当前 WorldTick，或 None（时间轴为空时）
        """
        if 0 <= self.current_tick < len(self.ticks):
            return self.ticks[self.current_tick]
        return None

    def get_active_characters_at_tick(self, tick_id: int) -> List[str]:
        """
        获取指定 tick 的活跃角色列表

        Args:
            tick_id: 时间刻 ID

        Returns:
            角色名列表，找不到返回空列表
        """
        tick = self.get_tick(tick_id)
        if tick is None:
            return []
        return list(tick.active_characters)

    # ─── 修改 ───

    def make_tick_immutable(self, tick_id: int):
        """
        锁定一个 tick 为不可变

        被锁定的 tick 不能被引擎修改。通常在章节结束时调用。

        Args:
            tick_id: 要锁定的时间刻 ID
        """
        tick = self.get_tick(tick_id)
        if tick is not None:
            tick.is_immutable = True

    # ─── 序列化 ───

    def to_dict(self) -> dict:
        """序列化为字典（用于持久化或传输）"""
        return {
            "ticks": [t.to_dict() for t in self.ticks],
            "current_tick": self.current_tick,
            "chapter_tick_map": self.chapter_tick_map,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "WorldTimeline":
        """从字典反序列化"""
        tl = cls()
        for td in data.get("ticks", []):
            tick = WorldTick.from_dict(td)
            tl.ticks.append(tick)
        tl.current_tick = data.get("current_tick", 0)
        tl.chapter_tick_map = data.get("chapter_tick_map", {})
        return tl

    # ─── 统计 ───

    def get_stats(self) -> Dict:
        """返回时间轴统计信息"""
        # 统计各章节的 tick 数量
        chapter_counts = {
            ch: len(tids) for ch, tids in self.chapter_tick_map.items()
        }
        # 统计时间标记分布
        time_dist = {}
        for t in self.ticks:
            time_dist[t.time_marker] = time_dist.get(t.time_marker, 0) + 1
        # 统计不可变 tick 数
        immutable_count = sum(1 for t in self.ticks if t.is_immutable)
        return {
            "total_ticks": len(self.ticks),
            "current_tick_index": self.current_tick,
            "current_tick_id": self.get_current_tick().tick_id if self.get_current_tick() else None,
            "chapters": len(self.chapter_tick_map),
            "chapter_tick_counts": chapter_counts,
            "time_marker_distribution": time_dist,
            "immutable_ticks": immutable_count,
        }

    # ─── 持久化 ───

    def _load(self, project_dir: str):
        """
        从磁盘加载时间轴数据

        Args:
            project_dir: 项目目录路径
        """
        filepath = os.path.join(project_dir, "world_timeline.json")
        if not os.path.exists(filepath):
            return
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
            loaded = WorldTimeline.from_dict(data)
            self.ticks = loaded.ticks
            self.current_tick = loaded.current_tick
            self.chapter_tick_map = loaded.chapter_tick_map
            print(f"[WorldTimeline] 从 {filepath} 加载了 {len(self.ticks)} 个 tick")
        except Exception as e:
            print(f"[WorldTimeline] 加载失败: {e}")

    def _save(self, project_dir: str):
        """
        保存时间轴到磁盘

        Args:
            project_dir: 项目目录路径
        """
        os.makedirs(project_dir, exist_ok=True)
        filepath = os.path.join(project_dir, "world_timeline.json")
        try:
            data = self.to_dict()
            data["updated"] = time.strftime("%Y-%m-%d %H:%M")
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            print(f"[WorldTimeline] 已保存 {len(self.ticks)} 个 tick 到 {filepath}")
        except Exception as e:
            print(f"[WorldTimeline] 保存失败: {e}")
