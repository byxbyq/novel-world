# -*- coding: utf-8 -*-
"""
上下文节流系统 — 降低 Token 消耗，解决长文丢失设定

三层机制：
1. 静态设定缓存：世界规则、角色基础性格、势力关系 — 首次全量，后续仅传 hash 校验
2. 差分状态传输：每轮只传变动的角色/势力字段，未变动角色传摘要
3. 历史滑动窗口：近 N 章完整正文 + 远章摘要压缩

使用方式：
    from novel_world.engine.context_throttle import ContextThrottler

    throttler = ContextThrottler(
        static_cache_enabled=True,
        diff_transmission_enabled=True,
        sliding_window_chapters=3,
    )

    # 生成压缩后的 prompt
    compressed = throttler.build_prompt(
        world=world,
        characters=characters,
        chapter_history=chapter_texts,
        current_chapter=5,
    )
"""

import hashlib
import json
from dataclasses import dataclass, field
from typing import Optional
import logging

logger = logging.getLogger("context_throttle")


# ==========================================================================
# 一、配置
# ==========================================================================

@dataclass
class ThrottleConfig:
    """上下文节流配置"""
    static_cache_enabled: bool = True
    diff_transmission_enabled: bool = True
    sliding_window_enabled: bool = True
    sliding_window_chapters: int = 3
    max_summary_chars: int = 500
    character_summary_threshold: int = 3
    token_budget: int = 4000

    def to_dict(self) -> dict:
        return {
            "static_cache_enabled": self.static_cache_enabled,
            "diff_transmission_enabled": self.diff_transmission_enabled,
            "sliding_window_enabled": self.sliding_window_enabled,
            "sliding_window_chapters": self.sliding_window_chapters,
            "max_summary_chars": self.max_summary_chars,
            "character_summary_threshold": self.character_summary_threshold,
            "token_budget": self.token_budget,
        }


# ==========================================================================
# 二、静态设定缓存
# ==========================================================================

@dataclass
class StaticCache:
    """静态设定缓存 — 不随 Tick 变化的设定"""
    world_rules_hash: str = ""
    world_rules_text: str = ""
    factions_hash: str = ""
    factions_text: str = ""
    character_baselines: dict = field(default_factory=dict)

    def is_cached(self, key: str, content_hash: str) -> bool:
        if key == "world_rules":
            return self.world_rules_hash == content_hash
        elif key == "factions":
            return self.factions_hash == content_hash
        return False

    def update(self, key: str, content: str):
        content_hash = _hash_text(content)
        if key == "world_rules":
            self.world_rules_hash = content_hash
            self.world_rules_text = content
        elif key == "factions":
            self.factions_hash = content_hash
            self.factions_text = content

    def update_character(self, char_id: str, baseline_text: str):
        self.character_baselines[char_id] = {
            "hash": _hash_text(baseline_text),
            "text": baseline_text,
        }

    def get_character_baseline(self, char_id: str) -> Optional[str]:
        cached = self.character_baselines.get(char_id)
        return cached["text"] if cached else None


def _hash_text(text: str) -> str:
    return hashlib.md5(text.encode('utf-8')).hexdigest()[:12]


# ==========================================================================
# 三、差分状态生成
# ==========================================================================

@dataclass
class CharacterStateSnapshot:
    """角色状态快照（用于差分比较）"""
    char_id: str
    name: str
    attrs: dict = field(default_factory=dict)
    goal: str = ""
    emotion: str = ""
    position: tuple = (0, 0)
    inventory: list = field(default_factory=list)
    health: str = "healthy"

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "attrs": dict(self.attrs),
            "goal": self.goal,
            "emotion": self.emotion,
            "position": list(self.position),
            "inventory": list(self.inventory),
            "health": self.health,
        }


def _snapshot_character(char) -> CharacterStateSnapshot:
    """从角色对象提取状态快照"""
    char_id = getattr(char, 'id', '') or getattr(char, 'name', '')
    name = getattr(char, 'name', '')
    attrs = {}
    if hasattr(char, 'attrs') and char.attrs:
        if isinstance(char.attrs, dict):
            attrs = dict(char.attrs)

    goal = getattr(char, 'goal', '') or ''
    emotion = getattr(char, 'emotion', getattr(char, 'story_state', '')) or ''
    pos = getattr(char, 'pos', getattr(char, 'position', (0, 0)))
    if isinstance(pos, list):
        pos = tuple(pos)
    inventory = []
    if hasattr(char, 'inventory'):
        try:
            inventory = list(char.inventory)
        except TypeError:
            inventory = []

    health = getattr(char, 'health', 'healthy') or 'healthy'
    if not isinstance(health, str):
        health = str(health)

    return CharacterStateSnapshot(
        char_id=char_id,
        name=name,
        attrs=attrs,
        goal=goal,
        emotion=emotion,
        position=pos,
        inventory=inventory,
        health=health,
    )


def _diff_snapshots(old: CharacterStateSnapshot, new: CharacterStateSnapshot) -> dict:
    """比较两个快照，返回变动字段"""
    changes = {}
    if old.attrs != new.attrs:
        # 只传变动的属性
        attr_changes = {}
        for k in set(list(old.attrs.keys()) + list(new.attrs.keys())):
            if old.attrs.get(k) != new.attrs.get(k):
                attr_changes[k] = new.attrs.get(k)
        if attr_changes:
            changes["attrs"] = attr_changes
    if old.goal != new.goal:
        changes["goal"] = new.goal
    if old.emotion != new.emotion:
        changes["emotion"] = new.emotion
    if old.position != new.position:
        changes["position"] = list(new.position)
    if old.inventory != new.inventory:
        changes["inventory"] = list(new.inventory)
    if old.health != new.health:
        changes["health"] = new.health
    return changes


# ==========================================================================
# 四、历史滑动窗口
# ==========================================================================

@dataclass
class HistoryWindow:
    """历史滑动窗口状态"""
    full_chapters: list = field(default_factory=list)
    summarized_chapters: list = field(default_factory=list)
    running_summary: str = ""
    _summarizer_fn: object = None  # AI 摘要回调函数 (chapter_num, text) -> str

    def set_summarizer(self, fn):
        """设置 AI 摘要回调"""
        self._summarizer_fn = fn

    def add_chapter(self, chapter_num: int, text: str, max_full: int = 3):
        """添加章节，自动将远章压缩为摘要"""
        self.full_chapters.append({
            "chapter": chapter_num,
            "text": text,
        })

        # 超出窗口的章节移到摘要
        while len(self.full_chapters) > max_full:
            oldest = self.full_chapters.pop(0)
            # 优先使用 AI 摘要，失败则回退到抽取式
            summary_text = ""
            if self._summarizer_fn:
                try:
                    summary_text = self._summarizer_fn(oldest["chapter"], oldest["text"])
                except Exception as e:
                    logger.warning(f"AI 摘要失败（回退到抽取式）: {e}")
                    summary_text = ""
            if not summary_text:
                summary_text = _extractive_summarize(oldest["text"])
            summary = {"chapter": oldest["chapter"], "summary": summary_text}
            self.summarized_chapters.append(summary)
            self.running_summary = _merge_summaries(
                self.running_summary, summary
            )

    def get_recent(self, n: int = 3) -> list:
        """获取最近 N 章完整正文（返回列表）"""
        recent = self.full_chapters[-n:] if len(self.full_chapters) >= n else self.full_chapters[:]
        return recent

    def get_recent_text(self, n: int = 3) -> str:
        """获取最近 N 章完整正文（格式化文本）"""
        recent = self.get_recent(n)
        parts = []
        for ch in recent:
            parts.append(f"第{ch['chapter']}章：\n{ch['text']}")
        return "\n\n".join(parts)

    def get_earlier_summary(self, max_chars: int = 800) -> str:
        """获取更早章节的摘要（压缩版）"""
        if not self.running_summary:
            return ""
        if len(self.running_summary) <= max_chars:
            return self.running_summary
        return self.running_summary[:max_chars] + "..."

    def get_earlier_summaries_list(self) -> list:
        """获取所有远章摘要列表"""
        return list(self.summarized_chapters)

    def clear(self):
        """清空所有状态"""
        self.full_chapters.clear()
        self.summarized_chapters.clear()
        self.running_summary = ""


def _extractive_summarize(text: str) -> str:
    """抽取式摘要（回退方案）：提取首尾关键句，最多 200 字"""
    if not text:
        return ""

    sentences = [s.strip() for s in text.replace('\n', '。').split('。') if s.strip()]
    if len(sentences) <= 3:
        summary = text
    else:
        summary = f"{sentences[0]}。...{sentences[-2]}。{sentences[-1]}。"

    if len(summary) > 200:
        summary = summary[:200] + "..."
    return summary


def _merge_summaries(running: str, new_summary: dict) -> str:
    """合并摘要到运行摘要中"""
    ch = new_summary.get("chapter", "?")
    s = new_summary.get("summary", "")
    if not running:
        return f"第{ch}章概要：{s}"
    return f"{running}\n第{ch}章概要：{s}"


# ==========================================================================
# 五、主控制器
# ==========================================================================

class ContextThrottler:
    """上下文节流主控制器

    三层节流：静态缓存 + 差分传输 + 滑动窗口
    """

    def __init__(self, config: ThrottleConfig = None):
        self.config = config or ThrottleConfig()
        self.static_cache = StaticCache()
        self.prev_snapshots: dict[str, CharacterStateSnapshot] = {}
        self.history = HistoryWindow()
        self.total_tokens_saved = 0
        self.total_chars_saved = 0

    def build_prompt_context(
        self,
        world=None,
        characters: list = None,
        chapter_history: list = None,
        current_chapter: int = 1,
        full_character_ids: list = None,
    ) -> dict:
        """构建压缩后的上下文 prompt。

        Args:
            world: 世界对象
            characters: 角色列表
            chapter_history: 历史章节文本列表 [(chapter_num, text), ...]
            current_chapter: 当前章节号
            full_character_ids: 需要全量传输的角色 ID（主角等）

        Returns:
            dict with keys:
                - world_rules: 世界规则文本（或 'cached:hash'）
                - factions: 势力关系（或 'cached'）
                - characters: 角色数据（全量 or 差分）
                - history_recent: 近 N 章完整正文
                - history_earlier_summary: 更早章节摘要
                - stats: 节流统计
        """
        characters = characters or []
        full_ids = set(full_character_ids or [])
        result = {}
        original_chars = 0
        compressed_chars = 0

        # 1. 世界规则（静态缓存）
        world_rules_text = _extract_world_rules(world)
        original_chars += len(world_rules_text)
        if self.config.static_cache_enabled:
            wr_hash = _hash_text(world_rules_text)
            if self.static_cache.is_cached("world_rules", wr_hash):
                result["world_rules_cached"] = True
                result["world_rules_hash"] = wr_hash
                compressed_chars += len(world_rules_text)
            else:
                self.static_cache.update("world_rules", world_rules_text)
                result["world_rules"] = world_rules_text
                result["world_rules_cached"] = False
        else:
            result["world_rules"] = world_rules_text

        # 2. 势力关系（静态缓存）
        factions_text = _extract_factions_text(world)
        original_chars += len(factions_text)
        if self.config.static_cache_enabled:
            fac_hash = _hash_text(factions_text)
            if self.static_cache.is_cached("factions", fac_hash):
                result["factions_cached"] = True
                result["factions_hash"] = fac_hash
                compressed_chars += len(factions_text)
            else:
                self.static_cache.update("factions", factions_text)
                result["factions"] = factions_text
                result["factions_cached"] = False
        else:
            result["factions"] = factions_text

        # 3. 角色状态（差分传输）
        char_data = {}
        for char in characters:
            char_id = getattr(char, 'id', '') or getattr(char, 'name', '')
            name = getattr(char, 'name', '')
            snap = _snapshot_character(char)
            baseline_text = _character_baseline_text(char)

            # 主角或前 N 个角色：全量
            is_full = char_id in full_ids or len(char_data) < self.config.character_summary_threshold
            if is_full or not self.config.diff_transmission_enabled:
                char_data[name] = {
                    "mode": "full",
                    "baseline": baseline_text,
                    "state": snap.to_dict(),
                }
                original_chars += len(baseline_text) + len(json.dumps(snap.to_dict(), ensure_ascii=False))
                compressed_chars += 0  # 全量传输无节省
            else:
                # 其他角色：差分
                prev = self.prev_snapshots.get(char_id)
                if prev is None:
                    # 第一次出现，传全量
                    char_data[name] = {
                        "mode": "full",
                        "baseline": baseline_text,
                        "state": snap.to_dict(),
                    }
                    original_chars += len(baseline_text) + len(json.dumps(snap.to_dict(), ensure_ascii=False))
                else:
                    diff = _diff_snapshots(prev, snap)
                    if diff:
                        char_data[name] = {
                            "mode": "diff",
                            "changes": diff,
                        }
                        original_chars += len(baseline_text) + len(json.dumps(snap.to_dict(), ensure_ascii=False))
                        compressed_chars += len(baseline_text) + len(json.dumps(snap.to_dict(), ensure_ascii=False)) - len(json.dumps(diff, ensure_ascii=False)) - 30
                    else:
                        char_data[name] = {
                            "mode": "unchanged",
                            "summary": f"{name}：状态未变化",
                        }
                        original_chars += len(baseline_text) + len(json.dumps(snap.to_dict(), ensure_ascii=False))
                        compressed_chars += len(baseline_text) + len(json.dumps(snap.to_dict(), ensure_ascii=False)) - 20

            self.prev_snapshots[char_id] = snap

        result["characters"] = char_data

        # 4. 历史滑动窗口
        if self.config.sliding_window_enabled and chapter_history:
            for ch_num, ch_text in chapter_history:
                self.history.add_chapter(
                    ch_num, ch_text,
                    max_full=self.config.sliding_window_chapters,
                )
            result["history_recent"] = self.history.get_recent_text(self.config.sliding_window_chapters)
            result["history_earlier_summary"] = self.history.get_earlier_summary(self.config.max_summary_chars)
        else:
            result["history_recent"] = ""
            result["history_earlier_summary"] = ""

        # 统计
        saved = original_chars - (original_chars - compressed_chars) if compressed_chars > 0 else 0
        self.total_chars_saved += max(0, compressed_chars)
        result["stats"] = {
            "original_estimate_chars": original_chars,
            "compressed_chars": original_chars - max(0, compressed_chars),
            "saved_chars": max(0, compressed_chars),
            "compression_ratio": round(max(0, compressed_chars) / max(1, original_chars) * 100, 1),
            "total_saved_chars": self.total_chars_saved,
        }

        return result

    def format_prompt_text(self, context: dict) -> str:
        """将结构化上下文格式化为 prompt 文本。"""
        parts = []

        # 世界规则
        if context.get("world_rules"):
            parts.append("【世界规则】\n" + context["world_rules"])
        elif context.get("world_rules_cached"):
            parts.append(f"【世界规则】（已缓存，hash={context.get('world_rules_hash','')}）")

        # 势力
        if context.get("factions"):
            parts.append("【势力关系】\n" + context["factions"])
        elif context.get("factions_cached"):
            parts.append(f"【势力关系】（已缓存，hash={context.get('factions_hash','')}）")

        # 角色
        chars_text = []
        for name, data in context.get("characters", {}).items():
            mode = data.get("mode", "full")
            if mode == "full":
                chars_text.append(f"[{name}] {data.get('baseline', '')}\n状态：{json.dumps(data.get('state',{}),ensure_ascii=False)}")
            elif mode == "diff":
                chars_text.append(f"[{name}]（差分更新）\n变动：{json.dumps(data.get('changes',{}),ensure_ascii=False)}")
            elif mode == "unchanged":
                chars_text.append(f"[{name}] {data.get('summary', '')}")
        if chars_text:
            parts.append("【角色状态】\n" + "\n\n".join(chars_text))

        # 更早历史（摘要）
        if context.get("history_earlier_summary"):
            parts.append("【前期剧情概要】\n" + context["history_earlier_summary"])

        # 近期历史（完整）
        if context.get("history_recent"):
            parts.append("【近期剧情】\n" + context["history_recent"])

        return "\n\n".join(parts)

    # ── 章节历史专用接口（供 NarrativeGenerator 使用） ──

    def set_summarizer(self, fn):
        """设置 AI 摘要回调函数。
        
        Args:
            fn: 回调函数 (chapter_num: int, text: str) -> str
                返回该章的摘要文本（150-200字）
        """
        self.history.set_summarizer(fn)

    def feed_chapter(self, chapter_num: int, text: str):
        """喂入一章完整正文，自动管理滑动窗口。
        
        超出窗口的旧章节会被压缩为摘要（优先 AI，回退抽取式）。
        """
        if not text or len(text.strip()) < 50:
            return
        self.history.add_chapter(
            chapter_num, text,
            max_full=self.config.sliding_window_chapters,
        )

    def build_chapter_context(self, max_total_chars: int = 8000) -> str:
        """构建分层章节上下文文本（供 prompt 注入）。
        
        输出格式：
            ## 前期剧情概要（远章摘要）
            第1章概要：...
            第2章概要：...
            
            ## 近期完整章节
            第3章：
            [完整正文]
            ...
        
        Args:
            max_total_chars: 上下文总字数上限
            
        Returns:
            格式化的历史上下文文本
        """
        parts = []

        # 远章摘要
        earlier = self.history.get_earlier_summary(max_chars=1500)
        if earlier:
            parts.append("## 前期剧情概要（远章摘要）\n" + earlier)

        # 近期完整章节
        recent_list = self.history.get_recent(self.config.sliding_window_chapters)
        if recent_list:
            recent_parts = []
            char_budget = max_total_chars - len(earlier) if earlier else max_total_chars
            used = 0
            for ch in recent_list:
                ch_text = ch['text']
                ch_num = ch['chapter']
                # 如果单章超出预算，截断
                if used + len(ch_text) > char_budget:
                    remaining = char_budget - used
                    if remaining > 500:
                        ch_text = ch_text[:remaining] + "\n...(本章内容过长，已截断)"
                    else:
                        break
                recent_parts.append(f"第{ch_num}章：\n{ch_text}")
                used += len(ch_text)
            if recent_parts:
                parts.append("## 近期完整章节（供衔接参考，勿重复）\n" + "\n\n".join(recent_parts))

        return "\n\n".join(parts) if parts else ""

    def rebuild_from_chapters(self, chapters: list):
        """从已存档的章节列表重建滑动窗口状态。
        
        用于服务器重启后恢复 throttler 状态。
        重建时使用抽取式摘要（快速），不调用 AI，避免大量 API 请求。
        
        Args:
            chapters: [(chapter_num, text), ...] 或 [{"chapter": n, "narrative": text}, ...]
        """
        self.history.clear()
        # 重建时临时禁用 AI 摘要，使用抽取式（快速恢复）
        saved_fn = self.history._summarizer_fn
        self.history._summarizer_fn = None
        try:
            for item in chapters:
                if isinstance(item, tuple) and len(item) == 2:
                    ch_num, ch_text = item
                elif isinstance(item, dict):
                    ch_num = item.get("chapter", 0)
                    ch_text = item.get("narrative", item.get("text", ""))
                else:
                    continue
                if ch_text and len(ch_text.strip()) >= 50:
                    self.feed_chapter(ch_num, ch_text)
        finally:
            # 恢复 AI 摘要器（后续新章节滑出窗口时使用）
            self.history._summarizer_fn = saved_fn

    def get_stats(self) -> dict:
        """获取当前状态统计"""
        return {
            "full_chapter_count": len(self.history.full_chapters),
            "summarized_chapter_count": len(self.history.summarized_chapters),
            "sliding_window_size": self.config.sliding_window_chapters,
            "has_ai_summarizer": self.history._summarizer_fn is not None,
        }


# ==========================================================================
# 六、辅助提取函数
# ==========================================================================

def _extract_world_rules(world) -> str:
    """从世界对象提取规则文本"""
    if world is None:
        return ""
    parts = []
    theme = getattr(world, 'theme', '')
    if theme:
        parts.append(f"世界主题：{theme}")
    main_obj = getattr(world, 'main_objective', '')
    if main_obj:
        parts.append(f"世界主线：{main_obj}")
    # 世界规则 / world_rules
    world_rules = getattr(world, 'world_rules', None) or getattr(world, 'rules', None)
    if world_rules:
        if isinstance(world_rules, list):
            for r in world_rules:
                if isinstance(r, str):
                    parts.append(f"- {r}")
                elif hasattr(r, 'name') and hasattr(r, 'description'):
                    parts.append(f"- {r.name}：{r.description}")
        elif isinstance(world_rules, dict):
            for k, v in world_rules.items():
                parts.append(f"- {k}：{v}")
    return "\n".join(parts)


def _extract_factions_text(world) -> str:
    """从世界对象提取势力关系文本"""
    if world is None:
        return ""
    factions = getattr(world, 'factions', {})
    if not factions:
        return ""
    parts = []
    for fid, fac in factions.items():
        name = getattr(fac, 'name', fid)
        desc = getattr(fac, 'description', '')
        enemies = getattr(fac, 'enemies', [])
        allies = getattr(fac, 'allies', [])
        line = f"【{name}】{desc}"
        if enemies:
            line += f" 敌对：{', '.join(enemies) if isinstance(enemies, list) else str(enemies)}"
        if allies:
            line += f" 同盟：{', '.join(allies) if isinstance(allies, list) else str(allies)}"
        parts.append(line)
    return "\n".join(parts)


def _character_baseline_text(char) -> str:
    """提取角色基础设定（不随 Tick 变化的部分）"""
    name = getattr(char, 'name', '')
    personality = getattr(char, 'personality', '') or ''
    fate_arc = getattr(char, 'fate_arc', getattr(char, 'background', '')) or ''
    char_type = getattr(char, 'char_type', '')
    if hasattr(char_type, 'value'):
        char_type = char_type.value

    lines = []
    if name:
        lines.append(f"姓名：{name}")
    if char_type:
        lines.append(f"身份：{char_type}")
    if personality:
        lines.append(f"性格：{personality}")
    if fate_arc:
        lines.append(f"背景：{fate_arc}")
    return "；".join(lines)
