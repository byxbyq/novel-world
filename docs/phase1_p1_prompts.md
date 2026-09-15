# Phase1 P1 — 章节收尾 Prompt 优化 + Prompt 集中管理

## 概述

两项合并处理：
- **任务A**：优化章节生成 prompt，新增悬念收尾/过渡收尾/终局收尾三种指令
- **任务B**：新建 `PromptRegistry` 类，将散落在 11 个文件中的 25+ 处硬编码 prompt 统一管理

---

## 任务A：章节收尾 Prompt 优化

### 改动文件

| 文件 | 改动 | 说明 |
|------|------|------|
| `backend/narrative.py` | 修改 `generate_chapter` | 新增 `is_last_chapter` / `has_conflicts` 参数，追加三种收尾指令 |
| `backend/engine.py` | 修改 `run_chapter` | 传入 `is_last_chapter` 和 `has_conflicts` |

### 收尾逻辑

| 场景 | 条件 | 指令 |
|------|------|------|
| 终局收尾 | `is_last_chapter=True` | 收束所有伏笔和角色命运线 |
| 悬念收尾 | 最后一帧有冲突 | 保持张力，如"他握紧长剑，黑暗中传来脚步声..." |
| 过渡收尾 | 日常场景 | 自然过渡，如"夜色渐深，明天又将是新的一天" |

### 验证

`run_demo.py` 3 章 60 tick 正常生成，0 报错。

---

## 任务B：Prompt 集中管理

### 新建文件

| 文件 | 说明 |
|------|------|
| `novel_world/engine/core/prompt_registry.py` | `PromptRegistry` 类，含 26 个内置 prompt 模板 |

### PromptRegistry API

```python
PromptRegistry.register(name: str, template: str)   # 注册模板
PromptRegistry.get(name: str, **kwargs) -> str       # 获取+格式化（安全转义花括号）
PromptRegistry.get_raw(name: str) -> str             # 获取原始模板
PromptRegistry.list_all() -> List[str]               # 列出所有已注册名称
```

### 已注册 Prompt 清单（26 个）

| 名称 | 用途 | 原始位置 |
|------|------|----------|
| `tian_dao` | 天道 system prompt | `backend/ai_client.py` |
| `character_agent` | 角色 Agent system prompt | `backend/ai_client.py` |
| `chapter_generation` | 章节生成（含新增收尾指令） | `backend/narrative.py` |
| `world_event` | 世界事件生成 | `backend/narrative.py` |
| `character_action` | 角色行动决策 | `backend/engine.py` |
| `collision_event` | 碰撞事件叙事 | `backend/collision.py` |
| `finale` | 终局章节 | `backend/engine.py` |
| `goal_alignment` | 目标与主线关联度分析 | `backend/engine.py` |
| `goal_analyst_system` | 叙事分析 system prompt | `backend/engine.py` |
| `world_builder_system` | 世界构建 system prompt | `backend/ai_client.py` |
| `world_builder_user` | 世界构建 user prompt | `backend/ai_client.py` |
| `character_designer_system` | 角色设计 system prompt | `backend/ai_client.py` |
| `character_designer_user` | 角色设计 user prompt | `backend/ai_client.py` |
| `content_analyzer_system` | 内容分析 system prompt | `backend/ai_client.py` |
| `content_analyzer_user` | 内容分析 user prompt | `backend/ai_client.py` |
| `collision_narrative_system` | 碰撞叙事 system prompt | `novel_world/engine/collision/collision_engine.py` |
| `collision_narrative_user` | 碰撞叙事 user prompt | `novel_world/engine/collision/collision_engine.py` |
| `entry_narrative_system` | 入场叙事 system prompt | `novel_world/engine/collision/collision_engine.py` |
| `entry_narrative_user` | 入场叙事 user prompt | `novel_world/engine/collision/collision_engine.py` |
| `chapter_polish_system` | 章节润色 system prompt | `novel_world/engine/collision/collision_engine.py` |
| `faction_goals_system` | 势力目标 system prompt | `novel_world/engine/core/world.py` |
| `faction_goals_user` | 势力目标 user prompt | `novel_world/engine/core/world.py` |
| `dialogue_generation` | 对话生成 | `novel_world/engine/core/dialogue_system.py` |
| `story_intro_system` | 故事开头 system prompt | `novel_world/engine/core/engine.py` |
| `story_intro_user` | 故事开头 user prompt | `novel_world/engine/core/engine.py` |
| `history_summary` | 历史压缩摘要 | `novel_world/engine/core/events.py` |

### 被修改文件（prompt 替换）

| 文件 | 替换数量 | 说明 |
|------|----------|------|
| `backend/ai_client.py` | 5 处 | `tian_dao` / `character_agent` / `world_builder_*` / `character_designer_*` / `content_analyzer_*` |
| `backend/collision.py` | 1 处 | `collision_event` |
| `backend/narrative.py` | 2 处 | `chapter_generation` / `world_event` |
| `backend/engine.py` | 3 处 | `goal_alignment` + `goal_analyst_system` / `finale` / `character_action` |
| `novel_world/engine/collision/collision_engine.py` | 3 处 | `collision_narrative_*` / `entry_narrative_*` / `chapter_polish_system` |
| `novel_world/engine/core/world.py` | 1 处 | `faction_goals_*` |
| `novel_world/engine/core/dialogue_system.py` | 1 处 | `dialogue_generation` |
| `novel_world/engine/core/engine.py` | 1 处 | `story_intro_*` |
| `novel_world/engine/core/events.py` | 1 处 | `history_summary` |

### 使用方式

```python
from novel_world.engine.core.prompt_registry import PromptRegistry

# 获取渲染后的 prompt
prompt = PromptRegistry.get("chapter_generation", chapter_num=5, title="...", ...)

# 获取原始模板（适合作为 system_prompt 传入 ai.chat）
system = PromptRegistry.get_raw("collision_narrative_system")
```

---

## 验证结果

- `run_demo.py`：3 章 60 tick，0 报错，章节生成正常 ✅
- backend 侧 5 个文件的 prompt 替换后无语法错误 ✅
- novel_world 侧 5 个文件的 prompt 替换后无语法错误 ✅
- `PromptRegistry.list_all()` 返回 26 个已注册 prompt ✅
