"""游戏引擎 —— 主循环：天道 → 角色行动 → 碰撞 → 叙事生成"""

from dataclasses import asdict
from .world import World
from .character import CharacterAgent
from .collision import CollisionEngine
from .narrative import NarrativeGenerator
from .ai_client import chat, build_layered_character_prompt, tian_dao_prompt
from .storage import Storage
from .engine_config import EngineConfig


class GameEngine:
    """核心引擎：每章循环执行

    循环（每章）:
      1. 天道评估世界状态 → 决定世界事件
      2. 每个角色根据自己的目标行动
      3. 碰撞引擎处理碰撞 → 目标/关系变化
      4. 天道综合 → 生成章节正文
      5. 更新角色记忆
    """

    def __init__(self, config: EngineConfig = None):
        self.config = config or EngineConfig()
        self.world: World = None
        self.characters: list[CharacterAgent] = []
        self.collision_engine = CollisionEngine()
        self.narrative_generator = NarrativeGenerator()
        self.storage = Storage()
        self.chapters: list[dict] = []   # 已生成的章节
        self._tick_count: int = 0         # 当前章节内的Tick计数
        self._novel_finalized: bool = False  # 终局是否已触发
        self.outline_data: dict = None    # 大纲数据（卷/章节规划）

    def init_game(self, world: World, characters: list[CharacterAgent]):
        """初始化游戏"""
        self.world = world
        self.characters = characters
        self.chapters = []
        self._tick_count = 0
        self._novel_finalized = False

        # 设置角色初始位置
        for char in self.characters:
            if char.current_location:
                self.world.set_character_position(char.name, char.current_location)

        # 如果世界设定了主线目标，自动校准角色目标权重（修复三）
        if self.world.config.main_objective:
            self.align_goals_to_main_objective()

    # ── 目标权重对齐（修复三） ──

    def align_goals_to_main_objective(self):
        """根据 WorldConfig.main_objective 校准所有角色目标的权重。"""
        from novel_world.engine.core.prompt_registry import PromptRegistry  # noqa: E402

        main_obj = self.world.config.main_objective
        if not main_obj:
            return

        for char in self.characters:
            all_goals = []
            if char.long_term_goal.progress not in ("已完成", "已放弃"):
                all_goals.append(("long_term", char.long_term_goal))
            for g in char.short_term_goals:
                if g.progress not in ("已完成", "已放弃"):
                    all_goals.append(("short_term", g))

            if not all_goals:
                continue

            goals_text = "\n".join(
                f"{i+1}. {g.description}" for i, (_, g) in enumerate(all_goals)
            )
            prompt = PromptRegistry.get(
                "goal_alignment",
                main_objective=main_obj,
                character_name=char.name,
                goals_text=goals_text,
            )
            system_prompt = PromptRegistry.get_raw("goal_analyst_system")
            try:
                # 解析 AI 返回的分数
                scores = {}
                for line in response.strip().split("\n"):
                    line = line.strip()
                    parts = line.split("-", 2)
                    if len(parts) >= 2:
                        try:
                            idx = int(parts[0].strip())
                            score = float(parts[1].strip())
                            scores[idx] = max(0.0, min(10.0, score))
                        except (ValueError, IndexError):
                            continue

                # 根据分数调整权重（以 main_objective_weight 为全局缩放系数）
                weight_mul = self.world.config.main_objective_weight
                for idx, (goal_type, goal) in enumerate(all_goals, start=1):
                    score = scores.get(idx)
                    if score is None:
                        continue
                    if score >= 7:
                        goal.weight = (1.5 + (score - 7) / 6) * weight_mul  # 1.5 ~ 2.0 × 系数
                    elif score <= 3:
                        goal.weight = (0.3 + score / 10) * weight_mul     # 0.3 ~ 0.6 × 系数
                    else:
                        goal.weight = 1.0 * weight_mul  # 中等关联 × 系数
            except Exception:
                # AI 调用失败时不阻塞流程，保持权重不变
                pass

    # ── Tick 级控制 ──

    def advance_tick(self) -> dict | None:
        """推进一个Tick（角色行动轮次）。

        Tick到达 ticks_per_chapter 时自动触发章节收尾；
        章节数到达 total_chapters 后触发 _finalize_novel()。

        Returns:
            若触发了章节收尾或终局，返回章节数据 dict；否则返回 None。
        """
        if self._novel_finalized:
            return None  # 终局已触发，不再推进

        self._tick_count += 1

        # 检查是否达到章节Tick上限 → 收尾本章
        if self._tick_count >= self.config.total_chapters * self.config.ticks_per_chapter:
            # 如果当前章节未生成过，先以"收尾"方式跑最后一章
            if len(self.chapters) < self.config.total_chapters:
                return self.run_chapter(title=f"第{self.config.total_chapters}章（终章）")
            return None

        # 检查是否达到单章Tick上限 → 章节收尾
        if self._tick_count % self.config.ticks_per_chapter == 0:
            # 检查是否已达总章节数
            next_ch = len(self.chapters) + 1
            if next_ch > self.config.total_chapters:
                return self._finalize_novel()
            return self.run_chapter(title=f"第{next_ch}章")

        return None  # 普通Tick，不生成章节

    def _compute_chapter_progress_ratio(self) -> float:
        """计算当前章节进度比例（0.0 ~ 1.0），用于推导 world_stage。"""
        if self.config.total_chapters <= 0:
            return 0.0
        return min(len(self.chapters) / self.config.total_chapters, 1.0)

    def _finalize_novel(self) -> dict:
        """生成终局叙事，收束所有伏笔和角色线。

        将 expected_ending 注入 prompt，要求 AI 按预期结局收束。
        返回终局章节数据 dict。
        """
        self._novel_finalized = True

        world = self.world
        end_behavior = self.config.end_behavior
        expected_ending = self.config.expected_ending

        # 构造终局 prompt
        from novel_world.engine.core.prompt_registry import PromptRegistry  # noqa: E402

        ending_guidance = ""
        if expected_ending:
            ending_guidance = f"\n\n## 预期结局（请围绕此方向收束所有伏笔和角色线）\n{expected_ending}"

        actions_summary = "\n".join(
            f"{c.name}：{c.current_action or '完成最终行动'}"
            for c in self.characters
        )

        prompt = PromptRegistry.get(
            "finale",
            end_behavior=end_behavior,
            actions_summary=actions_summary,
            world_events=world.recent_events(),
            ending_guidance=ending_guidance,
        )
        system_prompt = tian_dao_prompt(
            world.config.to_prompt_text(),
            "\n\n".join(c.full_state_text() for c in self.characters),
            world.recent_events(),
        )
        narrative = chat(system_prompt=system_prompt, user_prompt=prompt, temperature=0.85)

        chapter_log = {
            # 编号跟随章节列表（world.current_chapter 在中止/失败的推演中也会累加，
            # 与列表脱节后会跳号）
            "chapter": len(self.chapters) + 1,
            "title": "终章（大结局）",
            "world_event": "",
            "character_actions": {},
            "collisions": [],
            "narrative": narrative,
            "is_finale": True,
        }
        self.chapters.append(chapter_log)
        return chapter_log

    def run_chapter(self, title: str = "") -> dict:
        """运行一章，返回章节数据"""
        world = self.world
        # 章节编号以实际章节列表为准：world.current_chapter 每次推演都累加，
        # 删章/热重载丢章/中止推演后会与列表脱节，导致新章编号跳号
        next_num = len(self.chapters) + 1
        if not title:
            title = f"第{next_num}章"
        world.advance_chapter()

        # 自动推进世界叙事阶段（基于章节进度比例）
        progress = self._compute_chapter_progress_ratio()
        world.config.advance_world_stage(progress)

        chapter_log = {
            "chapter": next_num,
            "title": title,
            "world_event": "",
            "character_actions": {},
            "collisions": [],
            "narrative": "",
        }

        # 步骤1：天道决定世界事件
        world_event = self.narrative_generator.generate_world_event(world, self.characters)
        if world_event and world_event != "无":
            world.add_event("world", world_event, [c.name for c in self.characters])
            chapter_log["world_event"] = world_event
            # 所有角色记录此事件
            for char in self.characters:
                char.remember("世界事件", world_event)

        # 步骤2：每个角色根据自己的目标行动
        character_actions = {}
        for char in self.characters:
            action = self._character_act(char)
            character_actions[char.name] = action
            char.current_action = action
            char.remember("行动", action)
        chapter_log["character_actions"] = character_actions

        # 步骤3：碰撞引擎处理碰撞
        collision_pairs = self.narrative_generator.determine_collisions(world, self.characters)
        collision_results = []
        for i, j in collision_pairs:
            ca = self.characters[i]
            cb = self.characters[j]
            result = self.collision_engine.process_collision(ca, cb, world)
            collision_results.append({
                "characters": [ca.name, cb.name],
                "narrative": result["narrative"],
                "goal_changes": result["goal_changes"],
                "relationship_changes": result["relationship_changes"],
            })

            # 记录碰撞记忆
            ca.remember("碰撞", f"与{cb.name}相遇：{result['narrative'][:100]}")
            cb.remember("碰撞", f"与{ca.name}相遇：{result['narrative'][:100]}")
        chapter_log["collisions"] = collision_results

        # 步骤4：天道生成章节正文
        has_conflicts = len(collision_pairs) > 0
        is_last = world.current_chapter >= self.config.total_chapters
        # 获取大纲上下文
        outline_context = self._get_outline_context(world.current_chapter)
        narrative = self.narrative_generator.generate_chapter(
            world, self.characters, character_actions, title,
            is_last_chapter=is_last,
            has_conflicts=has_conflicts,
            outline_context=outline_context,
            chapter_num=world.current_chapter,
            total_chapters=self.config.total_chapters,
        )
        chapter_log["narrative"] = narrative
        self.chapters.append(chapter_log)

        return chapter_log

    def _get_outline_context(self, chapter_num: int) -> str:
        """根据当前章节号，从大纲中获取对应的上下文信息"""
        if not self.outline_data:
            return ""
        volumes = self.outline_data.get("volumes", [])
        if not volumes:
            return ""
        # 计算全局章节索引 -> 卷/章
        global_idx = chapter_num - 1  # 0-based
        cumulative = 0
        for vol in volumes:
            vol_chapters = vol.get("chapters", [])
            if global_idx < cumulative + len(vol_chapters):
                local_idx = global_idx - cumulative
                vol_name = vol.get("name", "")
                vol_theme = vol.get("theme", "")
                ch_info = vol_chapters[local_idx] if local_idx < len(vol_chapters) else {}
                ch_title = ch_info.get("title", "")
                ch_summary = ch_info.get("summary", "")
                # 获取前后章节信息用于连贯性
                prev_ch = vol_chapters[local_idx - 1] if local_idx > 0 else None
                next_ch = vol_chapters[local_idx + 1] if local_idx < len(vol_chapters) - 1 else None
                # 构建上下文
                ctx_parts = [
                    f"【大纲位置】第{cumulative + local_idx + 1}章 / 共{sum(len(v.get('chapters',[])) for v in volumes)}章",
                    f"【所属卷】{vol_name} —— {vol_theme}",
                    f"【本章规划标题】{ch_title}",
                    f"【本章规划内容】{ch_summary}",
                ]
                if prev_ch:
                    ctx_parts.append(f"【上一章】{prev_ch.get('title','')}：{prev_ch.get('summary','')}")
                if next_ch:
                    ctx_parts.append(f"【下一章预告】{next_ch.get('title','')}：{next_ch.get('summary','')}")
                # 如果是本卷最后一章，提示卷收束
                if local_idx == len(vol_chapters) - 1:
                    ctx_parts.append(f"【卷收束】这是「{vol_name}」的最后一章，请收束本卷线索，为下一卷做过渡")
                return "\n".join(ctx_parts)
            cumulative += len(vol_chapters)
        # 如果超出大纲范围
        total_planned = sum(len(v.get("chapters", [])) for v in volumes)
        if chapter_num > total_planned:
            return f"【大纲提示】本章已超出预设大纲范围（已规划{total_planned}章），请自然推进剧情"
        return ""

    def _character_act(self, char: CharacterAgent) -> str:
        """单个角色根据目标行动，返回行动描述。"""
        from novel_world.engine.core.prompt_registry import PromptRegistry  # noqa: E402

        prompt = PromptRegistry.get(
            "character_action",
            chapter_num=str(self.world.current_chapter),
            full_state=char.full_state_text(),
            goals_with_weights=char.goals_with_weights_text(),
            recent_events=self.world.recent_events(n=3),
        )
        response = chat(
            system_prompt=build_layered_character_prompt(
                char,
                self.world.config.to_prompt_text(),
                self.world.recent_events(),
            ),
            user_prompt=prompt,
            temperature=0.9,
        )
        return response.strip()

    def get_state(self) -> dict:
        """获取当前游戏状态（供前端展示）"""
        return {
            "world": {
                "name": self.world.config.name,
                "chapter": self.world.current_chapter,
                "genre": self.world.config.genre,
                "events_count": len(self.world.events),
                "main_objective": self.world.config.main_objective,      # 修复二
                "world_stage": self.world.config.world_stage,              # 修复二
            },
            "engine": {
                "total_chapters": self.config.total_chapters,              # 修复一
                "ticks_per_chapter": self.config.ticks_per_chapter,
                "end_behavior": self.config.end_behavior,
                "expected_ending": self.config.expected_ending,
                "tick_count": self._tick_count,
                "novel_finalized": self._novel_finalized,
            },
            "characters": [
                {
                    "name": c.name,
                    "gender": getattr(c.config, "gender", "") or "男",
                    "age": getattr(c.config, "age", 20) or 20,
                    "personality": getattr(c.config, "personality", ""),
                    "abilities": getattr(c.config, "abilities", []) or [],
                    "weaknesses": getattr(c.config, "weaknesses", []) or [],
                    "location": c.current_location,
                    "mood": c.current_mood,
                    "long_term_goal": c.long_term_goal.description if c.long_term_goal else "",
                    "active_short_goals": [
                        g.description for g in c.short_term_goals
                        if g.progress not in ("已完成", "已放弃")
                    ],
                    "relationships": c.relationship_text(),
                }
                for c in self.characters
            ],
            "chapters_count": len(self.chapters),
        }

    def save(self, slot: str = "auto"):
        ec = {
            "total_chapters": self.config.total_chapters,
            "ticks_per_chapter": self.config.ticks_per_chapter,
            "tick_speed": self.config.tick_speed,
            "auto_pause_between_chapters": self.config.auto_pause_between_chapters,
            "end_behavior": self.config.end_behavior,
            "expected_ending": self.config.expected_ending,
            "npc_filter_enabled": self.config.npc_filter_enabled,
            "offline_mode": self.config.offline_mode,
            "ai_provider": self.config.ai_provider,
        }
        self.storage.save(slot, self.world, self.characters, self.chapters,
                          self.outline_data, ec)

    def load(self, slot: str = "auto") -> bool:
        result = self.storage.load(slot)
        if result:
            self.world, self.characters, self.chapters, outline, ec = result
            self.outline_data = outline
            # 历史存档可能存在章节号跳号（删章/丢章所致），统一重排为连续编号
            for i, ch in enumerate(self.chapters):
                ch["chapter"] = i + 1
            if ec:
                for k, v in ec.items():
                    if hasattr(self.config, k):
                        setattr(self.config, k, v)
            return True
        return False
