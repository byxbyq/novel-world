# -*- coding: utf-8 -*-
"""
碰撞权重新标定模块 — 基于运行时统计反推权重偏移量

使用方式:
    calibrator = WeightCalibrator()
    # 运行期间收集碰撞数据
    calibrator.record(collision_type, collision_subtype, selected)
    # 章节结束后生成报告
    calibrator.export_report("output/weight_calibration_20260808.yaml")
"""

import os
import time
import json
import logging
from collections import defaultdict
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger("WeightCalibrator")

# 标定相关：仅依赖内置库，避免循环导入
try:
    import yaml
    _HAS_YAML = True
except ImportError:
    _HAS_YAML = False


@dataclass
class CollisionRecord:
    """单次碰撞事件记录"""
    collision_type: str
    collision_subtype: str
    weight: int
    selected: bool         # 是否被引擎选中（作为本轮主事件）
    chapter: int
    tick: int
    char_a: str
    char_b: str
    timestamp: float = field(default_factory=time.time)


@dataclass
class TypeStats:
    """某碰撞类型的统计汇总"""
    collision_type: str
    total_occurrences: int = 0          # 总触发次数
    selected_count: int = 0             # 被选中次数
    avg_weight: float = 0.0             # 平均权重
    selection_rate: float = 0.0         # 选中率
    # 建议
    suggested_weight: int = 0
    weight_shift: int = 0
    rationale: str = ""


class WeightCalibrator:
    """运行时权重新标定模块

    工作原理：
    1. 在碰撞引擎每次检测到碰撞事件时调用 record()
    2. 记录 collision_type / subtype / weight / selected
    3. 当数据量足够（可配置 min_samples）时，导出校准报告
    4. 报告基于两种指标：
       a. 选中率 — 某类型事件被选中最频，说明当前权重偏高
       b. 稀有度 — 某类型触发很少但被选中时非常重要，说明权重偏低
    """

    def __init__(self, min_samples: int = 50, report_dir: str = ""):
        self.records: List[CollisionRecord] = []
        self.min_samples = min_samples
        self.report_dir = report_dir or os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))),
            "output"
        )
        self._chapter_samples: Dict[int, int] = defaultdict(int)

    def record(
        self,
        collision_type: str,
        collision_subtype: str,
        weight: int,
        selected: bool,
        chapter: int,
        tick: int,
        char_a: str = "",
        char_b: str = "",
    ):
        """记录一次碰撞事件"""
        r = CollisionRecord(
            collision_type=collision_type,
            collision_subtype=collision_subtype,
            weight=weight,
            selected=selected,
            chapter=chapter,
            tick=tick,
            char_a=char_a,
            char_b=char_b,
        )
        self.records.append(r)
        self._chapter_samples[chapter] += 1

    def _compute_stats(self) -> Dict[str, TypeStats]:
        """按 collision_type 聚合统计"""
        groups: Dict[str, List[CollisionRecord]] = defaultdict(list)
        for r in self.records:
            groups[r.collision_type].append(r)

        stats: Dict[str, TypeStats] = {}
        for ctype, recs in groups.items():
            total = len(recs)
            selected = sum(1 for r in recs if r.selected)
            avg_w = sum(r.weight for r in recs) / max(total, 1)
            sel_rate = selected / max(total, 1)
            stats[ctype] = TypeStats(
                collision_type=ctype,
                total_occurrences=total,
                selected_count=selected,
                avg_weight=avg_w,
                selection_rate=sel_rate,
            )
        return stats

    def _compute_suggestions(
        self, stats: Dict[str, TypeStats]
    ) -> Dict[str, TypeStats]:
        """基于统计反推权重偏移量

        算法（简化版）：
        - 计算全局平均选中率 avg_sel_rate
        - 各类型选中率与全局 avg 对比:
          - sel_rate > avg * 1.5 → 权重偏高，建议下调
          - sel_rate < avg * 0.5 → 权重偏低，建议上调
        - 偏移量 = int((avg_sel_rate - sel_rate) * 100)，钳位在 [-30, 30]
        """
        if not stats:
            return stats

        total_sel = sum(s.selection_rate for s in stats.values())
        avg_sel_rate = total_sel / max(len(stats), 1)

        for ctype, st in stats.items():
            if st.total_occurrences < 5:
                st.rationale = "样本不足（< 5次），无法给出建议"
                st.suggested_weight = int(st.avg_weight)
                st.weight_shift = 0
                continue

            diff = avg_sel_rate - st.selection_rate
            shift = int(diff * 100)
            shift = max(-30, min(30, shift))

            st.weight_shift = shift
            st.suggested_weight = max(0, min(100, int(st.avg_weight) + shift))

            if shift > 5:
                st.rationale = (
                    f"选中率低于均值（{st.selection_rate:.2f} < {avg_sel_rate:.2f}），"
                    f"建议上调 {shift} → {st.suggested_weight}"
                )
            elif shift < -5:
                st.rationale = (
                    f"选中率高于均值（{st.selection_rate:.2f} > {avg_sel_rate:.2f}），"
                    f"建议下调 {abs(shift)} → {st.suggested_weight}"
                )
            else:
                st.rationale = (
                    f"选中率接近均值（{st.selection_rate:.2f} ≈ {avg_sel_rate:.2f}），"
                    f"当前权重合理，无需调整"
                )

        return stats

    def get_summary(self) -> dict:
        """获取当前统计摘要"""
        stats = self._compute_stats()
        stats = self._compute_suggestions(stats)

        total_events = len(self.records)
        total_selected = sum(1 for r in self.records if r.selected)

        return {
            "total_events": total_events,
            "total_selected": total_selected,
            "min_samples": self.min_samples,
            "sufficient_data": total_events >= self.min_samples,
            "types": {
                ctype: asdict(st) for ctype, st in stats.items()
            },
        }

    def get_yaml_report(self) -> str:
        """生成 YAML 格式的标定报告"""
        summary = self.get_summary()

        lines = [
            "# =============================================================================",
            "#  碰撞权重新标定报告",
            f"#  生成时间: {time.strftime('%Y-%m-%d %H:%M:%S')}",
            f"#  总事件数: {summary['total_events']}",
            f"#  总选中数: {summary['total_selected']}",
            f"#  数据充足: {'是' if summary['sufficient_data'] else '否'} (需要 >= {self.min_samples})",
            "# =============================================================================",
            "",
        ]

        if not summary["types"]:
            lines.append("# 无统计数据")
            return "\n".join(lines)

        lines.append("type_stats:")
        for ctype, st in sorted(summary["types"].items()):
            lines.extend([
                f"  {ctype}:",
                f"    total_occurrences: {st['total_occurrences']}",
                f"    selected_count: {st['selected_count']}",
                f"    avg_weight: {st.get('avg_weight', 0):.1f}",
                f"    selection_rate: {st.get('selection_rate', 0):.3f}",
                f"    suggested_weight: {st.get('suggested_weight', 0)}",
                f"    weight_shift: {st.get('weight_shift', 0)}",
                f"    rationale: \"{st.get('rationale', '')}\"",
                "",
            ])

        lines.append("")
        lines.append("# 建议的 weights 配置（可直接替换 weights.yaml 中的对应项）")
        lines.append("suggested_weights:")
        for ctype, st in sorted(summary["types"].items()):
            if st.get("weight_shift", 0) != 0 and st.get("suggested_weight", 0) > 0:
                lines.append(f"  {ctype}: {st['suggested_weight']}  # {st.get('rationale', '')}")

        return "\n".join(lines)

    def export_report(self, filename: str = "") -> str:
        """导出标定报告到文件，返回文件路径"""
        if not filename:
            filename = os.path.join(
                self.report_dir,
                f"weight_calibration_{time.strftime('%Y%m%d_%H%M%S')}.yaml",
            )

        os.makedirs(os.path.dirname(filename) or ".", exist_ok=True)
        report = self.get_yaml_report()

        with open(filename, "w", encoding="utf-8") as f:
            f.write(report)

        logger.info("标定报告已导出: %s", filename)
        return filename

    def export_json_records(self, filename: str = "") -> str:
        """导出所有原始记录为 JSON（供外部可视化分析）"""
        if not filename:
            filename = os.path.join(
                self.report_dir,
                f"collision_records_{time.strftime('%Y%m%d_%H%M%S')}.json",
            )

        os.makedirs(os.path.dirname(filename) or ".", exist_ok=True)
        records_data = [asdict(r) for r in self.records]

        with open(filename, "w", encoding="utf-8") as f:
            json.dump(records_data, f, ensure_ascii=False, indent=2)

        logger.info("原始记录已导出: %s (%d 条)", filename, len(records_data))
        return filename

    def reset(self):
        """清空所有历史记录（用于新章节/新会话初始化）"""
        self.records.clear()
        self._chapter_samples.clear()
        logger.info("标定器已重置")
