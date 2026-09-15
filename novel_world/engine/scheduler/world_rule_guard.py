# -*- coding: utf-8 -*-
"""
世界观规则守卫层 - 在叙事输出前校验内容是否符合世界观设定

核心职责：
  1. 检查叙事文本是否包含违反世界观设定的内容（禁词、禁用能力等）
  2. 检查角色行为是否符合其设定（性格、能力边界）
  3. 检查场景描述是否符合世界规则（物理法则、社会结构）
  4. 提供违规报告和修复建议

与现有模块的关系：
  - 与 quality/rule_validator.py 互补：RuleValidator 检查通用写作规则，
    WorldRuleGuard 检查世界观特有的设定规则
  - 从 TruthLedger 读取角色设定和世界状态作为校验基准
  - 在 CausalCollisionScheduler 输出叙事后进行守卫校验

设计原则：
  - 规则可配置，支持动态添加/移除
  - 校验不修改内容，只报告违规和修复建议
  - 按严重程度分级：block（阻断输出）/ warn（警告但放行）/ info（提示）
"""
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Dict, List, Optional, Set


class GuardLevel(Enum):
    """守卫级别"""
    BLOCK = "block"    # 阻断：严重违规，必须修改后才能输出
    WARN = "warn"      # 警告：可能违规，允许输出但需人工审查
    INFO = "info"      # 提示：轻微问题，不影响输出


@dataclass
class WorldRule:
    """
    世界观规则定义

    Attributes:
        id: 规则唯一 ID
        name: 规则名称
        description: 规则描述
        level: 违规级别
        rule_type: 规则类型（forbidden_word / power_limit / character_boundary / scene_rule）
        keywords: 违规关键词列表（forbidden_word 类型使用）
        condition: 规则条件描述（自然语言，供 AI 判断）
        auto_fix: 是否支持自动修复
        fix_suggestion: 修复建议模板
    """
    id: str = ""
    name: str = ""
    description: str = ""
    level: GuardLevel = GuardLevel.WARN
    rule_type: str = "forbidden_word"
    keywords: List[str] = field(default_factory=list)
    condition: str = ""
    auto_fix: bool = False
    fix_suggestion: str = ""

    def to_dict(self) -> dict:
        d = asdict(self)
        d["level"] = self.level.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "WorldRule":
        data = dict(data)
        if isinstance(data.get("level"), str):
            data["level"] = GuardLevel(data["level"])
        return cls(**data)


@dataclass
class GuardViolation:
    """
    规则违规记录

    Attributes:
        rule_id: 违反的规则 ID
        rule_name: 规则名称
        level: 违规级别
        message: 违规描述
        context: 违规上下文（包含违规关键词的文本片段）
        fix_suggestion: 修复建议
    """
    rule_id: str = ""
    rule_name: str = ""
    level: GuardLevel = GuardLevel.WARN
    message: str = ""
    context: str = ""
    fix_suggestion: str = ""

    def to_dict(self) -> dict:
        d = asdict(self)
        d["level"] = self.level.value
        return d


class WorldRuleGuard:
    """
    世界观规则守卫

    使用方式：
        guard = WorldRuleGuard()
        guard.set_truth_ledger(ledger)

        # 注册规则
        guard.add_rule(WorldRule(
            id="no_modern_tech",
            name="禁止现代科技",
            description="修仙世界不应出现手机、电脑等现代物品",
            level=GuardLevel.BLOCK,
            rule_type="forbidden_word",
            keywords=["手机", "电脑", "汽车", "飞机", "电视", "网络"],
            fix_suggestion="将现代物品替换为符合世界观的法器或信物",
        ))

        # 校验叙事
        violations = guard.check_narrative("叶凡拿出手机查看消息")
        if violations:
            print(guard.get_violation_report())
    """

    def __init__(self):
        self.rules: Dict[str, WorldRule] = {}
        self.truth_ledger = None
        self._violation_history: List[GuardViolation] = []

        # 初始化默认规则
        self._init_default_rules()

    # ─── 引用设置 ───

    def set_truth_ledger(self, ledger):
        """设置 TruthLedger 引用，用于读取角色/世界设定"""
        self.truth_ledger = ledger

    # ─── 默认规则 ───

    def _init_default_rules(self):
        """初始化内置默认规则"""
        defaults = [
            WorldRule(
                id="no_modern_tech",
                name="禁止现代科技",
                description="修仙/玄幻世界不应出现现代科技产品",
                level=GuardLevel.BLOCK,
                rule_type="forbidden_word",
                keywords=["手机", "电脑", "汽车", "飞机", "电视", "网络",
                          "互联网", "APP", "微信", "电梯", "空调"],
                fix_suggestion="将现代物品替换为符合世界观的法器、符纸或传音玉简",
            ),
            WorldRule(
                id="no_english_mix",
                name="禁止中英混杂",
                description="叙事文本中不应出现不必要的英文词汇",
                level=GuardLevel.WARN,
                rule_type="forbidden_word",
                keywords=["OK", "VIP", "CEO", "APP", "ID", "PPT", "GPS"],
                fix_suggestion="将英文词汇替换为中文表达",
            ),
            WorldRule(
                id="no_explicit_content",
                name="禁止露骨内容",
                description="叙事不应包含露骨的暴力或色情描写",
                level=GuardLevel.BLOCK,
                rule_type="forbidden_word",
                keywords=["详细性描写", "极端血腥", "虐杀细节"],
                fix_suggestion="使用含蓄的表达方式，淡化露骨描写",
            ),
        ]
        for rule in defaults:
            self.rules[rule.id] = rule

    # ─── 规则管理 ───

    def add_rule(self, rule: WorldRule):
        """添加规则"""
        self.rules[rule.id] = rule

    def remove_rule(self, rule_id: str) -> bool:
        """移除规则"""
        if rule_id in self.rules:
            del self.rules[rule_id]
            return True
        return False

    def get_rule(self, rule_id: str) -> Optional[WorldRule]:
        """获取规则"""
        return self.rules.get(rule_id)

    def list_rules(self) -> List[WorldRule]:
        """列出所有规则"""
        return list(self.rules.values())

    # ─── 核心：叙事校验 ───

    def check_narrative(self, narrative: str,
                        characters: List[str] = None) -> List[GuardViolation]:
        """
        校验叙事文本是否符合世界观规则

        Args:
            narrative: 待校验的叙事文本
            characters: 涉及的角色名列表（可选，用于角色边界检查）

        Returns:
            违规列表
        """
        violations = []

        for rule in self.rules.values():
            if rule.rule_type == "forbidden_word":
                v = self._check_forbidden_words(narrative, rule)
                violations.extend(v)
            elif rule.rule_type == "character_boundary":
                v = self._check_character_boundary(narrative, rule, characters or [])
                violations.extend(v)
            elif rule.rule_type == "scene_rule":
                v = self._check_scene_rule(narrative, rule)
                violations.extend(v)

        self._violation_history.extend(violations)
        return violations

    def _check_forbidden_words(self, text: str, rule: WorldRule) -> List[GuardViolation]:
        """检查禁用词"""
        violations = []
        for keyword in rule.keywords:
            if keyword in text:
                # 提取上下文（关键词前后各 20 字）
                idx = text.index(keyword)
                start = max(0, idx - 20)
                end = min(len(text), idx + len(keyword) + 20)
                context = text[start:end]

                violations.append(GuardViolation(
                    rule_id=rule.id,
                    rule_name=rule.name,
                    level=rule.level,
                    message=f"发现禁用词 '{keyword}'",
                    context=context,
                    fix_suggestion=rule.fix_suggestion,
                ))
        return violations

    def _check_character_boundary(self, text: str, rule: WorldRule,
                                    characters: List[str]) -> List[GuardViolation]:
        """检查角色行为边界"""
        violations = []
        if not self.truth_ledger or not characters:
            return violations

        for char_name in characters:
            cs = self.truth_ledger.character_states.get(char_name)
            if cs is None:
                continue

            # 检查死亡角色是否有行为
            if not cs.is_alive:
                action_keywords = ["说", "走", "跑", "看", "笑", "怒", "想", "做"]
                # 查找角色名附近的动作描述
                for kw in action_keywords:
                    pattern = f"{char_name}{kw}"
                    if pattern in text:
                        violations.append(GuardViolation(
                            rule_id=rule.id,
                            rule_name=rule.name,
                            level=GuardLevel.BLOCK,
                            message=f"已死亡角色 '{char_name}' 出现了行为描述: '{pattern}'",
                            context=text[max(0, text.index(pattern)-10):text.index(pattern)+20],
                            fix_suggestion=f"移除 '{char_name}' 的行为描述，或使用回忆/幻觉形式",
                        ))
                        break

            # 检查境界倒退
            realm = cs.realm
            if realm:
                realm_order = ["练气", "筑基", "金丹", "元婴", "化神", "炼虚", "合体", "大乘", "渡劫"]
                for i, r in enumerate(realm_order):
                    if r in realm:
                        # 检查文本中是否有更低境界的描述
                        for lower_r in realm_order[:i]:
                            pattern = f"{char_name}.*{lower_r}"
                            if lower_r in text and f"跌落{lower_r}" not in text:
                                # 简单检查：如果角色境界是金丹，但文本说他是筑基
                                nearby = text[max(0, text.index(char_name)-10):text.index(char_name)+50] if char_name in text else ""
                                if lower_r in nearby:
                                    violations.append(GuardViolation(
                                        rule_id=rule.id,
                                        rule_name=rule.name,
                                        level=GuardLevel.WARN,
                                        message=f"角色 '{char_name}' 境界({realm})与文本描述({lower_r})不符",
                                        context=nearby,
                                        fix_suggestion=f"检查 '{char_name}' 的境界描述是否正确",
                                    ))
                        break

        return violations

    def _check_scene_rule(self, text: str, rule: WorldRule) -> List[GuardViolation]:
        """检查场景规则"""
        # 预留：基于 condition 文本的 AI 判断
        # 当前只做关键词检查
        return []

    # ─── 便捷方法 ───

    def should_block(self, violations: List[GuardViolation]) -> bool:
        """判断是否有 BLOCK 级别的违规"""
        return any(v.level == GuardLevel.BLOCK for v in violations)

    def get_blocked_keywords(self, narrative: str) -> Set[str]:
        """获取叙事中被阻断的关键词集合"""
        blocked = set()
        for rule in self.rules.values():
            if rule.level == GuardLevel.BLOCK and rule.rule_type == "forbidden_word":
                for kw in rule.keywords:
                    if kw in narrative:
                        blocked.add(kw)
        return blocked

    def filter_narrative(self, narrative: str) -> str:
        """
        过滤叙事文本中的禁用词（替换为 *** ）

        仅替换 BLOCK 级别的 forbidden_word 规则中的关键词。
        """
        filtered = narrative
        for rule in self.rules.values():
            if rule.level == GuardLevel.BLOCK and rule.rule_type == "forbidden_word":
                for kw in rule.keywords:
                    if kw in filtered:
                        filtered = filtered.replace(kw, "***")
        return filtered

    # ─── 报告 ───

    def get_violation_report(self, violations: List[GuardViolation] = None) -> str:
        """生成违规报告"""
        target = violations if violations is not None else self._violation_history
        if not target:
            return "[WorldRuleGuard] 无违规记录，全部通过。"

        lines = ["=" * 50, "世界观规则守卫报告", "=" * 50]
        block_count = sum(1 for v in target if v.level == GuardLevel.BLOCK)
        warn_count = sum(1 for v in target if v.level == GuardLevel.WARN)
        info_count = sum(1 for v in target if v.level == GuardLevel.INFO)

        lines.append(f"阻断: {block_count} | 警告: {warn_count} | 提示: {info_count}")
        lines.append("-" * 50)

        level_tag = {"block": "[BLOCK]", "warn": "[WARN] ", "info": "[INFO] "}
        for v in target:
            tag = level_tag.get(v.level.value, "[?]   ")
            lines.append(f"{tag} [{v.rule_name}] {v.message}")
            if v.context:
                lines.append(f"       上下文: ...{v.context}...")
            if v.fix_suggestion:
                lines.append(f"       建议: {v.fix_suggestion}")

        return "\n".join(lines)

    # ─── 序列化 ───

    def to_dict(self) -> dict:
        return {
            "rules": {rid: r.to_dict() for rid, r in self.rules.items()},
            "violation_history": [v.to_dict() for v in self._violation_history],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "WorldRuleGuard":
        guard = cls()
        guard.rules = {}
        for rid, rdata in data.get("rules", {}).items():
            guard.rules[rid] = WorldRule.from_dict(rdata)
        for vdata in data.get("violation_history", []):
            guard._violation_history.append(GuardViolation(
                rule_id=vdata.get("rule_id", ""),
                rule_name=vdata.get("rule_name", ""),
                level=GuardLevel(vdata.get("level", "warn")),
                message=vdata.get("message", ""),
                context=vdata.get("context", ""),
                fix_suggestion=vdata.get("fix_suggestion", ""),
            ))
        return guard

    # ─── 统计 ───

    def get_stats(self) -> Dict:
        block_rules = sum(1 for r in self.rules.values() if r.level == GuardLevel.BLOCK)
        warn_rules = sum(1 for r in self.rules.values() if r.level == GuardLevel.WARN)

        block_violations = sum(1 for v in self._violation_history if v.level == GuardLevel.BLOCK)
        warn_violations = sum(1 for v in self._violation_history if v.level == GuardLevel.WARN)

        return {
            "total_rules": len(self.rules),
            "block_rules": block_rules,
            "warn_rules": warn_rules,
            "total_violations": len(self._violation_history),
            "block_violations": block_violations,
            "warn_violations": warn_violations,
            "has_truth_ledger": self.truth_ledger is not None,
        }
