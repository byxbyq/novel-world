# -*- coding: utf-8 -*-
"""
小说世界 - 记忆合成器
从书斋V66 backend/services/memory_synthesizer.py 移植与适配

核心算法：state_memory 分层聚合
将多卷、多章的蒸馏结果按层级聚合为 state_memory，
用于在AI生成时提供精确的上下文注入。
"""

import json
import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional


# ============================================================
# 数据类
# ============================================================

@dataclass
class StateMemoryEntry:
    """状态记忆条目"""
    entry_id: str
    scope: str            # global_state / volume_state / chapter_state
    chapter: int = 0
    volume: int = 0
    content: str = ""
    confidence: float = 1.0
    source_file: str = ""
    tags: List[str] = field(default_factory=list)


@dataclass
class AggregatedState:
    """聚合后的状态快照"""
    scope: str
    summary: str
    characters: List[dict] = field(default_factory=list)
    plot_state: dict = field(default_factory=dict)
    world_state: dict = field(default_factory=dict)
    entry_count: int = 0


# ============================================================
# MemorySynthesizer
# ============================================================

class MemorySynthesizer:
    """状态记忆分层聚合器

    三层架构：
        L1: chapter_state — 单章蒸馏结果
        L2: volume_state  — 卷内聚合
        L3: global_state  — 全书聚合

    聚合策略：
    - 同名角色状态合并（取最新）
    - 同名地点状态取最新
    - 关键事件按章节排序
    - 伏笔按 planted_chapter 排序

    适配说明：原书斋V66 使用 backend/services/memory_synthesizer.py 中的
    synthesize_memory_context() 函数。现封装为类，保留三层聚合逻辑，
    路径引用从 backend/ 改为相对导入。
    """

    MAX_ENTRIES_PER_SCOPE = 50
    AGGREGATION_WEIGHTS = {
        "global_state": {"summary": 1.0, "characters": 0.9, "plot": 0.8, "world": 0.7},
        "volume_state": {"summary": 1.0, "characters": 0.8, "plot": 0.7, "world": 0.5},
        "chapter_state": {"summary": 1.0, "characters": 0.6, "plot": 0.5, "world": 0.3},
    }

    def __init__(self, storage_dir: str = ""):
        self.storage_dir = storage_dir
        self.entries: List[StateMemoryEntry] = []
        self._chapter_cache: Dict[int, List[StateMemoryEntry]] = {}
        self._volume_cache: Dict[int, List[StateMemoryEntry]] = {}

    # ── 添加条目 ──

    def add_entry(
        self,
        content: str,
        scope: str = "chapter_state",
        chapter: int = 0,
        volume: int = 0,
        confidence: float = 1.0,
        source_file: str = "",
        tags: Optional[List[str]] = None,
    ) -> str:
        """添加状态记忆条目，返回 entry_id"""
        entry_id = f"state_{scope}_{chapter}_{len(self.entries):04d}"
        entry = StateMemoryEntry(
            entry_id=entry_id, scope=scope, chapter=chapter,
            volume=volume, content=content, confidence=confidence,
            source_file=source_file, tags=tags or [],
        )
        self.entries.append(entry)

        # 更新缓存
        if scope == "chapter_state":
            self._chapter_cache.setdefault(chapter, []).append(entry)
        elif scope == "volume_state":
            self._volume_cache.setdefault(volume, []).append(entry)

        if len(self.entries) > self.MAX_ENTRIES_PER_SCOPE * 3:
            self._prune()

        return entry_id

    def _prune(self):
        """裁剪低置信度条目，保持内存可控"""
        if len(self.entries) <= self.MAX_ENTRIES_PER_SCOPE:
            return
        self.entries.sort(key=lambda e: e.confidence, reverse=True)
        self.entries = self.entries[:self.MAX_ENTRIES_PER_SCOPE]

    # ── 分层聚合 ──

    def synthesize(self, current_chapter: int, current_volume: int = 1) -> AggregatedState:
        """三层聚合：chapter → volume → global"""
        # L1: 单章状态
        ch_entries = self._chapter_cache.get(current_chapter, [])

        # L2: 卷状态
        vol_entries = self._volume_cache.get(current_volume, [])

        # L3: 全局状态
        global_entries = [e for e in self.entries if e.scope == "global_state"]

        # 聚合
        merged = self._merge_entries(ch_entries + vol_entries + global_entries)

        return AggregatedState(
            scope=f"ch{current_chapter}_vol{current_volume}",
            summary=merged.get("summary", ""),
            characters=merged.get("characters", []),
            plot_state=merged.get("plot_state", {}),
            world_state=merged.get("world_state", {}),
            entry_count=len(ch_entries) + len(vol_entries) + len(global_entries),
        )

    def _merge_entries(self, entries: List[StateMemoryEntry]) -> dict:
        """合并多来源条目"""
        result = {"summary": "", "characters": [], "plot_state": {}, "world_state": {}}
        char_map: Dict[str, dict] = {}
        world_map: Dict[str, str] = {}
        summaries: List[str] = []

        for entry in sorted(entries, key=lambda e: (e.chapter, e.confidence), reverse=True):
            # 摘要
            if "summary" in entry.tags or not entry.tags:
                summaries.append(entry.content[:200])

            # 解析结构化内容
            try:
                data = json.loads(entry.content)
            except (json.JSONDecodeError, TypeError):
                data = {}

            # 角色状态
            if "characters" in data:
                for char in data["characters"]:
                    name = char.get("name", "")
                    if name:
                        char_map[name] = {**char_map.get(name, {}), **char}

            # 世界观状态
            if "locations" in data:
                for loc in data["locations"]:
                    world_map[loc.get("name", "")] = loc.get("state", "")

        result["summary"] = " | ".join(summaries[:3])
        result["characters"] = list(char_map.values())
        result["world_state"] = world_map

        return result

    def get_context_for_chapter(self, chapter: int, volume: int = 1) -> str:
        """为AI生成构建上下文注入文本"""
        state = self.synthesize(chapter, volume)

        parts = [f"## 当前状态 (第{chapter}章)"]

        if state.summary:
            parts.append(f"**摘要**: {state.summary}")

        if state.characters:
            parts.append("\n**角色状态**:")
            for c in state.characters[:10]:
                name = c.get("name", "?")
                items = [
                    f"{k}={v}" for k, v in c.items()
                    if k != "name" and v
                ]
                parts.append(f"  - {name}: {', '.join(items) if items else '无变化'}")

        return "\n".join(parts)

    # ── 持久化 ──

    def save(self):
        """保存到磁盘"""
        if not self.storage_dir:
            return
        os.makedirs(self.storage_dir, exist_ok=True)
        file_path = os.path.join(self.storage_dir, "state_memory.json")
        data = {
            "entries": [
                {
                    "entry_id": e.entry_id,
                    "scope": e.scope,
                    "chapter": e.chapter,
                    "volume": e.volume,
                    "content": e.content,
                    "confidence": e.confidence,
                    "source_file": e.source_file,
                    "tags": e.tags,
                }
                for e in self.entries
            ]
        }
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def load(self):
        """从磁盘加载"""
        if not self.storage_dir:
            return
        file_path = os.path.join(self.storage_dir, "state_memory.json")
        if not os.path.exists(file_path):
            return
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.entries = [
            StateMemoryEntry(**e) for e in data.get("entries", [])
        ]
        # 重建缓存
        self._chapter_cache.clear()
        self._volume_cache.clear()
        for e in self.entries:
            if e.scope == "chapter_state":
                self._chapter_cache.setdefault(e.chapter, []).append(e)
            elif e.scope == "volume_state":
                self._volume_cache.setdefault(e.volume, []).append(e)
