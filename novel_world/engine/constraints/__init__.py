# -*- coding: utf-8 -*-
"""
前置约束层 — 全局主线约束 + 目标绑定 + NPC过滤

核心思想：在推演开始前，将用户的全局主线意图注入角色和势力的目标体系，
从源头减少无意义的随机支线，让剧情天然贴合预设主线。

使用方式：
    from novel_world.engine.constraints import StoryConstraint, apply_constraints
    constraint = StoryConstraint(
        core_conflict="正邪对决",
        ending_direction="正道惨胜",
        main_quest_weight=0.8,
    )
    apply_constraints(constraint, world, characters, factions)
"""

from dataclasses import dataclass, field
from typing import Optional
import logging

logger = logging.getLogger("constraints")


# ==========================================================================
# 一、主线约束配置
# ==========================================================================

@dataclass
class StoryConstraint:
    """全局主线约束配置"""

    core_conflict: str = ""
    ending_direction: str = ""
    main_quest_weight: float = 0.7
    npc_filter_enabled: bool = True
    npc_action_weight: float = 0.2
    side_quest_weight: float = 0.3
    key_characters: list = field(default_factory=list)
    key_factions: list = field(default_factory=list)
    forbidden_plots: list = field(default_factory=list)
    required_plot_beats: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "core_conflict": self.core_conflict,
            "ending_direction": self.ending_direction,
            "main_quest_weight": self.main_quest_weight,
            "npc_filter_enabled": self.npc_filter_enabled,
            "npc_action_weight": self.npc_action_weight,
            "side_quest_weight": self.side_quest_weight,
            "key_characters": list(self.key_characters),
            "key_factions": list(self.key_factions),
            "forbidden_plots": list(self.forbidden_plots),
            "required_plot_beats": list(self.required_plot_beats),
        }


# ==========================================================================
# 二、目标绑定器
# ==========================================================================

def apply_constraints(
    constraint: StoryConstraint,
    world=None,
    characters: list = None,
    factions: list = None,
) -> dict:
    """将主线约束应用到角色和势力上。

    1. 给关键角色绑定主线相关的长期目标
    2. 给关键势力绑定主线相关的势力目标
    3. 给 NPC 角色降低行动权重（npc_filter_enabled 时）
    4. 将主线信息注入 world.main_objective

    Returns:
        绑定结果摘要 dict
    """
    characters = characters or []
    factions = factions or []
    result = {
        "characters_bound": 0,
        "factions_bound": 0,
        "npc_filtered": 0,
        "world_updated": False,
    }

    # 1. 更新世界主线目标
    if world is not None and constraint.core_conflict:
        if hasattr(world, 'main_objective'):
            world.main_objective = constraint.core_conflict
        if hasattr(world, 'config') and hasattr(world.config, 'main_objective'):
            world.config.main_objective = constraint.core_conflict
        result["world_updated"] = True

    # 2. 绑定角色目标
    key_char_set = set(constraint.key_characters)
    for char in characters:
        char_name = getattr(char, 'name', '')
        is_key = (not key_char_set) or char_name in key_char_set

        if is_key and constraint.core_conflict:
            _bind_character_main_goal(char, constraint)
            result["characters_bound"] += 1
        elif constraint.npc_filter_enabled:
            _set_npc_weight(char, constraint.npc_action_weight)
            result["npc_filtered"] += 1

    # 3. 绑定势力目标
    key_fac_set = set(constraint.key_factions)
    for faction in factions:
        fac_name = getattr(faction, 'name', '') or getattr(faction, 'id', '')
        is_key = (not key_fac_set) or fac_name in key_fac_set

        if is_key and constraint.core_conflict:
            _bind_faction_main_goal(faction, constraint)
            result["factions_bound"] += 1

    logger.info(
        f"主线约束应用完成：{result['characters_bound']} 角色绑定主线，"
        f"{result['factions_bound']} 势力绑定主线，"
        f"{result['npc_filtered']} NPC 权重下调"
    )
    return result


def _bind_character_main_goal(char, constraint: StoryConstraint):
    """给角色绑定与主线相关的目标。"""
    char_type = getattr(char, 'char_type', None)
    type_value = char_type.value if hasattr(char_type, 'value') else str(char_type)

    goal_prefix = f"【主线】{constraint.core_conflict}"

    # 根据角色类型生成不同的主线目标
    if 'protagonist' in type_value.lower() or '主角' in type_value:
        goal_text = f"{goal_prefix}：推动主线发展，直面{constraint.core_conflict}的核心矛盾"
    elif 'antagonist' in type_value.lower() or '反派' in type_value:
        goal_text = f"{goal_prefix}：阻碍正道，推进自身阴谋"
    elif 'heroine' in type_value.lower() or '女主' in type_value:
        goal_text = f"{goal_prefix}：在关键时刻提供助力，影响局势走向"
    elif 'supporting' in type_value.lower() or '配角' in type_value:
        goal_text = f"{goal_prefix}：在主线事件中发挥辅助作用"
    else:
        goal_text = f"{goal_prefix}：见证或参与主线事件"

    # 设置 long_term_goal（优先走 CharacterAgent 接口）
    if hasattr(char, 'long_term_goal') and hasattr(char.long_term_goal, 'description'):
        # 保留原有目标的同时，主线权重更高
        original = char.long_term_goal.description
        if original and '主线' not in original:
            char.long_term_goal.description = f"{goal_text}。{original}"
        else:
            char.long_term_goal.description = goal_text

    # 也设置 goal 字段（NWCharacter 接口）
    if hasattr(char, 'goal'):
        original_goal = char.goal or ''
        if '主线' not in original_goal:
            char.goal = f"{goal_text}。{original_goal}" if original_goal else goal_text

    # 设置主线权重属性（供移动/碰撞调度使用）
    if not hasattr(char, 'main_quest_weight'):
        try:
            char.main_quest_weight = constraint.main_quest_weight
        except (AttributeError, TypeError):
            pass


def _bind_faction_main_goal(faction, constraint: StoryConstraint):
    """给势力绑定与主线相关的目标。"""
    goal_prefix = f"【主线】{constraint.core_conflict}"

    # 判断势力正邪倾向（从名字简单推断）
    fac_name = getattr(faction, 'name', '') or getattr(faction, 'id', '')
    evil_keywords = ['魔', '邪', '九幽', '幽冥', '血', '暗']
    is_evil = any(k in fac_name for k in evil_keywords)

    if is_evil:
        goal_text = f"{goal_prefix}：扩大势力版图，颠覆现有秩序"
    else:
        goal_text = f"{goal_prefix}：维护正道秩序，抵御外敌入侵"

    # Faction 类有 goals 列表
    if hasattr(faction, 'goals') and isinstance(faction.goals, list):
        # 检查是否已有主线目标
        has_main = any('主线' in (getattr(g, 'description', '') if hasattr(g, 'description') else str(g))
                       for g in faction.goals)
        if not has_main:
            try:
                from novel_world.engine.core.world import FactionGoal
                faction.goals.insert(0, FactionGoal(description=goal_text, priority=9))
            except Exception:
                faction.goals.insert(0, goal_text)


def _set_npc_weight(char, weight: float):
    """降低 NPC 角色的行动权重。"""
    try:
        char.npc_action_weight = weight
    except (AttributeError, TypeError):
        pass


# ==========================================================================
# 三、从 YAML 配置加载约束
# ==========================================================================

def load_constraint_from_yaml(yaml_path: str) -> StoryConstraint:
    """从 YAML 文件加载主线约束配置。"""
    import yaml
    import os
    if not os.path.exists(yaml_path):
        return StoryConstraint()
    with open(yaml_path, 'r', encoding='utf-8') as f:
        data = yaml.safe_load(f) or {}

    constraint_data = data.get('story_constraint', data)
    return StoryConstraint(
        core_conflict=constraint_data.get('core_conflict', ''),
        ending_direction=constraint_data.get('ending_direction', ''),
        main_quest_weight=float(constraint_data.get('main_quest_weight', 0.7)),
        npc_filter_enabled=bool(constraint_data.get('npc_filter_enabled', True)),
        npc_action_weight=float(constraint_data.get('npc_action_weight', 0.2)),
        side_quest_weight=float(constraint_data.get('side_quest_weight', 0.3)),
        key_characters=list(constraint_data.get('key_characters', [])),
        key_factions=list(constraint_data.get('key_factions', [])),
        forbidden_plots=list(constraint_data.get('forbidden_plots', [])),
        required_plot_beats=list(constraint_data.get('required_plot_beats', [])),
    )
