"""
理论心智层（Theory of Mind）
源自 FictionForge v0.2.0 核心创新：角色间互相推断信念/意图/知识的理论心智层。
每个 tick 结束后，引擎维护一个全角色互推的真值表，供后处理/信息差渲染使用。

主要导出：
- TruthTable: 真值表容器（fact_id → Fact）
- Fact: 单个事实，包含知道/不知道该事实的角色集合
- KnowledgeSnapshot: 从多轮真值表提取的知识快照
- propagate_tom_all(): 全角色知识传播（事件→目击者→推定获取）
- detect_type_a(): 检测是否有角色即将发现"秘密"
- annotate_spec(): 由真值表生成叙事标注（谁该怎么做）
- render_info_gaps(): 为叙事生成信息差提示
"""
from .theory_of_mind import (
    TruthTable,
    Fact,
    KnowledgeSnapshot,
    propagate_tom_all,
    detect_type_a,
    annotate_spec,
    render_info_gaps,
)

__all__ = [
    "TruthTable",
    "Fact",
    "KnowledgeSnapshot",
    "propagate_tom_all",
    "detect_type_a",
    "annotate_spec",
    "render_info_gaps",
]
