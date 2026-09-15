# -*- coding: utf-8 -*-
"""
强制修正系统 - 不只是检测，而是强制修正
确保所有生成内容符合规则，违规内容被强制过滤/替换
"""
import re
from typing import Dict, List, Set, Tuple, Optional
from dataclasses import dataclass, field
from collections import defaultdict


@dataclass
class CorrectionResult:
    """修正结果"""
    original: str                    # 原始内容
    corrected: str                    # 修正后内容
    is_modified: bool                 # 是否被修正
    was_replaced: bool                # 是否被替换（原内容被丢弃）
    violations: List[str]             # 违规记录
    corrections: List[str]            # 修正记录


class EventDeduplicator:
    """事件去重器 - 规则1: 禁止重复桥段、重复句式"""
    
    def __init__(self):
        self.event_history: List[str] = []           # 事件历史
        self.sentence_patterns: Set[str] = set()     # 句式模式
        self.used_items: Set[str] = set()            # 已使用道具
        self.conflict_types: Set[str] = set()        # 已出现冲突类型
        self.max_history = 100                        # 最大历史记录
    
    def check_and_register(self, narrative: str) -> Tuple[bool, List[str]]:
        """
        检查并注册事件
        返回: (is_duplicate, violations)
        """
        violations = []
        is_duplicate = False
        
        # 1. 检查完全重复
        if narrative in self.event_history:
            violations.append("【事件去重】完全重复的事件")
            is_duplicate = True
            return (is_duplicate, violations)
        
        # 2. 提取句式模式（去掉具体名词，保留结构）
        pattern = self._extract_pattern(narrative)
        if pattern in self.sentence_patterns:
            violations.append(f"【事件去重】重复句式模式")
            is_duplicate = True
        
        # 3. 检查道具重复
        items = self._extract_items(narrative)
        repeated_items = items & self.used_items
        if repeated_items:
            violations.append(f"【事件去重】重复道具: {', '.join(repeated_items)}")
        
        # 4. 检查冲突类型重复
        conflict = self._extract_conflict_type(narrative)
        if conflict and conflict in self.conflict_types:
            violations.append(f"【事件去重】重复冲突类型: {conflict}")
            is_duplicate = True
        
        # 注册
        self._register(narrative, pattern, items, conflict)
        
        return (is_duplicate, violations)
    
    def _extract_pattern(self, narrative: str) -> str:
        """提取句式模式"""
        # 去掉人名、地名、道具名，保留动词和结构
        pattern = narrative
        # 简单处理：提取动词和关键结构词
        verbs = re.findall(r'[一-龥]{1,2}(了|着|过|到|出|入|进|退|起|落|上|下)', narrative)
        return '|'.join(verbs)
    
    def _extract_items(self, narrative: str) -> Set[str]:
        """提取道具"""
        item_keywords = ["药水", "药剂", "卷轴", "炸弹", "钥匙", "地图", "剑", "盾", "法杖"]
        items = set()
        for kw in item_keywords:
            if kw in narrative:
                items.add(kw)
        return items
    
    def _extract_conflict_type(self, narrative: str) -> Optional[str]:
        """提取冲突类型"""
        conflict_patterns = {
            "战斗": ["战斗", "打斗", "厮杀", "交战"],
            "追逐": ["追逐", "逃跑", "追击", "逃亡"],
            "谈判": ["谈判", "协商", "交涉", "对话"],
            "探索": ["探索", "调查", "搜寻", "寻找"],
            "陷阱": ["陷阱", "埋伏", "暗算", "突袭"],
        }
        for conflict_type, keywords in conflict_patterns.items():
            for kw in keywords:
                if kw in narrative:
                    return conflict_type
        return None
    
    def _register(self, narrative: str, pattern: str, items: Set[str], conflict: Optional[str]):
        """注册事件"""
        self.event_history.append(narrative)
        if len(self.event_history) > self.max_history:
            self.event_history.pop(0)
        
        self.sentence_patterns.add(pattern)
        self.used_items.update(items)
        if conflict:
            self.conflict_types.add(conflict)


class CharacterEnforcer:
    """角色强制约束器 - 规则2: 只使用指定角色，禁止OOC"""
    
    def __init__(self):
        self.established_characters: Dict[str, dict] = {}   # 已建立角色 {name: {设定}}
        self.character_behaviors: Dict[str, List[str]] = defaultdict(list)  # 角色行为历史
        self.max_behaviors = 20                             # 最大行为记录
    
    def register_character(self, name: str, personality: str = "", role: str = "", 
                          is_undefeatable: bool = False, is_immortal: bool = False):
        """注册角色"""
        self.established_characters[name] = {
            "personality": personality,
            "role": role,  # "protagonist", "antagonist", "npc"
            "is_undefeatable": is_undefeatable,
            "is_immortal": is_immortal,
        }
    
    def check_character_usage(self, narrative: str) -> Tuple[bool, List[str]]:
        """
        检查角色使用是否合规
        返回: (is_valid, violations)
        """
        violations = []
        is_valid = True
        
        # 1. 检查是否使用了未注册的角色（路人检测）
        used_names = self._extract_character_names(narrative)
        for name in used_names:
            if name not in self.established_characters:
                violations.append(f"【角色约束】发现未注册角色: {name}")
                is_valid = False
        
        # 2. 检查角色行为是否符合设定（OOC检测）
        for name, char_info in self.established_characters.items():
            if name in narrative:
                ooc = self._check_ooc(name, narrative, char_info)
                violations.extend(ooc)
                if ooc:
                    is_valid = False
        
        return (is_valid, violations)
    
    def _extract_character_names(self, narrative: str) -> Set[str]:
        """提取叙事中的角色名"""
        # 从已注册角色中匹配
        names = set()
        for name in self.established_characters:
            if name in narrative:
                names.add(name)
        return names
    
    def _check_ooc(self, name: str, narrative: str, char_info: dict) -> List[str]:
        """检查角色是否OOC（Out of Character）"""
        violations = []
        
        # 检查反派OOC
        if char_info.get("role") == "antagonist":
            # 反派不应该：逃跑、怕死、组队、被轻易杀死
            antagonist_ooc_patterns = [
                (f"{name}逃跑", "反派不应逃跑"),
                (f"{name}害怕", "反派不应表现出恐惧"),
                (f"{name}求饶", "反派不应求饶"),
                (f"{name}被轻易杀死", "反派不应被轻易杀死"),
                (f"{name}被击败", "反派不应被轻易击败") if char_info.get("is_undefeatable") else (None, None),
            ]
            
            for pattern, msg in antagonist_ooc_patterns:
                if pattern and pattern in narrative:
                    violations.append(f"【角色OOC】{msg}: {pattern}")
        
        # 检查不死角色
        if char_info.get("is_immortal"):
            death_patterns = [f"{name}死亡", f"{name}死了", f"{name}被杀"]
            for pattern in death_patterns:
                if pattern in narrative:
                    violations.append(f"【角色OOC】不死角色不应死亡: {pattern}")
        
        return violations
    
    def get_allowed_characters(self) -> List[str]:
        """获取允许使用的角色列表"""
        return list(self.established_characters.keys())


class WorldviewEnforcer:
    """世界观强制约束器 - 规则3: 世界观统一，不自相矛盾"""
    
    def __init__(self):
        self.worldview_rules: dict = {}
        self.theme: str = ""
    
    def set_worldview(self, theme: str, rules: dict):
        """设置世界观规则"""
        self.theme = theme
        self.worldview_rules = rules
    
    def check_worldview(self, narrative: str) -> Tuple[bool, List[str]]:
        """
        检查内容是否符合世界观
        返回: (is_valid, violations)
        """
        violations = []
        is_valid = True
        
        if not self.worldview_rules:
            return (is_valid, violations)
        
        perms = self.worldview_rules.get("permissions", {})
        
        # 1. 检查魔法/科技一致性
        has_magic = any(kw in narrative for kw in ["魔法", "法术", "咒语", "魔力", "施法"])
        has_tech = any(kw in narrative for kw in ["电脑", "手机", "汽车", "飞机", "电视"])
        
        if has_magic and not perms.get("allow_magic", True):
            violations.append("【世界观冲突】出现魔法元素，但世界观禁止魔法")
            is_valid = False
        
        if has_tech and not perms.get("allow_modern_items", True):
            violations.append("【世界观冲突】出现现代科技，但世界观禁止现代物品")
            is_valid = False
        
        # 2. 检查禁词
        forbidden = self.worldview_rules.get("forbidden_words", [])
        for word in forbidden:
            if word and word in narrative:
                violations.append(f"【世界观冲突】出现禁止词汇: {word}")
                is_valid = False
        
        # 3. 检查场景逻辑
        scene_violations = self._check_scene_logic(narrative)
        violations.extend(scene_violations)
        if scene_violations:
            is_valid = False
        
        return (is_valid, violations)
    
    def _check_scene_logic(self, narrative: str) -> List[str]:
        """检查场景逻辑是否成立"""
        violations = []
        
        # 检查不可能的场景组合
        invalid_combinations = [
            ("地下室", "阁楼", "地下室不可能有阁楼"),
            ("公园", "地下室", "公园不应该有地下室"),
            ("医院", "监狱", "医院不应该有监狱"),
            ("森林", "地下室", "森林不应该有地下室"),
        ]
        
        for scene1, scene2, msg in invalid_combinations:
            if scene1 in narrative and scene2 in narrative:
                violations.append(f"【场景逻辑】{msg}")
        
        return violations


class RuleEnforcer:
    """规则强制执行器 - 规则4: 违规必有代价"""
    
    def __init__(self):
        self.violation_count: Dict[str, int] = defaultdict(int)  # 违规计数
        self.consequence_log: List[str] = []                      # 后果日志
    
    def enforce_consequence(self, violation_type: str, context: dict) -> dict:
        """
        强制执行违规后果
        返回: {consequence_applied: bool, consequence: str, severity: str}
        """
        self.violation_count[violation_type] += 1
        count = self.violation_count[violation_type]
        
        consequence = ""
        severity = "warning"
        
        # 根据违规类型和次数决定后果
        if "重复" in violation_type:
            if count >= 3:
                consequence = "强制跳过该回合，不生成任何事件"
                severity = "critical"
            else:
                consequence = "警告：事件重复"
                severity = "warning"
        
        elif "OOC" in violation_type or "角色" in violation_type:
            if count >= 2:
                consequence = "强制修正角色行为，恢复角色设定"
                severity = "high"
            else:
                consequence = "警告：角色行为异常"
                severity = "warning"
        
        elif "世界观" in violation_type:
            consequence = "强制过滤违规内容，替换为符合世界观的描述"
            severity = "high"
        
        elif "道具" in violation_type:
            consequence = "强制扣除道具使用代价"
            severity = "medium"
        
        elif "死亡" in violation_type:
            consequence = "严格执行死亡机制，不可复活"
            severity = "critical"
        
        else:
            consequence = "记录违规"
            severity = "low"
        
        if consequence:
            self.consequence_log.append(f"[{severity}] {violation_type}: {consequence}")
        
        return {
            "consequence_applied": bool(consequence),
            "consequence": consequence,
            "severity": severity,
            "violation_count": count,
        }


class PlotStructureEnforcer:
    """剧情结构强制约束器 - 规则5: 剧情有逻辑，不随机堆砌"""
    
    def __init__(self):
        self.main_plot_events: List[str] = []       # 主线事件
        self.cause_effect_chain: List[Tuple] = []   # 因果链 [(cause, effect)]
        self.sentence_structures: List[str] = []    # 句式结构历史
        self.max_structures = 30                     # 最大句式记录
    
    def check_plot_structure(self, narrative: str, protagonist_name: str = "") -> Tuple[bool, List[str]]:
        """
        检查剧情结构
        返回: (is_valid, violations)
        """
        violations = []
        is_valid = True
        
        # 1. 检查是否有主线推进
        if protagonist_name and protagonist_name in narrative:
            # 检查是否是主线相关事件
            main_plot_keywords = ["目标", "发现", "获得线索", "遭遇敌人", "突破", "成功", "失败"]
            is_main_plot = any(kw in narrative for kw in main_plot_keywords)
            
            if is_main_plot:
                self.main_plot_events.append(narrative[:50])  # 记录主线事件
        else:
            # 主角不在叙事中，检查是否是必要的过渡
            transition_keywords = ["时间流逝", "天气", "环境", "氛围"]
            is_transition = any(kw in narrative for kw in transition_keywords)
            
            if not is_transition and len(narrative) > 50:
                violations.append("【剧情结构】非过渡事件但主角未出现，可能偏离主线")
        
        # 2. 检查句式多样性
        structure = self._extract_structure(narrative)
        if structure in self.sentence_structures:
            violations.append("【剧情结构】句式结构重复，缺乏变化")
            is_valid = False
        
        self.sentence_structures.append(structure)
        if len(self.sentence_structures) > self.max_structures:
            self.sentence_structures.pop(0)
        
        # 3. 检查是否有因果逻辑
        # 简单检查：是否有"因为"、"所以"、"导致"等因果词
        has_causality = any(kw in narrative for kw in ["因为", "所以", "导致", "于是", "因此", "结果"])
        
        return (is_valid, violations)
    
    def _extract_structure(self, narrative: str) -> str:
        """提取句式结构"""
        # 提取句子结构：主语+动词+宾语 的模式
        # 简化处理：提取前20个字符的结构
        structure = narrative[:20] if len(narrative) > 20 else narrative
        # 去掉具体名词，保留结构
        structure = re.sub(r'[一-龥]{2,4}', 'X', structure)
        return structure


class NarrativeCorrector:
    """
    叙事强制修正器 - 整合所有约束器
    在生成时强制修正内容，确保合规
    """
    
    def __init__(self):
        self.event_deduplicator = EventDeduplicator()
        self.character_enforcer = CharacterEnforcer()
        self.worldview_enforcer = WorldviewEnforcer()
        self.rule_enforcer = RuleEnforcer()
        self.plot_enforcer = PlotStructureEnforcer()
        
        self.correction_log: List[str] = []  # 修正日志
    
    def correct_narrative(self, narrative: str, context: dict = None) -> CorrectionResult:
        """
        强制修正叙事内容
        返回修正结果
        """
        if context is None:
            context = {}
        
        violations = []
        corrections = []
        corrected = narrative
        was_replaced = False
        
        # 1. 事件去重检查
        is_dup, dup_violations = self.event_deduplicator.check_and_register(narrative)
        violations.extend(dup_violations)
        
        if is_dup:
            # 强制替换为过渡事件
            corrected = self._generate_transition(context)
            corrections.append("【强制修正】重复事件已替换为过渡事件")
            was_replaced = True
        
        # 2. 角色约束检查
        is_char_valid, char_violations = self.character_enforcer.check_character_usage(corrected)
        violations.extend(char_violations)
        
        if not is_char_valid:
            # 强制移除未注册角色
            corrected = self._remove_random_characters(corrected)
            corrections.append("【强制修正】已移除未注册角色")
        
        # 3. 世界观检查
        is_world_valid, world_violations = self.worldview_enforcer.check_worldview(corrected)
        violations.extend(world_violations)
        
        if not is_world_valid:
            # 强制过滤违规内容
            corrected = self._filter_worldview_violations(corrected)
            corrections.append("【强制修正】已过滤世界观违规内容")
        
        # 4. 剧情结构检查
        protagonist_name = context.get("protagonist_name", "")
        is_plot_valid, plot_violations = self.plot_enforcer.check_plot_structure(corrected, protagonist_name)
        violations.extend(plot_violations)
        
        # 5. 执行违规后果
        for violation in violations:
            consequence = self.rule_enforcer.enforce_consequence(violation, context)
            if consequence["severity"] in ["critical", "high"]:
                corrected = self._generate_transition(context)
                was_replaced = True
                corrections.append(f"【强制修正】{consequence['consequence']}")
                break
        
        # 记录修正
        is_modified = (corrected != narrative)
        if is_modified:
            self.correction_log.append(f"原: {narrative[:30]}... → 修: {corrected[:30]}...")
        
        return CorrectionResult(
            original=narrative,
            corrected=corrected,
            is_modified=is_modified,
            was_replaced=was_replaced,
            violations=violations,
            corrections=corrections,
        )
    
    def _generate_transition(self, context: dict) -> str:
        """生成过渡事件"""
        import random
        protagonist_name = context.get("protagonist_name", "主角")
        
        transitions = [
            f"{protagonist_name}继续前行，思考着接下来的计划。",
            f"{protagonist_name}观察着周围的环境，寻找前进的方向。",
            f"时间悄然流逝，{protagonist_name}依然在为心中的目标努力。",
            f"{protagonist_name}稍作休息，整理着思绪。",
            f"前路漫漫，{protagonist_name}坚定地迈出下一步。",
        ]
        
        return random.choice(transitions)
    
    def _remove_random_characters(self, narrative: str) -> str:
        """移除未注册角色"""
        # 获取允许的角色
        allowed = self.character_enforcer.get_allowed_characters()
        
        # 常见的路人名字
        random_names = ["小明", "小红", "小强", "小李", "小王", "小张", "小雪", "小美",
                       "李青云", "周辰", "张三", "李四", "路人", "某人", "陌生人"]
        
        for name in random_names:
            if name in narrative and name not in allowed:
                # 用"某人"替换或直接删除
                narrative = narrative.replace(name, "某人")
        
        return narrative
    
    def _filter_worldview_violations(self, narrative: str) -> str:
        """过滤世界观违规内容"""
        perms = self.worldview_enforcer.worldview_rules.get("permissions", {})
        
        # 如果禁止魔法，移除魔法相关词
        if not perms.get("allow_magic", True):
            magic_words = ["魔法", "法术", "咒语", "魔力", "施法", "念咒"]
            for word in magic_words:
                narrative = narrative.replace(word, "神秘力量")
        
        # 如果禁止现代物品，移除现代词
        if not perms.get("allow_modern_items", True):
            modern_words = ["手机", "电脑", "汽车", "飞机", "电视", "网络"]
            for word in modern_words:
                narrative = narrative.replace(word, "物品")
        
        # 移除禁词
        forbidden = self.worldview_enforcer.worldview_rules.get("forbidden_words", [])
        for word in forbidden:
            if word:
                narrative = narrative.replace(word, "***")
        
        return narrative
    
    def register_character(self, name: str, **kwargs):
        """注册角色"""
        self.character_enforcer.register_character(name, **kwargs)
    
    def set_worldview(self, theme: str, rules: dict):
        """设置世界观"""
        self.worldview_enforcer.set_worldview(theme, rules)
    
    def get_correction_report(self) -> str:
        """获取修正报告"""
        if not self.correction_log:
            return "✅ 无修正记录"
        
        report = f"📝 修正记录（共{len(self.correction_log)}条）：\n"
        for i, log in enumerate(self.correction_log[-20:], 1):
            report += f"{i}. {log}\n"
        
        return report
    
    def get_violation_summary(self) -> dict:
        """获取违规统计"""
        return dict(self.rule_enforcer.violation_count)
