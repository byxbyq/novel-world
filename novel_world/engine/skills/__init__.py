# -*- coding: utf-8 -*-
"""
Skill系统 - 公共导出

使用示例：
    from engine.skills import (
        Skill, SkillType,
        CharacterSkillSet,
        WorldSkill, WorldSkillSet,
        CollisionType,
        SkillRegistry,
    )
"""
from .skill_model import (
    Skill,
    SkillType,
    CollisionType,
    CharacterSkillSet,
    WorldSkill,
    WorldSkillSet,
)
from .skill_registry import SkillRegistry

__all__ = [
    # 枚举
    "SkillType",
    "CollisionType",
    # 数据模型
    "Skill",
    "CharacterSkillSet",
    "WorldSkill",
    "WorldSkillSet",
    # 注册表
    "SkillRegistry",
]