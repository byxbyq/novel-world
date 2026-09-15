# -*- coding: utf-8 -*-
"""
小说世界引擎 - 演示脚本
===========================
本脚本展示如何使用小说世界（Novel World）引擎的完整流程：
  1. 初始化AI客户端（支持DeepSeek兼容接口 / 模板降级模式）
  2. 创建修仙世界
  3. 定义角色（含完整四维度技能 + 双目标）
  4. 注册技能到 SkillRegistry
  5. 启动碰撞引擎，自动检测角色冲突并生成剧情
  6. 通过 NovelWriter 将碰撞输出沉淀为章节文件
  7. 导出完整小说

运行方式：
  python run_demo.py

依赖：本脚本需要 novel_world 包在 sys.path 中可访问。
"""

import sys
import os
import json
import yaml
import logging
import random
from datetime import datetime

# ==========================================================================
# 第一部分：环境配置
# ==========================================================================
# 将项目根目录添加到 Python 模块搜索路径，确保能正确导入 novel_world 包
PROJECT_ROOT = r"H:\小说\小说世界"
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# 配置日志输出，方便调试和观察引擎运行过程
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("run_demo")

# 导入小说世界引擎的核心模块
from novel_world.engine.core.world import World, Faction, FactionGoal
from novel_world.engine.core.character import Character, CharType, CharState
from novel_world.engine.core.ai_client import AIClient
from novel_world.engine.skills import (
    Skill,
    SkillType,
    CharacterSkillSet,
    WorldSkill,
    WorldSkillSet,
    SkillRegistry,
)
from novel_world.engine.collision import (
    CollisionEngine,
    EntryMotivation,
)
from novel_world.engine.novel_output import (
    NovelWriter,
    NovelProject,
)
from novel_world.engine.scheduler import (
    WorldTimeline,
    GoalScheduler,
    ConsistencyChecker,
    WorldRuleGuard,
    WorldRule,
    CheckLevel,
    GuardLevel,
)
from novel_world.engine.quality import (
    QualityPipeline,
    PipelineLevel,
    ResultLevel,
    build_narrative_rules,
)

from novel_world.engine.tick_scheduler import TickScheduler, TickConfig

from backend.engine_config import EngineConfig


# ==========================================================================
# 第二部分：AI 客户端配置
# ==========================================================================
def create_ai_client():
    """
    创建 AI 客户端。

    提供三种模式：
      - "api"  : 调用 DeepSeek 兼容的 OpenAI 格式 API（需要填写实际地址和密钥）
      - "none" : 模板降级模式（无需API，碰撞引擎使用内置模板生成叙事文本）

    演示默认使用 "none" 模式，方便开箱即用。
    如需接入真实AI，请将 provider 改为 "api" 并填写对应的 api_url / api_key / api_model。
    """
    # ---- 模式一：API 模式（DeepSeek 兼容端点）----
    ai_client = AIClient(
        provider="api",
        api_url="https://api.deepseek.com/v1/chat/completions",
        api_key=os.getenv("OPENAI_API_KEY", ""),
        api_model="deepseek-v4-flash",
    )

    # ---- 模式二：模板降级模式（无需API，开箱即用）----
    # ai_client = AIClient(provider="none")

    logger.info(f"AI 客户端已创建（模式：{ai_client.provider}）")
    return ai_client


# ==========================================================================
# 第三部分：角色定义
# ==========================================================================
def create_characters():
    """
    从 characters.yaml 配置文件读取角色定义，动态创建 Character 和 CharacterSkillSet。

    配置文件路径：项目根目录/characters.yaml
    用户可直接编辑该 YAML 文件增减角色，无需修改代码。

    返回角色列表（Character 对象）和对应的技能集列表（CharacterSkillSet 对象）。
    """

    config_path = os.path.join(PROJECT_ROOT, "characters.yaml")
    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    # identity -> CharType 映射
    IDENTITY_MAP = {
        "protagonist": CharType.PROTAGONIST,
        "heroine": CharType.HEROINE,
        "antagonist": CharType.ANTAGONIST,
        "supporting": CharType.KEY_NPC,
        "npc": CharType.NPC,
    }

    characters = []
    skill_sets = []

    for entry in config["characters"]:
        name = entry["name"]

        # --- 构建 CharacterSkillSet ---
        sk = entry["skills"]
        skill_set = CharacterSkillSet(
            character_id=name,
            character_name=name,
            passive_skills=[
                Skill(
                    name=sk["passive"]["name"],
                    skill_type=SkillType.PASSIVE,
                    description=sk["passive"]["description"],
                    tags=sk["passive"]["tags"],
                ),
            ],
            active_skills=[
                Skill(
                    name=sk["active"]["name"],
                    skill_type=SkillType.ACTIVE,
                    description=sk["active"]["description"],
                    tags=sk["active"]["tags"],
                    trigger_condition=sk["active"].get("trigger_condition", ""),
                    effect_range=sk["active"].get("effect_range", 0),
                    duration=sk["active"].get("duration", 0),
                ),
            ],
            limits=[
                Skill(
                    name=sk["limit"]["name"],
                    skill_type=SkillType.LIMIT,
                    description=sk["limit"]["description"],
                    tags=sk["limit"]["tags"],
                    blind_spots=sk["limit"].get("blind_spots", []),
                ),
            ],
            costs=[
                Skill(
                    name=sk["cost"]["name"],
                    skill_type=SkillType.COST,
                    description=sk["cost"]["description"],
                    tags=sk["cost"]["tags"],
                    side_effects=sk["cost"].get("side_effects", []),
                    karma_debt=sk["cost"].get("karma_debt", ""),
                ),
            ],
            ultimate_goal=entry["ultimate_goal"],
            current_goal=entry["goal"],
        )

        # --- 构建 Character ---
        char_type = IDENTITY_MAP.get(entry["identity"], CharType.NPC)
        pos = tuple(entry["position"])

        character = Character(
            name=name,
            char_type=char_type,
            gender=entry.get("gender", ""),
            age=entry.get("age", 0),
            attrs=entry.get("attrs", {}),
            personality=entry["personality"],
            fate_arc=entry["fate_arc"],
            goal=entry["goal"],
            story_state=entry["story_state"],
            pos=pos,
            skills=[sk["被动特质"]["name"], sk["主动手段"]["name"]],
            faction_id=entry.get("faction", ""),
        )
        # 动态追加入场章节号（Character dataclass 支持动态属性）
        character.entry_chapter = entry.get("entry_chapter", 1)

        characters.append(character)
        skill_sets.append(skill_set)

    logger.info(f"从配置文件加载了 {len(characters)} 个角色：{[c.name for c in characters]}")
    return characters, skill_sets


def load_relationships(characters: list):
    """
    从 relationships.yaml 加载初始人际关系。

    替代原硬编码在 run_demo.py 中的关系初始化。
    返回 {(subject, object): (subject_feeling, object_feeling)} 字典。
    """
    config_path = os.path.join(PROJECT_ROOT, "relationships.yaml")
    if not os.path.exists(config_path):
        logger.warning(f"人际关系配置文件不存在: {config_path}")
        return {}

    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    relations = {}
    for entry in config.get("relations", []):
        key = (entry["subject"], entry["object"])
        relations[key] = (entry.get("subject_feeling", ""),
                          entry.get("object_feeling", ""))
    logger.info(f"已加载 {len(relations)} 组初始人际关系")
    return relations


# ==========================================================================
# 第三部分（续）：世界时间线加载
# ==========================================================================
def load_world_timeline():
    """
    从 world_timeline.yaml 加载世界时间线事件。

    返回字典 {chapter_num: [event_str, ...]}
    """
    config_path = os.path.join(PROJECT_ROOT, "world_timeline.yaml")
    if not os.path.exists(config_path):
        logger.warning(f"世界时间线配置文件不存在: {config_path}")
        return {}
    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    timeline = {}
    for entry in config.get("timeline", []):
        ch = entry["chapter"]
        timeline.setdefault(ch, []).append(entry["event"])
    logger.info(f"已加载世界时间线：{len(timeline)} 个章节有世界事件")
    return timeline


# ==========================================================================
# 第四部分：从 YAML 加载世界配置
# ==========================================================================
def load_world_mechanics():
    """
    从 world_mechanics.yaml 加载世界技能（WorldSkillSet）。

    世界技能是全局规则，会对所有角色的对应标签技能产生修正效果。
    用户可直接编辑该 YAML 文件增减世界规则。
    """
    config_path = os.path.join(PROJECT_ROOT, "world_mechanics.yaml")
    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    rules = []
    for entry in config["rules"]:
        rules.append(WorldSkill(
            name=entry["name"],
            description=entry["description"],
            effect=entry["effect"],
            affects_tags=entry["affects_tags"],
            modifier=entry["modifier"],
        ))

    world_skills = WorldSkillSet(world_name=config["world_name"], rules=rules)
    logger.info(f"已加载世界技能：{world_skills.world_name}（{len(rules)}条规则）")
    return world_skills


def load_factions(world):
    """
    从 factions.yaml 加载势力定义，创建 Faction 对象并加入 World。

    用户可直接编辑该 YAML 文件增减势力、修改敌对/同盟关系。
    """
    config_path = os.path.join(PROJECT_ROOT, "factions.yaml")
    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    for entry in config["factions"]:
        faction = Faction(
            id=entry["id"],
            name=entry["name"],
            color=entry.get("color", "#FFFFFF"),
            description=entry.get("description", ""),
            leader_id=entry.get("leader_id", ""),
            enemies=entry.get("enemies", []),
            allies=entry.get("allies", []),
            controlled_resources=entry.get("controlled_resources", []),
        )
        for gd in entry.get("goals", []):
            faction.goals.append(FactionGoal(description=gd))
        world.add_faction(faction)
        logger.info(f"  已加载势力：{faction.name}（{faction.member_count()}成员）")

    # 双向建立敌对/同盟关系
    for entry in config["factions"]:
        faction_name = entry["name"]
        faction = world.get_faction_by_name(faction_name)
        if not faction:
            continue
        for enemy_name in entry.get("enemies", []):
            enemy = world.get_faction_by_name(enemy_name)
            if enemy:
                faction.add_enemy(enemy_name)
                enemy.add_enemy(faction_name)
        for ally_name in entry.get("allies", []):
            ally = world.get_faction_by_name(ally_name)
            if ally:
                faction.add_ally(ally_name)
                ally.add_ally(faction_name)

    logger.info(f"已加载 {len(config['factions'])} 个势力")
    return config["factions"]


def load_map_config():
    """从 map.yaml 加载地图/主题配置"""
    config_path = os.path.join(PROJECT_ROOT, "map.yaml")
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_plot_config():
    """从 plot.yaml 加载剧情/世界初始化配置"""
    config_path = os.path.join(PROJECT_ROOT, "plot.yaml")
    if not os.path.exists(config_path):
        logger.warning(f"剧情配置文件不存在: {config_path}")
        return {}
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


# ==========================================================================
# 第五部分：注册技能
# ==========================================================================
def setup_skill_registry(skill_sets, world_skills):
    """
    创建 SkillRegistry 并注册所有角色和世界技能。

    SkillRegistry 是碰撞引擎的核心依赖，负责：
      - 存储所有角色的 CharacterSkillSet
      - 存储世界的 WorldSkillSet
      - 提供 find_collisions() 方法扫描角色间的碰撞
    """
    registry = SkillRegistry()

    # 注册每个角色的技能集
    for skill_set in skill_sets:
        registry.register_character(skill_set)
        logger.info(f"  已注册角色技能：{skill_set.character_name}（{skill_set.character_id}）")

    # 设置世界技能
    registry.set_world_skills(world_skills)
    logger.info(f"  已注册世界技能：{world_skills.world_name}（{len(world_skills.rules)}条规则）")

    return registry


# ==========================================================================
# 第六部分：主流程
# ==========================================================================
def main():
    """
    演示主流程：
      1. 创建AI客户端
      2. 创建修仙世界 + 生成地图
      3. 创建角色（含四维度技能 + 双目标）
      4. 注册技能到 SkillRegistry
      5. 启动碰撞引擎
      6. 循环：每章 20 tick，共 3 章
      7. 导出完整小说
    """
    print("=" * 60)
    print("  小说世界引擎 - 修仙主题演示")
    print(f"  运行时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    print()

    # ── Step 0: 创建引擎配置（Phase1 P1 — EngineConfig 标准化）──
    engine_config = EngineConfig(
        total_chapters=5,
        ticks_per_chapter=20,
        tick_speed="normal",
        end_behavior="wrap_up",
        ai_provider="api",
        offline_mode=False,
    )

    # ── Step 1: 创建 AI 客户端 -─
    print("[Step 1] 创建 AI 客户端...")
    ai_client = create_ai_client()
    print(f"  -> AI 模式：{ai_client.provider}")
    if ai_client.is_available:
        print("  -> AI 叙事生成：已启用")
    else:
        print("  -> AI 叙事生成：未启用（将使用模板降级）")
    print()

    # ---- Step 2: 从 YAML 加载世界配置并创建修仙世界 ----
    print("[Step 2] 加载世界配置并创建修仙世界...")
    plot_config = load_plot_config()
    map_config = load_map_config()

    # 读取世界初始化参数
    world_init = plot_config.get("world_init", {})
    theme = world_init.get("theme", "修仙")
    map_size = tuple(world_init.get("map_size", [40, 25]))
    main_objective = world_init.get("main_objective", "")

    world = World(theme=theme, map_size=map_size)
    world.main_objective = main_objective

    # 加载势力
    load_factions(world)

    # 获取当前主题的地图配置
    theme_config = map_config.get("themes", {}).get(theme, {})
    name_config = map_config.get("names", {})

    world.generate_map(theme_config=theme_config, name_config=name_config)
    print(f"  -> 世界主题：{world.theme}")
    print(f"  -> 地图尺寸：{world.map_size[0]} x {world.map_size[1]}")
    print(f"  -> 地图（主题配置）：{len(theme_config.get('tile_types', []))} 种地形")
    print(f"  -> 地块总数：{len(world.tiles)}")
    print(f"  -> 势力数：{len(world.factions)}")
    print()

    # ---- Step 2.5: 加载世界时间线 + 时间树 ----
    world_timeline = load_world_timeline()

    # 加载时间树（分支剧情引擎）
    from novel_world.engine.scheduler import TimelineTreeEngine, WorldState, ChapterResolution
    timeline_tree = TimelineTreeEngine()
    timeline_tree.load(PROJECT_ROOT)
    tree_stats = timeline_tree.get_stats()
    print(f"  -> 时间树已加载：{tree_stats['base_timeline_chapters']} 章基础事件，"
          f"{tree_stats['tree_chapters']} 章含分支，{tree_stats['total_branches']} 个分支")
    # 初始化世界状态（角色关系稍后在 Step 3 后补充）
    world_state = None  # 延迟到角色创建后

    # ---- Step 3: 创建角色 ----
    print("[Step 3] 创建角色（渐进入场模式）...")
    characters, skill_sets = create_characters()
    # 所有角色先创建但不直接加入世界，每章按 entry_chapter 渐进入场
    for char in characters:
        type_label = char.char_type.value
        entry_ch = getattr(char, 'entry_chapter', 1)
        print(f"  -> [{type_label}] {char.name}（位置：{char.pos}，入场章：第{entry_ch}章）")
    print()

    # ---- Step 4: 加载世界技能（从 YAML） ----
    print("[Step 4] 加载世界技能...")
    world_skills = load_world_mechanics()
    for rule in world_skills.rules:
        print(f"  -> {rule.name}：影响标签 {rule.affects_tags}，modifier={rule.modifier}")
    print()

    # ---- Step 5: 注册技能到 SkillRegistry ----
    print("[Step 5] 注册技能到 SkillRegistry...")
    skill_registry = setup_skill_registry(skill_sets, world_skills)

    # 初始化时间树世界状态（基于角色和势力）
    world_state = timeline_tree.load_initial_state(
        characters=characters,
        factions=list(world.factions.values()),
    )
    # 从 YAML 加载初始角色关系（替代硬编码）
    relations = load_relationships(characters)
    for (subj, obj), (subj_feel, obj_feel) in relations.items():
        world_state.set_char_relation(subj, obj, subj_feel)
    print(f"  -> 世界状态已初始化（{len(world_state.char_relations)} 组角色关系）")
    # 打印碰撞检测结果
    collisions = skill_registry.find_collisions()
    if collisions:
        print(f"  -> 初始碰撞检测结果（{len(collisions)}处）：")
        for c in collisions:
            print(f"     [{c['collision_type'].value}] {c['reason']}")
    else:
        print("  -> 初始碰撞检测：未发现碰撞（角色距离较远）")
    print()

    # ---- Step 6: 创建碰撞引擎 ----
    print("[Step 6] 创建碰撞引擎...")
    collision_engine = CollisionEngine(
        world=world,
        skill_registry=skill_registry,
        ai_client=ai_client,
    )

    # 注入叙事规则到碰撞引擎
    narrative_rules = build_narrative_rules()
    collision_engine.set_narrative_rules(narrative_rules)

    print("  -> 碰撞引擎已就绪（已绑定世界、技能注册表、AI客户端）")
    print()

    # ---- Step 6.5: 初始化质量管线与调度器 ----
    print("[Step 6.5] 初始化质量管线...")

    # 世界观规则守卫（分级：默认 WARN 以上报告）
    rule_guard = WorldRuleGuard()
    # 加载自定义世界规则
    if world_skills and hasattr(world_skills, 'rules'):
        for ws in world_skills.rules:
            rule = WorldRule(
                id=f"ws_{ws.name}",
                name=ws.name,
                description=ws.description,
                rule_type="scene_rule",
            )
            if hasattr(ws, 'affects_tags') and ws.affects_tags:
                rule.keywords = ws.affects_tags
            rule_guard.add_rule(rule)

    # 全局一致性校验器
    consistency_checker = ConsistencyChecker()

    # 目标调度器
    goal_scheduler = GoalScheduler()

    # 质量校验管线（8层，非严格模式 — 警告不中断）
    quality_pipeline = QualityPipeline(
        world_rule_guard=rule_guard,
        consistency_checker=consistency_checker,
        strict_mode=False,
    )

    print(f"  -> WorldRuleGuard 就绪（{len(rule_guard.rules) if hasattr(rule_guard, 'rules') else 0} 条世界规则）")
    print(f"  -> ConsistencyChecker 就绪")
    print(f"  -> GoalScheduler 就绪")
    print(f"  -> QualityPipeline 就绪（8层校验，非严格模式）")
    print()

    # ---- Step 7: 创建 NovelWriter ----
    print("[Step 7] 创建小说项目...")
    output_dir = os.path.join(PROJECT_ROOT, "output", "demo_novel")
    novel_meta = plot_config.get("novel_meta", {})
    project = NovelProject(
        title=novel_meta.get("title", "未命名小说"),
        author=novel_meta.get("author", "小说世界引擎"),
        genre=novel_meta.get("genre", theme),
        output_dir=output_dir,
    )
    writer = NovelWriter(project=project)
    print(f"  -> 小说标题：{project.title}")
    print(f"  -> 输出目录：{output_dir}")
    print()

    # ---- Step 8: TickScheduler + 模拟角色移动 + 碰撞检测 ----
    TOTAL_CHAPTERS = engine_config.total_chapters
    TICKS_PER_CHAPTER = engine_config.ticks_per_chapter

    # 创建三层 Tick 调度器
    tick_scheduler = TickScheduler(
        config=TickConfig(
            slow_ticks_per_chapter=1,
            medium_per_slow=TICKS_PER_CHAPTER,
            fast_per_medium=10,
            offline_mode=engine_config.offline_mode,
        )
    )

    # ── 慢Tick回调：世界技能刷新 / 气息衰减 / 地脉灵机 / 区域监控 ──
    chapter_stats = {"quality_issues": 0}  # 用字典避免 nonlocal 复杂

    def on_slow_tick(frame):
        _ = frame
        if world_skills and hasattr(world_skills, 'refresh'):
            world_skills.refresh()

        active_rules = world_skills.get_active_rules() if world_skills else []
        for rule in active_rules:
            if '灵气' in rule.name:
                for x in range(min(world._WIDTH if hasattr(world, '_WIDTH') else 40, 40)):
                    for y in range(min(world._HEIGHT if hasattr(world, '_HEIGHT') else 25, 25)):
                        key = (x, y)
                        current = world.spiritual_energy.get(key, 50)
                        world.spiritual_energy[key] = min(100, current + 5)
            elif '禁制' in rule.name:
                new_zones = dict(world.zone_monitoring)
                for (x, y), data in world.zone_monitoring.items():
                    for dx, dy in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                        nx, ny = x + dx, y + dy
                        if (nx, ny) not in world.zone_monitoring:
                            new_zones[(nx, ny)] = {
                                'controller': data.get('controller', '未知'),
                                'intensity': max(0, data.get('intensity', 50) - 20),
                            }
                world.zone_monitoring = new_zones

        for char in active_chars:
            if hasattr(char, 'aura_trail'):
                char.aura_trail = [
                    t for t in char.aura_trail
                    if t['intensity'] - 5 > 0
                ]
                for t in char.aura_trail:
                    t['intensity'] = max(0, t['intensity'] - 5)

    def on_medium_tick(frame):
        active = [c for c in characters if getattr(c, 'entry_chapter', 1) <= frame.chapter]

        if engine_config.offline_mode:
            event = collision_engine.tick_offline(active) if hasattr(
                collision_engine, 'tick_offline') else collision_engine.tick(active)
        else:
            event = collision_engine.tick(active)

        if event:
            tick_idx = frame.medium_tick
            print(f"  [Tick {tick_idx:02d}] 碰撞！"
                  f"{event.char_a_name} vs {event.char_b_name} "
                  f"[{event.collision_type}]")
            print(f"           原因：{event.collision_reason}")
            if event.narrative:
                print(f"           叙事：{event.narrative[:80]}...")

                try:
                    q_report = quality_pipeline.validate(
                        narrative=event.narrative,
                        chapter_index=frame.chapter,
                    )
                    if q_report.overall_level != ResultLevel.PASS:
                        chapter_stats["quality_issues"] += q_report.total_issues
                        if q_report.failed_layers:
                            print(f"     [质量] FAIL: {', '.join(l.layer.value for l in q_report.failed_layers)}")
                        if q_report.warning_layers:
                            print(f"     [质量] WARN: {', '.join(l.layer.value for l in q_report.warning_layers)}")
                except Exception as e:
                    logger.debug(f"质量校验跳过: {e}")

    # 注册回调
    tick_scheduler.on_slow_tick = on_slow_tick
    tick_scheduler.on_medium_tick = on_medium_tick

    print(f"[Step 8] 开始生成小说（{TOTAL_CHAPTERS}章，TickScheduler: "
          f"慢1/中{TICKS_PER_CHAPTER}/快{'10' if not engine_config.offline_mode else '跳过'}）...")
    print(f"  -> 引擎配置：speed={engine_config.tick_speed}, ai={engine_config.ai_provider}")
    print("-" * 60)

    all_chapters = []  # 存储所有完成的章节

    for chapter_idx in range(1, TOTAL_CHAPTERS + 1):
        print()
        print(f">>> ========== 第 {chapter_idx} 章 ==========")

        # ── 角色渐进入场：新入场的角色加入世界 ──
        newcomers = [c for c in characters if getattr(c, 'entry_chapter', 1) == chapter_idx]
        for char in newcomers:
            world.add_character(char)
            print(f"  [入场] {char.name} 在第{chapter_idx}章登场")
        # 收集当前活跃角色
        active_chars = [c for c in characters if getattr(c, 'entry_chapter', 1) <= chapter_idx]

        # 时间树提纲驱动
        resolution = timeline_tree.resolve(chapter=chapter_idx, world_state=world_state)
        prev_summary = collision_engine._get_recent_narrative_summary(n=2)
        chapter_context = timeline_tree.build_context(
            world=world, world_state=world_state, resolution=resolution,
            chapter_num=chapter_idx, previous_summary=prev_summary or "",
        )
        collision_engine.set_chapter_context(chapter_context)

        if resolution.matched_condition:
            print(f"  [时间树] 第{chapter_idx}章匹配分支：{resolution.matched_condition}，"
                  f"提纲 {len(resolution.branch_outline)} 条")
        elif resolution.base_events:
            print(f"  [时间树] 第{chapter_idx}章：无分支触发，"
                  f"基础事件 {len(resolution.base_events)} 条")

        chapter = collision_engine.start_new_chapter()
        outline = collision_engine._chapter_outline
        if outline:
            print(f"  [本章概要] {outline[:120]}...")

        for char in newcomers:
            if char.char_type != CharType.PROTAGONIST:
                entry_scene = collision_engine.generate_entry_scene(char)
                if entry_scene and entry_scene.entry_narrative:
                    print(f"  [入场叙事] {entry_scene.character_name}："
                          f"{entry_scene.entry_narrative[:60]}...")

        # ── 三层Tick驱动本章内容 ──
        chapter_stats["quality_issues"] = 0
        tick_scheduler.run_chapter(chapter_idx)

        # 收尾章节
        finalized_chapter = collision_engine.finalize_chapter()

        # ── 碰撞后：目标自动微调 ──
        if finalized_chapter and finalized_chapter.collisions:
            for col_event in finalized_chapter.collisions:
                for char_name in [col_event.char_a_name, col_event.char_b_name]:
                    try:
                        adjusted = goal_scheduler.adjust_goal(
                            character_name=char_name,
                            collision_event=col_event,
                            chapter_num=chapter_idx,
                        )
                        if adjusted:
                            print(f"     [目标] {char_name} 目标微调: {adjusted}")
                    except Exception as e:
                        logger.debug(f"目标调度跳过 {char_name}: {e}")

        # ── 碰撞后：角色状态追踪更新（情绪、气息残留等） ──
        if finalized_chapter and finalized_chapter.collisions:
            try:
                goal_scheduler.sync_pending_changes()
            except Exception as e:
                logger.debug(f"状态同步跳过: {e}")

        # 根据碰撞结果更新世界状态
        if finalized_chapter and finalized_chapter.collisions:
            timeline_tree.update_state_from_collisions(world_state, finalized_chapter.collisions)
        if finalized_chapter and finalized_chapter.chapter_text:
            word_count = len(finalized_chapter.chapter_text.replace(" ", "").replace("\n", ""))
            print(f"\n  第 {chapter_idx} 章完成："
                  f"{len(finalized_chapter.collisions)} 次碰撞，"
                  f"{len(finalized_chapter.entry_scenes)} 人入场，"
                  f"约 {word_count} 字")

            # 写入章节文件
            writer.write_chapter(finalized_chapter)

            # ── 大纲智能同步更新 ──
            try:
                writer.update_outline_smart(finalized_chapter, chapter_index=chapter_idx)
            except AttributeError:
                # 回退到旧版 update_outline
                writer.update_outline(finalized_chapter)

            # ── 全局一致性校验 ──
            try:
                consistency_issues = consistency_checker.check_all()
                if consistency_issues:
                    issues_count = len(consistency_issues)
                    if issues_count > 0:
                        print(f"     [一致性] {issues_count} 个问题待处理")
            except Exception as e:
                logger.debug(f"一致性校验跳过: {e}")

            # ── 章节快照 ──
            try:
                writer.save_chapter_snapshot(
                    chapter_index=chapter_idx,
                    world_state=world_state,
                    characters=active_chars,
                )
            except Exception as e:
                logger.debug(f"章节快照跳过: {e}")

            # 质量汇总
            if chapter_stats["quality_issues"] > 0:
                print(f"     [质量汇总] 第{chapter_idx}章共 {chapter_stats['quality_issues']} 个质量问题")
            else:
                print(f"     [质量汇总] 第{chapter_idx}章质量校验通过")

            # 保存碰撞明细
            if finalized_chapter.collisions:
                writer.save_collision_log(
                    chapter_idx,
                    finalized_chapter.collisions,
                )

            # 保存技能快照
            skill_data = []
            for char in active_chars:
                char_skill_set = skill_registry.get_character_skills(char.id)
                if char_skill_set:
                    skill_data.append(char_skill_set.to_dict())
            if skill_data:
                writer.save_skill_snapshot(chapter_idx, skill_data)

            # 记录人物目标追踪
            for char in active_chars:
                char_skill_set = skill_registry.get_character_skills(char.id)
                if char_skill_set:
                    if char.name not in project.goal_tracking:
                        project.goal_tracking[char.name] = {
                            "ultimate": char_skill_set.ultimate_goal,
                            "current_history": [],
                        }
                    project.goal_tracking[char.name]["current_history"].append(
                        char_skill_set.current_goal
                    )

            all_chapters.append(finalized_chapter)
        else:
            print(f"\n  第 {chapter_idx} 章完成（无碰撞事件，内容为空）")

    print()
    print("-" * 60)

    # ---- Step 9: 导出小说 ----
    print("[Step 9] 导出小说...")
    novel_path = writer.export_novel(format="txt")
    if novel_path:
        total_words = writer.get_word_count()
        print(f"  -> 完整小说已导出：{novel_path}")
        print(f"  -> 总字数：约 {total_words} 字")
    else:
        print("  -> 导出失败：没有可导出的章节内容")

    # 保存项目元数据
    writer.save_project()
    print(f"  -> 项目元数据已保存")

    # 打印引擎统计
    stats = collision_engine.get_stats()
    print()
    print("=" * 60)
    print("  运行统计")
    print("=" * 60)
    print(f"  全局 Tick 数：{stats['global_tick']}")
    print(f"  章节数：{stats['chapter_num']}")
    print(f"  总碰撞次数：{stats['total_collisions']}")
    if stats['collision_types']:
        print(f"  碰撞类型分布：")
        for ct, count in stats['collision_types'].items():
            print(f"    - {ct}：{count} 次")
    print(f"  小说总字数：约 {writer.get_word_count()} 字")
    print(f"  输出目录：{output_dir}")
    print()
    print("  演示完成！可查看输出目录中的章节文件和大纲。")
    print("=" * 60)


# ==========================================================================
# 入口
# ==========================================================================
if __name__ == "__main__":
    main()
