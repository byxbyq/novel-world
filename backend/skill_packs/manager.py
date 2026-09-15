# -*- coding: utf-8 -*-
"""
小说世界 - 技能包系统
移植自：书斋V66 backend/routers/skill_import.py (REST 路由 → 纯函数解耦)

提供：
- SkillPackManager: 技能包的创建/导入/列表/搜索/删除（纯 Python 接口）
- novel_distill: 从小说文本蒸馏技能包（不依赖 FastAPI）
- file_safe: 文件名安全化（防路径穿越）
"""
import json
import os
import re
import time
import logging
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field, asdict

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════
# 数据模型
# ═══════════════════════════════════════════

@dataclass
class SkillPack:
    """技能包数据模型"""
    id: str
    name: str
    type: str           # technique / character / world_setting / plot_pattern
    description: str
    content: str        # 核心内容（定义/使用说明）
    metadata: Dict = field(default_factory=dict)  # 扩展元数据

    # 自动填充
    created_at: str = ""
    updated_at: str = ""

    def __post_init__(self):
        now = time.strftime("%Y-%m-%d %H:%M:%S")
        if not self.created_at:
            self.created_at = now
        if not self.updated_at:
            self.updated_at = now

    def to_dict(self) -> Dict:
        return asdict(self)


# 必需的技能包字段
REQUIRED_FIELDS = ["id", "name", "type", "description", "content"]


# ═══════════════════════════════════════════
# 技能包管理器
# ═══════════════════════════════════════════

class SkillPackManager:
    """技能包管理 — 文件系统存储 (纯 Python 接口，不依赖 FastAPI)

    存储约定: <skills_dir>/<pack_id>.json
    """

    def __init__(self, skills_dir: str = None):
        if skills_dir is None:
            skills_dir = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                "data", "skills"
            )
        self.skills_dir = skills_dir
        os.makedirs(self.skills_dir, exist_ok=True)

    def _pack_path(self, pack_id: str) -> str:
        return os.path.join(self.skills_dir, f"{_sanitize_filename(pack_id)}.json")

    def _load_pack(self, pack_id: str) -> Optional[Dict]:
        path = self._pack_path(pack_id)
        if not os.path.exists(path):
            return None
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _save_pack(self, pack: SkillPack):
        path = self._pack_path(pack.id)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(pack.to_dict(), f, ensure_ascii=False, indent=2)

    def import_skill(self, skill_data: Dict) -> SkillPack:
        """导入/创建技能包"""
        # 必填字段校验
        for field in REQUIRED_FIELDS:
            if field not in skill_data or not skill_data.get(field):
                raise ValueError(f"缺少必填字段: {field}")

        pack = SkillPack(
            id=skill_data["id"],
            name=skill_data["name"],
            type=skill_data["type"],
            description=skill_data["description"],
            content=skill_data["content"],
            metadata=skill_data.get("metadata", {}),
            created_at=skill_data.get("created_at", ""),
            updated_at=time.strftime("%Y-%m-%d %H:%M:%S"),
        )
        self._save_pack(pack)
        logger.info("技能包导入成功: %s (%s)", pack.name, pack.id)
        return pack

    def list_skills(self) -> List[SkillPack]:
        """列出全部技能包"""
        skills = []
        if not os.path.isdir(self.skills_dir):
            return skills
        for fname in os.listdir(self.skills_dir):
            if not fname.endswith(".json"):
                continue
            pack_id = fname[:-5]
            data = self._load_pack(pack_id)
            if data:
                skills.append(_dict_to_skill(data))
        skills.sort(key=lambda s: s.updated_at, reverse=True)
        return skills

    def search_skills(self, keyword: str = "", skill_type: str = "") -> List[SkillPack]:
        """按关键词或类型搜索"""
        all_skills = self.list_skills()
        results = []
        for s in all_skills:
            if skill_type and s.type != skill_type:
                continue
            if keyword:
                kw = keyword.lower()
                if (kw in s.name.lower()
                        or kw in s.description.lower()
                        or kw in s.content.lower()):
                    results.append(s)
            else:
                results.append(s)
        return results

    def get_skill(self, pack_id: str) -> Optional[SkillPack]:
        """按ID获取技能包"""
        data = self._load_pack(pack_id)
        if data:
            return _dict_to_skill(data)
        return None

    def delete_skill(self, pack_id: str) -> bool:
        """删除技能包"""
        path = self._pack_path(pack_id)
        if not os.path.exists(path):
            return False
        os.remove(path)
        logger.info("技能包已删除: %s", pack_id)
        return True


# ═══════════════════════════════════════════
# 辅助函数
# ═══════════════════════════════════════════

def _dict_to_skill(data: Dict) -> SkillPack:
    """将 dict 转为 SkillPack 对象"""
    return SkillPack(
        id=data.get("id", ""),
        name=data.get("name", ""),
        type=data.get("type", "technique"),
        description=data.get("description", ""),
        content=data.get("content", ""),
        metadata=data.get("metadata", {}),
        created_at=data.get("created_at", ""),
        updated_at=data.get("updated_at", ""),
    )


def _sanitize_filename(name: str) -> str:
    """文件名消毒：移除危险字符，防路径穿越"""
    # 移除路径分隔符
    name = name.replace("\\", "").replace("/", "")
    # 移除特殊字符
    name = re.sub(r'[<>:"|?*]', "", name)
    # 压缩空白
    name = re.sub(r"\s+", "_", name).strip("_")
    return name or "unnamed"


def novel_distill(novel_text: str, skill_type: str = "technique") -> List[Dict]:
    """从小说文本中蒸馏技能包（基于规则提取，不消耗Token）

    提取策略：
    - 寻找 markdown 风格的分段标题 (##) 作为技能名
    - 通过冒号/方括号识别结构化字段
    - 自动填充 id/name/type

    Args:
        novel_text: 小说全文文本
        skill_type: 技能类型 (technique / character / plot_pattern / world_setting)

    Returns:
        解析出的技能数据列表（dict 格式，可直接传给 import_skill）
    """
    skills = []

    # 按 ## 分段
    sections = re.split(r'\n(?:#{2,3}\s+)', novel_text)
    if len(sections) < 2:
        return skills

    for i, section in enumerate(sections[1:]):
        lines = section.strip().split("\n")
        if len(lines) < 2:
            continue

        # 第一行是标题 (技能名)
        name_line = lines[0].strip()

        # 提取冒号键值对
        fields = {}
        desc_parts = []
        for line in lines[1:]:
            line = line.strip()
            if not line:
                continue
            if ":" in line:
                key, val = line.split(":", 1)
                key = key.strip().strip("**").strip("[]")
                fields[key] = val.strip()
            else:
                desc_parts.append(line)

        name = name_line
        description = fields.get("说明", fields.get("描述", "\n".join(desc_parts[:3])))
        content = fields.get("用法", fields.get("示例", "\n".join(desc_parts[3:])))

        skill_id = fields.get("id", f"distill_{skill_type}_{i+1:03d}")

        skills.append({
            "id": skill_id,
            "name": name,
            "type": skill_type,
            "description": description[:200] if description else "",
            "content": content[:2000] if content else "",
            "metadata": {"source": "novel_distill", "section": i + 1},
        })

    logger.info("从小说蒸馏 %d 个技能包 (type=%s)", len(skills), skill_type)
    return skills
