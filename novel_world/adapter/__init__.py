# -*- coding: utf-8 -*-
"""
Phase 1 P0: Adapter 适配层
对外暴露与 backend/engine.py 相同的 API，内部桥接 novel_world/engine。
"""
from .adapter import EngineAdapter

__all__ = ["EngineAdapter"]
