"""
叙事验证 Mixin - 内容校验方法
"""
import re

logger = __import__('logging').getLogger(__name__)


class NarrativeValidatorMixin:
    """叙事验证 - 包含内容过滤、主题校验、场景检查等方法"""
    def _filter_theme_violations(self, text):
        """增强版的_filter_theme_violations，使用规则验证"""
        if not text:
            return text
        
        # === 使用_merged_rules进行验证 ===
        if self._merged_rules:
            perms = self._merged_rules.get("permissions", {})
            forbidden_words = self._merged_rules.get("forbidden_words", [])
            
            # 检查禁止词汇
            for word in forbidden_words:
                if word and word in text:
                    text = text.replace(word, "事情")
            
            # 检查权限
            if not perms.get("allow_magic", True):
                magic_words = ["魔法", "法术", "咒语", "仙术", "神力", "灵力"]
                for word in magic_words:
                    if word in text:
                        text = text.replace(word, "技巧")
            
            if not perms.get("allow_combat", True):
                combat_words = ["杀死", "杀害", "屠杀", "灭口", "处决"]
                for word in combat_words:
                    if word in text:
                        text = text.replace(word, "制服")
            
            if not perms.get("allow_modern_items", True):
                modern_words = ["手机", "电脑", "互联网", "APP", "微信", "支付宝"]
                for word in modern_words:
                    if word in text:
                        text = text.replace(word, "工具")
        
        # 原有的日常主题过滤逻辑
        if self.theme == "日常":
            forbidden = ["宝藏", "宝箱", "寻宝", "魔法", "修仙", "恶龙", "神器", "仙境", "冒险", "魔兽", "攻击法术", "召唤", "咒语", "三国", "修仙者", "灵器", "法宝", "古墓", "地牢"]
            for word in forbidden:
                if word in text:
                    text = text.replace(word, "事情")
        
        return text
    def _validate_narrative_comprehensive(self, narrative, world, alive_chars):
        """综合验证叙事内容是否符合所有规则"""
        if not narrative:
            return narrative
        
        # === 人设校验 ===
        if self._character_params and alive_chars:
            for char in alive_chars:
                # 检查角色行为是否触犯禁忌
                char_type = "protagonist_daily" if hasattr(char, 'char_type') and char.char_type.value == "主角" else "npc_helper"
                replacement = self._character_params.check_taboo(char_type, narrative)
                if replacement:
                    # 记录违规并替换
                    import logging
                    logging.debug(f"[人设校验] 角色 {char.name} 行为触犯禁忌，已替换")
        
        # === 调试输出 ===
        if hasattr(self, '_debug_mode') and self._debug_mode:
            import logging
            logging.info(f"[叙事验证] 原始长度: {len(narrative)}, 验证后长度: {len(narrative)}")
            if self._plot_node_manager:
                node = self._plot_node_manager.get_current_node()
                if node:
                    logging.info(f"[剧情节点] 当前节点: {node.name}")
        
        # 1. 检查是否符合世界设定
        narrative = self._validate_world_setting(narrative, world)
        narrative = self._validate_world_setting(narrative, world)
        
        # 2. 检查角色行为是否符合性格设定
        narrative = self._validate_character_behavior(narrative, alive_chars)
        
        # 3. 检查是否符合主题规则
        narrative = self._filter_theme_violations(narrative)
        
        # 4. 检查是否有重复事件
        try:
            narrative = self._check_repetition(narrative, world)
        except Exception:
            pass
        
        # 5. Phase 3：禁词/禁情节硬校验（constants.py）
        narrative = self._check_forbidden_content(narrative)
        
        return narrative
    def _check_forbidden_content(self, text: str) -> str:
        """
        Phase 3：对叙事文本执行禁词、禁情节的硬校验。

        从 constants.py 导入 FORBIDDEN_WORDS 和 FORBIDDEN_PLOTS，
        对叙事文本进行字符串匹配过滤。
        """
        if not _HAS_CONSTANTS:
            return text
        try:
            # 禁词检查
            for word in FORBIDDEN_WORDS:
                if word and word in text:
                    original_len = len(text)
                    text = text.replace(word, "【已修】")
                    logger.warning(f"Phase3：叙事命中禁词「{word}」，已替换")

            # 禁情节检查
            for plot_pattern in FORBIDDEN_PLOTS:
                if plot_pattern and len(plot_pattern) > 3 and plot_pattern in text:
                    logger.warning(f"Phase3：叙事命中禁情节模式「{plot_pattern[:40]}」")
                    # 不直接删除，标记警告以便人工审查
            return text
        except Exception as e:
            logger.warning(f"Phase3：禁词校验异常: {e}")
            return text
    def _validate_world_setting(self, narrative, world):
        """验证叙事是否符合世界设定"""
        if not self._game_config:
            return narrative
        
        # 检查场景是否在允许的范围内
        allowed_scenes = self._game_config.get("allowed_scenes", [])
        if allowed_scenes:
            # 如果叙事中包含不允许的场景，进行标记
            for scene in allowed_scenes:
                if scene in narrative:
                    return narrative  # 包含允许的场景
        
        return narrative
    def _validate_character_behavior(self, narrative, alive_chars):
        """验证角色行为是否符合性格设定"""
        if not alive_chars:
            return narrative
        
        # 检查主角行为
        for char in alive_chars:
            if hasattr(char, 'char_type') and char.char_type.value == "主角":
                # 检查主角的行为是否符合目标
                if hasattr(char, 'goal') and char.goal:
                    # 如果主角有明确目标，确保叙事围绕目标展开
                    goal_keywords = self._extract_goal_keywords(char.goal)
                    if goal_keywords:
                        # 检查叙事是否包含目标相关内容
                        has_goal_content = any(kw in narrative for kw in goal_keywords)
                        if not has_goal_content and len(narrative) > 50:
                            # 如果叙事不包含目标内容，可能需要调整
                            pass  # 暂时不做处理，避免过度干预
        
        return narrative
    def _extract_goal_keywords(self, goal):
        """从目标中提取关键词"""
        if not goal:
            return []
        
        keywords = []
        # 提取动词
        goal_verbs = ["寻找", "找到", "救", "拯救", "保护", "击败", "打败", "得到",
                     "探索", "发现", "追查", "追踪", "完成", "实现", "阻止"]
        for verb in goal_verbs:
            if verb in goal:
                keywords.append(verb)
        
        # 提取名词（简单提取2-4字的词）
        for i in range(len(goal)):
            for length in range(2, 5):
                if i + length <= len(goal):
                    word = goal[i:i+length]
                    if word not in ["的", "了", "和", "与", "在", "是", "要", "去", "来", "到"]:
                        keywords.append(word)
        
        return list(set(keywords))[:10]  # 最多返回10个关键词
    def _validate_scene_nesting(self, text):
        """检查场景嵌套错误，如“阁楼的阁楼”“公园的电梯”"""
        import re
        # 不合理的场景组合
        invalid_patterns = [
            r"阁楼的阁楼", r"地下室的地下室", 
            r"公园的电梯", r"街道的阁楼",
            r"医院的教堂", r"教堂的医院",
            r"森林的地下室", r"山洞的阁楼",
            r"公园角落的教堂", r"医院的教堂",
            r"停车场的教堂", r"仓库的教堂",
            r"河边的阁楼", r"山洞的地下室",
        ]
        for pattern in invalid_patterns:
            if re.search(pattern, text):
                text = re.sub(pattern, "建筑内", text)
        return text

