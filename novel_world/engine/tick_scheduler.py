# -*- coding: utf-8 -*-
"""
三层 Tick 调度器 — 快/中/慢三层时间架构

架构层映射：
    每章 = N 个慢Tick
    每个慢Tick = M 个中Tick
    每个中Tick = K 个快Tick

比例默认：慢:中:快 = 1:5:10（可配置）

快Tick（玩家交互层）：
    - 联网模式：接收玩家操作、即时技能响应、移动
    - 离线模式：跳过（NOP）

中Tick（AI 自主层）：
    - 角色依据目标移动
    - 碰撞检测（三重碰撞扫描）
    - 叙事生成（微型叙事单元）

慢Tick（世界刷新层）：
    - World Skill 刷新（灵气潮汐/天道压制/禁制之地）
    - 气息残留衰减
    - 地脉灵机更新
    - 区域监控衰减
    - 账本归档
    - 章节快照
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class TickLevel(Enum):
    FAST = "fast"      # 玩家交互层
    MEDIUM = "medium"  # AI 自主层
    SLOW = "slow"      # 世界刷新层


@dataclass
class TickConfig:
    """三层 Tick 配置"""
    slow_ticks_per_chapter: int = 1        # 每章慢Tick数
    medium_per_slow: int = 5               # 每慢Tick的中Tick数
    fast_per_medium: int = 10              # 每中Tick的快Tick数
    offline_mode: bool = False             # 离线模式：True时跳过快Tick

    @property
    def medium_ticks_per_chapter(self) -> int:
        return self.slow_ticks_per_chapter * self.medium_per_slow

    @property
    def fast_ticks_per_chapter(self) -> int:
        return self.slow_ticks_per_chapter * self.medium_per_slow * self.fast_per_medium


@dataclass
class TickFrame:
    """单帧 Tick 上下文"""
    chapter: int = 0
    slow_tick: int = 0
    medium_tick: int = 0
    fast_tick: int = 0
    level: TickLevel = TickLevel.SLOW
    is_chapter_start: bool = False
    is_chapter_end: bool = False
    is_slow_start: bool = False
    is_slow_end: bool = False
    is_medium_start: bool = False
    is_medium_end: bool = False


class TickScheduler:
    """
    三层 Tick 调度器。

    使用方式：
        scheduler = TickScheduler(TickConfig(slow_ticks_per_chapter=1))
        for frame in scheduler:
            if frame.level == TickLevel.FAST:
                # 玩家交互（离线模式跳过）
                pass
            elif frame.level == TickLevel.MEDIUM:
                # 角色移动 + 碰撞 + 叙事
                pass
            elif frame.level == TickLevel.SLOW:
                # World Skill 刷新 + 衰减 + 快照
                pass
    """

    def __init__(self, config: TickConfig = None):
        self.config = config or TickConfig()
        self._chapter = 0
        self._slow = 0
        self._medium = 0
        self._fast = 0
        self._total_ticks = 0
        self._done = False

        # 回调钩子：每层 Tick 完成时调用，参数为 TickFrame
        self.on_slow_tick = None      # Callable[[TickFrame], None]
        self.on_medium_tick = None    # Callable[[TickFrame], None]
        self.on_fast_tick = None      # Callable[[TickFrame], None]
        # 章节开始/结束回调
        self.on_chapter_start = None  # Callable[[TickFrame], None]
        self.on_chapter_end = None    # Callable[[TickFrame], None]

    def reset(self, chapter: int = 0):
        """重置到指定章节"""
        self._chapter = chapter
        self._slow = 0
        self._medium = 0
        self._fast = 0
        self._total_ticks = 0
        self._done = False

    def _next_frame(self) -> Optional[TickFrame]:
        """推进一帧，返回 TickFrame 或 None（章节结束）"""
        if self._done:
            return None

        slow_max = self.config.slow_ticks_per_chapter

        # 确定当前层级
        # 快Tick检测
        if self._fast < self.config.fast_per_medium - 1:
            self._fast += 1
            self._total_ticks += 1
            return TickFrame(
                chapter=self._chapter,
                slow_tick=self._slow,
                medium_tick=self._medium,
                fast_tick=self._fast,
                level=TickLevel.FAST,
            )
        # 中Tick检测
        elif self._medium < self.config.medium_per_slow - 1:
            self._fast = 0
            self._medium += 1
            self._total_ticks += 1
            return TickFrame(
                chapter=self._chapter,
                slow_tick=self._slow,
                medium_tick=self._medium,
                fast_tick=0,
                level=TickLevel.MEDIUM,
                is_medium_start=True,
            )
        # 慢Tick检测
        elif self._slow < slow_max - 1:
            self._fast = 0
            self._medium = 0
            self._slow += 1
            self._total_ticks += 1

            prev_is_slow_end = self._slow == slow_max - 1
            return TickFrame(
                chapter=self._chapter,
                slow_tick=self._slow,
                medium_tick=0,
                fast_tick=0,
                level=TickLevel.SLOW,
                is_slow_start=True,
                is_slow_end=prev_is_slow_end,
                is_chapter_end=prev_is_slow_end,
            )
        else:
            # 章节结束
            self._done = True
            return TickFrame(
                chapter=self._chapter,
                slow_tick=self._slow,
                medium_tick=self._medium,
                fast_tick=self._fast,
                level=TickLevel.SLOW,
                is_slow_end=True,
                is_chapter_end=True,
            )

    def start_chapter(self, chapter: int):
        """开始新章节"""
        self.reset(chapter)
        # 下发章节起始帧
        return TickFrame(
            chapter=chapter,
            slow_tick=0,
            medium_tick=0,
            fast_tick=0,
            level=TickLevel.SLOW,
            is_chapter_start=True,
            is_slow_start=True,
        )

    def __iter__(self):
        return self

    def __next__(self) -> TickFrame:
        frame = self._next_frame()
        if frame is None:
            raise StopIteration
        return frame

    @property
    def total_ticks(self) -> int:
        return self._total_ticks

    @property
    def current_chapter(self) -> int:
        return self._chapter

    def run_chapter(self, chapter_num: int):
        """
        运行一整章：从 start_chapter 开始，遍历所有 Tick，
        并在每层 Tick 触发对应回调。

        离线模式（offline_mode=True）时跳过快 Tick，仅执行慢/中 Tick。

        Args:
            chapter_num: 章节号
        """
        frame = self.start_chapter(chapter_num)

        if self.on_chapter_start:
            self.on_chapter_start(frame)

        # 初始帧先触发慢Tick回调（章节开始帧）
        if self.on_slow_tick and frame.level == TickLevel.SLOW:
            self.on_slow_tick(frame)

        for frame in self:
            if frame.level == TickLevel.FAST:
                if self.config.offline_mode:
                    continue
                if self.on_fast_tick:
                    self.on_fast_tick(frame)
            elif frame.level == TickLevel.MEDIUM:
                if self.on_medium_tick:
                    self.on_medium_tick(frame)
            elif frame.level == TickLevel.SLOW:
                if self.on_slow_tick:
                    self.on_slow_tick(frame)

            if frame.is_chapter_end and self.on_chapter_end:
                self.on_chapter_end(frame)
