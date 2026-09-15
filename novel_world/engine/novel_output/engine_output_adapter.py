# -*- coding: utf-8 -*-
"""
引擎输出适配器 - 将新引擎模块的输出对接到 NovelWriter

核心职责：
  1. 接收 CausalCollisionScheduler 的 CollisionRecord 和章节文本
  2. 转换为 NovelWriter 能处理的格式
  3. 提供 write_chapter_from_engine() 一站式写入接口
  4. 提供章节大纲自动生成

与现有模块的关系：
  - NovelWriter: 实际的文件写入器（chapters/, outline.txt, collision_logs/ 等）
  - CausalCollisionScheduler: 提供 CollisionRecord
  - WorldTimeline: 提供 tick/chapter/scene 上下文
  - SwimlaneManager: 提供角色状态用于快照
  - WorldRuleGuard: 叙事校验（可选）

设计原则：
  - 不修改 NovelWriter 的现有方法
  - 适配器是薄包装层，只做数据转换
  - 一站式调用：一章只需调用一次 write_chapter_from_engine()
"""
import os
import json
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from datetime import datetime


@dataclass
class ChapterData:
    """
    章节数据 - 新引擎的章节输出格式

    与旧引擎的 ChapterTimeline 对应，但字段更简洁。
    """
    chapter_num: int = 0
    chapter_text: str = ""                          # 完整章节正文
    prelude: str = ""                               # 铺垫
    protagonist_action: str = ""                    # 主角行动
    epilogue: str = ""                              # 收尾
    scene: str = ""                                 # 场景
    time_marker: str = ""                           # 时间标记
    tick: int = 0                                   # 对应 tick
    collisions: List[dict] = field(default_factory=list)   # CollisionRecord.to_dict() 列表
    characters: List[str] = field(default_factory=list)     # 出场角色
    skill_data: List[dict] = field(default_factory=list)    # 技能快照数据

    def to_dict(self) -> dict:
        import dataclasses
        return dataclasses.asdict(self)


class EngineOutputAdapter:
    """
    引擎输出适配器

    使用方式：
        # 初始化
        project = NovelProject(title="测试小说", output_dir="./output")
        writer = NovelWriter(project)
        adapter = EngineOutputAdapter(writer)

        # 设置引擎引用（可选）
        adapter.set_timeline(timeline)
        adapter.set_swimlane_manager(sm)

        # 写入一章
        adapter.write_chapter_from_engine(
            chapter_num=1,
            chapter_text="叶凡盘膝而坐...",
            collisions=collision_records,   # List[CollisionRecord]
            characters=["叶凡", "苏瑶"],
            scene="青云宗后山",
        )

        # 导出完整小说
        adapter.export_novel()
    """

    def __init__(self, novel_writer):
        """
        Args:
            novel_writer: NovelWriter 实例
        """
        self.writer = novel_writer
        self.timeline = None
        self.swimlane_manager = None
        self.rule_guard = None

    def set_timeline(self, tl):
        self.timeline = tl

    def set_swimlane_manager(self, sm):
        self.swimlane_manager = sm

    def set_rule_guard(self, guard):
        self.rule_guard = guard

    # ─── 核心方法 ───

    def write_chapter_from_engine(
        self,
        chapter_num: int,
        chapter_text: str,
        collisions: List = None,
        characters: List[str] = None,
        scene: str = "",
        time_marker: str = "",
        prelude: str = "",
        protagonist_action: str = "",
        epilogue: str = "",
        skill_data: List[dict] = None,
        tick: int = 0,
    ) -> str:
        """
        一站式写入章节

        将章节正文、碰撞记录、技能快照、大纲全部写入文件。

        Args:
            chapter_num: 章节编号
            chapter_text: 章节完整正文
            collisions: CollisionRecord 列表（或字典列表）
            characters: 出场角色列表
            scene: 场景
            time_marker: 时间标记
            prelude: 铺垫文本
            protagonist_action: 主角行动
            epilogue: 收尾
            skill_data: 技能快照数据
            tick: 对应的 tick

        Returns:
            章节文件路径
        """
        # 1. 可选：规则守卫校验
        if self.rule_guard is not None and chapter_text:
            violations = self.rule_guard.check_narrative(chapter_text, characters or [])
            if violations:
                # 打印警告但继续写入
                from .engine_output_adapter import _format_violations
                print(f"[EngineOutputAdapter] 章节校验发现 {len(violations)} 个违规")

        # 2. 写入章节正文
        filepath = self._write_chapter_text(chapter_num, chapter_text)

        # 3. 写入碰撞明细
        if collisions:
            collision_dicts = self._convert_collisions(collisions)
            self.writer.save_collision_log(chapter_num, collision_dicts)

        # 4. 写入技能快照
        if skill_data:
            self.writer.save_skill_snapshot(chapter_num, skill_data)

        # 5. 更新大纲
        self._update_outline(
            chapter_num=chapter_num,
            prelude=prelude,
            protagonist_action=protagonist_action,
            epilogue=epilogue,
            collisions=collisions or [],
            characters=characters or [],
        )

        # 6. 更新项目元数据
        self.writer.project.chapters[chapter_num] = chapter_text
        if characters:
            for char_name in characters:
                if char_name not in self.writer.project.goal_tracking:
                    self.writer.project.goal_tracking[char_name] = {
                        "ultimate": "",
                        "current_history": [],
                    }

        # 7. 保存项目
        self.writer.save_project()

        return filepath

    # ─── 内部方法 ───

    def _write_chapter_text(self, chapter_num: int, text: str) -> str:
        """直接写入章节文件"""
        base = self.writer.project.output_dir
        if not base:
            return ""

        chapters_dir = os.path.join(base, "chapters")
        os.makedirs(chapters_dir, exist_ok=True)

        header = f"第{chapter_num}章"
        full_text = f"{header}\n\n{text}\n"

        filename = f"chapter_{chapter_num:03d}.txt"
        filepath = os.path.join(chapters_dir, filename)

        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(full_text)

        return filepath

    def _convert_collisions(self, collisions: List) -> List[dict]:
        """将 CollisionRecord 列表转为字典列表"""
        result = []
        for c in collisions:
            if hasattr(c, 'to_dict'):
                result.append(c.to_dict())
            elif isinstance(c, dict):
                result.append(c)
        return result

    def _update_outline(
        self,
        chapter_num: int,
        prelude: str = "",
        protagonist_action: str = "",
        epilogue: str = "",
        collisions: List = None,
        characters: List[str] = None,
    ):
        """更新大纲文件"""
        base = self.writer.project.output_dir
        if not base:
            return

        lines = [f"第{chapter_num}章"]

        # 碰撞类型摘要
        if collisions:
            types = []
            for c in collisions:
                ct = c.collision_type if hasattr(c, 'collision_type') else c.get('collision_type', '')
                if ct and ct not in types:
                    types.append(ct)
            if types:
                lines.append(f"  [碰撞类型：{'、'.join(types)}]")

        if prelude:
            lines.append(f"  - 铺垫：{prelude[:100]}...")

        if protagonist_action:
            lines.append(f"  - 主角行动：{protagonist_action[:100]}...")

        if characters:
            lines.append(f"  - 出场角色：{'、'.join(characters)}")

        if collisions:
            for c in collisions:
                if hasattr(c, 'description'):
                    desc = c.description
                else:
                    desc = c.get('description', '')
                lines.append(f"  - 碰撞：{desc[:80]}")

        if epilogue:
            lines.append(f"  - 收尾：{epilogue[:100]}...")

        lines.append("")

        outline_text = "\n".join(lines)

        outline_path = os.path.join(base, "outline.txt")
        with open(outline_path, 'a', encoding='utf-8') as f:
            f.write(outline_text)

        self.writer.project.outlines.append({
            "chapter_num": chapter_num,
            "text": outline_text,
        })

    # ─── 便捷方法 ───

    def export_novel(self, format: str = "txt") -> str:
        """导出完整小说"""
        return self.writer.export_novel(format)

    def get_word_count(self) -> int:
        """获取总字数"""
        return self.writer.get_word_count()

    def get_chapter_count(self) -> int:
        """获取章节数"""
        return self.writer.get_chapter_count()

    def get_stats(self) -> Dict:
        """获取项目统计"""
        return {
            "title": self.writer.project.title,
            "chapter_count": self.get_chapter_count(),
            "word_count": self.get_word_count(),
            "collision_log_count": sum(
                len(logs) for logs in self.writer.project.collision_logs.values()
            ),
            "has_timeline": self.timeline is not None,
            "has_swimlane_manager": self.swimlane_manager is not None,
            "has_rule_guard": self.rule_guard is not None,
        }


def _format_violations(violations) -> str:
    """格式化违规列表为字符串"""
    lines = []
    for v in violations:
        level = v.level.value if hasattr(v.level, 'value') else str(v.level)
        lines.append(f"  [{level}] {v.message}")
    return "\n".join(lines)
