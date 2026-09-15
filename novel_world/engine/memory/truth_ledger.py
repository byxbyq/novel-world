# -*- coding: utf-8 -*-
"""
Truth Ledger - 时间线 + 记忆上下文 + 伏笔管理
直接移植自书斋V65的 truth_ledger.json 持久化架构

核心数据结构：
- CharacterState: 角色状态快照（位置、心绪、健康、境界、持有物、关系、存活）
- TimelineEvent: 时间线事件（章节/事件/角色/地点/重要性）
- Foreshadowing: 伏笔全生命周期（planted→active→recovered/abandoned）
- ChapterLog: 章节日志（关键选择/代价/伏笔变化/角色变化/Strand线型）

附加系统：
- 追读力系统（0-100分）
- Strand Weave 三线节奏监控（Q/F/C）
"""
import json, os, time, threading
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional


@dataclass
class CharacterState:
    """角色状态快照 - 跨章节持久化"""
    name: str
    location: str = ""
    emotion: str = ""
    health: str = "正常"
    realm: str = ""               # 修炼等级/社会地位
    relationships: Dict[str, str] = field(default_factory=dict)
    possessions: List[str] = field(default_factory=list)
    secrets_known: List[str] = field(default_factory=list)
    last_seen_chapter: int = 0
    is_alive: bool = True
    arc_stage: str = ""           # 角色弧光阶段
    lifecycle_stage: str = "active"  # 生命周期阶段: "pending"(待激活), "active"(活跃), "sleeping"(休眠), "sealed"(封印), "dead"(死亡)
    entry_tick: int = 0           # 进入当前阶段的 tick
    exit_tick: int = 0            # 离开当前阶段的 tick（0=尚未离开）

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, data):
        return cls(**data)


@dataclass
class TimelineEvent:
    """时间线事件 - 记录谁在何时何地做了什么"""
    chapter: int
    event: str
    characters: List[str] = field(default_factory=list)
    location: str = ""
    time_marker: str = ""           # 时间标记：黎明/正午/黄昏/深夜
    importance: str = "normal"      # normal / important / critical
    event_type: str = "character"   # 事件类型: "world"(世界事件), "character"(角色事件), "collision"(碰撞事件)
    immutable: bool = False         # 不可变标记：世界事件默认不可被后续修改

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, data):
        return cls(**data)


@dataclass
class Foreshadowing:
    """伏笔 - 全生命周期管理"""
    id: str
    content: str
    planted_chapter: int
    planted_paragraph: str = ""
    expected_recovery_chapter: int = 0
    status: str = "planted"         # planted → active → recovered / abandoned
    related_characters: List[str] = field(default_factory=list)
    related_items: List[str] = field(default_factory=list)
    note: str = ""
    arc_type: str = ""              # short(2-3章) / medium(5-8章) / long(全书)
    strength: int = 2               # 悬念强度 1-5
    hook_type: str = ""             # 突然揭示/紧急危机/未完成动作/身份反转/两难选择/
                                    # 神秘线索/时间限制/承诺威胁/离奇消失/言外之意/
                                    # 意象钩子/回声钩子/留白钩子

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, data):
        return cls(**data)


@dataclass
class ChapterLog:
    """章节日志 - 每章记录"""
    chapter: int
    title: str = ""
    key_choices: List[str] = field(default_factory=list)
    costs: List[str] = field(default_factory=list)
    new_foreshadowing: List[str] = field(default_factory=list)
    resolved_foreshadowing: List[str] = field(default_factory=list)
    character_changes: Dict[str, dict] = field(default_factory=dict)
    strand_type: str = ""           # Q(Quest) / F(Fire) / C(Constellation)

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, data):
        return cls(**data)


class TruthLedger:
    """
    真相账本 — 跨章持久化唯一事实源
    
    每次AI生成叙事前，从TruthLedger提取角色当前状态、时间线、活跃伏笔
    生成后，把新事件/伏笔/状态变化写回TruthLedger
    """

    def __init__(self, project_dir: str):
        self.project_dir = project_dir
        self.character_states: Dict[str, CharacterState] = {}
        self.timeline: List[TimelineEvent] = []
        self.foreshadowing: List[Foreshadowing] = []
        self.chapter_logs: List[ChapterLog] = []
        self._dirty: bool = False
        self._save_timer: Optional[threading.Timer] = None
        self._debounce_interval: float = 0.5
        self._save_lock = threading.Lock()
        self._load()

    @property
    def _file(self):
        return os.path.join(self.project_dir, "truth_ledger.json")

    def _load(self):
        if os.path.exists(self._file):
            with open(self._file, 'r', encoding='utf-8') as f:
                d = json.load(f)
            self.character_states = {
                k: CharacterState(
                    name=v.get("name", k),
                    location=v.get("location", ""),
                    emotion=v.get("emotion", ""),
                    health=v.get("health", "正常"),
                    realm=v.get("realm", ""),
                    relationships=v.get("relationships", {}),
                    possessions=v.get("possessions", []),
                    secrets_known=v.get("secrets_known", []),
                    last_seen_chapter=v.get("last_seen_chapter", 0),
                    is_alive=v.get("is_alive", True),
                    arc_stage=v.get("arc_stage", ""),
                    lifecycle_stage=v.get("lifecycle_stage", "active"),
                    entry_tick=v.get("entry_tick", 0),
                    exit_tick=v.get("exit_tick", 0),
                )
                for k, v in d.get("character_states", {}).items()
            }
            self.timeline = [
                TimelineEvent(
                    chapter=e.get("chapter", 0),
                    event=e.get("event", ""),
                    characters=e.get("characters", []),
                    location=e.get("location", ""),
                    time_marker=e.get("time_marker", ""),
                    importance=e.get("importance", "normal"),
                    event_type=e.get("event_type", "character"),
                    immutable=e.get("immutable", False),
                )
                for e in d.get("timeline", [])
            ]
            self.foreshadowing = [
                Foreshadowing(**h)
                for h in d.get("foreshadowing", [])
            ]
            self.chapter_logs = [
                ChapterLog(**log)
                for log in d.get("chapter_logs", [])
            ]

    def save(self):
        """标记脏数据并调度延迟写入（防抖）"""
        self._dirty = True
        with self._save_lock:
            if self._save_timer is not None:
                self._save_timer.cancel()
            self._save_timer = threading.Timer(
                self._debounce_interval, self._do_save
            )
            self._save_timer.daemon = True
            self._save_timer.start()

    def _do_save(self):
        with self._save_lock:
            if not self._dirty:
                return
            os.makedirs(self.project_dir, exist_ok=True)
            with open(self._file, 'w', encoding='utf-8') as f:
                json.dump({
                    "character_states": {
                        k: asdict(v) for k, v in self.character_states.items()
                    },
                    "timeline": [asdict(e) for e in self.timeline],
                    "foreshadowing": [asdict(h) for h in self.foreshadowing],
                    "chapter_logs": [asdict(log) for log in self.chapter_logs],
                    "updated": time.strftime("%Y-%m-%d %H:%M")
                }, f, ensure_ascii=False, indent=2)
            self._dirty = False
            self._save_timer = None

    def flush(self):
        """立即写入磁盘"""
        with self._save_lock:
            if self._save_timer is not None:
                self._save_timer.cancel()
                self._save_timer = None
        if self._dirty:
            self._do_save()

    def close(self):
        self.flush()

    # ─── 角色状态 ───

    def ensure_character(self, name: str):
        if name not in self.character_states:
            self.character_states[name] = CharacterState(name=name)

    def update_character(self, name: str, chapter: int = 0, **kwargs):
        self.ensure_character(name)
        cs = self.character_states[name]
        # 检测生命周期阶段变更
        new_lifecycle = kwargs.get("lifecycle_stage")
        if new_lifecycle and new_lifecycle != cs.lifecycle_stage:
            cs.exit_tick = kwargs.get("_tick", 0)  # 离开旧阶段的 tick
            cs.lifecycle_stage = new_lifecycle
            cs.entry_tick = kwargs.get("_tick", 0)  # 进入新阶段的 tick
            kwargs = {k: v for k, v in kwargs.items() if k != "_tick"}
        for k, v in kwargs.items():
            if k == "lifecycle_stage":
                # 已在上面处理
                continue
            if hasattr(cs, k):
                cur = getattr(cs, k)
                if isinstance(cur, list):
                    if isinstance(v, str):
                        cur.append(v)
                    elif isinstance(v, list):
                        cur.extend(v)
                elif isinstance(cur, dict) and isinstance(v, dict):
                    cur.update(v)
                else:
                    setattr(cs, k, v)
        if chapter > 0:
            cs.last_seen_chapter = max(cs.last_seen_chapter, chapter)
        self.save()

    def get_character_summary(self, name: str = None) -> str:
        if name:
            cs = self.character_states.get(name)
            if not cs:
                return f"{name}: 无记录"
            items = ", ".join(cs.possessions) if cs.possessions else "无"
            rels = ", ".join(
                f"{k}({v})" for k, v in cs.relationships.items()
            ) if cs.relationships else "无"
            return (
                f"{name}: 位置[{cs.location}] 心绪[{cs.emotion}] "
                f"健康[{cs.health}] 境界[{cs.realm}] 持有[{items}] "
                f"关系[{rels}] 存活[{cs.is_alive}]"
            )
        lines = []
        for n, cs in self.character_states.items():
            lines.append(self.get_character_summary(n))
        return "\n".join(lines)

    # ─── 时间线 ───

    def add_event(self, chapter: int, event: str, **kwargs):
        ev = TimelineEvent(chapter=chapter, event=event, **kwargs)
        self.timeline.append(ev)
        self.save()

    def get_timeline(self, chapter: int = None, recent: int = 10) -> str:
        events = self.timeline
        if chapter is not None:
            events = [e for e in events if e.chapter == chapter]
        if not events:
            return "无时间线记录"
        events = events[-recent:] if recent > 0 else events
        return "\n".join(
            f"[第{e.chapter}章] {e.time_marker} {e.location}: {e.event}"
            for e in events
        )

    # ─── 伏笔 ───

    def add_hook(self, content: str, planted_chapter: int, **kwargs) -> str:
        hid = f"hook_{planted_chapter:03d}_{len(self.foreshadowing)+1:02d}"
        hook = Foreshadowing(
            id=hid, content=content,
            planted_chapter=planted_chapter, **kwargs
        )
        self.foreshadowing.append(hook)
        self.save()
        return hid

    def activate_hook(self, hook_id: str):
        for h in self.foreshadowing:
            if h.id == hook_id and h.status == "planted":
                h.status = "active"
                self.save()
                return True
        return False

    def recover_hook(self, hook_id: str, chapter: int) -> bool:
        for h in self.foreshadowing:
            if h.id == hook_id:
                h.status = "recovered"
                self.save()
                return True
        return False

    def abandon_hook(self, hook_id: str, reason: str = "") -> bool:
        for h in self.foreshadowing:
            if h.id == hook_id:
                h.status = "abandoned"
                h.note = reason
                self.save()
                return True
        return False

    def get_active_hooks(self) -> List[Foreshadowing]:
        return [h for h in self.foreshadowing
                if h.status in ("planted", "active")]

    def get_overdue_hooks(self, current_chapter: int) -> List[Foreshadowing]:
        return [
            h for h in self.get_active_hooks()
            if h.expected_recovery_chapter
            and current_chapter > h.expected_recovery_chapter
        ]

    # ─── 章节日志 ───

    def log_chapter(self, chapter: int, title: str = "", **kwargs):
        log = ChapterLog(chapter=chapter, title=title, **kwargs)
        self.chapter_logs.append(log)
        self.save()

    # ─── 构建AI Prompt上下文 ───

    def build_context(
        self,
        current_chapter: int,
        relevant_characters: List[str] = None,
        limit_foreshadowing: int = 0,
        skip_timeline: bool = False
    ) -> str:
        """
        构建给AI的上下文字符串
        
        Args:
            current_chapter: 当前章节号
            relevant_characters: 需要关注的角色名列表
            limit_foreshadowing: 0=不限，>0=只取最近N个活跃伏笔
            skip_timeline: 是否跳过时间线
        
        Returns:
            格式化上下文字符串
        """
        parts = []

        # 角色当前状态
        if relevant_characters:
            char_texts = []
            for name in relevant_characters:
                if name in self.character_states:
                    cs = self.character_states[name]
                    items = ", ".join(cs.possessions) if cs.possessions else "无"
                    char_texts.append(
                        f"【{name}】位置:{cs.location} | 心绪:{cs.emotion} | "
                        f"健康:{cs.health} | 境界:{cs.realm} | "
                        f"持有:{items} | 最后出现:第{cs.last_seen_chapter}章"
                    )
            if char_texts:
                parts.append("## 角色当前状态\n" + "\n".join(char_texts))

        # 待回收伏笔
        active = self.get_active_hooks()
        if active:
            if limit_foreshadowing > 0 and len(active) > limit_foreshadowing:
                active = active[-limit_foreshadowing:]
                label = (
                    f"## 待回收伏笔（最近{limit_foreshadowing}个，"
                    f"共{len(self.get_active_hooks())}个）"
                )
            else:
                label = f"## 待回收伏笔（{len(active)}个）"
            hooks_text = "\n".join(
                f"- [{h.id}] (埋于第{h.planted_chapter}章): {h.content}"
                for h in active
            )
            parts.append(f"{label}\n{hooks_text}")

        # 近期时间线
        if not skip_timeline:
            recent = [
                e for e in self.timeline
                if current_chapter - e.chapter <= 3
            ]
            if recent:
                parts.append(
                    "## 近期时间线\n" + "\n".join(
                        f"- 第{e.chapter}章: {e.event}"
                        for e in recent[-10:]
                    )
                )

        return "\n\n".join(parts) if parts else ""

    # ─── 扩展：世界事件与碰撞事件 ───

    def add_world_event(self, chapter: int, event: str, tick: int = 0, **kwargs):
        """
        添加世界事件 - 不可变的时间线事件
        世界事件是全局性的、不可被后续叙事修改的基础事实
        """
        kwargs["event_type"] = "world"
        kwargs["immutable"] = True
        ev = TimelineEvent(chapter=chapter, event=event, **kwargs)
        self.timeline.append(ev)
        self.save()
        return ev

    def add_collision_event(self, chapter: int, event: str,
                            characters: List[str] = None, **kwargs):
        """
        添加碰撞事件 - 角色碰撞产生的时间线事件
        碰撞事件由六轴图的碰撞检测触发
        """
        kwargs["event_type"] = "collision"
        kwargs["importance"] = kwargs.get("importance", "critical")
        ev = TimelineEvent(
            chapter=chapter, event=event,
            characters=characters or [], **kwargs
        )
        self.timeline.append(ev)
        self.save()
        return ev

    # ─── 扩展：角色生命周期管理 ───

    def seal_character(self, name: str, tick: int = 0):
        """
        封印角色 - 角色暂时退出叙事，不可被引用
        """
        self.ensure_character(name)
        self.update_character(
            name, lifecycle_stage="sealed", _tick=tick
        )

    def awaken_character(self, name: str, tick: int = 0):
        """
        唤醒角色 - 从封印或休眠中恢复
        """
        self.ensure_character(name)
        self.update_character(
            name, lifecycle_stage="active", _tick=tick
        )

    def get_active_characters(self) -> Dict[str, CharacterState]:
        """
        获取所有活跃状态的角色
        活跃 = lifecycle_stage 为 "active" 且 is_alive 为 True
        """
        return {
            name: cs for name, cs in self.character_states.items()
            if cs.lifecycle_stage == "active" and cs.is_alive
        }

        # ─── 统计 ───

    def get_stats(self) -> dict:
        # 统计事件类型分布
        event_type_counts = {}
        for e in self.timeline:
            et = getattr(e, "event_type", "character")
            event_type_counts[et] = event_type_counts.get(et, 0) + 1
        # 统计生命周期分布
        lifecycle_counts = {}
        for cs in self.character_states.values():
            ls = getattr(cs, "lifecycle_stage", "active")
            lifecycle_counts[ls] = lifecycle_counts.get(ls, 0) + 1
        return {
            "characters": len(self.character_states),
            "active_characters": len(self.get_active_characters()),
            "timeline_events": len(self.timeline),
            "event_type_distribution": event_type_counts,
            "lifecycle_distribution": lifecycle_counts,
            "active_hooks": len(self.get_active_hooks()),
            "recovered_hooks": len([
                h for h in self.foreshadowing if h.status == "recovered"
            ]),
            "abandoned_hooks": len([
                h for h in self.foreshadowing if h.status == "abandoned"
            ]),
            "chapters_logged": len(self.chapter_logs),
        }

    # ─── 追读力系统 ───

    def get_read_pull(self, current_chapter: int = 0) -> dict:
        active = self.get_active_hooks()
        if not active:
            return {
                "score": 0, "level": "empty",
                "summary": "无开放悬念，追读力为零",
                "active_count": 0
            }

        count_score = min(30, len(active) * 5)
        total_strength = sum(h.strength for h in active)
        max_strength = len(active) * 5
        strength_ratio = total_strength / max_strength if max_strength > 0 else 0
        strength_score = round(strength_ratio * 30)

        arc_types = set(h.arc_type for h in active if h.arc_type)
        arc_score = len(arc_types) * 7

        imminent_score = 0
        for h in active:
            if h.expected_recovery_chapter and h.expected_recovery_chapter > 0:
                gap = h.expected_recovery_chapter - current_chapter
                if gap <= 0:
                    imminent_score += 8
                elif gap <= 2:
                    imminent_score += 6
                elif gap <= 5:
                    imminent_score += 3
        imminent_score = min(20, imminent_score)

        total = min(100, count_score + strength_score + arc_score + imminent_score)

        if total >= 70:
            level, desc = "strong", "追读力强劲"
        elif total >= 40:
            level, desc = "moderate", "追读力适中"
        elif total >= 20:
            level, desc = "weak", "追读力偏弱"
        else:
            level, desc = "empty", "追读力不足"

        arc_distribution = {"short": 0, "medium": 0, "long": 0, "untyped": 0}
        strength_distribution = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
        for h in active:
            arc_distribution[h.arc_type or "untyped"] = (
                arc_distribution.get(h.arc_type or "untyped", 0) + 1
            )
            s = max(1, min(5, h.strength))
            strength_distribution[s] = strength_distribution.get(s, 0) + 1

        warnings = []
        if not arc_types:
            warnings.append("未设置悬念弧线类型")
        if len(arc_types) == 1:
            warnings.append(f"仅{list(arc_types)[0]}弧线在运行")
        if len(active) > 0 and total_strength / len(active) < 2:
            warnings.append("悬念强度偏低")

        summary = (
            f"追读力: {total}/100 ({desc}) | "
            f"开放悬念{len(active)}个 | "
            f"强度分{strength_score}/30 | "
            f"弧线分{arc_score}/21"
        )

        return {
            "score": total, "level": level, "summary": summary,
            "active_count": len(active),
            "count_score": count_score,
            "strength_score": strength_score,
            "arc_score": min(21, arc_score),
            "imminent_score": imminent_score,
            "arc_distribution": arc_distribution,
            "strength_distribution": strength_distribution,
            "warnings": warnings,
        }

    # ─── Strand Weave 节奏系统 ───

    def get_strand_stats(self, current_chapter: int = 0) -> dict:
        if not self.chapter_logs:
            return {
                "total": 0,
                "distribution": {"Q": 0, "F": 0, "C": 0, "untyped": 0},
                "percentages": {},
                "red_lines": [],
                "summary": "无章节记录"
            }

        distribution = {"Q": 0, "F": 0, "C": 0, "untyped": 0}
        strand_sequence = []
        for log in self.chapter_logs:
            st = log.strand_type.upper() if log.strand_type else ""
            if st in ("Q", "F", "C"):
                distribution[st] += 1
                strand_sequence.append(st)
            else:
                distribution["untyped"] += 1
                strand_sequence.append("")

        total = len(self.chapter_logs)
        typed = total - distribution["untyped"]
        percentages = {}
        if typed > 0:
            percentages = {
                "Q": round(distribution["Q"] / typed * 100),
                "F": round(distribution["F"] / typed * 100),
                "C": round(distribution["C"] / typed * 100),
            }

        # 红线检查
        red_lines = []

        consecutive_q = 0
        max_consecutive_q = 0
        for s in strand_sequence:
            if s == "Q":
                consecutive_q += 1
                max_consecutive_q = max(max_consecutive_q, consecutive_q)
            else:
                consecutive_q = 0
        if max_consecutive_q > 5:
            red_lines.append(
                f"Quest线连续{max_consecutive_q}章，超过5章红线"
            )

        last_fire_idx = -1
        max_fire_gap = 0
        for i, s in enumerate(strand_sequence):
            if s == "F":
                if last_fire_idx >= 0:
                    gap = i - last_fire_idx - 1
                    max_fire_gap = max(max_fire_gap, gap)
                last_fire_idx = i
        if last_fire_idx >= 0:
            gap_to_current = len(strand_sequence) - 1 - last_fire_idx
            max_fire_gap = max(max_fire_gap, gap_to_current)
        if max_fire_gap > 10:
            red_lines.append(
                f"Fire线断档{max_fire_gap}章，超过10章红线"
            )

        last_c_idx = -1
        max_c_gap = 0
        for i, s in enumerate(strand_sequence):
            if s == "C":
                if last_c_idx >= 0:
                    gap = i - last_c_idx - 1
                    max_c_gap = max(max_c_gap, gap)
                last_c_idx = i
        if last_c_idx >= 0:
            gap_to_current = len(strand_sequence) - 1 - last_c_idx
            max_c_gap = max(max_c_gap, gap_to_current)
        if max_c_gap > 15:
            red_lines.append(
                f"Constellation线断档{max_c_gap}章，超过15章红线"
            )

        target = {"Q": 60, "F": 20, "C": 20}
        deviations = {}
        for k in ("Q", "F", "C"):
            if k in percentages:
                dev = percentages[k] - target[k]
                if abs(dev) > 15:
                    deviations[k] = dev

        summary_parts = [
            f"Strand分布: Q={percentages.get('Q',0)}% "
            f"F={percentages.get('F',0)}% C={percentages.get('C',0)}%"
        ]
        if red_lines:
            summary_parts.append(f"红线告警{len(red_lines)}条")
        if deviations:
            summary_parts.append(
                "比例偏离: " + ", ".join(
                    k + ('+' if v > 0 else '') + str(v) + '%'
                    for k, v in deviations.items()
                )
            )

        return {
            "total": total, "typed": typed,
            "distribution": distribution,
            "percentages": percentages,
            "target": target,
            "deviations": deviations,
            "red_lines": red_lines,
            "strand_sequence": strand_sequence,
            "summary": " | ".join(summary_parts),
        }


# ─── 便捷工厂函数 ───

def get_truth_ledger(project_dir: str) -> TruthLedger:
    """获取或创建TruthLedger实例"""
    return TruthLedger(project_dir)
