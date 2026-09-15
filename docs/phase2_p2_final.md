---
AIGC:
    Label: "1"
    ContentProducer: 001191440300708461136T1XGW3
    ProduceID: 62a5f052892935463ed1c42751e16e2e_5d678fd581a011f1bbe75254006c9bbf
    ReservedCode1: YBRjgDlSmXUAcWCXXYq3uSBRCxeKN5RvlJI+wSwIByqfUmsXweZ7fYvQ/PXGGIxXEukxEjCISN6zD1BBNL9it9dStjQf7MwfF37lk9YpDrF+ZULWGrZbDBz0Tr5sV6hnicBaXghz19L9pigkJkbktguGpEJpYXlKBvk4RWGUCcqlLjbY1brLONsdauo=
    ContentPropagator: 001191440300708461136T1XGW3
    PropagateID: 62a5f052892935463ed1c42751e16e2e_5d678fd581a011f1bbe75254006c9bbf
    ReservedCode2: YBRjgDlSmXUAcWCXXYq3uSBRCxeKN5RvlJI+wSwIByqfUmsXweZ7fYvQ/PXGGIxXEukxEjCISN6zD1BBNL9it9dStjQf7MwfF37lk9YpDrF+ZULWGrZbDBz0Tr5sV6hnicBaXghz19L9pigkJkbktguGpEJpYXlKBvk4RWGUCcqlLjbY1brLONsdauo=
---

# Phase2 P2 Final: 地域-资源-角色目标联动 + 前端批量编辑

## 改动概述

实现两个核心系统：地域-资源-角色目标联动（角色目标含资源关键词 → 自动向资源所在地移动 → 同资源争夺碰撞）和前端批量编辑（批量角色/势力修改 + JSON 导入）。

---

## 任务A：地域-资源-角色目标联动

### 改动文件（3 个文件）

#### 1. `novel_world/engine/core/world.py`（步骤A1）

| 改动项 | 说明 |
|--------|------|
| `_RESOURCE_KEYWORD_MAP` | 新增类属性，4 类 36 个资源关键词映射：（灵石/神器/灵脉/灵药→灵物类）、（金矿/精铁/玄铁→矿产类）、（灵泉/水源/绿洲→水源类）、（功法/剑谱/秘术/传承→传承类） |
| `get_resource_location(resource_name)` | 新增方法：三级匹配（tile.resources 精确匹配→资源类型匹配→部分名称模糊匹配），返回资源所在地 Tile |
| `get_tile_by_name(name)` | 新增辅助方法：按 tile 名称查找 |

#### 2. `novel_world/engine/core/engine.py`（步骤A2/A3）

| 改动项 | 说明 |
|--------|------|
| `_move_characters()` | 新增方法：替代原 `_random_move_characters`，20% 概率触发移动。优先调用 `_resolve_goal_to_location`（目标导向），失败则随机移动。水 tile 阻挡有对角线尝试回退 |
| `_extract_resource_keywords(goal_text)` | 新增：从目标文本中匹配 World._RESOURCE_KEYWORD_MAP 关键词，按长度降序防短词误匹配，返回 `[(关键词, 资源类型), ...]` |
| `_resolve_goal_to_location(char)` | 新增：取第一个匹配资源 → 查资源所在地 → 向该方向移动 1 步。已在目标位置返回 False，水阻挡尝试轴优先备选方向 |
| `_random_move_characters()` | 保留为向后兼容通道，内部委托给 `_move_characters()` |
| `tick()` 调用点 | `_random_move_characters()` → `_move_characters()` |

#### 3. `novel_world/engine/collision/collision_engine.py`（步骤A4）

| 改动项 | 说明 |
|--------|------|
| `_check_resource_contention(char_a, char_b)` | 新增碰撞检测：双方在同一或邻接格、目标含相同资源关键词 → 权重 60 的"资源争夺"碰撞。同一势力跳过 |
| `detect_collisions()` 调用链 | 势力冲突检测后新增资源争夺检测步骤 |

---

## 任务B：前端批量编辑

### 改动文件（3 个文件）

#### 1. `app.py`（+3 个 API 端点）

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/characters/batch` | POST | 批量修改角色：`character_ids=["all"/id列表]` + `updates={字段:值}`。personality 追加模式，faction_id 自动迁移 member_ids，pos 解析 (x,y) |
| `/api/factions/batch` | POST | 批量修改势力：`faction_ids` + `updates`。支持 set_enemies/set_allies/add_resources |
| `/api/characters/import` | POST | JSON 数组导入：`{"characters":[{"name":"...","personality":[...],"goal":"..."}]}`，自动创建 Character 并 add_character |

#### 2. `frontend/index.html`（批量编辑 Tab）

| 组件 | 说明 |
|------|------|
| `interv-batch` Tab 按钮 | DM 干预面板新增「批量编辑」Tab |
| 批量角色编辑区 | ID 输入框（支持 `all` / 逗号分隔） + 字段下拉（性格/势力/位置/目标） + 值输入 + 应用按钮 + 状态提示 |
| 批量势力编辑区 | ID 输入 + 字段下拉（敌对/同盟/资源） + 值输入 + 应用按钮 |
| 批量导入区 | JSON textarea（含 placeholder 示例） + 导入按钮 + 状态提示 |

#### 3. `frontend/app.js`（3 个 JS 函数）

| 函数 | 说明 |
|------|------|
| `batchEditCharacters()` | 解析 ID 列表（`"all"` 或逗号分隔）→ 解析值（性格逗号分拆 / pos 整数对验证）→ POST `/api/characters/batch` |
| `batchEditFactions()` | 解析势力 ID → 解析值（逗号分拆列表）→ POST `/api/factions/batch` |
| `batchImportCharacters()` | 解析 textarea JSON → 验证数组格式 → POST `/api/characters/import` |

---

## 验证结果

- CollisionEngine 导入 OK，`_check_resource_contention` 方法存在
- World 导入 OK，`_RESOURCE_KEYWORD_MAP`(36 关键词)、`get_resource_location`、`get_tile_by_name` 存在
- app.py 语法检查通过
- engine.py 源码中 `_move_characters`、`_extract_resource_keywords`、`_resolve_goal_to_location` 代码存在
*（内容由AI生成，仅供参考）*
