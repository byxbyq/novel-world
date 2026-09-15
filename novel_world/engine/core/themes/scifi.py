# -*- coding: utf-8 -*-
"""
星际世界观模板 - 科幻太空
"""

MAP_SIZE = (50, 30)

TILE_TYPES = ["平原", "城市", "水域", "山地", "沙漠", "遗迹", "空间站"]
TILE_WEIGHTS = [10, 15, 10, 12, 15, 18, 20]

NAME_POOL = {
    "男": ["凯尔", "诺亚", "雷克斯", "赛斯", "艾登", "杰森", "卢卡斯", "马库斯", "奥利弗", "塞拉斯",
           "星河", "天翼", "银河", "烈焰", "雷霆", "暗影", "星辰", "曙光", "猎鹰", "黑鹰"],
    "女": ["艾拉", "露娜", "艾娃", "妮可", "奥拉", "塞拉", "莉娜", "诺娃", "星尘", "银河",
           "晨曦", "星云", "彗星", "极光", "暗星", "银翼", "流星", "月华", "星辉", "夜鹰"],
}

# 飞船/科技等级
TECH_LEVELS = ["民用级", "军用级", "星际级", "超光速", "维度级"]

EVENT_TEMPLATES = [
    {"type": "虫洞发现", "desc": "{name}发现了一个未知虫洞！", "weight": 3,
     "condition": "exploring", "attr_change": {"科技": 15}},
    {"type": "星际战争", "desc": "{faction}舰队与敌方爆发交战！", "weight": 5,
     "condition": "fighting", "attr_change": {"声望": 10}},
    {"type": "外星接触", "desc": "{name}首次与未知文明建立了联系。", "weight": 2,
     "condition": "exploring", "attr_change": {"科技": 20, "声望": 15}},
    {"type": "引擎升级", "desc": "{name}成功研发了新型引擎！", "weight": 4,
     "condition": "working", "attr_change": {"科技": 12}},
    {"type": "太空站被袭", "desc": "海盗突袭了{place}太空站！", "weight": 4,
     "condition": "any", "attr_change": {"财富": -20}},
    {"type": "资源发现", "desc": "在小行星带发现了稀有矿脉！", "weight": 5,
     "condition": "exploring", "attr_change": {"财富": 25}},
    {"type": "AI叛乱", "desc": "{place}的空间站AI突然失控！", "weight": 2,
     "condition": "any", "attr_change": {}},
    {"type": "基因改造", "desc": "{name}完成了基因强化手术。", "weight": 3,
     "condition": "working", "attr_change": {"力量": 10, "智慧": 5}},
    {"type": "星际贸易", "desc": "{name}完成了一笔跨星系的大交易！", "weight": 5,
     "condition": "working", "attr_change": {"财富": 20, "声望": 5}},
    {"type": "飞船故障", "desc": "{name}的飞船在太空中出现了故障...", "weight": 4,
     "condition": "moving", "attr_change": {"财富": -10}},
    {"type": "新星爆发", "desc": "附近一颗恒星进入超新星阶段！", "weight": 1,
     "condition": "any", "attr_change": {}},
    {"type": "殖民成功", "desc": "{faction}成功殖民了一颗新行星！", "weight": 3,
     "condition": "any", "attr_change": {"声望": 20, "财富": 15}},
]

STORY_TEMPLATES = {
    "idle": [
        "{name}在空间站上俯瞰星空。",
        "{name}在休眠舱中度过漫长旅途。",
        "{name}在飞船甲板上喝着合成咖啡。",
        "{name}检查着飞船的各项仪表。",
        "{name}透过舷窗看着远方的星云。",
    ],
    "working": [
        "{name}在实验室研究新型合金。",
        "{name}在控制中心监控星系扫描。",
        "{name}在维修舱修理飞船引擎。",
        "{name}编写着星际导航的AI程序。",
    ],
    "moving": [
        "{name}驾驶飞船跃迁到了{place}星系。",
        "{name}穿越虫洞，进入了未知空间。",
        "{name}的飞船在小行星带中穿行。",
    ],
    "fighting": [
        "{name}启动了武器系统，准备战斗！",
        "{name}的舰队与敌人在太空中交锋！",
        "激光炮火划过星空，{name}全力应战！",
    ],
    "exploring": [
        "{name}登陆了一颗未知行星。",
        "{name}在废弃空间站中搜寻线索。",
        "{name}探测到了一个神秘的信号源。",
        "{name}发现了一艘远古文明的飞船残骸。",
    ],
    "talking": [
        "{name}通过量子通讯与{place}基地联络。",
        "{name}在星际会议中发表意见。",
        "{name}和外星使者进行了首次交流。",
    ],
    "resting": [
        "{name}在空间站的人工重力区慢跑。",
        "{name}享受了一次零重力漂浮。",
        "{name}在生态舱中看着植物发呆。",
    ],
    "sick": [
        "{name}受到辐射影响，身体不适。",
        "{name}感染了未知太空病毒。",
    ],
}

FACTION_NAMES = ["地球联邦", "火星共和国", "星际商会", "自由舰队", "暗星帝国", "殖民联盟", "机甲军团"]
FACTION_COLORS = ["#1E90FF", "#FF6347", "#FFD700", "#00FF7F", "#4B0082", "#FF8C00", "#DC143C"]

TILE_NAMES = {
    "城市": ["太空站", "殖民城市", "星际港口", "矿场基地"],
    "平原": ["荒原", "草原行星", "训练场"],
    "山地": ["岩石行星", "环形山", "峡谷"],
    "水域": ["冰洋", "液态甲烷湖", "水下基地"],
    "沙漠": ["沙漠行星", "沙暴区", "红色荒漠"],
    "遗迹": ["远古遗迹", "废弃空间站", "文明废墟"],
    "空间站": ["空间站", "星际港口", "补给站", "研究站"],
}
