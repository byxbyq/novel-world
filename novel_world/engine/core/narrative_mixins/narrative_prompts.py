"""
叙事提示构建 Mixin - prompt 生成方法
"""

logger = __import__('logging').getLogger(__name__)


class NarrativePromptsMixin:
    """提示构建 - 包含叙事 prompt 组装和主题规则格式化"""
    def _build_prompts(self, world, alive_chars, ai_config):
        theme = self.theme
        world_desc = ai_config.get("world_desc", "")
        world_rules = ai_config.get("world_rules", "")

        # === 使用_merged_rules和_game_config ===
        if self._merged_rules:
            perms = self._merged_rules.get("permissions", {})
            iron_rules = self._merged_rules.get("iron_rules", [])
            forbidden_words = self._merged_rules.get("forbidden_words", [])
            
            # 构建权限说明
            perm_text = []
            if perms.get("allow_magic"):
                perm_text.append("允许使用魔法/玄幻/超自然")
            else:
                perm_text.append("禁止使用魔法/玄幻/超自然")
            if perms.get("allow_combat"):
                perm_text.append("允许战斗和杀戮")
            else:
                perm_text.append("禁止战斗和杀戮，通过对话/智谋解决")
            if perms.get("allow_modern_items"):
                perm_text.append("允许现代物品（手机、电脑等）")
            else:
                perm_text.append("禁止现代物品（手机、电脑等）")
            
            if perm_text:
                world_rules += "\n=== 权限设定 ===\n" + "\n".join(perm_text) + "\n"
            
            if iron_rules:
                world_rules += "\n=== 铁律规则 ===\n"
                for i, rule in enumerate(iron_rules, 1):
                    world_rules += f"{i}. {rule}\n"
            
            if forbidden_words:
                world_rules += f"\n=== 禁止词汇 ===\n这些词不能出现：{'、'.join(forbidden_words)}\n"


        # Build ability constraints for system prompt
        ability_rules = ""
        immortality_keywords = ["\u4e0d\u6b7b", "\u4e0d\u706d", "\u6c38\u751f", "\u91cd\u751f", "\u590d\u6d3b", "\u4e0d\u6b7b\u4e4b\u8eab"]
        for c in alive_chars:
            if c.skills:
                skills_str = "\u3001".join(c.skills)
                is_immortal = any(w in s for w in immortality_keywords for s in c.skills)
                if is_immortal:
                    ability_rules += f"\n  - {c.name} \u62e5\u6709\u4e0d\u6b7b\u80fd\u529b\uff08{skills_str}\uff09\uff0c\u4e0d\u80fd\u88ab\u6740\u6b7b\uff0c\u4f46\u53ef\u4ee5\u53d7\u4f24\u6216\u9762\u4e34\u5371\u9669\u2014\u2014\u53d9\u4e8b\u4e2d\u8981\u5c55\u73b0\u8fd9\u79cd\u4e0d\u6b7b\u7684\u7279\u8d28"

        # === 添加剧情节点信息 ===
        plot_node_info = ""
        if self._plot_node_manager:
            current_node = self._plot_node_manager.get_current_node()
            if current_node:
                plot_node_info = f"\\n=== 当前剧情节点 ===\\n节点：{current_node.name}\\n描述：{current_node.description}\\n必需元素：{', '.join(current_node.required_elements)}\\n"
        

        system = (
            f"\u4f60\u662f\u4e00\u4e2a{theme}\u4e3b\u9898\u7684\u53d9\u4e8b\u8005\u3002"
            f"\u4f60\u7684\u4efb\u52a1\u662f\u6839\u636e\u5f53\u524d\u4e16\u754c\u72b6\u6001\uff0c\u63a8\u8fdb\u4e00\u6bb5\u5267\u60c5\u3002\n"
            f"\n=== \u4e16\u754c\u89c2\u8bbe\u5b9a\uff08\u5fc5\u987b\u4e25\u683c\u9075\u5b88\uff09===\n{world_desc}\n"
        )
        if world_rules:
            system += f"\n=== \u4e16\u754c\u89c4\u5219 ===\n{world_rules}\n"
        if ability_rules:
            system += f"\n=== \u89d2\u8272\u80fd\u529b\u7ea6\u675f\uff08\u4e0d\u53ef\u8fdd\u53cd\uff09==={ability_rules}\n"
        system += (
            f"\n=== \u53d9\u4e8b\u89c4\u5219 ===\n"
            f"1. \u6bcf\u6b21\u53ea\u519960-200\u5b57\u7684\u4e00\u6bb5\u53d9\u8ff0\n"
            f"2. \u8981\u6709\u5177\u4f53\u7684\u4eba\u7269\u3001\u5730\u70b9\u3001\u4e8b\u4ef6\n"
            f"3. \u4fdd\u6301\u4e0e\u524d\u6587\u7684\u8fde\u7eed\u6027\n"
            f"4. \u53ef\u4ee5\u63a8\u8fdb\u591a\u4e2a\u89d2\u8272\u7684\u547d\u8fd0\u7ebf\n"
            f"5. \u9002\u5f53\u5236\u9020\u51b2\u7a81\u3001\u60ac\u5ff5\u3001\u8f6c\u6298\n"
            f"6. \u4e0d\u8981\u5199\u6218\u6597\u6570\u503c\uff0c\u5199\u8fc7\u7a0b\u548c\u7ed3\u679c\n"
            f"7. \u76f4\u63a5\u8f93\u51fa\u53d9\u8ff0\u6587\u672c\uff0c\u4e0d\u8981\u524d\u7f00\u6216\u6807\u7b7e\n"
            f"8. \u4e0d\u8981\u8f93\u51fa\u601d\u8003\u8fc7\u7a0b"
            f"9. \u53d9\u4e8b\u4ee5\u4e3b\u89d2\u89c6\u89d2\u5c55\u5f00\uff0c\u4e0d\u5207\u6362\u89c6\u89d2"
        )

        char_lines = []
        import time as _t
        # Always include protagonist and antagonist first
        priority_chars = []
        other_chars = []
        for c in alive_chars:
            if c.char_type in (CharType.PROTAGONIST, CharType.ANTAGONIST):
                priority_chars.append(c)
            else:
                other_chars.append(c)
        # Fill remaining slots from NPCs (up to 3 more)
        npcs_to_show = min(3, len(other_chars))
        if npcs_to_show > 0:
            idx = int(_t.time() * 7) % max(len(other_chars) - npcs_to_show, 1)
            priority_chars.extend(other_chars[idx:idx + npcs_to_show])
        for c in priority_chars:
            line = f"- {c.char_type.value}{c.name}\uff1a{c.personality}"
            if c.goal:
                line += f"\uff0c\u76ee\u6807\uff1a{c.goal}"
            if c.fate_arc:
                line += f"\uff0c\u547d\u8fd0\u7ebf\uff1a{c.fate_arc}"
            if c.skills:
                line += f"\uff0c\u80fd\u529b\uff1a{', '.join(c.skills)}"

            if c.key_memories:
                line += f"\uff0c\u8fd1\u671f\uff1a{c.key_memories[-1]}"
            char_lines.append(line)

        faction_lines = []
        for fid, faction in world.factions.items():
            members = [c for c in alive_chars if c.faction_id == fid]
            leader = ""
            for c in members:
                if c.char_type in (CharType.PROTAGONIST, CharType.ANTAGONIST):
                    leader = f"\uff0c\u6838\u5fc3\uff1a{c.name}"
                    break
            faction_lines.append(f"{faction.name}({len(members)}\u4eba{leader})")
        faction_text = "\u3001".join(faction_lines) if faction_lines else "\u65e0"

        # === 使用场景参数库生成场景细节 ===
        scene_info = ""
        if self._scene_params:
            # 从world中提取当前场景
            current_scene = None
            if hasattr(world, 'get_tile') and alive_chars:
                try:
                    tile = world.get_tile(*alive_chars[0].pos)
                    if tile and hasattr(tile, 'name'):
                        current_scene = tile.name
                except:
                    pass
            
            if current_scene and self._scene_params.is_scene_valid(current_scene):
                # 获取随机场景细节
                detail_result = self._scene_params.get_random_detail(current_scene)
                if detail_result:
                    area, actions = detail_result
                    action = self._scene_params.get_random_action(current_scene, area)
                    scene_info = f"\\n=== 当前场景细节 ===\\n场景：{current_scene}\\n区域：{area}\\n可执行动作：{action if action else '观察周围'}\\n"
        

        user = (
            f"\u3010\u4e16\u754c\u89c2\u3011{world_desc}\n"
            f"\u3010\u65f6\u95f4\u3011\u7b2c{world.current_time}\u56de\u5408\n\n"
            f"\u3010\u89d2\u8272\u72b6\u6001\u3011\n" + "\n".join(char_lines) +
            f"\n\n\u3010\u52bf\u529b\u683c\u5c40\u3011\n{faction_text}\n"
        )

        memory_ctx = self._build_memory_context(world, 0)
        if memory_ctx:
            user += "\n" + memory_ctx + "\n"
        if self._story_context:
            user += f"\n\u3010\u6700\u8fd1\u53d1\u751f\u7684\u4e8b\u3011\n{self._story_context}\n"
        
        # === 添加增强记忆上下文（事件历史、角色关系、避免重复） ===
        if _HAS_MEMORY_SYSTEMS:
            enhanced_context = self._build_enhanced_memory_context(world, world.current_time)
            if enhanced_context:
                user += "\n" + enhanced_context + "\n"

        # === 添加事件池上下文 ===
        if _HAS_EVENT_POOL:
            try:
                event_pool = get_event_pool()
                # 获取已发生的事件ID用于排除
                exclude_ids = set()
                if hasattr(self, ) and self._world_ref:
                    if hasattr(self._world_ref, ):
                        exclude_ids = set(str(e.get('id', e.get('$id', ''))) for e in self._world_ref.event_log if isinstance(e, dict))
                # 获取事件上下文，传递 exclude_ids 避免重复
                event_context = event_pool.get_event_context_by_situation({
                    "theme": self.theme,
                    "exclude_ids": exclude_ids
                }, count=15)
                if event_context:
                    user += event_context + "\n"
            except Exception:
                pass
        
        # === 添加主线剧情信息（关键！） ===
        if self._plot:
            plot_text = "\n【主线剧情】（请按照以下设定推进剧情）\n"
            if self._plot.get("start_event"):
                plot_text += f"起点事件：{self._plot['start_event']}\n"
            if self._plot.get("core_suspense"):
                plot_text += f"核心悬念：{self._plot['core_suspense']}\n"
            if self._plot.get("expected_ending"):
                plot_text += f"预期结局：{self._plot['expected_ending']}\n"
            subplots = self._plot.get("subplots", [])
            if subplots:
                plot_text += "支线剧情：\n"
                for i, sp in enumerate(subplots, 1):
                    trigger = sp.get("trigger_condition", "")[:50]
                    plot_text += f"  支线{i}：{trigger}...\n"
            user += plot_text
        
        user += "\n请推进剧情："
        return system, user
    def _get_theme_rules(self):
        """格式化合并规则为AI prompt片段"""
        rules = self._merged_rules
        if not rules:
            try:
                from .themes.theme_rules import THEME_RULES
                rules = THEME_RULES.get(self.theme, {})
            except ImportError:
                return ""
        if not rules:
            return ""

        parts = []
        # 权限说明
        perms = rules.get("permissions", {})
        perm_lines = []
        if perms.get("allow_magic"):
            perm_lines.append("允许使用魔法/法术/超自然力量")
        else:
            perm_lines.append("禁止使用魔法/法术/超自然力量")
        if perms.get("allow_combat"):
            perm_lines.append("允许战斗、我杀")
        else:
            perm_lines.append("禁止战斗、杀人，冲突通过对话/法律解决")
        if perms.get("allow_modern_items"):
            perm_lines.append("允许现代物品（手机、汽车、网络等）")
        else:
            perm_lines.append("禁止现代物品（手机、汽车、网络等）")
        parts.append("\n=== 权限说明 ===")
        parts.extend(perm_lines)

        # 禁止内容
        forbidden = rules.get("forbidden_words", [])
        if forbidden:
            parts.append("\n=== 禁止内容 ===")
            parts.append("绝对不能出现：" + "、".join(forbidden))

        # 核心规则
        iron = rules.get("iron_rules", [])
        if iron:
            parts.append("\n=== 核心规则 ===")
            for i, r in enumerate(iron, 1):
                parts.append(f"{i}. {r}")

        # 力量体系
        power = rules.get("power_system", "")
        if power:
            parts.append("\n=== 力量体系 ===")
            parts.append(power)

        # 叙事风格
        narr = rules.get("narrative_style", "")
        if narr:
            parts.append("\n=== 叙事风格 ===")
            parts.append(narr)

        # 允许场景
        scenes = rules.get("allowed_scenes", [])
        if scenes:
            parts.append("\n=== 允许场景 ===")
            parts.append("、".join(scenes))

        # 行为限制
        behavior = rules.get("behavior_limits", [])
        if behavior:
            parts.append("\n=== 角色行为限制 ===")
            for i, b in enumerate(behavior, 1):
                parts.append(f"{i}. {b}")

        # 势力规则
        faction = rules.get("faction_rules", [])
        if faction:
            parts.append("\n=== 势力规则 ===")
            for i, f in enumerate(faction, 1):
                parts.append(f"{i}. {f}")

        # 强制检查提示
        novel_req = (
            "\n=== 叙事要求 ===\n"
            "- 生成的文字记录本身即具备小说属性，无需后续修改\n"
            "- 必须包含场景描写、角色动作/对话/心理，绝不能只写事件概括\n"
            "- 与前文自然衍接，段落间有过渡，不能突兀跳转\n"
            "- 角色行为必须符合其性格和目标，不能人设崩塌\n"
            "- 严格遵循主角单一视角：叙事以主角视角展开，配角私下行为/心理只能通过主角视角呈现\n"
            "- 禁止生成重复的角色经历、场景、动作，每段情节必须推进\n"
            "- 请自动检查是否违反以上规则，违规视为无效；确保内容本身即具备小说属性"
        )
        parts.append(novel_req)

        return "\n".join(parts) + "\n"

