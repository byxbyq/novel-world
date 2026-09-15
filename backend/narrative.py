"""叙事生成器 —— 天道综合所有角色状态，生成小说章节正文"""

import re
import logging

from .world import World
from .character import CharacterAgent
from .ai_client import chat, tian_dao_prompt
from novel_world.engine.core.prompt_registry import PromptRegistry

try:
    from novel_world.engine.context_throttle import ContextThrottler, ThrottleConfig
    _HAS_THROTTLER = True
except ImportError:
    _HAS_THROTTLER = False

logger = logging.getLogger("NarrativeGenerator")


class NarrativeGenerator:
    """叙事生成器：将世界状态和角色行动编织为小说正文

    使用 ContextThrottler 实现分层历史上下文：
    - 近 N 章保留完整正文（默认 2 章）
    - 更早的章节用 AI 压缩为摘要（150-200字/章）
    - 生成新章节时，AI 能看到完整的前文衔接
    """

    def __init__(self):
        # 旧版摘要缓存（保留作为 fallback）
        self._chapter_summaries: list[str] = []

        # 分层历史上下文 throttler
        self._throttler = None
        if _HAS_THROTTLER:
            config = ThrottleConfig(
                static_cache_enabled=False,      # 静态缓存由 narrative.py 自行管理
                diff_transmission_enabled=False,  # 差分传输暂不使用
                sliding_window_enabled=True,
                sliding_window_chapters=2,        # 保留最近 2 章完整正文
                max_summary_chars=1500,           # 远章摘要总字数上限
            )
            self._throttler = ContextThrottler(config)
            self._throttler.set_summarizer(self._ai_summarize_chapter)
            logger.info("ContextThrottler 已接入（滑动窗口=2章，AI摘要已启用）")

    def feed_chapter(self, chapter_num: int, text: str):
        """喂入一章完整正文到滑动窗口。
        
        在章节生成完成后由 adapter 调用。
        """
        if self._throttler:
            self._throttler.feed_chapter(chapter_num, text)
        # 同时维护旧版摘要（fallback 用）
        summary_text = text[:200].replace("\n", " ")
        self._chapter_summaries.append(f"第{chapter_num}章: {summary_text}...")
        if len(self._chapter_summaries) > 5:
            self._chapter_summaries = self._chapter_summaries[-5:]

    def rebuild_chapter_history(self, chapters: list):
        """从已存档的章节列表重建滑动窗口状态。
        
        用于服务器重启后恢复 throttler。
        """
        if self._throttler:
            self._throttler.rebuild_from_chapters(chapters)
            stats = self._throttler.get_stats()
            logger.info(
                f"历史重建完成：{stats['full_chapter_count']}章完整 + "
                f"{stats['summarized_chapter_count']}章摘要"
            )
        # 重建旧版摘要
        self._chapter_summaries = []
        for item in chapters:
            if isinstance(item, dict):
                ch_num = item.get("chapter", 0)
                ch_text = item.get("narrative", item.get("text", ""))
            elif isinstance(item, (tuple, list)) and len(item) == 2:
                ch_num, ch_text = item
            else:
                continue
            if ch_text and len(ch_text.strip()) >= 50:
                summary_text = ch_text[:200].replace("\n", " ")
                self._chapter_summaries.append(f"第{ch_num}章: {summary_text}...")
        if len(self._chapter_summaries) > 5:
            self._chapter_summaries = self._chapter_summaries[-5:]

    def _ai_summarize_chapter(self, chapter_num: int, text: str) -> str:
        """AI 摘要回调：用 AI 将一章正文压缩为 150-200 字摘要。
        
        作为 ContextThrottler 的 summarizer 回调使用。
        失败时返回空字符串，throttler 会自动回退到抽取式摘要。
        """
        if not text or len(text.strip()) < 50:
            return ""

        # 截取前 2000 字给 AI（避免 token 过多）
        excerpt = text[:2000] if len(text) > 2000 else text

        prompt = f"""请将以下小说章节压缩为一段简洁的剧情摘要（150-200字）。

要求：
1. 保留关键剧情转折、人物互动、关系变化
2. 记录重要伏笔和悬念的进展
3. 记录角色状态变化（受伤、突破、获得物品等）
4. 简洁流畅，不要流水账式罗列
5. 只输出摘要正文，不要加"摘要："等前缀

第{chapter_num}章内容：
{excerpt}
"""
        try:
            summary = chat(
                system_prompt="你是一个小说编辑，擅长将长篇章节压缩为精准的剧情摘要。",
                user_prompt=prompt,
                temperature=0.3,
                max_tokens=300,
            )
            summary = summary.strip()
            if summary and len(summary) > 20:
                # 限制最大长度
                if len(summary) > 250:
                    summary = summary[:250] + "..."
                logger.info(f"AI摘要第{chapter_num}章完成（{len(summary)}字）")
                return summary
        except Exception as e:
            logger.warning(f"AI摘要第{chapter_num}章失败: {e}")

        return ""  # 返回空，让 throttler 回退到抽取式

    def generate_chapter(
        self,
        world: World,
        characters: list[CharacterAgent],
        character_actions: dict[str, str],
        title: str = "",
        is_last_chapter: bool = False,
        has_conflicts: bool = False,
        intervention_context: str = "",
        collision_summaries: str = "",
        outline_context: str = "",
        chapter_num: int = 0,
        total_chapters: int = 0,
        retry_hint: str = "",
        on_chunk=None,
    ) -> str:
        """
        生成一章完整的小说正文
        character_actions: {角色名: 该章的行动描述}
        is_last_chapter: 是否为终章（生成终局收尾）
        has_conflicts: 本章是否发生了角色碰撞（生成悬念收尾）
        collision_summaries: 本章碰撞要点（结构化要点，供正文扩写）
        retry_hint: 重写指令（当上一版本质量不达标时传入）
        on_chunk: 流式回调（逐 token），传入后正文生成改为流式
        """
        # 角色行动摘要
        action_summaries = []
        for char in characters:
            action = character_actions.get(char.name, f"{char.name}在本章中按自己的目标行事")
            action_summaries.append(f"{char.name}：{action}")

        # 根据本章状态决定收尾指令（含终局收束逻辑）
        chapters_remaining = total_chapters - chapter_num if total_chapters and chapter_num else 999
        if is_last_chapter:
            ending_instruction = (
                "【终章收束】这是整部小说的最终章！必须：\n"
                "1. 回收所有未解决的伏笔和悬念\n"
                "2. 给每个重要角色一个明确的结局交代\n"
                "3. 呼应世界主线目标，展示最终结果\n"
                "4. 用有余韵的方式结尾，让读者感到圆满而非仓促\n"
                "不要留任何未解悬念——这是整部小说的终点。"
            )
        elif chapters_remaining <= 2:
            ending_instruction = (
                f"【倒数第{chapters_remaining + 1}章·终局铺垫】故事即将结束，本章必须：\n"
                "1. 开始收束主要伏笔，解开关键悬念\n"
                "2. 将主线推向最终高潮的前奏\n"
                "3. 角色面临最终抉择或决战\n"
                "4. 营造终局感，让读者感受到故事正在走向终点"
            )
        elif chapters_remaining <= 5:
            ending_instruction = (
                f"【倒数第{chapters_remaining + 1}章·高潮推进】故事进入高潮阶段，本章应该：\n"
                "1. 主要冲突全面爆发\n"
                "2. 角色面对最大挑战\n"
                "3. 为终局做铺垫，不要引入新的长线悬念\n"
                "4. 节奏加快，张力拉满"
            )
        elif has_conflicts:
            ending_instruction = (
                "结尾制造悬念：停在冲突的紧张瞬间，让读者迫切想知道接下来会发生什么。"
                "可以用一个意外的转折、新线索的浮现、或角色做出关键决定来收尾。"
            )
        else:
            ending_instruction = (
                "结尾自然过渡：用环境描写或角色内心活动收束本章场景，"
                "暗示下一章的新方向或新挑战。避免突兀截断。"
            )

        # 构建分层历史上下文（throttler 优先，fallback 到旧版摘要）
        prev_summaries_text = ""
        if self._throttler:
            prev_summaries_text = self._throttler.build_chapter_context(max_total_chars=8000)
        if not prev_summaries_text and self._chapter_summaries:
            # Fallback: 使用旧版 200 字摘要
            recent_sums = self._chapter_summaries[-3:]
            prev_summaries_text = "## 前章剧情摘要\n" + "\n".join(recent_sums)

        # 角色能力档案（让AI在正文中体现能力差异）
        char_profiles = []
        for char in characters:
            # 标注角色级别（主角/关键配角/普通NPC）
            npc_tier = getattr(char, 'npc_tier', None)
            tier_label = ""
            if npc_tier == "key_npc":
                tier_label = " [关键配角]"
            elif npc_tier == "minor_npc":
                tier_label = " [次要NPC]"

            profile = f"【{char.name}】{tier_label}性别：{getattr(char.config, 'gender', '') or '男'}，年龄：{getattr(char.config, 'age', 20) or 20}"
            abilities = getattr(char.config, 'abilities', None) or []
            weaknesses = getattr(char.config, 'weaknesses', None) or []
            if abilities:
                profile += f"\n  能力：{'，'.join(abilities)}"
            if weaknesses:
                profile += f"\n  弱点：{'，'.join(weaknesses)}"
            if char.attrs:
                attr_str = "，".join(f"{k}={v}" for k, v in char.attrs.items())
                profile += f"\n  属性：{attr_str}"
            # 添加性格和背景信息（如果有的话）
            personality = getattr(char.config, 'personality', '') or ''
            background = getattr(char.config, 'background', '') or ''
            if personality:
                profile += f"\n  性格：{personality}"
            if background:
                profile += f"\n  背景：{background}"
            profile += f"\n  当前状态：{char.current_mood}，位置：{char.current_location or '未知'}"
            action = character_actions.get(char.name, "")
            if action:
                profile += f"\n  本章行动：{action}"
            char_profiles.append(profile)
        char_profiles_text = "\n\n".join(char_profiles) if char_profiles else "（无角色信息）"

        # ── 角色引入指导：根据叙事阶段和角色数量，鼓励AI引入新角色 ──
        char_count = len(characters)
        chapters_remaining = total_chapters - chapter_num if total_chapters and chapter_num else 999
        story_stage = getattr(world.config, 'world_stage', 'opening')

        intro_guidance_parts = []

        # 根据角色数量给出不同指导
        if char_count <= 3:
            # 角色太少，强烈建议引入新角色
            intro_guidance_parts.append(
                f"当前仅有{char_count}个主要角色，故事世界显得空旷。"
                "本章必须引入1-2个新的有名字的角色（NPC/配角/对手），"
                "让他们与现有角色产生互动。新角色要有明确的性格特征和动机，"
                "不能只是路过的无名路人。给新角色取具体的名字，写出他们的性格特点。"
            )
        elif char_count <= 5:
            # 角色偏少，适度引入
            if story_stage in ('opening', 'rising'):
                intro_guidance_parts.append(
                    f"当前有{char_count}个角色。故事正处于{story_stage}阶段，"
                    "可以根据剧情需要引入1个新的配角或对手，丰富人物关系网络。"
                    "新角色应该有名字、有性格、有自己的目的，与现有角色形成新的互动维度。"
                )
            else:
                intro_guidance_parts.append(
                    f"当前有{char_count}个角色。故事已进入{story_stage}阶段，"
                    "聚焦现有角色的命运收束，一般不再引入新的重要角色。"
                    "但可以出现一些次要的NPC（如守卫、商人、信使）来丰富场景。"
                )
        else:
            # 角色已较多
            intro_guidance_parts.append(
                f"当前已有{char_count}个角色，人物阵容丰富。"
                "本章聚焦现有角色的互动和冲突，新出场角色仅作为背景NPC点缀即可。"
            )

        # 续写场景的特殊指导
        if chapter_num > 10 and char_count <= 4:
            intro_guidance_parts.append(
                "注意：故事已推进较远但角色仍然很少，这会导致剧情单调。"
                "请务必在本章引入至少1个有戏份的新角色——可以是新的对手、盟友、"
                "或者被卷入事件的新人物。给新角色取一个独特的名字。"
            )

        intro_guidance = "\n".join(intro_guidance_parts) if intro_guidance_parts else "根据剧情需要自然引入角色。"

        # 构建大纲上下文字段
        outline_text = ""
        if outline_context:
            outline_text = f"## 大纲规划\n{outline_context}"

        prompt = PromptRegistry.get(
            "chapter_generation",
            chapter_num=str(world.current_chapter),
            title=title or f'第{world.current_chapter}章',
            action_summaries=chr(10).join(action_summaries),
            collision_summaries=collision_summaries or "（本章无碰撞）",
            world_events=world.recent_events(),
            tone=world.config.tone,
            ending_instruction=ending_instruction,
            prev_chapter_summaries=prev_summaries_text,
            character_profiles=char_profiles_text,
            character_introduction_guidance=intro_guidance,
            outline_context=outline_text,
        )

        # DM 干预上下文：追加到 prompt 末尾
        if intervention_context:
            prompt += f"\n\n{intervention_context}"

        # 重写指令：追加到 prompt 末尾（当上一版本质量不达标时）
        if retry_hint:
            prompt += retry_hint

        narrative = chat(
            system_prompt=tian_dao_prompt(
                world.config.to_prompt_text(),
                "\n\n".join(c.full_state_text() for c in characters),
                world.recent_events(),
            ),
            user_prompt=prompt,
            temperature=0.9 if retry_hint else 0.85,
            max_tokens=4096,
            on_chunk=on_chunk,
        )

        # 注意：章节摘要/滑动窗口由 adapter 调用 feed_chapter() 维护，
        # 此处不再手动缓存，避免重复

        # ── 章节后状态更新：根据正文内容更新角色心情/目标/关系 ──
        self._post_chapter_status_update(characters, narrative, title)

        # ── 自动发现新角色 ──
        self._auto_discover_characters(characters, narrative, title)

        return narrative

    def generate_world_event(self, world: World, characters: list[CharacterAgent],
                               factions_text: str = "") -> str:
        """天道生成世界级事件（天灾、政变、新势力登场等）。

        修复二注入：main_objective 和 world_stage 约束事件方向。
        修复四注入：factions_text（势力目标摘要）。
        """
        # 构造主线目标约束（修复二）
        main_obj_guidance = ""
        if world.config.main_objective:
            stage_hints = {
                "opening": "引入冲突，让角色感知到主线目标的压力",
                "rising": "冲突升级，推动角色更接近主线目标的核心矛盾",
                "climax": "触发决战或关键转折事件，直接关联主线目标的最核心对抗",
                "falling": "处理决战后果，展示胜负双方的状态",
                "ending": "收束世界线，给予主线目标一个明确的结局",
            }
            hint = stage_hints.get(world.config.world_stage, "")
            stage_cn = {
                "opening": "引入冲突",
                "rising": "冲突升级",
                "climax": "决战转折",
                "falling": "后果处理",
                "ending": "收束结局",
            }
            main_obj_guidance = f"""
【世界主线目标】：{world.config.main_objective}
【当前叙事阶段】：{world.config.world_stage}（{hint}）
请生成贴合主线目标的世界事件，推动叙事向{stage_cn.get(world.config.world_stage, world.config.world_stage)}阶段发展。"""

        # 获取最近事件作为上下文（防止重复）
        recent_events_text = world.recent_events(n=5)
        if recent_events_text == "（尚无世界事件）":
            recent_events_text = "（暂无，请自由发挥）"

        prompt = PromptRegistry.get(
            "world_event",
            chapter_num=str(world.current_chapter),
            world_stage=world.config.world_stage,
            current_situation=world.config.current_situation,
            main_obj_guidance=main_obj_guidance,
            recent_events=recent_events_text,
            active_characters=", ".join(c.name for c in characters),
            factions_text=factions_text,
        )
        return chat(
            system_prompt=tian_dao_prompt(
                world.config.to_prompt_text(),
                "\n\n".join(c.full_state_text() for c in characters),
                world.recent_events(),
            ),
            user_prompt=prompt,
            temperature=0.7,
        ).strip()

    def determine_collisions(
        self, world: World, characters: list[CharacterAgent]
    ) -> list[tuple[int, int]]:
        """天道决定哪些角色在本章中发生碰撞"""
        if len(characters) < 2:
            return []

        # 简单策略：同位置的角色自动碰撞
        collisions = []
        for i, ca in enumerate(characters):
            nearby = world.who_is_nearby(ca.name)
            for j, cb in enumerate(characters):
                if j <= i:
                    continue
                if cb.name in nearby:
                    collisions.append((i, j))
        return collisions

    def _post_chapter_status_update(self, characters: list, narrative: str, title: str):
        """章节生成后，让AI分析正文并更新角色 A/C/B 三层动态人格。

        同步更新传统字段（心情/目标/关系）以保持向后兼容。
        """
        from novel_world.engine.core.prompt_registry import PromptRegistry  # noqa: E402

        char_names = "、".join(c.name for c in characters)
        prompt = PromptRegistry.get(
            "post_chapter_status",
            title=title,
            char_names=char_names,
            narrative=narrative[:2000],
        )

        try:
            response = chat(
                system_prompt="你是小说状态分析师，分析章节中角色的行动风格、驱动力和认知边界变化。",
                user_prompt=prompt,
                temperature=0.3,
                max_tokens=800,
            )
            if not response or not response.strip():
                return

            for line in response.strip().split("\n"):
                line = line.strip()
                if "|" not in line:
                    continue
                parts = [p.strip() for p in line.split("|")]
                if len(parts) < 4:
                    continue
                name = parts[0]
                a_change = parts[1]  # A层·行为风格变化
                c_change = parts[2]  # C层·驱动力变化
                b_change = parts[3]  # B层·认知边界变化

                char = next((c for c in characters if c.name == name), None)
                if not char:
                    continue

                # A层：更新行为风格
                if a_change and a_change != "无":
                    char.action_style = f"{char.action_style}（本章变化：{a_change}）"
                    char.remember("行为风格变化", f"本章中我的行为风格发生了变化：{a_change}")

                # C层：更新驱动力
                if c_change and c_change != "无":
                    char.current_drive = f"{char.current_drive}（本章变化：{c_change}）"
                    char.remember("驱动力变化", f"本章中我的目标驱动力发生了变化：{c_change}")
                    # 提取新目标关键词加入短期目标
                    char.add_goal(c_change, priority=7)

                # B层：更新认知边界 + 关系
                if b_change and b_change != "无":
                    char.cognitive_boundary = f"{char.cognitive_boundary}（本章更新：{b_change}）"
                    char.remember("认知更新", f"本章中我对世界的认知发生了变化：{b_change}")
                    # 同步更新关系（保持向后兼容）
                    for other in characters:
                        if other.name != name and other.name in b_change:
                            for attitude in ["信任", "怀疑", "敌视", "感激", "忌惮", "亲近", "疏远", "敬重", "厌恶", "警惕", "依赖", "敬佩"]:
                                if attitude in b_change:
                                    char.update_relationship(other.name, attitude, b_change)
                                    break

                # 向后兼容：用 B层信息推断心情变化
                if b_change and b_change != "无":
                    char.current_mood = self._infer_mood_from_change(b_change)

        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"章节后状态更新失败: {e}")

    def _infer_mood_from_change(self, change_text: str) -> str:
        """从 B层认知变化文本中推断心情关键词"""
        mood_map = {
            "警惕": "警惕", "怀疑": "疑虑", "信任": "安心", "感激": "感激",
            "敌视": "敌意", "亲近": "愉悦", "疏远": "失落", "厌恶": "厌恶",
            "忌惮": "紧张", "依赖": "依赖", "敬佩": "敬佩",
            "惊讶": "惊讶", "震惊": "震惊", "困惑": "困惑", "好奇": "好奇",
        }
        for keyword, mood in mood_map.items():
            if keyword in change_text:
                return mood
        return "思索"

    def _auto_discover_characters(self, characters: list, narrative: str, title: str):
        """章节生成后，让AI分析正文发现新角色并自动加入。

        流程：AI分析正文 → 提取新出现的有名字角色 → 自动创建CharacterAgent → 加入引擎
        兜底：AI失败时用正则扫描正文中高频出现的中文名作为补充
        """
        existing_names = set(c.name for c in characters)
        prompt = f"""请分析以下章节正文，找出其中新出现的、有名字的重要角色（不包括已在场的角色）。

已在场角色：{'、'.join(existing_names)}

章节正文：
{narrative[:2000]}

请列出新出现的重要角色（有名字、有戏份的，不是路人甲乙）。
格式（每行一个，没有则回复"无"）：
角色名|性别|年龄(估)|性格(几个词)|能力/特长|背景(一句话)|长期目标(一句话)|短期目标(几个词用/分隔)
示例：赵天鸣|男|25|阴沉多疑|魔道功法|青云宗内门弟子，暗中布局夺权|夺取掌门之位|修炼魔功/拉拢内应/试探对手"""

        ai_discovered = []
        try:
            response = chat(
                system_prompt="你是小说角色分析师，从正文中提取新出现的重要角色信息。",
                user_prompt=prompt,
                temperature=0.3,
                max_tokens=500,
            )
            if response and response.strip() and response.strip() != "无":
                for line in response.strip().split("\n"):
                    line = line.strip()
                    if "|" not in line:
                        continue
                    parts = [p.strip() for p in line.split("|")]
                    if len(parts) < 2:
                        continue
                    name = parts[0]
                    if not name or name in existing_names:
                        continue

                    raw_gender = parts[1] if len(parts) > 1 else ""
                    gender = raw_gender if raw_gender in ("男", "女") else "男"
                    age = 20
                    if len(parts) > 2:
                        try:
                            age_str = parts[2].replace("岁", "").replace("(估)", "").strip()
                            age = int(age_str) if age_str else 20
                        except:
                            age = 20
                    personality = parts[3] if len(parts) > 3 else ""
                    abilities = [a.strip() for a in parts[4].split("/")] if len(parts) > 4 and parts[4] else []
                    background = parts[5] if len(parts) > 5 else ""
                    long_term_goal = parts[6] if len(parts) > 6 and parts[6] else ""
                    short_goals_raw = parts[7] if len(parts) > 7 and parts[7] else ""
                    short_term_goals = [g.strip() for g in short_goals_raw.split("/") if g.strip()]

                    from backend.config import CharacterConfig
                    from backend.character import CharacterAgent
                    cfg = CharacterConfig(
                        name=name, gender=gender, age=age,
                        personality=personality, background=background,
                        abilities=abilities, weaknesses=[],
                        long_term_goal=long_term_goal, short_term_goals=short_term_goals,
                        initial_location="",
                    )
                    agent = CharacterAgent(cfg)
                    ai_discovered.append(agent)
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"AI自动发现角色失败: {e}")

        # ── 正则兜底：扫描正文中高频出现的中文名 ──
        regex_discovered = []
        if len(ai_discovered) == 0:
            # 匹配2-4字中文名（排除常见非人名词）
            skip_words = {"他们", "我们", "你们", "众人", "大家", "弟子", "弟子们", "长老", "长老们",
                          "宗主", "掌门", "师兄", "师弟", "师姐", "师妹", "前辈", "晚辈", "小子",
                          "一人", "两人", "三人", "四人", "五人", "所有人", "任何人"}
            # 额外过滤常见非人名2字词
            skip_2char = {
                "目光", "心中", "身形", "衣袖", "手中", "脸色", "嘴角", "声音", "语气",
                "身影", "瞳孔", "膝盖", "指尖", "衣袂", "衣袍", "长啸", "呼啸",
                "地面", "通道", "石碑", "碎片", "宝珠", "锁链", "宫殿", "光柱", "封印",
                "灵力", "灵气", "气血", "魔气", "血光", "符文", "阵法", "禁制",
                "上古", "远古", "天外", "幽暗", "深邃", "漆黑", "幽蓝", "血红", "血色",
                "恐怖", "狰狞", "刺耳", "悠长", "古老", "苍老", "铜印", "长幡", "掌印",
                "血影", "天光", "口气", "这是", "他的", "她的", "那是", "这是",
            }
            name_pattern = re.compile(r'[\u4e00-\u9fa5]{2,4}')
            name_freq = {}
            name_contexts = {}  # 记录每个人名的上下文片段
            for m in name_pattern.finditer(narrative):
                word = m.group()
                if word in skip_words or len(word) < 2:
                    continue
                if len(word) == 2 and word in skip_2char:
                    continue
                # 检查是否像人名：前后有冒号、引号、或作为主语出现
                start = m.start()
                end = m.end()
                context = narrative[max(0,start-5):min(len(narrative),end+5)]
                # 人名通常出现在：「XX道」「XX说」「XX冷」「XX笑」「XX一」「XX脚」「XX手」等
                if any(kw in context for kw in ["道：", "道,", "说：", "说,", "冷笑", "一笑", "一脚",
                                                  "一手", "目光", "心中", "身形", "衣袖", "手中",
                                                  "脸色", "嘴角", "声音", "语气", "身影"]):
                    name_freq[word] = name_freq.get(word, 0) + 1
                    if word not in name_contexts:
                        name_contexts[word] = []
                    # 提取更长的上下文（前后各30字）
                    longer_ctx = narrative[max(0,start-30):min(len(narrative),end+30)]
                    name_contexts[word].append(longer_ctx)

            # 出现2次以上的可能是重要角色
            regex_candidates = []
            for name, freq in name_freq.items():
                if freq >= 2 and name not in existing_names:
                    regex_candidates.append((name, freq, name_contexts.get(name, [])))

            # 用AI为正则发现的角色补全人物卡
            for name, freq, contexts in regex_candidates:
                # 提取该角色在正文中的所有上下文片段
                context_text = "\n---\n".join(contexts[:5])  # 最多取5段上下文

                filled_agent = None
                try:
                    fill_prompt = f"""请根据以下章节正文中「{name}」出现的上下文，为这个角色补全人物卡。

角色名：{name}
出现频率：{freq}次

上下文片段：
{context_text}

请根据上下文推断这个角色的信息，输出格式（每行一个字段，用|分隔）：
{name}|性别|年龄(估)|性格(几个词)|能力/特长|背景(一句话)|长期目标(一句话)|短期目标(几个词用/分隔)
如果无法推断某项，留空即可。"""
                    fill_response = chat(
                        system_prompt="你是小说角色分析师，根据正文上下文推断角色信息。",
                        user_prompt=fill_prompt,
                        temperature=0.3,
                        max_tokens=300,
                    )
                    if fill_response and fill_response.strip() and "|" in fill_response:
                        parts = [p.strip() for p in fill_response.strip().split("|")]
                        raw_gender = parts[1] if len(parts) > 1 else ""
                        gender = raw_gender if raw_gender in ("男", "女") else "男"
                        age = 20
                        if len(parts) > 2:
                            try:
                                age_str = parts[2].replace("岁", "").replace("(估)", "").strip()
                                age = int(age_str) if age_str else 20
                            except:
                                age = 20
                        personality = parts[3] if len(parts) > 3 else ""
                        abilities = [a.strip() for a in parts[4].split("/")] if len(parts) > 4 and parts[4] else []
                        background = parts[5] if len(parts) > 5 else ""
                        long_term_goal = parts[6] if len(parts) > 6 and parts[6] else ""
                        short_goals_raw = parts[7] if len(parts) > 7 and parts[7] else ""
                        short_term_goals = [g.strip() for g in short_goals_raw.split("/") if g.strip()]

                        from backend.config import CharacterConfig
                        from backend.character import CharacterAgent
                        cfg = CharacterConfig(
                            name=name, gender=gender, age=age,
                            personality=personality, background=background,
                            abilities=abilities, weaknesses=[],
                            long_term_goal=long_term_goal, short_term_goals=short_term_goals,
                            initial_location="",
                        )
                        filled_agent = CharacterAgent(cfg)
                        import logging
                        logging.getLogger(__name__).info(
                            f"正则发现角色'{name}'(出现{freq}次)已用AI补全人物卡：性格={personality[:20]}"
                        )
                except Exception as e:
                    import logging
                    logging.getLogger(__name__).warning(f"AI补全角色'{name}'人物卡失败: {e}")

                # AI补全失败时，用基本信息创建
                if filled_agent is None:
                    from backend.config import CharacterConfig
                    from backend.character import CharacterAgent
                    cfg = CharacterConfig(
                        name=name, gender="男", age=20,
                        personality=f"（正则发现，出现{freq}次）",
                        background="",
                        abilities=[], weaknesses=[],
                        long_term_goal="", short_term_goals=[],
                        initial_location="",
                    )
                    filled_agent = CharacterAgent(cfg)

                regex_discovered.append(filled_agent)

        # 合并AI发现和正则发现（去重）
        all_new = ai_discovered + [r for r in regex_discovered if r.name not in {c.name for c in ai_discovered}]

        if all_new:
            if not hasattr(self, '_discovered_chars'):
                self._discovered_chars = []
            self._discovered_chars.extend(all_new)
            for nc in all_new:
                nc.remember("角色登场", f"在{title}中首次登场")
            import logging
            logging.getLogger(__name__).info(
                f"自动发现{len(all_new)}个新角色(AI:{len(ai_discovered)}, 正则:{len(regex_discovered)}): {[c.name for c in all_new]}"
            )
