"""Engine 仿真 Mixin — Tick推进/角色移动/对话/状态更新"""
import logging

from ..world import TileType
from ..character import CharState

logger = logging.getLogger(__name__)

class SimulationMixin:
    """tick / character movement / dialogues / state updates"""


    def tick(self):
        """一次推演"""
        self.world.current_time += 1
        self.world.tick_count += 1

        # 1. 角色移动（目标导向 + 随机）
        self._move_characters()

        # 2. 叙事生成
        alive = [c for c in self.world.characters if c.alive]
        
        # 如果故事开头还没生成，等待模型加载并生成故事开头
        if not self._story_intro_generated:
            if self.ai and hasattr(self.ai, 'is_model_loading') and self.ai.is_model_loading:
                self.world.story_log.append("【系统】等待 AI 模型加载...")
                import time
                while self.ai.is_model_loading:
                    time.sleep(0.1)
                self.world.story_log.append("【系统】AI 模型加载完成！")
            
            # 模型加载完成，生成故事开头
            intro = self._generate_story_intro()
            if intro:
                self.world.story_log.append(intro)
                self.world.story_log.append("【系统】故事开始，AI 叙事已启用。")
            self._story_intro_generated = True
            narrative = None  # 第一次 tick 不生成叙事
        else:
            # 故事开头已生成，开始正式叙事
            narrative = None
            if self.ai and self.ai.is_available and hasattr(self.ai, 'is_model_ready') and self.ai.is_model_ready:
                if not self._ai_busy:
                    try:
                        narrative = self.narrative_engine.generate_tick_narrative(
                            self.world, alive, self.ai_config  # 只使用活着的角色
                        )
                        if narrative:
                            if hasattr(self.narrative_engine, '_clean_output'):
                                narrative = self.narrative_engine._clean_output(narrative)
                            self.narrative_engine._update_context(narrative)
                    except Exception as e:
                        logging.warning(f"AI narrative error: {e}")
        if not narrative:
            narrative = self.narrative_engine._template_fallback(self.world, alive)
            self.narrative_engine._update_context(narrative)
            # 通知事件触发管理器
            if hasattr(self.narrative_engine, 'on_narrative_generated'):
                self.narrative_engine.on_narrative_generated(narrative)

        # 3. 角色对话处理
        dialogue_narrative = self._process_character_dialogues(alive)
        if dialogue_narrative:
            narrative = dialogue_narrative if not narrative else narrative + "\n" + dialogue_narrative

        # 4. 轻量解析叙事中的状态变化
        self._update_states_from_narrative(narrative)

        # 4. 更新势力领地
        if self.world.tick_count % 10 == 0:
            self._update_faction_territory()

        # 5. 势力目标驱动（phase2_p1）
        self._process_faction_goals()

        # 6. 记录
        self.world.story_log.append(narrative)

        # === 定期压缩摘要（每50个tick）===
        if self.world.tick_count % 50 == 0 and self.world.tick_count > 0:
            try:
                summary = self.narrative_engine.compress_history_summary(self.world)
                if summary:
                    self.world.story_log.append(f"【历史摘要】{summary}")
            except Exception as e:
                logging.warning(f"History compression error: {e}")

        # === 自动存档（每50个tick）===
        if self.world.tick_count % 50 == 0:
            try:
                from .storage import GameStorage
                storage = GameStorage()
                storage.auto_save(world=self.world)  # 循环使用5个自动存档位
            except Exception as e:
                logging.warning(f"Auto save error: {e}")  # 不再静默吞掉

        protagonist_dead = self.protagonist and not self.protagonist.alive

        return {
            "narrative": narrative,
            "logs": [{"text": narrative, "type": "叙事"}],
            "tick": self.world.tick_count,
            "paused": protagonist_dead,
            "protagonist_dead": protagonist_dead,
        }

    
    def _process_character_dialogues(self, alive: list) -> str:
        """
        处理角色之间的对话
        
        Args:
            alive: 存活的角色列表
        
        Returns:
            对话叙事文本
        """
        if not alive or len(alive) < 2:
            return ""
        
        dialogue_narratives = []
        
        # 遍历角色对
        for i, char1 in enumerate(alive):
            for char2 in alive[i+1:]:
                # 检查是否应该触发对话
                should_trigger, trigger_type, probability = self.dialogue_system.should_trigger_dialogue(
                    char1, char2, tick=self.world.tick_count
                )
                
                if should_trigger:
                    # 确定对话类型
                    dialogue_type = self.dialogue_system.determine_dialogue_type(
                        char1, char2, trigger_type
                    )
                    
                    # 生成对话
                    world_context = f"主题：{self.theme}，第{self.world.tick_count}回合"
                    dialogue = self.dialogue_system.generate_dialogue(
                        char1, char2, dialogue_type, world_context, self.world.tick_count, trigger_type
                    )
                    
                    # 应用对话效果
                    self.dialogue_system.apply_dialogue_effects(dialogue, char1, char2)
                    
                    # 添加到叙事
                    dialogue_narratives.append(f"【{dialogue.speaker1}与{dialogue.speaker2}】{dialogue.content}")
        
        return "\n".join(dialogue_narratives) if dialogue_narratives else ""

        return "\n".join(dialogue_narratives) if dialogue_narratives else ""

    def _ai_narrative_worker(self, world, characters):
        """后台AI叙事生成（不阻塞主线程）"""
        try:
            narrative = self.narrative_engine.generate_tick_narrative(
                self.world, alive, self.ai_config  # 只使用活着的角色
            )
            if narrative and self.world.story_log:
                self.world.story_log[-1] = narrative
        except Exception as e:
            logging.warning(f"AI narrative worker error: {e}")
        finally:
            self._ai_busy = False


    def _move_characters(self):
        """角色移动：优先目标导向（向资源所在地移动），否则随机移动"""
        alive = [c for c in self.world.characters if c.alive]
        for c in alive:
            if random.random() < 0.20:  # 20% 概率移动
                # 目标导向移动（优先级高）
                if self._resolve_goal_to_location(c):
                    continue

                # 否则随机移动
                dx = random.randint(-1, 1)
                dy = random.randint(-1, 1)
                new_pos = self._clamp_pos((c.pos[0] + dx, c.pos[1] + dy))
                tile = self.world.get_tile(*new_pos)
                if tile and tile.tile_type != TileType.WATER:
                    c.pos = new_pos


    def _extract_resource_keywords(self, goal_text: str) -> list:
        """从目标文本中提取资源关键词。"""
        if not goal_text:
            return []
        kw_map = self.world._RESOURCE_KEYWORD_MAP
        found = []
        for kw in sorted(kw_map.keys(), key=len, reverse=True):
            if kw in goal_text:
                found.append((kw, kw_map[kw]))
        return found


    def _resolve_goal_to_location(self, char) -> bool:
        """解析角色目标中的资源关键词，查询资源所在地，向该方向移动。"""
        goal_text = getattr(char, 'goal', '') or ''
        if not goal_text:
            return False
        resources = self._extract_resource_keywords(goal_text)
        if not resources:
            return False
        res_name, res_type = resources[0]
        target_tile = self.world.get_resource_location(res_name)
        if target_tile is None:
            return False
        dx = 1 if target_tile.x > char.pos[0] else (-1 if target_tile.x < char.pos[0] else 0)
        dy = 1 if target_tile.y > char.pos[1] else (-1 if target_tile.y < char.pos[1] else 0)
        if dx == 0 and dy == 0:
            return False
        new_pos = self._clamp_pos((char.pos[0] + dx, char.pos[1] + dy))
        tile = self.world.get_tile(*new_pos)
        if tile and tile.tile_type != TileType.WATER:
            char.pos = new_pos
            return True
        for alt in [(dx, 0), (0, dy)]:
            if alt == (dx, dy):
                continue
            alt_pos = self._clamp_pos((char.pos[0] + alt[0], char.pos[1] + alt[1]))
            alt_tile = self.world.get_tile(*alt_pos)
            if alt_tile and alt_tile.tile_type != TileType.WATER:
                char.pos = alt_pos
                return True
        return True


    def _random_move_characters(self):
        """角色随机小范围移动（向后兼容）"""
        self._move_characters()


    def _update_states_from_narrative(self, narrative):
        """根据叙述大致更新角色状态（轻量）"""
        import re
        death_keywords = ["死亡", "死了", "衰亡", "气绝", "坠崖", "毙命", "失去生命",
            "魂散", "杀害", "封債", "施命", "尸骨", "尸体", "死尸",
            "枚丽", "死当场", "归天", "残忍", "灭绝", "消失",
            "生机已绝", "生机极竭", "生机已尽", "彻底死亡",
            "灭活", "要命", "性命", "命丧", "血死"]
        death_names = set()
        for kw in death_keywords:
            for c in self.world.characters:
                if c.alive and c.name in narrative:
                    # 更严格的匹配：必须是直接描述角色死亡
                    # 格式1：角色名 + 死亡动词（如：张三死了）
                    if kw in ["死了", "死亡", "陨落", "牺牲", "被杀", "身亡", "倒下", "倒地"]:
                        pattern1 = c.name + r".{0,3}" + kw
                        if re.search(pattern1, narrative):
                            death_names.add(c.name)
                    # 格式2：死亡动词 + 角色名（如：杀死张三）
                    if kw in ["杀死", "击杀", "害死", "弄死"]:
                        pattern2 = kw + c.name
                        if re.search(pattern2, narrative):
                            death_names.add(c.name)
                    # 格式3：角色名 + 消失/终结等
                    if kw in ["消失", "终结", "消散", "不见"]:
                        pattern3 = c.name + r".{0,5}" + kw
                        if re.search(pattern3, narrative):
                            death_names.add(c.name)
        # Kill characters whose names appear near death keywords
        immortality_words = ["不死", "不灭", "永生", "重生", "复活", "不死之身"]
        for c in self.world.characters:
            if not c.alive:
                continue
            # Check if character has immortality skills
            if any(w in s for s in (c.skills or []) for w in immortality_words):
                continue
            if c.name in death_names:
                c.alive = False
                c.state = CharState.DEAD
                c._death_permanent = True  # 永久死亡，禁止复活
                c.add_key_memory("死亡：" + narrative[:50])
                # 描述式死亡，不用【死亡】标签
                import random
                death_templates = [
                    f"{c.name}的气息骤然消失，只留一声惨叫，再也没有踪迹。",
                    f"{c.name}被黑暗吞噬，连尸骨都未能找回。",
                    f"{c.name}的身影在镜中扭曲，最后一次回头后便再也没有出现。",
                    f"{c.name}在黑暗中的存在缑缓消散，只剩下一件被撕碎的衣物。",
                    f"{c.name}被无形的力量绞杀，身体扭曲成不可能的角度，当场死亡。",
                ]
                self.world.story_log.append(random.choice(death_templates))
            elif c.name in narrative:
                if "战斗" in narrative or "交手" in narrative or "激战" in narrative:
                    c.state = CharState.FIGHTING
                elif "休息" in narrative or "睡" in narrative:
                    c.state = CharState.RESTING
                elif "探索" in narrative or "前往" in narrative or "赶路" in narrative:
                    c.state = CharState.EXPLORING
                elif "生病" in narrative or "受伤" in narrative:
                    c.state = CharState.SICK
                elif "突破" in narrative or "觉醒" in narrative or "进阶" in narrative:
                    c.state = CharState.EVOLVING


    def _update_faction_territory(self):
        """\u66f4\u65b0\u52bf\u529b\u9886\u5730"""
        for faction in self.world.factions.values():
            faction.territory = []
            for c in self.world.characters:
                if c.alive and c.faction_id == faction.id:
                    cx, cy = c.pos
                    for dx in range(-3, 4):
                        for dy in range(-3, 4):
                            nx, ny = cx + dx, cy + dy
                            if (0 <= nx < self.world.map_size[0] and
                                0 <= ny < self.world.map_size[1] and
                                (nx, ny) not in faction.territory):
                                faction.territory.append((nx, ny))


    def _clamp_pos(self, pos):
        x = max(0, min(self.world.map_size[0] - 1, pos[0]))
        y = max(0, min(self.world.map_size[1] - 1, pos[1]))
        return (x, y)
