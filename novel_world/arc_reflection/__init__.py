# -*- coding: utf-8 -*-
"""
小说世界 - 弧末反思模块
从FictionForge移植：角色在每章结束后的自我反思

核心能力：
- ArcReflector: 弧末反思引擎，压缩章节记忆为 type="reflection" 结构化总结
- ArcSummary: 弧末反思结果数据类
"""

from .reflector import ArcReflector, ArcSummary

__all__ = ["ArcReflector", "ArcSummary"]
