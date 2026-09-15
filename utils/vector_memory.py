# -*- coding: utf-8 -*-
"""
书斋向量记忆系统 (Vector Memory / RAG)
=====================================
移植自白城主V2，适配小说写作场景：
- 章节内容向量化存储，语义检索相关前文
- 6种记忆类型（适配小说：对话/设定/剧情/世界观/角色/能力）
- 遗忘机制（不重要记忆自动清理）
- embedding: BAAI/bge-small-zh-v1.5 (default)（本地运行，无需API）
- 向量库: FAISS(可选加速) + NumPy(默认)
"""
import os
import json
import time
import logging
import hashlib
import threading
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime
from dataclasses import dataclass, field

# numpy 可选（EXE打包时可能不含）
try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False
    np = None

try:
    import faiss
    HAS_FAISS = True
except ImportError:
    HAS_FAISS = False
from enum import Enum
from collections import defaultdict

logger = logging.getLogger(__name__)


class MemoryType(Enum):
    """记忆类型（适配小说写作场景）"""
    CONVERSATION = "conversation"  # 对话片段
    FACT = "fact"                  # 设定事实（世界观规则、硬约束）
    EVENT = "event"                # 剧情事件（章节关键情节）
    KNOWLEDGE = "knowledge"        # 世界观知识（地点、势力、物品）
    PREFERENCE = "preference"      # 角色偏好（性格、习惯）
    SKILL = "skill"                # 角色能力（技能、境界）


@dataclass
class MemoryEntry:
    """记忆条目"""
    id: str
    content: str
    embedding: Optional[List[float]] = None
    memory_type: MemoryType = MemoryType.CONVERSATION
    importance: float = 0.5
    created_at: datetime = field(default_factory=datetime.now)
    last_accessed: datetime = field(default_factory=datetime.now)
    access_count: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "content": self.content,
            "memory_type": self.memory_type.value,
            "importance": self.importance,
            "created_at": self.created_at.isoformat(),
            "last_accessed": self.last_accessed.isoformat(),
            "access_count": self.access_count,
            "metadata": self.metadata
        }


# 可选嵌入模型列表
EMBEDDING_MODELS = {
    "all-MiniLM-L6-v2": {
        "dim": 384,
        "desc": "轻量级多语言模型（384维），速度快，中文一般",
        "zh_quality": 5,
    },
    "BAAI/bge-small-zh-v1.5": {
        "dim": 512,
        "desc": "BGE中文优化模型（512维），中文语义强，推荐中文网文",
        "zh_quality": 8,
    },
    "moka-ai/m3e-base": {
        "dim": 768,
        "desc": "M3E中文大模型（768维），中文最强，需较多内存",
        "zh_quality": 9,
    },
}

def _get_embedding_model_config() -> str:
    """从 ai_config.json 读取当前嵌入模型名称"""
    try:
        cfg_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "data", "ai_config.json")
        if os.path.exists(cfg_path):
            with open(cfg_path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            model_name = cfg.get("embedding_model", "BAAI/bge-small-zh-v1.5")
            if model_name in EMBEDDING_MODELS:
                return model_name
    except Exception:
        pass
    return "BAAI/bge-small-zh-v1.5"


class VectorMemory:
    """向量记忆系统（按项目隔离）"""

    # 类级别共享嵌入模型（所有实例复用同一个模型实例）
    _shared_embedding_model = None
    _shared_embedding_dim = 512
    _shared_model_name = "BAAI/bge-small-zh-v1.5"

    # 类级别保存锁（防止并发写入同一文件）
    _save_locks: Dict[str, threading.Lock] = {}
    _save_locks_mutex = threading.Lock()

    def __init__(self, project_dir: str, embedding_dim: int = None):
        """
        Args:
            project_dir: 小说项目目录路径
            embedding_dim: 嵌入维度（如不指定，从配置读取）
        """
        self.project_dir = project_dir
        self.memory_dir = os.path.join(project_dir, "vector_memory")
        self.index_file = os.path.join(self.memory_dir, "index.json")
        self.vectors_file = os.path.join(self.memory_dir, "vectors.npy")

        os.makedirs(self.memory_dir, exist_ok=True)

        # 读取配置中的嵌入模型名称
        self.model_name = _get_embedding_model_config()

        # 如果未指定维度，从模型配置获取
        if embedding_dim is not None:
            self.embedding_dim = embedding_dim
        else:
            self.embedding_dim = EMBEDDING_MODELS.get(self.model_name, {}).get("dim", 384)

        self.memories: Dict[str, MemoryEntry] = {}
        self.vectors: Optional[np.ndarray] = None
        self.id_list: List[str] = []
        self._vector_list: List[List[float]] = []  # 向量列表（用于增量添加，避免频繁vstack）
        self._vectors_dirty: bool = False  # 向量是否需要重建（加载时对齐失败等）

        # 配置
        self.max_memories = 10000
        self.forget_threshold = 0.0
        self.forget_days = 90  # 小说创作周期长，遗忘周期设为90天

        # 嵌入模型（延迟加载，类级别共享）
        self._embedding_model = None

        self._load()

    def migrate_embedding_model(self, new_model_name: str) -> dict:
        """迁移到新的嵌入模型——重新编码所有记忆

        Args:
            new_model_name: 新模型名称（必须在 EMBEDDING_MODELS 中）
        Returns:
            {"ok": bool, "migrated": int, "old_model": str, "new_model": str, "new_dim": int}
        """
        if new_model_name not in EMBEDDING_MODELS:
            return {"ok": False, "error": f"未知模型: {new_model_name}"}

        old_model = self.model_name
        new_dim = EMBEDDING_MODELS[new_model_name]["dim"]

        if old_model == new_model_name:
            return {"ok": True, "migrated": 0, "old_model": old_model, "new_model": new_model_name, "new_dim": new_dim, "message": "模型未变更"}

        # 更新 ai_config.json
        try:
            cfg_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "data", "ai_config.json")
            cfg = {}
            if os.path.exists(cfg_path):
                with open(cfg_path, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
            cfg["embedding_model"] = new_model_name
            with open(cfg_path, "w", encoding="utf-8") as f:
                json.dump(cfg, f, ensure_ascii=False, indent=2)
        except Exception as e:
            return {"ok": False, "error": f"配置保存失败: {e}"}

        # 重置类级别共享模型，强制重新加载
        VectorMemory._shared_embedding_model = None
        VectorMemory._shared_model_name = new_model_name
        VectorMemory._shared_embedding_dim = new_dim

        # 更新当前实例
        self.model_name = new_model_name
        self.embedding_dim = new_dim
        self._embedding_model = None

        # 重新编码所有记忆
        migrated = 0
        for entry in self.memories.values():
            entry.embedding = self._get_embedding(entry.content)
            migrated += 1

        # 重建向量矩阵
        self._rebuild_vectors()
        self._save()

        logger.info(f"嵌入模型迁移完成: {old_model} → {new_model_name} ({new_dim}维), 重新编码 {migrated} 条记忆")
        return {"ok": True, "migrated": migrated, "old_model": old_model, "new_model": new_model_name, "new_dim": new_dim}

    def add_memory(self, content: str, memory_type: MemoryType = MemoryType.EVENT,
                   importance: float = 0.5, metadata: Dict = None) -> MemoryEntry:
        """添加记忆"""
        if not content or not content.strip():
            return None

        # 限制单条记忆长度（避免整章注入，取关键段落）
        if len(content) > 2000:
            content = content[:2000] + "..."

        # 生成ID
        memory_id = hashlib.md5(f"{content}{time.time()}".encode(), usedforsecurity=False).hexdigest()[:16]

        # 生成嵌入向量
        embedding = self._get_embedding(content)

        # 创建记忆条目
        entry = MemoryEntry(
            id=memory_id,
            content=content,
            embedding=embedding,
            memory_type=memory_type,
            importance=importance,
            metadata=metadata or {}
        )

        # 添加到索引
        self.memories[memory_id] = entry
        self.id_list.append(memory_id)

        # 更新向量矩阵（增量append，搜索时一次性构建ndarray）
        if embedding:
            if not HAS_NUMPY:
                # 纯Python降级模式
                if self.vectors is None:
                    self.vectors = [embedding]
                else:
                    self.vectors.append(embedding)
            else:
                self._vector_list.append(embedding)
                self._vectors_dirty = True

        # 检查容量
        if len(self.memories) > self.max_memories:
            self._cleanup()

        # 保存
        self._save()

        logger.debug(f"添加记忆: {memory_id} (type={memory_type.value})")
        return entry

    def search(self, query: str, k: int = 5, memory_type: MemoryType = None,
               min_importance: float = 0.0) -> List[Tuple[MemoryEntry, float]]:
        """搜索记忆，返回 (记忆条目, 相似度) 列表"""
        if not self.memories:
            return []

        # 确保向量已构建（懒加载：搜索时一次性从_vector_list构建ndarray）
        self._ensure_vectors_built()

        if self.vectors is None or len(self.vectors) == 0:
            return []

        # 获取查询向量
        query_vector = self._get_embedding(query)
        if query_vector is None:
            return []

        if not HAS_NUMPY:
            # 纯Python降级模式：用文本匹配代替向量相似度
            results = []
            query_lower = query.lower()
            for i, mid in enumerate(self.id_list):
                entry = self.memories.get(mid)
                if not entry:
                    continue
                if memory_type and entry.memory_type != memory_type:
                    continue
                if entry.importance < min_importance:
                    continue
                # 简单文本匹配分数
                text_lower = entry.content.lower()
                overlap = sum(1 for w in query_lower.split() if w in text_lower)
                score = overlap / max(len(query_lower.split()), 1)
                results.append((entry, score))
            results.sort(key=lambda x: x[1], reverse=True)
            return results[:k]

        query_vector = np.array(query_vector)

        # 确保维度匹配
        if len(query_vector) != self.vectors.shape[1]:
            logger.warning(f"维度不匹配: query={len(query_vector)}, vectors={self.vectors.shape[1]}")
            return []

        # 计算余弦相似度
        norms = np.linalg.norm(self.vectors, axis=1)
        query_norm = np.linalg.norm(query_vector)
        if query_norm == 0:
            return []

        similarities = np.dot(self.vectors, query_vector) / (norms * query_norm + 1e-8)

        # 获取排序索引
        sorted_indices = np.argsort(similarities)[::-1]

        results = []
        for idx in sorted_indices:
            if idx >= len(self.id_list):
                continue

            memory_id = self.id_list[idx]
            entry = self.memories.get(memory_id)

            if not entry:
                continue

            # 过滤条件
            if memory_type and entry.memory_type != memory_type:
                continue
            if entry.importance < min_importance:
                continue

            # 更新访问信息
            entry.last_accessed = datetime.now()
            entry.access_count += 1

            results.append((entry, float(similarities[idx])))

            if len(results) >= k:
                break

        return results

    def search_for_generation(self, outline: str, chapter_index: int = 0, k: int = 5) -> str:
        """为章节生成构建召回上下文文本"""
        results = self.search(outline, k=k, min_importance=0.3)

        if not results:
            return ""

        parts = []
        for entry, score in results:
            meta = entry.metadata or {}
            ch_info = f"（第{meta.get('chapter', '?')}章）" if meta.get('chapter') is not None else ""
            type_label = {
                "event": "剧情",
                "fact": "设定",
                "knowledge": "世界观",
                "conversation": "对话",
                "preference": "角色",
                "skill": "能力"
            }.get(entry.memory_type.value, "记忆")
            parts.append(f"[相关{type_label}{ch_info} 相似度{score:.2f}]\n{entry.content}")

        return "\n\n".join(parts)

    def search_combined(self, query: str, shared_memory: 'VectorMemory' = None,
                        k: int = 5, memory_type: MemoryType = None,
                        min_importance: float = 0.0) -> List[Tuple[MemoryEntry, float]]:
        """合并搜索：项目记忆 + 共享记忆，按相似度统一排序

        Args:
            query: 查询文本
            shared_memory: 共享记忆实例（跨项目）
            k: 返回条数
            memory_type: 记忆类型过滤
            min_importance: 最低重要度
        Returns:
            合并后的 (记忆条目, 相似度) 列表，共享记忆的 metadata 中会标记 source='shared'
        """
        results = self.search(query, k=k, memory_type=memory_type, min_importance=min_importance)

        if shared_memory and shared_memory.memories:
            shared_results = shared_memory.search(query, k=k, memory_type=memory_type,
                                                   min_importance=min_importance)
            for entry, score in shared_results:
                # 标记来源为共享
                if not entry.metadata:
                    entry.metadata = {}
                entry.metadata['source'] = 'shared'
                results.append((entry, score))

            # 合并后重新按相似度排序，取top-k
            results.sort(key=lambda x: x[1], reverse=True)
            results = results[:k]

        return results

    def search_for_generation_combined(self, outline: str, shared_memory: 'VectorMemory' = None,
                                        chapter_index: int = 0, k: int = 5) -> str:
        """为章节生成构建召回上下文文本（含共享记忆）"""
        results = self.search_combined(outline, shared_memory, k=k*2, min_importance=0.3)

        if not results:
            return ""

        # 过滤掉检查结果/验证报告类内容（不是正文剧情）
        filter_keywords = ['检查结果', '连贯性检查', '完整性检查', '偏差检查', '风格检查',
                          '重复检查', '时间线检查', '冲突检查', '未完成', '断句',
                          '需要修改', '建议', '断裂点', '改进建议', 'val-results',
                          'check_result', '验证报告']
        filtered = []
        for entry, score in results:
            content = entry.content or ""
            # 跳过包含检查结果关键词的内容
            if any(kw in content for kw in filter_keywords):
                continue
            filtered.append((entry, score))
            if len(filtered) >= k:
                break

        if not filtered:
            return ""

        parts = []
        for entry, score in filtered:
            meta = entry.metadata or {}
            ch_info = f"（第{meta.get('chapter', '?')}章）" if meta.get('chapter') is not None else ""
            source_tag = " [跨项目共享]" if meta.get('source') == 'shared' else ""
            type_label = {
                "event": "剧情",
                "fact": "设定",
                "knowledge": "世界观",
                "conversation": "对话",
                "preference": "角色",
                "skill": "能力"
            }.get(entry.memory_type.value, "记忆")
            parts.append(f"[相关{type_label}{ch_info} 相似度{score:.2f}{source_tag}]\n{entry.content}")

        return "\n\n".join(parts)

    def promote_to_shared(self, memory_id: str, shared_memory: 'VectorMemory') -> bool:
        """将项目记忆提升为跨项目共享记忆

        Args:
            memory_id: 要共享的记忆ID
            shared_memory: 共享记忆实例
        Returns:
            是否成功
        """
        entry = self.memories.get(memory_id)
        if not entry:
            return False

        # 添加到共享记忆
        shared_entry = shared_memory.add_memory(
            content=entry.content,
            memory_type=entry.memory_type,
            importance=entry.importance,
            metadata={
                **entry.metadata,
                'source_project': os.path.basename(self.project_dir),
                'promoted_at': datetime.now().isoformat()
            }
        )
        return shared_entry is not None

    def delete_memory(self, memory_id: str) -> bool:
        """删除记忆"""
        if memory_id not in self.memories:
            return False

        del self.memories[memory_id]
        if memory_id in self.id_list:
            self.id_list.remove(memory_id)
        self._rebuild_vectors()
        self._save()
        return True

    def get_stats(self) -> Dict:
        """获取统计信息"""
        type_counts = defaultdict(int)
        for entry in self.memories.values():
            type_counts[entry.memory_type.value] += 1

        return {
            "total": len(self.memories),
            "by_type": dict(type_counts),
            "vectors_shape": list(self.vectors.shape) if self.vectors is not None else None,
            "embedding_dim": self.embedding_dim,
            "embedding_model": self.model_name,
            "has_faiss": HAS_FAISS,
            "has_model": self._embedding_model is not None,
        }

    def _get_embedding(self, text: str) -> Optional[List[float]]:
        """获取嵌入向量 - 优先用 sentence-transformers，fallback 到哈希"""
        # 使用类级别共享模型
        if VectorMemory._shared_embedding_model is None:
            self._init_embedding_model()

        model = VectorMemory._shared_embedding_model
        if model is not None:
            try:
                embedding = model.encode(text, convert_to_numpy=True)
                return embedding.tolist()
            except Exception as e:
                logger.warning(f"Embedding failed, using fallback: {e}")

        # Fallback: 多轮哈希嵌入
        text_hash = hashlib.sha256(text.encode()).hexdigest()
        embedding = []
        hash_source = text_hash
        while len(embedding) < self.embedding_dim:
            for i in range(0, len(hash_source) - 3, 4):
                val = int(hash_source[i:i+4], 16) / 65535.0 - 0.5
                embedding.append(val)
                if len(embedding) >= self.embedding_dim:
                    break
            hash_source = hashlib.sha256((text + str(len(embedding))).encode()).hexdigest()
        return embedding[:self.embedding_dim]

    def _init_embedding_model(self):
        """初始化嵌入模型 - 类级别共享，支持多模型切换，先尝试本地缓存"""
        # 如果已有共享模型且模型名匹配，直接使用
        if VectorMemory._shared_embedding_model is not None and VectorMemory._shared_model_name == self.model_name:
            self._embedding_model = VectorMemory._shared_embedding_model
            self.embedding_dim = VectorMemory._shared_embedding_dim
            return

        # 重置共享状态
        VectorMemory._shared_embedding_model = None
        VectorMemory._shared_model_name = self.model_name

        try:
            logging.getLogger("httpx").setLevel(logging.WARNING)
            logging.getLogger("sentence_transformers").setLevel(logging.WARNING)
            from sentence_transformers import SentenceTransformer
            import torch
            device = "cuda" if torch.cuda.is_available() else "cpu"

            model_name = self.model_name
            logger.info(f"Loading embedding model: {model_name} (target dim={self.embedding_dim})")

            # HF_HUB_OFFLINE 已在 server.py 启动时设置，优先使用本地缓存
            try:
                model = SentenceTransformer(model_name, device=device, local_files_only=True)
            except Exception:
                # 本地缓存不存在，临时允许在线下载
                logger.info(f"Local cache not found for {model_name}, downloading from HF Hub...")
                os.environ.pop("HF_HUB_OFFLINE", None)
                os.environ.pop("TRANSFORMERS_OFFLINE", None)
                model = SentenceTransformer(model_name, device=device, local_files_only=False)
                os.environ["HF_HUB_OFFLINE"] = "1"
                os.environ["TRANSFORMERS_OFFLINE"] = "1"

            # 缓存到类级别
            VectorMemory._shared_embedding_model = model
            VectorMemory._shared_embedding_dim = model.get_embedding_dimension()
            VectorMemory._shared_model_name = model_name
            self._embedding_model = model
            self.embedding_dim = VectorMemory._shared_embedding_dim
            logger.info(f"Embedding model loaded (shared): {model_name} (dim={self.embedding_dim}, device={device})")
        except ImportError:
            logger.warning("sentence-transformers not installed, using hash fallback")
            VectorMemory._shared_embedding_model = None
            self._embedding_model = None
        except Exception as e:
            logger.info(f"Embedding model not available, using hash fallback: {e}")
            VectorMemory._shared_embedding_model = None
            self._embedding_model = None

    def _cleanup(self):
        """清理不重要的记忆（Ebbinghaus 风格衰减）

        公式：forget_score = importance * access_weight - (age_days / forget_days)
        - access_weight = 1 + 0.5 * access_count（访问越多越难忘，但边际递减）
        - 年龄占比满 90 天=1.0，刚好抵消 importance=1.0 的记忆
        - 分数 < forget_threshold 时被遗忘
        """
        now = datetime.now()
        to_delete = []

        for memory_id, entry in self.memories.items():
            age_days = (now - entry.created_at).days
            access_weight = 1.0 + 0.5 * entry.access_count
            age_ratio = min(1.0, age_days / self.forget_days)
            forget_score = entry.importance * access_weight - age_ratio

            if forget_score < self.forget_threshold:
                to_delete.append(memory_id)

        for memory_id in to_delete:
            self.delete_memory(memory_id)

        logger.info(f"清理 {len(to_delete)} 条记忆")

    def _ensure_vectors_built(self):
        """确保向量矩阵已构建（懒加载：从_vector_list一次性构建ndarray）"""
        if not HAS_NUMPY:
            return
        if not self._vectors_dirty:
            return
        if not self._vector_list:
            self.vectors = None
            self._vectors_dirty = False
            return
        self.vectors = np.array(self._vector_list)
        self._vectors_dirty = False

    def _rebuild_vectors(self):
        """重建向量矩阵"""
        vectors = []
        self.id_list = []

        for memory_id, entry in self.memories.items():
            if entry.embedding:
                vectors.append(entry.embedding)
                self.id_list.append(memory_id)

        if vectors:
            if HAS_NUMPY:
                self._vector_list = vectors
                self.vectors = np.array(vectors)
                self._vectors_dirty = False
            else:
                self.vectors = vectors
        else:
            if HAS_NUMPY:
                self._vector_list = []
            self.vectors = None
            self._vectors_dirty = False

    def _load(self):
        """加载记忆 — 确保 id_list 与 vectors 行数严格对齐"""
        loaded_memories = {}
        loaded_ids = []

        if os.path.exists(self.index_file):
            try:
                with open(self.index_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)

                for item in data.get("memories", []):
                    try:
                        entry = MemoryEntry(
                            id=item["id"],
                            content=item["content"],
                            memory_type=MemoryType(item["memory_type"]),
                            importance=item["importance"],
                            created_at=datetime.fromisoformat(item["created_at"]),
                            last_accessed=datetime.fromisoformat(item["last_accessed"]),
                            access_count=item["access_count"],
                            metadata=item.get("metadata", {})
                        )
                        loaded_memories[entry.id] = entry
                        loaded_ids.append(entry.id)
                    except Exception as e:
                        logger.warning(f"跳过记忆条目 {item.get('id', '?')}: {e}")

                logger.info(f"加载 {len(loaded_memories)} 条向量记忆")
            except Exception as e:
                logger.error(f"加载记忆失败: {e}")

        self.memories = loaded_memories
        self.id_list = loaded_ids

        # 加载向量 — 严格校验与 id_list 对齐
        self.vectors = None
        self._vector_list = []
        if HAS_NUMPY and os.path.exists(self.vectors_file) and self.id_list:
            try:
                vecs = np.load(self.vectors_file)
                if vecs.shape[0] == len(self.id_list) and vecs.shape[1] == self.embedding_dim:
                    # 数量与维度均对齐，直接使用
                    self.vectors = vecs
                    self._vector_list = vecs.tolist()
                elif vecs.shape[0] == len(self.id_list) and vecs.shape[1] != self.embedding_dim:
                    # 条目数对齐但维度不匹配（模型已切换），需重建
                    logger.warning(
                        f"向量维度({vecs.shape[1]})与当前模型({self.embedding_dim})不匹配，重建向量索引"
                    )
                    self.vectors = None
                elif vecs.shape[0] > len(self.id_list):
                    # 向量比id多（可能有损坏条目被跳过），只取前 len(id_list) 条
                    # 注意：这是保守策略，实际语义对应关系可能错位
                    logger.warning(
                        f"向量数量({vecs.shape[0]})与记忆条目数({len(self.id_list)})不一致，"
                        f"重建向量索引"
                    )
                    self.vectors = None  # 标记为需要重建
                else:
                    # 向量比id少，不可靠，重建
                    logger.warning(
                        f"向量数量({vecs.shape[0]})少于记忆条目数({len(self.id_list)})，"
                        f"重建向量索引"
                    )
                    self.vectors = None
            except Exception as e:
                logger.error(f"加载向量文件失败: {e}")
                self.vectors = None

        # 如果向量未加载或对齐失败，触发延迟重建标记
        if self.vectors is None and self.memories and HAS_NUMPY:
            logger.info("向量记忆需要重建，将在下次 add/search 时自动触发")
            self._vectors_dirty = True
            # 从 memories 中重建 _vector_list
            self._vector_list = [
                entry.embedding for entry in self.memories.values()
                if entry.embedding
            ]
        else:
            self._vectors_dirty = False

    def _save(self):
        """原子保存记忆 — 先写临时文件再替换，避免中途崩溃导致双文件不一致

        使用类级别锁防止并发写入，并添加重试机制处理 Windows 文件锁冲突。
        """
        import tempfile

        # 获取或创建该目录的锁
        dir_path = os.path.dirname(self.index_file)
        with VectorMemory._save_locks_mutex:
            if dir_path not in VectorMemory._save_locks:
                VectorMemory._save_locks[dir_path] = threading.Lock()
            lock = VectorMemory._save_locks[dir_path]

        # 使用锁保护整个保存过程
        with lock:
            data = {
                "memories": [e.to_dict() for e in self.memories.values()],
                "last_update": datetime.now().isoformat()
            }

            os.makedirs(dir_path, exist_ok=True)

            # 1. 原子写入 index.json（带重试）
            max_retries = 3
            for attempt in range(max_retries):
                index_tmp_fd, index_tmp_path = tempfile.mkstemp(
                    prefix=".tmp_index_", suffix=".json", dir=dir_path
                )
                try:
                    with os.fdopen(index_tmp_fd, 'w', encoding='utf-8') as f:
                        json.dump(data, f, ensure_ascii=False, indent=2)
                    os.replace(index_tmp_path, self.index_file)
                    break
                except PermissionError as e:
                    # Windows 文件锁冲突，重试
                    try:
                        if os.path.exists(index_tmp_path):
                            os.unlink(index_tmp_path)
                    except Exception:
                        pass
                    if attempt < max_retries - 1:
                        time.sleep(0.1 * (attempt + 1))  # 递增等待
                        continue
                    logger.error(f"保存 index.json 失败（重试{max_retries}次后）: {e}")
                    raise
                except Exception:
                    try:
                        if os.path.exists(index_tmp_path):
                            os.unlink(index_tmp_path)
                    except Exception:
                        pass
                    raise

            # 2. 原子写入 vectors.npy（仅当有向量时，带重试）
            if HAS_NUMPY:
                self._ensure_vectors_built()
            if self.vectors is not None and HAS_NUMPY:
                for attempt in range(max_retries):
                    vec_tmp_fd, vec_tmp_path = tempfile.mkstemp(
                        prefix=".tmp_vec_", suffix=".npy", dir=dir_path
                    )
                    try:
                        os.close(vec_tmp_fd)  # np.save 自己打开文件
                        np.save(vec_tmp_path, self.vectors)
                        os.replace(vec_tmp_path, self.vectors_file)
                        break
                    except PermissionError as e:
                        # Windows 文件锁冲突，重试
                        try:
                            if os.path.exists(vec_tmp_path):
                                os.unlink(vec_tmp_path)
                        except Exception:
                            pass
                        if attempt < max_retries - 1:
                            time.sleep(0.1 * (attempt + 1))  # 递增等待
                            continue
                        logger.error(f"保存 vectors.npy 失败（重试{max_retries}次后）: {e}")
                        raise
                    except Exception:
                        try:
                            if os.path.exists(vec_tmp_path):
                                os.unlink(vec_tmp_path)
                        except Exception:
                            pass
                        raise
