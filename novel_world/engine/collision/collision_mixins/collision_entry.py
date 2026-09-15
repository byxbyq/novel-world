# -*- coding: utf-8 -*-
"""入场场景与章节聚合 Mixin：角色入场/章节收尾/正文聚合/弧末反思"""

import logging
from typing import Optional

from novel_world.engine.core.prompt_registry import PromptRegistry
from ..collision_engine import EntryMotivation, EntryScene, ChapterTimeline, CollisionEvent, CollisionOutcome

logger = logging.getLogger(__name__)


class CollisionEntryMixin:
    """
    入场场景与章节聚合 Mixin：角色入场/章节收尾/正文聚合/弧末反思 - Mixin for CollisionEngine
    """

    def generate_entry_scene(
        self,
        character,
        motivation: EntryMotivation = None
    ) -> EntryScene:
        """
        生成角色入场场景
        基于角色的目标、技能、性格、命运线，生成独立的入场叙事。
        每个角色都有自己独立的目的和剧情线，不是为配合主角而存在。

        Args:
            character: 入场角色对象
            motivation: 入场动机（None则根据角色属性自动推断）

        Returns:
            EntryScene 入场场景对象
        """
        char_id = getattr(character, 'id', str(uuid.uuid4())[:8])
        char_name = getattr(character, 'name', '未知角色')

        # 自动推断入场动机
        if motivation is None:
            motivation = self._infer_entry_motivation(character)

        # 提取角色信息
        goal = getattr(character, 'goal', '') or ''
        personality = getattr(character, 'personality', '') or ''
        fate_arc = getattr(character, 'fate_arc', '') or ''
        skills = self._extract_skills(character)
        skill_names = [s["name"] for s in skills if s.get("name")]

        # 构建入场状态描述
        entry_state_parts = []
        if skill_names:
            entry_state_parts.append(f"携带技能：{'、'.join(skill_names[:5])}")
        if personality:
            entry_state_parts.append(f"性格倾向：{personality}")
        story_state = getattr(character, 'story_state', '')
        if story_state:
            entry_state_parts.append(f"当前处境：{story_state}")
        entry_state = "；".join(entry_state_parts)

        # 推断私人目的
        private_purpose = goal if goal else "寻找自己的道路"

        # 生成独立入场剧情描述
        independent_plot = self._generate_independent_plot(character, motivation)

        # 尝试使用AI生成入场叙事
        entry_narrative = self._generate_entry_narrative(
            char_name=char_name,
            motivation=motivation,
            private_purpose=private_purpose,
            independent_plot=independent_plot,
            entry_state=entry_state,
            personality=personality,
            fate_arc=fate_arc,
        )

        scene = EntryScene(
            character_id=char_id,
            character_name=char_name,
            entry_time=f"第{self._chapter_num}章",
            entry_motivation=motivation,
            private_purpose=private_purpose,
            independent_plot=independent_plot,
            entry_state=entry_state,
            entry_narrative=entry_narrative,
        )

        # 添加到当前章节
        if self._current_chapter is not None:
            self._current_chapter.entry_scenes.append(scene)

        logger.info(f"碰撞引擎：生成入场场景 - {char_name} [{motivation.value}]")
        return scene
    def _infer_entry_motivation(self, character) -> EntryMotivation:
        """
        根据角色属性自动推断入场动机
        优先级：有目标 -> 有命运线 -> 有人际关系 -> 默认目标驱动
        """
        goal = getattr(character, 'goal', '') or ''
        fate_arc = getattr(character, 'fate_arc', '') or ''
        relationships = getattr(character, 'relationships', {}) or {}

        if goal:
            return EntryMotivation.GOAL_DRIVEN
        if fate_arc:
            return EntryMotivation.FATE_DRIVEN
        if relationships:
            return EntryMotivation.RELATION_DRIVEN
        return EntryMotivation.GOAL_DRIVEN
    def _generate_independent_plot(
        self, character, motivation: EntryMotivation
    ) -> str:
        """生成角色的独立入场剧情描述（不是为了配合主角）"""
        char_name = getattr(character, 'name', '')
        goal = getattr(character, 'goal', '') or ''
        fate_arc = getattr(character, 'fate_arc', '') or ''

        if motivation == EntryMotivation.GOAL_DRIVEN and goal:
            return f"{char_name}为了{goal}而来，这与他/她自己的利益直接相关"
        elif motivation == EntryMotivation.FATE_DRIVEN:
            return f"命运的安排将{char_name}推到了这里：{fate_arc}"
        elif motivation == EntryMotivation.RELATION_DRIVEN:
            return f"{char_name}因为某个重要之人的缘故来到了这里"
        else:
            return f"{char_name}纯属偶然地出现在了这里"
    def _generate_entry_narrative(
        self, char_name, motivation, private_purpose,
        independent_plot, entry_state, personality, fate_arc
    ) -> str:
        """
        生成入场叙事文本
        优先使用AI，降级使用模板

        Returns:
            入场叙事文本
        """
        from novel_world.engine.core.prompt_registry import PromptRegistry

        system_prompt = PromptRegistry.get_raw("entry_narrative_system")

        personality_line = f"性格：{personality}\n" if personality else ""
        fate_arc_line = f"命运线：{fate_arc}\n" if fate_arc else ""

        user_prompt = PromptRegistry.get(
            "entry_narrative_user",
            char_name=char_name,
            motivation=motivation.value,
            private_purpose=private_purpose,
            independent_plot=independent_plot,
            entry_state=entry_state,
            personality_line=personality_line,
            fate_arc_line=fate_arc_line,
        )

        if self.ai and hasattr(self.ai, 'is_available') and self.ai.is_available:
            try:
                narrative = self.ai.chat(
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    max_tokens=300,
                )
                if narrative and len(narrative.strip()) > 10:
                    return narrative.strip()
            except Exception as e:
                logger.warning(f"AI入场叙事生成失败，使用模板降级: {e}")

        # 模板降级
        motivation_desc = {
            EntryMotivation.GOAL_DRIVEN: "带着明确的目的",
            EntryMotivation.FATE_DRIVEN: "被不可抗拒的力量牵引",
            EntryMotivation.RELATION_DRIVEN: "因为某个重要的人",
            EntryMotivation.ACCIDENT: "毫无预兆地",
        }
        desc = motivation_desc.get(motivation, "")
        return (
            f"{char_name}{desc}出现在了这里。"
            f"{independent_plot}。"
            f"他/她的目光扫过四周，{private_purpose}的念头在脑海中盘旋。"
        )
    def finalize_chapter(self) -> ChapterTimeline:
        """
        结束当前章节，聚合所有碰撞叙事为一章正文
        调用 _aggregate_chapter_text 将四段式时间线合成为连贯章节

        Returns:
            聚合完成的 ChapterTimeline
        """
        if self._current_chapter is None:
            if self._last_finalized_chapter is not None:
                return self._last_finalized_chapter
            logger.warning("碰撞引擎：没有活跃章节需要收尾")
            return ChapterTimeline()

        chapter = self._current_chapter

        # 聚合章节正文
        chapter.chapter_text = self._aggregate_chapter_text(chapter)

        # 生成收尾（如果尚未设置）
        if not chapter.epilogue and chapter.collisions:
            epilogue_parts = []
            last_collision = chapter.collisions[-1]
            if last_collision.aftermath:
                epilogue_parts.append(last_collision.aftermath)
            if last_collision.new_foreshadowing:
                for fs in last_collision.new_foreshadowing[:3]:
                    epilogue_parts.append(f"（伏笔：{fs}）")
            if last_collision.new_crisis:
                for crisis in last_collision.new_crisis[:2]:
                    epilogue_parts.append(f"（危机：{crisis}）")
            if epilogue_parts:
                chapter.epilogue = "\n".join(epilogue_parts)

        logger.info(
            f"碰撞引擎：第{chapter.chapter_num}章收尾完成，"
            f"碰撞{len(chapter.collisions)}次，"
            f"入场{len(chapter.entry_scenes)}人，"
            f"正文{len(chapter.chapter_text)}字"
        )

        # Phase 3：弧末反思 — 章节结束时触发每个角色的 Agent 反思
        self._chapter_arc_reflection(chapter)

        self._current_chapter = None
        self._last_finalized_chapter = chapter
        return chapter
    def _chapter_arc_reflection(self, chapter: "ChapterTimeline"):
        """
        Phase 3：弧末反思 — 章节结束时触发每个角色 Agent 的反思。

        为每个有 Agent 缓存的角色调用 ArcReflector.reflect()，
        生成角色成长摘要，记录到 Agent 记忆中。
        """
        if not self._phase3_enabled:
            return
        if not self._agent_cache:
            return
        try:
            chapter_reflections = {}
            for name, agent in self._agent_cache.items():
                if name in self._arc_reflectors:
                    try:
                        summary = self._arc_reflectors[name].reflect(chapter)
                        chapter_reflections[name] = summary
                        if summary:
                            agent.add_memory(f"[章节反思] {summary}")
                        logger.debug(f"Phase3：角色 [{name}] 弧末反思完成")
                    except Exception as e:
                        logger.warning(f"Phase3：角色 [{name}] 弧末反思失败: {e}")

            if chapter_reflections:
                logger.info(
                    f"Phase3：第{chapter.chapter_num}章弧末反思完成，"
                    f"覆盖 {len(chapter_reflections)} 个角色"
                )
                # 将反思结果附加到章节收尾
                if chapter.epilogue:
                    for name, summary in chapter_reflections.items():
                        if summary:
                            chapter.epilogue += f"\n（{name}的成长：{summary}）"
        except Exception as e:
            logger.warning(f"Phase3：弧末反思流程异常（不影响核心流程）: {e}")
    def _aggregate_chapter_text(self, chapter: ChapterTimeline) -> str:
        """
        将章节时间线中的所有内容聚合为连贯的章节正文
        结构：铺垫 -> 主角行动 -> 各角色入场 -> 碰撞叙事 -> 收尾

        如果AI可用，还会尝试对拼接结果进行润色衔接。

        Args:
            chapter: 章节时间线对象

        Returns:
            完整的章节正文文本
        """
        parts = []

        # ---- 1. 前置铺垫 ----
        if chapter.prelude:
            parts.append(chapter.prelude)

        # ---- 2. 主角行动 ----
        if chapter.protagonist_action:
            parts.append(chapter.protagonist_action)

        # ---- 3. 各配角独立入场 ----
        for entry_scene in chapter.entry_scenes:
            if entry_scene.entry_narrative:
                parts.append(entry_scene.entry_narrative)

        # ---- 4. 碰撞叙事 ----
        for collision in chapter.collisions:
            if collision.narrative:
                parts.append(collision.narrative)
            # 对话已包含在叙事文本中，不再单独追加（避免重复列表）

        # ---- 5. 收尾 ----
        if chapter.epilogue:
            parts.append(chapter.epilogue)

        if not parts:
            return ""

        # 用换行连接各部分
        full_text = "\n\n".join(parts)

        # 如果AI可用且开启了章节润色，尝试润色衔接（默认关闭省 token）
        if (
            self.enable_chapter_polish
            and self.ai
            and hasattr(self.ai, 'is_available')
            and self.ai.is_available
            and len(full_text) > 100
        ):
            try:
                from novel_world.engine.core.prompt_registry import PromptRegistry
                polished = self.ai.chat(
                    system_prompt=PromptRegistry.get_raw("chapter_polish_system"),
                    user_prompt=full_text[:2000],  # 限制输入长度防止溢出
                    max_tokens=1000,
                )
                if polished and len(polished.strip()) > 50:
                    return polished.strip()
            except Exception as e:
                logger.debug(f"章节润色失败，使用原始拼接: {e}")

        return full_text
