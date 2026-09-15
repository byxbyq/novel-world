# -*- coding: utf-8 -*-
"""叙事生成 Mixin：AI碰撞叙事/模板降级/章节概要推演"""

import logging
import re
import time
import random
from typing import Tuple

from ..collision_engine import CollisionEvent

logger = logging.getLogger(__name__)


class CollisionNarrativeMixin:
    """
    叙事生成 Mixin：AI碰撞叙事/模板降级/章节概要推演 - Mixin for CollisionEngine
    """

    def _should_use_ai_for_collision(self, event: CollisionEvent) -> bool:
        """判断本次碰撞是否应该调用 AI（按分级 + 配额控制）。

        分级规则：
        - S级（目标对冲/势力冲突）：必用 AI，但受配额限制
        - A级（能力对冲/资源争夺）：按概率用 AI，受配额限制
        - B级（感知对冲/接近碰撞）：直接用模板，不调用 AI
        """
        if not self.ai or not hasattr(self.ai, 'is_available') or not self.ai.is_available:
            return False

        ct = event.collision_type or ""
        config = self.collision_tier_config.get(ct, {"tier": "B", "ai_probability": 0.0})
        tier = config.get("tier", "B")
        prob = config.get("ai_probability", 0.0)

        if tier == "B" or prob <= 0:
            return False

        if self._ai_collisions_used >= self.ai_collision_quota:
            return False

        if tier == "A":
            import random
            if random.random() > prob:
                return False

        return True
    def _generate_collision_narrative(self, event: CollisionEvent) -> str:
        """
        调用AI将碰撞事件转化为叙事文本
        v2：增加重试逻辑（最多2次重试）+ 输出清洗（去Markdown标题/粗体/斜体）

        Args:
            event: 碰撞事件

        Returns:
            叙事文本字符串
        """
        # ── 碰撞分级 + 配额控制（节省 token）──
        if not self._should_use_ai_for_collision(event):
            return self._template_narrative(event)

        system_prompt, user_prompt = self._build_collision_prompt(event)

        # 尝试调用AI（含重试）
        if self.ai and hasattr(self.ai, 'is_available') and self.ai.is_available:
            self._ai_collisions_used += 1
            max_attempts = 2  # 1次初始 + 1次重试（减少重试次数省 token）
            for attempt in range(max_attempts):
                try:
                    narrative = self.ai.chat(
                        system_prompt=system_prompt,
                        user_prompt=user_prompt,
                        max_tokens=self.max_collision_output_tokens,
                    )
                    if narrative and len(narrative.strip()) > 10:
                        # 清洗 Markdown 残留标记
                        narrative = self._clean_narrative(narrative)
                        # 尝试从AI输出中提取对话和伏笔
                        self._extract_narrative_components(event, narrative)
                        return narrative.strip()
                    else:
                        # AI 返回内容过短，视为失败
                        logger.warning(
                            f"AI叙事生成内容过短 "
                            f"({event.char_a_name} vs {event.char_b_name}, "
                            f"attempt {attempt + 1}/{max_attempts})"
                        )
                except Exception as e:
                    logger.warning(
                        f"AI叙事生成失败 "
                        f"({event.char_a_name} vs {event.char_b_name}, "
                        f"attempt {attempt + 1}/{max_attempts}): {e}"
                    )

                # 还有重试机会：等待1秒后加扰动重试
                if attempt < max_attempts - 1:
                    time.sleep(1)
                    user_prompt += (
                        "\n\n[重试指令] 请用与前次完全不同的风格和开头来写，"
                        "视角、切入点、句式都要有显著变化。"
                    )

        # 全部重试失败 → 模板降级
        logger.info(
            f"AI叙事全部重试失败，降级到模板 "
            f"({event.char_a_name} vs {event.char_b_name})"
        )
        return self._template_narrative(event)
    @staticmethod
    def _clean_narrative(text: str) -> str:
        """清洗AI输出中的Markdown残留标记和重复对话列表

        - 移除以 # 开头的独立行（Markdown 标题）
        - 移除 **粗体** 标记（保留文字）
        - 移除 *斜体* 标记（保留文字）
        - 删除段落末尾的连续对话列表（「...」格式的连续行，≥2行）
        - 清理开头/结尾多余空行
        """
        # 1. 移除以 # 开头的独立行（Markdown 标题 h1-h6）
        text = re.sub(r'^\s*#{1,6}\s+.*$', '', text, flags=re.MULTILINE)

        # 2. 移除 **粗体** 标记（保留内部文字）
        text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)

        # 3. 移除 *斜体* 标记（保留内部文字，小心不误删列表 * item）
        #    只匹配非行首的 *xxx* 或行首但紧跟非空格字符的
        text = re.sub(r'(?<!\n)\*(.+?)\*(?!\*)', r'\1', text)
        #    再处理行首 *xxx*（但不匹配 *   这类列表标记）
        text = re.sub(r'(?<=\n)\*(.+?)\*(?!\*)', r'\1', text)

        # 4. 删除段落末尾的连续对话列表（≥2行以「开头、」结尾的连续行）
        #    只在文本末尾区域检测——段落内穿插在叙述中的正常对话不受影响
        text = re.sub(
            r'\n(\n?「[^」]*」){2,}\s*$',
            '',
            text,
        )

        # 5. 清理多余空行：开头/结尾去空白行，连续3+空行压缩为2个
        text = text.strip()
        text = re.sub(r'\n{3,}', '\n\n', text)

        return text
    def _get_recent_narrative_summary(self, n: int = 2) -> str:
        """获取最近 n 次碰撞的叙事摘要，用于跨章连贯性注入

        从 _collision_history 中取最近 n 条已有 narrative 的碰撞事件，
        提取每条叙事的前 120 字符作为简要摘要。

        Args:
            n: 取最近 n 条有叙事的碰撞

        Returns:
            格式化的"前情提要"文本，无结果时返回空字符串
        """
        if not self._collision_history:
            return ""

        # 倒序遍历，取最近 n 条有叙事文本的事件
        recent_with_narrative = []
        for ev in reversed(self._collision_history):
            if ev.narrative and ev.narrative.strip():
                # 取叙事的前 120 字符作为摘要（截断到完整句子边界）
                raw = ev.narrative.strip()
                snippet = raw[:120]
                # 尝试在句号/问号/感叹号处截断
                for sep in ["。", "？", "！", "\n"]:
                    idx = snippet.rfind(sep)
                    if idx > 40:
                        snippet = snippet[:idx + 1]
                        break
                recent_with_narrative.append(
                    f"  - {ev.char_a_name}与{ev.char_b_name}：{snippet}"
                )
            if len(recent_with_narrative) >= n:
                break

        if not recent_with_narrative:
            return ""

        # 反转回时间顺序
        recent_with_narrative.reverse()
        return "## 前情提要\n" + "\n".join(recent_with_narrative) + "\n"
    def _generate_chapter_outline(self) -> str:
        """在每章开始时调用 AI 推演本章剧情方向

        优先使用 external_context（时间树提纲 + 世界状态）驱动生成；
        无 external_context 时回退到传统 role-based prompt。

        Returns:
            本章概要文本，AI 不可用时返回空字符串
        """
        if not self.ai or not hasattr(self.ai, 'is_available') or not self.ai.is_available:
            return ""

        if not self.world or not self.world.characters:
            return ""

        # ── 提纲驱动模式（外部上下文注入）──
        if self._external_context:
            system_prompt = (
                "你是一位小说剧情策划。根据提供的世界状态和情节提纲，"
                "为本章推演 3-5 句话的剧情方向。"
                "不要直接写死对话和动作，给出场景推进方向即可。"
                "描述本章将要发生的核心事件和冲突方向，要具体、有冲突感。"
                "直接输出概要文本，不要加标题或编号。"
            )
            user_prompt = (
                f"{self._external_context}\n\n"
                f"请根据以上世界状态和情节提纲，生成本章叙事方向（3-5句话）："
            )

            try:
                outline = self.ai.chat(
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    max_tokens=300,
                )
                if outline and len(outline.strip()) > 20:
                    logger.info(f"碰撞引擎：[提纲驱动] 第{self._chapter_num}章概要已生成")
                    result = outline.strip()
                    # 日志记录匹配的分支条件
                    logger.info(f"碰撞引擎：[提纲驱动] 上下文长度={len(self._external_context)}字符")
                    return result
            except Exception as e:
                logger.warning(f"章节概要生成失败: {e}")
            return ""

        # ── 传统模式（无外部上下文时兜底）──
        # 构建角色状态摘要
        char_summaries = []
        for c in self.world.characters:
            if not getattr(c, 'alive', True):
                continue
            char_summaries.append(
                f"- {c.name}（{getattr(c, 'char_type', 'NPC')}）："
                f"目标={c.goal or '无'}，"
                f"位置=({c.pos[0]},{c.pos[1]})，"
                f"势力={getattr(c, 'faction_id', '') or '无'}"
            )

        # 前情提要
        recent_summary = self._get_recent_narrative_summary(n=2) or "（本章为开篇，无前情）"

        # 世界主线
        main_obj = getattr(self.world, 'main_objective', '') or "未设定"

        system_prompt = (
            "你是一位小说剧情策划。基于当前角色状态和前情提要，"
            "为本章推演 3-5 句话的剧情方向。"
            "描述本章将要发生的核心事件和冲突方向，"
            "要具体、有冲突感，不要空洞的总结。"
            "直接输出概要文本，不要加标题或编号。"
        )

        user_prompt = (
            f"## 世界主线\n{main_obj}\n\n"
            f"## 当前章节：第{self._chapter_num}章\n\n"
            f"## 角色状态\n" + "\n".join(char_summaries) + "\n\n"
            f"{recent_summary}\n\n"
            f"请推演第{self._chapter_num}章的剧情方向（3-5句话）："
        )

        try:
            outline = self.ai.chat(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                max_tokens=300,
            )
            if outline and len(outline.strip()) > 20:
                logger.info(f"碰撞引擎：第{self._chapter_num}章概要已生成")
                return outline.strip()
        except Exception as e:
            logger.warning(f"章节概要生成失败: {e}")

        return ""
    def _build_collision_prompt(self, event: CollisionEvent) -> Tuple[str, str]:
        """构建碰撞叙事的 system / user prompt"""
        from novel_world.engine.core.prompt_registry import PromptRegistry

        system_prompt = PromptRegistry.get_raw("collision_narrative_system")

        # 查找碰撞双方角色信息
        char_a_info = self._get_character_info(event.char_a_id)
        char_b_info = self._get_character_info(event.char_b_id)

        # 构建前情提要（最近 2 次碰撞的叙事摘要）
        recent_context = self._get_recent_narrative_summary(n=2)
        if recent_context:
            recent_context += "\n"

        # 构建章节概要（本章剧情方向）
        chapter_outline = self._chapter_outline or ""
        if chapter_outline:
            chapter_outline = f"## 本章概要\n{chapter_outline}\n\n"

        # 解析弱方角色名（用于 prompt 提示）
        weaker_name = "无"
        if event.weaker_char_id:
            if event.weaker_char_id == event.char_a_id:
                weaker_name = event.char_a_name or "无"
            elif event.weaker_char_id == event.char_b_id:
                weaker_name = event.char_b_name or "无"

        # 实力差距：用文字档位描述，不传具体倍数（避免 AI 看数值游戏化思考）
        gap = event.power_gap or 0
        if gap >= 3.0:
            power_gap_text = "悬殊（弱方几乎不可能正面抗衡）"
        elif gap >= 2.5:
            power_gap_text = "差距很大（弱方难以抗衡）"
        elif gap >= 1.5:
            power_gap_text = "略悬殊（弱方略处下风）"
        else:
            power_gap_text = "相当"

        # 在场角色列表（供 AI 判断是否有外援可能）
        world_characters = "（无世界实例）"
        if self.world:
            chars = getattr(self.world, 'characters', []) or []
            if chars:
                lines = []
                for c in chars:
                    if not getattr(c, 'alive', True):
                        continue
                    cid = getattr(c, 'id', '')
                    cname = getattr(c, 'name', '未知')
                    if cid in (event.char_a_id, event.char_b_id):
                        continue  # 跳过碰撞双方
                    ctype = getattr(c, 'char_type', None)
                    ctype_str = ctype.value if hasattr(ctype, 'value') else str(ctype)
                    pos = getattr(c, 'pos', None)
                    pos_str = f"({pos[0]},{pos[1]})" if pos else "未知"
                    lines.append(f"  - {cname}（{ctype_str}，位置{pos_str}）")
                world_characters = "\n".join(lines) if lines else "（无其他在场角色）"

        user_prompt = PromptRegistry.get(
            "collision_narrative_user",
            chapter_num=str(self._chapter_num),
            chapter_outline=chapter_outline,
            collision_type=event.collision_type,
            collision_reason=event.collision_reason,
            location=event.location or "未指定",
            world_modifier=event.world_modifier or "无特殊规则",
            outcome_type=event.outcome_type or "未指定",
            weaker_char_name=weaker_name,
            power_gap=power_gap_text,
            char_a_name=event.char_a_name,
            char_a_skill=event.char_a_skill or "无",
            char_a_info=char_a_info,
            char_b_name=event.char_b_name,
            char_b_skill=event.char_b_skill or "无",
            char_b_info=char_b_info,
            world_characters=world_characters,
            recent_context=recent_context,
        )

        # 注入叙事规则（文风统一/禁用词/字数约束等）
        if self._narrative_rules:
            user_prompt += f"\n\n## 叙事规范\n{self._narrative_rules}"

        # 注入信息差上下文（感知状态）
        perception_info = self.build_perception_context()
        if perception_info:
            user_prompt += f"\n\n{perception_info}"

        return system_prompt, user_prompt
    def _get_character_info(self, char_id: str) -> str:
        """获取角色的详细信息，用于prompt构建
        v2：吸收书斋设计——注入深层角色设定（背景/能力/弱点/话术倾向）
        """
        if not self.world:
            return ""
        for c in self.world.characters:
            if getattr(c, 'id', '') == char_id:
                parts = []
                # 基本信息
                personality = getattr(c, 'personality', '')
                if personality:
                    parts.append(f"- 性格：{personality}")
                # 深层设定：背景故事（书斋 Lorebook 等价注入）
                background = getattr(c, 'background', '')
                if background:
                    parts.append(f"- 背景：{background}")
                fate_arc = getattr(c, 'fate_arc', '')
                if fate_arc:
                    parts.append(f"- 命运线：{fate_arc}")
                goal = getattr(c, 'goal', '')
                if goal:
                    parts.append(f"- 当前目标：{goal}")
                # 能力与弱点（书斋 TruthLedger 等价注入 — 用于人格一致性）
                abilities = getattr(c, 'abilities', None)
                if abilities:
                    ab_list = abilities if isinstance(abilities, list) else [abilities]
                    parts.append(f"- 能力：{'、'.join(str(a) for a in ab_list)}")
                weaknesses = getattr(c, 'weaknesses', None)
                if weaknesses:
                    wk_list = weaknesses if isinstance(weaknesses, list) else [weaknesses]
                    parts.append(f"- 弱点：{'、'.join(str(w) for w in wk_list)}")
                story_state = getattr(c, 'story_state', '')
                if story_state:
                    parts.append(f"- 状态：{story_state}")
                state = getattr(c, 'state', None)
                if state:
                    parts.append(
                        f"- 行为状态：{state.value if hasattr(state, 'value') else str(state)}"
                    )
                # 角色话术提示（基于性格派生，帮助AI区分角色语调）
                speech_hint = self._derive_speech_style(personality)
                if speech_hint:
                    parts.append(f"- 话术风格：{speech_hint}")
                return "\n".join(parts)
        return ""
    def _derive_speech_style(self, personality: str) -> str:
        """从性格描述中派生出话术风格提示（辅助 prompt 区分角色语调）"""
        if not personality:
            return ""
        p = personality
        hints = []
        if any(kw in p for kw in ["冷酷", "冷漠", "沉默", "寡言"]):
            hints.append("话少、短句、惜字如金，不说废话")
        elif any(kw in p for kw in ["热情", "开朗", "活泼", "外向"]):
            hints.append("语速快、爱用感叹号、容易兴奋")
        if any(kw in p for kw in ["傲慢", "自负", "骄傲", "狂妄"]):
            hints.append("居高临下、喜欢质问、尾音上扬")
        elif any(kw in p for kw in ["温柔", "善良", "体贴", "柔和"]):
            hints.append("语气温和、善用询问句、会顾及对方感受")
        if any(kw in p for kw in ["谨慎", "多疑", "戒备", "警惕"]):
            hints.append("说话留三分、常用反问、不轻易表态")
        if any(kw in p for kw in ["狡黠", "阴险", "狡猾", "权谋"]):
            hints.append("话中有话、爱打哑谜、表面客气暗藏杀机")
        if any(kw in p for kw in ["豪爽", "直率", "坦荡", "耿直"]):
            hints.append("直来直去、嗓门大、不绕弯子")
        if any(kw in p for kw in ["忧郁", "悲伤", "沉重", "阴郁"]):
            hints.append("语速慢、停顿多、用省略号、语气低沉")
        return "；".join(hints) if hints else ""
    def _extract_narrative_components(self, event: CollisionEvent, narrative: str):
        """
        从AI生成的叙事中尝试提取对话和伏笔
        使用启发式规则提取，后续可替换为AI结构化输出
        """
        import re

        # 提取对话（中文引号和英文引号）
        dialogue_pattern = r'[「\u201c\'"](.*?)[」\u201d\'"]'
        dialogues = re.findall(dialogue_pattern, narrative)
        if dialogues:
            event.dialogue = "\n".join(f"「{d}」" for d in dialogues)

        # 启发式伏笔检测：寻找暗示性关键词
        foreshadow_keywords = [
            "暗暗", "不知", "却没有注意到", "殊不知",
            "命运的齿轮", "谁也不知道", "无人知晓",
            "暗处", "阴影中", "殊不知",
        ]
        for kw in foreshadow_keywords:
            if kw in narrative:
                event.new_foreshadowing.append(f"叙事暗示：{kw}...")
                break  # 每次碰撞最多提取一条伏笔
    _CHAPTER_VARIATION = [
        {"开场": "就在此时，", "收尾": "这一回合的较量，让局势愈发微妙。"},
        {"开场": "转眼之间，", "收尾": "双方都意识到，这场争斗远未结束。"},
        {"开场": "片刻之后，", "收尾": "胜负未分，但暗中的天平已悄然倾斜。"},
        {"开场": "紧接着，", "收尾": "对峙仍在继续，谁也不敢率先露出破绽。"},
        {"开场": "不消多时，", "收尾": "风云变幻间，新的变数正在酝酿。"},
    ]
    def _template_narrative(self, event: CollisionEvent) -> str:
        """模板降级：生成【剧情要点】而非完整叙事（省 token）。
        当AI不可用时，根据碰撞类型生成结构化要点。
        """
        location = event.location or "某处"
        name_a = event.char_a_name
        name_b = event.char_b_name

        templates = {
            "目标对冲": (
                f"- 冲突点：{name_a}与{name_b}在{location}正面遭遇，目标互斥"
                f"- 变化：双方关系恶化，谁都不肯退让"
                f"- 伏笔：{name_b}身后还藏着没出手的人"
            ),
            "感知对冲": (
                f"- 冲突点：{name_a}在{location}察觉到{name_b}的踪迹"
                f"- 变化：{name_a}获得{name_b}位置线索"
                f"- 伏笔：{name_b}尚未发现自己已暴露"
            ),
            "能力对冲": (
                f"- 冲突点：{name_a}与{name_b}在{location}交手，功法相克"
                f"- 变化：{name_b}罩门被点破，实力受损"
                f"- 伏笔：{name_a}察觉{name_b}身上另有古物气息"
            ),
            "接近碰撞": (
                f"- 冲突点：{name_a}与{name_b}在{location}拐角相遇"
                f"- 变化：双方互相试探，关系未定"
                f"- 伏笔：{name_a}注意到{name_b}腰间挂着一枚陌生令牌"
            ),
        }

        narrative = templates.get(
            event.collision_type,
            f"- 冲突点：{name_a}与{name_b}在{location}相遇"
            f"- 变化：双方交换了信息"
            f"- 伏笔：暂无"
        )

        if event.char_a_skill or event.char_b_skill:
            narrative += (
                f"\n- 技能：{name_a}的{event.char_a_skill or '力量'}"
                f"对上{name_b}的{event.char_b_skill or '力量'}"
            )

        return narrative
