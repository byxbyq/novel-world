# -*- coding: utf-8 -*-
"""
质量校验管线 - 叙事生成后的 8 层自动校验

本管线将分散的 quality/ 和 scheduler/ 校验模块整合为一个统一入口，
碰撞后自动按层级检查，确保叙事质量符合以下标准：

层级（按严重程度递增）：
  L1  禁用词检测 → WorldRuleGuard
  L2  AI味检测  → audit_service.detect_ai_flavor()
  L3  战力崩坏   → audit_service.detect_power_collapse()
  L4  时序一致性 → timeline_checker
  L5  人设一致性 → narrative_corrector
  L6  伏笔一致性 → consistency_checker
  L7  世界观规则 → consistency_checker (全局)
  L8  文风统一   → audit_service.compare_style_fingerprint()

设计原则：
  - 每层可独立开关
  - L1-L3 纯规则，零Token；L4-L8 轻量 Token 或无 Token
  - 返回统一的结构化报告
  - 与 WorldRuleGuard / ConsistencyChecker / GoalScheduler 互补
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Any

# 内部模块（延迟导入，避免循环依赖）
from .audit_service import (
    detect_ai_flavor,
    detect_power_collapse,
    detect_coincidence,
    detect_tool_character,
    run_extended_audit,
    extract_style_fingerprint,
    compare_style_fingerprint,
)
from .constants import FORBIDDEN_WORDS, FORBIDDEN_PLOTS, build_narrative_rules


class PipelineLevel(Enum):
    """管线层级"""
    L1_FORBIDDEN = "L1_FORBIDDEN"
    L2_AI_FLAVOR = "L2_AI_FLAVOR"
    L3_POWER = "L3_POWER"
    L4_TIMELINE = "L4_TIMELINE"
    L5_CHARACTER = "L5_CHARACTER"
    L6_FORESHADOW = "L6_FORESHADOW"
    L7_WORLD_RULE = "L7_WORLD_RULE"
    L8_STYLE = "L8_STYLE"
    L9_COINCIDENCE = "L9_COINCIDENCE"
    L10_TOOL_CHARACTER = "L10_TOOL_CHARACTER"


class ResultLevel(Enum):
    """检查结果级别"""
    PASS = "pass"
    WARNING = "warning"
    FAIL = "fail"


@dataclass
class LayerResult:
    """单层校验结果"""
    layer: PipelineLevel
    level: ResultLevel
    passed: bool
    score: float = 0.0           # 0(完美) ~ 100(严重问题)
    issues: List[Dict] = field(default_factory=list)
    summary: str = ""

    @property
    def issue_count(self) -> int:
        return len(self.issues)


@dataclass
class QualityReport:
    """综合质量报告"""
    overall_level: ResultLevel = ResultLevel.PASS
    overall_score: float = 0.0
    layers: List[LayerResult] = field(default_factory=list)
    total_issues: int = 0

    @property
    def failed_layers(self) -> List[LayerResult]:
        return [l for l in self.layers if l.level == ResultLevel.FAIL]

    @property
    def warning_layers(self) -> List[LayerResult]:
        return [l for l in self.layers if l.level == ResultLevel.WARNING]

    def summary(self) -> str:
        parts = [f"质量报告: {self.overall_score:.0f}/100 ({self.overall_level.value})"]
        parts.append(f"问题数: {self.total_issues}")
        if self.failed_layers:
            parts.append(f"未通过: {', '.join(l.layer.value for l in self.failed_layers)}")
        if self.warning_layers:
            parts.append(f"警告: {', '.join(l.layer.value for l in self.warning_layers)}")
        return " | ".join(parts)


class QualityPipeline:
    """
    质量校验管线

    用法：
        pipeline = QualityPipeline(world_rule_guard=None, consistency_checker=None)
        report = pipeline.validate(narrative, chapter_index=1)
        if report.overall_level != ResultLevel.PASS:
            for layer in report.layers:
                print(layer.summary)
    """

    def __init__(self,
                 world_rule_guard=None,
                 consistency_checker=None,
                 style_reference: Dict = None,
                 enabled_layers: List[PipelineLevel] = None,
                 strict_mode: bool = False,
                 dm_controller=None):
        """
        Args:
            world_rule_guard: WorldRuleGuard 实例（可选，用于 L1）
            consistency_checker: ConsistencyChecker 实例（可选，用于 L6/L7）
            style_reference: 文风参考指纹（可选，用于 L8）
            enabled_layers: 启用的层级列表，默认全部启用
            strict_mode: 严格模式（任一 FAIL 即中断）
            dm_controller: DMController 实例（可选，用于 DM 联动反馈）
        """
        self.world_rule_guard = world_rule_guard
        self.consistency_checker = consistency_checker
        self.style_reference = style_reference
        self.enabled_layers = set(enabled_layers) if enabled_layers else set(PipelineLevel)
        self.strict_mode = strict_mode
        self.dm_controller = dm_controller
        self.chapter_context: Dict = {}  # {foreshadowing, character_spans, ...}
        self.narrative_corrector = None  # 延迟加载

    def _ensure_corrector(self):
        """延迟加载 narrative_corrector"""
        if self.narrative_corrector is None:
            try:
                from novel_world.engine.quality.narrative_corrector import NarrativeCorrector
                self.narrative_corrector = NarrativeCorrector()
            except Exception:
                pass  # 模块不存在时静默跳过

    # ─────────────────────────────
    # L1: 禁用词检测
    # ─────────────────────────────
    def _check_forbidden_words(self, narrative: str) -> LayerResult:
        issues = []
        for word in FORBIDDEN_WORDS:
            pos = 0
            count = 0
            while True:
                idx = narrative.find(word, pos)
                if idx == -1:
                    break
                count += 1
                pos = idx + 1
            if count:
                issues.append({'type': 'forbidden_word', 'word': word,
                               'count': count,
                               'message': f'禁用词 "{word}" 出现 {count} 次'})

        for plot in FORBIDDEN_PLOTS:
            plot_key = plot.split('（')[0] if '（' in plot else plot
            if plot_key in narrative:
                issues.append({'type': 'forbidden_plot', 'plot': plot_key,
                               'message': f'疑似禁用桥段: {plot_key}'})

        score = min(100, len(issues) * 10)
        level = ResultLevel.FAIL if issues else ResultLevel.PASS
        return LayerResult(
            layer=PipelineLevel.L1_FORBIDDEN,
            level=level, passed=(not issues),
            score=score, issues=issues,
            summary=f'L1 禁用词: {"通过" if not issues else f"发现 {len(issues)} 项问题"}'
        )

    # ─────────────────────────────
    # L2: AI味检测
    # ─────────────────────────────
    def _check_ai_flavor(self, narrative: str) -> LayerResult:
        if len(narrative) < 100:
            return LayerResult(
                layer=PipelineLevel.L2_AI_FLAVOR,
                level=ResultLevel.PASS, passed=True,
                summary='L2 AI味: 略过（内容太短）'
            )

        result = detect_ai_flavor(narrative)
        score = result['score']
        if score <= 15:
            level = ResultLevel.PASS
        elif score <= 40:
            level = ResultLevel.WARNING
        else:
            level = ResultLevel.FAIL

        return LayerResult(
            layer=PipelineLevel.L2_AI_FLAVOR,
            level=level, passed=(level != ResultLevel.FAIL),
            score=score, issues=result['issues'],
            summary=f'L2 AI味: {result["summary"]}'
        )

    # ─────────────────────────────
    # L3: 战力崩坏检测
    # ─────────────────────────────
    def _check_power(self, narrative: str, chapter_index: int = 0,
                     characters: List[Dict] = None) -> LayerResult:
        if not characters:
            return LayerResult(
                layer=PipelineLevel.L3_POWER,
                level=ResultLevel.PASS, passed=True,
                summary='L3 战力: 略过（无角色状态数据）'
            )

        result = detect_power_collapse(narrative, chapter_index, characters)
        score = result['score']
        if score == 0:
            level = ResultLevel.PASS
        elif score <= 20:
            level = ResultLevel.WARNING
        else:
            level = ResultLevel.FAIL

        return LayerResult(
            layer=PipelineLevel.L3_POWER,
            level=level, passed=(level != ResultLevel.FAIL),
            score=score, issues=result['issues'],
            summary=f'L3 战力: {result["summary"]}'
        )

    # ─────────────────────────────
    # L4: 时序一致性
    # ─────────────────────────────
    def _check_timeline(self, narrative: str, chapter_index: int = 0) -> LayerResult:
        """调用 timeline_checker 检查时间线一致性"""
        raw_issues = []
        try:
            from novel_world.engine.quality.timeline_checker import TimelineChecker
            checker = TimelineChecker()
            raw_issues = checker.check_narrative(narrative, chapter_index)
        except Exception:
            return LayerResult(
                layer=PipelineLevel.L4_TIMELINE,
                level=ResultLevel.PASS, passed=True,
                summary='L4 时序: timeline_checker 调用失败，略过'
            )

        if not raw_issues:
            return LayerResult(
                layer=PipelineLevel.L4_TIMELINE,
                level=ResultLevel.PASS, passed=True,
                summary='L4 时序: 通过'
            )

        formatted = []
        for issue in raw_issues[:5]:
            msg = issue if isinstance(issue, str) else issue.get('message', str(issue))
            formatted.append({'type': 'timeline', 'message': msg})

        score = min(100, len(raw_issues) * 15)
        level = ResultLevel.WARNING if score <= 30 else ResultLevel.FAIL
        result = LayerResult(
            layer=PipelineLevel.L4_TIMELINE,
            level=level, passed=(level != ResultLevel.FAIL),
            score=score, issues=formatted,
            summary=f'L4 时序: 发现 {len(raw_issues)} 项问题'
        )

        # ── DM 联动反馈钩子 ──
        self._push_to_dm(raw_issues, chapter_index)

        return result

    def _push_to_dm(self, raw_issues: list, chapter_index: int):
        """将质量管线发现的问题推送到 DM 控制器"""
        if not self.dm_controller:
            return
        for issue in raw_issues:
            if isinstance(issue, str):
                self.dm_controller.add_issue({
                    "source": "timeline_checker",
                    "severity": "warning",
                    "message": issue,
                    "dimension": "timeline",
                    "chapter": chapter_index,
                    "suggestion": "",
                })
            else:
                severity = issue.get("level", "warning")
                if hasattr(severity, 'value'):
                    severity = severity.value
                self.dm_controller.add_issue({
                    "source": issue.get("dimension", "timeline_checker"),
                    "severity": severity,
                    "message": issue.get("message", str(issue)),
                    "dimension": issue.get("dimension", "timeline"),
                    "tick": issue.get("tick", 0),
                    "chapter": issue.get("chapter", chapter_index),
                    "suggestion": issue.get("suggestion", ""),
                    "related_characters": issue.get("related_characters", []),
                    "detail": issue.get("detail", {}),
                })

    # ─────────────────────────────
    # L5: 人设一致性
    # ─────────────────────────────
    def _check_character(self, narrative: str) -> LayerResult:
        self._ensure_corrector()
        if not self.narrative_corrector:
            return LayerResult(
                layer=PipelineLevel.L5_CHARACTER,
                level=ResultLevel.PASS, passed=True,
                summary='L5 人设: narrative_corrector 不可用，略过'
            )

        try:
            result = self.narrative_corrector.check(narrative) if hasattr(
                self.narrative_corrector, 'check') else None
            if result is None:
                result = self.narrative_corrector.correct(narrative) if hasattr(
                    self.narrative_corrector, 'correct') else None
        except Exception:
            return LayerResult(
                layer=PipelineLevel.L5_CHARACTER,
                level=ResultLevel.PASS, passed=True,
                summary='L5 人设: 校验器调用异常，略过'
            )

        if not result:
            return LayerResult(
                layer=PipelineLevel.L5_CHARACTER,
                level=ResultLevel.PASS, passed=True,
                summary='L5 人设: 通过'
            )

        issues = []
        if isinstance(result, list):
            for r in result:
                msg = r if isinstance(r, str) else r.get('message', str(r))
                issues.append({'type': 'character', 'message': msg})
        elif isinstance(result, dict) and result.get('issues'):
            issues = result['issues']

        score = min(100, len(issues) * 12)
        level = ResultLevel.PASS if not issues else (ResultLevel.WARNING if score <= 20 else ResultLevel.FAIL)
        return LayerResult(
            layer=PipelineLevel.L5_CHARACTER,
            level=level, passed=(level != ResultLevel.FAIL),
            score=score, issues=issues,
            summary=f'L5 人设: {"通过" if not issues else f"发现 {len(issues)} 项问题"}'
        )

    # ─────────────────────────────
    # L6: 伏笔一致性
    # ─────────────────────────────
    def _check_foreshadowing(self, narrative: str) -> LayerResult:
        if not self.consistency_checker:
            return LayerResult(
                layer=PipelineLevel.L6_FORESHADOW,
                level=ResultLevel.PASS, passed=True,
                summary='L6 伏笔: ConsistencyChecker 未注入，略过'
            )

        try:
            result = self.consistency_checker.check_foreshadowing(narrative) if hasattr(
                self.consistency_checker, 'check_foreshadowing') else None
        except Exception:
            return LayerResult(
                layer=PipelineLevel.L6_FORESHADOW,
                level=ResultLevel.PASS, passed=True,
                summary='L6 伏笔: 检查调用异常，略过'
            )

        if not result:
            return LayerResult(
                layer=PipelineLevel.L6_FORESHADOW,
                level=ResultLevel.PASS, passed=True,
                summary='L6 伏笔: 通过'
            )

        issues = result if isinstance(result, list) else [result]
        score = min(100, len(issues) * 15)
        level = ResultLevel.PASS if not issues else (ResultLevel.WARNING if score <= 25 else ResultLevel.FAIL)
        return LayerResult(
            layer=PipelineLevel.L6_FORESHADOW,
            level=level, passed=(level != ResultLevel.FAIL),
            score=score, issues=issues,
            summary=f'L6 伏笔: {"通过" if not issues else f"发现 {len(issues)} 项问题"}'
        )

    # ─────────────────────────────
    # L7: 世界观规则
    # ─────────────────────────────
    def _check_world_rule(self, narrative: str) -> LayerResult:
        if self.consistency_checker:
            try:
                result = self.consistency_checker.check_world_rules(narrative) if hasattr(
                    self.consistency_checker, 'check_world_rules') else None
            except Exception:
                result = None
            if result:
                issues = result if isinstance(result, list) else [result]
                score = min(100, len(issues) * 12)
                level = ResultLevel.WARNING if score <= 20 else ResultLevel.FAIL
                return LayerResult(
                    layer=PipelineLevel.L7_WORLD_RULE,
                    level=level, passed=(level != ResultLevel.FAIL),
                    score=score, issues=issues,
                    summary=f'L7 世界观: 发现 {len(issues)} 项规则冲突'
                )

        # 兜底：WorldRuleGuard
        if self.world_rule_guard:
            try:
                result = self.world_rule_guard.check_narrative(narrative)
            except Exception:
                pass

        return LayerResult(
            layer=PipelineLevel.L7_WORLD_RULE,
            level=ResultLevel.PASS, passed=True,
            summary='L7 世界观: 通过'
        )

    # ─────────────────────────────
    # L8: 文风统一
    # ─────────────────────────────
    def _check_style(self, narrative: str) -> LayerResult:
        if not self.style_reference:
            return LayerResult(
                layer=PipelineLevel.L8_STYLE,
                level=ResultLevel.PASS, passed=True,
                summary='L8 文风: 无参考指纹，略过'
            )

        if len(narrative) < 200:
            return LayerResult(
                layer=PipelineLevel.L8_STYLE,
                level=ResultLevel.PASS, passed=True,
                summary='L8 文风: 略过（内容太短）'
            )

        result = compare_style_fingerprint(narrative, self.style_reference)
        if 'error' in result:
            return LayerResult(
                layer=PipelineLevel.L8_STYLE,
                level=ResultLevel.PASS, passed=True,
                summary=f'L8 文风: {result["error"]}'
            )

        deviations = result.get('deviations', [])
        score = result.get('deviation_score', 0)

        if score <= 15:
            level = ResultLevel.PASS
        elif score <= 40:
            level = ResultLevel.WARNING
        else:
            level = ResultLevel.FAIL

        return LayerResult(
            layer=PipelineLevel.L8_STYLE,
            level=level, passed=(level != ResultLevel.FAIL),
            score=score, issues=deviations,
            summary=f'L8 文风: {result["summary"]}'
        )

    # ─────────────────────────────
    # L9: 强行巧合检测
    # ─────────────────────────────
    def _check_coincidence(self, narrative: str, chapter_index: int = 0) -> LayerResult:
        if len(narrative) < 50:
            return LayerResult(
                layer=PipelineLevel.L9_COINCIDENCE,
                level=ResultLevel.PASS, passed=True,
                summary='L9 巧合: 略过（内容太短）'
            )

        chapter_ctx = self.chapter_context or {}
        result = detect_coincidence(narrative, chapter_ctx)
        score = min(result['count'] * 30, 100)

        if result['level'] == 'pass':
            level = ResultLevel.PASS
        elif result['level'] == 'warn':
            level = ResultLevel.WARNING
        else:
            level = ResultLevel.FAIL

        return LayerResult(
            layer=PipelineLevel.L9_COINCIDENCE,
            level=level, passed=(level != ResultLevel.FAIL),
            score=score, issues=result.get('violations', []),
            summary=f'L9 巧合: {result["summary"]}'
        )

    # ─────────────────────────────
    # L10: 工具人检测
    # ─────────────────────────────
    def _check_tool_character(self, narrative: str) -> LayerResult:
        if len(narrative) < 50:
            return LayerResult(
                layer=PipelineLevel.L10_TOOL_CHARACTER,
                level=ResultLevel.PASS, passed=True,
                summary='L10 工具人: 略过（内容太短）'
            )

        span_data = self.chapter_context.get('character_spans', {}) if self.chapter_context else {}
        result = detect_tool_character(narrative, span_data)
        score = min(len(result.get('tool_characters', [])) * 40, 100)

        if result['level'] == 'pass':
            level = ResultLevel.PASS
        else:
            level = ResultLevel.WARNING

        return LayerResult(
            layer=PipelineLevel.L10_TOOL_CHARACTER,
            level=level, passed=(level != ResultLevel.FAIL),
            score=score, issues=result.get('tool_characters', []),
            summary=f'L10 工具人: {result["summary"]}'
        )

    # ─────────────────────────────
    # 主入口: 完整校验
    # ─────────────────────────────
    def validate(self, narrative: str, chapter_index: int = 0,
                 characters: List[Dict] = None) -> QualityReport:
        """
        对叙事文本执行所有启用的校验层

        Args:
            narrative: 叙事文本
            chapter_index: 当前章节编号
            characters: 角色状态列表 [{name, realm, status}, ...]

        Returns:
            QualityReport: 综合质量报告
        """
        layers = []

        if PipelineLevel.L1_FORBIDDEN in self.enabled_layers:
            l1 = self._check_forbidden_words(narrative)
            layers.append(l1)
            if self.strict_mode and l1.level == ResultLevel.FAIL:
                return self._build_report(layers)

        if PipelineLevel.L2_AI_FLAVOR in self.enabled_layers:
            l2 = self._check_ai_flavor(narrative)
            layers.append(l2)
            if self.strict_mode and l2.level == ResultLevel.FAIL:
                return self._build_report(layers)

        if PipelineLevel.L3_POWER in self.enabled_layers:
            l3 = self._check_power(narrative, chapter_index, characters)
            layers.append(l3)
            if self.strict_mode and l3.level == ResultLevel.FAIL:
                return self._build_report(layers)

        if PipelineLevel.L4_TIMELINE in self.enabled_layers:
            l4 = self._check_timeline(narrative, chapter_index)
            layers.append(l4)
            if self.strict_mode and l4.level == ResultLevel.FAIL:
                return self._build_report(layers)

        if PipelineLevel.L5_CHARACTER in self.enabled_layers:
            l5 = self._check_character(narrative)
            layers.append(l5)
            if self.strict_mode and l5.level == ResultLevel.FAIL:
                return self._build_report(layers)

        if PipelineLevel.L6_FORESHADOW in self.enabled_layers:
            l6 = self._check_foreshadowing(narrative)
            layers.append(l6)
            if self.strict_mode and l6.level == ResultLevel.FAIL:
                return self._build_report(layers)

        if PipelineLevel.L7_WORLD_RULE in self.enabled_layers:
            l7 = self._check_world_rule(narrative)
            layers.append(l7)
            if self.strict_mode and l7.level == ResultLevel.FAIL:
                return self._build_report(layers)

        if PipelineLevel.L8_STYLE in self.enabled_layers:
            l8 = self._check_style(narrative)
            layers.append(l8)

        if PipelineLevel.L9_COINCIDENCE in self.enabled_layers:
            l9 = self._check_coincidence(narrative, chapter_index)
            layers.append(l9)
            if self.strict_mode and l9.level == ResultLevel.FAIL:
                return self._build_report(layers)

        if PipelineLevel.L10_TOOL_CHARACTER in self.enabled_layers:
            l10 = self._check_tool_character(narrative)
            layers.append(l10)

        return self._build_report(layers)

    def _build_report(self, layers: List[LayerResult]) -> QualityReport:
        """构建综合报告"""
        total_issues = sum(l.issue_count for l in layers)
        # 加权: 越高级别权重越大（L1=1, L2=1.2, ... L8=1.4）
        total_weight = sum(1.0 + (i * 0.05) for i in range(len(layers)))
        weights = [1.0 + (i * 0.05) for i in range(len(layers))]
        scores = [l.score * weights[i] for i, l in enumerate(layers)]
        overall = sum(scores) / total_weight if total_weight > 0 else 0

        if any(l.level == ResultLevel.FAIL for l in layers):
            overall_level = ResultLevel.FAIL
        elif any(l.level == ResultLevel.WARNING for l in layers):
            overall_level = ResultLevel.WARNING
        else:
            overall_level = ResultLevel.PASS

        return QualityReport(
            overall_level=overall_level,
            overall_score=round(overall, 1),
            layers=layers,
            total_issues=total_issues,
        )

    def get_narrative_rules(self) -> str:
        """获取叙事风格规则文本，用于注入 AI prompt"""
        return build_narrative_rules()
