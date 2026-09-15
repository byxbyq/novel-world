---
AIGC:
    Label: "1"
    ContentProducer: 001191440300708461136T1XGW3
    ProduceID: 62a5f052892935463ed1c42751e16e2e_0448475e818d11f180b3525400bff409
    ReservedCode1: JSMnwmCcOO7lbJkB7L6mcqUjaxf6b9Z4LD+kh33lNtGjSUDtQS5qdZEkjO6GGkiQ5g73a3GB1GJdP2yV65PD2FveIRGHkp20MJa7GUjZ0Vwg4xNm62YKWr3yu5kZeKLXklGUgFIBQWPSYDq7cFPW8KO0XGUBCqG2Ac92pWrbWwcaPECr5byWfXs9jq8=
    ContentPropagator: 001191440300708461136T1XGW3
    PropagateID: 62a5f052892935463ed1c42751e16e2e_0448475e818d11f180b3525400bff409
    ReservedCode2: JSMnwmCcOO7lbJkB7L6mcqUjaxf6b9Z4LD+kh33lNtGjSUDtQS5qdZEkjO6GGkiQ5g73a3GB1GJdP2yV65PD2FveIRGHkp20MJa7GUjZ0Vwg4xNm62YKWr3yu5kZeKLXklGUgFIBQWPSYDq7cFPW8KO0XGUBCqG2Ac92pWrbWwcaPECr5byWfXs9jq8=
---

# Phase 1 P0: Adapter 适配层 — 改动清单

> 日期：2026-07-17
> 目标：打通 backend 和 novel_world/engine 双引擎，前端通过统一接口调用重型引擎全部能力。

---

## 新增文件

| 文件 | 说明 |
|------|------|
| `novel_world/adapter/__init__.py` | 适配层包入口，导出 `EngineAdapter` |
| `novel_world/adapter/adapter.py` | Adapter 主实现，~420 行 |

---

## 修改文件

| 文件 | 变更 |
|------|------|
| `app.py` | 第 18 行：`from backend.engine import GameEngine` → `from novel_world.adapter import EngineAdapter` |
| `app.py` | 第 28 行：`engine = GameEngine()` → `engine = EngineAdapter()` |

---

## EngineAdapter 接口映射

| backend GameEngine API | Adapter 实现策略 | 状态 |
|---|---|---|
| `__init__(config)` | 创建 backend 组件 + novel_world World / CollisionEngine | ✅ |
| `init_game(world, characters)` | 双路径：创建 backend 状态 + 转换为 novel_world 引擎组件 | ✅ |
| `run_chapter(title)` → dict | 混合执行：backend NarrativeGenerator 生成世界事件/角色行动/章节叙事 + novel_world CollisionEngine 运行全体 ticks 并收尾 | ✅ |
| `advance_tick()` → dict\|None | Tick 驱动：普通 tick 推进 novel_world CollisionEngine；章节边界自动触发 run_chapter | ✅ |
| `get_state()` → dict | 返回 backend + novel_world 合并状态（含 nw_tick / nw_collisions 统计） | ✅ |
| `save(slot)` | 复用 backend Storage | ✅ |
| `load(slot)` | 复用 backend Storage，含重新 init_game | ✅ |
| `world` 属性 | 暴露 backend World（供 app.py 访问 `engine.world.current_chapter` 等） | ✅ |
| `align_goals_to_main_objective()` | 从 backend GameEngine 原样迁移 | ✅ |

---

## 数据转换映射

| backend 类型 | novel_world 类型 | 关键转换点 |
|---|---|---|
| `WorldConfig` (dataclass) | `novel_world.World` (dataclass) | genre → theme；description 丢失（novel_world World 无此字段） |
| `CharacterAgent` (dataclass) | `novel_world.Character` (dataclass) | config.personality → personality；config.background → fate_arc；long_term_goal.description → goal；char_type 硬编码为 PROTAGONIST |
| `WorldConfig.main_objective` | `novel_world.World.factions` | 通过 `faction_goals_text()` 提取为文本传入 `generate_world_event` |
| 章节结果 dict | `ChapterTimeline.narrative` + backend 叙事 | 合并双路径碰撞结果，backend 优先，novel_world 补充 |

---

## 已知限制与 TODO

| 项目 | 说明 | 优先级 |
|------|------|--------|
| novel_world NovelEngine 调度层 | `novel_world.engine.novel_engine.NovelEngine`（时间轴/泳道/目标调度/一致性校验/规则守卫）未接入，Adapter 仅使用 CollisionEngine 做碰撞检测 | P1 |
| 角色类型映射 | `CharacterAgent.config.char_type` 未传递给 novel_world Character.char_type（全部设为 PROTAGONIST） | P1 |
| 技能系统桥梁 | backend 无 Skill 概念，Adapter 创建空 SkillRegistry，novel_world 碰撞检测依赖位置而非技能标签 | P1 |
| AI 叙事降级 | novel_world CollisionEngine 的模板降级模式未接入 backend，章节叙事仍依赖 backend NarrativeGenerator（需真实 API Key） | P2 |
| 地图生成 | backend 无地图概念，CollisionEngine 角色坐标使用随机移动模拟 | P2 |
| 分阶段叙事 | novel_world 四段式章节结构（prelude/protagonist_action/entry_scenes/epilogue）未完全映射到 backend 的章节 log | P3 |

---

## 验证结果

- [x] Adapter 导入无报错
- [x] app.py 使用 EngineAdapter 加载成功，14 个 API 端点注册正常
- [x] Adapter 构造 + init_game 正常执行（创建 novel_world World 和 CollisionEngine）
- [x] run_chapter 结构路径正确（AI 超时是环境 API Key 问题，非 Adapter 代码问题）
- [x] 引擎统计信息正确合并（nw_tick / nw_collisions 出现在 get_state 返回中）
- [ ] 完整一章生成 —— 需要有效 API Key 环境
- [ ] run_demo.py 验证 —— 需要有效 API Key 环境
*（内容由AI生成，仅供参考）*
