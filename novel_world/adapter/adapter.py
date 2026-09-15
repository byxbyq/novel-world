# -*- coding: utf-8 -*-
"""
EngineAdapter — 薄桥接层

对外暴露与 backend.engine.GameEngine 完全相同的 API 签名，
内部将调用转换为 novel_world/engine 重型引擎的执行。

所有方法已按功能域提取至 adapter_mixins/ 子目录：
  - LifecycleMixin  — __init__ / init_game / save / load / get_state / 角色管理
  - ChapterMixin    — advance_tick / run_chapter / _character_act / 章节执行
  - QualityMixin    — timeline检查 / 终局结算 / DM / 势力管理
"""

import logging

from .adapter_mixins import LifecycleMixin, ChapterMixin, QualityMixin

logger = logging.getLogger("EngineAdapter")


from .adapter_mixins import LifecycleMixin, ChapterMixin, QualityMixin  # noqa: E402


class EngineAdapter(LifecycleMixin, ChapterMixin, QualityMixin):
    """薄桥接：对外 = backend.GameEngine，对内 = novel_world/engine"""

    # 所有方法已按功能域提取至 adapter_mixins/ 子目录：
    #   LifecycleMixin  — __init__ / init_game / save / load / get_state / 角色管理
    #   ChapterMixin    — advance_tick / run_chapter / _character_act / 章节执行
    #   QualityMixin    — timeline检查 / 终局结算 / DM / 势力管理
    pass
