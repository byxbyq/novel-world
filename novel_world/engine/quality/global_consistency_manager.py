# -*- coding: utf-8 -*-
"""
全局状态一致性管理器 - 解决场景/天气/物品/角色状态的跳转问题
"""
from typing import Dict, List, Optional, Set, Tuple
from dataclasses import dataclass, field
from enum import Enum
import random
from collections import defaultdict


# ========== 场景配置 ==========

THEME_SCENES = {
    "日常": {
        "scenes": ["家", "街道", "市场", "公园", "学校", "办公室", "餐厅", "商店", "医院", "健身房", "球场", "便利店", "咖啡馆"],
        "transitions": {
            "家": ["街道", "便利店"],
            "街道": ["家", "市场", "公园", "餐厅", "商店", "学校", "办公室", "医院", "健身房", "球场", "便利店", "咖啡馆"],
            "市场": ["街道", "商店"],
            "公园": ["街道", "家"],
            "学校": ["街道", "公园"],
            "办公室": ["街道", "餐厅", "咖啡馆"],
            "餐厅": ["街道", "办公室", "家"],
            "商店": ["街道", "市场"],
            "医院": ["街道", "家"],
            "健身房": ["街道", "公园", "家"],
            "球场": ["街道", "公园", "家"],
            "便利店": ["街道", "家"],
            "咖啡馆": ["街道", "办公室", "家"],
        },
    },
    "修仙": {
        "scenes": ["宗门", "炼丹房", "剑冢", "秘境", "山脉", "洞府", "坊市", "灵脉", "禁地", "试炼场"],
        "transitions": {
            "宗门": ["炼丹房", "剑冢", "坊市", "试炼场", "洞府"],
            "炼丹房": ["宗门", "坊市"],
            "剑冢": ["宗门", "山脉"],
            "秘境": ["山脉", "禁地"],
            "山脉": ["剑冢", "秘境", "洞府"],
            "洞府": ["山脉", "灵脉", "宗门"],
            "坊市": ["宗门", "炼丹房"],
            "灵脉": ["洞府", "禁地"],
            "禁地": ["秘境", "灵脉"],
            "试炼场": ["宗门", "秘境"],
        },
    },
    "奇幻": {
        "scenes": ["城镇", "酒馆", "森林", "山脉", "地下城", "遗迹", "魔法塔", "神殿", "港口", "荒野"],
        "transitions": {
            "城镇": ["酒馆", "港口", "魔法塔", "神殿"],
            "酒馆": ["城镇", "荒野", "森林"],
            "森林": ["山脉", "遗迹", "荒野", "酒馆"],
            "山脉": ["森林", "地下城"],
            "地下城": ["山脉", "遗迹"],
            "遗迹": ["森林", "地下城"],
            "魔法塔": ["城镇", "遗迹"],
            "神殿": ["城镇", "魔法塔"],
            "港口": ["城镇", "荒野"],
            "荒野": ["酒馆", "森林", "港口"],
        },
    },
    "末世": {
        "scenes": ["安全区", "废墟", "森林", "废弃城市", "地下掩体", "物资仓库", "医院", "军事基地", "避难所", "辐射区"],
        "transitions": {
            "安全区": ["废墟", "避难所", "医院", "物资仓库"],
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
    },
    "科幻": {
        "scenes": ["空间站", "飞船", "殖民地", "实验室", "星际港口", "数据中心", "工厂", "矿区", "科研基地", "虫洞"],
        "transitions": {
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
    },
    "恐怖": {
        "scenes": ["废弃医院", "老宅", "墓地", "地下室", "阁楼", "森林", "废弃学校", "教堂", "精神病院", "古堡"],
        "transitions": {
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
    },
}

# ========== 天气配置 ==========

WEATHERS = {
    "日常": ["晴天", "多云", "阴天", "小雨", "中雨", "大风"],
    "修仙": ["晴天", "多云", "灵气浓郁", "雷暴", "迷雾", "仙光"],
    "奇幻": ["晴天", "多云", "阴天", "暴雨", "大雾", "魔法风暴"],
    "末世": ["晴天", "阴天", "酸雨", "沙尘暴", "辐射雾", "暴风雪"],
    "科幻": ["晴天", "真空", "太阳风暴", "陨石雨", "空间震荡"],
    "恐怖": ["阴天", "浓雾", "暴雨", "雷暴", "血月", "诡异寂静"],
}

# ========== 角色状态配置 ==========

CHARACTER_STATES = {
    "正常": ["正常", "放松", "平静"],
    "积极": ["兴奋", "开心", "期待", "满足"],
    "消极": ["紧张", "焦虑", "沮丧", "害怕", "愤怒"],
    "身体": ["感冒", "胃疼", "头痛", "疲劳", "受伤"],
}


@dataclass
class GlobalState:
    """全局状态"""
    current_scene: str = ""
    previous_scene: str = ""
    weather: str = "晴天"
    time_of_day: int = 8  # 0-24
    day_count: int = 1
    inventory: List[str] = field(default_factory=list)
    character_states: Dict[str, str] = field(default_factory=dict)
    recent_scenes: List[str] = field(default_factory=list)  # 最近场景历史
    recent_weathers: List[str] = field(default_factory=list)  # 最近天气历史


class GlobalConsistencyManager:
    """全局一致性管理器"""
    
    def __init__(self, theme: str = "日常"):
        self.theme = theme
        self.state = GlobalState()
        self.theme_config = THEME_SCENES.get(theme, THEME_SCENES["日常"])
        self.allowed_weathers = WEATHERS.get(theme, WEATHERS["日常"])
        
        # 状态变化冷却
        self._scene_cooldown = 0
        self._weather_cooldown = 0
        self._min_scene_stay = 3  # 最少停留回合
        self._min_weather_stay = 5  # 天气最少持续回合
        
        # 物品获取记录
        self._item_acquire_log: Dict[str, int] = {}  # item -> round
        self._current_round = 0
        
        # 去重相关
        self._recent_phrases: List[str] = []
        self._phrase_usage: Dict[str, int] = defaultdict(int)
        self._max_phrase_usage = 2  # 每个短语最多使用次数
        
        # 高频模板词（需要去重）
        self._template_phrases = [
            "攥着", "指尖微凉", "喉结滚动", "神色微变", "若有所感",
            "深吸一口气", "心跳加速", "手心出汗", "眉头紧锁",
            "目光闪烁", "嘴角微扬", "心中一动", "暗自思忖",
            "若有所思", "心下暗道", "不禁一怔", "微微一愣",
            "心中涌起", "泛起涟漪", "犹豫", "紧张", "不敢",
        ]
    
    def validate_scene_transition(self, new_scene: str) -> Tuple[bool, str, str]:
        """
        验证场景跳转是否合理
        返回: (is_valid, corrected_scene, message)
        """
        valid_scenes = self.theme_config.get("scenes", [])
        transitions = self.theme_config.get("transitions", {})
        
        # 如果是首次设置场景
        if not self.state.current_scene:
            if new_scene in valid_scenes:
                return (True, new_scene, "")
            else:
                # 选择一个默认场景
                default_scene = valid_scenes[0] if valid_scenes else "街道"
                return (False, default_scene, f"场景 '{new_scene}' 无效，使用默认场景 '{default_scene}'")
        
        # 检查是否在冷却期
        if self._scene_cooldown > 0:
            return (True, self.state.current_scene, f"场景冷却中，保持当前场景")
        
        # 检查新场景是否有效
        if new_scene not in valid_scenes:
            # 尝试找到相似的有效场景
            similar = self._find_similar_scene(new_scene, valid_scenes)
            if similar:
                new_scene = similar
            else:
                return (True, self.state.current_scene, f"场景 '{new_scene}' 无效，保持当前场景")
        
        # 检查跳转是否合理
        allowed_transitions = transitions.get(self.state.current_scene, [])
        
        if new_scene == self.state.current_scene:
            return (True, new_scene, "")  # 同一场景
        elif new_scene in allowed_transitions:
            return (True, new_scene, "")  # 合理跳转
        else:
            # 检查是否可以通过中间场景跳转
            for intermediate in allowed_transitions:
                if new_scene in transitions.get(intermediate, []):
                    return (True, new_scene, f"通过 {intermediate} 跳转到 {new_scene}")
            
            # 强制允许跳转，但设置冷却
            self._scene_cooldown = self._min_scene_stay
            return (True, new_scene, f"场景跳转需要过渡")
    
    def _find_similar_scene(self, scene: str, valid_scenes: List[str]) -> Optional[str]:
        """找到相似的有效场景"""
        # 简单的相似度匹配
        for valid in valid_scenes:
            if scene in valid or valid in scene:
                return valid
        return None
    
    def validate_weather_change(self, new_weather: str) -> Tuple[bool, str, str]:
        """
        验证天气变化是否合理
        返回: (is_valid, corrected_weather, message)
        """
        # 检查是否在冷却期
        if self._weather_cooldown > 0:
            return (True, self.state.weather, "天气持续中")
        
        # 检查天气是否有效
        if new_weather not in self.allowed_weathers:
            return (True, self.state.weather, f"天气 '{new_weather}' 无效")
        
        # 天气变化需要合理过渡
        # 相似天气可以直接切换，差异大的需要过渡
        current = self.state.weather
        if current == new_weather:
            return (True, new_weather, "")
        
        # 设置冷却
        self._weather_cooldown = self._min_weather_stay
        return (True, new_weather, "")
    
    def validate_item_appearance(self, item: str, action: str) -> Tuple[bool, str]:
        """
        验证物品出现是否合理
        返回: (is_valid, message)
        """
        # 检查物品是否已经在库存中
        if item in self.state.inventory:
            return (True, "")
        
        # 检查是否有获取动作
        acquire_keywords = ["拿", "取", "买", "捡", "拾", "接", "收", "获得", "得到", "找到"]
        if any(kw in action for kw in acquire_keywords):
            # 合理获取
            self.state.inventory.append(item)
            self._item_acquire_log[item] = self._current_round
            return (True, f"获取物品: {item}")
        
        # 检查是否是常见物品（可以凭空出现）
        common_items = ["手机", "钱包", "钥匙", "包", "书", "笔", "水", "纸巾"]
        if item in common_items:
            return (True, "")
        
        return (False, f"物品 '{item}' 凭空出现，需要前置获取动作")
    
    def validate_character_state_change(self, char_name: str, new_state: str) -> Tuple[bool, str]:
        """
        验证角色状态变化是否合理
        返回: (is_valid, message)
        """
        current_state = self.state.character_states.get(char_name, "正常")
        
        # 状态不能随意跳跃
        # 身体状态需要恢复过程
        body_states = CHARACTER_STATES["身体"]
        if current_state in body_states and new_state == "正常":
            # 身体状态不能直接恢复，需要过渡
            return (False, f"角色 '{char_name}' 的 '{current_state}' 状态需要恢复过程")
        
        # 情绪状态可以变化，但不能反复横跳
        # 记录状态历史，防止快速反复
        return (True, "")
    
    def check_text_repetition(self, text: str) -> Tuple[str, List[str]]:
        """
        检查文本重复，返回过滤后的文本和警告
        """
        warnings = []
        
        # 1. 检查高频模板词
        for phrase in self._template_phrases:
            if phrase in text:
                usage = self._phrase_usage[phrase]
                if usage >= self._max_phrase_usage:
                    # 替换为更通用的表达
                    replacements = {
                        "指尖微凉": "心中有所触动",
                        "喉结滚动": "神色微变",
                        "深吸一口气": "调整了一下状态",
                        "心跳加速": "有些紧张",
                        "手心出汗": "感到压力",
                        "眉头紧锁": "陷入思考",
                        "目光闪烁": "若有所思",
                        "嘴角微扬": "神色缓和",
                        "攥着": "拿着",
                    }
                    replacement = replacements.get(phrase, "")
                    if replacement:
                        text = text.replace(phrase, replacement)
                        warnings.append(f"替换高频词 '{phrase}' -> '{replacement}'")
                else:
                    self._phrase_usage[phrase] += 1
        
        # 2. 检查与最近文本的相似度
        for recent in self._recent_phrases[-10:]:
            similarity = self._calculate_similarity(text, recent)
            if similarity > 0.65:  # 65%相似度
                warnings.append(f"文本相似度过高 ({similarity:.0%})")
                # 可以选择返回空字符串表示需要重新生成
                break
        
        # 记录当前文本
        self._recent_phrases.append(text)
        if len(self._recent_phrases) > 50:
            self._recent_phrases = self._recent_phrases[-50:]
        
        return (text, warnings)
    
    def _calculate_similarity(self, text1: str, text2: str) -> float:
        """计算两段文本的相似度"""
        if not text1 or not text2:
            return 0.0
        
        # 简单的词重叠率
        words1 = set(text1)
        words2 = set(text2)
        
        if not words1 or not words2:
            return 0.0
        
        intersection = words1 & words2
        union = words1 | words2
        
        return len(intersection) / len(union)
    
    def advance_round(self):
        """推进回合"""
        self._current_round += 1
        
        # 减少冷却
        if self._scene_cooldown > 0:
            self._scene_cooldown -= 1
        if self._weather_cooldown > 0:
            self._weather_cooldown -= 1
        
        # 推进时间
        self.state.time_of_day += 1
        if self.state.time_of_day >= 24:
            self.state.time_of_day = 0
            self.state.day_count += 1
    
    def update_scene(self, scene: str):
        """更新场景"""
        if scene != self.state.current_scene:
            self.state.previous_scene = self.state.current_scene
            self.state.current_scene = scene
            self.state.recent_scenes.append(scene)
            if len(self.state.recent_scenes) > 20:
                self.state.recent_scenes = self.state.recent_scenes[-20:]
    
    def update_weather(self, weather: str):
        """更新天气"""
        if weather != self.state.weather:
            self.state.weather = weather
            self.state.recent_weathers.append(weather)
            if len(self.state.recent_weathers) > 20:
                self.state.recent_weathers = self.state.recent_weathers[-20:]
    
    def get_time_description(self) -> str:
        """获取时间描述"""
        hour = self.state.time_of_day
        if 5 <= hour < 8:
            return "清晨"
        elif 8 <= hour < 12:
            return "上午"
        elif 12 <= hour < 14:
            return "中午"
        elif 14 <= hour < 18:
            return "下午"
        elif 18 <= hour < 20:
            return "傍晚"
        elif 20 <= hour < 23:
            return "晚上"
        else:
            return "深夜"
    
    def get_state_summary(self) -> str:
        """获取状态摘要"""
        return f"[第{self.state.day_count}天 {self.get_time_description()}] 场景:{self.state.current_scene} 天气:{self.state.weather}"


# 单例
_manager_instance = None

def get_consistency_manager(theme: str = "日常") -> GlobalConsistencyManager:
    global _manager_instance
    if _manager_instance is None:
        _manager_instance = GlobalConsistencyManager(theme)
    return _manager_instance
