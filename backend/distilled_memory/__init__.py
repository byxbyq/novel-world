# -*- coding: utf-8 -*-
"""
小说世界 - 蒸馏记忆模块
从书斋V66移植：5路提取器 + 10x压缩 + 状态记忆分层聚合

核心能力：
- DistillService: 单章蒸馏 → 5路并行提取（情节/技法/场景/反面/世界观）
- MemorySynthesizer: state_memory 分层聚合算法
- VectorMemory: 语义检索 + 6种记忆类型
- MemoryAgent: 伏笔/记忆 Agent
"""

from .distill_service import DistillService
from .memory_synthesizer import MemorySynthesizer
from .vector_memory import VectorMemory
from .memory_agent import MemoryAgent

__all__ = [
    "DistillService",
    "MemorySynthesizer",
    "VectorMemory",
    "MemoryAgent",
]
