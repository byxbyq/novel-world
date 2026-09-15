# -*- coding: utf-8 -*-
"""
剧情分支系统 - 解决情节逻辑重复问题
提供剧情分支和矛盾升级的接口，支持：
- 矛盾升级机制（小矛盾→大矛盾→核心矛盾）
- 情感转折点（情绪变化、关系变化）
- 剧情分支选择（多线叙事）
- 动态剧情推进
"""
from typing import Dict, List, Optional, Tuple, Set
from dataclasses import dataclass, field
from enum import Enum
import random
from collections import defaultdict


class ConflictLevel(Enum):
    """矛盾等级"""
    TRIVIAL = "琐碎"      # 日常小摩擦
    MINOR = "轻微"        # 小矛盾
    MODERATE = "中等"     # 中等矛盾
    MAJOR = "重大"        # 大矛盾
    CRITICAL = "核心"     # 核心矛盾


class EmotionPhase(Enum):
    """情感阶段"""
    CALM = "平静"
    TENSE = "紧张"
    AWKWARD = "尴尬"
    WARM = "温馨"
    HOPEFUL = "希望"
    DESPAIR = "绝望"
    EXCITED = "兴奋"
    MELANCHOLY = "忧伤"
    DETERMINED = "坚定"
    CONFUSED = "困惑"


class PlotBranchType(Enum):
    """剧情分支类型"""
    MAIN = "主线"
    SIDE = "支线"
    SECRET = "隐藏线"
    EMERGENCY = "突发线"


@dataclass
class ConflictNode:
    """矛盾节点"""
    name: str
    level: ConflictLevel
    description: str
    participants: List[str]  # 参与者
    possible_resolutions: List[str]  # 可能的解决方式
    escalation_paths: List[str] = field(default_factory=list)  # 升级路径
    de_escalation_paths: List[str] = field(default_factory=list)  # 降级路径
    is_resolved: bool = False


@dataclass
class EmotionalTurn:
    """情感转折点"""
    from_phase: EmotionPhase
    to_phase: EmotionPhase
    trigger: str  # 触发原因
    description: str
    intensity: int = 1  # 转折强度 1-5


@dataclass
class PlotBranch:
    """剧情分支"""
    branch_id: str
    branch_type: PlotBranchType
    name: str
    description: str
    current_node: str
    nodes: List[str] = field(default_factory=list)
    conflicts: List[ConflictNode] = field(default_factory=list)
    emotional_arc: List[EmotionPhase] = field(default_factory=list)
    is_active: bool = True
    priority: int = 1  # 优先级


class PlotBrancher:
    """剧情分支系统"""
    
    def __init__(self):
        self._branches: Dict[str, PlotBranch] = {}
        self._active_conflicts: List[ConflictNode] = []
        self._resolved_conflicts: List[ConflictNode] = []
        self._current_emotion: EmotionPhase = EmotionPhase.CALM
        self._emotion_history: List[EmotionPhase] = [EmotionPhase.CALM]
        self._conflict_templates: Dict[ConflictLevel, List[Dict]] = {}
        self._emotion_transition_rules: Dict[Tuple, List[str]] = {}
        self._plot_progress: int = 0  # 剧情进度
        self._max_same_emotion = 3  # 同一情感最大连续次数
        
        self._initialize_conflict_templates()
        self._initialize_emotion_rules()
    
    def _initialize_conflict_templates(self):
        """初始化矛盾模板"""
        
        self._conflict_templates[ConflictLevel.TRIVIAL] = [
            {"name": "言语误会", "desc": "一句话引起的误会", "resolution": ["解释清楚", "一笑置之", "沉默应对"]},
            {"name": "小摩擦", "desc": "日常生活中的小摩擦", "resolution": ["互相让步", "忽略不计", "稍作争执"]},
            {"name": "意见分歧", "desc": "对某事看法不同", "resolution": ["求同存异", "各执己见", "折中妥协"]},
        ]
        
        self._conflict_templates[ConflictLevel.MINOR] = [
            {"name": "信任危机", "desc": "对某人产生怀疑", "resolution": ["坦诚相谈", "暗中观察", "保持距离"]},
            {"name": "利益冲突", "desc": "利益分配产生分歧", "resolution": ["协商解决", "让步妥协", "坚持己见"]},
            {"name": "立场对立", "desc": "双方立场不同", "resolution": ["寻找共同点", "各退一步", "坚持立场"]},
        ]
        
        self._conflict_templates[ConflictLevel.MODERATE] = [
            {"name": "背叛嫌疑", "desc": "怀疑有人背叛", "resolution": ["调查真相", "直接质问", "暗中防备"]},
            {"name": "理念冲突", "desc": "核心价值观冲突", "resolution": ["深入讨论", "分道扬镳", "暂时搁置"]},
            {"name": "资源争夺", "desc": "重要资源的争夺", "resolution": ["公平竞争", "协商分配", "武力解决"]},
        ]
        
        self._conflict_templates[ConflictLevel.MAJOR] = [
            {"name": "生死抉择", "desc": "面临生死攸关的选择", "resolution": ["勇敢面对", "寻求他法", "牺牲妥协"]},
            {"name": "阵营决裂", "desc": "与重要势力决裂", "resolution": ["修复关系", "寻找新盟友", "独自面对"]},
            {"name": "真相揭露", "desc": "重要真相被揭露", "resolution": ["接受现实", "否认逃避", "重新评估"]},
        ]
        
        self._conflict_templates[ConflictLevel.CRITICAL] = [
            {"name": "命运抉择", "desc": "决定命运的关键时刻", "resolution": ["遵从内心", "理性抉择", "寻求指引"]},
            {"name": "终极对决", "desc": "与核心对手的最终对决", "resolution": ["全力以赴", "智取胜过力敌", "寻找弱点"]},
            {"name": "信念崩塌", "desc": "核心信念受到挑战", "resolution": ["重建信念", "寻找新方向", "接受改变"]},
        ]
    
    def _initialize_emotion_rules(self):
        """初始化情感转换规则"""
        
        # (from_phase, to_phase) -> [可能的触发原因]
        self._emotion_transition_rules = {
            (EmotionPhase.CALM, EmotionPhase.TENSE): ["发现异常", "感知危险", "气氛变化"],
            (EmotionPhase.CALM, EmotionPhase.WARM): ["善意举动", "温馨场景", "友好互动"],
            (EmotionPhase.CALM, EmotionPhase.CONFUSED): ["意外消息", "难以理解的事", "矛盾信息"],
            
            (EmotionPhase.TENSE, EmotionPhase.AWKWARD): ["说错话", "尴尬场面", "误会加深"],
            (EmotionPhase.TENSE, EmotionPhase.DETERMINED): ["下定决心", "找到方向", "鼓起勇气"],
            (EmotionPhase.TENSE, EmotionPhase.DESPAIR): ["希望破灭", "陷入绝境", "无力回天"],
            
            (EmotionPhase.AWKWARD, EmotionPhase.WARM): ["打破僵局", "善意化解", "幽默解围"],
            (EmotionPhase.AWKWARD, EmotionPhase.TENSE): ["矛盾升级", "新的冲突", "压力增加"],
            
            (EmotionPhase.WARM, EmotionPhase.HOPEFUL): ["看到希望", "关系改善", "取得进展"],
            (EmotionPhase.WARM, EmotionPhase.MELANCHOLY): ["想起往事", "离别在即", "美好易逝"],
            
            (EmotionPhase.HOPEFUL, EmotionPhase.EXCITED): ["好消息", "目标接近", "意外惊喜"],
            (EmotionPhase.HOPEFUL, EmotionPhase.DESPAIR): ["希望落空", "遭遇挫折", "计划失败"],
            
            (EmotionPhase.DESPAIR, EmotionPhase.DETERMINED): ["绝地反击", "找到转机", "重燃希望"],
            (EmotionPhase.DESPAIR, EmotionPhase.CALM): ["接受现实", "放下执念", "平静面对"],
            
            (EmotionPhase.DETERMINED, EmotionPhase.EXCITED): ["开始行动", "进展顺利", "信心增强"],
            (EmotionPhase.DETERMINED, EmotionPhase.TENSE): ["遇到阻碍", "压力增大", "风险出现"],
            
            (EmotionPhase.EXCITED, EmotionPhase.CALM): ["事情结束", "回归日常", "情绪平复"],
            (EmotionPhase.EXCITED, EmotionPhase.TENSE): ["新的挑战", "意外变故", "情况复杂"],
            
            (EmotionPhase.MELANCHOLY, EmotionPhase.CALM): ["时间流逝", "情绪淡化", "接受现实"],
            (EmotionPhase.MELANCHOLY, EmotionPhase.WARM): ["新的温暖", "回忆美好", "得到安慰"],
            
            (EmotionPhase.CONFUSED, EmotionPhase.DETERMINED): ["理清思路", "做出决定", "获得指引"],
            (EmotionPhase.CONFUSED, EmotionPhase.TENSE): ["情况恶化", "压力增大", "时间紧迫"],
        }
    
    def create_conflict(self, level: ConflictLevel, participants: List[str],
                       custom_name: str = None, custom_desc: str = None) -> ConflictNode:
        """创建新矛盾"""
        templates = self._conflict_templates.get(level, [])
        if not templates:
            template = {"name": "未知矛盾", "desc": "", "resolution": ["解决"]}
        else:
            template = random.choice(templates)
        
        name = custom_name or template["name"]
        desc = custom_desc or template["desc"]
        
        conflict = ConflictNode(
            name=name,
            level=level,
            description=desc,
            participants=participants,
            possible_resolutions=template.get("resolution", ["解决"])
        )
        
        self._active_conflicts.append(conflict)
        return conflict
    
    def escalate_conflict(self, conflict: ConflictNode) -> Optional[ConflictNode]:
        """升级矛盾"""
        level_order = [ConflictLevel.TRIVIAL, ConflictLevel.MINOR, ConflictLevel.MODERATE,
                      ConflictLevel.MAJOR, ConflictLevel.CRITICAL]
        
        current_idx = level_order.index(conflict.level)
        if current_idx >= len(level_order) - 1:
            return None  # 已经是最高级别
        
        new_level = level_order[current_idx + 1]
        
        # 创建升级后的矛盾
        escalated = self.create_conflict(
            new_level,
            conflict.participants,
            f"升级：{conflict.name}",
            f"矛盾升级 - {conflict.description}"
        )
        
        # 标记原矛盾为已解决
        conflict.is_resolved = True
        self._resolved_conflicts.append(conflict)
        if conflict in self._active_conflicts:
            self._active_conflicts.remove(conflict)
        
        return escalated
    
    def resolve_conflict(self, conflict: ConflictNode, resolution: str = None) -> str:
        """解决矛盾"""
        if not resolution and conflict.possible_resolutions:
            resolution = random.choice(conflict.possible_resolutions)
        
        conflict.is_resolved = True
        self._resolved_conflicts.append(conflict)
        if conflict in self._active_conflicts:
            self._active_conflicts.remove(conflict)
        
        return resolution or "以某种方式解决了"
    
    def get_emotional_turn(self, target_phase: EmotionPhase = None,
                          trigger: str = None) -> Optional[EmotionalTurn]:
        """获取情感转折"""
        current = self._current_emotion
        
        if target_phase:
            # 指定目标情感
            rules = self._emotion_transition_rules.get((current, target_phase), [])
            if not rules:
                # 直接转换
                trigger = trigger or "情况发生变化"
            else:
                trigger = trigger or random.choice(rules)
        else:
            # 随机选择可能的转换
            possible_transitions = [(k, v) for k, v in self._emotion_transition_rules.items()
                                   if k[0] == current]
            
            if not possible_transitions:
                return None
            
            (from_to, triggers) = random.choice(possible_transitions)
            target_phase = from_to[1]
            trigger = trigger or random.choice(triggers)
        
        # 创建转折
        turn = EmotionalTurn(
            from_phase=current,
            to_phase=target_phase,
            trigger=trigger,
            description=f"因「{trigger}」而从{current.value}转为{target_phase.value}"
        )
        
        # 更新当前情感
        self._current_emotion = target_phase
        self._emotion_history.append(target_phase)
        
        return turn
    
    def should_escalate(self) -> bool:
        """判断是否应该升级矛盾"""
        # 根据剧情进度和当前矛盾情况判断
        if not self._active_conflicts:
            return False
        
        # 如果同一情感持续太久，可能需要升级
        recent_emotions = self._emotion_history[-self._max_same_emotion:]
        if len(recent_emotions) == self._max_same_emotion and len(set(recent_emotions)) == 1:
            return random.random() < 0.5  # 50%概率升级
        
        # 根据剧情进度
        if self._plot_progress > 0 and self._plot_progress % 5 == 0:
            return random.random() < 0.3
        
        return False
    
    def create_branch(self, branch_id: str, branch_type: PlotBranchType,
                     name: str, description: str) -> PlotBranch:
        """创建剧情分支"""
        branch = PlotBranch(
            branch_id=branch_id,
            branch_type=branch_type,
            name=name,
            description=description,
            current_node="start"
        )
        
        self._branches[branch_id] = branch
        return branch
    
    def advance_branch(self, branch_id: str, node: str) -> bool:
        """推进剧情分支"""
        branch = self._branches.get(branch_id)
        if not branch or not branch.is_active:
            return False
        
        branch.nodes.append(branch.current_node)
        branch.current_node = node
        self._plot_progress += 1
        
        return True
    
    def get_active_branches(self) -> List[PlotBranch]:
        """获取所有活跃的剧情分支"""
        return [b for b in self._branches.values() if b.is_active]
    
    def get_current_conflicts(self) -> List[ConflictNode]:
        """获取当前活跃的矛盾"""
        return self._active_conflicts.copy()
    
    def get_current_emotion(self) -> EmotionPhase:
        """获取当前情感状态"""
        return self._current_emotion
    
    def get_emotion_description(self) -> str:
        """获取情感状态描述"""
        return self._current_emotion.value
    
    def generate_plot_description(self) -> str:
        """生成剧情状态描述"""
        parts = []
        
        # 情感状态
        parts.append(f"当前心情{self._current_emotion.value}")
        
        # 活跃矛盾
        if self._active_conflicts:
            conflict = self._active_conflicts[-1]
            parts.append(f"面临{conflict.level.value}矛盾：{conflict.name}")
        
        # 剧情进度
        if self._plot_progress > 0:
            progress_desc = "故事正在展开"
            if self._plot_progress > 10:
                progress_desc = "剧情进入高潮"
            if self._plot_progress > 20:
                progress_desc = "故事接近尾声"
            parts.append(progress_desc)
        
        return "。".join(parts) + "。"
    
    def increment_progress(self):
        """增加剧情进度"""
        self._plot_progress += 1
    
    def get_progress(self) -> int:
        """获取剧情进度"""
        return self._plot_progress
    
    def reset(self):
        """重置剧情状态"""
        self._active_conflicts.clear()
        self._resolved_conflicts.clear()
        self._current_emotion = EmotionPhase.CALM
        self._emotion_history = [EmotionPhase.CALM]
        self._plot_progress = 0
        for branch in self._branches.values():
            branch.is_active = False
        self._branches.clear()


# 单例模式
_plot_brancher_instance = None

def get_plot_brancher() -> PlotBrancher:
    """获取剧情分支器单例"""
    global _plot_brancher_instance
    if _plot_brancher_instance is None:
        _plot_brancher_instance = PlotBrancher()
    return _plot_brancher_instance
