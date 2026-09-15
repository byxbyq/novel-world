# Phase1 P0: 双引擎数据模型统一

> 任务：修复 backend 和 novel_world/engine 双引擎数据模型不一致问题，统一为单一数据源。
> 日期：2026-07-17

---

## 一、两套数据模型对比

### 1.1 Goal 类对比

| 维度 | backend.character.Goal | novel_world.engine.Character.goal |
|------|----------------------|----------------------------------|
| 类型 | `dataclass`，5 个字段 | **纯字符串 `str`** |
| 字段 | description, priority(1-10), weight(float), progress, reason_changed | 无结构 |
| 权重排序 | `select_primary_goal()` 加权随机选择 | 不支持 |
| 进度追踪 | 未开始/进行中/受阻/已完成/已放弃 | 不支持 |
| **判定** | 🔴 **严重不一致** — 语义完全不可互换 | |

**结论**：这是最核心的不一致。Adapter 转换时 `goal=agent.long_term_goal.description` 丢弃了所有元数据（weight/priority/progress）。

### 1.2 Character 类对比

| 维度 | backend.CharacterAgent | novel_world.engine.Character |
|------|----------------------|------------------------------|
| 类型 | 普通类（`__init__`），含方法 | `@dataclass`，纯数据 |
| 目标 | `Goal`（丰富结构） | `goal: str`（纯字符串） |
| 性格 | `config.personality: str` | `personality: str` ✅ 兼容 |
| 角色类型 | ❌ **缺失**（config 无 `char_type`） | `CharType` 枚举（5种） |
| 位置 | `current_location: str`（地点名） | `pos: tuple`（网格坐标） |
| 关系 | `{角色名: {态度, 描述}}` | `relations: dict`（数值-100~100）+ `relationships: dict` |
| 记忆 | `memory: list[dict]`（type+content） | `memory: list` + `key_memories: list` |
| 状态 | `current_mood` + `current_action` | `CharState` 枚举（10种） |
| 属性 | 无 | `attrs: dict`（体力/智力/魅力...） |
| RPG字段 | 无 | `alive, action_cooldown, faction_id, id, skills` |
| **判定** | 🟡 **语义不同** — 一个面向叙事，一个面向模拟。不可直接替换 | |

**关键差异**：`char_type` 在 backend CharacterConfig 中**完全缺失**，导致 Adapter 曾用 `hasattr` 防御性兜底，所有角色硬编码为 `PROTAGONIST`（长期记忆记载）。

### 1.3 World 类对比

| 维度 | backend.World | novel_world.engine.World |
|------|-------------|--------------------------|
| 核心概念 | 叙事世界（章节、事件、角色位置） | 模拟世界（地块、势力、Tick数） |
| 配置 | `WorldConfig` 数据类（丰富） | `theme + map_size`（极简） |
| 共享字段 | **无** | **无** |
| **判定** | 🟢 **不合并** — 职责完全不同 | |

**结论**：两套 World 服务于不同的引擎层，强行合并会破坏各自的语义。不在本次统一范围内。

### 1.4 Faction 类对比

| 维度 | backend | novel_world.engine |
|------|---------|---------------------|
| 定义 | ❌ **不存在** | `Faction` + `FactionGoal` dataclasses |
| **判定** | 🟡 仅 novel_world 有，backend 无需求 | |

---

## 二、采用的统一方案

### 方案选择：最小侵入式统一

考虑到两套 Character 和 World 的**语义根本不同**（叙事层 vs 模拟层），全量统一会导致大量重构。选择**只统一可对齐的核心数据单元**：

| 组件 | 策略 |
|------|------|
| **Goal** | ✅ 在 `novel_world/engine/core/goal.py` 定义为唯一真实定义，backend 改为 re-export |
| **char_type** | ✅ 在 `backend/config.py` CharacterConfig 中新增字段 |
| **Character/World** | 🟡 不合并（语义不同），文档记录差异 |

---

## 三、实施清单

### 3.1 新建：`novel_world/engine/core/goal.py`

共享的 Goal dataclass，包含 5 个字段：
- `description: str`
- `priority: int = 5`
- `weight: float = 1.0`
- `progress: str = "未开始"`
- `reason_changed: str = ""`

### 3.2 修改：`backend/character.py`

- **删除** 原有 `Goal` dataclass 定义
- **改为** `from novel_world.engine.core.goal import Goal`（re-export）
- 下游所有 `from backend.character import Goal` 的导入无需修改

### 3.3 修改：`backend/config.py`

- `CharacterConfig` 新增字段 `char_type: str = ""`
- 默认空字符串，由 Adapter 转换时按 CharType 枚举名解析

### 3.4 修改：`novel_world/adapter/adapter.py`

- `_convert_character()` 中移除 `hasattr` 防御代码
- 改为：优先 `CharType[char_type_str]` → 按值匹配 → 缺省 `CharType.NPC`
- 修复前：所有角色硬编码为 `PROTAGONIST`
- 修复后：正确解析配置中的角色类型，缺省回退到 `NPC`

---

## 四、验证

- ✅ `run_demo.py` 运行正常，3 章 60 tick 全部完成
- ✅ `from backend.character import Goal` 导入兼容（storage.py、adapter.py）
- ✅ Goal 构造函数签名与原有完全一致
- ✅ 不传 `char_type` 时缺省为 NPC（而非之前错误的 PROTAGONIST）

---

## 五、未覆盖项（标记后续）

| 项 | 说明 | 状态 |
|----|------|------|
| novel_world Character.goal 升级为 Goal | 目前仍为纯字符串，需评估对 CollisionEngine 等的影响 | P2 TODO |
| World 统一 | 两套 World 语义不可互换，不需要统一 | 无需处理 |
| Faction → backend | backend 无 Faction 需求，不需要移植 | 无需处理 |
| Character 语义统一 | 叙事 Agent vs 模拟 Dataclass，需要更深层架构调整 | P2 TODO |
