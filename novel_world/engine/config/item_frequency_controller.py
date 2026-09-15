# -*- coding: utf-8 -*-
"""
道具频率控制器 - 解决道具滥用问题
对高频道具做频率控制，支持同类替换
"""
from typing import Dict, List, Optional, Set, Tuple
from dataclasses import dataclass, field
from enum import Enum
import random
from collections import defaultdict


class ItemType(Enum):
    """道具类型"""
    WEAPON = "武器"
    MEDICINE = "药品"
    FOOD = "食物"
    TOOL = "工具"
    TREASURE = "宝物"
    DOCUMENT = "文书"
    CLOTHING = "衣物"
    ACCESSORY = "饰品"
    MATERIAL = "材料"
    SPECIAL = "特殊"


@dataclass
class ItemUsage:
    """道具使用记录"""
    item_name: str
    item_type: ItemType
    use_count: int = 0
    last_used_round: int = 0
    cooldown_remaining: int = 0


@dataclass
class ItemSubstitute:
    """道具替代品"""
    original: str           # 原道具
    substitutes: List[str]  # 替代品列表
    item_type: ItemType


class ItemFrequencyController:
    """道具频率控制器"""
    
    def __init__(self):
        # 道具使用记录
        self._usage_records: Dict[str, ItemUsage] = {}
        
        # 道具替代品映射
        self._substitutes: Dict[str, ItemSubstitute] = {}
        
        # 类型冷却配置
        self._type_cooldowns: Dict[ItemType, int] = {
            ItemType.WEAPON: 5,      # 武器冷却5回合
            ItemType.MEDICINE: 3,    # 药品冷却3回合
            ItemType.FOOD: 2,        # 食物冷却2回合
            ItemType.TOOL: 4,        # 工具冷却4回合
            ItemType.TREASURE: 10,   # 宝物冷却10回合
            ItemType.DOCUMENT: 6,    # 文书冷却6回合
            ItemType.CLOTHING: 8,    # 衣物冷却8回合
            ItemType.ACCESSORY: 7,   # 饰品冷却7回合
            ItemType.MATERIAL: 3,    # 材料冷却3回合
            ItemType.SPECIAL: 15,    # 特殊道具冷却15回合
        }
        
        # 高频道具阈值
        self._high_frequency_threshold = 3  # 使用次数超过此值为高频
        
        # 当前回合
        self._current_round = 0
        
        # 初始化替代品
        self._initialize_substitutes()
    
    def _initialize_substitutes(self):
        """初始化道具替代品"""
        
        # 武器替代
        self._substitutes["长剑"] = ItemSubstitute(
            original="长剑",
            substitutes=["钢刀", "短剑", "佩刀", "软剑", "重剑"],
            item_type=ItemType.WEAPON
        )
        self._substitutes["匕首"] = ItemSubstitute(
            original="匕首",
            substitutes=["短刀", "暗刃", "袖箭", "飞刀"],
            item_type=ItemType.WEAPON
        )
        
        # 药品替代
        self._substitutes["疗伤药"] = ItemSubstitute(
            original="疗伤药",
            substitutes=["金创药", "止血散", "回春丹", "愈伤膏"],
            item_type=ItemType.MEDICINE
        )
        self._substitutes["解毒药"] = ItemSubstitute(
            original="解毒药",
            substitutes=["清毒丹", "化毒散", "祛毒丸"],
            item_type=ItemType.MEDICINE
        )
        
        # 食物替代
        self._substitutes["干粮"] = ItemSubstitute(
            original="干粮",
            substitutes=["肉干", "面饼", "馒头", "包子", "饭团"],
            item_type=ItemType.FOOD
        )
        self._substitutes["酒"] = ItemSubstitute(
            original="酒",
            substitutes=["烧刀子", "女儿红", "竹叶青", "米酒", "果酒"],
            item_type=ItemType.FOOD
        )
        
        # 工具替代
        self._substitutes["绳索"] = ItemSubstitute(
            original="绳索",
            substitutes=["麻绳", "丝绳", "飞爪", "钩索"],
            item_type=ItemType.TOOL
        )
        self._substitutes["火折子"] = ItemSubstitute(
            original="火折子",
            substitutes=["火石", "火镰", "蜡烛", "灯笼"],
            item_type=ItemType.TOOL
        )
        
        # 宝物替代
        self._substitutes["玉佩"] = ItemSubstitute(
            original="玉佩",
            substitutes=["玉牌", "玉坠", "玉环", "玉扳指"],
            item_type=ItemType.TREASURE
        )
        self._substitutes["银两"] = ItemSubstitute(
            original="银两",
            substitutes=["铜钱", "金叶子", "银票", "碎银"],
            item_type=ItemType.TREASURE
        )
        
        # 文书替代
        self._substitutes["书信"] = ItemSubstitute(
            original="书信",
            substitutes=["密信", "传书", "便笺", "手札"],
            item_type=ItemType.DOCUMENT
        )
        self._substitutes["地图"] = ItemSubstitute(
            original="地图",
            substitutes=["舆图", "海图", "路线图", "藏宝图"],
            item_type=ItemType.DOCUMENT
        )
    
    def register_item_use(self, item_name: str, item_type: ItemType = None) -> str:
        """
        注册道具使用，返回实际使用的道具名称（可能是替代品）
        """
        # 查找道具类型
        if item_type is None:
            # 从替代品映射中查找
            for name, sub in self._substitutes.items():
                if name == item_name or item_name in sub.substitutes:
                    item_type = sub.item_type
                    break
            if item_type is None:
                item_type = ItemType.SPECIAL
        
        # 获取或创建使用记录
        if item_name not in self._usage_records:
            self._usage_records[item_name] = ItemUsage(
                item_name=item_name,
                item_type=item_type
            )
        
        record = self._usage_records[item_name]
        
        # 检查是否高频使用
        if record.use_count >= self._high_frequency_threshold:
            # 尝试使用替代品
            substitute = self._get_substitute(item_name, item_type)
            if substitute:
                # 更新替代品的使用记录
                if substitute not in self._usage_records:
                    self._usage_records[substitute] = ItemUsage(
                        item_name=substitute,
                        item_type=item_type
                    )
                self._usage_records[substitute].use_count += 1
                self._usage_records[substitute].last_used_round = self._current_round
                return substitute
        
        # 更新使用记录
        record.use_count += 1
        record.last_used_round = self._current_round
        
        # 设置冷却
        cooldown = self._type_cooldowns.get(item_type, 5)
        record.cooldown_remaining = cooldown
        
        return item_name
    
    def _get_substitute(self, item_name: str, item_type: ItemType) -> Optional[str]:
        """获取道具替代品"""
        # 查找替代品映射
        if item_name in self._substitutes:
            sub = self._substitutes[item_name]
            # 选择未使用的替代品
            available = [s for s in sub.substitutes 
                        if s not in self._usage_records or 
                        self._usage_records[s].cooldown_remaining <= 0]
            if available:
                return random.choice(available)
        
        # 如果没有预定义的替代品，生成通用替代
        return self._generate_generic_substitute(item_name, item_type)
    
    def _generate_generic_substitute(self, item_name: str, item_type: ItemType) -> Optional[str]:
        """生成通用替代品"""
        # 简单的前缀变化
        prefixes = {
            ItemType.WEAPON: ["精制", "普通", "旧", "新"],
            ItemType.MEDICINE: ["上等", "普通", "劣质"],
            ItemType.FOOD: ["新鲜", "普通", "陈"],
            ItemType.TOOL: ["实用", "简易", "精致"],
            ItemType.TREASURE: ["珍贵", "普通", "破旧"],
        }
        
        if item_type in prefixes:
            prefix = random.choice(prefixes[item_type])
            return f"{prefix}{item_name}"
        
        return None
    
    def is_item_available(self, item_name: str) -> bool:
        """检查道具是否可用（不在冷却中）"""
        if item_name not in self._usage_records:
            return True
        
        return self._usage_records[item_name].cooldown_remaining <= 0
    
    def get_item_suggestion(self, item_type: ItemType = None, 
                           exclude: Set[str] = None) -> Optional[str]:
        """
        获取道具建议（优先选择低频道具）
        """
        if exclude is None:
            exclude = set()
        
        # 找出该类型中低频使用的道具
        candidates = []
        for name, record in self._usage_records.items():
            if name in exclude:
                continue
            if item_type and record.item_type != item_type:
                continue
            if record.cooldown_remaining > 0:
                continue
            candidates.append((name, record.use_count))
        
        if not candidates:
            # 从替代品中选择
            for name, sub in self._substitutes.items():
                if item_type and sub.item_type != item_type:
                    continue
                for subst in sub.substitutes:
                    if subst not in exclude:
                        if subst not in self._usage_records or self._usage_records[subst].cooldown_remaining <= 0:
                            return subst
        
        # 选择使用次数最少的
        if candidates:
            candidates.sort(key=lambda x: x[1])
            return candidates[0][0]
        
        return None
    
    def advance_round(self):
        """推进回合，更新冷却"""
        self._current_round += 1
        
        for record in self._usage_records.values():
            if record.cooldown_remaining > 0:
                record.cooldown_remaining -= 1
    
    def get_high_frequency_items(self) -> List[Tuple[str, int]]:
        """获取高频道具列表"""
        high_freq = []
        for name, record in self._usage_records.items():
            if record.use_count >= self._high_frequency_threshold:
                high_freq.append((name, record.use_count))
        
        high_freq.sort(key=lambda x: x[1], reverse=True)
        return high_freq
    
    def get_statistics(self) -> Dict:
        """获取统计信息"""
        total_items = len(self._usage_records)
        total_uses = sum(r.use_count for r in self._usage_records.values())
        high_freq_count = len(self.get_high_frequency_items())
        
        type_stats = defaultdict(int)
        for record in self._usage_records.values():
            type_stats[record.item_type.value] += record.use_count
        
        return {
            "total_items": total_items,
            "total_uses": total_uses,
            "high_frequency_count": high_freq_count,
            "type_distribution": dict(type_stats),
            "current_round": self._current_round
        }
    
    def reset(self):
        """重置所有记录"""
        self._usage_records.clear()
        self._current_round = 0


# 单例
_item_controller_instance = None

def get_item_controller() -> ItemFrequencyController:
    global _item_controller_instance
    if _item_controller_instance is None:
        _item_controller_instance = ItemFrequencyController()
    return _item_controller_instance
