"""Engine 生命周期 Mixin — 初始化/存档/导出"""
import os
import random
import logging

from ..world import World, Faction
from ..character import Character, CharType, generate_random_character
from ..events import NarrativeEngine
from ..story import StoryGenerator
from ..rule_validator import RuleValidator
from ..item_system import ItemValidator, get_item_manager
from ..narrative_corrector import NarrativeCorrector
from ..dialogue_system import get_dialogue_system

logger = logging.getLogger(__name__)

class LifecycleMixin:
    """__init__ / save / export_story / 角色/势力创建"""


    def __init__(self, settings: dict = None, ai_client: 'AIClient' = None,
                 theme=None, map_size=None, protagonist_name=None,
                 antagonist_enabled=None, antagonist_name=None,
                 npc_count=None, ai_settings=None):
        # 兼容前端的关键字参数调用
        if settings is None:
            settings = {}
            if theme:
                settings["theme"] = theme
            if map_size:
                settings["map_size"] = map_size
            if protagonist_name:
                settings["hero_name"] = protagonist_name
            if antagonist_name is not None:
                settings["villain_enabled"] = antagonist_enabled if antagonist_enabled is not None else True
                settings["villain_name"] = antagonist_name
            if npc_count is not None:
                settings["npc_count"] = npc_count
            if ai_settings:
                settings.update(ai_settings)
        self.running = True
        self.speed = 1
        self.ai_interval = settings.get("ai_interval", 5)
        self._ai_busy = False
        self.ai_config = {
            "world_desc": settings.get("world_desc", ""),
            "world_rules": settings.get("world_rules", ""),
            "story": settings.get("story_enabled", True),
            "local_model": settings.get("local_model", ""),
        }

        # AI \u5ba2\u6237\u7aef
        provider_map = {0: "local", 1: "api", 2: "none"}
        if ai_client:
            self.ai = ai_client
        else:
            from .ai_client import AIClient
            provider_map = {0: "local", 1: "api", 2: "none"}
            provider_val = settings.get("ai_provider", 0)
            self.ai = AIClient(
                provider=provider_map.get(provider_val, "local"),
                api_url=settings.get("api_url", ""),
                api_key=settings.get("api_key", ""),
                api_model=settings.get("api_model", ""),
                local_model_path=self.ai_config.get("local_model", ""),
            )
  # \u4e0d\u5728\u8fd9\u91cc\u521b\u5efa\uff0c\u7531\u5916\u90e8\u4f20\u5165

        # \u4e16\u754c
        self.theme = settings.get("theme", "\u65e5\u5e38")
        
        # === 存储主线剧情信息（关键！） ===
        self.plot = settings.get("plot", {})
        if self.plot:
            print(f"[DEBUG] Engine 接收到主线剧情信息:")
            print(f"  start_event: {self.plot.get('start_event', '')[:50]}...")
            print(f"  core_suspense: {self.plot.get('core_suspense', '')[:50]}...")
            print(f"  subplots: {len(self.plot.get('subplots', []))} 个支线")
        
        # === 初始化游戏设定和规则 ===
        self.merged_rules = settings.get("merged_rules", {})
        self.game_config = settings.get("game_config", {})
        
        # 如果settings中没有，尝试从ai_settings中获取
        if not self.merged_rules and ai_settings:
            self.merged_rules = ai_settings.get("merged_rules", {})
        if not self.game_config and ai_settings:
            self.game_config = ai_settings.get("game_config", {})
        self.map_size = tuple(settings.get("map_size", (40, 25)))
        self.world = World(theme=self.theme, map_size=self.map_size)
        self.world.generate_map(settings.get("theme_config"))

        # 异步预加载模型，避免首次叙事卡顿
        self._model_preloaded = False
        self._story_intro_generated = False  # 故事开头是否已生成
        if self.ai and hasattr(self.ai, "provider") and self.ai.provider == "local":
            if hasattr(self.ai, 'preload_model'):
                self.ai.preload_model(callback=self._on_model_preloaded)
                self.world.story_log.append("【系统】AI 模型正在后台加载...")
        # \u53d9\u4e8b\u5f15\u64ce
        self.narrative_engine = NarrativeEngine(
            ai_client=self.ai, 
            theme=self.theme,
            merged_rules=getattr(self, 'merged_rules', None),
            game_config=getattr(self, 'game_config', None)
        )
        self.story_gen = StoryGenerator(self.theme)

        # === 叙事增强集成 ===
        try:
            from .narrative_integration_fix import integrate_improved_narrative_enhancer
            self.narrative_engine = integrate_improved_narrative_enhancer(self.narrative_engine)
        except Exception as e:
            print(f'[叙事增强] 集成失败: {e}')

        
        # 规则校验器
        self.rule_validator = RuleValidator(self)
        # 设置 world 到 narrative_engine
        if hasattr(self.narrative_engine, 'set_world'):
            self.narrative_engine.set_world(self.world)
        
        # 道具系统
        self.item_manager = get_item_manager()
        self.item_validator = ItemValidator()
        
        # 强制修正系统
        self.narrative_corrector = NarrativeCorrector()
        
        # 对话系统
        self.dialogue_system = get_dialogue_system(self.ai)

        # \u89d2\u8272
        self.protagonist = None
        self.antagonist = None

        # \u521b\u5efa\u89d2\u8272
        self._create_characters(settings)

        # \u52bf\u529b
        world_desc = settings.get("world_desc", "")
        self.world._generate_tile_names()
        self._create_default_factions(settings)

        # \u521d\u59cb\u5316\u5b8c\u6210
        self.world.story_log.append(f"\u4e16\u754c\u521b\u751f\u4e86\u3002\u4e3b\u9898\uff1a{self.theme}\u3002")


    def _on_model_preloaded(self, success):
        """模型预加载完成回调 - 生成故事开头"""
        self._model_preloaded = success
        if success:
            # 生成故事开头（基于主题和世界描述）
            intro = self._generate_story_intro()
            if intro:
                self.world.story_log.append(intro)
                self.world.story_log.append("【系统】故事开始，AI 叙事已启用。")
            self._story_intro_generated = True
        else:
            self.world.story_log.append("【系统】AI 模型加载失败，将使用模板叙事。")
            self._story_intro_generated = True


    def _generate_story_intro(self):
        """生成故事开头（基于主题和世界描述）"""
        if not self.ai or not self.ai.is_available:
            return None
        
        try:
            # 构建故事开头的提示
            theme = self.theme
            world_desc = self.ai_config.get("world_desc", "")
            
            # 获取主角和反派信息
            hero = self.protagonist
            villain = self.antagonist
            
            from novel_world.engine.core.prompt_registry import PromptRegistry

            system_prompt = PromptRegistry.get("story_intro_system", theme=theme)

            user_prompt = PromptRegistry.get(
                "story_intro_user",
                theme=theme,
                world_desc=world_desc if world_desc else "无特殊设定",
                hero_name=hero.name if hero else "无名英雄",
                hero_personality=hero.personality if hero else "",
                villain_name=villain.name if villain else "无",
                villain_personality=villain.personality if villain else "",
            )
            
            # 调用 AI 生成
            intro = self.ai.chat(system_prompt, user_prompt, max_tokens=400)
            
            # 清理输出
            if intro:
                import re
                intro = re.sub(r"<think[\s\S]*?</think\s*>", "", intro).strip()
                intro = re.sub(r"<think[\s\S]*", "", intro).strip()
                return intro
        except Exception as e:
            logging.warning(f"生成故事开头失败: {e}")
        
        return None

        return None

    def _create_characters(self, settings):
        """\u521b\u5efa\u89d2\u8272"""
        # \u4e3b\u89d2
        hero_name = settings.get("hero_name", "")
        hero_personality = settings.get("hero_personality", "")
        hero_goal = settings.get("hero_goal", "")
        hero_abilities_raw = settings.get("protagonist_abilities", "")
        hero_skills = [s.strip() for s in hero_abilities_raw.split(",") if s.strip()] if hero_abilities_raw else []
        if hero_name:
            self.protagonist = Character(
                name=hero_name,
                char_type=CharType.PROTAGONIST,
                personality=hero_personality or "\u52c7\u6562\u51b2\u52a8\u3001\u5ac9\u6076\u5982\u4ec7",
                goal=hero_goal,
                skills=hero_skills,
                fate_arc="\u521a\u521a\u8e0f\u4e0a\u5f81\u9014",
                story_state="\u5728\u51fa\u53d1\u70b9",
                gender="\u7537",
                pos=(self.map_size[0] // 4, self.map_size[1] // 2),
            )
        else:
            self.protagonist = generate_random_character(theme=self.theme)
            self.protagonist.char_type = CharType.PROTAGONIST

        self.world.add_character(self.protagonist)

        # 女主角（新增）
        heroine_enabled = settings.get("heroine_enabled", True)
        if heroine_enabled:
            heroine_name = settings.get("heroine_name", "")
            heroine_personality = settings.get("heroine_personality", "")
            heroine_goal = settings.get("heroine_goal", "")
            if heroine_name:
                self.heroine = Character(
                    name=heroine_name,
                    char_type=CharType.HEROINE,
                    personality=heroine_personality or "温柔善良、独立聪慧",
                    goal=heroine_goal or "找到真爱、实现梦想",
                    fate_arc="等待命运安排",
                    story_state="在人群中",
                    gender="女",
                    pos=(self.map_size[0] // 4 + 2, self.map_size[1] // 2),  # 在主角附近
                )
            else:
                self.heroine = generate_random_character(theme=self.theme)
                self.heroine.char_type = CharType.HEROINE
                self.heroine.gender = "女"
                self.heroine.name = "苏晚"  # 默认名字
            self.world.add_character(self.heroine)
            print(f"[OK] 女主角已创建: {self.heroine.name}")
        else:
            self.heroine = None

        # \u53cd\u6d3e
        villain_enabled = settings.get("villain_enabled", True)
        if villain_enabled:
            villain_name = settings.get("villain_name", "")
            villain_personality = settings.get("villain_personality", "")
            villain_goal = settings.get("villain_goal", "")
            if villain_name:
                self.antagonist = Character(
                    name=villain_name,
                    char_type=CharType.ANTAGONIST,
                    personality=villain_personality or "\u9634\u9669\u6df1\u6c89\u3001\u5fc3\u673a\u8bf8\u7b97",
                    goal=villain_goal or "\u963b\u6b62\u4e3b\u89d2",
                    fate_arc="\u6697\u4e2d\u89c2\u5bdf\uff0c\u7b49\u5f85\u65f6\u673a",
                    story_state="\u5728\u9634\u5f71\u4e2d",
                    gender="\u7537",
                    pos=(self.map_size[0] * 3 // 4, self.map_size[1] // 2),
                )
            else:
                self.antagonist = generate_random_character(theme=self.theme)
                self.antagonist.char_type = CharType.ANTAGONIST
            self.world.add_character(self.antagonist)
            
            # 注册反派到强制修正系统
            if hasattr(self, 'narrative_corrector'):
                # 检查反派是否不可击败
                is_undefeatable = any(kw in (self.antagonist.personality or "") 
                                     for kw in ["不可对抗", "无理智", "意志", "无法击败", "不死"])
                self.narrative_corrector.register_character(
                    self.antagonist.name,
                    personality=self.antagonist.personality,
                    role="antagonist",
                    is_undefeatable=is_undefeatable,
                    is_immortal=is_undefeatable
                )

        # NPC
        npc_count = settings.get("npc_count", 15)
        for i in range(npc_count):
            npc = generate_random_character(theme=self.theme)
            # 规则校验：检查NPC是否符合规则
            if hasattr(self, 'rule_validator'):
                is_valid, msg = self.rule_validator.validate_npc_generation(npc.name, npc.personality)
                if not is_valid:
                    # 如果校验失败，重新生成一个更独特的角色
                    import random
                    unique_names = ["云逸", "墨寒", "风清", "月白", "星河", "雪影", "霜华", "烟雨",
                                   "青竹", "白露", "紫烟", "红尘", "碧落", "苍穹", "玄冥", "凌霄"]
                    npc.name = random.choice(unique_names)
                    self.world.story_log.append(f"【系统校验】{msg}，已重新命名为 {npc.name}")
            self.world.add_character(npc)


    def _create_default_factions(self, settings):
        """\u521b\u5efa\u9ed8\u8ba4\u52bf\u529b"""
        faction_count = settings.get("faction_count", 2)
        colors = ["#4488FF", "#FF8844", "#44BB44", "#FF4466", "#AA44FF", "#44DDDD"]
        names_pool = {
            "\u65e5\u5e38": ["\u7530\u56ed\u8054\u76df", "\u98ce\u66b4\u56e2\u4f19", "\u94c1\u58c1\u5c71\u5e84"],
            "\u4fee\u4ed9": ["\u5929\u673a\u9600", "\u9b54\u9053\u5723\u6bbf", "\u5e7d\u51a5\u5b97"],
            "\u5947\u5e7b": ["\u94f6\u6708\u9a91\u58eb\u56e2", "\u6697\u5f71\u515a", "\u81ea\u7136\u4e4b\u5b50"],
            "\u672b\u4e16": ["\u6668\u5149\u57fa\u5730", "\u94c1\u62f3\u56e2\u4f53", "\u884c\u8005\u5e94\u8be5"],
            "\u79d1\u5e7b": ["\u661f\u9645\u8054\u90a6", "\u53db\u5f79\u519b", "\u81ea\u7531\u5546\u4f1a"],
            "\u6050\u6016": ["\u5b88\u591c\u4eba", "\u795e\u79d8\u8c03\u67e5\u5c40", "\u8ff7\u5e7b\u7814\u7a76\u4f1a"],
        }
        pool = names_pool.get(self.theme, names_pool["\u65e5\u5e38"])
        # 用户自定义势力名称
        custom_names_raw = settings.get("faction_names", "")
        if custom_names_raw:
            custom_names = [n.strip() for n in custom_names_raw.split("，") if n.strip()]
            if not custom_names:
                custom_names = [n.strip() for n in custom_names_raw.split(",") if n.strip()]
            if custom_names:
                pool = custom_names


        for i in range(faction_count):
            fname = pool[i] if i < len(pool) else f"\u52bf\u529b{i+1}"
            faction = Faction(
                name=fname,
                color=colors[i % len(colors)],
            )
            self.world.add_faction(faction)

        # \u5206\u914d\u89d2\u8272\u5230\u52bf\u529b
        all_fids = list(self.world.factions.keys())
        alive = [c for c in self.world.characters if c.alive]
        for c in alive:
            if c.char_type == CharType.PROTAGONIST and all_fids:
                c.faction_id = all_fids[0]
                self.world.factions[all_fids[0]].member_ids.append(c.id)
            elif c.char_type == CharType.ANTAGONIST and len(all_fids) > 1:
                c.faction_id = all_fids[1]
                self.world.factions[all_fids[1]].member_ids.append(c.id)
            elif c.char_type == CharType.NPC and all_fids:
                fid = random.choice(all_fids)
                c.faction_id = fid
                self.world.factions[fid].member_ids.append(c.id)

        # \u521d\u59cb\u5316\u52bf\u529b\u9886\u5730
        self._update_faction_territory()

        # 为多势力场景自动设置敌对关系（phase2_p1）
        if len(all_fids) >= 2:
            self.world.set_faction_enemies(all_fids[0], all_fids[1])


    def save(self):
        """\u4fdd\u5b58\u6e38\u620f\u72b6\u6001"""
        import json
        return {
            "world": self.world.to_dict(),
            "tick": self.world.tick_count,
        }

    # ---- 前端兼容方法 ----
    def set_speed(self, speed):
        self.speed = speed


    def get_tick_interval_ms(self):
        intervals = {1: 1500, 2: 800, 3: 400, 4: 150, 5: 50}
        return intervals.get(self.speed, 500)


    def toggle_pause(self):
        self.running = not self.running
        return self.running


    def save_game(self, slot=1):
        return {"slot": slot, "data": self.save()}


    def load_game(self, slot=1):
        return True


    def export_story(self, novel_mode=False):
        """导出故事，novel_mode=True 时输出小说风格纯文本"""
        import os, re
        save_dir = r"H:\baichengzhu\game\saves"
        os.makedirs(save_dir, exist_ok=True)

        logs = self.world.story_log
        if novel_mode:
            # 纯叙事，去除游戏冗余信息
            clean_logs = []
            skip_patterns = ["【死亡】", "tick", "Tick", "status", "save", "存档"]
            for log in logs:
                log = log.strip()
                if not log:
                    continue
                if any(p in log for p in skip_patterns):
                    continue
                if re.match(r"^\d+\.", log):
                    continue
                if log.startswith(("【", "#", "===", "---")):
                    continue
                clean_logs.append(log)

            # 按章节拆分（每50条为一章）
            chapters = []
            chapter_size = 50
            for i in range(0, len(clean_logs), chapter_size):
                chapters.append(clean_logs[i:i+chapter_size])

            lines = []
            lines.append(f"《{self.theme}世界录》")
            lines.append(f"纪元：{self.world.current_time}")
            lines.append("=" * 40)
            lines.append("")

            for ci, chapter in enumerate(chapters, 1):
                lines.append(f"第{ci}章")
                lines.append("-" * 20)
                lines.append("")
                for para in chapter:
                    lines.append(para)
                    lines.append("")
                lines.append("")

            fname = os.path.join(save_dir, f"{self.theme}_故事线_小说.txt")
            with open(fname, "w", encoding="utf-8") as f:
                f.write("\n".join(lines))
            return fname
        else:
            d = os.path.join(save_dir, "story_export.txt")
            with open(d, "w", encoding="utf-8") as f:
                for log in logs:
                    f.write(log + "\n")
            return d
