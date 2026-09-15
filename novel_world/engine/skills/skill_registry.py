# -*- coding: utf-8 -*-
"""
Skill注册表 - 管理所有角色和世界的技能
"""
from typing import Dict, List, Optional

from .skill_model import (
    CharacterSkillSet,
    WorldSkillSet,
    Skill,
    SkillType,
    CollisionType,
)

# 感知类关键词，用于识别"感知/侦查/洞察"类技能
_PERCEPTION_KEYWORDS = {"感知", "侦查", "洞察", "探查", "侦查", "觉察", "识破", "察觉", "感应"}

# 目标冲突关键词对（对立关系）
_GOAL_OPPOSITES: List[List[str]] = [
    ["保护", "摧毁"],
    ["拯救", "消灭"],
    ["守护", "侵袭"],
    ["建设", "破坏"],
    ["隐瞒", "揭露"],
    ["镇压", "反抗"],
    ["控制", "自由"],
    ["统一", "分裂"],
    ["生", "灭"],
    ["进攻", "防守"],
    ["夺取", "守护"],
    ["逃跑", "追捕"],
    ["欺骗", "识破"],
]


class SkillRegistry:
    """技能注册表"""

    def __init__(self):
        self._characters: Dict[str, CharacterSkillSet] = {}  # character_id -> skill_set
        self._world: Optional[WorldSkillSet] = None

    # ------------------------------------------------------------------ #
    #  注册 / 查询
    # ------------------------------------------------------------------ #

    def register_character(self, skill_set: CharacterSkillSet):
        """注册角色技能

        Args:
            skill_set: 角色技能集，character_id 不得为空。

        Raises:
            TypeError: 传入类型不是 CharacterSkillSet。
            ValueError: character_id 为空字符串。
        """
        if not isinstance(skill_set, CharacterSkillSet):
            raise TypeError(
                f"register_character 期望 CharacterSkillSet，实际得到 {type(skill_set).__name__}"
            )
        if not skill_set.character_id:
            raise ValueError("CharacterSkillSet.character_id 不能为空")
        self._characters[skill_set.character_id] = skill_set

    def unregister_character(self, character_id: str):
        """移除角色

        Args:
            character_id: 要移除的角色 ID。

        Raises:
            KeyError: 角色不存在。
        """
        if character_id not in self._characters:
            raise KeyError(f"角色 '{character_id}' 不在注册表中")
        del self._characters[character_id]

    def get_character_skills(self, character_id: str) -> Optional[CharacterSkillSet]:
        """获取角色技能集，不存在则返回 None"""
        return self._characters.get(character_id)

    def set_world_skills(self, world_skills: WorldSkillSet):
        """设置世界技能

        Args:
            world_skills: 世界技能组。

        Raises:
            TypeError: 传入类型不是 WorldSkillSet。
        """
        if not isinstance(world_skills, WorldSkillSet):
            raise TypeError(
                f"set_world_skills 期望 WorldSkillSet，实际得到 {type(world_skills).__name__}"
            )
        self._world = world_skills

    def get_world_skills(self) -> Optional[WorldSkillSet]:
        """获取世界技能，未设置则返回 None"""
        return self._world

    def get_all_character_ids(self) -> List[str]:
        """返回所有已注册角色 ID 列表"""
        return list(self._characters.keys())

    # ------------------------------------------------------------------ #
    #  碰撞检测
    # ------------------------------------------------------------------ #

    def find_collisions(self) -> List[dict]:
        """扫描所有角色，找出可能的碰撞

        返回碰撞候选列表，每项包含：
        - char_a_id / char_b_id: 碰撞双方 ID
        - char_a_name / char_b_name: 碰撞双方名称
        - collision_type: CollisionType 枚举
        - reason: 碰撞原因描述
        - a_skills: A 方相关技能列表（序列化后的 dict）
        - b_skills: B 方相关技能列表（序列化后的 dict）

        碰撞逻辑：
        1. GOAL 对冲：A 的 current_goal 与 B 的 current_goal 存在关键词对立
        2. PERCEPTION 对冲：A 拥有感知类主动技能，且 B 拥有与之匹配的盲区限制
        3. ABILITY 对冲：A 的主动技能标签命中 B 的弱点/盲区描述
        """
        collisions: List[dict] = []
        char_ids = list(self._characters.keys())

        # 预计算每个角色的弱点关键词集合（用于快速匹配）
        weakness_map: Dict[str, List[str]] = {}
        for cid, cs in self._characters.items():
            weakness_map[cid] = cs.get_weaknesses()

        for i in range(len(char_ids)):
            for j in range(i + 1, len(char_ids)):
                a_id = char_ids[i]
                b_id = char_ids[j]
                a_set = self._characters[a_id]
                b_set = self._characters[b_id]

                # 双向检测：A→B 和 B→A
                collisions.extend(self._detect_goal_collision(a_set, b_set))
                collisions.extend(self._detect_goal_collision(b_set, a_set))

                collisions.extend(
                    self._detect_perception_collision(a_set, b_set, weakness_map.get(b_id, []))
                )
                collisions.extend(
                    self._detect_perception_collision(b_set, a_set, weakness_map.get(a_id, []))
                )

                collisions.extend(
                    self._detect_ability_collision(a_set, b_set, weakness_map.get(b_id, []))
                )
                collisions.extend(
                    self._detect_ability_collision(b_set, a_set, weakness_map.get(a_id, []))
                )

        # 去重：按 (char_a_id, char_b_id, collision_type) 三元组去重
        seen: set = set()
        unique: List[dict] = []
        for c in collisions:
            key = (c["char_a_id"], c["char_b_id"], c["collision_type"].value)
            if key not in seen:
                seen.add(key)
                unique.append(c)
        return unique

    # ------------------------------------------------------------------ #
    #  碰撞检测子方法
    # ------------------------------------------------------------------ #

    @staticmethod
    def _detect_goal_collision(
        a: CharacterSkillSet, b: CharacterSkillSet
    ) -> List[dict]:
        """目标对冲检测

        检查 A 的 current_goal 和 B 的 current_goal 是否包含对立关键词。
        """
        results: List[dict] = []
        a_goal = a.current_goal.strip()
        b_goal = b.current_goal.strip()
        if not a_goal or not b_goal:
            return results

        for opposite_pair in _GOAL_OPPOSITES:
            # 找出 A 目标中包含的关键词
            a_has = [kw for kw in opposite_pair if kw in a_goal]
            # 找出 B 目标中包含的关键词
            b_has = [kw for kw in opposite_pair if kw in b_goal]
            # 如果 A 和 B 分别命中了同一对中的不同关键词
            if a_has and b_has and set(a_has) != set(b_has):
                results.append({
                    "char_a_id": a.character_id,
                    "char_b_id": b.character_id,
                    "char_a_name": a.character_name,
                    "char_b_name": b.character_name,
                    "collision_type": CollisionType.GOAL,
                    "reason": (
                        f"目标对冲：{a.character_name} 的目标「{a_goal}」"
                        f" 与 {b.character_name} 的目标「{b_goal}」"
                        f" 存在对立（{','.join(a_has)} vs {','.join(b_has)}）"
                    ),
                    "a_skills": [],
                    "b_skills": [],
                })
                break  # 每对角色只报一次目标对冲

        return results

    @staticmethod
    def _detect_perception_collision(
        a: CharacterSkillSet,
        b: CharacterSkillSet,
        b_weaknesses: List[str],
    ) -> List[dict]:
        """感知对冲检测

        如果 A 拥有感知类主动技能（标签或名称包含感知关键词），
        且 B 的弱点/盲区描述中包含与 A 感知技能相关的关键词，则产生碰撞。
        """
        results: List[dict] = []

        # 收集 A 的感知类主动技能
        perception_skills: List[Skill] = []
        for skill in a.active_skills:
            is_perception = False
            # 检查标签
            for tag in skill.tags:
                if any(kw in tag for kw in _PERCEPTION_KEYWORDS):
                    is_perception = True
                    break
            # 检查名称和描述
            if not is_perception:
                for kw in _PERCEPTION_KEYWORDS:
                    if kw in skill.name or kw in skill.description:
                        is_perception = True
                        break
            if is_perception:
                perception_skills.append(skill)

        if not perception_skills or not b_weaknesses:
            return results

        # 收集 B 的 LIMIT 技能
        b_limit_skills = [s for s in b.limits]

        # 检查感知技能的标签是否与 B 弱点文本有重叠
        matched_a_skills: List[Skill] = []
        matched_b_skills: List[Skill] = []

        for pskill in perception_skills:
            for b_limit in b_limit_skills:
                # 盲区关键词重叠
                overlap_found = False
                for blind in b_limit.blind_spots:
                    for kw in _PERCEPTION_KEYWORDS:
                        if kw in blind and (kw in pskill.name or kw in pskill.description):
                            overlap_found = True
                            break
                    if overlap_found:
                        break
                # 标签匹配
                if not overlap_found:
                    for tag in pskill.tags:
                        if any(tag in w for w in b_weaknesses):
                            overlap_found = True
                            break
                if overlap_found:
                    matched_a_skills.append(pskill)
                    matched_b_skills.append(b_limit)
                    break  # 每个 A 技能只匹配一次 B 限制

        if matched_a_skills:
            a_names = "、".join(s.name for s in matched_a_skills)
            b_names = "、".join(s.name for s in matched_b_skills)
            results.append({
                "char_a_id": a.character_id,
                "char_b_id": b.character_id,
                "char_a_name": a.character_name,
                "char_b_name": b.character_name,
                "collision_type": CollisionType.PERCEPTION,
                "reason": (
                    f"感知对冲：{a.character_name} 的感知技能「{a_names}」"
                    f" 可刺探 {b.character_name} 的盲区「{b_names}」"
                ),
                "a_skills": [s.to_dict() for s in matched_a_skills],
                "b_skills": [s.to_dict() for s in matched_b_skills],
            })

        return results

    @staticmethod
    def _detect_ability_collision(
        a: CharacterSkillSet,
        b: CharacterSkillSet,
        b_weaknesses: List[str],
    ) -> List[dict]:
        """能力对冲检测

        如果 A 的主动技能标签中的关键词出现在 B 的弱点/盲区描述文本中，
        说明 A 的能力可以克制 B 的短板。
        """
        results: List[dict] = []

        if not b_weaknesses:
            return results

        # 将 B 的弱点合并为一个大字符串用于关键词检测
        weakness_text = " ".join(b_weaknesses)

        matched_a_skills: List[Skill] = []
        for skill in a.active_skills:
            for tag in skill.tags:
                if tag and tag in weakness_text:
                    matched_a_skills.append(skill)
                    break  # 每个 A 技能只匹配一次

        if matched_a_skills:
            b_limit_skills = [s for s in b.limits]
            a_names = "、".join(s.name for s in matched_a_skills)
            b_names = "、".join(s.name for s in b_limit_skills) if b_limit_skills else "未知弱点"
            results.append({
                "char_a_id": a.character_id,
                "char_b_id": b.character_id,
                "char_a_name": a.character_name,
                "char_b_name": b.character_name,
                "collision_type": CollisionType.ABILITY,
                "reason": (
                    f"能力对冲：{a.character_name} 的技能「{a_names}」"
                    f" 可克制 {b.character_name} 的弱点「{b_names}」"
                ),
                "a_skills": [s.to_dict() for s in matched_a_skills],
                "b_skills": [s.to_dict() for s in b_limit_skills],
            })

        return results