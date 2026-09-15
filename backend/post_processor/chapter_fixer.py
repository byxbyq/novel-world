# -*- coding: utf-8 -*-
"""
局部段落修复 - 移植自书斋V66 (chapter_fixer.py + validate_models.py)

核心设计哲学：
  先规则清洗 → 再检测评分 → 最后只对定位到的问题段落做局部AI重写
  而非"检测到问题就全文推倒重来"

核心能力：
1. 段落级局部重写（而非整章重写）
2. 多策略问题段落定位（偏移量/关键词/匹配文本）
3. 上下文感知的修复指令（保留前后各2段作为上下文）
4. 长度保护和质量检查（拒绝过短的修复结果）
5. 问题分类：可定位问题优先修复，全局统计问题找最差段落修复
"""

import re
import hashlib
import logging
from typing import Dict, List, Tuple, Optional
from collections import Counter

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════
# 问题分类
# ═══════════════════════════════════════════

# 可局部修复的问题类型（有明确位置信息）
LOCAL_FIXABLE_TYPES = {
    'buzzword_forbidden', 'buzzword_density',
    'formulaic_transition', 'transition_overuse',
    'narrator_overreach',
    'negative_pivot', 'formulaic_modifier',
    'god_view',
    'sublimation_ending',
    'engineering_word_leak',
    'duplicate_paragraph',
    'dialogue_tag_density',
}

# 全局统计问题（无明确位置，需找最差段落修复）
GLOBAL_STATISTICAL_TYPES = {
    'low_burstiness', 'low_ttr', 'uniform_paragraphs',
    'pattern_repetition', 'monotonous_sentence',
    'connector_overuse', 'high_de_density',
}


# ═══════════════════════════════════════════
# 修复指令模板
# ═══════════════════════════════════════════

FIX_TEMPLATES = {
    'buzzword_forbidden': '请重写这段文字，删除所有AI禁用词（如"{detail}"），用更自然的表达替代',
    'buzzword_density': '请重写这段文字，减少AI高频词"{detail}"的使用，用同义词或不同表达替代',
    'formulaic_transition': '请重写这段文字，删除公式化过渡语（如"就在这时""话音刚落"），用更自然的场景衔接',
    'transition_overuse': '请重写这段文字，减少公式化过渡语的使用，用动作或场景描写自然衔接',
    'narrator_overreach': '请重写这段文字，删除叙事者越权评论（如"显然""毫无疑问"），让读者自己得出结论',
    'negative_pivot': '请重写这段文字，将"不是…而是…"的否定铺垫句式改为直接表达后项',
    'formulaic_modifier': '请重写这段文字，将万能状语句式改为独立短句或动作描写',
    'god_view': '请重写这段文字，删除上帝视角/解释腔（如"殊不知""多年以后"），用角色视角叙事',
    'sublimation_ending': '请重写这段文字，删除结尾升华/总结句式，用动作或场景收尾',
    'engineering_word_leak': '请重写这段文字，删除工程词泄漏（如"{detail}"），替换为正常的小说内容',
    'duplicate_paragraph': '请重写这段文字，使其内容与其他段落不同，消除重复模板化输出',
    'dialogue_tag_density': '请重写这段文字，减少对话标签（如"说道""问道"），用动作描写替代对话标签',
    # 全局统计问题
    'low_burstiness': '请重写这段文字，使句子长短差异更大——有的句子只有五六个字，有的可以到三四十字，打破均匀感',
    'low_ttr': '请重写这段文字，使用更多不同的词汇，减少重复用词，增加词汇多样性',
    'uniform_paragraphs': '请重写这段文字，调整段落长度使其与其他段落长短不一',
    'pattern_repetition': '请重写这段文字，改变句首模式，不要用相同的词开头',
    'monotonous_sentence': '请重写这段文字，避免连续句子以相同的词开头',
    'connector_overuse': '请重写这段文字，删除多余的连接词（如"然而""因此""于是"），用自然衔接',
    'high_de_density': '请重写这段文字，减少"的"字使用，用更简洁的表达',
}


# ═══════════════════════════════════════════
# 段落工具函数
# ═══════════════════════════════════════════

def _split_paragraphs(content: str) -> List[str]:
    """按空行或换行切分段落，保留非空段落。"""
    if not content:
        return []
    parts = content.split('\n\n')
    result = []
    for p in parts:
        p = p.strip()
        if p:
            sub_parts = p.split('\n')
            for sp in sub_parts:
                sp = sp.strip()
                if sp:
                    result.append(sp)
    return result


def _paragraph_fingerprint(text: str) -> str:
    """计算段落内容指纹：去除空白后取 MD5 前 16 位。

    用于跨轮追踪已修复段落，替代容易漂移的整数索引。
    去空白是为了容忍规则清洗带来的格式微调。
    """
    if not text:
        return ''
    normalized = re.sub(r'\s+', '', text)
    return hashlib.md5(normalized.encode('utf-8')).hexdigest()[:16]


def _dedup_paragraphs(content: str, min_length: int = 30) -> Tuple[str, int]:
    """段落级去重：删除完全相同的重复段落（按归一化全文匹配）。

    Returns:
        (cleaned_content, removed_count)
    """
    if not content or len(content) < 100:
        return content, 0

    paragraphs = _split_paragraphs(content)
    if len(paragraphs) < 3:
        return content, 0

    seen = set()
    cleaned = []
    removed = 0

    for p in paragraphs:
        trimmed = p.strip()
        if len(trimmed) > min_length:
            normalized = re.sub(r'\s+', ' ', trimmed)
            if normalized in seen:
                removed += 1
                continue
            seen.add(normalized)
        cleaned.append(p)

    if removed > 0:
        separator = '\n\n' if '\n\n' in content else '\n'
        return separator.join(cleaned), removed
    return content, 0


def _fuzzy_dedup_paragraphs(content: str, similarity_threshold: float = 0.28) -> Tuple[str, int]:
    """模糊段落去重：多策略检测并删除近似重复段落。

    比 _dedup_paragraphs 激进得多，能识别同义改写、细节增减的近似重复。
    
    策略：
    1. 分隔符行清理（---, ***, === 等）
    2. 精确去重（min_length=15，比 _dedup_paragraphs 更低）
    3. 前缀匹配：前8个非空白字符相同的段落视为重复
    4. Bigram Jaccard 相似度 >= threshold
    5. 公共子串 >= 6 字符（滑动窗口，步长3）

    重复段落中保留最长的版本（最详细）。
    
    Returns:
        (cleaned_content, removed_count)
    """
    if not content or len(content) < 100:
        return content, 0

    paragraphs = _split_paragraphs(content)
    if len(paragraphs) < 3:
        return content, 0

    # ── 1. 清理分隔符行和极短行 ──
    separator_pattern = re.compile(r'^[-—=*_~`#]{2,}$')
    working = []
    sep_removed = 0
    for p in paragraphs:
        stripped = p.strip()
        if separator_pattern.match(stripped):
            sep_removed += 1
            continue
        if len(stripped) < 2:
            sep_removed += 1
            continue
        working.append(p)

    if len(working) < 3:
        return content, 0

    # ── 2. 预计算 bigram 集合和前缀 ──
    def _get_bigrams(text: str) -> frozenset:
        normalized = re.sub(r'\s+', '', text)
        return frozenset(normalized[i:i+2] for i in range(len(normalized) - 1))

    def _get_prefix(text: str, n: int = 8) -> str:
        normalized = re.sub(r'\s+', '', text)
        return normalized[:n]

    bigrams = [_get_bigrams(p) for p in working]
    prefixes = [_get_prefix(p) for p in working]

    # ── 3. 精确去重（低阈值）──
    exact_seen = {}
    exact_to_remove = set()
    for i, p in enumerate(working):
        if len(p.strip()) < 15:
            continue
        normalized = re.sub(r'\s+', ' ', p.strip())
        if normalized in exact_seen:
            # 保留较长的
            prev_idx = exact_seen[normalized]
            if len(working[prev_idx]) >= len(p):
                exact_to_remove.add(i)
            else:
                exact_to_remove.add(prev_idx)
                exact_seen[normalized] = i
        else:
            exact_seen[normalized] = i

    # ── 4. 模糊去重 ──
    to_remove = set(exact_to_remove)

    for i in range(len(working)):
        if i in to_remove:
            continue

        for j in range(i + 1, len(working)):
            if j in to_remove:
                continue

            p_i = working[i]
            p_j = working[j]

            # 跳过太短的段落
            if len(p_i) < 15 or len(p_j) < 15:
                continue

            is_dup = False

            # 策略A: 前缀匹配（前8个非空白字符相同）
            if len(prefixes[i]) >= 8 and prefixes[i] == prefixes[j]:
                is_dup = True

            # 策略B: Bigram 相似度（Jaccard + Overlap Coefficient 双重判断）
            if not is_dup and bigrams[i] and bigrams[j]:
                intersection = len(bigrams[i] & bigrams[j])
                union = len(bigrams[i] | bigrams[j])
                min_len = min(len(bigrams[i]), len(bigrams[j]))
                if union > 0 and min_len > 0:
                    jaccard = intersection / union
                    overlap = intersection / min_len  # 重叠系数：对短段落更敏感
                    if jaccard >= similarity_threshold or overlap >= 0.35:
                        is_dup = True

            # 策略C: 公共子串 >= 5 字符
            if not is_dup:
                shorter = p_i if len(p_i) <= len(p_j) else p_j
                longer = p_j if len(p_i) <= len(p_j) else p_i
                norm_shorter = re.sub(r'\s+', '', shorter)
                norm_longer = re.sub(r'\s+', '', longer)

                if len(norm_shorter) >= 10:
                    window = 5
                    for k in range(0, len(norm_shorter) - window + 1, 2):
                        if norm_shorter[k:k + window] in norm_longer:
                            is_dup = True
                            break

            if is_dup:
                # 保留较长的，删除较短的
                if len(p_i) >= len(p_j):
                    to_remove.add(j)
                else:
                    to_remove.add(i)
                    break  # i 被删除，跳出内循环

    removed_count = len(to_remove) + sep_removed
    if removed_count == 0:
        return content, 0

    result = [p for i, p in enumerate(working) if i not in to_remove]
    separator = '\n\n' if '\n\n' in content else '\n'
    cleaned_content = separator.join(result)

    logger.info(
        f"[模糊去重] 原始{len(paragraphs)}段 → 保留{len(result)}段, "
        f"删除{len(to_remove)}段近似重复+{sep_removed}段分隔符"
    )

    return cleaned_content, removed_count


def _find_paragraph_by_offset(paragraphs: List[str], offset: int) -> int:
    """根据字符偏移量找到段落索引。"""
    pos = 0
    for i, p in enumerate(paragraphs):
        if pos + len(p) >= offset:
            return i
        pos += len(p) + 2  # +2 for \n\n separator
    return -1


def _find_paragraph_by_keyword(paragraphs: List[str], keyword: str) -> Tuple[int, int]:
    """根据关键词找到段落索引范围，返回 (start, end)。"""
    if not keyword or len(keyword) < 2:
        return -1, -1
    matches = [i for i, p in enumerate(paragraphs) if keyword in p]
    if matches:
        return matches[0], matches[-1]
    return -1, -1


def _locate_problem_paragraphs(
    content: str,
    issue: dict,
    paragraphs: Optional[List[str]] = None,
) -> Tuple[int, int, str, List[str]]:
    """定位问题段落，返回 (start, end, strategy, paragraphs)。

    定位策略（逐级降级）：
    1. 从 issue.locations 的 offset 字段精确定位
    2. 从 issue.locations 的 matched 字段关键词匹配
    3. 从 issue.word / issue.pattern 提取关键词匹配
    4. 无法定位返回 -1
    """
    if paragraphs is None:
        paragraphs = _split_paragraphs(content)
    if not paragraphs:
        return -1, -1, 'no_content', []

    # 策略1：从 locations 字段提取偏移量
    locations = issue.get('locations', [])
    if locations and isinstance(locations, list) and len(locations) > 0:
        first_loc = locations[0]
        if isinstance(first_loc, dict):
            offset = first_loc.get('offset', -1)
            if offset >= 0:
                idx = _find_paragraph_by_offset(paragraphs, offset)
                if idx >= 0:
                    # 多个位置时扩展范围
                    if len(locations) > 1:
                        last_offset = locations[-1].get('offset', offset)
                        last_idx = _find_paragraph_by_offset(paragraphs, last_offset)
                        if last_idx < 0:
                            last_idx = idx
                    else:
                        last_idx = idx
                    return idx, last_idx, 'offset_match', paragraphs

    # 策略2：从 matched 字段提取关键词
    if locations and isinstance(locations, list):
        for loc in locations:
            if isinstance(loc, dict):
                matched_text = loc.get('matched', '')
                if matched_text and len(matched_text) >= 2:
                    start, end = _find_paragraph_by_keyword(paragraphs, matched_text[:15])
                    if start >= 0:
                        return start, end, 'matched_text', paragraphs

    # 策略3：从 word / pattern 字段提取关键词
    keyword = issue.get('word', '') or issue.get('pattern', '')
    if keyword:
        # 清理正则特殊字符
        keyword_clean = re.sub(r'[\\^$.|?*+()\[\]{}]', '', str(keyword))
        if len(keyword_clean) >= 2:
            start, end = _find_paragraph_by_keyword(paragraphs, keyword_clean)
            if start >= 0:
                return start, end, 'keyword_match', paragraphs

    # 策略4：无法定位
    return -1, -1, 'not_located', paragraphs


def _build_fix_instruction(issue: dict) -> str:
    """构建修复指令。"""
    issue_type = issue.get('type', '')
    detail = ''
    if issue.get('word'):
        detail = issue['word']
    elif issue.get('pattern'):
        detail = str(issue['pattern'])[:30]
    elif issue.get('words'):
        words = issue['words']
        detail = ', '.join(words[:3]) if isinstance(words, list) else str(words)

    tpl = FIX_TEMPLATES.get(issue_type, '请重写这段文字，解决以下问题：{detail}')
    return tpl.format(detail=detail or issue.get('message', '改善文风，降低AI感'))


# ═══════════════════════════════════════════
# 局部修复核心
# ═══════════════════════════════════════════

def _is_severe_problem(issue: dict) -> bool:
    """判断是否为严重问题（不适合局部修复，需整章重写）"""
    issue_type = issue.get('type', '')
    # 工程词泄漏 >= 3 处
    if issue_type == 'engineering_word_leak':
        words = issue.get('words', [])
        if isinstance(words, list) and len(words) >= 3:
            return True
    # 重复段落 >= 3 处
    if issue_type == 'duplicate_paragraph':
        count = issue.get('count', 0)
        if count >= 3:
            return True
    return False


# 反AI模式黑名单 — 修复时必须避免的表达
_ANTI_AI_BLACKLIST = """
【绝对禁止使用的AI腔表达】（出现任何一个即判失败）
- 表情类：嘴角微扬/嘴角弯了弯/唇角微扬/嘴角勾起一抹/微微一笑/淡淡一笑/神色一凛/神色微变/面色微变/目光微动/目光一凝/目光闪了闪/眉梢一挑
- 眼神类：眸中/眸光/眸子里/眼中闪过一丝/掠过一丝/闪过一丝/划过一丝/眼中{0,4}一丝
- 动作类：缓缓开口/缓缓点头/微微颔首/深吸一口气/顿了顿/沉默片刻/沉默了一会儿/并肩而行/谁都没有再说话
- 心理类：心头一紧/心中一凛/心头微沉/心猛地一沉/心头一震/心中暗想/心中思忖/暗自思忖/不由自主/情不自禁
- 语气类：淡淡道/淡淡地说/声音里带着一丝/声音中带着/语气中带着/一丝笑意/一抹笑意/一丝复杂的
- 修仙类：一道灵光/一道光芒/一道金光/掌心蔓延/灵力波动/气息一变/气势暴涨
- 过渡类：就在这时/话音刚落/话音未落/下一秒/刹那间/一瞬间/电光火石之间/片刻后/片刻之后/短暂的沉默后/一阵沉默后/空气仿佛凝固
- 总结类：不可思议/难以置信/不容置疑/显而易见/不可否认/与此同时/由此可见/综上所述/他终于明白/她终于明白/这一刻/从此以后/新的篇章开始/命运的齿轮
- 句式类：不是…而是…/并非…而是…/不在于…而在于…/不仅仅…更是…/殊不知/多年以后/之所以…是因为
- 连接词：然而/因此/但是/不过/于是/随后/紧接着/不仅如此/事实上/实际上/换句话说/总而言之
"""

# 反AI写作指导
_ANTI_AI_GUIDE = """
【人类写作特征 — 必须体现】
1. 句子长短参差不齐：有的只有五六个字，有的三四十字，绝不能均匀
2. 用具体细节代替抽象描写：不说"气息一变"，说"他后背的汗毛竖了起来"
3. 用动作暗示情绪：不说"心中一紧"，写"他无意识地攥住了袖口"
4. 减少形容词堆砌，多用动词推进
5. 对话少用标签（说道/问道/笑道），用动作或语气自然衔接
6. 段落长度要有明显差异，不能都差不多长
7. 避免每段都用相似的结构开头
8. 用口语化、有个性的表达替代书面化模板
"""


def _strip_context_from_result(
    fixed_text: str,
    original_text: str,
    context_before: str = "",
    context_after: str = "",
) -> str:
    """从AI修复结果中剥离上下文内容，只保留目标段落的修复文本。

    AI 常见的上下文泄漏模式：
    1. 把【前文】内容也原样返回了
    2. 把【后文】内容也原样返回了
    3. 添加了"修改后的文本："等前缀标签
    4. 添加了"（修改说明：...）"等后缀解释
    5. 用 ``` 代码块包裹了输出
    6. 把原文也一并返回了（原文+修改后 或 修改后+原文）

    策略：逐层剥离，每层都做安全性检查（不能把结果剥空）。
    """
    if not fixed_text:
        return fixed_text

    result = fixed_text.strip()

    # ── 1. 剥离 markdown 代码块 ──
    # 匹配 ```text\n...\n``` 或 ```\n...\n```
    code_block = re.match(r'^```[a-zA-Z]*\s*\n(.*?)\n```\s*$', result, re.DOTALL)
    if code_block:
        result = code_block.group(1).strip()

    # ── 2. 剥离前缀标签 ──
    # 常见模式："修改后的文本：", "以下是修改后的内容：", "重写结果：", "修改后："
    prefix_patterns = [
        r'^修改后的文本[：:]\s*',
        r'^修改后[：:]\s*',
        r'^重写后的文本[：:]\s*',
        r'^重写结果[：:]\s*',
        r'^以下是修改后的内容[：:]\s*',
        r'^以下是重写后的内容[：:]\s*',
        r'^修改如下[：:]\s*',
        r'^重写如下[：:]\s*',
        r'^答[：:]\s*',
        r'^结果[：:]\s*',
    ]
    for pat in prefix_patterns:
        new_result = re.sub(pat, '', result)
        if new_result != result and len(new_result) > 20:
            result = new_result.strip()
            break

    # ── 3. 剥离后缀解释 ──
    # 常见模式："---\n修改说明：...", "（注：...）", "\n\n说明：..."
    suffix_patterns = [
        r'\n\s*[-—]{2,}\s*\n.*$',             # --- 分隔线后的解释
        r'\n\s*修改说明[：:].*$',                # 修改说明：...
        r'\n\s*注[：:].*$',                      # 注：...
        r'\n\s*说明[：:].*$',                    # 说明：...
        r'\n\s*（[^）]{10,}）\s*$',              # （较长的括号注释）
        r'\n\s*\([^)]{10,}\)\s*$',              # (longer parenthetical note)
        r'\n\s*备注[：:].*$',                    # 备注：...
    ]
    for pat in suffix_patterns:
        new_result = re.sub(pat, '', result, flags=re.DOTALL)
        if new_result != result and len(new_result) > 20:
            result = new_result.strip()

    # ── 4. 剥离引号包裹 ──
    # 如果整体被引号包裹，去掉外层引号
    if len(result) > 40:
        if (result.startswith('"') and result.endswith('"')) or \
           (result.startswith('"') and result.endswith('"')):
            inner = result[1:-1].strip()
            if len(inner) > 20:
                result = inner

    # ── 5. 剥离前文回声 ──
    # AI 可能把 context_before 的末尾几段也返回了
    if context_before:
        before_paras = _split_paragraphs(context_before)
        result_paras = _split_paragraphs(result)

        # 检查结果开头是否匹配前文的最后1-2段
        strip_count = 0
        for i in range(min(2, len(before_paras), len(result_paras))):
            # 取前文最后第(i+1)段
            before_para = before_paras[-(i + 1)].strip()
            # 在结果开头第i段中查找
            if i < len(result_paras):
                result_para = result_paras[i].strip()
                # 模糊匹配：前文段落的前30个字符出现在结果段落开头
                if len(before_para) > 15 and before_para[:30] in result_para:
                    strip_count = i + 1
                # 或者结果段落的前30个字符出现在前文段落中
                elif len(result_para) > 15 and result_para[:30] in before_para:
                    strip_count = i + 1

        if strip_count > 0:
            remaining = result_paras[strip_count:]
            if len(remaining) > 0:
                separator = '\n\n' if '\n\n' in result else '\n'
                result = separator.join(remaining)

    # ── 6. 剥离后文回声 ──
    if context_after:
        after_paras = _split_paragraphs(context_after)
        result_paras = _split_paragraphs(result)

        # 检查结果末尾是否匹配后文的前1-2段
        strip_count = 0
        for i in range(min(2, len(after_paras), len(result_paras))):
            after_para = after_paras[i].strip()
            check_idx = len(result_paras) - 1 - i
            if check_idx >= 0:
                result_para = result_paras[check_idx].strip()
                # 模糊匹配
                if len(after_para) > 15 and after_para[:30] in result_para:
                    strip_count = i + 1
                elif len(result_para) > 15 and result_para[:30] in after_para:
                    strip_count = i + 1

        if strip_count > 0:
            remaining = result_paras[:len(result_paras) - strip_count]
            if len(remaining) > 0:
                separator = '\n\n' if '\n\n' in result else '\n'
                result = separator.join(remaining)

    # ── 7. 剥离原文回声 ──
    # AI 可能把原文也返回了（原文+修改后 或 修改后+原文）
    if original_text:
        orig_paras = _split_paragraphs(original_text)
        result_paras = _split_paragraphs(result)

        if len(result_paras) > len(orig_paras) and len(orig_paras) > 0:
            # 检查开头是否匹配原文
            orig_first = orig_paras[0].strip()
            if len(orig_first) > 20 and result_paras[0].strip()[:40] == orig_first[:40]:
                # 开头匹配原文 → 剥离开头与原文等长的段落数
                strip_n = min(len(orig_paras), len(result_paras) - 1)
                remaining = result_paras[strip_n:]
                if remaining:
                    separator = '\n\n' if '\n\n' in result else '\n'
                    result = separator.join(remaining)

            # 检查末尾是否匹配原文
            elif len(result_paras) > 0:
                orig_last = orig_paras[-1].strip()
                last_result = result_paras[-1].strip()
                if len(orig_last) > 20 and last_result[:40] == orig_last[:40]:
                    strip_n = min(len(orig_paras), len(result_paras) - 1)
                    remaining = result_paras[:len(result_paras) - strip_n]
                    if remaining:
                        separator = '\n\n' if '\n\n' in result else '\n'
                        result = separator.join(remaining)

    # ── 安全检查：不能剥空 ──
    if len(result) < 10:
        # 剥离太狠了，返回原始AI输出
        logger.warning(f"[上下文剥离] 剥离后内容过短({len(result)}字)，回退到原始AI输出")
        return fixed_text.strip()

    return result


def _local_fix_paragraph(
    paragraph_text: str,
    fix_instruction: str,
    context_before: str = "",
    context_after: str = "",
    aggressive: bool = False,
) -> Tuple[Optional[str], str]:
    """局部修复单个段落，返回 (fixed_text, status_msg)。

    使用AI重写指定段落，保留前后上下文信息。
    包含长度保护：修复结果不得少于原长度的50%。
    aggressive=True 时使用更激进的重写策略。
    """
    from backend.ai_client import chat

    full_context = ""
    if context_before:
        full_context += f"【前文】\n{context_before[-300:]}\n\n"
    if context_after:
        full_context += f"【后文】\n{context_after[:300:]}\n\n"

    original_len = len(paragraph_text)
    min_accept_len = int(original_len * 0.5)

    if aggressive:
        rewrite_scope = "你可以大幅重写这段文字的措辞和句式"
        change_instruction = "大胆修改，不要害怕大改。保留核心剧情和人物关系，但措辞、句式、段落结构都应该有显著变化。"
    else:
        rewrite_scope = "针对检测到的问题进行修改"
        change_instruction = "按修复指令修改问题部分，保留无关内容。"

    prompt = f"""你是一位资深小说编辑，正在修正一段AI生成的文字，使其读起来像人类作家写的。

{fix_instruction}

{_ANTI_AI_BLACKLIST}

{_ANTI_AI_GUIDE}

【要修改的段落】
{paragraph_text}

{full_context}

修改要求：
1. {change_instruction}
2. {rewrite_scope}
3. 不要引入新设定或新角色，保持剧情不变
4. 修改后长度不能少于原长度的50%
5. 绝对不能使用上面黑名单中的任何表达
6. 必须体现人类写作特征（句子长短不一、具体细节、动作暗示情绪）
7. 只输出修改后的段落本身，不要重复前文或后文的内容
8. 直接输出修改后的文本，不要包含任何解释、标注、说明或代码块标记"""

    try:
        fixed_text = chat(
            system_prompt="你是一位有20年经验的资深小说编辑，极其擅长消除AI生成痕迹，让文字回归人类作家的自然质感。你痛恨公式化表达和模板化句式。",
            user_prompt=prompt,
            temperature=0.85,
            max_tokens=2048,
        ).strip()

        # 剥离AI返回值中的上下文泄漏（前文/后文回声、标签、解释等）
        raw_len = len(fixed_text)
        fixed_text = _strip_context_from_result(
            fixed_text, paragraph_text, context_before, context_after
        )
        if len(fixed_text) != raw_len:
            logger.info(f"[上下文剥离] AI返回{raw_len}字 → 剥离后{len(fixed_text)}字")

        if not fixed_text or len(fixed_text) < min_accept_len:
            return None, f"长度保护拒绝(原{original_len}→{len(fixed_text) if fixed_text else 0}，需>={min_accept_len})"

        # 检查修复结果是否仍包含黑名单词汇
        blacklist_hits = []
        for category_items in [
            ['嘴角微扬', '嘴角弯了弯', '唇角微扬', '嘴角勾起一抹', '神色一凛', '神色微变',
             '目光微动', '目光一凝', '目光闪了闪', '眉梢一挑',
             '眸中', '眸光', '眸子里', '眼中闪过一丝', '掠过一丝', '闪过一丝',
             '缓缓开口', '缓缓点头', '微微颔首', '深吸一口气', '顿了顿',
             '心头一紧', '心中一凛', '心头微沉', '心猛地一沉', '心头一震',
             '淡淡道', '淡淡地说', '声音里带着一丝', '声音中带着', '语气中带着',
             '一道灵光', '一道光芒', '灵力波动', '气息一变', '气势暴涨',
             '就在这时', '话音刚落', '话音未落', '下一秒', '刹那间', '一瞬间',
             '不可思议', '难以置信', '不容置疑', '显而易见',
             '他终于明白', '她终于明白', '命运的齿轮',
             '殊不知', '多年以后',
            ]
        ]:
            for word in category_items:
                if word in fixed_text:
                    blacklist_hits.append(word)

        if blacklist_hits:
            # 黑名单词命中，尝试再次清洗
            for word in blacklist_hits:
                # 直接删除或替换为空
                fixed_text = fixed_text.replace(word, '')

            logger.warning(f"[局部修复] 修复后仍含黑名单词{blacklist_hits[:5]}，已强制删除")

        return fixed_text, f"成功({len(fixed_text)}字, 黑名单命中{len(blacklist_hits)}处已清除)"
    except Exception as e:
        return None, f"异常: {str(e)[:80]}"


def _process_single_issue(
    issue: dict,
    content: str,
    paragraphs: List[str],
    dry_run: bool = False,
    aggressive: bool = False,
    fixed_fingerprints: Optional[set] = None,
) -> Tuple[str, Optional[dict], dict]:
    """处理单个问题，返回 (new_content, result_dict, status_flags)

    status_flags: dict with keys: fixed, skipped_locate, skipped_failed, skipped_severe, skipped_long, skipped_done
    aggressive: 使用激进重写策略
    fixed_fingerprints: 已修复段落的内容指纹集合，跳过这些段落避免重复修复
    """
    status_flags = {'fixed': 0, 'skipped_locate': 0, 'skipped_failed': 0, 'skipped_severe': 0, 'skipped_long': 0, 'skipped_done': 0}

    if _is_severe_problem(issue):
        status_flags['skipped_severe'] = 1
        return content, {
            'type': issue.get('type', ''),
            'message': issue.get('message', '')[:60],
            'status': 'skipped_severe',
            'reason': '严重问题，建议整章重写',
        }, status_flags

    start, end, strategy, _ = _locate_problem_paragraphs(content, issue, paragraphs)

    if start < 0 or end < 0:
        status_flags['skipped_locate'] = 1
        return content, {
            'type': issue.get('type', ''),
            'message': issue.get('message', '')[:60],
            'status': 'skipped_locate',
            'reason': '无法定位段落',
        }, status_flags

    target_text = '\n\n'.join(paragraphs[start:end + 1])

    # 跳过已修复过的段落（按内容指纹匹配，不受索引漂移影响）
    target_fp = _paragraph_fingerprint(target_text)
    if fixed_fingerprints and target_fp in fixed_fingerprints:
        status_flags['skipped_done'] = 1
        return content, {
            'type': issue.get('type', ''),
            'message': issue.get('message', '')[:60],
            'status': 'skipped_already_fixed',
            'reason': '该段落已修复过（指纹匹配），跳过避免重复',
            'paragraph_range': f'{start + 1}-{end + 1}',
        }, status_flags

    # 跳过过长的段落（>1500字建议人工处理）
    if len(target_text) > 1500:
        status_flags['skipped_long'] = 1
        return content, {
            'type': issue.get('type', ''),
            'message': issue.get('message', '')[:60],
            'status': 'skipped_too_long',
            'reason': f'定位段落过长({len(target_text)}字)',
            'paragraph_range': f'{start + 1}-{end + 1}',
        }, status_flags

    context_before = '\n\n'.join(paragraphs[max(0, start - 2):start]) if start > 0 else ''
    context_after = '\n\n'.join(paragraphs[end + 1:min(len(paragraphs), end + 3)]) if end < len(paragraphs) - 1 else ''

    if dry_run:
        return content, {
            'type': issue.get('type', ''),
            'message': issue.get('message', '')[:60],
            'status': 'located',
            'strategy': strategy,
            'paragraph_range': f'{start + 1}-{end + 1}',
            'target_len': len(target_text),
        }, status_flags

    fix_instruction = _build_fix_instruction(issue)
    fixed_text, status_msg = _local_fix_paragraph(
        target_text, fix_instruction, context_before, context_after, aggressive=aggressive
    )

    if fixed_text is None:
        status_flags['skipped_failed'] = 1
        return content, {
            'type': issue.get('type', ''),
            'message': issue.get('message', '')[:60],
            'status': 'failed',
            'reason': status_msg,
            'paragraph_range': f'{start + 1}-{end + 1}',
        }, status_flags

    new_paragraphs = paragraphs[:start] + [fixed_text] + paragraphs[end + 1:]
    new_content = '\n\n'.join(new_paragraphs)

    # 记录 FIXED 文本的指纹，供后续轮次跳过
    if fixed_fingerprints is not None:
        fixed_fingerprints.add(_paragraph_fingerprint(fixed_text))

    status_flags['fixed'] = 1
    return new_content, {
        'type': issue.get('type', ''),
        'message': issue.get('message', '')[:60],
        'status': 'fixed',
        'reason': status_msg,
        'strategy': strategy,
        'paragraph_range': f'{start + 1}-{end + 1}',
        'original_len': len(target_text),
        'fixed_len': len(fixed_text),
        'len_change': len(fixed_text) - len(target_text),
        'fingerprint': _paragraph_fingerprint(fixed_text),
    }, status_flags


# ═══════════════════════════════════════════
# 全局问题：找最差段落修复
# ═══════════════════════════════════════════

def _find_worst_paragraphs_for_global(
    paragraphs: List[str],
    issue_type: str,
    max_count: int = 1,
) -> List[int]:
    """为全局统计问题找到最需要修复的段落索引。"""
    if not paragraphs:
        return []

    if issue_type == 'low_burstiness':
        # 找句子长度最均匀的段落（CV最低）
        scores = []
        for i, p in enumerate(paragraphs):
            sentences = [s for s in re.split(r'[。！？\n]+', p) if len(s.strip()) > 2]
            if len(sentences) > 3:
                lengths = [len(s) for s in sentences]
                mean = sum(lengths) / len(lengths)
                if mean > 0:
                    cv = (sum((l - mean) ** 2 for l in lengths) / len(lengths)) ** 0.5 / mean
                    scores.append((i, cv))
        scores.sort(key=lambda x: x[1])
        return [idx for idx, _ in scores[:max_count]]

    elif issue_type == 'high_de_density':
        # 找"的"字密度最高的段落
        scores = []
        for i, p in enumerate(paragraphs):
            if len(p) > 20:
                density = p.count('的') / (len(p) / 1000)
                scores.append((i, density))
        scores.sort(key=lambda x: -x[1])
        return [idx for idx, _ in scores[:max_count]]

    elif issue_type == 'connector_overuse':
        # 找连接词最多的段落
        connectors = ['然而', '因此', '但是', '不过', '于是', '随后', '紧接着', '与此同时']
        scores = []
        for i, p in enumerate(paragraphs):
            if len(p) > 20:
                count = sum(p.count(c) for c in connectors)
                density = count / (len(p) / 1000)
                scores.append((i, density))
        scores.sort(key=lambda x: -x[1])
        return [idx for idx, _ in scores[:max_count]]

    elif issue_type == 'low_ttr':
        # 找词汇最重复的段落（TTR最低）
        scores = []
        for i, p in enumerate(paragraphs):
            chars = re.sub(r'[^\u4e00-\u9fa5]', '', p)
            if len(chars) > 50:
                bigrams = [chars[j:j+2] for j in range(len(chars) - 1)]
                ttr = len(set(bigrams)) / len(bigrams) if bigrams else 1
                scores.append((i, ttr))
        scores.sort(key=lambda x: x[1])
        return [idx for idx, _ in scores[:max_count]]

    elif issue_type in ('pattern_repetition', 'monotonous_sentence'):
        # 找句首模式最重复的段落
        scores = []
        for i, p in enumerate(paragraphs):
            sentences = [s for s in re.split(r'[。！？\n]+', p) if len(s.strip()) > 2]
            if len(sentences) > 3:
                starts = [s[:3] for s in sentences if len(s) >= 3]
                if starts:
                    repeated = sum(1 for v in Counter(starts).values() if v >= 2)
                    scores.append((i, repeated))
        scores.sort(key=lambda x: -x[1])
        return [idx for idx, _ in scores[:max_count]]

    elif issue_type == 'uniform_paragraphs':
        # 段落均匀性是全局问题，返回长度最接近平均值的段落
        if len(paragraphs) > 5:
            para_lens = [len(p) for p in paragraphs]
            mean_len = sum(para_lens) / len(para_lens)
            scores = [(i, abs(len(p) - mean_len)) for i, p in enumerate(paragraphs)]
            scores.sort(key=lambda x: x[1])  # 最接近平均值的=最均匀的
            return [idx for idx, _ in scores[:max_count]]

    return []


# ═══════════════════════════════════════════
# 主入口：基于AI味检测结果执行局部修复
# ═══════════════════════════════════════════

def local_fix_from_flavor(
    content: str,
    flavor_result: dict,
    max_fixes: int = 5,
    dry_run: bool = False,
    aggressive: bool = False,
    fixed_fingerprints: Optional[set] = None,
) -> Tuple[str, dict]:
    """基于AI味检测结果执行局部段落修复

    流程：
    1. 从检测结果中分离"可定位问题"和"全局统计问题"
    2. 优先修复可定位问题（精确定位到段落）
    3. 如有配额，修复全局问题中最差的段落
    4. 每次修复后重新分段（内容已变化）

    Args:
        content: 章节正文
        flavor_result: detect_ai_flavor() 的返回结果
        max_fixes: 最多修复的问题数量（控制Token消耗）
        dry_run: 仅定位不实际修复（用于预检）
        aggressive: 使用激进重写策略
        fixed_fingerprints: 已修复段落的内容指纹集合，传入后会跳过这些段落。
                           本函数会就地修改此集合（添加新修复段落的指纹），
                           以便调用者跨轮追踪。如需保留原始集合，请自行 copy。

    Returns:
        (fixed_content, fix_report)
    """
    if not content or len(content) < 100:
        return content, {'fixed': 0, 'results': [], 'summary': '内容过短', 'content_changed': False}

    issues = flavor_result.get('issues', [])
    if not issues:
        return content, {'fixed': 0, 'results': [], 'summary': '无问题', 'content_changed': False}

    paragraphs = _split_paragraphs(content)
    if not paragraphs:
        return content, {'fixed': 0, 'results': [], 'summary': '无法分段', 'content_changed': False}

    # 分离可定位问题和全局问题
    locatable_issues = []
    global_issues = []
    for issue in issues:
        issue_type = issue.get('type', '')
        if issue_type in LOCAL_FIXABLE_TYPES:
            locatable_issues.append(issue)
        elif issue_type in GLOBAL_STATISTICAL_TYPES:
            global_issues.append(issue)

    fix_results = []
    fixed_count = 0
    current_content = content
    current_paragraphs = paragraphs[:]
    # 就地使用传入的指纹集合，使跨轮追踪生效
    if fixed_fingerprints is None:
        fixed_fingerprints = set()
    tracked_fps = fixed_fingerprints

    # Phase 1: 优先修复可定位问题
    for issue in locatable_issues[:max_fixes * 2]:  # 多取一些，因为有些会被跳过
        if fixed_count >= max_fixes:
            break

        current_content, result, flags = _process_single_issue(
            issue, current_content, current_paragraphs, dry_run,
            aggressive=aggressive, fixed_fingerprints=tracked_fps
        )

        if result:
            fix_results.append(result)

        if flags['fixed']:
            fixed_count += 1
            # 修复后重新分段（内容已变化）
            current_paragraphs = _split_paragraphs(current_content)
            # 指纹已在 _process_single_issue 内部记录到 tracked_fps，无需手动提取

    # Phase 2: 如果还有配额，修复全局问题中最差的段落
    remaining = max_fixes - fixed_count
    if remaining > 0 and global_issues and not dry_run:
        for issue in global_issues[:remaining * 2]:  # 多取一些
            if fixed_count >= max_fixes:
                break

            issue_type = issue.get('type', '')
            worst_indices = _find_worst_paragraphs_for_global(
                current_paragraphs, issue_type, max_count=3  # 多取几个备选
            )

            for idx in worst_indices:
                if fixed_count >= max_fixes:
                    break
                if idx >= len(current_paragraphs):
                    continue

                target_text = current_paragraphs[idx]
                # 跳过已修复的段落（按指纹匹配）
                target_fp = _paragraph_fingerprint(target_text)
                if target_fp in tracked_fps:
                    continue

                if len(target_text) > 1500 or len(target_text) < 50:
                    fix_results.append({
                        'type': issue_type,
                        'message': issue.get('message', '')[:60],
                        'status': 'skipped_long',
                        'reason': f'段落长度异常({len(target_text)}字)',
                    })
                    continue

                context_before = '\n\n'.join(
                    current_paragraphs[max(0, idx - 2):idx]
                ) if idx > 0 else ''
                context_after = '\n\n'.join(
                    current_paragraphs[idx + 1:min(len(current_paragraphs), idx + 3)]
                ) if idx < len(current_paragraphs) - 1 else ''

                fix_instruction = _build_fix_instruction(issue)
                fixed_text, status_msg = _local_fix_paragraph(
                    target_text, fix_instruction, context_before, context_after,
                    aggressive=aggressive
                )

                if fixed_text:
                    current_paragraphs = (
                        current_paragraphs[:idx] + [fixed_text] + current_paragraphs[idx + 1:]
                    )
                    current_content = '\n\n'.join(current_paragraphs)
                    fixed_count += 1
                    # 记录 FIXED 文本的指纹
                    tracked_fps.add(_paragraph_fingerprint(fixed_text))
                    fix_results.append({
                        'type': issue_type,
                        'message': issue.get('message', '')[:60],
                        'status': 'fixed',
                        'reason': status_msg,
                        'strategy': 'global_worst',
                        'paragraph_range': f'{idx + 1}',
                        'original_len': len(target_text),
                        'fixed_len': len(fixed_text),
                    })
                else:
                    fix_results.append({
                        'type': issue_type,
                        'message': issue.get('message', '')[:60],
                        'status': 'failed',
                        'reason': status_msg,
                        'strategy': 'global_worst',
                        'paragraph_range': f'{idx + 1}',
                    })

    # 修复后执行模糊段落去重
    current_content, dedup_count = _fuzzy_dedup_paragraphs(current_content)
    if dedup_count > 0:
        logger.info(f"[局部修复] 模糊去重清理{dedup_count}处近似重复段落")

    content_changed = current_content != content
    skipped = len(fix_results) - fixed_count
    summary = f"局部修复完成: 修复{fixed_count}处, 跳过{skipped}处"

    logger.info(f"[局部修复] {summary} (可定位{len(locatable_issues)}, 全局{len(global_issues)})")

    return current_content, {
        'fixed': fixed_count,
        'total_issues': len(issues),
        'locatable_count': len(locatable_issues),
        'global_count': len(global_issues),
        'results': fix_results,
        'summary': summary,
        'content_changed': content_changed,
    }


def local_fix_multi_round(
    content: str,
    max_rounds: int = 5,
    max_fixes_per_round: int = 8,
    target_score: int = 20,
    target_probability: int = 25,
    force_continue: bool = True,
    apply_rules_first: bool = True,
    force: bool = False,
) -> Tuple[str, dict]:
    """深度多轮去AI味：规则清洗 + 反复AI局部修复

    完整流程：
    1. 先执行规则清洗（削"的"字、去连接词、替换AI高频词）— 不消耗Token
    2. 检测AI味，如果仍超标则进入多轮AI修复
    3. 每轮：检测→定位问题段落→AI重写→黑名单后处理→再检测
    4. 第3轮起启用激进模式（大幅重写措辞和句式）
    5. 跨轮追踪已修复段落，避免重复修复同一段
    6. force_continue=True 时即使分数不降也继续尝试不同段落
    7. force=True 时即使已达标也强制执行至少1轮修复（用于多次点击场景）

    Args:
        content: 章节正文
        max_rounds: 最多修复轮数（默认5轮）
        max_fixes_per_round: 每轮最多修复的问题数（默认8处）
        target_score: 目标AI味评分（低于此值停止）
        target_probability: 目标AI概率（低于此值停止）
        force_continue: 分数不降时是否继续尝试
        apply_rules_first: 是否先执行规则清洗

    Returns:
        (fixed_content, multi_round_report)
    """
    from .ai_detector import detect_ai_flavor
    from .de_ai_rules import apply_de_ai_postprocess, DE_DENSITY_TARGET, DE_REPLACEMENTS, \
        CONNECTOR_REPLACEMENTS, AI_WORDS_LIMIT, AI_WORDS_SYNONYMS

    if not content or len(content) < 100:
        return content, {
            'rounds': 0, 'total_fixed': 0,
            'round_reports': [], 'summary': '内容过短',
            'final_score': 0, 'final_probability': 0,
            'content_changed': False,
        }

    current_content = content
    dedup_before = 0

    # Step 0: 模糊段落去重（在任何检测/修复之前执行）
    # 这一步确保重复段落被清理，即使AI修复因分数达标而不执行
    current_content, dedup_before = _fuzzy_dedup_paragraphs(current_content)
    if dedup_before > 0:
        logger.info(f"[深度去AI味] 预去重: 清理{dedup_before}处近似重复段落")

    # 记录原始分数（去重后的基线）
    original_flavor = detect_ai_flavor(current_content)
    original_score = original_flavor.get('score', 0)
    original_prob = original_flavor.get('ai_probability', 0)

    rule_cleaned = False

    # Step 1: 规则清洗（不消耗Token）
    if apply_rules_first:
        try:
            cleaned = apply_de_ai_postprocess(
                current_content,
                de_density_target=DE_DENSITY_TARGET,
                words_limit=AI_WORDS_LIMIT,
                connector_reps=CONNECTOR_REPLACEMENTS,
                de_reps=DE_REPLACEMENTS,
                words_synonyms=AI_WORDS_SYNONYMS,
            )
            if cleaned != current_content:
                current_content = cleaned
                rule_cleaned = True
                after_rule = detect_ai_flavor(current_content)
                logger.info(
                    f"[深度去AI味] 规则清洗完成: "
                    f"评分 {original_score}→{after_rule.get('score', 0)}, "
                    f"概率 {original_prob}%→{after_rule.get('ai_probability', 0)}%"
                )
        except Exception as e:
            logger.warning(f"[深度去AI味] 规则清洗失败: {e}")

    # Step 1b: 结构扰动（只拆合段落不改文字，不耗 Token）
    # 针对外部 AIGC 检测器的“段落均匀、节奏规整”统计特征
    try:
        from .de_ai_rules import apply_structure_perturb
        perturbed = apply_structure_perturb(current_content)
        if perturbed != current_content:
            current_content = perturbed
            rule_cleaned = True
            logger.info("[深度去AI味] 结构扰动完成（长段拆分/短段合并）")
    except Exception as e:
        logger.warning(f"[深度去AI味] 结构扰动失败: {e}")

    # Step 2: 多轮AI局部修复
    round_reports = []
    total_fixed = 0
    prev_score = 999
    fixed_fingerprints = set()  # 跨轮追踪已修复段落（按内容指纹）

    for round_num in range(max_rounds):
        # 检测当前AI味
        flavor = detect_ai_flavor(current_content)
        cur_score = flavor.get('score', 0)
        cur_prob = flavor.get('ai_probability', 0)
        issue_count = len(flavor.get('issues', []))

        logger.info(
            f"[深度去AI味] 第{round_num + 1}轮: "
            f"评分={cur_score}, 概率={cur_prob}%, "
            f"问题数={issue_count}, 已修复段落={len(fixed_fingerprints)}"
        )

        # 达标则停止（force 模式不提前退出，全程继续处理）
        if cur_score <= target_score and cur_prob <= target_probability:
            if not force:
                logger.info(f"[深度去AI味] 已达标，停止")
                break
            else:
                logger.info(f"[深度去AI味] 已达标，但 force=True，继续执行")

        # 无问题可修则停止（force 模式下合成全局重写问题，避免空转）
        if issue_count == 0:
            if not force:
                logger.info(f"[深度去AI味] 无检测到问题，停止")
                break
            flavor = dict(flavor)
            flavor['issues'] = [{
                'type': 'uniform_paragraphs', 'scope': 'global',
                'message': '强制模式：全文拟人化重写',
            }]
            issue_count = 1
            logger.info("[深度去AI味] 强制模式：自家检测无问题，合成全文重写问题")

        # 分数不再下降的处理
        if round_num > 0 and cur_score >= prev_score:
            if not force_continue:
                logger.info(f"[深度去AI味] 分数不再下降({prev_score}→{cur_score})，停止")
                break
            else:
                logger.info(f"[深度去AI味] 分数未降({prev_score}→{cur_score})，强制继续尝试不同段落")

        # 第3轮起启用激进模式（force 模式全程激进）
        aggressive = force or (round_num >= 2)

        # 执行本轮局部修复
        fixed_content, fix_report = local_fix_from_flavor(
            current_content, flavor,
            max_fixes=max_fixes_per_round,
            aggressive=aggressive,
            fixed_fingerprints=fixed_fingerprints,
        )

        round_reports.append({
            'round': round_num + 1,
            'aggressive': aggressive,
            'before_score': cur_score,
            'before_probability': cur_prob,
            'issues_count': issue_count,
            'fix_report': fix_report,
        })

        if fix_report.get('content_changed', False):
            current_content = fixed_content
            total_fixed += fix_report.get('fixed', 0)
        else:
            if not force_continue:
                logger.info(f"[深度去AI味] 本轮无内容变化，停止")
                break
            else:
                logger.info(f"[深度去AI味] 本轮无内容变化，但强制继续下一轮")
                # 强制继续时不清空fixed_fingerprints，让下一轮找其他段落

        prev_score = cur_score

    # Step 3: 最终模糊去重（修复可能引入的新重复）
    current_content, dedup_after = _fuzzy_dedup_paragraphs(current_content)
    if dedup_after > 0:
        logger.info(f"[深度去AI味] 后去重: 清理{dedup_after}处近似重复段落")

    # 最终检测
    final_flavor = detect_ai_flavor(current_content)
    final_score = final_flavor.get('score', 0)
    final_prob = final_flavor.get('ai_probability', 0)

    content_changed = current_content != content

    # 判断未修改原因，供前端展示
    skipped_reason = ''
    if not content_changed:
        if final_score <= target_score and final_prob <= target_probability:
            skipped_reason = 'already_at_target'
        elif len(round_reports) == 0:
            skipped_reason = 'no_issues_found'
        else:
            skipped_reason = 'no_improvement'

    total_dedup = dedup_before + dedup_after
    summary = (
        f"深度去AI味完成: 规则清洗={'是' if rule_cleaned else '否'}, "
        f"AI修复{len(round_reports)}轮共{total_fixed}处, "
        f"模糊去重{total_dedup}处, "
        f"评分 {original_score}→{final_score}, "
        f"概率 {original_prob}%→{final_prob}%"
    )

    logger.info(f"[深度去AI味] {summary}")

    return current_content, {
        'rounds': len(round_reports),
        'total_fixed': total_fixed,
        'total_dedup': total_dedup,
        'rule_cleaned': rule_cleaned,
        'round_reports': round_reports,
        'summary': summary,
        'original_score': original_score,
        'original_probability': original_prob,
        'final_score': final_score,
        'final_probability': final_prob,
        'content_changed': content_changed,
        'skipped_reason': skipped_reason,
    }


# ═══════════════════════════════════════════
# 反外部检测全文重写
# ═══════════════════════════════════════════

_EXT_SYSTEM_PROMPT = (
    "你是一位写了十五年网络小说的职业作家，文风粗粝鲜活、节奏多变，"
    "极其厌恶AI那种顺滑、工整、四平八稳的腔调。"
    "你写的每个段落都带着人的毛边：省略、跳跃、突然的短句。"
)


# 深度反检测重写提示词（移植自书斋V66 deai-deep，实测可把外部检测降到个位数）
_DEAI_DEEP_PROMPT = """你是一位有十年经验的网文作者，请把下面的小说段落改写成反AI检测风格。

【红线】
- 每段的情节、人物动作、对话含义必须完全保留，不增不减不改剧情
- 逐段改写：输入有几段就输出几段，用换行分隔，顺序不变

【风格要求（破坏AI文本的统计指纹）】
1. 句长必须极端参差：三五个字的超短句和四十字以上的长句混用，禁止均匀的中长句
2. 多用残句、省略主语的句子、倒装（“走进来一个男人。”“安静。整个房间都安静。”）
3. 节奏突变：流畅描写到一半硬生生切断，跳到另一个细节
4. 删掉所有圆滑过渡词（然而、就在此时、只见、不禁、缓缓、一丝、一抹）
5. 对话要口语、结巴、说半句、带岔开，禁止过于工整的回答
6. 形容词减到最少，用具体动词和名词；描写带生活化的细节质感
7. 偶尔插入与主线无关的琐碎细节（小动作、环境的声音和颜色）
8. 破折号（——）每千字不超过2个
9. 字数与原文接近（上下浮动20%以内）

【输出】
直接输出改写后的段落，每段一行，不要编号，不要任何解释。
"""


def anti_external_rewrite(
    content: str,
    max_paragraphs: Optional[int] = None,
    min_para_len: int = 60,
) -> Tuple[str, dict]:
    """反外部检测全文重写（移植自书斋V66 deai-deep 算法，实测有效）

    与旧版逐段重写的区别：
    - 每 3 段一批重写全部段落（含对话短段），避免逐段稀释
    - temperature=1.05，提示词针对外部 ML 检测器的统计特征
      （句长极差/残句/节奏突变/无关琐碎细节）
    - 批次级长度闸门 50%~200%，单批失败保留原文不阻塞整体

    Args:
        content: 章节正文
        max_paragraphs: 最多处理段落数（None=全部）
        min_para_len: 已废弃（书斋算法重写全部段落），保留仅为兼容

    Returns:
        (new_content, report)
    """
    from backend.ai_client import chat

    if not content or len(content) < 100:
        return content, {'rewritten': 0, 'failed': 0, 'skipped': 0,
                         'content_changed': False, 'summary': '内容过短'}

    paragraphs = [p.strip() for p in content.split('\n') if p.strip()]
    if max_paragraphs is not None:
        paragraphs = paragraphs[:max_paragraphs]

    batch_size = 3
    rewritten_out = []
    processed = 0
    failed_paras = 0
    total_batches = (len(paragraphs) + batch_size - 1) // batch_size

    for bi, start in enumerate(range(0, len(paragraphs), batch_size)):
        batch = paragraphs[start:start + batch_size]
        batch_text = '\n'.join(batch)
        prompt = _DEAI_DEEP_PROMPT + "\n【原文段落】\n" + batch_text
        result = None
        try:
            result = chat(
                system_prompt=_EXT_SYSTEM_PROMPT,
                user_prompt=prompt,
                temperature=1.05,
                max_tokens=6000,
            )
        except Exception as e:
            logger.warning(f"[反外部检测] 批次{bi + 1}/{total_batches} AI调用异常: {str(e)[:80]}")
        if result and not result.startswith(('[错误', '[生成失败')):
            result = result.strip()
            m = re.match(r'^```(?:\w+)?\s*\n([\s\S]*?)\n```$', result)
            if m:
                result = m.group(1).strip()
            new_paras = [p.strip() for p in result.split('\n') if p.strip()]
            orig_len = sum(len(p) for p in batch)
            new_len = sum(len(p) for p in new_paras)
            # 合理性闸门：重写结果长度需在原文的 50%~200% 之间，否则回退原文
            if new_paras and orig_len > 0 and 0.5 < new_len / orig_len < 2.0:
                rewritten_out.extend(new_paras)
                processed += len(batch)
                logger.info(f"[反外部检测] 批次{bi + 1}/{total_batches} 重写成功，{len(batch)}段")
                continue
            logger.warning(f"[反外部检测] 批次{bi + 1} 结果长度异常({new_len}/{orig_len})，回退原文")
        else:
            logger.warning(f"[反外部检测] 批次{bi + 1}/{total_batches} 生成失败，保留原文")
        failed_paras += len(batch)
        rewritten_out.extend(batch)

    new_content = '\n\n'.join(rewritten_out)
    content_changed = new_content != content
    summary = f"反外部检测重写完成: 重写{processed}段, 失败{failed_paras}段, 共{len(paragraphs)}段"
    logger.info(f"[反外部检测] {summary}")

    return new_content, {
        'rewritten': processed,
        'failed': failed_paras,
        'skipped': 0,
        'content_changed': content_changed,
        'summary': summary,
    }


# 人类化重写提示词（移植自书斋V66 “去AI味”按钮，配合重复执行可降到个位数）
_HUMANIZE_PROMPT = """请将以下小说正文完全重写。不是微调，不是优化，是用完全不同的语言重新讲同一个故事。

重写规则：
1. 剧情事件、人物、对话含义保持不变
2. 但叙事视角、句子结构、用词习惯必须完全不同
3. 打乱原文的段落结构，重新组织叙事顺序
4. 用一种粗粝的、不完美的、口语化的风格重写
5. 大量使用短句、断句、省略号，但破折号（——）每千字最多用2次
6. 偶尔用方言感或非标准语法
7. 删掉冗余的修饰性形容词副词，保留必要的动词和名词
8. 对话用引号（""）或自然嵌入，不要刻意替换为破折号
9. 段落之间可以跳跃，不需要平滑过渡
10. 加入一些跟主线无关的细节描写（比如角色的小动作、环境的琐碎细节）
11. 字数跟原文接近

直接输出重写的正文。"""


def humanize_rewrite(content: str) -> Tuple[str, dict]:
    """人类化重写（移植自书斋V66 “去AI味”按钮）：全文粗粝重写，temperature=1.3

    书斋实测：反复执行此重写可将外部 AIGC 检测降到 4~5%。
    每轮产生完全不同的变体（可打乱段落顺序），逐步脱离 LLM 统计分布。
    重写结果长度异常（<50% 或 >200%）时回退原文。
    """
    from backend.ai_client import chat

    if not content or len(content) < 100:
        return content, {'success': False, 'reason': '内容过短', 'content_changed': False}

    prompt = _HUMANIZE_PROMPT + "\n\n原文：\n" + content
    try:
        result = chat(
            system_prompt=_EXT_SYSTEM_PROMPT,
            user_prompt=prompt,
            temperature=1.3,
            max_tokens=8192,
        )
    except Exception as e:
        logger.warning(f"[人类化重写] AI调用异常: {str(e)[:80]}")
        return content, {'success': False, 'reason': f'AI调用异常: {str(e)[:60]}',
                         'content_changed': False}

    if not result or result.startswith(('[错误', '[生成失败')):
        logger.warning("[人类化重写] AI返回空或错误")
        return content, {'success': False, 'reason': 'AI返回空或错误', 'content_changed': False}

    result = result.strip()
    m = re.match(r'^```(?:\w+)?\s*\n([\s\S]*?)\n```$', result)
    if m:
        result = m.group(1).strip()

    ratio = len(result) / max(len(content), 1)
    if not (0.5 <= ratio <= 2.0):
        logger.warning(f"[人类化重写] 长度异常({len(content)}→{len(result)})，回退原文")
        return content, {'success': False,
                         'reason': f'长度异常({len(content)}→{len(result)})，已回退',
                         'content_changed': False}

    logger.info(f"[人类化重写] 成功({len(content)}→{len(result)}字)")
    return result, {'success': True, 'reason': '', 'content_changed': True,
                    'original_length': len(content), 'new_length': len(result)}
