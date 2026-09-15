# -*- coding: utf-8 -*-
"""
小说世界 - 角色Agent基类
从 FictionForge framework/agent_base.py 移植与适配

提供角色独立长期记忆能力：
- Memory: 角色记忆条目（事件/对话/观察/反思）
- Belief: 角色信念（AGM式修正）
- AgentState: 角色当前状态快照
- MemoryRetriever: 非embedding多策略记忆检索
- Agent: 角色Agent基类
"""

import json
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from datetime import datetime


# ============================================================
# 数据类
# ============================================================

@dataclass
class Memory:
    """角色记忆条目

    适配说明：原 FictionForge 使用 embedding 向量检索，小说世界适配为
    关键词 + 时间衰减混合检索（MemoryRetriever），降低外部依赖。
    """
    memory_id: str
    type: str          # event / dialogue / observation / reflection
    source_chapter: int
    content: str
    keywords: List[str] = field(default_factory=list)
    strength: float = 1.0          # 记忆强度 0.0-1.0，随回忆衰减
    timestamp: str = ""
    last_recalled: int = 0         # 最后回忆章节号

    def recall(self, current_chapter: int = 0):
        """标记回忆，更新强度（时间衰减）"""
        self.last_recalled = current_chapter or 0
        self.strength = max(0.1, self.strength - 0.05)

    def to_dict(self) -> dict:
        return {
            "memory_id": self.memory_id,
            "type": self.type,
            "source_chapter": self.source_chapter,
            "content": self.content,
            "keywords": self.keywords,
            "strength": self.strength,
            "timestamp": self.timestamp,
            "last_recalled": self.last_recalled,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Memory":
        return cls(**{k: v for k, v in data.items() if k in {
            "memory_id", "type", "source_chapter", "content",
            "keywords", "strength", "timestamp", "last_recalled"
        }})


@dataclass
class Belief:
    """角色信念 — AGM式信念修正"""
    belief_id: str
    content: str                   # 信念内容
    confidence: float = 0.5        # 置信度 0.0-1.0
    evidence_count: int = 0        # 支持证据数量
    last_updated: str = ""
    source_context: str = ""       # 信念来源上下文

    def reinforce(self, evidence: str = "", delta: float = 0.1):
        """增强信念"""
        self.evidence_count += 1
        self.confidence = min(1.0, self.confidence + delta)
        if evidence:
            self.source_context += f"\n[+]{evidence}"

    def weaken(self, counter_evidence: str = "", delta: float = 0.15):
        """削弱信念"""
        self.confidence = max(0.0, self.confidence - delta)
        if counter_evidence:
            self.source_context += f"\n[-]{counter_evidence}"

    def to_dict(self) -> dict:
        return {
            "belief_id": self.belief_id,
            "content": self.content,
            "confidence": self.confidence,
            "evidence_count": self.evidence_count,
            "last_updated": self.last_updated,
            "source_context": self.source_context,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Belief":
        return cls(**{k: v for k, v in data.items() if k in {
            "belief_id", "content", "confidence", "evidence_count",
            "last_updated", "source_context"
        }})


@dataclass
class AgentState:
    """角色当前状态快照"""
    agent_id: str
    chapter: int = 0
    emotions: Dict[str, float] = field(default_factory=dict)
    goals: List[str] = field(default_factory=list)
    relationships: Dict[str, str] = field(default_factory=dict)
    memory_ids: List[str] = field(default_factory=list)
    belief_ids: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "agent_id": self.agent_id,
            "chapter": self.chapter,
            "emotions": self.emotions,
            "goals": self.goals,
            "relationships": self.relationships,
            "memory_ids": self.memory_ids,
            "belief_ids": self.belief_ids,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "AgentState":
        return cls(**{k: v for k, v in data.items() if k in {
            "agent_id", "chapter", "emotions", "goals",
            "relationships", "memory_ids", "belief_ids"
        }})


# ============================================================
# 记忆检索器
# ============================================================

class MemoryRetriever:
    """非embedding多策略记忆检索器

    适配说明：原 FictionForge 依赖 ChromaDB embedding 检索。
    小说世界改用关键词匹配 + 时间衰减 + 类型权重混合排序，
    零外部依赖，适合轻量部署。
    """

    TYPE_WEIGHTS = {
        "event": 1.0,
        "dialogue": 0.8,
        "observation": 0.6,
        "reflection": 0.9,
    }

    def __init__(self, memories: List[Memory], decay_factor: float = 0.15):
        self.memories = memories
        self.decay_factor = decay_factor

    def retrieve(
        self,
        query: str,
        current_chapter: int,
        top_k: int = 5,
        memory_types: Optional[List[str]] = None,
    ) -> List[Memory]:
        """多策略检索：关键词匹配 + 时间衰减 + 类型权重"""
        query_tokens = set(query.lower().split())
        scored = []

        for mem in self.memories:
            if memory_types and mem.type not in memory_types:
                continue

            # 关键词匹配分数
            mem_text = (mem.content + " " + " ".join(mem.keywords)).lower()
            keyword_score = sum(
                1.0 for t in query_tokens if t in mem_text
            ) / max(1, len(query_tokens))

            # 类型权重
            type_weight = self.TYPE_WEIGHTS.get(mem.type, 0.5)

            # 时间衰减
            chapter_distance = current_chapter - mem.source_chapter
            time_decay = max(0.1, 1.0 - self.decay_factor * chapter_distance)

            # 综合分数
            score = (keyword_score * 0.5 + type_weight * 0.25 + time_decay * 0.25) * mem.strength
            scored.append((score, mem))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [mem for _, mem in scored[:top_k]]

    def get_recent(self, current_chapter: int, n: int = 10) -> List[Memory]:
        """按章节排序获取最近N条记忆"""
        sorted_mems = sorted(self.memories, key=lambda m: m.source_chapter, reverse=True)
        return sorted_mems[:n]

    def get_by_type(self, mem_type: str, n: int = 10) -> List[Memory]:
        """按类型获取记忆"""
        return [m for m in self.memories if m.type == mem_type][:n]

    def get_important(self, n: int = 10) -> List[Memory]:
        """获取最重要的记忆（按强度排序）"""
        sorted_mems = sorted(self.memories, key=lambda m: m.strength, reverse=True)
        return sorted_mems[:n]


# ============================================================
# Agent 基类
# ============================================================

class Agent:
    """角色Agent基类

    核心能力：
    - 独立记忆管理（事件/对话/观察/反思）
    - 信念系统（AGM式修正）
    - 上下文构建（为LLM注入角色视角）
    - 弧末反思（压缩章节记忆为结构化总结）
    """

    # 反思输出 schema
    _REFLECTION_SCHEMA = {
        "arc_summary": "string, 本章角色弧线一句话总结",
        "key_decisions": "list, 本章角色做出的关键决定",
        "emotional_shifts": "list, 情绪变化节点",
        "relationship_changes": "list, 关系变化",
        "belief_updates": "list, 信念变化",
        "unresolved_tensions": "list, 未解决的内心冲突",
        "goals_progress": "string, 目标推进情况",
    }

    def __init__(self, agent_id: str, name: str = ""):
        self.agent_id = agent_id
        self.name = name or agent_id
        self.memories: List[Memory] = []
        self.beliefs: Dict[str, Belief] = {}
        self.state = AgentState(agent_id=agent_id)
        self._memory_counter = 0
        self._belief_counter = 0

    # ── 记忆管理 ──

    def add_memory(
        self,
        content: str,
        mem_type: str = "event",
        source_chapter: int = 0,
        keywords: Optional[List[str]] = None,
        strength: float = 1.0,
    ) -> str:
        self._memory_counter += 1
        mid = f"{self.agent_id}_mem_{self._memory_counter:04d}"
        mem = Memory(
            memory_id=mid,
            type=mem_type,
            source_chapter=source_chapter,
            content=content,
            keywords=keywords or [],
            strength=strength,
            timestamp=datetime.now().isoformat(),
            last_recalled=source_chapter,
        )
        self.memories.append(mem)
        self.state.memory_ids.append(mid)
        return mid

    def get_retriever(self) -> MemoryRetriever:
        return MemoryRetriever(self.memories)

    def get_relevant_context(
        self,
        query: str,
        current_chapter: int,
        top_k: int = 5,
        memory_types: Optional[List[str]] = None,
    ) -> str:
        """获取与查询相关的角色记忆上下文（用于注入LLM prompt）"""
        retriever = self.get_retriever()
        results = retriever.retrieve(query, current_chapter, top_k, memory_types)
        lines = [f"## {self.name} 的相关记忆"]
        for i, mem in enumerate(results, 1):
            lines.append(f"{i}. [{mem.type}] 第{mem.source_chapter}章: {mem.content}")
        return "\n".join(lines)

    # ── 信念管理 ──

    def set_belief(self, content: str, confidence: float = 0.5) -> str:
        self._belief_counter += 1
        bid = f"{self.agent_id}_belief_{self._belief_counter:04d}"
        belief = Belief(
            belief_id=bid, content=content, confidence=confidence,
            last_updated=datetime.now().isoformat()
        )
        self.beliefs[bid] = belief
        self.state.belief_ids.append(bid)
        return bid

    def apply_belief_updates(self, updates: List[dict]):
        """AGM式信念修正：expand / revise / contract

        每项: {"action": "reinforce"|"weaken"|"add"|"remove",
                "belief_id"|"content": ..., "evidence": "...", "delta": float}
        """
        for update in updates:
            action = update.get("action", "")
            if action == "add":
                content = update.get("content", "")
                if content:
                    self.set_belief(content, update.get("confidence", 0.5))
            elif action == "remove":
                bid = update.get("belief_id", "")
                if bid and bid in self.beliefs:
                    del self.beliefs[bid]
                    if bid in self.state.belief_ids:
                        self.state.belief_ids.remove(bid)
            elif action == "reinforce":
                bid = update.get("belief_id", "")
                if bid in self.beliefs:
                    self.beliefs[bid].reinforce(
                        update.get("evidence", ""), update.get("delta", 0.1)
                    )
            elif action == "weaken":
                bid = update.get("belief_id", "")
                if bid in self.beliefs:
                    self.beliefs[bid].weaken(
                        update.get("evidence", ""), update.get("delta", 0.15)
                    )

    def get_belief_context(self) -> str:
        """获取角色信念上下文（用于注入LLM prompt）"""
        if not self.beliefs:
            return f"## {self.name} 的信念\n（暂无明确信念）"
        lines = [f"## {self.name} 的信念"]
        for belief in sorted(
            self.beliefs.values(),
            key=lambda b: b.confidence, reverse=True
        ):
            lines.append(f"- [{belief.confidence:.0%}] {belief.content}")
        return "\n".join(lines)

    # ── 弧末反思 ──

    def reflect(self, chapter: int) -> dict:
        """弧末反思：压缩章节记忆为结构化总结，生成 type="reflection" 新记忆

        返回结构化反思数据，供LLM使用。
        """
        recent_mems = [m for m in self.memories if m.source_chapter == chapter]
        if not recent_mems:
            return {"arc_summary": f"第{chapter}章无新记忆", "key_decisions": [],
                    "emotional_shifts": [], "relationship_changes": [],
                    "belief_updates": [], "unresolved_tensions": [],
                    "goals_progress": "无"}

        # 聚合本章记忆
        events = [m for m in recent_mems if m.type == "event"]
        dialogues = [m for m in recent_mems if m.type == "dialogue"]
        observations = [m for m in recent_mems if m.type == "observation"]

        # 生成反思摘要
        reflection_text = f"第{chapter}章经历：{len(events)}个事件，{len(dialogues)}次对话，{len(observations)}次观察。"

        reflection_mem_id = self.add_memory(
            content=reflection_text,
            mem_type="reflection",
            source_chapter=chapter,
            strength=0.8,
        )

        # 更新状态
        self.state.chapter = chapter

        return {
            "reflection_memory_id": reflection_mem_id,
            "arc_summary": reflection_text,
            "event_count": len(events),
            "dialogue_count": len(dialogues),
            "observation_count": len(observations),
            "mental_state": self.state.emotions,
        }

    # ── 序列化 ──

    def to_dict(self) -> dict:
        return {
            "agent_id": self.agent_id,
            "name": self.name,
            "state": self.state.to_dict(),
            "memories": [m.to_dict() for m in self.memories],
            "beliefs": {k: v.to_dict() for k, v in self.beliefs.items()},
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Agent":
        agent = cls(agent_id=data["agent_id"], name=data.get("name", ""))
        agent.state = AgentState.from_dict(data.get("state", {"agent_id": data["agent_id"]}))
        agent.memories = [Memory.from_dict(m) for m in data.get("memories", [])]
        agent.beliefs = {
            k: Belief.from_dict(v) for k, v in data.get("beliefs", {}).items()
        }
        agent._memory_counter = len(agent.memories)
        agent._belief_counter = len(agent.beliefs)
        return agent

    def save(self, file_path: str):
        """持久化到JSON文件"""
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, ensure_ascii=False, indent=2)

    @classmethod
    def load(cls, file_path: str) -> "Agent":
        with open(file_path, "r", encoding="utf-8") as f:
            return cls.from_dict(json.load(f))
