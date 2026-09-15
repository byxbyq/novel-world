# -*- coding: utf-8 -*-
"""
游戏规则校验系统 - 确保所有生成内容符合规则
"""
import re
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from .character import Character
    from .world import World


class RuleValidator:
    """规则校验器 - 统一管理所有规则校验"""
    
    def __init__(self, engine):
        self.engine = engine
        self.protagonist_appear_count = 0  # 主角出现次数
        self.total_event_count = 0  # 总事件数
        self.violation_log = []  # 违规记录
        
    def validate_narrative(self, narrative: str, world_rules: dict = None) -> dict:
        """
        综合校验叙事内容
        返回: {
            "is_valid": bool,
            "filtered_narrative": str,
            "violations": list,
            "impact_type": str,
            "should_filter": bool
        }
        """
        violations = []
        is_valid = True
        filtered_narrative = narrative
        impact_type = "无关"
        should_filter = False
        
        # 1. 检查无名路人角色
        v1 = self._check_no_random_npc(narrative)
        if v1:
            violations.extend(v1)
            is_valid = False
        
        # 2. 检查反派行为
        v2 = self._check_antagonist_behavior(narrative)
        if v2:
            violations.extend(v2)
            is_valid = False
        
        # 3. 检查主角焦点和事件影响类型
        is_focus_valid, impact_type, focus_msg = self._check_protagonist_focus(narrative, world_rules)
        if not is_focus_valid:
            violations.append(focus_msg)
            should_filter = True  # 无关联事件应该过滤
        
        # 4. 检查事件重复
        v4 = self._check_event_repetition(narrative)
        if v4:
            violations.append(v4)
            should_filter = True
        
        # 5. 检查路人死亡结尾
        v5 = self._check_random_death_ending(narrative)
        if v5:
            violations.append(v5)
            is_valid = False
            should_filter = True
        
        # 6. 检查世界观规则
        v6 = self._check_world_rules(narrative, world_rules)
        if v6:
            violations.extend(v6)
            is_valid = False
        
        # 7. 检查道具使用（规则6）
        v7 = self._check_item_usage(narrative, world_rules)
        if v7:
            violations.extend(v7)
            is_valid = False
        
        # 7. 更新主角占比统计
        self._update_protagonist_stats(narrative)
        
        # 记录违规
        if violations:
            self.violation_log.extend(violations)
        
        return {
            "is_valid": is_valid,
            "filtered_narrative": filtered_narrative,
            "violations": violations,
            "impact_type": impact_type,
            "should_filter": should_filter
        }
    
    def _check_no_random_npc(self, narrative: str) -> list:
        """规则1: 检查是否有无设定无关联的无名NPC"""
        violations = []
        
        # 常见的路人名字模式
        random_names = [
            "小明", "小红", "小强", "小李", "小王", "小张", "小雪", "小美",
            "李青云", "周辰", "王伟", "张三", "李四", "路人", "某人", "陌生人",
            "一个路人", "一个陌生人", "某个人"
        ]
        
        # 获取已建立的角色名称
        established_names = set()
        if self.engine and hasattr(self.engine, 'world'):
            for char in self.engine.world.characters:
                established_names.add(char.name)
        
        for name in random_names:
            if name in narrative:
                # 检查这个角色是否在已知角色列表中
                if name not in established_names:
                    violations.append(f"【规则1违规】发现无名NPC: {name}")
        
        return violations
    
    def _check_antagonist_behavior(self, narrative: str) -> list:
        """规则5: 检查反派行为是否符合设定"""
        violations = []
        
        if not self.engine or not hasattr(self.engine, 'antagonist'):
            return violations
        
        antagonist = self.engine.antagonist
        if not antagonist:
            return violations
        
        # 检查反派设定
        if hasattr(antagonist, 'personality') and antagonist.personality:
            # 如果设定为不可对抗、无理智、意志类
            is_undefeatable = any(kw in antagonist.personality for kw in ["不可对抗", "无理智", "意志", "无法击败", "不死"])
            
            if is_undefeatable:
                # 检查是否有违规描述（被击败、被杀死等）
                defeat_patterns = [
                    f"击败了{antagonist.name}",
                    f"打败了{antagonist.name}",
                    f"杀死了{antagonist.name}",
                    f"{antagonist.name}被击败",
                    f"{antagonist.name}被打败",
                    f"{antagonist.name}死亡",
                    f"{antagonist.name}死了"
                ]
                
                for pattern in defeat_patterns:
                    if pattern in narrative:
                        violations.append(f"【规则5违规】反派 {antagonist.name} 行为与设定矛盾：设定为不可对抗，但出现了'{pattern}'")
        
        return violations
    
    def _check_protagonist_focus(self, narrative: str, world_rules: dict = None) -> tuple:
        """
        规则4: 检查事件是否围绕主角目标展开
        返回: (is_valid, impact_type, message)
        """
        if not self.engine or not hasattr(self.engine, 'protagonist'):
            return (True, "无关", "无主角")
        
        protagonist = self.engine.protagonist
        if not protagonist:
            return (True, "无关", "无主角")
        
        # 提取主角目标关键词
        goal = protagonist.goal or ""
        goal_keywords = self._extract_goal_keywords(goal)
        
        # 分析事件影响类型
        impact_type = self._analyze_impact_type(narrative, protagonist.name, goal_keywords)
        
        # 如果是无关事件
        if impact_type == "无关":
            # 检查是否是必要的过渡事件
            if self._is_necessary_transition(narrative):
                return (True, "过渡", "必要过渡事件")
            else:
                return (False, "无关", "【规则4违规】事件与主角目标无关，应过滤")
        
        return (True, impact_type, f"事件符合规则，影响类型：{impact_type}")
    
    def _extract_goal_keywords(self, goal: str) -> list:
        """从主角目标中提取关键词"""
        if not goal:
            return []
        
        keywords = []
        
        # 常见的目标动词
        goal_verbs = [
            "寻找", "找到", "救", "拯救", "击败", "打败", "获得", "得到",
            "发现", "探索", "调查", "追查", "追踪", "保护", "守护",
            "逃离", "逃出", "返回", "回去", "前往", "到达", "进入",
            "解开", "破解", "完成", "实现", "达成", "阻止"
        ]
        
        for verb in goal_verbs:
            if verb in goal:
                keywords.append(verb)
        
        # 提取名词
        for i in range(len(goal)):
            for length in range(2, 5):
                if i + length <= len(goal):
                    word = goal[i:i+length]
                    if word not in ["的", "了", "是", "在", "有", "和", "与", "或", "我", "要", "把", "被", "给", "向", "从", "到"]:
                        keywords.append(word)
        
        return list(set(keywords))[:15]
    
    def _analyze_impact_type(self, narrative: str, protagonist_name: str, goal_keywords: list) -> str:
        """分析事件对主角目标的影响类型"""
        
        # 检查推进型事件
        progress_verbs = ["成功", "完成", "获得", "得到", "找到", "发现", "到达", "进入", "击败", "战胜", "救出", "拯救", "解开", "破解", "实现", "达成"]
        for verb in progress_verbs:
            if verb in narrative:
                if any(kw in narrative for kw in goal_keywords):
                    return "推进"
                if protagonist_name in narrative:
                    return "推进"
        
        # 检查阻碍型事件
        obstacle_patterns = ["失败", "受阻", "困难", "危险", "敌人", "对手", "陷阱", "危机", "受伤", "被困", "迷路", "丢失", "被抢", "被阻", "遭遇", "陷入"]
        for pattern in obstacle_patterns:
            if pattern in narrative and protagonist_name in narrative:
                return "阻碍"
        
        # 检查揭示线索型事件
        clue_verbs = ["发现", "得知", "了解", "看到", "听到", "注意到", "意识到", "察觉", "获知"]
        clue_nouns = ["线索", "秘密", "真相", "证据", "提示", "消息", "情报", "踪迹", "痕迹", "记录"]
        for verb in clue_verbs:
            if verb in narrative:
                for noun in clue_nouns:
                    if noun in narrative:
                        return "揭示线索"
                if any(kw in narrative for kw in goal_keywords):
                    return "揭示线索"
        
        # 检查主角是否在叙述中
        if protagonist_name in narrative:
            for kw in goal_keywords:
                if kw in narrative:
                    return "推进"
            action_verbs = ["前往", "走向", "进入", "离开", "开始", "准备", "出发", "行动"]
            for verb in action_verbs:
                if verb in narrative:
                    return "推进"
        
        return "无关"
    
    def _is_necessary_transition(self, narrative: str) -> bool:
        """检查是否是必要的过渡事件"""
        transition_patterns = [
            "时间流逝", "天气变化", "环境描写", "氛围营造",
            "夜幕降临", "天色渐暗", "黎明到来", "日上三竿",
            "休息", "准备", "整装", "出发", "启程",
            "思考", "回忆", "沉思", "等待", "观察"
        ]
        
        for pattern in transition_patterns:
            if pattern in narrative:
                return True
        
        # 短小的纯环境描写允许
        has_character_action = any(kw in narrative for kw in ["说", "做", "走", "跑", "看", "听", "想", "拿", "放", "打开", "关闭"])
        if not has_character_action and len(narrative) < 100:
            return True
        
        return False
    
    def _check_event_repetition(self, narrative: str) -> str:
        """规则3/8: 检查事件是否重复"""
        if not self.engine or not hasattr(self.engine, 'world'):
            return ""
        
        story_log = self.engine.world.story_log
        if len(story_log) < 2:
            return ""
        
        # 检查最近5条日志
        recent = story_log[-5:]
        
        for log in recent:
            if log == narrative:
                return "【规则3违规】事件完全重复"
            
            # 计算相似度
            if len(narrative) > 20 and len(log) > 20:
                words1 = set(re.findall(r'[一-龥]{2,}', narrative))
                words2 = set(re.findall(r'[一-龥]{2,}', log))
                
                if words1 and words2:
                    overlap = len(words1 & words2)
                    if overlap / len(words1) > 0.7:
                        return "【规则8违规】事件内容高度重复"
        
        return ""
    
    def _check_random_death_ending(self, narrative: str) -> str:
        """规则8: 检查是否有无名路人死亡强行结尾"""
        tail = narrative[-80:] if len(narrative) > 80 else narrative
        
        death_keywords = ["死", "亡", "牺牲", "去世", "毙命"]
        random_names = ["小明", "小红", "小强", "路人", "某人", "陌生人"]
        
        # 获取已建立的角色名称
        established_names = set()
        if self.engine and hasattr(self.engine, 'world'):
            for char in self.engine.world.characters:
                established_names.add(char.name)
        
        for name in random_names:
            for death in death_keywords:
                if name in tail and death in tail:
                    if name not in established_names:
                        return f"【规则8违规】无名路人 {name} 死亡强行结尾"
        
        return ""
    
    def _check_world_rules(self, narrative: str, world_rules: dict) -> list:
        """规则2/9: 检查是否违反世界观规则"""
        violations = []
        
        if not world_rules:
            return violations
        
        perms = world_rules.get("permissions", {})
        
        # 检查魔法
        if not perms.get("allow_magic", True):
            magic_keywords = ["魔法", "法术", "咒语", "魔力", "施法", "念咒", "法阵", "灵力", "仙术"]
            for kw in magic_keywords:
                if kw in narrative:
                    violations.append(f"【规则2违规】事件违反世界观规则：禁止魔法/超能力，但出现了'{kw}'")
                    break
        
        # 检查战斗
        if not perms.get("allow_combat", True):
            combat_keywords = ["战斗", "打斗", "厮杀", "交战", "对打", "攻击", "杀", "砍", "刺"]
            for kw in combat_keywords:
                if kw in narrative:
                    violations.append(f"【规则2违规】事件违反世界观规则：禁止战斗/杀戮，但出现了'{kw}'")
                    break
        
        # 检查现代物品
        if not perms.get("allow_modern_items", True):
            modern_keywords = ["手机", "电脑", "汽车", "飞机", "电视", "网络", "互联网", "APP", "微信"]
            for kw in modern_keywords:
                if kw in narrative:
                    violations.append(f"【规则2违规】事件违反世界观规则：禁止现代物品，但出现了'{kw}'")
                    break
        
        # 检查禁词
        forbidden = world_rules.get("forbidden_words", [])
        for word in forbidden:
            if word and word in narrative:
                violations.append(f"【规则2违规】事件包含禁止词汇：{word}")
        
        return violations
    
    def _update_protagonist_stats(self, narrative: str):
        """更新主角占比统计"""
        self.total_event_count += 1
        
        if self.engine and hasattr(self.engine, 'protagonist') and self.engine.protagonist:
            if self.engine.protagonist.name in narrative:
                self.protagonist_appear_count += 1
    
    def get_protagonist_ratio(self) -> float:
        """获取主角占比"""
        if self.total_event_count == 0:
            return 0.0
        return self.protagonist_appear_count / self.total_event_count
    
    def check_protagonist_ratio_rule(self) -> str:
        """规则4: 检查主角占比是否达到60%"""
        ratio = self.get_protagonist_ratio()
        if ratio < 0.6:
            return f"【规则4违规】主角占比仅 {ratio*100:.1f}%，未达到60%要求"
        return ""
    
    def generate_transition_event(self) -> str:
        """生成过渡事件作为被过滤事件的替代"""
        import random
        
        if self.engine and hasattr(self.engine, 'protagonist') and self.engine.protagonist:
            name = self.engine.protagonist.name
            transitions = [
                f"{name}继续前行，思考着接下来的计划。",
                f"{name}观察着周围的环境，寻找前进的方向。",
                f"时间悄然流逝，{name}依然在为心中的目标努力。",
                f"{name}稍作休息，整理着思绪。",
                f"前路漫漫，{name}坚定地迈出下一步。",
            ]
            return random.choice(transitions)
        
        return "时间悄然流逝，故事继续。"
    
    def validate_npc_generation(self, name: str, personality: str = None) -> tuple:
        """规则1: 校验NPC生成是否符合规则"""
        # 常见的路人名字模式
        random_names = [
            "小明", "小红", "小强", "小李", "小王", "小张", "小雪", "小美",
            "李青云", "周辰", "张三", "李四"
        ]
        
        for pattern in random_names:
            if name == pattern or name.startswith(pattern):
                if not personality or len(personality) < 5:
                    return (False, f"【规则1违规】禁止生成无设定NPC: {name}")
        
        return (True, "")
    
    def get_violation_report(self) -> str:
        """获取违规报告"""
        if not self.violation_log:
            return "✅ 无违规记录"
        
        report = "❌ 违规记录：\n"
        for i, v in enumerate(self.violation_log[-20:], 1):  # 最近20条
            report += f"{i}. {v}\n"
        
        # 添加主角占比检查
        ratio_check = self.check_protagonist_ratio_rule()
        if ratio_check:
            report += f"\n{ratio_check}\n"
        
        return report

    
    def _check_item_usage(self, narrative: str, world_rules: dict) -> list:
        """规则6: 检查道具使用是否符合规则"""
        violations = []
        
        # 检测道具使用关键词
        use_keywords = ["使用", "服用", "喝下", "吃下", "装备", "激活", "投掷"]
        item_keywords = ["药水", "药剂", "卷轴", "炸弹", "道具", "物品"]
        
        # 检查是否有道具使用描述
        has_item_use = False
        for use_kw in use_keywords:
            for item_kw in item_keywords:
                if use_kw in narrative and item_kw in narrative:
                    has_item_use = True
                    break
        
        if has_item_use:
            # 检查是否有代价描述
            cost_keywords = ["消耗", "花费", "付出", "扣除"]
            has_cost = any(kw in narrative for kw in cost_keywords)
            
            # 检查是否有效果描述
            effect_keywords = ["恢复", "增加", "提升", "造成", "获得", "失去"]
            has_effect = any(kw in narrative for kw in effect_keywords)
            
            # 如果道具使用没有代价或效果，记录违规
            if not has_cost:
                violations.append("【规则6违规】道具使用没有描述代价")
            if not has_effect:
                violations.append("【规则6违规】道具使用没有描述效果")
        
        return violations
