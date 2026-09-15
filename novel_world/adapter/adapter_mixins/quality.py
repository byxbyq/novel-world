"""EngineAdapter 质量与终局 Mixin — Timeline检查/终局结算/势力管理"""
import logging

from backend.ai_client import chat, tian_dao_prompt

logger = logging.getLogger("EngineAdapter")

class QualityMixin:
    """timeline checks / finalize / faction / DM"""


    def _nw_tick_timeline_check(self, tick_i: int):
        """Tick 级别的时间回溯检查（轻量，只检查 Tick 顺序 + 角色位置）"""
        try:
            tick_number = self._tick_count - self.config.ticks_per_chapter + tick_i + 1
            world_state = {
                "characters": [
                    {"name": c.name, "position": f"({c.pos[0]},{c.pos[1]})"}
                    for c in self._nw_characters if c.alive
                ],
                "constraints": [],
                "time_marker": "",
            }
            self.timeline_checker.check(
                world_state=world_state,
                narrative_text="",
                tick_number=max(1, tick_number),
                chapter_number=self._backend_world.current_chapter if self._backend_world else 0,
            )
        except Exception:
            pass  # Tick 级检查静默失败


    def inject_world_event(self, cmd: dict):
        """注入世界事件到当前叙事流（DM 干预用）"""
        desc = cmd.get("description", "")
        self.current_chapter_events.append(desc)


    def _run_timeline_check(self, narrative: str, dm_controller=None):
        """调用 TimelineChecker 执行 Fast 规则检查，并将问题写入日志"""
        try:
            # 构造 world_state 摘要（从 Adapter 内部状态提取）
            world_state = {
                "characters": [
                    {
                        "name": c.name,
                        "position": getattr(c, "current_location", ""),
                        "relationships": self._extract_character_relations(c),
                    }
                    for c in self._characters
                ],
                "constraints": (
                    self._backend_world.config.rules if self._backend_world and hasattr(self._backend_world.config, "rules")
                    else []
                ),
                "time_marker": self._backend_world.config.world_stage if self._backend_world else "",
            }

            issues = self.timeline_checker.check(
                world_state=world_state,
                narrative_text=narrative,
                tick_number=self._tick_count,
                chapter_number=self._backend_world.current_chapter if self._backend_world else 0,
            )

            if issues:
                self._timeline_issues.extend(issues)
                # 写入日志
                for issue in issues:
                    logger.warning(
                        f"TimelineChecker [{issue.level.value}] {issue.dimension}: {issue.message}"
                    )

                # 如果有 DM 控制器，将严重问题作为 DM 通知
                if dm_controller:
                    for issue in issues:
                        if issue.level.value in ("error", "blocker"):
                            dm_controller._log(
                                "intervention",
                                "TimelineChecker",
                                {"issue": issue.to_dict()},
                            )
        except Exception as e:
            logger.error(f"TimelineChecker 检查异常: {e}")


    def get_timeline_report(self) -> dict:
        """获取时间线检查报告"""
        return self.timeline_checker.generate_report()


    def get_timeline_issues(self) -> list:
        """获取所有已发现的 Timeline 问题"""
        return [i.to_dict() for i in self._timeline_issues]


    def _dm_sync_state(self, dm_controller, chapter_log: dict = None):
        """同步 DM 控制器的运行时状态（tick / chapter 信息）"""
        if dm_controller is None:
            return
        dm_controller.current_tick = self._tick_count
        dm_controller.current_chapter = self._backend_world.current_chapter if self._backend_world else 0
        dm_controller.total_chapters = self.config.total_chapters
        dm_controller.ticks_per_chapter = self.config.ticks_per_chapter


    def _ai_generate_char_endings(self) -> list:
        """用AI根据角色在本章的表现生成个性化结局总结。

        返回：["角色名：一句话结局", ...] 或 []（AI失败时用兜底逻辑）
        """
        if not self._characters or not self.chapters:
            return []

        # 取最近一章的正文
        last_chapter = self.chapters[-1]
        narrative = last_chapter.get("narrative", "")
        if not narrative:
            return []

        # 构建角色信息
        char_infos = []
        for c in self._characters:
            info = f"{c.name}（{getattr(c.config, 'gender', '') or '男'}，{getattr(c.config, 'age', 20) or 20}岁）"
            lt_goal = getattr(c.config, 'long_term_goal', '') or ''
            if lt_goal:
                info += f"，长期目标：{lt_goal}"
            char_infos.append(info)

        prompt = f"""请根据以下章节正文，为每个角色写一句个性化的结局总结（不是机械的目标完成检查，而是根据角色在本章的实际表现、选择和命运走向）。

角色列表：
{chr(10).join(char_infos)}

章节正文（前2000字）：
{narrative[:2000]}

要求：
1. 每行一个角色，格式：角色名：一句话总结
2. 总结要体现角色在本章的关键行为、选择或命运变化
3. 不要所有人都写"旅途尚未抵达终点"——要根据实际内容写
4. 如果角色在本章没有重要表现，可以写"本章未直接出场，状态不变"
5. 语言简洁有力，有文学感

示例：
白韵秋：交出爷爷的笔记，选择信任同伴，迈出直面真相的第一步
老孙头：从吧台下翻出泛黄的旧手机，把家族秘密托付给了年轻人
织云旧客：匿名发来关键证据，选择站在正义一边但仍保持距离"""

        try:
            from backend.ai_client import chat
            response = chat(
                system_prompt="你是小说结局分析师，根据正文为每个角色写一句个性化结局总结。",
                user_prompt=prompt,
                temperature=0.4,
                max_tokens=500,
            )
            if not response or not response.strip():
                return []

            endings = []
            for line in response.strip().split("\n"):
                line = line.strip()
                if "：" in line or ":" in line:
                    endings.append(line)
            return endings if endings else []
        except Exception:
            return []


    def _finalize_world(self) -> str:
        """终局结算：收拢伏笔、结算势力、生成结局上下文。

        在最后一章叙事生成之前调用，将结果注入到叙事 prompt 中。
        返回：终局结算上下文文本，直接追加到叙事末尾。
        """
        parts = []

        # ── 1. 结算势力斗争 ──
        if self._nw_world and self._nw_world.factions:
            faction_endings = []
            factions = list(self._nw_world.factions.values())
            # 按成员数排序，最大势力胜率最高
            factions.sort(key=lambda f: f.member_count(), reverse=True)
            for i, faction in enumerate(factions):
                rank = "霸主" if i == 0 else ("中坚" if i < len(factions) // 2 + 1 else "衰微")
                enemies = faction.enemies
                ending = f"「{faction.name}」：{rank}"
                if enemies:
                    surviving_enemies = [e for e in enemies if any(
                        f.name == e for f in self._nw_world.factions.values()
                    )]
                    if surviving_enemies:
                        ending += f"，与 {', '.join(surviving_enemies)} 的对抗仍未终结"
                    else:
                        ending += "，已消灭所有敌对势力"
                faction_endings.append(ending)
            if faction_endings:
                parts.append("【势力结局】\n" + "\n".join(faction_endings))

        # ── 2. 角色结局判定 ──
        if self._characters:
            char_endings = []
            # 先尝试用AI生成个性化结局
            ai_endings = self._ai_generate_char_endings()
            if ai_endings:
                char_endings = ai_endings
            else:
                # 兜底：基于目标完成度
                for char in self._characters:
                    goals_done = sum(1 for g in char.short_term_goals 
                                     if hasattr(g, 'progress') and g.progress in ("已完成", "已放弃"))
                    if goals_done > 0:
                        ending = f"{char.name}：完成了 {goals_done} 个目标，"
                        ending += "迎来了自己的归宿" if goals_done >= 2 else "仍在追寻未竟之事"
                    else:
                        ending = f"{char.name}：旅途尚未抵达终点，故事仍在延续"
                    char_endings.append(ending)
            if char_endings:
                parts.append("【角色结局】\n" + "\n".join(char_endings))

        # ── 3. 回收到期伏笔 ──
        clue_text = ""
        if hasattr(self, 'timeline_checker') and self.timeline_checker:
            try:
                unresolved = self.timeline_checker.unresolved_clues
                if unresolved:
                    half_ticks = int(self.config.ticks_per_chapter * 0.5)
                    due_clues = [c for c in unresolved if c.get("age_ticks", 0) > half_ticks]
                    if due_clues:
                        clue_text = "【待回收伏笔】\n" + "\n".join(
                            f"- {c.get('content', c)}" for c in due_clues
                        )
                        parts.append(clue_text)
            except Exception:
                pass

        if not parts:
            return ""

        return "\n\n---\n\n## 终局结算\n\n" + "\n\n".join(parts)

        return "\n\n---\n\n## 终局结算\n\n" + "\n\n".join(parts)

    def _finalize_novel(self) -> dict:
        """生成终局——使用 PromptRegistry 'finale' 模板"""
        from novel_world.engine.core.prompt_registry import PromptRegistry

        self._novel_finalized = True
        world = self._backend_world
        end_behavior = self.config.end_behavior
        expected_ending = self.config.expected_ending

        ending_guidance = ""
        if expected_ending:
            ending_guidance = f"\n\n## 预期结局\n{expected_ending}"

        actions_summary = "\n".join(
            f"{c.name}：{c.current_action or '完成最终行动'}"
            for c in self._characters
        )

        # 终局结算上下文
        final_context = self._finalize_world()

        prompt = PromptRegistry.get(
            "finale",
            end_behavior=end_behavior or "所有主线伏笔收束，角色命运线闭合，世界进入新的平衡",
            actions_summary=actions_summary,
            world_end_state=world.recent_events(),
            ending_guidance=ending_guidance,
            final_context=final_context,
        )
        system_prompt = tian_dao_prompt(
            world.config.to_prompt_text(),
            "\n\n".join(c.full_state_text() for c in self._characters),
            world.recent_events(),
        )
        narrative = chat(system_prompt=system_prompt, user_prompt=prompt, temperature=0.85)

        chapter_log = {
            # 编号跟随章节列表（world.current_chapter 与列表脱节后会跳号）
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

    # ── 势力管理（phase2_p1）──

    def get_faction_summary(self) -> list:
        """获取所有势力摘要（委托给 novel_world World）"""
        if self._nw_world and self._nw_world.factions:
            return [f.to_dict() for f in self._nw_world.factions.values()]
        return []


    def update_faction(self, faction_id: str, data: dict) -> bool:
        """更新势力数据（委托给 novel_world World）"""
        faction = self._nw_world.get_faction(faction_id) if self._nw_world else None
        if not faction:
            return False
        for key in ("name", "description", "territory", "resources", "controlled_resources"):
            if key in data:
                setattr(faction, key, data[key])
        return True
