# -*- coding: utf-8 -*-
"""
小说世界 - 大纲系统
从书斋V66 backend/project_volumes.py + backend/project_chapters.py 移植与适配

核心能力：
- 卷大纲管理（CRUD + 结构化纲要）
- 大纲驱动卷结构（根据大纲自动分配章节到卷）
- 自动重建（从章节标题推断卷结构）

适配说明：原书斋V66 大纲逻辑嵌入在 ProjectVolumesMixin / ProjectChaptersMixin 中，
需要 self.volumes / self.chapters / self._dirty / self._save_meta() 等槽位。
现提取为独立 OutlineManager，数据通过方法参数传入/传出，解耦项目对象。
"""

import re
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


# ============================================================
# 数据类
# ============================================================

@dataclass
class Outline:
    """卷纲要"""
    summary: str = ""
    theme: str = ""
    key_events: List[str] = field(default_factory=list)
    character_arcs: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "summary": self.summary,
            "theme": self.theme,
            "key_events": self.key_events,
            "character_arcs": self.character_arcs,
        }

    @classmethod
    def from_dict(cls, data) -> "Outline":
        if isinstance(data, str):
            return cls(summary=data)
        if not isinstance(data, dict):
            return cls()
        return cls(
            summary=data.get("summary", ""),
            theme=data.get("theme", ""),
            key_events=data.get("key_events", []),
            character_arcs=data.get("character_arcs", []),
        )


@dataclass
class VolumeInfo:
    """卷信息"""
    index: int
    title: str
    outline: Outline = field(default_factory=Outline)
    chapters: List[int] = field(default_factory=list)

    @property
    def chapter_count(self) -> int:
        return len(self.chapters)

    def to_dict(self) -> dict:
        return {
            "index": self.index,
            "title": self.title,
            "outline": self.outline.to_dict(),
            "chapters": self.chapters,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "VolumeInfo":
        outline_data = data.get("outline", {})
        if isinstance(outline_data, str):
            outline_data = {"summary": outline_data}
        return cls(
            index=data.get("index", 0),
            title=data.get("title", ""),
            outline=Outline.from_dict(outline_data),
            chapters=data.get("chapters", []),
        )


# ============================================================
# OutlineManager
# ============================================================

class OutlineManager:
    """大纲管理器 — 卷结构 + 章节规划

    独立于项目对象，数据通过 volumes 列表管理。
    可配合 TruthLedger 或独立使用。

    使用方式：
        mgr = OutlineManager()
        mgr.add_volume("序幕", outline=Outline(summary="引入世界观"))
        mgr.add_volume("高潮")
        mgr.add_chapter_to_volume(0, 1)  # 第1章归入第1卷
        volumes = mgr.get_volumes()
    """

    def __init__(self, volumes: Optional[List[VolumeInfo]] = None):
        self.volumes: List[VolumeInfo] = volumes or []

    # ── Volumes CRUD ──

    def set_volumes(self, volumes_data: List[dict]):
        """设置卷数据（覆盖）"""
        self.volumes = []
        for i, vol_dict in enumerate(volumes_data):
            vol = VolumeInfo.from_dict(vol_dict)
            if not vol.index:
                vol.index = i
            # 自动生成 chapters 数组
            if not vol.chapters:
                start = vol_dict.get("start_chapter", 0)
                end = vol_dict.get("end_chapter", 0)
                if start > 0 and end >= start:
                    vol.chapters = list(range(start, end + 1))
            self.volumes.append(vol)
        self._reindex()

    def get_volumes(self) -> List[dict]:
        """获取所有卷数据（返回dict列表）"""
        result = []
        for i, vol in enumerate(self.volumes):
            d = vol.to_dict()
            d["index"] = i
            d["chapter_count"] = vol.chapter_count
            result.append(d)
        return result

    def add_volume(
        self,
        title: str,
        outline: Optional[Outline] = None,
        start_chapter: int = 0,
        end_chapter: int = 0,
    ) -> int:
        """添加一卷，返回卷索引"""
        idx = len(self.volumes)
        chapters = []
        if start_chapter > 0 and end_chapter >= start_chapter:
            chapters = list(range(start_chapter, end_chapter + 1))
            # 从已有卷中移除重叠章节
            for vol in self.volumes:
                vol.chapters = [c for c in vol.chapters
                                if c < start_chapter or c > end_chapter]

        vol = VolumeInfo(
            index=idx,
            title=title or f"第{idx + 1}卷",
            outline=outline or Outline(),
            chapters=chapters,
        )
        self.volumes.append(vol)
        self._reindex()
        return idx

    def delete_volume(self, vol_index: int) -> bool:
        """删除一卷"""
        if vol_index < 0 or vol_index >= len(self.volumes):
            return False
        if len(self.volumes) <= 1:
            self.volumes = []
            return True
        removed = self.volumes.pop(vol_index)
        # 将被删卷的章节移到前一卷
        target_idx = vol_index - 1 if vol_index > 0 else 0
        if target_idx < len(self.volumes):
            self.volumes[target_idx].chapters.extend(removed.chapters)
            self.volumes[target_idx].chapters.sort()
        self._reindex()
        return True

    def rename_volume(self, vol_index: int, title: str) -> bool:
        """重命名一卷"""
        if vol_index < 0 or vol_index >= len(self.volumes):
            return False
        self.volumes[vol_index].title = title
        return True

    def set_volume_outline(self, vol_index: int, outline_data: dict) -> bool:
        """设置卷纲要"""
        if vol_index < 0 or vol_index >= len(self.volumes):
            return False
        self.volumes[vol_index].outline = Outline.from_dict(outline_data)
        return True

    def get_volume_outline(self, vol_index: int) -> dict:
        """获取卷纲要"""
        if vol_index < 0 or vol_index >= len(self.volumes):
            return {"summary": "", "theme": "", "key_events": [], "character_arcs": []}
        return self.volumes[vol_index].outline.to_dict()

    # ── 章节分配 ──

    def add_chapter_to_volume(self, vol_index: int, chapter_idx: int) -> bool:
        """将章节添加到指定卷"""
        if vol_index < 0 or vol_index >= len(self.volumes):
            return False
        vol = self.volumes[vol_index]
        if chapter_idx not in vol.chapters:
            vol.chapters.append(chapter_idx)
            vol.chapters.sort()
            return True
        return False

    def remove_chapter_from_volume(self, vol_index: int, chapter_idx: int) -> bool:
        """从指定卷移除章节"""
        if vol_index < 0 or vol_index >= len(self.volumes):
            return False
        vol = self.volumes[vol_index]
        if chapter_idx in vol.chapters:
            vol.chapters.remove(chapter_idx)
            return True
        return False

    def set_volume_chapters(self, vol_index: int, chapter_indices: List[int]) -> bool:
        """设置卷的章节列表（覆盖）"""
        if vol_index < 0 or vol_index >= len(self.volumes):
            return False
        self.volumes[vol_index].chapters = sorted(list(set(chapter_indices)))
        return True

    # ── 自动重建 ──

    def rebuild_from_chapters(self, chapters: List[dict]) -> List[VolumeInfo]:
        """根据章节标题自动重建卷结构

        Args:
            chapters: [{"index": 1, "title": "第1卷·序章"}, ...]

        Returns:
            重建后的 VolumeInfo 列表
        """
        if not chapters:
            self.volumes = []
            return []

        volume_map: Dict[int, VolumeInfo] = {}
        default_volume = VolumeInfo(
            index=0, title="正文",
            outline=Outline(), chapters=[]
        )

        for ch in chapters:
            ch_idx = ch.get("index", 0)
            title = ch.get("title", "")
            vol_num = self._extract_volume_number(title)

            if vol_num == 0:
                default_volume.chapters.append(ch_idx)
            else:
                if vol_num not in volume_map:
                    volume_map[vol_num] = VolumeInfo(
                        index=vol_num,
                        title=f"第{vol_num}卷",
                        outline=Outline(),
                        chapters=[],
                    )
                volume_map[vol_num].chapters.append(ch_idx)

        result = []
        if default_volume.chapters:
            result.append(default_volume)
        result.extend(sorted(volume_map.values(), key=lambda v: v.index))

        if not result:
            result.append(default_volume)

        self.volumes = result
        self._reindex()
        return self.volumes

    @staticmethod
    def _extract_volume_number(title: str) -> int:
        """从标题中提取卷号"""
        m = re.search(r'(?:第|卷·?)(\d+)卷', title)
        if m:
            return int(m.group(1))
        m2 = re.search(r'卷(\d+)', title)
        if m2:
            return int(m2.group(1))
        return 0

    # ── 大纲验证 ──

    def validate_outline(self) -> dict:
        """验证大纲完整性

        Returns:
            {"valid": bool, "issues": [str], "warnings": [str]}
        """
        issues = []
        warnings = []

        if not self.volumes:
            issues.append("无任何卷定义")
            return {"valid": False, "issues": issues, "warnings": warnings}

        # 检查章节分配
        all_chapters = set()
        for vol in self.volumes:
            all_chapters.update(vol.chapters)
            if vol.chapter_count == 0:
                warnings.append(f"卷「{vol.title}」无章节")

        # 检查重复分配
        chapter_counts = {}
        for vol in self.volumes:
            for ch in vol.chapters:
                chapter_counts[ch] = chapter_counts.get(ch, 0) + 1
        duplicates = {ch: cnt for ch, cnt in chapter_counts.items() if cnt > 1}
        if duplicates:
            issues.append(f"章节重复分配: {duplicates}")

        # 检查卷纲要完整性
        empty_outlines = [vol.title for vol in self.volumes
                          if not vol.outline.summary and not vol.outline.key_events]
        if empty_outlines:
            warnings.append(f"以下卷缺少纲要: {', '.join(empty_outlines)}")

        return {
            "valid": len(issues) == 0,
            "issues": issues,
            "warnings": warnings,
        }

    # ── 工具方法 ──

    def _reindex(self):
        """重新索引所有卷"""
        for i, vol in enumerate(self.volumes):
            vol.index = i

    def find_volume_for_chapter(self, chapter_idx: int) -> Optional[VolumeInfo]:
        """查找指定章节所属的卷"""
        for vol in self.volumes:
            if chapter_idx in vol.chapters:
                return vol
        return None

    def to_dict(self) -> dict:
        return {"volumes": [v.to_dict() for v in self.volumes]}

    @classmethod
    def from_dict(cls, data: dict) -> "OutlineManager":
        volumes = [VolumeInfo.from_dict(v) for v in data.get("volumes", [])]
        return cls(volumes=volumes)
