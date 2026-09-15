# -*- coding: utf-8 -*-
"""
场景动态变化器 - 解决场景设定重复问题
提供场景细节差异化的渲染接口，支持：
- 光线变化（晨光、午阳、暮色、夜光）
- 天气动态（晴、阴、雨、雪、雾）
- 氛围变化（热闹、冷清、温馨、紧张）
- 细节物件互动（场景中的小物件、NPC活动）
"""
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum
import random
from collections import defaultdict


class LightCondition(Enum):
    """光线条件"""
    DAWN = "晨光熹微"
    MORNING = "朝阳初升"
    NOON = "正午阳光"
    AFTERNOON = "午后斜阳"
    DUSK = "暮色苍茫"
    EVENING = "华灯初上"
    NIGHT = "夜色深沉"
    MIDNIGHT = "月明星稀"


class WeatherCondition(Enum):
    """天气条件"""
    SUNNY = "晴空万里"
    CLOUDY = "云层低垂"
    OVERCAST = "阴云密布"
    LIGHT_RAIN = "细雨绵绵"
    HEAVY_RAIN = "大雨倾盆"
    SNOW = "雪花飘落"
    FOG = "雾气弥漫"
    WINDY = "狂风呼啸"


class AtmosphereType(Enum):
    """氛围类型"""
    LIVELY = "热闹非凡"
    QUIET = "安静祥和"
    COLD = "冷清萧瑟"
    WARM = "温馨舒适"
    TENSE = "紧张压抑"
    MYSTERIOUS = "神秘莫测"
    CHEERFUL = "欢快轻松"
    MELANCHOLY = "忧伤低沉"


@dataclass
class SceneDetailElement:
    """场景细节元素"""
    name: str  # 元素名称
    description: str  # 描述
    interactions: List[str]  # 可交互动作
    visibility_weight: float = 1.0  # 可见权重（影响出现频率）


@dataclass
class DynamicSceneState:
    """动态场景状态"""
    scene_name: str
    light: LightCondition = LightCondition.NOON
    weather: WeatherCondition = WeatherCondition.SUNNY
    atmosphere: AtmosphereType = AtmosphereType.QUIET
    active_elements: List[SceneDetailElement] = field(default_factory=list)
    npc_activities: List[str] = field(default_factory=list)
    time_last_updated: int = 0  # 上次更新的时间点
    visit_count: int = 0  # 访问次数


class SceneVariator:
    """场景动态变化器"""
    
    def __init__(self):
        self._scene_states: Dict[str, DynamicSceneState] = {}
        self._element_pool: Dict[str, List[SceneDetailElement]] = {}
        self._npc_activity_pool: Dict[str, List[str]] = {}
        self._used_combinations: Dict[str, int] = defaultdict(int)  # 已使用的组合
        self._max_same_combination = 2  # 同一组合最大重复次数
        
        self._initialize_element_pool()
        self._initialize_npc_activities()
    
    def _initialize_element_pool(self):
        """初始化场景元素池"""
        
        # 市场场景元素
        self._element_pool["市场"] = [
            SceneDetailElement("摊位", "琳琅满目的商品摊位", ["驻足观看", "询问价格", "挑选商品"]),
            SceneDetailElement("叫卖声", "商贩的吆喝声此起彼伏", ["倾听", "循声而去"]),
            SceneDetailElement("人群", "熙熙攘攘的人群", ["穿行", "避让", "跟随"]),
            SceneDetailElement("香气", "各种食物的香气飘散", ["闻香", "寻找来源"]),
            SceneDetailElement("货物", "堆积如山的货物", ["翻看", "比较", "议价"]),
            SceneDetailElement("招牌", "各式各样的店铺招牌", ["抬头看", "辨认文字"]),
            SceneDetailElement("小孩", "在人群中穿梭的小孩", ["观察", "微笑"]),
            SceneDetailElement("老者", "坐在角落的老者", ["攀谈", "请教"]),
        ]
        
        # 街道场景元素
        self._element_pool["街道"] = [
            SceneDetailElement("路灯", "昏黄的路灯", ["仰望", "数数"]),
            SceneDetailElement("落叶", "飘落的树叶", ["踩踏", "拾起", "观察"]),
            SceneDetailElement("行人", "匆匆路过的行人", ["打招呼", "观察", "避让"]),
            SceneDetailElement("店铺", "沿街的店铺", ["进入", "张望", "驻足"]),
            SceneDetailElement("流浪猫", "角落里的流浪猫", ["靠近", "喂食", "观察"]),
            SceneDetailElement("自行车", "停靠的自行车", ["观察", "绕过"]),
            SceneDetailElement("广告牌", "斑驳的广告牌", ["阅读", "忽略"]),
            SceneDetailElement("水坑", "路面的积水", ["跳过", "绕行", "踩水"]),
        ]
        
        # 酒馆/茶馆场景元素
        self._element_pool["酒馆"] = self._element_pool["茶馆"] = [
            SceneDetailElement("酒客", "三三两两的酒客", ["攀谈", "观察", "加入"]),
            SceneDetailElement("酒香", "浓郁的酒香", ["闻香", "品味"]),
            SceneDetailElement("烛光", "摇曳的烛光", ["注视", "借光"]),
            SceneDetailElement("琴声", "若有若无的琴声", ["倾听", "寻声"]),
            SceneDetailElement("酒保", "忙碌的酒保", ["招手", "点单", "询问"]),
            SceneDetailElement("角落", "安静的角落座位", ["选择", "观察"]),
            SceneDetailElement("招牌酒", "柜台的招牌酒", ["询问", "品尝"]),
            SceneDetailElement("故事", "酒客们的故事", ["倾听", "分享"]),
        ]
        
        # 森林场景元素
        self._element_pool["森林"] = [
            SceneDetailElement("古树", "参天古树", ["仰望", "抚摸", "依靠"]),
            SceneDetailElement("鸟鸣", "清脆的鸟鸣", ["倾听", "寻找"]),
            SceneDetailElement("落叶", "厚厚的落叶层", ["踩踏", "翻找"]),
            SceneDetailElement("溪流", "潺潺溪流", ["靠近", "饮水", "洗脸"]),
            SceneDetailElement("野兽", "远处的野兽身影", ["观察", "追踪", "避开"]),
            SceneDetailElement("蘑菇", "树下的蘑菇", ["采摘", "辨认", "观察"]),
            SceneDetailElement("藤蔓", "垂落的藤蔓", ["拨开", "攀爬"]),
            SceneDetailElement("阳光", "透过树叶的阳光", ["沐浴", "观察"]),
        ]
        
        # 室内场景元素
        self._element_pool["室内"] = [
            SceneDetailElement("家具", "陈旧的家具", ["观察", "使用", "擦拭"]),
            SceneDetailElement("窗户", "半开的窗户", ["推窗", "眺望", "关闭"]),
            SceneDetailElement("书籍", "书架上的书籍", ["翻阅", "取书", "放回"]),
            SceneDetailElement("茶具", "精致的茶具", ["泡茶", "品茶", "清洗"]),
            SceneDetailElement("画像", "墙上的画像", ["注视", "询问"]),
            SceneDetailElement("香炉", "袅袅香烟", ["闻香", "添加香料"]),
            SceneDetailElement("地毯", "柔软的地毯", ["踩踏", "坐下"]),
            SceneDetailElement("花瓶", "插着鲜花的花瓶", ["欣赏", "更换"]),
        ]
        
        # 战斗场景元素
        self._element_pool["战场"] = [
            SceneDetailElement("残骸", "战斗留下的残骸", ["检查", "翻找", "避开"]),
            SceneDetailElement("血迹", "地上的血迹", ["辨认", "追踪", "忽略"]),
            SceneDetailElement("兵器", "散落的兵器", ["拾起", "检查", "使用"]),
            SceneDetailElement("烟尘", "弥漫的烟尘", ["穿过", "等待散去"]),
            SceneDetailElement("喊杀声", "远处的喊杀声", ["倾听", "判断方向"]),
            SceneDetailElement("旗帜", "倒下的旗帜", ["辨认", "扶起"]),
            SceneDetailElement("伤员", "呻吟的伤员", ["救助", "询问", "忽略"]),
            SceneDetailElement("陷阱", "隐蔽的陷阱", ["发现", "避开", "利用"]),
        ]
    
    def _initialize_npc_activities(self):
        """初始化NPC活动池"""
        
        self._npc_activity_pool["市场"] = [
            "商贩正在热情地推销商品",
            "一位老妇人在挑选蔬菜",
            "几个孩子追逐嬉戏",
            "有人在与商贩讨价还价",
            "一个书生模样的年轻人在书摊前驻足",
            "几个江湖客在角落低声交谈",
        ]
        
        self._npc_activity_pool["街道"] = [
            "路人匆匆而过",
            "有人在街边闲聊",
            "一个小贩推着车经过",
            "几个孩童在玩耍",
            "一位老者坐在门前晒太阳",
            "巡逻的卫兵走过",
        ]
        
        self._npc_activity_pool["酒馆"] = self._npc_activity_pool["茶馆"] = [
            "酒客们举杯畅饮",
            "有人在角落独自饮酒",
            "几个江湖人在谈论最近的传闻",
            "说书人正在讲故事",
            "有人在弹奏乐器",
            "两个客人正在划拳",
        ]
        
        self._npc_activity_pool["森林"] = [
            "远处传来野兽的嚎叫",
            "一只鹿从眼前窜过",
            "鸟群惊起飞向天空",
            "松鼠在树枝间跳跃",
            "猎人留下的足迹依稀可见",
        ]
        
        self._npc_activity_pool["战场"] = [
            "远处仍有战斗的声音",
            "有人在搜寻幸存者",
            "几只秃鹫在空中盘旋",
            "伤者在低声呻吟",
            "有人在打扫战场",
        ]
    
    def get_or_create_scene_state(self, scene_name: str, current_time: int = 0) -> DynamicSceneState:
        """获取或创建场景状态"""
        if scene_name not in self._scene_states:
            self._scene_states[scene_name] = DynamicSceneState(
                scene_name=scene_name,
                time_last_updated=current_time
            )
        return self._scene_states[scene_name]
    
    def update_scene_conditions(self, scene_name: str, current_time: int = 0,
                                force_light: LightCondition = None,
                                force_weather: WeatherCondition = None,
                                force_atmosphere: AtmosphereType = None) -> DynamicSceneState:
        """
        更新场景条件（光线、天气、氛围）
        每次访问都会产生变化，避免重复
        """
        state = self.get_or_create_scene_state(scene_name, current_time)
        state.visit_count += 1
        
        # 根据时间推断光线条件
        if force_light:
            state.light = force_light
        else:
            state.light = self._infer_light_from_time(current_time)
        
        # 随机变化天气（有一定概率保持不变）
        if force_weather:
            state.weather = force_weather
        elif random.random() < 0.3:  # 30%概率变化天气
            state.weather = random.choice(list(WeatherCondition))
        
        # 根据场景和访问次数调整氛围
        if force_atmosphere:
            state.atmosphere = force_atmosphere
        else:
            state.atmosphere = self._infer_atmosphere(scene_name, state.visit_count)
        
        state.time_last_updated = current_time
        return state
    
    def _infer_light_from_time(self, time_val: int) -> LightCondition:
        """根据时间推断光线条件"""
        hour = time_val % 24
        if 5 <= hour < 7:
            return LightCondition.DAWN
        elif 7 <= hour < 10:
            return LightCondition.MORNING
        elif 10 <= hour < 14:
            return LightCondition.NOON
        elif 14 <= hour < 17:
            return LightCondition.AFTERNOON
        elif 17 <= hour < 19:
            return LightCondition.DUSK
        elif 19 <= hour < 22:
            return LightCondition.EVENING
        elif 22 <= hour < 24 or 0 <= hour < 2:
            return LightCondition.NIGHT
        else:
            return LightCondition.MIDNIGHT
    
    def _infer_atmosphere(self, scene_name: str, visit_count: int) -> AtmosphereType:
        """根据场景和访问次数推断氛围"""
        # 不同场景的默认氛围
        scene_atmospheres = {
            "市场": [AtmosphereType.LIVELY, AtmosphereType.CHEERFUL, AtmosphereType.QUIET],
            "街道": [AtmosphereType.QUIET, AtmosphereType.LIVELY, AtmosphereType.COLD],
            "酒馆": [AtmosphereType.WARM, AtmosphereType.LIVELY, AtmosphereType.MYSTERIOUS],
            "茶馆": [AtmosphereType.QUIET, AtmosphereType.WARM, AtmosphereType.CHEERFUL],
            "森林": [AtmosphereType.QUIET, AtmosphereType.MYSTERIOUS, AtmosphereType.COLD],
            "战场": [AtmosphereType.TENSE, AtmosphereType.COLD, AtmosphereType.QUIET],
            "室内": [AtmosphereType.WARM, AtmosphereType.QUIET, AtmosphereType.TENSE],
        }
        
        options = scene_atmospheres.get(scene_name, [AtmosphereType.QUIET])
        # 根据访问次数轮换氛围
        return options[visit_count % len(options)]
    
    def get_scene_elements(self, scene_name: str, count: int = 3) -> List[SceneDetailElement]:
        """获取场景细节元素（避免重复组合）"""
        pool = self._element_pool.get(scene_name, self._element_pool.get("室内", []))
        
        if not pool:
            return []
        
        # 尝试找到未重复的组合
        max_attempts = 10
        for _ in range(max_attempts):
            selected = random.sample(pool, min(count, len(pool)))
            combo_key = scene_name + "|" + "|".join(e.name for e in selected)
            
            if self._used_combinations[combo_key] < self._max_same_combination:
                self._used_combinations[combo_key] += 1
                return selected
        
        # 如果所有组合都用过了，返回随机选择并重置计数
        return random.sample(pool, min(count, len(pool)))
    
    def get_npc_activities(self, scene_name: str, count: int = 2) -> List[str]:
        """获取NPC活动描述"""
        pool = self._npc_activity_pool.get(scene_name, [])
        
        if not pool:
            return []
        
        return random.sample(pool, min(count, len(pool)))
    
    def generate_scene_description(self, scene_name: str, current_time: int = 0,
                                   include_elements: bool = True,
                                   include_npc: bool = True) -> str:
        """
        生成完整的场景描述
        包含：光线 + 天气 + 氛围 + 细节元素 + NPC活动
        """
        state = self.update_scene_conditions(scene_name, current_time)
        
        # 基础描述
        parts = []
        
        # 光线和天气
        parts.append(f"{state.light.value}，{state.weather.value}")
        
        # 氛围
        parts.append(f"四周{state.atmosphere.value}")
        
        # 细节元素
        if include_elements:
            elements = self.get_scene_elements(scene_name)
            if elements:
                elem_desc = random.choice(elements[0].interactions)
                parts.append(f"{elements[0].description}，可以{elem_desc}")
        
        # NPC活动
        if include_npc:
            activities = self.get_npc_activities(scene_name, 1)
            if activities:
                parts.append(activities[0])
        
        return "。".join(parts) + "。"
    
    def get_element_interaction(self, scene_name: str, element_name: str = None) -> Optional[Tuple[str, str]]:
        """获取元素交互动作，返回 (元素名, 动作)"""
        pool = self._element_pool.get(scene_name, [])
        
        if not pool:
            return None
        
        if element_name:
            for elem in pool:
                if elem.name == element_name and elem.interactions:
                    return (elem.name, random.choice(elem.interactions))
        else:
            elem = random.choice(pool)
            if elem.interactions:
                return (elem.name, random.choice(elem.interactions))
        
        return None
    
    def reset_scene(self, scene_name: str):
        """重置场景状态"""
        if scene_name in self._scene_states:
            del self._scene_states[scene_name]
    
    def reset_all(self):
        """重置所有场景状态"""
        self._scene_states.clear()
        self._used_combinations.clear()


# 单例模式
_scene_variator_instance = None

def get_scene_variator() -> SceneVariator:
    """获取场景变化器单例"""
    global _scene_variator_instance
    if _scene_variator_instance is None:
        _scene_variator_instance = SceneVariator()
    return _scene_variator_instance

