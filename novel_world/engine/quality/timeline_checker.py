# -*- coding: utf-8 -*-
"""
TimelineChecker — Fast 规则检查层
===================================
纯规则、零 AI 调用、实时生效的时间线一致性检查。

5 个检测维度：
1. 时间回溯检测 — Tick 顺序 + time_marker 单调性
2. 角色状态一致性 — 位置可达性 + 数量/名称一致性 + 关系变更审计
3. 物品/道具一致性 — 归属变更记录 + 重复存在检测
4. 世界规则违规 — 逐条检查叙事文本中是否出现违规关键词
5. 伏笔追踪 — 记录未解伏笔 + 超期未回收警告
"""

import re
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Set, Tuple

logger = logging.getLogger("TimelineChecker")


class IssueLevel(Enum):
    BLOCKER = "blocker"    # 硬错误，必须修正
    ERROR = "error"        # 严重矛盾
    WARNING = "warning"    # 潜在问题
    INFO = "info"          # 提示信息


@dataclass
class TimelineIssue:
    """一次检查发现的问题"""
    dimension: str                    # 检查维度
    level: IssueLevel                 # 严重级别
    message: str                      # 问题描述
    tick: int = 0                     # 发现问题的 Tick
    chapter: int = 0                  # 发现问题的章节
    detail: dict = field(default_factory=dict)   # 详细数据
    suggestion: str = ""              # 修复建议
    related_characters: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "dimension": self.dimension,
            "level": self.level.value,
            "message": self.message,
            "tick": self.tick,
            "chapter": self.chapter,
            "detail": self.detail,
            "suggestion": self.suggestion,
            "related_characters": self.related_characters,
        }


@dataclass
class ClueRecord:
    """伏笔记录"""
    content: str                      # 伏笔关键词/描述
    found_tick: int                   # 发现 Tick
    found_chapter: int                # 发现章节
    resolved: bool = False            # 是否已回收
    resolved_tick: int = 0            # 回收 Tick
    resolved_chapter: int = 0         # 回收章节


class TimelineChecker:
    """时间线 Fast 规则检查器

    纯代码逻辑，不调用 AI。在每个 Tick 结束后运行，
    检测时间回溯、角色异常、物品矛盾、世界规则违规、伏笔超期。

    用法:
        checker = TimelineChecker()
        issues = checker.check(world, narrative_text, tick, chapter)
        if issues:
            for i in issues:
                print(f"[{i.level.value}] {i.message}")
    """

    # ── 伏笔检测的关键词模式 ──
    _CLUE_PATTERNS = [
        # 物品类伏笔
        r"(?:神秘|上古|远古|失落)(?:的)?(?:玉佩|卷轴|法宝|遗物|丹药|兵器|残卷|秘籍|戒指)",
        r"(?:古怪|奇异)(?:的)?(?:石头|珠子|令牌|符箓|符文)",
        # 人物类伏笔
        r"(?:神秘|来历不明)(?:的)?(?:老者|少年|女子|人|修士|道人)",
        r"(?P<name>.{2,4})(?:的身份|的来历|的真实身份|似乎并不简单)",
        # 预言类伏笔
        r"(?:预言|预言中|古书记载|天机所示|星象预示)",
        r"(?:传说|传说中的|古时|上古时期).{0,10}(?:将会|必将|注定)",
        # 线索类伏笔
        r"(?:留下了|留下)(?:一个|一道|一些)(?:线索|暗号|标记)",
        r"(?:似乎|仿佛|好像).{0,10}(?:隐藏|藏着|隐瞒).{0,10}(?:什么|秘密|真相)",
        # 特殊标记
        r"(?:暗处|阴影中|暗中).{0,10}(?:注视着|观察着|窥视)",
    ]
    _CLUE_REGEX = re.compile("|".join(_CLUE_PATTERNS), re.IGNORECASE)

    # ── 超出范围时的伏笔回收关键词 ──
    _RESOLVE_PATTERNS = [
        r"(?:终于|这才|方才)(?:明白|知道|发现|领悟|揭开|解开了).{0,15}(?:真相|秘密|谜团|身份|来历)",
        r"(?:原来|原来如此|原来是这样)(.{0,20})",
        r"(?:果不其然|不出所料|正如.+所料)",
    ]
    _RESOLVE_REGEX = re.compile("|".join(_RESOLVE_PATTERNS), re.IGNORECASE)

    def __init__(self, max_unresolved_clue_ticks: int = 30):
        """
        Args:
            max_unresolved_clue_ticks: 伏笔超期阈值（Tick 数），超过此值仍未回收则 WARNING
        """
        self.max_unresolved_clue_ticks = max_unresolved_clue_ticks

        # 历史状态：用于跨 Tick 比较
        self._prev_tick: int = 0
        self._prev_time_marker: str = ""
        self._character_positions: Dict[str, str] = {}           # 角色名 → 上次位置
        self._character_relationships: Dict[str, Dict[str, str]] = {}  # 角色名 → {目标角色: 关系}
        self._character_roster: Set[str] = set()                 # 上一 Tick 的角色名单
        self._item_ownership: Dict[str, str] = {}                # 物品名 → 持有者
        self._item_locations: Dict[str, str] = {}                # 物品名 → 位置

        # 伏笔追踪
        self.unresolved_clues: List[ClueRecord] = []
        self._all_clues: List[ClueRecord] = []

        # 已执行的检查记录
        self.checks: List[dict] = []

    # ── 主入口 ──

    def check(
        self,
        world_state,        # World / dict with state info
        narrative_text: str,
        tick_number: int,
        chapter_number: int,
    ) -> List[TimelineIssue]:
        """执行所有 Fast 规则检查，返回问题列表"""
        issues: List[TimelineIssue] = []

        # 提取角色和物品状态
        chars = self._extract_characters(world_state)
        constraints = self._extract_constraints(world_state)
        time_marker = self._extract_time_marker(world_state)

        # 维度1: 时间回溯
        issues.extend(self._check_temporal_order(tick_number, time_marker, chapter_number))

        # 维度2: 角色状态一致性
        issues.extend(self._check_character_consistency(chars, narrative_text, tick_number, chapter_number))

        # 维度3: 物品/道具一致性
        issues.extend(self._check_item_consistency(narrative_text, tick_number, chapter_number))

        # 维度4: 世界规则违规
        issues.extend(self._check_world_rules(narrative_text, constraints, tick_number, chapter_number))

        # 维度5: 伏笔追踪
        issues.extend(self._check_clues(narrative_text, tick_number, chapter_number))

        # 更新内部状态
        self._update_state(chars, tick_number, time_marker)

        # 记录检查
        self.checks.append({
            "tick": tick_number,
            "chapter": chapter_number,
            "issues_count": len(issues),
            "timestamp": datetime.now().isoformat(),
        })

        return issues

    # ── 维度1: 时间回溯检测 ──

    def _check_temporal_order(
        self,
        tick_number: int,
        time_marker: str,
        chapter_number: int,
    ) -> List[TimelineIssue]:
        """检测时间回溯：Tick 必须递增，time_marker 不能倒退"""
        issues = []

        # Tick 顺序
        if self._prev_tick > 0 and tick_number <= self._prev_tick:
            issues.append(TimelineIssue(
                dimension="temporal_order",
                level=IssueLevel.ERROR,
                message=f"Tick 倒流：当前 Tick {tick_number} ≤ 上一 Tick {self._prev_tick}",
                tick=tick_number,
                chapter=chapter_number,
                detail={"prev_tick": self._prev_tick, "current_tick": tick_number},
                suggestion="检查引擎推演顺序，Tick 必须严格递增",
            ))

        # time_marker 单调性
        if time_marker and self._prev_time_marker:
            order = {"morning": 1, "noon": 2, "afternoon": 3, "evening": 4, "night": 5}
            prev_val = order.get(self._prev_time_marker.lower(), 0)
            curr_val = order.get(time_marker.lower(), 0)
            if prev_val > 0 and curr_val > 0 and curr_val < prev_val:
                issues.append(TimelineIssue(
                    dimension="temporal_order",
                    level=IssueLevel.WARNING,
                    message=f"时间标记倒退：从 '{self._prev_time_marker}' 回退到 '{time_marker}'",
                    tick=tick_number,
                    chapter=chapter_number,
                    detail={"prev": self._prev_time_marker, "current": time_marker},
                    suggestion=f"将当前 time_marker 改为 'night' 或 'next_morning'",
                ))

        return issues

    # ── 维度2: 角色状态一致性 ──

    def _check_character_consistency(
        self,
        chars: List[dict],
        narrative_text: str,
        tick_number: int,
        chapter_number: int,
    ) -> List[TimelineIssue]:
        """检测角色位置跳变、数量/名称一致性、关系变更"""
        issues = []

        current_names = {c["name"] for c in chars}

        # 检测角色名单变化
        if self._character_roster:
            vanished = self._character_roster - current_names
            appeared = current_names - self._character_roster

            # 只在非初始状态下报告（第一 tick 跳过）
            for name in vanished:
                # 检查叙事中是否有合理解释（死亡/离开）
                if not self._has_disappearance_reason(name, narrative_text):
                    issues.append(TimelineIssue(
                        dimension="character_consistency",
                        level=IssueLevel.WARNING,
                        message=f"角色「{name}」在上 Tick 存在但本 Tick 消失，叙事中未提供明确离开原因",
                        tick=tick_number,
                        chapter=chapter_number,
                        detail={"vanished_character": name},
                        related_characters=[name],
                        suggestion=f"在叙事中说明「{name}」的去向",
                    ))

            for name in appeared:
                # 检查叙事中是否有新角色介绍
                if not self._has_appearance_reason(name, narrative_text):
                    issues.append(TimelineIssue(
                        dimension="character_consistency",
                        level=IssueLevel.INFO,
                        message=f"新角色「{name}」出现，叙事中未提供明确介绍",
                        tick=tick_number,
                        chapter=chapter_number,
                        detail={"new_character": name},
                        related_characters=[name],
                        suggestion=f"在叙事中简要介绍「{name}」",
                    ))

        # 检测位置跳变
        for c in chars:
            name = c["name"]
            position = c.get("position", "")
            if name in self._character_positions and position:
                prev_pos = self._character_positions[name]
                if prev_pos != position:
                    distance = self._estimate_location_distance(prev_pos, position)
                    if distance > 2:  # 跨越 3+ 条距离边，可能不合理
                        issues.append(TimelineIssue(
                            dimension="character_consistency",
                            level=IssueLevel.WARNING,
                            message=f"角色「{name}」位置跳变过大：{prev_pos} → {position}",
                            tick=tick_number,
                            chapter=chapter_number,
                            detail={"from": prev_pos, "to": position, "estimated_distance": distance},
                            related_characters=[name],
                            suggestion=f"添加过渡叙事说明「{name}」如何从 {prev_pos} 到达 {position}",
                        ))

        # 检测关系突然变化（仅在有关系数据的角色间检查）
        for c in chars:
            name = c["name"]
            rels = c.get("relationships", {})
            if name in self._character_relationships:
                prev_rels = self._character_relationships[name]
                for target, rel_type in rels.items():
                    prev_type = prev_rels.get(target)
                    if prev_type and prev_type != rel_type:
                        # 关系从 positive 变 negative 需有触发事件
                        if self._is_relation_reversal(prev_type, rel_type):
                            if not self._has_conflict_event(name, target, narrative_text):
                                issues.append(TimelineIssue(
                                    dimension="character_consistency",
                                    level=IssueLevel.WARNING,
                                    message=f"角色关系突变：{name}↔{target} 从「{prev_type}」变为「{rel_type}」，无对应冲突事件",
                                    tick=tick_number,
                                    chapter=chapter_number,
                                    detail={"from": prev_type, "to": rel_type, "pair": f"{name}↔{target}"},
                                    related_characters=[name, target],
                                    suggestion=f"添加冲突事件解释关系变化",
                                ))

        return issues

    # ── 维度3: 物品/道具一致性 ──

    def _check_item_consistency(
        self,
        narrative_text: str,
        tick_number: int,
        chapter_number: int,
    ) -> List[TimelineIssue]:
        """检测物品归属变更和重复存在"""
        issues = []

        # 通过简单正则检测物品提及
        item_mentions = self._extract_item_mentions(narrative_text)

        for item in item_mentions:
            name = item["name"]
            holder = item["holder"]
            location = item.get("location", "")

            # 归属变更检测
            if name in self._item_ownership:
                prev_holder = self._item_ownership[name]
                if prev_holder != holder and holder:
                    # 物品易主，检查是否有交接叙事
                    if not self._has_transfer_event(name, prev_holder, holder, narrative_text):
                        issues.append(TimelineIssue(
                            dimension="item_consistency",
                            level=IssueLevel.WARNING,
                            message=f"物品「{name}」归属变更无记录：{prev_holder} → {holder}",
                            tick=tick_number,
                            chapter=chapter_number,
                            detail={"item": name, "from": prev_holder, "to": holder},
                            suggestion=f"添加交接/转让叙事",
                        ))

            # 重复存在检测（同一物品出现在两个不同位置）
            if name in self._item_locations and location:
                prev_loc = self._item_locations[name]
                if prev_loc != location:
                    issues.append(TimelineIssue(
                        dimension="item_consistency",
                        level=IssueLevel.ERROR,
                        message=f"物品「{name}」同时出现在两个位置：{prev_loc} 和 {location}",
                        tick=tick_number,
                        chapter=chapter_number,
                        detail={"item": name, "locations": [prev_loc, location]},
                        suggestion="确认物品的实际位置，修正矛盾",
                    ))

        # 更新物品状态
        for item in item_mentions:
            if item["holder"]:
                self._item_ownership[item["name"]] = item["holder"]
            if item.get("location"):
                self._item_locations[item["name"]] = item["location"]

        return issues

    # ── 维度4: 世界规则违规 ──

    def _check_world_rules(
        self,
        narrative_text: str,
        constraints: List[str],
        tick_number: int,
        chapter_number: int,
    ) -> List[TimelineIssue]:
        """逐条检查叙事文本中是否出现违反世界规则的内容"""
        issues = []

        for constraint in constraints:
            violation = self._parse_constraint_violation(constraint, narrative_text)
            if violation:
                issues.append(TimelineIssue(
                    dimension="world_rule",
                    level=IssueLevel.ERROR,
                    message=f"世界规则违反：{violation}",
                    tick=tick_number,
                    chapter=chapter_number,
                    detail={"constraint": constraint, "violation": violation},
                    suggestion=f"修改叙事使其符合规则：「{constraint}」",
                ))

        return issues

    # ── 维度5: 伏笔追踪 ──

    def _check_clues(
        self,
        narrative_text: str,
        tick_number: int,
        chapter_number: int,
    ) -> List[TimelineIssue]:
        """检测新伏笔埋设 + 旧伏笔回收 + 超期未回收"""
        issues = []

        # 检测新伏笔
        for match in self._CLUE_REGEX.finditer(narrative_text):
            content = match.group().strip()
            # 避免重复记录
            already = any(c.content == content and not c.resolved for c in self.unresolved_clues)
            if not already:
                clue = ClueRecord(
                    content=content,
                    found_tick=tick_number,
                    found_chapter=chapter_number,
                )
                self.unresolved_clues.append(clue)
                self._all_clues.append(clue)
                issues.append(TimelineIssue(
                    dimension="clue_tracking",
                    level=IssueLevel.INFO,
                    message=f"新伏笔埋设：「{content}」",
                    tick=tick_number,
                    chapter=chapter_number,
                    detail={"clue": content},
                ))

        # 检测回收
        resolve_matches = list(self._RESOLVE_REGEX.finditer(narrative_text))
        if resolve_matches:
            # 尝试将回收与最近的未回收伏笔关联
            resolved_content = " | ".join(m.group().strip() for m in resolve_matches)
            for clue in self.unresolved_clues:
                if not clue.resolved:
                    # 简单启发式：回收叙事与伏笔在同一章或紧邻
                    if chapter_number >= clue.found_chapter:
                        clue.resolved = True
                        clue.resolved_tick = tick_number
                        clue.resolved_chapter = chapter_number
                        issues.append(TimelineIssue(
                            dimension="clue_tracking",
                            level=IssueLevel.INFO,
                            message=f"伏笔疑似回收：「{clue.content}」→ {resolved_content}",
                            tick=tick_number,
                            chapter=chapter_number,
                            detail={"clue": clue.content, "resolution": resolved_content},
                        ))

        # 超期未回收
        for clue in self.unresolved_clues:
            if not clue.resolved:
                age = tick_number - clue.found_tick
                if age > self.max_unresolved_clue_ticks:
                    issues.append(TimelineIssue(
                        dimension="clue_tracking",
                        level=IssueLevel.WARNING,
                        message=f"伏笔超期未回收：「{clue.content}」已埋设 {age} Tick",
                        tick=tick_number,
                        chapter=chapter_number,
                        detail={"clue": clue.content, "age_ticks": age, "found_tick": clue.found_tick},
                        suggestion="考虑在近期叙事中回收此伏笔",
                    ))

        return issues

    # ── 报告生成 ──

    def generate_report(self) -> dict:
        """生成当前检查汇总报告"""
        all_issues = self.checks
        unresolved = [c for c in self.unresolved_clues if not c.resolved]
        resolved = [c for c in self.unresolved_clues if c.resolved]

        return {
            "total_checks": len(all_issues),
            "unresolved_clues_count": len(unresolved),
            "resolved_clues_count": len(resolved),
            "unresolved_clues": [
                {
                    "content": c.content,
                    "found_tick": c.found_tick,
                    "found_chapter": c.found_chapter,
                    "age_ticks": (self._prev_tick - c.found_tick) if self._prev_tick > 0 else 0,
                }
                for c in unresolved
            ],
            "resolved_clues": [
                {
                    "content": c.content,
                    "found_tick": c.found_tick,
                    "resolved_tick": c.resolved_tick,
                }
                for c in resolved
            ],
            "recent_checks": all_issues[-5:] if len(all_issues) > 5 else all_issues,
        }

    # ── 内部辅助 ──

    def _extract_characters(self, world_state) -> List[dict]:
        """从 World 对象提取角色列表"""
        chars = []
        if hasattr(world_state, '_characters'):
            for c in world_state._characters:
                chars.append({
                    "name": getattr(c, 'name', '?'),
                    "position": getattr(c, 'current_location', ''),
                    "relationships": getattr(c, 'relationships', {}),
                })
        elif isinstance(world_state, dict):
            for c in world_state.get("characters", []):
                chars.append({
                    "name": c.get("name", "?"),
                    "position": c.get("position", c.get("current_location", "")),
                    "relationships": c.get("relationships", {}),
                })
        return chars

    def _extract_constraints(self, world_state) -> List[str]:
        """从 World 配置提取规则约束"""
        if hasattr(world_state, 'config') and hasattr(world_state.config, 'rules'):
            return world_state.config.rules or []
        if isinstance(world_state, dict):
            return world_state.get("constraints", world_state.get("rules", []))
        return []

    def _extract_time_marker(self, world_state) -> str:
        """从 World 状态提取当前时间标记"""
        if hasattr(world_state, 'time_marker'):
            return world_state.time_marker or ""
        if isinstance(world_state, dict):
            return world_state.get("time_marker", "")
        return ""

    def _update_state(self, chars: List[dict], tick_number: int, time_marker: str):
        """更新内部历史状态"""
        self._prev_tick = tick_number
        if time_marker:
            self._prev_time_marker = time_marker
        self._character_roster = {c["name"] for c in chars}
        for c in chars:
            if c.get("position"):
                self._character_positions[c["name"]] = c["position"]
            if c.get("relationships"):
                self._character_relationships[c["name"]] = dict(c["relationships"])

    def _has_disappearance_reason(self, name: str, text: str) -> bool:
        """检查叙事中是否有角色消失的理由"""
        patterns = [
            rf"{name}.*(?:离开|离去|消失|隐去|遁走|飞升|陨落|身亡|逝去|不见)",
            rf"(?:离开|离去|消失).*{name}",
        ]
        return any(re.search(p, text) for p in patterns)

    def _has_appearance_reason(self, name: str, text: str) -> bool:
        """检查叙事中是否有新角色出现的介绍"""
        patterns = [
            rf"{name}.*(?:出现|现身|降临|来到|步入|走进|踏入|引入|介绍)",
            rf"(?:一位|一名|一个).*{name}",
        ]
        return any(re.search(p, text) for p in patterns)

    def _estimate_location_distance(self, loc_a: str, loc_b: str) -> int:
        """估算两个位置的距离（简单字符差异法）"""
        if loc_a == loc_b:
            return 0
        # 粗略估算：名称完全不同则距离大
        common = len(set(loc_a) & set(loc_b))
        total = max(len(set(loc_a) | set(loc_b)), 1)
        similarity = common / total
        if similarity > 0.6:
            return 1    # 疑似同一地区
        if similarity > 0.3:
            return 2    # 可能相关
        return 3        # 完全不同

    def _is_relation_reversal(self, prev: str, curr: str) -> bool:
        """判断关系是否发生反转（友→敌）"""
        positive = {"友", "friend", "友善", "友好", "信任", "亲密", "爱慕"}
        negative = {"敌", "enemy", "敌对", "仇视", "憎恨", "厌恶"}
        prev_positive = prev in positive or any(p in prev for p in positive)
        curr_negative = curr in negative or any(n in curr for n in negative)
        prev_negative = prev in negative or any(n in prev for n in negative)
        curr_positive = curr in positive or any(p in curr for p in positive)
        return (prev_positive and curr_negative) or (prev_negative and curr_positive)

    def _has_conflict_event(self, name_a: str, name_b: str, text: str) -> bool:
        """检查叙事中是否有两个角色间的冲突事件"""
        patterns = [
            rf"({name_a}|{name_b}).*(?:冲突|争执|对战|交手|翻脸|决裂).*({name_a}|{name_b})",
            rf"(?:冲突|争执|对战).*{name_a}.*{name_b}",
        ]
        return any(re.search(p, text) for p in patterns)

    def _has_transfer_event(self, item: str, from_who: str, to_who: str, text: str) -> bool:
        """检查是否有物品交接事件"""
        patterns = [
            rf"{from_who}.*(?:交给|递给|赠予|交给|递给).*{to_who}.*{item}",
            rf"{to_who}.*(?:接过|接过|获得|得到).*{from_who}.*{item}",
            rf"{item}.*(?:转交|转赠|落到).*{to_who}",
        ]
        return any(re.search(p, text) for p in patterns)

    def _extract_item_mentions(self, narrative_text: str) -> List[dict]:
        """从叙事中提取物品提及"""
        items = []
        # 匹配「XXX的YYY」或「持有XX」等模式
        patterns = [
            r"(?P<holder>.{2,4})(?:的|手中的|怀中的|佩戴的|持有的)(?P<item>(?:玉佩|卷轴|法宝|遗物|丹药|兵器|残卷|秘籍|戒指|剑|刀|符|灵石|令牌|宝珠|神器|法杖|护符|甲|盾))",
            r"(?P<item>(?:玉佩|卷轴|法宝|遗物|丹药|兵器|残卷|秘籍|戒指|神剑|宝刀|神符|灵石|令牌|宝珠|神器|法杖|护符|宝甲|神盾))(?:落入了|被)(?P<holder>.{2,4})(?:手中|之手|得到)",
            r"(?P<holder>.{2,4})(?:取出|拿出|掏出|亮出)(?:了)?(?P<item>(?:玉佩|卷轴|法宝|遗物|丹药|兵器|残卷|秘籍|戒指|剑|刀|符|灵石|令牌|宝珠|神器|法杖|护符|甲|盾))",
        ]
        for pat in patterns:
            for m in re.finditer(pat, narrative_text):
                items.append({
                    "name": m.group("item"),
                    "holder": m.group("holder"),
                    "location": "",
                })
        return items

    def _parse_constraint_violation(self, constraint: str, text: str) -> Optional[str]:
        """解析单条世界规则是否被违反

        约束格式示例：
        - "魔法只存在于秘境" → 检测非秘境位置出现「魔法」
        - "禁止使用现代科技" → 检测「手机/电脑/汽车」等关键词
        - "凡人无法修炼" → 检测「凡人.+修炼」模式
        """
        # 模式1: "X只存在于Y" → 检测 X 在非 Y 位置出现
        m = re.match(r"(.+?)只存在于(.+)", constraint)
        if m:
            entity = m.group(1).strip()
            location = m.group(2).strip()
            # 查找 narrative 中 entity 是否出现在非 location 的上下文中
            for sentence in re.split(r'[。！？\n]', text):
                if entity in sentence and location not in sentence:
                    return f"「{entity}」出现在非「{location}」的上下文中"
            return None

        # 模式2: "禁止/不允许 X" → 检测 X 相关关键词
        m = re.match(r"(?:禁止|不允许|不可)(.+)", constraint)
        if m:
            forbidden = m.group(1).strip()
            # 展开为关键词列表
            keywords = self._expand_forbidden_keywords(forbidden)
            found = [kw for kw in keywords if kw in text]
            if found:
                return f"叙事中出现禁止内容：「{forbidden}」（关键词: {', '.join(found)}）"
            return None

        # 模式3: "X无法/不能Y" → 检测 X + Y 组合
        m = re.match(r"(.+?)(?:无法|不能|不可)(.+)", constraint)
        if m:
            subject = m.group(1).strip()
            action = m.group(2).strip()
            pattern = rf"{subject}.{{0,10}}{action}"
            if re.search(pattern, text):
                return f"「{subject}」执行了不可为的行为：「{action}」"
            return None

        # 默认：直接在叙事中搜索约束关键词
        if constraint in text:
            return f"叙事中出现与规则「{constraint}」矛盾的内容"

        return None

    def _expand_forbidden_keywords(self, forbidden: str) -> List[str]:
        """将禁止描述展开为关键词列表"""
        mapping = {
            "手机": ["手机", "电话", "拨号", "短信", "微信"],
            "电脑": ["电脑", "计算机", "键盘", "鼠标", "屏幕"],
            "现代科技": ["手机", "电脑", "汽车", "飞机", "机器人", "激光", "导弹", "卫星", "网络"],
            "汽车": ["汽车", "轿车", "跑车", "卡车"],
            "热武器": ["枪", "手枪", "步枪", "炸弹", "导弹", "火炮"],
        }
        return mapping.get(forbidden, [forbidden])
