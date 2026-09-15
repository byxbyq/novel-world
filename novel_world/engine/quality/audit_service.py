# -*- coding: utf-8 -*-
"""
叙事质量审计服务 — 移植自书斋V65 services/audit.py

核心能力：
  1. AI味检测（统计特征 + 规则，不消耗Token）
  2. 战力崩坏检测（基于角色境界和战斗结果）
  3. 文风指纹提取与对比
  4. 综合审计（整合以上检测 + 伏笔逾期检查）

设计原则：
  - 纯规则/统计驱动，不消耗AI Token
  - 所有检测返回结构化结果（分数 + 级别 + 问题列表）
  - 与 WorldRuleGuard / ConsistencyChecker 互补
"""

import re
import math
import time
from typing import List, Dict, Tuple, Optional, Set
from collections import Counter


# ═══════════════════════════════════════════
# 辅助函数
# ═══════════════════════════════════════════

def _line_number(content: str, pos: int) -> int:
    """计算字符偏移对应的行号（1-based）"""
    return content[:pos].count('\n') + 1


def _context_snippet(content: str, pos: int, span: int = 20) -> str:
    """提取位置周围的上下文片段"""
    start = max(0, pos - span)
    end = min(len(content), pos + span)
    return content[start:end].replace('\n', ' ')


def _find_all_positions(content: str, pattern: str) -> List[Dict]:
    """用正则查找所有匹配位置"""
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
    """查找关键词所有出现位置"""
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


# ═══════════════════════════════════════════
# AI味检测词表
# ═══════════════════════════════════════════

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
}

FORMULAIC_TRANSITIONS = [
    r'就在这时[，,]', r'话音刚落[，,]', r'话音未落[，,]',
    r'还没等.{1,6}反应', r'下一秒[，,]', r'刹那间[，,]',
    r'一瞬间[，,]', r'电光火石之间',
]

NARRATOR_OVERREACH = [
    r'这证明了[，,]?', r'这意味着[，,]?', r'这说明了[，,]?',
    r'不难看出[，,]?', r'显然[，,]', r'毫无疑问[，,]',
    r'不言而喻[，,]', r'可想而知[，,]',
]

NEGATIVE_PIVOT_PATTERNS = [
    r'不是.{1,12}[，,].{0,4}而是', r'并非.{1,12}[，,].{0,4}而是',
    r'不在于.{1,12}[，,].{0,4}而在于', r'不仅仅.{1,12}[，,].{0,4}更是',
]

DIALOGUE_TAGS = [
    '说道', '问道', '笑道', '喊道', '叫道', '答道',
    '怒道', '冷道', '叹道', '低声道', '低声说', '大声说', '轻声说'
]

SUBLIMATION_PATTERNS = [
    r'这一切都说明', r'他终于明白', r'她终于明白',
    r'新的篇章开始', r'这一刻[，,]', r'从此以后[，,]',
    r'他知道[，,].{2,20}的意义', r'她知道[，,].{2,20}的意义',
    r'在那一瞬间[，,].{2,10}明白了',
]

GOD_VIEW_PATTERNS = [
    r'她不知道的是', r'他不知道的是', r'殊不知[，,]',
    r'多年以后[，,]', r'之所以.{1,20}是因为',
    r'原来.{1,15}竟然', r'仿佛预示着', r'仿佛在宣判',
]

ENGINEERING_WORDS = [
    'placeholder', 'TODO', 'FIXME', 'lorem ipsum',
    '此处省略', '占位符', '待补充内容',
    '生成的', '作为一个AI', '我无法',
    '请注意', '总结如下', '以下内容',
]

# ═══════════════════════════════════════════
# 战力体系
# ═══════════════════════════════════════════

REALM_HIERARCHY = [
    '凡人', '觉醒', '入门', '初级', '中级', '高级',
    '超凡', '蜕变', '蜕变期', '入微', '化境', '巅峰',
    '仙', '神', '圣', '至尊', '创世', '归零',
]

# ═══════════════════════════════════════════
# AI味检测
# ═══════════════════════════════════════════

def detect_ai_flavor(content: str) -> Dict:
    """
    AI味检测 - 统计特征分析 + 规则检测

    不消耗 Token，纯基于统计与正则。
    返回包含 score/level/issues/stats 的完整结果。
    """
    if not content or len(content) < 100:
        return {
            'score': 0, 'level': 'clean', 'issues': [],
            'summary': 'content too short', 'stats': {}, 'ai_probability': 0
        }

    char_count = len(content)
    scale = max(char_count / 3000.0, 1.0)
    issues = []
    total_deduction = 0

    # ---- 统计特征 ----
    raw_sentences = re.split(r'[。！？\n]+', content)
    sentences = [s.strip() for s in raw_sentences if len(s.strip()) > 2]
    sentence_lengths = [len(s) for s in sentences]
    n_sentences = len(sentence_lengths)

    # 突发性（Burstiness）
    burstiness_score = 0
    cv = 0
    if n_sentences > 10:
        mean_len = sum(sentence_lengths) / n_sentences
        variance = sum((l - mean_len) ** 2 for l in sentence_lengths) / n_sentences
        std_dev = math.sqrt(variance)
        cv = std_dev / mean_len if mean_len > 0 else 0
        if cv < 0.3:
            burstiness_score = 25
            issues.append({'type': 'low_burstiness', 'cv': round(cv, 3),
                           'scope': 'global',
                           'message': f'句子长度过于均匀(变异系数{cv:.2f})，AI特征明显'})
        elif cv < 0.45:
            burstiness_score = 15
            issues.append({'type': 'low_burstiness', 'cv': round(cv, 3),
                           'scope': 'global',
                           'message': f'句子长度较均匀(变异系数{cv:.2f})，偏AI风格'})
        elif cv < 0.6:
            burstiness_score = 7
    total_deduction += burstiness_score

    # 词汇多样性（TTR）
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

    # 段落均匀性
    para_cv = 0
    paragraphs = [p.strip() for p in content.split('\n') if len(p.strip()) > 20]
    if len(paragraphs) > 5:
        para_lens = [len(p) for p in paragraphs]
        para_mean = sum(para_lens) / len(para_lens)
        para_cv = math.sqrt(
            sum((l - para_mean) ** 2 for l in para_lens) / len(para_lens)
        ) / para_mean if para_mean > 0 else 0
        if para_cv < 0.25:
            total_deduction += 12
            issues.append({'type': 'uniform_paragraphs', 'cv': round(para_cv, 3),
                           'scope': 'global',
                           'message': f'段落长度过于均匀(变异系数{para_cv:.2f})，AI排版特征'})
        elif para_cv < 0.40:
            total_deduction += 6
    total_deduction += 0  # already added above

    # 句首模式重复
    if n_sentences > 15:
        sentence_starts = [s[:3] for s in sentences if len(s) >= 3]
        start_counter = Counter(sentence_starts)
        repeated_starts = sum(1 for v in start_counter.values() if v >= 3)
        if repeated_starts >= 3:
            top_pattern = start_counter.most_common(1)[0]
            total_deduction += 10
            issues.append({'type': 'pattern_repetition', 'scope': 'global',
                           'message': f'句首模式重复过多，"{top_pattern[0]}…"出现{top_pattern[1]}次'})
        elif repeated_starts >= 2:
            total_deduction += 5

    # 连接词密度
    connectors = ['然而', '因此', '但是', '不过', '于是', '随后', '紧接着',
                  '与此同时', '不仅如此', '事实上', '实际上', '换句话说',
                  '总而言之', '综上所述', '由此可见']
    connector_count = sum(content.count(c) for c in connectors)
    connector_density = connector_count / (char_count / 1000)
    if connector_density > 5:
        connector_score = min(12, int((connector_density - 5) * 3))
        total_deduction += connector_score
        issues.append({'type': 'connector_overuse', 'count': connector_count,
                       'density': round(connector_density, 1), 'scope': 'global',
                       'message': f'连接词密度过高({connector_density:.1f}/千字)，AI行文特征'})

    # "的"字密度
    de_density = content.count('的') / (char_count / 1000) if char_count > 0 else 0
    if de_density > 35:
        de_score = min(10, int((de_density - 35) * 1.5))
        total_deduction += de_score
        issues.append({'type': 'high_de_density', 'density': round(de_density, 1),
                       'scope': 'global',
                       'message': f'"的"字密度过高({de_density:.1f}/千字)，AI行文特征'})

    # ---- 规则检测 ----
    # Buzzword
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
                           'message': f'[forbidden] "{word}" 出现 {count} 次'})
            total_deduction += deduction
        elif count > allowed:
            excess = int(count - allowed)
            deduction = min(10, excess * 2)
            issues.append({'type': 'buzzword_density', 'word': word, 'count': count,
                           'limit': int(allowed), 'locations': locations,
                           'message': f'"{word}" 出现 {count} 次（上限 {int(allowed)}）'})
            total_deduction += deduction

    # 公式化过渡
    transition_count = 0
    for pattern in FORMULAIC_TRANSITIONS:
        locs = _find_all_positions(content, pattern)
        if locs:
            transition_count += len(locs)
            if len(locs) > 1:
                issues.append({'type': 'formulaic_transition', 'pattern': pattern,
                               'count': len(locs), 'locations': locs,
                               'message': f'公式化过渡重复 {len(locs)} 次'})
                total_deduction += min(5, len(locs) * 2)
    if transition_count > 3 * scale:
        total_deduction += 5

    # 叙述者越权
    for pattern in NARRATOR_OVERREACH:
        locs = _find_all_positions(content, pattern)
        if locs:
            issues.append({'type': 'narrator_overreach',
                           'pattern': locs[0]['matched'][:20], 'count': len(locs),
                           'locations': locs,
                           'message': f'叙述者越权: "{locs[0]["matched"][:20]}" 替读者下结论'})
            total_deduction += min(8, len(locs) * 3)

    # Gate B: 否定铺垫
    for pattern in NEGATIVE_PIVOT_PATTERNS:
        locs = _find_all_positions(content, pattern)
        if locs:
            issues.append({'type': 'negative_pivot', 'gate': 'B',
                           'pattern': locs[0]['matched'][:20], 'count': len(locs),
                           'locations': locs,
                           'message': f'否定铺垫句式: "{locs[0]["matched"][:20]}..." 出现{len(locs)}次'})
            total_deduction += min(10, len(locs) * 4)

    # Gate E: 对话标签密度
    dialogue_sentences = re.findall(r'[""「」『』].*?[""「」『』]', content)
    dialogue_tag_count = sum(content.count(tag) for tag in DIALOGUE_TAGS)
    if dialogue_sentences and len(dialogue_sentences) > 5:
        ratio = dialogue_tag_count / len(dialogue_sentences)
        if ratio > 0.5:
            issues.append({'type': 'dialogue_tag_density', 'gate': 'E',
                           'count': dialogue_tag_count, 'ratio': round(ratio, 2),
                           'message': f'对话标签密度过高({int(ratio*100)}%)，建议用动作替代"说道/问道"'})
            total_deduction += min(10, int((ratio - 0.5) * 20))

    # Gate F: 结尾升华
    sublimation_count = 0
    for pattern in SUBLIMATION_PATTERNS:
        locs = _find_all_positions(content, pattern)
        if locs:
            sublimation_count += len(locs)
    if sublimation_count > 0:
        issues.append({'type': 'sublimation_ending', 'gate': 'F',
                       'count': sublimation_count,
                       'message': f'结尾升华句式: 检测到 {sublimation_count} 处总结/升华'})
        total_deduction += min(8, sublimation_count * 3)

    # Gate G: 上帝视角
    god_view_count = 0
    for pattern in GOD_VIEW_PATTERNS:
        locs = _find_all_positions(content, pattern)
        if locs:
            god_view_count += len(locs)
            issues.append({'type': 'god_view', 'gate': 'G',
                           'pattern': locs[0]['matched'][:20], 'count': len(locs),
                           'locations': locs,
                           'message': f'解释腔/上帝感: "{locs[0]["matched"][:20]}..." 叙述者越权'})
            total_deduction += min(12, len(locs) * 4)

    # 工程词泄漏
    eng_hits = [w for w in ENGINEERING_WORDS if w in content]
    if eng_hits:
        issues.append({'type': 'engineering_word_leak', 'gate': 'degeneration',
                       'words': eng_hits, 'count': len(eng_hits),
                       'message': f'工程词泄漏: {", ".join(eng_hits[:3])}'})
        total_deduction += min(20, len(eng_hits) * 8)

    # ---- 综合评分 ----
    score = min(100, total_deduction)
    level = 'clean' if score == 0 else ('minor' if score <= 15 else ('moderate' if score <= 35 else 'heavy'))

    # AI概率估算
    ai_prob = 0
    if n_sentences > 10:
        if cv < 0.3: ai_prob += 40
        elif cv < 0.4: ai_prob += 25
        elif cv < 0.5: ai_prob += 15
        elif cv < 0.6: ai_prob += 5
    if len(chars_clean) > 200:
        if ttr < 0.45: ai_prob += 25
        elif ttr < 0.50: ai_prob += 15
        elif ttr < 0.55: ai_prob += 8
    if len(paragraphs) > 5:
        if para_cv < 0.25: ai_prob += 15
        elif para_cv < 0.35: ai_prob += 8
    if connector_density > 5: ai_prob += 10
    if de_density > 35: ai_prob += 8
    ai_prob = min(99, ai_prob)

    ai_level = 'high' if ai_prob >= 70 else ('medium' if ai_prob >= 40 else ('low' if ai_prob >= 20 else 'minimal'))

    summary = f'AI味评分: {score}/100 ({level})'
    summary += f' | 预估AI概率: {ai_prob}% ({ai_level})'
    if issues:
        top = [i['message'] for i in issues[:3]]
        summary += '. 主要问题: ' + '; '.join(top)

    return {
        'score': score, 'level': level, 'ai_probability': ai_prob,
        'ai_level': ai_level, 'issues': issues, 'summary': summary,
        'stats': {
            'burstiness_cv': round(cv, 3) if n_sentences > 10 else 0,
            'ttr': round(ttr, 3) if len(chars_clean) > 200 else 0,
            'para_cv': round(para_cv, 3) if len(paragraphs) > 5 else 0,
            'connector_density': round(connector_density, 1),
            'de_density': round(de_density, 1),
            'sentence_count': n_sentences,
            'avg_sentence_len': round(sum(sentence_lengths) / n_sentences, 1) if n_sentences > 0 else 0,
            'buzzword_total': sum(1 for i in issues if 'buzzword' in i['type']),
            'transition_total': transition_count,
            'god_view_total': god_view_count,
        }
    }


# ═══════════════════════════════════════════
# 战力崩坏检测
# ═══════════════════════════════════════════

def detect_power_collapse(content: str, chapter_index: int = 0,
                          characters: List[Dict] = None) -> Dict:
    """
    战力崩坏检测 - 基于角色境界和战斗叙事

    检查项：
      1. 境界跳跃过大（单章跨2级以上）
      2. 已死亡角色出现
      3. 越级击败不合理（低境界击败高2级以上）

    Args:
        content: 叙事文本
        chapter_index: 当前章节
        characters: 角色状态列表 [{name, realm, prev_realm, status}, ...]

    Returns:
        检测结果字典
    """
    if not content:
        return {'score': 0, 'level': 'ok', 'issues': [], 'summary': 'no content'}

    issues = []
    total_deduction = 0

    if characters:
        for char in characters:
            name = char.get('name', '')
            realm = char.get('realm', '')
            prev_realm = char.get('prev_realm', '')

            # 境界跳跃检测
            if realm and prev_realm:
                try:
                    curr_idx = REALM_HIERARCHY.index(realm) if realm in REALM_HIERARCHY else -1
                    prev_idx = REALM_HIERARCHY.index(prev_realm) if prev_realm in REALM_HIERARCHY else -1
                    if curr_idx >= 0 and prev_idx >= 0:
                        jump = curr_idx - prev_idx
                        if jump > 2:
                            issues.append({
                                'type': 'realm_jump', 'character': name,
                                'from': prev_realm, 'to': realm, 'jump': jump,
                                'message': f'{name} 境界从 {prev_realm} 跳至 {realm}（跨 {jump} 级）'
                            })
                            total_deduction += min(20, jump * 5)
                except (ValueError, IndexError):
                    pass

            # 死亡角色出现检测
            status = char.get('status', '')
            if status == 'dead' and name and name in content:
                revival_kw = ['复活', '重生', '苏醒', '诈尸', '未死', '还活着']
                if not any(kw in content for kw in revival_kw):
                    issues.append({
                        'type': 'dead_revival', 'character': name,
                        'message': f'已死亡角色 {name} 出现，未伴随复活描述'
                    })
                    total_deduction += 15

    # 越级击败检测
    victory_patterns = [
        r'(.{1,8})击败了(.{1,8})',
        r'(.{1,8})战胜了(.{1,8})',
        r'(.{1,8})杀了(.{1,8})',
    ]
    realm_keywords = ['筑基', '金丹', '元婴', '化神', '炼虚', '合体', '大乘', '渡劫',
                      '练气', '先天', '宗师', '大宗师', '天人', '超凡', '入圣']

    for pattern in victory_patterns:
        matches = re.findall(pattern, content)
        for winner, loser in matches:
            winner_realm = None
            loser_realm = None
            for realm in realm_keywords:
                if realm in winner: winner_realm = realm
                if realm in loser: loser_realm = realm

            if winner_realm and loser_realm:
                w_idx = realm_keywords.index(winner_realm) if winner_realm in realm_keywords else -1
                l_idx = realm_keywords.index(loser_realm) if loser_realm in realm_keywords else -1
                if l_idx - w_idx > 2:
                    issues.append({
                        'type': 'power_mismatch',
                        'winner': winner.strip(), 'loser': loser.strip(),
                        'winner_realm': winner_realm, 'loser_realm': loser_realm,
                        'message': f'{winner.strip()}({winner_realm}) 击败了 {loser.strip()}({loser_realm}) - 越级战斗'
                    })
                    total_deduction += 10

    score = min(100, total_deduction)
    level = 'ok' if score == 0 else ('warning' if score <= 20 else 'serious')

    summary = f'战力一致性: {100 - score}/100 ({level})'
    if issues:
        top = [i['message'] for i in issues[:3]]
        summary += '. 问题: ' + '; '.join(top)

    return {
        'score': score, 'level': level, 'issues': issues, 'summary': summary,
    }


# ═══════════════════════════════════════════
# 综合审计
# ═══════════════════════════════════════════

def run_extended_audit(content: str, chapter_index: int = 0,
                       characters: List[Dict] = None,
                       overdue_hooks: List[Dict] = None) -> Dict:
    """
    运行扩展审计（纯规则，不消耗Token）

    整合 AI 味检测 + 战力崩坏 + 伏笔逾期检查，
    输出综合评分和所有问题列表。

    Args:
        content: 待审计的叙事文本
        chapter_index: 当前章节编号
        characters: 角色状态列表
        overdue_hooks: 逾期伏笔列表

    Returns:
        综合审计结果
    """
    ai_result = detect_ai_flavor(content)
    power_result = detect_power_collapse(content, chapter_index, characters)

    all_issues = ai_result['issues'] + power_result['issues']

    # 伏笔逾期检查
    hook_issues = []
    if overdue_hooks:
        for hook in overdue_hooks:
            hook_text = hook.get('content', '')[:30]
            hook_ch = hook.get('chapter', '?')
            hook_issues.append({
                'type': 'overdue_foreshadowing',
                'hook': hook_text,
                'set_at': hook_ch,
                'message': f'逾期伏笔（第{hook_ch}章埋设）: {hook_text}...'
            })
    all_issues.extend(hook_issues)

    # 综合评分: AI味 50% + 战力 30% + 伏笔 20%
    ai_score = ai_result['score']
    power_score = power_result['score']
    hook_penalty = len(hook_issues) * 5
    overall = min(100, ai_score * 0.5 + power_score * 0.3 + hook_penalty * 0.2)

    level = 'pass' if overall <= 15 else ('review' if overall <= 40 else 'fail')

    summary = f'综合审计: {round(overall, 1)}/100 ({level})'
    summary += f' | AI味: {ai_score} | 战力: {power_score} | 伏笔: {len(hook_issues)}'

    return {
        'ai_flavor': ai_result,
        'power_collapse': power_result,
        'overdue_hooks': hook_issues,
        'overall_score': round(overall, 1),
        'overall_level': level,
        'all_issues': all_issues,
        'summary': summary,
    }


# ═══════════════════════════════════════════
# 文风指纹系统
# ═══════════════════════════════════════════

RHETORICAL_PATTERNS_ZH = [
    {'name': '比喻(像/如/仿佛)', 'regex': r'[像如仿佛似](?:是|同|一般|一样)'},
    {'name': '排比', 'regex': r'[，。；]([^，。；]{2,6})[，。；]\1'},
    {'name': '反问', 'regex': r'难道|怎么可能|岂不是|何尝不'},
    {'name': '夸张', 'regex': r'天崩地裂|惊天动地|翻天覆地|震耳欲聋'},
    {'name': '拟人', 'regex': r'[风雨雪月花树草石](?:在|像|仿佛).*?(?:笑|哭|叹|呻|吟|怒|舞)'},
    {'name': '短句节奏', 'regex': r'[。！？][^。！？]{1,8}[。！？]'},
]


def extract_style_fingerprint(text: str, source_name: str = "") -> Dict:
    """
    从参考文本中提取文风指纹（纯统计分析）

    提取维度：句长分布、段落节奏、词汇多样性、修辞特征、对话密度等。
    用于生成风格指南文本，注入 AI prompt 中指导叙事风格。

    Args:
        text: 参考文本（≥200字）
        source_name: 来源名称

    Returns:
        文风指纹字典
    """
    if not text or len(text) < 200:
        return {'error': '文本太短（需≥200字）', 'source_name': source_name}

    sentences = re.split(r'[。！？\n]+', text)
    sentences = [s.strip() for s in sentences if len(s.strip()) > 2]
    sentence_lengths = [len(s) for s in sentences]
    n_sentences = len(sentence_lengths)

    avg_sl = sum(sentence_lengths) / n_sentences if n_sentences > 0 else 0
    if n_sentences > 1:
        variance = sum((l - avg_sl) ** 2 for l in sentence_lengths) / n_sentences
        sl_std = math.sqrt(variance)
    else:
        sl_std = 0

    paragraphs = [p.strip() for p in text.split('\n') if len(p.strip()) > 20]
    para_lengths = [len(p) for p in paragraphs]
    n_paras = len(para_lengths)
    avg_pl = sum(para_lengths) / n_paras if n_paras > 0 else 0

    chars_clean = re.sub(r'[^\u4e00-\u9fa5a-zA-Z]', '', text)
    ttr = 0
    if len(chars_clean) > 100:
        bigrams = [chars_clean[i:i+2] for i in range(len(chars_clean) - 1)]
        ttr = len(set(bigrams)) / len(bigrams) if bigrams else 0

    # 句首模式
    opening_counts = {}
    for s in sentences:
        key = s[:2] if len(s) >= 2 else s
        if key:
            opening_counts[key] = opening_counts.get(key, 0) + 1
    top_patterns = sorted(opening_counts.items(), key=lambda x: -x[1])[:5]
    top_patterns = [f'{p}…({c}次)' for p, c in top_patterns if c >= 3]

    # 修辞特征
    rhetorical = []
    for pat in RHETORICAL_PATTERNS_ZH:
        matches = re.findall(pat['regex'], text)
        if len(matches) >= 2:
            rhetorical.append(f"{pat['name']}({len(matches)}处)")

    de_density = text.count('的') / (len(text) / 1000) if len(text) > 0 else 0
    dialogue_count = len(re.findall(r'[""「」『』].*?[""「」『』]', text))
    dialogue_density = dialogue_count / (n_sentences / 10) if n_sentences > 0 else 0

    # 句长分布直方图
    length_buckets = {'极短(≤10)': 0, '短(11-20)': 0, '中(21-40)': 0,
                      '长(41-60)': 0, '极长(>60)': 0}
    for l in sentence_lengths:
        if l <= 10: length_buckets['极短(≤10)'] += 1
        elif l <= 20: length_buckets['短(11-20)'] += 1
        elif l <= 40: length_buckets['中(21-40)'] += 1
        elif l <= 60: length_buckets['长(41-60)'] += 1
        else: length_buckets['极长(>60)'] += 1

    fingerprint = {
        'source_name': source_name,
        'analyzed_at': time.strftime('%Y-%m-%d %H:%M'),
        'text_length': len(text),
        'sentence_count': n_sentences,
        'avg_sentence_length': round(avg_sl, 1),
        'sentence_length_std': round(sl_std, 1),
        'sentence_length_cv': round(sl_std / avg_sl, 3) if avg_sl > 0 else 0,
        'paragraph_count': n_paras,
        'avg_paragraph_length': round(avg_pl, 1),
        'vocabulary_diversity': round(ttr, 3),
        'top_opening_patterns': top_patterns,
        'rhetorical_features': rhetorical,
        'de_density': round(de_density, 1),
        'dialogue_density': round(dialogue_density, 2),
        'length_distribution': length_buckets,
    }

    # 生成风格指南
    guide_lines = [
        f'## 文风指南（提取自{source_name or "参考文本"}）',
        f'- 平均句长: {fingerprint["avg_sentence_length"]}字（标准差{fingerprint["sentence_length_std"]}）',
        f'- 句长变异系数: {fingerprint["sentence_length_cv"]}（{"均匀-偏AI" if fingerprint["sentence_length_cv"] < 0.4 else "自然-人类风格"}）',
        f'- 平均段落长度: {fingerprint["avg_paragraph_length"]}字',
        f'- 词汇多样性(TTR): {fingerprint["vocabulary_diversity"]}',
        f'- "的"字密度: {fingerprint["de_density"]}/千字',
        f'- 对话密度: {fingerprint["dialogue_density"]}/10句',
        f'- 句长分布: {", ".join(f"{k}={v}" for k,v in length_buckets.items())}',
    ]
    if top_patterns: guide_lines.append(f'- 高频句首: {", ".join(top_patterns)}')
    if rhetorical: guide_lines.append(f'- 修辞特征: {", ".join(rhetorical)}')
    guide_lines.append('- 写作要求: 句长分布、段落节奏、修辞频率应贴近以上指纹参数')

    fingerprint['style_guide'] = '\n'.join(guide_lines)
    return fingerprint


def compare_style_fingerprint(content: str, reference_fingerprint: Dict) -> Dict:
    """
    对比正文与参考文风指纹的偏离度

    Args:
        content: 待检测文本
        reference_fingerprint: 参考指纹（由 extract_style_fingerprint 生成）

    Returns:
        偏离度分析结果
    """
    if not content or not reference_fingerprint:
        return {'error': '缺少内容或参考指纹'}

    current = extract_style_fingerprint(content)
    if 'error' in current:
        return current

    deviations = []

    ref_avg = reference_fingerprint.get('avg_sentence_length', 20)
    cur_avg = current['avg_sentence_length']
    avg_dev = abs(cur_avg - ref_avg) / ref_avg if ref_avg > 0 else 0
    if avg_dev > 0.3:
        deviations.append({
            'dimension': 'avg_sentence_length', 'reference': ref_avg,
            'current': cur_avg, 'deviation': round(avg_dev * 100),
            'message': f'平均句长偏离{round(avg_dev*100)}%（参考{ref_avg}→当前{cur_avg}）'
        })

    ref_cv = reference_fingerprint.get('sentence_length_cv', 0.5)
    cur_cv = current['sentence_length_cv']
    cv_dev = abs(cur_cv - ref_cv) / ref_cv if ref_cv > 0 else 0
    if cv_dev > 0.3:
        deviations.append({
            'dimension': 'sentence_length_cv', 'reference': ref_cv,
            'current': cur_cv, 'deviation': round(cv_dev * 100),
            'message': f'句长变异系数偏离{round(cv_dev*100)}%（参考{ref_cv}→当前{cur_cv}）'
        })

    ref_ttr = reference_fingerprint.get('vocabulary_diversity', 0.5)
    cur_ttr = current['vocabulary_diversity']
    ttr_dev = abs(cur_ttr - ref_ttr) / ref_ttr if ref_ttr > 0 else 0
    if ttr_dev > 0.2:
        deviations.append({
            'dimension': 'vocabulary_diversity', 'reference': ref_ttr,
            'current': cur_ttr, 'deviation': round(ttr_dev * 100),
            'message': f'词汇多样性偏离{round(ttr_dev*100)}%（参考{ref_ttr}→当前{cur_ttr}）'
        })

    ref_para = reference_fingerprint.get('avg_paragraph_length', 100)
    cur_para = current['avg_paragraph_length']
    para_dev = abs(cur_para - ref_para) / ref_para if ref_para > 0 else 0
    if para_dev > 0.4:
        deviations.append({
            'dimension': 'avg_paragraph_length', 'reference': ref_para,
            'current': cur_para, 'deviation': round(para_dev * 100),
            'message': f'段落长度偏离{round(para_dev*100)}%（参考{ref_para}→当前{cur_para}）'
        })

    total_deviation = 0
    if deviations:
        total_deviation = min(100,
            sum(d['deviation'] for d in deviations) // len(deviations) + len(deviations) * 10)

    level = ('matched' if total_deviation <= 15
             else ('minor_deviation' if total_deviation <= 35
                   else ('moderate_deviation' if total_deviation <= 60
                         else 'severe_deviation')))

    return {
        'deviation_score': total_deviation,
        'level': level,
        'summary': f'文风偏离度: {total_deviation}/100 ({level}) | 偏离维度: {len(deviations)}',
        'deviations': deviations,
    }


# ═══════════════════════════════════════════
# 强行巧合检测
# ═══════════════════════════════════════════

COINCIDENCE_PATTERNS = [
    # 关键线索恰好被某人发现（无铺垫）
    (r'(恰好|正巧|刚好|无意中|碰巧|偶然).{1,20}(发现|捡到|听到|看到|撞见)', 60),
    # 救援恰好到达
    (r'(千钧一发|危急关头|生死关头|命悬一线).{1,20}(赶到|出现|杀出|现身|降临)', 70),
    (r'(就在此时|正在这时).{1,20}(一道.{1,10}(出现|降临|杀到))', 50),
    # 敌人恰好内讧
    (r'(突然|忽然|竟).{1,20}(内讧|反目|背叛|自相残杀)', 55),
    # 主角恰好获得关键物品
    (r'(无意中|随手|不经意).{1,15}(得到|获得|捡起|收取).{1,10}(神器|秘籍|法宝|传承)', 80),
    # 恰好遇到关键人物
    (r'(正巧|恰好).{1,15}(遇到|碰上|撞见).{1,10}(高人|前辈|师父|神秘人)', 55),
]

COINCIDENCE_FORBIDDEN_KEYWORDS = [
    '恰好', '正巧', '碰巧', '天意', '命中注定',
    '阴差阳错', '机缘巧合', '巧合的是',
]


def detect_coincidence(content: str, chapter_context: dict = None) -> Dict:
    """
    强行巧合检测

    规则：
    1. 同一角色每章巧合事件 ≤ 1 次
    2. 巧合必须可追溯到已有伏笔（通过 chapter_context 中的 foreshadowing 判断）

    Args:
        content: 叙事文本
        chapter_context: 章节上下文，含 foreshadowing/pending_clues 列表

    Returns:
        检测结果字典
    """
    if not content:
        return {'has_coincidence': False, 'count': 0, 'violations': []}

    violations = []
    chapter_context = chapter_context or {}

    # 检测巧合模式匹配
    for pattern, severity in COINCIDENCE_PATTERNS:
        for m in re.finditer(pattern, content):
            violations.append({
                'pattern': pattern,
                'severity': severity,
                'matched_text': m.group(0),
                'position': _line_number(content, m.start()),
                'context': _context_snippet(content, m.start()),
            })

    # 检测禁用关键词
    for kw in COINCIDENCE_FORBIDDEN_KEYWORDS:
        for m in re.finditer(re.escape(kw), content):
            violations.append({
                'pattern': f'关键词: {kw}',
                'severity': 40,
                'matched_text': m.group(0),
                'position': _line_number(content, m.start()),
                'context': _context_snippet(content, m.start()),
            })

    # 按角色分组统计巧合次数
    by_character = {}
    for v in violations:
        ctx = v.get('context', '')
        # 简单提取：上下文中可能提到的角色名
        # 这里不做精确提取，统一记录
        by_character['全局'] = by_character.get('全局', 0) + 1

    # 判断是否超标
    over_limit = any(c > 1 for c in by_character.values())

    # 检查是否有伏笔支撑
    pending_clues = chapter_context.get('foreshadowing', []) or \
                    chapter_context.get('pending_clues', [])
    unsupported = len(violations) > 0 and len(pending_clues) == 0

    level = 'pass'
    if over_limit or unsupported:
        level = 'warn' if violations else 'fail'

    return {
        'has_coincidence': len(violations) > 0,
        'count': len(violations),
        'by_character': by_character,
        'over_limit': over_limit,
        'unsupported': unsupported,
        'level': level,
        'violations': violations,
        'summary': (
            f"检测到 {len(violations)} 处巧合事件"
            + ("，超出每章1次限制" if over_limit else "")
            + ("，无伏笔支撑" if unsupported else "")
        ),
    }


# ═══════════════════════════════════════════
# 工具人（配角）检测
# ═══════════════════════════════════════════

TOOL_CHARACTER_PATTERNS = {
    '情报提供': [
        r'(告诉|告知|透露|悄悄.{1,6}说).{1,20}(线索|情报|消息|秘密|真相)',
        r'(递过|拿出).{1,15}(地图|信件|令牌|卷轴|玉简|符箓)',
    ],
    '战斗打手': [
        r'(出手|挡住|拦下|击退).{1,15}(攻击|偷袭|包围|追杀)',
        r'(断后|掩护).{1,10}(撤退|逃|离开)',
    ],
    '信使传话': [
        r'(传话|带话|捎信|转告).{1,15}',
        r'(飞鸽|传讯|传音符|灵力传讯)',
    ],
}


def detect_tool_character(
    content: str,
    character_span: Dict[str, tuple] = None,
) -> Dict:
    """
    工具人（配角）检测

    追踪每个配角的活跃跨度和作用类型。
    规则：
    - 跨度 ≤ 2 章 + 作用单一（仅情报/仅打手/仅信使）→ 标记为工具人

    Args:
        content: 叙事文本
        character_span: {角色名: (入场章节号, 最后出场章节号)}

    Returns:
        检测结果字典
    """
    character_span = character_span or {}

    violations = []

    # 检测工具人模式
    for role_type, patterns in TOOL_CHARACTER_PATTERNS.items():
        for pattern in patterns:
            for m in re.finditer(pattern, content):
                violations.append({
                    'role_type': role_type,
                    'matched_text': m.group(0),
                    'position': _line_number(content, m.start()),
                })

    # 按角色统计
    by_character = {}
    for v in violations:
        # 无法从正则结果中精确提取角色名，统一记录
        key = v['role_type']
        by_character[key] = by_character.get(key, 0) + 1

    # 检查跨度
    tool_chars = []
    for char_name, (entry_ch, exit_ch) in character_span.items():
        span = exit_ch - entry_ch + 1
        if span <= 2:
            # 检查该角色是否只做了单一类型的事
            tool_chars.append({
                'name': char_name,
                'span': span,
                'entry_chapter': entry_ch,
                'exit_chapter': exit_ch,
            })

    # 判断
    has_tool_char = len(tool_chars) > 0
    level = 'warn' if has_tool_char else 'pass'

    return {
        'has_tool_characters': has_tool_char,
        'violations_count': len(violations),
        'by_role_type': by_character,
        'tool_characters': tool_chars,
        'level': level,
        'summary': (
            f"检测到 {len(tool_chars)} 个疑似工具人角色（跨度≤2章）: "
            + ', '.join(c['name'] for c in tool_chars)
            if tool_chars else "未检测到工具人模式"
        ),
        'suggestion': (
            "建议：将工具人角色的功能合并到已有常驻配角，"
            "或扩展该角色的支线使其跨越3章以上"
        ) if has_tool_char else "",
    }
