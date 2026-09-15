"""Engine 规则 Mixin — 规则更新/叙事过滤/过渡事件生成"""
import os
import logging

logger = logging.getLogger(__name__)

class RulesMixin:
    """update_rules / _filter_narrative_by_rules / _generate_transition_event"""

    # 新方法 - 添加到 engine.py

    def update_rules(self, new_rules: dict):
        """动态更新游戏规则 - 运行时调整"""
        if not new_rules:
            return

        # 更新 narrative_engine 的规则
        if hasattr(self, 'narrative_engine') and self.narrative_engine:
            self.narrative_engine.set_merged_rules(new_rules)

        # 更新 ai_config 中的规则
        if hasattr(self, 'ai_config'):
            rules_text = self._rules_to_text(new_rules)
            self.ai_config["world_rules"] = rules_text

        # 记录规则更新
        self.world.story_log.append("【系统】规则已更新，将在后续生成中生效。")


    def _rules_to_text(self, rules: dict) -> str:
        """将规则字典转换为文本"""
        parts = []
        perms = rules.get("permissions", {})
        if perms.get("allow_magic"):
            parts.append("允许使用魔法/超能力")
        else:
            parts.append("禁止使用魔法/超能力")
        if perms.get("allow_combat"):
            parts.append("允许战斗和杀戮")
        else:
            parts.append("禁止战斗和杀戮")

        iron = rules.get("iron_rules", [])
        if iron:
            parts.append("铁律：" + "；".join(iron))

        forbidden = rules.get("forbidden_words", [])
        if forbidden:
            parts.append("禁止词汇：" + "、".join(forbidden))

        return "\n".join(parts)


    def _filter_narrative_by_rules(self, narrative: str) -> str:
        """
        按规则过滤叙事内容
        确保事件围绕主角目标展开，过滤无关联事件
        """
        try:
            from game.backend.events import filter_narrative_by_protagonist_goal

            # 获取当前规则
            world_rules = None
            if hasattr(self, 'narrative_engine') and self.narrative_engine:
                world_rules = getattr(self.narrative_engine, '_merged_rules', None)

            # 调用过滤函数
            filtered, is_valid, impact_type, message = filter_narrative_by_protagonist_goal(
                narrative, self.protagonist, world_rules
            )

            # 如果被过滤，记录日志
            if not is_valid:
                self.world.story_log.append(f"【系统过滤】{message}")
                # 返回一个过渡事件作为替代
                return self._generate_transition_event()

            return filtered

        except Exception as e:
            # 如果校验出错，返回原内容
            import logging
            logging.warning(f"Narrative filter error: {e}")
            return narrative


    def _generate_transition_event(self) -> str:
        """生成过渡事件作为被过滤事件的替代"""
        import random

        if self.protagonist:
            name = self.protagonist.name
            transitions = [
                f"{name}继续前行，思考着接下来的计划。",
                f"{name}观察着周围的环境，寻找前进的方向。",
                f"时间悄然流逝，{name}依然在为心中的目标努力。",
                f"{name}稍作休息，整理着思绪。",
                f"前路漫漫，{name}坚定地迈出下一步。",
            ]
            return random.choice(transitions)

        return "时间悄然流逝，故事继续。"

    def _apply_rule_validation(self, narrative: str) -> str:
        """
        应用强制修正系统，确保生成内容符合所有规则
        """
        # 首先使用强制修正系统
        if hasattr(self, 'narrative_corrector'):
            try:
                # 构建上下文
                context = {
                    "protagonist_name": self.protagonist.name if self.protagonist else "",
                    "theme": self.theme,
                }
                
                # 执行强制修正
                result = self.narrative_corrector.correct_narrative(narrative, context)
                
                # 记录违规
                if result.violations:
                    for v in result.violations:
                        self.world.story_log.append(f"【强制修正】{v}")
                
                # 记录修正
                if result.corrections:
                    for c in result.corrections:
                        self.world.story_log.append(f"【修正】{c}")
                
                # 返回修正后的内容
                return result.corrected
                
            except Exception as e:
                import logging
                logging.warning(f"Narrative corrector error: {e}")
        
        # 回退到原来的校验器
        if hasattr(self, 'rule_validator'):
            try:
                world_rules = None
                if hasattr(self, 'narrative_engine') and self.narrative_engine:
                    world_rules = getattr(self.narrative_engine, '_merged_rules', None)
                
                result = self.rule_validator.validate_narrative(narrative, world_rules)
                
                if result["violations"]:
                    for v in result["violations"]:
                        self.world.story_log.append(f"【系统校验】{v}")
                
                if result["should_filter"]:
                    return self.rule_validator.generate_transition_event()
                
                return narrative
                
            except Exception as e:
                import logging
                logging.warning(f"Rule validation error: {e}")
                return narrative
        
        return narrative

    
    def process_item_event(self, item_id: str, character_id: str, action: str = "use") -> dict:
        """
        处理道具事件
        action: "use" | "acquire" | "equip" | "drop"
        """
        result = {
            "success": False,
            "message": "",
            "item_id": item_id,
            "character_id": character_id,
            "action": action
        }
        
        # 获取道具定义
        item = self.item_manager.get_item(item_id)
        if not item:
            result["message"] = f"道具 {item_id} 不存在"
            return result
        
        # 获取角色
        character = None
        for c in self.world.characters:
            if c.id == character_id or c.name == character_id:
                character = c
                break
        
        if not character:
            result["message"] = f"角色 {character_id} 不存在"
            return result
        
        if action == "use":
            # 使用道具
            if not character.has_item(item_id):
                result["message"] = f"{character.name} 没有 {item.name}"
                return result
            
            # 构建校验上下文
            context = {
                "hp": character.attrs.get("体力", 50),
                "mp": character.attrs.get("智力", 50),
                "stamina": 100,
                "gold": character.attrs.get("财富", 0),
                "in_combat": character.state.value == "战斗中",
                "level": 1,
                "skills": character.skills or [],
            }
            
            # 校验道具使用
            validation = self.item_validator.validate_item_use(item, context)
            
            if not validation["can_use"]:
                result["message"] = validation["reason"]
                return result
            
            # 应用代价
            if item.cost.consume_self:
                character.remove_item(item_id)
            
            # 应用效果
            if item.effect.hp_restore > 0:
                character.modify_attr("体力", item.effect.hp_restore)
            if item.effect.mp_restore > 0:
                character.modify_attr("智力", item.effect.mp_restore)
            
            # 添加buff
            if item.effect.buff_attack > 0:
                character.add_buff("attack", item.effect.buff_attack, item.effect.buff_duration)
            if item.effect.buff_defense > 0:
                character.add_buff("defense", item.effect.buff_defense, item.effect.buff_duration)
            
            result["success"] = True
            result["message"] = f"{character.name} 使用了 {item.name}"
            
            # 记录到故事日志
            self.world.story_log.append(f"{character.name}使用了{item.name}。{item.get_use_description()}")
            
        elif action == "acquire":
            # 获取道具
            character.add_item(item_id)
            result["success"] = True
            result["message"] = f"{character.name} 获得了 {item.name}"
            self.world.story_log.append(f"{character.name}获得了{item.name}。")
            
        elif action == "equip":
            # 装备道具
            if character.equip_item(item_id):
                result["success"] = True
                result["message"] = f"{character.name} 装备了 {item.name}"
                self.world.story_log.append(f"{character.name}装备了{item.name}。")
            else:
                result["message"] = f"无法装备 {item.name}"
        
        return result
    
    def give_starting_items(self, character, theme: str = "日常"):
        """给角色发放初始道具"""
        # 根据主题发放不同的初始道具
        starting_items = {
            "日常": ["health_potion"],
            "修仙": ["health_potion", "mana_potion"],
            "奇幻": ["health_potion", "mana_potion"],
            "末世": ["health_potion", "bomb"],
            "科幻": ["health_potion", "stamina_potion"],
            "恐怖": ["health_potion", "smoke_bomb"],
        }
        
        items = starting_items.get(theme, ["health_potion"])
        for item_id in items:
            character.add_item(item_id)
        
        return items

    
    def get_correction_report(self) -> str:
        """获取强制修正报告"""
        if hasattr(self, 'narrative_corrector'):
            return self.narrative_corrector.get_correction_report()
        return "无修正记录"
    
    def get_violation_summary(self) -> dict:
        """获取违规统计"""
        if hasattr(self, 'narrative_corrector'):
            return self.narrative_corrector.get_violation_summary()
        return {}

    # ── 势力目标驱动（phase2_p1）──

    def _process_faction_goals(self):
        """处理势力集体目标，影响成员行为。

        遍历所有势力的目标，将势力级目标转化为成员行为引导：
        - 势力目标关键词 → 成员行动倾向
        - 敌对势力 → 成员移动方向偏向远离/靠近敌方领地
        - 同盟势力 → 成员更容易协调行动
        """
        if not self.world.factions:
            return

        for faction in self.world.factions.values():
            if not faction.goals:
                continue

            members = self.world.get_faction_members(faction.id)
            if not members:
                continue

            for goal in faction.goals:
                goal_text = goal.description if hasattr(goal, "description") else str(goal)

                for member in members:
                    # 势力目标作为角色行为的高权重引导
                    self._align_character_to_faction(member, faction, goal_text)

    def _align_character_to_faction(self, character, faction, goal_text: str):
        """将势力目标对齐到角色行为

        根据势力目标内容，调整角色的行为倾向：
        - 夺取类目标 → 角色倾向向目标方向移动
        - 防御类目标 → 角色倾向在领地周围巡逻
        - 敌对势力 → 移至角色短期目标中
        """
        # 敌对势力处理：if faction has enemies, members may move toward enemy territory
        if faction.enemies:
            for enemy_name in faction.enemies:
                enemy_faction = self.world.get_faction_by_name(enemy_name)
                if enemy_faction and enemy_faction.territory:
                    # 将敌对信息注入角色目标
                    if not hasattr(character, '_faction_enemies_targeted'):
                        character._faction_enemies_targeted = set()
                    if enemy_name not in getattr(character, '_faction_enemies_targeted', set()):
                        character._faction_enemies_targeted = getattr(character, '_faction_enemies_targeted', set())
                        character._faction_enemies_targeted.add(enemy_name)

        # 同盟势力处理：allies may boost cooperation
        if faction.allies:
            for ally_name in faction.allies:
                ally_faction = self.world.get_faction_by_name(ally_name)
                if ally_faction:
                    # 记录同盟信息
                    pass  # 后续可在叙事层体现

        # 进度更新：目标随 tick 缓慢推进（仅在均匀间隔推进）
        if self.world.tick_count % 5 == 0:
            for goal in faction.goals:
                if hasattr(goal, "progress") and goal.progress < 1.0:
                    # 势力大小影响推进速度
                    member_count = faction.member_count()
                    advance_rate = 0.005 * max(1, member_count)  # 每5 tick 0.5% 起步
                    goal.progress = min(1.0, goal.progress + advance_rate)

    def get_faction_summary(self) -> list:
        """获取所有势力摘要（供 API 使用）"""
        result = []
        for faction in self.world.factions.values():
            result.append({
                "id": faction.id,
                "name": faction.name,
                "color": faction.color,
                "member_count": faction.member_count(),
                "territory": faction.territory,
                "enemies": faction.enemies,
                "allies": faction.allies,
                "controlled_resources": faction.controlled_resources,
                "description": faction.description,
                "goals": [
                    {"description": g.description, "progress": g.progress, "weight": g.weight}
                    if hasattr(g, "description") else str(g)
                    for g in faction.goals
                ],
                "resources": faction.resources,
            })
        return result

    def update_faction(self, faction_id: str, data: dict):
        """更新势力数据（供 API 使用）"""
        faction = self.world.factions.get(faction_id)
        if not faction:
            return False

        if "name" in data:
            faction.name = data["name"]
        if "description" in data:
            faction.description = data["description"]
        if "color" in data:
            faction.color = data["color"]
        if "enemies" in data:
            faction.enemies = list(data["enemies"])
        if "allies" in data:
            faction.allies = list(data["allies"])
        if "controlled_resources" in data:
            faction.controlled_resources = list(data["controlled_resources"])
        if "goals" in data:
            faction.goals = []
            for gd in data["goals"]:
                if isinstance(gd, dict):
                    faction.goals.append(FactionGoal(
                        description=gd.get("description", ""),
                        progress=gd.get("progress", 0.0),
                        weight=gd.get("weight", 1.0),
                    ))
        return True
