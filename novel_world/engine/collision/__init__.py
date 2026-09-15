# -*- coding: utf-8 -*-
"""
碰撞引擎包 - 导出核心类
"""
from .collision_engine import (
    CollisionEngine,
    CollisionEvent,
    EntryScene,
    EntryMotivation,
    ChapterTimeline,
)
from .weight_loader import WeightConfig
from .weight_calibrator import WeightCalibrator

__all__ = [
    "CollisionEngine",
    "CollisionEvent",
    "EntryScene",
    "EntryMotivation",
    "ChapterTimeline",
    "WeightConfig",
    "WeightCalibrator",
]
