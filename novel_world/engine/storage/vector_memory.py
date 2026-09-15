# -*- coding: utf-8 -*-
"""
向量记忆系统 - 移植自小说写作工具，扩展时间搜索

核心功能：
- 基于向量相似度的记忆检索（NumPy余弦相似度）
- 四个倒排索引：章节、角色、地点、时间刻
- 多维度过滤搜索：按角色/地点/章节范围/时间刻/类型/重要性
- 自动遗忘机制（基于访问次数和重要性）
- sentence-transformers 嵌入，hash 降级备选
"""
import json, os, time, hashlib, threading
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Dict, List, Optional, Any, Set, Tuple

# 尝试导入 NumPy，失败则降级为列表运算
try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False

# 尝试导入 faiss（可选，暂未使用）
try:
    import faiss
    HAS_FAISS = True
except ImportError:
    HAS_FAISS = False


class MemoryType(Enum):
    """记忆类型枚举 - 9种"""
    CONVERSATION = "conversation"   # 对话记忆
    FACT = "fact"                   # 事实知识
    EVENT = "event"                 # 事件记录
    KNOWLEDGE = "knowledge"         # 世界观知识
    PREFERENCE = "preference"       # 角色偏好
    SKILL = "skill"                 # 技能/能力
    SNAPSHOT = "snapshot"           # 状态快照
    COLLISION = "collision"         # 碰撞/冲突事件
    WORLD_EVENT = "world_event"     # 世界级事件


@dataclass
class MemoryEntry:
    """单条记忆条目"""
    id: str
    content: str
    embedding: Optional[List[float]] = None
    memory_type: MemoryType = MemoryType.FACT
    importance: float = 0.5           # 0.0 ~ 1.0
    created_at: float = 0.0
    last_accessed: float = 0.0
    access_count: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "content": self.content,
            "embedding": self.embedding,
            "memory_type": self.memory_type.value,
            "importance": self.importance,
            "created_at": self.created_at,
            "last_accessed": self.last_accessed,
            "access_count": self.access_count,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "MemoryEntry":
        data = dict(data)  # 避免修改原始数据
        if isinstance(data.get("memory_type"), str):
            data["memory_type"] = MemoryType(data["memory_type"])
        return cls(**data)


class VectorMemory:
    """
    向量记忆系统

    支持向量相似度搜索和多维度倒排索引过滤。
    嵌入模型优先使用 sentence-transformers，不可用时降级为 hash 嵌入。
    """

    def __init__(self, persist_dir: str, dim: int = 512):
        self.persist_dir = persist_dir
        self.dim = dim
        self.memories: Dict[str, MemoryEntry] = {}
        self._lock = threading.Lock()

        # 嵌入模型（延迟加载）
        self._model = None
        self._model_name = "BAAI/bge-small-zh-v1.5"

        # 四个倒排索引：memory_id -> 列表
        self._chapter_index: Dict[int, List[str]] = {}   # 章节号 -> [memory_id]
        self._character_index: Dict[str, List[str]] = {} # 角色ID -> [memory_id]
        self._location_index: Dict[str, List[str]] = {}  # 地点 -> [memory_id]
        self._tick_index: Dict[int, List[str]] = {}      # 时间刻 -> [memory_id]

        # 配置
        self.max_memories = 10000
        self.cleanup_threshold = 8000   # 触发遗忘的阈值
        self.forget_low_importance = 0.2
        self.forget_min_access = 1

        self._load()

    # ─── 嵌入生成 ───

    def _get_model(self):
        """延迟加载 sentence-transformers 模型"""
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer
                self._model = SentenceTransformer(self._model_name)
                self.dim = self._model.get_sentence_embedding_dimension()
            except Exception:
                self._model = "hash_fallback"
        return self._model

    def _get_embedding(self, text: str) -> List[float]:
        """
        生成文本嵌入向量
        优先使用 sentence-transformers，失败则用 hash 降级
        """
        model = self._get_model()
        if model is not None and model != "hash_fallback":
            vec = model.encode(text).tolist()
            return vec
        # hash 降级：将文本分块后取 hash 值作为伪向量
        vec = []
        chunk_size = 8
        for i in range(0, max(len(text), self.dim * chunk_size), chunk_size):
            chunk = text[i:i + chunk_size]
            h = hashlib.md5(chunk.encode("utf-8")).hexdigest()
            vec.append(int(h[:8], 16) / 0xFFFFFFFF)
            if len(vec) >= self.dim:
                break
        # 填充至目标维度
        while len(vec) < self.dim:
            vec.append(0.0)
        return vec[:self.dim]

    # ─── 余弦相似度 ───

    @staticmethod
    def _cosine_similarity(a: List[float], b: List[float]) -> float:
        """计算两个向量的余弦相似度"""
        if HAS_NUMPY:
            va, vb = np.array(a), np.array(b)
            norm_a = np.linalg.norm(va)
            norm_b = np.linalg.norm(vb)
            if norm_a == 0 or norm_b == 0:
                return 0.0
            return float(np.dot(va, vb) / (norm_a * norm_b))
        # 纯 Python 降级
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = sum(x * x for x in a) ** 0.5
        norm_b = sum(x * x for x in b) ** 0.5
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot / (norm_a * norm_b)

    # ─── 核心操作 ───

    def add_memory(self, content: str, memory_type: MemoryType = MemoryType.FACT,
                   importance: float = 0.5, metadata: Dict = None) -> str:
        """添加一条记忆，自动更新索引"""
        with self._lock:
            mid = f"mem_{int(time.time() * 1000)}_{len(self.memories):04d}"
            embedding = self._get_embedding(content)
            now = time.time()
            entry = MemoryEntry(
                id=mid, content=content, embedding=embedding,
                memory_type=memory_type, importance=importance,
                created_at=now, last_accessed=now, access_count=0,
                metadata=metadata or {},
            )
            self.memories[mid] = entry
            # 更新倒排索引
            self._update_indexes(mid, entry.metadata)
            # 检查是否需要遗忘
            if len(self.memories) > self.cleanup_threshold:
                self._cleanup()
            self._save()
            return mid

    def delete_memory(self, memory_id: str) -> bool:
        """删除指定记忆"""
        with self._lock:
            if memory_id not in self.memories:
                return False
            entry = self.memories.pop(memory_id)
            # 从所有索引中移除
            for idx in (self._chapter_index, self._character_index,
                        self._location_index, self._tick_index):
                for key, ids in list(idx.items()):
                    if memory_id in ids:
                        ids.remove(memory_id)
                        if not ids:
                            del idx[key]
            self._save()
            return True

    def search(self, query: str, k: int = 5,
               memory_type: MemoryType = None,
               min_importance: float = 0.0) -> List[Tuple[MemoryEntry, float]]:
        """
        标准向量搜索 - 全量余弦相似度排序
        返回 [(MemoryEntry, similarity), ...] 按相似度降序
        """
        query_vec = self._get_embedding(query)
        scored = []
        for mid, entry in self.memories.items():
            # 类型过滤
            if memory_type and entry.memory_type != memory_type:
                continue
            # 重要性过滤
            if entry.importance < min_importance:
                continue
            sim = self._cosine_similarity(query_vec, entry.embedding)
            scored.append((entry, sim))
        # 更新访问信息
        for entry, _ in scored[:k]:
            entry.last_accessed = time.time()
            entry.access_count += 1
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:k]

    # ─── 倒排索引搜索 ───

    def search_by_time_range(self, query: str, start_chapter: int,
                             end_chapter: int, k: int = 5) -> List[Tuple[MemoryEntry, float]]:
        """按章节范围搜索：先用章节索引预过滤，再向量搜索"""
        candidate_ids: Set[str] = set()
        for ch in range(start_chapter, end_chapter + 1):
            candidate_ids.update(self._chapter_index.get(ch, []))
        return self._search_from_candidates(query, candidate_ids, k)

    def search_by_character(self, query: str, character_id: str,
                            k: int = 5) -> List[Tuple[MemoryEntry, float]]:
        """按角色搜索：用角色索引预过滤，再向量搜索"""
        candidate_ids = set(self._character_index.get(character_id, []))
        return self._search_from_candidates(query, candidate_ids, k)

    def search_by_location(self, query: str, location: str,
                           k: int = 5) -> List[Tuple[MemoryEntry, float]]:
        """
        按地点搜索：模糊匹配地点索引
        支持子串匹配，例如 "长安" 可匹配 "长安城东"
        """
        candidate_ids: Set[str] = set()
        for loc_key, ids in self._location_index.items():
            if location in loc_key or loc_key in location:
                candidate_ids.update(ids)
        return self._search_from_candidates(query, candidate_ids, k)

    def search_by_tick(self, query: str, tick: int,
                       k: int = 5) -> List[Tuple[MemoryEntry, float]]:
        """按时间刻搜索"""
        candidate_ids = set(self._tick_index.get(tick, []))
        return self._search_from_candidates(query, candidate_ids, k)

    def search_multi_filter(self, query: str, k: int = 5,
                            character_id: str = None, location: str = None,
                            start_chapter: int = None, end_chapter: int = None,
                            tick: int = None, memory_type: MemoryType = None,
                            min_importance: float = 0.0) -> List[Tuple[MemoryEntry, float]]:
        """
        多维度过滤搜索 - 所有条件的交集
        同时按角色、地点、章节范围、时间刻、类型、重要性过滤
        """
        candidate_ids: Optional[Set[str]] = None

        # 角色
        if character_id:
            ids = set(self._character_index.get(character_id, []))
            candidate_ids = ids if candidate_ids is None else candidate_ids & ids
        # 地点（模糊匹配）
        if location:
            ids: Set[str] = set()
            for loc_key, mids in self._location_index.items():
                if location in loc_key or loc_key in location:
                    ids.update(mids)
            candidate_ids = ids if candidate_ids is None else candidate_ids & ids
        # 章节范围
        if start_chapter is not None and end_chapter is not None:
            ids: Set[str] = set()
            for ch in range(start_chapter, end_chapter + 1):
                ids.update(self._chapter_index.get(ch, []))
            candidate_ids = ids if candidate_ids is None else candidate_ids & ids
        # 时间刻
        if tick is not None:
            ids = set(self._tick_index.get(tick, []))
            candidate_ids = ids if candidate_ids is None else candidate_ids & ids

        # 如果没有索引过滤条件，用全量；否则用交集
        if candidate_ids is None:
            candidate_ids = set(self.memories.keys())

        return self._search_from_candidates(
            query, candidate_ids, k,
            memory_type=memory_type,
            min_importance=min_importance,
        )

    def _search_from_candidates(self, query: str, candidate_ids: Set[str],
                                k: int, memory_type: MemoryType = None,
                                min_importance: float = 0.0) -> List[Tuple[MemoryEntry, float]]:
        """
        内部方法：在候选集合上进行向量搜索
        候选集为空时返回空列表
        """
        if not candidate_ids:
            return []
        query_vec = self._get_embedding(query)
        scored = []
        for mid in candidate_ids:
            entry = self.memories.get(mid)
            if entry is None:
                continue
            if memory_type and entry.memory_type != memory_type:
                continue
            if entry.importance < min_importance:
                continue
            sim = self._cosine_similarity(query_vec, entry.embedding)
            scored.append((entry, sim))
        # 更新访问
        for entry, _ in scored[:k]:
            entry.last_accessed = time.time()
            entry.access_count += 1
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:k]

    # ─── 索引维护 ───

    def _update_indexes(self, memory_id: str, meta: Dict[str, Any]):
        """根据 metadata 更新四个倒排索引"""
        # 章节索引
        ch = meta.get("chapter")
        if ch is not None:
            self._chapter_index.setdefault(int(ch), []).append(memory_id)
        # 角色索引
        char = meta.get("character_id")
        if char:
            self._character_index.setdefault(str(char), []).append(memory_id)
        # 地点索引
        loc = meta.get("location")
        if loc:
            self._location_index.setdefault(str(loc), []).append(memory_id)
        # 时间刻索引
        tick = meta.get("tick")
        if tick is not None:
            self._tick_index.setdefault(int(tick), []).append(memory_id)

    def _rebuild_indexes(self):
        """从全部记忆重建倒排索引"""
        self._chapter_index.clear()
        self._character_index.clear()
        self._location_index.clear()
        self._tick_index.clear()
        for mid, entry in self.memories.items():
            self._update_indexes(mid, entry.metadata)

    # ─── 遗忘机制 ───

    def _cleanup(self):
        """
        遗忘机制：当记忆数超过阈值时，淘汰低价值记忆
        淘汰规则：重要性低于阈值 且 访问次数极少的记忆
        """
        to_remove = []
        for mid, entry in self.memories.items():
            if (entry.importance < self.forget_low_importance
                    and entry.access_count <= self.forget_min_access):
                to_remove.append(mid)
        # 最多清理到 cleanup_threshold 以下
        remove_count = max(0, len(self.memories) - self.cleanup_threshold)
        to_remove = to_remove[:remove_count]
        for mid in to_remove:
            self.delete_memory(mid)
        if to_remove:
            print(f"[VectorMemory] 遗忘清理：移除 {len(to_remove)} 条低价值记忆")

    # ─── 持久化 ───

    def _load(self):
        """从磁盘加载记忆（原子读取）"""
        path = os.path.join(self.persist_dir, "vector_memory.json")
        if not os.path.exists(path):
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            for v in data.get("memories", {}).values():
                entry = MemoryEntry.from_dict(v)
                self.memories[entry.id] = entry
            self._rebuild_indexes()
        except Exception as e:
            print(f"[VectorMemory] 加载失败: {e}")

    def _save(self):
        """保存到磁盘（原子写入：先写临时文件，再重命名）"""
        os.makedirs(self.persist_dir, exist_ok=True)
        path = os.path.join(self.persist_dir, "vector_memory.json")
        tmp_path = path + ".tmp"
        try:
            data = {
                "memories": {
                    mid: entry.to_dict()
                    for mid, entry in self.memories.items()
                },
                "updated": time.strftime("%Y-%m-%d %H:%M"),
            }
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            # 原子替换
            if os.path.exists(path):
                os.replace(tmp_path, path)
            else:
                os.rename(tmp_path, path)
        except Exception as e:
            print(f"[VectorMemory] 保存失败: {e}")

    # ─── 统计 ───

    def get_stats(self) -> dict:
        """返回记忆系统统计信息"""
        type_counts = {}
        for entry in self.memories.values():
            t = entry.memory_type.value
            type_counts[t] = type_counts.get(t, 0) + 1
        return {
            "total_memories": len(self.memories),
            "type_distribution": type_counts,
            "chapter_index_size": len(self._chapter_index),
            "character_index_size": len(self._character_index),
            "location_index_size": len(self._location_index),
            "tick_index_size": len(self._tick_index),
            "has_numpy": HAS_NUMPY,
            "has_faiss": HAS_FAISS,
            "max_capacity": self.max_memories,
        }
