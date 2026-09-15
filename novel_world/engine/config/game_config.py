# -*- coding: utf-8 -*-
"""
游戏配置模板 - 支持所有主题的通用设定
包含：主题设定、角色设定、世界设定、规则设定、剧情设定、道具设定
"""
from dataclasses import dataclass, field
from typing import List, Dict, Optional
from enum import Enum


class ThemeType(Enum):
    """主题类型"""
    DAILY = "日常"
    CULTIVATION = "修仙"
    FANTASY = "奇幻"
    APOCALYPSE = "末世"
    SCIFI = "科幻"
    HORROR = "恐怖"
    MYTHOLOGY = "神话"
    CUSTOM = "自定义"


@dataclass
class ThemeSetting:
    """主题设定"""
    name: str = "日常"  # 主题名称
    style: str = "温馨治愈"  # 主题风格
    core_conflict: str = ""  # 核心冲突
    core_law: str = ""  # 主题核心法则
    
    def to_dict(self) -> Dict:
        return {
            "name": self.name,
            "style": self.style,
            "core_conflict": self.core_conflict,
            "core_law": self.core_law,
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'ThemeSetting':
        return cls(
            name=data.get("name", "日常"),
            style=data.get("style", "温馨治愈"),
            core_conflict=data.get("core_conflict", ""),
            core_law=data.get("core_law", ""),
        )


@dataclass
class CharacterSetting:
    """角色设定"""
    name: str = ""
    char_type: str = "主角"  # 主角/反派/NPC
    personality: str = ""  # 性格
    goal: str = ""  # 目标
    fate_arc: str = ""  # 命运弧线
    special_ability: str = "无"  # 特殊能力
    motivation: str = ""  # 动机（反派用）
    methods: str = ""  # 手段（反派用）
    role_position: str = ""  # 角色定位（NPC用）
    relationship: str = "中立"  # 与主角关系（NPC用）
    secret: str = ""  # 关键秘密（NPC用）
    
    def to_dict(self) -> Dict:
        return {
            "name": self.name,
            "char_type": self.char_type,
            "personality": self.personality,
            "goal": self.goal,
            "fate_arc": self.fate_arc,
            "special_ability": self.special_ability,
            "motivation": self.motivation,
            "methods": self.methods,
            "role_position": self.role_position,
            "relationship": self.relationship,
            "secret": self.secret,
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'CharacterSetting':
        return cls(
            name=data.get("name", ""),
            char_type=data.get("char_type", "主角"),
            personality=data.get("personality", ""),
            goal=data.get("goal", ""),
            fate_arc=data.get("fate_arc", ""),
            special_ability=data.get("special_ability", "无"),
            motivation=data.get("motivation", ""),
            methods=data.get("methods", ""),
            role_position=data.get("role_position", ""),
            relationship=data.get("relationship", "中立"),
            secret=data.get("secret", ""),
        )


@dataclass
class WorldSetting:
    """世界设定"""
    name: str = ""
    era: str = ""  # 时代背景
    geography: str = ""  # 地理结构
    core_rules: str = ""  # 核心规则
    taboos: str = ""  # 禁忌
    special_scenes: str = ""  # 主题专属场景
    
    def to_dict(self) -> Dict:
        return {
            "name": self.name,
            "era": self.era,
            "geography": self.geography,
            "core_rules": self.core_rules,
            "taboos": self.taboos,
            "special_scenes": self.special_scenes,
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'WorldSetting':
        return cls(
            name=data.get("name", ""),
            era=data.get("era", ""),
            geography=data.get("geography", ""),
            core_rules=data.get("core_rules", ""),
            taboos=data.get("taboos", ""),
            special_scenes=data.get("special_scenes", ""),
        )


@dataclass
class RuleSetting:
    """规则设定"""
    allowed: List[str] = field(default_factory=list)  # 允许的行为
    forbidden: List[str] = field(default_factory=list)  # 禁止的行为
    iron_rules: List[str] = field(default_factory=list)  # 铁律
    special_rules: List[str] = field(default_factory=list)  # 主题特殊规则
    
    def to_dict(self) -> Dict:
        return {
            "allowed": self.allowed,
            "forbidden": self.forbidden,
            "iron_rules": self.iron_rules,
            "special_rules": self.special_rules,
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'RuleSetting':
        return cls(
            allowed=data.get("allowed", []),
            forbidden=data.get("forbidden", []),
            iron_rules=data.get("iron_rules", []),
            special_rules=data.get("special_rules", []),
        )


@dataclass
class SubplotSetting:
    """支线剧情设定"""
    name: str = ""  # 支线名称
    trigger_condition: str = ""  # 触发条件
    key_characters: str = ""  # 关键角色
    reward_consequence: str = ""  # 奖励/后果
    description: str = ""  # 支线描述
    
    def to_dict(self) -> Dict:
        return {
            "name": self.name,
            "trigger_condition": self.trigger_condition,
            "key_characters": self.key_characters,
            "reward_consequence": self.reward_consequence,
            "description": self.description,
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'SubplotSetting':
        return cls(
            name=data.get("name", ""),
            trigger_condition=data.get("trigger_condition", ""),
            key_characters=data.get("key_characters", ""),
            reward_consequence=data.get("reward_consequence", ""),
            description=data.get("description", ""),
        )


@dataclass
class PlotSetting:
    """剧情设定"""
    # 主线
    start_event: str = ""  # 起点事件
    core_suspense: str = ""  # 核心悬念
    expected_ending: str = ""  # 预期结局
    # 支线（保留旧字段以兼容）
    trigger_condition: str = ""  # 触发条件
    key_characters: str = ""  # 关键角色
    reward_consequence: str = ""  # 奖励/后果
    # 多支线支持
    subplots: List['SubplotSetting'] = field(default_factory=list)
    
    def to_dict(self) -> Dict:
        return {
            "start_event": self.start_event,
            "core_suspense": self.core_suspense,
            "expected_ending": self.expected_ending,
            "trigger_condition": self.trigger_condition,
            "key_characters": self.key_characters,
            "reward_consequence": self.reward_consequence,
            "subplots": [sp.to_dict() for sp in self.subplots],
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'PlotSetting':
        return cls(
            start_event=data.get("start_event", ""),
            core_suspense=data.get("core_suspense", ""),
            expected_ending=data.get("expected_ending", ""),
            trigger_condition=data.get("trigger_condition", ""),
            key_characters=data.get("key_characters", ""),
            reward_consequence=data.get("reward_consequence", ""),
            subplots=[SubplotSetting.from_dict(sp) for sp in data.get("subplots", [])],
        )


@dataclass
class ItemSetting:
    """道具设定"""
    name: str = ""
    appearance: str = ""  # 外观描述
    acquisition: str = ""  # 获取方式
    effect: str = ""  # 固定效果
    usage_limit: str = ""  # 使用限制
    plot_significance: str = ""  # 剧情意义
    
    def to_dict(self) -> Dict:
        return {
            "name": self.name,
            "appearance": self.appearance,
            "acquisition": self.acquisition,
            "effect": self.effect,
            "usage_limit": self.usage_limit,
            "plot_significance": self.plot_significance,
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'ItemSetting':
        return cls(
            name=data.get("name", ""),
            appearance=data.get("appearance", ""),
            acquisition=data.get("acquisition", ""),
            effect=data.get("effect", ""),
            usage_limit=data.get("usage_limit", ""),
            plot_significance=data.get("plot_significance", ""),
        )


@dataclass
class GameConfig:
    """游戏配置 - 包含所有设定"""
    theme: ThemeSetting = field(default_factory=ThemeSetting)
    protagonist: CharacterSetting = field(default_factory=CharacterSetting)
    heroine: CharacterSetting = field(default_factory=CharacterSetting)  # 新增：女主角设定
    antagonist: CharacterSetting = field(default_factory=CharacterSetting)
    npcs: List[CharacterSetting] = field(default_factory=list)
    world: WorldSetting = field(default_factory=WorldSetting)
    rules: RuleSetting = field(default_factory=RuleSetting)
    plot: PlotSetting = field(default_factory=PlotSetting)
    items: List[ItemSetting] = field(default_factory=list)
    
    def to_dict(self) -> Dict:
        return {
            "theme": self.theme.to_dict(),
            "protagonist": self.protagonist.to_dict(),
            "heroine": self.heroine.to_dict(),  # 新增
            "antagonist": self.antagonist.to_dict(),
            "npcs": [npc.to_dict() for npc in self.npcs],
            "world": self.world.to_dict(),
            "rules": self.rules.to_dict(),
            "plot": self.plot.to_dict(),
            "items": [item.to_dict() for item in self.items],
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'GameConfig':
        return cls(
            theme=ThemeSetting.from_dict(data.get("theme", {})),
            protagonist=CharacterSetting.from_dict(data.get("protagonist", {})),
            heroine=CharacterSetting.from_dict(data.get("heroine", {})),  # 新增
            antagonist=CharacterSetting.from_dict(data.get("antagonist", {})),
            npcs=[CharacterSetting.from_dict(npc) for npc in data.get("npcs", [])],
            world=WorldSetting.from_dict(data.get("world", {})),
            rules=RuleSetting.from_dict(data.get("rules", {})),
            plot=PlotSetting.from_dict(data.get("plot", {})),
            items=[ItemSetting.from_dict(item) for item in data.get("items", [])],
        )
    
    def save(self, filepath: str):
        """保存配置到文件"""
        import json
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(self.to_dict(), f, ensure_ascii=False, indent=2)
    
    @classmethod
    def load(cls, filepath: str) -> 'GameConfig':
        """从文件加载配置"""
        import json
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return cls.from_dict(data)


# 预设模板 - 各主题的默认配置（不自动加载任何模板，由用户手动选择）
PRESET_TEMPLATES = {
    "日常": GameConfig(
        theme=ThemeSetting(name="日常", style="温馨治愈", core_conflict="人际关系", core_law="现实逻辑"),
    ),
    "修仙": GameConfig(
        theme=ThemeSetting(
            name="修仙",
            style="热血玄幻",
            core_conflict="凡人vs天道，修炼突破",
            core_law="灵气为修炼之本，境界决定实力",
        ),
        world=WorldSetting(
            name="修仙世界",
            era="架空古代",
            geography="五大宗门/三大禁地/灵脉福地",
            core_rules="灵气可修炼，等级决定实力",
            taboos="不可逆天行事，不可私藏邪功",
            special_scenes="炼丹房/剑冢/宗门大殿/秘境",
        ),
        rules=RuleSetting(
            allowed=["修炼突破", "炼丹炼器", "宗门争斗", "探索秘境"],
            forbidden=["现代科技", "枪械火炮"],
            iron_rules=["境界体系：炼气-筑基-金丹-元婴-化神", "灵气为修炼之本"],
            special_rules=["灵气耗尽会修为大跌", "渡劫失败会身死道消"],
        ),
    ),
    "末世": GameConfig(
        theme=ThemeSetting(
            name="末世",
            style="黑暗压抑",
            core_conflict="生存vs人性",
            core_law="资源稀缺，弱肉强食",
        ),
        world=WorldSetting(
            name="末世废土",
            era="末世废土",
            geography="安全区/丧尸区/废弃城市/资源点",
            core_rules="丧尸不可治愈，咬伤即感染",
            taboos="不可背叛队友，不可销毁生存物资",
            special_scenes="物资仓库/防御工事/安全区/废墟",
        ),
        rules=RuleSetting(
            allowed=["组队求生", "搭建防御", "收集物资", "探索废墟"],
            forbidden=["滥用资源", "背叛队友"],
            iron_rules=["死亡不可逆转", "资源有限"],
            special_rules=["深夜有高阶丧尸出没", "感染后无法治愈"],
        ),
    ),
    "科幻": GameConfig(
        theme=ThemeSetting(
            name="科幻",
            style="冰冷科幻",
            core_conflict="人类vs未知，科技vs伦理",
            core_law="科技至上，星际航行可行",
        ),
        world=WorldSetting(
            name="星际世界",
            era="星际时代",
            geography="星际空间站/殖民星球/废弃星球/虫洞",
            core_rules="科技至上，人工智能可自主思考",
            taboos="不可滥用时空技术，不可伤害无辜",
            special_scenes="星际港口/实验室/飞船/控制中心",
        ),
        rules=RuleSetting(
            allowed=["研发科技", "星际航行", "探索未知", "改造机械"],
            forbidden=["滥用时空技术", "无意义杀戮"],
            iron_rules=["科技是核心力量", "星际航行需资源"],
            special_rules=["陨石带危险", "能量有限"],
        ),
    ),
    "恐怖": GameConfig(
        theme=ThemeSetting(
            name="恐怖",
            style="悬疑惊悚",
            core_conflict="人类vs超自然",
            core_law="超自然现象可干预现实",
        ),
        world=WorldSetting(
            name="灵异世界",
            era="现代/架空",
            geography="废弃建筑/灵异地点/禁忌区域",
            core_rules="超自然存在可干预现实",
            taboos="不可主动唤醒邪物，不可触碰禁忌",
            special_scenes="废弃医院/老宅/墓地/镜子前",
        ),
        rules=RuleSetting(
            allowed=["寻找线索", "驱邪", "组队探索", "使用道具"],
            forbidden=["主动唤醒邪物", "独自深入"],
            iron_rules=["超自然存在真实", "死亡不可逆转"],
            special_rules=["午夜照镜危险", "某些物品可驱邪"],
        ),
    ),
}
