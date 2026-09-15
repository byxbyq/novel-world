# -*- coding: utf-8 -*-
"""
时间树引擎 - 基于 YAML 的分支剧情系统

核心职责：
  1. 加载 timeline_tree.yaml，结合 world_timeline.yaml 的基础事件
  2. 维护 WorldState（角色关系、存活状态、势力关系）
  3. 每章开始时评估条件，解析出本章应触发的事件列表
  4. 根据碰撞结果自动更新世界状态

与现有模块的关系：
  - world_timeline.yaml 保留不变（必然事件），本模块在其基础上叠加分支事件
  - 碰撞引擎的 _collision_history 作为世界状态更新的输入源
  - 在 run_demo.py 中替代原有的简单世界事件注入逻辑

设计原则：
  - 分支条件基于可量化的世界状态（关系、存活、势力），不依赖 AI 推理
  - default 分支保证每章至少有一个可走路径
  - 世界状态可手动设置，也可自动从碰撞历史推断
"""
import logging
import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

import yaml

logger = logging.getLogger(__name__)

# ======================== 关系枚举 ========================

# 角色间关系（正向/中性/负向）
CHAR_RELATIONS = {"信任", "排斥", "敌对", "同盟", "疏远", "亲近", "中立", "敬畏", "敌视"}

# 势力间关系
FACTION_RELATIONS = {"同盟", "敌对", "中立", "附属", "竞争"}

# 势力状态
FACTION_STATUSES = {"活跃", "覆灭", "潜伏"}


# ======================== 条件数据结构 ========================

@dataclass
class Condition:
    """分支条件 - 单个可评估条件"""

    type: str = ""  # "char_relation" / "char_alive" / "faction_relation" / "faction_status" / "default"

    # char_relation / char_alive
    char_a: str = ""
    char_b: str = ""  # char_relation 时为目标角色
    relation: str = ""  # char_relation 的关系词

    # faction_relation / faction_status
    faction_a: str = ""
    faction_b: str = ""  # faction_relation 时为目标势力

    # default
    is_default: bool = False

    def __repr__(self):
        if self.is_default:
            return "Condition(default)"
        if self.type == "char_relation":
            return f"Condition({self.char_a} {self.relation} {self.char_b})"
        if self.type == "char_alive":
            return f"Condition({self.char_a} {'存活' if self.relation == '存活' else '死亡'})"
        if self.type == "faction_relation":
            return f"Condition({self.faction_a} {self.relation} {self.faction_b})"
        if self.type == "faction_status":
            return f"Condition({self.faction_a} {self.relation})"
        return f"Condition({self.type})"


# ======================== 解析结果数据结构 ========================

@dataclass
class ChapterResolution:
    """章节解析结果 — resolve() 的返回值"""

    base_events: List[str] = field(default_factory=list)  # world_timeline.yaml 的基础事件
    branch_outline: List[str] = field(default_factory=list)  # 匹配分支的情节提纲
    matched_condition: str = ""  # 匹配到的条件字符串（调试用）


# ======================== 世界状态 ========================

@dataclass
class WorldState:
    """
    世界状态 - 记录可影响分支走向的所有状态变量

    核心字段：
      - char_relations: 角色A -> 角色B -> 关系词
      - char_alive: 角色名 -> True/False
      - faction_relations: 势力A -> 势力B -> 关系词
      - faction_status: 势力名 -> 状态词（活跃/覆灭/潜伏）
    """

    char_relations: Dict[str, Dict[str, str]] = field(default_factory=dict)
    char_alive: Dict[str, bool] = field(default_factory=dict)
    faction_relations: Dict[str, Dict[str, str]] = field(default_factory=dict)
    faction_status: Dict[str, str] = field(default_factory=dict)

    # ─── 角色关系 ───

    def set_char_relation(self, char_a: str, char_b: str, relation: str):
        """设置角色 A 对 B 的关系（单向）"""
        if char_a not in self.char_relations:
            self.char_relations[char_a] = {}
        self.char_relations[char_a][char_b] = relation

    def get_char_relation(self, char_a: str, char_b: str) -> str:
        """获取角色 A 对 B 的关系，默认返回 '中立'"""
        return self.char_relations.get(char_a, {}).get(char_b, "中立")

    def get_relation_between(self, char_a: str, char_b: str) -> str:
        """
        获取两个角色之间的双向关系（取更明确的一方）。
        优先级：信任 > 亲近 > 中立 > 疏远 > 排斥 > 敌对
        """
        a_to_b = self.get_char_relation(char_a, char_b)
        b_to_a = self.get_char_relation(char_b, char_a)
        priority = {"信任": 6, "亲近": 5, "中立": 4, "敬畏": 4, "疏远": 3, "排斥": 2, "敌视": 1, "敌对": 1}
        if priority.get(a_to_b, 0) >= priority.get(b_to_a, 0):
            return a_to_b
        return b_to_a

    # ─── 角色存活 ───

    def set_alive(self, char_name: str, alive: bool):
        """设置角色存活状态"""
        self.char_alive[char_name] = alive

    def is_alive(self, char_name: str) -> bool:
        """查询角色是否存活，默认 True"""
        return self.char_alive.get(char_name, True)

    # ─── 势力关系 ───

    def set_faction_relation(self, fa: str, fb: str, relation: str):
        """设置势力关系（双向同步）"""
        self.faction_relations.setdefault(fa, {})[fb] = relation
        self.faction_relations.setdefault(fb, {})[fa] = relation

    def get_faction_relation(self, fa: str, fb: str) -> str:
        """查询势力关系，默认 '中立'"""
        return self.faction_relations.get(fa, {}).get(fb, "中立")

    # ─── 势力状态 ───

    def set_faction_status(self, faction: str, status: str):
        """设置势力状态"""
        self.faction_status[faction] = status

    def get_faction_status(self, faction: str) -> str:
        """查询势力状态，默认 '活跃'"""
        return self.faction_status.get(faction, "活跃")


# ======================== 时间树引擎 ========================

class TimelineTreeEngine:
    """
    时间树引擎 - 分支剧情解析与注入

    使用方式：
        engine = TimelineTreeEngine()
        engine.load(project_root)

        # 初始化世界状态
        ws = WorldState()
        ws.set_char_relation("李青云", "苏晚", "信任")

        # 第2章开始前获取事件
        events = engine.resolve(chapter=2, world_state=ws)
        # events 包含：基础必然事件 + 匹配分支的事件

        # 章节结束后更新世界状态
        engine.update_state_from_collisions(ws, collision_events)
    """

    def __init__(self):
        self._tree_config: Dict = {}
        self._base_timeline: Dict[int, List[str]] = {}  # world_timeline.yaml 的基础事件
        self._project_root: str = ""

    # ─── 加载 ───

    def load(self, project_root: str):
        """加载所有配置文件"""
        self._project_root = project_root

        # 加载 world_timeline.yaml（基础必然事件）
        timeline_path = os.path.join(project_root, "world_timeline.yaml")
        if os.path.exists(timeline_path):
            with open(timeline_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
            for item in data.get("timeline", []):
                ch = item.get("chapter", 0)
                # 兼容 "event"（单数字符串）和 "events"（列表）两种格式
                event_val = item.get("events", [])
                if not event_val:
                    single = item.get("event", "")
                    if single:
                        event_val = [single]
                if ch > 0 and event_val:
                    self._base_timeline[ch] = list(event_val) if isinstance(event_val, list) else [event_val]
            logger.info(f"[TimelineTree] 已加载基础时间线：{len(self._base_timeline)} 个章节")

        # 加载 timeline_tree.yaml（分支条件）
        tree_path = os.path.join(project_root, "timeline_tree.yaml")
        if os.path.exists(tree_path):
            with open(tree_path, "r", encoding="utf-8") as f:
                self._tree_config = yaml.safe_load(f) or {}
            logger.info(f"[TimelineTree] 已加载时间树配置："
                        f"{len(self._tree_config.get('timeline', []))} 个章节节点")
        else:
            logger.warning(f"[TimelineTree] 未找到 timeline_tree.yaml，仅使用基础时间线")

    # ─── 核心：解析章节事件 ───

    def resolve(self, chapter: int, world_state: WorldState) -> ChapterResolution:
        """
        解析指定章节的事件列表（基础事件 + 分支提纲）

        Args:
            chapter: 章节号
            world_state: 当前世界状态

        Returns:
            ChapterResolution: base_events（必然事件）+ branch_outline（情节提纲）
        """
        result = ChapterResolution()

        # 1. 添加基础必然事件
        if chapter in self._base_timeline:
            result.base_events = list(self._base_timeline[chapter])

        # 2. 评估时间树分支
        tree_chapter = self._get_tree_chapter(chapter)
        if tree_chapter is None:
            return result

        # 3. 匹配条件分支，获取提纲
        branches = tree_chapter.get("branches", [])
        match_result = self._match_branches(branches, world_state)
        if match_result:
            result.branch_outline = match_result["outline"]
            result.matched_condition = match_result["condition"]

        return result

    def _get_tree_chapter(self, chapter: int) -> Optional[Dict]:
        """从时间树配置中获取指定章节节点"""
        for item in self._tree_config.get("timeline", []):
            if item.get("chapter") == chapter:
                return item
        return None

    # ─── 章节上下文构建 ───

    def build_context(
        self,
        world,
        world_state: WorldState,
        resolution: ChapterResolution,
        chapter_num: int,
        previous_summary: str = "",
    ) -> str:
        """
        收集当前世界状态的完整上下文，供 AI 生成叙事使用。

        Args:
            world: World 对象（含 characters / factions / theme / main_objective）
            world_state: WorldState 对象（关系/存活/势力状态）
            resolution: resolve() 返回的 ChapterResolution
            chapter_num: 当前章节号
            previous_summary: 上一章的叙事摘要

        Returns:
            格式化的章节上下文字符串
        """
        lines = []

        # ── 章节标识 ──
        lines.append(f"## 第 {chapter_num} 章 世界状态上下文")
        lines.append("")

        # ── 世界主线 ──
        main_obj = getattr(world, "main_objective", "") or ""
        if main_obj:
            lines.append(f"### 世界主线")
            lines.append(main_obj)
            lines.append("")

        # ── 当前活跃角色 ──
        lines.append("### 活跃角色")
        for c in getattr(world, "characters", []):
            if not getattr(c, "alive", True):
                continue
            name = getattr(c, "name", "?")
            char_type = getattr(c, "char_type", "")
            char_type_str = str(char_type) if char_type else "NPC"
            faction = getattr(c, "faction_id", "") or "无"
            personality = getattr(c, "personality", "") or "未设定"
            goal = getattr(c, "goal", "") or "无"
            lines.append(f"- {name}（{char_type_str}）：势力={faction}，性格={personality}，目标={goal}")
        lines.append("")

        # ── 角色关系网 ──
        lines.append("### 角色关系网")
        if world_state.char_relations:
            for a, rels in world_state.char_relations.items():
                for b, rel in rels.items():
                    if a != b and rel != "中立":
                        lines.append(f"- {a} → {b}：{rel}")
        else:
            lines.append("（无特殊关系记录）")
        lines.append("")

        # ── 势力状态 ──
        lines.append("### 势力状态")
        factions = getattr(world, "factions", {})
        if factions:
            for fid, faction in factions.items():
                fname = getattr(faction, "name", fid) if hasattr(faction, "name") else str(faction)
                status = world_state.get_faction_status(fname)
                lines.append(f"- {fname}：{status}")
        lines.append("")

        # 势力间关系
        if world_state.faction_relations:
            lines.append("#### 势力关系")
            seen_pairs = set()
            for fa, rels in world_state.faction_relations.items():
                for fb, rel in rels.items():
                    pair = tuple(sorted([fa, fb]))
                    if pair not in seen_pairs and rel != "中立":
                        seen_pairs.add(pair)
                        lines.append(f"- {fa} ↔ {fb}：{rel}")
            lines.append("")

        # ── 地域环境 ──
        lines.append("### 地域环境")
        theme = getattr(world, "theme", "") or "未知"
        map_size = getattr(world, "map_size", (0, 0))
        lines.append(f"- 世界主题：{theme}，地图大小：{map_size[0]}x{map_size[1]}")
        lines.append("")

        # ── 上章摘要 ──
        if previous_summary:
            lines.append("### 上章摘要")
            lines.append(previous_summary.strip())
            lines.append("")

        # ── 本章基础事件 ──
        if resolution.base_events:
            lines.append("### 本章必然事件（来自世界时间线）")
            for e in resolution.base_events:
                lines.append(f"- {e}")
            lines.append("")

        # ── 本章分支提纲 ──
        if resolution.branch_outline:
            lines.append("### 本章情节提纲（来自时间树分支）")
            if resolution.matched_condition:
                lines.append(f"匹配条件：{resolution.matched_condition}")
            for item in resolution.branch_outline:
                lines.append(f"- {item}")
            lines.append("")

        # ── AI 指令 ──
        lines.append("### 叙事生成指引")
        lines.append(
            "根据以上世界状态和情节提纲，生成本章叙事方向。"
            "不要直接写死对话和动作，给出场景推进方向即可。"
            "描述本章将要发生的核心事件和冲突方向，要具体、有冲突感。"
        )
        lines.append("")

        return "\n".join(lines)

    # ─── 分支匹配逻辑 ───

    def _match_branches(self, branches: List[Dict], ws: WorldState) -> Optional[Dict]:
        """
        匹配条件分支，返回匹配分支的提纲和条件。

        返回值格式：
            {"outline": [...], "condition": "..."} 或 None

        规则：
        - 多个分支依次评估，取第一个匹配的非 default 分支
        - 如果没有非 default 分支匹配，走 default 分支
        - 如果多个非 default 分支都匹配，只取第一个（避免歧义）
        """
        default_branch = None

        for branch in branches:
            condition_str = branch.get("condition", "")
            parsed = _parse_condition(condition_str)

            if parsed.is_default:
                default_branch = branch
                continue

            if self._evaluate_condition(parsed, ws):
                logger.debug(f"[TimelineTree] 分支匹配: {condition_str}")
                return {
                    "outline": list(branch.get("outline", [])),
                    "condition": condition_str,
                }

        # 没有非 default 匹配，走 default
        if default_branch:
            logger.debug(f"[TimelineTree] 使用 default 分支")
            condition_str = default_branch.get("condition", "default")
            return {
                "outline": list(default_branch.get("outline", [])),
                "condition": condition_str,
            }

        return None

    def _evaluate_condition(self, cond: Condition, ws: WorldState) -> bool:
        """评估单个条件"""
        if cond.type == "char_relation":
            actual = ws.get_char_relation(cond.char_a, cond.char_b)
            return actual == cond.relation

        if cond.type == "char_alive":
            alive = ws.is_alive(cond.char_a)
            if cond.relation == "存活":
                return alive
            if cond.relation == "死亡":
                return not alive
            return False

        if cond.type == "faction_relation":
            actual = ws.get_faction_relation(cond.faction_a, cond.faction_b)
            return actual == cond.relation

        if cond.type == "faction_status":
            actual = ws.get_faction_status(cond.faction_a)
            return actual == cond.relation

        return False

    # ─── 碰撞事件 → 世界状态更新 ───

    def update_state_from_collisions(self, ws: WorldState, collision_events: List) -> WorldState:
        """
        根据碰撞历史自动更新世界状态。

        推断规则（基于碰撞类型）：
        - 感知对冲：双方互相了解 → char_relation 设为 "亲近"（初次相遇）或 "信任"（再次相遇）
        - 目标对冲：目标冲突 → char_relation 设为 "排斥"
        - 能力对冲：一方克制另一方 → char_relation 设为 "敌视"（A克制B → A敌视B）
        - 接近碰撞：仅靠拢，不改变关系

        势力关系更新：
        - 同势力角色碰撞视为势力内部事务，不影响势力间关系
        - 敌对势力角色碰撞 → 势力关系设为 "敌对"
        """
        for ev in collision_events:
            # 提取碰撞信息（兼容 CollisionEvent 和 dict 两种格式）
            if hasattr(ev, "collision_type"):
                ct = ev.collision_type
                ca = ev.char_a_name
                cb = ev.char_b_name
            else:
                ct = ev.get("collision_type", "")
                ca = ev.get("char_a_name", "")
                cb = ev.get("char_b_name", "")

            if not ca or not cb:
                continue

            # 感知对冲 → 互相了解
            if ct == "感知对冲":
                existing = ws.get_char_relation(ca, cb)
                if existing == "中立":
                    ws.set_char_relation(ca, cb, "亲近")
                    ws.set_char_relation(cb, ca, "亲近")

            # 目标对冲 → 排斥
            elif ct == "目标对冲":
                ws.set_char_relation(ca, cb, "排斥")
                ws.set_char_relation(cb, ca, "排斥")

            # 能力对冲 → 被克制方敌视克制方
            elif ct == "能力对冲":
                # 通过碰撞原因判断方向
                reason = ""
                if hasattr(ev, "collision_reason"):
                    reason = ev.collision_reason
                else:
                    reason = ev.get("collision_reason", "")
                # 简单判断：reason 中可能包含"克制"等关键词
                ws.set_char_relation(ca, cb, "排斥")
                ws.set_char_relation(cb, ca, "敌视")

            # 势力冲突 → 更新势力关系
            elif ct == "势力冲突":
                # 需要从碰撞中获取势力信息，此处做保守处理
                pass

        return ws

    # ─── 加载初始世界状态 ───

    def load_initial_state(self, characters: List, factions: List) -> WorldState:
        """
        从角色和势力列表加载初始世界状态。

        Args:
            characters: Character 对象列表
            factions: Faction 对象列表（dict 或 Faction）

        Returns:
            初始 WorldState
        """
        ws = WorldState()

        # 角色存活状态
        for char in characters:
            name = char.name if hasattr(char, "name") else char.get("name", "")
            if name:
                ws.set_alive(name, True)
                # 初始化自身关系
                ws.set_char_relation(name, name, "中立")

        # 势力状态
        for faction in factions:
            fname = faction.name if hasattr(faction, "name") else faction.get("name", "")
            if fname:
                ws.set_faction_status(fname, "活跃")

        # 势力关系（从 factions 配置中的 enemies/allies）
        for faction in factions:
            fname = faction.name if hasattr(faction, "name") else faction.get("name", "")
            enemies = []
            allies = []
            if hasattr(faction, "enemies"):
                enemies = faction.enemies
            elif isinstance(faction, dict):
                enemies = faction.get("enemies", [])
                allies = faction.get("allies", [])

            for e in enemies:
                ws.set_faction_relation(fname, e, "敌对")
            for a in allies:
                ws.set_faction_relation(fname, a, "同盟")

        return ws

    # ─── 统计与调试 ───

    def get_chapter_info(self, chapter: int) -> Optional[Dict]:
        """获取指定章节的配置信息（调试用）"""
        tree_chapter = self._get_tree_chapter(chapter)
        if tree_chapter is None and chapter not in self._base_timeline:
            return None

        result = {
            "chapter": chapter,
            "base_events": self._base_timeline.get(chapter, []),
            "branch_count": 0,
            "branches": [],
        }
        if tree_chapter:
            branches = tree_chapter.get("branches", [])
            result["branch_count"] = len(branches)
            result["branches"] = [
                {
                    "condition": b.get("condition", ""),
                    "outline_count": len(b.get("outline", [])),
                }
                for b in branches
            ]
        return result

    def get_stats(self) -> Dict:
        """返回统计信息"""
        tree_chapters = len(self._tree_config.get("timeline", []))
        total_branches = sum(
            len(ch.get("branches", []))
            for ch in self._tree_config.get("timeline", [])
        )
        return {
            "base_timeline_chapters": len(self._base_timeline),
            "tree_chapters": tree_chapters,
            "total_branches": total_branches,
            "project_root": self._project_root,
        }


# ======================== 条件解析器 ========================

def _parse_condition(text: str) -> Condition:
    """
    将条件字符串解析为 Condition 对象。

    支持的格式：
      - "default" → Condition(is_default=True)
      - "<角色A> <关系> <角色B>" → char_relation
      - "<角色A> 存活" 或 "<角色A> 死亡" → char_alive
      - "<势力A> <关系> <势力B>" → faction_relation
      - "<势力A> 活跃" 或 "<势力A> 覆灭" → faction_status
    """
    text = text.strip()

    # default
    if text == "default":
        return Condition(is_default=True)

    parts = text.split()

    # 尝试解析 <角色A> <关系词> <角色B>（三词格式）
    if len(parts) == 3 and parts[1] in CHAR_RELATIONS:
        return Condition(
            type="char_relation",
            char_a=parts[0],
            relation=parts[1],
            char_b=parts[2],
        )

    # 尝试 <角色A> 存活 / 死亡
    if len(parts) == 2 and parts[1] in ("存活", "死亡"):
        # 判断是角色还是势力：查势力状态表
        if parts[1] in ("活跃", "覆灭", "潜伏"):
            return Condition(
                type="faction_status",
                faction_a=parts[0],
                relation=parts[1],
            )
        return Condition(
            type="char_alive",
            char_a=parts[0],
            relation=parts[1],
        )

    # 尝试 <势力A> <关系词> <势力B>
    if len(parts) == 3 and parts[1] in FACTION_RELATIONS:
        return Condition(
            type="faction_relation",
            faction_a=parts[0],
            relation=parts[1],
            faction_b=parts[2],
        )

    # 尝试 <势力A> 活跃 / 覆灭
    if len(parts) == 2 and parts[1] in FACTION_STATUSES:
        return Condition(
            type="faction_status",
            faction_a=parts[0],
            relation=parts[1],
        )

    # 无法识别
    logger.warning(f"[TimelineTree] 无法解析条件: {text!r}")
    return Condition(is_default=True)
