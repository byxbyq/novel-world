# -*- coding: utf-8 -*-
"""
小说世界 - TruthLedger 增强模块
从书斋V66 backend/ledger.py 移植增强特征

在现有 TruthLedger 基础上新增：
- Artifact（道具/功法设定）— 物品全生命周期追踪
- Faction（势力/组织设定）— 势力关系管理
- Location（地点设定）— 空间追踪
- SubplotState（支线追踪）— 独立支线状态机
- Snapshot（叙事快照）— 全书剧情节点完整备份
- 角色归档/取消归档（archived 标志）
- 支线上下文构建（get_subplot_context）
- 审计反馈存储（dynamic AI-flavor avoidance guiding）
- 校验警告历史

使用方式：
    from novel_world.engine.memory.truth_ledger import TruthLedger
    from novel_world.engine.memory.truth_ledger_enhanced import (
        Artifact, Faction, Location, SubplotState, Snapshot,
        LedgerEnhancer, enhance_ledger
    )

    ledger = TruthLedger(project_dir)
    enhancer = LedgerEnhancer(ledger)
    enhancer.register_subplot("支线名称", description="描述", start_chapter=5)
"""

import json
import os
import time
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional


# ============================================================
# 新增数据类
# ============================================================

@dataclass
class Artifact:
    """道具/功法设定

    从书斋V66移植：物品全生命周期追踪（创建→易主→损毁）
    """
    id: str
    name: str
    type: str = ""              # weapon / pill / technique / treasure / misc
    grade: str = ""             # 品级：凡/灵/仙/神/圣
    owner: str = ""             # 当前持有者
    description: str = ""
    created_at: str = ""        # 创建章节/时间
    destroyed: bool = False

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Artifact":
        return cls(**{k: v for k, v in data.items() if k in {
            "id", "name", "type", "grade", "owner",
            "description", "created_at", "destroyed"
        }})


@dataclass
class Faction:
    """势力/组织设定

    从书斋V66移植：宗门/家族/王朝关系管理
    """
    id: str
    name: str
    type: str = ""              # 宗门/家族/王朝/帮派/散修联盟
    leader: str = ""
    members: List[str] = field(default_factory=list)
    description: str = ""
    status: str = "active"      # active / disbanded / destroyed

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Faction":
        return cls(**{k: v for k, v in data.items() if k in {
            "id", "name", "type", "leader", "members",
            "description", "status"
        }})


@dataclass
class Location:
    """地点设定

    从书斋V66移植：空间追踪 + 势力归属
    """
    id: str
    name: str
    type: str = ""              # city / mountain / sect / cave / misc
    description: str = ""
    first_seen_chapter: int = 0
    faction: str = ""           # 所属势力

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Location":
        return cls(**{k: v for k, v in data.items() if k in {
            "id", "name", "type", "description",
            "first_seen_chapter", "faction"
        }})


@dataclass
class SubplotState:
    """支线追踪状态 — 独立于主线的支线剧情追踪

    从书斋V66移植：支线状态机 + 裁剪优先级
    状态机: dormant → active → advancing → resolved / abandoned
    """
    id: str
    title: str
    description: str = ""
    status: str = "dormant"             # dormant / active / advancing / resolved / abandoned
    start_chapter: int = 0
    last_progress_chapter: int = 0
    resolve_chapter: int = 0
    related_characters: List[str] = field(default_factory=list)
    related_locations: List[str] = field(default_factory=list)
    key_events: List[str] = field(default_factory=list)
    priority: int = 2                   # 1(高,主线关联) 2(中) 3(低)
    target_chapter: int = 0             # 预期解决章节
    note: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "SubplotState":
        return cls(**{k: v for k, v in data.items() if k in {
            "id", "title", "description", "status",
            "start_chapter", "last_progress_chapter", "resolve_chapter",
            "related_characters", "related_locations", "key_events",
            "priority", "target_chapter", "note"
        }})


@dataclass
class Snapshot:
    """叙事状态快照 — 全书剧情节点完整副本

    从书斋V66移植：任意时刻保存完整 leder 数据深拷贝
    """
    snapshot_id: str
    version: int
    timestamp: str
    chapter: int
    data: dict                     # 完整 ledger 数据的深拷贝

    def to_dict(self) -> dict:
        return {
            "snapshot_id": self.snapshot_id,
            "version": self.version,
            "timestamp": self.timestamp,
            "chapter": self.chapter,
            "data": self.data,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Snapshot":
        return cls(**data)


# ============================================================
# LedgerEnhancer — TruthLedger 增强包装器
# ============================================================

class LedgerEnhancer:
    """TruthLedger 增强器

    包裹现有 TruthLedger 实例，新增以下能力：
    - 道具/势力/地点管理
    - 支线追踪（独立状态机）
    - 叙事快照
    - 角色归档
    - 审计反馈/校验警告
    - 增强上下文构建

    设计原则：
    - 不修改现有 TruthLedger 的 API
    - 新增功能通过 enhancer 独立调用
    - 与原 ledger 共享同一个项目目录和数据文件
    """

    # 增强数据持久化的文件名
    ENHANCED_DATA_FILE = "truth_ledger_enhanced.json"

    def __init__(self, ledger):
        """
        Args:
            ledger: 现有 TruthLedger 实例
        """
        self.ledger = ledger
        self.artifacts: Dict[str, Artifact] = {}
        self.factions: Dict[str, Faction] = {}
        self.locations: Dict[str, Location] = {}
        self.subplots: List[SubplotState] = []
        self.snapshots: List[Snapshot] = []
        self.audit_feedback: List[dict] = []
        self.validation_warnings: List[dict] = []
        self._loaded = False

    @property
    def _file(self) -> str:
        return os.path.join(self.ledger.project_dir, self.ENHANCED_DATA_FILE)

    # ── 持久化 ──

    def load(self):
        """加载增强数据"""
        if self._loaded:
            return
        if os.path.exists(self._file):
            with open(self._file, "r", encoding="utf-8") as f:
                d = json.load(f)

            self.artifacts = {
                k: Artifact.from_dict(v) for k, v in d.get("artifacts", {}).items()
            }
            self.factions = {
                k: Faction.from_dict(v) for k, v in d.get("factions", {}).items()
            }
            self.locations = {
                k: Location.from_dict(v) for k, v in d.get("locations", {}).items()
            }
            self.subplots = [
                SubplotState.from_dict(s) for s in d.get("subplots", [])
            ]
            self.snapshots = [
                Snapshot.from_dict(s) for s in d.get("snapshots", [])
            ]
            self.audit_feedback = d.get("audit_feedback", [])
            self.validation_warnings = d.get("validation_warnings", [])
        self._loaded = True

    def save(self):
        """保存增强数据"""
        data = {
            "artifacts": {k: v.to_dict() for k, v in self.artifacts.items()},
            "factions": {k: v.to_dict() for k, v in self.factions.items()},
            "locations": {k: v.to_dict() for k, v in self.locations.items()},
            "subplots": [s.to_dict() for s in self.subplots],
            "snapshots": [s.to_dict() for s in self.snapshots],
            "audit_feedback": self.audit_feedback,
            "validation_warnings": self.validation_warnings,
        }
        os.makedirs(self.ledger.project_dir, exist_ok=True)
        with open(self._file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    # ── 道具管理 ──

    def add_artifact(
        self,
        name: str,
        artifact_type: str = "misc",
        grade: str = "",
        owner: str = "",
        description: str = "",
    ) -> str:
        """注册新道具"""
        aid = f"artifact_{len(self.artifacts) + 1:03d}"
        artifact = Artifact(
            id=aid, name=name, type=artifact_type,
            grade=grade, owner=owner, description=description,
            created_at=time.strftime("%Y-%m-%d %H:%M"),
        )
        self.artifacts[aid] = artifact
        self.save()
        return aid

    def transfer_artifact(self, artifact_id: str, new_owner: str) -> bool:
        """转移道具所有权"""
        if artifact_id in self.artifacts:
            self.artifacts[artifact_id].owner = new_owner
            self.save()
            return True
        return False

    def destroy_artifact(self, artifact_id: str) -> bool:
        """标记道具已损毁"""
        if artifact_id in self.artifacts:
            self.artifacts[artifact_id].destroyed = True
            self.save()
            return True
        return False

    # ── 势力管理 ──

    def add_faction(
        self,
        name: str,
        faction_type: str = "",
        leader: str = "",
        description: str = "",
    ) -> str:
        """注册新势力"""
        fid = f"faction_{len(self.factions) + 1:03d}"
        faction = Faction(
            id=fid, name=name, type=faction_type,
            leader=leader, description=description,
        )
        self.factions[fid] = faction
        self.save()
        return fid

    def add_member_to_faction(self, faction_id: str, character_name: str) -> bool:
        """向势力添加成员"""
        if faction_id in self.factions:
            if character_name not in self.factions[faction_id].members:
                self.factions[faction_id].members.append(character_name)
                self.save()
            return True
        return False

    # ── 地点管理 ──

    def add_location(
        self,
        name: str,
        location_type: str = "",
        description: str = "",
        chapter: int = 0,
        faction: str = "",
    ) -> str:
        """注册新地点"""
        lid = f"location_{len(self.locations) + 1:03d}"
        location = Location(
            id=lid, name=name, type=location_type,
            description=description, first_seen_chapter=chapter,
            faction=faction,
        )
        self.locations[lid] = location
        self.save()
        return lid

    # ── 支线追踪 ──

    def register_subplot(
        self,
        title: str,
        description: str = "",
        start_chapter: int = 0,
        related_characters: Optional[List[str]] = None,
        priority: int = 2,
        target_chapter: int = 0,
    ) -> str:
        """注册新支线，返回支线ID"""
        sid = f"subplot_{start_chapter:03d}_{len(self.subplots) + 1:02d}"
        sub = SubplotState(
            id=sid, title=title, description=description,
            start_chapter=start_chapter,
            related_characters=related_characters or [],
            priority=priority, target_chapter=target_chapter,
            status="active" if start_chapter > 0 else "dormant",
            last_progress_chapter=start_chapter,
        )
        self.subplots.append(sub)
        self.save()
        return sid

    def update_subplot(
        self,
        sub_id: str,
        chapter: int,
        event: str = "",
        status: Optional[str] = None,
    ) -> bool:
        """更新支线状态/推进进度"""
        for s in self.subplots:
            if s.id == sub_id:
                if status:
                    s.status = status
                if event:
                    s.key_events.append(f"第{chapter}章: {event}")
                s.last_progress_chapter = chapter
                if status == "resolved":
                    s.resolve_chapter = chapter
                self.save()
                return True
        return False

    def resolve_subplot(self, sub_id: str, chapter: int) -> bool:
        """标记支线已解决"""
        return self.update_subplot(sub_id, chapter, status="resolved")

    def abandon_subplot(self, sub_id: str, chapter: int = 0) -> bool:
        """放弃支线"""
        return self.update_subplot(sub_id, chapter, status="abandoned")

    def get_active_subplots(self) -> List[SubplotState]:
        """获取活跃/推进中的支线"""
        return [s for s in self.subplots
                if s.status in ("dormant", "active", "advancing")]

    def get_subplot_context(self, current_chapter: int) -> str:
        """构建支线上下文文本（用于LLM prompt注入）"""
        active = self.get_active_subplots()
        if not active:
            return ""

        active.sort(key=lambda s: s.priority)
        lines = ["## 支线追踪"]
        for s in active:
            status_label = {
                "dormant": "潜伏", "active": "启动",
                "advancing": "推进中"
            }.get(s.status, s.status)

            gap = (current_chapter - s.last_progress_chapter
                   if s.last_progress_chapter > 0 else 0)
            gap_warn = f"（已{gap}章未推进）" if gap > 10 else ""

            line = f"- [{s.id}] {s.title}（{status_label}）{gap_warn}"
            if s.description:
                line += f"\n  描述：{s.description[:60]}"
            if s.related_characters:
                line += f"\n  关联角色：{', '.join(s.related_characters[:5])}"
            if s.key_events:
                line += f"\n  最近进展：{s.key_events[-1]}"
            if s.target_chapter and current_chapter >= s.target_chapter - 3:
                line += f"\n  目标章节{s.target_chapter}临近，建议收束"

            lines.append(line)
        return "\n".join(lines)

    # ── 快照 ──

    def create_snapshot(self, chapter: int, version: int = 1) -> str:
        """创建叙事快照（完整ledger数据深拷贝）"""
        import copy as _copy
        snapshot_id = f"snap_{chapter:03d}_{len(self.snapshots) + 1:02d}"
        snapshot = Snapshot(
            snapshot_id=snapshot_id,
            version=version,
            timestamp=time.strftime("%Y-%m-%d %H:%M:%S"),
            chapter=chapter,
            data=_copy.deepcopy(self.ledger.to_dict()),
        )
        self.snapshots.append(snapshot)
        self.save()
        return snapshot_id

    def restore_snapshot(self, snapshot_id: str) -> bool:
        """从快照恢复状态"""
        for snap in self.snapshots:
            if snap.snapshot_id == snapshot_id:
                # 恢复 ledger 核心数据
                data = snap.data
                for name, cs_data in data.get("character_states", {}).items():
                    self.ledger.update_character(name, **cs_data)
                self.ledger.foreshadowing = [
                    type(self.ledger.foreshadowing[0]).from_dict(h)
                    if self.ledger.foreshadowing else h
                    for h in data.get("foreshadowing", [])
                ]
                self.save()
                return True
        return False

    # ── 角色归档 ──

    def archive_character(self, name: str) -> bool:
        """归档角色：标记已退场，后续回忆/提及不触发校验"""
        if name in self.ledger.character_states:
            self.ledger.character_states[name].is_alive = False
            if not hasattr(self.ledger.character_states[name], "archived"):
                # 动态添加归档标志
                self.ledger.character_states[name].__dict__["archived"] = True
            self.ledger.save()
            return True
        return False

    def unarchive_character(self, name: str) -> bool:
        """取消归档：恢复角色活跃状态"""
        if name in self.ledger.character_states:
            self.ledger.character_states[name].is_alive = True
            if hasattr(self.ledger.character_states[name], "archived"):
                self.ledger.character_states[name].archived = False
            self.ledger.save()
            return True
        return False

    def get_archived_characters(self) -> List[dict]:
        """获取所有已归档角色"""
        result = []
        for name, cs in self.ledger.character_states.items():
            is_archived = getattr(cs, "archived", False)
            if is_archived:
                result.append({
                    "name": name,
                    "last_seen_chapter": cs.last_seen_chapter,
                    "location": cs.location,
                    "realm": cs.realm,
                })
        return result

    # ── 审计反馈 ──

    def store_audit_feedback(self, chapter: int, audit_issues: List[dict]):
        """存储章节审计反馈，用于动态去AI味引导"""
        ai_issues = [
            {"type": i.get("type", ""), "message": i.get("message", "")}
            for i in audit_issues
            if i.get("type", "") in (
                "buzzword_forbidden", "ai_flavor", "formulaic",
                "character_break", "pov_drift", "logic_gaps"
            )
        ]
        if ai_issues:
            self.audit_feedback.append({"chapter": chapter, "issues": ai_issues})
            self.audit_feedback = self.audit_feedback[-10:]
            self.save()

    def get_audit_feedback(self, chapter: int) -> str:
        """获取前一章的审计反馈（注入prompt）"""
        prev = None
        for fb in self.audit_feedback:
            if fb["chapter"] < chapter:
                prev = fb
            else:
                break
        if not prev or not prev.get("issues"):
            return ""
        lines = [f"上一章（第{prev['chapter']}章）检测到以下问题，本章请主动避免："]
        for i in prev["issues"][:5]:
            lines.append(f"- {i.get('type', '')}: {i.get('message', '')[:80]}")
        return "\n".join(lines)

    # ── 校验警告 ──

    def add_validation_warning(self, chapter: int, title: str, warnings: List[str]):
        """添加校验警告（保留最近20条）"""
        self.validation_warnings.append({
            "chapter": chapter, "title": title, "warnings": warnings,
        })
        self.validation_warnings = self.validation_warnings[-20:]
        self.save()

    # ── 增强上下文构建 ──

    def build_context(
        self,
        current_chapter: int,
        relevant_characters: Optional[List[str]] = None,
        limit_foreshadowing: int = 0,
    ) -> str:
        """构建完整的LLM上下文（合并TruthLedger + 增强数据）

        Args:
            current_chapter: 当前章节号
            relevant_characters: 相关角色列表（可选）
            limit_foreshadowing: 伏笔数量限制，0=不限

        Returns:
            格式化的上下文字符串
        """
        parts = []

        # 1. 角色状态
        if relevant_characters:
            char_texts = []
            for name in relevant_characters:
                if name in self.ledger.character_states:
                    cs = self.ledger.character_states[name]
                    items = ", ".join(cs.possessions) if cs.possessions else "无"
                    char_texts.append(
                        f"【{name}】位置:{cs.location} | 心绪:{cs.emotion} | "
                        f"健康:{cs.health} | 境界:{cs.realm} | "
                        f"持有:{items} | 最后出现:第{cs.last_seen_chapter}章"
                    )
            if char_texts:
                parts.append("## 角色当前状态\n" + "\n".join(char_texts))

        # 2. 伏笔
        active_hooks = self.ledger.get_pending_hooks()
        if active_hooks:
            if limit_foreshadowing > 0 and len(active_hooks) > limit_foreshadowing:
                active_hooks = active_hooks[-limit_foreshadowing:]
                label = f"## 待回收伏笔（最近{limit_foreshadowing}个，共{len(self.ledger.get_pending_hooks())}个）"
            else:
                label = f"## 待回收伏笔（{len(active_hooks)}个）"
            hooks_text = "\n".join(
                f"- [{h.id}] (埋于第{h.planted_chapter}章) {h.hook_type}: {h.content[:120]}"
                for h in active_hooks
            )
            parts.append(f"{label}\n{hooks_text}")

        # 3. 支线追踪
        subplot_text = self.get_subplot_context(current_chapter)
        if subplot_text:
            parts.append(subplot_text)

        # 4. 审计反馈
        audit_text = self.get_audit_feedback(current_chapter)
        if audit_text:
            parts.append(audit_text)

        return "\n\n".join(parts) if parts else ""

    # ── 统计 ──

    def get_stats(self) -> dict:
        """获取增强统计信息"""
        stats = {
            "artifacts": len(self.artifacts),
            "factions": len(self.factions),
            "locations": len(self.locations),
            "subplots_total": len(self.subplots),
            "subplots_active": len(self.get_active_subplots()),
            "subplots_resolved": len(
                [s for s in self.subplots if s.status == "resolved"]
            ),
            "subplots_abandoned": len(
                [s for s in self.subplots if s.status == "abandoned"]
            ),
            "snapshots": len(self.snapshots),
            "validation_warnings": len(self.validation_warnings),
            "audit_feedback_entries": len(self.audit_feedback),
        }
        return stats


# ============================================================
# 便捷函数
# ============================================================

def enhance_ledger(ledger, auto_load: bool = True) -> LedgerEnhancer:
    """为现有 TruthLedger 创建增强器并自动加载增强数据

    Args:
        ledger: 现有 TruthLedger 实例
        auto_load: 是否自动调用 load() 加载持久化数据

    Returns:
        LedgerEnhancer 实例
    """
    enhancer = LedgerEnhancer(ledger)
    if auto_load:
        enhancer.load()
    return enhancer
