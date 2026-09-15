"""AI Detector Mixins"""
from .core import (
    detect_ai_flavor,
    compute_ai_score,
    _line_number,
    _paragraph_index,
    _context_snippet,
    _find_all_positions,
    _find_word_positions,
    REALM_HIERARCHY,
    AI_BUZZWORDS,
    RHETORICAL_PATTERNS_ZH,
)
from .quality import (
    detect_power_collapse,
    detect_logic_gaps,
    detect_character_break,
    detect_pov_drift,
    detect_setting_conflict,
    detect_spatial_consistency,
    detect_climax_missing,
    run_extended_audit,
)
from .style import (
    extract_style_fingerprint,
    compare_style_fingerprint,
)

__all__ = [
    "detect_ai_flavor",
    "compute_ai_score",
    "detect_power_collapse",
    "detect_logic_gaps",
    "detect_character_break",
    "detect_pov_drift",
    "detect_setting_conflict",
    "detect_spatial_consistency",
    "detect_climax_missing",
    "run_extended_audit",
    "extract_style_fingerprint",
    "compare_style_fingerprint",
    "REALM_HIERARCHY",
    "AI_BUZZWORDS",
    "RHETORICAL_PATTERNS_ZH",
]
