# -*- coding: utf-8 -*-
"""
角色参数库 - 角色人设、成长节点、禁忌行为参数化设计
"""
from typing import Dict, List, Optional
from dataclasses import dataclass, field


@dataclass
class CharacterTrait:
    """角色特质参数"""
    name: str  # 特质名称
    value: int  # 特质强度 (0-10)
    description: str = ""  # 特质描述
    growth_stages: List[str] = field(default_factory=list)  # 成长阶段描述
    

@dataclass
class CharacterTaboo:
    """角色禁忌行为"""
    action: str  # 禁忌行为描述
    replacement: str  # 替代行为
    reason: str = ""  # 禁忌原因
    

@dataclass
class CharacterGrowthNode:
    """角色成长节点"""
    stage: int  # 阶段编号
    name: str  # 阶段名称
    description: str  # 阶段描述
    trigger_conditions: Dict = field(default_factory=dict)  # 触发条件
    behavior_changes: List[str] = field(default_factory=list)  # 行为变化
    

class CharacterParams:
    """角色参数库"""
    
    def __init__(self):
        self._characters: Dict[str, Dict] = {}
        self._initialize_default_characters()
    
    def _initialize_default_characters(self):
        """初始化默认角色参数"""
        
        # 主角模板（日常主题）
        self._characters["protagonist_daily"] = {
            "name": "主角",
            "core_traits": [
                CharacterTrait("内敛", 7, "不善表达，内心丰富", 
                             growth_stages=["沉默观察", "偶尔搭话", "主动交流"]),
                CharacterTrait("节俭", 8, "精打细算，避免浪费"),
                CharacterTrait("善良", 6, "乐于助人，心地善良"),
                CharacterTrait("坚韧", 5, "面对困难不轻易放弃"),
            ],
            "taboos": [
                CharacterTaboo("冲动消费", "深思熟虑后购买", "不符合节俭特质"),
                CharacterTaboo("大声喧哗", "轻声细语", "不符合内敛特质"),
                CharacterTaboo("轻易放弃", "坚持尝试", "不符合坚韧特质"),
            ],
            "growth_nodes": [
                CharacterGrowthNode(1, "犹豫期", "面对新事物犹豫不决", 
                                  trigger_conditions={"confidence": 0.3},
                                  behavior_changes=["观察", "思考"]),
                CharacterGrowthNode(2, "尝试期", "开始尝试新事物", 
                                  trigger_conditions={"confidence": 0.5},
                                  behavior_changes=["主动搭话", "小范围尝试"]),
                CharacterGrowthNode(3, "成长期", "逐渐适应并成长", 
                                  trigger_conditions={"confidence": 0.7},
                                  behavior_changes=["主动邀约", "积极行动"]),
            ],
            "interaction_weight": 1.0,  # 互动权重（核心角色）
        }
        
        # 反派模板
        self._characters["antagonist_daily"] = {
            "name": "反派",
            "core_traits": [
                CharacterTrait("精明", 8, "善于算计，目光敏锐"),
                CharacterTrait("强势", 7, "喜欢掌控，不甘人下"),
                CharacterTrait("野心", 9, "目标明确，不择手段"),
            ],
            "taboos": [
                CharacterTaboo("轻易妥协", "坚持己见", "不符合强势特质"),
                CharacterTaboo("无目的行动", "明确目标后行动", "不符合精明特质"),
            ],
            "growth_nodes": [],
            "interaction_weight": 0.8,
        }
        
        # NPC模板（辅助角色）
        self._characters["npc_helper"] = {
            "name": "辅助角色",
            "core_traits": [
                CharacterTrait("友善", 6, "乐于助人"),
                CharacterTrait("普通", 5, "平凡但真诚"),
            ],
            "taboos": [
                CharacterTaboo("抢戏", "适度参与", "辅助角色不应主导剧情"),
            ],
            "growth_nodes": [],
            "interaction_weight": 0.3,  # 辅助角色权重较低
        }
    
    def get_character_params(self, character_type: str) -> Optional[Dict]:
        """获取角色参数"""
        return self._characters.get(character_type)
    
    def get_trait_value(self, character_type: str, trait_name: str) -> int:
        """获取角色特质值"""
        params = self.get_character_params(character_type)
        if not params:
            return 5  # 默认中等
        
        for trait in params.get("core_traits", []):
            if trait.name == trait_name:
                return trait.value
        return 5
    
    def check_taboo(self, character_type: str, action: str) -> Optional[str]:
        """检查行为是否触犯禁忌，返回替代行为"""
        params = self.get_character_params(character_type)
        if not params:
            return None
        
        for taboo in params.get("taboos", []):
            if taboo.action in action:
                return taboo.replacement
        return None
    
    def get_growth_stage(self, character_type: str, confidence: float) -> Optional[CharacterGrowthNode]:
        """根据信心值获取当前成长阶段"""
        params = self.get_character_params(character_type)
        if not params:
            return None
        
        for node in params.get("growth_nodes", []):
            trigger_conf = node.trigger_conditions.get("confidence", 0)
            if confidence >= trigger_conf:
                return node
        return None
    
    def get_interaction_weight(self, character_type: str) -> float:
        """获取角色互动权重"""
        params = self.get_character_params(character_type)
        if not params:
            return 0.5
        return params.get("interaction_weight", 0.5)
    
    def add_character(self, character_type: str, params: Dict):
        """添加新角色参数"""
        self._characters[character_type] = params
    
    def list_characters(self) -> List[str]:
        """列出所有角色类型"""
        return list(self._characters.keys())


# 单例模式
_character_params_instance = None

def get_character_params() -> CharacterParams:
    """获取角色参数库单例"""
    global _character_params_instance
    if _character_params_instance is None:
        _character_params_instance = CharacterParams()
    return _character_params_instance
