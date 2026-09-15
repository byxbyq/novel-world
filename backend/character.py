"""角色 Agent 系统"""

import sys, os
from dataclasses import dataclass, field
from .config import CharacterConfig

# Goal 统一数据源：backend 不再独立定义，改为从 novel_world/engine/core 导入
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)
from novel_world.engine.core.goal import Goal  # noqa: E402  — 唯一真实定义

# 保持向后兼容：Goal 类名在同一命名空间可用
__all__ = ["Goal", "CharacterAgent"]


class CharacterAgent:
    """角色 Agent —— 拥有独立人格、目标和记忆的个体"""

    def __init__(self, config: CharacterConfig):
        self.config = config
        self.name = config.name

        # 目标系统
        self.long_term_goal = Goal(content=config.long_term_goal, priority=10)
        self.short_term_goals: list[Goal] = [
            Goal(content=g, priority=7) for g in config.short_term_goals
        ]
        self.goal_history: list[str] = []   # 目标变更记录

        # 记忆系统
        self.memory: list[dict] = []        # 角色记忆事件
        self.memory.append({
            "type": "origin",
            "content": f"我来到了这个世界。我的目标是：{config.long_term_goal}",
        })

        # 关系系统
        self.relationships: dict[str, dict] = {}  # {角色名: {"态度": "友好", "描述": "..."}}
        for other_name, desc in (config.initial_relationships or {}).items():
            self.relationships[other_name] = {"态度": "中立", "描述": desc}

        # 属性值（体力/智力/攻击/防御等）
        self.attrs: dict = {}

        # 当前状态
        self.current_location: str = config.initial_location or ""
        self.current_action: str = ""
        self.current_mood: str = "平静"

        # A/C/B 三层动态人格（由 _post_chapter_status_update 每章更新）
        self.action_style: str = ""       # A层：当前行为风格/措辞习惯
        self.current_drive: str = ""      # C层：当前核心驱动力总结
        self.cognitive_boundary: str = "" # B层：认知边界/已知信息/立场
        self._init_layered_persona()

    # ── 目标操作 ──

    def add_goal(self, description: str, priority: int = 5):
        """新增目标"""
        self.short_term_goals.append(Goal(content=description, priority=priority))

    def update_goal(self, old_desc: str, new_desc: str, reason: str):
        """变更目标"""
        for g in self.short_term_goals:
            if g.description == old_desc:
                g.description = new_desc
                g.progress = "未开始"
                g.reason_changed = reason
                self.goal_history.append(f"目标变更：{old_desc} → {new_desc}（原因：{reason}）")
                return
        if self.long_term_goal.description == old_desc:
            self.long_term_goal.description = new_desc
            self.long_term_goal.progress = "未开始"
            self.long_term_goal.reason_changed = reason
            self.goal_history.append(f"长期目标变更：{old_desc} → {new_desc}（原因：{reason}）")

    def abandon_goal(self, description: str, reason: str):
        """放弃目标"""
        for g in self.short_term_goals:
            if g.description == description:
                g.progress = "已放弃"
                g.reason_changed = reason
                self.goal_history.append(f"目标放弃：{description}（原因：{reason}）")
                return

    def active_goals_text(self) -> str:
        """活跃目标的文本描述（不含权重）"""
        lines = []
        if self.long_term_goal.progress not in ("已完成", "已放弃"):
            lines.append(f"长期目标（优先级{self.long_term_goal.priority}）：{self.long_term_goal.description} [{self.long_term_goal.progress}]")
        for g in self.short_term_goals:
            if g.progress not in ("已完成", "已放弃"):
                lines.append(f"短期目标（优先级{g.priority}）：{g.description} [{g.progress}]")
        return "\n".join(lines) if lines else "（暂无活跃目标）"

    def goals_with_weights_text(self) -> str:
        """含权重的活跃目标文本（修复三：供 AI prompt 使用，引导优先推进高权重目标）"""
        lines = []
        if self.long_term_goal.progress not in ("已完成", "已放弃"):
            lines.append(
                f"长期目标（权重{self.long_term_goal.weight:.1f}，优先级{self.long_term_goal.priority}）："
                f"{self.long_term_goal.description} [{self.long_term_goal.progress}]"
            )
        for g in self.short_term_goals:
            if g.progress not in ("已完成", "已放弃"):
                lines.append(
                    f"短期目标（权重{g.weight:.1f}，优先级{g.priority}）："
                    f"{g.description} [{g.progress}]"
                )
        return "\n".join(lines) if lines else "（暂无活跃目标）"

    def select_primary_goal(self) -> Goal | None:
        """按 weight 加权随机选择当前应推进的目标（修复三：Goal 权重排序）。

        高权重目标有更高概率被选中。返回被选中的 Goal 或 None。
        """
        import random
        active = []
        if self.long_term_goal.progress not in ("已完成", "已放弃"):
            active.append(self.long_term_goal)
        for g in self.short_term_goals:
            if g.progress not in ("已完成", "已放弃"):
                active.append(g)
        if not active:
            return None
        weights = [max(g.weight, 0.01) for g in active]  # 保证至少极小权重
        return random.choices(active, weights=weights, k=1)[0]

    # ── 记忆操作 ──

    def remember(self, event_type: str, content: str):
        """记录记忆"""
        self.memory.append({"type": event_type, "content": content})
        # 限制记忆数量，保留最近 30 条
        if len(self.memory) > 30:
            self.memory = self.memory[-30:]

    def recent_memory_text(self, n: int = 8) -> str:
        """最近 n 条记忆文本"""
        if not self.memory:
            return "（我什么都不记得了）"
        return "\n".join(
            f"- [{m['type']}] {m['content']}" for m in self.memory[-n:]
        )

    # ── 关系操作 ──

    def update_relationship(self, other_name: str, attitude: str, reason: str):
        """更新与其他角色的关系"""
        if other_name not in self.relationships:
            self.relationships[other_name] = {"态度": "中立", "描述": ""}
        old = self.relationships[other_name]["态度"]
        self.relationships[other_name]["态度"] = attitude
        self.relationships[other_name]["描述"] = reason
        self.remember("关系变化", f"我对{other_name}的态度从「{old}」变为「{attitude}」：{reason}")

    def relationship_text(self) -> str:
        """关系文本摘要"""
        if not self.relationships:
            return "（暂无特殊关系）"
        lines = []
        for name, rel in self.relationships.items():
            lines.append(f"{name}：{rel['态度']} - {rel['描述']}")
        return "\n".join(lines)

    # ── A/C/B 三层人格 ──

    def _init_layered_persona(self):
        """从 config 静态字段初始化三层人格，后续由 _post_chapter_status_update 动态更新"""
        abilities = getattr(self.config, 'abilities', None) or []
        weaknesses = getattr(self.config, 'weaknesses', None) or []
        personality = getattr(self.config, 'personality', '') or ''
        self.action_style = (
            f"性格：{personality}。"
            f"擅长：{'，'.join(abilities) if abilities else '无特殊'}。"
            f"弱点：{'，'.join(weaknesses) if weaknesses else '无特殊'}。"
        )
        short = "；".join(self.config.short_term_goals) if self.config.short_term_goals else "无"
        self.current_drive = f"长期目标：{self.config.long_term_goal or '无'}。短期目标：{short}"
        background = getattr(self.config, 'background', '') or ''
        rels = getattr(self.config, 'initial_relationships', None) or {}
        rel_text = "；".join(f"{k}: {v}" for k, v in rels.items()) if rels else "暂无"
        self.cognitive_boundary = f"背景：{background}。初始关系：{rel_text}"

    def layered_prompt_text(self) -> str:
        """将 A/C/B 三层动态人格组装为 prompt 注入片段"""
        return (
            f"【行为风格（A层）】{self.action_style}\n\n"
            f"【当前驱动力（C层）】{self.current_drive}\n\n"
            f"【认知边界（B层）】{self.cognitive_boundary}"
        )

    # ── 综合态 ──

    def full_state_text(self) -> str:
        """角色完整状态文本（用于 AI prompt）——包含能力/弱点/属性"""
        parts = [
            f"姓名：{self.name}，性别：{getattr(self.config, 'gender', '') or '男'}，年龄：{getattr(self.config, 'age', 20) or 20}",
            f"当前心情：{self.current_mood}",
            f"当前位置：{self.current_location or '未知'}",
        ]
        # 能力与弱点（从 config 读取）
        abilities = getattr(self.config, 'abilities', None) or []
        weaknesses = getattr(self.config, 'weaknesses', None) or []
        if abilities:
            parts.append(f"能力/特长：{'，'.join(abilities)}")
        if weaknesses:
            parts.append(f"弱点/短板：{'，'.join(weaknesses)}")
        # 数值属性（体力/智力/攻击/防御等）
        if self.attrs:
            attr_text = "，".join(f"{k}={v}" for k, v in self.attrs.items())
            parts.append(f"属性值：{attr_text}")
        goals = self.active_goals_text()
        if goals:
            parts.append(f"当前目标：\n{goals}")
        parts.append(f"近期记忆：\n{self.recent_memory_text()}")
        rel = self.relationship_text()
        if rel != "（暂无特殊关系）":
            parts.append(f"人际关系：\n{rel}")
        return "\n\n".join(parts)
