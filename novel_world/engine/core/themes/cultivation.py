# -*- coding: utf-8 -*-
"""
修仙世界观模板 - 仙侠世界
"""

MAP_SIZE = (40, 25)

TILE_TYPES = ["平原", "山地", "森林", "水域", "遗迹", "沙漠", "城市"]
TILE_WEIGHTS = [15, 20, 18, 12, 15, 8, 12]

NAME_POOL = {
    "男": ["云逸", "墨尘", "玄明", "清风", "凌霄", "天机", "道玄", "长生", "无涯", "紫阳",
           "青莲", "苍云", "玉衡", "灵均", "星河", "太虚", "归元", "玄清", "忘忧", "静远"],
    "女": ["若水", "紫烟", "灵儿", "冰心", "青鸾", "月华", "雪瑶", "碧瑶", "瑶光", "素心",
           "丹青", "玉璃", "幽兰", "仙儿", "梦蝶", "织云", "妙音", "清荷", "灵犀", "雪莲"],
}

# 境界列表（修仙专属）
REALMS = ["炼气", "筑基", "金丹", "元婴", "化神", "合体", "大乘", "渡劫"]

EVENT_TEMPLATES = [
    {"type": "突破", "desc": "{name}闭关修炼，成功突破到{realm}境！", "weight": 6,
     "condition": "idle", "attr_change": {"修为": 30, "声望": 10}},
    {"type": "渡劫", "desc": "{name}引动天劫，{result}！", "weight": 3,
     "condition": "idle", "attr_change": {"修为": -20}},
    {"type": "收徒", "desc": "{name}收{name2}为弟子，传承道统。", "weight": 4,
     "condition": "idle", "attr_change": {"声望": 8}},
    {"type": "夺宝", "desc": "{name}在秘境中获得了一件宝物！", "weight": 5,
     "condition": "exploring", "attr_change": {"修为": 15}},
    {"type": "斗法", "desc": "{name}与{name2}展开了一场激烈的斗法！", "weight": 7,
     "condition": "fighting", "attr_change": {"修为": 5}},
    {"type": "走火入魔", "desc": "{name}修炼出了岔子，走火入魔了！", "weight": 2,
     "condition": "any", "attr_change": {"修为": -30, "健康": -20}},
    {"type": "机缘", "desc": "{name}偶遇仙人指点，修为大进！", "weight": 2,
     "condition": "exploring", "attr_change": {"修为": 25, "智慧": 10}},
    {"type": "宗门大战", "desc": "{faction}与敌对势力爆发大战！", "weight": 3,
     "condition": "any", "attr_change": {"声望": 5}},
    {"type": "炼丹", "desc": "{name}成功炼制了一炉{pill}！", "weight": 5,
     "condition": "working", "attr_change": {"修为": 10}},
    {"type": "渡劫失败", "desc": "{name}渡劫失败，境界跌落...", "weight": 2,
     "condition": "idle", "attr_change": {"修为": -40}},
    {"type": "秘境开启", "desc": "上古秘境突然开启，各方势力蠢蠢欲动。", "weight": 3,
     "condition": "any", "attr_change": {}},
    {"type": "双修", "desc": "{name}与{name2}双修，修为精进。", "weight": 2,
     "condition": "idle", "attr_change": {"修为": 15}},
]

STORY_TEMPLATES = {
    "idle": [
        "{name}在洞府中打坐修炼。",
        "{name}御剑飞行，俯瞰山河。",
        "{name}在灵池旁参悟天道。",
        "{name}翻阅古籍，寻找突破之法。",
        "{name}站在山巅，感应天地灵气。",
    ],
    "working": [
        "{name}在炼丹房中炼制丹药。",
        "{name}在藏经阁研读功法秘籍。",
        "{name}为宗门布设阵法。",
        "{name}闭关修炼，周身灵气涌动。",
    ],
    "moving": [
        "{name}御剑飞向{place}。",
        "{name}踏云而行，飘然若仙。",
        "{name}穿过重重迷雾，前往秘境。",
    ],
    "fighting": [
        "{name}祭出法宝，与{name2}激战正酣！",
        "{name}施展出绝招，天地变色！",
        "{name}以剑意压制对手，步步紧逼。",
    ],
    "evolving": [
        "{name}周身灵光环绕，正在突破！",
        "{name}渡过雷劫，境界更进一步。",
        "天降异象，{name}即将飞升！",
    ],
    "exploring": [
        "{name}踏入了一处上古秘境。",
        "{name}在深山中发现了一处灵脉。",
        "{name}探索了一座废弃的仙人洞府。",
    ],
    "talking": [
        "{name}与{name2}论道三日，各有收获。",
        "{name}在仙市上与散修交谈。",
        "{name}向师父请教修炼心得。",
    ],
    "resting": [
        "{name}在灵泉中疗伤恢复。",
        "{name}服下丹药，闭目养神。",
        "{name}在仙鹤背上歇息。",
    ],
    "sick": [
        "{name}中了毒，面色苍白。",
        "{name}旧伤复发，不得不停下修炼。",
    ],
}

FACTION_NAMES = ["青云宗", "天剑门", "万妖谷", "丹鼎阁", "散修联盟", "九幽宫", "紫霄殿"]
FACTION_COLORS = ["#7B68EE", "#00CED1", "#FF4500", "#FFD700", "#90EE90", "#8B0000", "#9370DB"]

TILE_NAMES = {
    "城市": ["仙城", "坊市", "宗门驻地", "灵石矿场"],
    "平原": ["灵田", "草原", "练功场"],
    "山地": ["仙山", "灵脉", "绝壁悬崖", "仙人洞府"],
    "森林": ["灵木林", "竹林", "药园"],
    "水域": ["灵泉", "仙湖", "天河"],
    "沙漠": ["死亡荒漠", "炼狱沙海"],
    "遗迹": ["上古遗迹", "仙人墓", "古战场"],
}
