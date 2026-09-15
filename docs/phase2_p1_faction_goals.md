# Phase2 P1: Faction 势力目标系统

> 实施日期：2026-07-17 | 状态：已完成

## 一、改动概要

| 文件 | 操作 | 说明 |
|------|------|------|
| `novel_world/world/world.py` | 修改 | Faction 类新增 enemies/allies/controlled_resources 字段 + 关系管理方法；World 类新增 get_faction_by_name/set_faction_enemies/set_faction_allies/detect_faction_overlap_resources |
| `novel_world/engine/core/engine.py` | 修改 | tick() 插入 _process_faction_goals()；新增 _process_faction_goals/_align_character_to_faction/get_faction_summary/update_faction；_create_default_factions 自动设置敌对关系 |
| `novel_world/engine/collision/collision_engine.py` | 修改 | _check_faction_conflict 实现四级冲突升级（基础 50 → 敌对 70 → 领地/资源 75 → 全面对抗 90） |
| `novel_world/adapter/adapter.py` | 修改 | 新增 get_faction_summary/update_faction 委托方法 |
| `app.py` | 修改 | 新增 GET /api/dm/factions、POST /api/dm/faction/<id>、/add_enemy、/add_ally 四个端点 |
| `frontend/index.html` | 修改 | DM 面板新增「势力管理」Tab |
| `frontend/app.js` | 修改 | 新增 refreshFactions() + Tab 切换自动刷新 + DM 暂停轮询联动 |

## 二、Faction 数据模型

| 字段 | 类型 | 说明 |
|------|------|------|
| name | str | 势力名称 |
| enemies | List[str] | 敌对势力名称列表 |
| allies | List[str] | 同盟势力名称列表 |
| controlled_resources | List[str] | 实际控制的资源列表 |
| goals | List[FactionGoal] | 势力集体目标（含 description/progress/weight） |
| territory | str | 领地/地盘 |
| resources | List[str] | 理论资源声明 |

新增方法：`is_enemy_of(name)`、`is_ally_of(name)`、`add_enemy(name)`、`add_ally(name)`、`remove_relation(name)`、`member_count()`。

## 三、World 新增能力

- `get_faction_by_name(name)` — 按名称查找势力
- `set_faction_enemies(fid1, fid2)` — 双向设置敌对关系
- `set_faction_allies(fid1, fid2)` — 双向设置同盟关系
- `detect_faction_overlap_resources(fid1, fid2)` — 检测三方冲突（领地重叠、资源争夺、目标提及对方）

## 四、Tick 循环势力步骤

```
tick() 执行顺序：
1. 角色随机移动
2. 叙事生成
3. 对话处理
4. 状态更新
5. 势力领地更新（每 10 tick）
6. ★ 势力目标驱动 _process_faction_goals()  [NEW]
7. 记录故事日志
```

### _process_faction_goals 逻辑
- 遍历所有势力的 goals，将敌对信息注入成员角色
- `_align_character_to_faction()`：将势力目标的敌对信息写入角色的关系/行为上下文
- 每 5 tick 推进目标进度（progress += 0.02）

## 五、碰撞引擎冲突升级

```
不同 faction_id          → weight=50  "势力-直接冲突"
+ 明确敌对 (enemies)     → weight=70  "势力-敌对冲突"
+ 领地重叠              → weight=75  "势力-领地冲突"
+ 资源争夺              → weight=75  "势力-资源冲突"
+ 领地+资源同时重叠     → weight=90  "势力-全面对抗"
```

## 六、API 端点

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/dm/factions` | GET | 获取所有势力摘要 |
| `/api/dm/faction/<id>` | POST | 更新势力数据（名称/描述/敌对/同盟等） |
| `/api/dm/faction/<id>/add_enemy` | POST | 添加双向敌对关系 |
| `/api/dm/faction/<id>/add_ally` | POST | 添加双向同盟关系 |

## 七、前端「势力管理」Tab

- 势力卡片：名称（色标）、成员数、领地、敌对/同盟标签、目标及进度
- DM 暂停时自动轮询刷新（1s 间隔）
- Tab 切换时触发首次加载
