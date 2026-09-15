# -*- coding: utf-8 -*-
"""
模板解析器 - 将 GameConfig 转换为游戏引擎可用的格式
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from typing import Dict, List, Any
from game.backend.game_config import GameConfig
from game.backend.world import World
from game.backend.character import Character, CharType
from game.backend.themes.theme_rules import THEME_RULES


class TemplateParser:
    """模板解析器 - 将配置转换为游戏对象"""
    
    @staticmethod
    def parse_config(config: GameConfig) -> Dict[str, Any]:
        """
        解析配置，返回游戏初始化所需的参数
        
        Returns:
            {
                "world": World对象,
                "characters": [Character对象列表],
                "theme_rules": 主题规则字典,
                "merged_rules": 合并后的规则,
                "ai_config": AI配置,
            }
        """
        result = {}
        
        # 1. 创建世界
        world = TemplateParser._create_world(config)
        result["world"] = world
        
        # 2. 创建角色
        characters = TemplateParser._create_characters(config)
        result["characters"] = characters
        
        # 3. 获取主题规则
        theme_rules = TemplateParser._get_theme_rules(config)
        result["theme_rules"] = theme_rules
        
        # 4. 合并规则
        merged_rules = TemplateParser._merge_rules(config, theme_rules)
        result["merged_rules"] = merged_rules
        
        # 5. 创建 AI 配置
        ai_config = TemplateParser._create_ai_config(config)
        result["ai_config"] = ai_config
        
        return result
    
    @staticmethod
    def _create_world(config: GameConfig) -> World:
        """创建世界对象"""
        world = World(map_size=(20, 20))
        
        # 设置世界名称
        if config.world.name:
            world.name = config.world.name
        
        # 设置时代背景（存储在 world 的扩展属性中）
        if hasattr(world, 'era'):
            world.era = config.world.era
        if hasattr(world, 'description'):
            world.description = f"时代：{config.world.era}\n地理：{config.world.geography}"
        
        return world
    
    @staticmethod
    def _create_characters(config: GameConfig) -> List[Character]:
        """创建角色对象列表"""
        characters = []
        
        # 创建主角
        if config.protagonist.name:
            protagonist = Character(
                name=config.protagonist.name,
                char_type=CharType.PROTAGONIST,
                pos=(10, 10),  # 默认位置
                personality=config.protagonist.personality,
                goal=config.protagonist.goal,
            )
            # 设置命运弧线
            if hasattr(protagonist, 'fate_arc'):
                protagonist.fate_arc = config.protagonist.fate_arc
            # 设置特殊能力
            if hasattr(protagonist, 'special_ability'):
                protagonist.special_ability = config.protagonist.special_ability
            characters.append(protagonist)
        
        # 创建反派
        if config.antagonist.name and config.antagonist.name != "无":
            antagonist = Character(
                name=config.antagonist.name,
                char_type=CharType.ANTAGONIST,
                pos=(15, 15),  # 默认位置
                personality=config.antagonist.personality,
                goal=config.antagonist.motivation,  # 反派的目标是动机
            )
            # 设置手段
            if hasattr(antagonist, 'methods'):
                antagonist.methods = config.antagonist.methods
            characters.append(antagonist)
        
        # 创建 NPC
        for npc_config in config.npcs:
            if npc_config.name:
                npc = Character(
                    name=npc_config.name,
                    char_type=CharType.NPC,
                    pos=(12, 12),  # 默认位置
                    personality=npc_config.personality,
                    goal=npc_config.role_position,  # NPC 的目标是角色定位
                )
                # 设置关系
                if hasattr(npc, 'relationship'):
                    npc.relationship = npc_config.relationship
                # 设置秘密
                if hasattr(npc, 'secret'):
                    npc.secret = npc_config.secret
                characters.append(npc)
        
        return characters
    
    @staticmethod
    def _get_theme_rules(config: GameConfig) -> Dict:
        """获取主题规则"""
        theme_name = config.theme.name
        
        # 从预设规则中获取
        if theme_name in THEME_RULES:
            return THEME_RULES[theme_name]
        
        # 返回默认规则
        return {
            "permissions": {
                "allow_magic": False,
                "allow_combat": False,
                "allow_modern_items": True,
            },
            "iron_rules": [],
            "behavior_limits": [],
            "forbidden_words": [],
        }
    
    @staticmethod
    def _merge_rules(config: GameConfig, theme_rules: Dict) -> Dict:
        """合并用户自定义规则和主题规则"""
        merged = theme_rules.copy()
        
        # 添加用户自定义的禁止规则
        if config.rules.forbidden:
            if "behavior_limits" not in merged:
                merged["behavior_limits"] = []
            merged["behavior_limits"].extend(config.rules.forbidden)
        
        # 添加用户自定义的铁律
        if config.rules.iron_rules:
            if "iron_rules" not in merged:
                merged["iron_rules"] = []
            merged["iron_rules"].extend(config.rules.iron_rules)
        
        # 添加用户自定义的特殊规则
        if config.rules.special_rules:
            if "special_rules" not in merged:
                merged["special_rules"] = []
            merged["special_rules"].extend(config.rules.special_rules)
        
        # 添加允许的行为
        if config.rules.allowed:
            if "allowed" not in merged:
                merged["allowed"] = []
            merged["allowed"].extend(config.rules.allowed)
        
        return merged
    
    @staticmethod
    def _create_ai_config(config: GameConfig) -> Dict:
        """创建 AI 配置"""
        ai_config = {
            "theme": config.theme.name,
            "theme_style": config.theme.style,
            "core_conflict": config.theme.core_conflict,
            "core_law": config.theme.core_law,
            "world_name": config.world.name,
            "world_era": config.world.era,
            "world_geography": config.world.geography,
            "world_rules": config.world.core_rules,
            "world_taboos": config.world.taboos,
            "special_scenes": config.world.special_scenes,
            "start_event": config.plot.start_event,
            "core_suspense": config.plot.core_suspense,
            "expected_ending": config.plot.expected_ending,
        }
        
        # 添加主角信息
        if config.protagonist.name:
            ai_config["protagonist_name"] = config.protagonist.name
            ai_config["protagonist_personality"] = config.protagonist.personality
            ai_config["protagonist_goal"] = config.protagonist.goal
            ai_config["protagonist_fate_arc"] = config.protagonist.fate_arc
            ai_config["protagonist_ability"] = config.protagonist.special_ability
        
        # 添加反派信息
        if config.antagonist.name and config.antagonist.name != "无":
            ai_config["antagonist_name"] = config.antagonist.name
            ai_config["antagonist_personality"] = config.antagonist.personality
            ai_config["antagonist_motivation"] = config.antagonist.motivation
            ai_config["antagonist_methods"] = config.antagonist.methods
        
        return ai_config
    
    @staticmethod
    def apply_to_engine(engine, config: GameConfig):
        """
        将配置应用到游戏引擎
        
        Args:
            engine: 游戏引擎实例
            config: 游戏配置
        """
        parsed = TemplateParser.parse_config(config)
        
        # 应用世界
        if hasattr(engine, 'world'):
            engine.world = parsed["world"]
        
        # 应用角色
        if hasattr(engine, 'world') and parsed["characters"]:
            engine.world.characters = parsed["characters"]
        
        # 应用主题规则
        if hasattr(engine, 'theme'):
            engine.theme = config.theme.name
        
        # 应用合并规则
        if hasattr(engine, 'merged_rules'):
            engine.merged_rules = parsed["merged_rules"]
        
        # 应用 AI 配置
        if hasattr(engine, 'ai_config'):
            engine.ai_config = parsed["ai_config"]
        
        # 应用到叙事引擎
        if hasattr(engine, 'narrative_engine'):
            ne = engine.narrative_engine
            if hasattr(ne, 'theme'):
                ne.theme = config.theme.name
            if hasattr(ne, '_merged_rules'):
                ne._merged_rules = parsed["merged_rules"]
        
        return parsed


# 叙事格式验证器
class NarrativeValidator:
    """叙事格式验证器 - 确保叙事输出符合模板规范"""
    
    @staticmethod
    def validate(narrative: str, config: GameConfig, merged_rules: Dict) -> Dict[str, Any]:
        """
        验证叙事是否符合模板规范
        
        Returns:
            {
                "valid": bool,
                "issues": [问题列表],
                "suggestions": [建议列表],
            }
        """
        result = {
            "valid": True,
            "issues": [],
            "suggestions": [],
        }
        
        # 1. 检查禁止词汇
        forbidden_words = merged_rules.get("forbidden_words", [])
        for word in forbidden_words:
            if word in narrative:
                result["valid"] = False
                result["issues"].append(f"包含禁止词汇：{word}")
        
        # 2. 检查是否包含主角名字
        if config.protagonist.name and config.protagonist.name not in narrative:
            result["suggestions"].append("建议叙事中包含主角")
        
        # 3. 检查叙事格式（应该以 [叙事] 开头或包含角色名）
        if not narrative.strip().startswith("[叙事]"):
            # 检查是否包含任何角色名
            has_character = False
            if config.protagonist.name and config.protagonist.name in narrative:
                has_character = True
            if config.antagonist.name and config.antagonist.name in narrative:
                has_character = True
            for npc in config.npcs:
                if npc.name and npc.name in narrative:
                    has_character = True
                    break
            
            if not has_character:
                result["suggestions"].append("建议叙事格式：角色 + 场景 + 事件")
        
        # 4. 检查是否违反铁律
        iron_rules = merged_rules.get("iron_rules", [])
        for rule in iron_rules:
            # 简单检查：如果铁律说"无超自然力量"，检查是否有魔法相关词汇
            if "无超自然" in rule or "无魔法" in rule:
                magic_words = ["魔法", "法术", "灵气", "修仙", "神仙"]
                for word in magic_words:
                    if word in narrative:
                        result["valid"] = False
                        result["issues"].append(f"违反铁律：{rule}")
                        break
        
        return result
    
    @staticmethod
    def format_narrative(narrative: str, config: GameConfig) -> str:
        """
        格式化叙事，使其符合模板规范
        
        格式：[叙事] 角色1（+角色2）+ 场景 + 事件
        """
        # 如果已经以 [叙事] 开头，直接返回
        if narrative.strip().startswith("[叙事]"):
            return narrative
        
        # 否则添加前缀
        return f"[叙事] {narrative}"


# 测试代码
if __name__ == "__main__":
    from game.backend.game_config import PRESET_TEMPLATES
    
    # 测试解析
    config = PRESET_TEMPLATES["修仙"]
    config.protagonist.name = "李青云"
    config.protagonist.personality = "冷静理性"
    config.protagonist.goal = "筑基飞升"
    
    parsed = TemplateParser.parse_config(config)
    print("解析结果：")
    print(f"世界：{parsed['world'].name if hasattr(parsed['world'], 'name') else '未命名'}")
    print(f"角色数：{len(parsed['characters'])}")
    print(f"主题规则：{parsed['theme_rules'].get('iron_rules', [])[:2]}")
    
    # 测试验证
    test_narrative = "李青云在宗门炼丹房，尝试炼制筑基丹。"
    result = NarrativeValidator.validate(test_narrative, config, parsed['merged_rules'])
    print(f"\n验证结果：{result}")

