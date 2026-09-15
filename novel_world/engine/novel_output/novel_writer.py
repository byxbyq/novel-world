# -*- coding: utf-8 -*-
"""
小说沉淀层 - 将碰撞引擎的输出聚合为完整小说
对接书斋V65的文件格式：chapters/chapter_NNN.txt + outline.txt

输出结构：
  {output_dir}/
    chapters/
      chapter_001.txt
      chapter_002.txt
      ...
    outline.txt           # 全书大纲
    snapshots/
      snapshot_ch001.json # 每章角色技能快照
      ...
    collision_logs/
      collision_ch001.json # 每章碰撞明细
      ...
    novel.txt             # 导出的完整小说
"""
import os
import json
import logging
from dataclasses import dataclass, field
from typing import List, Dict, Optional, TYPE_CHECKING
from datetime import datetime

if TYPE_CHECKING:
    from ..collision.collision_engine import ChapterTimeline, CollisionEvent

logger = logging.getLogger(__name__)


@dataclass
class NovelProject:
    """小说项目 - 管理一部小说的全部元数据和输出"""
    title: str = ""
    author: str = "AI"
    genre: str = ""                # 题材：玄幻/都市/修仙等
    output_dir: str = ""           # 输出根目录

    # 章节管理
    chapters: Dict[int, str] = field(default_factory=dict)          # chapter_num -> 正文
    outlines: List[Dict] = field(default_factory=list)              # 章节大纲列表

    # 角色技能清单（每章快照）
    skill_snapshots: Dict[int, List[Dict]] = field(default_factory=dict)

    # 碰撞明细（每章）
    collision_logs: Dict[int, List[Dict]] = field(default_factory=dict)

    # 人物目标追踪
    goal_tracking: Dict[str, Dict] = field(default_factory=dict)    # char_name -> {ultimate, current_history}

    def to_dict(self) -> Dict:
        """序列化为字典，用于项目持久化"""
        return {
            "title": self.title,
            "author": self.author,
            "genre": self.genre,
            "output_dir": self.output_dir,
            "chapters": self.chapters,
            "outlines": self.outlines,
            "skill_snapshots": self.skill_snapshots,
            "collision_logs": self.collision_logs,
            "goal_tracking": self.goal_tracking,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> 'NovelProject':
        """从字典反序列化"""
        return cls(
            title=data.get("title", ""),
            author=data.get("author", "AI"),
            genre=data.get("genre", ""),
            output_dir=data.get("output_dir", ""),
            chapters=data.get("chapters", {}),
            outlines=data.get("outlines", []),
            skill_snapshots=data.get("skill_snapshots", {}),
            collision_logs=data.get("collision_logs", {}),
            goal_tracking=data.get("goal_tracking", {}),
        )


class NovelWriter:
    """
    小说沉淀器
    核心职责：
      1. 接收 ChapterTimeline，写入章节文件
      2. 维护大纲（追加式更新）
      3. 保存每章的技能快照和碰撞明细
      4. 导出完整小说（TXT格式，后续可扩展EPUB）
      5. 导出章节填写模版（用于人工审阅）
    """

    def __init__(self, project: NovelProject):
        """
        初始化小说沉淀器

        Args:
            project: NovelProject 实例，包含项目元数据和输出目录
        """
        self.project = project
        self._ensure_dirs()

    def _ensure_dirs(self):
        """确保输出目录及子目录存在"""
        base = self.project.output_dir
        if not base:
            logger.warning("NovelWriter：未设置输出目录")
            return

        # 创建所有必要的子目录
        subdirs = [
            "",                  # 根目录
            "chapters",          # 章节正文
            "snapshots",         # 技能快照 + 世界快照
            "collision_logs",    # 碰撞明细
            "outline_chapters",  # 每章独立大纲
        ]
        for subdir in subdirs:
            full_path = os.path.join(base, subdir) if subdir else base
            os.makedirs(full_path, exist_ok=True)

        logger.debug(f"NovelWriter：输出目录已就绪 {base}")

    def write_chapter(self, chapter: 'ChapterTimeline'):
        """
        写入一个章节到文件
        文件路径：{output_dir}/chapters/chapter_{NNN:03d}.txt

        Args:
            chapter: ChapterTimeline 对象，包含聚合后的章节正文
        """
        if not chapter:
            logger.warning("NovelWriter：收到空章节，跳过写入")
            return

        chapter_num = chapter.chapter_num
        chapter_text = chapter.chapter_text or ""

        # 如果没有聚合正文，尝试从碰撞事件拼接
        if not chapter_text:
            parts = []
            if chapter.prelude:
                parts.append(chapter.prelude)
            if chapter.protagonist_action:
                parts.append(chapter.protagonist_action)
            for es in chapter.entry_scenes:
                if es.entry_narrative:
                    parts.append(es.entry_narrative)
            for c in chapter.collisions:
                if c.narrative:
                    parts.append(c.narrative)
            if chapter.epilogue:
                parts.append(chapter.epilogue)
            chapter_text = "\n\n".join(parts)

        if not chapter_text.strip():
            logger.warning(f"NovelWriter：第{chapter_num}章内容为空，跳过写入")
            return

        # 构建章节标题
        header = f"第{chapter_num}章"
        full_text = f"{header}\n\n{chapter_text}\n"

        # 写入文件
        filename = f"chapter_{chapter_num:03d}.txt"
        filepath = os.path.join(self.project.output_dir, "chapters", filename)

        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(full_text)
            logger.info(f"NovelWriter：第{chapter_num}章已写入 {filename}（{len(full_text)}字）")
        except Exception as e:
            logger.error(f"NovelWriter：写入第{chapter_num}章失败: {e}")
            raise

        # 更新内存中的章节记录
        self.project.chapters[chapter_num] = chapter_text

    def update_outline(self, chapter: 'ChapterTimeline'):
        """
        更新大纲
        将章节概要追加到 {output_dir}/outline.txt

        大纲格式：
          第N章 [碰撞类型摘要]
          - 铺垫：...
          - 主角行动：...
          - 入场角色：...
          - 碰撞事件：...
          - 收尾：...

        Args:
            chapter: ChapterTimeline 对象
        """
        if not chapter:
            return

        chapter_num = chapter.chapter_num

        # 构建大纲条目
        lines = [f"第{chapter_num}章"]

        # 碰撞类型摘要
        collision_types = [c.collision_type for c in chapter.collisions if c.collision_type]
        if collision_types:
            type_summary = "、".join(dict.fromkeys(collision_types))  # 去重保序
            lines.append(f"  [碰撞类型：{type_summary}]")

        # 铺垫
        if chapter.prelude:
            lines.append(f"  - 铺垫：{chapter.prelude[:100]}{'...' if len(chapter.prelude) > 100 else ''}")

        # 主角行动
        if chapter.protagonist_action:
            lines.append(
                f"  - 主角行动：{chapter.protagonist_action[:100]}"
                f"{'...' if len(chapter.protagonist_action) > 100 else ''}"
            )

        # 入场角色
        if chapter.entry_scenes:
            entry_names = [es.character_name for es in chapter.entry_scenes if es.character_name]
            if entry_names:
                lines.append(f"  - 入场角色：{'、'.join(entry_names)}")

        # 碰撞事件
        for c in chapter.collisions:
            lines.append(
                f"  - 碰撞：{c.char_a_name} vs {c.char_b_name}"
                f" [{c.collision_type}] {c.collision_reason[:60]}"
            )

        # 收尾
        if chapter.epilogue:
            lines.append(f"  - 收尾：{chapter.epilogue[:100]}{'...' if len(chapter.epilogue) > 100 else ''}")

        lines.append("")  # 空行分隔

        outline_text = "\n".join(lines)

        # 写入大纲文件（追加模式）
        outline_path = os.path.join(self.project.output_dir, "outline.txt")
        try:
            with open(outline_path, 'a', encoding='utf-8') as f:
                f.write(outline_text)
            logger.info(f"NovelWriter：大纲已更新（第{chapter_num}章）")
        except Exception as e:
            logger.error(f"NovelWriter：更新大纲失败: {e}")
            raise

        # 更新内存中的大纲记录
        self.project.outlines.append({
            "chapter_num": chapter_num,
            "text": outline_text,
        })

    def save_skill_snapshot(self, chapter_num: int, skill_data: list):
        """
        保存本章角色技能清单
        文件路径：{output_dir}/snapshots/snapshot_ch{NNN:03d}.json

        Args:
            chapter_num: 章节编号
            skill_data: 技能数据列表，每项为包含角色名和技能信息的字典
                       示例：[{"name": "张三", "skills": ["剑术", "心眼"]}, ...]
        """
        if not skill_data:
            logger.debug(f"NovelWriter：第{chapter_num}章无技能数据，跳过")
            return

        filename = f"snapshot_ch{chapter_num:03d}.json"
        filepath = os.path.join(self.project.output_dir, "snapshots", filename)

        snapshot = {
            "chapter_num": chapter_num,
            "timestamp": datetime.now().isoformat(),
            "characters": skill_data,
        }

        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(snapshot, f, ensure_ascii=False, indent=2)
            logger.info(f"NovelWriter：第{chapter_num}章技能快照已保存")
        except Exception as e:
            logger.error(f"NovelWriter：保存技能快照失败: {e}")
            raise

        # 更新内存记录
        self.project.skill_snapshots[chapter_num] = skill_data

    def save_chapter_snapshot(self, chapter_index: int, world_state=None,
                               characters: list = None):
        """
        保存章节世界快照（角色状态/位置/关系等）。

        文件路径：{output_dir}/snapshots/chapter_snapshot_ch{NNN:03d}.json

        Args:
            chapter_index: 章节编号
            world_state: WorldState 实例（可选）
            characters: 角色列表（可选）
        """
        from datetime import datetime as dt

        snapshot = {
            "chapter_index": chapter_index,
            "timestamp": dt.now().isoformat(),
            "world_state": {},
            "characters": [],
        }

        if world_state and hasattr(world_state, 'to_dict'):
            snapshot["world_state"] = world_state.to_dict()
        if characters:
            for c in characters:
                snapshot["characters"].append({
                    "name": getattr(c, 'name', ''),
                    "pos": getattr(c, 'pos', (0, 0)),
                    "goal": getattr(c, 'goal', ''),
                    "emotion": getattr(c, 'emotion', ''),
                    "alive": getattr(c, 'alive', True),
                })

        filename = f"chapter_snapshot_ch{chapter_index:03d}.json"
        filepath = os.path.join(self.project.output_dir, "snapshots", filename)
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(snapshot, f, ensure_ascii=False, indent=2)
            logger.info(f"NovelWriter：第{chapter_index}章世界快照已保存")
        except Exception as e:
            logger.error(f"NovelWriter：保存快照失败: {e}")

    def update_outline_smart(self, chapter: 'ChapterTimeline', chapter_index: int = 0):
        """
        大纲智能同步更新：合并/更新已有条目而非简单追加。

        与 update_outline() 的差异：
        - 检测已有条目，若本章与已有章节大纲内容冲突则合并
        - 若本章是已有章节大纲的延续则追加补充
        - 若本章是新信息则追加新条目

        Args:
            chapter: 已收尾的 ChapterTimeline
            chapter_index: 章节编号
        """
        # 构建新大纲文本（与 update_outline 相同的基础逻辑）
        collisions = getattr(chapter, 'collisions', []) or []
        entry_scenes = getattr(chapter, 'entry_scenes', []) or []
        chapter_num = getattr(chapter, 'chapter_num', chapter_index) or chapter_index

        lines = [f"## 第{chapter_num}章大纲"]

        for coll in collisions:
            a = getattr(coll, 'char_a_name', '?')
            b = getattr(coll, 'char_b_name', '?')
            ctype = getattr(coll, 'collision_type', '?')
            lines.append(f"- [{ctype}] {a} vs {b}")

        for es in entry_scenes:
            name = getattr(es, 'character_name', '?')
            lines.append(f"- [入场] {name}登场")

        new_outline = "\n".join(lines)

        # 写入独立章节大纲文件（按章节分离，便于智能管理）
        chapter_outline_path = os.path.join(
            self.project.output_dir, "outline_chapters",
            f"outline_ch{chapter_num:03d}.txt"
        )
        try:
            with open(chapter_outline_path, 'w', encoding='utf-8') as f:
                f.write(new_outline)
        except Exception as e:
            logger.error(f"NovelWriter：写入章节大纲失败: {e}")
            # 回退到传统追加模式
            self.update_outline(chapter)
            return

        # 重建完整大纲（合并所有已写入的章节大纲）
        try:
            chapter_dir = os.path.join(self.project.output_dir, "outline_chapters")
            if os.path.exists(chapter_dir):
                all_outlines = []
                for fname in sorted(os.listdir(chapter_dir)):
                    if fname.startswith("outline_ch") and fname.endswith(".txt"):
                        fpath = os.path.join(chapter_dir, fname)
                        with open(fpath, 'r', encoding='utf-8') as f:
                            all_outlines.append(f.read())
                full_outline = "\n\n".join(all_outlines)
                outline_path = os.path.join(self.project.output_dir, "outline.txt")
                with open(outline_path, 'w', encoding='utf-8') as f:
                    f.write(full_outline)
        except Exception as e:
            logger.error(f"NovelWriter：重建大纲失败: {e}")
            self.update_outline(chapter)

        # 更新内存记录
        self.project.outlines.append({
            "chapter_num": chapter_num,
            "text": new_outline,
        })
        logger.info(f"NovelWriter：大纲智能更新（第{chapter_num}章）")

    def save_collision_log(self, chapter_num: int, collisions: list):
        """
        保存本章碰撞明细
        文件路径：{output_dir}/collision_logs/collision_ch{NNN:03d}.json

        Args:
            chapter_num: 章节编号
            collisions: 碰撞事件列表（CollisionEvent 对象或字典）
        """
        if not collisions:
            logger.debug(f"NovelWriter：第{chapter_num}章无碰撞数据，跳过")
            return

        # 统一转换为字典格式
        collision_dicts = []
        for c in collisions:
            if hasattr(c, 'to_dict'):
                collision_dicts.append(c.to_dict())
            elif isinstance(c, dict):
                collision_dicts.append(c)
            else:
                logger.warning(f"NovelWriter：未知的碰撞数据类型 {type(c)}，跳过")

        if not collision_dicts:
            return

        filename = f"collision_ch{chapter_num:03d}.json"
        filepath = os.path.join(self.project.output_dir, "collision_logs", filename)

        log_data = {
            "chapter_num": chapter_num,
            "timestamp": datetime.now().isoformat(),
            "collision_count": len(collision_dicts),
            "collisions": collision_dicts,
        }

        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(log_data, f, ensure_ascii=False, indent=2)
            logger.info(
                f"NovelWriter：第{chapter_num}章碰撞明细已保存（{len(collision_dicts)}条）"
            )
        except Exception as e:
            logger.error(f"NovelWriter：保存碰撞明细失败: {e}")
            raise

        # 更新内存记录
        self.project.collision_logs[chapter_num] = collision_dicts

    def export_novel(self, format: str = "txt") -> str:
        """
        导出完整小说
        将所有章节按顺序拼接，添加书名和章节分隔，输出为完整文件。

        Args:
            format: 导出格式，目前支持 "txt"（后续可扩展 "epub"）

        Returns:
            导出文件的完整路径

        Raises:
            ValueError: 不支持的格式
        """
        if format not in ("txt", "epub"):
            raise ValueError(f"不支持的导出格式: {format}，目前仅支持 'txt' 和 'epub'")

        if not self.project.chapters:
            logger.warning("NovelWriter：没有章节可导出")
            return ""

        if format == "txt":
            return self._export_txt()
        elif format == "epub":
            return self._export_epub()

        return ""

    def _export_txt(self) -> str:
        """
        导出为TXT格式
        文件路径：{output_dir}/novel.txt

        Returns:
            导出文件路径
        """
        parts = []

        # 书名标题
        if self.project.title:
            parts.append(f"{'=' * 40}")
            parts.append(f"  {self.project.title}")
            if self.project.author:
                parts.append(f"  作者：{self.project.author}")
            if self.project.genre:
                parts.append(f"  题材：{self.project.genre}")
            parts.append(f"{'=' * 40}")
            parts.append("")

        # 按章节编号排序，逐章拼接
        sorted_chapters = sorted(self.project.chapters.items())
        for chapter_num, chapter_text in sorted_chapters:
            # 章节分隔
            parts.append(f"\n{'~' * 30}")
            parts.append(f"第{chapter_num}章")
            parts.append(f"{'~' * 30}\n")
            parts.append(chapter_text)

        full_text = "\n".join(parts)

        # 写入文件
        filepath = os.path.join(self.project.output_dir, "novel.txt")
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(full_text)
            word_count = len(full_text.replace('\n', '').replace(' ', ''))
            logger.info(
                f"NovelWriter：小说已导出为TXT（{len(sorted_chapters)}章，约{word_count}字）"
            )
            return filepath
        except Exception as e:
            logger.error(f"NovelWriter：导出TXT失败: {e}")
            raise

    def _export_epub(self) -> str:
        """
        导出为EPUB格式（基础实现）
        使用 ebooklib 库生成EPUB文件，如果不可用则降级为带HTML标签的TXT。

        Returns:
            导出文件路径
        """
        filepath = os.path.join(self.project.output_dir, "novel.epub")

        try:
            from ebooklib import epub
        except ImportError:
            # ebooklib 不可用，降级为HTML文件
            logger.warning("NovelWriter：ebooklib不可用，降级导出为HTML")
            return self._export_html_fallback()

        try:
            book = epub.EpubBook()

            # 设置书籍元数据
            book.set_title(self.project.title or "未命名小说")
            book.set_language('zh')
            book.add_author(self.project.author or "AI")

            # 添加默认样式
            style = '''
            body { font-family: "Microsoft YaHei", "SimSun", serif; margin: 1em; }
            h1 { text-align: center; margin-bottom: 1em; }
            h2 { text-align: center; margin-top: 2em; }
            p { text-indent: 2em; line-height: 1.8; }
            .separator { text-align: center; color: #999; }
            '''
            nav_css = epub.EpubItem(
                uid="style_nav",
                file_name="style/nav.css",
                media_type="text/css",
                content=style.encode('utf-8'),
            )
            book.add_item(nav_css)

            # 按章节编号排序创建EPUB章节
            spine_items = []
            sorted_chapters = sorted(self.project.chapters.items())

            for chapter_num, chapter_text in sorted_chapters:
                chapter_id = f"chapter_{chapter_num:03d}"
                chapter_title = f"第{chapter_num}章"

                # 将纯文本转为HTML段落
                html_content = f"<h2>{chapter_title}</h2>\n"
                for para in chapter_text.split('\n'):
                    para = para.strip()
                    if para:
                        html_content += f"<p>{para}</p>\n"
                    else:
                        html_content += "<br/>\n"

                epub_chapter = epub.EpubHtml(
                    title=chapter_title,
                    file_name=f"{chapter_id}.xhtml",
                    lang='zh',
                )
                epub_chapter.content = html_content.encode('utf-8')
                epub_chapter.add_item(nav_css)
                book.add_item(epub_chapter)
                spine_items.append(epub_chapter)

            # 设置目录和阅读顺序
            book.toc = spine_items
            book.add_item(epub.EpubNcx())
            book.add_item(epub.EpubNav())
            book.spine = ['nav'] + spine_items

            # 写入文件
            epub.write_epub(filepath, book, {})
            logger.info(
                f"NovelWriter：小说已导出为EPUB（{len(sorted_chapters)}章）"
            )
            return filepath

        except Exception as e:
            logger.error(f"NovelWriter：导出EPUB失败: {e}")
            # 降级为HTML
            return self._export_html_fallback()

    def _export_html_fallback(self) -> str:
        """
        EPUB导出失败时的降级方案：输出带HTML标签的文件

        Returns:
            导出文件路径
        """
        parts = [
            "<html><head><meta charset='utf-8'>"
            f"<title>{self.project.title or '未命名小说'}</title>"
            "<style>body{font-family:'Microsoft YaHei',serif;max-width:800px;margin:auto;padding:2em;}"
            "h1{text-align:center;}h2{text-align:center;margin-top:2em;}"
            "p{text-indent:2em;line-height:1.8;}</style></head><body>"
        ]

        if self.project.title:
            parts.append(f"<h1>{self.project.title}</h1>")

        sorted_chapters = sorted(self.project.chapters.items())
        for chapter_num, chapter_text in sorted_chapters:
            parts.append(f"<h2>第{chapter_num}章</h2>")
            for para in chapter_text.split('\n'):
                para = para.strip()
                if para:
                    parts.append(f"<p>{para}</p>")

        parts.append("</body></html>")

        filepath = os.path.join(self.project.output_dir, "novel.html")
        full_html = "\n".join(parts)
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(full_html)
            logger.info(f"NovelWriter：已降级导出为HTML")
            return filepath
        except Exception as e:
            logger.error(f"NovelWriter：导出HTML失败: {e}")
            raise

    def export_chapter_template(self, chapter: 'ChapterTimeline') -> str:
        """
        导出章节填写模版（用于人工审阅）
        结构化输出：时间线 + 技能清单 + 碰撞明细 + 目标清单

        Args:
            chapter: ChapterTimeline 对象

        Returns:
            模版文本字符串
        """
        if not chapter:
            return ""

        lines = []
        lines.append("=" * 60)
        lines.append(f"  章节审阅模版 - 第{chapter.chapter_num}章")
        lines.append(f"  生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append("=" * 60)
        lines.append("")

        # ---- 一、时间线结构 ----
        lines.append("【一、章节时间线】")
        lines.append("-" * 40)

        lines.append("1. 前置铺垫：")
        if chapter.prelude:
            lines.append(f"   {chapter.prelude}")
        else:
            lines.append("   （无）")

        lines.append("")
        lines.append("2. 主角行动：")
        if chapter.protagonist_action:
            lines.append(f"   {chapter.protagonist_action}")
        else:
            lines.append("   （无）")

        lines.append("")
        lines.append("3. 角色入场：")
        if chapter.entry_scenes:
            for es in chapter.entry_scenes:
                lines.append(f"   - {es.character_name} [{es.entry_motivation.value if hasattr(es.entry_motivation, 'value') else es.entry_motivation}]")
                if es.private_purpose:
                    lines.append(f"     私人目的：{es.private_purpose}")
                if es.independent_plot:
                    lines.append(f"     独立剧情：{es.independent_plot}")
                if es.entry_state:
                    lines.append(f"     入场状态：{es.entry_state}")
                if es.entry_narrative:
                    lines.append(f"     入场叙事：{es.entry_narrative[:80]}...")
        else:
            lines.append("   （无入场）")

        lines.append("")
        lines.append("4. 碰撞事件：")
        if chapter.collisions:
            for i, c in enumerate(chapter.collisions, 1):
                lines.append(f"   碰撞#{i}：{c.char_a_name} vs {c.char_b_name}")
                lines.append(f"     类型：{c.collision_type}")
                lines.append(f"     原因：{c.collision_reason}")
                if c.char_a_skill:
                    lines.append(f"     {c.char_a_name}技能：{c.char_a_skill}")
                if c.char_b_skill:
                    lines.append(f"     {c.char_b_name}技能：{c.char_b_skill}")
                if c.location:
                    lines.append(f"     地点：{c.location}")
                if c.narrative:
                    lines.append(f"     叙事：{c.narrative[:80]}...")
                if c.dialogue:
                    lines.append(f"     对话：{c.dialogue[:80]}...")
                if c.aftermath:
                    lines.append(f"     后果：{c.aftermath}")
                if c.new_foreshadowing:
                    lines.append(f"     伏笔：{'、'.join(c.new_foreshadowing)}")
                if c.new_crisis:
                    lines.append(f"     危机：{'、'.join(c.new_crisis)}")
        else:
            lines.append("   （无碰撞）")

        lines.append("")
        lines.append("5. 收尾：")
        if chapter.epilogue:
            lines.append(f"   {chapter.epilogue}")
        else:
            lines.append("   （无）")

        lines.append("")

        # ---- 二、技能清单（从碰撞事件中提取） ----
        lines.append("【二、本章涉及技能清单】")
        lines.append("-" * 40)
        seen_skills = {}  # name -> char_name 去重
        for c in chapter.collisions:
            if c.char_a_skill and c.char_a_name:
                if c.char_a_skill not in seen_skills:
                    seen_skills[c.char_a_skill] = c.char_a_name
            if c.char_b_skill and c.char_b_name:
                if c.char_b_skill not in seen_skills:
                    seen_skills[c.char_b_skill] = c.char_b_name
        if seen_skills:
            for skill_name, char_name in seen_skills.items():
                lines.append(f"   - {skill_name}（{char_name}）")
        else:
            lines.append("   （无技能涉及）")

        lines.append("")

        # ---- 三、碰撞明细汇总 ----
        lines.append("【三、碰撞明细汇总】")
        lines.append("-" * 40)
        type_counts = {}
        for c in chapter.collisions:
            ct = c.collision_type or "未知"
            type_counts[ct] = type_counts.get(ct, 0) + 1
        if type_counts:
            for ct, count in type_counts.items():
                lines.append(f"   - {ct}：{count}次")
            lines.append(f"   合计：{len(chapter.collisions)}次碰撞")
        else:
            lines.append("   （无碰撞）")

        lines.append("")

        # ---- 四、人物目标清单 ----
        lines.append("【四、人物目标清单】")
        lines.append("-" * 40)

        # 从碰撞事件中提取角色目标（如果有 world 引用的话可以更精确）
        seen_chars = {}
        for c in chapter.collisions:
            if c.char_a_name and c.char_a_id:
                if c.char_a_id not in seen_chars:
                    seen_chars[c.char_a_id] = c.char_a_name
            if c.char_b_name and c.char_b_id:
                if c.char_b_id not in seen_chars:
                    seen_chars[c.char_b_id] = c.char_b_name

        if seen_chars:
            for char_id, char_name in seen_chars.items():
                # 从 goal_tracking 中查找
                tracking = self.project.goal_tracking.get(char_name, {})
                ultimate = tracking.get("ultimate", "（未记录）")
                lines.append(f"   - {char_name}")
                lines.append(f"     终极目标：{ultimate}")
                history = tracking.get("current_history", [])
                if history:
                    latest = history[-1] if history else ""
                    lines.append(f"     当前目标：{latest}")
        elif self.project.goal_tracking:
            for name, info in self.project.goal_tracking.items():
                lines.append(f"   - {name}")
                lines.append(f"     终极目标：{info.get('ultimate', '（未记录）')}")
                history = info.get("current_history", [])
                if history:
                    lines.append(f"     当前目标：{history[-1]}")
        else:
            lines.append("   （无目标记录）")

        lines.append("")
        lines.append("=" * 60)
        lines.append("  审阅人：________  日期：________")
        lines.append("=" * 60)

        template_text = "\n".join(lines)

        # 同时写入文件
        template_filename = f"template_ch{chapter.chapter_num:03d}.txt"
        template_path = os.path.join(self.project.output_dir, template_filename)
        try:
            with open(template_path, 'w', encoding='utf-8') as f:
                f.write(template_text)
            logger.info(f"NovelWriter：章节审阅模版已导出 {template_filename}")
        except Exception as e:
            logger.error(f"NovelWriter：导出章节模版失败: {e}")

        return template_text

    def get_word_count(self) -> int:
        """
        获取总字数
        统计所有章节正文的字符数（去除空白）

        Returns:
            总字数
        """
        total = 0
        for chapter_text in self.project.chapters.values():
            # 去除空白字符和换行后的字符数
            total += len(chapter_text.replace(' ', '').replace('\n', '').replace('\r', ''))
        return total

    def get_chapter_count(self) -> int:
        """
        获取章节数

        Returns:
            已写入的章节数量
        """
        return len(self.project.chapters)

    def save_project(self):
        """
        保存项目元数据到文件
        文件路径：{output_dir}/project.json

        Raises:
            Exception: 写入失败时抛出
        """
        if not self.project.output_dir:
            logger.warning("NovelWriter：未设置输出目录，跳过项目保存")
            return

        filepath = os.path.join(self.project.output_dir, "project.json")
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(self.project.to_dict(), f, ensure_ascii=False, indent=2)
            logger.info(f"NovelWriter：项目元数据已保存")
        except Exception as e:
            logger.error(f"NovelWriter：保存项目失败: {e}")
            raise

    def load_project(self) -> bool:
        """
        从文件加载项目元数据
        文件路径：{output_dir}/project.json

        Returns:
            是否加载成功
        """
        filepath = os.path.join(self.project.output_dir, "project.json")
        if not os.path.exists(filepath):
            logger.warning(f"NovelWriter：项目文件不存在 {filepath}")
            return False

        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
            loaded = NovelProject.from_dict(data)
            # 更新当前 project 实例
            self.project.title = loaded.title
            self.project.author = loaded.author
            self.project.genre = loaded.genre
            self.project.chapters = loaded.chapters
            self.project.outlines = loaded.outlines
            self.project.skill_snapshots = loaded.skill_snapshots
            self.project.collision_logs = loaded.collision_logs
            self.project.goal_tracking = loaded.goal_tracking
            logger.info(f"NovelWriter：项目已从文件加载（{len(loaded.chapters)}章）")
            return True
        except Exception as e:
            logger.error(f"NovelWriter：加载项目失败: {e}")
            return False
