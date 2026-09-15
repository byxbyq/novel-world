# -*- coding: utf-8 -*-
"""
AI味检测 + 战力崩坏检测 + 文风指纹 + 6项扩展审计

所有实现已按功能域提取至 ai_detector_mixins/ 子目录：
  - core     — AI味检测/评分/常量 (detect_ai_flavor, compute_ai_score, REALM_HIERARCHY, AI_BUZZWORDS)
  - quality  — 质量审计 (战力崩坏/逻辑/人设/POV/设定/空间/高潮/扩展审计)
  - style    — 文风分析 (指纹提取/偏离度对比)

本文件仅做 re-export，保持向后兼容。
"""

from .ai_detector_mixins.core import (  # noqa: F401
    detect_ai_flavor,
    compute_ai_score,
    _line_number,
    _paragraph_index,
    _context_snippet,
    _find_all_positions,
    _find_word_positions,
    REALM_HIERARCHY,
    AI_BUZZWORDS,
)
from .ai_detector_mixins.quality import (  # noqa: F401
    detect_power_collapse,
    detect_logic_gaps,
    detect_character_break,
    detect_pov_drift,
    detect_setting_conflict,
    detect_spatial_consistency,
    detect_climax_missing,
    run_extended_audit,
)
from .ai_detector_mixins.style import (  # noqa: F401
    extract_style_fingerprint,
    compare_style_fingerprint,
)
