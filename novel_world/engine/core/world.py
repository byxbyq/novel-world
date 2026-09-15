"""
世界和地块系统 - 地图、势力、世界状态
"""
from dataclasses import dataclass, field
from enum import Enum
import random
import uuid


class TileType(Enum):
    PLAIN = "平原"
    MOUNTAIN = "山脉"
    WATER = "水域"
    CITY = "城市"
    FOREST = "森林"
    DESERT = "沙漠"
    RUIN = "遗迹"
    SPACE_STATION = "空间站"
    VOLCANO = "火山"
    SWAMP = "沼泽"
    SNOW = "雪地"
    ISLAND = "岛屿"


@dataclass
class Tile:
    x: int = 0
    y: int = 0
    tile_type: TileType = TileType.PLAIN
    faction_id: str = ""
    resources: dict = field(default_factory=lambda: {"food": 0, "material": 0, "energy": 0})
    name: str = ""
    description: str = ""

    def to_dict(self):
        return {
            "x": self.x, "y": self.y,
            "tile_type": self.tile_type.value,
            "faction_id": self.faction_id,
            "resources": self.resources,
            "name": self.name,
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, data):
        return cls(
            x=data["x"], y=data["y"],
            tile_type=TileType(data["tile_type"]),
            faction_id=data.get("faction_id", ""),
            resources=data.get("resources", {}),
            name=data.get("name", ""),
            description=data.get("description", ""),
        )


@dataclass
class FactionGoal:
    """势力目标（修复四：Faction 势力目标）

    每个势力可以有多个目标，用于驱动势力的集体行为。
    """
    description: str            # 目标描述，如"集结反抗军""镇压人族叛乱"
    progress: float = 0.0       # 进度 0.0 ~ 1.0
    weight: float = 1.0         # 调度权重


@dataclass
class Faction:
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    name: str = "未命名势力"
    color: str = "#FFFFFF"
    member_ids: list = field(default_factory=list)
    resources: dict = field(default_factory=lambda: {"gold": 100, "food": 50})
    territory: list = field(default_factory=list)
    leader_id: str = ""
    description: str = ""
    goals: list = field(default_factory=list)  # List[FactionGoal] — 势力目标（修复四）
    enemies: list = field(default_factory=list)  # 敌对势力名列表（phase2_p1）
    allies: list = field(default_factory=list)   # 同盟势力名列表（phase2_p1）
    controlled_resources: list = field(default_factory=list)  # 控制的资源名（phase2_p1）

    # ── 关系查询辅助方法 ──

    def is_enemy_of(self, other_name: str) -> bool:
        """检查对方是否为敌对势力"""
        return other_name in self.enemies

    def is_ally_of(self, other_name: str) -> bool:
        """检查对方是否为同盟势力"""
        return other_name in self.allies

    def add_enemy(self, enemy_name: str):
        """添加敌对势力，同时设置双向敌对"""
        if enemy_name and enemy_name not in self.enemies and enemy_name != self.name:
            self.enemies.append(enemy_name)
            # 如果对方也在 allies 中，移除
            if enemy_name in self.allies:
                self.allies.remove(enemy_name)

    def add_ally(self, ally_name: str):
        """添加同盟势力，同时设置双向同盟"""
        if ally_name and ally_name not in self.allies and ally_name != self.name:
            self.allies.append(ally_name)
            if ally_name in self.enemies:
                self.enemies.remove(ally_name)

    def remove_relation(self, target_name: str):
        """移除与目标势力的所有关系"""
        if target_name in self.enemies:
            self.enemies.remove(target_name)
        if target_name in self.allies:
            self.allies.remove(target_name)

    def member_count(self) -> int:
        """返回成员数"""
        return len(self.member_ids)

    def to_dict(self):
        return {
            "id": self.id, "name": self.name, "color": self.color,
            "member_ids": self.member_ids, "resources": self.resources,
            "territory": self.territory, "leader_id": self.leader_id,
            "description": self.description,
            "goals": [
                {"description": g.description, "progress": g.progress, "weight": g.weight}
                if hasattr(g, "description") else g
                for g in self.goals
            ],
            "enemies": self.enemies,
            "allies": self.allies,
            "controlled_resources": self.controlled_resources,
        }

    @classmethod
    def from_dict(cls, data):
        instance = cls(
            id=data["id"], name=data["name"], color=data.get("color", "#FFFFFF"),
            member_ids=data.get("member_ids", []), resources=data.get("resources", {}),
            territory=data.get("territory", []), leader_id=data.get("leader_id", ""),
            description=data.get("description", ""),
            enemies=data.get("enemies", []),
            allies=data.get("allies", []),
            controlled_resources=data.get("controlled_resources", []),
        )
        # 反序列化势力目标（修复四）
        for gd in data.get("goals", []):
            if isinstance(gd, dict):
                instance.goals.append(FactionGoal(
                    description=gd.get("description", ""),
                    progress=gd.get("progress", 0.0),
                    weight=gd.get("weight", 1.0),
                ))
            elif hasattr(gd, "description"):
                instance.goals.append(gd)
        return instance


class World:
    def __init__(self, theme="日常", map_size=(40, 25)):
        self.tiles: dict = {}
        self.characters: list = []
        self.factions: dict = {}
        self.current_time: int = 0
        self.map_size: tuple = map_size
        self.theme: str = theme
        self.story_log: list = []
        self.event_log: list = []
        self.trigger_states: dict = {}  # TRIGGER_变量存储，用于控制剧情线触发
        self.world_seed: int = random.randint(0, 999999)
        self.tick_count: int = 0
        self.total_events: int = 0
        self.main_objective: str = ""  # 世界级主线目标

        # I2: 地脉灵机强度 {(x, y): intensity}
        self.spiritual_energy: dict = {}

        # I3: 区域监控状态 {(x, y): {controller: faction_name, intensity: 0-100}}
        self.zone_monitoring: dict = {}

    _CITY_NAMES = {
        "日常": ["老城街","县城中学","人民医院","南街市场","江边公园","县政府大院","火车站广场","北街巷子","中山路","建设路","新区小区","十字街口"],
        "修仙": ["天机城","凌霄城","灵山","幽冥谷","落星崖","万妖山","紫霄宫","雷火台","丹霞峰","天元城"],
        "科幻": ["空间站Alpha","殖民前哨","矿星基地","星际港口","AI核心","星环城","量子站"],
        "奇幻": ["艾尔文城","暗影堡","龙巢","精灵之森","矮人铁堡","亡灵之地","银月城"],
        "末世": ["幸存者基地","废弃医院","辐射区","军事堡垒","避难所","补给站"],
        "恐怖": ["无名镇","深山古宅","废弃教堂","迷雾森林","血月庄园"],
        "神": ["奥林匹斯","阿斯加德","天庭","冥界入口","命运神殿"],
    }
    _RUIN_NAMES = ["古战场","迷雾废墟","沉没之城","龙骨荒原","失落神殿","千年古墓","坍塌塔楼","遗忘洞穴"]
    _VOLCANO_NAMES = ["烈焰山","熔岩之巅","怒火岭","炽天使峰","灰烬谷","永燃之口"]
    _REGION_NAMES = {
        "日常": ["单位楼前","小区大门","贡江大桥","街尾河边","学校操场","卖菜摄旁","街头理发店","超市后门","公交站牌子下","小区车棚","父母家楼下","加油站"],
        "修仙": ["灵气洞天","剑意峰","药王谷","雷泽","幽冥海域","仙人渡"],
        "科幻": ["星际矿场","暗物质区","能量风暴带","虫洞边缘","星际航道"],
        "奇幻": ["巨龙荒野","精灵花园","矮人熔炉","亡灵沼泽","魔法源泉"],
        "末世": ["辐射荒原","感染区","无人之地","废墟走廊","死亡公路"],
        "恐怖": ["诡异林区","寂静岭","无底深渊","噩梦回廊","血色彼岸"],
        "神": ["彩虹桥","命运之河","混沌虚空","永恒之泉","雷霆平原"],
    }
    _PLACE_NAMES = {
        "日常": ["煮君小店","早餐摄","草坦理发店","快递站","街头小卖部","草席摄","小区门口","街边排档","小学校门口","小区花坛","超市后门","街心广场","单位楼下","家门口","车库旁","集市口","药房","图书馆","网吧","废品收购站","干洗店","加油站","小学旁","医院偏门","客车站","河边石板","体育场","篮球场","县工会","街头下棋处","购物中心","烟酒店"],
        "修仙": ["修炼场","灵药园","参惟堂","荒山小径","悬崖边","破庙","古树下"],
        "奇幻": ["魔法塔","精灵泉","古战场","祭坛"],
        "末世": ["废境","破的商店","沙袋阵地","废弃加油站"],
        "科幻": ["能量站","实验室","传送门","观测站"],
        "恐怖": ["废弃医院","阴暗巷子","古老公墓"],
    }


    def generate_map(self, theme_config=None, name_config=None):
        """
        生成地图。

        Args:
            theme_config: 主题配置，含 tile_types / tile_weights 等
            name_config:  外部命名配置，可覆盖类级 _CITY_NAMES / _RUIN_NAMES 等。
                          结构：{
                              "city_names": {...},
                              "ruin_names": [...],
                              "volcano_names": [...],
                              "region_names": {...},
                              "place_names": {...},
                          }
                          不传则使用类级默认值。
        """
        # 允许外部 YAML 配置覆盖命名池
        city_names = self._CITY_NAMES
        ruin_names = self._RUIN_NAMES
        volcano_names = self._VOLCANO_NAMES
        region_names = self._REGION_NAMES
        place_names = self._PLACE_NAMES
        if name_config:
            if "city_names" in name_config:
                city_names = name_config["city_names"]
            if "ruin_names" in name_config:
                ruin_names = name_config["ruin_names"]
            if "volcano_names" in name_config:
                volcano_names = name_config["volcano_names"]
            if "region_names" in name_config:
                region_names = name_config["region_names"]
            if "place_names" in name_config:
                place_names = name_config["place_names"]

        w, h = self.map_size
        tile_types = [TileType.PLAIN]
        weights = [1.0]
        if theme_config and "tile_types" in theme_config:
            tile_types = [TileType(t) for t in theme_config["tile_types"]]
            weights = theme_config.get("tile_weights", [1.0] * len(tile_types))
        for y in range(h):
            for x in range(w):
                tt = random.choices(tile_types, weights=weights, k=1)[0]
                tile = Tile(x=x, y=y, tile_type=tt)
                if tt == TileType.CITY:
                    tile.resources = {"food": random.randint(20, 60), "material": random.randint(30, 80), "energy": random.randint(10, 40)}
                elif tt == TileType.FOREST:
                    tile.resources = {"food": random.randint(10, 40), "material": random.randint(20, 50), "energy": 0}
                elif tt == TileType.MOUNTAIN:
                    tile.resources = {"food": random.randint(0, 10), "material": random.randint(30, 70), "energy": 0}
                elif tt == TileType.WATER:
                    tile.resources = {"food": random.randint(15, 45), "material": 0, "energy": 0}
                elif tt == TileType.DESERT:
                    tile.resources = {"food": 0, "material": random.randint(5, 15), "energy": random.randint(20, 60)}
                elif tt == TileType.RUIN:
                    tile.resources = {"food": 0, "material": random.randint(10, 30), "energy": random.randint(5, 20)}
                else:
                    tile.resources = {"food": random.randint(5, 20), "material": random.randint(5, 20), "energy": 0}
                self.tiles[(x, y)] = tile

        # 给特殊地形和部分区域生成名字
        import random as _rng
        used_names = set()
        for (tx, ty), tile in self.tiles.items():
            if tile.tile_type == TileType.CITY:
                names = city_names.get(self.theme, city_names["日常"])
                available = [n for n in names if n not in used_names]
                if available:
                    tile.name = _rng.choice(available)
                    used_names.add(tile.name)
                else:
                    tile.name = f"城镇{tx},{ty}"
            elif tile.tile_type == TileType.RUIN:
                available = [n for n in ruin_names if n not in used_names]
                if available:
                    tile.name = _rng.choice(available)
                    used_names.add(tile.name)
            elif tile.tile_type == TileType.VOLCANO:
                available = [n for n in volcano_names if n not in used_names]
                if available:
                    tile.name = _rng.choice(available)
                    used_names.add(tile.name)
            elif tile.tile_type in (TileType.MOUNTAIN, TileType.FOREST, TileType.SWAMP,
                                    TileType.SNOW, TileType.ISLAND, TileType.DESERT,
                                    TileType.SPACE_STATION):
                if _rng.random() < 0.08:
                    names = region_names.get(self.theme, region_names["日常"])
                    available = [n for n in names if n not in used_names]
                    if available:
                        tile.name = _rng.choice(available)
                        used_names.add(tile.name)

    
        # 给未命名的普通地块也分配地名
        pn_pool = place_names.get(self.theme, place_names["日常"])
        place_used = {tile.name for tile in self.tiles.values() if tile.name}
        for tile in self.tiles.values():
            if not tile.name or tile.tile_type.value in tile.name:
                available = [n for n in pn_pool if n not in place_used]
                if available:
                    tile.name = _rng.choice(available)
                    place_used.add(tile.name)

    
    def _generate_tile_names(self):
        """Give names to tiles"""
        import random as _rng
        used = set()
        for tile in self.tiles.values():
            if tile.tile_type == TileType.CITY:
                names = self._CITY_NAMES.get(self.theme, self._CITY_NAMES["\u65e5\u5e38"])
                available = [n for n in names if n not in used]
                if available:
                    tile.name = _rng.choice(available)
                    used.add(tile.name)
                else:
                    tile.name = "\u57ce\u9547" + str(tile.x) + "," + str(tile.y)
            elif tile.tile_type == TileType.RUIN:
                names = self._REGION_NAMES.get(self.theme, self._REGION_NAMES["\u65e5\u5e38"])
                available = [n for n in names if n not in used]
                if available:
                    tile.name = _rng.choice(available)
                    used.add(tile.name)
            elif tile.tile_type == TileType.VOLCANO:
                names = self._REGION_NAMES.get(self.theme, self._REGION_NAMES["\u65e5\u5e38"])
                available = [n for n in names if n not in used]
                if available:
                    tile.name = _rng.choice(available)
                    used.add(tile.name)
        # Name unnamed tiles with PLACE_NAMES
        place_names = self._PLACE_NAMES.get(self.theme, self._PLACE_NAMES["\u65e5\u5e38"])
        place_used = {tile.name for tile in self.tiles.values() if tile.name}
        for tile in self.tiles.values():
            if not tile.name:
                available = [n for n in place_names if n not in place_used]
                if available:
                    tile.name = _rng.choice(available)
                    place_used.add(tile.name)

    def get_tile(self, x, y):
        return self.tiles.get((x, y))

    def get_characters_at(self, x, y):
        return [c for c in self.characters if c.pos == (x, y) and c.alive]

    def get_faction_members(self, faction_id):
        return [c for c in self.characters if c.faction_id == faction_id and c.alive]

    def get_faction(self, faction_id):
        return self.factions.get(faction_id)

    def add_faction(self, faction):
        self.factions[faction.id] = faction

    def remove_faction(self, faction_id):
        self.factions.pop(faction_id, None)

    def get_faction_by_name(self, name: str):
        """按名称查找势力"""
        for f in self.factions.values():
            if f.name == name:
                return f
        return None

    def set_faction_enemies(self, faction_a_id: str, faction_b_id: str):
        """双向设置两个势力为敌对"""
        fa = self.factions.get(faction_a_id)
        fb = self.factions.get(faction_b_id)
        if fa and fb:
            fa.add_enemy(fb.name)
            fb.add_enemy(fa.name)

    def set_faction_allies(self, faction_a_id: str, faction_b_id: str):
        """双向设置两个势力为同盟"""
        fa = self.factions.get(faction_a_id)
        fb = self.factions.get(faction_b_id)
        if fa and fb:
            fa.add_ally(fb.name)
            fb.add_ally(fa.name)

    def detect_faction_overlap_resources(self, faction_a_id: str, faction_b_id: str) -> list:
        """检测两个势力之间的共同资源/领地"""
        fa = self.factions.get(faction_a_id)
        fb = self.factions.get(faction_b_id)
        if not fa or not fb:
            return []
        overlaps = []
        # 领地重叠
        common_territory = set(fa.territory) & set(fb.territory)
        if common_territory:
            overlaps.append(f"领地重叠: {', '.join(common_territory)}")
        # 控制资源重叠
        common_resources = set(fa.controlled_resources) & set(fb.controlled_resources)
        if common_resources:
            overlaps.append(f"资源争夺: {', '.join(common_resources)}")
        # 目标冲突检测（关键词匹配）
        fa_texts = " ".join(
            g.description if hasattr(g, "description") else str(g)
            for g in fa.goals
        )
        fb_texts = " ".join(
            g.description if hasattr(g, "description") else str(g)
            for g in fb.goals
        )
        if fa.name in fb_texts or fb.name in fa_texts:
            overlaps.append("目标提及对方势力")
        return overlaps

    def add_character(self, character):
        self.characters.append(character)

    def get_neighbors(self, x, y, radius=1):
        result = []
        for dx in range(-radius, radius + 1):
            for dy in range(-radius, radius + 1):
                if dx == 0 and dy == 0:
                    continue
                nx, ny = x + dx, y + dy
                tile = self.tiles.get((nx, ny))
                if tile:
                    result.append(tile)
        return result

    def to_dict(self):
        return {
            "theme": self.theme,
            "map_size": self.map_size,
            "current_time": self.current_time,
            "world_seed": self.world_seed,
            "tiles": {f"{k[0]},{k[1]}": v.to_dict() for k, v in self.tiles.items()},
            "factions": {k: v.to_dict() for k, v in self.factions.items()},
            "story_log": self.story_log[-200:],
            "event_log": self.event_log[-100:],
            "trigger_states": self.trigger_states,
        }
    def get_random_faction_name(self) -> str:
        """随机获取一个势力名称"""
        if not self.factions:
            return ""
        return random.choice(list(self.factions.values())).name

    def align_faction_goals(self, main_objective: str):
        """根据世界主线目标，为每个势力生成贴合主线的势力目标（修复四：Faction 势力目标）。

        例如：主线="人族推翻魔朝" →
            - 人族势力目标="集结反抗军"
            - 魔族势力目标="镇压人族叛乱"

        Args:
            main_objective: 世界主线目标文本。
        """
        if not main_objective or not self.factions:
            return

        for faction in self.factions.values():
            from novel_world.engine.core.prompt_registry import PromptRegistry
            prompt = PromptRegistry.get(
                "faction_goals_user",
                main_objective=main_objective,
                faction_name=faction.name,
                faction_description=faction.description,
                faction_resources=faction.resources,
            )
            try:
                from ai_client import chat  # 延迟导入避免循环依赖
                response = chat(
                    system_prompt=PromptRegistry.get_raw("faction_goals_system"),
                    user_prompt=prompt,
                    temperature=0.7,
                )
                # 清除旧目标，设置新目标
                faction.goals = []
                for line in response.strip().split("\n"):
                    line = line.strip().lstrip("0123456789. -·")
                    if line and len(line) >= 3:
                        faction.goals.append(FactionGoal(description=line))
            except Exception:
                # AI 调用失败时给默认目标
                faction.goals = [
                    FactionGoal(description=f"对'{main_objective}'做出反应"),
                ]

    def faction_goals_text(self) -> str:
        """生成所有势力的目标文本摘要（供 generate_world_event 注入 prompt，修复四）。"""
        lines = []
        for faction in self.factions.values():
            if faction.goals:
                lines.append(f"【{faction.name}】")
                for g in faction.goals:
                    lines.append(f"  - {g.description} (进度: {g.progress:.0%})")
        return "\n".join(lines) if lines else "（无势力目标）"

    # ── 资源-地域联动（phase2_p2）──

    # 通用资源关键词 → 标准资源类型映射
    _RESOURCE_KEYWORD_MAP = {
        # 食物类
        "粮食": "food", "食物": "food", "食品": "food", "灵果": "food", "丹药": "food",
        "药材": "food", "草药": "food", "灵石": "food", "灵草": "food", "仙果": "food",
        # 材料类
        "矿石": "material", "灵石": "material", "铁矿": "material", "金矿": "material",
        "木材": "material", "石料": "material", "晶石": "material", "灵矿": "material",
        "魔晶": "material", "宝石": "material", "陨铁": "material",
        # 能量类
        "灵气": "energy", "魔力": "energy", "能量": "energy", "灵力": "energy",
        "法力": "energy", "仙气": "energy", "元素": "energy", "核能": "energy",
        # 特殊类
        "秘籍": "special", "法宝": "special", "神器": "special", "卷轴": "special",
        "圣物": "special", "遗物": "special", "权杖": "special", "王冠": "special",
    }

    def get_resource_location(self, resource_name: str):
        """查询某资源在哪个地块（按名称或类型匹配）。

        Args:
            resource_name: 资源关键词（如 "灵石"、"粮食"、"秘籍"）

        Returns:
            包含该资源的地块 Tile 对象，未找到返回 None
        """
        # 标准化：转小写
        key = resource_name.lower().strip()

        # 1. 精确匹配 tile 名称中的资源关键词
        for tile in self.tiles.values():
            if tile.name and key in tile.name.lower():
                return tile

        # 2. 匹配资源类型
        res_type = self._RESOURCE_KEYWORD_MAP.get(resource_name)
        if res_type is None:
            res_type = self._RESOURCE_KEYWORD_MAP.get(key)
        if res_type is None:
            # 尝试模糊匹配
            for kw, rt in self._RESOURCE_KEYWORD_MAP.items():
                if kw in key or key in kw:
                    res_type = rt
                    break

        if res_type:
            # 先找有命名的高资源 tile
            best = None
            best_val = 0
            for tile in self.tiles.values():
                val = tile.resources.get(res_type, 0)
                if val > best_val:
                    best_val = val
                    best = tile
                elif val == best_val and best and not best.name and tile.name:
                    best = tile  # 有名字的优先
            if best and best_val > 0:
                return best

        # 3. 模糊匹配 tile 名称
        for tile in self.tiles.values():
            if tile.name and any(kw in tile.name.lower() for kw in key.split()):
                return tile

        return None

    def get_tile_by_name(self, name: str):
        """按名称查找地块"""
        for tile in self.tiles.values():
            if tile.name == name:
                return tile
        return None

    # ══════════════════════════════════════
    # I2: 地脉灵机强度
    # ══════════════════════════════════════
    def set_spiritual_energy(self, x: int, y: int, intensity: int):
        """设置指定位置的地脉灵机强度（0-100）"""
        self.spiritual_energy[(x, y)] = max(0, min(100, intensity))

    def get_spiritual_energy(self, x: int, y: int) -> int:
        """获取指定位置的地脉灵机强度"""
        return self.spiritual_energy.get((x, y), 0)

    def apply_aura_tide(self, center: tuple, radius: int, modifier: float):
        """灵气潮汐效果：以 center 为中心 radius 范围内能量 *= modifier"""
        cx, cy = center
        for (x, y) in list(self.spiritual_energy.keys()):
            if abs(x - cx) <= radius and abs(y - cy) <= radius:
                new_val = int(self.spiritual_energy[(x, y)] * modifier)
                self.spiritual_energy[(x, y)] = max(0, min(100, new_val))

    # ══════════════════════════════════════
    # I3: 区域监控状态
    # ══════════════════════════════════════
    def set_zone_monitoring(self, x: int, y: int,
                            controller: str, intensity: int = 50):
        """设置某位置的区域监控"""
        self.zone_monitoring[(x, y)] = {
            "controller": controller,
            "intensity": max(0, min(100, intensity)),
        }

    def get_zone_monitoring(self, x: int, y: int) -> dict:
        """获取某位置的区域监控状态"""
        return self.zone_monitoring.get((x, y), {})

    def refresh_zone_monitoring(self):
        """每慢Tick衰减所有区域监控强度 (-5)"""
        to_remove = []
        for pos, data in self.zone_monitoring.items():
            data["intensity"] = max(0, data["intensity"] - 5)
            if data["intensity"] <= 0:
                to_remove.append(pos)
        for pos in to_remove:
            del self.zone_monitoring[pos]