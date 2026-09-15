# -*- coding: utf-8 -*-
"""
关系追踪系统 - 追踪角色之间的关系变化

核心功能：
1. 记录角色之间的关系状态（朋友、恋人、敌人等）
2. 检测叙事中的关系变化
3. 提供关系约束给 AI 生成时参考
"""

import re
from typing import List, Dict, Tuple, Optional, Set
from dataclasses import dataclass, field
from enum import Enum


class RelationType(Enum):
    """关系类型"""
    STRANGER = "陌生人"
    ACQUAINTANCE = "熟人"
    FRIEND = "朋友"
    CLOSE_FRIEND = "好友"
    LOVER = "恋人"
    SPOUSE = "配偶"
    FAMILY = "家人"
    ENEMY = "敌人"
    RIVAL = "对手"
    COLLEAGUE = "同事"
    NEIGHBOR = "邻居"
    STRANGER_TO_LOVER = "追求中"  # 从陌生人到恋人的过渡
    FRIEND_TO_LOVER = "暧昧"      # 从朋友到恋人的过渡


@dataclass
class Relation:
    """角色关系"""
    char1: str                   # 角色1
    char2: str                   # 角色2
    relation_type: RelationType  # 关系类型
    strength: float              # 关系强度 (0-1)
    history: List[str] = field(default_factory=list)  # 关系发展历史
    tick_established: int = 0    # 建立关系的 tick
    last_updated: int = 0        # 最后更新的 tick
    
    def to_summary(self) -> str:
        """生成关系摘要"""
        return f"{self.char1}与{self.char2}：{self.relation_type.value}（强度{self.strength:.1f}）"


class RelationshipTracker:
    """关系追踪系统"""
    
    # 关系变化关键词
    RELATION_PATTERNS = {
        # 恋爱相关
        RelationType.LOVER: [
            r"牵手", r"拥抱", r"表白", r"在一起", r"成为恋人",
            r"相爱", r"确立关系", r"交往", r"恋爱",
        ],
        RelationType.FRIEND_TO_LOVER: [
            r"脸红", r"心跳", r"紧张", r"局促", r"耳根红",
            r"指尖触碰", r"对视", r"温柔", r"害羞",
        ],
        RelationType.STRANGER_TO_LOVER: [
            r"追求", r"暗恋", r"心动", r"喜欢",
        ],
        
        # 友情相关
        RelationType.FRIEND: [
            r"成为朋友", r"交朋友", r"友谊", r"聊得来",
        ],
        RelationType.CLOSE_FRIEND: [
            r"好友", r"知己", r"死党", r"闺蜜", r"兄弟",
        ],
        
        # 敌对相关
        RelationType.ENEMY: [
            r"成为敌人", r"结仇", r"仇恨", r"对立",
        ],
        RelationType.RIVAL: [
            r"竞争", r"对手", r"较量",
        ],
        
        # 家庭相关
        RelationType.FAMILY: [
            r"家人", r"亲戚", r"父母", r"兄弟", r"姐妹",
        ],
        RelationType.SPOUSE: [
            r"结婚", r"夫妻", r"配偶", r"丈夫", r"妻子",
        ],
        
        # 其他
        RelationType.COLLEAGUE: [
            r"同事", r"一起工作", r"合作",
        ],
        RelationType.NEIGHBOR: [
            r"邻居", r"住在隔壁",
        ],
    }
    
    # 关系冲突检测
    CONFLICT_PATTERNS = [
        # 恋人关系冲突：如果 A 和 B 是恋人，不应该出现 A 和 C 的恋爱行为
        (RelationType.LOVER, RelationType.LOVER, "同一人不能同时与多人保持恋人关系"),
        (RelationType.SPOUSE, RelationType.SPOUSE, "同一人不能同时与多人保持配偶关系"),
    ]
    
    def __init__(self):
        self.relations: Dict[Tuple[str, str], Relation] = {}  # (char1, char2) -> Relation
        self._compiled_patterns = self._compile_patterns()
    
    def _compile_patterns(self) -> Dict[RelationType, List[re.Pattern]]:
        """编译关系识别的正则模式"""
        compiled = {}
        for rel_type, patterns in self.RELATION_PATTERNS.items():
            compiled[rel_type] = [re.compile(p) for p in patterns]
        return compiled
    
    def _make_key(self, char1: str, char2: str) -> Tuple[str, str]:
        """创建关系键（保证顺序一致）"""
        return tuple(sorted([char1, char2]))
    
    def get_relation(self, char1: str, char2: str) -> Optional[Relation]:
        """获取两个角色之间的关系"""
        key = self._make_key(char1, char2)
        return self.relations.get(key)
    
    def set_relation(self, char1: str, char2: str, relation_type: RelationType, 
                     strength: float = 0.5, tick: int = 0) -> Relation:
        """设置两个角色之间的关系"""
        key = self._make_key(char1, char2)
        
        # 检查关系冲突
        conflicts = self._check_conflicts(char1, char2, relation_type)
        if conflicts:
            # 记录冲突，但仍然设置关系（由上层决定如何处理）
            pass
        
        # 创建或更新关系
        if key in self.relations:
            relation = self.relations[key]
            old_type = relation.relation_type
            relation.relation_type = relation_type
            relation.strength = strength
            relation.last_updated = tick
            relation.history.append(f"[{tick}] 关系从 {old_type.value} 变为 {relation_type.value}")
        else:
            relation = Relation(
                char1=char1,
                char2=char2,
                relation_type=relation_type,
                strength=strength,
                tick_established=tick,
                last_updated=tick,
                history=[f"[{tick}] 建立关系：{relation_type.value}"],
            )
            self.relations[key] = relation
        
        return relation
    
    def _check_conflicts(self, char1: str, char2: str, new_type: RelationType) -> List[str]:
        """检查关系冲突"""
        conflicts = []
        
        for (existing_type, check_type, msg) in self.CONFLICT_PATTERNS:
            if new_type == check_type:
                # 检查 char1 是否已有此类型关系
                for (c1, c2), rel in self.relations.items():
                    if rel.relation_type == existing_type:
                        if (c1 == char1 or c2 == char1) and (c1 != char2 and c2 != char2):
                            conflicts.append(f"{char1} 已与 {c1 if c2 == char1 else c2} 有 {existing_type.value} 关系")
                        if (c1 == char2 or c2 == char2) and (c1 != char1 and c2 != char1):
                            conflicts.append(f"{char2} 已与 {c1 if c2 == char2 else c2} 有 {existing_type.value} 关系")
        
        return conflicts
    
    def detect_relation_change(self, narrative: str, characters: List[str], tick: int = 0) -> List[Tuple[str, str, RelationType]]:
        """
        从叙事中检测关系变化
        
        Args:
            narrative: 叙事文本
            characters: 已知角色列表
            tick: 当前 tick
        
        Returns:
            检测到的关系变化列表 [(char1, char2, new_relation_type), ...]
        """
        if not narrative or len(characters) < 2:
            return []
        
        changes = []
        
        # 检查每对角色
        for i, char1 in enumerate(characters):
            for char2 in characters[i+1:]:
                if char1 not in narrative or char2 not in narrative:
                    continue
                
                # 检查是否出现关系变化模式
                for rel_type, patterns in self._compiled_patterns.items():
                    for pattern in patterns:
                        if pattern.search(narrative):
                            # 检查两个角色是否都出现在模式附近
                            # 简单方法：检查叙事中是否同时包含两个角色名
                            if char1 in narrative and char2 in narrative:
                                changes.append((char1, char2, rel_type))
                                break
                    if changes and changes[-1][:2] == (char1, char2):
                        break
        
        return changes
    
    def update_from_narrative(self, narrative: str, characters: List[str], tick: int = 0) -> List[Relation]:
        """
        从叙事中更新关系
        
        Args:
            narrative: 叙事文本
            characters: 已知角色列表
            tick: 当前 tick
        
        Returns:
            更新的关系列表
        """
        changes = self.detect_relation_change(narrative, characters, tick)
        updated_relations = []
        
        for char1, char2, rel_type in changes:
            # 获取现有关系
            existing = self.get_relation(char1, char2)
            
            # 确定新关系强度
            if existing:
                # 如果已有关系，增加强度
                new_strength = min(existing.strength + 0.1, 1.0)
            else:
                new_strength = 0.5
            
            # 设置关系
            relation = self.set_relation(char1, char2, rel_type, new_strength, tick)
            updated_relations.append(relation)
        
        return updated_relations
    
    def get_all_relations_for_character(self, char: str) -> List[Relation]:
        """获取角色所有关系"""
        result = []
        for (c1, c2), rel in self.relations.items():
            if c1 == char or c2 == char:
                result.append(rel)
        return result
    
    def get_relation_summary(self, char: str) -> str:
        """获取角色关系摘要"""
        relations = self.get_all_relations_for_character(char)
        if not relations:
            return ""
        
        lines = [f"【{char}的关系】"]
        for rel in relations:
            other = rel.char2 if rel.char1 == char else rel.char1
            lines.append(f"- {other}：{rel.relation_type.value}")
        
        return "\n".join(lines)
    
    def get_context_for_ai(self, characters: List[str] = None, max_length: int = 300) -> str:
        """生成给 AI 参考的关系上下文"""
        if not self.relations:
            return ""
        
        lines = ["【角色关系】（请遵守以下关系设定）"]
        total_len = len(lines[0])
        
        if characters:
            # 只显示涉及指定角色的关系
            char_set = set(characters)
            relations_to_show = [
                rel for (c1, c2), rel in self.relations.items()
                if c1 in char_set or c2 in char_set
            ]
        else:
            relations_to_show = list(self.relations.values())
        
        for rel in relations_to_show:
            summary = rel.to_summary()
            if total_len + len(summary) > max_length:
                break
            lines.append(summary)
            total_len += len(summary)
        
        if len(lines) > 1:
            return "\n".join(lines)
        return ""
    
    def check_consistency(self, narrative: str, characters: List[str]) -> List[str]:
        """
        检查叙事是否与关系设定一致
        
        Returns:
            不一致的问题列表
        """
        issues = []
        
        # 检查恋人关系冲突
        for (c1, c2), rel in self.relations.items():
            if rel.relation_type == RelationType.LOVER:
                # 如果 A 和 B 是恋人，检查是否有 A 和其他人的恋爱行为
                for char in characters:
                    if char != c1 and char != c2:
                        # 检查是否有 c1 和 char 的恋爱行为
                        for pattern in self._compiled_patterns.get(RelationType.LOVER, []):
                            if pattern.search(narrative):
                                if c1 in narrative and char in narrative:
                                    issues.append(f"{c1} 已与 {c2} 是恋人，不应与 {char} 有恋爱行为")
                                if c2 in narrative and char in narrative:
                                    issues.append(f"{c2} 已与 {c1} 是恋人，不应与 {char} 有恋爱行为")
        
        return issues
    
    def clear(self):
        """清空所有关系"""
        self.relations.clear()
    
    def to_dict(self) -> dict:
        """序列化为字典"""
        return {
            "relations": [
                {
                    "char1": rel.char1,
                    "char2": rel.char2,
                    "relation_type": rel.relation_type.value,
                    "strength": rel.strength,
                    "history": rel.history,
                    "tick_established": rel.tick_established,
                    "last_updated": rel.last_updated,
                }
                for rel in self.relations.values()
            ]
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'RelationshipTracker':
        """从字典反序列化"""
        tracker = cls()
        for r_data in data.get("relations", []):
            # 找到对应的 RelationType
            rel_type = RelationType.STRANGER
            for rt in RelationType:
                if rt.value == r_data["relation_type"]:
                    rel_type = rt
                    break
            
            key = tuple(sorted([r_data["char1"], r_data["char2"]]))
            relation = Relation(
                char1=r_data["char1"],
                char2=r_data["char2"],
                relation_type=rel_type,
                strength=r_data["strength"],
                history=r_data.get("history", []),
                tick_established=r_data.get("tick_established", 0),
                last_updated=r_data.get("last_updated", 0),
            )
            tracker.relations[key] = relation
        return tracker


# 全局单例
_relationship_tracker_instance: Optional[RelationshipTracker] = None


def get_relationship_tracker() -> RelationshipTracker:
    """获取关系追踪系统单例"""
    global _relationship_tracker_instance
    if _relationship_tracker_instance is None:
        _relationship_tracker_instance = RelationshipTracker()
    return _relationship_tracker_instance


def reset_relationship_tracker():
    """重置关系追踪系统"""
    global _relationship_tracker_instance
    _relationship_tracker_instance = None
