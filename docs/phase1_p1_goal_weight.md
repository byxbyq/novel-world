# Phase1 P1 — Goal.weight 权重字段与加权调度

## 概述

为 GoalScheduler 的 Goal 数据模型新增 `weight` 字段，实现基于权重的目标调度排序，解决"所有目标等权处理"的问题。

## 改动文件

| 文件 | 改动类型 | 说明 |
|------|----------|------|
| `novel_world/engine/scheduler/goal_scheduler.py` | 修改 | Goal 新增 weight 字段；新增 add_mainline_goal / get_weighted_daily_goals_for_tick / get_all_active_goals_weighted；序列化支持 weight |

## 详细改动

### 1. Goal dataclass 新增 `weight` 字段

**位置：** `goal_scheduler.py` → `class Goal`

```python
weight: float = 1.0  # 调度权重，越高越优先（3.0=主线/2.0=长期/1.0=普通/0.5=临时）
```

权重语义：
- 3.0：主线目标（从 `main_objective` 派生）
- 2.0：长期目标（角色核心追求）
- 1.0：普通目标（默认）
- 0.5：短期/临时目标

### 2. 序列化兼容

- `Goal.to_dict()`：新增 `"weight": self.weight` 键
- `Goal.from_dict()`：无需改动（`cls(**data)` 自动使用 `weight=1.0` 默认值），旧序列化数据缺失 `weight` 键时自动回退到 1.0

### 3. 新增方法

#### `GoalScheduler.add_mainline_goal(content, character_name, level, tick)`

根据世界主线目标创建高权重 Goal（weight=3.0）。`metadata["source"] = "main_objective"` 标记来源。

#### `GoalScheduler.get_weighted_daily_goals_for_tick(character_name, tick)`

获取角色日常目标，按 `(weight DESC, created_tick DESC)` 排序。高权重目标优先返回。

#### `GoalScheduler.get_all_active_goals_weighted(character_name)`

获取角色所有层级（DAILY / STAGE / ULTIMATE）活跃目标，按 `(weight DESC, created_tick DESC)` 排序。

### 4. 已有基础（无需额外改动）

- `novel_world/engine/core/goal.py`（统一 Goal）：已有 `weight: float = 1.0`（Phase0 P0）
- `backend/character.py`：`select_primary_goal()` 已实现加权随机选择
- `backend/engine.py`：`align_goals_to_main_objective()` 已根据 main_objective 相似度计算 goal.weight
- `WorldConfig.main_objective_weight`：已在 Phase1 P1 EngineConfig 标准化中接入

## 验证结果

- `run_demo.py`：3 章 60 tick，0 报错 ✅
- 内联测试（7 项全部通过）：
  - weight 默认值 = 1.0 ✅
  - to_dict / from_dict round-trip ✅
  - 旧数据反序列化兼容 ✅
  - add_mainline_goal 创建 weight=3.0 ✅
  - get_all_active_goals_weighted 按 weight 降序排列 ✅
  - get_weighted_daily_goals_for_tick 正确过滤 DAILY 层级 ✅
  - add_goal 默认 weight=1.0 ✅
