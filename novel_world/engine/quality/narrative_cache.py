# -*- coding: utf-8 -*-
"""
叙事缓存管理器 - 解决内容复用优化问题
提供智能缓存和复用管理，支持：
- 叙事元素缓存（场景、动作、对话等）
- 智能去重（避免重复使用相同元素）
- 冷却机制（元素使用后需要冷却才能再次使用）
- 变化追踪（追踪元素的变化历史）
"""
from typing import Dict, List, Optional, Set, Tuple
from dataclasses import dataclass, field
from enum import Enum
import random
from collections import defaultdict
import time


class ElementType(Enum):
    """叙事元素类型"""
    SCENE = "场景"
    ACTION = "动作"
    DIALOGUE = "对话"
    DESCRIPTION = "描述"
    EMOTION = "情感"
    CONFLICT = "矛盾"
    TRANSITION = "过渡"


@dataclass
class CacheEntry:
    """缓存条目"""
    element_type: ElementType
    content: str
    key: str  # 用于去重的键
    use_count: int = 0
    last_used: int = 0  # 时间戳
    cooldown: int = 3  # 冷却回合数
    variations: List[str] = field(default_factory=list)  # 变体


@dataclass
class UsageRecord:
    """使用记录"""
    element_key: str
    element_type: ElementType
    round_number: int
    context: str = ""


class NarrativeCache:
    """叙事缓存管理器"""
    
    def __init__(self):
        self._cache: Dict[str, CacheEntry] = {}
        self._usage_history: List[UsageRecord] = []
        self._round_number: int = 0
        self._cooldown_tracker: Dict[str, int] = {}  # key -> 剩余冷却回合
        self._pattern_cache: Dict[str, int] = defaultdict(int)  # 句式模式缓存
        self._max_history = 100
        self._max_pattern_repeat = 2  # 同一句式最大重复次数
        
        # 预定义的叙事模板和变体
        self._scene_templates: Dict[str, List[str]] = {}
        self._dialogue_templates: Dict[str, List[str]] = {}
        self._transition_templates: List[str] = []
        
        self._initialize_templates()
    
    def _initialize_templates(self):
        """初始化叙事模板"""
        
        # 场景描述模板（带变体）
        self._scene_templates = {
            "进入场景": [
                "踏入{scene}，{detail}",
                "来到{scene}，只见{detail}",
                "走进{scene}，眼前{detail}",
                "步入{scene}，四周{detail}",
            ],
            "观察场景": [
                "环顾{scene}，{detail}",
                "打量着{scene}，{detail}",
                "目光扫过{scene}，{detail}",
            ],
            "离开场景": [
                "离开{scene}，{feeling}",
                "走出{scene}，心中{feeling}",
                "告别{scene}，{feeling}",
            ],
        }
        
        # 对话模板
        self._dialogue_templates = {
            "询问": [
                "「{content}」{name}问道",
                "「{content}」{name}出声询问",
                "{name}开口问道：「{content}」",
            ],
            "回答": [
                "「{content}」{name}回答道",
                "{name}回应道：「{content}」",
                "「{content}」{name}说道",
            ],
            "感叹": [
                "「{content}」{name}感叹道",
                "{name}叹道：「{content}」",
                "「{content}」{name}叹息",
            ],
            "低语": [
                "「{content}」{name}低声说道",
                "{name}低语道：「{content}」",
                "「{content}」{name}轻声说",
            ],
        }
        
        # 过渡句模板
        self._transition_templates = [
            "时间悄然流逝。",
            "片刻之后。",
            "一阵沉默。",
            "气氛有些微妙。",
            "风轻轻吹过。",
            "周围安静下来。",
            "时间一分一秒过去。",
            "没有人说话。",
            "远处传来些许声响。",
            "天色渐渐变化。",
        ]
    
    def register_element(self, element_type: ElementType, content: str,
                        key: str = None, variations: List[str] = None,
                        cooldown: int = 3) -> str:
        """
        注册叙事元素
        返回元素的key
        """
        if not key:
            # 根据内容生成key
            key = f"{element_type.value}:{content[:20]}"
        
        entry = CacheEntry(
            element_type=element_type,
            content=content,
            key=key,
            cooldown=cooldown,
            variations=variations or []
        )
        
        self._cache[key] = entry
        return key
    
    def get_element(self, key: str, allow_variations: bool = True) -> Optional[str]:
        """获取叙事元素（考虑冷却）"""
        entry = self._cache.get(key)
        if not entry:
            return None
        
        # 检查冷却
        remaining_cooldown = self._cooldown_tracker.get(key, 0)
        if remaining_cooldown > 0:
            return None  # 还在冷却中
        
        # 更新使用记录
        entry.use_count += 1
        entry.last_used = int(time.time())
        self._cooldown_tracker[key] = entry.cooldown
        
        # 记录使用历史
        self._usage_history.append(UsageRecord(
            element_key=key,
            element_type=entry.element_type,
            round_number=self._round_number
        ))
        
        # 返回内容或变体
        if allow_variations and entry.variations:
            # 优先返回未使用过的变体
            unused_variations = [v for v in entry.variations 
                               if v not in [r.element_key for r in self._usage_history[-20:]]]
            if unused_variations:
                return random.choice(unused_variations)
        
        return entry.content
    
    def get_fresh_element(self, element_type: ElementType, 
                         candidates: List[str]) -> Optional[str]:
        """
        获取新鲜的元素（未使用或冷却已过）
        从候选列表中选择
        """
        # 过滤掉还在冷却中的
        available = []
        for content in candidates:
            key = f"{element_type.value}:{content[:20]}"
            remaining = self._cooldown_tracker.get(key, 0)
            if remaining == 0:
                available.append(content)
        
        if not available:
            # 所有都在冷却中，重置冷却最久的
            oldest_key = min(self._cooldown_tracker.keys(), 
                           key=lambda k: self._cache.get(k, CacheEntry(ElementType.SCENE, "", k)).last_used)
            self._cooldown_tracker[oldest_key] = 0
            available = candidates
        
        selected = random.choice(available)
        
        # 注册并设置冷却
        self.register_element(element_type, selected)
        
        return selected
    
    def get_scene_description(self, template_type: str, scene: str, 
                             detail: str, feeling: str = "") -> str:
        """获取场景描述（自动去重）"""
        templates = self._scene_templates.get(template_type, [])
        
        if not templates:
            return f"在{scene}，{detail}"
        
        # 选择未重复的模板
        for _ in range(len(templates)):
            template = random.choice(templates)
            pattern_key = f"scene:{template}"
            
            if self._pattern_cache[pattern_key] < self._max_pattern_repeat:
                self._pattern_cache[pattern_key] += 1
                return template.format(scene=scene, detail=detail, feeling=feeling)
        
        # 所有模板都用过了，使用基础描述
        return f"在{scene}，{detail}"
    
    def get_dialogue(self, dialogue_type: str, name: str, content: str) -> str:
        """获取对话描述（自动去重）"""
        templates = self._dialogue_templates.get(dialogue_type, [])
        
        if not templates:
            return f"「{content}」{name}说道"
        
        # 选择模板
        template = random.choice(templates)
        return template.format(name=name, content=content)
    
    def get_transition(self) -> str:
        """获取过渡句"""
        # 选择未重复的过渡句
        available = [t for t in self._transition_templates 
                    if self._pattern_cache.get(f"transition:{t}", 0) < self._max_pattern_repeat]
        
        if not available:
            available = self._transition_templates
        
        selected = random.choice(available)
        self._pattern_cache[f"transition:{selected}"] += 1
        
        return selected
    
    def is_element_used_recently(self, key: str, rounds: int = 3) -> bool:
        """检查元素是否在最近N回合内使用过"""
        recent_usage = [r for r in self._usage_history 
                       if r.round_number >= self._round_number - rounds]
        return any(r.element_key == key for r in recent_usage)
    
    def get_usage_stats(self, element_type: ElementType = None) -> Dict:
        """获取使用统计"""
        stats = {
            "total_elements": len(self._cache),
            "total_usage": len(self._usage_history),
            "current_round": self._round_number,
        }
        
        if element_type:
            type_usage = [r for r in self._usage_history if r.element_type == element_type]
            stats["type_usage"] = len(type_usage)
        
        return stats
    
    def advance_round(self):
        """推进回合（更新冷却）"""
        self._round_number += 1
        
        # 更新所有冷却
        for key in list(self._cooldown_tracker.keys()):
            if self._cooldown_tracker[key] > 0:
                self._cooldown_tracker[key] -= 1
    
    def add_pattern(self, pattern: str) -> bool:
        """
        添加句式模式并检查是否重复
        返回 True 如果可以继续使用，False 如果应该避免
        """
        self._pattern_cache[pattern] += 1
        return self._pattern_cache[pattern] <= self._max_pattern_repeat
    
    def clear_cooldowns(self):
        """清除所有冷却"""
        self._cooldown_tracker.clear()
    
    def reset(self):
        """完全重置"""
        self._cache.clear()
        self._usage_history.clear()
        self._cooldown_tracker.clear()
        self._pattern_cache.clear()
        self._round_number = 0
    
    def get_recent_elements(self, count: int = 10) -> List[str]:
        """获取最近使用的元素"""
        recent = self._usage_history[-count:]
        return [r.element_key for r in recent]
    
    def avoid_repetition(self, content: str, similarity_threshold: float = 0.7) -> bool:
        """
        检查内容是否与最近的内容过于相似
        返回 True 表示应该避免（太相似），False 表示可以使用
        """
        recent_contents = [self._cache[r.element_key].content 
                         for r in self._usage_history[-5:] 
                         if r.element_key in self._cache]
        
        for recent in recent_contents:
            # 简单的相似度检查
            if self._calculate_similarity(content, recent) > similarity_threshold:
                return True
        
        return False
    
    def _calculate_similarity(self, text1: str, text2: str) -> float:
        """计算文本相似度（简单实现）"""
        if not text1 or not text2:
            return 0.0
        
        # 使用共同字符比例作为相似度
        set1 = set(text1)
        set2 = set(text2)
        
        intersection = len(set1 & set2)
        union = len(set1 | set2)
        
        if union == 0:
            return 0.0
        
        return intersection / union


# 单例模式
_narrative_cache_instance = None

def get_narrative_cache() -> NarrativeCache:
    """获取叙事缓存单例"""
    global _narrative_cache_instance
    if _narrative_cache_instance is None:
        _narrative_cache_instance = NarrativeCache()
    return _narrative_cache_instance
