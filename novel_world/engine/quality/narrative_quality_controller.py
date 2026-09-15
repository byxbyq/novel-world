# -*- coding: utf-8 -*-
"""
叙事质量控制器 - 解决叙事质量问题
1. 叙事片段去重逻辑
2. 事件因果/时间顺序排序
3. 统一第三人称视角
4. 角色状态连贯性检查
5. 主线事件优先级
6. 叙事元素密度控制
"""
from typing import Dict, List, Optional, Set, Tuple
from dataclasses import dataclass, field
from enum import Enum
import re
import random
from collections import defaultdict


class NarrativePriority(Enum):
    """叙事优先级"""
    CRITICAL = 5      # 关键主线事件
    MAIN = 4          # 主线事件
    IMPORTANT = 3     # 重要支线
    NORMAL = 2        # 普通事件
    TRIVIAL = 1       # 琐碎事件


@dataclass
class NarrativeFragment:
    """叙事片段"""
    content: str                      # 片段内容
    timestamp: int                    # 时间戳
    cause: str = ""                   # 原因事件
    effect: str = ""                  # 结果事件
    priority: NarrativePriority = NarrativePriority.NORMAL
    scene: str = ""                   # 场景
    characters: List[str] = field(default_factory=list)  # 涉及角色
    items: List[str] = field(default_factory=list)       # 涉及道具
    actions: List[str] = field(default_factory=list)     # 动作
    emotions: List[str] = field(default_factory=list)    # 情感
    is_main_plot: bool = False        # 是否主线
    fragment_id: str = ""             # 片段ID


@dataclass
class CharacterStateTracker:
    """角色状态追踪器"""
    character_name: str
    current_state: str = ""
    current_emotion: str = "平静"
    current_location: str = ""
    last_action: str = ""
    state_history: List[Tuple[int, str]] = field(default_factory=list)  # (时间戳, 状态)
    emotion_history: List[Tuple[int, str]] = field(default_factory=list)


class NarrativeQualityController:
    """叙事质量控制器"""
    
    def __init__(self):
        # 叙事片段存储
        self._fragments: List[NarrativeFragment] = []
        self._max_fragments = 100
        
        # 去重相关
        self._scene_history: List[str] = []
        self._action_history: List[str] = []
        self._item_history: List[str] = []
        self._max_history = 20
        
        # 角色状态追踪
        self._character_trackers: Dict[str, CharacterStateTracker] = {}
        
        # 当前时间戳
        self._current_timestamp = 0
        
        # 视角设置
        self._perspective = "第三人称"
        self._protagonist_name = ""
        
        # 元素密度控制
        self._max_elements_per_fragment = 5  # 每条叙事最多5个主要元素
        self._max_description_length = 200   # 描述最大长度
        
        # 主线关键词
        self._main_plot_keywords = [
            "目标", "使命", "命运", "关键", "决定", "转折",
            "突破", "危机", "抉择", "真相", "揭示", "对抗"
        ]
        
        # 无关支线关键词
        self._trivial_keywords = [
            "路过", "偶然", "顺便", "无关", "琐事", "日常"
        ]
    
    # ========== 1. 叙事片段去重 ==========
    
    def check_duplicate(self, fragment: NarrativeFragment) -> Tuple[bool, str]:
        """
        检查叙事片段是否重复
        返回: (是否重复, 重复类型)
        """
        content = fragment.content
        
        # 检查场景重复
        if fragment.scene:
            recent_scenes = self._scene_history[-5:]
            if fragment.scene in recent_scenes:
                return (True, f"场景重复: {fragment.scene}")
        
        # 检查动作重复
        for action in fragment.actions:
            recent_actions = self._action_history[-3:]
            if action in recent_actions:
                return (True, f"动作重复: {action}")
        
        # 检查道具重复
        for item in fragment.items:
            recent_items = self._item_history[-3:]
            if item in recent_items:
                return (True, f"道具重复: {item}")
        
        # 检查内容相似度
        for existing in self._fragments[-10:]:
            similarity = self._calculate_similarity(content, existing.content)
            if similarity > 0.7:  # 70%相似度阈值
                return (True, "内容相似度过高")
        
        return (False, "")
    
    def _calculate_similarity(self, text1: str, text2: str) -> float:
        """计算文本相似度"""
        if not text1 or not text2:
            return 0.0
        
        # 简单的词频相似度
        words1 = set(text1)
        words2 = set(text2)
        
        intersection = len(words1 & words2)
        union = len(words1 | words2)
        
        if union == 0:
            return 0.0
        
        return intersection / union
    
    def register_fragment(self, fragment: NarrativeFragment):
        """注册叙事片段（用于去重）"""
        # 更新历史
        if fragment.scene:
            self._scene_history.append(fragment.scene)
            if len(self._scene_history) > self._max_history:
                self._scene_history = self._scene_history[-self._max_history:]
        
        self._action_history.extend(fragment.actions)
        if len(self._action_history) > self._max_history:
            self._action_history = self._action_history[-self._max_history:]
        
        self._item_history.extend(fragment.items)
        if len(self._item_history) > self._max_history:
            self._item_history = self._item_history[-self._max_history:]
        
        # 存储片段
        self._fragments.append(fragment)
        if len(self._fragments) > self._max_fragments:
            self._fragments = self._fragments[-self._max_fragments:]
    
    # ========== 2. 事件因果/时间顺序排序 ==========
    
    def sort_fragments(self, fragments: List[NarrativeFragment]) -> List[NarrativeFragment]:
        """按因果/时间顺序排序叙事片段"""
        if not fragments:
            return fragments
        
        # 构建因果图
        cause_effect_map: Dict[str, List[str]] = defaultdict(list)
        fragment_map: Dict[str, NarrativeFragment] = {}
        
        for f in fragments:
            if f.fragment_id:
                fragment_map[f.fragment_id] = f
                if f.cause:
                    cause_effect_map[f.cause].append(f.fragment_id)
        
        # 拓扑排序
        sorted_ids = []
        visited = set()
        
        def visit(fid: str):
            if fid in visited:
                return
            visited.add(fid)
            
            # 先访问原因事件
            f = fragment_map.get(fid)
            if f and f.cause and f.cause in fragment_map:
                visit(f.cause)
            
            sorted_ids.append(fid)
        
        # 按时间戳排序后进行拓扑排序
        sorted_by_time = sorted(fragments, key=lambda x: x.timestamp)
        for f in sorted_by_time:
            if f.fragment_id:
                visit(f.fragment_id)
        
        # 构建结果
        result = []
        for fid in sorted_ids:
            if fid in fragment_map:
                result.append(fragment_map[fid])
        
        return result
    
    # ========== 3. 统一第三人称视角 ==========
    
    def enforce_third_person(self, content: str, protagonist: str = None) -> str:
        """强制转换为第三人称视角"""
        if protagonist:
            self._protagonist_name = protagonist
        
        # 第一人称代词映射
        first_person_map = {
            "我": protagonist or "他",
            "我们": "他们",
            "我的": f"{protagonist or '他'}的",
            "我们的": "他们的",
            "我自己": f"{protagonist or '他'}自己",
        }
        
        # 第二人称代词映射
        second_person_map = {
            "你": "他",
            "你们": "他们",
            "你的": "他的",
            "你们的": "他们的",
        }
        
        result = content
        
        # 替换第一人称
        for first, third in first_person_map.items():
            result = result.replace(first, third)
        
        # 替换第二人称（除非是对话中的）
        # 简单处理：不在引号内的"你"替换为"他"
        in_quote = False
        chars = list(result)
        for i, char in enumerate(chars):
            if char in '"「『':
                in_quote = True
            elif char in '"」』':
                in_quote = False
            elif not in_quote and char == '你':
                chars[i] = '他'
        
        result = ''.join(chars)
        
        return result
    
    # ========== 4. 角色状态连贯性检查 ==========
    
    def check_character_coherence(self, character_name: str, 
                                  new_state: str = None,
                                  new_emotion: str = None,
                                  new_action: str = None) -> Tuple[bool, List[str]]:
        """
        检查角色状态连贯性
        返回: (是否连贯, 警告信息列表)
        """
        warnings = []
        is_coherent = True
        
        # 获取或创建追踪器
        if character_name not in self._character_trackers:
            self._character_trackers[character_name] = CharacterStateTracker(
                character_name=character_name
            )
        
        tracker = self._character_trackers[character_name]
        
        # 检查状态突变
        if new_state and tracker.current_state:
            # 定义合理的状态转换
            valid_transitions = {
                "空闲": ["移动中", "工作中", "战斗中", "交谈中"],
                "移动中": ["空闲", "工作中", "探索中", "战斗中"],
                "工作中": ["空闲", "休息中", "移动中"],
                "战斗中": ["空闲", "移动中", "休息中"],
                "交谈中": ["空闲", "移动中", "工作中"],
                "探索中": ["空闲", "战斗中", "移动中"],
                "休息中": ["空闲", "移动中", "工作中"],
            }
            
            allowed = valid_transitions.get(tracker.current_state, [])
            if new_state not in allowed and new_state != tracker.current_state:
                warnings.append(f"角色状态突变: {tracker.current_state} → {new_state}")
                is_coherent = False
        
        # 检查情感突变
        if new_emotion and tracker.current_emotion:
            # 情感变化应该是渐进的
            emotion_distance = self._get_emotion_distance(
                tracker.current_emotion, new_emotion
            )
            if emotion_distance > 2:  # 情感跨度太大
                warnings.append(f"情感突变: {tracker.current_emotion} → {new_emotion}")
                # 这不算不连贯，只是需要注意
                # is_coherent = False  # 注释掉，情感突变可以接受
        
        # 检查动作连贯性
        if new_action and tracker.last_action:
            # 某些动作组合不合理
            invalid_combinations = [
                ("休息中", "战斗"),
                ("战斗中", "睡觉"),
                ("死亡", "移动"),
            ]
            for state, action in invalid_combinations:
                if tracker.current_state == state and action in new_action:
                    warnings.append(f"状态与动作不匹配: {state} 状态下不能 {action}")
                    is_coherent = False
        
        return (is_coherent, warnings)
    
    def _get_emotion_distance(self, emotion1: str, emotion2: str) -> int:
        """计算情感距离"""
        # 情感环形模型
        emotions = [
            "平静", "满足", "喜悦", "兴奋",
            "紧张", "焦虑", "愤怒", "恐惧",
            "悲伤", "失望", "释然", "希望"
        ]
        
        if emotion1 not in emotions or emotion2 not in emotions:
            return 0
        
        idx1 = emotions.index(emotion1)
        idx2 = emotions.index(emotion2)
        
        # 环形距离
        direct = abs(idx1 - idx2)
        circular = len(emotions) - direct
        
        return min(direct, circular)
    
    def update_character_state(self, character_name: str,
                               state: str = None,
                               emotion: str = None,
                               action: str = None):
        """更新角色状态"""
        if character_name not in self._character_trackers:
            self._character_trackers[character_name] = CharacterStateTracker(
                character_name=character_name
            )
        
        tracker = self._character_trackers[character_name]
        
        if state:
            tracker.state_history.append((self._current_timestamp, state))
            tracker.current_state = state
        
        if emotion:
            tracker.emotion_history.append((self._current_timestamp, emotion))
            tracker.current_emotion = emotion
        
        if action:
            tracker.last_action = action
    
    # ========== 5. 主线事件优先级 ==========
    
    def calculate_priority(self, content: str, is_explicit_main: bool = False) -> NarrativePriority:
        """计算叙事片段优先级"""
        if is_explicit_main:
            return NarrativePriority.CRITICAL
        
        # 检查主线关键词
        main_count = sum(1 for kw in self._main_plot_keywords if kw in content)
        if main_count >= 2:
            return NarrativePriority.CRITICAL
        elif main_count == 1:
            return NarrativePriority.MAIN
        
        # 检查无关支线关键词
        trivial_count = sum(1 for kw in self._trivial_keywords if kw in content)
        if trivial_count >= 2:
            return NarrativePriority.TRIVIAL
        elif trivial_count == 1:
            return NarrativePriority.NORMAL
        
        return NarrativePriority.IMPORTANT
    
    def filter_by_priority(self, fragments: List[NarrativeFragment],
                          min_priority: NarrativePriority = NarrativePriority.NORMAL) -> List[NarrativeFragment]:
        """按优先级过滤叙事片段"""
        return [f for f in fragments if f.priority.value >= min_priority.value]
    
    # ========== 6. 叙事元素密度控制 ==========
    
    def control_density(self, content: str) -> str:
        """控制叙事元素密度，减少冗余描写"""
        # 提取元素
        elements = self._extract_elements(content)
        
        # 如果元素过多，进行精简
        if len(elements) > self._max_elements_per_fragment:
            # 保留最重要的元素
            important_elements = elements[:self._max_elements_per_fragment]
            content = self._rebuild_content(content, important_elements)
        
        # 控制描述长度
        if len(content) > self._max_description_length:
            # 截断到最大长度，保持句子完整
            content = self._truncate_content(content, self._max_description_length)
        
        return content
    
    def _extract_elements(self, content: str) -> List[str]:
        """提取叙事元素"""
        elements = []
        
        # 提取场景词
        scene_patterns = ["在", "来到", "进入", "离开"]
        for pattern in scene_patterns:
            matches = re.findall(f'{pattern}(.{{2,10}})', content)
            elements.extend(matches)
        
        # 提取动作词
        action_patterns = ["着", "了", "过"]
        for pattern in action_patterns:
            matches = re.findall(f'(.{{2,6}}){pattern}', content)
            elements.extend(matches)
        
        return list(set(elements))  # 去重
    
    def _rebuild_content(self, content: str, elements: List[str]) -> str:
        """根据保留的元素重建内容"""
        # 简单实现：保留包含重要元素的句子
        sentences = re.split('[。！？]', content)
        important_sentences = []
        
        for sentence in sentences:
            if any(elem in sentence for elem in elements):
                important_sentences.append(sentence)
        
        return '。'.join(important_sentences) + '。'
    
    def _truncate_content(self, content: str, max_length: int) -> str:
        """截断内容到最大长度"""
        if len(content) <= max_length:
            return content
        
        # 找到最后一个句号的位置
        truncated = content[:max_length]
        last_period = truncated.rfind('。')
        
        if last_period > max_length * 0.7:  # 如果句号位置合理
            return truncated[:last_period + 1]
        else:
            return truncated + '……'
    
    # ========== 工具方法 ==========
    
    def advance_timestamp(self):
        """推进时间戳"""
        self._current_timestamp += 1
    
    def get_current_timestamp(self) -> int:
        """获取当前时间戳"""
        return self._current_timestamp
    
    def reset(self):
        """重置所有状态"""
        self._fragments.clear()
        self._scene_history.clear()
        self._action_history.clear()
        self._item_history.clear()
        self._character_trackers.clear()
        self._current_timestamp = 0


# 单例
_quality_controller_instance = None

def get_quality_controller() -> NarrativeQualityController:
    global _quality_controller_instance
    if _quality_controller_instance is None:
        _quality_controller_instance = NarrativeQualityController()
    return _quality_controller_instance
