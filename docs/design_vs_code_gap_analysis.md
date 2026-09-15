---
AIGC:
    Label: "1"
    ContentProducer: 001191440300708461136T1XGW3
    ProduceID: 62a5f052892935463ed1c42751e16e2e_4572b73c814811f180b3525400bff409
    ReservedCode1: OklaTIadanLLt8MlyNKIIaEH4UZEuQ1TjS5TUyFvsQyiSKQCUDxbq5Dg4W8eudDeZCXqgv4v4TVD+9T4zxKTIGGLRQXD/4UHJ5fSXVbmN6DwZIr8mOEcXL5464bEEhwOeegwI1N0bKi5BtRfG9CupQvW/9nf2lUSQXwPnAOnB+68mtldJxKQBFGRuvk=
    ContentPropagator: 001191440300708461136T1XGW3
    PropagateID: 62a5f052892935463ed1c42751e16e2e_4572b73c814811f180b3525400bff409
    ReservedCode2: OklaTIadanLLt8MlyNKIIaEH4UZEuQ1TjS5TUyFvsQyiSKQCUDxbq5Dg4W8eudDeZCXqgv4v4TVD+9T4zxKTIGGLRQXD/4UHJ5fSXVbmN6DwZIr8mOEcXL5464bEEhwOeegwI1N0bKi5BtRfG9CupQvW/9nf2lUSQXwPnAOnB+68mtldJxKQBFGRuvk=
---

# 设计文档 vs 代码实现 — 全面差距分析

> 分析日期：2026-07-17
> 设计文档：`docs/dm_mode_and_timeline_check_design.md`
> 代码范围：`H:\小说\小说世界\**` 全部 .py / .js / .html / .css

---

## 一、总体结论

| 维度 | 结论 |
|------|------|
| **功能一（时间线检查）** | 设计文档中的 TimelineChecker **在代码中尚未实现**。NovelEngine 已有 `ConsistencyChecker` 作为规则引擎框架（8 个维度），但它与设计文档定义的 6 个检查维度、3 层执行架构、4 种触发时机、前端 TimelinePanel 均**不对应**。 |
| **功能二（实时 DM 模式）** | **代码中完全不存在**。无 DMManager、无 DM 干预 API、无 WebSocket、无 DM 前端面板。 |
| **联动闭环** | **不存在**。 |
| **实施路线图** | 设计文档列出的 4 阶段中，基础设施阶段约有 40% 的准备工作已在代码中就绪（NovelEngine 框架、TruthLedger、WorldTimeline），但均未按设计文档的接口规范对接。 |

---

## 二、已覆盖：设计有、代码也有对应

| 设计要点 | 代码对应 | 对齐度 |
|----------|----------|--------|
| 时间轴数据结构 WorldTick | `scheduler/world_timeline.py` — WorldTick + WorldTimeline | 高度一致 |
| TruthLedger 存储 | `memory/truth_ledger.py` — 已集成到 NovelEngine | 一致 |
| 一致性校验框架（ConsistencyChecker） | `scheduler/consistency_checker.py` — 8 个检查维度，CheckLevel 分级，ConsistencyIssue 数据结构 | 部分一致（维度不同） |
| 世界规则守卫 | `scheduler/` 下的 `WorldRuleGuard` + `GuardViolation` | 一致 |
| 泳道管理（SwimlaneManager） | `scheduler/` 下的 `SwimlaneManager` | 一致 |
| 因果碰撞调度 | `scheduler/causal_collision_scheduler.py` — CollisionRecord | 一致 |
| 六轴图（SixAxisGraph） | `graph/six_axis_graph.py` | 一致 |
| 向量记忆（VectorMemory） | `storage/vector_memory.py` | 一致 |
| 目标调度器（GoalScheduler） | `scheduler/` 下的 `GoalScheduler` + `GoalLevel`/`GoalStatus` | 一致 |
| 时间线分支（TimelineBranch） | `scheduler/timeline_branch.py` | 一致 |
| NovelEngine 统一门面 | `novel_engine.py` — advance_tick 流程串联调度/管控层 | 一致（但缺少 DM/检查集成点） |

---

## 三、设计有但代码暂无对应入口（正常，非遗漏）

这些是设计文档中规划但尚未实现的——属于待执行的工作：

| 设计要点 | 缺失程度 | 说明 |
|----------|----------|------|
| **TimelineChecker 核心类** | 完全无 | 设计有完整的类定义、`check_all()`/`quick_scan()`/`deep_check()`/`correlation_analysis()`，代码无 |
| **6 个检查维度枚举** | 完全无 | `CheckDimension` 枚举（CHARACTER_STATE / TIMELINE_COHERENCE / GOAL_PROGRESS / FORESHADOWING / TIME_BACKFLOW / ITEM_CLUE），代码的 ConsistencyChecker 有类似但不同（多了 six_axis/world_rule，少了 item_clue） |
| **3 层检查执行架构** | 完全无 | 快速扫描(100ms) → 深度检查(500ms) → 关联分析(2000ms)，代码无任何执行层概念 |
| **4 种触发时机** | 完全无 | 用户主动 / 章节自动 / 保存前 / 加载后 |
| **检查报告 Report 数据结构** | 完全无 | `TimelineReport(timestamp, version, dimension_results, summary, recommendations)` |
| **NovelEngine 集成点** | 无 | `advance_tick()` 中无 `timeline_checker.check_after_tick()` 调用 |
| **TickResult.timeline_issues 字段** | 无 | 当前 TickResult 只有 `consistency_issues`，无 timeline_issues |
| **前端 TimelinePanel 组件** | 完全无 | 前端无任何检查报告展示 |
| **API `/api/timeline/check`** | 完全无 | Flask app.py 无此路由 |
| **DMManager 核心类** | 完全无 | 无状态机、无 pause/resume、无撤回队列 |
| **DM 5 类干预能力** | 完全无 | 修改叙事 / 调整目标 / 强制碰撞 / 添加角色 / 修改世界 — 均无接口 |
| **DM 恢复模式** | 完全无 | 从干预点继续 / 完全重新生成 / 分支 |
| **前端 DM 面板** | 完全无 | 无干预表单、无暂停控制、无回滚 |
| **WebSocket `/ws/dm`** | 完全无 | Flask 无 WebSocket 支持 |
| **API `/api/dm/*`** | 完全无 | 无 start/pause/intervene/resume 接口 |
| **联动闭环** | 完全无 | 检查→暂停→干预→再检查 均未实现 |
| **4 阶段实施路线图跟踪** | 无 | 无任何阶段标记或进度追踪 |

---

## 四、代码有但设计文档未提及（重要发现）

### 4.1 双代码体系架构

代码中存在**两套独立的代码体系**，设计文档将其视为单一引擎：

| 体系 | 位置 | 特点 |
|------|------|------|
| **Flask AI 叙事引擎** | `backend/` | Flask + OpenAI API；简化流程（天道→角色行动→碰撞→章节正文）；前端直连 |
| **完整规则引擎框架** | `novel_world/engine/` | 纯 Python 框架；不依赖 Flask；包含调度层/管控层/存储层/图形层；**当前未与前端对接** |

**设计文档影响**：DM 模式和 Timeline 检查应覆盖哪套体系？若两套都要覆盖，实现量翻倍。

### 4.2 庞大但未被设计文档考虑的质量管控层

代码中 `novel_world/engine/quality/` 和 `core/` 下有 **12+ 个质量管控模块**，设计文档未提及其中任何一个：

| 模块 | 文件 | 功能 |
|------|------|------|
| 叙事验证器 | `template_parser.py` → `NarrativeValidator` | 禁止词汇 / 铁律规则校验 |
| 强制修正系统 | `core/narrative_corrector.py` → `NarrativeCorrector` | 注册不可击败角色、人设防崩塌 |
| 叙事质量控制器 | `quality/narrative_quality_controller.py` | 片段去重 / 时间排序 / 视角控制 |
| 硬约束控制器 | `quality/hard_constraint_controller.py` | 高频词替换词库 / 空洞表述拦截 |
| 世界规则守卫 | `quality/world_rule_guard.py` | 关键词和规则条件校验 |
| 叙事增强器 | `quality/narrative_enhancer.py` | 场景变化 / 动作扩展 / 剧情分支 / 缓存 |
| 事件去重器 | `quality/narrative_corrector.py` → `EventDeduplicator` | 句式模式和冲突类型字典去重 |
| 动作扩展器 | `quality/action_expander.py` | 动作库模板管理 |
| 对话系统 | `core/dialogue_system.py` → `DialogueSystem` | 角色对话触发/生成/效果 |
| 命运系统 | `core/fate_system.py` → `FateSystem` | 命运线推进 |
| 交互系统 | `core/interaction_system.py` → `InteractionSystem` | 角色交互 |
| 道具系统 | `core/item_system.py` → `ItemManager` + `ItemValidator` | 道具管理/校验 |

**设计文档影响**：这些模块已经构建了一个事实上的"隐式检查层"。设计文档中 TimelineChecker 的 6 个检查维度应与此对齐，而非重新定义。

### 4.3 记忆系统（超出设计文档范围）

| 系统 | 位置 | 功能 |
|------|------|------|
| 五层记忆系统 | `utils/memory_manager.py` → `MemoryManager` | 短期/场景/长期/关键事件/关系记忆 |
| 事件记忆 | `core/event_memory.py` → `EventMemory` | 事件历史追踪 |
| 关系追踪 | `core/relationship_tracker.py` → `RelationshipTracker` | 角色关系一致性检查 |
| 叙事去重 | `core/narrative_dedup.py` → `NarrativeDeduplicator` | 重复叙事检测和替代生成 |

### 4.4 Self-Evolution 系统（未在设计文档出现）

`core/self_evolution.py`：白城主的自我进化系统，已被 `NarrativeEngine` 集成，在每轮叙事生成后触发。

### 4.5 剧情节点管理系统（未在设计文档出现）

`core/plot_nodes.py` → `PlotNodeManager`：管理剧情节点推进（起承转合），控制剧情节奏——这是一个比 TimelineChecker 更高层的叙事结构管控。

### 4.6 前端功能远超设计文档描述

现有前端（`frontend/index.html` + `app.js`）已实现：
- 世界观设定表单（含 AI 智能填充）
- 角色设定表单（含 AI 批量生成）
- 灵感输入 → AI 分析提取世界和角色
- 章节自动生成和阅读界面
- 角色状态面板
- 碰撞展示
- 存档/读档

但设计文档只提到 DM 面板和 TimelinePanel —— 这些与现有功能如何共存？是共存还是替换？

---

## 五、真正遗漏（代码逻辑/模块设计文档完全未考虑）

### 5.1 设计文档未提及但代码已实现的 ConsistencyChecker 维度

代码的 `ConsistencyChecker` 包含 6 个检查维度，与设计文档定义的 6 个**不对齐**：

| 代码维度 | 设计文档维度 | 对齐 |
|----------|-------------|------|
| character_state | CHARACTER_STATE | 对齐 |
| timeline | TIMELINE_COHERENCE | 部分对齐 |
| goal | GOAL_PROGRESS | 对齐 |
| foreshadowing | FORESHADOWING | 对齐 |
| time_backflow | TIME_BACKFLOW | 对齐 |
| **item** | — | 代码有，设计无 |
| **six_axis** | — | 代码有，设计无 |
| **world_rule** | — | 代码有，设计无 |
| — | ITEM_CLUE | 设计有，代码无 |

**影响**：实现 TimelineChecker 时不是从零开始，而是基于现有的 ConsistencyChecker 扩展。但现有的 item/six_axis/world_rule 三个维度如何处理需要决策。

### 5.2 DM 模式与现有章节生成流程的根本冲突

Backend 的 `GameEngine.run_chapter()` 是**一次性全自动**的：天道→角色行动→碰撞→正文，用户无法在中间干预。DM 模式要求**暂停-审查-干预-继续**，这需要把 `run_chapter()` 拆解为可中断的流水线。

`novel_world/engine/` 体系中的 `NovelEngine.advance_tick()` 虽然已经分步化（注册 tick → 调度目标 → 检测碰撞 → 校验一致性），但其设计也是自动推进，没有暂停机制。

### 5.3 Prompt 层面：最严重的缺口

**这是本次分析的核心发现。**

#### 5.3.1 现有 Prompt 分布全景

代码中所有 AI prompt 均为**内联硬编码字符串**，零散分布在 7 个文件中：

| 文件 | Prompt 用途 | System Prompt | User Prompt |
|------|------------|--------------|-------------|
| `backend/ai_client.py` | `tian_dao_prompt()` | 天道角色设定 + 世界 + 角色 + 时间线 + 行为准则 | 无（由调用方构建） |
| `backend/ai_client.py` | `character_agent_prompt()` | 角色设定 + 世界 + 近期事件 + 行为准则 | 无（由调用方构建） |
| `backend/ai_client.py` | `generate_world()` | 世界构建师角色 + JSON 输出格式 | 用户输入的世界设定 JSON |
| `backend/ai_client.py` | `generate_characters()` | 角色设计师角色 + JSON 输出格式 | 世界设定 JSON + 数量 |
| `backend/ai_client.py` | `analyze_content()` | 编辑分析师角色 + JSON 输出格式 | 用户原始文本 |
| `backend/narrative.py` | 章节正文生成 | 复用 `tian_dao_prompt()` | 标题 + 角色行动 + 世界事件 + 叙事要求 |
| `backend/narrative.py` | 世界事件决策 | 复用 `tian_dao_prompt()` | 世界局势 + 活跃角色 |
| `backend/collision.py` | 碰撞叙事生成 | 复用 `character_agent_prompt()` | 碰撞事件上下文 |
| `novel_world/engine/core/events.py` | `_build_prompts()` — tick 级叙事 | 主题叙事者 + 世界观 + 规则 + 能力约束 + 叙事规则（9条） | 世界状态 + 角色状态 + 势力格局 + 记忆上下文 + 场景细节 + 事件池 + 主线剧情 |
| `novel_world/engine/core/engine.py` | `_generate_story_intro()` | 主题叙事者 + 世界 + 主角 + 反派 + 要求（5条） | 主题 + 世界设定 + 主角 + 反派 |
| `novel_world/engine/collision/collision_engine.py` | `_build_collision_prompt()` | 网文作家 + 风格要求（6条） | 碰撞类型 + 原因 + 地点 + 世界规则 + 角色A/B信息 + 剧情上下文 |
| `novel_world/engine/collision/collision_engine.py` | `_generate_entry_narrative()` | 网文作家 + 独立性要求（4条） | 角色名 + 入场动机 + 私人目的 + 独立剧情 + 性格 + 命运线 |
| `novel_world/engine/collision/collision_engine.py` | `_aggregate_chapter_text()` | 小说编辑 + 润色要求（4条） | 拼接的章节片段（限制2000字） |

**总计：13 个独立 prompt 位置，零管理机制。**

#### 5.3.2 设计文档对 Prompt 的覆盖情况

设计文档 `dm_mode_and_timeline_check_design.md` **全文未出现 "prompt" 一词**。

这意味着以下关键问题在设计文档中完全没有涉及：

| 问题 | 严重性 |
|------|--------|
| **Prompt 审查机制**：谁来审查 prompt？怎么审查？频率？ | 严重 |
| **Prompt 版本管理**：每次修改 prompt 是否有版本记录？如何回滚？ | 严重 |
| **DM 干预时 Prompt 修改**：DM 说"语气不对"后，是否需要修改 system prompt 中的叙事风格？怎么改？ | 严重 |
| **Prompt 输出质量检查**：TimelineChecker 检查时是否需要评估 AI 输出是否遵循了 prompt 指令？ | 中等 |
| **Prompt 模板化**：当前所有 prompt 都是硬编码，是否需要抽象为可配置模板？ | 中等 |
| **Prompt 变更与 Chapter 的关联**：修改 prompt 后，已生成的章节是否受影响？ | 中等 |
| **不同角色/场景的动态 Prompt**：是否需要根据角色性格、场景切换不同的 prompt？ | 低 |

#### 5.3.3 具体缺口场景

**场景 1：DM 说"战斗描写太弱"**

- DM 干预触发 → 需要修改碰撞叙事 prompt 中的风格要求
- 当前代码：`_build_collision_prompt()` 中风格要求是固定的 `"注重氛围和细节"`、`"体现双方性格和能力的对抗"`
- 缺口：没有任何机制让 DM 的反馈转化为 prompt 修改

**场景 2：TimelineChecker 发现角色行为不一致**

- 检查发现：角色 A 性格"冷酷"，但叙事中频繁出现温暖对话
- 当前代码：NarrativeValidator 只检查禁止词汇，不检查 prompt 指令是否被 AI 遵循
- 缺口：没有 "prompt 合规度检查" 机制——即检查 AI 输出是否实际上遵循了 system prompt 的约束

**场景 3：创作者想实验不同的叙事风格**

- 用户："下一章试试第一人称"
- 当前代码：所有 prompt 中硬编码了 `"第三人称叙事"` 和 `"叙事以主角视角展开，不切换视角"`
- 缺口：没有 prompt 参数化能力，修改需要改代码

---

## 六、关键建议

### 6.1 优先级排序

| 优先级 | 事项 | 原因 |
|--------|------|------|
| P0 | **建立 Prompt 管理机制** | 这是 DM 干预和 Timeline 检查的前提——没有可控的 prompt，DM 无法真正"干预"生成质量 |
| P1 | **基于现有 ConsistencyChecker 实现 TimelineChecker** | 代码已有 60% 基础，按设计文档补齐 3 层架构和 6 个检查维度即可 |
| P1 | **确定两套代码体系的对接策略** | `backend/`（Flask 简化版）和 `novel_world/engine/`（完整框架）必须选一个作为 DM 模式载体 |
| P2 | **实现 DM 状态机和暂停机制** | 依赖 P0 和 P1 完成 |
| P3 | **DM 前端面板和 WebSocket** | 依赖后端 DM 接口就绪 |

### 6.2 Prompt 管理机制设计建议

最低可行方案（MVP）：

```
1. Prompt Registry（prompt 注册表）
   - 集中存储所有 prompt 模板
   - 每个 prompt 有唯一 ID、版本号、用途描述
   - 存储格式：JSON 或 YAML 文件

2. Prompt 变量系统
   - 模板中支持 {variable} 占位符
   - 运行时根据上下文填充
   - DM 可覆盖变量值（如 {tone} = "紧张" → "轻松"）

3. DM Prompt 修改接口
   - DM 干预时自动生成 prompt 修改建议
   - 支持预览修改前后的输出对比
   - 修改后自动版本号递增

4. Prompt 合规度检查
   - TimelineChecker 中新加一个维度：检查 AI 输出是否遵循了 prompt 指令
   - 使用规则匹配（关键词/格式检查）而非再次调用 AI
```

### 6.3 两套体系对接建议

| 方案 | 描述 | 优劣 |
|------|------|------|
| A | 以 `novel_world/engine/` 为基础，重写 Flask 层 | 完整、可持续；工作量大 |
| B | 以 `backend/` 为基础，逐步迁移 `novel_world/engine/` 的模块 | 渐进式；但 backend 架构过于简化 |
| **C（推荐）** | 保持双轨：`backend/` 继续服务现有前端，DM/Timeline 在 `novel_world/engine/` 独立开发，通过 API 适配层桥接 | 最小风险；两套可独立迭代 |

### 6.4 设计文档应补充的内容

1. **Prompt 管理章节**：描述 prompt 的存储、版本、审查、DM 修改机制
2. **质量管控层对接**：明确 TimelineChecker 与现有 12+ 个质量模块的关系
3. **双体系策略**：说明 `backend/` 和 `novel_world/engine/` 的分工
4. **前端共存方案**：现有设置/阅读 UI 与 DM 面板如何共存

---

## 七、附录：Prompt 完整清单

| # | 文件 | 函数/位置 | 角色 | 用途 |
|---|------|----------|------|------|
| 1 | `backend/ai_client.py:31` | `tian_dao_prompt()` | 天道 | 章节正文/世界事件生成 |
| 2 | `backend/ai_client.py:56` | `character_agent_prompt()` | 角色 Agent | 角色行动决策 |
| 3 | `backend/ai_client.py:82` | `generate_world()` | 世界构建师 | AI 补全世界设定 |
| 4 | `backend/ai_client.py:138` | `generate_characters()` | 角色设计师 | AI 批量生成角色 |
| 5 | `backend/ai_client.py:193` | `analyze_content()` | 编辑分析师 | 分析灵感文本提取设定 |
| 6 | `backend/narrative.py:38` | `generate_chapter()` | 天道(复用#1) | 章节正文 user prompt |
| 7 | `backend/narrative.py:57` | `generate_world_event()` | 天道(复用#1) | 世界事件决策 |
| 8 | `backend/collision.py:30` | `process_collision()` | 角色Agent(复用#2) | 碰撞叙事 |
| 9 | `novel_world/engine/core/events.py:265` | `_build_prompts()` | 主题叙事者 | tick 级叙事生成 |
| 10 | `novel_world/engine/core/engine.py:172` | `_generate_story_intro()` | 主题叙事者 | 故事开头 |
| 11 | `novel_world/engine/collision/collision_engine.py:902` | `_build_collision_prompt()` | 网文作家 | 碰撞叙事 |
| 12 | `novel_world/engine/collision/collision_engine.py:1106` | `_generate_entry_narrative()` | 网文作家 | 角色入场叙事 |
| 13 | `novel_world/engine/collision/collision_engine.py:1227` | `_aggregate_chapter_text()` | 小说编辑 | 章节润色衔接 |
*（内容由AI生成，仅供参考）*
