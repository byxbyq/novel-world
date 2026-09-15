# -*- coding: utf-8 -*-
"""
奇幻世界观模板 - 魔法与冒险
"""

MAP_SIZE = (40, 25)

TILE_TYPES = ["平原", "山地", "森林", "水域", "遗迹", "沙漠", "城市"]
TILE_WEIGHTS = [15, 18, 20, 12, 15, 8, 12]

NAME_POOL = {
    "男": ["艾尔文", "索林", "格罗姆", "菲恩", "洛基", "塞拉斯", "加里安", "雷恩", "达里安", "托尔",
           "亚瑟", "兰斯洛特", "格里芬", "奥利弗", "卡西乌斯", "瓦尔基里", "贝恩", "塞巴斯蒂安", "卡尔", "乌瑟"],
    "女": ["艾拉", "伊莎贝尔", "瑟琳娜", "露娜", "芙蕾雅", "阿丽亚娜", "米拉", "希拉", "维多利亚", "尼娜",
           "艾薇", "菲奥娜", "盖尔", "赫尔加", "伊莲娜", "凯瑟琳", "莉莉丝", "梅芙", "奥菲利亚", "罗莎"],
}

# 魔法元素
ELEMENTS = ["火", "水", "风", "土", "雷", "冰", "暗", "光"]

EVENT_TEMPLATES = [
    {"type": "觉醒", "desc": "{name}觉醒了{element}属性魔法！","weight": 5,
     "condition": "idle", "attr_change": {"魔法": 20, "声望": 5}},
    {"type": "屠龙", "desc": "{name}成功讨伐了一头巨龙！", "weight": 2,
     "condition": "fighting", "attr_change": {"声望": 30, "财富": 20}},
    {"type": "诅咒", "desc": "{name}被不明力量诅咒了...", "weight": 3,
     "condition": "any", "attr_change": {"魔法": -15, "健康": -10}},
    {"type": "神器", "desc": "{name}在遗迹中发现了一件神器！", "weight": 3,
     "condition": "exploring", "attr_change": {"魔法": 15, "声望": 10}},
    {"type": "公会任务", "desc": "{name}完成了一个S级公会任务！", "weight": 5,
     "condition": "working", "attr_change": {"财富": 15, "声望": 12}},
    {"type": "魔王降临", "desc": "黑暗魔王苏醒了，世界陷入危机！", "weight": 1,
     "condition": "any", "attr_change": {}},
    {"type": "精灵契约", "desc": "{name}与一只精灵签订了契约！", "weight": 3,
     "condition": "exploring", "attr_change": {"魔法": 12}},
    {"type": "王都盛典", "desc": "{place}举办了盛大的庆典！", "weight": 3,
     "condition": "any", "attr_change": {"快乐": 10}},
    {"type": "魔物袭击", "desc": "一群魔物袭击了{place}！", "weight": 6,
     "condition": "any", "attr_change": {}},
    {"type": "转职", "desc": "{name}成功转职为{job}！", "weight": 4,
     "condition": "working", "attr_change": {"力量": 10, "魔法": 10}},
    {"type": "地下城", "desc": "{name}挑战了一座地下城！", "weight": 5,
     "condition": "exploring", "attr_change": {"财富": 12, "经验": 15}},
    {"type": "亡灵入侵", "desc": "亡灵大军入侵了{place}附近！", "weight": 3,
     "condition": "any", "attr_change": {}},
]

STORY_TEMPLATES = {
    "idle": [
        "{name}在酒馆里喝着蜂蜜酒。",
        "{name}坐在篝火旁擦拭着武器。",
        "{name}在魔法塔中翻阅魔法书。",
        "{name}在集市上闲逛，寻找装备。",
        "{name}仰望星空，思考下一步冒险。",
    ],
    "working": [
        "{name}在铁匠铺锻造新武器。",
        "{name}在魔法工坊中调配药水。",
        "{name}在公会大厅接取新任务。",
        "{name}在训练场苦练剑术。",
    ],
    "moving": [
        "{name}骑马穿过{place}的原野。",
        "{name}沿着古老的道路向{place}进发。",
        "{name}踏入了危险的{place}森林。",
    ],
    "fighting": [
        "{name}挥剑斩向{name2}！",
        "{name}释放了一个{element}系魔法！",
        "{name}与{name2}展开了激烈的决斗！",
    ],
    "exploring": [
        "{name}探索了一座废弃的城堡。",
        "{name}在地下迷宫中寻找宝藏。",
        "{name}发现了一个隐藏的魔法洞穴。",
        "{name}进入了一片被诅咒的森林。",
    ],
    "talking": [
        "{name}与{name2}交换了冒险情报。",
        "{name}向村长询问了附近的传说。",
        "{name}在酒馆里听吟游诗人唱歌。",
    ],
    "resting": [
        "{name}在旅馆里美美地睡了一觉。",
        "{name}泡在温泉里恢复体力。",
        "{name}在教堂里接受牧师的治疗。",
    ],
    "sick": [
        "{name}中了毒，急需解药。",
        "{name}被诅咒折磨，痛苦不堪。",
    ],
}

FACTION_NAMES = ["骑士团", "魔法师公会", "精灵部落", "矮人工坊", "暗影兄弟会", "光明教会", "冒险者联盟"]
FACTION_COLORS = ["#FFD700", "#9370DB", "#228B22", "#D2691E", "#2F2F2F", "#FFFFFF", "#FF8C00"]

TILE_NAMES = {
    "城市": ["王都", "港口城市", "精灵之森", "矮人堡垒", "魔法学院"],
    "平原": ["绿野", "牧场", "训练场"],
    "山地": ["龙脊山脉", "矮人矿山", "鹰巢峰"],
    "森林": ["精灵森林", "黑暗森林", "蘑菇林"],
    "水域": ["圣湖", "深海入口", "精灵之泉"],
    "沙漠": ["死亡沙漠", "沙虫荒原"],
    "遗迹": ["远古神殿", "龙巢", "精灵废墟", "地下城入口"],
}
