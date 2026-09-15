"""
章节 SpecBuilder
从 FictionForge framework/spec_builder.py 提取。

Spec 是传给 LLM 的结构化「写作规格」—— 控制：
- 叙事风格（style: 史诗/冷峻/抒情...）
- 叙事模式（mode: omniscient/limited...）
- 节奏（rhythm: fast/medium/slow）
- 人物密度（char_density: 每千字出场角色数）
- 描写比重（description_ratio: 描写 vs 对话 vs 动作）
- 信息差策略（info_gap: Class I / Class II 转变触发点）
- 伏笔强度（clue_intensity: 0~1）

原始来源：FictionForge framework/spec_builder.py → SpecBuilder / build_spec_mechanical
适配：小说世界 Phase 3
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Optional


# ── Spec Schema ────────────────────────────────────────────────────────────

def fields_spec_schema() -> dict:
    """Spec 字段的可选值 schema（供前端下拉菜单）。"""
    return {
        "style": ["史诗", "冷峻", "抒情", "悬疑", "写实", "意识流", "江湖气", "仙风道骨", "自动"],
        "mode": ["omniscient", "limited", "multiple_pov", "auto"],
        "rhythm": ["fast", "medium", "slow", "auto"],
        "perspective": ["third", "first", "auto"],
        "description_ratio": ["描写为主", "对话为主", "动作为主", "平衡", "auto"],
        "info_gap_strategy": ["none", "mild", "aggressive", "auto"],
    }


@dataclass
class Spec:
    """章节写作规格。"""
    # ── 风格类 ──
    style: str = "auto"                        # 叙事风格
    mode: str = "auto"                         # 叙事模式
    rhythm: str = "auto"                       # 节奏
    perspective: str = "auto"                  # 视角

    # ── 密度类 ──
    char_density: float = 2.0                  # 每千字体现的角色数
    description_ratio: str = "auto"            # 描写/对话/动作比重
    min_sensory_modes: int = 2                 # 最少激活的五感模式数

    # ── 信息差类 ──
    info_gap_strategy: str = "auto"            # 信息差策略
    clue_intensity: float = 0.3                # 伏笔强度 0~1

    # ── 字数类 ──
    target_words: int = 2000                   # 目标字数（中文按字符计）
    max_words: int = 4000                      # 上限

    # ── 元信息 ──
    chapter_index: int = 0
    world_name: str = ""
    tone: str = ""
    genre: str = ""

    # 额外字段（供扩展）
    extra: dict[str, Any] = None

    def __post_init__(self):
        if self.extra is None:
            self.extra = {}

    def to_prompt(self) -> str:
        """将 Spec 转为 LLM prompt 中的规格文本块。"""
        lines = [
            f"【写作规格】",
            f"- 风格：{self.style}",
            f"- 模式：{self.mode}",
            f"- 节奏：{self.rhythm}",
            f"- 视角：{self.perspective}",
            f"- 角色密度：每千字约 {self.char_density} 个角色活跃",
            f"- 描写比重：{self.description_ratio}",
            f"- 最少感官激活：{self.min_sensory_modes} 种",
            f"- 信息差策略：{self.info_gap_strategy}",
            f"- 伏笔强度：{self.clue_intensity}/1.0",
            f"- 目标字数：{self.target_words} 字以内",
        ]
        return "\n".join(lines)

    def to_dict(self) -> dict:
        """序列化。"""
        d = asdict(self)
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "Spec":
        """反序列化。"""
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


# ── SpecBuilder ────────────────────────────────────────────────────────────

class SpecBuilder:
    """Spec 构建器。

    两层：
    1. build_spec_mechanical() — 纯机械层，不调用 LLM，从世界设定/角色/引擎配置推导 Spec
    2. build_spec_with_ai() — 调用 LLM 补充风格判断（可选）
    """

    def __init__(self, world_config: Optional[dict] = None,
                 character_count: int = 1,
                 chapter_index: int = 1,
                 total_chapters: int = 20):
        self.world = world_config or {}
        self.character_count = max(character_count, 1)
        self.chapter_index = chapter_index
        self.total_chapters = total_chapters

    def build_mechanical(self) -> Spec:
        """纯机械层构建 Spec（无需 LLM）。"""
        genre = self.world.get("genre", "")
        tone = self.world.get("tone", "")

        # ── 风格推断 ──
        style = self._infer_style(genre, tone)

        # ── 模式推断 ──
        mode = "limited"
        if self.character_count >= 5:
            mode = "multiple_pov"
        elif self.character_count <= 2:
            mode = "limited"

        # ── 节奏推断 ──
        rhythm = self._infer_rhythm()

        # ── 视角 ──
        perspective = self.world.get("perspective", "third")

        # ── 角色密度 ──
        char_density = min(self.character_count, 4.0)

        # ── 描写比重 ──
        description_ratio = self._infer_description_ratio()

        # ── 信息差策略 ──
        info_gap_strategy = self._infer_info_gap()

        # ── 伏笔强度 ──
        clue_intensity = self._infer_clue_intensity()

        # ── 字数 ──
        target_words = 2000 if self.total_chapters >= 10 else 3500

        return Spec(
            style=style,
            mode=mode,
            rhythm=rhythm,
            perspective=perspective,
            char_density=char_density,
            description_ratio=description_ratio,
            min_sensory_modes=2,
            info_gap_strategy=info_gap_strategy,
            clue_intensity=clue_intensity,
            target_words=target_words,
            max_words=target_words * 2,
            chapter_index=self.chapter_index,
            world_name=self.world.get("name", ""),
            tone=tone,
            genre=genre,
        )

    # ── 辅助推断方法 ──

    def _infer_style(self, genre: str, tone: str) -> str:
        """从类型和基调推断叙事风格。"""
        genre_style_map = {
            "玄幻": "史诗",
            "科幻": "写实",
            "末世": "冷峻",
            "都市": "写实",
            "神话": "史诗",
            "奇幻": "史诗",
            "恐怖": "悬疑",
        }
        tone_style_map = {
            "史诗冒险": "史诗",
            "黑暗残酷": "冷峻",
            "轻松日常": "抒情",
            "权谋博弈": "悬疑",
            "热血燃向": "史诗",
        }
        # 基调优先
        return tone_style_map.get(tone) or genre_style_map.get(genre, "写实")

    def _infer_rhythm(self) -> str:
        """从章节位置推断节奏。"""
        progress = self.chapter_index / max(self.total_chapters, 1)
        if progress < 0.15:
            return "slow"           # 开场慢
        elif progress < 0.4:
            return "medium"
        elif progress < 0.8:
            return "fast"           # 中间加速
        elif progress < 0.95:
            return "medium"
        else:
            return "fast"           # 终局冲刺

    def _infer_description_ratio(self) -> str:
        """从节奏推断描写比重。"""
        rhythm = self._infer_rhythm()
        if rhythm == "fast":
            return "动作为主"
        elif rhythm == "slow":
            return "描写为主"
        else:
            return "平衡"

    def _infer_info_gap(self) -> str:
        """从角色数和章节位置推断信息差策略。"""
        progress = self.chapter_index / max(self.total_chapters, 1)
        if self.character_count <= 2:
            return "none"
        if progress < 0.3:
            return "mild"            # 前期：温和铺垫
        elif progress < 0.8:
            return "aggressive"      # 中期：信息差拉开
        else:
            return "mild"            # 后期：收束

    def _infer_clue_intensity(self) -> float:
        """推断伏笔强度（0~1）。"""
        progress = self.chapter_index / max(self.total_chapters, 1)
        if progress < 0.1:
            return 0.5               # 开场埋线
        elif progress < 0.5:
            return 0.35
        elif progress < 0.85:
            return 0.15              # 回收期少埋线
        else:
            return 0.05              # 终局几乎不埋新线

    def update_context(self, world_config: dict, chapter_index: int,
                       character_count: int, total_chapters: int) -> None:
        """更新构建上下文。"""
        self.world = world_config
        self.chapter_index = chapter_index
        self.character_count = max(character_count, 1)
        self.total_chapters = max(total_chapters, 1)


# ── 便捷函数 ──────────────────────────────────────────────────────────────

def build_spec_mechanical(world_config: dict, character_count: int = 1,
                          chapter_index: int = 1, total_chapters: int = 20) -> Spec:
    """
    纯机械层构建 Spec（无 LLM 调用）。
    这是最常用的入口——在 tick 循环中按章节索引动态生成写作规格。
    """
    builder = SpecBuilder(
        world_config=world_config,
        character_count=character_count,
        chapter_index=chapter_index,
        total_chapters=total_chapters,
    )
    return builder.build_mechanical()
