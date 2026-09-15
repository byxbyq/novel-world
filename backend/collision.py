"""碰撞引擎 —— 处理角色之间的互动与冲突"""

from .character import CharacterAgent
from .world import World
from .ai_client import chat, character_agent_prompt
from novel_world.engine.core.prompt_registry import PromptRegistry


class CollisionEngine:
    """碰撞引擎：当两个角色处于同一位置时，触发互动碰撞"""

    def process_collision(
        self,
        char_a: CharacterAgent,
        char_b: CharacterAgent,
        world: World,
    ) -> dict:
        """
        处理两个角色的碰撞互动
        返回碰撞结果：action_a, action_b, narrative, goal_changes
        """
        prompt = PromptRegistry.get(
            "collision_event",
            char_a_name=char_a.name,
            char_b_name=char_b.name,
            location=world.get_character_position(char_a.name),
            char_a_state=char_a.full_state_text(),
            char_b_state=char_b.full_state_text(),
            relationship=char_a.relationships.get(char_b.name, {}).get('描述', '初次相遇'),
        )
        response = chat(
            system_prompt=character_agent_prompt(
                "", world.config.to_prompt_text(), world.recent_events()
            ),
            user_prompt=prompt,
            temperature=0.8,
        )
        return self._parse_collision_result(response, char_a, char_b)

    def _parse_collision_result(self, response: str, char_a: CharacterAgent, char_b: CharacterAgent) -> dict:
        """解析碰撞结果"""
        result = {
            "narrative": "",
            "goal_changes": [],
            "relationship_changes": [],
        }

        section = None
        for line in response.split("\n"):
            line = line.strip()
            if "【叙事】" in line:
                section = "narrative"
                continue
            elif "【目标变化】" in line:
                section = "goal"
                continue
            elif "【关系变化】" in line:
                section = "relation"
                continue
            if not line:
                continue

            if section == "narrative":
                result["narrative"] += line + "\n"
            elif section == "goal" and line != "无":
                result["goal_changes"].append(line)
            elif section == "relation" and line != "无":
                result["relationship_changes"].append(line)

        # 应用目标变化
        for change in result["goal_changes"]:
            self._apply_goal_change(change, char_a, char_b)

        # 应用关系变化
        for change in result["relationship_changes"]:
            self._apply_relationship_change(change, char_a, char_b)

        return result

    def _apply_goal_change(self, change: str, char_a: CharacterAgent, char_b: CharacterAgent):
        """解析并应用目标变化"""
        # 格式："角色名：原目标 → 新目标"
        try:
            name_part, goal_part = change.split("：", 1)
            old_new = goal_part.strip().split("→")
            if len(old_new) != 2:
                return
            old_goal, new_goal = old_new[0].strip(), old_new[1].strip()
            target = char_a if char_a.name == name_part.strip() else char_b
            target.update_goal(old_goal, new_goal, f"与{char_a.name if target == char_b else char_b.name}的碰撞")
        except (ValueError, AttributeError):
            pass

    def _apply_relationship_change(self, change: str, char_a: CharacterAgent, char_b: CharacterAgent):
        """解析并应用关系变化"""
        # 格式："角色名对角色名：旧态度 → 新态度，原因"
        try:
            pair, rest = change.split("：", 1)
            names = pair.split("对")
            if len(names) != 2:
                return
            actor, target = names[0].strip(), names[1].strip()

            attitude_part = rest.strip()
            if "→" in attitude_part:
                parts = attitude_part.split("→")
                new_attitude = parts[1].split("，")[0].split(",")[0].strip()
                reason = parts[1].split("，", 1)[1].strip() if "，" in parts[1] else ""
            else:
                new_attitude = attitude_part.split("，")[0].split(",")[0].strip()
                reason = attitude_part.split("，", 1)[1].strip() if "，" in attitude_part else ""

            actor_obj = char_a if char_a.name == actor else char_b
            actor_obj.update_relationship(target, new_attitude, reason)
        except (ValueError, AttributeError):
            pass
