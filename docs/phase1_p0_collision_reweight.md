# Phase 1 P0: CollisionEngine 碰撞权重改造 — 改动清单

## 概述

在 `novel_world/engine/collision/collision_engine.py` 中新增两维碰撞判定——**目标-角色关联检测**和**势力冲突检测**——并引入权重排序体系，使目标对立碰撞的优先级高于纯关键词/位置碰撞。

**影响文件**：仅 `collision_engine.py`（+ 本文档），不涉及其他模块。

---

## 原来的碰撞判定机制

### 碰撞检测顺序（`_detect_collisions`，原 ~L442-495）

```
for each character pair:
    1. 感知对冲（perception vs stealth）
    2. 目标对冲（关键词表 _OPPOSITE_KEYWORDS 匹配）
    3. 能力对冲（技能克制弱点）
    4. 接近碰撞（曼哈顿距离 ≤ 3）
```

### 排序方式（`tick`，原 ~L366-368）

```python
priority_map = {"目标对冲": 3, "能力对冲": 2, "感知对冲": 1, "接近碰撞": 0}
events.sort(key=lambda e: priority_map.get(e.collision_type, 0), reverse=True)
```

固定优先级排序，不区分目标对立的严重程度。

### 缺失的问题

| 缺失项 | 具体后果 |
|--------|---------|
| 目标-角色关联 | "苏晚的目标是跟随李青云"不会自动触发碰撞，除非违反关键词表 |
| 势力冲突 | 两个对立势力的角色即使面对面，也不视为天然碰撞 |
| 权重排序 | "要杀他"和"碰巧路过"被视为同级别的"目标对冲" |

---

## 改造后的碰撞判定机制

### 新增检测维度

```
for each character pair:
    ── NEW ── 目标-角色关联（_check_goal_opposition）→ weight=100/80
    ── NEW ── 势力冲突（_check_faction_conflict）    → weight=50
    1. 感知对冲（原有，weight=0）
    2. 目标-关键词对冲（原有，weight=50）
    3. 能力对冲（原有，weight=0）
    4. 接近碰撞（原有，weight=0）
```

### 排序方式（`tick`，修改后）

```python
events.sort(key=lambda e: getattr(e, 'collision_weight', 0), reverse=True)
```

基于 `collision_weight` 字段降序排列。

### 权重体系

| 碰撞类型 | 子类型 | 权重 | 说明 |
|---------|--------|------|------|
| 目标对冲 | 目标-角色关联（双向） | **100** | 双方目标互为指向 |
| 目标对冲 | 目标-角色关联（单向） | **80** | 一方目标提及另一方 |
| 目标对冲 | 目标-关键词 | **50** | `_OPPOSITE_KEYWORDS` 匹配 |
| 势力冲突 | 势力-直接冲突 | **50** | 分属不同势力 |
| 能力对冲 | — | 0 | 默认为 0 |
| 感知对冲 | — | 0 | 默认为 0 |
| 接近碰撞 | — | 0 | 默认为 0 |

---

## 代码变更详情

### 1. `CollisionEvent` 数据类新增字段

**文件位置**：`collision_engine.py` L~76-79

```python
# 新增字段
collision_subtype: str = ""    # 子类型
collision_weight: int = 0      # 碰撞权重
```

### 2. `to_dict()` / `from_dict()` 序列化同步

**文件位置**：`collision_engine.py` L~108-110（to_dict）、L~136-138（from_dict）

新增 `collision_subtype` 和 `collision_weight` 的序列化/反序列化。

### 3. `_make_collision_event()` 工厂方法扩展

**文件位置**：`collision_engine.py` L~788-792

新增参数 `collision_subtype: str = ""`、`collision_weight: int = 0`，透传给 `CollisionEvent` 构造函数。

### 4. 新增 `_check_goal_opposition()` 方法（~70 行）

**文件位置**：`collision_engine.py` L~593-663（插入在 `_check_goal_collision` 之后）

检测逻辑：
- 读取两角色的 `goal` / `current_goal` 字符串
- 如果角色 A 的目标包含角色 B 的名字，且角色 B 的目标包含角色 A 的名字 → **双向目标关联**，weight=100
- 如果仅角色 A 的目标包含角色 B 的名字 → **单向目标关联**，weight=80

### 5. 新增 `_check_faction_conflict()` 方法（~40 行）

**文件位置**：`collision_engine.py` L~665-704

检测逻辑：
- 比较两角色的 `faction_id` 字段
- 不同且非空 → 势力冲突，weight=50
- 从 `self.world.factions` 查找势力名称用于碰撞原因描述

### 6. `_check_goal_collision()` 补全子类型和权重

**文件位置**：`collision_engine.py` L~534-590

原有关键词匹配的碰撞事件增加 `collision_subtype="目标-关键词"` 和 `collision_weight=50`。

### 7. `_detect_collisions()` 插入新检测步骤

**文件位置**：`collision_engine.py` L~465-480

在原有检测步骤之前插入：
```python
# ── 新增：目标-角色关联检测（最高权重） ──
goal_opp_event = self._check_goal_opposition(char_a, char_b, skill_a, skill_b)
if goal_opp_event:
    events.append(goal_opp_event)
    continue

# ── 新增：势力冲突检测（次高权重） ──
faction_event = self._check_faction_conflict(char_a, char_b, skill_a, skill_b)
if faction_event:
    events.append(faction_event)
    continue
```

### 8. `tick()` 排序改为权重排序

**文件位置**：`collision_engine.py` L~366-373

```python
# 旧：固定类型优先级 Map 排序
priority_map = {"目标对冲": 3, "能力对冲": 2, "感知对冲": 1, "接近碰撞": 0}
events.sort(key=lambda e: priority_map.get(e.collision_type, 0), reverse=True)

# 新：collision_weight 字段排序
events.sort(key=lambda e: getattr(e, 'collision_weight', 0), reverse=True)
```

---

## 验证结果

| 验证 | 结果 |
|---|---|
| `run_demo.py` | 通过，3 章 × 20 tick 正常运行无报错 |
| Tick 01 — 目标-角色关联 | 苏晚 → 李青云（单向），weight=80，排序第一 ✓ |
| Tick 02 — 势力冲突 | 天机阁 vs 九幽宫，weight=50，排序第二 ✓ |
| Tick 03-06 — 原有碰撞 | 能力对冲 × 3 + 感知对冲 × 1，正常运行 ✓ |
| 碰撞分布 | 目标对冲 1 次 + 势力冲突 1 次 + 能力对冲 3 次 + 感知对冲 1 次 = 6 次 |

### demo 输出中的新碰撞事件

```
[Tick 01] 碰撞！李青云 vs 苏晚 [目标对冲]
         原因：目标关联：苏晚的目标「跟随李青云，因为直觉告诉她此行至关重要」直接涉及李青云

[Tick 02] 碰撞！李青云 vs 魔尊玄冥 [势力冲突]
         原因：势力对峙：李青云所属「天机阁」与魔尊玄冥所属「九幽宫」对立
```

---

## 不涉及的部分

- `_check_perception_collision()` — 不变
- `_check_ability_collision()` — 不变
- `_check_proximity_collision()` — 不变
- 叙事生成 (`_generate_collision_narrative`) — 不变
- 章节管理 (`start_new_chapter` / `finalize_chapter`) — 不变
- 去重逻辑 (`_collided_pairs_chapter`) — 不变

## TODO（标注但未阻塞）

| 项 | 说明 |
|---|---|
| 势力关系矩阵 | 当前仅比较 `faction_id` 是否不同。理想的实现应有 `FactionRelationGraph` 记录每对势力的外交状态（敌对/同盟/中立），而非将"不同势力"一律视为冲突 |
| 目标语义理解 | 当前仅做字符串包含检查（`name in goal`）。如果角色 A 的目标用代称/绰号指代角色 B（如"那个魔头"而非"魔尊玄冥"），会漏检。未来可接入 LLM 做语义级别判断 |
