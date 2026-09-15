# -*- coding: utf-8 -*-
"""
小说世界 - 弧末反思引擎
从 FictionForge framework/agent_base.py 的 reflect() 方法移植与适配

在每章结束后，对角色已积累的记忆进行结构化反思，
产出角色弧线总结、关键决策、情绪变化、关系变化、信念更新等。
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional
from datetime import datetime


@dataclass
class ArcSummary:
    """弧末反思结果"""
    chapter: int
    agent_id: str
    arc_summary: str = ""
    key_decisions: List[str] = field(default_factory=list)
    emotional_shifts: List[dict] = field(default_factory=list)
    relationship_changes: List[dict] = field(default_factory=list)
    belief_updates: List[str] = field(default_factory=list)
    unresolved_tensions: List[str] = field(default_factory=list)
    goals_progress: str = ""
    reflection_timestamp: str = ""

    def to_dict(self) -> dict:
        return {
            "chapter": self.chapter,
            "agent_id": self.agent_id,
            "arc_summary": self.arc_summary,
            "key_decisions": self.key_decisions,
            "emotional_shifts": self.emotional_shifts,
            "relationship_changes": self.relationship_changes,
            "belief_updates": self.belief_updates,
            "unresolved_tensions": self.unresolved_tensions,
            "goals_progress": self.goals_progress,
            "reflection_timestamp": self.reflection_timestamp,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ArcSummary":
        return cls(**{k: v for k, v in data.items() if k in {
            "chapter", "agent_id", "arc_summary", "key_decisions",
            "emotional_shifts", "relationship_changes", "belief_updates",
            "unresolved_tensions", "goals_progress", "reflection_timestamp"
        }})


# 反思系统提示词模板（供LLM调用时注入）
_REFLECTION_SYSTEM = """你是角色弧线分析师。根据角色在本章的经历，进行结构化反思。

请输出以下JSON格式：
{{
    "arc_summary": "角色本章弧线一句话总结",
    "key_decisions": ["决定1", "决定2"],
    "emotional_shifts": [{{"from": "初始情绪", "to": "最终情绪", "trigger": "触发事件"}}],
    "relationship_changes": [{{"character": "角色名", "change": "关系变化描述"}}],
    "belief_updates": ["信念变化1", "信念变化2"],
    "unresolved_tensions": ["未解决的内心冲突"],
    "goals_progress": "目标推进情况描述"
}}

要求：
1. arc_summary 必须简洁，不超过50字
2. key_decisions 只列确实改变剧情走向的决定
3. emotional_shifts 基于角色实际经历，不做臆测
4. 如果某个字段无内容，填空数组/空字符串
"""


class ArcReflector:
    """弧末反思引擎

    使用方式：
        reflector = ArcReflector(agent)
        summary = reflector.reflect(chapter_number)

    返回 ArcSummary 数据类，包含弧末反思的完整结构化结果。
    可与LLM配合，将角色记忆输入模型生成更深入的反思内容。
    """

    def __init__(self, agent=None):
        """
        Args:
            agent: novel_world.agent.Agent 实例，提供记忆与信念访问
        """
        self.agent = agent

    def build_reflection_prompt(
        self,
        chapter: int,
        additional_context: str = "",
    ) -> str:
        """构建反思提示词（供LLM调用）

        将角色记忆和信念打包为反思prompt，由LLM生成结构化反思。
        """
        prompt_parts = [_REFLECTION_SYSTEM, "", f"第{chapter}章反思"]

        if self.agent:
            # 注入角色记忆
            memories = [m for m in self.agent.memories
                        if m.source_chapter == chapter]
            if memories:
                prompt_parts.append("\n## 本章记忆")
                for i, mem in enumerate(memories[:20], 1):
                    prompt_parts.append(
                        f"{i}. [{mem.type}] (强度:{mem.strength:.2f}) {mem.content}"
                    )

            # 注入角色信念
            if self.agent.beliefs:
                prompt_parts.append("\n## 当前信念")
                for belief in self.agent.beliefs.values():
                    if belief.confidence >= 0.3:
                        prompt_parts.append(
                            f"- [{belief.confidence:.0%}] {belief.content}"
                        )

            # 注入角色当前状态
            if self.agent.state.emotions:
                prompt_parts.append("\n## 当前情绪")
                for emotion, intensity in self.agent.state.emotions.items():
                    prompt_parts.append(f"- {emotion}: {intensity:.2f}")

            if self.agent.state.goals:
                prompt_parts.append("\n## 当前目标")
                for goal in self.agent.state.goals:
                    prompt_parts.append(f"- {goal}")

        if additional_context:
            prompt_parts.append(f"\n## 补充上下文\n{additional_context}")

        prompt_parts.append("\n请输出上述JSON格式的反思结果：")
        return "\n".join(prompt_parts)

    def reflect(self, chapter: int) -> ArcSummary:
        """执行弧末反思

        如果关联了agent，从agent获取记忆进行本地聚合；
        否则返回空 ArcSummary。
        """
        summary = ArcSummary(
            chapter=chapter,
            agent_id=self.agent.agent_id if self.agent else "unknown",
            reflection_timestamp=datetime.now().isoformat(),
        )

        if self.agent:
            # 聚合角色的 reflect() 结果
            agent_reflection = self.agent.reflect(chapter)
            summary.arc_summary = agent_reflection.get("arc_summary", "")

            # 记忆计数统计
            event_count = agent_reflection.get("event_count", 0)
            dialogue_count = agent_reflection.get("dialogue_count", 0)

            if event_count > 0 or dialogue_count > 0:
                summary.arc_summary = (
                    f"第{chapter}章：经历{event_count}个事件、{dialogue_count}次对话"
                )

        return summary

    def reflect_with_llm(
        self,
        chapter: int,
        llm_callable,
        additional_context: str = "",
    ) -> ArcSummary:
        """使用LLM进行深度弧末反思

        Args:
            chapter: 章节号
            llm_callable: 可调用对象，接收prompt字符串，返回LLM响应字符串
            additional_context: 额外上下文
        """
        prompt = self.build_reflection_prompt(chapter, additional_context)

        try:
            response = llm_callable(prompt)
            # 尝试解析JSON
            import json as _json
            import re as _re
            json_match = _re.search(r'\{[\s\S]*\}', response)
            if json_match:
                data = _json.loads(json_match.group())
                return ArcSummary(
                    chapter=chapter,
                    agent_id=self.agent.agent_id if self.agent else "unknown",
                    arc_summary=data.get("arc_summary", ""),
                    key_decisions=data.get("key_decisions", []),
                    emotional_shifts=data.get("emotional_shifts", []),
                    relationship_changes=data.get("relationship_changes", []),
                    belief_updates=data.get("belief_updates", []),
                    unresolved_tensions=data.get("unresolved_tensions", []),
                    goals_progress=data.get("goals_progress", ""),
                    reflection_timestamp=datetime.now().isoformat(),
                )
        except Exception:
            pass

        # LLM调用失败时回退到本地聚合
        return self.reflect(chapter)

    def summarize_arc(self, start_chapter: int, end_chapter: int) -> str:
        """汇总多章弧线"""
        if not self.agent:
            return ""

        relevant = [m for m in self.agent.memories
                    if start_chapter <= m.source_chapter <= end_chapter]
        if not relevant:
            return ""

        types = {"event": 0, "dialogue": 0, "observation": 0, "reflection": 0}
        for m in relevant:
            types[m.type] = types.get(m.type, 0) + 1

        return (
            f"第{start_chapter}-{end_chapter}章弧线：共{len(relevant)}条记忆 "
            f"（事件{types['event']}/对话{types['dialogue']}/观察{types['observation']}/反思{types['reflection']}）"
        )
