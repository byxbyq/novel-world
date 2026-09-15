"""
叙事记忆 Mixin - 记忆系统方法
"""
import hashlib
import json
import time

logger = __import__('logging').getLogger(__name__)


class NarrativeMemoryMixin:
    """叙事记忆 - 包含上下文管理、记忆压缩、线索提取等方法"""
    def _process_with_memory_systems(self, narrative: str, world, alive_chars, tick: int) -> str:
        """使用新的记忆系统处理叙事"""
        if not narrative or len(narrative) < 10:
            return narrative
        
        if not _HAS_MEMORY_SYSTEMS:
            return narrative
        
        # 更新当前 tick
        self._current_tick = tick
        
        # 获取角色名列表
        char_names = [c.name for c in alive_chars if hasattr(c, 'name')]
        
        # 1. 检查叙事去重
        is_dup, sim, similar_narrative, template_count = self._narrative_deduplicator.check_duplicate(
            narrative, char_names
        )
        
        if is_dup:
            # 记录重复警告
            import logging
            logging.warning(f"[叙事去重] 相似度 {sim:.2f}, 模板出现 {template_count} 次")
            
            # 【修改】更积极的去重：相似度 > 0.7 或模板出现 >= 2 次，就生成替代叙事
            if sim >= 0.7 or template_count >= 2:
                logging.warning(f"[叙事去重] 触发替代叙事生成 (sim={sim:.2f}, template={template_count})")
                # 使用模板回退生成替代叙事
                alt_narrative = self._template_fallback(world, alive_chars)
                if alt_narrative and alt_narrative != narrative:
                    # 检查替代叙事是否也重复
                    is_dup2, sim2, _, tc2 = self._narrative_deduplicator.check_duplicate(alt_narrative, char_names)
                    # 如果替代叙事重复度更低，使用替代叙事
                    if sim2 < sim:
                        logging.info(f"[叙事去重] 使用替代叙事 (原sim={sim:.2f}, 新sim={sim2:.2f})")
                        narrative = alt_narrative
                    else:
                        logging.warning(f"[叙事去重] 替代叙事也重复 (sim={sim2:.2f})，保留原叙事")
        
        # 2. 检查关系一致性
        consistency_issues = self._relationship_tracker.check_consistency(narrative, char_names)
        if consistency_issues:
            import logging
            for issue in consistency_issues:
                logging.warning(f"[关系一致性] {issue}")
        
        # 3. 记录事件到事件记忆
        self._event_memory.record_event(tick, narrative, char_names)
        
        # 4. 更新关系追踪
        self._relationship_tracker.update_from_narrative(narrative, char_names, tick)
        
        # 5. 添加到去重历史
        self._narrative_deduplicator.add_to_history(narrative, char_names)
        
        return narrative
    def _build_enhanced_memory_context(self, world, tick: int) -> str:
        """构建增强的记忆上下文（给 AI 参考）"""
        if not _HAS_MEMORY_SYSTEMS:
            return ""
        
        parts = []
        
        # 1. 事件历史
        event_context = self._event_memory.get_context_for_ai(max_length=400)
        if event_context:
            parts.append(event_context)
        
        # 2. 角色关系
        char_names = [c.name for c in world.characters if hasattr(c, 'name') and getattr(c, 'alive', True)]
        relation_context = self._relationship_tracker.get_context_for_ai(char_names, max_length=300)
        if relation_context:
            parts.append(relation_context)
        
        # 3. 避免重复的场景
        dedup_stats = self._narrative_deduplicator.get_stats()
        if dedup_stats["total_narratives"] > 0:
            action_dist = dedup_stats.get("action_distribution", {})
            if action_dist:
                top_actions = sorted(action_dist.items(), key=lambda x: x[1], reverse=True)[:3]
                avoid_lines = []
                for action, count in top_actions:
                    if count >= 3:
                        avoid_lines.append(f"- {action}场景（已出现{count}次）")
                if avoid_lines:
                    avoid_text = "【避免重复】以下场景类型已频繁出现，请勿重复：\n" + "\n".join(avoid_lines)
                    parts.append(avoid_text)
        
        return "\n\n".join(parts) if parts else ""
    def _update_context(self, new_narrative):
        """更新叙事上下文，使用白城主五层记忆系统"""
        if not new_narrative:
            return
        
        if self._use_memory_manager:
            # 使用白城主的记忆系统
            # 1. 添加到短期记忆
            self._memory.add_short_term(
                window_id="game",
                memory_type="narrative",
                content=new_narrative
            )
            # 2. 添加到场景记忆
            self._memory.add_scene_memory(
                scene="game_world",
                content=new_narrative,
                importance=0.5
            )
            # 3. 检查是否包含关键事件，添加到长期记忆
            key_keywords = ["死", "杀", "背叛", "结盟", "宣战", "突破", "获得", "发现", "危机", "转折"]
            for kw in key_keywords:
                if kw in new_narrative:
                    self._memory.add_long_term(
                        key=f"event_{len(self._key_events)}",
                        value=new_narrative,
                        category="game_events"
                    )
                    self._key_events.append(f"【{kw}】{new_narrative[:50]}...")
                    break
        else:
            # 回退到简单记忆系统
            if self._story_context:
                self._story_context += "\n" + new_narrative
            else:
                self._story_context = new_narrative
            
            if len(self._story_context) > self._max_context:
                overflow = len(self._story_context) - self._max_context
                move_length = overflow + 500
                early_part = self._story_context[:move_length]
                summary = self._compress_narrative(early_part)
                if summary and summary not in self._long_term_memory:
                    self._long_term_memory.append(summary)
                    if len(self._long_term_memory) > self._max_long_term:
                        self._long_term_memory = self._long_term_memory[-self._max_long_term:]
                self._story_context = self._story_context[move_length:]
    def _compress_narrative(self, text):
        """压缩叙事为摘要（提取关键句子）"""
        if not text or len(text) < 50:
            return text
        
        # 关键词列表 - 包含这些词的句子更重要
        key_keywords = [
            "死", "杀", "背叛", "结盟", "宣战", "突破", "获得", "得到",
            "发现", "决定", "计划", "成功", "失败", "危机", "转折",
            "离开", "到达", "遇见", "战胜", "击败", "拯救", "牺牲",
            "宝物", "神器", "秘密", "真相", "阴谋", "重要"
        ]
        
        # 按句子分割
        import re
        sentences = re.split(r'[。！？\n]', text)

        sentences = [s.strip() for s in sentences if s.strip()]
        
        # 提取关键句子
        key_sentences = []
        for s in sentences:
            if any(kw in s for kw in key_keywords):
                key_sentences.append(s)
        
        # 如果关键句子太少，补充一些句子
        if len(key_sentences) < 2:
            # 取首尾各一句
            if sentences:
                key_sentences.append(sentences[0])
            if len(sentences) > 1:
                key_sentences.append(sentences[-1])
        
        # 合并为摘要
        if key_sentences:
            return "->".join(key_sentences[:3])  # 最多保留 3 句
        return text[:100]  # 兜底：返回前 100 字符
    def _extract_threads(self, narrative, alive_chars):
        """从叙述中提取未解决的悬念"""
        # 悬念关键词
        thread_keywords = [
            ("寻找", "在找"), ("追踪", "追"), ("调查", "查探"),
            ("等待", "等"), ("计划", "准备"), ("筹划", "图谋"),
            ("秘密", "隐藏"), ("疑惑", "困惑"), ("未知", "降临"),
            ("谋划", "阴谋"), ("危机", "危险信号"), ("警觉", "警惕"),
            ("发现", "发现了"), ("突然", "意外"), ("神秘", "奇怪"),
            ("请求", "帮助"), ("威胁", "威胁"), ("目标", "目标是"),
            ("没有完成", "未成"), ("还没有", "尚未"),
        ]
        new_threads = []
        for char in alive_chars:
            if char.name not in narrative:
                continue
            for kw, hint in thread_keywords:
                if kw in narrative:
                    # 提取角色名后的上下文
                    idx = narrative.find(char.name)
                    snippet = narrative[max(0, idx-5):idx+30]
                    thread_text = f"[{char.name}] {snippet.strip()[:25]}"
                    # 避免重复
                    if not any(char.name in t and kw in t for t in self._unresolved_threads):
                        new_threads.append(thread_text)
                    break  # 每个角色每次只提取一条

        # 如果发现死亡、突破等关键词，尝试清除已解决的悬念
        resolve_keywords = ["完成", "成功", "解开", "找到", "突破", "彻底击败"]
        for kw in resolve_keywords:
            if kw in narrative:
                # 删除相关角色的旧悬念
                for char in alive_chars:
                    if char.name in narrative:
                        self._unresolved_threads = [
                            t for t in self._unresolved_threads
                            if not (char.name in t)
                        ]

        self._unresolved_threads.extend(new_threads)
        if len(self._unresolved_threads) > self._max_threads:
            self._unresolved_threads = self._unresolved_threads[-self._max_threads:]
    def compress_history_summary(self, world):
        """压缩历史摘要，每50 tick 调用一次，生成一段历史总结"""
        if not self._key_events and not self._story_context:
            return None
        
        # 收集最近的关键事件
        recent_events = self._key_events[-10:] if self._key_events else []
        
        # 收集最近的叙事（最后500字）
        recent_narrative = self._story_context[-500:] if self._story_context else ""
        
        # 构建压缩提示
        from novel_world.engine.core.prompt_registry import PromptRegistry
        summary_prompt = PromptRegistry.get(
            "history_summary",
            recent_events=chr(10).join(recent_events) if recent_events else "无",
            recent_narrative=recent_narrative[-300:] if recent_narrative else "无",
        )

        # 尝试用 AI 生成摘要
        if self.ai and self.ai.is_available:
            try:
                summary = self.ai.generate(summary_prompt, max_tokens=100)
                if summary:
                    # 清理输出
                    summary = summary.strip()
                    if len(summary) > 100:
                        summary = summary[:100] + "..."
                    # 更新长期记忆
                    if hasattr(self, '_long_term_memory'):
                        self._long_term_memory.append(summary)
                        if len(self._long_term_memory) > 10:
                            self._long_term_memory = self._long_term_memory[-10:]
                    return summary
            except Exception as e:
                pass
        
        # Fallback: 简单拼接关键事件
        if recent_events:
            summary = "；".join(recent_events[-3:])
            return summary[:100] if len(summary) > 100 else summary
        
        return None
    def update_memory(self, world, tick_count):
        for c in world.characters:
            if c.alive and c.key_memories:
                latest = c.key_memories[-1]
                if not any(c.name in e for e in self._key_events):
                    self._key_events.append(f"[{c.name}] {latest}")
        if len(self._key_events) > self._max_key_events:
            self._key_events = self._key_events[-self._max_key_events:]
        keywords = ["\u6b7b\u4ea1", "\u7a81\u7834", "\u80cc\u53db", "\u7ed3\u76df", "\u5ba3\u6218", "\u8f6c\u6298", "\u5371\u673a"]
        if self._story_context:
            for kw in keywords:
                if kw in self._story_context[-200:]:
                    if not any(kw in e for e in self._key_events):
                        self._key_events.append(kw)
                        if len(self._key_events) > self._max_key_events:
                            self._key_events = self._key_events[-self._max_key_events:]
    def _build_memory_context(self, world, tick_count):
        """构建记忆上下文，使用白城主五层记忆系统"""
        parts = []
        
        if self._use_memory_manager:
            # 使用白城主的记忆系统
            # 1. 从长期记忆获取游戏事件
            game_events = self._memory.get_long_term(category="game_events")
            if game_events:
                items = ["【历史事件】"]
                for key, data in list(game_events.items())[-10:]:
                    items.append(f"- {data.get('value', '')[:50]}...")
                parts.append("\n".join(items))
            
            # 2. 从场景记忆获取
            scene_mem = self._memory.get_scene_memory("game_world")
            if scene_mem:
                items = ["【场景记忆】"]
                for mem in scene_mem[-5:]:
                    items.append(f"- {mem.get('content', '')[:50]}...")
                parts.append("\n".join(items))
            
            # 3. 从短期记忆获取最近叙事
            short_mem = self._memory.get_short_term(window_id="game", memory_type="narrative")
            if short_mem:
                items = ["【最近发生】"]
                for mem in short_mem[-5:]:
                    items.append(f"- {mem.get('content', '')[:50]}...")
                parts.append("\n".join(items))
        else:
            # 回退到简单记忆系统
            if self._long_term_memory:
                items = ["【历史摘要】"]
                items.extend(self._long_term_memory[-5:])
                parts.append("\n".join(items))
        
        # 4. 关键事件（兼容旧代码）
        if self._key_events:
            items = ["【关键事件】"]
            items.extend(self._key_events[-10:])
            parts.append("\n".join(items))
        
        # 5. 角色命运进展
        fate_lines = []
        for c in world.characters:
            if c.alive and c.char_type != CharType.NPC and c.fate_arc:
                memos = ""
                if c.key_memories:
                    memos = "，经历：" + "->".join(c.key_memories[-3:])
                fate_lines.append(f"- {c.char_type.value}{c.name}：{c.fate_arc}{memos}")
        if fate_lines:
            parts.append("【角色命运】")
            parts.append("\n".join(fate_lines))
        
        return "\n".join(parts) if parts else ""

