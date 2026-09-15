# -*- coding: utf-8 -*-
"""节奏控制器 - 调节冲突触发概率"""
from enum import Enum

class PaceLevel(Enum):
    SLOW = "慢"      # x0.5
    NORMAL = "正常"  # x1.0
    FAST = "快"      # x1.5
    INTENSE = "激烈" # x2.0

class PaceController:
    MULTIPLIERS = {
        PaceLevel.SLOW: 0.5,
        PaceLevel.NORMAL: 1.0,
        PaceLevel.FAST: 1.5,
        PaceLevel.INTENSE: 2.0,
    }
    
    def __init__(self, pace: PaceLevel = PaceLevel.NORMAL):
        self._pace = pace
    
    def set_pace(self, pace: PaceLevel):
        self._pace = pace
        print(f"PaceController: pace set to {pace.value}")
    
    def get_pace(self) -> PaceLevel:
        return self._pace
    
    def adjust_probability(self, base_prob: float) -> float:
        return min(1.0, base_prob * self.MULTIPLIERS[self._pace])
    
    def should_trigger(self, base_prob: float) -> bool:
        import random
        return random.random() < self.adjust_probability(base_prob)

_pace = None
def get_pace_controller() -> PaceController:
    global _pace
    if _pace is None:
        _pace = PaceController()
    return _pace
