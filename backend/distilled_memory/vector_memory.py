# -*- coding: utf-8 -*-
"""
小说世界 - 向量记忆
从书斋V66 backend/services/vector_memory.py 移植与适配

提供6种记忆类型的语义检索能力：
- chapter_memory: 章级总结
- character_memory: 角色状态记忆
- event_memory: 关键事件记忆
- foreshadow_memory: 伏笔记忆
- world_memory: 世界观记忆
- technique_memory: 技法记忆

适配说明：原书斋V66 依赖 ChromaDB/Sentence-Transformers 做语义检索。
小说世界适配为轻量级关键词+TF-IDF检索，零外部依赖。
"""

import json
import os
import math
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class MemoryEntry:
    """记忆条目"""
    entry_id: str
    memory_type: str     # chapter_memory / character_memory / event_memory
                         # foreshadow_memory / world_memory / technique_memory
    content: str
    chapter: int = 0
    volume: int = 0
    metadata: dict = field(default_factory=dict)
    embedding_keywords: List[str] = field(default_factory=list)


class VectorMemory:
    """轻量级向量记忆（关键词+TF-IDF检索）

    6种记忆类型，每种有独立检索策略：
    - character_memory: 角色名精确匹配 + 状态关键词
    - event_memory: 事件关键词 + 章节范围
    - foreshadow_memory: 伏笔状态过滤 (planted/active/recovered)
    - chapter_memory: 章节摘要聚合
    - world_memory: 世界观实体检索
    - technique_memory: 技法标签检索
    """

    MEMORY_TYPES = [
        "chapter_memory",
        "character_memory",
        "event_memory",
        "foreshadow_memory",
        "world_memory",
        "technique_memory",
    ]

    def __init__(self, storage_dir: str = ""):
        self.storage_dir = storage_dir
        self.entries: Dict[str, List[MemoryEntry]] = {t: [] for t in self.MEMORY_TYPES}
        self._counter = 0

    def add(
        self,
        content: str,
        memory_type: str = "event_memory",
        chapter: int = 0,
        volume: int = 0,
        metadata: Optional[dict] = None,
        keywords: Optional[List[str]] = None,
    ) -> str:
        """添加记忆条目"""
        if memory_type not in self.MEMORY_TYPES:
            raise ValueError(f"未知记忆类型: {memory_type}，有效类型: {self.MEMORY_TYPES}")

        self._counter += 1
        eid = f"{memory_type}_{self._counter:05d}"
        entry = MemoryEntry(
            entry_id=eid,
            memory_type=memory_type,
            content=content,
            chapter=chapter,
            volume=volume,
            metadata=metadata or {},
            embedding_keywords=keywords or [],
        )
        self.entries[memory_type].append(entry)
        return eid

    # ── 检索 ──

    def search(
        self,
        query: str,
        memory_types: Optional[List[str]] = None,
        top_k: int = 10,
        chapter_range: Optional[tuple] = None,
    ) -> List[MemoryEntry]:
        """关键词+TF-IDF混合检索"""
        types = memory_types or self.MEMORY_TYPES
        tokens = set(query.lower().split())

        # 构建TF-IDF索引
        scored = []
        for mt in types:
            if mt not in self.entries:
                continue
            entries = self.entries[mt]
            if not entries:
                continue

            # 计算IDF
            df = defaultdict(int)
            for e in entries:
                doc_tokens = set(e.content.lower().split())
                doc_tokens.update(e.embedding_keywords)
                for t in doc_tokens:
                    df[t] += 1

            N = len(entries)
            for e in entries:
                if chapter_range:
                    if not (chapter_range[0] <= e.chapter <= chapter_range[1]):
                        continue

                doc_tokens = set(e.content.lower().split())
                doc_tokens.update(e.embedding_keywords)

                tfidf_score = 0.0
                for t in tokens:
                    if t in doc_tokens:
                        tf = 1.0 + math.log(1.0 + e.content.lower().count(t))
                        idf = math.log((N + 1) / (df.get(t, 0) + 1))
                        tfidf_score += tf * idf

                # 关键词直接匹配加分
                keyword_bonus = sum(
                    2.0 for kw in e.embedding_keywords
                    if kw.lower() in query.lower()
                )

                total_score = tfidf_score + keyword_bonus
                if total_score > 0:
                    scored.append((total_score, e))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [e for _, e in scored[:top_k]]

    def search_by_character(self, character_name: str, top_k: int = 10) -> List[MemoryEntry]:
        """按角色名检索角色记忆"""
        entries = self.entries.get("character_memory", [])
        results = [
            e for e in entries
            if character_name in e.content or character_name in e.embedding_keywords
        ]
        results.sort(key=lambda e: e.chapter, reverse=True)
        return results[:top_k]

    def search_foreshadows(
        self,
        status: Optional[str] = None,  # planted / active / recovered
        top_k: int = 20,
    ) -> List[MemoryEntry]:
        """检索伏笔记忆，支持按状态过滤"""
        entries = self.entries.get("foreshadow_memory", [])
        if status:
            entries = [e for e in entries if e.metadata.get("status") == status]
        entries.sort(key=lambda e: e.chapter)
        return entries[:top_k]

    def search_world(self, entity_name: str, top_k: int = 10) -> List[MemoryEntry]:
        """检索世界观实体"""
        entries = self.entries.get("world_memory", [])
        results = [
            e for e in entries
            if entity_name.lower() in e.content.lower()
            or entity_name.lower() in [kw.lower() for kw in e.embedding_keywords]
        ]
        return results[:top_k]

    # ── 上下文构建 ──

    def get_chapter_summary(self, chapter: int) -> str:
        """获取指定章节的摘要"""
        entries = self.entries.get("chapter_memory", [])
        matching = [e for e in entries if e.chapter == chapter]
        if matching:
            return matching[0].content
        return ""

    def get_character_context(self, character_name: str, top_k: int = 5) -> str:
        """构建角色上下文（用于LLM注入）"""
        results = self.search_by_character(character_name, top_k)
        if not results:
            return ""
        lines = [f"## {character_name} 的相关记忆"]
        for i, e in enumerate(results, 1):
            meta = f"第{e.chapter}章" if e.chapter else ""
            lines.append(f"{i}. {meta} {e.content}")
        return "\n".join(lines)

    def get_foreshadow_context(self, current_chapter: int) -> str:
        """构建活跃伏笔上下文（用于LLM注入）"""
        pending = self.search_foreshadows(status="active") + self.search_foreshadows(status="planted")
        # 去重
        seen = set()
        unique = []
        for e in sorted(pending, key=lambda x: x.chapter):
            if e.entry_id not in seen:
                seen.add(e.entry_id)
                unique.append(e)

        if not unique:
            return "（当前无活跃伏笔）"

        lines = ["## 活跃伏笔"]
        for i, e in enumerate(unique[:10], 1):
            lines.append(f"{i}. [第{e.chapter}章埋下] {e.content}")
        return "\n".join(lines)

    # ── 持久化 ──

    def save(self):
        if not self.storage_dir:
            return
        os.makedirs(self.storage_dir, exist_ok=True)
        data = {
            mt: [
                {
                    "entry_id": e.entry_id,
                    "memory_type": e.memory_type,
                    "content": e.content,
                    "chapter": e.chapter,
                    "volume": e.volume,
                    "metadata": e.metadata,
                    "embedding_keywords": e.embedding_keywords,
                }
                for e in entries
            ]
            for mt, entries in self.entries.items()
        }
        file_path = os.path.join(self.storage_dir, "vector_memory.json")
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def load(self):
        if not self.storage_dir:
            return
        file_path = os.path.join(self.storage_dir, "vector_memory.json")
        if not os.path.exists(file_path):
            return
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        for mt in self.MEMORY_TYPES:
            self.entries[mt] = [
                MemoryEntry(**e) for e in data.get(mt, [])
            ]
        if self.entries:
            max_counter = 0
            for entries in self.entries.values():
                for e in entries:
                    try:
                        num = int(e.entry_id.split("_")[-1])
                        max_counter = max(max_counter, num)
                    except (ValueError, IndexError):
                        pass
            self._counter = max_counter
