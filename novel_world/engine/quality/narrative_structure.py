# -*- coding: utf-8 -*-
"""
叙事结构多样化器 - 解决叙事结构重复问题
支持多种叙事结构模板，避免全是"内心纠结 + 轻微突破"的循环
"""
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum
import random
from collections import defaultdict


class NarrativeStructure(Enum):
    """叙事结构类型"""
    # 基础结构
    LINEAR = "线性推进"           # A → B → C
    EPISODIC = "单元剧式"         # 独立小故事
    
    # 情感结构
    EMOTIONAL_ASCENT = "情感上升"  # 平静 → 紧张 → 高潮
    EMOTIONAL_DESCENT = "情感下降"  # 高潮 → 平静 → 反思
    EMOTIONAL_WAVE = "情感波动"    # 起伏变化
    
    # 冲突结构
    CONFLICT_BUILDUP = "冲突积累"  # 小矛盾 → 中矛盾 → 大矛盾
    CONFLICT_RESOLUTION = "冲突解决"  # 大矛盾 → 解决 → 新平衡
    CONFLICT_CYCLE = "冲突循环"    # 矛盾 → 解决 → 新矛盾
    
    # 探索结构
    DISCOVERY = "发现式"          # 发现线索 → 追踪 → 揭秘
    MYSTERY = "悬疑式"            # 疑问 → 调查 → 真相
    
    # 成长结构
    GROWTH_INTERNAL = "内在成长"   # 困惑 → 领悟 → 改变
    GROWTH_EXTERNAL = "外在成长"   # 挑战 → 克服 → 提升
    GROWTH_BALANCED = "平衡成长"   # 内外兼修
    
    # 互动结构
    DIALOGUE_HEAVY = "对话主导"    # 大量对话推进
    ACTION_HEAVY = "动作主导"      # 大量动作场面
    BALANCED = "平衡式"           # 对话与动作平衡
    
    # 特殊结构
    REVERSAL = "反转式"           # 铺垫 → 反转
    PARALLEL = "平行叙事"         # 多线并行
    FLASHBACK = "闪回式"          # 现实 → 回忆 → 现实


@dataclass
class StructureTemplate:
    """叙事结构模板"""
    name: str
    structure_type: NarrativeStructure
    phases: List[str]           # 阶段列表
    phase_weights: List[float]  # 各阶段权重
    emotion_flow: List[str]     # 情感流向
    action_density: float       # 动作密度 0-1
    dialogue_density: float     # 对话密度 0-1
    description: str = ""


@dataclass
class NarrativePhase:
    """叙事阶段"""
    name: str
    description: str
    emotion: str
    action_type: str            # 动作类型建议
    content_focus: str          # 内容焦点
    duration_weight: float      # 时长权重


class NarrativeStructureManager:
    """叙事结构管理器"""
    
    def __init__(self):
        self._templates: Dict[NarrativeStructure, StructureTemplate] = {}
        self._current_structure: Optional[NarrativeStructure] = None
        self._current_phase: int = 0
        self._phase_count: int = 0
        self._structure_history: List[NarrativeStructure] = []
        self._max_history = 20
        
        self._initialize_templates()
    
    def _initialize_templates(self):
        """初始化叙事结构模板"""
        
        # 线性推进
        self._templates[NarrativeStructure.LINEAR] = StructureTemplate(
            name="线性推进",
            structure_type=NarrativeStructure.LINEAR,
            phases=["起点", "发展", "高潮", "结局"],
            phase_weights=[0.2, 0.3, 0.3, 0.2],
            emotion_flow=["平静", "期待", "紧张", "满足"],
            action_density=0.5,
            dialogue_density=0.5
        )
        
        # 情感上升
        self._templates[NarrativeStructure.EMOTIONAL_ASCENT] = StructureTemplate(
            name="情感上升",
            structure_type=NarrativeStructure.EMOTIONAL_ASCENT,
            phases=["平静开端", "微澜初起", "波澜渐起", "风起云涌", "高潮迭起"],
            phase_weights=[0.15, 0.2, 0.25, 0.25, 0.15],
            emotion_flow=["平静", "好奇", "紧张", "兴奋", "激昂"],
            action_density=0.6,
            dialogue_density=0.4
        )
        
        # 情感下降
        self._templates[NarrativeStructure.EMOTIONAL_DESCENT] = StructureTemplate(
            name="情感下降",
            structure_type=NarrativeStructure.EMOTIONAL_DESCENT,
            phases=["余波未平", "逐渐平复", "反思沉淀", "归于平静"],
            phase_weights=[0.3, 0.3, 0.25, 0.15],
            emotion_flow=["激昂", "释然", "平静", "淡然"],
            action_density=0.3,
            dialogue_density=0.5
        )
        
        # 情感波动
        self._templates[NarrativeStructure.EMOTIONAL_WAVE] = StructureTemplate(
            name="情感波动",
            structure_type=NarrativeStructure.EMOTIONAL_WAVE,
            phases=["起伏", "低谷", "回升", "高峰", "回落"],
            phase_weights=[0.2, 0.2, 0.2, 0.2, 0.2],
            emotion_flow=["紧张", "失落", "希望", "兴奋", "平静"],
            action_density=0.5,
            dialogue_density=0.5
        )
        
        # 冲突积累
        self._templates[NarrativeStructure.CONFLICT_BUILDUP] = StructureTemplate(
            name="冲突积累",
            structure_type=NarrativeStructure.CONFLICT_BUILDUP,
            phases=["隐患初现", "矛盾萌芽", "冲突升级", "矛盾激化", "危机爆发"],
            phase_weights=[0.15, 0.2, 0.25, 0.25, 0.15],
            emotion_flow=["不安", "焦虑", "紧张", "愤怒", "决绝"],
            action_density=0.7,
            dialogue_density=0.3
        )
        
        # 冲突解决
        self._templates[NarrativeStructure.CONFLICT_RESOLUTION] = StructureTemplate(
            name="冲突解决",
            structure_type=NarrativeStructure.CONFLICT_RESOLUTION,
            phases=["直面矛盾", "寻求突破", "关键抉择", "解决矛盾", "新平衡"],
            phase_weights=[0.2, 0.25, 0.25, 0.2, 0.1],
            emotion_flow=["决心", "挣扎", "坚定", "释然", "平静"],
            action_density=0.5,
            dialogue_density=0.5
        )
        
        # 发现式
        self._templates[NarrativeStructure.DISCOVERY] = StructureTemplate(
            name="发现式",
            structure_type=NarrativeStructure.DISCOVERY,
            phases=["蛛丝马迹", "追踪线索", "意外发现", "真相浮现", "豁然开朗"],
            phase_weights=[0.2, 0.25, 0.25, 0.2, 0.1],
            emotion_flow=["好奇", "专注", "惊讶", "震惊", "释然"],
            action_density=0.6,
            dialogue_density=0.4
        )
        
        # 悬疑式
        self._templates[NarrativeStructure.MYSTERY] = StructureTemplate(
            name="悬疑式",
            structure_type=NarrativeStructure.MYSTERY,
            phases=["疑云密布", "抽丝剥茧", "峰回路转", "真相大白"],
            phase_weights=[0.25, 0.3, 0.25, 0.2],
            emotion_flow=["疑惑", "专注", "惊讶", "恍然"],
            action_density=0.4,
            dialogue_density=0.6
        )
        
        # 内在成长
        self._templates[NarrativeStructure.GROWTH_INTERNAL] = StructureTemplate(
            name="内在成长",
            structure_type=NarrativeStructure.GROWTH_INTERNAL,
            phases=["困惑迷茫", "内心挣扎", "顿悟时刻", "蜕变新生"],
            phase_weights=[0.25, 0.3, 0.25, 0.2],
            emotion_flow=["迷茫", "挣扎", "明朗", "坚定"],
            action_density=0.3,
            dialogue_density=0.4
        )
        
        # 外在成长
        self._templates[NarrativeStructure.GROWTH_EXTERNAL] = StructureTemplate(
            name="外在成长",
            structure_type=NarrativeStructure.GROWTH_EXTERNAL,
            phases=["挑战来临", "艰难应对", "突破自我", "实力提升"],
            phase_weights=[0.2, 0.3, 0.3, 0.2],
            emotion_flow=["紧张", "压力", "决心", "自信"],
            action_density=0.7,
            dialogue_density=0.3
        )
        
        # 反转式
        self._templates[NarrativeStructure.REVERSAL] = StructureTemplate(
            name="反转式",
            structure_type=NarrativeStructure.REVERSAL,
            phases=["表面平静", "暗流涌动", "铺垫完成", "惊天反转", "余波震荡"],
            phase_weights=[0.2, 0.2, 0.2, 0.25, 0.15],
            emotion_flow=["平静", "疑惑", "紧张", "震惊", "复杂"],
            action_density=0.5,
            dialogue_density=0.5
        )
        
        # 对话主导
        self._templates[NarrativeStructure.DIALOGUE_HEAVY] = StructureTemplate(
            name="对话主导",
            structure_type=NarrativeStructure.DIALOGUE_HEAVY,
            phases=["相遇", "交谈", "深入", "共识/分歧"],
            phase_weights=[0.2, 0.3, 0.3, 0.2],
            emotion_flow=["好奇", "投入", "共鸣", "感慨"],
            action_density=0.2,
            dialogue_density=0.8
        )
        
        # 动作主导
        self._templates[NarrativeStructure.ACTION_HEAVY] = StructureTemplate(
            name="动作主导",
            structure_type=NarrativeStructure.ACTION_HEAVY,
            phases=["蓄势", "爆发", "激战", "结果"],
            phase_weights=[0.2, 0.3, 0.3, 0.2],
            emotion_flow=["紧张", "兴奋", "激昂", "疲惫/满足"],
            action_density=0.8,
            dialogue_density=0.2
        )
    
    def select_structure(self, context: Dict = None) -> NarrativeStructure:
        """根据上下文选择叙事结构"""
        if context is None:
            context = {}
        
        # 获取上下文信息
        emotion = context.get("emotion", "平静")
        conflict_level = context.get("conflict_level", 0)
        plot_progress = context.get("plot_progress", 0)
        recent_structures = self._structure_history[-5:] if self._structure_history else []
        
        # 根据情况选择结构
        candidates = []
        
        # 高冲突 → 冲突相关结构
        if conflict_level >= 3:
            candidates.extend([
                NarrativeStructure.CONFLICT_BUILDUP,
                NarrativeStructure.CONFLICT_RESOLUTION,
                NarrativeStructure.ACTION_HEAVY
            ])
        
        # 探索/发现场景
        if context.get("is_exploring"):
            candidates.extend([
                NarrativeStructure.DISCOVERY,
                NarrativeStructure.MYSTERY
            ])
        
        # 成长场景
        if context.get("is_growth"):
            candidates.extend([
                NarrativeStructure.GROWTH_INTERNAL,
                NarrativeStructure.GROWTH_EXTERNAL
            ])
        
        # 根据情感选择
        if emotion in ["紧张", "焦虑", "愤怒"]:
            candidates.extend([
                NarrativeStructure.EMOTIONAL_ASCENT,
                NarrativeStructure.CONFLICT_BUILDUP
            ])
        elif emotion in ["平静", "淡然"]:
            candidates.extend([
                NarrativeStructure.LINEAR,
                NarrativeStructure.DIALOGUE_HEAVY
            ])
        elif emotion in ["迷茫", "困惑"]:
            candidates.extend([
                NarrativeStructure.GROWTH_INTERNAL,
                NarrativeStructure.DISCOVERY
            ])
        
        # 避免重复
        for s in recent_structures:
            if s in candidates:
                candidates.remove(s)
        
        # 如果没有候选，随机选择
        if not candidates:
            all_structures = list(NarrativeStructure)
            candidates = [s for s in all_structures if s not in recent_structures]
        
        if not candidates:
            candidates = list(NarrativeStructure)
        
        # 随机选择
        selected = random.choice(candidates)
        self._current_structure = selected
        self._current_phase = 0
        self._structure_history.append(selected)
        
        if len(self._structure_history) > self._max_history:
            self._structure_history = self._structure_history[-self._max_history:]
        
        return selected
    
    def get_current_template(self) -> Optional[StructureTemplate]:
        """获取当前结构模板"""
        if self._current_structure:
            return self._templates.get(self._current_structure)
        return None
    
    def get_current_phase(self) -> Optional[NarrativePhase]:
        """获取当前阶段"""
        template = self.get_current_template()
        if not template:
            return None
        
        if self._current_phase >= len(template.phases):
            self._current_phase = len(template.phases) - 1
        
        phase_name = template.phases[self._current_phase]
        emotion = template.emotion_flow[self._current_phase] if self._current_phase < len(template.emotion_flow) else "平静"
        
        return NarrativePhase(
            name=phase_name,
            description=f"当前处于{phase_name}阶段",
            emotion=emotion,
            action_type="动作" if template.action_density > 0.5 else "对话",
            content_focus=self._get_content_focus(phase_name),
            duration_weight=template.phase_weights[self._current_phase] if self._current_phase < len(template.phase_weights) else 0.2
        )
    
    def _get_content_focus(self, phase_name: str) -> str:
        """获取阶段内容焦点"""
        focus_map = {
            "起点": "建立场景和角色状态",
            "发展": "推进剧情，引入变化",
            "高潮": "冲突爆发，情感激荡",
            "结局": "解决冲突，收束剧情",
            "发现": "揭示新信息，推动探索",
            "转折": "改变方向，制造惊喜",
            "冲突": "展现矛盾，加深张力",
            "解决": "化解矛盾，达成新平衡",
            "成长": "角色变化，能力提升",
        }
        return focus_map.get(phase_name, "推进叙事")
    
    def advance_phase(self) -> bool:
        """推进到下一阶段"""
        template = self.get_current_template()
        if not template:
            return False
        
        self._phase_count += 1
        
        # 根据阶段权重决定是否推进
        if self._current_phase < len(template.phases) - 1:
            current_weight = template.phase_weights[self._current_phase] if self._current_phase < len(template.phase_weights) else 0.2
            
            # 如果当前阶段的内容足够，推进到下一阶段
            if random.random() < current_weight or self._phase_count >= 3:
                self._current_phase += 1
                self._phase_count = 0
                return True
        
        return False
    
    def should_change_structure(self) -> bool:
        """是否应该更换叙事结构"""
        template = self.get_current_template()
        if not template:
            return True
        
        # 如果已经完成所有阶段，应该更换
        if self._current_phase >= len(template.phases) - 1 and self._phase_count >= 2:
            return True
        
        # 随机更换（10%概率）
        if random.random() < 0.1:
            return True
        
        return False
    
    def get_structure_description(self) -> str:
        """获取当前结构描述"""
        template = self.get_current_template()
        phase = self.get_current_phase()
        
        if not template or not phase:
            return ""
        
        return f"[叙事结构: {template.name}] 当前阶段: {phase.name}，情感基调: {phase.emotion}，内容焦点: {phase.content_focus}"


# 单例
_structure_manager_instance = None

def get_structure_manager() -> NarrativeStructureManager:
    global _structure_manager_instance
    if _structure_manager_instance is None:
        _structure_manager_instance = NarrativeStructureManager()
    return _structure_manager_instance
