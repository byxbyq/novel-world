# -*- coding: utf-8 -*-
"""
小说世界 - 信念系统模块
从FictionForge移植：角色信念层 + AGM式信念修正

核心能力：
- Belief: 信念数据类（置信度/证据计数/来源上下文）
- BeliefSystem: 信念管理器，AGM式修正（expand/revise/contract）
"""

from .belief_system import Belief, BeliefSystem

__all__ = ["Belief", "BeliefSystem"]
