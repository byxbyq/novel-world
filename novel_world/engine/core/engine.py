# -*- coding: utf-8 -*-
"""
\u63a8\u6f14\u5f15\u64ce - \u6838\u5fc3\u6e38\u620f\u903b\u8f91
"""
import os
import random
import threading
import logging
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from .ai_client import AIClient

from .world import World, TileType, Faction
from .character import Character, CharType, CharState, generate_random_character
from .events import NarrativeEngine
from .story import StoryGenerator
from .themes.custom_rules import CustomRules
from .rule_validator import RuleValidator
from .item_system import ItemManager, ItemValidator, get_item_manager
from .dialogue_system import DialogueSystem, get_dialogue_system
from .interaction_system import InteractionSystem, get_interaction_system
from .fate_system import FateSystem, get_fate_system
from .narrative_corrector import NarrativeCorrector

from .engine_mixins import LifecycleMixin, SimulationMixin, RulesMixin


class Engine(LifecycleMixin, SimulationMixin, RulesMixin):
    """\u63a8\u6f14\u5f15\u64ce"""
    # 所有方法已按功能域提取至 engine_mixins/ 子目录
    pass
