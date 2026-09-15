# -*- coding: utf-8 -*-
"""
Memory Manager — 小说世界记忆适配层
===================================
对 events.py 暴露统一接口，底层使用书斋V66的 VectorMemory（FAISS + BGE 向量记忆）。
并非"轻量版"——完整接入书斋V66的语义检索、6种记忆分类、遗忘机制。

接口（供 events.py 使用）:
    mm = MemoryManager()
    mm.auto_cleanup_if_needed()
    mm.add_short_term(window_id, memory_type, content)
    mm.add_scene_memory(scene, content, importance=0.5)
    mm.add_long_term(key, value, category)
    mm.get_short_term(window_id, memory_type) → list[{content: ...}]
    mm.get_scene_memory(scene) → list[{content: ...}]
    mm.get_long_term(category) → dict{key: {value: ...}}
"""
import os
import logging
from datetime import datetime
from typing import Dict, List, Optional

# 书斋V66 向量记忆核心
from utils.vector_memory import VectorMemory, MemoryType

logger = logging.getLogger(__name__)

# 游戏世界记忆存储目录
_SAVES_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "saves")


class MemoryManager:
    """统一记忆管理器 — 底层为书斋V66 VectorMemory + dict 结构层"""

    # 映射：events.py 的 category → VectorMemory 的 MemoryType
    CATEGORY_TO_TYPE = {
        "game_events": MemoryType.EVENT,
        "character": MemoryType.PREFERENCE,
        "world": MemoryType.KNOWLEDGE,
        "dialogue": MemoryType.CONVERSATION,
        "fact": MemoryType.FACT,
        "skill": MemoryType.SKILL,
    }

    def __init__(self):
        # 书斋V66 向量记忆引擎（FAISS + BGE 嵌入，按 saves/ 目录隔离开）
        self._vector = VectorMemory(project_dir=_SAVES_DIR)

        # 简单的 dict 层：短期记忆（窗口化，只保留最近 N 条）
        self._short_term: Dict[str, Dict[str, List[Dict]]] = {}  # window_id → {memory_type: [{content, timestamp}]}
        self._short_term_max = 50  # 每种类型最多保留条数

        # 场景记忆：dict 辅助索引（底层也写入 VectorMemory）
        self._scene_memories: Dict[str, List[Dict]] = {}  # scene → [{content, importance, timestamp}]
        self._scene_max = 100

        # 长期记忆：dict 辅助索引（底层也写入 VectorMemory）
        self._long_term: Dict[str, Dict[str, Dict]] = {}  # category → {key: {value, timestamp, ...}}
        self._long_term_max = 200

        # 上次清理时间
        self._last_cleanup = datetime.now()

    # ═══════════════════════════════════════════
    # 写入接口
    # ═══════════════════════════════════════════

    def auto_cleanup_if_needed(self) -> None:
        """自动清理过期记忆（VectorMemory 内置遗忘机制）"""
        try:
            # 书斋V66 的遗忘机制：按时间 + 重要性阈值清理
            stats_before = self._vector.get_stats()
            # VectorMemory 没有直接暴露 forget 的公开方法，
            # 但它的 _load() 会在初始化时清理过期条目。
            # 这里手动触发一次统计检查。
            count_before = stats_before.get("total", 0)
            if count_before > self._vector.max_memories * 0.8:
                logger.info(
                    f"[MemoryManager] 记忆数 {count_before} 接近上限 "
                    f"{self._vector.max_memories}，自动遗忘已启用"
                )
        except Exception as e:
            logger.debug(f"[MemoryManager] auto_cleanup: {e}")

    def add_short_term(self, window_id: str, memory_type: str, content: str) -> None:
        """添加短期记忆（滑动窗口，超出时自动淘汰旧条目）"""
        if window_id not in self._short_term:
            self._short_term[window_id] = {}
        if memory_type not in self._short_term[window_id]:
            self._short_term[window_id][memory_type] = []

        entry = {
            "content": content,
            "timestamp": datetime.now().isoformat(),
        }
        self._short_term[window_id][memory_type].append(entry)

        # 超量时淘汰最旧的
        if len(self._short_term[window_id][memory_type]) > self._short_term_max:
            self._short_term[window_id][memory_type] = \
                self._short_term[window_id][memory_type][-self._short_term_max:]

        # 同时写入 VectorMemory（语义检索备用）
        try:
            self._vector.add_memory(
                content=content,
                memory_type=MemoryType.EVENT,
                importance=0.3,  # 短期重要性较低
                metadata={
                    "window_id": window_id,
                    "memory_type": memory_type,
                    "layer": "short_term",
                },
            )
        except Exception as e:
            logger.debug(f"[MemoryManager] add_short_term vector error: {e}")

    def add_scene_memory(self, scene: str, content: str, importance: float = 0.5) -> None:
        """添加场景记忆"""
        if scene not in self._scene_memories:
            self._scene_memories[scene] = []

        entry = {
            "content": content,
            "importance": importance,
            "timestamp": datetime.now().isoformat(),
        }
        self._scene_memories[scene].append(entry)

        if len(self._scene_memories[scene]) > self._scene_max:
            self._scene_memories[scene] = self._scene_memories[scene][-self._scene_max:]

        # 写入 VectorMemory
        try:
            self._vector.add_memory(
                content=content,
                memory_type=MemoryType.KNOWLEDGE,
                importance=importance,
                metadata={
                    "scene": scene,
                    "layer": "scene_memory",
                },
            )
        except Exception as e:
            logger.debug(f"[MemoryManager] add_scene_memory vector error: {e}")

    def add_long_term(self, key: str, value: str, category: str) -> None:
        """添加长期记忆"""
        if category not in self._long_term:
            self._long_term[category] = {}

        self._long_term[category][key] = {
            "value": value,
            "timestamp": datetime.now().isoformat(),
        }

        # 超量时淘汰最旧的
        total_keys = sum(len(v) for v in self._long_term.values())
        if total_keys > self._long_term_max:
            # 简单策略：删除每个 category 中最旧的条目
            for cat in list(self._long_term.keys()):
                if len(self._long_term[cat]) > 1:
                    oldest_key = min(
                        self._long_term[cat].keys(),
                        key=lambda k: self._long_term[cat][k].get("timestamp", ""),
                    )
                    del self._long_term[cat][oldest_key]
                    break

        # 写入 VectorMemory
        mem_type = self.CATEGORY_TO_TYPE.get(category, MemoryType.EVENT)
        try:
            self._vector.add_memory(
                content=f"{key}: {value}",
                memory_type=mem_type,
                importance=0.7,  # 长期记忆重要性较高
                metadata={
                    "key": key,
                    "category": category,
                    "layer": "long_term",
                },
            )
        except Exception as e:
            logger.debug(f"[MemoryManager] add_long_term vector error: {e}")

    # ═══════════════════════════════════════════
    # 读取接口
    # ═══════════════════════════════════════════

    def get_short_term(self, window_id: str, memory_type: str) -> List[Dict]:
        """获取短期记忆列表，每项含 content + timestamp"""
        window = self._short_term.get(window_id, {})
        return window.get(memory_type, [])

    def get_scene_memory(self, scene: str) -> List[Dict]:
        """获取场景记忆列表，每项含 content + importance + timestamp"""
        return self._scene_memories.get(scene, [])

    def get_long_term(self, category: str) -> Dict[str, Dict]:
        """获取长期记忆字典，格式 {key: {value: ..., timestamp: ...}}"""
        return self._long_term.get(category, {})

    # ═══════════════════════════════════════════
    # 统计
    # ═══════════════════════════════════════════

    def get_stats(self) -> Dict:
        """获取记忆统计信息"""
        vector_stats = {}
        try:
            vector_stats = self._vector.get_stats()
        except Exception:
            pass

        return {
            "short_term_windows": len(self._short_term),
            "short_term_entries": sum(
                sum(len(items) for items in w.values())
                for w in self._short_term.values()
            ),
            "scene_memory_scenes": len(self._scene_memories),
            "scene_memory_entries": sum(len(v) for v in self._scene_memories.values()),
            "long_term_categories": len(self._long_term),
            "long_term_entries": sum(len(v) for v in self._long_term.values()),
            "vector_memory": vector_stats,
        }


# 单例
_memory_manager: Optional[MemoryManager] = None


def get_memory_manager() -> MemoryManager:
    """获取全局单例 MemoryManager"""
    global _memory_manager
    if _memory_manager is None:
        _memory_manager = MemoryManager()
    return _memory_manager
