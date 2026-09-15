"""
人味审六维度（Humanity Audit）
从 FictionForge gen.py 的 verve_review 函数提取，对生成文本进行「人味」审核：
六维度 —— 内心独白、温情角色温度、C层动作、温度触觉、幽默自嘲、感官密度。

主要导出：
- HumanityAuditResult: 审核结果 dataclass
- verve_review(): 主审核函数（六维度评分 + 综合人味指数）
- render_humanity_report(): 生成审核报告 Markdown
"""
from .verve_review import (
    HumanityAuditResult,
    verve_review,
    render_humanity_report,
)

__all__ = [
    "HumanityAuditResult",
    "verve_review",
    "render_humanity_report",
]
