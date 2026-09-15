# -*- coding: utf-8 -*-
"""
角色对话系统 - 处理角色间的对话、交易、结盟等互动

优化内容：
1. 多种触发条件 - 距离、目标相关性、事件、场景
2. 角色意愿判断 - 忙碌/敌对状态拒绝对话
3. 对话冷却时间 - 避免短时间内重复触发
"""
import random
import time
from typing import List, Dict, Optional, Tuple, Set, Any, Callable
from dataclasses import dataclass, field
from enum import Enum
from collections import defaultdict

logger = __import__('logging').getLogger(__name__)


# ============================================================
# 对话类型
# ============================================================
class DialogueType(Enum):
    """对话类型"""
    CHAT = "闲聊"
    TRADE = "交易"
    ALLIANCE = "结盟"
    CONFLICT = "冲突"
    SECRET = "密谈"
    NEGOTIATION = "谈判"
    GOSSIP = "八卦"       # 新增：八卦/传播消息
    QUEST = "任务"        # 新增：任务相关对话
    ROMANCE = "浪漫"      # 新增：浪漫对话


# ============================================================
# 触发条件类型
# ============================================================
class TriggerType(Enum):
    """触发条件类型"""
    DISTANCE = "distance"           # 距离触发
    GOAL_RELATED = "goal_related"   # 目标相关
    EVENT = "event"                 # 事件触发
    SCENE = "scene"                 # 场景触发
    RANDOM = "random"               # 随机触发
    FORCED = "forced"               # 强制触发


# ============================================================
# 角色状态
# ============================================================
class CharacterStatus(Enum):
    """角色状态"""
    IDLE = "idle"           # 空闲
    BUSY = "busy"           # 忙碌
    IN_COMBAT = "combat"    # 战斗中
    RESTING = "resting"     # 休息中
    TRAVELING = "traveling" # 旅行中
    HOSTILE = "hostile"     # 敌对状态


# ============================================================
# 触发条件配置
# ============================================================
@dataclass
class TriggerConfig:
    """触发条件配置"""
    # 距离触发
    max_distance: int = 2              # 最大触发距离
    distance_weight: float = 0.3      # 距离条件权重
    
    # 随机触发
    base_probability: float = 0.15    # 基础触发概率
    
    # 目标相关性
    goal_relevance_weight: float = 0.25   # 目标相关性权重
    goal_relevance_threshold: float = 0.5  # 目标相关性阈值
    
    # 事件触发
    event_trigger_weight: float = 0.2     # 事件触发权重
    
    # 场景触发
    scene_trigger_weight: float = 0.15    # 场景触发权重
    
    # 冷却时间
    cooldown_seconds: float = 60.0        # 对话冷却时间（秒）
    cooldown_ticks: int = 10              # 对话冷却时间（tick）
    
    # 状态限制
    blocked_statuses: Set[CharacterStatus] = field(default_factory=lambda: {
        CharacterStatus.IN_COMBAT,
        CharacterStatus.HOSTILE,
    })
    
    # 关系限制
    min_relationship_for_dialogue: float = 0.1  # 最低关系值才能对话


# ============================================================
# 对话
# ============================================================
@dataclass
class Dialogue:
    """一次对话"""
    speaker1: str
    speaker2: str
    dialogue_type: DialogueType
    content: str
    outcome: str = ""
    tick: int = 0
    trigger_type: TriggerType = TriggerType.RANDOM
    timestamp: float = field(default_factory=time.time)


# ============================================================
# 对话触发条件检查器
# ============================================================
class DialogueTriggerChecker:
    """对话触发条件检查器"""
    
    def __init__(self, config: Optional[TriggerConfig] = None):
        self.config = config or TriggerConfig()
        
        # 冷却记录: (角色1, 角色2) -> 上次对话时间
        self._cooldowns: Dict[Tuple[str, str], float] = {}
        self._cooldown_ticks: Dict[Tuple[str, str], int] = {}
        
        # 事件触发器
        self._event_triggers: Dict[str, Callable] = {}
        
        # 场景触发器
        self._scene_triggers: Dict[str, Callable] = {}
    
    def check_cooldown(self, char1_name: str, char2_name: str, current_tick: int = 0) -> bool:
        """
        检查对话冷却
        
        Args:
            char1_name: 角色1名称
            char2_name: 角色2名称
            current_tick: 当前tick
        
        Returns:
            是否在冷却中（True表示还在冷却，不能对话）
        """
        key = tuple(sorted([char1_name, char2_name]))
        
        # 检查时间冷却
        if key in self._cooldowns:
            if time.time() - self._cooldowns[key] < self.config.cooldown_seconds:
                return True
        
        # 检查tick冷却
        if key in self._cooldown_ticks:
            if current_tick - self._cooldown_ticks[key] < self.config.cooldown_ticks:
                return True
        
        return False
    
    def set_cooldown(self, char1_name: str, char2_name: str, current_tick: int = 0):
        """设置对话冷却"""
        key = tuple(sorted([char1_name, char2_name]))
        self._cooldowns[key] = time.time()
        self._cooldown_ticks[key] = current_tick
    
    def check_status(self, status: CharacterStatus) -> bool:
        """
        检查角色状态是否允许对话
        
        Returns:
            是否允许对话
        """
        return status not in self.config.blocked_statuses
    
    def check_distance(self, pos1: Tuple[int, int], pos2: Tuple[int, int]) -> Tuple[bool, float]:
        """
        检查距离条件
        
        Returns:
            (是否满足, 距离分数)
        """
        dist = abs(pos1[0] - pos2[0]) + abs(pos1[1] - pos2[1])
        
        if dist > self.config.max_distance:
            return False, 0.0
        
        # 距离分数：越近分数越高
        score = 1.0 - (dist / (self.config.max_distance + 1))
        return True, score
    
    def check_goal_relevance(
        self,
        char1_goals: List[str],
        char2_goals: List[str]
    ) -> Tuple[bool, float]:
        """
        检查目标相关性
        
        Args:
            char1_goals: 角色1的目标列表
            char2_goals: 角色2的目标列表
        
        Returns:
            (是否相关, 相关性分数)
        """
        if not char1_goals or not char2_goals:
            return False, 0.0
        
        # 计算目标重叠
        set1 = set(g.lower() for g in char1_goals)
        set2 = set(g.lower() for g in char2_goals)
        
        intersection = set1 & set2
        union = set1 | set2
        
        if not union:
            return False, 0.0
        
        # Jaccard 相似度
        similarity = len(intersection) / len(union)
        
        return similarity >= self.config.goal_relevance_threshold, similarity
    
    def check_event_trigger(
        self,
        event_type: str,
        char1: Any,
        char2: Any
    ) -> Tuple[bool, float]:
        """
        检查事件触发
        
        Args:
            event_type: 事件类型
            char1: 角色1
            char2: 角色2
        
        Returns:
            (是否触发, 触发分数)
        """
        if event_type not in self._event_triggers:
            return False, 0.0
        
        try:
            triggered, score = self._event_triggers[event_type](char1, char2)
            return triggered, score
        except Exception as e:
            logger.error(f"Event trigger error: {e}")
            return False, 0.0
    
    def check_scene_trigger(
        self,
        scene_type: str,
        char1: Any,
        char2: Any
    ) -> Tuple[bool, float]:
        """
        检查场景触发
        
        Args:
            scene_type: 场景类型
            char1: 角色1
            char2: 角色2
        
        Returns:
            (是否触发, 触发分数)
        """
        if scene_type not in self._scene_triggers:
            return False, 0.0
        
        try:
            triggered, score = self._scene_triggers[scene_type](char1, char2)
            return triggered, score
        except Exception as e:
            logger.error(f"Scene trigger error: {e}")
            return False, 0.0
    
    def register_event_trigger(self, event_type: str, trigger_func: Callable):
        """注册事件触发器"""
        self._event_triggers[event_type] = trigger_func
    
    def register_scene_trigger(self, scene_type: str, trigger_func: Callable):
        """注册场景触发器"""
        self._scene_triggers[scene_type] = trigger_func
    
    def calculate_trigger_probability(
        self,
        distance_score: float = 0.0,
        goal_score: float = 0.0,
        event_score: float = 0.0,
        scene_score: float = 0.0
    ) -> float:
        """
        计算综合触发概率
        
        Returns:
            触发概率 (0-1)
        """
        base = self.config.base_probability
        
        # 加权计算
        weighted_score = (
            distance_score * self.config.distance_weight +
            goal_score * self.config.goal_relevance_weight +
            event_score * self.config.event_trigger_weight +
            scene_score * self.config.scene_trigger_weight
        )
        
        # 综合概率 = 基础概率 + 加权分数
        probability = base + weighted_score * (1.0 - base)
        
        return min(1.0, max(0.0, probability))


# ============================================================
# 对话系统（优化版）
# ============================================================
class DialogueSystem:
    """角色对话系统 - 增强触发条件"""
    
    def __init__(self, ai_client=None, trigger_config: Optional[TriggerConfig] = None):
        self.ai = ai_client
        self.dialogue_history: List[Dialogue] = []
        self.max_history = 50
        
        # 触发检查器
        self.trigger_checker = DialogueTriggerChecker(trigger_config)
        
        # 关系阈值
        self.alliance_threshold = 0.7
        self.conflict_threshold = 0.3
        self.romance_threshold = 0.8
        
        # 统计
        self._stats = {
            "total_dialogues": 0,
            "by_type": defaultdict(int),
            "by_trigger": defaultdict(int),
            "blocked_by_cooldown": 0,
            "blocked_by_status": 0,
        }
    
    def should_trigger_dialogue(
        self,
        char1,
        char2,
        tick: int = 0,
        event_type: Optional[str] = None,
        scene_type: Optional[str] = None,
        force: bool = False
    ) -> Tuple[bool, TriggerType, float]:
        """
        判断是否应该触发对话
        
        Args:
            char1: 角色1
            char2: 角色2
            tick: 当前tick
            event_type: 可选的事件类型
            scene_type: 可选的场景类型
            force: 是否强制触发
        
        Returns:
            (是否触发, 触发类型, 触发概率)
        """
        # 强制触发
        if force:
            return True, TriggerType.FORCED, 1.0
        
        # 检查角色存活
        if not getattr(char1, 'alive', True) or not getattr(char2, 'alive', True):
            return False, TriggerType.RANDOM, 0.0
        
        # 检查冷却
        if self.trigger_checker.check_cooldown(char1.name, char2.name, tick):
            self._stats["blocked_by_cooldown"] += 1
            return False, TriggerType.RANDOM, 0.0
        
        # 检查角色状态
        status1 = getattr(char1, 'status', CharacterStatus.IDLE)
        status2 = getattr(char2, 'status', CharacterStatus.IDLE)
        
        if not self.trigger_checker.check_status(status1) or not self.trigger_checker.check_status(status2):
            self._stats["blocked_by_status"] += 1
            return False, TriggerType.RANDOM, 0.0
        
        # 检查关系值
        rel1 = char1.relationships.get(char2.name, 0.5) if hasattr(char1, 'relationships') else 0.5
        rel2 = char2.relationships.get(char1.name, 0.5) if hasattr(char2, 'relationships') else 0.5
        
        config = self.trigger_checker.config
        if rel1 < config.min_relationship_for_dialogue or rel2 < config.min_relationship_for_dialogue:
            return False, TriggerType.RANDOM, 0.0
        
        # 计算各项触发分数
        distance_ok, distance_score = self.trigger_checker.check_distance(
            getattr(char1, 'pos', (0, 0)),
            getattr(char2, 'pos', (0, 0))
        )
        
        if not distance_ok:
            return False, TriggerType.RANDOM, 0.0
        
        # 目标相关性
        char1_goals = getattr(char1, 'goals', [])
        char2_goals = getattr(char2, 'goals', [])
        goal_ok, goal_score = self.trigger_checker.check_goal_relevance(char1_goals, char2_goals)
        
        # 事件触发
        event_score = 0.0
        if event_type:
            _, event_score = self.trigger_checker.check_event_trigger(event_type, char1, char2)
        
        # 场景触发
        scene_score = 0.0
        if scene_type:
            _, scene_score = self.trigger_checker.check_scene_trigger(scene_type, char1, char2)
        
        # 计算综合概率
        probability = self.trigger_checker.calculate_trigger_probability(
            distance_score, goal_score, event_score, scene_score
        )
        
        # 判断触发
        if random.random() < probability:
            # 确定触发类型
            if event_score > 0.5:
                trigger_type = TriggerType.EVENT
            elif scene_score > 0.5:
                trigger_type = TriggerType.SCENE
            elif goal_ok:
                trigger_type = TriggerType.GOAL_RELATED
            else:
                trigger_type = TriggerType.RANDOM
            
            return True, trigger_type, probability
        
        return False, TriggerType.RANDOM, probability
    
    def determine_dialogue_type(self, char1, char2, trigger_type: TriggerType = TriggerType.RANDOM) -> DialogueType:
        """根据角色关系和触发类型确定对话类型"""
        # 获取关系值
        rel1 = char1.relationships.get(char2.name, 0.5) if hasattr(char1, 'relationships') else 0.5
        rel2 = char2.relationships.get(char1.name, 0.5) if hasattr(char2, 'relationships') else 0.5
        avg_rel = (rel1 + rel2) / 2
        
        # 根据触发类型调整
        if trigger_type == TriggerType.EVENT:
            # 事件触发更可能是任务或谈判
            return random.choice([DialogueType.QUEST, DialogueType.NEGOTIATION, DialogueType.CHAT])
        
        if trigger_type == TriggerType.GOAL_RELATED:
            # 目标相关更可能是任务或结盟
            return random.choice([DialogueType.QUEST, DialogueType.ALLIANCE, DialogueType.NEGOTIATION])
        
        # 根据关系值确定类型
        if avg_rel >= self.romance_threshold:
            return random.choice([DialogueType.ROMANCE, DialogueType.SECRET, DialogueType.CHAT])
        elif avg_rel >= self.alliance_threshold:
            return random.choice([DialogueType.ALLIANCE, DialogueType.CHAT, DialogueType.SECRET])
        elif avg_rel <= self.conflict_threshold:
            return random.choice([DialogueType.CONFLICT, DialogueType.NEGOTIATION])
        else:
            return random.choice([DialogueType.CHAT, DialogueType.TRADE, DialogueType.GOSSIP])
    
    def generate_dialogue(
        self,
        char1,
        char2,
        dialogue_type: DialogueType,
        world_context: str = "",
        tick: int = 0,
        trigger_type: TriggerType = TriggerType.RANDOM
    ) -> Dialogue:
        """生成一次对话"""
        
        # 构建对话提示
        type_prompts = {
            DialogueType.CHAT: "闲聊几句",
            DialogueType.TRADE: "讨论物品交换",
            DialogueType.ALLIANCE: "商讨结盟事宜",
            DialogueType.CONFLICT: "发生争执",
            DialogueType.SECRET: "秘密交谈",
            DialogueType.NEGOTIATION: "进行谈判",
            DialogueType.GOSSIP: "交换八卦消息",
            DialogueType.QUEST: "讨论任务相关事宜",
            DialogueType.ROMANCE: "浪漫的对话",
        }

        # 获取角色状态
        char1_mood = getattr(char1, 'mood', '平静')
        char2_mood = getattr(char2, 'mood', '平静')

        from novel_world.engine.core.prompt_registry import PromptRegistry
        prompt = PromptRegistry.get(
            "dialogue_generation",
            char_a_name=char1.name,
            char_a_personality=getattr(char1, 'personality', '普通'),
            char_a_mood=char1_mood,
            char_b_name=char2.name,
            char_b_personality=getattr(char2, 'personality', '普通'),
            char_b_mood=char2_mood,
            dialogue_type=dialogue_type.value,
            dialogue_type_desc=type_prompts.get(dialogue_type, '交谈'),
            world_context=world_context[:100] if world_context else "无",
        )

        # 尝试用AI生成
        content = ""
        if self.ai and hasattr(self.ai, 'is_available') and self.ai.is_available:
            try:
                content = self.ai.generate(prompt, max_tokens=100)
                if content:
                    content = content.strip()
            except Exception as e:
                logger.error(f"AI generation failed: {e}")
                content = self._fallback_dialogue(char1, char2, dialogue_type)
        else:
            content = self._fallback_dialogue(char1, char2, dialogue_type)
        
        # 确定结果
        outcome = self._determine_outcome(dialogue_type, char1, char2)
        
        # 创建对话记录
        dialogue = Dialogue(
            speaker1=char1.name,
            speaker2=char2.name,
            dialogue_type=dialogue_type,
            content=content,
            outcome=outcome,
            tick=tick,
            trigger_type=trigger_type,
        )
        
        # 设置冷却
        self.trigger_checker.set_cooldown(char1.name, char2.name, tick)
        
        # 记录历史
        self.dialogue_history.append(dialogue)
        if len(self.dialogue_history) > self.max_history:
            self.dialogue_history = self.dialogue_history[-self.max_history:]
        
        # 更新统计
        self._stats["total_dialogues"] += 1
        self._stats["by_type"][dialogue_type.value] += 1
        self._stats["by_trigger"][trigger_type.value] += 1
        
        return dialogue
    
    def _fallback_dialogue(self, char1, char2, dialogue_type: DialogueType) -> str:
        """Fallback：模板生成对话"""
        templates = {
            DialogueType.CHAT: [
                f'{char1.name}向{char2.name}打招呼，两人闲聊了几句。',
                f'{char1.name}和{char2.name}交换了最近的见闻。',
            ],
            DialogueType.TRADE: [
                f'{char1.name}提出想要交换物品，{char2.name}考虑了一下。',
                f'{char1.name}和{char2.name}讨论了物品的价值。',
            ],
            DialogueType.ALLIANCE: [
                f'{char1.name}提议结盟，{char2.name}表示同意。',
                f'{char1.name}和{char2.name}达成了合作协议。',
            ],
            DialogueType.CONFLICT: [
                f'{char1.name}和{char2.name}发生了争执。',
                f'{char1.name}对{char2.name}表示不满。',
            ],
            DialogueType.SECRET: [
                f'{char1.name}悄悄对{char2.name}说了些什么。',
                f'{char1.name}和{char2.name}在角落里低声交谈。',
            ],
            DialogueType.NEGOTIATION: [
                f'{char1.name}提出条件，{char2.name}开始谈判。',
                f'{char1.name}和{char2.name}就某事进行协商。',
            ],
            DialogueType.GOSSIP: [
                f'{char1.name}和{char2.name}交换了最近的消息。',
                f'{char1.name}告诉{char2.name}一个有趣的传闻。',
            ],
            DialogueType.QUEST: [
                f'{char1.name}和{char2.name}讨论了任务细节。',
                f'{char1.name}向{char2.name}询问任务相关信息。',
            ],
            DialogueType.ROMANCE: [
                f'{char1.name}温柔地看着{char2.name}。',
                f'{char1.name}对{char2.name}说了些甜蜜的话。',
            ],
        }
        return random.choice(templates.get(dialogue_type, templates[DialogueType.CHAT]))
    
    def _determine_outcome(self, dialogue_type: DialogueType, char1, char2) -> str:
        """确定对话结果"""
        outcomes = {
            DialogueType.CHAT: "增进了了解",
            DialogueType.TRADE: "交换了物品" if random.random() > 0.3 else "交易未达成",
            DialogueType.ALLIANCE: "结盟成功" if random.random() > 0.2 else "需要更多信任",
            DialogueType.CONFLICT: "关系恶化" if random.random() > 0.4 else "暂时搁置争议",
            DialogueType.SECRET: "达成了秘密协议" if random.random() > 0.3 else "只是交换了信息",
            DialogueType.NEGOTIATION: "达成共识" if random.random() > 0.3 else "谈判破裂",
            DialogueType.GOSSIP: "交换了消息",
            DialogueType.QUEST: "获得任务信息" if random.random() > 0.4 else "没有有用信息",
            DialogueType.ROMANCE: "感情升温" if random.random() > 0.3 else "气氛有些尴尬",
        }
        return outcomes.get(dialogue_type, "无特殊结果")
    
    def apply_dialogue_effects(self, dialogue: Dialogue, char1, char2):
        """应用对话效果到角色"""
        # 更新关系值
        if not hasattr(char1, 'relationships'):
            char1.relationships = {}
        if not hasattr(char2, 'relationships'):
            char2.relationships = {}
        
        # 根据对话类型调整关系
        rel_change = {
            DialogueType.CHAT: 0.05,
            DialogueType.TRADE: 0.03,
            DialogueType.ALLIANCE: 0.15,
            DialogueType.CONFLICT: -0.1,
            DialogueType.SECRET: 0.08,
            DialogueType.NEGOTIATION: 0.05,
            DialogueType.GOSSIP: 0.02,
            DialogueType.QUEST: 0.05,
            DialogueType.ROMANCE: 0.1,
        }
        
        change = rel_change.get(dialogue.dialogue_type, 0)
        
        # 更新关系
        current_rel1 = char1.relationships.get(char2.name, 0.5)
        current_rel2 = char2.relationships.get(char1.name, 0.5)
        
        char1.relationships[char2.name] = max(0, min(1, current_rel1 + change))
        char2.relationships[char1.name] = max(0, min(1, current_rel2 + change))
        
        # 记录到记忆
        if hasattr(char1, 'key_memories'):
            char1.key_memories.append(f"与{char2.name}{dialogue.dialogue_type.value}")
            if len(char1.key_memories) > 20:
                char1.key_memories = char1.key_memories[-20:]
        
        if hasattr(char2, 'key_memories'):
            char2.key_memories.append(f"与{char1.name}{dialogue.dialogue_type.value}")
            if len(char2.key_memories) > 20:
                char2.key_memories = char2.key_memories[-20:]
    
    def get_recent_dialogues(self, char_name: str = None, count: int = 5) -> List[Dialogue]:
        """获取最近的对话"""
        if char_name:
            dialogues = [d for d in self.dialogue_history 
                        if d.speaker1 == char_name or d.speaker2 == char_name]
            return dialogues[-count:]
        return self.dialogue_history[-count:]
    
    def get_dialogue_summary(self) -> str:
        """获取对话摘要"""
        if not self.dialogue_history:
            return ""
        
        recent = self.dialogue_history[-5:]
        lines = []
        for d in recent:
            lines.append(f"【{d.tick}】{d.speaker1}与{d.speaker2}{d.dialogue_type.value}，{d.outcome}")
        return "\n".join(lines)
    
    def get_stats(self) -> Dict:
        """获取统计"""
        return {
            "total_dialogues": self._stats["total_dialogues"],
            "by_type": dict(self._stats["by_type"]),
            "by_trigger": dict(self._stats["by_trigger"]),
            "blocked_by_cooldown": self._stats["blocked_by_cooldown"],
            "blocked_by_status": self._stats["blocked_by_status"],
        }
    
    def clear_cooldowns(self):
        """清除所有冷却"""
        self.trigger_checker._cooldowns.clear()
        self.trigger_checker._cooldown_ticks.clear()


# ============================================================
# 全局实例
# ============================================================
_dialogue_system: Optional[DialogueSystem] = None


def get_dialogue_system(ai_client=None, trigger_config: Optional[TriggerConfig] = None) -> DialogueSystem:
    """获取对话系统实例"""
    global _dialogue_system
    if _dialogue_system is None:
        _dialogue_system = DialogueSystem(ai_client, trigger_config)
    return _dialogue_system
