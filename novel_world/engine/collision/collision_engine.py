# -*- coding: utf-8 -*-
"""
碰撞引擎 - 人物Skill在世界中对撞，自动生成剧情
核心逻辑：人人带目标入场 + 人人带独立剧情 + 人人有专属技能 + 相遇自动技能碰撞 = 自动生长剧情

碰撞模型说明：
  (1) 感知对冲：一方泄露、一方感知、一方盲区
  (2) 目标对冲：两人目的地相同、目的相反
  (3) 能力对冲：甲的克制点 = 乙的短板
"""
import logging
import os
import re
import time
import uuid
from dataclasses import dataclass, field
from typing import List, Dict, Optional, TYPE_CHECKING, Tuple
from enum import Enum

if TYPE_CHECKING:
    from ..core.character import Character
    from ..core.world import World

# ── Phase 3 集成：导入 agent / beliefs / theory_of_mind / arc_reflection ──
try:
    from novel_world.agent import Agent, MemoryRetriever
    from novel_world.beliefs import Belief, BeliefSystem
    from novel_world.theory_of_mind import TruthTable, propagate_tom_all, detect_type_a, annotate_spec
    from novel_world.arc_reflection import ArcReflector, ArcSummary
    _HAS_PHASE3_MODULES = True
except ImportError as e:
    _HAS_PHASE3_MODULES = False
    logger = logging.getLogger(__name__)
    logger.warning(f"Phase 3 模块导入失败（将跳过增强功能）: {e}")

# ── 权重配置加载 ──
try:
    from .weight_loader import WeightConfig
    _weight_config = WeightConfig.load()
except Exception as e:
    logger = logging.getLogger(__name__)
    logger.warning(f"权重配置加载失败，使用硬编码默认值: {e}")
    _weight_config = None

logger = logging.getLogger(__name__)


# ======================== 对立关键词表 ========================
# 用于目标对冲检测：键与值互为对立目标
_OPPOSITE_KEYWORDS: Dict[str, List[str]] = {
    "保护": ["摧毁", "破坏", "消灭", "抹杀", "杀"],
    "摧毁": ["保护", "守护", "保卫", "防御"],
    "寻找": ["隐藏", "藏匿", "掩埋", "销毁"],
    "隐藏": ["寻找", "搜寻", "追踪", "侦查"],
    "进攻": ["防守", "防御", "退守", "撤退"],
    "防守": ["进攻", "攻击", "入侵", "突袭"],
    "欺骗": ["识破", "揭穿", "真相", "调查"],
    "拯救": ["毁灭", "扼杀", "抛弃", "牺牲"],
    "控制": ["反抗", "挣脱", "逃脱", "自由"],
    "偷取": ["守护", "看守", "保护", "防御"],
    "复活": ["封印", "镇压", "消灭", "阻止"],
    "修炼": ["打断", "干扰", "压制", "封印"],
    "逃亡": ["追捕", "追杀", "围堵", "追踪"],
    "建设": ["破坏", "摧毁", "拆迁", "瓦解"],
    "团结": ["分裂", "挑拨", "离间", "策反"],
}

# 感知类技能关键词
_PERCEPTION_KEYWORDS = ["感知", "侦查", "洞察", "探查", "识破", "追踪",
                        "预言", "占卜", "望气", "神识", "天眼", "直觉", "察觉"]

# 隐匿类技能关键词（与感知互为对抗）
_STEALTH_KEYWORDS = ["隐匿", "潜行", "遁形", "伪装", "隐身", "暗影",
                     "幻术", "障眼", "迷雾", "烟幕", "匿踪", "隐遁"]

# 碰撞检测的空间距离阈值
def _get_proximity_threshold():
    if _weight_config:
        return _weight_config.proximity_threshold
    return 3

_PROXIMITY_THRESHOLD = _get_proximity_threshold()

# 碰撞历史环形上限：超长运行（数百章）时防止内存无限增长
# 消费方均只取最近几条（ToM 取 [-5:]、叙事摘要取最近 2 条），500 条冗余足够
_COLLISION_HISTORY_MAX = 500


class EntryMotivation(Enum):
    """入场动机类型"""
    GOAL_DRIVEN = "目标驱动"       # 为自己的目标而来
    FATE_DRIVEN = "命运牵引"       # 被命运/事件推动
    RELATION_DRIVEN = "关系驱动"   # 被他人关系牵引
    ACCIDENT = "偶然"              # 真正的偶然（极少用）


class CollisionOutcome:
    """碰撞结局基础物理方向（脚本只判定物理事实，脱险方式交给 AI 叙事）

    物理层（脚本判定）：
    - STALEMATE: 实力相当（ratio < 1.5），互有胜负
    - PROBE: 实力略悬殊（1.5 <= ratio < 2.5），谨慎试探
    - ESCAPE: 弱方有逃生技能（事实判定），逃出生天
    - CRUSH: 实力悬殊（ratio >= 2.5）+ 无逃生技能，碾压风险
            → 具体脱险方式由 AI 根据情境选择（见 prompt 指引）

    情境层（交给 AI 在 CRUSH 时选择，不入脚本）：
    - 危险感知/外援介入/奇遇反杀/重伤/被擒/失物等
    """
    CRUSH = "碾压"        # 碾压风险，弱方需脱险（脱险方式由 AI 决定）
    STALEMATE = "僵持"    # 实力相当
    ESCAPE = "逃脱"       # 弱方有逃生技能
    PROBE = "试探"        # 实力略悬殊，谨慎接触
    UNKNOWN = "未知"


@dataclass
class CollisionEvent:
    """碰撞事件 - 两个角色在世界上产生冲突/交集的完整记录"""
    id: str = ""
    tick: int = 0

    # 碰撞双方
    char_a_id: str = ""
    char_a_name: str = ""
    char_b_id: str = ""
    char_b_name: str = ""

    # 碰撞类型和原因
    collision_type: str = ""       # "感知对冲" / "目标对冲" / "能力对冲" / "势力冲突" / "接近碰撞"
    collision_subtype: str = ""    # 子类型："目标-关键词" / "目标-角色关联" / "势力-直接冲突"
    collision_reason: str = ""     # 人类可读的碰撞原因
    collision_weight: int = 0     # 碰撞权重（用于排序，越大越优先）

    # ── 碰撞结局（防止主角横死）──
    outcome_type: str = ""         # CollisionOutcome: 碾压/僵持/逃脱/反杀/试探
    power_gap: float = 0.0         # 实力差距比（强者/弱者）
    weaker_char_id: str = ""       # 弱方角色ID（用于逃跑/奇遇判定）

    # 双方相关技能
    char_a_skill: str = ""         # A方触发技能名
    char_b_skill: str = ""         # B方触发技能名

    # 碰撞上下文
    location: str = ""            # 碰撞发生地点
    world_modifier: str = ""      # 世界规则对碰撞的影响

    # 生成结果
    narrative: str = ""             # AI生成的叙事文本
    dialogue: str = ""              # 碰撞产生的对话
    aftermath: str = ""             # 碰撞后遗症/后果

    # 伏笔和悬念
    new_foreshadowing: List[str] = field(default_factory=list)
    new_crisis: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict:
        """序列化为字典，用于持久化存储"""
        return {
            "id": self.id,
            "tick": self.tick,
            "char_a_id": self.char_a_id,
            "char_a_name": self.char_a_name,
            "char_b_id": self.char_b_id,
            "char_b_name": self.char_b_name,
            "collision_type": self.collision_type,
            "collision_subtype": self.collision_subtype,
            "collision_reason": self.collision_reason,
            "collision_weight": self.collision_weight,
            "outcome_type": self.outcome_type,
            "power_gap": self.power_gap,
            "weaker_char_id": self.weaker_char_id,
            "char_a_skill": self.char_a_skill,
            "char_b_skill": self.char_b_skill,
            "location": self.location,
            "world_modifier": self.world_modifier,
            "narrative": self.narrative,
            "dialogue": self.dialogue,
            "aftermath": self.aftermath,
            "new_foreshadowing": self.new_foreshadowing,
            "new_crisis": self.new_crisis,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> 'CollisionEvent':
        """从字典反序列化"""
        ct = data.get("collision_type", "")
        if hasattr(ct, 'value'):
            ct = ct.value
        return cls(
            id=data.get("id", ""),
            tick=data.get("tick", 0),
            char_a_id=data.get("char_a_id", ""),
            char_a_name=data.get("char_a_name", ""),
            char_b_id=data.get("char_b_id", ""),
            char_b_name=data.get("char_b_name", ""),
            collision_type=ct,
            collision_subtype=data.get("collision_subtype", ""),
            collision_reason=data.get("collision_reason", "") or data.get("reason", ""),
            collision_weight=data.get("collision_weight", 0),
            char_a_skill=data.get("char_a_skill", ""),
            char_b_skill=data.get("char_b_skill", ""),
            location=data.get("location", ""),
            world_modifier=data.get("world_modifier", ""),
            narrative=data.get("narrative", ""),
            dialogue=data.get("dialogue", ""),
            aftermath=data.get("aftermath", ""),
            new_foreshadowing=data.get("new_foreshadowing", []),
            new_crisis=data.get("new_crisis", []),
        )


@dataclass
class EntryScene:
    """角色入场场景 - 每个角色入场时自动生成"""
    character_id: str = ""
    character_name: str = ""
    entry_time: str = ""                        # 入场时间点/剧情节点
    entry_motivation: EntryMotivation = EntryMotivation.GOAL_DRIVEN
    private_purpose: str = ""                    # 私人目的（不是为了配合主角）
    independent_plot: str = ""                   # 独立入场剧情
    entry_state: str = ""                         # 携带的技能/信息/偏见
    entry_narrative: str = ""                    # 生成的入场叙事文本

    def to_dict(self) -> Dict:
        """序列化为字典"""
        return {
            "character_id": self.character_id,
            "character_name": self.character_name,
            "entry_time": self.entry_time,
            "entry_motivation": (
                self.entry_motivation.value
                if isinstance(self.entry_motivation, EntryMotivation)
                else str(self.entry_motivation)
            ),
            "private_purpose": self.private_purpose,
            "independent_plot": self.independent_plot,
            "entry_state": self.entry_state,
            "entry_narrative": self.entry_narrative,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> 'EntryScene':
        """从字典反序列化"""
        mot = data.get("entry_motivation", "目标驱动")
        if isinstance(mot, str):
            try:
                mot_enum = EntryMotivation(mot)
            except ValueError:
                mot_enum = EntryMotivation.GOAL_DRIVEN
        else:
            mot_enum = mot
        return cls(
            character_id=data.get("character_id", ""),
            character_name=data.get("character_name", ""),
            entry_time=data.get("entry_time", ""),
            entry_motivation=mot_enum,
            private_purpose=data.get("private_purpose", ""),
            independent_plot=data.get("independent_plot", ""),
            entry_state=data.get("entry_state", ""),
            entry_narrative=data.get("entry_narrative", ""),
        )


@dataclass
class ChapterTimeline:
    """章节时间线 - 四段式结构
    1. 前置铺垫时序 -> 2. 主角行动时序 -> 3. 配角独立入场时序 -> 4. 收尾收束时序
    """
    chapter_num: int = 0

    # 1. 前置铺垫时序
    prelude: str = ""                              # 上一章伏笔、遗留状态、场景环境

    # 2. 主角行动时序
    protagonist_action: str = ""                   # 主角本章目标、动作、选择、布局

    # 3. 各配角独立入场时序
    entry_scenes: List[EntryScene] = field(default_factory=list)

    # 4. 收尾收束时序
    epilogue: str = ""                              # 残留结果、技能碰撞后遗症、下一章触发条件

    # 本章碰撞事件
    collisions: List[CollisionEvent] = field(default_factory=list)

    # 聚合后的章节正文
    chapter_text: str = ""

    def to_dict(self) -> Dict:
        """序列化为字典"""
        return {
            "chapter_num": self.chapter_num,
            "prelude": self.prelude,
            "protagonist_action": self.protagonist_action,
            "entry_scenes": [es.to_dict() for es in self.entry_scenes],
            "epilogue": self.epilogue,
            "collisions": [c.to_dict() for c in self.collisions],
            "chapter_text": self.chapter_text,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> 'ChapterTimeline':
        """从字典反序列化"""
        entry_scenes = [EntryScene.from_dict(es) for es in data.get("entry_scenes", [])]
        collisions = [CollisionEvent.from_dict(c) for c in data.get("collisions", [])]
        return cls(
            chapter_num=data.get("chapter_num", 0),
            prelude=data.get("prelude", ""),
            protagonist_action=data.get("protagonist_action", ""),
            entry_scenes=entry_scenes,
            epilogue=data.get("epilogue", ""),
            collisions=collisions,
            chapter_text=data.get("chapter_text", ""),
        )


from .collision_mixins import CollisionDetectorMixin, CollisionNarrativeMixin, CollisionEntryMixin


class CollisionEngine(CollisionDetectorMixin, CollisionNarrativeMixin, CollisionEntryMixin):
    """
    碰撞引擎 - 系统心脏
    核心职责：
      1. 扫描角色状态，检测碰撞（感知对冲/目标对冲/能力对冲 + 基于位置的距离碰撞）
      2. 生成碰撞事件
      3. 调用AI将碰撞事件转化为叙事文本
      4. 管理章节时间线（四段式：铺垫 -> 主角行动 -> 配角入场 -> 收尾）
    """

    def __init__(self, world=None, skill_registry=None, ai_client=None):
        """
        初始化碰撞引擎

        Args:
            world: World 实例，用于获取地图/地块信息
            skill_registry: 技能注册表，支持 find_collisions() 方法
            ai_client: AIClient 实例，用于调用AI生成叙事
        """
        self.world = world
        self.skill_registry = skill_registry
        self.ai = ai_client
        self._collision_history: List[CollisionEvent] = []
        self._current_chapter: Optional[ChapterTimeline] = None
        self._chapter_num = 0
        self._chapter_outline: str = ""  # 当前章节的AI推演概要
        self._external_context: str = ""  # 外部注入的章节上下文（时间树提纲+世界状态）
        self._narrative_rules: str = ""  # 叙事风格规则（质量管线注入）
        self._tick_in_chapter = 0
        self._ticks_per_chapter = 20  # 每20个tick聚合为一章
        self._global_tick = 0         # 全局tick计数器
        self._collided_pairs_chapter: set = set()  # 本章已碰撞的 (char_a, char_b, type) 去重
        self._last_finalized_chapter: Optional[ChapterTimeline] = None  # 最近一次收尾的章节

        # ── AI 调用节流配置（控制 token 消耗）──
        # 碰撞分级：S=必用AI, A=概率用AI, B=只用模板
        self.collision_tier_config = {
            "目标对冲": {"tier": "S", "ai_probability": 1.0},
            "势力冲突": {"tier": "S", "ai_probability": 1.0},
            "能力对冲": {"tier": "A", "ai_probability": 0.5},
            "资源争夺": {"tier": "A", "ai_probability": 0.5},
            "感知对冲": {"tier": "B", "ai_probability": 0.0},
            "接近碰撞": {"tier": "B", "ai_probability": 0.0},
        }
        self.ai_collision_quota = 5  # 每章 AI 碰撞次数上限（控制 token）
        self._ai_collisions_used = 0  # 本章已用 AI 碰撞次数
        self.enable_chapter_polish = False  # 章节润色默认关闭（省 token）
        self.max_collision_output_tokens = 120  # 碰撞只生成要点（谁/发生了什么/关系变化）

        # ── Phase 3 集成：Agent / 信念 / 理论心智 / 弧末反思 ──
        self._agent_cache: Dict[str, "Agent"] = {}           # 角色名 → Agent 实例
        self._belief_systems: Dict[str, "BeliefSystem"] = {}  # 角色名 → BeliefSystem
        self._tom_table: Optional["TruthTable"] = None        # 理论心智真值表
        self._arc_reflectors: Dict[str, "ArcReflector"] = {}  # 角色名 → ArcReflector
        self._phase3_enabled: bool = _HAS_PHASE3_MODULES     # 是否启用 Phase 3 增强

    # ======================== 配置方法 ========================

    def _w(self, name: str, default: int = 0) -> int:
        """获取配置化权重值，带默认值兜底

        Args:
            name: 权重键名（与 weights.yaml 中键名一致）
            default: 配置不可用时的硬编码兜底值
        """
        if _weight_config:
            return getattr(_weight_config, name, default)
        return default

    def set_world(self, world):
        """设置世界实例"""
        self.world = world
        logger.info("碰撞引擎：已绑定世界实例")

    def set_skill_registry(self, registry):
        """设置技能注册表"""
        self.skill_registry = registry
        logger.info("碰撞引擎：已绑定技能注册表")

    def set_ai_client(self, ai_client):
        """设置AI客户端"""
        self.ai = ai_client
        logger.info("碰撞引擎：已绑定AI客户端")

    def set_chapter_context(self, context: str):
        """
        设置外部注入的章节上下文（时间树提纲 + 世界状态）。

        此上下文会在 _generate_chapter_outline() 中替换传统 prompt，
        使 AI 根据提纲驱动生成叙事方向，而非凭空推演。

        Args:
            context: 由 TimelineTreeEngine.build_context() 生成的完整上下文字符串
        """
        self._external_context = context
        logger.info(f"碰撞引擎：已接收外部章节上下文（{len(context)} 字符）")

    def set_narrative_rules(self, rules: str):
        """设置叙事风格规则（由质量管线注入），附加到AI叙事prompt末尾。"""
        self._narrative_rules = rules
        logger.info(f"碰撞引擎：已接收叙事规则（{len(rules)} 字符）")

    # ── Phase 3 增强：Agent / 信念 / 理论心智 管理 ──

    def _ensure_agent(self, char_name: str, personality: str = ""):
        """为角色创建 Agent 实例（带独立记忆缓存和信念系统），幂等。"""
        if not self._phase3_enabled:
            return
        if char_name not in self._agent_cache:
            try:
                agent = Agent(agent_id=char_name, name=char_name)
                if personality:
                    agent.set_belief(f"我的性格：{personality}", confidence=0.8)
                self._agent_cache[char_name] = agent
                self._belief_systems[char_name] = BeliefSystem()
                self._arc_reflectors[char_name] = ArcReflector(agent)
                logger.debug(f"Phase3：已为角色 [{char_name}] 创建 Agent/信念/反思器")
            except Exception as e:
                logger.warning(f"Phase3：角色 [{char_name}] Agent 创建失败: {e}")

    def _ensure_agents_for_chars(self, characters: list):
        """批量确保角色 Agent 的就绪状态。"""
        if not self._phase3_enabled:
            return
        for c in characters:
            name = getattr(c, 'name', '') or str(getattr(c, 'id', ''))
            personality = getattr(c, 'personality', '')
            if name:
                self._ensure_agent(name, personality)

    def _ensure_tom_table(self, characters: list):
        """初始化或更新理论心智真值表。"""
        if not self._phase3_enabled:
            return
        try:
            char_names = [getattr(c, 'name', '') or str(getattr(c, 'id', '')) for c in characters]
            char_names = [n for n in char_names if n]
            relations = {}
            # 从 World 提取关系边（如果可用）
            if self.world and hasattr(self.world, 'relations'):
                relations = self.world.relations
            self._tom_table = TruthTable(characters=char_names, relations=relations)
        except Exception as e:
            logger.warning(f"Phase3：ToM 表初始化失败: {e}")

    def _update_beliefs_and_tom(self, event, characters: list):
        """碰撞后更新信念系统 + 理论心智表。

        Hook：碰撞发生 → 更新角色信念 → 记录到 memory → 更新理论心智表
        """
        if not self._phase3_enabled:
            return
        try:
            name_a, name_b = event.char_a_name, event.char_b_name

            # 1. 更新信念：碰撞事件是信念冲击的触发点
            belief_event = f"{event.collision_type}: {event.collision_reason or f'{name_a}与{name_b}相遇'}"
            for name in [name_a, name_b]:
                if name in self._agent_cache:
                    agent = self._agent_cache[name]
                    agent.add_memory(belief_event)

                    # 根据碰撞类型派生信念更新
                    bs = self._belief_systems.get(name)
                    if bs:
                        updates = self._derive_belief_updates(event, name, name_a, name_b)
                        if updates:
                            bs.apply_updates(updates)
                            # 同步到 Agent
                            if hasattr(agent, 'apply_belief_updates'):
                                agent.apply_belief_updates(updates)

            # 2. 更新理论心智表：记录 "A 认为 B 是 X"
            if self._tom_table:
                coll_type = event.collision_type or "接近碰撞"
                fact_desc = f"[{coll_type}] {name_a} vs {name_b}: {event.collision_reason or '角色交锋'}"
                from novel_world.theory_of_mind import Fact
                fact = Fact(
                    fact_id=f"collision_{self._global_tick}_{name_a}_{name_b}",
                    description=fact_desc,
                    known_by={name_a, name_b},
                    source="collision_engine",
                    importance=0.6,
                    tags=[coll_type],
                )
                self._tom_table.facts[fact.fact_id] = fact

                # 3. 传播 ToM：更新所有角色之间的相互认知
                char_names = [getattr(c, 'name', '') or str(getattr(c, 'id', '')) for c in characters]
                all_events = [self._event_to_tom_entry(ev) for ev in self._collision_history[-5:]]
                propagate_tom_all(self._tom_table, all_events, char_names, {})

                # 4. 检测 Type-A 秘密冲突，标记高优先级
                for name in [name_a, name_b]:
                    a_alerts = detect_type_a(self._tom_table, name)
                    if a_alerts:
                        logger.info(f"Phase3：角色 [{name}] 触发 Type-A 秘密冲突: {len(a_alerts)} 项")
        except Exception as e:
            logger.warning(f"Phase3：信念/ToM 更新失败（不影响核心流程）: {e}")

    def _derive_belief_updates(self, event, target_name: str, name_a: str, name_b: str) -> list:
        """从碰撞事件派生信念更新。"""
        updates = []
        other = name_b if target_name == name_a else name_a
        coll_type = event.collision_type or ""
        if "目标对冲" in coll_type:
            updates.append({"belief_id": f"信任_{other}", "delta": -0.15, "reason": "目标对立"})
        elif "能力对冲" in coll_type:
            updates.append({"belief_id": f"实力评估_{other}", "delta": 0.10, "reason": "能力对抗"})
        elif "感知对冲" in coll_type:
            updates.append({"belief_id": f"信息对称_{other}", "delta": 0.05, "reason": "信息感知"})
        return updates

    @staticmethod
    def _event_to_tom_entry(event) -> dict:
        """将 CollisionEvent 转为 ToM 事件条目。"""
        return {
            "type": event.collision_type or "collision",
            "char_a": event.char_a_name,
            "char_b": event.char_b_name,
            "description": event.collision_reason or "",
            "tick": event.tick,
        }

    # ======================== 章节管理 ========================

    def start_new_chapter(self) -> ChapterTimeline:
        """
        开始新章节
        如果当前章节存在，会先自动 finalize

        Returns:
            新创建的 ChapterTimeline
        """
        # 若有未结束的旧章节，先收尾
        if self._current_chapter is not None:
            logger.warning(f"碰撞引擎：第{self._chapter_num}章未收尾，自动执行 finalize")
            self.finalize_chapter()

        self._chapter_num += 1
        self._tick_in_chapter = 0

        chapter = ChapterTimeline(chapter_num=self._chapter_num)

        # 从上一章的收尾提取伏笔作为本章节的铺垫
        if self._collision_history:
            last_chapter_events = [
                e for e in self._collision_history
                if e.new_foreshadowing or e.aftermath
            ]
            if last_chapter_events:
                latest = last_chapter_events[-1]
                prelude_parts = []
                if latest.aftermath:
                    prelude_parts.append(f"上章余波：{latest.aftermath}")
                for fs in latest.new_foreshadowing[-3:]:  # 最多取3条伏笔
                    prelude_parts.append(f"伏笔待解：{fs}")
                chapter.prelude = "。".join(prelude_parts)

        self._current_chapter = chapter
        self._collided_pairs_chapter.clear()
        self._ai_collisions_used = 0  # 重置本章 AI 碰撞计数

        # AI 推演本章剧情方向
        self._chapter_outline = self._generate_chapter_outline()

        logger.info(f"碰撞引擎：开始第{self._chapter_num}章")
        return chapter

    def _goal_directed_move(self, characters: list):
        """目标驱动移动：每个角色向最近的其他存活角色移动"""
        for char in characters:
            if not getattr(char, 'alive', True):
                continue

            # 找到最近的其他存活角色
            nearest = None
            min_dist = float('inf')
            for other in characters:
                if other is char or not getattr(other, 'alive', True):
                    continue
                dist = abs(char.pos[0] - other.pos[0]) + abs(char.pos[1] - other.pos[1])
                if dist < min_dist:
                    min_dist = dist
                    nearest = other

            if nearest is None:
                continue

            # 向目标移动 1-2 格
            dx = 1 if nearest.pos[0] > char.pos[0] else (-1 if nearest.pos[0] < char.pos[0] else 0)
            dy = 1 if nearest.pos[1] > char.pos[1] else (-1 if nearest.pos[1] < char.pos[1] else 0)

            steps = min(2, min_dist)

            new_x = max(0, min(self.world.map_size[0] - 1, char.pos[0] + dx * steps))
            new_y = max(0, min(self.world.map_size[1] - 1, char.pos[1] + dy * steps))
            char.pos = (new_x, new_y)

    def tick(self, characters: list) -> Optional[CollisionEvent]:
        """
        每个tick执行一次碰撞检测
        先执行目标驱动移动，然后检测碰撞

        Args:
            characters: 当前世界中的角色列表

        Returns:
            本tick检测到的碰撞事件（可能为None）
        """
        self._global_tick += 1
        self._tick_in_chapter += 1

        if not characters or len(characters) < 2:
            return None

        # 过滤存活角色
        alive_chars = [c for c in characters if getattr(c, 'alive', True)]
        if len(alive_chars) < 2:
            return None

        # Phase 3：确保所有存活角色有 Agent 实例
        self._ensure_agents_for_chars(alive_chars)

        # 目标驱动移动：让角色互相靠近
        self._goal_directed_move(alive_chars)

        # 执行碰撞检测
        events = self._detect_collisions(alive_chars)

        # 如果有碰撞事件，按碰撞权重排序并去重
        if events:
            # 按 collision_weight 降序排列（权重越高越优先）
            # 权重体系：目标-角色关联(100/80) > 目标-关键词(50) = 势力冲突(50)
            #          > 能力对冲(默认0) > 感知对冲(默认0) > 接近碰撞(默认0)
            events.sort(key=lambda e: getattr(e, 'collision_weight', 0), reverse=True)

            # 过滤本章已发生的同类型碰撞（角色ID排序去重，双向视为同一对）
            fresh_events = []
            for ev in events:
                pair_key = tuple(sorted([ev.char_a_id, ev.char_b_id])) + (ev.collision_type,)
                if pair_key not in self._collided_pairs_chapter:
                    fresh_events.append(ev)
            if not fresh_events:
                # 所有碰撞均已在本章发生过，检查自动收尾
                if self._tick_in_chapter >= self._ticks_per_chapter and self._current_chapter:
                    logger.info(f"碰撞引擎：tick已达{self._ticks_per_chapter}，自动收尾第{self._chapter_num}章")
                    self.finalize_chapter()
                return None
            main_event = fresh_events[0]
            self._collided_pairs_chapter.add(
                tuple(sorted([main_event.char_a_id, main_event.char_b_id])) + (main_event.collision_type,)
            )

            # 为碰撞事件生成叙事
            main_event.narrative = self._generate_collision_narrative(main_event)

            # 记录到历史和当前章节（环形上限防内存膨胀）
            self._record_history(main_event)
            if self._current_chapter is not None:
                self._current_chapter.collisions.append(main_event)

            # Phase 3：碰撞后更新信念系统 + 理论心智表
            self._update_beliefs_and_tom(main_event, alive_chars)

            logger.info(
                f"碰撞引擎 tick#{self._global_tick}："
                f"{main_event.char_a_name} vs {main_event.char_b_name} "
                f"[{main_event.collision_type}] {main_event.collision_reason}"
            )
            return main_event

        # 检查是否需要自动收尾章节
        if self._tick_in_chapter >= self._ticks_per_chapter and self._current_chapter:
            logger.info(
                f"碰撞引擎：tick已达{self._ticks_per_chapter}，自动收尾第{self._chapter_num}章"
            )
            self.finalize_chapter()

        return None



    # ======================== 查询方法 ========================

    def _record_history(self, event: CollisionEvent):
        """记录碰撞到历史，环形上限防止超长运行内存膨胀"""
        self._collision_history.append(event)
        if len(self._collision_history) > _COLLISION_HISTORY_MAX:
            self._collision_history = self._collision_history[-_COLLISION_HISTORY_MAX:]

    def get_collision_history(self) -> List[CollisionEvent]:
        """获取全部碰撞历史"""
        return list(self._collision_history)

    def get_current_chapter(self) -> Optional[ChapterTimeline]:
        """获取当前活跃章节"""
        return self._current_chapter

    def get_stats(self) -> Dict:
        """获取引擎运行统计信息"""
        return {
            "global_tick": self._global_tick,
            "chapter_num": self._chapter_num,
            "tick_in_chapter": self._tick_in_chapter,
            "total_collisions": len(self._collision_history),
            "collision_types": self._count_collision_types(),
        }

    def _count_collision_types(self) -> Dict[str, int]:
        """统计各碰撞类型的数量"""
        counts: Dict[str, int] = {}
        for event in self._collision_history:
            ct = event.collision_type or "未知"
            counts[ct] = counts.get(ct, 0) + 1
        return counts
