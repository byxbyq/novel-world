# -*- coding: utf-8 -*-
"""
天意指引（Divine Guidance）— DM 与角色的超自然对话

通过构造叙事化 inject_event 指令，复用 DM 干预管线，将天意指引
以梦境/顿悟/天象/偶遇/内心独白等形式自然融入小说正文。
"""

import logging
from enum import Enum

logger = logging.getLogger("DivineGuidance")


class GuidanceForm(Enum):
    """融入形式"""
    DREAM = "梦境"              # 角色入睡后梦境中接收指引
    EPIPHANY = "顿悟"           # 角色突然想通某事
    OMEN = "天象"               # 天降异象暗示
    ENCOUNTER = "偶遇"          # 偶遇神秘人物传递信息
    INNER_VOICE = "内心独白"     # 角色内心升起某种直觉
    AUTO = "自主选择"           # AI 根据上下文选择最合适形式


class GuidanceStrength(Enum):
    """指引强度"""
    DIRECT = "指引"             # 明确的指引，角色清楚知道该做什么
    HINT = "暗示"               # 有倾向的暗示，角色需要思考解读
    VAGUE = "模糊预感"          # 模糊的感觉，角色不完全确定


class DivineGuidance:
    """天意指引管理器

    底层复用 DM 干预管线：send_guidance() 构造一条带叙事提示的
    inject_event 指令，通过 DMController.execute_command() 注入，
    在下一章叙事生成时由 AI 自然融入。
    """

    # ── 各形式的叙事模板 ──

    _FORM_TEMPLATES = {
        GuidanceForm.DREAM: (
            "【天意指引·梦境】\n"
            "目标角色：{char_name}\n"
            "融入方式：{char_name}做了一个梦。在梦境中，{message}\n"
            "叙事要求：请在后续叙事中详细描写{char_name}的梦境场景（80-150字），"
            "以{strength}的程度传达指引内容。"
            "梦境描写应生动具体，包含象征性意象，角色醒来后应有合理反应。"
        ),
        GuidanceForm.EPIPHANY: (
            "【天意指引·顿悟】\n"
            "目标角色：{char_name}\n"
            "融入方式：{char_name}在日常场景中突然灵光一闪，领悟到：{message}\n"
            "叙事要求：请在后续叙事中自然展现{char_name}的顿悟过程（60-120字），"
            "以{strength}的程度传达指引内容。"
            "通过环境触发（景物/声音/对话）引出灵感，描写角色内心转变的瞬间。"
        ),
        GuidanceForm.OMEN: (
            "【天意指引·天象】\n"
            "目标角色：{char_name}\n"
            "融入方式：天空出现异象（流星/异光/云象/星象），{char_name}观察后内心有所感应：{message}\n"
            "叙事要求：请在后续叙事中描写一个契合世界观的异常天象（80-130字），"
            "以{strength}的程度传达指引内容。"
            "天象的明显程度应与强度匹配，角色对天象的解读应自然合理。"
        ),
        GuidanceForm.ENCOUNTER: (
            "【天意指引·偶遇】\n"
            "目标角色：{char_name}\n"
            "融入方式：{char_name}偶遇一位神秘路人（老者/旅人/孩童），对方的一句无心之言暗含深意：{message}\n"
            "叙事要求：请在后续叙事中创建一个自然的偶遇场景（80-150字），"
            "以{strength}的程度传达指引内容。"
            "路人说完后自然离去，不刻意解释身份，让角色自己品味话中深意。"
        ),
        GuidanceForm.INNER_VOICE: (
            "【天意指引·内心独白】\n"
            "目标角色：{char_name}\n"
            "融入方式：{char_name}心中莫名升起一种预感：{message}\n"
            "叙事要求：请在后续叙事中描写{char_name}的内心活动（60-100字），"
            "以{strength}的程度传达指引内容。"
            "用内心独白或自由间接引语展现角色的直觉，保持自然不突兀。"
        ),
    }

    def __init__(self, dm_controller):
        """
        Args:
            dm_controller: DMController 实例，用于注入指令
        """
        self.dm = dm_controller

    def send_guidance(
        self,
        character_name: str,
        message: str,
        form: GuidanceForm = GuidanceForm.AUTO,
        strength: GuidanceStrength = GuidanceStrength.HINT,
    ) -> dict:
        """向指定角色发送天意指引。

        底层：构造一条 inject_event 指令并通过 DM 管线注入。
        该指令的 description 字段包含叙事模板，在下一章叙事生成时
        由 AI 根据模板要求自然融入正文。

        Args:
            character_name: 目标角色名
            message: 指引内容
            form: 融入形式，AUTO 时自动选择
            strength: 指引强度

        Returns:
            DM 管线执行结果
        """
        # AUTO 模式：自动选择最合适的融入形式
        if form == GuidanceForm.AUTO:
            form = self._auto_select_form(message, strength)

        # 构造叙事化指令
        cmd = self._build_narrative_instruction(
            character_name, message, form, strength
        )

        # 通过已有 DM 干预管线注入
        result = self.dm.execute_command(cmd)

        if result.get("success"):
            logger.info(
                f"天意指引已注入: 角色={character_name}, "
                f"形式={form.value}, 强度={strength.value}"
            )

        return result

    def _build_narrative_instruction(
        self,
        char_name: str,
        message: str,
        form: GuidanceForm,
        strength: GuidanceStrength,
    ) -> dict:
        """构造叙事化 inject_event 指令"""
        template = self._FORM_TEMPLATES.get(
            form, self._FORM_TEMPLATES[GuidanceForm.INNER_VOICE]
        )
        description = template.format(
            char_name=char_name,
            message=message,
            strength=strength.value,
        )
        return {
            "type": "inject_event",
            "description": description,
            "target_characters": [char_name],
            "guidance_form": form.value,
            "guidance_strength": strength.value,
        }

    def _auto_select_form(
        self,
        message: str,
        strength: GuidanceStrength,
    ) -> GuidanceForm:
        """基于关键词启发式自动选择融入形式"""
        msg_lower = message.lower()

        if any(kw in msg_lower for kw in ["修炼", "突破", "功法", "灵气", "丹田", "境界"]):
            return GuidanceForm.INNER_VOICE
        if any(kw in msg_lower for kw in ["预言", "灾难", "大劫", "命运", "星象", "征兆"]):
            return GuidanceForm.OMEN
        if any(kw in msg_lower for kw in ["遗产", "秘典", "古", "传承", "遗迹", "发现"]):
            return GuidanceForm.ENCOUNTER
        if any(kw in msg_lower for kw in ["梦", "睡", "夜"]):
            return GuidanceForm.DREAM
        if strength == GuidanceStrength.DIRECT:
            return GuidanceForm.DREAM
        if strength == GuidanceStrength.HINT:
            return GuidanceForm.ENCOUNTER
        return GuidanceForm.INNER_VOICE
