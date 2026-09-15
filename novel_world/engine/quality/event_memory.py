# -*- coding: utf-8 -*-
"""
事件记忆系统 - 记录已发生的事件，避免重复叙事

核心功能：
1. 记录每个事件的摘要（谁、做什么、结果）
2. 检查新事件是否与已发生事件重复
3. 提供事件历史给 AI 生成时参考
"""

import re
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class EventRecord:
    """事件记录"""
    tick: int                    # 发生时的 tick
    characters: List[str]        # 涉及的角色
    action: str                  # 动作/事件类型
    location: str                # 地点
    result: str                  # 结果
    raw_text: str                # 原始叙事文本
    keywords: List[str] = field(default_factory=list)  # 关键词
    
    def to_summary(self) -> str:
        """生成事件摘要"""
        chars = "、".join(self.characters[:3])  # 最多显示3个角色
        return f"[{self.tick}] {chars}在{self.location}{self.action}，{self.result}"
    
    def similarity_to(self, other: 'EventRecord') -> float:
        """计算与另一个事件的相似度 (0-1)"""
        score = 0.0
        
        # 角色重叠
        char_overlap = len(set(self.characters) & set(other.characters))
        char_union = len(set(self.characters) | set(other.characters))
        if char_union > 0:
            score += 0.3 * (char_overlap / char_union)
        
        # 动作相似
        if self.action == other.action:
            score += 0.3
        elif self.action in other.action or other.action in self.action:
            score += 0.15
        
        # 地点相同
        if self.location == other.location:
            score += 0.2
        
        # 关键词重叠
        kw_overlap = len(set(self.keywords) & set(other.keywords))
        kw_union = len(set(self.keywords) | set(other.keywords))
        if kw_union > 0:
            score += 0.2 * (kw_overlap / kw_union)
        
        return score


class EventMemory:
    """事件记忆系统"""
    
    MAX_EVENTS = 100             # 最多记录的事件数
    RECENT_WINDOW = 20           # 最近事件窗口（用于去重检查）
    SIMILARITY_THRESHOLD = 0.6   # 相似度阈值（超过则认为重复）
    
    # 常见动作关键词
    ACTION_KEYWORDS = {
        "递送": ["递", "送", "给", "递给", "送给", "递过来", "送过去"],
        "触碰": ["触碰", "碰到", "触到", "手指", "指尖", "手心"],
        "对话": ["说", "问", "答", "道", "轻声", "笑着", "嘟囔"],
        "移动": ["走", "来", "去", "离开", "到达", "进入"],
        "情感": ["脸红", "紧张", "心跳", "耳根红", "局促"],
        "饮食": ["喝", "吃", "尝", "温水", "热水", "牛奶", "蛋糕"],
        "关系": ["牵手", "拥抱", "表白", "约定", "结婚"],
        "居住": ["搬来", "住", "同居", "搬走"],
    }
    
    # 地点关键词
    LOCATION_KEYWORDS = [
        "玄关", "客厅", "厨房", "卧室", "阳台",
        "街道", "公园", "咖啡", "便利店", "医院",
        "公司", "办公室", "学校", "书店",
    ]
    
    def __init__(self):
        self.events: List[EventRecord] = []
        self._action_patterns = self._compile_action_patterns()
    
    def _compile_action_patterns(self) -> Dict[str, re.Pattern]:
        """编译动作识别的正则模式"""
        patterns = {}
        for action_type, keywords in self.ACTION_KEYWORDS.items():
            pattern = "|".join(re.escape(kw) for kw in keywords)
            patterns[action_type] = re.compile(pattern)
        return patterns
    
    def record_event(self, tick: int, narrative: str, characters: List[str] = None) -> Optional[EventRecord]:
        """
        从叙事文本中提取并记录事件
        
        Args:
            tick: 当前 tick
            narrative: 叙事文本
            characters: 已知角色列表（用于识别）
        
        Returns:
            EventRecord 如果成功提取，否则 None
        """
        if not narrative or len(narrative) < 10:
            return None
        
        # 提取涉及的角色
        involved_chars = self._extract_characters(narrative, characters or [])
        if not involved_chars:
            return None
        
        # 提取动作类型
        action = self._extract_action(narrative)
        
        # 提取地点
        location = self._extract_location(narrative)
        
        # 提取结果（简化）
        result = self._extract_result(narrative)
        
        # 提取关键词
        keywords = self._extract_keywords(narrative)
        
        # 创建事件记录
        event = EventRecord(
            tick=tick,
            characters=involved_chars,
            action=action,
            location=location,
            result=result,
            raw_text=narrative,
            keywords=keywords,
        )
        
        # 添加到事件列表
        self.events.append(event)
        
        # 限制事件数量
        if len(self.events) > self.MAX_EVENTS:
            self.events = self.events[-self.MAX_EVENTS:]
        
        return event
    
    def _extract_characters(self, narrative: str, known_chars: List[str]) -> List[str]:
        """从叙事中提取涉及的角色"""
        found = []
        for char in known_chars:
            if char in narrative:
                found.append(char)
        return found
    
    def _extract_action(self, narrative: str) -> str:
        """提取动作类型"""
        for action_type, pattern in self._action_patterns.items():
            if pattern.search(narrative):
                return action_type
        return "其他"
    
    def _extract_location(self, narrative: str) -> str:
        """提取地点"""
        for loc in self.LOCATION_KEYWORDS:
            if loc in narrative:
                return loc
        return "某处"
    
    def _extract_result(self, narrative: str) -> str:
        """提取结果（简化为前30字）"""
        # 尝试找到结果部分
        result_markers = ["，", "。", "后", "时"]
        for marker in result_markers:
            if marker in narrative:
                parts = narrative.split(marker, 1)
                if len(parts) > 1 and len(parts[1]) > 5:
                    return parts[1][:30].strip()
        return narrative[:30].strip()
    
    def _extract_keywords(self, narrative: str) -> List[str]:
        """提取关键词（2-4字的词）"""
        keywords = []
        # 提取中文词
        words = re.findall(r'[一-鿿]{2,4}', narrative)
        # 过滤常见虚词
        stop_words = {"的", "了", "是", "在", "有", "和", "与", "或", "我", "你", "他", "她"}
        for word in words:
            if word not in stop_words and len(word) >= 2:
                keywords.append(word)
        return list(set(keywords))[:10]
    
    def is_duplicate(self, narrative: str, characters: List[str] = None) -> Tuple[bool, float, Optional[EventRecord]]:
        """
        检查叙事是否与最近事件重复
        
        Args:
            narrative: 新叙事文本
            characters: 已知角色列表
        
        Returns:
            (是否重复, 相似度, 最相似的已发生事件)
        """
        if not self.events:
            return (False, 0.0, None)
        
        # 提取新事件的特征
        new_chars = self._extract_characters(narrative, characters or [])
        new_action = self._extract_action(narrative)
        new_location = self._extract_location(narrative)
        new_keywords = self._extract_keywords(narrative)
        
        # 创建临时事件记录用于比较
        new_event = EventRecord(
            tick=0,
            characters=new_chars,
            action=new_action,
            location=new_location,
            result="",
            raw_text=narrative,
            keywords=new_keywords,
        )
        
        # 与最近事件比较
        recent_events = self.events[-self.RECENT_WINDOW:]
        max_similarity = 0.0
        most_similar = None
        
        for event in recent_events:
            sim = event.similarity_to(new_event)
            if sim > max_similarity:
                max_similarity = sim
                most_similar = event
        
        is_dup = max_similarity >= self.SIMILARITY_THRESHOLD
        return (is_dup, max_similarity, most_similar)
    
    def get_recent_events(self, count: int = 10) -> List[EventRecord]:
        """获取最近的事件"""
        return self.events[-count:] if self.events else []
    
    def get_events_by_characters(self, characters: List[str], limit: int = 10) -> List[EventRecord]:
        """获取涉及指定角色的事件"""
        result = []
        char_set = set(characters)
        for event in reversed(self.events):
            if char_set & set(event.characters):
                result.append(event)
                if len(result) >= limit:
                    break
        return result
    
    def get_events_by_action(self, action: str, limit: int = 10) -> List[EventRecord]:
        """获取指定动作类型的事件"""
        result = []
        for event in reversed(self.events):
            if event.action == action:
                result.append(event)
                if len(result) >= limit:
                    break
        return result
    
    def get_context_for_ai(self, max_length: int = 500) -> str:
        """生成给 AI 参考的事件上下文"""
        if not self.events:
            return ""
        
        recent = self.get_recent_events(15)
        lines = ["【已发生的事件】（请勿重复以下事件）"]
        
        total_len = 0
        for event in recent:
            summary = event.to_summary()
            if total_len + len(summary) > max_length:
                break
            lines.append(summary)
            total_len += len(summary)
        
        if len(lines) > 1:
            return "\n".join(lines)
        return ""
    
    def clear(self):
        """清空事件记忆"""
        self.events.clear()
    
    def to_dict(self) -> dict:
        """序列化为字典"""
        return {
            "events": [
                {
                    "tick": e.tick,
                    "characters": e.characters,
                    "action": e.action,
                    "location": e.location,
                    "result": e.result,
                    "raw_text": e.raw_text,
                    "keywords": e.keywords,
                }
                for e in self.events
            ]
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'EventMemory':
        """从字典反序列化"""
        memory = cls()
        for e_data in data.get("events", []):
            event = EventRecord(
                tick=e_data["tick"],
                characters=e_data["characters"],
                action=e_data["action"],
                location=e_data["location"],
                result=e_data["result"],
                raw_text=e_data["raw_text"],
                keywords=e_data.get("keywords", []),
            )
            memory.events.append(event)
        return memory


# 全局单例
_event_memory_instance: Optional[EventMemory] = None


def get_event_memory() -> EventMemory:
    """获取事件记忆系统单例"""
    global _event_memory_instance
    if _event_memory_instance is None:
        _event_memory_instance = EventMemory()
    return _event_memory_instance


def reset_event_memory():
    """重置事件记忆系统"""
    global _event_memory_instance
    _event_memory_instance = None
