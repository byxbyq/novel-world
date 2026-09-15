# -*- coding: utf-8 -*-
"""
自定义规则系统 - 覆盖层
优先级：自定义规则 > 基础主题规则
支持：权限开关、禁词增删、规则增改、自定义主题
"""

from copy import deepcopy


class CustomRules:
    """自定义规则 - 作为基础规则的覆盖层"""

    def __init__(self, base_theme="日常"):
        self.base_theme = base_theme

        # 权限覆盖（None = 不覆盖，用基础值）
        self.permissions = {
            "allow_magic": None,
            "allow_combat": None,
            "allow_modern_items": None,
        }

        # 规则覆盖（空列表 = 不覆盖，用基础值；非空 = 替换基础）
        self.iron_rules = []
        self.behavior_limits = []
        self.faction_rules = []

        # 禁词增删
        self.forbidden_words_remove = []
        self.forbidden_words_add = []

        # 力量体系和场景（空字符串 = 不覆盖）
        self.power_system = ""
        self.narrative_style = ""
        self.allowed_scenes = []

    def merge(self):
        """
        合并基础规则 + 自定义规则
        优先级：自定义 > 基础
        返回合并后的最终规则字典
        """
        from .theme_rules import THEME_RULES

        # 自定义主题 = 空白基底
        if self.base_theme == "custom":
            base = {
                "permissions": {
                    "allow_magic": True,
                    "allow_combat": True,
                    "allow_modern_items": True,
                },
                "iron_rules": [],
                "behavior_limits": [],
                "faction_rules": [],
                "forbidden_words": [],
                "power_system": "",
                "narrative_style": "",
                "allowed_scenes": [],
            }
        else:
            base = THEME_RULES.get(self.base_theme, THEME_RULES["日常"])
            base = deepcopy(base)

        # 1. 权限：自定义覆盖
        for key, val in self.permissions.items():
            if val is not None:
                base["permissions"][key] = val

        # 2. 规则列表：自定义非空则替换
        if self.iron_rules:
            base["iron_rules"] = list(self.iron_rules)
        if self.behavior_limits:
            base["behavior_limits"] = list(self.behavior_limits)
        if self.faction_rules:
            base["faction_rules"] = list(self.faction_rules)

        # 3. 禁词：基础 - 删除 + 新增
        base_set = set(base["forbidden_words"])
        base_set -= set(self.forbidden_words_remove)
        base_set |= set(self.forbidden_words_add)
        base["forbidden_words"] = list(base_set)

        # 4. 力量体系和场景
        if self.power_system:
            base["power_system"] = self.power_system
        if self.narrative_style:
            base["narrative_style"] = self.narrative_style
        if self.allowed_scenes:
            base["allowed_scenes"] = list(self.allowed_scenes)

        return base

    def to_dict(self):
        """序列化为字典（用于存档）"""
        d = {
            "base_theme": self.base_theme,
            "permissions": {},
            "iron_rules": self.iron_rules,
            "behavior_limits": self.behavior_limits,
            "faction_rules": self.faction_rules,
            "forbidden_words_remove": self.forbidden_words_remove,
            "forbidden_words_add": self.forbidden_words_add,
            "power_system": self.power_system,
            "narrative_style": self.narrative_style,
            "allowed_scenes": self.allowed_scenes,
        }
        # 只序列化非None的权限覆盖
        for k, v in self.permissions.items():
            if v is not None:
                d["permissions"][k] = v
        return d

    @classmethod
    def from_dict(cls, data):
        """从字典反序列化"""
        cr = cls(base_theme=data.get("base_theme", "日常"))
        # 恢复权限
        for k, v in data.get("permissions", {}).items():
            cr.permissions[k] = v
        cr.iron_rules = data.get("iron_rules", [])
        cr.behavior_limits = data.get("behavior_limits", [])
        cr.faction_rules = data.get("faction_rules", [])
        cr.forbidden_words_remove = data.get("forbidden_words_remove", [])
        cr.forbidden_words_add = data.get("forbidden_words_add", [])
        cr.power_system = data.get("power_system", "")
        cr.narrative_style = data.get("narrative_style", "")
        cr.allowed_scenes = data.get("allowed_scenes", [])
        return cr

    def reset(self):
        """重置所有自定义规则"""
        self.permissions = {k: None for k in self.permissions}
        self.iron_rules = []
        self.behavior_limits = []
        self.faction_rules = []
        self.forbidden_words_remove = []
        self.forbidden_words_add = []
        self.power_system = ""
        self.narrative_style = ""
        self.allowed_scenes = []

    def is_customized(self):
        """检查是否有任何自定义规则"""
        if any(v is not None for v in self.permissions.values()):
            return True
        if self.iron_rules or self.behavior_limits or self.faction_rules:
            return True
        if self.forbidden_words_remove or self.forbidden_words_add:
            return True
        if self.power_system or self.narrative_style or self.allowed_scenes:
            return True
        return False
