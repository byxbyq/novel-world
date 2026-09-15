# -*- coding: utf-8 -*-
"""
动作扩展系统 - 解决人物动作重复问题
提供角色动作模块的扩展接口，支持：
- 动作库管理（基础动作、特殊动作、组合动作）
- 动态动作组合（根据情境生成新动作）
- 角色差异化动作（不同角色有不同动作风格）
- 动作去重和轮换
"""
from typing import Dict, List, Optional, Tuple, Set
from dataclasses import dataclass, field
from enum import Enum
import random
from collections import defaultdict


class ActionType(Enum):
    """动作类型"""
    MOVEMENT = "移动"      # 移动类：走、跑、跳、爬等
    INTERACTION = "交互"   # 交互类：说话、交易、战斗等
    OBSERVATION = "观察"   # 观察类：看、听、闻等
    EMOTION = "情感"       # 情感类：笑、哭、叹气等
    COMBAT = "战斗"        # 战斗类：攻击、防御、闪避等
    REST = "休息"          # 休息类：坐、躺、睡等
    SKILL = "技能"         # 技能类：施法、修炼、制作等


class CharacterRole(Enum):
    """角色定位"""
    PROTAGONIST = "主角"
    ANTAGONIST = "反派"
    MENTOR = "导师"
    COMPANION = "同伴"
    NPC = "路人"
    MERCHANT = "商人"
    WARRIOR = "武者"
    SCHOLAR = "书生"


@dataclass
class ActionDefinition:
    """动作定义"""
    name: str                    # 动作名称
    action_type: ActionType      # 动作类型
    description: str             # 动作描述模板
    variations: List[str] = field(default_factory=list)  # 变体描述
    requires_target: bool = False  # 是否需要目标
    emotion_tone: str = "neutral"  # 情感基调
    intensity: int = 1           # 强度 1-5


@dataclass
class ActionCombination:
    """动作组合"""
    name: str
    actions: List[str]           # 组合的动作列表
    description_template: str    # 组合描述模板
    applicable_roles: List[CharacterRole] = field(default_factory=list)
    applicable_contexts: List[str] = field(default_factory=list)  # 适用情境


class ActionExpander:
    """动作扩展系统"""
    
    def __init__(self):
        self._action_library: Dict[str, ActionDefinition] = {}
        self._combinations: List[ActionCombination] = []
        self._role_actions: Dict[CharacterRole, List[str]] = defaultdict(list)
        self._used_actions: Dict[str, int] = defaultdict(int)  # 角色已用动作计数
        self._action_history: Dict[str, List[str]] = defaultdict(list)  # 角色动作历史
        self._max_history = 20
        self._max_same_action = 2  # 同一动作最大连续使用次数
        
        self._initialize_action_library()
        self._initialize_combinations()
        self._initialize_role_actions()
    
    def _initialize_action_library(self):
        """初始化动作库"""
        
        # 移动类动作
        movement_actions = [
            ActionDefinition("缓步前行", ActionType.MOVEMENT, "缓步向前走去", 
                           ["慢慢踱步向前", "迈着沉稳的步伐前行"], emotion_tone="calm"),
            ActionDefinition("快步疾行", ActionType.MOVEMENT, "加快脚步向前", 
                           ["急匆匆地赶路", "步伐加快"], emotion_tone="urgent", intensity=2),
            ActionDefinition("转身回望", ActionType.MOVEMENT, "转身向后望去", 
                           ["回过身来", "转过身去"], emotion_tone="hesitant"),
            ActionDefinition("驻足停步", ActionType.MOVEMENT, "停下脚步", 
                           ["脚步一顿", "停了下来"], emotion_tone="alert"),
            ActionDefinition("悄然退后", ActionType.MOVEMENT, "悄悄后退几步", 
                           ["不动声色地后退", "悄然拉开距离"], emotion_tone="cautious"),
            ActionDefinition("跃步向前", ActionType.MOVEMENT, "纵身跃向前方", 
                           ["一跃而起", "飞身扑去"], emotion_tone="bold", intensity=3),
            ActionDefinition("踉跄前行", ActionType.MOVEMENT, "踉踉跄跄地走着", 
                           ["脚步不稳地前行", "摇摇晃晃地走"], emotion_tone="weak", intensity=2),
            ActionDefinition("稳步后退", ActionType.MOVEMENT, "稳步向后退去", 
                           ["一步步后退", "缓缓后退"], emotion_tone="cautious"),
        ]
        
        # 交互类动作
        interaction_actions = [
            ActionDefinition("开口询问", ActionType.INTERACTION, "开口问道", 
                           ["出声询问", "张口问"], requires_target=True, emotion_tone="curious"),
            ActionDefinition("低声回应", ActionType.INTERACTION, "低声回应道", 
                           ["轻声回答", "小声说道"], requires_target=True, emotion_tone="quiet"),
            ActionDefinition("拱手行礼", ActionType.INTERACTION, "拱手行了一礼", 
                           ["抱拳施礼", "拱手作揖"], emotion_tone="respectful"),
            ActionDefinition("点头示意", ActionType.INTERACTION, "微微点头示意", 
                           ["轻轻点头", "颔首致意"], emotion_tone="friendly"),
            ActionDefinition("摇头叹息", ActionType.INTERACTION, "摇头叹了口气", 
                           ["摇了摇头", "叹息着摇头"], emotion_tone="sad"),
            ActionDefinition("抱拳告辞", ActionType.INTERACTION, "抱拳告辞", 
                           ["拱手告别", "行礼离去"], emotion_tone="formal"),
            ActionDefinition("伸手相邀", ActionType.INTERACTION, "伸手示意邀请", 
                           ["做出请的手势", "伸手相请"], requires_target=True, emotion_tone="friendly"),
            ActionDefinition("拱手相谢", ActionType.INTERACTION, "拱手道谢", 
                           ["抱拳感谢", "施礼致谢"], emotion_tone="grateful"),
        ]
        
        # 观察类动作
        observation_actions = [
            ActionDefinition("环顾四周", ActionType.OBSERVATION, "环顾四周", 
                           ["打量着周围", "四处张望"], emotion_tone="alert"),
            ActionDefinition("凝神细看", ActionType.OBSERVATION, "凝神细看", 
                           ["仔细观察", "定睛看去"], emotion_tone="focused"),
            ActionDefinition("侧耳倾听", ActionType.OBSERVATION, "侧耳倾听", 
                           ["竖起耳朵听", "凝神细听"], emotion_tone="alert"),
            ActionDefinition("抬头仰望", ActionType.OBSERVATION, "抬头仰望", 
                           ["仰头看去", "举目远眺"], emotion_tone="wonder"),
            ActionDefinition("低头沉思", ActionType.OBSERVATION, "低头沉思", 
                           ["垂首思考", "低下头去"], emotion_tone="contemplative"),
            ActionDefinition("闭目感知", ActionType.OBSERVATION, "闭上眼睛感知", 
                           ["闭目凝神", "阖目感应"], emotion_tone="focused", intensity=2),
            ActionDefinition("目光扫过", ActionType.OBSERVATION, "目光扫过", 
                           ["视线掠过", "眼神扫向"], emotion_tone="sharp"),
            ActionDefinition("凝视前方", ActionType.OBSERVATION, "凝视前方", 
                           ["目光定定地看着前方", "眼神坚定"], emotion_tone="determined"),
        ]
        
        # 情感类动作
        emotion_actions = [
            ActionDefinition("微微一笑", ActionType.EMOTION, "嘴角微微上扬", 
                           ["露出一丝微笑", "淡淡一笑"], emotion_tone="happy"),
            ActionDefinition("苦笑摇头", ActionType.EMOTION, "苦笑着摇了摇头", 
                           ["无奈地笑了笑", "露出苦涩的笑容"], emotion_tone="sad"),
            ActionDefinition("眉头紧锁", ActionType.EMOTION, "眉头紧锁", 
                           ["眉头皱起", "双眉紧蹙"], emotion_tone="worried"),
            ActionDefinition("神色凝重", ActionType.EMOTION, "神色变得凝重", 
                           ["面色一肃", "表情严肃起来"], emotion_tone="serious"),
            ActionDefinition("眼中闪过精光", ActionType.EMOTION, "眼中闪过一丝精光", 
                           ["目光一凛", "眼神变得锐利"], emotion_tone="sharp", intensity=2),
            ActionDefinition("面露喜色", ActionType.EMOTION, "脸上露出喜色", 
                           ["喜上眉梢", "神色一喜"], emotion_tone="happy"),
            ActionDefinition("神色黯然", ActionType.EMOTION, "神色黯然", 
                           ["面露黯然之色", "表情变得落寞"], emotion_tone="sad"),
            ActionDefinition("强作镇定", ActionType.EMOTION, "强作镇定", 
                           ["努力保持镇定", "勉强镇定下来"], emotion_tone="tense"),
        ]
        
        # 战斗类动作
        combat_actions = [
            ActionDefinition("拔剑出鞘", ActionType.COMBAT, "拔剑出鞘", 
                           ["长剑出鞘", "剑光一闪"], emotion_tone="aggressive", intensity=3),
            ActionDefinition("挥剑斩出", ActionType.COMBAT, "挥剑斩出", 
                           ["剑锋一挥", "长剑横扫"], emotion_tone="aggressive", intensity=4),
            ActionDefinition("侧身闪避", ActionType.COMBAT, "侧身闪开", 
                           ["身形一闪", "侧身躲过"], emotion_tone="alert", intensity=2),
            ActionDefinition("凝神蓄势", ActionType.COMBAT, "凝神蓄势", 
                           ["暗暗蓄力", "调整呼吸"], emotion_tone="focused", intensity=2),
            ActionDefinition("拳风呼啸", ActionType.COMBAT, "一拳轰出", 
                           ["拳势如风", "拳影呼啸"], emotion_tone="aggressive", intensity=4),
            ActionDefinition("身形暴退", ActionType.COMBAT, "身形暴退", 
                           ["急忙后退", "飞身退开"], emotion_tone="urgent", intensity=3),
            ActionDefinition("剑势一转", ActionType.COMBAT, "剑势一转", 
                           ["剑锋一变", "招式变换"], emotion_tone="focused", intensity=2),
            ActionDefinition("护住要害", ActionType.COMBAT, "护住要害", 
                           ["守住关键部位", "格挡防御"], emotion_tone="defensive", intensity=2),
        ]
        
        # 休息类动作
        rest_actions = [
            ActionDefinition("席地而坐", ActionType.REST, "席地而坐", 
                           ["盘膝坐下", "就地坐下"], emotion_tone="calm"),
            ActionDefinition("靠树休息", ActionType.REST, "靠在树边休息", 
                           ["倚树小憩", "靠树坐下"], emotion_tone="calm"),
            ActionDefinition("闭目养神", ActionType.REST, "闭目养神", 
                           ["阖目休息", "闭眼调息"], emotion_tone="calm"),
            ActionDefinition("伸展筋骨", ActionType.REST, "伸展筋骨", 
                           ["活动一下身体", "舒展筋骨"], emotion_tone="relaxed"),
            ActionDefinition("调息吐纳", ActionType.REST, "开始调息吐纳", 
                           ["调整呼吸", "运功调息"], emotion_tone="focused", intensity=2),
        ]
        
        # 技能类动作
        skill_actions = [
            ActionDefinition("掐诀施法", ActionType.SKILL, "双手掐诀", 
                           ["手指掐诀", "结印施法"], emotion_tone="focused", intensity=3),
            ActionDefinition("运转功法", ActionType.SKILL, "运转功法", 
                           ["催动内力", "运功行气"], emotion_tone="focused", intensity=3),
            ActionDefinition("祭出法宝", ActionType.SKILL, "祭出法宝", 
                           ["唤出法宝", "法器飞出"], emotion_tone="aggressive", intensity=3),
            ActionDefinition("神识探出", ActionType.SKILL, "放出神识探查", 
                           ["神识外放", "以神识探查"], emotion_tone="focused", intensity=2),
            ActionDefinition("布下阵法", ActionType.SKILL, "开始布阵", 
                           ["布置阵法", "刻画阵纹"], emotion_tone="focused", intensity=4),
        ]
        
        # 注册所有动作
        for action in (movement_actions + interaction_actions + observation_actions + 
                      emotion_actions + combat_actions + rest_actions + skill_actions):
            self._action_library[action.name] = action
    
    def _initialize_combinations(self):
        """初始化动作组合"""
        
        self._combinations = [
            ActionCombination(
                "观察后行动",
                ["环顾四周", "驻足停步"],
                "{0}，随后{1}",
                [CharacterRole.PROTAGONIST, CharacterRole.WARRIOR],
                ["探索", "警戒"]
            ),
            ActionCombination(
                "礼貌问候",
                ["拱手行礼", "开口询问"],
                "{0}，{1}",
                [CharacterRole.PROTAGONIST, CharacterRole.SCHOLAR],
                ["社交", "求助"]
            ),
            ActionCombination(
                "战斗准备",
                ["拔剑出鞘", "凝神蓄势"],
                "{0}，{1}",
                [CharacterRole.WARRIOR, CharacterRole.PROTAGONIST],
                ["战斗", "对峙"]
            ),
            ActionCombination(
                "沉思后决定",
                ["低头沉思", "微微一笑"],
                "{0}，片刻后{1}",
                [CharacterRole.PROTAGONIST, CharacterRole.SCHOLAR],
                ["决策", "领悟"]
            ),
            ActionCombination(
                "警惕后退",
                ["神色凝重", "稳步后退"],
                "{0}，{1}",
                [CharacterRole.PROTAGONIST, CharacterRole.WARRIOR],
                ["危险", "撤退"]
            ),
            ActionCombination(
                "友好接近",
                ["微微一笑", "缓步前行"],
                "{0}，{1}",
                [CharacterRole.PROTAGONIST, CharacterRole.COMPANION],
                ["友好", "接近"]
            ),
        ]
    
    def _initialize_role_actions(self):
        """初始化角色专属动作"""
        
        self._role_actions[CharacterRole.PROTAGONIST] = [
            "缓步前行", "环顾四周", "低头沉思", "微微一笑", "开口询问",
            "驻足停步", "凝神细看", "点头示意", "转身回望", "神色凝重"
        ]
        
        self._role_actions[CharacterRole.ANTAGONIST] = [
            "冷笑一声", "眼中闪过精光", "拔剑出鞘", "挥剑斩出", "神色凝重",
            "侧身闪避", "凝神蓄势", "转身回望", "眉头紧锁", "强作镇定"
        ]
        
        self._role_actions[CharacterRole.MENTOR] = [
            "微微一笑", "摇头叹息", "拱手行礼", "低声回应", "闭目感知",
            "调息吐纳", "伸手相邀", "点头示意", "拱手相谢", "低头沉思"
        ]
        
        self._role_actions[CharacterRole.COMPANION] = [
            "快步疾行", "环顾四周", "低声回应", "微微一笑", "驻足停步",
            "侧耳倾听", "伸手相邀", "点头示意", "拱手行礼", "神色凝重"
        ]
        
        self._role_actions[CharacterRole.WARRIOR] = [
            "拔剑出鞘", "挥剑斩出", "侧身闪避", "凝神蓄势", "拳风呼啸",
            "身形暴退", "剑势一转", "护住要害", "神色凝重", "眼中闪过精光"
        ]
        
        self._role_actions[CharacterRole.SCHOLAR] = [
            "拱手行礼", "低头沉思", "开口询问", "摇头叹息", "微微一笑",
            "凝神细看", "闭目感知", "拱手相谢", "抱拳告辞", "点头示意"
        ]
        
        self._role_actions[CharacterRole.MERCHANT] = [
            "拱手行礼", "微微一笑", "开口询问", "点头示意", "拱手相谢",
            "环顾四周", "伸手相邀", "低声回应", "抱拳告辞", "神色凝重"
        ]
        
        self._role_actions[CharacterRole.NPC] = [
            "微微一笑", "点头示意", "低声回应", "摇头叹息", "拱手行礼",
            "环顾四周", "驻足停步", "转身回望", "抱拳告辞", "缓步前行"
        ]
    
    def get_action(self, character_name: str, role: CharacterRole = CharacterRole.PROTAGONIST,
                   action_type: ActionType = None, context: str = None) -> str:
        """
        获取角色动作（自动去重和轮换）
        """
        # 获取角色可用的动作
        available = self._role_actions.get(role, self._role_actions[CharacterRole.PROTAGONIST])
        
        # 如果指定了动作类型，筛选
        if action_type:
            available = [a for a in available 
                        if a in self._action_library and self._action_library[a].action_type == action_type]
        
        if not available:
            available = list(self._action_library.keys())
        
        # 获取角色历史动作
        history = self._action_history.get(character_name, [])
        
        # 过滤掉最近使用的动作
        recent_actions = history[-3:] if len(history) >= 3 else history
        candidates = [a for a in available if a not in recent_actions]
        
        # 如果所有动作都用过了，重置
        if not candidates:
            candidates = available
        
        # 选择动作
        selected = random.choice(candidates)
        
        # 记录历史
        self._action_history[character_name].append(selected)
        if len(self._action_history[character_name]) > self._max_history:
            self._action_history[character_name] = self._action_history[character_name][-self._max_history:]
        
        # 返回动作描述（可能有变体）
        action_def = self._action_library.get(selected)
        if action_def:
            if action_def.variations and random.random() < 0.4:
                return random.choice(action_def.variations)
            return action_def.description
        
        return selected
    
    def get_action_combination(self, role: CharacterRole, context: str) -> Optional[str]:
        """获取动作组合"""
        # 筛选适用的组合
        applicable = [c for c in self._combinations 
                     if role in c.applicable_roles and context in c.applicable_contexts]
        
        if not applicable:
            return None
        
        combo = random.choice(applicable)
        
        # 获取组合中每个动作的描述
        action_descs = []
        for action_name in combo.actions:
            action_def = self._action_library.get(action_name)
            if action_def:
                action_descs.append(action_def.description)
            else:
                action_descs.append(action_name)
        
        # 组合描述
        try:
            return combo.description_template.format(*action_descs)
        except:
            return "，".join(action_descs)
    
    def get_contextual_action(self, character_name: str, role: CharacterRole,
                              situation: str, target_name: str = None) -> str:
        """
        根据情境获取动作
        situation: 探索/战斗/社交/休息/警戒/危险/友好
        """
        # 情境到动作类型的映射
        situation_mapping = {
            "探索": [ActionType.MOVEMENT, ActionType.OBSERVATION],
            "战斗": [ActionType.COMBAT, ActionType.MOVEMENT],
            "社交": [ActionType.INTERACTION, ActionType.EMOTION],
            "休息": [ActionType.REST, ActionType.EMOTION],
            "警戒": [ActionType.OBSERVATION, ActionType.MOVEMENT],
            "危险": [ActionType.COMBAT, ActionType.MOVEMENT],
            "友好": [ActionType.INTERACTION, ActionType.EMOTION],
            "沉思": [ActionType.OBSERVATION, ActionType.EMOTION],
        }
        
        action_types = situation_mapping.get(situation, [ActionType.MOVEMENT])
        action_type = random.choice(action_types)
        
        action_desc = self.get_action(character_name, role, action_type)
        
        # 如果需要目标，添加目标名
        action_def = None
        for name, defn in self._action_library.items():
            if defn.description == action_desc or action_desc in defn.variations:
                action_def = defn
                break
        
        if action_def and action_def.requires_target and target_name:
            return f"{action_desc}「{target_name}」"
        
        return action_desc
    
    def add_custom_action(self, action: ActionDefinition, roles: List[CharacterRole] = None):
        """添加自定义动作"""
        self._action_library[action.name] = action
        if roles:
            for role in roles:
                self._role_actions[role].append(action.name)
    
    def add_custom_combination(self, combination: ActionCombination):
        """添加自定义动作组合"""
        self._combinations.append(combination)
    
    def get_available_actions(self, role: CharacterRole) -> List[str]:
        """获取角色可用动作列表"""
        return self._role_actions.get(role, [])
    
    def reset_character_history(self, character_name: str):
        """重置角色动作历史"""
        if character_name in self._action_history:
            del self._action_history[character_name]
    
    def reset_all(self):
        """重置所有历史"""
        self._action_history.clear()
        self._used_actions.clear()


# 单例模式
_action_expander_instance = None

def get_action_expander() -> ActionExpander:
    """获取动作扩展器单例"""
    global _action_expander_instance
    if _action_expander_instance is None:
        _action_expander_instance = ActionExpander()
    return _action_expander_instance
