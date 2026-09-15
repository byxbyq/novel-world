"""剧情生成器 - 纯规则模板，不调用AI"""
import random
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from .world import World
    from .events import Event
    from .character import Character


class StoryGenerator:
    """基于模板的剧情生成器"""

    def __init__(self, theme: str = "日常"):
        self.theme = theme
        self.templates = []
        self._load_templates()

    def _load_templates(self):
        if self.theme == "日常":
            self.templates = [
                "{name}今天在{place}遇到了{thing}，{reaction}。",
                "{name}决定{action}，感觉{feeling}。",
                "第{time}天，{name}的{attr}提升了。",
                "{name}和{other}一起去了{place}，{result}。",
                "{name}在家休息了一天，恢复了{num}点体力。",
                "天气变化，{name}去了附近的{place}。",
            ]
        elif self.theme == "修仙":
            self.templates = [
                "{name}在{place}闭关修炼，{result}。",
                "第{time}天，{name}的修为精进了一步。",
                "{name}遭遇{enemy}，激战后{result}。",
                "{name}感悟天地法则，{reaction}。",
                "仙门大比将至，{name}正在积极备战。",
                "{name}在{place}发现了一株灵药，{result}。",
            ]
        elif self.theme == "星际":
            self.templates = [
                "{name}率领舰队前往{place}进行探索。",
                "第{time}天，{faction}的殖民地{result}。",
                "{name}在{place}遭遇了未知信号，{reaction}。",
                "星际贸易繁荣，{name}获得了{num}单位的资源。",
                "{name}研究了新型武器系统，{result}。",
            ]
        elif self.theme == "奇幻":
            self.templates = [
                "{name}踏上了前往{place}的冒险之旅。",
                "在{place}，{name}遇到了{enemy}，{result}。",
                "{name}从商人那里购买了{thing}。",
                "第{time}天，{name}的等级提升了。",
                "{name}在酒馆听到了关于{thing}的传闻。",
            ]
        elif self.theme == "末世":
            self.templates = [
                "{name}在废墟中搜索，找到了{thing}。",
                "第{time}天，幸存者们{result}。",
                "一波威胁逼近，{name}决定{action}。",
                "{name}的物资消耗殆尽，必须外出搜寻。",
                "通讯设备收到了一段求救信号，来自{place}。",
            ]
        elif self.theme == "诡异":
            self.templates = [
                "{name}在{place}看到了不该看的东西，{reaction}。",
                "第{time}天，{place}发生了无法解释的事件。",
                "{name}的理智值下降了{num}点，{result}。",
                "奇怪的符号出现在{name}面前，{reaction}。",
                "{name}决定调查{place}的秘密，{result}。",
            ]
        elif self.theme == "神话":
            self.templates = [
                "{name}受到了神谕指引，前往{place}。",
                "第{time}天，{name}完成了神的试炼，{result}。",
                "神器{thing}显露出新的力量。",
                "{name}与众神之{enemy}交战，{result}。",
                "命运之轮转动，{name}的使命{reaction}。",
            ]
        else:
            self.templates = [
                "{name}进行了{action}，{result}。",
                "第{time}天，世界{reaction}。",
            ]

    def generate(self, world: 'World', events: list = None) -> str:
        """生成一段短剧情（10-20字）"""
        if not self.templates:
            return "世界继续运转..."

        chars = [c for c in world.characters if c.alive]
        if not chars:
            return "世界一片寂静。"

        template = random.choice(self.templates)

        name = random.choice(chars).name
        other = random.choice([c for c in chars if c.name != name]).name if len(chars) > 1 else "某人"

        # 随机填充变量
        places = ["市场", "森林", "河边", "广场", "城堡", "村落", "洞穴", "山顶", "平原", "地下城"]
        if self.theme == "修仙":
            places = ["洞府", "仙山", "宗门", "秘境", "坊市", "丹房", "藏经阁"]
        elif self.theme == "星际":
            places = ["空间站", "星球表面", "虫洞附近", "殖民地", "废弃飞船"]
        elif self.theme == "末世":
            places = ["废墟", "超市", "地下室", "公路", "军事基地"]
        elif self.theme == "诡异":
            places = ["废弃医院", "老宅", "墓地", "地下隧道", "迷雾森林"]

        reactions = ["心中一动", "若有所思", "暗自警惕", "充满期待", "感到不安"]
        results = ["收获颇丰", "一无所获", "险象环生", "化险为夷", "得到了启发"]
        actions = ["外出探索", "修炼休息", "结交朋友", "收集资源", "建造设施"]
        feelings = ["精力充沛", "略有疲惫", "心情愉悦", "若有所失"]
        enemies = ["哥布林", "强盗", "妖兽", "亡灵", "海盗", "暗影", "巨龙"]
        things = ["稀有宝物", "神秘卷轴", "强力武器", "古老地图", "珍贵矿石"]

        try:
            text = template.format(
                name=name,
                other=other,
                time=str(world.current_time),
                place=random.choice(places),
                reaction=random.choice(reactions),
                result=random.choice(results),
                action=random.choice(actions),
                feeling=random.choice(feelings),
                enemy=random.choice(enemies),
                thing=random.choice(things),
                num=str(random.randint(1, 10)),
                attr=random.choice(["智力", "体力", "声望", "魅力"]),
                faction=world.get_random_faction_name() or "某个势力",
            )
        except (KeyError, ValueError):
            text = f"第{world.current_time}天，{name}在探索中。"

        # 截断到20字以内
        if len(text) > 25:
            text = text[:22] + "..."

        return text
