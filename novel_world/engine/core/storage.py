"""存档系统 - 支持加密和校验"""
import json
import os
import time
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Optional, Tuple, Dict, Any, List
from datetime import datetime

logger = logging.getLogger(__name__)

# 存档目录：项目根目录下的 saves/（可用环境变量 NOVEL_WORLD_SAVE_DIR 覆盖）。
# 历史 bug：这里曾硬编码别的项目的绝对路径 H:\baichengzhu\game\saves，
# 导致推演自动存档写到项目外且失败被静默吞掉
SAVE_DIR = Path(os.environ.get(
    "NOVEL_WORLD_SAVE_DIR",
    str(Path(__file__).resolve().parents[3] / "saves"),
))
MAX_AUTO_SAVES = 5


# ============================================================
# 加密和签名工具 → storage_mixins.crypto
# ============================================================
from .storage_mixins.crypto import SaveCrypto  # noqa: E402, F401 — re-export for backward compat


# ============================================================
# 存档数据结构 → storage_mixins.data
# ============================================================
from .storage_mixins.data import SaveData  # noqa: E402, F401 — re-export for backward compat


# ============================================================
# 基础存档管理
# ============================================================
class GameStorage:
    """游戏存档管理"""

    def __init__(self):
        SAVE_DIR.mkdir(parents=True, exist_ok=True)

    def _world_to_dict(self, world: 'World') -> dict:
        """将 World 对象序列化为字典"""
        from .world import TileType, Tile, Faction, World
        from .character import Character, CharType, CharState
        
        data = {
            "theme": world.theme,
            "current_time": world.current_time,
            "map_size": world.map_size,
            "tick_count": world.tick_count,
            "tiles": {},
            "characters": [],
            "factions": {},
            "total_events": world.total_events,
        }

        # 序列化自定义规则
        cr = getattr(world, "custom_rules", None)
        if cr and hasattr(cr, "to_dict") and cr.is_customized():
            data["custom_rules"] = cr.to_dict()

        # 序列化地块
        for (x, y), tile in world.tiles.items():
            data["tiles"][f"{x},{y}"] = {
                "x": x, "y": y,
                "type": tile.tile_type.value,
                "faction_id": tile.faction_id,
                "resources": tile.resources,
                "name": tile.name,
                "description": tile.description,
            }

        # 序列化角色
        for char in world.characters:
            data["characters"].append({
                "id": char.id,
                "name": char.name,
                "char_type": char.char_type.value,
                "pos": list(char.pos),
                "age": char.age,
                "gender": char.gender,
                "attrs": {k: v for k, v in char.attrs.items() if isinstance(v, (int, float, str, bool))},
                "skills": char.skills,
                "goal": char.goal,
                "state": char.state.value,
                "faction_id": char.faction_id,
                "relations": {k: v for k, v in char.relations.items()},
                "alive": char.alive,
                "action_cooldown": char.action_cooldown,
                "memory": char.memory[-20:],
                # 核心叙事属性
                "personality": char.personality,
                "fate_arc": char.fate_arc,
                "story_state": char.story_state,
                "key_memories": char.key_memories,
                "relationships": char.relationships,
            })

        # 序列化势力
        for fid, faction in world.factions.items():
            data["factions"][fid] = {
                "id": faction.id,
                "name": faction.name,
                "color": faction.color,
                "member_ids": faction.member_ids,
                "resources": faction.resources,
            }

        return data

    def _dict_to_world(self, data: dict) -> 'World':
        """从字典反序列化 World 对象"""
        from .world import TileType, Tile, Faction, World
        from .character import Character, CharType, CharState

        world = World(theme=data["theme"], map_size=tuple(data["map_size"]))
        world.current_time = data["current_time"]
        world.tick_count = data.get("tick_count", 0)
        world.total_events = data.get("total_events", 0)

        # 恢复自定义规则
        if "custom_rules" in data:
            from .themes.custom_rules import CustomRules
            world.custom_rules = CustomRules.from_dict(data["custom_rules"])

        # 恢复地块
        for key, td in data["tiles"].items():
            tile = Tile(
                tile_type=TileType(td["type"]),
                faction_id=td.get("faction_id", ""),
                resources=td.get("resources", {}),
                name=td.get("name", ""),
                description=td.get("description", ""),
            )
            world.tiles[(td["x"], td["y"])] = tile

        # 恢复势力
        for fid, fd in data["factions"].items():
            faction = Faction(
                id=fd["id"],
                name=fd["name"],
                color=fd.get("color", "#FFFFFF"),
                member_ids=fd.get("member_ids", []),
            )
            faction.resources = fd.get("resources", {})
            world.factions[fid] = faction

        # 恢复角色
        for cd in data["characters"]:
            char = Character(
                name=cd["name"],
                char_type=CharType(cd["char_type"]),
                pos=tuple(cd["pos"]),
                age=cd["age"],
                gender=cd["gender"],
                attrs=cd["attrs"],
                skills=cd.get("skills", []),
                goal=cd.get("goal", ""),
                state=CharState(cd["state"]),
                faction_id=cd.get("faction_id", ""),
                id=cd["id"],
                alive=cd["alive"],
                action_cooldown=cd.get("action_cooldown", 0),
            )
            char.relations = cd.get("relations", {})
            char.memory = cd.get("memory", [])
            # 核心叙事属性
            char.personality = cd.get("personality", "")
            char.fate_arc = cd.get("fate_arc", "")
            char.story_state = cd.get("story_state", "")
            char.key_memories = cd.get("key_memories", [])
            char.relationships = cd.get("relationships", {})
            world.characters.append(char)

        return world

    def save(self, world: 'World', slot: int = 1):
        """保存游戏到指定槽位"""
        data = self._world_to_dict(world)
        filepath = SAVE_DIR / f"save_slot_{slot}.json"
        # 先写临时文件再重命名，防止写坏
        tmp_path = filepath.with_suffix(".tmp")
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        tmp_path.replace(filepath)
        return filepath

    def load(self, slot: int = 1) -> 'World':
        """从指定槽位加载游戏"""
        filepath = SAVE_DIR / f"save_slot_{slot}.json"
        if not filepath.exists():
            raise FileNotFoundError(f"存档槽位 {slot} 不存在")
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        return self._dict_to_world(data)

    def auto_save(self, world: 'World'):
        """自动存档（循环覆盖5个槽位）"""
        idx = world.tick_count % MAX_AUTO_SAVES
        filepath = SAVE_DIR / f"auto_save_{idx}.json"
        data = self._world_to_dict(world)
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def get_save_list(self) -> list:
        """获取所有存档信息"""
        saves = []
        for f in sorted(SAVE_DIR.glob("save_slot_*.json")):
            try:
                with open(f, "r", encoding="utf-8") as fp:
                    data = json.load(fp)
                saves.append({
                    "slot": int(f.stem.split("_")[-1]),
                    "path": str(f),
                    "time": data.get("current_time", 0),
                    "theme": data.get("theme", "未知"),
                    "mtime": time.ctime(f.stat().st_mtime),
                })
            except Exception:
                continue
        return saves

    def export_story(self, world: 'World', filepath: str = None):
        """导出所有角色的记忆为文本"""
        if filepath is None:
            filepath = str(SAVE_DIR / f"story_export_{int(time.time())}.txt")

        lines = [f"=== 世界演化模拟器 - 剧情导出 ===",
                 f"世界观：{world.theme}",
                 f"时间：第 {world.current_time} 天",
                 f"角色数：{len(world.characters)}",
                 ""]

        for char in world.characters:
            lines.append(f"--- {char.name} ({char.char_type.value}) ---")
            if char.memory:
                for mem in char.memory:
                    lines.append(f"  {mem}")
            else:
                lines.append("  （暂无记忆）")
            lines.append("")

        with open(filepath, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        return filepath


# ============================================================
# 增强版存档管理（加密支持）
# ============================================================
import gzip
import pickle


class EnhancedGameStorage(GameStorage):
    """增强版存档管理 - 支持加密和校验"""
    
    def __init__(
        self,
        encryption_key: Optional[str] = None,
        signing_key: Optional[str] = None,
        enable_encryption: bool = True,
        verify_on_load: bool = True
    ):
        """
        初始化增强版存档管理
        
        Args:
            encryption_key: 加密密钥
            signing_key: 签名密钥
            enable_encryption: 是否启用加密
            verify_on_load: 是否在加载时验证
        """
        super().__init__()
        
        self.metadata_file = SAVE_DIR / "save_metadata.json"
        self.enable_encryption = enable_encryption
        self.verify_on_load = verify_on_load
        
        # 初始化加密工具
        self.crypto = SaveCrypto(encryption_key, signing_key)
        
        # 如果没有提供密钥，保存默认密钥
        self._key_file = SAVE_DIR / ".save_key"
        if encryption_key is None and not self._key_file.exists():
            self._generate_and_save_key()
    
    def _generate_and_save_key(self):
        """生成并保存默认密钥"""
        import secrets
        
        # 生成随机密钥
        encryption_key = secrets.token_hex(32)
        signing_key = secrets.token_hex(32)
        
        # 保存（注意：实际应用中应该更安全地存储）
        key_data = {
            "encryption_key": encryption_key,
            "signing_key": signing_key,
        }
        
        with open(self._key_file, 'w') as f:
            json.dump(key_data, f)
        
        # 重新初始化加密工具
        self.crypto = SaveCrypto(encryption_key, signing_key)
        
        logger.info("Generated new save encryption keys")
    
    def _load_key(self) -> Tuple[Optional[str], Optional[str]]:
        """加载保存的密钥"""
        if self._key_file.exists():
            try:
                with open(self._key_file, 'r') as f:
                    key_data = json.load(f)
                return key_data.get("encryption_key"), key_data.get("signing_key")
            except:
                pass
        return None, None
    
    def save_encrypted(self, world, slot: int = 1, description: str = "", play_time: int = 0) -> dict:
        """
        加密保存存档
        
        Args:
            world: 游戏世界
            slot: 存档槽位
            description: 存档描述
            play_time: 游戏时间
        
        Returns:
            存档元数据
        """
        # 序列化世界数据
        world_data = self._world_to_dict(world)
        
        # 创建存档数据
        save_data = SaveData(world_data, self.crypto)
        
        # 封存（加密+签名）
        sealed = save_data.seal(encrypt=self.enable_encryption)
        
        # 添加元数据
        sealed["description"] = description or f"存档 {slot}"
        sealed["play_time_seconds"] = play_time
        
        # 保存到文件
        filepath = SAVE_DIR / f"save_slot_{slot}.json"
        tmp_path = filepath.with_suffix(".tmp")
        
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(sealed, f, ensure_ascii=False, indent=2)
        
        tmp_path.replace(filepath)
        
        # 更新元数据
        metadata = {
            "slot": slot,
            "description": description or f"存档 {slot}",
            "created_time": datetime.now().isoformat(),
            "tick_count": world.tick_count,
            "play_time_seconds": play_time,
            "theme": world.theme,
            "character_count": len([c for c in world.characters if c.alive]),
            "encrypted": self.enable_encryption,
        }
        
        all_metadata = self._load_all_metadata()
        all_metadata[str(slot)] = metadata
        self._save_all_metadata(all_metadata)
        
        logger.info(f"Save encrypted to slot {slot}")
        return metadata
    
    def load_encrypted(self, slot: int = 1) -> Tuple['World', dict]:
        """
        加载加密存档
        
        Args:
            slot: 存档槽位
        
        Returns:
            (世界对象, 元数据)
        
        Raises:
            ValueError: 验证失败时抛出
        """
        filepath = SAVE_DIR / f"save_slot_{slot}.json"
        
        if not filepath.exists():
            raise FileNotFoundError(f"存档槽位 {slot} 不存在")
        
        with open(filepath, "r", encoding="utf-8") as f:
            sealed_data = json.load(f)
        
        # 检查是否是加密存档
        if sealed_data.get("encrypted", False) or "signature" in sealed_data:
            # 解封（验证+解密）
            try:
                save_data = SaveData.unseal(sealed_data, self.crypto, verify=self.verify_on_load)
                world_data = save_data.data
            except ValueError as e:
                logger.error(f"Save verification failed: {e}")
                raise
        else:
            # 旧格式存档
            world_data = sealed_data
        
        # 反序列化世界
        world = self._dict_to_world(world_data)
        
        # 获取元数据
        metadata = self.get_slot_metadata(slot)
        
        logger.info(f"Save loaded from slot {slot}")
        return world, metadata
    
    def save_with_metadata(self, world, slot: int = 1, description: str = "",
                           play_time: int = 0) -> dict:
        """带元数据的存档（兼容旧接口）"""
        return self.save_encrypted(world, slot, description, play_time)
    
    def load_with_metadata(self, slot: int = 1) -> tuple:
        """带元数据的读档（兼容旧接口）"""
        return self.load_encrypted(slot)
    
    def get_slot_metadata(self, slot: int) -> dict:
        """获取指定槽位的元数据"""
        all_metadata = self._load_all_metadata()
        return all_metadata.get(str(slot), {})
    
    def _load_all_metadata(self) -> dict:
        """加载所有元数据"""
        if self.metadata_file.exists():
            try:
                with open(self.metadata_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                return {}
        return {}
    
    def _save_all_metadata(self, metadata: dict):
        """保存所有元数据"""
        with open(self.metadata_file, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, ensure_ascii=False, indent=2)
    
    def quick_save(self, world, play_time: int = 0) -> str:
        """快速存档到槽位0"""
        metadata = self.save_encrypted(world, slot=0, description="快速存档", play_time=play_time)
        return f"已快速存档（tick {world.tick_count}）"
    
    def quick_load(self) -> tuple:
        """快速读档从槽位0"""
        return self.load_encrypted(slot=0)
    
    def compress_save(self, world, slot: int = 1) -> bool:
        """压缩存档"""
        try:
            data = self._world_to_dict(world)
            filepath = SAVE_DIR / f"save_slot_{slot}.json.gz"
            with gzip.open(filepath, 'wt', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False)
            return True
        except Exception as e:
            logger.error(f"压缩存档失败: {e}")
            return False
    
    def decompress_load(self, slot: int = 1) -> 'World':
        """解压读档"""
        try:
            filepath = SAVE_DIR / f"save_slot_{slot}.json.gz"
            if filepath.exists():
                with gzip.open(filepath, 'rt', encoding='utf-8') as f:
                    data = json.load(f)
                return self._dict_to_world(data)
            return None
        except Exception as e:
            logger.error(f"解压读档失败: {e}")
            return None
    
    def get_save_info_list(self) -> list:
        """获取带元数据的存档列表"""
        saves = []
        all_metadata = self._load_all_metadata()
        
        for slot in range(1, 6):  # 5个存档槽位
            filepath = SAVE_DIR / f"save_slot_{slot}.json"
            if filepath.exists():
                info = {
                    "slot": slot,
                    "exists": True,
                    "metadata": all_metadata.get(str(slot), {}),
                    "file_size": filepath.stat().st_size,
                    "modified_time": datetime.fromtimestamp(filepath.stat().st_mtime).isoformat(),
                }
            else:
                info = {"slot": slot, "exists": False}
            saves.append(info)
        
        return saves
    
    def delete_save(self, slot: int) -> bool:
        """删除存档"""
        try:
            filepath = SAVE_DIR / f"save_slot_{slot}.json"
            if filepath.exists():
                filepath.unlink()
            
            # 更新元数据
            all_metadata = self._load_all_metadata()
            if str(slot) in all_metadata:
                del all_metadata[str(slot)]
                self._save_all_metadata(all_metadata)
            
            return True
        except:
            return False
    
    def verify_save(self, slot: int = 1) -> Tuple[bool, str]:
        """
        验证存档完整性
        
        Args:
            slot: 存档槽位
        
        Returns:
            (是否有效, 消息)
        """
        filepath = SAVE_DIR / f"save_slot_{slot}.json"
        
        if not filepath.exists():
            return False, f"存档槽位 {slot} 不存在"
        
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                sealed_data = json.load(f)
            
            # 检查签名
            if "signature" in sealed_data and self.crypto:
                save_data = SaveData.unseal(sealed_data, self.crypto, verify=True)
                return True, "存档验证通过"
            else:
                # 无签名存档
                return True, "存档无签名（旧格式）"
            
        except ValueError as e:
            return False, f"验证失败: {e}"
        except Exception as e:
            return False, f"读取失败: {e}"
    
    def is_encryption_available(self) -> bool:
        """检查加密功能是否可用"""
        return self.crypto.is_encryption_available()


def get_enhanced_storage(
    encryption_key: Optional[str] = None,
    signing_key: Optional[str] = None,
    enable_encryption: bool = True
) -> EnhancedGameStorage:
    """获取增强版存档管理器"""
    return EnhancedGameStorage(encryption_key, signing_key, enable_encryption)


# ============================================================
# 云存储 / 云端存档 → storage_mixins.cloud
# ============================================================
from .storage_mixins.cloud import (  # noqa: E402, F401 — re-export for backward compat
    CloudStorageProvider,
    HttpApiCloudStorage,
    SimpleHttpCloudStorage,
    CloudSaveManager,
    create_http_cloud_storage,
    create_cloud_save_manager,
)
