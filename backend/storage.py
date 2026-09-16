"""存档系统

安全机制：
- 滚动备份：每次保存前将旧存档复制为 {slot}.bak（保留上一份完整数据）
- 原子写入：先写 .tmp 再 os.replace 替换，避免写入中途崩溃导致存档损坏
- gzip 压缩：新存档以 gzip 写入降低磁盘占用，读取时按魔数自动识别旧明文存档
- 自动恢复：读取时若主存档损坏/缺失，自动回退到 .bak 备份
- 槽位校验：拦截路径遍历类非法槽位名（如 ../ 越权读写）
- 串行锁：save/load/delete 串行执行，避免并发保存互相覆盖
"""

import gzip
import json
import logging
import os
import re
import shutil
import threading
import zlib
from datetime import datetime
from .world import World
from .config import WorldConfig, CharacterConfig
from .character import CharacterAgent, Goal
from novel_world.engine.core.goal import GoalStatus

logger = logging.getLogger(__name__)

_WRITABLE_BASE = os.environ.get("NOVEL_WORLD_WRITABLE") or os.path.dirname(os.path.dirname(__file__))
SAVES_DIR = os.path.join(_WRITABLE_BASE, "saves")

# 合法槽位名：字母/数字/下划线/连字符/中文，1-64 字符
_SLOT_PATTERN = re.compile(r"^[\w\u4e00-\u9fa5-]{1,64}$")


def _safe_slot_path(slot: str) -> str:
    """校验槽位名并返回存档路径，非法时抛 ValueError（防路径遍历）"""
    if not isinstance(slot, str) or not _SLOT_PATTERN.match(slot):
        raise ValueError(f"非法存档槽位名：{slot!r}")
    filepath = os.path.abspath(os.path.join(SAVES_DIR, f"{slot}.json"))
    # 双保险：解析后路径必须仍在 SAVES_DIR 内
    if os.path.commonpath([os.path.abspath(SAVES_DIR), filepath]) != os.path.abspath(SAVES_DIR):
        raise ValueError(f"存档路径越权：{slot!r}")
    return filepath


def _read_json_safe(filepath: str) -> dict | None:
    """安全读取存档（自动识别 gzip 与旧明文格式），损坏/缺失时返回 None"""
    try:
        with open(filepath, "rb") as f:
            raw = f.read()
        if raw.startswith(b"\x1f\x8b"):  # gzip 魔数
            raw = gzip.decompress(raw)
        return json.loads(raw.decode("utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError, ValueError, zlib.error) as e:
        logger.warning("存档读取失败 %s: %s", filepath, e)
        return None


class Storage:

    def __init__(self):
        os.makedirs(SAVES_DIR, exist_ok=True)
        self._io_lock = threading.Lock()

    def save(self, slot: str, world: World, characters: list[CharacterAgent], chapters: list[dict],
             outline_data: dict = None, engine_config: dict = None):
        """保存游戏到指定存档槽"""
        filepath = _safe_slot_path(slot)

        data = {
            "meta": {
                "saved_at": datetime.now().isoformat(),
                "slot": slot,
            },
            "world_config": {
                "name": world.config.name,
                "genre": world.config.genre,
                "era": world.config.era,
                "description": world.config.description,
                "rules": world.config.rules,
                "key_locations": world.config.key_locations,
                "current_situation": world.config.current_situation,
                "tone": world.config.tone,
                "main_objective": world.config.main_objective,
                "perspective": getattr(world.config, "perspective", "third"),
            },
            "world_state": {
                "current_chapter": world.current_chapter,
                "events": world.events,
                "character_positions": world.character_positions,
            },
            "characters": [],
            "chapters": chapters,
            "outline_data": outline_data,
            "engine_config": engine_config,
        }

        for char in characters:
            char_data = {
                "config": {
                    "name": char.config.name,
                    "age": char.config.age,
                    "gender": char.config.gender,
                    "personality": char.config.personality,
                    "background": char.config.background,
                    "appearance": char.config.appearance,
                    "short_term_goals": char.config.short_term_goals,
                    "long_term_goal": char.config.long_term_goal,
                    "abilities": char.config.abilities,
                    "weaknesses": char.config.weaknesses,
                    "initial_location": char.config.initial_location,
                    "initial_relationships": char.config.initial_relationships,
                },
                "long_term_goal": {
                    "description": char.long_term_goal.description,
                    "priority": char.long_term_goal.priority,
                    "progress": char.long_term_goal.progress,
                    "reason_changed": char.long_term_goal.reason_changed,
                },
                "short_term_goals": [
                    {
                        "description": g.description,
                        "priority": g.priority,
                        "progress": g.progress,
                        "reason_changed": g.reason_changed,
                    }
                    for g in char.short_term_goals
                ],
                "goal_history": char.goal_history,
                "memory": char.memory,
                "relationships": char.relationships,
                "current_location": char.current_location,
                "current_mood": char.current_mood,
                "action_style": char.action_style,
                "current_drive": char.current_drive,
                "cognitive_boundary": char.cognitive_boundary,
            }
            data["characters"].append(char_data)

        # 滚动备份：先保留上一份存档，再原子写入新存档（串行锁防并发覆盖）
        # 新存档以 gzip 压缩写入，章节越多收益越大
        bak_path = filepath + ".bak"
        tmp_path = filepath + ".tmp"
        with self._io_lock:
            if os.path.exists(filepath):
                try:
                    shutil.copy2(filepath, bak_path)
                except OSError as e:
                    logger.warning("备份旧存档失败 %s: %s", filepath, e)

            payload = json.dumps(data, ensure_ascii=False).encode("utf-8")
            with open(tmp_path, "wb") as f:
                f.write(gzip.compress(payload))
            os.replace(tmp_path, filepath)

    def load(self, slot: str) -> tuple[World, list[CharacterAgent], list[dict]] | None:
        """从存档槽加载游戏（主存档损坏时自动回退 .bak 备份）"""
        filepath = _safe_slot_path(slot)
        data = None
        with self._io_lock:
            if os.path.exists(filepath):
                data = _read_json_safe(filepath)
            if data is None:
                # 主存档缺失或损坏，尝试从备份恢复
                bak_path = filepath + ".bak"
                if os.path.exists(bak_path):
                    data = _read_json_safe(bak_path)
                    if data is not None:
                        logger.warning("存档 %s 损坏，已从备份 %s 恢复", filepath, bak_path)
                        try:
                            # 用备份覆盖损坏的主存档，恢复正常读取路径
                            shutil.copy2(bak_path, filepath)
                        except OSError as e:
                            logger.warning("备份恢复写回失败 %s: %s", filepath, e)
        if data is None:
            if not os.path.exists(filepath):
                return None
            raise ValueError(f"存档 {slot} 已损坏且无可用备份：{filepath}")

        # 重建世界
        wc_data = data["world_config"]
        world_config = WorldConfig(
            name=wc_data["name"],
            genre=wc_data.get("genre", "玄幻"),
            era=wc_data.get("era", "古代"),
            description=wc_data.get("description", ""),
            rules=wc_data.get("rules", []),
            key_locations=wc_data.get("key_locations", []),
            current_situation=wc_data.get("current_situation", ""),
            tone=wc_data.get("tone", "史诗冒险"),
            main_objective=wc_data.get("main_objective", ""),
            perspective=wc_data.get("perspective", "third"),
        )
        world = World(world_config)
        world.current_chapter = data["world_state"]["current_chapter"]
        world.events = data["world_state"]["events"]
        world.character_positions = data["world_state"]["character_positions"]

        # 重建角色
        characters = []
        for cd in data["characters"]:
            cfg = cd["config"]
            char_config = CharacterConfig(
                name=cfg["name"],
                age=cfg.get("age", 20),
                gender=cfg.get("gender", "男"),
                personality=cfg.get("personality", ""),
                background=cfg.get("background", ""),
                appearance=cfg.get("appearance", ""),
                short_term_goals=cfg.get("short_term_goals", []),
                long_term_goal=cfg.get("long_term_goal", ""),
                abilities=cfg.get("abilities", []),
                weaknesses=cfg.get("weaknesses", []),
                initial_location=cfg.get("initial_location", ""),
                initial_relationships=cfg.get("initial_relationships", {}),
            )
            char = CharacterAgent(char_config)

            # 恢复运行时状态
            char.long_term_goal = Goal(
                content=cd["long_term_goal"]["description"],
                priority=cd["long_term_goal"]["priority"],
                status=GoalStatus.from_progress(cd["long_term_goal"]["progress"]),
                reason_changed=cd["long_term_goal"].get("reason_changed", ""),
            )
            char.short_term_goals = [
                Goal(
                    content=g["description"],
                    priority=g["priority"],
                    status=GoalStatus.from_progress(g["progress"]),
                    reason_changed=g.get("reason_changed", ""),
                )
                for g in cd["short_term_goals"]
            ]
            char.goal_history = cd.get("goal_history", [])
            char.memory = cd.get("memory", [])
            char.relationships = cd.get("relationships", {})
            char.current_location = cd.get("current_location", "")
            char.current_mood = cd.get("current_mood", "平静")
            char.action_style = cd.get("action_style", "")
            char.current_drive = cd.get("current_drive", "")
            char.cognitive_boundary = cd.get("cognitive_boundary", "")

            characters.append(char)

        return world, characters, data.get("chapters", []), data.get("outline_data"), data.get("engine_config")

    def list_slots(self) -> list[dict]:
        """列出所有存档"""
        slots = []
        if not os.path.exists(SAVES_DIR):
            return slots
        for filename in os.listdir(SAVES_DIR):
            if filename.endswith(".json"):
                filepath = os.path.join(SAVES_DIR, filename)
                data = _read_json_safe(filepath)
                if data is None:
                    # 损坏的存档仍展示在列表中，标记状态提醒用户
                    slots.append({
                        "slot": filename.replace(".json", ""),
                        "saved_at": "",
                        "world_name": "",
                        "chapter": 0,
                        "corrupted": True,
                        "has_backup": os.path.exists(filepath + ".bak"),
                    })
                    continue
                meta = data.get("meta", {})
                slots.append({
                    "slot": filename.replace(".json", ""),
                    "saved_at": meta.get("saved_at", ""),
                    "world_name": data.get("world_config", {}).get("name", ""),
                    "chapter": data.get("world_state", {}).get("current_chapter", 0),
                })
        return slots

    def delete_slot(self, slot: str):
        """删除存档（连同备份与临时文件）"""
        base = _safe_slot_path(slot)
        with self._io_lock:
            for suffix in ("", ".bak", ".tmp"):
                filepath = base + suffix
                if os.path.exists(filepath):
                    os.remove(filepath)
