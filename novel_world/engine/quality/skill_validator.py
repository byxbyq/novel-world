# -*- coding: utf-8 -*-
"""
叙事中技能逻辑校验器 — 校验AI生成的叙事中技能使用是否合法

检测规则：
  1. 越权使用：角色A使用了角色B的技能
  2. 超限使用：限用1次的技能在叙事中用了多次
  3. 场景违规：技能使用违反其描述中声明的限制条件
"""

from typing import List, Dict, Set, Optional
import re


class SkillViolation:
    """技能违规记录"""
    def __init__(self, rule: str, message: str, context: str = ""):
        self.rule = rule
        self.message = message
        self.context = context

    def to_dict(self) -> dict:
        return {
            "type": "skill_violation",
            "rule": self.rule,
            "message": self.message,
            "context": self.context,
        }


def validate_skill_usage(
    narrative: str,
    character_skills: Dict[str, List[str]],
    skill_limits: Dict[str, Dict] = None,
) -> List[SkillViolation]:
    """
    校验叙事文本中的技能使用是否合法

    Args:
        narrative: AI生成的叙事文本
        character_skills: {角色名: [该角色拥有的技能名列表]}
        skill_limits: {技能名: {"max_uses": N, "owner": 角色名, "condition": "限制条件"}}

    Returns:
        违规列表
    """
    violations = []
    skill_limits = skill_limits or {}

    # 构建技能名 → 所属角色 的映射
    skill_to_owner: Dict[str, str] = {}
    for char_name, skills in character_skills.items():
        for sk in skills:
            skill_to_owner[sk] = char_name

    all_skill_names = set(skill_to_owner.keys())
    if not all_skill_names:
        return violations

    # 1. 越权使用检测：扫描叙事中出现的技能名，核对使用者
    for skill_name in all_skill_names:
        owner = skill_to_owner[skill_name]
        # 查找叙事中提到该技能的所有位置
        for m in re.finditer(re.escape(skill_name), narrative):
            pos = m.start()
            # 提取上下文（前后各30字）
            ctx_start = max(0, pos - 30)
            ctx_end = min(len(narrative), pos + len(skill_name) + 30)
            context = narrative[ctx_start:ctx_end].replace('\n', ' ')

            # 检查上下文中是否提到了该技能的合法使用者
            if owner not in context:
                # 检查附近有没有其他角色名
                other_chars = [c for c in character_skills.keys()
                             if c != owner and c in context]
                if other_chars:
                    violations.append(SkillViolation(
                        rule="越权使用",
                        message=f"技能「{skill_name}」属于{owner}，但叙事中似乎由{other_chars[0]}使用",
                        context=context,
                    ))

    # 2. 超限使用检测
    for skill_name, limit_info in skill_limits.items():
        max_uses = limit_info.get("max_uses", 1)
        count = len(list(re.finditer(re.escape(skill_name), narrative)))
        if count > max_uses:
            violations.append(SkillViolation(
                rule="超限使用",
                message=f"技能「{skill_name}」限用{max_uses}次，叙事中出现了{count}次",
                context=f"技能: {skill_name}, 出现次数: {count}",
            ))

    # 3. 场景违规：检查技能限制条件是否在叙事中被违反
    for skill_name, limit_info in skill_limits.items():
        condition = limit_info.get("condition", "")
        if not condition:
            continue
        # 简单的关键词逆向检测：如果 condition 说"需在有水环境"，但叙事中无"水/湖/河"等词
        # 这里用比较松弛的规则
        condition_keywords = _extract_condition_keywords(condition)
        if condition_keywords:
            for kw in condition_keywords:
                if kw not in narrative:
                    # 仅当技能确实出现在叙事中时才报告
                    if skill_name in narrative:
                        violations.append(SkillViolation(
                            rule="场景违规",
                            message=f"技能「{skill_name}」需要条件「{condition}」，"
                                    f"但叙事中未体现关键词「{kw}」",
                            context=f"条件: {condition}",
                        ))
                    break

    return violations


def _extract_condition_keywords(condition: str) -> List[str]:
    """从限制条件文本中提取关键环境词"""
    env_keywords = [
        "水", "湖", "河", "海", "火", "焰", "暗", "夜", "光", "日",
        "灵", "气", "血", "剑", "阵", "封印", "禁制",
    ]
    found = []
    for kw in env_keywords:
        if kw in condition:
            found.append(kw)
    return found


def build_skill_limits_from_yaml(
    characters_yaml: dict,
    skill_config: dict = None,
) -> Dict[str, Dict]:
    """
    从 characters.yaml 构建技能限制字典

    Args:
        characters_yaml: characters.yaml 解析后的字典
        skill_config: 技能配置（可选覆盖）

    Returns:
        {技能名: {max_uses, owner, condition}}
    """
    limits = {}
    for char in characters_yaml.get("characters", []):
        char_name = char["name"]
        skills = char.get("skills", {})
        # 支持中文和英文标签
        skill_labels = ["被动特质", "主动手段", "passive", "active"]
        for label in skill_labels:
            for sk in skills.get(label, []):
                sk_name = sk if isinstance(sk, str) else sk.get("name", "")
                if not sk_name:
                    continue
                limit_info = {"owner": char_name, "max_uses": 3}  # 默认
                if isinstance(sk, dict):
                    # 检查是否有使用限制
                    cost = sk.get("cost", sk.get("使用代价", ""))
                    if "一次性" in str(cost) or "限一次" in str(cost):
                        limit_info["max_uses"] = 1
                    elif "两次" in str(cost):
                        limit_info["max_uses"] = 2
                limits[sk_name] = limit_info

    # 覆盖/补充
    if skill_config:
        limits.update(skill_config)
    return limits


def build_char_skill_map_from_yaml(characters_yaml: dict) -> Dict[str, List[str]]:
    """从 characters.yaml 构建 {角色名: [技能名列表]}"""
    char_map = {}
    for char in characters_yaml.get("characters", []):
        char_name = char["name"]
        skill_names = []
        skills = char.get("skills", {})
        skill_labels = ["被动特质", "主动手段", "技能限制", "使用代价", "passive", "active", "limit", "cost"]
        for label in skill_labels:
            cat = skills.get(label)
            if cat is None:
                continue
            if isinstance(cat, list):
                for sk in cat:
                    if isinstance(sk, dict):
                        name = sk.get("name", "")
                        if name:
                            skill_names.append(name)
                    elif isinstance(sk, str):
                        skill_names.append(sk)
            elif isinstance(cat, dict):
                # 单技能结构：{name: ..., description: ..., tags: ...}
                name = cat.get("name", "")
                if name:
                    skill_names.append(name)
        char_map[char_name] = list(set(skill_names))
    return char_map
