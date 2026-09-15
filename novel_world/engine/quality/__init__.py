# -*- coding: utf-8 -*-
"""
quality 包 - 叙事质量校验管线

本包提供叙事生成后的多层级质量校验：
  - constants: 禁用词/桥段/叙事风格规则
  - audit_service: AI味检测、战力崩坏检测、文风指纹
  - quality_pipeline: 8 层自动校验管线
  - timeline_checker: 时序一致性
  - narrative_corrector: 人设校正
  - narrative_state_manager: 角色状态追踪
  - world_rule_guard: 世界观规则守卫（在 scheduler 包中）
"""

from .constants import (
    FORBIDDEN_WORDS,
    FORBIDDEN_PLOTS,
    build_narrative_rules,
)

from .audit_service import (
    detect_ai_flavor,
    detect_power_collapse,
    extract_style_fingerprint,
    compare_style_fingerprint,
    run_extended_audit,
)

from .quality_pipeline import (
    PipelineLevel,
    ResultLevel,
    LayerResult,
    QualityReport,
    QualityPipeline,
)

from .narrative_template import (
    check_word_count,
    validate_narrative_structure,
    build_narrative_template_rules,
    inject_word_count_prompt,
    MIN_WORDS,
    MAX_WORDS,
)

from .skill_validator import (
    SkillViolation,
    validate_skill_usage,
    build_skill_limits_from_yaml,
    build_char_skill_map_from_yaml,
)

__all__ = [
    # constants
    "FORBIDDEN_WORDS",
    "FORBIDDEN_PLOTS",
    "build_narrative_rules",
    # audit_service
    "detect_ai_flavor",
    "detect_power_collapse",
    "detect_coincidence",
    "detect_tool_character",
    "extract_style_fingerprint",
    "compare_style_fingerprint",
    "run_extended_audit",
    # quality_pipeline
    "PipelineLevel",
    "ResultLevel",
    "LayerResult",
    "QualityReport",
    "QualityPipeline",
    # narrative_template
    "check_word_count",
    "validate_narrative_structure",
    "build_narrative_template_rules",
    "inject_word_count_prompt",
    "MIN_WORDS",
    "MAX_WORDS",
    # skill_validator
    "SkillViolation",
    "validate_skill_usage",
    "build_skill_limits_from_yaml",
    "build_char_skill_map_from_yaml",
]
