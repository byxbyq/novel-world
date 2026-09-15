"""配置数据模型"""

from dataclasses import dataclass, field
from typing import Optional

from .engine_config import EngineConfig


@dataclass
class CharacterConfig:
    """角色设定"""
    name: str                          # 角色名
    age: int = 20                      # 年龄
    gender: str = "男"                 # 性别
    personality: str = ""              # 性格描述
    background: str = ""               # 背景故事
    appearance: str = ""               # 外貌描述
    short_term_goals: list[str] = field(default_factory=list)  # 短期目标
    long_term_goal: str = ""           # 长期目标
    abilities: list[str] = field(default_factory=list)         # 能力/特长
    weaknesses: list[str] = field(default_factory=list)        # 弱点
    initial_location: str = ""         # 初始位置
    initial_relationships: dict[str, str] = field(default_factory=dict)  # 初始关系 {角色名: 关系描述}
    char_type: str = ""                # 角色类型：对应 novel_world CharType 枚举名（PROTAGONIST/HEROINE/ANTAGONIST/NPC/KEY_NPC）

    def to_prompt_text(self) -> str:
        """生成用于 AI prompt 的角色文本"""
        parts = [
            f"【{self.name}】",
            f"性别：{self.gender}，年龄：{self.age}",
        ]
        if self.personality:
            parts.append(f"性格：{self.personality}")
        if self.background:
            parts.append(f"背景：{self.background}")
        if self.appearance:
            parts.append(f"外貌：{self.appearance}")
        if self.short_term_goals:
            parts.append(f"短期目标：{'；'.join(self.short_term_goals)}")
        if self.long_term_goal:
            parts.append(f"长期目标：{self.long_term_goal}")
        if self.abilities:
            parts.append(f"能力：{'，'.join(self.abilities)}")
        if self.weaknesses:
            parts.append(f"弱点：{'，'.join(self.weaknesses)}")
        return "\n".join(parts)


@dataclass
class WorldConfig:
    """世界设定"""
    name: str                          # 世界名称
    genre: str = "玄幻"                # 类型：玄幻/科幻/末世/都市/神话/自定义
    era: str = "古代"                  # 时代背景
    description: str = ""              # 世界描述
    rules: list[str] = field(default_factory=list)             # 世界规则（如力量体系、社会结构）
    key_locations: list[str] = field(default_factory=list)     # 关键地点
    current_situation: str = ""        # 当前局势
    tone: str = "史诗冒险"             # 叙事基调
    perspective: str = "third"         # 叙事视角：third(第三人称) / first(第一人称)

    # 引擎运行时配置（Phase1 P1 — EngineConfig 标准化）
    engine_config: EngineConfig = field(default_factory=EngineConfig)

    # 世界主线目标与叙事阶段（修复二：WorldConfig — 世界主线目标）
    main_objective: str = ""           # 世界主线目标，如"人族十年内推翻魔朝统治"
    main_objective_weight: float = 1.0 # 主线权重（影响角色Goal绑定强度，1.0=标准，>1.0=强化主线引导）
    world_stage: str = "opening"       # 叙事阶段：opening / rising / climax / falling / ending

    # 硬约束配置（Phase1 P0 — 从代码中移出，变为用户可配置数据）
    # 为空字典时 HardConstraintController 使用内置 Demo 默认值
    constraints: dict = field(default_factory=dict)
    # constraints 字典结构：
    # {
    #     "mainline_characters": ["主角A", "主角B"],
    #     "core_relation_type": "异性爱情",   # 可选，None 表示不锁定关系类型
    #     "mainline_stages": {
    #         "stage_1": {"name": "阶段名", "description": "...",
    #                     "keywords": ["关键词1"], "min_narratives": 3, "max_narratives": 4},
    #         ...
    #     },
    #     "supporting_characters": {
    #         "配角A": {"probability": 0.3, "base_cooldown": 3},
    #         ...
    #     },
    #     "mainline_keywords": ["关键词1", ...],
    #     "completion_keywords": ["完成标志词1", ...],
    #     "ending_templates": ["收尾模板1", ...],
    # }

    def to_prompt_text(self) -> str:
        """生成用于 AI prompt 的世界设定文本"""
        parts = [
            f"【世界：{self.name}】",
            f"类型：{self.genre}，时代：{self.era}",
        ]
        if self.description:
            parts.append(f"描述：{self.description}")
        if self.rules:
            parts.append(f"世界规则：{'；'.join(self.rules)}")
        if self.key_locations:
            parts.append(f"关键地点：{'，'.join(self.key_locations)}")
        if self.current_situation:
            parts.append(f"当前局势：{self.current_situation}")
        if self.main_objective:
            parts.append(f"世界主线目标：{self.main_objective}")
            parts.append(f"叙事阶段：{self.world_stage}")
        parts.append(f"叙事基调：{self.tone}")
        if self.perspective == "first":
            parts.append("叙事视角：第一人称（使用「我」作为叙述者）")
        else:
            parts.append("叙事视角：第三人称（使用角色名/他/她，禁止使用「我」作为叙述者）")
        return "\n".join(parts)

    def advance_world_stage(self, progress_ratio: float):
        """根据章节进度比例自动推进叙事阶段。

        Args:
            progress_ratio: 0.0 ~ 1.0，当前已生成章节数 / 总章节数。
        """
        if progress_ratio < 0.20:
            self.world_stage = "opening"
        elif progress_ratio < 0.60:
            self.world_stage = "rising"
        elif progress_ratio < 0.80:
            self.world_stage = "climax"
        elif progress_ratio < 0.95:
            self.world_stage = "falling"
        else:
            self.world_stage = "ending"
