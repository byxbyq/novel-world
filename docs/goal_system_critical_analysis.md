---
AIGC:
    Label: "1"
    ContentProducer: 001191440300708461136T1XGW3
    ProduceID: 62a5f052892935463ed1c42751e16e2e_2ae2129d818811f1bbe75254006c9bbf
    ReservedCode1: loP/oNb+yhClJ2yn8l9MQOM+DNRsVD44TreNFQAFbOD27J/YBdpAG4zFuXqf24632K6M1nSSZdjjf9bkP+K6/sQG7jShf/cSv6G03JCu6Xx/lZkZs9sf6SMEsX53w4tVheoWv4CGG+niKjqXKB9TwAot6lWKsZHV9gTAbSoF3ggdmzWNfz25GA+gwwg=
    ContentPropagator: 001191440300708461136T1XGW3
    PropagateID: 62a5f052892935463ed1c42751e16e2e_2ae2129d818811f1bbe75254006c9bbf
    ReservedCode2: loP/oNb+yhClJ2yn8l9MQOM+DNRsVD44TreNFQAFbOD27J/YBdpAG4zFuXqf24632K6M1nSSZdjjf9bkP+K6/sQG7jShf/cSv6G03JCu6Xx/lZkZs9sf6SMEsX53w4tVheoWv4CGG+niKjqXKB9TwAot6lWKsZHV9gTAbSoF3ggdmzWNfz25GA+gwwg=
---

# 目标体系批判分析报告

> 分析日期：2026-07-17  
> 分析范围：`backend/` 全量 + `novel_world/engine/` 全量  
> 对照对象：用户五项批判  

---

## 一、现状总览：代码中已有的目标相关功能

### 1.1 backend 体系（8个 .py 文件，`H:\小说\小说世界\backend\`）

| 文件 | 行 | 目标相关功能 | 定位 |
|------|-----|-----------|------|
| `character.py` | L8-14 | `Goal` dataclass: description + priority(1-10) + progress + reason_changed | 角色级目标核心数据结构 |
| `character.py` | L23-28 | `CharacterAgent` 持有 `long_term_goal` (priority=10) + `short_term_goals` list (priority=7) | 角色初始化绑定目标 |
| `character.py` | L49-66 | `add_goal()` / `update_goal()` / `abandon_goal()` | 目标增改放弃 |
| `character.py` | L77-85 | `active_goals_text()` → 渲染活跃目标为 prompt 文本 | 喂给 AI prompt |
| `config.py` | L16-17 | `CharacterConfig.short_term_goals` / `long_term_goal` | 用户配置入口 |
| `engine.py` | L16-17 | 主循环注释声明"每个角色根据自己的目标行动" | 引擎流程声明 |
| `engine.py` | L102-144 | `_character_act()` 将 `full_state_text()` 写入 AI prompt 驱动行动 | 目标→AI行动的唯一通路 |
| `engine.py` | L135-139 | `get_state()` 输出 `long_term_goal` / `active_short_goals` | 前端展示 |
| `collision.py` | L19, L36, L43-44 | AI prompt 明确要求"这次相遇是否改变了其中任何一方的目标" | 碰撞触发目标变更 |
| `collision.py` | L83-108 | 解析 AI 返回的 `【目标变化】` 节，调用 `update_goal()` | 目标自动变更 |
| `ai_client.py` | L83-84 | 角色 system prompt: "你的短期和长期目标是行动的核心驱动力" / "你可以因为遭遇的事件而改变目标" | Prompt 层面的目标驱动声明 |
| `ai_client.py` | L149-161 | `generate_characters()` 的 AI prompt 要求角色含 `long_term_goal` + `short_term_goals` | AI 生成角色时附带目标 |
| `storage.py` | L55-150 | 完整的 Goal 序列化/反序列化 | 持久化 |
| `narrative.py` | L25 | 角色行动默认值："在本章中按自己的目标行事" | 叙事兜底 |
| `narrative.py` | L57-73 | `generate_world_event()` 生成世界事件，但**不基于任何世界级目标** | 世界事件生成（空壳） |
| `world.py` | L1-57 | `World` 管理章节计数和事件列表，**无任何目标相关字段** | 世界状态（无目标概念） |

### 1.2 novel_world/engine 体系（`H:\小说\小说世界\novel_world\engine\`）

| 文件 | 行 | 目标相关功能 | 定位 |
|------|-----|-----------|------|
| `scheduler/goal_scheduler.py` | 全 777 行 | `Goal` dataclass (含 level / status / parent / children / backup_pool / defer / threshold / branch / metadata)；`GoalStatus` 五态枚举；`GoalLevel` 三层层级(DAILY/STAGE/ULTIMATE)；`GoalScheduler` 完整调度器 | 目标调度的核心实现 |
| `scheduler/goal_scheduler.py` | L43-48 | `GoalLevel`: DAILY → STAGE → ULTIMATE 三层层级 | 层级体系，但仅限角色级 |
| `scheduler/goal_scheduler.py` | L290-355 | `_resolve_failed_goal()`: downgrade/reroute/abandon 三分支 | 失败处理机制 |
| `scheduler/goal_scheduler.py` | L360-412 | `tick_advance()`: 扫描 EXECUTING 的 DAILY 目标 → 未完成即 defer → 超阈值触发失败处理 | Tick 推进核心 |
| `scheduler/goal_scheduler.py` | L414-442 | `tick_advance_all()`: 批量推进所有角色 | 批量处理入口 |
| `novel_engine.py` | L202-227 | `add_goal()` / `complete_goal()` 门面方法 | NovelEngine 暴露的目标 API |
| `novel_engine.py` | L303-316 | `advance_tick()` 步骤2：推进所有活跃角色的目标 | Tick 主循环中绑定 |
| `novel_engine.py` | L39-41 | `TickResult` 含 `new_goals` / `deferred_goals` / `failed_goals` | 结果汇总 |
| `config/game_config.py` | L189 | `PlotSetting.expected_ending: str` | 预期结局（字符串，未接入引擎） |
| `config/game_config.py` | L63-64 | `CharacterSetting.goal` + `fate_arc` | 角色级目标配置 |
| `core/world.py` | L58-83 | `Faction` dataclass: 8 个字段，**无 goal 字段** | 势力数据结构 |
| `core/events.py` | L356-368 | `priority_chars` 筛选逻辑（事件叙事中的角色优先级） | 事件优先级，非目标优先级 |
| `collision/collision_engine.py` | L277 | `_ticks_per_chapter = 20` (硬编码) | 章节长度控制（硬编码） |
| `collision/collision_engine.py` | L366 | `priority_map = {"目标对冲": 3, ...}` | 碰撞类型优先级，非目标调度优先级 |
| `collision/collision_engine.py` | L1259-1289 | `finalize_chapter()`: 聚合碰撞叙事，生成收尾 | 章节收尾机制 |

---

## 二、逐条验证

### 批判一：角色 Goal 仅驱动个体行为，无法约束世界整体走向

**验证结果：成立。**

#### 证据

1. **`backend/world.py`**（共 57 行）：`World` 类完全没有目标相关字段。没有 `world_goal`、`main_plot_target`、`global_objective` 等任何概念。它只管章节计数、事件记录、角色位置追踪。

2. **`backend/config.py`**：`WorldConfig` 包含 `name / genre / era / description / rules / key_locations / current_situation / tone`，独缺世界级目标字段。

3. **`backend/narrative.py` L57-73**：`generate_world_event()` 每章调用一次，但 AI prompt 中只传了 `world.config.current_situation`（一段静态描述字符串）和角色列表。生成的"世界事件"是 AI 即兴发挥的产物，**不受任何预设的主线约束**。

4. **`novel_world/engine/config/game_config.py` L189**：`PlotSetting.expected_ending` 只是一个自由文本字符串。后端和引擎中没有任何代码读取它来约束目标生成或叙事走向。

5. **角色目标随机生成**：`backend/ai_client.py` L149-161 的 `generate_characters()` 让 AI "根据世界设定生成角色"，角色目标是 AI 自由发挥的结果。`CharacterConfig.short_term_goals` / `long_term_goal` 来自用户手动填写或 AI 生成，无任何机制校验其与"世界主线"的一致性。

6. **无全局主线配置入口**：用户配置项中 `WorldConfig` 没有"主线目标"字段。启动时用户无法预设"这个世界要讲一个什么故事"。

#### 结论

世界级目标概念在代码中**完全不存在**。角色目标生成后独立驱动个体行为，天道（AI prompt）每章即兴生成世界事件，两者之间没有约束关系。`expected_ending` 写了没人读。

---

### 批判二：目标调度缺少权重优先级

**验证结果：部分成立。**

#### 证据

**成立部分：engine GoalScheduler 没有优先级/权重字段**

- `scheduler/goal_scheduler.py` L72-99 的 `Goal` dataclass 字段清单：`id, content, level, status, character_name, parent_goal_id, child_goal_ids, backup_pool, defer_count, defer_threshold, created_tick, completed_tick, failed_branch, metadata` —— **没有 `priority` 或 `weight` 字段**。
- `tick_advance()` (L360-412) 对所有角色的所有 EXECUTING 状态的 DAILY 目标**等权处理**：遍历 → 未完成就 defer。没有任何排序或优先级筛选。
- `get_daily_goals_for_tick()` (L255-268) 只过滤 `level == DAILY and status in (PENDING, EXECUTING)`，不排序。

**不成立部分：层级体系提供了隐式优先级**

- `GoalLevel`: DAILY(日常) → STAGE(阶段) → ULTIMATE(终极)，三层层级形成树形结构。DAILY 服务于 STAGE，STAGE 服务于 ULTIMATE。这是一种隐式的优先级（高层级目标驱动低层级目标的生成）。
- 父子关系（`parent_goal_id` → `child_goal_ids`）和完成级联（`complete_goal()` L288-293 检查兄弟目标完成状态）构成了结构性优先级。

**backend Goal 有字段但未用于调度**

- `backend/character.py` L8-13: `Goal.priority: int = 5`（注释说明 "1-10，越高越重要"）。但这个字段只在以下场景使用：(a) `active_goals_text()` 渲染为提示文本 → 展示给 AI；(b) 初始化时硬编码 `long_term_goal.priority=10`，`short_term_goal.priority=7`。**在 engine.py 的行动决策流程中完全未参与调度**——角色的行动由 AI 自由决定，AI prompt 中包含了优先级文本但 AI 不一定严格遵循。

#### 结论

engine 的 GoalScheduler 在真正的调度逻辑中没有任何数值优先级字段，所有活跃目标等权处理。backend 的 `priority` 字段存在但只用于 prompt 展示，未参与行动调度。层级体系提供了结构性优先级，但缺少运行时动态权重排序机制（如"主角目标权重高于龙套"、"与主线相关的目标加权"等）。

---

### 批判三：目标未绑定世界终局

**验证结果：成立。**

#### 证据

1. **`backend/world.py`**：`World` 只有 `current_chapter` 递增，**没有 `max_chapters` 或任何停止条件**。引擎会无限循环直到用户手动停止。

2. **`novel_world/engine/collision/collision_engine.py` L277**：`_ticks_per_chapter = 20` 是硬编码常量，控制每章 tick 数。但**没有对应的 `_max_chapters`**。`finalize_chapter()` (L1259-1289) 只聚合叙事和生成收尾，收尾后 `_current_chapter = None` → 调用方如果继续 `start_new_chapter()` 则进入下一章，无限循环。

3. **`novel_world/engine/config/game_config.py` L189**：`PlotSetting.expected_ending` 存在但未被任何引擎代码引用。全文搜索 `expected_ending` 只在 `game_config.py` 的 `to_dict()` / `from_dict()` 中出现，无调用方。

4. **自动收尾逻辑**：碰撞引擎有自动收尾（`ticks_per_chapter` 达到后自动 finalize），但这是**章节级**自动收尾，不是**故事级**终局收尾。没有代码检查"所有角色的 ULTIMATE 目标是否都已完成/放弃"来决定故事是否结束。

5. **DM v2 文档**（`docs/dm_mode_and_timeline_check_design_v2.md`）§3.3 完整设计了 `EngineConfig`（含 `total_chapters`、`chapter_end_behavior`、`auto_pause_between_chapters`）、DM 启动面板、运行时配置修改 API。但这是**纯文档设计，代码中零实现**。

6. **角色长期目标完成后对世界状态的影响**：`goal_scheduler.py` 的 `complete_goal()` 在 DAILY 目标完成且无父目标时，会从 backup_pool 或 STAGE 目标生成下一个 DAILY 目标 (L295-318)，属于"自动续杯"逻辑。STAGE/ULTIMATE 目标完成后**不触发任何世界级事件，也不检查故事是否该结束**。

#### 结论

`max_chapters` 和全局结局在代码中完全缺失。DM v2 文档设计了完整的 `EngineConfig` 方案但未实现。角色目标有"自动续杯"机制（完成后生成下一个），但没有"杯子满了就停止"的终局判断。世界故事的起承转合没有任何程序化约束。

---

### 批判四：缺失世界级和势力级长线目标

**验证结果：成立。**

#### 证据

**WorldGoal 类**：全局搜索 `WorldGoal`、`world_goal`、`world.*goal` → **零命中**。

**FactionGoal 类**：全局搜索 `FactionGoal`、`faction.*goal` → **零命中**。

**Faction 类**（`novel_world/engine/core/world.py` L58-83）：

```python
@dataclass
class Faction:
    id: str
    name: str = "未命名势力"
    color: str = "#FFFFFF"
    member_ids: list = field(default_factory=list)
    resources: dict = field(default_factory=lambda: {"gold": 100, "food": 50})
    territory: list = field(default_factory=list)
    leader_id: str = ""
    description: str = ""
```

8 个字段中，没有一个与目标/目的/宗旨相关。势力是纯数据结构——存身份、资源、领地，不存志向。

**engine 的 GoalLevel 体系**：`GoalLevel` 枚举定义了 `DAILY / STAGE / ULTIMATE` 三个层级，但 `Goal.character_name` 字段（L96）将目标绑定到单个角色。目标调度器的 `character_goals: Dict[str, List[str]]` 索引也是角色维度。整个 `GoalScheduler` 没有 `faction` 或 `world` 维度的目标存储。

**Faction 势力的集体行为**：`interaction_system.py` L14-35 定义了 `FactionInteraction`（含 `ALLIANCE = "结盟"`），这是势力间的**交互行为**（类似碰撞），不是势力的**目标驱动行为**。势力没有"我们想要占领 X 领地"这样的目标规划能力。

**theme_rules.py** 中各主题的势力规则都是描述性文本（L4: "势力是学校、公司、社团"；L59: "势力是宗门、家族、坊市"），不是可执行的数据结构。

#### 结论

代码中所有目标语义都限定在角色维度。`WorldGoal` 和 `FactionGoal` 是空白——没有类定义、没有调度逻辑、没有与角色目标的关联机制。Faction 有资源和领地系统但缺乏"为什么要这样做"的目标层。整个目标体系是"只有细胞（角色目标），没有器官（势力目标）和身体（世界目标）"。这三层如果能对齐，角色目标服务于势力目标、势力目标服务于世界目标，将形成强大的故事驱动力——目前完全缺失。

---

### 批判五：DM 干预只是临时修正

**验证结果：部分成立——设计完整但代码未实现，且缺少批量操作**

#### 证据

**DM v2 文档**（`docs/dm_mode_and_timeline_check_design_v2.md` §3.5）定义了 5 类干预能力：

| 干预类型 | 粒度 | 文档位置 | 代码实现 |
|----------|------|----------|----------|
| 注入事件 (Inject Event) | 单次事件，可设 `affect_goals=True` | §3.5.1 | 未实现 |
| 修改角色属性 (Modify Character) | 单角色：境界/位置/关系/目标/技能/物品 | §3.5.2 | 未实现 |
| 强制行动 (Force Action) | 单角色，覆盖 AI 目标，持续 N ticks | §3.5.3 | 未实现 |
| 增减角色 (Add/Remove Character) | 单角色 | §3.5.4 | 未实现 |
| 调整世界观 (Adjust World) | 增规则/增地点/改全局状态 | §3.5.5 | 未实现 |

**成立部分——缺少批量操作机制**：

1. **批量目标操作缺失**：DM 可以逐角色修改目标（通过 Modify Character），但没有"将所有角色的 DAILY 目标对齐到某个新 STAGE 目标"或"为所有反派批量注入目标"的批量操作接口。
2. **目标模板/预设缺失**：DM 无法预定义"标准剧情模板"（如"秘境探险模板"包含 3 个 STAGE + 6 个 DAILY 目标），每次需手动逐条创建。
3. **跨角色目标联动缺失**：无法创建"角色 A 和角色 B 的共同目标"或"如果角色 A 完成目标 X，自动为角色 B 注入目标 Y"的关联规则。

**部分成立——干预本身是临时性的**：

- DM v2 文档设计的干预机制本质上是"暂停 → 手动修改状态 → 继续运行"。修改的是当前世界快照，不建立持久的约束规则。例如 DM 手动把角色 A 的目标改成"寻找神剑"，但如果后续碰撞引擎触发目标变更，这个手动设置可能被 AI 覆写——没有锁机制。
- DM v2 文档 §3.6 设计了快照和回退机制，但所有干预都是**快照级修改**，不是**规则级约束**。没有"无论如何，这个目标优先级锁定为最高"的持久化标记。

**文本中现有的实际代码能力**：

- `backend/engine.py` 没有 DM 接口，纯自动驾驶。
- `novel_world/engine/novel_engine.py` 暴露了 `add_goal()` / `complete_goal()` API，这可以勉强算是最小化的 DM 干预（手动添加/完成目标），但没有暂停/恢复/快照/批量等上层能力。

#### 结论

DM v2 文档设计了较完善的单条干预能力（5 类操作），但：① 全部停留在文档阶段，代码中零实现；② 缺少批量操作、目标模板、跨角色联动目标等高级机制；③ 干预是快照级修改而非规则级约束，无法防止后续被 AI 覆写。

---

## 三、缺口总结

| 缺口 | 严重程度 | 现状 | 影响 |
|------|----------|------|------|
| **无世界级目标** | 🔴 致命 | 零概念、零代码 | 故事没有主线，全靠 AI 即兴发挥 |
| **无势力级目标** | 🔴 致命 | Faction 有雏形但无目标层 | 势力是空壳，无法驱动集体行为 |
| **无全局终局控制** | 🔴 致命 | `max_chapters` 在 DM v2 文档中设计但未实现 | 引擎无限循环，永远不停止 |
| **角色目标无运行时优先级** | 🟡 重要 | backend 有字段但没用；engine 完全没有 | 龙套和主角的目标等权重处理 |
| **DM 干预未实现** | 🟡 重要 | v2 文档完整设计，零代码 | 用户无法在运行中引导故事走向 |
| **世界事件无主线约束** | 🟡 重要 | `generate_world_event()` 纯 AI 即兴 | 世界事件可能与角色目标无关联 |
| **expected_ending 是死数据** | 🟡 重要 | 字段存在但无消费代码 | 用户写了结局预期但引擎不看 |
| **缺少批量目标操作** | 🟢 次要 | DM v2 设计文档中未涉及 | DM 无法高效管理多角色目标 |
| **无目标模板/预设** | 🟢 次要 | 无设计、无代码 | 每次需手动逐条创建目标 |
| **目标无持久化锁** | 🟢 次要 | 无设计、无代码 | DM 手动修改可能被 AI 覆写 |

### 已有雏形但不够的

| 功能 | 已有 | 不够 |
|------|------|------|
| 角色目标层级 | engine 的 ULTIMATE/STAGE/DAILY 三层 + 父子树 + 完成级联 | 仅限角色级，无势力/世界级扩展 |
| 失败处理 | 三分支策略 (downgrade/reroute/abandon) | 只在 DAILY 触发 defer → 失败，STAGE/ULTIMATE 缺少主动推送机制 |
| 章节收尾 | `finalize_chapter()` + 四段式聚合 | 只有章节级，没有故事级收尾 |
| 目标优先级 | backend `Goal.priority` 字段存在 | 仅在 prompt 文本中展示，未参与调度 |
| DM 干预设计 | v2 文档 5 类操作完整定义 | 代码未实现；缺批量/模板/锁 |

---

## 四、改进优先级

### P0（阻塞性——必须优先解决）

| 序号 | 改进项 | 理由 | 建议方案 |
|------|--------|------|----------|
| 1 | 实现 `EngineConfig`（含 `total_chapters`） | 解决引擎无限循环的致命问题 | 将 DM v2 文档 §3.3 的 `EngineConfig` 落地到 `novel_world/engine/config/engine_config.py`，接入 `NovelEngine.advance_tick()` 流程 |
| 2 | 新增 `WorldGoal` 数据结构 + 调度 | 补全世界级目标，约束整体走向 | 在 `goal_scheduler.py` 同级创建 `world_goal.py`，含 `WorldGoal` 类（绑定到主题/主线），与角色 Goal 共享 `GoalLevel.ULTIMATE` 语义 |
| 3 | 用户可配置"世界主线目标" | 启动时预设故事方向 | 在 `WorldConfig` / `PlotSetting` 中增加 `main_objective` 字段，在初始化时将主线目标拆解为角色级 ULTIMATE 目标下发 |

### P1（重要——影响核心体验）

| 序号 | 改进项 | 理由 | 建议方案 |
|------|--------|------|----------|
| 4 | `Faction` 增加目标字段 | 势力从"数据结构"升级为"有意图的实体" | 在 `Faction` 中增加 `goals: List[Goal]`，复用 Goal 的层级体系；在 `GoalScheduler` 中增加 `faction_goals` 索引 |
| 5 | `tick_advance` 引入运行时优先级排序 | 主角目标 > 配角目标，主线相关目标加权 | 在 `Goal` 中增加 `weight: float` 字段；`tick_advance` 中按 weight 排序处理；默认按角色类型赋权 |
| 6 | `expected_ending` 接入终局判断 | 让引擎知道"故事该结束了" | 在 `advance_tick()` 流程中增加终局检查：当 `current_chapter >= total_chapters` 或所有角色 ULTIMATE 目标完成时，触发 `finalize_story()` |

### P2（增强——提升 DM 体验）

| 序号 | 改进项 | 理由 | 建议方案 |
|------|--------|------|----------|
| 7 | 实现 DM 核心干预 API | 让 DM 模式可用 | 将 v2 文档 §3.5 的 5 类干预实现为 `DMManager` 方法，尤其是 Modify Character（含目标增删改） |
| 8 | 世界事件生成基于世界目标约束 | 停止 AI 即兴发挥 | 修改 `generate_world_event()` 的 prompt，传入世界主线目标作为约束条件 |
| 9 | 批量目标操作 + 预设模板 | 提高 DM 效率 | 提供"批量注入 DAILY 目标"API + "剧情模板库"（含预设的目标树结构） |

---

## 五、与 DM 模式 / 天意指引的联动设计建议

### 5.1 三层目标对齐架构

```
┌─────────────────────────────────────────┐
│           WorldGoal (天道)               │
│  "修仙世界：正邪大战，正道胜利"          │
│  → 拆解为势力目标                         │
├──────────────┬──────────────────────────┤
│  FactionGoal │  FactionGoal             │
│  正道联盟：   │  魔教：                  │
│  团结各派     │  夺取灵脉                │
│  → 拆解为角色目标                        │
├──────────────┬──────────┬───────────────┤
│ CharacterGoal│CharacterGoal│CharacterGoal│
│ 主角：修炼突破│ 盟友：寻找神器│ 反派：破坏联盟│
└──────────────┴──────────┴───────────────┘
```

### 5.2 DM 干预从"临时修正"升级为"天意指引"

当前 DM 干预是手动修改快照。升级后：

1. **DM 干预世界目标** → 自动级联更新势力目标 → 再级联更新角色目标
2. **DM 设定"天意指引"约束** → 角色 AI 在决策时受约束（prompt 中注入"天道意志：你必须..."）
3. **DM 锁定关键目标** → 标记 `locked=True`，碰撞引擎和角色 AI 不得变更
4. **终局触发器** → DM 预设"当主角达到化神期，触发最终决战事件"，引擎自动检测条件

### 5.3 与 DM v2 文档的衔接

DM v2 文档 §3.3 的 `EngineConfig` 和 §3.5 的干预能力已经为上述设计预留了接口。建议：

- `EngineConfig` 增加 `world_objective: str` 字段
- `Modify Character` (API: `/api/dm/modify_char`) 的 `modifications` 中 `goal` 操作增加 `locked: bool` 选项
- 新增 API: `POST /api/dm/set_world_goal` 和 `POST /api/dm/set_faction_goal`
- `DMManager` 增加 `apply_divine_guidance()` 方法，将 DM 指令转化为 prompt 约束注入 AI

### 5.4 最小可行路径

如果资源有限，建议优先实现：

1. `EngineConfig` 落地（含 `total_chapters`）→ 解决无限循环
2. `WorldConfig.main_objective` + 在 `generate_world_event()` prompt 中注入 → 解决世界事件随机性
3. `Goal.weight` + `tick_advance` 排序 → 解决调度无序
4. `Faction.goals` 字段 + 基础级联 → 解决势力无目标

这四项改变约 200-300 行代码，覆盖 🔴 致命缺口的 80%。

---

## 附录：代码行号索引

| 概念 | 文件 | 行号 |
|------|------|------|
| backend Goal dataclass | `backend/character.py` | L8-14 |
| backend CharacterAgent 目标初始化 | `backend/character.py` | L23-28 |
| backend 目标操作 (add/update/abandon) | `backend/character.py` | L49-74 |
| backend active_goals_text() | `backend/character.py` | L77-85 |
| backend full_state_text() | `backend/character.py` | L129-140 |
| backend CharacterConfig 目标字段 | `backend/config.py` | L16-17 |
| backend 引擎主循环 | `backend/engine.py` | L15-95 |
| backend _character_act() | `backend/engine.py` | L102-144 |
| backend 碰撞目标变更 | `backend/collision.py` | L36-108 |
| backend AI prompt 目标声明 | `backend/ai_client.py` | L83-84 |
| backend 角色生成 prompt | `backend/ai_client.py` | L149-161 |
| backend 世界事件生成 | `backend/narrative.py` | L57-73 |
| engine Goal dataclass | `novel_world/engine/scheduler/goal_scheduler.py` | L72-131 |
| engine GoalLevel 枚举 | `novel_world/engine/scheduler/goal_scheduler.py` | L49-65 |
| engine GoalStatus 枚举 | `novel_world/engine/scheduler/goal_scheduler.py` | L37-47 |
| engine GoalScheduler 类 | `novel_world/engine/scheduler/goal_scheduler.py` | L134-777 |
| engine add_goal() | `novel_world/engine/scheduler/goal_scheduler.py` | L166-215 |
| engine complete_goal() | `novel_world/engine/scheduler/goal_scheduler.py` | L260-318 |
| engine _resolve_failed_goal() | `novel_world/engine/scheduler/goal_scheduler.py` | L331-399 |
| engine tick_advance() | `novel_world/engine/scheduler/goal_scheduler.py` | L403-442 |
| engine tick_advance_all() | `novel_world/engine/scheduler/goal_scheduler.py` | L444-472 |
| engine NovelEngine 目标管理 | `novel_world/engine/novel_engine.py` | L202-227 |
| engine advance_tick 目标推进 | `novel_world/engine/novel_engine.py` | L303-316 |
| engine Faction dataclass | `novel_world/engine/core/world.py` | L58-83 |
| engine PlotSetting.expected_ending | `novel_world/engine/config/game_config.py` | L189 |
| engine _ticks_per_chapter 硬编码 | `novel_world/engine/collision/collision_engine.py` | L277 |
| engine finalize_chapter() | `novel_world/engine/collision/collision_engine.py` | L1259-1289 |
| DM v2 EngineConfig 设计 | `docs/dm_mode_and_timeline_check_design_v2.md` | §3.3 |
| DM v2 干预能力设计 | `docs/dm_mode_and_timeline_check_design_v2.md` | §3.5 |
| DM v2 恢复机制 | `docs/dm_mode_and_timeline_check_design_v2.md` | §3.6 |
*（内容由AI生成，仅供参考）*
