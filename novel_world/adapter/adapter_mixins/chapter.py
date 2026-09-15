"""EngineAdapter 章节执行 Mixin — Tick推进/章节运行/角色行动"""
import logging
import random

from backend.ai_client import chat, build_layered_character_prompt
from backend.character import CharacterAgent

try:
    from novel_world.spec_builder import build_spec_mechanical
    _HAS_SPEC_BUILDER = True
except ImportError:
    _HAS_SPEC_BUILDER = False

# 去AI味后处理 + 局部段落修复
try:
    from backend.post_processor import (
        apply_de_ai_postprocess, detect_ai_flavor, detect_structural_issues,
        local_fix_from_flavor,
    )
    _HAS_DE_AI = True
except ImportError:
    _HAS_DE_AI = False

logger = logging.getLogger("EngineAdapter")

class ChapterMixin:
    """advance_tick / run_chapter / _character_act"""

    # ── 前置主线约束 ──

    def _apply_story_constraint(self, world):
        """应用前置主线约束：绑定角色/势力主线目标 + NPC过滤。

        从 world.config 读取 story_constraint 配置（若有），
        或从 main_objective 自动生成最小约束。
        """
        try:
            from novel_world.engine.constraints import StoryConstraint, apply_constraints
        except ImportError:
            return

        constraint = None
        # 1. 优先从 world.config.story_constraint 读取
        if hasattr(world.config, 'story_constraint') and world.config.story_constraint:
            sc = world.config.story_constraint
            if isinstance(sc, dict):
                constraint = StoryConstraint(**{
                    k: v for k, v in sc.items()
                    if k in StoryConstraint.__dataclass_fields__
                })
            elif isinstance(sc, StoryConstraint):
                constraint = sc

        # 2. 否则从 main_objective 生成最小约束
        if constraint is None:
            main_obj = getattr(world.config, 'main_objective', '') or ''
            if main_obj:
                constraint = StoryConstraint(
                    core_conflict=main_obj,
                    main_quest_weight=0.7,
                    npc_filter_enabled=True,
                    npc_action_weight=0.2,
                )

        if constraint is None:
            return

        # 收集势力列表
        factions_list = list(self._nw_world.factions.values()) if self._nw_world else []

        # 同时应用到 backend 角色和 novel_world 角色
        result_be = apply_constraints(
            constraint,
            world=self._backend_world,
            characters=self._characters,
            factions=factions_list,
        )
        result_nw = apply_constraints(
            constraint,
            world=self._nw_world,
            characters=self._nw_characters,
            factions=factions_list,
        )

        self._story_constraint = constraint
        logger.info(
            f"主线约束已应用：核心矛盾={constraint.core_conflict[:30]}... "
            f"主线权重={constraint.main_quest_weight} "
            f"NPC过滤={'开' if constraint.npc_filter_enabled else '关'}"
        )

    # ── 目标权重对齐（从 backend 原样迁移） ──

    def align_goals_to_main_objective(self):
        """根据 WorldConfig.main_objective 校准所有角色目标的权重。"""
        main_obj = self._backend_world.config.main_objective
        if not main_obj:
            return

        for char in self._characters:
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
            prompt = f"""主线目标：{main_obj}

角色「{char.name}」的当前目标：
{goals_text}

请判断以上每个目标与主线目标的关联度，用 0-10 打分（10=直接相关，0=完全无关）。
输出格式（每行一个）：序号-分数-一句话理由"""
            try:
                response = chat(
                    system_prompt="你是一个叙事分析师，判断角色目标与故事主线的关联度。",
                    user_prompt=prompt,
                    temperature=0.3,
                )
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

                for idx, (goal_type, goal) in enumerate(all_goals, start=1):
                    score = scores.get(idx)
                    if score is None:
                        continue
                    if score >= 7:
                        goal.weight = 1.5 + (score - 7) / 6
                    elif score <= 3:
                        goal.weight = 0.3 + score / 10
                    else:
                        goal.weight = 1.0
            except Exception:
                pass

    # ── Tick 推进 ──

    def advance_tick(self) -> dict | None:
        """推进一个 Tick。

        Tick 到达 ticks_per_chapter 时自动触发章节收尾；
        章节数到达 total_chapters 后触发终局。

        续写机制：当 total_chapters 被外部扩容后，
        _novel_finalized 会被重置为 False，引擎恢复运行。
        """
        # 已终局且未续写扩容 → 停止推进
        if self._novel_finalized:
            return None

        self._tick_count += 1

        tick_result = None

        # 终局检查：仅在 tick 到达上限且章节数也到达上限时触发
        if self._tick_count >= self.config.total_chapters * self.config.ticks_per_chapter:
            if len(self.chapters) < self.config.total_chapters:
                tick_result = self.run_chapter(title=f"第{self.config.total_chapters}章（终章）")
            else:
                # 章节已满 → 触发终局（仅一次）
                if not self._novel_finalized:
                    tick_result = self._finalize_novel()
                else:
                    return None
        # 章节收尾检查
        elif self._tick_count % self.config.ticks_per_chapter == 0:
            next_ch = len(self.chapters) + 1
            if next_ch > self.config.total_chapters:
                # 超出规划上限 → 触发终局（仅一次）
                if not self._novel_finalized:
                    tick_result = self._finalize_novel()
                else:
                    return None
            else:
                tick_result = self.run_chapter(title=f"第{next_ch}章")
        else:
            # 普通 Tick：推进 novel_world CollisionEngine 一个 tick
            self._nw_tick_once()
            return None

        # ── HardConstraintController: 章节叙事约束检查 ──
        if self._hard_constraint and tick_result and tick_result.get("narrative"):
            is_valid, corrected, issues = self._hard_constraint.validate_narrative_hard(
                tick_result["narrative"]
            )
            if issues:
                tick_result["constraint_issues"] = issues

        return tick_result

    def _goal_directed_move(self):
        """目标导向角色移动。

        规则：
        - 有目标（goal 非空）的角色：向最近的其他角色方向移动 → 制造交互
        - 无目标的角色：随机小幅移动（纯背景路人行为）
        """
        if not self._nw_characters:
            return

        nw_map_w = self._nw_world.map_size[0] if self._nw_world else 40
        nw_map_h = self._nw_world.map_size[1] if self._nw_world else 25

        alive = [c for c in self._nw_characters if c.alive]

        for char in alive:
            if not char.goal:
                # ── 无目标：纯背景路人，随机小幅移动 ──
                dx = random.choice([-1, 0, 1])
                dy = random.choice([-1, 0, 1])
            else:
                # ── 有目标：向最近的其他角色方向移动 ──
                others = [c for c in alive if c.id != char.id]
                if not others:
                    dx = random.choice([-1, 0, 1])
                    dy = random.choice([-1, 0, 1])
                else:
                    # 找最近的角色
                    nearest = min(
                        others,
                        key=lambda o: abs(o.pos[0] - char.pos[0]) + abs(o.pos[1] - char.pos[1])
                    )
                    tx, ty = nearest.pos
                    sx, sy = char.pos
                    dx = 1 if tx > sx else (-1 if tx < sx else 0)
                    dy = 1 if ty > sy else (-1 if ty < sy else 0)
                    # 目标导向移动可以更激进（步长 1~2）
                    if random.random() < 0.3:
                        dx *= 2
                        dy *= 2

            new_x = max(0, min(nw_map_w - 1, char.pos[0] + dx))
            new_y = max(0, min(nw_map_h - 1, char.pos[1] + dy))
            char.pos = (new_x, new_y)


    def _nw_tick_once(self):
        """推进 novel_world CollisionEngine 一个 tick"""
        if self._nw_collision is None or not self._nw_characters:
            return

        try:
            # 确保章节已开始
            if self._nw_collision.get_current_chapter() is None:
                self._nw_collision.start_new_chapter()
                self._nw_chapter_idx += 1

            # 目标导向移动 → 碰撞检测
            self._goal_directed_move()
            self._nw_collision.tick(self._nw_characters)
        except Exception:
            pass  # novel_world tick 失败不阻塞

    # ── 章节生成 ──

    def run_chapter(self, title: str = "", dm_controller=None, outline_context: str = "") -> dict:
        """运行一章，返回章节数据。

        混合执行：
          1. backend NarrativeGenerator 生成世界事件 + 角色行动 + AI 叙事
          2. novel_world CollisionEngine 运行本章 ticks + 收尾
          3. 合并双方碰撞结果进入章节 log
        """
        world = self._backend_world
        # 章节编号以实际章节列表为准：world.current_chapter 每次推演都累加，
        # 删章/热重载丢章/中止推演后会与列表脱节，导致新章编号跳号
        next_num = len(self.chapters) + 1
        if not title:
            title = f"第{next_num}章"
        world.advance_chapter()

        # 叙事阶段推进
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

        # ── 步骤1：天道决定世界事件 ──
        if dm_controller:
            dm_controller.set_phase("世界事件推演中")
        factions_text = ""
        if self._nw_world and self._nw_world.factions:
            try:
                factions_text = self._nw_world.faction_goals_text()
            except Exception:
                pass

        world_event = self._narrator.generate_world_event(
            world, self._characters, factions_text=factions_text,
        )
        if world_event and world_event != "无":
            world.add_event("world", world_event, [c.name for c in self._characters])
            chapter_log["world_event"] = world_event
            for char in self._characters:
                char.remember("世界事件", world_event)

        # DM: 世界事件完成后的检查点
        if dm_controller:
            self._dm_sync_state(dm_controller, chapter_log)
            dm_controller._checkpoint()

        # ── 步骤2：角色行动 ──
        if dm_controller:
            dm_controller.set_phase("角色行动推演中")
        character_actions = {}
        for char in self._characters:
            action = self._character_act(char)
            character_actions[char.name] = action
            char.current_action = action
            char.remember("行动", action)
        chapter_log["character_actions"] = character_actions

        # DM: 角色行动完成后的检查点
        if dm_controller:
            self._dm_sync_state(dm_controller, chapter_log)
            dm_controller._checkpoint()

        # ── 步骤3：碰撞检测（backend + novel_world 合并） ──
        if dm_controller:
            dm_controller.set_phase("碰撞推演中")
        # 3a. backend 碰撞（同位置自动碰撞 → AI 生成叙事）
        collision_pairs = self._narrator.determine_collisions(world, self._characters)
        backend_collisions = []
        for i, j in collision_pairs:
            ca = self._characters[i]
            cb = self._characters[j]
            result = self._backend_collision.process_collision(ca, cb, world)
            backend_collisions.append({
                "characters": [ca.name, cb.name],
                "narrative": result["narrative"],
                "goal_changes": result["goal_changes"],
                "relationship_changes": result["relationship_changes"],
                "source": "backend",
            })
            ca.remember("碰撞", f"与{cb.name}相遇：{result['narrative'][:100]}")
            cb.remember("碰撞", f"与{ca.name}相遇：{result['narrative'][:100]}")

        # 3b. novel_world 碰撞（运行本章所有 ticks + 收尾）
        nw_collisions = []
        try:
            if self._nw_collision is not None and self._nw_characters:
                # Phase 3：在生成新章节前，构建章节规格并注入
                if _HAS_SPEC_BUILDER:
                    try:
                        wc = getattr(world, 'config', {})
                        if not isinstance(wc, dict):
                            import dataclasses
                            wc = dataclasses.asdict(wc)
                        spec = build_spec_mechanical(
                            world_config=wc,
                            character_count=len(self._characters),
                            chapter_index=world.current_chapter,
                            total_chapters=getattr(self.config, 'total_chapters', 50),
                        )
                        if spec:
                            spec_prompt = spec.to_prompt()
                            self._nw_collision.set_chapter_context(spec_prompt)
                            logger.info(f"Phase3：章节规格已注入（{len(spec_prompt)} 字符）")
                    except Exception as e:
                        logger.warning(f"Phase3：章节规格构建失败（不影响核心流程）: {e}")

                self._nw_collision.start_new_chapter()
                self._nw_chapter_idx += 1

                for tick_i in range(self.config.ticks_per_chapter):
                    # DM: 每个 Tick 前的检查点
                    if dm_controller:
                        self._dm_sync_state(dm_controller, chapter_log)
                        dm_controller._checkpoint()

                    self._nw_collision.tick(self._nw_characters)

                    # TimelineChecker: 每个 Tick 的时间回溯检查（不依赖叙事文本）
                    self._nw_tick_timeline_check(tick_i)

                finalized = self._nw_collision.finalize_chapter()

                # 提取 novel_world 碰撞结果
                for event in finalized.collisions:
                    nw_collisions.append({
                        "characters": [event.char_a_name, event.char_b_name],
                        "narrative": event.narrative or event.collision_reason or "",
                        "goal_changes": [],
                        "relationship_changes": [],
                        "source": "novel_world",
                        "collision_type": event.collision_type,
                    })

                # 如果没有 backend 碰撞但有 novel_world 碰撞，使用 novel_world 的
                if finalized.chapter_text and not chapter_log.get("narrative"):
                    # 提取主角行动
                    if finalized.protagonist_action:
                        chapter_log.setdefault("_protagonist_action", finalized.protagonist_action)
        except Exception as e:
            logger.warning(f"novel_world CollisionEngine 运行异常: {e}")

        # 合并碰撞结果（去重：相同角色对的只保留一个，优先 backend 的详细版）
        merged_collisions = list(backend_collisions)
        backend_pairs = {tuple(sorted(c["characters"])) for c in backend_collisions}
        for nc in nw_collisions:
            pair = tuple(sorted(nc["characters"]))
            if pair not in backend_pairs:
                merged_collisions.append(nc)
                backend_pairs.add(pair)

        chapter_log["collisions"] = merged_collisions

        # DM: 碰撞完成后的检查点
        if dm_controller:
            self._dm_sync_state(dm_controller, chapter_log)
            dm_controller._checkpoint()

        # ── 步骤4：天道生成章节正文 ──
        if dm_controller:
            dm_controller.set_phase("AI 生成正文中")
            dm_controller.preview_reset(world.current_chapter)
        # 仅在精确到达 total_chapters 时判定为终章（用 == 而非 >=）
        # 这样续写扩容后，新的终章才会正确触发结局
        is_last_chapter = (len(self.chapters) + 1) == self.config.total_chapters

        # 终章结算：收拢伏笔、结算势力、生成结局上下文
        if is_last_chapter:
            final_context = self._finalize_world()
        else:
            final_context = ""

        intervention_context = ""
        if dm_controller:
            intervention_context = dm_controller.get_intervention_context()

        # 将碰撞要点汇总为结构化文本，供天道扩写为正文场景
        collision_summaries = ""
        if merged_collisions:
            summary_lines = []
            for idx, c in enumerate(merged_collisions, 1):
                chars_pair = " vs ".join(c.get("characters", []))
                narr = c.get("narrative", "").strip()
                if narr:
                    summary_lines.append(f"[{idx}] {chars_pair}（{c.get('collision_type','碰撞')}）:\n{narr}")
            collision_summaries = chr(10).join(summary_lines) if summary_lines else "（本章碰撞无要点）"

        narrative = self._narrator.generate_chapter(
            world, self._characters, character_actions, title,
            is_last_chapter=is_last_chapter,
            intervention_context=intervention_context,
            collision_summaries=collision_summaries,
            outline_context=outline_context,
            chapter_num=world.current_chapter,
            total_chapters=self.config.total_chapters,
            on_chunk=dm_controller.preview_append if dm_controller else None,
        )

        # 检查正文是否有效
        if not narrative or len(narrative.strip()) < 50:
            raise RuntimeError(f"AI 生成的正文过短（{len(narrative.strip()) if narrative else 0}字），请检查API连接或稍后重试")

        # 终章附加结算上下文
        if final_context:
            narrative += final_context
        chapter_log["narrative"] = narrative

        # Phase 3：NarrativeEngine 质量管道 + 叙事事件记录
        if self._narrative_engine:
            try:
                narrative = self._narrative_engine._validate_narrative_comprehensive(
                    narrative, world, self._nw_characters
                )
                chapter_log["narrative"] = narrative
            except Exception as e:
                logger.warning(f"Phase3：叙事质量校验跳过: {e}")
            try:
                self._narrative_engine.on_narrative_generated(narrative)
            except Exception:
                pass

        # ── 去AI味后处理 + 局部修复优先 + 全文重写兜底 ──
        if dm_controller:
            dm_controller.set_phase("去AI味后处理与质量审计")
        ai_flavor_result = None
        max_retries = 2  # 最多全文重写2次

        for attempt in range(max_retries + 1):
            if _HAS_DE_AI:
                try:
                    # 后处理前先检测一次
                    before_flavor = detect_ai_flavor(narrative)
                    # 执行规则化清洗
                    narrative = apply_de_ai_postprocess(narrative)
                    chapter_log["narrative"] = narrative
                    # 后处理后检测
                    after_flavor = detect_ai_flavor(narrative)
                    # 结构性问题检测（后处理无法修复的）
                    structural = detect_structural_issues(narrative)

                    ai_flavor_result = {
                        "before_score": before_flavor.get("score", 0),
                        "before_level": before_flavor.get("level", "unknown"),
                        "after_score": after_flavor.get("score", 0),
                        "after_level": after_flavor.get("level", "unknown"),
                        "ai_probability": after_flavor.get("ai_probability", 0),
                        "summary": after_flavor.get("summary", ""),
                        "stats": after_flavor.get("stats", {}),
                        "structural_issues": structural.get("issues", []),
                        "structural_severity": structural.get("severity", "minor"),
                        "regeneration_attempt": attempt,
                    }
                    logger.info(
                        f"[去AI味] 第{world.current_chapter}章 (尝试{attempt+1}/{max_retries+1}): "
                        f"AI味评分 {before_flavor.get('score', 0)}→{after_flavor.get('score', 0)}, "
                        f"AI概率 {before_flavor.get('ai_probability', 0)}%→{after_flavor.get('ai_probability', 0)}%, "
                        f"结构性问题: {structural.get('severity', 'none')}"
                    )

                    # ── 策略分流 ──
                    # 严重结构性问题 → 全文重写（局部修复无法解决）
                    # AI味问题 → 先局部修复，不达标再全文重写
                    need_full_regenerate = False
                    need_local_fix = False
                    retry_reasons = []

                    if structural.get("should_regenerate", False):
                        need_full_regenerate = True
                        retry_reasons.append(
                            f"结构性问题({structural.get('severity')}): "
                            f"{'; '.join(structural.get('issues', []))}"
                        )
                    elif (after_flavor.get("ai_probability", 0) >= 30 or
                          after_flavor.get("score", 0) >= 40):
                        need_local_fix = True
                        retry_reasons.append(
                            f"AI味问题(评分{after_flavor.get('score', 0)}, "
                            f"概率{after_flavor.get('ai_probability', 0)}%)"
                        )

                    # ── 路径A：严重结构性问题 → 全文重写 ──
                    if need_full_regenerate and attempt < max_retries:
                        logger.warning(
                            f"[去AI味] 第{world.current_chapter}章 严重问题，全文重写: "
                            f"{' | '.join(retry_reasons)}"
                        )
                        retry_hint = self._build_retry_prompt(retry_reasons, after_flavor, structural)
                        if dm_controller:
                            dm_controller.set_phase("质量不达标，AI 重写正文中")
                            dm_controller.preview_reset(world.current_chapter)
                        narrative = self._narrator.generate_chapter(
                            world, self._characters, character_actions, title,
                            is_last_chapter=is_last_chapter,
                            intervention_context=intervention_context,
                            collision_summaries=collision_summaries,
                            outline_context=outline_context,
                            chapter_num=world.current_chapter,
                            total_chapters=self.config.total_chapters,
                            retry_hint=retry_hint,
                            on_chunk=dm_controller.preview_append if dm_controller else None,
                        )
                        if narrative and len(narrative.strip()) >= 50:
                            chapter_log["narrative"] = narrative
                            if self._narrative_engine:
                                try:
                                    narrative = self._narrative_engine._validate_narrative_comprehensive(
                                        narrative, world, self._nw_characters
                                    )
                                    chapter_log["narrative"] = narrative
                                except Exception:
                                    pass
                            continue  # 重新检测
                        else:
                            logger.warning(
                                f"[去AI味] 第{world.current_chapter}章 "
                                f"全文重写失败（正文过短），保留原版"
                            )
                            break

                    # ── 路径B：AI味问题 → 局部段落修复 ──
                    elif need_local_fix and attempt < max_retries:
                        logger.info(
                            f"[去AI味] 第{world.current_chapter}章 "
                            f"执行局部段落修复: {retry_reasons}"
                        )
                        narrative, fix_report = local_fix_from_flavor(
                            narrative, after_flavor, max_fixes=5
                        )
                        chapter_log["narrative"] = narrative
                        ai_flavor_result["local_fix"] = fix_report

                        # 局部修复后重新检测
                        post_fix_flavor = detect_ai_flavor(narrative)
                        ai_flavor_result["after_score"] = post_fix_flavor.get("score", 0)
                        ai_flavor_result["after_level"] = post_fix_flavor.get("level", "unknown")
                        ai_flavor_result["ai_probability"] = post_fix_flavor.get("ai_probability", 0)

                        logger.info(
                            f"[去AI味] 第{world.current_chapter}章 局部修复后: "
                            f"评分{after_flavor.get('score', 0)}→{post_fix_flavor.get('score', 0)}, "
                            f"AI概率{after_flavor.get('ai_probability', 0)}%→"
                            f"{post_fix_flavor.get('ai_probability', 0)}%, "
                            f"修复{fix_report.get('fixed', 0)}处"
                        )

                        # 局部修复后仍严重不达标 → 兜底全文重写
                        if (post_fix_flavor.get("ai_probability", 0) >= 45 or
                            post_fix_flavor.get("score", 0) >= 55):
                            logger.warning(
                                f"[去AI味] 第{world.current_chapter}章 "
                                f"局部修复后仍不达标，尝试全文重写"
                            )
                            fallback_reasons = [
                                f"局部修复后AI概率仍高"
                                f"({post_fix_flavor.get('ai_probability', 0)}%)"
                            ]
                            retry_hint = self._build_retry_prompt(
                                fallback_reasons, post_fix_flavor,
                                {"issues": [], "severity": "minor"}
                            )
                            narrative = self._narrator.generate_chapter(
                                world, self._characters, character_actions, title,
                                is_last_chapter=is_last_chapter,
                                intervention_context=intervention_context,
                                collision_summaries=collision_summaries,
                                outline_context=outline_context,
                                chapter_num=world.current_chapter,
                                total_chapters=self.config.total_chapters,
                                retry_hint=retry_hint,
                            )
                            if narrative and len(narrative.strip()) >= 50:
                                chapter_log["narrative"] = narrative
                                if self._narrative_engine:
                                    try:
                                        narrative = self._narrative_engine._validate_narrative_comprehensive(
                                            narrative, world, self._nw_characters
                                        )
                                        chapter_log["narrative"] = narrative
                                    except Exception:
                                        pass
                                continue  # 重新检测
                        # 局部修复达标或无需全文重写
                        break

                    else:
                        if need_full_regenerate or need_local_fix:
                            logger.warning(
                                f"[去AI味] 第{world.current_chapter}章 "
                                f"已达最大尝试次数，保留当前版本"
                            )
                        break  # 无需处理或已达上限

                except Exception as e:
                    logger.warning(f"[去AI味] 后处理失败（不影响正文）: {e}")
                    break

        if ai_flavor_result:
            chapter_log["ai_flavor"] = ai_flavor_result

        # 干预已融入叙事，清理干预日志
        if dm_controller:
            dm_controller.clear_interventions()
            self.current_chapter_events.clear()

        # ── TimelineChecker: Fast 规则检查 ──
        self._run_timeline_check(narrative, dm_controller)

        # ─ 自动发现的新角色加入引擎 ─
        self._integrate_discovered_characters()

        self.chapters.append(chapter_log)

        # ── 喂入滑动窗口：让下一章能看到本章完整正文 ──
        try:
            self._narrator.feed_chapter(world.current_chapter, narrative)
        except Exception as e:
            logger.warning(f"feed_chapter 失败（不影响章节生成）: {e}")

        # Phase 3：章节结束 — 生成 TruthLedger 快照
        if self._narrative_engine:
            try:
                self._narrative_engine.archive_chapter(world.current_chapter)
                logger.info(f"Phase3：第{world.current_chapter}章 TruthLedger 快照已生成")
            except Exception as e:
                logger.warning(f"Phase3：章节快照失败: {e}")

        return chapter_log

    def _build_retry_prompt(self, retry_reasons: list, flavor_result: dict, structural: dict) -> str:
        """构建重写指令：根据检测到的问题生成具体的修正提示。

        Args:
            retry_reasons: 重写原因列表
            flavor_result: AI味检测结果
            structural: 结构性问题检测结果

        Returns:
            重写指令文本，将追加到生成prompt末尾
        """
        parts = [
            "\n\n## ⚠️ 重写指令（上一版本被拒绝，必须修正以下问题）",
        ]

        for reason in retry_reasons:
            parts.append(f"- {reason}")

        # 结构性问题具体指导
        structural_issues = structural.get("issues", [])
        if any("过短" in s for s in structural_issues):
            parts.append("\n### 字数不足")
            parts.append("上一版本字数严重不足。本章必须达到2000-3000字。不要只写概要，要展开完整的场景、对话、动作、心理描写。")

        if any("重复段落" in s or "模板化" in s for s in structural_issues):
            parts.append("\n### 消除重复模板")
            parts.append("上一版本出现了大量重复的模板化段落（如'片刻之后，某处，X遇到了Y'反复出现）。")
            parts.append("绝对禁止：")
            parts.append("- 不要逐条罗列角色相遇，要把碰撞融入连贯的叙事场景中")
            parts.append("- 不要用'片刻之后''某处'等模板化过渡词")
            parts.append("- 每段内容必须不同，不能复制粘贴改名字")

        if any("句首模式重复" in s for s in structural_issues):
            stats = flavor_result.get("stats", {})
            cv = stats.get("burstiness_cv", 0)
            parts.append(f"\n### 句式变化不足（变异系数{cv}）")
            parts.append("上一版本句子开头高度重复。修正方法：")
            parts.append("- 连续两句绝对不能以相同词/短语开头")
            parts.append("- 混合使用：动作开头、对话开头、环境描写开头、心理活动开头")
            parts.append("- 长短句交错：有的句子只有5个字，有的可以到40字")

        if any("碰撞摘要泄漏" in s for s in structural_issues):
            parts.append("\n### 碰撞摘要泄漏（最严重！）")
            parts.append("上一版本直接输出了碰撞摘要的模板文本，而非小说正文！")
            parts.append("碰撞要点只是骨架，你必须把它扩写成完整的小说场景：")
            parts.append("- 写出具体的打斗动作、对话、环境、心理")
            parts.append("- 不要出现'X遇到了Y''两道气息同时爆发'等摘要式语句")
            parts.append("- 要像写小说一样写，不是写大纲")

        if any("引号格式混乱" in s for s in structural_issues):
            parts.append("\n### 对话格式统一")
            parts.append("上一版本同时使用了""和「」两种引号。全文统一使用""引号，不要混用「」引号。")

        # AI味问题指导
        ai_prob = flavor_result.get("ai_probability", 0)
        if ai_prob >= 30:
            stats = flavor_result.get("stats", {})
            parts.append(f"\n### AI特征明显（AI概率{ai_prob}%）")
            if stats.get("ttr", 0) > 0 and stats.get("ttr", 0) < 0.5:
                parts.append(f"- 词汇多样性过低(TTR={stats.get('ttr', 0):.2f})：多用不同的词，减少重复用词")
            if stats.get("para_cv", 0) > 0 and stats.get("para_cv", 0) < 0.3:
                parts.append(f"- 段落长度过于均匀(CV={stats.get('para_cv', 0):.2f})：段落必须长短不一，有的一句话成段，有的五六句")
            if stats.get("connector_density", 0) > 5:
                parts.append(f"- 连接词过多(密度{stats.get('connector_density', 0):.1f}/千字)：删除'然而''因此''于是'等连接词")

        parts.append("\n请基于以上问题重新写作本章正文，确保这次的质量达标。")

        return "\n".join(parts)

    def _character_act(self, char: CharacterAgent) -> str:
        """单个角色根据目标行动"""
        recent = self._backend_world.recent_events(n=3)
        if recent == "（尚无世界事件）":
            recent = "（故事刚开始，请根据角色设定自由行动）"
        prompt = f"""当前是第{self._backend_world.current_chapter}章。

你的目标及权重：
{char.goals_with_weights_text()}

最近发生的事（请在此基础上推进，不要重复）：
{recent}

请决定你现在要做什么。优先推进权重最高的目标。从你的视角出发，描述你的行动（80-150字，小说叙事风格）。
要求：
1. 必须有具体的动作或对话，不要只写心理活动
2. 要推动你的目标进展，不要原地踏步
3. 如果与其他角色在同一地点，可以产生互动
输出格式：「（角色心理）行动描写」
"""
        response = chat(
            system_prompt=build_layered_character_prompt(
                char,
                self._backend_world.config.to_prompt_text(),
                self._backend_world.recent_events(),
            ),
            user_prompt=prompt,
            temperature=0.9,
        )
        return response.strip()


    def _compute_chapter_progress_ratio(self) -> float:
        if self.config.total_chapters <= 0:
            return 0.0
        return min(len(self.chapters) / self.config.total_chapters, 1.0)


    def _extract_character_relations(self, char) -> dict:
        """提取角色关系为简单字典"""
        try:
            if hasattr(char, "relationship_text"):
                text = char.relationship_text()
                rels = {}
                for line in text.split("\n"):
                    if "：" in line:
                        target, rel = line.split("：", 1)
                        rels[target.strip()] = rel.strip()
                return rels
        except Exception:
            pass
        return {}
