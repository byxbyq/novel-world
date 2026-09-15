"""
理论心智层（Theory of Mind）
源自 FictionForge v0.2.0 核心创新。

每个 tick 结束后，引擎维护一个全角色互推的真值表：
- 哪些角色知道某个事实？
- 哪些角色以为别人不知道？
- 秘密浮出水面的临界点（Type-A 检测）？

适用场景：
- 后处理模块在渲染叙事前读取真值表，生成"信息差"标注
- 引擎合成器根据角色知识快照决定其行动/意图

FictionForge 原始作者：FictionForge 项目
适配者：小说世界 Phase 3 模块移植
"""

from __future__ import annotations

import json
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    # 小说世界内部引用（适配路径）
    pass


# ── 数据模型 ──────────────────────────────────────────────────────────────

@dataclass
class Fact:
    """单个事实条目。
    
    含义：fact_id 标识的事实，known_by 中的角色知道它，
    known_by_holding 中的角色持有但尚未被其他人感知，unknown_to 为明确不知情的角色。
    """
    fact_id: str
    description: str                           # 可读描述
    known_by: set[str] = field(default_factory=set)
    known_by_holding: set[str] = field(default_factory=set)  # 持有但未被感知
    unknown_to: set[str] = field(default_factory=set)
    source: str = ""                           # 来源：角色名/事件名
    importance: float = 1.0                    # 核心度 0~1
    age: int = 0                               # 存在 tick 数
    tags: list[str] = field(default_factory=list)
    
    # 叙事标注
    annotation: str = ""                       # 如 "角色A不知道B知道的事"
    annotator: str = ""                        # 由哪个函数生成的标注

    def clone(self) -> "Fact":
        """深拷贝（集合内容重新创建）。"""
        return Fact(
            fact_id=self.fact_id,
            description=self.description,
            known_by=set(self.known_by),
            known_by_holding=set(self.known_by_holding),
            unknown_to=set(self.unknown_to),
            source=self.source,
            importance=self.importance,
            age=self.age,
            tags=list(self.tags),
            annotation=self.annotation,
            annotator=self.annotator,
        )


@dataclass
class KnowledgeSnapshot:
    """从当前真值表提取的角色知识快照。
    
    known: 该角色确实知道的事实的 ID 集合
    unknown: 该角色不知道的事实的 ID 集合
    holding: 该角色持有但别人尚未感知的事实的 ID 集合
    secret_to: 该角色对某人隐瞒的事实的 ID → 目标角色名 映射
    """
    character: str
    known: set[str] = field(default_factory=set)
    unknown: set[str] = field(default_factory=set)
    holding: set[str] = field(default_factory=set)
    secret_to: dict[str, set[str]] = field(default_factory=dict)  # target_char → {fact_ids}
    timestamp: float = 0.0


@dataclass
class TruthTable:
    """全角色知识真值表。
    
    索引：
        facts[fact_id] → Fact
        by_char[char_name] → { "known": {fact_ids}, "unknown": {fact_ids} }
    """
    facts: dict[str, Fact] = field(default_factory=dict)
    
    def register(self, fact_id: str, description: str, source: str = "",
                 known_by: Optional[list[str]] = None,
                 unknown_to: Optional[list[str]] = None,
                 importance: float = 1.0,
                 tags: Optional[list[str]] = None) -> Fact:
        """注册一个新事实，若 fact_id 已存在则更新 known_by / unknown_to。"""
        if fact_id in self.facts:
            f = self.facts[fact_id]
            if known_by:
                f.known_by.update(known_by)
            if unknown_to:
                f.unknown_to.update(unknown_to)
            return f
        f = Fact(
            fact_id=fact_id,
            description=description,
            known_by=set(known_by or []),
            unknown_to=set(unknown_to or []),
            source=source,
            importance=importance,
            tags=tags or [],
        )
        self.facts[fact_id] = f
        return f

    def update_knowledge(self, fact_id: str, newly_known_by: list[str]) -> None:
        """原子更新：将一批角色加入某事实的 known_by。"""
        if fact_id not in self.facts:
            return
        f = self.facts[fact_id]
        for c in newly_known_by:
            f.known_by.add(c)
            f.unknown_to.discard(c)

    def snapshot_for(self, character: str) -> KnowledgeSnapshot:
        """提取单个角色的知识快照。"""
        known: set[str] = set()
        unknown: set[str] = set()
        holding: set[str] = set()
        secret_to: dict[str, set[str]] = defaultdict(set)

        for fid, fact in self.facts.items():
            if character in fact.known_by or character in fact.known_by_holding:
                known.add(fid)
            else:
                unknown.add(fid)
            if character in fact.known_by_holding:
                holding.add(fid)
            # 该角色知道但某个 target 不知道 → secret_to
            if character in fact.known_by:
                for target in fact.unknown_to:
                    if target != character:
                        secret_to[target].add(fid)

        return KnowledgeSnapshot(
            character=character,
            known=known,
            unknown=unknown,
            holding=holding,
            secret_to=dict(secret_to),
            timestamp=time.time(),
        )

    def all_snapshots(self, character_names: list[str]) -> dict[str, KnowledgeSnapshot]:
        """批量提取所有角色的知识快照。"""
        return {name: self.snapshot_for(name) for name in character_names}

    def age_all_facts(self, delta: int = 1) -> None:
        """所有事实 age += delta。"""
        for f in self.facts.values():
            f.age += delta

    def to_dict(self) -> dict:
        """序列化（用于存档）。"""
        def _set(s): return sorted(list(s)) if s else []
        return {
            fid: {
                "fact_id": f.fact_id,
                "description": f.description,
                "known_by": _set(f.known_by),
                "known_by_holding": _set(f.known_by_holding),
                "unknown_to": _set(f.unknown_to),
                "source": f.source,
                "importance": f.importance,
                "age": f.age,
                "tags": f.tags,
                "annotation": f.annotation,
                "annotator": f.annotator,
            }
            for fid, f in self.facts.items()
        }

    @classmethod
    def from_dict(cls, data: dict) -> "TruthTable":
        """反序列化。"""
        tt = cls()
        for fid, d in data.items():
            tt.facts[fid] = Fact(
                fact_id=d["fact_id"],
                description=d["description"],
                known_by=set(d.get("known_by", [])),
                known_by_holding=set(d.get("known_by_holding", [])),
                unknown_to=set(d.get("unknown_to", [])),
                source=d.get("source", ""),
                importance=d.get("importance", 1.0),
                age=d.get("age", 0),
                tags=d.get("tags", []),
                annotation=d.get("annotation", ""),
                annotator=d.get("annotator", ""),
            )
        return tt


# ── 知识传播函数 ──────────────────────────────────────────────────────────

def propagate_tom_all(
    truth_table: TruthTable,
    events: list[dict],
    characters: list[str],
    relations: Optional[dict] = None,
) -> TruthTable:
    """
    全角色知识传播（每个 tick 结束调用）。

    传播规则：
    1. 事件目击者 → known_by 新增（事件中的角色/地点目击者）
    2. 推定获取：如果 A 和 B 通信/共处，A 已知的事实标记 B 为"可能获取"
    3. known_by_holding → known_by 转移（持有→公开）

    Args:
        truth_table: 当前真值表
        events: 本轮世界事件列表，每个含 {"type": str, "characters": [...], "description": str, "fact_id": str}
        characters: 全部角色名列表
        relations: 角色关系（{"A": {"B": {"type": "friend", "trust": 0.8}}, ...}），可选

    Returns:
        更新后的 truth_table（原地修改 + 返回）
    """
    # 1. 事件目击者注册
    for ev in events:
        fid = ev.get("fact_id", "")
        desc = ev.get("description", "")
        chars = ev.get("characters", [])
        ev_type = ev.get("type", "")
        if not fid:
            fid = f"event_{len(truth_table.facts)}_{ev_type}"

        if fid not in truth_table.facts:
            truth_table.register(
                fact_id=fid,
                description=f"事件: {desc}",
                source="event",
                importance=0.7,
                tags=[ev_type, "event"],
            )
        truth_table.update_knowledge(fid, chars)
        # 目击者也标记为持有
        fact = truth_table.facts[fid]
        for c in chars:
            fact.known_by_holding.add(c)

    # 2. 通信推定：如果 role_pair 在一起/通信，推定知识交换
    if relations:
        for a in characters:
            for b in characters:
                if a >= b:
                    continue
                rel = (relations.get(a, {}).get(b) or relations.get(b, {}).get(a) or {})
                trust = rel.get("trust", 0)
                if trust >= 0.6:  # 高信任 → 推定知识共享
                    for fid, fact in truth_table.facts.items():
                        if a in fact.known_by and b not in fact.known_by:
                            fact.known_by.add(b)
                        elif b in fact.known_by and a not in fact.known_by:
                            fact.known_by.add(a)

    # 3. 年龄递增
    truth_table.age_all_facts(1)

    return truth_table


# ── Type-A 检测 ───────────────────────────────────────────────────────────

def detect_type_a(truth_table: TruthTable, character: str) -> list[tuple[str, str, str]]:
    """
    检测是否有角色即将发现「秘密」（Type-A 转变触发）。

    Type-A 转变定义：
    - 该角色 unknown 的事实中，若某事实的 importance >= 0.8 且
    - known_by 中已包含其高信任关联者 → 触发"接近发现"标记

    Returns:
        list of (fact_id, description, "即将揭晓还是尚远？")
    """
    alerts: list[tuple[str, str, str]] = []

    snapshot = truth_table.snapshot_for(character)

    for fid in snapshot.unknown:
        fact = truth_table.facts.get(fid)
        if not fact or fact.importance < 0.6:
            continue
        # 检查 known_by 中是否有高信任伙伴
        who_knows = fact.known_by - {character}
        if who_knows:
            if fact.importance >= 0.8:
                alerts.append((fid, fact.description, f"即将揭晓 — 已知者: {', '.join(sorted(who_knows))}"))
            else:
                alerts.append((fid, fact.description, "线索浮现 — 尚需更多信息"))

    return alerts


# ── 叙事标注 ──────────────────────────────────────────────────────────────

def annotate_spec(truth_table: TruthTable, characters: list[str]) -> TruthTable:
    """
    由真值表生成叙事标注，填入每个 Fact 的 annotation 字段。

    标注规则（语言风格：信息差叙事）：
    - "X 不知道 Y 知道 Z" → 信息差
    - "X 以为 Y 不知道 Z" → 误判
    - "全员已知" → 公共知识

    Returns:
        更新后的 truth_table（原地修改 + 返回）
    """
    for fid, fact in truth_table.facts.items():
        annotations: list[str] = []
        # 找出信息差
        for c in characters:
            if c in fact.known_by:
                # 该角色知道的事实，有哪些人不知道？
                for u in fact.unknown_to:
                    if u != c and u in characters:
                        annotations.append(f"{c}知道{u}不知道：{fact.description[:30]}")

        if not annotations:
            if len(fact.known_by) >= len(characters) * 0.8:
                annotations.append("（公共知识）")
            elif fact.known_by:
                annotations.append(f"（{', '.join(sorted(fact.known_by))}已知）")

        fact.annotation = " | ".join(annotations[:3]) if annotations else ""
        fact.annotator = "annotate_spec"

    return truth_table


def render_info_gaps(truth_table: TruthTable, pov_character: str, max_lines: int = 8) -> str:
    """
    为叙事渲染信息差提示（供 NarrativeEngine 或后处理模块使用）。

    Args:
        truth_table: 当前真值表
        pov_character: POV 角色名
        max_lines: 最多输出行数

    Returns:
        信息差提示字符串（嵌入叙事提示中）
    """
    snapshot = truth_table.snapshot_for(pov_character)
    lines: list[str] = []

    # 该角色不知道的高重要性事实
    important_unknown = [
        fid for fid in snapshot.unknown
        if truth_table.facts.get(fid) and truth_table.facts[fid].importance >= 0.5
    ]
    important_unknown.sort(key=lambda fid: truth_table.facts[fid].importance, reverse=True)

    for i, fid in enumerate(important_unknown[:max_lines]):
        fact = truth_table.facts[fid]
        who_knows = sorted(fact.known_by - {pov_character})
        if who_knows:
            lines.append(f"- {pov_character} 不知道「{fact.description[:50]}」（{', '.join(who_knows)}已知）")

    # 该角色对别人隐瞒的事实
    for target, fid_set in snapshot.secret_to.items():
        for fid in list(fid_set)[:2]:
            if len(lines) >= max_lines:
                break
            fact = truth_table.facts.get(fid)
            if fact:
                lines.append(f"- {pov_character} 对 {target} 隐瞒「{fact.description[:50]}」")

    if not lines:
        return "（{pov_character} 的知识状态与公共信息一致）"

    return "\n".join(lines)


# ── Class I / Class II 转变检测 ─────────────────────────────────────────

def detect_class_i(truth_table: TruthTable, character: str, 
                   belief_system: Optional[dict] = None) -> list[str]:
    """
    检测角色是否即将经历 Class I 转变（内心信念/认知转变）。
    当角色未知的高重要性事实积累到临界点。

    Args:
        truth_table: 当前真值表
        character: 角色名
        belief_system: 角色信念系统（可选），{belief_id: {confidence, ...}}

    Returns:
        list of 转变提示字符串
    """
    alerts = detect_type_a(truth_table, character)
    critical_alerts = [a for a in alerts if "即将揭晓" in a[2]]
    
    hints = []
    if len(critical_alerts) >= 2:
        hints.append(f"{character}可能经历内心信念转变（多个关键事实即将揭晓）")
    if belief_system:
        for bid, bdata in belief_system.items():
            if bdata.get("confidence", 1.0) < 0.3:
                hints.append(f"{character}的信念「{bid}」已薄弱，接近推翻")
    return hints


def detect_class_ii(truth_table: TruthTable, char_a: str, char_b: str) -> list[str]:
    """
    检测两个角色间是否接近 Class II 转变（关系性质转变）。
    当双方互相隐瞒/误解的高重要性事实达到临界。

    Returns:
        list of 关系转变提示
    """
    snap_a = truth_table.snapshot_for(char_a)
    snap_b = truth_table.snapshot_for(char_b)

    hints = []

    # 互相隐瞒
    a_secrets_for_b = snap_a.secret_to.get(char_b, set())
    b_secrets_for_a = snap_b.secret_to.get(char_a, set())
    if a_secrets_for_b and b_secrets_for_a:
        hints.append(f"{char_a} 与 {char_b} 互相隐瞒关键信息，关系可能剧变")

    # 信息不对称
    a_known_not_b = snap_a.known - snap_b.known
    b_known_not_a = snap_b.known - snap_a.known
    high_impact_asym = 0
    for fid in a_known_not_b | b_known_not_a:
        if truth_table.facts.get(fid) and truth_table.facts[fid].importance >= 0.7:
            high_impact_asym += 1
    if high_impact_asym >= 2:
        hints.append(f"{char_a} 与 {char_b} 存在严重信息不对称（{high_impact_asym}个高影响事实）")

    return hints
