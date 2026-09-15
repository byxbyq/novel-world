# -*- coding: utf-8 -*-
"""
小说世界 - 信念系统
从 FictionForge framework/agent_base.py 的 Belief dataclass + apply_belief_updates 移植

为小说世界角色添加信念层，支持AGM式修正（expand/revise/contract）。
信念是角色对世界的持久认知，影响角色行为和对话风格。
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional
from datetime import datetime


@dataclass
class Belief:
    """角色信念 — AGM式信念修正

    AGM模型：
    - **Expand**: 增强信念（新证据支持）→ reinforce()
    - **Revise**: 修订信念（新证据修正）→ revise()
    - **Contract**: 削弱信念（反证据削弱）→ weaken()
    """

    belief_id: str
    content: str                   # 信念内容
    confidence: float = 0.5        # 置信度 0.0-1.0
    evidence_count: int = 0        # 支持证据数量
    last_updated: str = ""
    source_context: str = ""       # 信念来源上下文

    # AGM 扩展字段
    category: str = "personal"     # personal / social / worldview / goal
    conflicting_beliefs: List[str] = field(default_factory=list)  # 冲突信念ID列表
    revision_history: List[dict] = field(default_factory=list)    # 修正历史

    def reinforce(self, evidence: str = "", delta: float = 0.1):
        """增强信念（Expand）"""
        self.evidence_count += 1
        old_conf = self.confidence
        self.confidence = min(1.0, self.confidence + delta)
        self.revision_history.append({
            "action": "reinforce", "timestamp": datetime.now().isoformat(),
            "evidence": evidence, "old_confidence": old_conf,
            "new_confidence": self.confidence,
        })
        if evidence:
            self.source_context += f"\n[+]{evidence}"

    def weaken(self, counter_evidence: str = "", delta: float = 0.15):
        """削弱信念（Contract）"""
        old_conf = self.confidence
        self.confidence = max(0.0, self.confidence - delta)
        self.revision_history.append({
            "action": "weaken", "timestamp": datetime.now().isoformat(),
            "evidence": counter_evidence, "old_confidence": old_conf,
            "new_confidence": self.confidence,
        })
        if counter_evidence:
            self.source_context += f"\n[-]{counter_evidence}"

    def revise(self, new_content: str, replacement_reason: str = ""):
        """修订信念内容（Revise）"""
        old_content = self.content
        self.content = new_content
        self.revision_history.append({
            "action": "revise",
            "timestamp": datetime.now().isoformat(),
            "old_content": old_content,
            "new_content": new_content,
            "reason": replacement_reason,
        })

    def is_active(self, threshold: float = 0.3) -> bool:
        """信念是否仍活跃（置信度高于阈值）"""
        return self.confidence >= threshold

    def to_dict(self) -> dict:
        return {
            "belief_id": self.belief_id,
            "content": self.content,
            "confidence": self.confidence,
            "evidence_count": self.evidence_count,
            "last_updated": self.last_updated,
            "source_context": self.source_context,
            "category": self.category,
            "conflicting_beliefs": self.conflicting_beliefs,
            "revision_history": self.revision_history,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Belief":
        return cls(**{k: v for k, v in data.items() if k in {
            "belief_id", "content", "confidence", "evidence_count",
            "last_updated", "source_context", "category",
            "conflicting_beliefs", "revision_history"
        }})


class BeliefSystem:
    """信念系统管理器

    管理角色的信念集合，提供信念增删改查与冲突检测。
    信念冲突是指在角色心理中同时存在两个矛盾信念（如"我应该复仇"
    与"复仇只会带来痛苦"），高置信度冲突可能需要角色成长事件来调和。

    使用方式：
        bs = BeliefSystem()
        bs.add_belief("复仇是唯一的道路", confidence=0.8)
        bs.add_belief("善良的人最终会得到好报", confidence=0.6)
        conflicts = bs.detect_conflicts()
    """

    def __init__(self):
        self.beliefs: Dict[str, Belief] = {}
        self._counter = 0

    def add_belief(
        self,
        content: str,
        confidence: float = 0.5,
        category: str = "personal",
    ) -> str:
        """添加新信念，返回信念ID"""
        self._counter += 1
        bid = f"belief_{self._counter:04d}"
        belief = Belief(
            belief_id=bid, content=content, confidence=confidence,
            category=category, last_updated=datetime.now().isoformat(),
        )
        self.beliefs[bid] = belief
        return bid

    def remove_belief(self, belief_id: str) -> bool:
        """移除信念"""
        if belief_id in self.beliefs:
            del self.beliefs[belief_id]
            # 清理其他信念中的冲突引用
            for b in self.beliefs.values():
                if belief_id in b.conflicting_beliefs:
                    b.conflicting_beliefs.remove(belief_id)
            return True
        return False

    def get_belief(self, belief_id: str) -> Optional[Belief]:
        return self.beliefs.get(belief_id)

    def get_active_beliefs(self, threshold: float = 0.3) -> List[Belief]:
        """获取置信度高于阈值的活跃信念"""
        return [b for b in self.beliefs.values() if b.confidence >= threshold]

    def apply_updates(self, updates: List[dict]):
        """批量应用信念修正"""
        for update in updates:
            action = update.get("action", "")
            bid = update.get("belief_id", "")

            if action == "add":
                self.add_belief(
                    update.get("content", ""),
                    confidence=update.get("confidence", 0.5),
                    category=update.get("category", "personal"),
                )
            elif action == "remove" and bid in self.beliefs:
                self.remove_belief(bid)
            elif action == "reinforce" and bid in self.beliefs:
                self.beliefs[bid].reinforce(
                    update.get("evidence", ""), update.get("delta", 0.1)
                )
            elif action == "weaken" and bid in self.beliefs:
                self.beliefs[bid].weaken(
                    update.get("evidence", ""), update.get("delta", 0.15)
                )
            elif action == "revise" and bid in self.beliefs:
                self.beliefs[bid].revise(
                    update.get("content", ""), update.get("reason", "")
                )

    def get_context(self) -> str:
        """获取所有活跃信念的上下文文本"""
        active = self.get_active_beliefs()
        if not active:
            return ""
        lines = ["## 角色信念"]
        for b in sorted(active, key=lambda x: x.confidence, reverse=True):
            lines.append(f"- [{b.confidence:.0%}] [{b.category}] {b.content}")
        return "\n".join(lines)

    def to_dict(self) -> dict:
        return {k: v.to_dict() for k, v in self.beliefs.items()}

    @classmethod
    def from_dict(cls, data: dict) -> "BeliefSystem":
        bs = cls()
        for k, v in data.items():
            bs.beliefs[k] = Belief.from_dict(v)
            # 计数器恢复
            num = int(k.split("_")[1]) if "_" in k and k.split("_")[1].isdigit() else 0
            bs._counter = max(bs._counter, num)
        return bs
