# -*- coding: utf-8 -*-
"""
碰撞权重加载器 — 从 weights.yaml 读取配置，提供默认值兜底

使用方式：
    from .weight_loader import WeightConfig
    w = WeightConfig.load()
    priority = w.goal_keyword_opposition
"""

import os
import logging
import yaml

logger = logging.getLogger("WeightLoader")

# 默认权重常量（与 weights.example.yaml 保持同步）
_DEFAULT_WEIGHTS = {
    "goal_keyword_opposition": 50,
    "goal_character_bidirectional": 100,
    "goal_character_unidirectional": 80,
    "faction_direct_conflict": 50,
    "faction_enemy_conflict": 70,
    "faction_territory_conflict": 75,
    "faction_resource_conflict": 75,
    "faction_full_confrontation": 90,
    "faction_target_conflict": 65,
    "resource_contention": 60,
    "perception_default": 0,
    "capability_default": 0,
    "proximity_default": 0,
}

_DEFAULT_THRESHOLDS = {
    "proximity": 3,
    "combat_stalemate": 1.5,
    "combat_crush": 2.5,
    "capability_diff_threshold": 0,
}

_DEFAULT_CONSTRAINTS = {
    "min_weight": 0,
    "max_weight": 100,
}

_CONFIG_FILE = os.path.join(os.path.dirname(__file__), "weights.yaml")


class WeightConfig:
    """碰撞权重配置，属性名与 YAML weights 键名一一对应"""

    _instance = None

    def __init__(self, weights: dict, thresholds: dict, constraints: dict):
        self._weights = weights
        self._thresholds = thresholds
        self._constraints = constraints

    # ── 权重属性 ──
    @property
    def goal_keyword_opposition(self) -> int:
        return int(self._weights["goal_keyword_opposition"])

    @property
    def goal_character_bidirectional(self) -> int:
        return int(self._weights["goal_character_bidirectional"])

    @property
    def goal_character_unidirectional(self) -> int:
        return int(self._weights["goal_character_unidirectional"])

    @property
    def faction_direct_conflict(self) -> int:
        return int(self._weights["faction_direct_conflict"])

    @property
    def faction_enemy_conflict(self) -> int:
        return int(self._weights["faction_enemy_conflict"])

    @property
    def faction_territory_conflict(self) -> int:
        return int(self._weights["faction_territory_conflict"])

    @property
    def faction_resource_conflict(self) -> int:
        return int(self._weights["faction_resource_conflict"])

    @property
    def faction_full_confrontation(self) -> int:
        return int(self._weights["faction_full_confrontation"])

    @property
    def faction_target_conflict(self) -> int:
        return int(self._weights["faction_target_conflict"])

    @property
    def resource_contention(self) -> int:
        return int(self._weights["resource_contention"])

    @property
    def perception_default(self) -> int:
        return int(self._weights["perception_default"])

    @property
    def capability_default(self) -> int:
        return int(self._weights["capability_default"])

    @property
    def proximity_default(self) -> int:
        return int(self._weights["proximity_default"])

    # ── 阈值属性 ──
    @property
    def proximity_threshold(self) -> int:
        return int(self._thresholds["proximity"])

    @property
    def combat_stalemate(self) -> float:
        return float(self._thresholds["combat_stalemate"])

    @property
    def combat_crush(self) -> float:
        return float(self._thresholds["combat_crush"])

    @property
    def capability_diff_threshold(self) -> int:
        return int(self._thresholds["capability_diff_threshold"])

    # ── 便利方法 ──
    def clamp(self, value: int) -> int:
        """将权重值限制在 [min_weight, max_weight] 范围内"""
        lo = int(self._constraints.get("min_weight", 0))
        hi = int(self._constraints.get("max_weight", 100))
        return max(lo, min(hi, value))

    def to_dict(self) -> dict:
        return {
            "weights": dict(self._weights),
            "thresholds": dict(self._thresholds),
            "constraints": dict(self._constraints),
        }

    # ── 加载 ──
    @classmethod
    def load(cls, reload: bool = False) -> "WeightConfig":
        """加载配置，单例模式。传入 reload=True 强制重新读取。"""
        if cls._instance is not None and not reload:
            return cls._instance

        weights = dict(_DEFAULT_WEIGHTS)
        thresholds = dict(_DEFAULT_THRESHOLDS)
        constraints = dict(_DEFAULT_CONSTRAINTS)

        if os.path.exists(_CONFIG_FILE):
            try:
                with open(_CONFIG_FILE, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f) or {}
                if "weights" in data and isinstance(data["weights"], dict):
                    for k, v in data["weights"].items():
                        if k in _DEFAULT_WEIGHTS:
                            weights[k] = int(v)
                if "thresholds" in data and isinstance(data["thresholds"], dict):
                    for k, v in data["thresholds"].items():
                        if k in _DEFAULT_THRESHOLDS:
                            thresholds[k] = v
                if "constraints" in data and isinstance(data["constraints"], dict):
                    for k, v in data["constraints"].items():
                        if k in _DEFAULT_CONSTRAINTS:
                            constraints[k] = v
                logger.info("已从 %s 加载碰撞权重配置", _CONFIG_FILE)
            except Exception as e:
                logger.warning("加载权重配置文件失败 (%s)，使用默认值", e)
        else:
            logger.info("权重配置文件不存在，使用默认权重")

        cls._instance = cls(weights, thresholds, constraints)
        return cls._instance

    @classmethod
    def reload(cls):
        """强制重新加载配置"""
        return cls.load(reload=True)
