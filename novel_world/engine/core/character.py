# -*- coding: utf-8 -*-
"""
角色系统 - 主角、反派、NPC
"""
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List
import random
import uuid


class CharType(Enum):
    PROTAGONIST = "\u4e3b\u89d2"
    HEROINE = "\u5973\u4e3b\u89d2"  # 新增：女主角
    ANTAGONIST = "\u53cd\u6d3e"
    NPC = "NPC"
    KEY_NPC = "\u5173\u952e\u914d\u89d2"  # 新增：关键配角


class CharState(Enum):
    IDLE = "\u7a7a\u95f2"
    MOVING = "\u79fb\u52a8\u4e2d"
    WORKING = "\u5de5\u4f5c\u4e2d"
    RESTING = "\u4f11\u606f\u4e2d"
    FIGHTING = "\u6218\u6597\u4e2d"
    TALKING = "\u4ea4\u8c08\u4e2d"
    EVOLVING = "\u7a81\u7834\u4e2d"
    EXPLORING = "\u63a2\u7d22\u4e2d"
    SICK = "\u751f\u75c5"
    DEAD = "\u6b7b\u4ea1"


@dataclass
class Character:
    name: str = ""
    char_type: CharType = CharType.NPC
    pos: tuple = (0, 0)
    age: int = 18
    gender: str = "\u7537"
    attrs: dict = field(default_factory=lambda: {
        "\u4f53\u529b": 50, "\u667a\u529b": 50, "\u9b45\u529b": 50, "\u8fd0\u6c14": 50,
        "\u653b\u51fb": 20, "\u9632\u5fa1": 20, "\u58f0\u671b": 0, "\u8d22\u5bcc": 0,
    })
    skills: list = field(default_factory=list)
    goal: str = ""
    state: CharState = CharState.IDLE
    faction_id: str = ""
    relations: dict = field(default_factory=dict)
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    memory: list = field(default_factory=list)
    alive: bool = True
    action_cooldown: int = 0
    # --- \u6838\u5fc3\u53d9\u4e8b\u5c5e\u6027 ---
    personality: str = ""       # \u6027\u683c\u63cf\u8ff0
    fate_arc: str = ""          # \u547d\u8fd0\u7ebf/\u5f53\u524d\u5904\u5883
    story_state: str = ""       # AI\u7ef4\u62a4\u7684\u5f53\u524d\u72b6\u6001
    key_memories: list = field(default_factory=list)  # \u5173\u952e\u8bb0\u5fc6
    relationships: dict = field(default_factory=dict)  # {id: "\u5173\u7cfb\u63cf\u8ff0"}

    # 气息残留追踪（I1）
    aura_trail: list = field(default_factory=list)
    # aura_trail 条目: {tile: (x,y), intensity: 0-100, decay_tick: N}

    # 信息差状态追踪（F）：角色对其它角色的感知状态
    # {target_name: {"status": "see"|"partial"|"hidden", "since_tick": N, "reason": "..."}}
    perception_state: dict = field(default_factory=dict)

    def __post_init__(self):
        if not self.name:
            self.name = f"\u89d2\u8272_{self.id[:4]}"

    def get_attr(self, key):
        return self.attrs.get(key, 0)

    def modify_attr(self, key, delta):
        val = self.attrs.get(key, 0)
        self.attrs[key] = max(0, min(999, val + delta))

    def is_ready(self):
        return self.alive and self.action_cooldown <= 0

    def tick_cooldown(self):
        if self.action_cooldown > 0:
            self.action_cooldown -= 1

    def add_memory(self, text, max_memories=50):
        self.memory.append(text)
        if len(self.memory) > max_memories:
            self.memory = self.memory[-max_memories:]

    def add_key_memory(self, text, max_memories=20):
        """\u6dfb\u52a0\u5173\u952e\u8bb0\u5fc6\uff08\u6709\u60c5\u8282\u610f\u4e49\u7684\uff09"""
        self.key_memories.append(text)
        if len(self.key_memories) > max_memories:
            self.key_memories = self.key_memories[-max_memories:]

    def get_relation(self, other_id):
        return self.relations.get(other_id, 0)

    def modify_relation(self, other_id, delta):
        val = self.relations.get(other_id, 0)
        self.relations[other_id] = max(-100, min(100, val + delta))

    def set_relationship(self, other_id, desc):
        """\u8bbe\u7f6e\u5173\u7cfb\u63cf\u8ff0"""
        self.relationships[other_id] = desc

    def get_relationship(self, other_id):
        return self.relationships.get(other_id, "\u4e0d\u8ba4\u8bc6")

    # ══════════════════════════════════════
    # I1: 气息残留追踪
    # ══════════════════════════════════════
    def add_aura_trail(self, x: int, y: int, intensity: int = 30,
                       decay_per_tick: int = 5):
        """角色移动后自动在旧位置生成气息残留"""
        self.aura_trail.append({
            "tile": (x, y),
            "intensity": max(0, min(100, intensity)),
            "decay_per_tick": decay_per_tick,
        })

    def decay_aura_trails(self):
        """每慢Tick衰减气息残留，intensity <= 0 则移除"""
        self.aura_trail = [
            t for t in self.aura_trail
            if (t["intensity"] - t["decay_per_tick"]) > 0
        ]
        for t in self.aura_trail:
            t["intensity"] = max(0, t["intensity"] - t["decay_per_tick"])

    def get_strongest_aura_at(self, x: int, y: int) -> int:
        """检查某位置是否有该角色的气息残留，返回最高强度"""
        best = 0
        for t in self.aura_trail:
            if t["tile"] == (x, y) and t["intensity"] > best:
                best = t["intensity"]
        return best


_PERSONALITIES = {
    "\u65e5\u5e38": ["\u52c7\u6562\u51b2\u52a8\u3001\u5ac9\u6076\u5982\u4ec7", "\u51b7\u9759\u667a\u6167\u3001\u5fc3\u601d\u7ec6\u5bc6", "\u6e29\u67d4\u5584\u826f\u3001\u5fc3\u5730\u5584\u826f",
              "\u6027\u683c\u5f00\u6717\u3001\u7cbe\u529b\u5145\u6c9b", "\u6c89\u9ed8\u5bde\u8a00\u3001\u5185\u5fc3\u654f\u611f", "\u4e50\u89c2\u5929\u7136\u3001\u968f\u9047\u800c\u5b89",
              "\u56fa\u6267\u575a\u5f3a\u3001\u4e0d\u5c48\u4e0d\u6320", "\u72e1\u733e\u591a\u8c0b\u3001\u884c\u4e8b\u4fdd\u5bc6"],
    "\u4fee\u4ed9": ["\u5b64\u50b2\u4e0d\u7fa4\u3001\u5411\u9053\u4e4b\u5fc3", "\u67d4\u5f31\u5916\u8868\u3001\u575a\u5f3a\u5185\u5fc3", "\u6076\u8da3\u76f8\u6295\u3001\u4e5f\u6709\u6b63\u4e49\u611f",
              "\u51b7\u9759\u7406\u6027\u3001\u4e0d\u5584\u4ea4\u9645", "\u5929\u8d44\u806a\u9896\u3001\u4f46\u6027\u60c5\u504f\u6025"],
    "\u5947\u5e7b": ["\u6076\u4f5c\u5267\u4f46\u5185\u5fc3\u5584\u826f", "\u5fe0\u8bda\u52c7\u6562\u3001\u6b63\u4e49\u611f\u5f3a", "\u6076\u6bd2\u800c\u6709\u9b45\u529b\u3001\u6709\u81ea\u5df1\u7684\u89c4\u5219",
              "\u597d\u5947\u5fc3\u5f3a\u3001\u559c\u6b22\u5192\u9669", "\u4e25\u8083\u6b63\u7ecf\u3001\u6309\u89c4\u77e9\u529e\u4e8b"],
    "\u672b\u4e16": ["\u8b66\u89c9\u9ad8\u3001\u4e0d\u4fe1\u4efb\u4efb\u4f55\u4eba", "\u5f3a\u58ee\u5b9e\u5e72\u3001\u5584\u4e8e\u5b9e\u7528\u4e3b\u4e49",
              "\u4e50\u89c2\u7684\u60b2\u89c2\u4e3b\u4e49\u8005", "\u6c89\u9ed8\u5be1\u8a00\u3001\u6709\u7740\u8fc7\u53bb\u7684\u79d8\u5bc6"],
    "\u79d1\u5e7b": ["\u7406\u6027\u5145\u8db3\u3001\u4fe1\u4efb\u79d1\u6280", "\u53db\u9006\u7cbe\u795e\u3001\u8d28\u7591\u6743\u5a01", "\u5bb6\u65cf\u8363\u8a89\u611f\u5f3a\u3001\u627f\u62c5\u8d23\u4efb",
              "\u72e1\u733e\u5584\u53d8\u3001\u8eab\u4efd\u6210\u8c1c", "\u7eaf\u7cb9\u597d\u5947\u3001\u6e34\u671b\u63a2\u7d22\u672a\u77e5"],
    "\u6050\u6016": ["\u67d0\u7c9f\u602f\u60e7\u3001\u4f46\u5f3a\u8feb\u81ea\u5df1\u52c7\u6562", "\u597d\u5947\u5fc3\u91cd\u3001\u5e38\u5e38\u5ffd\u7565\u5371\u9669",
              "\u7406\u6027\u5145\u8db3\u3001\u8bd5\u56fe\u7528\u79d1\u5b66\u89e3\u91ca\u4e00\u5207", "\u6562\u4e8e\u9762\u5bf9\u6050\u60e7\u3001\u6709\u7740\u5f3a\u5927\u7684\u610f\u5fd7\u529b"],
}

_FATE_ARCS = {
    "\u65e5\u5e38": ["\u6b63\u5728\u5bfb\u627e\u5931\u6563\u7684\u4eb2\u4eba", "\u8ffd\u6c42\u68a6\u60f3\u4e2d\u7684\u804c\u4e1a\u9053\u8def",
              "\u56e0\u4e00\u573a\u610f\u5916\u5f00\u59cb\u4e86\u65b0\u7684\u751f\u6d3b", "\u5e26\u7740\u79d8\u5bc6\u6765\u5230\u65b0\u7684\u57ce\u9547",
              "\u60f3\u8981\u8bc1\u660e\u81ea\u5df1\u7684\u6e05\u767d", "\u5bfb\u627e\u4f20\u8bf4\u4e2d\u7684\u5b9d\u85cf"],
    "\u4fee\u4ed9": ["\u4fee\u70bc\u9047\u5230\u74f6\u9888\uff0c\u9700\u8981\u5bfb\u627e\u7a81\u7834\u4e4b\u6cd5",
              "\u5e08\u95e8\u88ab\u706d\uff0c\u80cc\u8d1f\u590d\u4ec7\u4e4b\u8def", "\u53d1\u73b0\u4e86\u4e00\u5904\u53e4\u8ff9\uff0c\u85cf\u7740\u5927\u79d8",
              "\u5728\u6b63\u90aa\u4e4b\u95f4\u72b9\u8c6b\u4e0d\u51b3"],
    "\u5947\u5e7b": ["\u88ab\u9009\u4e2d\u6267\u884c\u4e00\u4e2a\u5371\u9669\u7684\u4efb\u52a1",
              "\u63ed\u5f00\u4e00\u4e2a\u5371\u53ca\u738b\u56fd\u7684\u9634\u8c0b", "\u5bfb\u627e\u5931\u8e2a\u7684\u795e\u5668",
              "\u88ab\u8bc5\u5492\u53d8\u6210\u4e86\u53e6\u4e00\u4e2a\u5f62\u6001"],
    "\u672b\u4e16": ["\u5728\u5e9f\u589f\u4e2d\u5bfb\u627e\u4e00\u5904\u5b89\u5168\u7684\u5e87\u6240",
              "\u643a\u5e26\u7740\u91cd\u8981\u7684\u7269\u8d44\u524d\u5f80\u8fdc\u65b9",
              "\u88ab\u4e00\u4e2a\u795e\u79d8\u7684\u7535\u53f0\u5438\u5f15\uff0c\u51b3\u5b9a\u53bb\u8c03\u67e5",
              "\u611f\u67d3\u5373\u5c06\u53d1\u4f5c\uff0c\u5fc5\u987b\u627e\u5230\u89e3\u836f"],
    "\u79d1\u5e7b": ["\u53d1\u73b0\u4e86\u5916\u661f\u4fe1\u53f7\uff0c\u51b3\u5b9a\u524d\u5f80\u8c03\u67e5",
              "\u661f\u9645\u6218\u4e89\u5373\u5c06\u7206\u53d1\uff0c\u5fc5\u987b\u5b8c\u6210\u4f7f\u547d",
              "\u53d1\u73b0AI\u6709\u81ea\u6211\u610f\u8bc6\uff0c\u9677\u5165\u9053\u5fb7\u56f0\u5883",
              "\u8981\u5728\u4e24\u4e2a\u661f\u7403\u4e4b\u95f4\u505a\u51fa\u9009\u62e9"],
    "\u6050\u6016": ["\u63a2\u7d22\u4e00\u5ea7\u88ab\u9057\u5f03\u7684\u5efa\u7b51\uff0c\u53d1\u73b0\u4e86\u4e0d\u53ef\u601d\u8bae\u7684\u4e8b\u7269",
              "\u88ab\u566a\u68a6\u7f20\u7ed5\uff0c\u5fc5\u987b\u627e\u5230\u566a\u68a6\u7684\u6765\u6e90",
              "\u53d1\u73b0\u5c0f\u9547\u4e0a\u7684\u4eba\u6b63\u5728\u9010\u4e2a\u6d88\u5931",
              "\u4e00\u672c\u53e4\u4e66\u6307\u5411\u4e86\u4e00\u4e2a\u7981\u6b62\u7684\u5730\u65b9"],
}

_NAMES = {
    "\u7537": ["\u5c0f\u660e", "\u5c0f\u5f3a", "\u963f\u6770", "\u8001\u738b", "\u5c0f\u674e", "\u5f20\u4f1f", "\u8d75\u5fb7", "\u5468\u8fb0", "\u674e\u9752\u4e91", "\u5218\u5929"],
    "\u5973": ["\u5c0f\u7ea2", "\u5c0f\u7f8e", "\u963f\u82b1", "\u5c0f\u96ea", "\u674e\u6708", "\u738b\u59d3\u59d3", "\u6797\u6674", "\u5468\u5983", "\u82cf\u5a49\u513f", "\u5f20\u6653\u6668"],
}


def generate_random_character(name="", theme="\u65e5\u5e38", personality=None, goal=None, fate_arc=None):
    gender = random.choice(["\u7537", "\u5973"])
    if not name:
        name = random.choice(_NAMES.get(gender, _NAMES["\u7537"]))
    if not personality:
        personality = random.choice(_PERSONALITIES.get(theme, _PERSONALITIES["\u65e5\u5e38"]))
    if not fate_arc:
        fate_arc = random.choice(_FATE_ARCS.get(theme, _FATE_ARCS["\u65e5\u5e38"]))

    attrs = {
        "\u4f53\u529b": random.randint(30, 80),
        "\u667a\u529b": random.randint(30, 80),
        "\u9b45\u529b": random.randint(30, 80),
        "\u8fd0\u6c14": random.randint(30, 80),
        "\u653b\u51fb": random.randint(10, 40),
        "\u9632\u5fa1": random.randint(10, 40),
        "\u58f0\u671b": random.randint(0, 30),
        "\u8d22\u5bcc": random.randint(0, 50),
    }

    age = random.randint(16, 45) if theme == "\u65e5\u5e38" else random.randint(18, 200)

    return Character(
        name=name,
        gender=gender,
        age=age,
        attrs=attrs,
        personality=personality,
        goal=goal or "",
        fate_arc=fate_arc,
        story_state=f"\u5728\u65c5\u9014\u4e2d",
        pos=(random.randint(2, 35), random.randint(2, 20)),
    )

# NPC生成规则校验 - 添加到 character.py

# 已知角色名称集合（用于检查是否是无名NPC）
_established_names = set()

def register_character_name(name: str):
    """注册已建立的角色名称"""
    _established_names.add(name)

def is_established_character(name: str) -> bool:
    """检查是否是已建立的角色"""
    return name in _established_names

def validate_npc_generation(name: str, theme: str, personality: str = None) -> tuple:
    """
    校验NPC生成是否符合规则
    返回: (is_valid, message)
    """
    # 检查是否使用了常见的路人名字
    random_name_patterns = ["小明", "小红", "小强", "小李", "小王", "小张", 
                           "小雪", "小美", "李青云", "周辰", "张三", "李四"]
    
    for pattern in random_name_patterns:
        if name == pattern or name.startswith(pattern):
            # 如果没有个性描述，可能是无设定NPC
            if not personality or len(personality) < 5:
                return (False, f"禁止生成无设定NPC: {name}")
    
    # 检查名字是否已经在已建立角色中（避免重复）
    if name in _established_names:
        return (False, f"角色名称重复: {name}")
    
    # 注册新角色
    register_character_name(name)
    
    return (True, "")

def generate_character_with_rules(name: str = "", theme: str = "日常", 
                                  personality: str = None, goal: str = None,
                                  fate_arc: str = None, char_type = None):
    """
    带规则校验的角色生成
    """
    from game.backend.character import Character, CharType, generate_random_character
    
    # 如果没有提供名字，生成一个不常见的名字
    if not name:
        # 使用更独特的名字池
        unique_names = [
            "云逸", "墨寒", "风清", "月白", "星河", "雪影", "霜华", "烟雨",
            "青竹", "白露", "紫烟", "红尘", "碧落", "黄泉", "苍穹", "玄冥",
            "凌霄", "傲雪", "飞羽", "流云", "幻月", "寒星", "烈焰", "冰心",
            "梦璃", "素心", "若水", "无痕", "长风", "落霞", "孤鸿", "惊鸿"
        ]
        import random
        name = random.choice(unique_names)
    
    # 校验NPC生成
    is_valid, message = validate_npc_generation(name, theme, personality)
    if not is_valid:
        # 如果校验失败，重新生成名字
        import random
        unique_names = ["云逸", "墨寒", "风清", "月白", "星河", "雪影"]
        name = random.choice(unique_names)
    
    # 生成角色
    char = generate_random_character(name=name, theme=theme, personality=personality, 
                                    goal=goal, fate_arc=fate_arc)
    
    # 如果指定了角色类型，更新
    if char_type:
        char.char_type = char_type
    
    return char


    # ==================== 道具系统方法 ====================
    
    def add_item(self, item_id: str, count: int = 1):
        """添加道具到背包"""
        if item_id in self.inventory:
            self.inventory[item_id] += count
        else:
            self.inventory[item_id] = count
    
    def remove_item(self, item_id: str, count: int = 1) -> bool:
        """从背包移除道具，返回是否成功"""
        if item_id not in self.inventory:
            return False
        if self.inventory[item_id] < count:
            return False
        self.inventory[item_id] -= count
        if self.inventory[item_id] <= 0:
            del self.inventory[item_id]
        return True
    
    def has_item(self, item_id: str, count: int = 1) -> bool:
        """检查是否有足够的道具"""
        return self.inventory.get(item_id, 0) >= count
    
    def get_item_count(self, item_id: str) -> int:
        """获取道具数量"""
        return self.inventory.get(item_id, 0)
    
    def equip_item(self, item_id: str) -> bool:
        """装备道具"""
        if item_id not in self.inventory:
            return False
        if item_id in self.equipped_items:
            return False
        self.equipped_items.append(item_id)
        return True
    
    def unequip_item(self, item_id: str) -> bool:
        """卸下装备"""
        if item_id not in self.equipped_items:
            return False
        self.equipped_items.remove(item_id)
        return True
    
    def add_buff(self, buff_type: str, value: int, duration: int):
        """添加buff"""
        self.active_buffs[buff_type] = {"value": value, "duration": duration}
    
    def tick_buffs(self):
        """每回合更新buff"""
        expired = []
        for buff_type, buff_data in self.active_buffs.items():
            buff_data["duration"] -= 1
            if buff_data["duration"] <= 0:
                expired.append(buff_type)
        for buff_type in expired:
            del self.active_buffs[buff_type]
    
    def get_buff_value(self, buff_type: str) -> int:
        """获取buff加成值"""
        if buff_type in self.active_buffs:
            return self.active_buffs[buff_type]["value"]
        return 0
