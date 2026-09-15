# -*- coding: utf-8 -*-
"""
小说世界 - 记忆Agent
从书斋V66 backend/agents/memory_agent.py 移植与适配

伏笔/记忆管理Agent — 在叙事生成流程中自动发现和管理伏笔。
与 TruthLedger 配合使用，实现伏笔全生命周期追踪。
"""

import logging
from typing import Dict, List, Optional, Any
from datetime import datetime

logger = logging.getLogger(__name__)


class MemoryAgent:
    """记忆Agent — 伏笔/记忆管理自动化

    职责：
    1. 从生成文本中自动发现新伏笔
    2. 追踪伏笔生命周期（埋下→激活→回收→废弃）
    3. 检测临近回收的伏笔，提醒AI适时回收
    4. 与管理角色记忆的 Agent 协同

    使用方式：
        magent = MemoryAgent(truth_ledger)
        hooks = magent.scan_for_hooks(chapter_text, chapter_num=5)
        magent.register_hooks(hooks, chapter_num=5)
        reminders = magent.get_recovery_reminders(current_chapter=5)
    """

    # 伏笔信号词（帮助发现潜在伏笔）
    HOOK_SIGNAL_PATTERNS = [
        ("未解", "unresolved"), ("伏笔", "foreshadow"), ("暗示", "hint"),
        ("线索", "clue"), ("铺垫", "foreshadow"), ("预言", "prophecy"),
        ("秘密", "secret"), ("隐藏", "hidden"), ("谜", "mystery"),
        ("留下", "left_behind"), ("约定", "promise"), ("日后", "later"),
        ("将来", "future"), ("预兆", "omen"), ("奇怪", "strange"),
        ("不对劲", "suspicious"), ("隐患", "hidden_danger"),
    ]

    def __init__(self, truth_ledger=None):
        """初始化记忆Agent

        Args:
            truth_ledger: TruthLedger 实例，用于伏笔持久化
        """
        self.ledger = truth_ledger

    def scan_for_hooks(
        self,
        chapter_text: str,
        chapter_num: int,
        min_confidence: float = 0.3,
    ) -> List[dict]:
        """扫描文本中的潜在伏笔

        Args:
            chapter_text: 章节文本
            chapter_num: 章节号
            min_confidence: 最小置信度（0.0-1.0）

        Returns:
            [{"content": "伏笔内容", "hook_type": "神秘线索", "confidence": 0.7}, ...]
        """
        hooks = []
        text_lower = chapter_text.lower()

        for signal_word, hook_type_en in self.HOOK_SIGNAL_PATTERNS:
            if signal_word in text_lower or signal_word in chapter_text:
                # 找到信号词附近的上下文
                idx = chapter_text.find(signal_word)
                if idx < 0:
                    continue

                # 提取上下文（前后各50字）
                start = max(0, idx - 50)
                end = min(len(chapter_text), idx + len(signal_word) + 50)
                context = chapter_text[start:end].strip()

                # 映射到13式钩子类型
                hook_type_cn = self._map_signal_to_hook_type(signal_word)
                confidence = self._estimate_confidence(context)

                if confidence >= min_confidence:
                    hooks.append({
                        "content": context,
                        "hook_type": hook_type_cn,
                        "confidence": confidence,
                        "signal_word": signal_word,
                    })

        # 按置信度排序，去重
        hooks.sort(key=lambda h: h["confidence"], reverse=True)
        return self._deduplicate_hooks(hooks)

    def _map_signal_to_hook_type(self, signal_word: str) -> str:
        """信号词 → 13式钩子类型映射"""
        mapping = {
            "秘密": "神秘线索", "隐藏": "神秘线索", "谜": "神秘线索",
            "预言": "承诺威胁", "预兆": "承诺威胁",
            "暗示": "神秘线索", "线索": "神秘线索",
            "伏笔": "神秘线索", "铺垫": "回声钩子",
            "隐患": "紧急危机", "奇怪": "离奇消失", "不对劲": "离奇消失",
            "未解": "未完成动作", "留下": "留白钩子",
            "约定": "承诺威胁", "日后": "时间限制", "将来": "时间限制",
        }
        return mapping.get(signal_word, "神秘线索")

    @staticmethod
    def _estimate_confidence(context: str) -> float:
        """估计伏笔置信度（基于上下文特征）"""
        score = 0.2  # 基准
        # 含未完成句子
        if "……" in context or "——" in context:
            score += 0.15
        # 含时间指示词
        time_words = ["日后", "将来", "不久", "很快", "下一次", "等"]
        if any(w in context for w in time_words):
            score += 0.15
        # 含承诺/威胁
        if any(w in context for w in ["一定", "必定", "发誓", "承诺", "保证"]):
            score += 0.15
        # 含未解提问
        if "为什么" in context or "怎么" in context:
            score += 0.1
        return min(1.0, score)

    @staticmethod
    def _deduplicate_hooks(hooks: List[dict]) -> List[dict]:
        """去重：相同内容的伏笔只保留置信度最高的"""
        seen = set()
        unique = []
        for h in hooks:
            key = h["content"][:30]
            if key not in seen:
                seen.add(key)
                unique.append(h)
        return unique

    def register_hooks(
        self,
        hooks: List[dict],
        chapter_num: int,
        related_characters: Optional[List[str]] = None,
    ) -> List[str]:
        """将发现的伏笔注册到 TruthLedger

        Returns:
            注册的 hook_id 列表
        """
        if not self.ledger:
            logger.warning("MemoryAgent: 未绑定 TruthLedger，无法注册伏笔")
            return []

        hook_ids = []
        for hook in hooks:
            hook_type = hook.get("hook_type", "神秘线索")
            confidence = hook.get("confidence", 0.5)
            content = hook.get("content", "")

            # 根据置信度估计 arc_type 和 strength
            if confidence >= 0.8:
                arc_type, strength = "long", 5
                expected_recovery = chapter_num + 8
            elif confidence >= 0.6:
                arc_type, strength = "medium", 3
                expected_recovery = chapter_num + 5
            else:
                arc_type, strength = "short", 2
                expected_recovery = chapter_num + 3

            hid = self.ledger.add_hook(
                content=content,
                planted_chapter=chapter_num,
                hook_type=hook_type,
                arc_type=arc_type,
                strength=strength,
                expected_recovery_chapter=expected_recovery,
                related_characters=related_characters or [],
            )
            hook_ids.append(hid)

        return hook_ids

    def get_recovery_reminders(self, current_chapter: int) -> dict:
        """获取伏笔回收提醒

        Returns:
            {
                "overdue": [...],     # 过期待回收
                "nearby": [...],      # 临近回收（±3章）
                "active_count": int,   # 活跃伏笔数
                "pending_count": int,  # 未回收总数
            }
        """
        if not self.ledger:
            return {"overdue": [], "nearby": [], "active_count": 0, "pending_count": 0}

        # 自动激活临近回收的伏笔
        self.ledger.activate_nearby_hooks(current_chapter, window=3)

        overdue = [
            {"id": h.id, "content": h.content, "planted_chapter": h.planted_chapter,
             "expected_recovery": h.expected_recovery_chapter, "hook_type": h.hook_type}
            for h in self.ledger.get_overdue_hooks(current_chapter)
        ]

        pending = self.ledger.get_pending_hooks()
        nearby = [
            {"id": h.id, "content": h.content, "planted_chapter": h.planted_chapter,
             "expected_recovery": h.expected_recovery_chapter, "status": h.status}
            for h in pending
            if h.expected_recovery_chapter
            and abs(current_chapter - h.expected_recovery_chapter) <= 3
        ]

        return {
            "overdue": overdue,
            "nearby": nearby,
            "active_count": len(self.ledger.get_active_hooks()),
            "pending_count": len(pending),
        }

    def format_reminders(self, reminders: dict) -> str:
        """将提醒格式化为LLM可用的上下文文本"""
        parts = []

        if reminders.get("overdue"):
            parts.append("## ⚠️ 过期待回收伏笔")
            for h in reminders["overdue"]:
                parts.append(
                    f"- [{h['hook_type']}] 第{h['planted_chapter']}章埋下，应在第{h['expected_recovery']}章回收: {h['content']}"
                )

        if reminders.get("nearby"):
            parts.append("\n## 📌 临近回收伏笔")
            for h in reminders["nearby"]:
                parts.append(
                    f"- [{h.get('hook_type', '')}] 第{h['planted_chapter']}章埋下: {h['content'][:100]}"
                )

        if not parts:
            parts.append("## 伏笔状态")
            parts.append(f"活跃: {reminders.get('active_count', 0)} | 未回收: {reminders.get('pending_count', 0)}")

        return "\n".join(parts)
