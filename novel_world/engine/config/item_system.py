# -*- coding: utf-8 -*-
"""
道具系统 - 道具定义、管理、使用、校验
规则6：道具使用必须有代价、有规则、有效果
"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Callable, Any
from enum import Enum
import random


class ItemType(Enum):
    """道具类型"""
    CONSUMABLE = "消耗品"      # 使用后消失
    EQUIPMENT = "装备"         # 可装备
    KEY_ITEM = "关键道具"      # 任务道具，不可丢弃
    MATERIAL = "材料"          # 制作材料
    BOOK = "书籍"              # 可阅读
    TOOL = "工具"              # 可重复使用


class ItemRarity(Enum):
    """道具稀有度"""
    COMMON = "普通"
    UNCOMMON = "稀有"
    RARE = "精良"
    EPIC = "史诗"
    LEGENDARY = "传说"


@dataclass
class ItemCost:
    """道具使用代价"""
    hp: int = 0                    # 消耗生命值
    mp: int = 0                    # 消耗魔力值
    stamina: int = 0               # 消耗体力
    gold: int = 0                  # 消耗金币
    consume_self: bool = True      # 是否消耗道具本身
    cooldown: int = 0              # 冷却时间（回合）


@dataclass
class ItemEffect:
    """道具效果"""
    hp_restore: int = 0            # 恢复生命值
    mp_restore: int = 0            # 恢复魔力值
    stamina_restore: int = 0       # 恢复体力
    buff_attack: int = 0           # 攻击力加成
    buff_defense: int = 0          # 防御力加成
    buff_speed: int = 0            # 速度加成
    buff_duration: int = 0         # 加成持续时间
    special_effect: str = ""       # 特殊效果描述
    teleport_to: str = ""          # 传送到指定地点
    damage: int = 0                # 造成伤害（投掷类道具）


@dataclass
class ItemRule:
    """道具使用规则"""
    allowed_scenes: List[str] = field(default_factory=list)    # 允许使用的场景
    forbidden_scenes: List[str] = field(default_factory=list)  # 禁止使用的场景
    requires_target: bool = False                              # 是否需要目标
    requires_combat: bool = False                               # 是否需要战斗中
    requires_peace: bool = False                                # 是否需要非战斗
    min_level: int = 0                                          # 最低等级要求
    required_skills: List[str] = field(default_factory=list)   # 需要的技能
    forbidden_if: List[str] = field(default_factory=list)      # 禁止条件


@dataclass
class Item:
    """道具定义"""
    id: str
    name: str
    item_type: ItemType
    description: str
    rarity: ItemRarity = ItemRarity.COMMON
    cost: ItemCost = field(default_factory=ItemCost)
    effect: ItemEffect = field(default_factory=ItemEffect)
    rule: ItemRule = field(default_factory=ItemRule)
    stackable: bool = True           # 是否可堆叠
    max_stack: int = 99              # 最大堆叠数
    value: int = 0                   # 价值（金币）
    weight: float = 0.0              # 重量
    
    def can_use(self, context: dict) -> tuple:
        """
        检查是否可以使用
        返回: (can_use: bool, reason: str)
        """
        # 检查场景
        current_scene = context.get("scene", "")
        if self.rule.allowed_scenes and current_scene not in self.rule.allowed_scenes:
            return (False, f"道具 {self.name} 不能在 {current_scene} 使用")
        if current_scene in self.rule.forbidden_scenes:
            return (False, f"道具 {self.name} 禁止在 {current_scene} 使用")
        
        # 检查战斗状态
        in_combat = context.get("in_combat", False)
        if self.rule.requires_combat and not in_combat:
            return (False, f"道具 {self.name} 只能在战斗中使用")
        if self.rule.requires_peace and in_combat:
            return (False, f"道具 {self.name} 不能在战斗中使用")
        
        # 检查等级
        user_level = context.get("level", 1)
        if user_level < self.rule.min_level:
            return (False, f"使用 {self.name} 需要等级 {self.rule.min_level}")
        
        # 检查技能
        user_skills = context.get("skills", [])
        for skill in self.rule.required_skills:
            if skill not in user_skills:
                return (False, f"使用 {self.name} 需要技能: {skill}")
        
        # 检查代价是否足够
        hp = context.get("hp", 0)
        mp = context.get("mp", 0)
        stamina = context.get("stamina", 0)
        gold = context.get("gold", 0)
        
        if self.cost.hp > 0 and hp < self.cost.hp:
            return (False, f"生命值不足，需要 {self.cost.hp}")
        if self.cost.mp > 0 and mp < self.cost.mp:
            return (False, f"魔力值不足，需要 {self.cost.mp}")
        if self.cost.stamina > 0 and stamina < self.cost.stamina:
            return (False, f"体力不足，需要 {self.cost.stamina}")
        if self.cost.gold > 0 and gold < self.cost.gold:
            return (False, f"金币不足，需要 {self.cost.gold}")
        
        return (True, "可以使用")
    
    def get_use_description(self) -> str:
        """获取使用描述"""
        parts = []
        
        # 代价
        cost_parts = []
        if self.cost.hp > 0:
            cost_parts.append(f"消耗{self.cost.hp}生命")
        if self.cost.mp > 0:
            cost_parts.append(f"消耗{self.cost.mp}魔力")
        if self.cost.stamina > 0:
            cost_parts.append(f"消耗{self.cost.stamina}体力")
        if self.cost.gold > 0:
            cost_parts.append(f"消耗{self.cost.gold}金币")
        if self.cost.consume_self and self.item_type == ItemType.CONSUMABLE:
            cost_parts.append("消耗道具")
        
        if cost_parts:
            parts.append("代价：" + "、".join(cost_parts))
        
        # 效果
        effect_parts = []
        if self.effect.hp_restore > 0:
            effect_parts.append(f"恢复{self.effect.hp_restore}生命")
        if self.effect.mp_restore > 0:
            effect_parts.append(f"恢复{self.effect.mp_restore}魔力")
        if self.effect.stamina_restore > 0:
            effect_parts.append(f"恢复{self.effect.stamina_restore}体力")
        if self.effect.buff_attack > 0:
            effect_parts.append(f"攻击+{self.effect.buff_attack}")
        if self.effect.buff_defense > 0:
            effect_parts.append(f"防御+{self.effect.buff_defense}")
        if self.effect.damage > 0:
            effect_parts.append(f"造成{self.effect.damage}伤害")
        if self.effect.special_effect:
            effect_parts.append(self.effect.special_effect)
        
        if effect_parts:
            parts.append("效果：" + "、".join(effect_parts))
        
        return "\n".join(parts)


class ItemManager:
    """道具管理器"""
    
    def __init__(self):
        self.items: Dict[str, Item] = {}        # 所有道具定义
        self._init_default_items()
    
    def _init_default_items(self):
        """初始化默认道具"""
        # 消耗品
        self.register_item(Item(
            id="health_potion",
            name="治疗药水",
            item_type=ItemType.CONSUMABLE,
            description="恢复30点生命值",
            rarity=ItemRarity.COMMON,
            cost=ItemCost(consume_self=True),
            effect=ItemEffect(hp_restore=30),
            value=50,
        ))
        
        self.register_item(Item(
            id="mana_potion",
            name="魔力药水",
            item_type=ItemType.CONSUMABLE,
            description="恢复20点魔力值",
            rarity=ItemRarity.COMMON,
            cost=ItemCost(consume_self=True),
            effect=ItemEffect(mp_restore=20),
            value=60,
        ))
        
        self.register_item(Item(
            id="stamina_potion",
            name="体力药水",
            item_type=ItemType.CONSUMABLE,
            description="恢复全部体力",
            rarity=ItemRarity.UNCOMMON,
            cost=ItemCost(consume_self=True),
            effect=ItemEffect(stamina_restore=100),
            value=80,
        ))
        
        self.register_item(Item(
            id="elixir",
            name="万能药",
            item_type=ItemType.CONSUMABLE,
            description="恢复全部生命和魔力",
            rarity=ItemRarity.RARE,
            cost=ItemCost(consume_self=True),
            effect=ItemEffect(hp_restore=999, mp_restore=999),
            value=300,
        ))
        
        # 战斗道具
        self.register_item(Item(
            id="bomb",
            name="炸弹",
            item_type=ItemType.CONSUMABLE,
            description="对敌人造成50点伤害",
            rarity=ItemRarity.UNCOMMON,
            cost=ItemCost(consume_self=True),
            effect=ItemEffect(damage=50),
            rule=ItemRule(requires_combat=True),
            value=100,
        ))
        
        self.register_item(Item(
            id="smoke_bomb",
            name="烟雾弹",
            item_type=ItemType.CONSUMABLE,
            description="逃离战斗",
            rarity=ItemRarity.COMMON,
            cost=ItemCost(consume_self=True),
            effect=ItemEffect(special_effect="逃离战斗"),
            rule=ItemRule(requires_combat=True),
            value=80,
        ))
        
        # 增益道具
        self.register_item(Item(
            id="attack_boost",
            name="力量药剂",
            item_type=ItemType.CONSUMABLE,
            description="攻击力提升20，持续3回合",
            rarity=ItemRarity.RARE,
            cost=ItemCost(consume_self=True),
            effect=ItemEffect(buff_attack=20, buff_duration=3),
            value=150,
        ))
        
        self.register_item(Item(
            id="defense_boost",
            name="护盾药剂",
            item_type=ItemType.CONSUMABLE,
            description="防御力提升30，持续3回合",
            rarity=ItemRarity.RARE,
            cost=ItemCost(consume_self=True),
            effect=ItemEffect(buff_defense=30, buff_duration=3),
            value=150,
        ))
        
        # 传送道具
        self.register_item(Item(
            id="teleport_scroll",
            name="传送卷轴",
            item_type=ItemType.CONSUMABLE,
            description="传送到已探索的地点",
            rarity=ItemRarity.UNCOMMON,
            cost=ItemCost(mp=10, consume_self=True),
            effect=ItemEffect(special_effect="传送"),
            rule=ItemRule(requires_peace=True),
            value=200,
        ))
        
        # 关键道具
        self.register_item(Item(
            id="mysterious_key",
            name="神秘钥匙",
            item_type=ItemType.KEY_ITEM,
            description="一把古老的钥匙，用途未知",
            rarity=ItemRarity.EPIC,
            stackable=False,
            value=0,
        ))
        
        self.register_item(Item(
            id="ancient_map",
            name="古老地图",
            item_type=ItemType.KEY_ITEM,
            description="标注了隐藏宝藏的位置",
            rarity=ItemRarity.RARE,
            stackable=False,
            value=0,
        ))
    
    def register_item(self, item: Item):
        """注册道具"""
        self.items[item.id] = item
    
    def get_item(self, item_id: str) -> Optional[Item]:
        """获取道具定义"""
        return self.items.get(item_id)
    
    def get_items_by_type(self, item_type: ItemType) -> List[Item]:
        """按类型获取道具"""
        return [item for item in self.items.values() if item.item_type == item_type]
    
    def get_items_by_rarity(self, rarity: ItemRarity) -> List[Item]:
        """按稀有度获取道具"""
        return [item for item in self.items.values() if item.rarity == rarity]


class ItemValidator:
    """道具规则校验器 - 规则6"""
    
    def validate_item_use(self, item: Item, context: dict) -> dict:
        """
        校验道具使用是否符合规则
        返回: {
            "can_use": bool,
            "reason": str,
            "cost_applied": bool,
            "effect_applied": bool,
            "violations": list
        }
        """
        violations = []
        
        # 1. 检查是否可以使用
        can_use, reason = item.can_use(context)
        if not can_use:
            violations.append(f"【规则6违规】{reason}")
            return {
                "can_use": False,
                "reason": reason,
                "cost_applied": False,
                "effect_applied": False,
                "violations": violations
            }
        
        # 2. 检查代价是否合理
        if item.cost.hp > 50:
            violations.append(f"【规则6警告】道具 {item.name} 生命代价过高: {item.cost.hp}")
        
        # 3. 检查效果是否存在
        has_effect = (
            item.effect.hp_restore > 0 or
            item.effect.mp_restore > 0 or
            item.effect.stamina_restore > 0 or
            item.effect.buff_attack > 0 or
            item.effect.buff_defense > 0 or
            item.effect.damage > 0 or
            item.effect.special_effect
        )
        
        if not has_effect:
            violations.append(f"【规则6违规】道具 {item.name} 没有任何效果")
            return {
                "can_use": False,
                "reason": "道具没有任何效果",
                "cost_applied": False,
                "effect_applied": False,
                "violations": violations
            }
        
        # 4. 检查代价和效果是否匹配
        total_cost = item.cost.hp + item.cost.mp + item.cost.stamina + item.cost.gold
        total_effect = item.effect.hp_restore + item.effect.mp_restore + item.effect.stamina_restore + item.effect.damage
        
        if total_cost > 0 and total_effect == 0 and not item.effect.special_effect:
            violations.append(f"【规则6警告】道具 {item.name} 有代价但无直接效果")
        
        return {
            "can_use": True,
            "reason": "可以使用",
            "cost_applied": False,
            "effect_applied": False,
            "violations": violations
        }
    
    def apply_item_cost(self, item: Item, character_stats: dict) -> dict:
        """
        应用道具代价
        返回: 更新后的角色属性
        """
        stats = character_stats.copy()
        
        stats["hp"] = stats.get("hp", 0) - item.cost.hp
        stats["mp"] = stats.get("mp", 0) - item.cost.mp
        stats["stamina"] = stats.get("stamina", 0) - item.cost.stamina
        stats["gold"] = stats.get("gold", 0) - item.cost.gold
        
        # 确保不低于0
        stats["hp"] = max(0, stats["hp"])
        stats["mp"] = max(0, stats["mp"])
        stats["stamina"] = max(0, stats["stamina"])
        stats["gold"] = max(0, stats["gold"])
        
        return stats
    
    def apply_item_effect(self, item: Item, character_stats: dict) -> dict:
        """
        应用道具效果
        返回: 更新后的角色属性
        """
        stats = character_stats.copy()
        
        stats["hp"] = stats.get("hp", 0) + item.effect.hp_restore
        stats["mp"] = stats.get("mp", 0) + item.effect.mp_restore
        stats["stamina"] = stats.get("stamina", 0) + item.effect.stamina_restore
        
        # 添加buff
        if item.effect.buff_attack > 0:
            buffs = stats.get("buffs", {})
            buffs["attack"] = {"value": item.effect.buff_attack, "duration": item.effect.buff_duration}
            stats["buffs"] = buffs
        
        if item.effect.buff_defense > 0:
            buffs = stats.get("buffs", {})
            buffs["defense"] = {"value": item.effect.buff_defense, "duration": item.effect.buff_duration}
            stats["buffs"] = buffs
        
        return stats
    
    def generate_item_event(self, item: Item, character_name: str, success: bool) -> str:
        """生成道具使用事件描述"""
        if success:
            return f"{character_name}使用了{item.name}。{item.get_use_description()}"
        else:
            return f"{character_name}试图使用{item.name}，但条件不满足。"


# 全局道具管理器实例
_item_manager = None

def get_item_manager() -> ItemManager:
    """获取全局道具管理器"""
    global _item_manager
    if _item_manager is None:
        _item_manager = ItemManager()
    return _item_manager
