# -*- coding: utf-8 -*-
"""
叙事状态管理器 - 解决叙事状态和一致性问题
1. 剧情推进状态机
2. 场景与物品一致性检查
3. 配角出场规则
4. 冗余心理描写清洗
5. 叙事句式规范
"""
from typing import Dict, List, Optional, Set, Tuple
from dataclasses import dataclass, field
from enum import Enum
import re
import random
from collections import defaultdict


# ========== 主题场景配置 ==========

THEME_SCENES = {
    "日常": {
        "scenes": ["家", "街道", "市场", "公园", "学校", "办公室", "餐厅", "商店", "医院", "健身房"],
        "adjacent": {
            "家": ["街道", "公园"],
            "街道": ["家", "市场", "公园", "餐厅", "商店"],
            "市场": ["街道", "商店"],
            "公园": ["街道", "家"],
            "学校": ["街道", "公园"],
            "办公室": ["街道", "餐厅"],
            "餐厅": ["街道", "办公室"],
            "商店": ["街道", "市场"],
            "医院": ["街道"],
            "健身房": ["街道", "公园"],
        },
        "vague_locations": [
            "街角", "公园长椅上", "咖啡店里", "超市货架间",
            "公交车上", "地铁站", "小区楼下", "便利店门口",
            "书店角落", "餐厅卡座", "办公室茶水间", "健身房跑步机上",
        ],
    },
    "修仙": {
        "scenes": ["宗门", "炼丹房", "剑冢", "秘境", "山脉", "洞府", "坊市", "灵脉", "禁地", "试炼场"],
        "adjacent": {
            "宗门": ["炼丹房", "剑冢", "坊市", "试炼场"],
            "炼丹房": ["宗门", "坊市"],
            "剑冢": ["宗门", "山脉"],
            "秘境": ["山脉", "禁地"],
            "山脉": ["剑冢", "秘境", "洞府"],
            "洞府": ["山脉", "灵脉"],
            "坊市": ["宗门", "炼丹房"],
            "灵脉": ["洞府", "禁地"],
            "禁地": ["秘境", "灵脉"],
            "试炼场": ["宗门", "秘境"],
        },
        "vague_locations": [
            "山崖边", "洞府深处", "灵气浓郁的密林", "古修遗址",
            "瀑布后的洞穴", "云雾缭绕的山峰", "灵药园中", "藏经阁角落",
            "演武场上", "护宗大阵边缘", "灵脉交汇处", "禁地入口",
        ],
    },
    "奇幻": {
        "scenes": ["城镇", "酒馆", "森林", "山脉", "地下城", "遗迹", "魔法塔", "神殿", "港口", "荒野"],
        "adjacent": {
            "城镇": ["酒馆", "港口", "魔法塔", "神殿"],
            "酒馆": ["城镇", "荒野"],
            "森林": ["山脉", "遗迹", "荒野"],
            "山脉": ["森林", "地下城"],
            "地下城": ["山脉", "遗迹"],
            "遗迹": ["森林", "地下城"],
            "魔法塔": ["城镇", "遗迹"],
            "神殿": ["城镇", "魔法塔"],
            "港口": ["城镇", "荒野"],
            "荒野": ["酒馆", "森林", "港口"],
        },
        "vague_locations": [
            "古老遗迹深处", "魔法阵中心", "龙巢边缘", "精灵聚落",
            "矮人矿坑入口", "亡灵墓地", "巨龙山脉脚下", "魔法森林空地",
            "传送阵旁", "神秘泉水边", "符文石柱间", "幻境迷宫中",
        ],
    },
    "末世": {
        "scenes": ["安全区", "废墟", "森林", "废弃城市", "地下掩体", "物资仓库", "医院", "军事基地", "避难所", "辐射区"],
        "adjacent": {
            "安全区": ["废墟", "避难所", "医院"],
            "废墟": ["安全区", "废弃城市", "森林"],
            "森林": ["废墟", "辐射区"],
            "废弃城市": ["废墟", "地下掩体", "物资仓库"],
            "地下掩体": ["废弃城市", "军事基地"],
            "物资仓库": ["废弃城市", "安全区"],
            "医院": ["安全区", "废墟"],
            "军事基地": ["地下掩体", "避难所"],
            "避难所": ["安全区", "军事基地"],
            "辐射区": ["森林", "废墟"],
        },
        "vague_locations": [
            "废弃建筑内", "瓦砾堆中", "生锈的车辆旁", "坍塌的墙角",
            "地下管道里", "防空洞深处", "被封锁的超市", "加油站废墟",
            "医院走廊尽头", "军火库入口", "避难所通风口", "辐射警示牌旁",
        ],
    },
    "科幻": {
        "scenes": ["空间站", "飞船", "殖民地", "实验室", "星际港口", "数据中心", "工厂", "矿区", "科研基地", "虫洞"],
        "adjacent": {
            "空间站": ["飞船", "星际港口", "实验室"],
            "飞船": ["空间站", "殖民地", "虫洞"],
            "殖民地": ["飞船", "工厂", "矿区"],
            "实验室": ["空间站", "科研基地", "数据中心"],
            "星际港口": ["空间站", "殖民地"],
            "数据中心": ["实验室", "科研基地"],
            "工厂": ["殖民地", "矿区"],
            "矿区": ["殖民地", "工厂"],
            "科研基地": ["实验室", "数据中心"],
            "虫洞": ["飞船", "空间站"],
        },
        "vague_locations": [
            "飞船驾驶舱", "冷冻舱旁", "气闸门外", "引擎室角落",
            "实验室培养皿前", "量子计算机旁", "太空电梯轿厢", "戴森球内壁",
            "虫洞边缘", "外星遗迹入口", "纳米机器人群中心", "全息投影室",
        ],
    },
    "恐怖": {
        "scenes": ["废弃医院", "老宅", "墓地", "地下室", "阁楼", "森林", "废弃学校", "教堂", "精神病院", "古堡"],
        "adjacent": {
            "废弃医院": ["地下室", "精神病院", "森林"],
            "老宅": ["地下室", "阁楼", "墓地"],
            "墓地": ["老宅", "教堂", "森林"],
            "地下室": ["废弃医院", "老宅", "古堡"],
            "阁楼": ["老宅", "古堡"],
            "森林": ["废弃医院", "墓地", "废弃学校"],
            "废弃学校": ["森林", "地下室"],
            "教堂": ["墓地", "老宅"],
            "精神病院": ["废弃医院", "地下室"],
            "古堡": ["阁楼", "地下室", "森林"],
        },
        "vague_locations": [
            "昏暗走廊尽头", "吱呀作响的楼梯上", "布满灰尘的房间", "镜子前",
            "棺材旁", "祭坛前", "血迹斑斑的墙角", "破旧神像下",
            "摇曳的烛光中", "阴冷的停尸房", "精神病院禁闭室", "古堡密道",
        ],
    },
}

# 默认场景配置（日常）
DEFAULT_SCENES = THEME_SCENES["日常"]


# ========== 1. 剧情推进状态机 ==========

class PlotState(Enum):
    """剧情阶段状态"""
    IDLE = 0           # 初始闲逛
    GOAL_SET = 1       # 产生目标
    PREPARING = 2      # 准备物品
    APPROACHING = 3    # 靠近目标
    ATTEMPTING = 4     # 尝试交互
    INTERACTING = 5    # 交互中
    RESULT = 6         # 结果与后续
    COMPLETED = 7      # 完成


@dataclass
class PlotStateMachine:
    """剧情状态机"""
    current_state: PlotState = PlotState.IDLE
    state_history: List[Tuple[int, PlotState]] = field(default_factory=list)
    stuck_count: int = 0           # 卡住计数
    max_stuck: int = 2             # 最大卡住次数
    
    def advance(self) -> Tuple[bool, str]:
        """推进到下一状态"""
        # 检查是否卡住
        if self.stuck_count >= self.max_stuck:
            # 强制推进
            self.stuck_count = 0
            return self._force_advance()
        
        # 正常推进
        next_state = self._get_next_state()
        if next_state != self.current_state:
            self.state_history.append((len(self.state_history), self.current_state))
            self.current_state = next_state
            self.stuck_count = 0
            return (True, f"剧情推进: {self.current_state.name}")
        else:
            self.stuck_count += 1
            return (False, f"剧情卡在: {self.current_state.name}")
    
    def _get_next_state(self) -> PlotState:
        """获取下一状态"""
        transitions = {
            PlotState.IDLE: PlotState.GOAL_SET,
            PlotState.GOAL_SET: PlotState.PREPARING,
            PlotState.PREPARING: PlotState.APPROACHING,
            PlotState.APPROACHING: PlotState.ATTEMPTING,
            PlotState.ATTEMPTING: PlotState.INTERACTING,
            PlotState.INTERACTING: PlotState.RESULT,
            PlotState.RESULT: PlotState.COMPLETED,
            PlotState.COMPLETED: PlotState.IDLE,  # 循环
        }
        return transitions.get(self.current_state, PlotState.IDLE)
    
    def _force_advance(self) -> Tuple[bool, str]:
        """强制推进"""
        next_state = self._get_next_state()
        self.state_history.append((len(self.state_history), self.current_state))
        self.current_state = next_state
        return (True, f"强制推进: {self.current_state.name}")
    
    def can_stay(self) -> bool:
        """检查是否可以停留在当前状态"""
        return self.stuck_count < self.max_stuck


# ========== 2. 场景与物品一致性检查 ==========

@dataclass
class WorldState:
    """世界状态"""
    current_location: str = ""
    inventory: List[str] = field(default_factory=list)
    nearby_characters: List[str] = field(default_factory=list)
    time_of_day: int = 12


class ConsistencyChecker:
    """一致性检查器 - 支持主题动态场景"""
    
    def __init__(self, theme: str = "日常"):
        self._world_state = WorldState()
        self._state_history: List[WorldState] = []
        self._theme = theme
        self._theme_config = THEME_SCENES.get(theme, DEFAULT_SCENES)
    
    def set_theme(self, theme: str):
        """设置主题并更新场景配置"""
        self._theme = theme
        self._theme_config = THEME_SCENES.get(theme, DEFAULT_SCENES)
    
    def get_valid_scenes(self) -> List[str]:
        """获取当前主题的有效场景列表"""
        return self._theme_config.get("scenes", DEFAULT_SCENES["scenes"])
    
    def get_vague_locations(self) -> List[str]:
        """获取当前主题的模糊场景列表"""
        return self._theme_config.get("vague_locations", DEFAULT_SCENES["vague_locations"])
    
    def check_location_consistency(self, new_location: str) -> Tuple[bool, str]:
        """检查场景一致性"""
        if not self._world_state.current_location:
            # 首次设置
            self._world_state.current_location = new_location
            return (True, "")
        
        # 检查是否是有效场景
        valid_scenes = self.get_valid_scenes()
        if new_location not in valid_scenes:
            # 检查是否是模糊场景（允许）
            vague_locations = self.get_vague_locations()
            if new_location in vague_locations:
                return (True, "")  # 模糊场景允许
            # 无效场景
            return (False, f"场景 '{new_location}' 不是当前主题 '{self._theme}' 的有效场景")
        
        # 检查是否合理跳转
        valid_transitions = self._get_valid_transitions(self._world_state.current_location)
        
        if new_location == self._world_state.current_location:
            return (True, "")  # 同一场景
        elif new_location in valid_transitions:
            return (True, "")  # 合理跳转
        else:
            # 允许跳转到任意有效场景（放宽限制）
            return (True, "")
    
    def _get_valid_transitions(self, location: str) -> List[str]:
        """获取合理的场景跳转"""
        adjacent = self._theme_config.get("adjacent", DEFAULT_SCENES["adjacent"])
        return adjacent.get(location, [])
    
    def check_item_consistency(self, action: str, items: List[str]) -> Tuple[bool, str]:
        """检查物品一致性"""
        # 检查是否凭空出现物品
        for item in items:
            if item not in self._world_state.inventory:
                # 检查是否是拾取动作
                if "拾" in action or "拿" in action or "买" in action:
                    # 合理获取
                    continue
                else:
                    return (False, f"物品凭空出现: {item}")
        
        return (True, "")
    
    def update_state(self, location: str = None, inventory: List[str] = None):
        """更新世界状态"""
        if location:
            self._world_state.current_location = location
        if inventory is not None:
            self._world_state.inventory = inventory.copy()
        
        # 记录历史
        self._state_history.append(WorldState(
            current_location=self._world_state.current_location,
            inventory=self._world_state.inventory.copy(),
            nearby_characters=self._world_state.nearby_characters.copy(),
            time_of_day=self._world_state.time_of_day
        ))
    
    def get_current_state(self) -> WorldState:
        """获取当前世界状态"""
        return self._world_state


# ========== 3. 配角出场规则 ==========

@dataclass
class SupportingCharacterRule:
    """配角规则"""
    name: str
    appearance_probability: float    # 出场概率
    cooldown: int                    # 冷却回合
    current_cooldown: int = 0        # 当前冷却
    appearance_count: int = 0        # 出场次数
    must_relates_to_main: bool = True  # 必须与主线相关


class SupportingCharacterController:
    """配角出场控制器"""
    
    def __init__(self):
        self._character_rules: Dict[str, SupportingCharacterRule] = {}
        self._recent_appearances: List[str] = []  # 最近出场的配角
        self._max_recent = 5
        self._max_consecutive = 2  # 最大连续出场次数
        
        self._initialize_rules()
    
    def _initialize_rules(self):
        """初始化配角规则"""
        self._character_rules = {
            "赵磊": SupportingCharacterRule("赵磊", 0.3, 3),
            "阿花": SupportingCharacterRule("阿花", 0.25, 4),
            "婴儿": SupportingCharacterRule("婴儿", 0.15, 5),
            "猫": SupportingCharacterRule("猫", 0.2, 3),
        }
    
    def can_appear(self, character_name: str, is_main_related: bool = True) -> Tuple[bool, str]:
        """检查配角是否可以出场"""
        if character_name not in self._character_rules:
            return (True, "")  # 未知角色，默认允许
        
        rule = self._character_rules[character_name]
        
        # 检查冷却
        if rule.current_cooldown > 0:
            return (False, f"{character_name} 在冷却中")
        
        # 检查是否与主线相关
        if rule.must_relates_to_main and not is_main_related:
            return (False, f"{character_name} 必须与主线相关才能出场")
        
        # 检查连续出场
        consecutive = self._count_consecutive(character_name)
        if consecutive >= self._max_consecutive:
            return (False, f"{character_name} 连续出场次数过多")
        
        # 概率检查
        if random.random() > rule.appearance_probability:
            return (False, f"{character_name} 出场概率未通过")
        
        return (True, "")
    
    def _count_consecutive(self, character_name: str) -> int:
        """计算连续出场次数"""
        count = 0
        for name in reversed(self._recent_appearances):
            if name == character_name:
                count += 1
            else:
                break
        return count
    
    def register_appearance(self, character_name: str):
        """注册配角出场"""
        if character_name in self._character_rules:
            self._character_rules[character_name].current_cooldown = self._character_rules[character_name].cooldown
            self._character_rules[character_name].appearance_count += 1
        
        self._recent_appearances.append(character_name)
        if len(self._recent_appearances) > self._max_recent:
            self._recent_appearances = self._recent_appearances[-self._max_recent:]
    
    def advance_cooldowns(self):
        """推进冷却"""
        for rule in self._character_rules.values():
            if rule.current_cooldown > 0:
                rule.current_cooldown -= 1


# ========== 4. 冗余心理描写清洗 ==========

class PsychologicalDescriptionCleaner:
    """心理描写清洗器"""
    
    def __init__(self):
        # 高频心理描写模板词
        self._template_phrases = [
            "指尖微凉", "喉结滚动", "深吸一口气", "心跳加速",
            "手心出汗", "眉头紧锁", "目光闪烁", "嘴角微扬",
            "心中一动", "暗自思忖", "若有所思", "心下暗道",
            "不禁一怔", "微微一愣", "心中涌起", "泛起涟漪",
        ]
        
        # 每段最大心理描写数量
        self._max_per_paragraph = 1
        
        # 使用计数
        self._usage_count: Dict[str, int] = defaultdict(int)
        self._max_usage = 3  # 每个模板词最大使用次数
    
    def clean(self, content: str) -> str:
        """清洗冗余心理描写"""
        # 找出所有心理描写
        found_phrases = []
        for phrase in self._template_phrases:
            if phrase in content:
                found_phrases.append(phrase)
        
        # 如果超过限制，移除多余的
        if len(found_phrases) > self._max_per_paragraph:
            # 保留第一个，移除其他的
            to_remove = found_phrases[self._max_per_paragraph:]
            for phrase in to_remove:
                content = content.replace(phrase, "")
        
        # 检查使用次数
        for phrase in found_phrases[:self._max_per_paragraph]:
            if self._usage_count[phrase] >= self._max_usage:
                # 替换为更通用的表达
                content = content.replace(phrase, self._get_generic_alternative(phrase))
            else:
                self._usage_count[phrase] += 1
        
        return content
    
    def _get_generic_alternative(self, phrase: str) -> str:
        """获取通用替代表达"""
        alternatives = [
            "心中有所触动",
            "神色微变",
            "若有所感",
        ]
        return random.choice(alternatives)
    
    def reset_usage(self):
        """重置使用计数"""
        self._usage_count.clear()


# ========== 5. 叙事句式规范 ==========

class NarrativeStyleEnforcer:
    """叙事句式规范执行器"""
    
    def __init__(self):
        # 禁止的自指模式
        self._self_reference_patterns = [
            r'(\S+?)……\s*\1',  # "陈阳…… 陈阳"
            r'我\S*我',         # 自指重复
        ]
        
        # 第三人称代词
        self._third_person_pronouns = ["他", "她", "它", "他们", "她们", "它们"]
        
        # 禁止的第一/第二人称
        self._forbidden_pronouns = ["我", "我们", "你", "你们"]
    
    def enforce_style(self, content: str, protagonist: str = None) -> Tuple[str, List[str]]:
        """执行句式规范"""
        warnings = []
        
        # 1. 检查自指重复
        for pattern in self._self_reference_patterns:
            matches = re.findall(pattern, content)
            if matches:
                warnings.append(f"发现自指重复: {matches}")
                # 移除重复
                content = re.sub(pattern, r'\1', content)
        
        # 2. 检查第一/第二人称（不在对话中）
        content = self._check_pronouns(content, warnings)
        
        # 3. 检查未完成句
        content = self._check_incomplete_sentences(content, warnings)
        
        return (content, warnings)
    
    def _check_pronouns(self, content: str, warnings: List[str]) -> str:
        """检查人称"""
        # 简单处理：不在引号内的第一/第二人称替换
        in_quote = False
        chars = list(content)
        
        for i, char in enumerate(chars):
            if char in '"「『':
                in_quote = True
            elif char in '"」』':
                in_quote = False
            elif not in_quote:
                if char == '我':
                    chars[i] = '他'
                elif char == '你':
                    chars[i] = '他'
        
        return ''.join(chars)
    
    def _check_incomplete_sentences(self, content: str, warnings: List[str]) -> str:
        """检查未完成句"""
        # 检查以省略号结尾但没有主语的句子
        incomplete_pattern = r'([。！？])\s*……'
        if re.search(incomplete_pattern, content):
            warnings.append("发现未完成句")
            content = re.sub(incomplete_pattern, r'\1', content)
        
        # 检查孤立的省略号
        content = re.sub(r'……\s*……', '……', content)
        
        return content


# ========== 统一管理器 ==========

class NarrativeStateManager:
    """叙事状态管理器 - 统一入口"""
    
    def __init__(self, theme: str = "日常"):
        self.plot_machine = PlotStateMachine()
        self.consistency_checker = ConsistencyChecker(theme=theme)
        self.supporting_controller = SupportingCharacterController()
        self.psychological_cleaner = PsychologicalDescriptionCleaner()
        self.style_enforcer = NarrativeStyleEnforcer()
        
        self._current_timestamp = 0
        self._theme = theme
    
    def set_theme(self, theme: str):
        """设置主题"""
        self._theme = theme
        self.consistency_checker.set_theme(theme)
    
    def get_theme_scenes(self) -> List[str]:
        """获取当前主题的有效场景"""
        return self.consistency_checker.get_valid_scenes()
    
    def get_theme_vague_locations(self) -> List[str]:
        """获取当前主题的模糊场景"""
        return self.consistency_checker.get_vague_locations()
    
    def process_narrative(self, content: str, context: Dict = None) -> Tuple[str, List[str]]:
        """
        处理叙事内容
        返回: (处理后的内容, 警告列表)
        """
        if context is None:
            context = {}
        
        all_warnings = []
        
        # 1. 推进剧情状态
        advanced, msg = self.plot_machine.advance()
        if not advanced:
            all_warnings.append(msg)
        
        # 2. 检查场景一致性
        new_location = context.get("location", "")
        if new_location:
            valid, msg = self.consistency_checker.check_location_consistency(new_location)
            if not valid:
                all_warnings.append(msg)
        
        # 3. 清洗冗余心理描写
        content = self.psychological_cleaner.clean(content)
        
        # 4. 执行句式规范
        protagonist = context.get("protagonist", "")
        content, warnings = self.style_enforcer.enforce_style(content, protagonist)
        all_warnings.extend(warnings)
        
        # 5. 推进时间戳
        self._current_timestamp += 1
        
        return (content, all_warnings)
    
    def check_supporting_character(self, name: str, is_main_related: bool = True) -> Tuple[bool, str]:
        """检查配角是否可以出场"""
        return self.supporting_controller.can_appear(name, is_main_related)
    
    def register_supporting_appearance(self, name: str):
        """注册配角出场"""
        self.supporting_controller.register_appearance(name)
    
    def advance_round(self):
        """推进回合"""
        self.supporting_controller.advance_cooldowns()
    
    def get_plot_state(self) -> PlotState:
        """获取当前剧情状态"""
        return self.plot_machine.current_state
    
    def get_world_state(self) -> WorldState:
        """获取当前世界状态"""
        return self.consistency_checker.get_current_state()


# 单例
_state_manager_instance = None

def get_state_manager(theme: str = "日常") -> NarrativeStateManager:
    global _state_manager_instance
    if _state_manager_instance is None:
        _state_manager_instance = NarrativeStateManager(theme=theme)
    return _state_manager_instance

def get_theme_scenes(theme: str) -> List[str]:
    """获取指定主题的有效场景列表"""
    config = THEME_SCENES.get(theme, DEFAULT_SCENES)
    return config.get("scenes", DEFAULT_SCENES["scenes"])

def get_theme_vague_locations(theme: str) -> List[str]:
    """获取指定主题的模糊场景列表"""
    config = THEME_SCENES.get(theme, DEFAULT_SCENES)
    return config.get("vague_locations", DEFAULT_SCENES["vague_locations"])
