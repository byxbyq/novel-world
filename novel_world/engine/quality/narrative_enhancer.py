# -*- coding: utf-8 -*-
"""
叙事增强器 - 集成所有叙事优化模块
提供统一的接口来解决叙事重复问题：
- 场景动态变化
- 动作扩展
- 剧情分支
- 缓存管理
"""
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
import random

# 导入所有子模块
from .scene_variator import (
    SceneVariator, get_scene_variator,
    LightCondition, WeatherCondition, AtmosphereType
)
from .action_expander import (
    ActionExpander, get_action_expander,
    ActionType, CharacterRole
)
from .plot_brancher import (
    PlotBrancher, get_plot_brancher,
    ConflictLevel, EmotionPhase, PlotBranchType
)
from .narrative_cache import (
    NarrativeCache, get_narrative_cache,
    ElementType
)


@dataclass
class EnhancedNarrative:
    """增强叙事结果"""
    content: str                    # 叙事内容
    scene_description: str          # 场景描述
    character_actions: List[str]    # 角色动作
    emotional_state: str            # 情感状态
    plot_progress: str              # 剧情进展
    conflicts: List[str]            # 当前矛盾
    is_modified: bool               # 是否被修改


class NarrativeEnhancer:
    """叙事增强器 - 主控制器"""
    
    def __init__(self):
        self.scene_variator = get_scene_variator()
        self.action_expander = get_action_expander()
        self.plot_brancher = get_plot_brancher()
        self.narrative_cache = get_narrative_cache()
        
        self._initialized = False
    
    def initialize(self, theme: str = "日常"):
        """初始化增强器"""
        self._initialized = True
        # 可以根据主题进行特定初始化
    
    def generate_scene_narrative(self, scene_name: str, current_time: int = 0,
                                include_elements: bool = True,
                                include_npc: bool = True) -> str:
        """
        生成场景叙事（动态变化）
        解决：场景设定重复问题
        """
        # 使用场景变化器生成动态描述
        description = self.scene_variator.generate_scene_description(
            scene_name, current_time, include_elements, include_npc
        )
        
        # 检查是否重复
        if self.narrative_cache.avoid_repetition(description):
            # 如果重复，重新生成（强制变化）
            self.scene_variator.update_scene_conditions(scene_name, current_time)
            description = self.scene_variator.generate_scene_description(
                scene_name, current_time, include_elements, include_npc
            )
        
        # 缓存
        self.narrative_cache.register_element(
            ElementType.SCENE, description, f"scene:{scene_name}:{current_time}"
        )
        
        return description
    
    def generate_action_narrative(self, character_name: str, 
                                 role: CharacterRole = CharacterRole.PROTAGONIST,
                                 situation: str = None,
                                 target_name: str = None) -> str:
        """
        生成角色动作叙事（动态扩展）
        解决：人物动作重复问题
        """
        # 使用动作扩展器获取动作
        if situation:
            action = self.action_expander.get_contextual_action(
                character_name, role, situation, target_name
            )
        else:
            action = self.action_expander.get_action(character_name, role)
        
        # 检查是否重复
        key = f"action:{character_name}:{action[:15]}"
        if self.narrative_cache.is_element_used_recently(key, 2):
            # 如果重复，获取不同类型的动作
            action_types = list(ActionType)
            random.shuffle(action_types)
            for action_type in action_types:
                new_action = self.action_expander.get_action(
                    character_name, role, action_type
                )
                if new_action != action:
                    action = new_action
                    break
        
        # 缓存
        self.narrative_cache.register_element(
            ElementType.ACTION, action, key
        )
        
        return action
    
    def generate_plot_narrative(self, context: str = None) -> Tuple[str, str]:
        """
        生成剧情叙事（分支和矛盾升级）
        解决：情节逻辑重复问题
        返回: (叙事内容, 情感描述)
        """
        parts = []
        
        # 检查是否应该升级矛盾
        if self.plot_brancher.should_escalate():
            conflicts = self.plot_brancher.get_current_conflicts()
            if conflicts:
                escalated = self.plot_brancher.escalate_conflict(conflicts[-1])
                if escalated:
                    parts.append(f"矛盾升级：{escalated.description}")
        
        # 获取情感状态
        emotion = self.plot_brancher.get_current_emotion()
        emotion_desc = emotion.value
        
        # 可能的情感转折
        if random.random() < 0.3:  # 30%概率发生情感转折
            turn = self.plot_brancher.get_emotional_turn()
            if turn:
                parts.append(turn.description)
                emotion_desc = turn.to_phase.value
        
        # 推进剧情
        self.plot_brancher.increment_progress()
        
        # 获取剧情状态描述
        plot_desc = self.plot_brancher.generate_plot_description()
        parts.append(plot_desc)
        
        return ("。".join(parts) + "。", emotion_desc)
    
    def generate_transition(self) -> str:
        """生成过渡句"""
        return self.narrative_cache.get_transition()
    
    def enhance_narrative(self, original_content: str, 
                         scene_name: str = None,
                         character_name: str = None,
                         character_role: CharacterRole = None,
                         current_time: int = 0) -> EnhancedNarrative:
        """
        增强叙事内容（主接口）
        对原始内容进行优化，避免重复
        """
        scene_description = ""
        character_actions = []
        is_modified = False
        
        # 1. 场景增强
        if scene_name:
            scene_description = self.generate_scene_narrative(scene_name, current_time)
            if scene_description and scene_description not in original_content:
                is_modified = True
        
        # 2. 动作增强
        if character_name and character_role:
            action = self.generate_action_narrative(character_name, character_role)
            character_actions.append(action)
            if action and action not in original_content:
                is_modified = True
        
        # 3. 剧情增强
        plot_content, emotion_state = self.generate_plot_narrative()
        
        # 4. 获取当前矛盾
        conflicts = [c.name for c in self.plot_brancher.get_current_conflicts()]
        
        # 5. 组合内容
        enhanced_parts = []
        if scene_description:
            enhanced_parts.append(scene_description)
        enhanced_parts.append(original_content)
        if character_actions:
            enhanced_parts.extend(character_actions)
        
        enhanced_content = "。".join(enhanced_parts)
        
        # 6. 推进回合
        self.narrative_cache.advance_round()
        
        return EnhancedNarrative(
            content=enhanced_content,
            scene_description=scene_description,
            character_actions=character_actions,
            emotional_state=emotion_state,
            plot_progress=plot_content,
            conflicts=conflicts,
            is_modified=is_modified
        )
    
    def create_new_conflict(self, level: ConflictLevel, participants: List[str],
                           name: str = None, description: str = None) -> str:
        """创建新矛盾"""
        conflict = self.plot_brancher.create_conflict(level, participants, name, description)
        return f"新矛盾出现：{conflict.name} - {conflict.description}"
    
    def resolve_current_conflict(self, resolution: str = None) -> str:
        """解决当前矛盾"""
        conflicts = self.plot_brancher.get_current_conflicts()
        if conflicts:
            result = self.plot_brancher.resolve_conflict(conflicts[-1], resolution)
            return f"矛盾解决：{result}"
        return ""
    
    def trigger_emotional_turn(self, target_phase: EmotionPhase = None,
                               trigger: str = None) -> str:
        """触发情感转折"""
        turn = self.plot_brancher.get_emotional_turn(target_phase, trigger)
        if turn:
            return turn.description
        return ""
    
    def get_scene_element_interaction(self, scene_name: str) -> Optional[Tuple[str, str]]:
        """获取场景元素交互"""
        return self.scene_variator.get_element_interaction(scene_name)
    
    def get_full_status(self) -> Dict:
        """获取完整状态"""
        return {
            "current_emotion": self.plot_brancher.get_emotion_description(),
            "plot_progress": self.plot_brancher.get_progress(),
            "active_conflicts": len(self.plot_brancher.get_current_conflicts()),
            "cache_stats": self.narrative_cache.get_usage_stats(),
        }
    
    def reset_all(self):
        """重置所有状态"""
        self.scene_variator.reset_all()
        self.action_expander.reset_all()
        self.plot_brancher.reset()
        self.narrative_cache.reset()


# 单例模式
_narrative_enhancer_instance = None

def get_narrative_enhancer() -> NarrativeEnhancer:
    """获取叙事增强器单例"""
    global _narrative_enhancer_instance
    if _narrative_enhancer_instance is None:
        _narrative_enhancer_instance = NarrativeEnhancer()
    return _narrative_enhancer_instance
