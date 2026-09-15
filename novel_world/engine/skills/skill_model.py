# -*- coding: utf-8 -*-
"""
Skill系统 - 人物Skill四维度 + 世界Skill + 双目标
"""
from dataclasses import dataclass, field
from typing import List, Dict, Optional
from enum import Enum


class SkillType(Enum):
    """技能类型"""
    PASSIVE = "被动"       # 被动技能：核心特质，永久生效
    ACTIVE = "主动"        # 主动技能：可主动使用的手段
    LIMIT = "限制"         # 技能限制：盲点、做不到的事
    COST = "代价"          # 技能代价：使用后的后遗症/心魔/隐患


class CollisionType(Enum):
    """碰撞类型"""
    PERCEPTION = "感知对冲"    # 信息差戏：一方泄露、一方感知、一方盲区
    GOAL = "目标对冲"          # 立场戏：目的地相同但目的相反
    ABILITY = "能力对冲"       # 战斗/智谋戏：克制点 vs 短板


@dataclass
class Skill:
    """单条技能"""
    name: str = ""                    # 技能名称
    skill_type: SkillType = SkillType.ACTIVE
    description: str = ""             # 详细描述
    tags: List[str] = field(default_factory=list)  # 标签，用于碰撞匹配（如"感知类""攻击类""谋略类""防御类"）

    # 以下仅 ACTIVE 类型需要填写
    trigger_condition: str = ""       # 触发条件（主动技能）
    effect_range: int = 0             # 作用范围（格子数，0=自身/无范围限制）
    duration: int = 0                 # 持续时间（tick数，0=即时）

    # 以下仅 LIMIT 类型需要填写
    blind_spots: List[str] = field(default_factory=list)  # 盲区描述

    # 以下仅 COST 类型需要填写
    side_effects: List[str] = field(default_factory=list)  # 副作用/后遗症
    karma_debt: str = ""              # 因果债/心魔描述

    def to_dict(self) -> Dict:
        """序列化为字典"""
        return {
            "name": self.name,
            "skill_type": self.skill_type.value,
            "description": self.description,
            "tags": list(self.tags),
            "trigger_condition": self.trigger_condition,
            "effect_range": self.effect_range,
            "duration": self.duration,
            "blind_spots": list(self.blind_spots),
            "side_effects": list(self.side_effects),
            "karma_debt": self.karma_debt,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> 'Skill':
        """从字典反序列化"""
        if not isinstance(data, dict):
            raise TypeError(f"Skill.from_dict 期望传入 dict，实际得到 {type(data).__name__}")

        # 解析枚举值，兼容字符串和枚举
        raw_type = data.get("skill_type", "主动")
        if isinstance(raw_type, str):
            skill_type = SkillType(raw_type)
        elif isinstance(raw_type, SkillType):
            skill_type = raw_type
        else:
            raise ValueError(f"无效的 skill_type: {raw_type!r}")

        return cls(
            name=data.get("name", ""),
            skill_type=skill_type,
            description=data.get("description", ""),
            tags=list(data.get("tags", [])),
            trigger_condition=data.get("trigger_condition", ""),
            effect_range=int(data.get("effect_range", 0)),
            duration=int(data.get("duration", 0)),
            blind_spots=list(data.get("blind_spots", [])),
            side_effects=list(data.get("side_effects", [])),
            karma_debt=data.get("karma_debt", ""),
        )


@dataclass
class CharacterSkillSet:
    """角色技能组 - 四维度完整技能集"""
    character_id: str = ""
    character_name: str = ""

    passive_skills: List[Skill] = field(default_factory=list)    # 被动技能（核心特质）
    active_skills: List[Skill] = field(default_factory=list)     # 主动技能（行动手段）
    limits: List[Skill] = field(default_factory=list)            # 技能限制（盲点）
    costs: List[Skill] = field(default_factory=list)             # 技能代价（后遗症）

    # 双目标
    ultimate_goal: str = ""           # 终极目标（一生执念）
    current_goal: str = ""            # 当下短期目标（本章行动理由）

    # 技能标签索引（自动生成，用于碰撞匹配）
    _tag_index: Dict[str, List[Skill]] = field(default_factory=dict, repr=False)

    def __post_init__(self):
        self._rebuild_tag_index()

    def _rebuild_tag_index(self):
        """重建标签索引——遍历所有技能，按 tag 聚合"""
        index: Dict[str, List[Skill]] = {}
        all_skills = self.get_all_skills()
        for skill in all_skills:
            for tag in skill.tags:
                index.setdefault(tag, []).append(skill)
        self._tag_index = index

    def get_skills_by_tag(self, tag: str) -> List[Skill]:
        """按标签查找技能"""
        return list(self._tag_index.get(tag, []))

    def get_all_skills(self) -> List[Skill]:
        """获取所有技能（被动 + 主动 + 限制 + 代价）"""
        return (
            list(self.passive_skills)
            + list(self.active_skills)
            + list(self.limits)
            + list(self.costs)
        )

    def get_weaknesses(self) -> List[str]:
        """获取所有弱点和盲区描述（用于被克制判定）

        来源包括：
        - LIMIT 类技能的 blind_spots
        - LIMIT 类技能的 description（作为兜底）
        - COST 类技能的 side_effects
        """
        weaknesses: List[str] = []
        for skill in self.limits:
            weaknesses.extend(skill.blind_spots)
            if skill.description:
                weaknesses.append(skill.description)
        for skill in self.costs:
            weaknesses.extend(skill.side_effects)
        return weaknesses

    def to_dict(self) -> Dict:
        """序列化为字典"""
        return {
            "character_id": self.character_id,
            "character_name": self.character_name,
            "passive_skills": [s.to_dict() for s in self.passive_skills],
            "active_skills": [s.to_dict() for s in self.active_skills],
            "limits": [s.to_dict() for s in self.limits],
            "costs": [s.to_dict() for s in self.costs],
            "ultimate_goal": self.ultimate_goal,
            "current_goal": self.current_goal,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> 'CharacterSkillSet':
        """从字典反序列化"""
        if not isinstance(data, dict):
            raise TypeError(
                f"CharacterSkillSet.from_dict 期望传入 dict，实际得到 {type(data).__name__}"
            )

        def _parse_skill_list(raw_list: list) -> List[Skill]:
            if not isinstance(raw_list, list):
                raise TypeError(f"技能列表必须是 list，实际得到 {type(raw_list).__name__}")
            return [Skill.from_dict(item) for item in raw_list]

        return cls(
            character_id=data.get("character_id", ""),
            character_name=data.get("character_name", ""),
            passive_skills=_parse_skill_list(data.get("passive_skills", [])),
            active_skills=_parse_skill_list(data.get("active_skills", [])),
            limits=_parse_skill_list(data.get("limits", [])),
            costs=_parse_skill_list(data.get("costs", [])),
            ultimate_goal=data.get("ultimate_goal", ""),
            current_goal=data.get("current_goal", ""),
        )


@dataclass
class WorldSkill:
    """世界Skill - 世界规则对角色的影响"""
    name: str = ""                     # 规则名称
    description: str = ""              # 规则描述
    effect: str = ""                   # 效果描述
    affects_tags: List[str] = field(default_factory=list)  # 影响哪些技能标签
    modifier: float = 1.0              # 修正系数（>1增强，<1削弱）

    # I4: 持续效果追踪
    duration: int = 0                  # 持续Tick数（0=永久/被动）
    remaining_ticks: int = 0           # 剩余持续Tick
    active: bool = True                # 是否激活

    def to_dict(self) -> Dict:
        """序列化为字典"""
        return {
            "name": self.name,
            "description": self.description,
            "effect": self.effect,
            "affects_tags": list(self.affects_tags),
            "modifier": self.modifier,
            "duration": self.duration,
            "remaining_ticks": self.remaining_ticks,
            "active": self.active,
        }

    def refresh(self):
        """每个慢Tick调用：递减remaining_ticks"""
        if self.duration <= 0:
            return  # 永久效果
        if self.remaining_ticks > 0:
            self.remaining_ticks -= 1
        if self.remaining_ticks <= 0 and self.duration > 0:
            self.active = False

    @classmethod
    def from_dict(cls, data: Dict) -> 'WorldSkill':
        """从字典反序列化"""
        if not isinstance(data, dict):
            raise TypeError(
                f"WorldSkill.from_dict 期望传入 dict，实际得到 {type(data).__name__}"
            )
        return cls(
            name=data.get("name", ""),
            description=data.get("description", ""),
            effect=data.get("effect", ""),
            affects_tags=list(data.get("affects_tags", [])),
            modifier=float(data.get("modifier", 1.0)),
        )


@dataclass
class WorldSkillSet:
    """世界技能组"""
    world_name: str = ""
    rules: List[WorldSkill] = field(default_factory=list)

    def get_modifier_for_tag(self, tag: str) -> float:
        """获取对某类技能的修正系数

        如果有多条规则影响同一标签，取累乘结果。
        如果没有任何规则影响该标签，返回 1.0（无修正）。
        """
        modifier = 1.0
        for rule in self.rules:
            if rule.active and tag in rule.affects_tags:
                modifier *= rule.modifier
        return modifier

    def refresh(self):
        """每个慢Tick调用：刷新所有规则的持续效果"""
        for rule in self.rules:
            rule.refresh()

    def get_active_rules(self) -> List[WorldSkill]:
        """获取所有当前激活的规则"""
        return [r for r in self.rules if r.active]

    def to_dict(self) -> Dict:
        """序列化为字典"""
        return {
            "world_name": self.world_name,
            "rules": [r.to_dict() for r in self.rules],
        }

    @classmethod
    def from_dict(cls, data: Dict) -> 'WorldSkillSet':
        """从字典反序列化"""
        if not isinstance(data, dict):
            raise TypeError(
                f"WorldSkillSet.from_dict 期望传入 dict，实际得到 {type(data).__name__}"
            )

        raw_rules = data.get("rules", [])
        if not isinstance(raw_rules, list):
            raise TypeError(f"rules 必须是 list，实际得到 {type(raw_rules).__name__}")

        return cls(
            world_name=data.get("world_name", ""),
            rules=[WorldSkill.from_dict(item) for item in raw_rules],
        )