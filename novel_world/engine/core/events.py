# -*- coding: utf-8 -*-
"""
\u53d9\u4e8b\u5f15\u64ce - AI\u9a71\u52a8\u7684\u4e16\u754c\u53d9\u8ff0\u751f\u6210
"""

# === 导入人生重开事件池 ===
try:
    from .life_restart_event_pool import get_event_pool
    _HAS_EVENT_POOL = True
except ImportError:
    _HAS_EVENT_POOL = False

# 事件触发管理器
try:
    from .event_trigger_manager import get_trigger_manager
    _HAS_TRIGGER_MANAGER = True
except ImportError:
    _HAS_TRIGGER_MANAGER = False


import re
import random
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from .world import World
    from .ai_client import AIClient

# 导入新的参数库
try:
    from .character_params import get_character_params
    from .scene_params import get_scene_params
    from .plot_nodes import get_plot_node_manager
    _HAS_PARAM_LIBS = True
except ImportError:
    _HAS_PARAM_LIBS = False

from .character import CharType

# 导入模板解析器和验证器
try:
    from .template_parser import NarrativeValidator
    _HAS_VALIDATOR = True
except ImportError:
    _HAS_VALIDATOR = False

# 导入白城主的记忆管理器
try:
    from utils.memory_manager import MemoryManager
    _HAS_MEMORY_MANAGER = True
except ImportError:
    _HAS_MEMORY_MANAGER = False

# 导入白城主的自我进化系统
# 独立版：self_evolution 为可选依赖
try:
    from core.self_evolution import get_self_evolution_manager
    _HAS_SELF_EVOLUTION = True
except ImportError:
    get_self_evolution_manager = None
    _HAS_SELF_EVOLUTION = False

# 导入新的记忆系统（事件记忆、关系追踪、叙事去重）
try:
    from .event_memory import get_event_memory, EventMemory
    from .relationship_tracker import get_relationship_tracker, RelationshipTracker
    from .narrative_dedup import get_narrative_deduplicator, NarrativeDeduplicator
    _HAS_MEMORY_SYSTEMS = True
except ImportError:
    _HAS_MEMORY_SYSTEMS = False

# Phase 3 集成：TruthLedger 增强 + 禁词常量
try:
    from novel_world.engine.memory.truth_ledger_enhanced import LedgerEnhancer
    _HAS_LEDGER_ENHANCER = True
except ImportError:
    _HAS_LEDGER_ENHANCER = False

try:
    from novel_world.engine.quality.constants import FORBIDDEN_WORDS, FORBIDDEN_PLOTS, NARRATIVE_STYLE_GUIDE
    _HAS_CONSTANTS = True
except ImportError:
    _HAS_CONSTANTS = False
    FORBIDDEN_WORDS = []
    FORBIDDEN_PLOTS = []
    NARRATIVE_STYLE_GUIDE = {}

import logging
logger = logging.getLogger(__name__)

# === Mixin 导入（从 NarrativeEngine 拆分出的功能域） ===
from .narrative_mixins.narrative_template import NarrativeTemplateMixin
from .narrative_mixins.narrative_validator import NarrativeValidatorMixin
from .narrative_mixins.narrative_memory import NarrativeMemoryMixin
from .narrative_mixins.narrative_prompts import NarrativePromptsMixin


class NarrativeEngine(NarrativeTemplateMixin, NarrativeValidatorMixin, NarrativeMemoryMixin, NarrativePromptsMixin):
    """叙事引擎 - 每个 tick 生成一段叙述"""

    def __init__(self, ai_client=None, theme="日常", merged_rules=None, game_config=None, plot=None):
        self.ai = ai_client
        self.theme = theme
        self._game_config = game_config  # 完整的游戏设定
        self._merged_rules = merged_rules  # 合并后的最终规则
        self._plot = plot  # 新增：主线剧情信息
        
        # 打印 plot 信息用于调试
        if plot:
            print(f"[DEBUG] NarrativeEngine 接收到主线剧情:")
            print(f"  start_event: {plot.get('start_event', '')[:50]}...")
            print(f"  core_suspense: {plot.get('core_suspense', '')[:50]}...")
            print(f"  subplots: {len(plot.get('subplots', []))} 个支线")
        
        # 使用白城主的五层记忆系统
        if _HAS_MEMORY_MANAGER:
            self._memory = MemoryManager()
            self._use_memory_manager = True
            print("[OK] 游戏已接入白城主五层记忆系统")
            
            # 自动清理记忆（如果需要）
            try:
                self._memory.auto_cleanup_if_needed()
            except Exception:
                pass
            # 即使使用MemoryManager，也初始化_story_context以保持兼容性
            self._story_context = ""
            self._max_context = 2000
        else:
            # 回退到简单的记忆系统
            self._story_context = ""
            self._max_context = 2000
            self._long_term_memory = []
            self._max_long_term = 50
            self._use_memory_manager = False
            print("[!] MemoryManager 不可用，使用简单记忆系统")
        
        # 兼容旧代码的属性
        self._key_events = []
        self._max_key_events = 15
        self._unresolved_threads = []  # 未解决的悬念
        self._max_threads = 8
        
        # 接入白城主的自我进化系统
        if _HAS_SELF_EVOLUTION:
            try:
                self._self_evolution = get_self_evolution_manager()
                print("[OK] 游戏已接入白城主自我进化系统")
            except Exception as e:
                print(f"[!] 自我进化系统初始化失败: {e}")
                self._self_evolution = None
        else:
            self._self_evolution = None
        
        # 白城主的成长系统（需要外部设置）
        self._growth_system = None
        
        # 游戏配置（用于叙事格式验证）
        if self._game_config is None:
            self._game_config = {}

        
        # === 初始化参数库 ===
        if _HAS_PARAM_LIBS:
            self._character_params = get_character_params()
            self._scene_params = get_scene_params()
            self._plot_node_manager = get_plot_node_manager()
        else:
            self._character_params = None
            self._scene_params = None
            self._plot_node_manager = None
        
        # === 调试模式 ===
        self._debug_mode = False

        # 事件触发管理器
        if _HAS_TRIGGER_MANAGER:
            self._trigger_manager = get_trigger_manager()
        else:
            self._trigger_manager = None
        self._last_selected_events = []  # 最近选择的事件ID列表
        self._world_ref = None  # 世界对象引用  # 设置为True启用调试输出

        # === 初始化新的记忆系统 ===
        if _HAS_MEMORY_SYSTEMS:
            self._event_memory = get_event_memory()
            self._relationship_tracker = get_relationship_tracker()
            self._narrative_deduplicator = get_narrative_deduplicator()
            self._current_tick = 0
            print("[OK] 叙事引擎已集成事件记忆、关系追踪、叙事去重系统")
        else:
            self._event_memory = None
            self._relationship_tracker = None
            self._narrative_deduplicator = None
            self._current_tick = 0

        # Phase 3：TruthLedger 增强器
        if _HAS_LEDGER_ENHANCER:
            self._ledger_enhancer = LedgerEnhancer(None)
            self._ledger_enhancer_enabled = True
            print("[OK] 叙事引擎已集成 TruthLedger 增强器")
        else:
            self._ledger_enhancer = None
            self._ledger_enhancer_enabled = False

    
    def set_world(self, world):
        """设置世界对象"""
        self._world_ref = world
        if self._trigger_manager:
            self._trigger_manager.set_world(world)
        # 同时设置到事件池
        if _HAS_EVENT_POOL:
            try:
                event_pool = get_event_pool()
                if hasattr(event_pool, 'set_world'):
                    event_pool.set_world(world)
            except Exception:
                pass

    # ── Phase 3：TruthLedger 增强器集成 ──

    def set_ledger(self, ledger):
        """
        设置 TruthLedger 实例，供 LedgerEnhancer 使用。

        由 adapter.py 在初始化后调用，传入 TruthLedger 实例。
        """
        if self._ledger_enhancer_enabled and self._ledger_enhancer and ledger:
            self._ledger_enhancer._ledger = ledger
            print("[OK] TruthLedger 增强器已绑定 ledger 实例")

    def archive_chapter(self, chapter_num: int):
        """
        Phase 3：章节结束时生成 TruthLedger 快照。

        由 adapter.py 在每个章节结束时调用。
        """
        if not self._ledger_enhancer_enabled or not self._ledger_enhancer:
            return
        try:
            snapshot = self._ledger_enhancer.create_snapshot(chapter_num, version=f"ch{chapter_num:03d}")
            logger.info(f"Phase3：第{chapter_num}章 TruthLedger 快照已生成")
            return snapshot
        except Exception as e:
            logger.warning(f"Phase3：章节快照生成失败: {e}")
            return None

    def _record_ledger_event(self, event_type: str, event_data: dict):
        """
        Phase 3：事件推演时将事件记录到 TruthLedger 增强器。
        覆盖 artifact（道具位移）、location_shift（位置变化）、faction_change（派系变化）。
        """
        if not self._ledger_enhancer_enabled or not self._ledger_enhancer:
            return
        try:
            enh = self._ledger_enhancer
            if event_type == "artifact" and "item_name" in event_data:
                enh.add_artifact(event_data["item_name"], event_data.get("note", ""))
            elif event_type == "location_shift" and "character" in event_data:
                enh.record_location_shift(
                    event_data["character"],
                    event_data.get("from_loc", ""),
                    event_data.get("to_loc", "")
                )
            elif event_type == "faction_change" and "character" in event_data:
                enh.record_faction_change(
                    event_data["character"],
                    event_data.get("from_faction", ""),
                    event_data.get("to_faction", "")
                )
        except Exception as e:
            logger.warning(f"Phase3：Ledger 事件记录失败: {e}")

    def generate_tick_narrative(self, world, characters, ai_config=None):
        alive = [c for c in characters if c.alive]
        if not alive:
            return "\u4e16\u754c\u4e00\u7247\u6b89\u9759\u3002"
        # === 剧情节点管理 ===
        if self._plot_node_manager:
            # 【新增】同步成长阶段
            if self._growth_system:
                try:
                    from .plot_nodes import GrowthStage
                    stage_map = {
                        "infant": GrowthStage.INFANT,
                        "growing": GrowthStage.GROWING,
                        "adult": GrowthStage.ADULT
                    }
                    new_stage = stage_map.get(self._growth_system.current_stage.value, GrowthStage.INFANT)
                    if self._plot_node_manager.get_current_stage() != new_stage:
                        self._plot_node_manager.set_growth_stage(new_stage)
                except Exception:
                    pass

            # 如果没有当前节点，开始新剧情
            if not self._plot_node_manager.get_current_node():
                self._plot_node_manager.start_new_plot()
            
            # 检查是否应该收尾
            if self._plot_node_manager.check_should_end():
                # 强制推进到收尾节点
                self._plot_node_manager._current_node = "收尾"
        

        if self.ai and self.ai.is_available:
            narrative = self._ai_generate(world, alive, ai_config or {})
            if narrative:
                narrative = self._clean_output(narrative)
                narrative = self._validate_narrative_comprehensive(narrative, world, alive)

                # === 增强去重检查 ===
                try:
                    narrative = self._check_repetition(narrative, world)
                    if not narrative or len(narrative) < 20:
                        narrative = self._template_fallback(world, alive)
                except Exception:
                    pass
                
                # === 剧情推进判定 ===
                if self._plot_node_manager:
                    # 验证内容是否有推进
                    has_progress = self._plot_node_manager.validate_content_has_progress(narrative)
                    if not has_progress:
                        # 内容无推进，尝试触发冲突/转机
                        conflict = self._plot_node_manager.try_trigger_conflict()
                        if conflict:
                            narrative += f"\\n（{conflict.description}）"
                    
                    # 推进到下一节点
                    self._plot_node_manager.advance_to_next_node()
                    self._plot_node_manager.increment_paragraph()
                # 检测并处理重复叙事
                if narrative:
                    self._update_context(narrative)
                    self.update_memory(world, 0)
                    self._extract_threads(narrative, alive)
                    
                    # 触发白城主的自我进化
                    self._trigger_self_evolution(narrative)
                    
                    # === 使用新的记忆系统处理叙事 ===
                    if _HAS_MEMORY_SYSTEMS:
                        narrative = self._process_with_memory_systems(narrative, world, alive, world.current_time)
                    
                    return narrative
        narrative = self._template_fallback(world, alive)
        # 检测并处理重复叙事
        try:
            narrative = self._check_repetition(narrative, world)
        except Exception:
            pass  # 如果重复检测出错，继续使用原叙事
        self._update_context(narrative)
        self.update_memory(world, 0)
        self._extract_threads(narrative, alive)
        return narrative

    def _ai_generate(self, world, alive_chars, ai_config):
        system_prompt, user_prompt = self._build_prompts(world, alive_chars, ai_config)
        if system_prompt is None or user_prompt is None:
            return None
        return self.ai.generate(system_prompt, user_prompt)

    def set_merged_rules(self, merged_rules):
        """运行时更新合并规则"""
        self._merged_rules = merged_rules

    def _get_location_name(self, world, char):
        tile = world.get_tile(*char.pos)
        if tile and tile.name:
            return tile.name
        elif tile:
            return tile.tile_type.value
        return f"({char.pos[0]},{char.pos[1]})"

    def _check_repetition(self, narrative, world=None):
        """检测重复内容，若与近期叙述过于相似则替换"""
        try:
            if not self._story_context or len(narrative) < 5:
                return narrative
            # 取近期上下文做简单比对
            recent = self._story_context[-200:]
            # 提取叙述中的关键词（去除常用字）
            import re
            stop_words = set("的了在上中下和与对到这那就是也不过得要可以已从以前还没有然后但又一个很多都自己来说去看着吗什么怎么业技只能大家因为要不要出去回来没关系却又有点再给了发过两个三个地方时候可能发生一些几乎稍微一下一会感觉很好")
            words_n = set(re.findall(r'[一-鿿]{2,}', narrative)) - stop_words
            words_r = set(re.findall(r'[一-鿿]{2,}', recent)) - stop_words
            if not words_n:
                return narrative
            # 计算重叠率
            overlap = words_n & words_r
            if len(words_n) > 0 and len(overlap) / len(words_n) > 0.6:
                # 太相似，用模板重新生成
                if world is None:
                    return narrative  # 如果没有 world，返回原叙事
                return self._template_fallback_no_dup(world, None)
        except Exception:
            pass
        return narrative

    def _clean_output(self, text):

        if not text:
            return ""
        text = re.sub(r"<think[\s\S]*?</think\s*>", "", text).strip()
        text = re.sub(r"<think[\s\S]*", "", text).strip()
        if text.startswith("Thinking Process"):
            parts = re.split(r"\n{2,}", text)
            for part in parts:
                sp = part.strip()
                if sp and not sp.startswith(("Thinking", "1.", "2.", "Step", "Analyze", "Role", "Task", "Output", "*")):
                    text = sp
                    break
            else:
                text = ""
        lines = text.split("\n")
        cleaned = []
        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue
            if stripped.startswith(("Thinking", "1.", "2.", "3.", "4.", "Step", "Analyze", "Role:", "Task:", "Output:")):
                continue
            if re.match(r"^\*\*[A-Z]", stripped):
                continue
            cleaned.append(line)
        return "\n".join(cleaned)

    def _trigger_self_evolution(self, narrative: str):
        """触发白城主的自我进化和成长系统"""
        # 1. 触发自我进化系统
        if self._self_evolution:
            try:
                user_input = f"[游戏叙事] {self.theme}主题"
                bot_response = narrative
                self._self_evolution.record_conversation(user_input, bot_response)
            except Exception as e:
                import logging
                logging.getLogger(__name__).debug(f"自我进化记录失败: {e}")
        
        # 2. 触发成长系统（使用白城主的同一个实例）
        if self._growth_system:
            try:
                # 记录交互 - 这会增加参数规模
                self._growth_system.record_interaction("chat", success=True)
                self._growth_system.record_interaction("memory_added", success=True)
                
                # 记忆数也增加
                self._growth_system.total_memories += 1
                
                # 保存并检查阶段升级
                self._growth_system._save_growth_data()
                self._growth_system._check_stage_progression()
                self._growth_system._check_ability_unlocks()
                
            except Exception as e:
                import logging
                logging.getLogger(__name__).debug(f"成长系统记录失败: {e}")




    def set_growth_system(self, growth_system):
        """设置白成竹的成长系统实例"""
        self._growth_system = growth_system
        print("? 游戏已接入白成竹成长系统")
        
        # 【新增】同步成长阶段到剧情节点管理器
        if self._plot_node_manager and growth_system:
            try:
                from .plot_nodes import GrowthStage
                stage_map = {
                    "infant": GrowthStage.INFANT,
                    "growing": GrowthStage.GROWING,
                    "adult": GrowthStage.ADULT
                }
                current_stage = stage_map.get(growth_system.current_stage.value, GrowthStage.INFANT)
                self._plot_node_manager.set_growth_stage(current_stage)
                print(f"? 剧情节点已同步到成长阶段: {current_stage.value}")
            except Exception as e:
                print(f"? 同步成长阶段失败: {e}")

    def set_game_config(self, config):
        self._game_config = config

# ============================================================
# 严格的主角目标校验系统 - 事件必须围绕主角目标展开
# ============================================================

def validate_protagonist_focus_strict(narrative: str, protagonist, world_rules: dict = None) -> tuple:
    """
    严格检查事件是否围绕主角目标展开
    
    规则：
    1. 事件内容 -> 直接影响主角当前目标（推进/阻碍/揭示线索）
    2. 事件形式 -> 符合当前世界观规则
    3. 无关联目标的事件，直接过滤不生成
    
    返回: (is_valid, impact_type, message)
    impact_type: "推进" | "阻碍" | "揭示线索" | "过渡" | "无关"
    """
    if not protagonist:
        return (True, "无关", "无主角设定")
    
    # 1. 提取主角目标关键词
    goal = protagonist.goal or ""
    goal_keywords = _extract_goal_keywords(goal)
    
    # 2. 分析事件内容，判断影响类型
    impact_type = _analyze_impact_type(narrative, protagonist.name, goal_keywords)
    
    # 3. 如果是无关事件，检查是否有特殊情况
    if impact_type == "无关":
        # 检查是否是必要的过渡事件
        if _is_necessary_transition(narrative):
            return (True, "过渡", "必要过渡事件")
        else:
            return (False, "无关", "【过滤】事件与主角目标无关，不应生成")
    
    # 4. 校验事件形式是否符合世界观规则
    if world_rules:
        is_valid, msg = _validate_world_rules(narrative, world_rules)
        if not is_valid:
            return (False, impact_type, f"【过滤】{msg}")
    
    return (True, impact_type, f"事件符合规则，影响类型：{impact_type}")


def _extract_goal_keywords(goal: str) -> list:
    """从主角目标中提取关键词"""
    if not goal:
        return []
    
    keywords = []
    
    # 常见的目标动词
    goal_verbs = [
        "寻找", "找到", "救", "拯救", "击败", "打败", "获得", "得到",
        "发现", "探索", "调查", "追查", "追踪", "保护", "守护",
        "逃离", "逃出", "返回", "回去", "前往", "到达", "进入",
        "解开", "破解", "完成", "实现", "达成", "阻止", "阻止"
    ]
    
    for verb in goal_verbs:
        if verb in goal:
            keywords.append(verb)
    
    # 提取名词（简单的分词，取2-4字的词）
    for i in range(len(goal)):
        for length in range(2, 5):
            if i + length <= len(goal):
                word = goal[i:i+length]
                # 过滤常见虚词
                if word not in ["的", "了", "是", "在", "有", "和", "与", "或", "我", "要", "把", "被", "给", "向", "从", "到"]:
                    keywords.append(word)
    
    # 去重并返回
    return list(set(keywords))[:15]  # 最多15个关键词


def _analyze_impact_type(narrative: str, protagonist_name: str, goal_keywords: list) -> str:
    """
    分析事件对主角目标的影响类型
    返回: "推进" | "阻碍" | "揭示线索" | "无关"
    """
    
    # 1. 检查推进型事件
    progress_verbs = [
        "成功", "完成", "获得", "得到", "找到", "发现", "到达", "进入",
        "击败", "战胜", "救出", "拯救", "解开", "破解", "实现", "达成"
    ]
    for verb in progress_verbs:
        if verb in narrative:
            # 检查是否与目标相关
            if any(kw in narrative for kw in goal_keywords):
                return "推进"
            # 如果主角在叙述中，也认为是推进
            if protagonist_name in narrative:
                return "推进"
    
    # 2. 检查阻碍型事件
    obstacle_patterns = [
        "失败", "受阻", "困难", "危险", "敌人", "对手", "陷阱", "危机",
        "受伤", "被困", "迷路", "丢失", "被抢", "被阻", "遭遇", "陷入"
    ]
    for pattern in obstacle_patterns:
        if pattern in narrative and protagonist_name in narrative:
            return "阻碍"
    
    # 3. 检查揭示线索型事件
    clue_verbs = ["发现", "得知", "了解", "看到", "听到", "注意到", "意识到", "察觉", "获知"]
    clue_nouns = ["线索", "秘密", "真相", "证据", "提示", "消息", "情报", "踪迹", "痕迹", "记录"]
    
    for verb in clue_verbs:
        if verb in narrative:
            for noun in clue_nouns:
                if noun in narrative:
                    return "揭示线索"
            # 如果发现的是目标相关内容
            if any(kw in narrative for kw in goal_keywords):
                return "揭示线索"
    
    # 4. 检查主角是否在叙述中
    if protagonist_name in narrative:
        # 检查是否有目标相关内容
        for kw in goal_keywords:
            if kw in narrative:
                return "推进"  # 默认认为是推进
        
        # 检查是否有行动动词
        action_verbs = ["前往", "走向", "进入", "离开", "开始", "准备", "出发", "行动"]
        for verb in action_verbs:
            if verb in narrative:
                return "推进"
    
    return "无关"


def _is_necessary_transition(narrative: str) -> bool:
    """检查是否是必要的过渡事件"""
    # 必要的过渡事件类型（允许生成）
    transition_patterns = [
        "时间流逝", "天气变化", "环境描写", "氛围营造",
        "夜幕降临", "天色渐暗", "黎明到来", "日上三竿",
        "休息", "准备", "整装", "出发", "启程", "启程",
        "思考", "回忆", "沉思", "等待", "观察"
    ]
    
    for pattern in transition_patterns:
        if pattern in narrative:
            return True
    
    # 检查是否是纯环境描写（没有角色互动）
    has_character_action = any(kw in narrative for kw in ["说", "做", "走", "跑", "看", "听", "想", "拿", "放", "打开", "关闭"])
    if not has_character_action and len(narrative) < 100:
        return True  # 短小的纯环境描写允许
    
    return False


def _validate_world_rules(narrative: str, world_rules: dict) -> tuple:
    """校验事件形式是否符合世界观规则"""
    if not world_rules:
        return (True, "")
    
    # 检查权限
    perms = world_rules.get("permissions", {})
    
    # 如果禁止魔法，但事件中有魔法
    if not perms.get("allow_magic", True):
        magic_keywords = ["魔法", "法术", "咒语", "魔力", "施法", "念咒", "法阵", "灵力", "仙术"]
        if any(kw in narrative for kw in magic_keywords):
            return (False, "事件违反世界观规则：禁止魔法/超能力")
    
    # 如果禁止战斗，但事件中有战斗
    if not perms.get("allow_combat", True):
        combat_keywords = ["战斗", "打斗", "厮杀", "交战", "对打", "攻击", "杀", "砍", "刺"]
        if any(kw in narrative for kw in combat_keywords):
            return (False, "事件违反世界观规则：禁止战斗/杀戮")
    
    # 如果禁止现代物品，但事件中有现代物品
    if not perms.get("allow_modern_items", True):
        modern_keywords = ["手机", "电脑", "汽车", "飞机", "电视", "网络", "互联网", "APP", "微信"]
        if any(kw in narrative for kw in modern_keywords):
            return (False, "事件违反世界观规则：禁止现代物品")
    
    # 检查禁词
    forbidden = world_rules.get("forbidden_words", [])
    for word in forbidden:
        if word and word in narrative:
            return (False, f"事件包含禁止词汇：{word}")
    
    # 检查铁律
    iron_rules = world_rules.get("iron_rules", [])
    for rule in iron_rules:
        # 铁律是必须遵守的，检查是否违反
        if "禁止" in rule:
            # 提取禁止的内容
            import re
            match = re.search(r"禁止(.+)", rule)
            if match:
                forbidden_content = match.group(1)
                if forbidden_content in narrative:
                    return (False, f"事件违反铁律：{rule}")
    
    return (True, "")


def filter_narrative_by_protagonist_goal(narrative: str, protagonist, world_rules: dict = None) -> tuple:
    """
    过滤叙事内容，确保符合主角目标规则
    
    返回: (filtered_narrative, is_valid, impact_type, message)
    如果 is_valid=False，filtered_narrative 为空字符串（过滤掉）
    """
    is_valid, impact_type, message = validate_protagonist_focus_strict(narrative, protagonist, world_rules)
    
    if is_valid:
        return (narrative, True, impact_type, message)
    else:
        # 过滤掉无关联事件
        return ("", False, impact_type, message)


# ============================================================
# 其他规则校验函数
# ============================================================

def validate_no_random_npc(narrative: str, known_characters: list) -> tuple:
    """检查是否有无设定无关联的无名NPC"""
    import re
    # 常见的路人名字模式
    random_names = ["小明", "小红", "小强", "小李", "小王", "小张", "小雪", "小美", 
                   "李青云", "周辰", "王伟", "张三", "李四", "路人", "某人"]
    
    violations = []
    for name in random_names:
        if name in narrative:
            # 检查这个角色是否在已知角色列表中
            if not any(name in str(c.name) for c in known_characters):
                violations.append(f"发现无名NPC: {name}")
    
    return (len(violations) == 0, violations)


def validate_antagonist_behavior(narrative: str, antagonist) -> tuple:
    """检查反派行为是否符合设定"""
    if not antagonist:
        return (True, [])
    
    violations = []
    
    # 检查反派是否被写成可探索、可移动、可死亡的普通角色
    if hasattr(antagonist, 'personality') and antagonist.personality:
        if "不可对抗" in antagonist.personality or "无理智" in antagonist.personality:
            if any(kw in narrative for kw in ["击败了" + antagonist.name, "杀死了" + antagonist.name, antagonist.name + "被击败"]):
                violations.append(f"反派 {antagonist.name} 行为与设定矛盾")
    
    return (len(violations) == 0, violations)


def validate_no_random_death_ending(narrative: str, known_characters: list) -> tuple:
    """检查是否有无名路人死亡强行结尾"""
    import re
    
    tail = narrative[-80:] if len(narrative) > 80 else narrative
    
    death_keywords = ["死", "亡", "牺牲", "去世", "毙命"]
    random_names = ["小明", "小红", "小强", "路人", "某人", "陌生人"]
    
    for name in random_names:
        for death in death_keywords:
            if name in tail and death in tail:
                if not any(name in str(c.name) for c in known_characters):
                    return (False, [f"无名路人 {name} 死亡强行结尾"])
    
    return (True, [])


# ============================================================
# 道具系统叙事处理 - 规则6
# ============================================================

def process_item_in_narrative(narrative: str, characters: list, world_rules: dict = None) -> str:
    """
    处理叙事中的道具使用，确保符合规则6
    如果道具使用不符合规则，进行修正或过滤
    """
    import re
    
    # 检测道具使用模式
    use_patterns = [
        r'(\w+)(使用|服用|喝下|吃下)了(\w+)',
        r'(\w+)装备了(\w+)',
        r'(\w+)投掷了(\w+)',
    ]
    
    for pattern in use_patterns:
        matches = re.findall(pattern, narrative)
        for match in matches:
            # 检查道具使用是否有代价和效果
            # 如果没有，添加提示
            pass  # 暂时只检测，不修改
    
    return narrative


def generate_item_acquire_event(character_name: str, item_name: str, source: str = "") -> str:
    """生成道具获取事件"""
    if source:
        return f"{character_name}从{source}获得了{item_name}。"
    return f"{character_name}获得了{item_name}。"


def generate_item_use_event(character_name: str, item_name: str, success: bool, reason: str = "") -> str:
    """生成道具使用事件"""
    if success:
        return f"{character_name}使用了{item_name}。"
    else:
        return f"{character_name}试图使用{item_name}，但{reason}。"

    def on_narrative_generated(self, narrative: str):
        """
        叙事生成后调用，更新事件触发状态
        
        检查叙事中是否包含已选择事件的关键词，如果匹配则触发事件
        """
        # Phase 3：叙事生成后记录到 TruthLedger 增强器
        if self._ledger_enhancer_enabled and narrative:
            try:
                self._record_ledger_event("artifact", {
                    "item_name": f"narrative_tick_{self._current_tick}",
                    "note": narrative[:80],
                })
            except Exception:
                pass

        if not self._trigger_manager:
            return
        
        # 从事件池获取最近选择的事件
        if _HAS_EVENT_POOL:
            try:
                event_pool = get_event_pool()
                # 获取最近的事件（如果事件池支持）
                if hasattr(event_pool, '_last_selected_events'):
                    for evt_id in event_pool._last_selected_events:
                        evt = event_pool.events_by_id.get(str(evt_id), {})
                        if evt:
                            # 检查叙事中是否包含事件关键词
                            event_text = evt.get('event', '')
                            if event_text and len(event_text) > 10:
                                # 提取关键词（简单方法：取前20个字符）
                                keywords = event_text[:20]
                                if keywords in narrative:
                                    # 事件被触发，更新 TRIGGER_ 变量
                                    self._trigger_manager.on_event_triggered(evt)
                                    break  # 只触发一个事件
            except Exception as e:
                pass
