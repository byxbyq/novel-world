# -*- coding: utf-8 -*-
"""
小说世界 - 大纲系统模块
从书斋V66移植：卷大纲管理 + 章节规划 + 大纲驱动卷结构

核心能力：
- OutlineManager: 卷纲要CRUD + 自动重建 + 大纲解析卷结构
- Outline: 卷纲要数据类（summary/theme/key_events/character_arcs）
"""

from .outline_manager import OutlineManager, Outline

__all__ = ["OutlineManager", "Outline"]
