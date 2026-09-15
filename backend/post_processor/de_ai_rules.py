# -*- coding: utf-8 -*-
"""
后处理去AI腔规则配置
移植自：书斋V66 backend/post_process_rules.py

提供：
- "的"字替换规则（降低密度）
- 连接词替换规则
- AI高频词限制与同义词表
- 后处理清洗函数
"""
import re

# 1. "的"字替换规则（用于降低"的"字密度）
DE_REPLACEMENTS = [
    ('他的手', '他手'), ('她的手', '她手'), ('他的眼', '他眼'),
    ('他的脸', '他脸'), ('她的脸', '她脸'), ('他的心', '他心'),
    ('他的身', '他身'), ('她的身', '她身'), ('他的脚', '他脚'),
    ('白色的光', '白光'), ('黑色的影', '黑影'), ('蓝色的光', '蓝光'),
    ('红色的光', '红光'), ('银色的光', '银光'), ('金色的光', '金光'),
    ('微弱的光', '微光'), ('刺眼的光', '强光'),
    ('安静的', '寂静'), ('沉默的', '无声'),
    ('巨大的', '极大'), ('强烈的', '猛烈'),
    ('冰冷的', '冰冷'), ('温暖的', '温热'),
    ('熟悉的', '熟稔'), ('陌生的', '生疏'),
    ('缓慢的', '缓缓'), ('迅速的', '急速'),
    ('低沉的', '低哑'), ('尖锐的', '尖利'),
    ('古老的', '古旧'), ('年轻的', '年少'),
    ('深刻的', '深切'), ('明显的', '显著'),
    ('突然的', '骤然'), ('短暂的', '短促'),
    ('不安的', '惴惴'), ('紧张的', '绷紧'),
    ('平静的', '宁和'), ('混乱的', '纷乱'),
    ('空旷的', '空荡'), ('狭窄的', '逼仄'),
    ('的月光', '月华'), ('的阳光', '日光'),
    ('的声音', '声响'), ('的气息', '气息'),
    ('的目光', '视线'), ('的笑容', '笑意'),
    ('的身影', '身形'), ('的动作', '举动'),
    ('的感觉', '感觉'), ('的样子', '模样'),
    ('的时候', '时'), ('的地方', '处'),
    ('的话', '之言'), ('的事', '之事'),
    ('的人', '者'), ('的间', '间'),
    ('的震动', '震颤'), ('的颤栗', '战栗'),
]

# 2. 连接词替换规则
CONNECTOR_REPLACEMENTS = {
    '然而，': '但', '然而': '但', '因此，': '所以', '因此': '所以',
    '于是，': '', '于是': '', '紧接着，': '', '紧接着': '随后',
    '与此同时，': '', '与此同时': '', '事实上，': '', '事实上': '',
    '实际上，': '', '实际上': '', '换句话说，': '', '换句话说': '',
    '总而言之，': '', '总而言之': '', '综上所述，': '', '综上所述': '',
    '由此可见，': '', '由此可见': '',
}

# 3. AI高频词限制（每个词的出现次数上限）
AI_WORDS_LIMIT = {
    '突然': 1,
    '忽然': 1,
    '仿佛': 1,
    '似乎': 2,
    '不禁': 1,
    '不由得': 1,
}

# 4. AI高频词同义词替换表
AI_WORDS_SYNONYMS = {
    '突然': ['猛地', '倏地', '骤然', '陡然'],
    '忽然': ['猛然', '倏然', '骤然', '陡然'],
    '仿佛': ['宛若', '恍若', '好似'],
    '似乎': ['好像', '好似', '看样子'],
    '不禁': ['忍不住', '不由'],
    '不由得': ['忍不住', '不由'],
}

# 5. "的"字密度目标（每千字）
DE_DENSITY_TARGET = 25

# 6. 章节标题正则
CHAPTER_TITLE_PATTERN = re.compile(
    r'^(?:第[一二三四五六七八九十百千\d]+[章节卷部回]|'
    r'(?:楔子|序章|引子|终章|尾声|番外)).*$',
    re.MULTILINE
)


def apply_de_ai_postprocess(text: str,
                            de_density_target: int = None,
                            words_limit: dict = None,
                            words_synonyms: dict = None,
                            connector_reps: dict = None,
                            de_reps: list = None) -> str:
    """后处理去AI腔：对生成文本执行规则化清洗

    流程：
    1. 删除章节标题行
    2. 降低"的"字密度（逐条替换直到达标）
    3. 替换连接词
    4. 替换超限AI高频词
    5. 清空空行

    Args:
        text: 待清洗的文本
        de_density_target: "的"字密度目标/千字，默认 DE_DENSITY_TARGET
        words_limit: AI高频词限制表，默认 AI_WORDS_LIMIT
        words_synonyms: AI高频词同义词表，默认 AI_WORDS_SYNONYMS
        connector_reps: 连接词替换表，默认 CONNECTOR_REPLACEMENTS
        de_reps: "的"字替换列表，默认 DE_REPLACEMENTS

    Returns:
        清洗后的文本
    """
    if not text:
        return text

    de_density_target = de_density_target or DE_DENSITY_TARGET
    words_limit = words_limit or AI_WORDS_LIMIT
    words_synonyms = words_synonyms or AI_WORDS_SYNONYMS
    connector_reps = connector_reps or CONNECTOR_REPLACEMENTS
    de_reps = de_reps or DE_REPLACEMENTS

    # Step 1: 删除章节标题
    text = CHAPTER_TITLE_PATTERN.sub('', text)

    # Step 2: 降低"的"字密度
    char_count = len(text)
    de_count = text.count('的')
    de_density = de_count / (char_count / 1000) if char_count > 0 else 0
    if de_density > de_density_target:
        # 计算需要减少的数量
        excess = int(de_count - de_density_target * (char_count / 1000))
        replaced = 0
        # 2a. 先用 DE_REPLACEMENTS 逐条替换
        for old, new in de_reps:
            while old in text and replaced < excess:
                text = text.replace(old, new, 1)
                replaced += 1
            if replaced >= excess:
                break
        # 2b. "之"字回退已禁用——现代网文不应大量使用"之"替代"的"，
        # 这会制造不自然的文言腔调，反而增加AI检测风险。
        # 如果 DE_REPLACEMENTS 不足以降到目标密度，保持原样即可。

    # Step 3: 替换连接词
    for old, new in connector_reps.items():
        if old in text:
            text = text.replace(old, new)

    # Step 4: 替换超限AI高频词（顺序替换，保留首次出现）
    for word, limit in words_limit.items():
        actual = text.count(word)
        if actual > limit:
            synonyms = words_synonyms.get(word, [word])
            if synonyms:
                excess = actual - limit
                idx = 0
                # 跳过前 limit 个（保留），替换后面的
                skip = limit
                search_start = 0
                for _ in range(excess):
                    pos = text.find(word, search_start)
                    if pos < 0:
                        break
                    # 跳过前 skip 个
                    if skip > 0:
                        skip -= 1
                        search_start = pos + len(word)
                        continue
                    syn = synonyms[idx % len(synonyms)]
                    text = text[:pos] + syn + text[pos+len(word):]
                    search_start = pos + len(syn)
                    idx += 1

    # Step 5: 去除重复段落（结构性清洗）
    text = _remove_duplicate_paragraphs(text)

    # Step 6: 清空空行
    lines = text.split('\n')
    cleaned = []
    prev_empty = False
    for line in lines:
        is_empty = not line.strip()
        if is_empty and prev_empty:
            continue
        cleaned.append(line)
        prev_empty = is_empty
    text = '\n'.join(cleaned)

    return text.strip()


def _remove_duplicate_paragraphs(text: str) -> str:
    """去除高度重复的段落。

    当AI生成出模板化的重复内容（如"片刻之后，某处，X遇到了Y"反复出现），
    只保留首次出现的段落，删除后续重复或近乎重复的段落。
    """
    paragraphs = text.split('\n')
    seen = set()
    result = []
    for para in paragraphs:
        stripped = para.strip()
        if not stripped:
            result.append(para)
            continue
        # 用前30字作为去重键（足够区分模板化重复，又不会误删正常段落）
        key = stripped[:30]
        if key in seen:
            continue
        seen.add(key)
        result.append(para)
    return '\n'.join(result)


def detect_structural_issues(text: str) -> dict:
    """检测后处理无法修复的结构性问题。

    返回包含以下字段的字典：
    - has_issues: 是否存在结构性问题
    - issues: 问题列表
    - severity: 严重程度 (critical/moderate/minor)
    - should_regenerate: 是否建议重新生成

    这些问题无法通过词语替换修复，需要重新生成正文。
    """
    if not text or len(text) < 100:
        return {'has_issues': True, 'issues': ['文本过短'], 'severity': 'critical',
                'should_regenerate': True}

    issues = []
    severity = 'minor'

    char_count = len(text)

    # 1. 文本过短（正常章节应在2000字以上）
    if char_count < 800:
        issues.append(f'正文过短({char_count}字)，远低于正常章节长度')
        severity = 'critical'

    # 2. 重复段落检测
    paragraphs = [p.strip() for p in text.split('\n') if len(p.strip()) > 20]
    if len(paragraphs) > 3:
        seen_prefixes = {}
        duplicate_count = 0
        for p in paragraphs:
            prefix = p[:25]
            if prefix in seen_prefixes:
                duplicate_count += 1
            seen_prefixes[prefix] = True
        if duplicate_count >= 3:
            issues.append(f'高度重复段落({duplicate_count}处)，疑似模板化输出')
            severity = 'critical'

    # 3. 句首模式重复检测
    import re as _re
    sentences = [s.strip() for s in _re.split(r'[。！？\n]+', text) if len(s.strip()) > 3]
    if len(sentences) > 10:
        from collections import Counter
        starts = [s[:4] for s in sentences if len(s) >= 4]
        start_counter = Counter(starts)
        for prefix, count in start_counter.items():
            if count >= 5:
                issues.append(f'句首模式重复: "{prefix}…" 出现{count}次')
                if severity != 'critical':
                    severity = 'moderate'

    # 4. 碰撞摘要泄漏检测（非叙事内容）
    collision_patterns = [
        r'片刻之后[，,]某处',
        r'两道气息同时爆发',
        r'变了脸色——对方的功法恰好克制',
        r'也不是第一次被人逼到墙角',
    ]
    collision_hits = 0
    for pattern in collision_patterns:
        matches = _re.findall(pattern, text)
        if len(matches) >= 3:
            collision_hits += len(matches)
    if collision_hits >= 5:
        issues.append(f'碰撞摘要泄漏({collision_hits}处)，正文非叙事内容')
        severity = 'critical'

    # 5. 对话格式混乱检测（同时存在 "" 和 「」 引号）
    has_double_quote = bool(_re.search(r'["\u201c\u201d].*?["\u201c\u201d]', text))
    has_angle_quote = bool(_re.search(r'[\u300c\u300e].*?[\u300d\u300f]', text))
    if has_double_quote and has_angle_quote:
        angle_count = len(_re.findall(r'[\u300c\u300e]', text))
        if angle_count >= 3:
            issues.append(f'引号格式混乱: 同时存在 "" 和 「」 引号({angle_count}处)')
            if severity != 'critical':
                severity = 'moderate'

    should_regenerate = severity == 'critical' or len(issues) >= 2

    return {
        'has_issues': len(issues) > 0,
        'issues': issues,
        'severity': severity,
        'should_regenerate': should_regenerate,
    }


# ═══════════════════════════════════════════
# 结构扰动：只调整段落结构，零内容修改
# ═══════════════════════════════════════════

import random as _random

_SENTENCE_BOUNDARY = re.compile(r'[。！？…]+')


def apply_structure_perturb(text: str, seed=None) -> str:
    """结构扰动清洗（不耗 Token，不改任何文字）

    外部 AIGC 检测器对“段落长度均匀、节奏规整”极其敏感。
    本函数只移动换行符，制造参差的段落长度分布：
    1. 长段落（>160字）在中间附近的句界处拆成两段
    2. 相邻的超短非对话段落合并，拉开长短差距
    内容字符（忽略空白）完全不变，对剧情零风险。
    """
    if not text or len(text) < 100:
        return text

    rng = _random.Random(seed)
    paragraphs = [p.strip() for p in re.split(r'\n+', text) if p.strip()]
    if len(paragraphs) < 4:
        return text

    # Pass 1: 拆长段（在 30%~70% 区间找最近的句界）
    expanded = []
    for p in paragraphs:
        if len(p) > 160 and rng.random() < 0.75:
            lo, hi = int(len(p) * 0.3), int(len(p) * 0.7)
            best = None
            for m in _SENTENCE_BOUNDARY.finditer(p):
                if lo <= m.end() <= hi:
                    best = m
            if best:
                head, tail = p[:best.end()].strip(), p[best.end():].strip()
                if len(head) >= 30 and len(tail) >= 30:
                    expanded.extend([head, tail])
                    continue
        expanded.append(p)

    # Pass 2: 合并相邻超短非对话段（对话行保持独立）
    def _is_dialogue(p):
        return p[:1] in ('“', '「', '"', '『')

    merged = []
    i = 0
    while i < len(expanded):
        cur = expanded[i]
        nxt = expanded[i + 1] if i + 1 < len(expanded) else None
        if (nxt is not None and len(cur) < 45 and len(nxt) < 45
                and not _is_dialogue(cur) and not _is_dialogue(nxt)
                and rng.random() < 0.6):
            merged.append(cur + nxt)
            i += 2
        else:
            merged.append(cur)
            i += 1

    result = '\n\n'.join(merged)
    # 安全校验：文字内容（去空白）必须完全一致，否则回滚
    if re.sub(r'\s', '', result) != re.sub(r'\s', '', text):
        return text
    return result
