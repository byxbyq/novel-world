"""
人味审六维度（Humanity Audit）
从 FictionForge 的 gen.py → verve_review() 提取与适配。

在生成每个 tick 的叙事文本后，执行六维度审核：
1. 内心独白 (inner_voice) — 角色是否有真正的内心声音
2. 温情角色温度 (warmth) — 角色间互动的温度/情感质感
3. C层动作 (c_layer_action) — 动作层面的具体性和身体性
4. 温度触觉 (thermal_haptic) — 写作中的温度和触觉描写
5. 幽默自嘲 (wit) — 是否有幽默、自嘲、讽刺
6. 感官密度 (sensory_density) — 五感描写的密度和精准度

综合产出「人味指数」（0~1），低于阈值则触发重写提示。

原始来源：FictionForge scripts/gen.py — verve_review()
适配：小说世界 Phase 3
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class HumanityAuditResult:
    """人味审计结果。"""
    text_sample: str                          # 审核文本（截断前 2000 字）
    scores: dict[str, float] = field(default_factory=dict)  # 六维度 0~1 分
    humanity_index: float = 0.0               # 综合人味指数（0~1）
    flaws: list[str] = field(default_factory=list)          # 检测到的问题
    strengths: list[str] = field(default_factory=list)      # 亮点
    rewrite_hint: str = ""                    # 若 index < 阈值，提供重写提示


# ── 各维度评分辅助函数 ────────────────────────────────────────────────────

def _score_inner_voice(text: str) -> tuple[float, list[str], list[str]]:
    """评估内心独白维度：是否有角色的真实内心声音。"""
    flaws: list[str] = []
    strengths: list[str] = []

    # 检测内心独白/思考标记
    markers = [
        r'(?:他|她|它)心想[：:]',
        r'(?:他想|她想|暗想|心想|思忖|琢磨|寻思)[：:；;]',
        r'(?:脑中|心里|心底|内心深处|潜意识里)',
        r'「[^」]{10,}」',        # 引号内长句可能是内心声音
        r'难道.{5,}\?',
        r'自言自语[：:]',
    ]
    count = sum(1 for m in markers if re.search(m, text))

    # 叙事中是否有"向内"视角
    inward_keywords = ['意识到', '突然明白', '豁然开朗', '隐隐感到', '说不清', '莫名']
    inward_count = sum(1 for kw in inward_keywords if kw in text)

    if count >= 3 or inward_count >= 4:
        strengths.append(f"内心独白丰富（标记 {count}，向内信号 {inward_count}）")
        score = 0.85
    elif count >= 1:
        score = 0.55
        if inward_count >= 2:
            score = 0.7
    else:
        flaws.append("缺少内心独白/角色思考（0处内心标记）")
        score = 0.25

    return score, flaws, strengths


def _score_warmth(text: str) -> tuple[float, list[str], list[str]]:
    """评估温情/角色温度：角色互动是否有温度感。"""
    flaws: list[str] = []
    strengths: list[str] = []

    warmth_markers = [
        '微微一笑', '温柔地', '握紧.*手', '轻轻.*拍', '眼角.*湿润',
        '哽咽', '红了眼眶', '喉头.*滚动', '抿嘴', '暖意', '心里.*暖',
        '感动', '动容', '抱紧', '依偎', '靠着.*肩', '轻轻.*抱',
    ]
    cold_markers = ['淡淡', '冷冷', '面无表情', '漠然', '冷声', '毫无波澜']

    warmth_count = sum(1 for m in warmth_markers if re.search(m, text))
    cold_count = sum(1 for m in cold_markers if re.search(m, text))

    if warmth_count >= 2:
        strengths.append(f"角色互动有温度感（{warmth_count}处温情标记）")
        score = 0.8
    elif warmth_count >= 1:
        score = 0.55
    else:
        if cold_count >= 3:
            flaws.append("角色互动温度过低（冷漠类标记过多）")
        else:
            flaws.append("角色互动缺乏温度感")
        score = 0.3

    return score, flaws, strengths


def _score_c_layer_action(text: str) -> tuple[float, list[str], list[str]]:
    """评估 C层动作：动作描写是否有具体性和身体性。"""
    flaws: list[str] = []
    strengths: list[str] = []

    body_parts = ['手', '脚', '腿', '臂', '肩', '背', '腰', '颈', '头', '眼', '眉', '唇',
                  '指', '掌', '拳', '肘', '膝', '额', '颚', '舌', '牙', '脸', '腕', '踝']
    action_verbs = ['挥', '踢', '跃', '冲', '奔', '闪', '躲', '挡', '劈', '斩', '刺', '撞',
                    '翻', '滚', '爬', '跳', '跑', '推', '拉', '扯', '拽', '摔', '砸', '按',
                    '掐', '捏', '掐', '舞', '抛', '投', '掷', '转', '旋', '蹬', '踹', '踏']

    body_count = sum(1 for bp in body_parts if bp in text)
    action_count = sum(1 for av in action_verbs if av in text)

    # 动作密度 = (肢体 + 动作) / 千字
    char_count = max(len(text), 1)
    density = (body_count + action_count) / (char_count / 1000) if char_count > 0 else 0

    if density >= 15:
        strengths.append(f"动作描写密度高（density={density:.1f}/千字）")
        score = 0.85
    elif density >= 8:
        score = 0.6
    else:
        flaws.append(f"动作描写不足（density={density:.1f}/千字）")
        score = 0.3

    return score, flaws, strengths


def _score_thermal_haptic(text: str) -> tuple[float, list[str], list[str]]:
    """评估温度触觉维度。"""
    flaws: list[str] = []
    strengths: list[str] = []

    thermal = ['冰冷', '滚烫', '温热', '凉意', '寒意', '灼热', '发烫', '冰寒', '凛冽', '暖洋洋',
               '冷飕飕', '热气', '凉风', '闷热', '燥热', '寒气', '温热']
    haptic = ['粗糙', '光滑', '柔软', '坚硬', '黏腻', '干涩', '湿润', '毛茸茸', '刺手', '滑腻',
              '硌', '扎', '麻痹', '酥麻', '发痒', '刺痛', '按压', '抚摸', '触碰', '摩擦']

    thermal_count = sum(1 for t in thermal if t in text)
    haptic_count = sum(1 for h in haptic if h in text)

    if thermal_count + haptic_count >= 3:
        strengths.append(f"温度/触觉描写充分（{thermal_count}温 + {haptic_count}触）")
        score = 0.8
    elif thermal_count + haptic_count >= 1:
        score = 0.5
    else:
        flaws.append("缺少温度和触觉描写")
        score = 0.2

    return score, flaws, strengths


def _score_wit(text: str) -> tuple[float, list[str], list[str]]:
    """评估幽默自嘲维度。"""
    flaws: list[str] = []
    strengths: list[str] = []

    wit_markers = [
        '苦笑', '自嘲', '调侃', '幽默', '逗趣', '打趣', '揶揄', '戏谑', '风趣',
        '噗嗤', '忍俊不禁', '哑然失笑', '玩味', '促狭', '调笑', '忍笑',
        '翻了.*白眼', '没好气', '腹诽', '暗中吐槽', '心里吐槽',
        '阴阳怪气', '讽刺', '反讽',
    ]
    count = sum(1 for m in wit_markers if re.search(m, text))

    if count >= 2:
        strengths.append(f"幽默/自嘲元素丰富（{count}处）")
        score = 0.85
    elif count >= 1:
        score = 0.55
    else:
        # 幽默不是必需品，但完全缺失会扣分
        score = 0.4

    return score, flaws, strengths


def _score_sensory_density(text: str) -> tuple[float, list[str], list[str]]:
    """评估五感描写密度。"""
    flaws: list[str] = []
    strengths: list[str] = []

    visual = ['看到', '望去', '映入眼帘', '放眼', '远眺', '凝视', '瞥见', '目击',
              '光芒', '阴影', '颜色', '红', '蓝', '绿', '金', '白', '黑', '灰']
    audio = ['听到', '传来', '响起', '声音', '轰鸣', '低语', '大喊', '尖叫', '呼吸声',
             '脚步声', '风声', '水声', '铃声', '回音', '寂静', '嘈杂', '沉默']
    smell = ['闻到', '气味', '香', '臭', '芬芳', '腥', '霉', '焦', '泥土.*味', '药.*味']
    taste = ['尝到', '味道', '甘甜', '苦涩', '辛辣', '酸', '咸', '鲜美', '涩']
    touch = ['触感', '摸到', '冰凉', '温热', '粗糙', '光滑', '刺痛', '酥麻']

    counts = {
        "视觉": sum(1 for v in visual if v in text),
        "听觉": sum(1 for a in audio if a in text),
        "嗅觉": sum(1 for s in smell if s in text),
        "味觉": sum(1 for t in taste if t in text),
        "触觉": sum(1 for to in touch if to in text),
    }
    active_senses = sum(1 for c in counts.values() if c > 0)
    total = sum(counts.values())

    if active_senses >= 4:
        strengths.append(f"五感描写丰富（{active_senses}/5种感官激活，共{total}处）")
        score = 0.85
    elif active_senses >= 2:
        score = 0.55
        if active_senses == 2:
            missing = [k for k, v in counts.items() if v == 0]
            flaws.append(f"五感描写不均衡（缺失: {', '.join(missing)}）")
    else:
        flaws.append(f"五感描写贫乏（仅{active_senses}种感官激活）")
        score = 0.2

    return score, flaws, strengths


# ── 维度权重表 ────────────────────────────────────────────────────────────

_DIMENSION_WEIGHTS = {
    "inner_voice": 0.25,
    "warmth": 0.15,
    "c_layer_action": 0.20,
    "thermal_haptic": 0.12,
    "wit": 0.10,
    "sensory_density": 0.18,
}


# ── 主审核函数 ────────────────────────────────────────────────────────────

def verve_review(text: str, genre: str = "default",
                 threshold: float = 0.55) -> HumanityAuditResult:
    """
    对生成文本执行「人味审」六维度评分。

    Args:
        text: 待审核的叙事文本（通常是单 tick 或单章节的 LLM 输出）
        genre: 小说类型（影响阈值期望，如 "玄幻"的 C层动作权重略高）
        threshold: 人味指数阈值，低于此值触发 rewrite_hint

    Returns:
        HumanityAuditResult 包含六维度分、综合指数、问题列表和重写提示
    """
    sample = text[:2000]  # 取前 2000 字分析

    all_flaws: list[str] = []
    all_strengths: list[str] = []
    scores: dict[str, float] = {}

    scorers = [
        ("inner_voice", _score_inner_voice),
        ("warmth", _score_warmth),
        ("c_layer_action", _score_c_layer_action),
        ("thermal_haptic", _score_thermal_haptic),
        ("wit", _score_wit),
        ("sensory_density", _score_sensory_density),
    ]

    for dim_name, scorer in scorers:
        s, f, st = scorer(sample)
        scores[dim_name] = s
        all_flaws.extend(f)
        all_strengths.extend(st)

    # 综合人味指数（加权）
    humanity_index = sum(
        scores.get(dim, 0) * _DIMENSION_WEIGHTS.get(dim, 1 / 6)
        for dim in _DIMENSION_WEIGHTS
    )

    # 重写提示
    rewrite_hint = ""
    if humanity_index < threshold:
        weakest = sorted(scores.items(), key=lambda x: x[1])[:3]
        dim_labels = {
            "inner_voice": "内心独白",
            "warmth": "角色温度",
            "c_layer_action": "动作描写",
            "thermal_haptic": "温度触觉",
            "wit": "幽默自嘲",
            "sensory_density": "感官密度",
        }
        weak_parts = [f"{dim_labels.get(d, d)}({v:.2f})" for d, v in weakest]
        rewrite_hint = (
            f"人味指数 {humanity_index:.2f} 低于阈值 {threshold}。"
            f"最薄弱维度: {', '.join(weak_parts)}。"
            f"建议：增加内心独白（{weakest[0][0]}）、感官细节和动作描写。"
        )

    return HumanityAuditResult(
        text_sample=sample,
        scores=scores,
        humanity_index=round(humanity_index, 3),
        flaws=all_flaws,
        strengths=all_strengths,
        rewrite_hint=rewrite_hint,
    )


def render_humanity_report(result: HumanityAuditResult) -> str:
    """生成人味审核报告 Markdown。"""
    dim_labels = {
        "inner_voice": "内心独白",
        "warmth": "角色温度",
        "c_layer_action": "C层动作",
        "thermal_haptic": "温度触觉",
        "wit": "幽默自嘲",
        "sensory_density": "感官密度",
    }

    lines = [
        "## 人味审核报告",
        f"**综合人味指数**: {result.humanity_index:.2f} / 1.00",
        "",
        "### 六维度评分",
        "| 维度 | 得分 | 状态 |",
        "|------|------|------|",
    ]
    for dim, label in dim_labels.items():
        s = result.scores.get(dim, 0)
        status = "✅" if s >= 0.6 else ("⚠️" if s >= 0.35 else "❌")
        lines.append(f"| {label} | {s:.2f} | {status} |")

    if result.strengths:
        lines.append("")
        lines.append("### 亮点")
        for s in result.strengths:
            lines.append(f"- {s}")

    if result.flaws:
        lines.append("")
        lines.append("### 问题")
        for f in result.flaws:
            lines.append(f"- {f}")

    if result.rewrite_hint:
        lines.append("")
        lines.append(f"> **重写建议**: {result.rewrite_hint}")

    return "\n".join(lines)
