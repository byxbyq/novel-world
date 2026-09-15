# -*- coding: utf-8 -*-
"""
小说世界 - 角色Agent模块
从FictionForge移植：角色独立记忆 + 信念系统 + 上下文检索

核心能力：
- Memory / Belief / AgentState: 角色记忆与信念数据类
- MemoryRetriever: 非embedding多策略记忆检索（近期/重要/主题）
- Agent: 角色Agent基类，含上下文构建、AGM信念修正、弧末反思
"""

from .base import Memory, Belief, AgentState, Agent, MemoryRetriever

__all__ = [
    "Memory",
    "Belief",
    "AgentState",
    "Agent",
    "MemoryRetriever",
]
