"""文风分析 Mixin — 文风指纹提取/偏离度对比"""
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

from .core import RHETORICAL_PATTERNS_ZH

logger = logging.getLogger(__name__)



def extract_style_fingerprint(text: str, source_name: str = "") -> Dict:
    """从参考文本中提取文风指纹（纯统计分析，不消耗Token）"""
    if not text or len(text) < 200:
        return {'error': '文本太短（需≥200字）', 'source_name': source_name}

    sentences = re.split(r'[。！？\n]+', text)
    sentences = [s.strip() for s in sentences if len(s.strip()) > 2]
    sentence_lengths = [len(s) for s in sentences]
    n_sentences = len(sentence_lengths)

    avg_sentence_length = sum(sentence_lengths) / n_sentences if n_sentences > 0 else 0
    if n_sentences > 1:
        variance = sum((l - avg_sentence_length) ** 2 for l in sentence_lengths) / n_sentences
        sentence_length_std = math.sqrt(variance)
    else:
        sentence_length_std = 0

    paragraphs = [p.strip() for p in text.split('\n') if len(p.strip()) > 20]
    para_lengths = [len(p) for p in paragraphs]
    n_paras = len(para_lengths)
    avg_para_length = sum(para_lengths) / n_paras if n_paras > 0 else 0
    para_min = min(para_lengths) if para_lengths else 0
    para_max = max(para_lengths) if para_lengths else 0

    chars_clean = re.sub(r'[^\u4e00-\u9fa5a-zA-Z]', '', text)
    ttr = 0
    if len(chars_clean) > 100:
        bigrams = [chars_clean[i:i+2] for i in range(len(chars_clean) - 1)]
        ttr = len(set(bigrams)) / len(bigrams) if bigrams else 0

    opening_counts = {}
    for s in sentences:
        key = s[:2] if len(s) >= 2 else s
        if key:
            opening_counts[key] = opening_counts.get(key, 0) + 1
    top_patterns = sorted(opening_counts.items(), key=lambda x: -x[1])[:5]
    top_patterns = [f'{p}…({c}次)' for p, c in top_patterns if c >= 3]

    rhetorical_features = []
    for pattern in RHETORICAL_PATTERNS_ZH:
        matches = re.findall(pattern['regex'], text)
        if len(matches) >= 2:
            rhetorical_features.append(f"{pattern['name']}({len(matches)}处)")

    de_density = text.count('的') / (len(text) / 1000) if len(text) > 0 else 0

    dialogue_count = len(re.findall(r'[""「」『』].*?[""「」『』]', text))
    dialogue_density = dialogue_count / (n_sentences / 10) if n_sentences > 0 else 0

    length_buckets = {'极短(≤10)': 0, '短(11-20)': 0, '中(21-40)': 0, '长(41-60)': 0, '极长(>60)': 0}
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
        'avg_sentence_length': round(avg_sentence_length, 1),
        'sentence_length_std': round(sentence_length_std, 1),
        'sentence_length_cv': round(sentence_length_std / avg_sentence_length, 3) if avg_sentence_length > 0 else 0,
        'paragraph_count': n_paras,
        'avg_paragraph_length': round(avg_para_length, 1),
        'paragraph_length_range': {'min': para_min, 'max': para_max},
        'vocabulary_diversity': round(ttr, 3),
        'top_opening_patterns': top_patterns,
        'rhetorical_features': rhetorical_features,
        'de_density': round(de_density, 1),
        'dialogue_density': round(dialogue_density, 2),
        'length_distribution': length_buckets,
    }

    guide_lines = [
        f'## 文风指南（提取自{source_name or "参考文本"}）',
        f'- 平均句长: {fingerprint["avg_sentence_length"]}字（标准差{fingerprint["sentence_length_std"]}）',
        f'- 句长变异系数: {fingerprint["sentence_length_cv"]}（{"均匀-偏AI" if fingerprint["sentence_length_cv"] < 0.4 else "自然-人类风格"}）',
        f'- 平均段落长度: {fingerprint["avg_paragraph_length"]}字',
        f'- 段落长度范围: {para_min}-{para_max}字',
        f'- 词汇多样性(TTR): {fingerprint["vocabulary_diversity"]}',
        f'- "的"字密度: {fingerprint["de_density"]}/千字',
        f'- 对话密度: {fingerprint["dialogue_density"]}/10句',
        f'- 句长分布: {", ".join(f"{k}={v}" for k,v in length_buckets.items())}',
    ]
    if top_patterns:
        guide_lines.append(f'- 高频句首: {", ".join(top_patterns)}')
    if rhetorical_features:
        guide_lines.append(f'- 修辞特征: {", ".join(rhetorical_features)}')
    guide_lines.append('- 写作要求: 句长分布、段落节奏、修辞频率应贴近以上指纹参数')

    fingerprint['style_guide'] = '\n'.join(guide_lines)
    return fingerprint


def compare_style_fingerprint(content: str, reference_fingerprint: Dict) -> Dict:
    """对比正文与参考文风指纹的偏离度（纯统计，不消耗Token）"""
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

    ref_de = reference_fingerprint.get('de_density', 20)
    cur_de = current['de_density']
    de_dev = abs(cur_de - ref_de) / ref_de if ref_de > 0 else 0
    if de_dev > 0.3:
        deviations.append({
            'dimension': 'de_density', 'reference': ref_de,
            'current': cur_de, 'deviation': round(de_dev * 100),
            'message': f'"的"字密度偏离{round(de_dev*100)}%（参考{ref_de}→当前{cur_de}）'
        })

    total_deviation = 0
    if deviations:
        total_deviation = min(100, sum(d['deviation'] for d in deviations) // len(deviations) + len(deviations) * 10)

    level = ('matched' if total_deviation <= 15
             else 'minor_deviation' if total_deviation <= 35
             else 'moderate_deviation' if total_deviation <= 60
             else 'severe_deviation')

    return {
        'deviation_score': total_deviation,
        'level': level,
        'summary': f'文风偏离度: {total_deviation}/100 ({level}) | 偏离维度: {len(deviations)}',
        'deviations': deviations,
        'current_fingerprint': current,
        'reference_fingerprint': {
            k: reference_fingerprint.get(k) for k in
            ('avg_sentence_length', 'sentence_length_cv', 'vocabulary_diversity',
             'avg_paragraph_length', 'de_density')
        }
    }
