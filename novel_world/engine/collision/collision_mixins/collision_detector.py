# -*- coding: utf-8 -*-
"""碰撞检测 Mixin：感知对冲/目标对冲/能力对冲/势力冲突/资源争夺/距离碰撞"""

import uuid
from typing import List, Dict, Optional, Tuple

from ..collision_engine import _OPPOSITE_KEYWORDS, _PERCEPTION_KEYWORDS, _STEALTH_KEYWORDS, _PROXIMITY_THRESHOLD, CollisionEvent, CollisionOutcome


class CollisionDetectorMixin:
    """
    碰撞检测 Mixin：感知对冲/目标对冲/能力对冲/势力冲突/资源争夺/距离碰撞 - Mixin for CollisionEngine
    """

    def _detect_collisions(self, characters: list) -> List[CollisionEvent]:
        """
        碰撞检测核心逻辑
        遍历所有角色对，依次检测：
          (1) 感知对冲：一方有感知技能，另一方有隐匿/伪装
          (2) 目标对冲：两人目标包含对立关键词
          (3) 能力对冲：甲的主动技能标签匹配乙的限制/弱点标签
          (4) 接近碰撞：两人在空间上距离足够近（基于 pos 坐标）

        Args:
            characters: 存活角色列表

        Returns:
            检测到的碰撞事件列表
        """
        events: List[CollisionEvent] = []

        # 先尝试通过技能注册表批量检测
        if self.skill_registry and hasattr(self.skill_registry, 'find_collisions'):
            try:
                registry_events = self.skill_registry.find_collisions()
                for re in registry_events:
                    if isinstance(re, CollisionEvent):
                        events.append(re)
                    elif isinstance(re, dict):
                        events.append(CollisionEvent.from_dict(re))
            except Exception as e:
                logger.warning(f"技能注册表碰撞检测异常: {e}")

        # 遍历所有角色对进行逐一检测
        n = len(characters)
        for i in range(n):
            for j in range(i + 1, n):
                char_a = characters[i]
                char_b = characters[j]

                # 获取角色技能信息（兼容 list 和 dict 格式）
                skill_a = self._extract_skills(char_a)
                skill_b = self._extract_skills(char_b)

                # 跳过已经由注册表处理过的对
                existing_pair = any(
                    (e.char_a_id == char_a.id and e.char_b_id == char_b.id) or
                    (e.char_a_id == char_b.id and e.char_b_id == char_a.id)
                    for e in events
                )
                if existing_pair:
                    continue

                # ── 新增：目标-角色关联检测（最高权重） ──
                goal_opp_event = self._check_goal_opposition(
                    char_a, char_b, skill_a, skill_b
                )
                if goal_opp_event:
                    events.append(goal_opp_event)
                    continue

                # ── 新增：势力冲突检测（次高权重） ──
                faction_event = self._check_faction_conflict(
                    char_a, char_b, skill_a, skill_b
                )
                if faction_event:
                    events.append(faction_event)
                    continue

                # ── 新增：资源争夺检测（phase2_p2）──
                resource_event = self._check_resource_contention(
                    char_a, char_b
                )
                if resource_event:
                    events.append(resource_event)
                    continue

                # 1. 感知对冲检测
                perception_event = self._check_perception_collision(
                    char_a, char_b, skill_a, skill_b
                )
                if perception_event:
                    events.append(perception_event)
                    continue

                # 2. 目标对冲检测
                goal_event = self._check_goal_collision(
                    char_a, char_b, skill_a, skill_b
                )
                if goal_event:
                    events.append(goal_event)
                    continue

                # 3. 能力对冲检测
                ability_event = self._check_ability_collision(
                    char_a, char_b, skill_a, skill_b
                )
                if ability_event:
                    events.append(ability_event)
                    continue

                # 4. 基于位置的距离碰撞检测
                proximity_event = self._check_proximity_collision(
                    char_a, char_b, skill_a, skill_b
                )
                if proximity_event:
                    events.append(proximity_event)

        return events
    def _extract_skills(self, character) -> list:
        """
        从角色对象中提取技能列表
        兼容多种格式：str列表、dict列表、Skill对象列表

        Args:
            character: 角色对象

        Returns:
            标准化的技能信息列表，每项包含 name/tags/type/limits/counters
        """
        skills_raw = getattr(character, 'skills', [])
        if not skills_raw:
            return []

        result = []
        for s in skills_raw:
            if isinstance(s, str):
                result.append({"name": s, "tags": [], "type": "unknown",
                              "limits": [], "counters": []})
            elif isinstance(s, dict):
                result.append({
                    "name": s.get("name", s.get("skill_name", "")),
                    "tags": s.get("tags", s.get("keywords", [])),
                    "type": s.get("type", s.get("skill_type", "unknown")),
                    "limits": s.get("limits", s.get("weaknesses", [])),
                    "counters": s.get("counters", s.get("克制", [])),
                })
            elif hasattr(s, 'name'):
                result.append({
                    "name": getattr(s, 'name', ''),
                    "tags": list(getattr(s, 'tags', [])) if hasattr(s, 'tags') else [],
                    "type": getattr(s, 'type', 'unknown') if hasattr(s, 'type') else 'unknown',
                    "limits": list(getattr(s, 'limits', [])) if hasattr(s, 'limits') else [],
                    "counters": list(getattr(s, 'counters', [])) if hasattr(s, 'counters') else [],
                })
        return result
    def _check_goal_collision(self, char_a, char_b, skill_a, skill_b) -> Optional[CollisionEvent]:
        """
        目标对冲检测
        比较两个角色的 current_goal / goal 字段，检查是否包含对立关键词

        对立关系示例：
          保护 <-> 摧毁
          寻找 <-> 隐藏
          进攻 <-> 防守
          拯救 <-> 毁灭

        Returns:
            检测到碰撞返回 CollisionEvent，否则返回 None
        """
        goal_a = getattr(char_a, 'goal', '') or getattr(char_a, 'current_goal', '')
        goal_b = getattr(char_b, 'goal', '') or getattr(char_b, 'current_goal', '')

        # 如果任一方没有目标，无法形成目标对冲
        if not goal_a or not goal_b:
            return None

        # 在目标A中搜索对立于目标B的关键词
        for keyword_a, opposites in _OPPOSITE_KEYWORDS.items():
            if keyword_a in goal_a:
                for opp in opposites:
                    if opp in goal_b:
                        return self._make_collision_event(
                            char_a=char_a, char_b=char_b,
                            collision_type="目标对冲",
                            collision_subtype="目标-关键词",
                            collision_reason=(
                                f"目标对立：{char_a.name}的「{keyword_a}」"
                                f"与{char_b.name}的「{opp}」直接冲突"
                            ),
                            skill_a_name=self._find_skill_by_keyword(skill_a, keyword_a),
                            skill_b_name=self._find_skill_by_keyword(skill_b, opp),
                            collision_weight=self._w("goal_keyword_opposition", 50),
                        )

            # 反向检查：目标B中的关键词对立于目标A
            if keyword_a in goal_b:
                for opp in opposites:
                    if opp in goal_a:
                        return self._make_collision_event(
                            char_a=char_a, char_b=char_b,
                            collision_type="目标对冲",
                            collision_subtype="目标-关键词",
                            collision_reason=(
                                f"目标对立：{char_b.name}的「{keyword_a}」"
                                f"与{char_a.name}的「{opp}」直接冲突"
                            ),
                            skill_a_name=self._find_skill_by_keyword(skill_a, opp),
                            skill_b_name=self._find_skill_by_keyword(skill_b, keyword_a),
                            collision_weight=self._w("goal_keyword_opposition", 50),
                        )

        return None
    def _check_goal_opposition(
        self, char_a, char_b, skill_a, skill_b
    ) -> Optional[CollisionEvent]:
        """
        目标-角色关联检测（最高权重碰撞）

        检查两个角色的 Goal 是否直接指向对方：
        - 角色A的目标字符串中包含角色B的名字 → 目标关联
        - 角色B的目标字符串中包含角色A的名字 → 双向目标关联

        这比关键词匹配更精准——"叶凡要杀魔尊玄冥"直接建立人物之间的对抗关系，
        而非依赖"杀"和"逃亡"在关键词表中的巧合匹配。

        Returns:
            检测到碰撞返回 CollisionEvent（weight=100），否则返回 None
        """
        goal_a = getattr(char_a, 'goal', '') or getattr(char_a, 'current_goal', '')
        goal_b = getattr(char_b, 'goal', '') or getattr(char_b, 'current_goal', '')
        name_a = getattr(char_a, 'name', '')
        name_b = getattr(char_b, 'name', '')

        if not goal_a or not goal_b:
            return None

        # 反向查：B的名字出现在A的目标中，同时A的名字出现在B的目标中 → 双向目标关联
        a_mentions_b = name_b and name_b in goal_a
        b_mentions_a = name_a and name_a in goal_b

        if a_mentions_b and b_mentions_a:
            return self._make_collision_event(
                char_a=char_a, char_b=char_b,
                collision_type="目标对冲",
                collision_subtype="目标-角色关联",
                collision_reason=(
                    f"双向目标关联：{char_a.name}的目标「{goal_a}」与"
                    f"{char_b.name}的目标「{goal_b}」互为指向"
                ),
                collision_weight=self._w("goal_character_bidirectional", 100),
            )

        # 单向：A的目标提到了B
        if a_mentions_b:
            return self._make_collision_event(
                char_a=char_a, char_b=char_b,
                collision_type="目标对冲",
                collision_subtype="目标-角色关联",
                collision_reason=(
                    f"目标关联：{char_a.name}的目标「{goal_a}」直接涉及{char_b.name}"
                ),
                collision_weight=self._w("goal_character_unidirectional", 80),
            )

        # 单向：B的目标提到了A
        if b_mentions_a:
            return self._make_collision_event(
                char_a=char_a, char_b=char_b,
                collision_type="目标对冲",
                collision_subtype="目标-角色关联",
                collision_reason=(
                    f"目标关联：{char_b.name}的目标「{goal_b}」直接涉及{char_a.name}"
                ),
                collision_weight=self._w("goal_character_unidirectional", 80),
            )

        return None
    def _check_faction_conflict(
        self, char_a, char_b, skill_a, skill_b
    ) -> Optional[CollisionEvent]:
        """
        势力冲突检测（phase2_p1 增强版）

        检查两个角色是否属于互相敌对的势力：
        - 不同 faction_id → 潜在冲突（weight=50 基础）
        - 明确敌对关系 → 升级为「势力敌对」（weight=70）
        - 领地/资源重叠 → 升级为「资源冲突」或「领地冲突」
        - 资源 + 领地同时重叠 → 「全面对抗」（weight=90）
        """
        faction_a = getattr(char_a, 'faction_id', '') or ''
        faction_b = getattr(char_b, 'faction_id', '') or ''

        if not faction_a or not faction_b or faction_a == faction_b:
            return None

        # 获取势力引用
        fa = None
        fb = None
        if self.world and hasattr(self.world, 'factions'):
            fa = self.world.factions.get(faction_a)
            fb = self.world.factions.get(faction_b)

        faction_name_a = faction_a
        faction_name_b = faction_b
        if fa and hasattr(fa, 'name'):
            faction_name_a = fa.name
        if fb and hasattr(fb, 'name'):
            faction_name_b = fb.name

        # 确定冲突级别
        weight = self._w("faction_direct_conflict", 50)
        collision_subtype = "势力-直接冲突"
        reasons_parts = []

        # 检查是否为明确敌对
        is_enemy = False
        if fa and fb:
            is_enemy = fa.is_enemy_of(faction_name_b) or fb.is_enemy_of(faction_name_a)

        if is_enemy:
            weight = self._w("faction_enemy_conflict", 70)
            collision_subtype = "势力-敌对冲突"
            reasons_parts.append(f"「{faction_name_a}」与「{faction_name_b}」为敌对势力")

        # 检测领地/资源重叠
        if self.world and hasattr(self.world, 'detect_faction_overlap_resources'):
            overlaps = self.world.detect_faction_overlap_resources(faction_a, faction_b)
            if overlaps:
                has_territory = any("领地" in o for o in overlaps)
                has_resource = any("资源" in o for o in overlaps)
                has_target = any("目标提及" in o for o in overlaps)

                if has_territory and has_resource:
                    weight = max(weight, self._w("faction_full_confrontation", 90))
                    collision_subtype = "势力-全面对抗"
                elif has_territory:
                    weight = max(weight, self._w("faction_territory_conflict", 75))
                    collision_subtype = "势力-领地冲突"
                elif has_resource:
                    weight = max(weight, self._w("faction_resource_conflict", 75))
                    collision_subtype = "势力-资源冲突"
                elif has_target:
                    weight = max(weight, self._w("faction_target_conflict", 65))
                    collision_subtype = "势力-目标冲突"

                reasons_parts.append("; ".join(overlaps))

        base_reason = (
            f"势力对峙：{char_a.name}所属「{faction_name_a}」"
            f"与{char_b.name}所属「{faction_name_b}」对立"
        )
        if reasons_parts:
            base_reason += f"（{'; '.join(reasons_parts)}）"

        return self._make_collision_event(
            char_a=char_a, char_b=char_b,
            collision_type="势力冲突",
            collision_subtype=collision_subtype,
            collision_reason=base_reason,
            collision_weight=weight,
        )
    def _check_resource_contention(
        self, char_a, char_b
    ) -> Optional[CollisionEvent]:
        """
        资源争夺检测（phase2_p2）

        条件：
        1. 两个角色在同一位置（或相邻）
        2. 两个角色目标中都涉及同一资源关键词
        3. 该位置恰好是资源所在地

        权重：基础 60，同一势力则跳过
        """
        # 位置检查（同一位置 或 8 邻域内）
        ax, ay = char_a.pos
        bx, by = char_b.pos
        if max(abs(ax - bx), abs(ay - by)) > 1:
            return None

        goal_a = getattr(char_a, 'goal', '') or ''
        goal_b = getattr(char_b, 'goal', '') or ''
        if not goal_a or not goal_b:
            return None

        # 提取双方目标中的资源关键词
        from novel_world.engine.core.world import World
        kw_map = World._RESOURCE_KEYWORD_MAP
        res_a = []
        res_b = []
        for kw in sorted(kw_map.keys(), key=len, reverse=True):
            if kw in goal_a:
                res_a.append(kw)
            if kw in goal_b:
                res_b.append(kw)

        # 找交集资源
        common = set(res_a) & set(res_b)
        if not common:
            return None

        resource = list(common)[0]

        # 确认当前位置是资源所在地
        if self.world:
            loc = self.world.get_resource_location(resource)
            if loc and (loc.x, loc.y) != (ax, ay) and (loc.x, loc.y) != (bx, by):
                # 不在资源所在地，降级但仍报告
                pass

        # 同一势力不触发资源内部竞争
        fid_a = getattr(char_a, 'faction_id', '') or ''
        fid_b = getattr(char_b, 'faction_id', '') or ''
        if fid_a and fid_a == fid_b:
            return None

        reason = (
            f"资源争夺：{char_a.name}与{char_b.name}都觊觎「{resource}」，"
            f"在坐标({ax},{ay})附近相遇"
        )

        return self._make_collision_event(
            char_a=char_a, char_b=char_b,
            collision_type="资源争夺",
            collision_subtype="资源争夺-直接冲突",
            collision_reason=reason,
            collision_weight=self._w("resource_contention", 60),
        )
    def _check_perception_collision(
        self, char_a, char_b, skill_a, skill_b
    ) -> Optional[CollisionEvent]:
        """
        感知对冲检测 + 信息差状态累积（跨tick持久）

        检测模式：
          - 角色A有感知/侦查类技能，角色B有隐匿/伪装类技能 -> 信息攻防
          - 碰撞后更新 perception_state，替代旧版关键词匹配
          - 状态持续跨 tick 累积，直到被新的感知碰撞覆盖

        Returns:
            检测到碰撞返回 CollisionEvent，否则返回 None
        """
        a_perception = self._find_perception_skill(skill_a)
        b_stealth = self._find_stealth_skill(skill_b)
        b_perception = self._find_perception_skill(skill_b)
        a_stealth = self._find_stealth_skill(skill_a)

        global_tick = self.global_tick if hasattr(self, 'global_tick') else 0
        result = None

        # 双向对冲：A 感知 vs B 隐匿
        if a_perception and b_stealth:
            a_pow = self._calc_perception_power(a_perception, skill_a)
            b_pow = self._calc_stealth_power(b_stealth, skill_b)
            result = self._make_collision_event(
                char_a=char_a, char_b=char_b,
                collision_type="感知对冲",
                collision_reason=(
                    f"感知攻防：{char_a.name}的感知能力「{a_perception}」"
                    f"与{char_b.name}的隐匿手段「{b_stealth}」形成对冲"
                ),
                skill_a_name=a_perception,
                skill_b_name=b_stealth,
            )
            if a_pow >= b_pow:
                self._set_perception(char_a, char_b.name, "see", global_tick,
                    f"「{a_perception}」识破「{b_stealth}」")
                self._set_perception(char_b, char_a.name, "partial", global_tick,
                    f"隐匿被「{a_perception}」识破")
            else:
                self._set_perception(char_a, char_b.name, "partial", global_tick,
                    f"「{a_perception}」被「{b_stealth}」干扰")
                self._set_perception(char_b, char_a.name, "hidden", global_tick,
                    f"「{b_stealth}」成功隐匿")

        # 反向双向对冲：B 感知 vs A 隐匿
        if b_perception and a_stealth:
            b_pow = self._calc_perception_power(b_perception, skill_b)
            a_pow = self._calc_stealth_power(a_stealth, skill_a)
            if result is None:
                result = self._make_collision_event(
                    char_a=char_a, char_b=char_b,
                    collision_type="感知对冲",
                    collision_reason=(
                        f"感知攻防：{char_b.name}的感知能力「{b_perception}」"
                        f"与{char_a.name}的隐匿手段「{a_stealth}」形成对冲"
                    ),
                    skill_a_name=a_stealth,
                    skill_b_name=b_perception,
                )
            if b_pow >= a_pow:
                self._set_perception(char_b, char_a.name, "see", global_tick,
                    f"「{b_perception}」识破「{a_stealth}」")
                self._set_perception(char_a, char_b.name, "partial", global_tick,
                    f"隐匿被「{b_perception}」识破")
            else:
                self._set_perception(char_b, char_a.name, "partial", global_tick,
                    f"「{b_perception}」被「{a_stealth}」干扰")
                self._set_perception(char_a, char_b.name, "hidden", global_tick,
                    f"「{a_stealth}」成功隐匿")

        # 单方感知优势
        if a_perception and not b_stealth and result is None:
            self._set_perception(char_a, char_b.name, "see", global_tick,
                f"「{a_perception}」主动感知")
            result = self._make_collision_event(
                char_a=char_a, char_b=char_b,
                collision_type="感知对冲",
                collision_reason=(
                    f"信息差：{char_a.name}的「{a_perception}」发现"
                    f"{char_b.name}的位置与状态"
                ),
                skill_a_name=a_perception,
                skill_b_name="",
            )

        return result
    @staticmethod
    def _calc_perception_power(skill_name: str, skills: list) -> int:
        """根据标签计算感知技能强度"""
        strength = 1
        for s in skills:
            if s.get("name") == skill_name:
                for t in s.get("tags", []):
                    if t in ("洞察", "监视", "天机", "全知"):
                        strength += 2
                    elif t in ("感知", "侦查", "探查"):
                        strength += 1
                break
        return strength
    @staticmethod
    def _calc_stealth_power(skill_name: str, skills: list) -> int:
        """根据标签计算隐匿技能强度"""
        strength = 1
        for s in skills:
            if s.get("name") == skill_name:
                for t in s.get("tags", []):
                    if t in ("空间隐匿", "天道遮蔽", "绝对隐匿"):
                        strength += 2
                    elif t in ("隐匿", "伪装", "潜行"):
                        strength += 1
                break
        return strength
    @staticmethod
    def _set_perception(observer, target: str, status: str,
                         tick: int, reason: str = ""):
        """更新观察者对目标的感知状态"""
        ps = getattr(observer, 'perception_state', None)
        if ps is not None:
            ps[target] = {"status": status, "since_tick": tick, "reason": reason}
    def build_perception_context(self) -> str:
        """为叙事生成构建信息差上下文"""
        chars = getattr(self, 'characters', None)
        if not chars:
            return ""
        lines = ["[信息差状态]"]
        for c in chars:
            ps = getattr(c, 'perception_state', {})
            if not ps:
                continue
            hidden = [t for t, s in ps.items() if s["status"] == "hidden"]
            partial = [t for t, s in ps.items() if s["status"] == "partial"]
            if hidden:
                lines.append(
                    f"  {c.name} 完全不知晓以下角色: {', '.join(hidden)}")
            if partial:
                lines.append(
                    f"  {c.name} 仅模糊感知以下角色: {', '.join(partial)}")
        return "\n".join(lines) if len(lines) > 1 else ""
    def _check_ability_collision(
        self, char_a, char_b, skill_a, skill_b
    ) -> Optional[CollisionEvent]:
        """
        能力对冲检测
        检测模式：角色A的主动技能标签/克制标签 匹配 角色B的弱点/限制标签

        Returns:
            检测到碰撞返回 CollisionEvent，否则返回 None
        """
        # 收集A的克制标签（包括技能名本身）
        a_counters = set()
        for s in skill_a:
            for tag in s.get("counters", []):
                a_counters.add(tag)
            if s.get("name"):
                a_counters.add(s["name"])

        # 收集B的弱点/标签
        b_limits = set()
        for s in skill_b:
            for tag in s.get("limits", []):
                b_limits.add(tag)
            for tag in s.get("tags", []):
                b_limits.add(tag)

        # 检查交集
        intersection = a_counters & b_limits
        if intersection:
            matched_tag = list(intersection)[0]
            a_skill_name = self._find_skill_with_tag(skill_a, matched_tag)
            b_skill_name = self._find_skill_with_tag(skill_b, matched_tag)
            return self._make_collision_event(
                char_a=char_a, char_b=char_b,
                collision_type="能力对冲",
                collision_reason=(
                    f"能力克制：{char_a.name}的「{a_skill_name}」克制"
                    f"{char_b.name}的「{b_skill_name}」（匹配标签：{matched_tag}）"
                ),
                skill_a_name=a_skill_name,
                skill_b_name=b_skill_name,
            )

        # 反向检查：B克制A
        b_counters = set()
        for s in skill_b:
            for tag in s.get("counters", []):
                b_counters.add(tag)
            if s.get("name"):
                b_counters.add(s["name"])

        a_limits = set()
        for s in skill_a:
            for tag in s.get("limits", []):
                a_limits.add(tag)
            for tag in s.get("tags", []):
                a_limits.add(tag)

        intersection = b_counters & a_limits
        if intersection:
            matched_tag = list(intersection)[0]
            a_skill_name = self._find_skill_with_tag(skill_a, matched_tag)
            b_skill_name = self._find_skill_with_tag(skill_b, matched_tag)
            return self._make_collision_event(
                char_a=char_a, char_b=char_b,
                collision_type="能力对冲",
                collision_reason=(
                    f"能力克制：{char_b.name}的「{b_skill_name}」克制"
                    f"{char_a.name}的「{a_skill_name}」（匹配标签：{matched_tag}）"
                ),
                skill_a_name=a_skill_name,
                skill_b_name=b_skill_name,
            )

        return None
    def _check_proximity_collision(
        self, char_a, char_b, skill_a, skill_b
    ) -> Optional[CollisionEvent]:
        """
        基于空间位置的距离碰撞检测
        当两个角色的 pos 坐标在阈值距离内时触发

        Returns:
            检测到碰撞返回 CollisionEvent，否则返回 None
        """
        pos_a = getattr(char_a, 'pos', None)
        pos_b = getattr(char_b, 'pos', None)

        if pos_a is None or pos_b is None:
            return None

        # 计算曼哈顿距离
        distance = abs(pos_a[0] - pos_b[0]) + abs(pos_a[1] - pos_b[1])

        if distance <= _PROXIMITY_THRESHOLD:
            # 获取碰撞地点信息
            location_name = ""
            if self.world:
                tile = self.world.get_tile(pos_a[0], pos_a[1])
                if tile and hasattr(tile, 'name') and tile.name:
                    location_name = tile.name
                elif tile and hasattr(tile, 'tile_type'):
                    location_name = tile.tile_type.value
            if not location_name:
                location_name = f"({pos_a[0]}, {pos_a[1]})"

            # 两人都在移动或有目标时，接近才有意义
            goal_a = getattr(char_a, 'goal', '') or ''
            goal_b = getattr(char_b, 'goal', '') or ''

            if not goal_a and not goal_b:
                return None  # 两人都没目标，单纯的接近不算碰撞

            skill_a_name = skill_a[0]["name"] if skill_a else ""
            skill_b_name = skill_b[0]["name"] if skill_b else ""

            event = self._make_collision_event(
                char_a=char_a, char_b=char_b,
                collision_type="接近碰撞",
                collision_reason=(
                    f"空间接近：{char_a.name}与{char_b.name}"
                    f"在「{location_name}」附近相遇"
                ),
                skill_a_name=skill_a_name,
                skill_b_name=skill_b_name,
            )
            event.location = location_name
            return event

        return None
    def _make_collision_event(
        self, char_a, char_b,
        collision_type: str, collision_reason: str,
        skill_a_name: str = "", skill_b_name: str = "",
        collision_subtype: str = "", collision_weight: int = 0,
    ) -> CollisionEvent:
        """
        创建碰撞事件的基础工厂方法
        自动填充 id、tick、角色信息和地点/世界修饰器
        并评估实力差距，决定碰撞结局（碾压/僵持/逃脱/反杀/试探）
        """
        # 获取碰撞地点
        location_name = ""
        pos_a = getattr(char_a, 'pos', None)
        if pos_a and self.world:
            tile = self.world.get_tile(pos_a[0], pos_a[1])
            if tile and hasattr(tile, 'name') and tile.name:
                location_name = tile.name

        # 获取世界修饰器
        world_modifier = ""
        if self.world:
            theme = getattr(self.world, 'theme', '')
            if theme:
                world_modifier = f"世界主题：{theme}"

        # ── 评估实力差距，决定碰撞结局（防止主角横死）──
        outcome, power_gap, weaker_id = self._evaluate_outcome(
            char_a, char_b, skill_a_name, skill_b_name, location_name
        )

        return CollisionEvent(
            id=str(uuid.uuid4())[:8],
            tick=self._global_tick,
            char_a_id=getattr(char_a, 'id', ''),
            char_a_name=getattr(char_a, 'name', '未知'),
            char_b_id=getattr(char_b, 'id', ''),
            char_b_name=getattr(char_b, 'name', '未知'),
            collision_type=collision_type,
            collision_subtype=collision_subtype,
            collision_reason=collision_reason,
            collision_weight=collision_weight,
            outcome_type=outcome,
            power_gap=power_gap,
            weaker_char_id=weaker_id,
            char_a_skill=skill_a_name,
            char_b_skill=skill_b_name,
            location=location_name,
            world_modifier=world_modifier,
        )
    def _calc_combat_power(self, char) -> int:
        """计算角色综合战力 = 攻击 + 防御 + 体力"""
        attrs = getattr(char, 'attrs', {}) or {}
        return (
            attrs.get("攻击", 0)
            + attrs.get("防御", 0)
            + attrs.get("体力", 0)
        )
    def _has_escape_skill(self, char, skill_name: str) -> bool:
        """检查角色是否有逃生类技能（隐匿/速度/幻术/轻功等）"""
        # 逃生类关键词：隐匿 + 速度 + 幻术 + 轻功 + 闪避
        escape_keywords = [
            "隐", "匿", "逃", "遁", "速", "幻", "藏", "瞬", "迷",
            "轻功", "踏", "行", "闪", "避", "飞", "纵", "跃", "翔",
        ]
        # 优先检查本次碰撞触发的技能
        if skill_name:
            if any(kw in skill_name for kw in escape_keywords):
                return True
        # 再检查角色所有技能
        skills_raw = getattr(char, 'skills', []) or []
        for s in skills_raw:
            name = s if isinstance(s, str) else (s.get("name", "") if isinstance(s, dict) else getattr(s, 'name', ''))
            if name and any(kw in name for kw in escape_keywords):
                return True
        return False
    def _evaluate_outcome(
        self, char_a, char_b, skill_a: str, skill_b: str, location: str
    ) -> tuple:
        """评估碰撞结局的基础物理方向（不剧本化脱险方式）。

        设计原则：
        - 物理层（保留）：实力差距比 ratio + 逃跑能力事实
        - 情境层（交给 AI）：察觉危险 / 外援介入 / 奇遇触发 / 付出代价
          → 这些不再用面板数值门槛判定，而是让 AI 看情境写

        Returns:
            (outcome_type, power_gap, weaker_char_id)
            outcome_type 只会是 STALEMATE / PROBE / ESCAPE / CRUSH 四种基础方向
            CRUSH 时由 AI 在叙事中选择具体脱险方式
        """
        pa = self._calc_combat_power(char_a)
        pb = self._calc_combat_power(char_b)
        # 防止除零
        if pa <= 0 and pb <= 0:
            return CollisionOutcome.STALEMATE, 1.0, ""

        if pa == 0 or pb == 0:
            return CollisionOutcome.STALEMATE, 1.0, ""

        ratio = max(pa, pb) / max(1, min(pa, pb))
        weaker = char_a if pa < pb else char_b
        weaker_skill = skill_a if pa < pb else skill_b
        weaker_id = getattr(weaker, 'id', '')

        # 实力相当（<1.5倍）→ 僵持
        if ratio < 1.5:
            return CollisionOutcome.STALEMATE, ratio, weaker_id

        # 弱方有逃生技能 → 逃跑成功（事实判定，非数值门槛）
        if self._has_escape_skill(weaker, weaker_skill):
            return CollisionOutcome.ESCAPE, ratio, weaker_id

        # 实力悬殊（>=2.5倍）+ 无逃生技能 → 碾压风险
        # 具体脱险方式由 AI 在叙事中根据情境判断
        if ratio >= 2.5:
            return CollisionOutcome.CRUSH, ratio, weaker_id

        # 1.5-2.5 倍 → 试探
        return CollisionOutcome.PROBE, ratio, weaker_id
    def _find_skill_by_keyword(self, skills: list, keyword: str) -> str:
        """在技能列表中查找包含指定关键词的技能名"""
        for s in skills:
            name = s.get("name", "")
            if keyword in name:
                return name
            tags = s.get("tags", [])
            if keyword in tags:
                return name
        return ""
    def _find_perception_skill(self, skills: list) -> Optional[str]:
        """在技能列表中查找感知类技能"""
        for s in skills:
            name = s.get("name", "")
            for kw in _PERCEPTION_KEYWORDS:
                if kw in name:
                    return name
            tags = s.get("tags", [])
            for kw in _PERCEPTION_KEYWORDS:
                if kw in tags:
                    return name
        return None
    def _find_stealth_skill(self, skills: list) -> Optional[str]:
        """在技能列表中查找隐匿类技能"""
        for s in skills:
            name = s.get("name", "")
            for kw in _STEALTH_KEYWORDS:
                if kw in name:
                    return name
            tags = s.get("tags", [])
            for kw in _STEALTH_KEYWORDS:
                if kw in tags:
                    return name
        return None
    def _find_skill_with_tag(self, skills: list, tag: str) -> str:
        """在技能列表中查找包含指定标签的技能名"""
        for s in skills:
            if tag in s.get("name", ""):
                return s.get("name", "")
            if tag in s.get("tags", []):
                return s.get("name", "")
            if tag in s.get("limits", []):
                return s.get("name", "")
            if tag in s.get("counters", []):
                return s.get("name", "")
        return ""
