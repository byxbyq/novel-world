"""EngineAdapter 生命周期 Mixin — 初始化/存档/状态/角色管理"""
from __future__ import annotations
import os
import sys
import logging

# ── Backend imports ──
from backend.world import World as BackendWorld
from backend.character import CharacterAgent
from backend.collision import CollisionEngine as BackendCollision
from backend.narrative import NarrativeGenerator
from backend.storage import Storage
from backend.engine_config import EngineConfig

# ── novel_world imports ──
from novel_world.engine.core.character import Character as NWCharacter, CharType, CharState
from novel_world.engine.core.world import World as NWWorld, Faction, FactionGoal
from novel_world.engine.core.ai_client import AIClient
from novel_world.engine.collision import CollisionEngine as NWCollisionEngine
from novel_world.engine.skills import (
    CharacterSkillSet,
    WorldSkillSet,
    SkillRegistry,
)
from novel_world.engine.quality.timeline_checker import TimelineChecker
from novel_world.engine.quality.hard_constraint_controller import HardConstraintController
from novel_world.engine.memory.truth_ledger import TruthLedger

try:
    from novel_world.engine.core.events import NarrativeEngine
    _HAS_NARRATIVE_ENGINE = True
except ImportError:
    _HAS_NARRATIVE_ENGINE = False

logger = logging.getLogger("EngineAdapter")

class LifecycleMixin:
    """init / save / load / state / character conversion"""

    # ── 构造与初始化 ──

    def __init__(self, config: EngineConfig = None):
        self.config = config or EngineConfig()

        # backend 内部引用（供 AI 叙事、存档等 novel_world 不负责的能力复用）
        self._backend_world: BackendWorld = None
        self._characters: list[CharacterAgent] = []

        # novel_world 引擎组件
        self._nw_world: NWWorld = None
        self._nw_characters: list[NWCharacter] = []
        self._nw_collision: NWCollisionEngine = None
        self._nw_ai_client: AIClient = None
        self._nw_skill_registry: SkillRegistry = None

        # HardConstraintController（延迟初始化，init_game 中创建）
        self._hard_constraint: HardConstraintController = None

        # Phase 3：TruthLedger + NarrativeEngine
        self._truth_ledger: TruthLedger = None
        self._narrative_engine = None

        # bridge 内部组件
        self._narrator = NarrativeGenerator()
        self._backend_collision = BackendCollision()
        self.storage = Storage()
        self.outline_data: dict = None  # 大纲数据（卷/章节规划）

        # 运行状态
        self.chapters: list[dict] = []
        self._tick_count: int = 0
        self._novel_finalized: bool = False
        self._nw_chapter_idx: int = 0  # novel_world CollisionEngine 章节号
        self.current_chapter_events: list[str] = []  # DM 注入的世界事件

        # TimelineChecker — Fast 规则检查层
        self.timeline_checker = TimelineChecker()
        self._timeline_issues: list = []  # 当前累积的所有问题


    def init_game(self, world: BackendWorld, characters: list[CharacterAgent]):
        """初始化游戏：同时创建 backend 状态和 novel_world 引擎组件"""
        self._backend_world = world
        self._characters = characters
        self.chapters = []
        self._tick_count = 0
        self._novel_finalized = False
        self._nw_chapter_idx = 0

        # 重置叙事生成器的滑动窗口状态
        if hasattr(self._narrator, '_chapter_summaries'):
            self._narrator._chapter_summaries = []
        if hasattr(self._narrator, '_throttler') and self._narrator._throttler:
            self._narrator._throttler.history.clear()

        # ── 1. 创建 novel_world World ──
        self._nw_world = NWWorld(
            theme=world.config.genre,
            map_size=(40, 25),
        )
        # 尝试按主题生成地图
        try:
            import yaml
            import os
            map_yaml_path = os.path.join(os.path.dirname(__file__), '..', '..', 'map.yaml')
            map_yaml_path = os.path.normpath(map_yaml_path)
            name_config = None
            theme_config = {
                "tile_types": ["平原", "山脉", "森林", "水域", "遗迹", "沙漠", "城市"],
                "tile_weights": [15, 20, 18, 12, 15, 8, 12],
            }
            if os.path.exists(map_yaml_path):
                with open(map_yaml_path, 'r', encoding='utf-8') as f:
                    map_data = yaml.safe_load(f) or {}
                themes = map_data.get('themes', {})
                genre = world.config.genre or '修仙'
                if genre in themes:
                    t = themes[genre]
                    if 'tile_types' in t:
                        theme_config['tile_types'] = t['tile_types']
                    if 'tile_weights' in t:
                        theme_config['tile_weights'] = t['tile_weights']
                    if 'map_size' in t:
                        ms = t['map_size']
                        self._nw_world.map_size = (int(ms[0]), int(ms[1]))
                names = map_data.get('names', {})
                if names:
                    # city_names / region_names / place_names 是按主题分的 dict
                    # ruin_names / volcano_names 是通用列表
                    name_config = {
                        'city_names': names.get('city_names', {}),
                        'ruin_names': names.get('ruin_names', []),
                        'volcano_names': names.get('volcano_names', []),
                        'region_names': names.get('region_names', {}),
                        'place_names': names.get('place_names', {}),
                    }
            self._nw_world.generate_map(theme_config=theme_config, name_config=name_config)
        except Exception:
            pass  # 地图生成失败不阻塞

        # ── 2. 转换角色 → novel_world Character ──
        self._nw_characters = []
        self._nw_skill_registry = SkillRegistry()

        for char in characters:
            nw_char = self._convert_character(char)
            self._nw_world.add_character(nw_char)
            self._nw_characters.append(nw_char)

            # 构造最小技能集（无 AI 生成，仅占位）
            skill_set = CharacterSkillSet(
                character_id=nw_char.id,
                character_name=nw_char.name,
                passive_skills=[],
                active_skills=[],
                limits=[],
                costs=[],
                ultimate_goal=char.long_term_goal.description,
                current_goal=(
                    char.short_term_goals[0].description
                    if char.short_term_goals else ""
                ),
            )
            self._nw_skill_registry.register_character(skill_set)

        # 世界技能
        world_skills = WorldSkillSet(
            world_name=world.config.name,
            rules=[],
        )
        self._nw_skill_registry.set_world_skills(world_skills)

        # ── 2.5. 创建势力（Faction）──
        faction_configs = getattr(world.config, 'factions', None)
        if faction_configs:
            for fc in faction_configs:
                goals = []
                for g in fc.get("goals", []) or []:
                    if isinstance(g, str):
                        goals.append(FactionGoal(description=g))
                    elif isinstance(g, dict):
                        goals.append(FactionGoal(
                            description=g.get("description", ""),
                            priority=g.get("priority", 5),
                        ))
                faction = Faction(
                    id=fc.get("id", fc.get("name", "")),
                    name=fc.get("name", fc.get("id", "")),
                    description=fc.get("description", ""),
                    leader_id=fc.get("leader_id", ""),
                    color=fc.get("color", "#888888"),
                    goals=goals,
                    controlled_resources=list(fc.get("controlled_resources", []) or []),
                )
                # 先将 enemies/allies 暂存为名字列表，全部加载后再双向同步
                faction._pending_enemies = list(fc.get("enemies", []) or [])
                faction._pending_allies = list(fc.get("allies", []) or [])
                self._nw_world.add_faction(faction)

            # 双向同步敌对/同盟关系（按 name 匹配）
            for faction in self._nw_world.factions.values():
                pending_enemies = getattr(faction, '_pending_enemies', [])
                pending_allies = getattr(faction, '_pending_allies', [])
                for ename in pending_enemies:
                    target = self._nw_world.get_faction_by_name(ename)
                    if target and target.id != faction.id:
                        self._nw_world.set_faction_enemies(faction.id, target.id)
                for aname in pending_allies:
                    target = self._nw_world.get_faction_by_name(aname)
                    if target and target.id != faction.id:
                        self._nw_world.set_faction_allies(faction.id, target.id)
                if hasattr(faction, '_pending_enemies'):
                    del faction._pending_enemies
                if hasattr(faction, '_pending_allies'):
                    del faction._pending_allies
        else:
            # 从角色数据中自动生成默认势力
            faction_names = set()
            for char in characters:
                faction_attr = getattr(char.config, 'faction', None)
                if faction_attr and faction_attr.strip():
                    faction_names.add(faction_attr.strip())
            for fname in faction_names:
                faction = Faction(
                    name=fname,
                    description=f"{fname}势力",
                )
                self._nw_world.add_faction(faction)

        # ── 3. 初始化 CollisionEngine + 统一 AI 客户端 ──
        # 优先从环境变量读取，避免 EngineConfig 默认值覆盖已配置的 provider
        ai_provider = os.getenv("AI_PROVIDER", "").strip() or getattr(self.config, 'ai_provider', 'none') or 'none'
        # 非法 provider（如历史遗留的 "api"/"none"）会导致所有 AI 调用静默失败，回退 deepseek
        from backend.ai_client import VALID_PROVIDERS
        if ai_provider not in VALID_PROVIDERS:
            logger.warning(f"AI_PROVIDER={ai_provider!r} 非法，回退为 deepseek")
            ai_provider = "deepseek"
        # 同步初始化 backend.ai_client（两套入口共用同一套 AI 客户端）
        from backend.ai_client import init_client as _backend_init_ai
        _backend_init_ai(provider=ai_provider)

        self._nw_ai_client = AIClient(
            provider=ai_provider,
            api_url=os.getenv("OPENAI_BASE_URL", ""),
            api_key=os.getenv("OPENAI_API_KEY", ""),
            api_model=os.getenv("OPENAI_MODEL", ""),
        )
        self._nw_collision = NWCollisionEngine(
            world=self._nw_world,
            skill_registry=self._nw_skill_registry,
            ai_client=self._nw_ai_client,
        )

        # ── 4. backend 状态同步 ──
        for char in self._characters:
            if char.current_location:
                self._backend_world.set_character_position(char.name, char.current_location)

        if self._backend_world.config.main_objective:
            self.align_goals_to_main_objective()

        # ── 5. 初始化 HardConstraintController ──
        constraints = getattr(world.config, 'constraints', None) if hasattr(world.config, 'constraints') else None
        self._hard_constraint = HardConstraintController(
            theme=world.config.genre,
            constraints=constraints,
        )

        # ── 5.5. 应用前置主线约束 ──
        self._apply_story_constraint(world)

        # ── 6. 初始化 TruthLedger + NarrativeEngine ──
        _truth_ledger_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            'saves', 'truth_ledger',
        )
        os.makedirs(_truth_ledger_dir, exist_ok=True)
        self._truth_ledger = TruthLedger(_truth_ledger_dir)

        if _HAS_NARRATIVE_ENGINE:
            try:
                self._narrative_engine = NarrativeEngine(
                    ai_client=self._nw_ai_client,
                    theme=world.config.genre or '日常',
                )
                self._narrative_engine.set_ledger(self._truth_ledger)
                logger.info("Phase3：NarrativeEngine 已初始化并绑定 TruthLedger")
            except Exception as e:
                logger.warning(f"Phase3：NarrativeEngine 初始化失败（不影响核心流程）: {e}")
                self._narrative_engine = None

        logger.info(
            f"EngineAdapter: 初始化完成 — "
            f"{len(self._characters)} 角色, "
            f"{len(self._nw_world.tiles)} 地块"
        )


    def _convert_character(self, agent: CharacterAgent) -> NWCharacter:
        """CharacterAgent → novel_world Character"""
        # 推断角色类型：优先使用 config.char_type，缺省按 NPC 处理
        char_type_str = getattr(agent.config, 'char_type', '') or ''
        if char_type_str:
            try:
                char_type = CharType[char_type_str]
            except KeyError:
                # 尝试按值匹配
                char_type_map = {e.value: e for e in CharType}
                char_type = char_type_map.get(char_type_str, CharType.NPC)
        else:
            char_type = CharType.NPC

        # 映射属性：优先从 CharacterAgent 读取，缺失则用默认
        base_attrs = {
            "体力": 60, "智力": 60, "魅力": 50, "运气": 50,
            "攻击": 40, "防御": 40, "声望": 0, "财富": 0,
        }
        agent_attrs = getattr(agent, 'attrs', None) or getattr(agent.config, 'attributes', None) or {}
        if isinstance(agent_attrs, dict):
            for k in base_attrs:
                if k in agent_attrs:
                    try:
                        base_attrs[k] = int(agent_attrs[k])
                    except (ValueError, TypeError):
                        pass

        nw_char = NWCharacter(
            name=agent.name,
            char_type=char_type,
            gender=agent.config.gender,
            age=agent.config.age,
            attrs=base_attrs,
            personality=agent.config.personality,
            fate_arc=agent.config.background,
            goal=agent.long_term_goal.description,
            story_state=agent.current_mood,
            pos=(0, 0),
            skills=[g.description for g in agent.short_term_goals[:3]],
        )
        return nw_char


    def get_character(self, name: str) -> CharacterAgent:
        """按名称查找 CharacterAgent"""
        for char in self._characters:
            if char.name == name:
                return char
        raise ValueError(f"角色不存在: {name}")

    @property
    def world(self):
        """暴露 backend World，供 app.py 直接访问"""
        return self._backend_world


    def get_state(self) -> dict:
        """获取当前游戏状态（格式与 backend GameEngine 完全一致）"""
        nw_stats = {}
        try:
            if self._nw_collision:
                nw_stats = self._nw_collision.get_stats()
        except Exception:
            pass

        return {
            "world": {
                "name": self._backend_world.config.name if self._backend_world else "",
                "chapter": self._backend_world.current_chapter if self._backend_world else 0,
                "genre": self._backend_world.config.genre if self._backend_world else "",
                "events_count": len(self._backend_world.events) if self._backend_world else 0,
                "main_objective": self._backend_world.config.main_objective if self._backend_world else "",
                "world_stage": self._backend_world.config.world_stage if self._backend_world else "",
            },
            "engine": {
                "total_chapters": self.config.total_chapters,
                "ticks_per_chapter": self.config.ticks_per_chapter,
                "end_behavior": self.config.end_behavior,
                "expected_ending": self.config.expected_ending,
                "tick_count": self._tick_count,
                "novel_finalized": self._novel_finalized,
                "nw_tick": nw_stats.get("global_tick", 0),
                "nw_collisions": nw_stats.get("total_collisions", 0),
            },
            "characters": [
                {
                    "name": c.name,
                    "gender": getattr(c.config, "gender", "") or "男",
                    "age": getattr(c.config, "age", 20) or 20,
                    "personality": getattr(c.config, "personality", ""),
                    "abilities": getattr(c.config, "abilities", []) or [],
                    "weaknesses": getattr(c.config, "weaknesses", []) or [],
                    "location": c.current_location,
                    "mood": c.current_mood,
                    "long_term_goal": c.long_term_goal.description if c.long_term_goal else "",
                    "active_short_goals": [
                        g.description for g in c.short_term_goals
                        if g.progress not in ("已完成", "已放弃")
                    ],
                    "relationships": c.relationship_text(),
                }
                for c in self._characters
            ],
            "chapters_count": len(self.chapters),
        }

    # ── 存档（复用 backend Storage） ──

    def save(self, slot: str = "auto"):
        ec = {
            "total_chapters": self.config.total_chapters,
            "ticks_per_chapter": self.config.ticks_per_chapter,
            "tick_speed": self.config.tick_speed,
            "auto_pause_between_chapters": self.config.auto_pause_between_chapters,
            "end_behavior": self.config.end_behavior,
            "expected_ending": self.config.expected_ending,
            "npc_filter_enabled": self.config.npc_filter_enabled,
            "offline_mode": self.config.offline_mode,
            "ai_provider": self.config.ai_provider,
        }
        self.storage.save(slot, self._backend_world, self._characters, self.chapters,
                          self.outline_data, ec)


    def load(self, slot: str = "auto") -> bool:
        result = self.storage.load(slot)
        if result:
            world, characters, chapters, outline, ec = result
            self.init_game(world, characters)
            # 历史存档可能存在章节号跳号（删章/丢章所致），统一重排为连续编号
            for i, ch in enumerate(chapters):
                ch["chapter"] = i + 1
            self.chapters = chapters
            self.outline_data = outline
            if ec:
                for k, v in ec.items():
                    if hasattr(self.config, k):
                        setattr(self.config, k, v)
            # 重建滑动窗口历史（让续写时能看到之前的完整章节）
            try:
                self._narrator.rebuild_chapter_history(chapters)
            except Exception as e:
                logger.warning(f"重建章节历史失败（不影响加载）: {e}")
            return True
        return False


    def _integrate_discovered_characters(self):
        """将叙事生成器自动发现的新角色加入引擎（backend + novel_world）

        NPC分级机制：
        - 根据角色在正文中是否有完整的人物卡（性格/背景/目标），分为：
          - KEY_NPC（关键配角）：有人物卡，有明确性格和目标，参与后续剧情
          - NPC（普通配角）：有名字但信息不全，作为背景角色存在
        - 角色出现次数追踪：跨章节累计出现次数，达到阈值自动升级为KEY_NPC
        """
        discovered = getattr(self._narrator, '_discovered_chars', None)
        if not discovered:
            return

        import random
        from novel_world.engine.core.character import Character as NWCharacter, CharType, CharState

        # 取出后立即清空，避免重复处理
        self._narrator._discovered_chars = []

        # 初始化角色出现追踪表（如果不存在）
        if not hasattr(self, '_char_appearance_tracker'):
            self._char_appearance_tracker = {}

        for agent in discovered:
            # ── NPC分级：根据人物卡完整度决定角色类型 ──
            has_personality = bool(getattr(agent.config, 'personality', '') and len(agent.config.personality) > 3)
            has_background = bool(getattr(agent.config, 'background', '') and len(agent.config.background) > 5)
            has_goal = bool(getattr(agent.config, 'long_term_goal', '') and len(agent.config.long_term_goal) > 3)

            info_score = sum([has_personality, has_background, has_goal])

            if info_score >= 2:
                # 有人物卡 → 关键配角
                char_type = CharType.KEY_NPC
                npc_tier = "key_npc"
            else:
                # 信息不全 → 普通NPC
                char_type = CharType.NPC
                npc_tier = "minor_npc"

            # 设置角色的npc_tier属性
            agent.npc_tier = npc_tier
            agent.appearance_count = 1

            # 1. 加入 backend 角色列表
            self._characters.append(agent)

            # 2. 创建 novel_world 角色
            nw_char = NWCharacter(
                name=agent.name,
                char_type=char_type,
                state=CharState.IDLE,
                personality=[agent.config.personality] if agent.config.personality else [],
                pos=(random.randint(0, self._nw_world.map_size[0]-1),
                     random.randint(0, self._nw_world.map_size[1]-1)),
                goal=agent.config.background or "",
            )
            self._nw_world.add_character(nw_char)
            self._nw_characters.append(nw_char)

            # 记录出现追踪
            self._char_appearance_tracker[agent.name] = 1

            import logging
            logging.getLogger(__name__).info(
                f"新角色加入引擎: {agent.name} (级别: {npc_tier}, "
                f"信息完整度: {info_score}/3)"
            )

        # ── 检查已有NPC是否在后续章节中多次出现，自动升级 ──
        # 扫描最近章节正文，统计已有NPC的出现次数
        if len(self.chapters) > 0:
            recent_narrative = ""
            for ch in self.chapters[-3:]:  # 最近3章
                recent_narrative += ch.get("narrative", "") + "\n"

            for char in self._characters:
                if hasattr(char, 'npc_tier') and char.npc_tier == "minor_npc":
                    count = recent_narrative.count(char.name)
                    total = self._char_appearance_tracker.get(char.name, 0) + count
                    self._char_appearance_tracker[char.name] = total

                    # 出现5次以上 → 升级为关键配角
                    if total >= 5:
                        char.npc_tier = "key_npc"
                        # 同步更新 novel_world 角色
                        for nw_c in self._nw_characters:
                            if nw_c.name == char.name:
                                nw_c.char_type = CharType.KEY_NPC
                                break
                        import logging
                        logging.getLogger(__name__).info(
                            f"角色'{char.name}'出现{total}次，升级为关键配角(KEY_NPC)"
                        )

        # 清空已处理
        self._narrator._discovered_chars = []
