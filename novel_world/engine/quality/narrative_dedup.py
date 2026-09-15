# -*- coding: utf-8 -*-
"""
叙事去重系统 - 检测并防止相似场景重复

核心功能：
1. 提取叙事的场景特征
2. 计算场景相似度
3. 提供去重建议
"""

import re
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass, field
from collections import Counter


@dataclass
class SceneFeature:
    """场景特征"""
    characters: List[str]          # 涉及的角色
    actions: List[str]             # 动作列表
    objects: List[str]             # 物品列表
    location: str                  # 地点
    emotion: str                   # 情感基调
    key_phrases: List[str]         # 关键短语
    
    def to_vector(self) -> Tuple:
        """转换为可比较的向量"""
        return (
            tuple(sorted(self.characters)),
            tuple(sorted(self.actions)),
            tuple(sorted(self.objects)),
            self.location,
            self.emotion,
        )


class NarrativeDeduplicator:
    """叙事去重系统"""
    
    # 动作关键词
    ACTION_WORDS = {
        "递送": ["递", "送", "给", "递给", "送给"],
        "触碰": ["触碰", "碰到", "触到", "手指", "指尖"],
        "对话": ["说", "问", "答", "道", "轻声", "笑着"],
        "移动": ["走", "来", "去", "离开", "到达"],
        "情感": ["脸红", "紧张", "心跳", "耳根红", "局促", "害羞"],
        "饮食": ["喝", "吃", "尝", "温水", "热水", "牛奶"],
        "关系": ["牵手", "拥抱", "表白", "约定"],
    }
    
    # 物品关键词
    OBJECT_WORDS = [
        "蛋糕", "咖啡", "牛奶", "水", "茶", "酒",
        "书", "信", "礼物", "花", "戒指",
        "手机", "电脑", "钥匙", "钱包",
    ]
    
    # 地点关键词
    LOCATION_WORDS = [
        "玄关", "客厅", "厨房", "卧室", "阳台",
        "街道", "公园", "咖啡", "便利店", "医院",
        "公司", "办公室", "学校", "书店",
    ]
    
    # 情感关键词
    EMOTION_PATTERNS = {
        "温馨": ["温柔", "温暖", "关心", "体贴", "微笑"],
        "紧张": ["紧张", "局促", "心跳", "脸红", "耳根红"],
        "悲伤": ["悲伤", "难过", "眼泪", "哭", "失落"],
        "快乐": ["开心", "高兴", "快乐", "笑", "欢乐"],
        "浪漫": ["浪漫", "甜蜜", "心动", "暧昧", "温柔"],
        "冲突": ["争吵", "冲突", "矛盾", "不满", "生气"],
    }
    
    # 高频重复场景模板（需要特别警惕）
    HIGH_FREQ_TEMPLATES = [
        {
            "name": "递蛋糕场景",
            "pattern": r"蛋糕.*递|递.*蛋糕",
            "keywords": ["蛋糕", "递", "手", "指尖"],
        },
        {
            "name": "手凉喝热水场景",
            "pattern": r"手凉.*喝|喝.*手凉|温水|热水",
            "keywords": ["手凉", "喝", "水", "温"],
        },
        {
            "name": "触碰场景",
            "pattern": r"指尖.*触碰|触碰.*指尖",
            "keywords": ["指尖", "触碰", "手", "温热"],
        },
        {
            "name": "脸红场景",
            "pattern": r"脸红|耳根红|脸颊.*红",
            "keywords": ["脸", "红", "耳根", "脸颊"],
        },
    ]
    
    MAX_HISTORY = 50              # 保留的历史叙事数
    SIMILARITY_THRESHOLD = 0.5    # 相似度阈值
    
    def __init__(self):
        self.history: List[Tuple[str, SceneFeature]] = []  # (原始叙事, 场景特征)
        self._compiled_patterns = self._compile_patterns()
        self._template_patterns = self._compile_template_patterns()
    
    def _compile_patterns(self) -> Dict[str, re.Pattern]:
        """编译正则模式"""
        patterns = {}
        
        # 动作模式
        for action_type, words in self.ACTION_WORDS.items():
            pattern = "|".join(re.escape(w) for w in words)
            patterns[f"action_{action_type}"] = re.compile(pattern)
        
        # 情感模式
        for emotion, words in self.EMOTION_PATTERNS.items():
            pattern = "|".join(re.escape(w) for w in words)
            patterns[f"emotion_{emotion}"] = re.compile(pattern)
        
        return patterns
    
    def _compile_template_patterns(self) -> List[Dict]:
        """编译高频模板模式"""
        templates = []
        for template in self.HIGH_FREQ_TEMPLATES:
            templates.append({
                "name": template["name"],
                "pattern": re.compile(template["pattern"]),
                "keywords": template["keywords"],
            })
        return templates
    
    def extract_features(self, narrative: str, known_characters: List[str] = None) -> SceneFeature:
        """从叙事中提取场景特征"""
        
        # 提取角色
        characters = []
        if known_characters:
            for char in known_characters:
                if char in narrative:
                    characters.append(char)
        
        # 提取动作
        actions = []
        for action_type, words in self.ACTION_WORDS.items():
            for word in words:
                if word in narrative:
                    actions.append(action_type)
                    break
        
        # 提取物品
        objects = [obj for obj in self.OBJECT_WORDS if obj in narrative]
        
        # 提取地点
        location = "某处"
        for loc in self.LOCATION_WORDS:
            if loc in narrative:
                location = loc
                break
        
        # 提取情感
        emotion = "中性"
        for emo, words in self.EMOTION_PATTERNS.items():
            for word in words:
                if word in narrative:
                    emotion = emo
                    break
            if emotion != "中性":
                break
        
        # 提取关键短语（2-4字的词，按频率排序）
        words = re.findall(r'[一-鿿]{2,4}', narrative)
        word_freq = Counter(words)
        key_phrases = [w for w, _ in word_freq.most_common(10)]
        
        return SceneFeature(
            characters=characters,
            actions=list(set(actions)),
            objects=objects,
            location=location,
            emotion=emotion,
            key_phrases=key_phrases,
        )
    
    def calculate_similarity(self, feature1: SceneFeature, feature2: SceneFeature) -> float:
        """计算两个场景特征的相似度"""
        score = 0.0
        
        # 角色重叠 (权重 0.3)
        if feature1.characters and feature2.characters:
            char_overlap = len(set(feature1.characters) & set(feature2.characters))
            char_union = len(set(feature1.characters) | set(feature2.characters))
            if char_union > 0:
                score += 0.3 * (char_overlap / char_union)
        
        # 动作重叠 (权重 0.25)
        if feature1.actions and feature2.actions:
            action_overlap = len(set(feature1.actions) & set(feature2.actions))
            action_union = len(set(feature1.actions) | set(feature2.actions))
            if action_union > 0:
                score += 0.25 * (action_overlap / action_union)
        
        # 物品重叠 (权重 0.15)
        if feature1.objects and feature2.objects:
            obj_overlap = len(set(feature1.objects) & set(feature2.objects))
            obj_union = len(set(feature1.objects) | set(feature2.objects))
            if obj_union > 0:
                score += 0.15 * (obj_overlap / obj_union)
        
        # 地点相同 (权重 0.1)
        if feature1.location == feature2.location and feature1.location != "某处":
            score += 0.1
        
        # 情感相同 (权重 0.1)
        if feature1.emotion == feature2.emotion and feature1.emotion != "中性":
            score += 0.1
        
        # 关键短语重叠 (权重 0.1)
        if feature1.key_phrases and feature2.key_phrases:
            phrase_overlap = len(set(feature1.key_phrases) & set(feature2.key_phrases))
            phrase_union = len(set(feature1.key_phrases) | set(feature2.key_phrases))
            if phrase_union > 0:
                score += 0.1 * (phrase_overlap / phrase_union)
        
        return score
    
    def check_high_freq_template(self, narrative: str) -> Tuple[bool, Optional[str], int]:
        """
        检查是否匹配高频重复模板
        
        Returns:
            (是否匹配, 模板名称, 历史中出现次数)
        """
        for template in self._template_patterns:
            if template["pattern"].search(narrative):
                # 计算历史中匹配此模板的次数
                count = 0
                for hist_narrative, _ in self.history:
                    if template["pattern"].search(hist_narrative):
                        # 检查关键词是否也匹配
                        keyword_match = sum(1 for kw in template["keywords"] if kw in hist_narrative)
                        if keyword_match >= len(template["keywords"]) * 0.5:
                            count += 1
                return (True, template["name"], count)
        
        return (False, None, 0)
    
    def add_to_history(self, narrative: str, known_characters: List[str] = None):
        """将叙事添加到历史"""
        feature = self.extract_features(narrative, known_characters)
        self.history.append((narrative, feature))
        
        # 限制历史长度
        if len(self.history) > self.MAX_HISTORY:
            self.history = self.history[-self.MAX_HISTORY:]
    
    def check_duplicate(self, narrative: str, known_characters: List[str] = None) -> Tuple[bool, float, Optional[str], int]:
        """
        检查叙事是否重复
        
        Args:
            narrative: 新叙事
            known_characters: 已知角色列表
        
        Returns:
            (是否重复, 相似度, 最相似的历史叙事, 高频模板出现次数)
        """
        # 1. 检查高频模板
        is_template, template_name, template_count = self.check_high_freq_template(narrative)
        if is_template and template_count >= 2:
            # 如果高频模板已出现2次以上，直接判定为重复
            return (True, 0.8, f"【{template_name}】已出现{template_count}次", template_count)
        
        # 2. 计算与历史叙事的相似度
        if not self.history:
            return (False, 0.0, None, template_count)
        
        new_feature = self.extract_features(narrative, known_characters)
        
        max_similarity = 0.0
        most_similar = None
        
        # 只检查最近的20条
        for hist_narrative, hist_feature in self.history[-20:]:
            sim = self.calculate_similarity(new_feature, hist_feature)
            if sim > max_similarity:
                max_similarity = sim
                most_similar = hist_narrative[:50] + "..." if len(hist_narrative) > 50 else hist_narrative
        
        is_duplicate = max_similarity >= self.SIMILARITY_THRESHOLD
        return (is_duplicate, max_similarity, most_similar, template_count)
    
    def get_duplicate_report(self, narrative: str, known_characters: List[str] = None) -> str:
        """获取重复检测报告"""
        is_dup, sim, similar_narrative, template_count = self.check_duplicate(narrative, known_characters)
        
        if not is_dup:
            return ""
        
        report_lines = ["【重复检测警告】"]
        
        if template_count >= 2:
            report_lines.append(f"此场景类型已重复出现 {template_count} 次，建议更换场景")
        
        if sim >= self.SIMILARITY_THRESHOLD:
            report_lines.append(f"与历史叙事相似度: {sim:.2f}")
            if similar_narrative:
                report_lines.append(f"相似叙事: {similar_narrative}")
        
        return "\n".join(report_lines)
    
    def get_recent_similar_scenes(self, narrative: str, known_characters: List[str] = None, limit: int = 5) -> List[str]:
        """获取最近相似的场景"""
        if not self.history:
            return []
        
        new_feature = self.extract_features(narrative, known_characters)
        
        similarities = []
        for hist_narrative, hist_feature in self.history[-20:]:
            sim = self.calculate_similarity(new_feature, hist_feature)
            if sim >= 0.3:  # 只返回有一定相似度的
                similarities.append((sim, hist_narrative))
        
        # 按相似度排序
        similarities.sort(reverse=True, key=lambda x: x[0])
        
        return [narr for _, narr in similarities[:limit]]
    
    def clear(self):
        """清空历史"""
        self.history.clear()
    
    def get_stats(self) -> dict:
        """获取统计信息"""
        # 统计各种场景类型的出现次数
        action_counts = Counter()
        emotion_counts = Counter()
        location_counts = Counter()
        
        for _, feature in self.history:
            for action in feature.actions:
                action_counts[action] += 1
            emotion_counts[feature.emotion] += 1
            location_counts[feature.location] += 1
        
        return {
            "total_narratives": len(self.history),
            "action_distribution": dict(action_counts.most_common(10)),
            "emotion_distribution": dict(emotion_counts.most_common(10)),
            "location_distribution": dict(location_counts.most_common(10)),
        }


# 全局单例
_deduplicator_instance: Optional[NarrativeDeduplicator] = None


def get_narrative_deduplicator() -> NarrativeDeduplicator:
    """获取叙事去重系统单例"""
    global _deduplicator_instance
    if _deduplicator_instance is None:
        _deduplicator_instance = NarrativeDeduplicator()
    return _deduplicator_instance


def reset_narrative_deduplicator():
    """重置叙事去重系统"""
    global _deduplicator_instance
    _deduplicator_instance = None
