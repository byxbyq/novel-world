# -*- coding: utf-8 -*-
"""事件参考系统 - 基于人生重开游戏事件"""
import os, json, random
from typing import Dict, List, Optional
from dataclasses import dataclass

@dataclass
class LifeEvent:
    age: int
    event: str

class EventReference:
    def __init__(self):
        self._events: Dict[int, List[LifeEvent]] = {}
        self._all: List[LifeEvent] = []
        self._load()
    
    def _load(self):
        # 内置事件
        builtin = {
            0: ["你出生了", "你出生时哭声嘹亮", "你出生时安静如天使"],
            1: ["你学会了叫妈妈", "你学会了叫爸爸", "你开始蹒跚学步"],
            3: ["你上幼儿园了", "你在幼儿园交到第一个朋友"],
            6: ["你上小学了", "你第一次考试得满分", "你在学校被同学欺负"],
            12: ["你上初中了", "你开始对异性产生好奇", "你迷上网络游戏"],
            15: ["你上高中了", "你暗恋上同学", "你的成绩开始下滑"],
            18: ["你高考了", "你考上大学", "你高考失利"],
            22: ["你大学毕业", "你找到第一份工作", "你考研成功"],
            25: ["你升职了", "你谈了恋爱", "你开始考虑买房"],
            30: ["你结婚了", "你有孩子了", "你事业步入正轨"],
        }
        for age, events in builtin.items():
            self._events[age] = [LifeEvent(age, e) for e in events]
            self._all.extend(self._events[age])
        print(f"EventReference: {len(self._all)} events loaded")
    
    def get_examples(self, age: int = None, count: int = 5) -> List[str]:
        if age and age in self._events:
            pool = self._events[age]
        else:
            pool = self._all
        return random.sample([e.event for e in pool], min(count, len(pool)))
    
    def generate_prompt(self, age: int, theme: str) -> str:
        examples = self.get_examples(age, 3)
        return "参考事件:\n" + "\n".join(f"- {e}" for e in examples) + f"\n请根据【{theme}】主题生成类似风格的事件。"

_ref = None
def get_event_reference() -> EventReference:
    global _ref
    if _ref is None:
        _ref = EventReference()
    return _ref
