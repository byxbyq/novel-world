"""质量审计 Mixin — 战力崩坏/逻辑/人设/POV/设定/空间/高潮检测"""
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

from .core import (
    REALM_HIERARCHY,
    detect_ai_flavor,
    compute_ai_score,
    _line_number,
)

logger = logging.getLogger(__name__)



def detect_power_collapse(content: str, chapter_index: int = 0,
                          characters: List[Dict] = None) -> Dict:
    """战力崩坏检测 - 基于角色状态和正文内容"""
    if not content:
        return {'score': 0, 'level': 'ok', 'issues': [], 'summary': 'no content'}

    issues = []
    total_deduction = 0

    # 1. Realm jump detection
    if characters:
        for char in characters:
            name = char.get('name', '')
            realm = char.get('realm', '')
            prev_realm = char.get('prev_realm', '')
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
                                'message': f'{name} realm jumped from {prev_realm} to {realm} ({jump} levels)'
                            })
                            total_deduction += min(20, jump * 5)
                except (ValueError, IndexError):
                    pass

            # 2. Dead character revival
            status = char.get('status', '')
            archived = char.get('archived', False)
            if status == 'dead' and not archived and name and name in content:
                revival_keywords = ['复活', '重生', '苏醒', '诈尸', '未死', '还活着']
                has_revival = any(kw in content for kw in revival_keywords)
                if not has_revival:
                    mention_contexts = ['回忆', '想起', '记得', '记忆中', '当年', '曾经',
                                        '往事', '梦中', '闪回', '提到', '说起', '墓', '碑', '遗', '画像', '缅怀']
                    loc = content.find(name)
                    context = content[max(0, loc-30):loc+len(name)+30] if loc >= 0 else ''
                    in_mention = any(mc in context for mc in mention_contexts)
                    if not in_mention:
                        issues.append({
                            'type': 'dead_revival', 'character': name,
                            'message': f'dead character {name} appears without revival description'
                        })
                        total_deduction += 15

    # 3. Realm mentions
    realm_mentions = {r: content.count(r) for r in REALM_HIERARCHY if r in content}

    # 4. Victory mismatch detection
    victory_patterns = [
        r'(.{1,8})击败了(.{1,8})',
        r'(.{1,8})战胜了(.{1,8})',
        r'(.{1,8})杀了(.{1,8})',
    ]
    for pattern in victory_patterns:
        for winner, loser in re.findall(pattern, content):
            winner_realm = next((r for r in REALM_HIERARCHY if r in winner), None)
            loser_realm = next((r for r in REALM_HIERARCHY if r in loser), None)
            if winner_realm and loser_realm:
                w_idx = REALM_HIERARCHY.index(winner_realm)
                l_idx = REALM_HIERARCHY.index(loser_realm)
                if l_idx - w_idx > 2:
                    issues.append({
                        'type': 'power_mismatch', 'winner': winner.strip(),
                        'loser': loser.strip(), 'winner_realm': winner_realm,
                        'loser_realm': loser_realm,
                        'message': f'{winner.strip()}({winner_realm}) defeated {loser.strip()}({loser_realm}) - cross-level victory'
                    })
                    total_deduction += 10

    score = min(100, total_deduction)
    level = 'ok' if score == 0 else ('warning' if score <= 20 else 'serious')

    return {
        'score': score, 'level': level, 'issues': issues,
        'summary': f'Power consistency: {100-score}/100 ({level})',
        'realm_mentions': realm_mentions
    }


def detect_logic_gaps(content: str, chapter_index: int = 0,
                      characters: List[Dict] = None) -> List[Dict]:
    """逻辑断层检测：abrupt scene transitions, missing causal connectors"""
    issues = []
    if not content or len(content) < 200:
        return issues

    paragraphs = [p.strip() for p in content.split('\n') if p.strip()]
    if len(paragraphs) < 3:
        return issues

    location_markers = ['来到', '回到', '抵达', '进入', '走出', '离开', '赶到']
    time_markers = ['第二天', '三天后', '一周后', '半月后', '一个月后', '数月后', '翌日', '当晚', '清晨', '黄昏']
    transition_words = ['然而', '不过', '与此同时', '就在这时', '随后', '接着', '于是', '因此']

    for i in range(1, len(paragraphs)):
        prev_p = paragraphs[i - 1]
        curr_p = paragraphs[i]
        if len(prev_p) < 50 and len(curr_p) < 50:
            has_transition = any(tw in prev_p[-10:] or tw in curr_p[:10] for tw in transition_words)
            if not has_transition:
                prev_loc = any(lm in prev_p for lm in location_markers)
                curr_time = any(tm in curr_p[:20] for tm in time_markers)
                if prev_loc and curr_time:
                    pos = content.find(curr_p)
                    issues.append({
                        'type': 'logic_gaps',
                        'location': _line_number(content, pos) if pos >= 0 else 0,
                        'message': f'段落{i+1}可能存在场景跳跃：缺少过渡'
                    })

    if characters:
        knowledge_keywords = ['早已知道', '心中了然', '早就料到', '分明是', '显然是']
        for char in characters:
            name = char.get('name', '')
            if name and name in content:
                for kw in knowledge_keywords:
                    if kw in content:
                        pos = content.find(kw)
                        context_window = content[max(0, pos-30):pos+30]
                        if name in context_window:
                            issues.append({
                                'type': 'logic_gaps',
                                'location': _line_number(content, pos),
                                'message': f'角色{name}可能存在信息来源不明的全知判断'
                            })
                            break

    # 悬念未解决
    suspense_patterns = [
        r'(忽然|突然|蓦地).*?(？|！)',
        r'(是谁|为什么|怎么回事|什么情况)',
    ]
    for pattern in suspense_patterns:
        for m in re.finditer(pattern, content):
            after_text = content[m.end():m.end()+500]
            has_resolution = any(w in after_text for w in ['原来', '是因为', '答案是', '真相', '其实', '事实上'])
            if not has_resolution:
                issues.append({
                    'type': 'logic_gaps',
                    'location': _line_number(content, m.start()),
                    'message': '此处设置了悬念/疑问，但后续500字内未见回应'
                })
                break

    return issues[:5]


def detect_character_break(content: str, chapter_index: int = 0,
                           characters: List[Dict] = None) -> List[Dict]:
    """人设崩坏检测：角色行为与设定矛盾"""
    issues = []
    if not content or not characters:
        return issues

    personality_map = {
        '冷静': ['暴怒', '歇斯底里', '疯狂', '失控', '气急败坏'],
        '冷酷': ['温柔', '心疼', '不舍', '柔情', '暖意'],
        '善良': ['残忍', '狠毒', '冷血', '无动于衷'],
        '胆小': ['挺身而出', '毫不畏惧', '勇往直前', '正面迎击'],
        '高傲': ['卑微', '恳求', '低声下气', '屈服'],
        '沉稳': ['慌张', '手足无措', '惊慌失措', '六神无主'],
    }

    for char in characters:
        name = char.get('name', '')
        if not name or name not in content:
            continue
        char_desc = str(char.get('realm', '')) + str(char.get('status', ''))
        for personality, break_words in personality_map.items():
            if personality in char_desc or personality in name:
                for bw in break_words:
                    if bw in content:
                        pos = content.find(bw)
                        context = content[max(0, pos-100):pos+100]
                        if name in context:
                            issues.append({
                                'type': 'character_break', 'character': name,
                                'location': _line_number(content, pos),
                                'message': f'角色{name}设定为"{personality}"，但出现了"{bw}"，可能存在人设崩坏'
                            })
                            break

    emotion_shift_pattern = r'(愤怒|暴怒|狂怒|悲愤).{0,20}(开心|大笑|愉悦|欣喜)'
    for m in re.finditer(emotion_shift_pattern, content):
        issues.append({
            'type': 'character_break',
            'location': _line_number(content, m.start()),
            'message': f'情绪转换过于突兀，缺少心理过渡'
        })

    return issues[:3]


def detect_pov_drift(content: str, chapter_index: int = 0) -> List[Dict]:
    """POV漂移检测"""
    issues = []
    if not content or len(content) < 500:
        return issues

    paragraphs = [p.strip() for p in content.split('\n') if p.strip() and len(p.strip()) > 30]
    if len(paragraphs) < 3:
        return issues

    first_person = ['我', '我们', '我的']
    third_person = ['他', '她', '它', '他们', '她们']

    first_paras = []
    third_paras = []
    for i, p in enumerate(paragraphs):
        fc = sum(p.count(fp) for fp in first_person)
        tc = sum(p.count(tp) for tp in third_person)
        if fc > tc and fc > 2:
            first_paras.append(i)
        elif tc > fc and tc > 2:
            third_paras.append(i)

    if len(first_paras) > 2 and len(third_paras) > 2:
        for i in range(1, len(paragraphs)):
            if i in first_paras and (i-1) in third_paras:
                pos = content.find(paragraphs[i])
                if pos >= 0:
                    issues.append({
                        'type': 'pov_drift',
                        'location': _line_number(content, pos),
                        'message': '叙事视角可能从第三人称切换到第一人称，检查是否有意为之'
                    })
                    break

    omniscient_patterns = [
        r'(他|她)不知道.{0,30}(其实|实际上|殊不知).{0,50}(另一个人|对方)',
    ]
    for pattern in omniscient_patterns:
        for m in re.finditer(pattern, content):
            issues.append({
                'type': 'pov_drift',
                'location': _line_number(content, m.start()),
                'message': '可能存在全知视角侵入'
            })

    return issues[:3]


def detect_setting_conflict(content: str, chapter_index: int = 0,
                            world_settings: Dict = None) -> List[Dict]:
    """设定冲突检测"""
    issues = []
    if not content:
        return issues

    ancient_markers = ['马车', '客栈', '镖局', '科举', '皇帝', '宫中', '城门', '骑马']
    modern_markers = ['手机', '电脑', '电视', '汽车', '飞机', '网络', 'APP', '微信', '电梯', '空调']
    scifi_markers = ['飞船', '星舰', '量子', '光年', '银河', '星际', '机甲', '人工智能']

    ancient_count = sum(content.count(m) for m in ancient_markers)
    modern_count = sum(content.count(m) for m in modern_markers)
    scifi_count = sum(content.count(m) for m in scifi_markers)

    if ancient_count > 3 and modern_count > 2:
        for mm in modern_markers:
            pos = content.find(mm)
            if pos >= 0:
                issues.append({
                    'type': 'setting_conflict',
                    'location': _line_number(content, pos),
                    'message': f'检测到古代设定中出现了现代物品"{mm}"'
                })
                break

    if ancient_count > 3 and scifi_count > 2:
        for sm in scifi_markers:
            pos = content.find(sm)
            if pos >= 0:
                issues.append({
                    'type': 'setting_conflict',
                    'location': _line_number(content, pos),
                    'message': f'检测到古代设定中出现了科幻元素"{sm}"'
                })
                break

    if world_settings:
        era = world_settings.get('era', '')
        if '古代' in era or '修仙' in era or '仙侠' in era:
            for mm in modern_markers:
                if mm in content:
                    pos = content.find(mm)
                    issues.append({
                        'type': 'setting_conflict',
                        'location': _line_number(content, pos),
                        'message': f'世界观设定为{era}，但出现了"{mm}"'
                    })
                    break

    return issues[:3]


def detect_spatial_consistency(content: str, chapter_index: int = 0,
                               characters: List[Dict] = None) -> List[Dict]:
    """空间一致性检测：角色位置矛盾"""
    issues = []
    if not content or not characters:
        return issues

    paragraphs = [p.strip() for p in content.split('\n') if p.strip()]
    location_patterns = [
        r'(?:在|来到|回到|抵达|进入|赶往|离开)([^\s，。！？]{2,8}?)(?:城|山|谷|洞|宫|殿|阁|楼|院|府|门|宗|营|寨|塔|桥|关)',
    ]

    for char in characters:
        name = char.get('name', '')
        if not name or name not in content:
            continue
        locations = []
        for i, p in enumerate(paragraphs):
            if name in p:
                for pattern in location_patterns:
                    matches = re.findall(pattern, p)
                    for loc in matches:
                        locations.append((i, loc.strip()))

        if len(locations) >= 2:
            for i in range(1, len(locations)):
                prev_para, prev_loc = locations[i-1]
                curr_para, curr_loc = locations[i]
                if curr_para - prev_para <= 2 and prev_loc and curr_loc and prev_loc != curr_loc:
                    movement = any(m in content for m in ['飞', '瞬移', '传送', '赶往', '前往', '奔向'])
                    if not movement:
                        issues.append({
                            'type': 'spatial_consistency', 'character': name,
                            'location': _line_number(content, content.find(paragraphs[curr_para]))
                                if curr_para < len(paragraphs) else 0,
                            'message': f'角色{name}可能存在位置矛盾：从"{prev_loc}"到"{curr_loc}"缺少移动描述'
                        })
                        break

    return issues[:3]


def detect_climax_missing(content: str, chapter_index: int = 0,
                          chapter_info: Dict = None) -> List[Dict]:
    """高潮缺失检测"""
    issues = []
    if not content or len(content) < 500:
        return issues

    is_key_chapter = False
    if chapter_info:
        importance = chapter_info.get('importance', '')
        strand_type = chapter_info.get('strand_type', '')
        if importance in ['climax', 'key', 'turning_point'] or strand_type in ['F', 'C']:
            is_key_chapter = True

    climax_indicators = [
        r'(战|斗|杀|攻|防|挡|劈|刺|轰|爆|裂)',
        r'(怒|悲|痛|哭|喊|吼|嘶|咆哮|怒吼)',
        r'(却|然而|不料|谁知|突然|忽然|蓦地|陡然)',
        r'(终于|终究|到底|毕竟|果不其然|不出所料)',
    ]

    indicator_counts = [len(re.findall(p, content)) for p in climax_indicators]
    total_indicators = sum(indicator_counts)
    climax_density = (total_indicators / max(len(content), 1)) * 1000

    if is_key_chapter and climax_density < 5:
        issues.append({
            'type': 'climax_missing', 'location': 1,
            'message': f'关键章节高潮密度过低（{climax_density:.1f}/千字），缺少冲突、转折或情感爆发'
        })
    elif not is_key_chapter:
        ending = content[-200:] if len(content) > 200 else content
        hook_indicators = ['？', '！', '……', '未知', '不知道', '究竟', '到底', '何去何从', '且看下回']
        hook_count = sum(ending.count(h) for h in hook_indicators)
        if hook_count == 0 and chapter_index > 0:
            issues.append({
                'type': 'climax_missing',
                'location': _line_number(content, len(content) - 200) if len(content) > 200 else 1,
                'message': '章节结尾缺少悬念钩子，可能导致读者流失'
            })

    return issues[:2]


def run_extended_audit(content: str, chapter_index: int = 0,
                       characters: List[Dict] = None,
                       overdue_hooks: List[Dict] = None) -> Dict:
    """运行扩展审计（纯规则，不消耗Token）"""
    ai_result = detect_ai_flavor(content)
    power_result = detect_power_collapse(content, chapter_index, characters)
    ai_score_info = compute_ai_score(ai_result)

    all_issues = list(ai_result['issues']) + list(power_result['issues'])

    logic_issues = detect_logic_gaps(content, chapter_index, characters)
    character_issues = detect_character_break(content, chapter_index, characters)
    pov_issues = detect_pov_drift(content, chapter_index)
    setting_issues = detect_setting_conflict(content, chapter_index)
    spatial_issues = detect_spatial_consistency(content, chapter_index, characters)
    climax_issues = detect_climax_missing(content, chapter_index)

    all_issues.extend(logic_issues)
    all_issues.extend(character_issues)
    all_issues.extend(pov_issues)
    all_issues.extend(setting_issues)
    all_issues.extend(spatial_issues)
    all_issues.extend(climax_issues)

    hook_issues = []
    if overdue_hooks:
        for hook in overdue_hooks:
            hook_text = hook.get('content', '')[:30]
            hook_ch = hook.get('chapter', '?')
            hook_issues.append({
                'type': 'overdue_foreshadowing', 'hook': hook_text,
                'set_at': hook_ch,
                'message': f'overdue foreshadowing from chapter {hook_ch}: {hook_text}...'
            })
    all_issues.extend(hook_issues)

    ai_score = ai_result['score']
    power_score = power_result['score']
    hook_penalty = len(hook_issues) * 5
    ext_audit_penalty = (len(logic_issues) * 8 + len(character_issues) * 6 +
                         len(pov_issues) * 5 + len(setting_issues) * 7 +
                         len(spatial_issues) * 5 + len(climax_issues) * 4)
    overall = min(100, ai_score * 0.4 + power_score * 0.25 + hook_penalty * 0.15 + ext_audit_penalty * 0.2)

    level = 'pass' if overall <= 15 else ('review' if overall <= 40 else 'fail')

    summary = f'Extended audit: {round(overall, 1)}/100 ({level})'
    summary += f' | AI flavor: {ai_result["score"]}'
    summary += f' | Power: {power_result["score"]}'
    summary += f' | Hooks: {len(hook_issues)}'
    summary += f' | Logic/Char/POV/Setting/Spatial/Climax: {len(logic_issues)}/{len(character_issues)}/{len(pov_issues)}/{len(setting_issues)}/{len(spatial_issues)}/{len(climax_issues)}'

    return {
        'ai_flavor': ai_result,
        'power_collapse': power_result,
        'overdue_hooks': hook_issues,
        'logic_gaps': logic_issues,
        'character_break': character_issues,
        'pov_drift': pov_issues,
        'setting_conflict': setting_issues,
        'spatial_consistency': spatial_issues,
        'climax_missing': climax_issues,
        'overall_score': round(overall, 1),
        'overall_level': level,
        'all_issues': all_issues,
        'summary': summary,
        'ai_score': ai_score_info['ai_score'],
        'ai_level': ai_score_info['ai_level']
    }
