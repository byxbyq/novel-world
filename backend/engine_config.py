"""引擎配置 — 章节上限、终局绑定、节奏控制、运行模式"""

from dataclasses import dataclass, field


@dataclass
class EngineConfig:
    """小说引擎运行时配置

    控制章节上限、节奏、终局行为和运行模式。
    """
    # ── 章节节奏控制 ──
    total_chapters: int = 10             # 总章节数上限
    ticks_per_chapter: int = 20          # 每章Tick数（角色行动轮次）
    tick_speed: str = "normal"           # 推演速度：slow / normal / fast
    auto_pause_between_chapters: bool = True  # 章间是否自动暂停

    # ── 终局控制 ──
    end_behavior: str = "wrap_up"        # 终局行为：wrap_up(收尾) / stop(停止) / loop(循环)
    expected_ending: str = ""            # 预期结局描述，注入终局prompt引导AI收束伏笔

    # ── 运行模式 ──
    npc_filter_enabled: bool = False     # NPC路人过滤：True时跳过纯背景NPC的碰撞/叙事
    offline_mode: bool = False           # 离线模式：True时关闭AI调用，纯模板降级
    ai_provider: str = "local"           # AI来源：local / api / none
