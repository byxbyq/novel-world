"""AI检测核心 — AI味检测/评分/常量"""
# -*- coding: utf-8 -*-
"""
AI味检测 + 战力崩坏检测 + 文风指纹 + 6项扩展审计
移植自：书斋V66 backend/services/audit.py

核心能力（纯规则/统计，不消耗Token）：
1. detect_ai_flavor: AI味统计特征+规则双轨检测
2. compute_ai_score: 7Gate加权综合评分
3. detect_power_collapse: 战力崩坏检测
4. run_extended_audit: 综合审计（AI味+战力+6项扩展+伏笔）
5. extract_style_fingerprint: 文风指纹提取
6. compare_style_fingerprint: 文风偏离度对比
"""
import re
import math
import time
import logging
from typing import List, Dict, Tuple, Optional
from collections import Counter

logger = logging.getLogger(__name__)



def _line_number(content: str, pos: int) -> int:
    return content[:pos].count('\n') + 1


def _paragraph_index(content: str, pos: int) -> int:
    text_before = content[:pos]
    paras = [p for p in text_before.split('\n') if p.strip()]
    return len(paras)


def _context_snippet(content: str, pos: int, span: int = 20) -> str:
    start = max(0, pos - span)
    end = min(len(content), pos + span)
    return content[start:end].replace('\n', ' ')


def _find_all_positions(content: str, pattern: str) -> List[Dict]:
    locations = []
    for m in re.finditer(pattern, content):
        pos = m.start()
        locations.append({
            'line': _line_number(content, pos),
            'offset': pos,
            'matched': m.group(),
            'context': _context_snippet(content, pos)
        })
    return locations


def _find_word_positions(content: str, word: str) -> List[Dict]:
    locations = []
    start = 0
    lw = len(word)
    while True:
        idx = content.find(word, start)
        if idx == -1:
            break
        locations.append({
            'line': _line_number(content, idx),
            'offset': idx,
            'matched': word,
            'context': _context_snippet(content, idx)
        })
        start = idx + lw
    return locations


AI_BUZZWORDS = {
    '忽然': 3, '突然': 3, '竟然': 2, '不禁': 2, '仿佛': 3,
    '似乎': 4, '不由得': 2, '莫名地': 1, '不知为何': 1,
    '一股暖流': 0, '心头一震': 0, '倒吸一口凉气': 1,
    '瞳孔放大': 0, '嘴角微微': 1, '微微一笑': 1,
    '眼中闪过一丝': 0, '攥紧拳头': 1,
    '深吸一口气': 0, '缓缓开口': 0, '嘴角勾起一抹': 0,
    '如寒冰般': 0, '命运的齿轮': 0, '心猛地一沉': 0,
    '眼神复杂': 0, '深刻变化': 0, '踏上新的旅程': 0,
    '不容置疑': 1, '显而易见': 1, '不可否认': 1,
    '与此同时': 2, '由此可见': 1, '综上所述': 0,
    # ── 扩充：AI古风/玄幻高频表达 ──
    '嘴角弯了弯': 0, '嘴角微扬': 0, '唇角微扬': 0,
    '神色一凛': 0, '神色微变': 0, '面色微变': 0,
    '眸中': 2, '眸光': 2, '眸子里': 2,
    '掠过一丝': 0, '闪过一丝': 0, '划过一丝': 0,
    '顿了顿': 1, '沉默片刻': 1, '沉默了一会儿': 1,
    '并肩而行': 1, '谁都没有再说话': 0,
    '目光微动': 0, '目光一凝': 0, '目光闪了闪': 0,
    '眉梢一挑': 0, '眉毛微挑': 0,
    '声音里带着一丝': 0, '声音中带着': 0, '语气中带着': 0,
    '一丝笑意': 1, '一抹笑意': 1, '一丝复杂的': 0,
    '自顾自': 1, '不再说话': 1,
    '心头一紧': 0, '心中一凛': 0, '心头微沉': 0,
    '微微颔首': 0, '缓缓点头': 0,
    '淡淡道': 1, '淡淡地说': 1, '淡淡一笑': 1,
    '心中暗想': 1, '心中思忖': 1, '暗自思忖': 1,
    '不由自主': 1, '情不自禁': 1,
    '一道灵光': 0, '一道光芒': 0, '一道金光': 0,
    '掌心蔓延': 0, '灵力波动': 0,
    '气息一变': 0, '气势暴涨': 0,
    '不可思议': 1, '难以置信': 1,
    '一字一句': 1, '一字一顿': 1,
}

FORMULAIC_TRANSITIONS = [
    r'就在这时[，,]',
    r'话音刚落[，,]',
    r'话音未落[，,]',
    r'还没等.{1,6}反应',
    r'下一秒[，,]',
    r'刹那间[，,]',
    r'一瞬间[，,]',
    r'电光火石之间',
    # 扩充
    r'片刻后[，,]',
    r'片刻之后[，,]',
    r'沉默片刻[，,]',
    r'短暂的沉默后[，,]',
    r'一阵沉默后[，,]',
    r'空气仿佛凝固[，,]?',
    r'气氛变得[，,]',
    r'还没等.{1,8}说完',
]

NARRATOR_OVERREACH = [
    r'这证明了[，,]?',
    r'这意味着[，,]?',
    r'这说明了[，,]?',
    r'不难看出[，,]?',
    r'显然[，,]',
    r'毫无疑问[，,]',
    r'不言而喻[，,]',
    r'可想而知[，,]',
]

PLASTIC_PATTERNS = [
    r'[，,].{2,8}[，,].{2,8}[，,].{2,8}[。.]',
]

# Gate B: 否定铺垫句式
NEGATIVE_PIVOT_PATTERNS = [
    r'不是.{1,12}[，,].{0,4}而是',
    r'并非.{1,12}[，,].{0,4}而是',
    r'不在于.{1,12}[，,].{0,4}而在于',
    r'不仅仅.{1,12}[，,].{0,4}更是',
]

# Gate B: 万能状语句式
FORMULAIC_MODIFIER_PATTERNS = [
    r'[，,].{0,6}带着',
    r'声音不大[，,].{0,6}却',
    r'声音不大[，,].{0,6}但',
    # 扩充
    r'声音里带着一丝',
    r'声音中带着',
    r'语气中带着',
    r'语气里带着',
    r'眼中.{0,4}一丝',
    r'眸中.{0,4}一丝',
    r'目光中.{0,4}一丝',
]

# Gate E: 对话标签
DIALOGUE_TAGS = ['说道', '问道', '笑道', '喊道', '叫道', '答道',
                 '怒道', '冷道', '叹道', '低声道', '低声说', '大声说', '轻声说',
                 # 扩充
                 '开口道', '回道', '应道', '淡淡道', '沉声道',
                 '冷声道', '轻声道', '缓缓道', '沉声说', '冷声说']

# Gate F: 结尾升华句式
SUBLIMATION_PATTERNS = [
    r'这一切都说明',
    r'他终于明白',
    r'她终于明白',
    r'新的篇章开始',
    r'这一刻[，,]',
    r'从此以后[，,]',
    r'他知道[，,].{2,20}的意义',
    r'她知道[，,].{2,20}的意义',
    r'在那一瞬间[，,].{2,10}明白了',
]

# Gate G: 解释腔/上帝感
GOD_VIEW_PATTERNS = [
    r'她不知道的是',
    r'他不知道的是',
    r'殊不知[，,]',
    r'多年以后[，,]',
    r'之所以.{1,20}是因为',
    r'原来.{1,15}竟然',
    r'仿佛预示着',
    r'仿佛在宣判',
    r'演得真好',
    r'这出戏她看过',
    r'他就是这样',
]

# 退化检测
ENGINEERING_WORDS = [
    'placeholder', 'TODO', 'FIXME', 'lorem ipsum',
    '此处省略', '占位符', '待补充内容',
    '生成的', '作为一个AI', '我无法',
    '请注意', '总结如下', '以下内容',
]


def detect_ai_flavor(content: str) -> Dict:
    """AI味检测 - 统计特征分析 + 规则检测"""
    if not content or len(content) < 100:
        return {'score': 0, 'level': 'clean', 'issues': [], 'summary': 'content too short',
                'stats': {}, 'ai_probability': 0}

    char_count = len(content)
    scale = max(char_count / 3000.0, 1.0)
    issues = []
    total_deduction = 0

    raw_sentences = re.split(r'[。！？\n]+', content)
    sentences = [s.strip() for s in raw_sentences if len(s.strip()) > 2]
    sentence_lengths = [len(s) for s in sentences]
    n_sentences = len(sentence_lengths)

    # A1. 突发性
    burstiness_score = 0
    mean_len = 0
    cv = 0
    if n_sentences > 10:
        mean_len = sum(sentence_lengths) / n_sentences
        variance = sum((l - mean_len) ** 2 for l in sentence_lengths) / n_sentences
        std_dev = math.sqrt(variance)
        cv = std_dev / mean_len if mean_len > 0 else 0
        if cv < 0.3:
            burstiness_score = 25
            issues.append({'type': 'low_burstiness', 'cv': round(cv, 3),
                           'scope': 'global', 'message': f'句子长度过于均匀(变异系数{cv:.2f})，AI特征明显'})
        elif cv < 0.45:
            burstiness_score = 15
            issues.append({'type': 'low_burstiness', 'cv': round(cv, 3),
                           'scope': 'global', 'message': f'句子长度较均匀(变异系数{cv:.2f})，偏AI风格'})
        elif cv < 0.6:
            burstiness_score = 7
    total_deduction += burstiness_score

    # A2. 词汇多样性
    ttr = 0
    chars_clean = re.sub(r'[^\u4e00-\u9fa5a-zA-Z]', '', content)
    if len(chars_clean) > 200:
        bigrams = [chars_clean[i:i+2] for i in range(len(chars_clean) - 1)]
        ttr = len(set(bigrams)) / len(bigrams) if bigrams else 0
        if ttr < 0.45:
            total_deduction += 15
            issues.append({'type': 'low_ttr', 'ttr': round(ttr, 3), 'scope': 'global',
                           'message': f'词汇多样性低(2-gram TTR={ttr:.2f})，用词重复率高'})
        elif ttr < 0.50:
            total_deduction += 8
            issues.append({'type': 'low_ttr', 'ttr': round(ttr, 3), 'scope': 'global',
                           'message': f'词汇多样性偏低(2-gram TTR={ttr:.2f})'})

    # A3. 段落均匀性
    paragraphs = [p.strip() for p in content.split('\n') if len(p.strip()) > 20]
    para_cv = 0
    if len(paragraphs) > 5:
        para_lens = [len(p) for p in paragraphs]
        para_mean = sum(para_lens) / len(para_lens)
        para_cv = math.sqrt(sum((l - para_mean) ** 2 for l in para_lens) / len(para_lens)) / para_mean if para_mean > 0 else 0
        if para_cv < 0.25:
            total_deduction += 12
            issues.append({'type': 'uniform_paragraphs', 'cv': round(para_cv, 3),
                           'scope': 'global', 'message': f'段落长度过于均匀(变异系数{para_cv:.2f})，AI排版特征'})
        elif para_cv < 0.40:
            total_deduction += 6

    # A4. 句式重复
    if n_sentences > 15:
        starts = [s[:3] for s in sentences if len(s) >= 3]
        start_counter = Counter(starts)
        repeated = sum(1 for v in start_counter.values() if v >= 3)
        if repeated >= 3:
            top = start_counter.most_common(1)[0]
            total_deduction += 10
            issues.append({'type': 'pattern_repetition', 'scope': 'global',
                           'message': f'句首模式重复过多，"({top[0]})…"出现{top[1]}次'})
        elif repeated >= 2:
            total_deduction += 5

    # A5. 连接词密度
    connectors = ['然而', '因此', '但是', '不过', '于是', '随后', '紧接着',
                  '与此同时', '不仅如此', '事实上', '实际上', '换句话说',
                  '总而言之', '综上所述', '由此可见']
    connector_count = sum(content.count(c) for c in connectors)
    connector_density = connector_count / (char_count / 1000)
    if connector_density > 5:
        ded = min(12, int((connector_density - 5) * 3))
        total_deduction += ded
        issues.append({'type': 'connector_overuse', 'count': connector_count,
                       'density': round(connector_density, 1), 'scope': 'global',
                       'message': f'连接词密度过高({connector_density:.1f}/千字)，AI行文特征'})

    # A6. 的字密度
    de_count = content.count('的')
    de_density = de_count / (char_count / 1000)
    if de_density > 35:
        ded = min(10, int((de_density - 35) * 1.5))
        total_deduction += ded
        issues.append({'type': 'high_de_density', 'density': round(de_density, 1),
                       'scope': 'global', 'message': f'"的"字密度过高({de_density:.1f}/千字)，AI行文特征'})

    # B1. Buzzword
    for word, max_per_3k in AI_BUZZWORDS.items():
        count = content.count(word)
        if count == 0:
            continue
        allowed = max_per_3k * scale
        locations = _find_word_positions(content, word)
        if max_per_3k == 0 and count > 0:
            deduction = min(15, 5 + count * 3)
            issues.append({'type': 'buzzword_forbidden', 'word': word, 'count': count,
                           'locations': locations,
                           'message': f'[forbidden] word "{word}" appears {count} times'})
            total_deduction += deduction
        elif count > allowed:
            excess = int(count - allowed)
            deduction = min(10, excess * 2)
            issues.append({'type': 'buzzword_density', 'word': word, 'count': count,
                           'limit': int(allowed), 'locations': locations,
                           'message': f'word "{word}" appears {count} times (limit {int(allowed)})'})
            total_deduction += deduction

    # B2. Formulaic transitions
    transition_count = 0
    all_transition_locs = []
    for pattern in FORMULAIC_TRANSITIONS:
        locs = _find_all_positions(content, pattern)
        if locs:
            transition_count += len(locs)
            all_transition_locs.extend(locs)
            if len(locs) > 1:
                issues.append({'type': 'formulaic_transition', 'pattern': pattern,
                               'count': len(locs), 'locations': locs,
                               'message': f'formulaic transition repeated {len(locs)} times'})
                total_deduction += min(5, len(locs) * 2)
    if transition_count > 3 * scale:
        issues.append({'type': 'transition_overuse', 'count': transition_count,
                       'locations': all_transition_locs,
                       'message': f'total formulaic transitions: {transition_count}, density too high'})
        total_deduction += 5

    # B3. Narrator overreach
    overreach_count = 0
    for pattern in NARRATOR_OVERREACH:
        locs = _find_all_positions(content, pattern)
        if locs:
            overreach_count += len(locs)
            issues.append({'type': 'narrator_overreach',
                           'pattern': locs[0]['matched'] if locs else pattern,
                           'count': len(locs), 'locations': locs,
                           'message': f'narrator overreach: draws conclusion for reader'})
            total_deduction += min(8, len(locs) * 3)

    # B4. Plastic prose
    plastic_count = 0
    all_plastic_locs = []
    for pattern in PLASTIC_PATTERNS:
        locs = _find_all_positions(content, pattern)
        if locs:
            plastic_count += len(locs)
            all_plastic_locs.extend(locs)
    if plastic_count > 5 * scale:
        issues.append({'type': 'plastic_prose', 'count': plastic_count,
                       'locations': all_plastic_locs,
                       'message': f'parallel/antithesis patterns: {plastic_count}, too uniform'})
        total_deduction += 5

    # B5. Monotonous sentence starts
    if n_sentences > 10:
        same_start = sum(1 for i in range(1, n_sentences)
                         if sentences[i][:2] == sentences[i-1][:2])
        if same_start > n_sentences * 0.2:
            ratio = round(same_start / n_sentences, 2)
            issues.append({'type': 'monotonous_sentence', 'count': same_start,
                           'ratio': ratio, 'scope': 'global',
                           'message': f'{same_start} consecutive sentences with same start ({int(ratio*100)}%)'})
            total_deduction += 5

    # Gate B: 否定铺垫
    negative_pivot_count = 0
    for pattern in NEGATIVE_PIVOT_PATTERNS:
        locs = _find_all_positions(content, pattern)
        if locs:
            negative_pivot_count += len(locs)
            issues.append({'type': 'negative_pivot', 'gate': 'B',
                           'pattern': locs[0]['matched'][:20] if locs else pattern,
                           'count': len(locs), 'locations': locs,
                           'message': f'Gate B 否定铺垫句式: 出现{len(locs)}次'})
            total_deduction += min(10, len(locs) * 4)

    # Gate B: 万能状语
    for pattern in FORMULAIC_MODIFIER_PATTERNS:
        locs = _find_all_positions(content, pattern)
        if len(locs) > 2:
            issues.append({'type': 'formulaic_modifier', 'gate': 'B', 'pattern': pattern,
                           'count': len(locs), 'locations': locs,
                           'message': f'Gate B 万能状语: 出现{len(locs)}次'})
            total_deduction += min(6, len(locs) * 2)

    # Gate E: 对话标签密度
    dialogue_sentences = re.findall(r'[""「」『』].*?[""「」『』]', content)
    dialogue_tag_count = 0
    for tag in DIALOGUE_TAGS:
        locs = _find_word_positions(content, tag)
        if locs:
            dialogue_tag_count += len(locs)
    if dialogue_sentences and len(dialogue_sentences) > 5:
        dialogue_tag_ratio = dialogue_tag_count / len(dialogue_sentences)
        if dialogue_tag_ratio > 0.5:
            issues.append({'type': 'dialogue_tag_density', 'gate': 'E',
                           'count': dialogue_tag_count,
                           'ratio': round(dialogue_tag_ratio, 2),
                           'message': f'Gate E 对话标签密度过高({int(dialogue_tag_ratio*100)}%)'})
            total_deduction += min(10, int((dialogue_tag_ratio - 0.5) * 20))

    # Gate F: 结尾升华
    sublimation_count = 0
    for pattern in SUBLIMATION_PATTERNS:
        locs = _find_all_positions(content, pattern)
        if locs:
            sublimation_count += len(locs)
    if sublimation_count > 0:
        issues.append({'type': 'sublimation_ending', 'gate': 'F',
                       'count': sublimation_count,
                       'message': f'Gate F 结尾升华: 检测到{sublimation_count}处'})
        total_deduction += min(8, sublimation_count * 3)

    # Gate G: 上帝视角
    god_view_count = 0
    for pattern in GOD_VIEW_PATTERNS:
        locs = _find_all_positions(content, pattern)
        if locs:
            god_view_count += len(locs)
            issues.append({'type': 'god_view', 'gate': 'G',
                           'pattern': locs[0]['matched'][:20] if locs else pattern,
                           'count': len(locs),
                           'message': f'Gate G 解释腔/上帝感: 出现{len(locs)}次'})
            total_deduction += min(12, len(locs) * 4)

    # 退化检测
    engineering_hits = []
    for word in ENGINEERING_WORDS:
        locs = _find_word_positions(content, word)
        if locs:
            engineering_hits.append(word)
    if engineering_hits:
        issues.append({'type': 'engineering_word_leak', 'gate': 'degeneration',
                       'words': engineering_hits, 'count': len(engineering_hits),
                       'message': f'退化检测: 工程词泄漏 {", ".join(engineering_hits[:3])}'})
        total_deduction += min(20, len(engineering_hits) * 8)

    # 退化检测: 重复段落
    if len(paragraphs) > 3:
        seen_paras = set()
        duplicate_paras = []
        for p in paragraphs:
            p_key = p[:50]
            if p_key in seen_paras and len(p) > 30:
                duplicate_paras.append(p[:30])
            seen_paras.add(p_key)
        if duplicate_paras:
            issues.append({'type': 'duplicate_paragraph', 'gate': 'degeneration',
                           'count': len(duplicate_paras),
                           'message': f'退化检测: 逐字复读段落 {len(duplicate_paras)}处'})
            total_deduction += min(15, len(duplicate_paras) * 5)

    # Part C: 综合评分
    score = min(100, total_deduction)

    # 估算AI概率
    ai_prob = 0
    if n_sentences > 10 and cv > 0:
        if cv < 0.3: ai_prob += 40
        elif cv < 0.4: ai_prob += 25
        elif cv < 0.5: ai_prob += 15
        elif cv < 0.6: ai_prob += 5
    if ttr > 0:
        if ttr < 0.45: ai_prob += 25
        elif ttr < 0.50: ai_prob += 15
        elif ttr < 0.55: ai_prob += 8
    if para_cv > 0:
        if para_cv < 0.25: ai_prob += 15
        elif para_cv < 0.35: ai_prob += 8
    if connector_density > 5: ai_prob += 10
    if de_density > 35: ai_prob += 8
    ai_prob = min(99, ai_prob)

    if score == 0:
        level = 'clean'
    elif score <= 15:
        level = 'minor'
    elif score <= 35:
        level = 'moderate'
    else:
        level = 'heavy'

    if ai_prob >= 70:
        ai_level = 'high'
    elif ai_prob >= 40:
        ai_level = 'medium'
    elif ai_prob >= 20:
        ai_level = 'low'
    else:
        ai_level = 'minimal'

    summary = f'AI味评分: {score}/100 ({level})'
    summary += f' | 预估AI概率: {ai_prob}% ({ai_level})'

    return {
        'score': score, 'level': level,
        'ai_probability': ai_prob, 'ai_level': ai_level,
        'issues': issues, 'summary': summary,
        'stats': {
            'burstiness_cv': round(cv, 3) if n_sentences > 10 else 0,
            'ttr': round(ttr, 3) if len(chars_clean) > 200 else 0,
            'para_cv': round(para_cv, 3) if len(paragraphs) > 5 else 0,
            'connector_density': round(connector_density, 1),
            'de_density': round(de_density, 1),
            'sentence_count': n_sentences,
            'avg_sentence_len': round(mean_len, 1) if n_sentences > 0 else 0,
            'buzzword_total': sum(1 for i in issues if 'buzzword' in i.get('type', '')),
            'transition_total': transition_count,
            'overreach_total': overreach_count,
            'plastic_total': plastic_count,
            'negative_pivot_total': negative_pivot_count,
            'dialogue_tag_ratio': round(dialogue_tag_count / len(dialogue_sentences), 2)
                if dialogue_sentences and len(dialogue_sentences) > 5 else 0,
            'sublimation_total': sublimation_count,
            'god_view_total': god_view_count,
            'gate_b_hits': (negative_pivot_count +
                           sum(1 for i in issues if i.get('type') == 'formulaic_modifier')),
            'gate_e_hits': sum(1 for i in issues if i.get('gate') == 'E'),
            'gate_f_hits': sublimation_count,
            'gate_g_hits': god_view_count,
        }
    }


def compute_ai_score(ai_result: Dict) -> Dict:
    """聚合降熵评分：基于7个Gate检测结果计算加权综合AI概率

    权重分配：TTR×0.3 + 禁用词×0.25 + 公式化句式×0.2 + 工程词×0.1
            + 上帝视角×0.05 + 结尾升华×0.05 + 否定铺垫×0.05
    """
    stats = ai_result.get('stats', {})

    ttr = stats.get('ttr', 0.5)
    ttr_score = max(0, min(100, int((0.6 - ttr) * 250)))

    buzzword_total = stats.get('buzzword_total', 0)
    buzzword_score = min(100, buzzword_total * 12)

    transition_total = stats.get('transition_total', 0)
    formulaic_score = min(100, transition_total * 8)

    gate_degen = stats.get('gate_degen_hits', 0)
    eng_score = min(100, gate_degen * 25)

    gate_g = stats.get('gate_g_hits', 0)
    god_score = min(100, gate_g * 20)

    gate_f = stats.get('gate_f_hits', 0)
    sublim_score = min(100, gate_f * 25)

    gate_b = stats.get('gate_b_hits', 0)
    neg_score = min(100, gate_b * 15)

    score = int(
        ttr_score * 0.30 +
        buzzword_score * 0.25 +
        formulaic_score * 0.20 +
        eng_score * 0.10 +
        god_score * 0.05 +
        sublim_score * 0.05 +
        neg_score * 0.05
    )
    score = min(100, score)

    level = 'low' if score <= 20 else ('medium' if score <= 50 else 'high')

    return {'ai_score': score, 'ai_level': level}


REALM_HIERARCHY = [
    '凡人', '觉醒', '入门', '初级', '中级', '高级',
    '超凡', '蜕变', '蜕变期', '入微', '化境', '巅峰',
    '仙', '神', '圣', '至尊', '创世', '归零',
]


RHETORICAL_PATTERNS_ZH = [
    {'name': '比喻(像/如/仿佛)', 'regex': r'[像如仿佛似](?:是|同|一般|一样)'},
    {'name': '排比', 'regex': r'[，。；]([^，。；]{2,6})[，。；]\1'},
    {'name': '反问', 'regex': r'难道|怎么可能|岂不是|何尝不'},
    {'name': '夸张', 'regex': r'天崩地裂|惊天动地|翻天覆地|震耳欲聋'},
    {'name': '拟人', 'regex': r'[风雨雪月花树草石](?:在|像|仿佛).*?(?:笑|哭|叹|呻|吟|怒|舞)'},
    {'name': '短句节奏', 'regex': r'[。！？][^。！？]{1,8}[。！？]'},
]
