# -*- coding: utf-8 -*-
"""
小说世界 - 后处理去AI腔模块
移植自：书斋V66 (backend/post_process_rules.py, backend/services/audit.py, backend/prompt_sanitizer.py)

提供：
- AI味检测与评分（统计特征 + 规则）
- 后处理文本清洗（削"的"字、去连接词、替换AI高频词）
- Prompt注入防护
- 文风指纹系统（提取 + 对比偏离度）
- 6项扩展审计（逻辑/人设/POV/设定/空间/高潮）
- 战力崩坏检测
"""

from .de_ai_rules import (
    DE_REPLACEMENTS,
    CONNECTOR_REPLACEMENTS,
    AI_WORDS_LIMIT,
    AI_WORDS_SYNONYMS,
    DE_DENSITY_TARGET,
    apply_de_ai_postprocess,
    apply_structure_perturb,
    detect_structural_issues,
)

from .ai_detector import (
    detect_ai_flavor,
    compute_ai_score,
    detect_power_collapse,
    run_extended_audit,
    extract_style_fingerprint,
    compare_style_fingerprint,
    REALM_HIERARCHY,
    AI_BUZZWORDS,
)

from .prompt_sanitizer import (
    sanitize_user_input,
    sanitize_light,
    reload_config,
)

from .chapter_fixer import (
    local_fix_from_flavor,
    local_fix_multi_round,
    anti_external_rewrite,
    humanize_rewrite,
    LOCAL_FIXABLE_TYPES,
    GLOBAL_STATISTICAL_TYPES,
)

__all__ = [
    # 去AI腔规则
    "DE_REPLACEMENTS",
    "CONNECTOR_REPLACEMENTS",
    "AI_WORDS_LIMIT",
    "AI_WORDS_SYNONYMS",
    "DE_DENSITY_TARGET",
    "apply_de_ai_postprocess",
    "apply_structure_perturb",
    "detect_structural_issues",
    # AI味检测
    "detect_ai_flavor",
    "compute_ai_score",
    "REALM_HIERARCHY",
    "AI_BUZZWORDS",
    # 战力崩坏
    "detect_power_collapse",
    # 扩展审计
    "run_extended_audit",
    # 文风指纹
    "extract_style_fingerprint",
    "compare_style_fingerprint",
    # Prompt防护
    "sanitize_user_input",
    "sanitize_light",
    "reload_config",
    # 局部段落修复
    "local_fix_from_flavor",
    "local_fix_multi_round",
    "anti_external_rewrite",
    "humanize_rewrite",
    "LOCAL_FIXABLE_TYPES",
    "GLOBAL_STATISTICAL_TYPES",
]
