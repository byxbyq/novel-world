# -*- coding: utf-8 -*-
"""
narrative-rpg 叙事模板 + 60-200字字数闸门

移植自书斋V65 prompt体系，提供：
  1. narrative-rpg 格式化叙事模板（开头/中段/结尾结构）
  2. 硬字数闸门：< 60 → 拒绝；> 200 → 截断+补省略
  3. 接入 QualityPipeline L1 层（基础格式校验）

设计原则：
  - 纯规则驱动，不消耗 Token
  - 字数统计基于中文字符 + 对话标记
"""

from typing import Dict, List, Optional, Tuple

# ═══════════════════════════════════════════
# 字数闸门
# ═══════════════════════════════════════════

MIN_WORDS = 60
MAX_WORDS = 200
ELLIPSIS = "……"


def _count_chinese_chars(text: str) -> int:
    """统计中文字符数（含中文标点）"""
    count = 0
    for ch in text:
        if '\u4e00' <= ch <= '\u9fff' or '\u3000' <= ch <= '\u303f' \
                or '\uff00' <= ch <= '\uffef':
            count += 1
    return count


def check_word_count(narrative: str) -> Dict:
    """
    字数闸门检测。

    Returns:
        {
            "passed": bool,
            "word_count": int,
            "level": "pass"|"warn"|"fail",
            "summary": str,
            "truncated": str | None,   # 当 > MAX 时的截断版
        }
    """
    wc = _count_chinese_chars(narrative)

    if wc < MIN_WORDS:
        return {
            "passed": False,
            "word_count": wc,
            "level": "fail",
            "summary": f"字数不足：{wc}字 < {MIN_WORDS}字下限，需重写",
            "suggestion": f"当前叙事仅{wc}字，远低于最低标准{MIN_WORDS}字。请丰富场景描写、角色心理或对话细节。",
        }

    if wc > MAX_WORDS:
        # 在完整句子边界截断
        truncated = _truncate_at_boundary(narrative, MAX_WORDS)
        return {
            "passed": False,
            "word_count": wc,
            "level": "warn",
            "summary": f"字数超限：{wc}字 > {MAX_WORDS}字上限，已截断至{_count_chinese_chars(truncated)}字",
            "truncated": truncated,
        }

    return {
        "passed": True,
        "word_count": wc,
        "level": "pass",
        "summary": f"字数合格：{wc}字（{MIN_WORDS}-{MAX_WORDS}）",
    }


def _truncate_at_boundary(text: str, max_chars: int) -> str:
    """在句子边界（。！？…）截断文本"""
    target = ""
    count = 0
    last_boundary = 0
    for i, ch in enumerate(text):
        if '\u4e00' <= ch <= '\u9fff' or '\u3000' <= ch <= '\u303f' \
                or '\uff00' <= ch <= '\uffef':
            count += 1
        target += ch
        if ch in '。！？…':
            last_boundary = len(target)
        if count >= max_chars:
            break

    if last_boundary > 0:
        return text[:last_boundary] + ELLIPSIS
    return target.strip() + ELLIPSIS


# ═══════════════════════════════════════════
# narrative-rpg 叙事模板
# ═══════════════════════════════════════════

NARRATIVE_TEMPLATE = """
## narrative-rpg 叙事模板规则

### 一、开头段（约20-40字）
- 立即进入场景，用动作或环境开场
- 禁止以"就在这"/"此时"/"忽然"等过渡词开头
- 首选：角色动作 / 环境氛围 / 对话切入点

### 二、中段（约40-100字）
- 核心冲突推进：技能碰撞结果 / 心理活动 / 对话交锋
- 每个角色至少一句主动行为或心理描写
- 技能使用须有可视化效果描述（光影/声响/气候变化）

### 三、结尾段（约20-40字）
- 状态变化 / 伏笔暗示 / 场景转换
- 不可用省略号直接结束正文（省略号仅作为字数截断标记）
- 若有伏笔：用含蓄方式暗示，不直接说破

### 通用要求
- 全文：60-200字（硬下限60，硬上限200）
- 人称：第三人称限定视角切换（每次仅一个视点角色）
- 禁用词检查：避免使用"眼中闪过一丝""嘴角勾起""冷声""寒芒"等AI味表达
- 战力一致：确保角色技能效果与设定的被动/限制/代价一致
"""


def build_narrative_template_rules() -> str:
    """返回完整的 narrative-rpg 模板规则文本，供注入 prompt 使用"""
    rules = NARRATIVE_TEMPLATE.strip()
    rules += f"\n\n硬字数字数约束：每条叙事段落必须 >= {MIN_WORDS} 字且 <= {MAX_WORDS} 字。"
    return rules


def validate_narrative_structure(narrative: str) -> Dict:
    """
    校验叙事是否符合 narrative-rpg 模板结构。

    Returns:
        {
            "passed": bool,
            "issues": [str, ...],
            "level": "pass"|"warn"|"fail",
            "summary": str,
        }
    """
    issues = []
    wc = _count_chinese_chars(narrative)

    # 1. 字数闸门
    wc_result = check_word_count(narrative)
    if not wc_result["passed"]:
        issues.append(wc_result["summary"])

    # 2. 开头禁用词
    banned_openings = [
        "就在这", "此时", "忽然", "突然", "与此同时",
        "而此刻", "在这一刻",
    ]
    for opener in banned_openings:
        if narrative.startswith(opener):
            issues.append(
                f"开头使用禁用过渡词「{opener}」，应以角色动作或环境开场")
            break

    # 3. 结尾检查（禁止纯省略号结尾）
    if narrative.rstrip().endswith("……") and \
            not narrative.rstrip().rstrip("…").endswith(("。", "！", "？")):
        issues.append("结尾不可用省略号作为正文结束")

    # 4. 对话占比检查（对话过多则提示）
    quote_count = narrative.count('"') + narrative.count('"') + \
                  narrative.count('「') + narrative.count('「')
    if quote_count > 4 and wc < 100:
        issues.append(f"对话引号过多({quote_count}个)，建议增加描写和动作")

    level = "pass" if len(issues) == 0 else ("fail" if len(issues) >= 2 else "warn")

    return {
        "passed": len(issues) == 0,
        "issues": issues,
        "level": level,
        "summary": (
            f"叙事结构校验{'通过' if not issues else '未通过：' + '；'.join(issues)}"
        ),
    }


def inject_word_count_prompt() -> str:
    """生成注入到叙事 prompt 的字数约束文本"""
    return (
        f"## 字数硬约束\n"
        f"- 每条独立叙事段落必须严格控制在 {MIN_WORDS}-{MAX_WORDS} 字之间（仅计中文字符）。\n"
        f"- 低于 {MIN_WORDS} 字：内容不足以构成完整场景，拒绝并重写。\n"
        f"- 超过 {MAX_WORDS} 字：系统将自动截断并补省略号。"
    )
