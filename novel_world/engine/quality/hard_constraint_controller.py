# -*- coding: utf-8 -*-
"""
硬约束叙事控制器 - 修复版（Phase1 P0 可配置化改造）
解决场景嵌套检测问题，强化主线导向。

改造说明：
- 角色名、主线阶段、配角列表等所有故事相关约束已从代码中移出
- 通过 WorldConfig.constraints 传入，不传则使用内置 Demo 默认值
- 内置默认值仅作为首个 Demo 故事的示例保留，换世界观时通过配置覆盖即可
"""
from typing import Dict, List, Optional, Tuple, Callable
from dataclasses import dataclass, field
import re
import random
from collections import defaultdict


# ============================================================
# 内置 Demo 默认约束（仅在未传入 constraints 配置时使用）
# 这是「陈阳×苏晚」恋爱故事的专属配置，换世界观时通过
# WorldConfig.constraints 完全覆盖即可，无需改代码。
# ============================================================

_DEFAULT_MAINLINE_CHARACTERS = ["陈阳", "苏晚"]
_DEFAULT_CORE_RELATION_TYPE = "异性爱情"
_DEFAULT_MAINLINE_CORE_CHARACTERS = ["林夏", "苏晴"]

_DEFAULT_MAINLINE_STAGES = {
    "stage_1": {
        "name": "初识/试探",
        "description": "陈阳与苏晚的简单互动",
        "keywords": ["送礼物", "搭话", "问候", "帮忙", "接近"],
        "min_narratives": 3,
        "max_narratives": 4,
    },
    "stage_2": {
        "name": "关系升温",
        "description": "约会约定、单独相处、情感表态",
        "keywords": ["约会", "约定", "单独", "相处", "表白", "暗示", "关心"],
        "min_narratives": 3,
        "max_narratives": 4,
    },
    "stage_3": {
        "name": "关系确定/延伸",
        "description": "确定关系、长期见面安排、共同行动",
        "keywords": ["确定", "在一起", "女朋友", "男朋友", "未来", "计划"],
        "min_narratives": 3,
        "max_narratives": 10,
    },
}

_DEFAULT_SUPPORTING_CHARACTERS = {
    "赵磊": {"probability": 0.3, "base_cooldown": 3},
    "阿花": {"probability": 0.25, "base_cooldown": 4},
    "婴儿": {"probability": 0.15, "base_cooldown": 5},
    "猫":   {"probability": 0.2, "base_cooldown": 3},
}

_DEFAULT_MAINLINE_KEYWORDS = [
    "苏晚", "陈阳", "约会", "礼物", "表白", "约定", "关系", "感情",
    "喜欢", "心动", "心意", "接近", "搭话",
]

_DEFAULT_COMPLETION_KEYWORDS = ["确定关系", "在一起", "成为恋人", "确定恋爱关系"]

_DEFAULT_ENDING_TEMPLATES = [
    "两人并肩相伴，约定后续同行",
    "相视而笑，期待未来的每一天",
    "手牵手，一起走向明天",
]


# ========== 高频词替换词库 ==========

HIGH_FREQ_REPLACEMENTS = {
    # 原有高频词
    "攥着": ["握着", "紧攥", "托着", "捏着"],
    "深吸一口气": ["缓缓吸气", "吸了口气", "定了定神"],
    "思考着接下来的计划": ["盘算着后续安排", "思索着下一步动作", "琢磨着接下来该做什么"],
    "整理思绪": ["梳理思路", "平复心绪", "理清头绪"],
    
    # 新增高频词（针对当前叙事重复问题）
    "指尖微颤": ["指尖轻颤", "手有一丝颤抖", "指尖微抖"],
    "脸颊微红": ["脸颊发烫", "脸颊泛红", "脸颊有一丝红晕"],
    "脸颊发红": ["脸颊发烫的变化", "脸颊泛起红晕", "脸颊有一丝发烫"],
    "不知道说什么": ["不知道该说什么", "不知道怎么开口", "不知道自己该说什么"],
    "想了一会": ["想了一会儿动作", "突然有了想法", "突然想到什么"],
    "整理心情": ["整理好心情", "默默调整心情", "心情整理调整"],
    
    # 新增当前叙事高频重复词（场景灯光、气味、情感神态等）
    "暖光": ["柔和灯光", "暖色调灯光", "昏黄灯光"],
    "淡淡的香气": ["场景对应气味", "主题相关香气", "烟火气"],
    "语无伦次": ["支支吾吾", "轻声结巴", "笨拙开口"],
    "身体微微发紧": ["局部隐痛", "身体不适", "身体有些紧张"],
}

# 高频句式（空洞句式）
EMPTY_PATTERNS = [
    r"(.+?)在(.+?)，(.+?)着(.+?)的(.+?)",  # "陈阳在XX，XX着XX的XX"
    r"(.+?)端详着(.+?)",  # "XX端详着XX"
    r"(.+?)感受着(.+?)的变化",  # "XX感受着XX的变化"
    r"(.+?)思考着(.+?)",  # "XX思考着XX"
    r"(.+?)整理着(.+?)思绪",  # "XX整理着XX思绪"
]

# 空洞表述拦截词库
EMPTY_EXPRESSIONS = [
    "思考计划", "整理思绪", "端详", "感受变化", 
    "思考着", "琢磨着", "思考着",
    "忙碌等待", "默默观察", "整理着思绪",
    "有了新的想法", "忙碌着", "忙碌",
    # 新增空洞表述（针对当前叙事问题）
    "停留在场景入口紧张", "不敢推进", "不知道该怎么办",
    "时间流逝", "有了想法", "决定多待一会儿",
]

# 所有有效场景列表
ALL_VALID_SCENES = [
    "街道", "家", "公园", "学校", "办公室", "餐厅", "商店", "医院", 
    "球场", "便利店", "咖啡馆", "健身房", "书店", "洗衣店", "厨房"
]

# 场景设备（不是独立场景）
SCENE_EQUIPMENT = [
    "跑步机", "长椅", "床", "沙发", "桌子", "椅子", "柜台", "货架"
]

# 错误用词修正
WORD_CORRECTIONS = {
    "不知乕处": "不知何处",
    "惄惄发生": "悄然发生",
    "惄然变化": "悄然变化",
    "惄然": "悄然",
    "乕": "处",
    # 新增错误用词修正
    "不知处": "不知何处",
    "某人的": "",  # 清除模糊指代
    "某人地": "",  # 清除模糊指代
}


# ========== 主线阶段定义 ==========
# 【已废弃】MAINLINE_STAGES 全局常量保留仅作为向后兼容引用。
# 实际使用时应通过 constraints 配置传入，或回退到 _DEFAULT_MAINLINE_STAGES。
# 换世界观时请使用 WorldConfig.constraints["mainline_stages"] 覆盖。
MAINLINE_STAGES = _DEFAULT_MAINLINE_STAGES

# ========== 主题相关的主线动作模板 ==========

# 日常/恋爱主题的主线动作





@dataclass
class HardState:
    """硬状态 - 必须满足，否则拦截"""
    # 场景
    current_scene: str = "街道"
    previous_scene: str = ""
    valid_scenes: List[str] = field(default_factory=lambda: ALL_VALID_SCENES)
    scene_locked: bool = False
    min_scene_stay: int = 2
    scene_stay_count: int = 0
    scene_repeat_count: int = 0  # 场景重复计数（新增）
    scene_max_repeat: int = 3  # 场景最大重复次数（新增）
    
    # 天气
    current_weather: str = "晴天"
    weather_locked: bool = False
    weather_stay_count: int = 0
    min_weather_stay: int = 5
    
    # 物品
    inventory: List[str] = field(default_factory=list)
    
    # 配角冷却（硬屏蔽）— 默认值在 HardConstraintController.__init__ 中根据配置填充
    配角_cooldown: Dict[str, int] = field(default_factory=dict)
    配角_probability: Dict[str, float] = field(default_factory=dict)
    配角_base_cooldown: Dict[str, int] = field(default_factory=dict)
    
    # 剧情阶段
    plot_stage: str = "idle"
    plot_stuck_count: int = 0
    max_plot_stuck: int = 2
    
    # 主线阶段
    mainline_stage: str = "stage_1"
    mainline_narrative_count: int = 0
    mainline_progress_actions: int = 0
    mainline_stage_timeout: int = 4  # 主线阶段超时限制（新增）
    mainline_force_progress_count: int = 0  # 强制推进计数（新增）
    
    # 时间
    time_hour: int = 8
    day_count: int = 1
    
    # 去重
    recent_narratives: List[str] = field(default_factory=list)
    recent_phrases: Dict[str, int] = field(default_factory=lambda: defaultdict(int))
    max_phrase_usage: int = 2
    similarity_threshold: float = 0.50
    
    # 拦截计数
    intercept_count: int = 0
    regenerate_count: int = 0
    
    # 模板回退限制（新增）
    template_fallback_count: int = 0  # 模板回退计数
    template_fallback_limit: int = 10  # 每10条叙事最多触发1次
    template_fallback_narrative_count: int = 0  # 叙事计数
    
    # 关键状态
    key_states: Dict[str, any] = field(default_factory=dict)
    
    # 核心关系校验（新增）— 默认值在 HardConstraintController.__init__ 中根据配置填充
    core_relation_type: str = ""
    core_relation_locked: bool = True  # 关系是否锁定
    relation_conflict_count: int = 0  # 关系冲突计数
    
    # 主线角色绑定（新增）— 默认值在 HardConstraintController.__init__ 中根据配置填充
    mainline_core_characters: List[str] = field(default_factory=list)
    mainline_character_interaction_count: int = 0  # 核心角色互动计数
    mainline_no_interaction_limit: int = 2  # 无互动限制
    
    # 主线收尾约束（新增）
    mainline_completed: bool = False  # 主线是否完成
    mainline_ending_triggered: bool = False  # 收尾是否触发
    mainline_ending_narrative_count: int = 0  # 收尾叙事计数
    mainline_ending_max: int = 2  # 收尾最多2条叙事
    
    # 关系冲突拦截日志
    relation_intercept_logs: List[str] = field(default_factory=list)
    
    # 配角屏蔽日志（新增）
    npc_intercept_logs: List[str] = field(default_factory=list)


class HardConstraintController:
    """硬约束控制器 - 可配置版（Phase1 P0 改造）

    所有故事相关参数通过 constraints 字典传入，未传入时回退到
    内置 Demo 默认值（_DEFAULT_* 常量）。
    
    Args:
        theme: 主题名（保留兼容，实际约束从 constraints 读取）
        constraints: 可选配置字典，结构见 WorldConfig.constraints 字段注释
    """
    
    def __init__(self, theme: str = "日常", constraints: dict = None):
        self.state = HardState()
        self.theme = theme
        self._max_regenerate = 3
        
        # --- 解析配置，缺失项回退到内置 Demo 默认值 ---
        c = constraints or {}
        
        self.mainline_characters = c.get("mainline_characters", _DEFAULT_MAINLINE_CHARACTERS)
        self.mainline_stages = c.get("mainline_stages", _DEFAULT_MAINLINE_STAGES)
        self.mainline_keywords = c.get("mainline_keywords", _DEFAULT_MAINLINE_KEYWORDS)
        self.completion_keywords = c.get("completion_keywords", _DEFAULT_COMPLETION_KEYWORDS)
        self.ending_templates = c.get("ending_templates", _DEFAULT_ENDING_TEMPLATES)
        
        # 核心关系
        core_rel = c.get("core_relation_type")
        if core_rel is None:
            self.core_relation_type = ""
        elif core_rel:
            self.core_relation_type = core_rel
        else:
            self.core_relation_type = _DEFAULT_CORE_RELATION_TYPE
        
        # 主线核心角色
        self._mainline_core_chars = c.get(
            "mainline_core_characters",
            _DEFAULT_MAINLINE_CORE_CHARACTERS
        )
        
        # 配角
        supporting = c.get("supporting_characters", _DEFAULT_SUPPORTING_CHARACTERS)
        self._supporting_names = list(supporting.keys())
        self._supporting_cooldown = {**{k: 0 for k in self._supporting_names}, "某人": 0}
        self._supporting_prob = {k: v.get("probability", 0.3) for k, v in supporting.items()}
        self._supporting_base_cd = {
            **{k: v.get("base_cooldown", 3) for k, v in supporting.items()},
            "某人": 2,
        }
        
        # 填充 HardState 中的动态默认值
        self.state.配角_cooldown = dict(self._supporting_cooldown)
        self.state.配角_probability = self._supporting_prob
        self.state.配角_base_cooldown = self._supporting_base_cd
        self.state.core_relation_type = self.core_relation_type
        self.state.mainline_core_characters = list(self._mainline_core_chars)
        
        self.theme_info = {}
        
        # 场景过渡映射
        self._scene_transitions = {
            "街道": ["家", "公园", "学校", "办公室", "餐厅", "商店", "医院", "球场", "便利店", "咖啡馆", "健身房", "书店"],
            "公园": ["街道", "家", "球场"],
            "学校": ["街道", "公园"],
            "办公室": ["街道", "餐厅", "咖啡馆"],
            "餐厅": ["街道", "办公室", "家"],
            "商店": ["街道", "便利店"],
            "医院": ["街道", "家"],
            "球场": ["街道", "公园", "家"],
            "便利店": ["街道", "家"],
            "咖啡馆": ["街道", "办公室", "家"],
            "健身房": ["街道", "家"],
            "书店": ["街道", "家"],
        }
        
        # 日志
        self._logs: List[str] = []
    
    # ========== 1. 高频词拦截及替换 ==========
    
    def replace_high_freq_words(self, narrative: str) -> Tuple[str, List[str]]:
        """替换高频词"""
        replacements = []
        
        for old_phrase, new_options in HIGH_FREQ_REPLACEMENTS.items():
            if old_phrase in narrative:
                usage = self.state.recent_phrases[old_phrase]
                if usage >= self.state.max_phrase_usage:
                    new_phrase = random.choice(new_options)
                    narrative = narrative.replace(old_phrase, new_phrase)
                    replacements.append(f"'{old_phrase}' → '{new_phrase}'")
                else:
                    self.state.recent_phrases[old_phrase] += 1
        
        return (narrative, replacements)
    
    def detect_empty_pattern(self, narrative: str) -> Tuple[bool, str]:
        """检测空洞句式"""
        # 检测空洞句式
        for pattern in EMPTY_PATTERNS:
            if re.search(pattern, narrative):
                return (True, f"匹配空洞句式: {pattern}")
        
        # 检测空洞表述
        for expr in EMPTY_EXPRESSIONS:
            if expr in narrative:
                return (True, f"包含空洞表述: '{expr}'")
        
        return (False, "")
    
    # ========== 2. 相似度拦截 ==========
    
    def check_similarity_hard(self, narrative: str) -> Tuple[bool, str]:
        """相似度硬校验"""
        # 检查100%重复
        for recent in self.state.recent_narratives:
            if narrative == recent:
                return (True, "100%重复，拦截重生成")
        
        # 检查相似度≥55%
        for recent in self.state.recent_narratives[-10:]:
            similarity = self._calc_similarity(narrative, recent)
            if similarity >= self.state.similarity_threshold:
                return (True, f"相似度 {similarity:.0%} ≥ 55%，拦截重生成")
        
        # 检查连续高相似度
        if len(self.state.recent_narratives) >= 2:
            last_two = self.state.recent_narratives[-2:]
            for recent in last_two:
                similarity = self._calc_similarity(narrative, recent)
                if similarity >= 0.70:
                    return (True, f"连续相似度 {similarity:.0%} ≥ 80%，拦截")
        
        return (False, "")
    
    def _calc_similarity(self, text1: str, text2: str) -> float:
        """计算相似度"""
        if not text1 or not text2:
            return 0.0
        words1 = set(text1)
        words2 = set(text2)
        if not words1 or not words2:
            return 0.0
        return len(words1 & words2) / len(words1 | words2)
    
    # ========== 3. 剧情推进强制校验 ==========
    
    def check_substance_and_mainline(self, narrative: str) -> Tuple[bool, str]:
        """实质内容 + 主线导向 双重校验"""
        # 检查实质内容
        has_action = any(kw in narrative for kw in ["走", "跑", "拿", "放", "说", "问", "看", "听", "想", "决定", "打算", "准备", "约", "送", "找", "遇"])
        has_interaction = any(kw in narrative for kw in ["对", "向", "跟", "和", "与", "约", "送", "接", "聊"])
        has_transition = any(kw in narrative for kw in ["离开", "到达", "进入", "走出", "来到", "偶遇", "遇到"])
        
        has_substance = has_action or has_interaction or has_transition
        
        if not has_substance:
            return (False, "无实质内容（缺少动作/交互/过渡）")
        
        # 检查主线导向（从配置读取）
        mainline_keywords = self.mainline_keywords  # 已在 __init__ 中解析
        has_mainline = any(kw in narrative for kw in mainline_keywords)
        
        # 检查是否是主线角色的互动
        main_chars = self.mainline_characters
        has_mainline_interaction = len(main_chars) >= 2 and all(ch in narrative for ch in main_chars[:2])
        
        if not has_mainline and not has_mainline_interaction:
            # 检查是否是配角单独出场（非主线）
            has_配角_alone = any(name in narrative and main_chars[0] not in narrative for name in self._supporting_names)
            if has_配角_alone:
                return (False, "配角单独出场，脱离主线")
            
            # 检查是否是空洞的独自活动
            if "独自" in narrative or "一个人" in narrative:
                return (False, "独自活动，脱离主线")
            
            # 检查是否是无关活动
            if any(kw in narrative for kw in ["健身", "看书", "下棋", "洗衣服"]):
                return (False, "无关活动，脱离主线")
        
        return (True, "")
    
    def check_mainline_progress(self) -> Tuple[bool, str]:
        """检查主线进度"""
        stage = self.state.mainline_stage
        stage_config = self.mainline_stages.get(stage, {})
        max_narratives = stage_config.get("max_narratives", 5)
        
        # 检查是否需要推进主线
        if self.state.mainline_narrative_count >= max_narratives:
            return (True, f"主线阶段 {stage} 已满，需要推进")
        
        # 检查是否需要主线推进动作
        if self.state.mainline_narrative_count > 0 and self.state.mainline_narrative_count % 2 == 0:
            if self.state.mainline_progress_actions == 0:
                return (True, "每5条叙事需要1次主线推进动作")
        
        return (False, "")
    
    def get_mainline_action(self, theme_info=None):
        stage = self.state.mainline_stage
        stage_config = self.mainline_stages.get(stage, {})
        stage_name = stage_config.get("name", "unknown")
        if theme_info:
            return None  # Let AI generate narrative based on theme
        return None  # Let AI generate narrative based on theme
    def check_mainline_character_binding(self, narrative: str) -> Tuple[bool, str]:
        """主线角色绑定校验 - 确保核心角色互动"""
        # 检测是否包含核心角色
        has_core_character = any(char in narrative for char in self.state.mainline_core_characters)
        
        # 检测是否是核心角色互动
        has_interaction = False
        if len(self.state.mainline_core_characters) >= 2:
            char1, char2 = self.state.mainline_core_characters[0], self.state.mainline_core_characters[1]
            has_interaction = char1 in narrative and char2 in narrative
        
        if has_interaction:
            self.state.mainline_character_interaction_count += 1
            return (True, "核心角色互动")
        
        # 如果连续2条叙事无核心角色互动，返回警告
        if self.state.mainline_no_interaction_limit > 0:
            self.state.mainline_no_interaction_limit -= 1
            if self.state.mainline_no_interaction_limit == 0:
                self.state.mainline_no_interaction_limit = 2  # 重置
                return (False, "需要核心角色互动")
        
        return (has_core_character, "包含核心角色" if has_core_character else "无核心角色")
    
    def force_mainline_progress(self) -> str:
        """强制主线推进"""
        stage = self.state.mainline_stage
        stage_config = self.mainline_stages.get(stage, {})
        if False:
            action = random.choice(actions)
            self.state.mainline_force_progress_count += 1
            return action
        return "推进主线关系发展"


    def check_template_fallback_allowed(self) -> Tuple[bool, str]:
        """检查是否允许模板回退"""
        self.state.template_fallback_narrative_count += 1
        
        # 每10条叙事重置计数
        if self.state.template_fallback_narrative_count >= self.state.template_fallback_limit:
            self.state.template_fallback_narrative_count = 0
            self.state.template_fallback_count = 0
        
        # 检查是否超过限制
        if self.state.template_fallback_count >= 1:
            return (False, "模板回退次数已达上限，等待重置")
        
        return (True, "允许模板回退")
    
    def trigger_template_fallback(self) -> str:
        """触发模板回退"""
        allowed, reason = self.check_template_fallback_allowed()
        if not allowed:
            return ""
        
        self.state.template_fallback_count += 1
        
        # 返回主线相关模板
        stage = self.state.mainline_stage
        stage_config = self.mainline_stages.get(stage, {})
        if False:
            return random.choice(actions)
        return "推进主线关系发展"


    def check_mainline_ending(self, narrative: str) -> Tuple[bool, str, str]:
        """主线收尾校验"""
        # 检测主线完成标志（从配置读取）
        if any(kw in narrative for kw in self.completion_keywords):
            self.state.mainline_completed = True
            self.state.mainline_ending_triggered = True
            return (True, narrative, "主线完成，开始收尾")
        
        # 如果主线已完成，检查收尾叙事数量
        if self.state.mainline_completed:
            self.state.mainline_ending_narrative_count += 1
            
            # 收尾叙事超过限制，强制结束
            if self.state.mainline_ending_narrative_count > self.state.mainline_ending_max:
                return (True, "", "主线收尾已完成，停止生成")
            
            # 检查收尾内容是否偏离主题
            deviation_keywords = ["新角色", "新任务", "新目标", "未完成"]
            if any(kw in narrative for kw in deviation_keywords):
                return (True, "", "收尾内容偏离主题，已拦截")
        
        return (False, narrative, "")
    
    def get_ending_template(self) -> str:
        """获取收尾模板"""
        return random.choice(self.ending_templates)

    def advance_mainline_stage(self):
        """推进主线阶段"""
        stage_order = list(self.mainline_stages.keys())
        current_idx = stage_order.index(self.state.mainline_stage) if self.state.mainline_stage in stage_order else 0
        
        if current_idx < len(stage_order) - 1:
            self.state.mainline_stage = stage_order[current_idx + 1]
            self.state.mainline_narrative_count = 0
            self.state.mainline_progress_actions = 0
            self._log(f"主线阶段推进: {self.state.mainline_stage}")
    
    # ========== 4. 场景/语法校验 ==========
    
    def validate_scene_hard(self, narrative: str) -> Tuple[bool, str, str]:
        """场景硬校验 - 检测场景嵌套"""
        # 检测场景嵌套模式：XX里的XX、XX上的XX、XX中的XX
        nesting_patterns = [
            (r"(.{2,10})里的(.{2,10})", "里"),
            (r"(.{2,10})上的(.{2,10})", "上"),
            (r"(.{2,10})中的(.{2,10})", "中"),
        ]
        
        for pattern, connector in nesting_patterns:
            match = re.search(pattern, narrative)
            if match:
                part1, part2 = match.groups()
                
                # 检查是否包含两个场景（场景嵌套）
                scene_in_part1 = any(scene in part1 for scene in ALL_VALID_SCENES)
                scene_in_part2 = any(scene in part2 for scene in ALL_VALID_SCENES)
                equipment_in_part1 = any(eq in part1 for eq in SCENE_EQUIPMENT)
                
                # 如果 part2 是一个场景，且 part1 是设备或另一个场景，则是无效嵌套
                if scene_in_part2:
                    if equipment_in_part1 or scene_in_part1:
                        # 这是无效的场景嵌套，需要修正
                        # 提取有效的场景
                        valid_scene = None
                        for scene in ALL_VALID_SCENES:
                            if scene in part2:
                                valid_scene = scene
                                break
                            if scene in part1:
                                valid_scene = scene
                                break
                        
                        if not valid_scene:
                            valid_scene = random.choice(["街道", "家", "公园"])
                        
                        # 替换整个嵌套部分
                        old_text = f"{part1}{connector}的{part2}"
                        corrected = narrative.replace(old_text, valid_scene)
                        return (True, corrected, f"场景嵌套无效 '{old_text}'，修正为 '{valid_scene}'")
        
        # 检测场景跳转
        detected_scene = self._detect_scene(narrative)
        if detected_scene:
            current = self.state.current_scene
            
            # 检查停留期
            if self.state.scene_stay_count < self.state.min_scene_stay:
                if detected_scene != current:
                    corrected = narrative.replace(detected_scene, current)
                    return (True, corrected, f"场景停留期，保持 {current}")
            
            # 检查有效跳转
            valid_transitions = self._scene_transitions.get(current, [])
            if detected_scene != current and detected_scene not in valid_transitions:
                if valid_transitions:
                    target = random.choice(valid_transitions)
                else:
                    target = current
                corrected = narrative.replace(detected_scene, target)
                return (True, corrected, f"无效跳转 {current}→{detected_scene}，修正为 {target}")
        
        return (False, narrative, "")
    

    def validate_scene_enhanced(self, narrative: str) -> Tuple[bool, str, str]:
        """增强的场景校验 - 包含场景重复拦截"""
        # 先调用原有的场景校验
        should_block, corrected, reason = self.validate_scene_hard(narrative)
        
        # 场景重复拦截
        detected_scene = self._detect_scene(corrected)
        if detected_scene == self.state.current_scene:
            self.state.scene_repeat_count += 1
            if self.state.scene_repeat_count >= self.state.scene_max_repeat:
                # 强制切换场景
                valid_transitions = self._scene_transitions.get(self.state.current_scene, [])
                if valid_transitions:
                    new_scene = random.choice(valid_transitions)
                    reason = f"场景重复{self.state.scene_repeat_count}次，强制切换至{new_scene}"
                    self.state.scene_repeat_count = 0
                    return (True, corrected, reason)
        else:
            self.state.scene_repeat_count = 0
        
        return (should_block, corrected, reason)
    
    def check_fuzzy_reference(self, narrative: str) -> Tuple[bool, str, str]:
        """指代校验 - 拦截模糊指代"""
        corrected = narrative
        issues = []
        
        # 拦截"身影"等模糊指代
        if "身影" in narrative and "的" in narrative:
            # 检查是否有明确的指代对象
            has_clear_ref = any(char in narrative for char in self.state.mainline_core_characters)
            if not has_clear_ref:
                issues.append("身影(无明确指代)")
                # 尝试替换为核心角色
                default_char = self.state.mainline_core_characters[0] if self.state.mainline_core_characters else "某人"
                corrected = narrative.replace("身影", default_char)
        
        # 拦截"某人"等模糊指代
        if "某人" in narrative or "某人" in narrative:
            issues.append("某人(模糊指代)")
        
        if issues:
            return (True, corrected, f"指代问题: {', '.join(issues)}")
        return (False, narrative, "")

    def fix_grammar_hard(self, narrative: str) -> Tuple[str, List[str]]:
        """语法硬修正"""
        corrections = []
        
        # 修正错误用词
        for wrong, correct in WORD_CORRECTIONS.items():
            if wrong in narrative:
                narrative = narrative.replace(wrong, correct)
                corrections.append(f"'{wrong}' → '{correct}'")
        
        # 修正半截句
        if narrative.endswith("，") or narrative.endswith("、"):
            narrative = narrative[:-1] + "。"
            corrections.append("半截句修正")
        
        # 修正重复标点
        narrative = re.sub(r'。{3,}', '……', narrative)
        narrative = re.sub(r'，{3,}', '……', narrative)
        
        # 修正指代混乱
        narrative = re.sub(r'他[，,\s]+([^\s，。]+)[，,\s]+', r'\1', narrative)
        
        return (narrative, corrections)
    
    def _detect_scene(self, narrative: str) -> str:
        """检测场景"""
        for scene in self.state.valid_scenes:
            if scene in narrative:
                return scene
        return ""
    
    # ========== 5. 配角屏蔽机制 ==========
    
    def get_available_配角(self) -> List[str]:
        """获取可用配角"""
        available = []
        for name, cooldown in self.state.配角_cooldown.items():
            if name == "某人":
                continue
            if cooldown <= 0:
                prob = self.state.配角_probability.get(name, 0.3)
                if random.random() < prob:
                    available.append(name)
        return available
    
    def validate_配角_hard(self, narrative: str) -> Tuple[bool, str, str]:
        """配角硬校验"""
        corrected = narrative
        blocked = []
        
        for name in self._supporting_names:
            if name in narrative:
                cooldown = self.state.配角_cooldown.get(name, 0)
                if cooldown > 0:
                    corrected = corrected.replace(name, "")
                    blocked.append(f"{name}(冷却{cooldown}回合)")
                else:
                    prob = self.state.配角_probability.get(name, 0.3)
                    if random.random() > prob:
                        corrected = corrected.replace(name, "")
                        blocked.append(f"{name}(概率未通过)")
                    else:
                        self.state.配角_cooldown[name] = self.state.配角_base_cooldown.get(name, 3)
        
        if "某人" in narrative:
            if self.state.配角_cooldown.get("某人", 0) > 0:
                corrected = corrected.replace("某人", "")
                blocked.append("某人(冷却中)")
            else:
                self.state.配角_cooldown["某人"] = 2
        
        if blocked:
            return (True, corrected, f"配角屏蔽: {', '.join(blocked)}")
        return (False, narrative, "")
    

    def validate_某人_enhanced(self, narrative: str) -> Tuple[bool, str, str]:
        """增强的配角校验 - 包含模糊指代拦截"""
        corrected = narrative
        blocked = []
        
        # 拦截模糊指代"某人"
        if "某人" in narrative or "某人" in narrative:
            # 检查是否在冷却期
            if self.state.配角_cooldown.get("某人", 0) > 0:
                corrected = corrected.replace("某人", "").replace("某人", "")
                blocked.append("某人(模糊指代冷却中)")
                self.state.npc_intercept_logs.append(f"模糊指代拦截: 某人")
            else:
                # 设置冷却期
                self.state.配角_cooldown["某人"] = 15
                if not hasattr(self.state, '某人_appearance_count'):
                    self.state.__dict__['某人_appearance_count'] = 0
                self.state.__dict__['某人_appearance_count'] += 1
                
                # 检查出场频率
                max_appearance = getattr(self.state, '某人_max_appearance_per_15', 3)
                if getattr(self.state, '某人_appearance_count', 0) > max_appearance:
                    corrected = corrected.replace("某人", "").replace("某人", "")
                    blocked.append("某人(出场频率超限)")
                    self.state.npc_intercept_logs.append(f"配角出场频率超限: 某人")
        
        # 拦截配角单独出场
        for name in self._supporting_names:
            if name in narrative:
                # 检查是否伴随核心角色
                has_core_character = any(char in narrative for char in self.state.mainline_core_characters)
                if not has_core_character:
                    # 配角单独出场，检查冷却期
                    cooldown = self.state.配角_cooldown.get(name, 0)
                    if cooldown > 0:
                        corrected = corrected.replace(name, "")
                        blocked.append(f"{name}(单独出场冷却{cooldown}回合)")
                        self.state.npc_intercept_logs.append(f"配角单独出场拦截: {name}")
        
        if blocked:
            return (True, corrected, f"配角拦截: {', '.join(blocked)}")
        return (False, narrative, "")

    # ========== 6. 综合校验 ==========
    
    def validate_narrative_hard(self, narrative: str) -> Tuple[bool, str, List[str]]:
        """综合硬校验 - 主入口"""
        reasons = []
        corrected = narrative
        
        # 1. 相似度硬拦截（最先）
        should_intercept, reason = self.check_similarity_hard(corrected)
        if should_intercept:
            self.state.intercept_count += 1
            return (True, "", [reason])
        
        # 2. 高频词替换
        corrected, replacements = self.replace_high_freq_words(corrected)
        if replacements:
            reasons.append(f"高频词替换: {', '.join(replacements)}")
        
        # 3. 空洞句式检测
        is_empty, reason = self.detect_empty_pattern(corrected)
        if is_empty:
            self.state.intercept_count += 1
            return (True, "", [reason])
        
        # 4. 实质内容 + 主线校验
        is_valid, reason = self.check_substance_and_mainline(corrected)
        if not is_valid:
            self.state.intercept_count += 1
            return (True, "", [reason])
        
        # 5. 主线进度检查
        need_progress, reason = self.check_mainline_progress()
        if need_progress:
            mainline_action = self.get_mainline_action()
            if mainline_action:
                corrected = mainline_action + chr(34) + chr(46) + chr(34) + corrected
            reasons.append(f"主线推进: {mainline_action}")
            self.state.mainline_progress_actions += 1
        
        # 6. 场景硬校验
        should_block, corrected, reason = self.validate_scene_hard(corrected)
        if reason:
            reasons.append(reason)
        
        # 7. 配角硬校验
        should_block, corrected, reason = self.validate_配角_hard(corrected)
        if reason:
            reasons.append(reason)
        
        # 8. 语法硬修正
        corrected, corrections = self.fix_grammar_hard(corrected)
        if corrections:
            reasons.append(f"语法修正: {', '.join(corrections)}")
        
        # 9. 核心关系校验（新增）
        should_block, corrected, reason = self.validate_core_relation(corrected)
        if reason:
            reasons.append(f"核心关系校验: {reason}")
        
        # 10. 主线收尾校验（新增）
        should_block, corrected, reason = self.check_mainline_ending(corrected)
        if reason:
            reasons.append(f"主线收尾: {reason}")
        
        # 更新状态
        self._update_state_after_validation(corrected)
        
        return (False, corrected, reasons)
    
    def _update_state_after_validation(self, narrative: str):
        """校验后更新状态"""
        self.state.recent_narratives.append(narrative)
        if len(self.state.recent_narratives) > 50:
            self.state.recent_narratives = self.state.recent_narratives[-50:]
        
        detected = self._detect_scene(narrative)
        if detected == self.state.current_scene:
            self.state.scene_stay_count += 1
        elif detected:
            self.state.scene_stay_count = 0
            self.state.previous_scene = self.state.current_scene
            self.state.current_scene = detected
        
        self.state.mainline_narrative_count += 1
        
        stage = self.state.mainline_stage
        stage_config = self.mainline_stages.get(stage, {})
        max_narratives = stage_config.get("max_narratives", 5)
        if self.state.mainline_narrative_count >= max_narratives:
            self.advance_mainline_stage()
    
    def _log(self, message: str):
        """记录日志"""
        self._logs.append(message)
        print(f"[硬约束] {message}")
    
    # ========== 回合推进 ==========
    
    def advance_round(self):
        """推进回合"""
        for name in self.state.配角_cooldown:
            if self.state.配角_cooldown[name] > 0:
                self.state.配角_cooldown[name] -= 1
        
        self.state.time_hour += 1
        if self.state.time_hour >= 24:
            self.state.time_hour = 0
            self.state.day_count += 1
    
    # ========== 记忆管理 ==========
    
    def cleanup_memory_safe(self, context: str, max_length: int) -> str:
        """安全清理记忆"""
        if len(context) <= max_length:
            return context
        
        key_info = f"""
[关键状态]
场景: {self.state.current_scene}
天气: {self.state.current_weather}
物品: {', '.join(self.state.inventory[:5])}
主线阶段: {self.state.mainline_stage}
剧情阶段: {self.state.plot_stage}
"""
        keep_ratio = 0.6
        keep_length = int(max_length * keep_ratio)
        
        return key_info + "\n" + context[-keep_length:]
    
    # ========== 状态摘要 ==========
    
    def get_state_summary(self) -> str:
        """获取状态摘要"""
        time_desc = self._get_time_desc()
        stage_name = self.mainline_stages.get(self.state.mainline_stage, {}).get("name", "未知")
        return f"[第{self.state.day_count}天{time_desc}] 场景:{self.state.current_scene} 主线:{stage_name} 拦截:{self.state.intercept_count}"
    

    # ========== 7. 核心关系校验（新增） ==========
    
    def validate_core_relation(self, narrative: str) -> Tuple[bool, str, str]:
        """核心关系校验 - 防止关系错乱"""
        # 定义关系冲突关键词
        conflict_keywords = {
            "同性亲密": ["同性", "同居", "一起规划未来", "确定关系"],
            "配角越界": ["某人", "某人", "模糊指代"],
        }
        
        # 检测关系冲突
        if self.state.core_relation_type == "异性爱情":
            # 检测同性关系冲突
            if "同性" in narrative and ("同居" in narrative or "确定关系" in narrative):
                self.state.relation_conflict_count += 1
                self.state.relation_intercept_logs.append(f"同性关系冲突: {narrative[:50]}")
                return (True, "", "检测到同性关系与异性主线冲突，已拦截")
            
            # 检测配角越界
            if "某人" in narrative or "某人" in narrative:
                self.state.relation_intercept_logs.append(f"模糊指代拦截: {narrative[:50]}")
                # 替换模糊指代为核心角色名
                default_char = self.state.mainline_core_characters[0] if self.state.mainline_core_characters else "主角"
                corrected = narrative.replace("某人", default_char).replace("某人", default_char)
                return (True, corrected, "模糊指代已替换为核心角色名")
        
        return (False, narrative, "")
    
    def lock_core_relation(self, relation_type: str):
        """锁定核心关系类型"""
        self.state.core_relation_type = relation_type
        self.state.core_relation_locked = True
        self._log(f"核心关系已锁定: {relation_type}")
    

    def set_theme(self, theme: str):
        """设置当前主题"""
        self.theme = theme
        self._log(f"主题已切换为: {theme}")
    
    def get_theme_actions(self) -> Dict:
        """获取当前主题的主线动作"""
        return {}

    def get_relation_status(self) -> Dict:
        """获取关系状态"""
        return {
            "core_relation_type": self.state.core_relation_type,
            "core_relation_locked": self.state.core_relation_locked,
            "relation_conflict_count": self.state.relation_conflict_count,
            "recent_intercepts": self.state.relation_intercept_logs[-5:],
        }

    def _get_time_desc(self) -> str:
        hour = self.state.time_hour
        if 5 <= hour < 8: return "清晨"
        elif 8 <= hour < 12: return "上午"
        elif 12 <= hour < 14: return "中午"
        elif 14 <= hour < 18: return "下午"
        elif 18 <= hour < 20: return "傍晚"
        elif 20 <= hour < 23: return "晚上"
        else: return "深夜"


# ========== 单例 ==========
_controller_instance = None

def get_hard_controller(theme: str = "日常", constraints: dict = None) -> HardConstraintController:
    """获取 HardConstraintController 单例。

    Args:
        theme: 主题名（向后兼容）
        constraints: 约束配置字典，结构见 WorldConfig.constraints。
                      传入 None 或不传则使用内置 Demo 默认值。
    """
    global _controller_instance
    if _controller_instance is None:
        _controller_instance = HardConstraintController(theme, constraints=constraints)
    return _controller_instance
