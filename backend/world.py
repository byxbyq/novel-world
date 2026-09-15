"""世界状态管理"""

from .config import WorldConfig


class World:
    """世界层 —— 天道管理的世界状态"""

    def __init__(self, config: WorldConfig):
        self.config = config
        self.current_chapter: int = 0
        self.events: list[dict] = []         # 世界事件列表
        self.character_positions: dict[str, str] = {}  # 角色当前位置

    def advance_chapter(self) -> int:
        """进入下一章"""
        self.current_chapter += 1
        return self.current_chapter

    def add_event(self, event_type: str, description: str, involved_characters: list[str]):
        """记录世界事件"""
        self.events.append({
            "chapter": self.current_chapter,
            "type": event_type,
            "description": description,
            "involved": involved_characters[:],
        })

    def recent_events(self, n: int = 5) -> str:
        """获取最近 n 个世界事件的文本"""
        if not self.events:
            return "（尚无世界事件）"
        recent = self.events[-n:]
        lines = []
        for e in recent:
            chars = "、".join(e["involved"])
            lines.append(f"第{e['chapter']}章 - {e['type']}：{e['description']}（涉及：{chars}）")
        return "\n".join(lines)

    def set_character_position(self, char_name: str, location: str):
        self.character_positions[char_name] = location

    def get_character_position(self, char_name: str) -> str:
        return self.character_positions.get(char_name, "未知")

    def who_is_nearby(self, char_name: str, threshold: str = None) -> list[str]:
        """找出和某个角色在同一位置的其他角色"""
        pos = self.character_positions.get(char_name, "")
        if not pos:
            return []
        return [name for name, loc in self.character_positions.items()
                if loc == pos and name != char_name]

    def get_state_summary(self) -> str:
        """世界状态摘要"""
        return f"第{self.current_chapter}章 | 世界事件数：{len(self.events)}"
