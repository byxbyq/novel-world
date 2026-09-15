---
AIGC:
    Label: "1"
    ContentProducer: 001191440300708461136T1XGW3
    ProduceID: 62a5f052892935463ed1c42751e16e2e_6131c1c2818e11f1bbe75254006c9bbf
    ReservedCode1: tJOqYqpkSy3yDAtlsxqmz58o/q49mYCZHv++SpdKNQ9PdobDnllKbXdyRYaQGWq6atim53pUSqhduMXcyaihkIKg51WspAL9oBPce220zbiaSf4gpJSk0tN8R6FnLatgcK80NbwKuoVbqQ3I0vHnnlFPXHf3V+AEG7nXTEv0sHg96ffyuROIbyIHQMQ=
    ContentPropagator: 001191440300708461136T1XGW3
    PropagateID: 62a5f052892935463ed1c42751e16e2e_6131c1c2818e11f1bbe75254006c9bbf
    ReservedCode2: tJOqYqpkSy3yDAtlsxqmz58o/q49mYCZHv++SpdKNQ9PdobDnllKbXdyRYaQGWq6atim53pUSqhduMXcyaihkIKg51WspAL9oBPce220zbiaSf4gpJSk0tN8R6FnLatgcK80NbwKuoVbqQ3I0vHnnlFPXHf3V+AEG7nXTEv0sHg96ffyuROIbyIHQMQ=
---

# Adapter 适配层 5 个 TODO 技术说明

> 生成日期：2026-07-17  
> 基于源码版本：Phase 1 P0 Adapter 适配层完成时的代码快照

---

## 问题1：NovelEngine 调度层 (scheduler/timeline/goal/consistency) 未接入

### 是什么？

`novel_world/engine/scheduler/` 是一个**六模块调度层**，在 `NovelEngine`（`novel_world/engine/novel_engine.py`）中被统一编排。以下是各模块职责：

| 模块 | 文件 | 核心类 | 职责 |
|------|------|--------|------|
| **WorldTimeline** | `world_timeline.py` | `WorldTimeline`, `WorldTick` | 管理世界时间轴：tick → chapter → scene 的层级映射。每个 tick 归属一个阶段（铺垫/主角行动/配角入场/收尾），追踪章节边界 |
| **SwimlaneManager** | `swimlane_manager.py` | `CharacterSwimlane`, `ActionRecord`, `LifecycleStage` | 每个角色一条独立泳道，记录动作历史、状态机（激活/退出/死亡/长休）。防止同 tick 内角色"分身"出现矛盾动作 |
| **GoalScheduler** | `goal_scheduler.py` | `Goal`, `GoalStatus`, `GoalLevel` | 角色目标调度器，支持目标等级（DAILY/CHAPTER/ARCH/MACGUFFIN），追踪完成/推迟/失败状态，跨 tick 推进多角色并行目标 |
| **CausalCollisionScheduler** | `causal_collision_scheduler.py` | `CollisionRecord`, `CausalCollisionScheduler` | 因果链接碰撞调度，把单次碰撞关联到上下游因果链。例如"A 的目标受阻 → 触发 B 入场"形成叙事因果网络 |
| **ConsistencyChecker** | `consistency_checker.py` | `ConsistencyIssue`, `CheckLevel` | 跨 tick 一致性校验：角色状态跳跃（上 tick 受伤下 tick 满状态复活）、目标链断裂、时间线矛盾，分 WARNING/ERROR 两级 |
| **WorldRuleGuard** | `world_rule_guard.py` | `GuardViolation`, `GuardLevel`, `WorldRule` | 世界规则守卫：检查叙事是否违反底层设定（如"修仙世界不能用手机"）。可插拔规则源，支持硬约束和软建议 |
| **TimelineBranch** | `timeline_branch.py` | `TimelineBranch` | 时间线分支系统：从任意 tick fork 出一条 IF 分支线，支持平行宇宙叙事和多结局管理 |

### NovelEngine 如何编排它们？

`NovelEngine.advance_tick()` 的完整流程（`novel_engine.py` 第 60+ 行）：

```
advance_tick(scene)
  ├── WorldTimeline.advance()          # tick+1，确定当前 chapter 和 phase
  ├── SwimlaneManager.open_tick()      # 为每个角色打开本 tick 的泳道槽
  ├── GoalScheduler.schedule()         # 按优先级分配角色目标（每日/章节/宏目标）
  ├── CausalCollisionScheduler.detect()# 检测碰撞并构建因果链
  ├── ConsistencyChecker.check()       # 跨 tick 一致性校验
  ├── WorldRuleGuard.guard()           # 规则兜底检查
  └── 返回 TickResult
```

### 为什么 Adapter 暂时跳过？

1. **发展阶段**：scheduler 是"重型引擎"的腹地模块，正在独立演进。Adapter 当前目标是"打通双引擎"，不是"瞬间替换全部能力"。
2. **下游依赖链**：CausalCollisionScheduler 依赖 GoalScheduler 产出，GoalScheduler 依赖 SwimlaneManager。接入需要完整链路就绪，不能局部接通。
3. **与 backend 差异巨大**：backend 的 `GameEngine.tick()` 没有目标/泳道/因果链概念，它的 tick 就是"随机移动 → AI 叙事 → 碰撞 → 归入 story_log"。强行映射反而会造成语义断裂。
4. **当前替代方案**：Adapter 保留了 backend 的 tick 流程（AI 叙事 + 同位置碰撞），只是底层换成了 novel_world 的数据结构。这已经实现了"数据结构统一"，调度层接入是下一步精细化的事情。

### 证据

- `novel_engine.py` 第 1-60 行：NovelEngine 导入所有 6 个 scheduler 模块，`TickResult` dataclass 汇总全部输出
- `scheduler/__init__.py`（102 行）：明确列出 6 个子模块及其职责
- `adapter/adapter.py` 第 234-244 行：`_nw_tick_once()` 未加载任何 scheduler 模块

---

## 问题2：角色类型映射 — char_type 全部硬编码为 PROTAGONIST

### 两边的类型体系

#### backend 端（`backend/character.py`）

**backend 没有 `char_type` 字段。**

`CharacterAgent` 和 `CharacterConfig` 是两个独立的 dataclass（`character.py` 共 179 行），字段包含 `name`、`personality`、`goal`、`appearance`、`position` 等，但**没有角色类型枚举**。backend 的角色类型由 AI 叙事自行理解——AI 从 `personality` 和 `goal` 的文本描述中推断"这是主角/反派/路人"，不依赖枚举标记。

#### novel_world 端（`novel_world/engine/core/character.py`）

**novel_world 有明确的 `CharType` 枚举**（5 种，`character.py` 第 20-26 行）：

| 枚举值 | 含义 | 语义 |
|--------|------|------|
| `PROTAGONIST` | 主角 | 故事核心，目标驱动主线 |
| `HEROINE` | 女主角 | 关键女性角色，通常与主角有感情线 |
| `ANTAGONIST` | 反派 | 对抗主角，有自己的目标体系 |
| `NPC` | 普通路人 | 填充世界的背景角色 |
| `KEY_NPC` | 关键配角 | 与主线强相关但不属于前三类 |

### 体系一致吗？

**不完全一致。** backend 没有枚举（靠 AI 自由理解），novel_world 有精确枚举。novel_world 的枚举是 backend 的超集——novel_world 可以接管 backend 的全部语义（把 backend 的角色映射为 5 种类型之一），但反过来不行（backend 无法精确区分 NPC 和 KEY_NPC）。

### char_type 是用户输入还是 AI 生成？

**两种来源都有：**

- **用户输入**：`novel_world/engine/core/engine.py` 第 187-251 行 `_create_characters()` 中，主角/女主角/反派的 `char_type` 由用户在 `settings` 中指定（如 `hero_name` → `CharType.PROTAGONIST`），没有提供则使用默认值和 `generate_random_character()` 自动生成。
- **AI/系统自动生成**：NPC 的 `char_type` 全部由系统在 `generate_random_character()` 中赋值为 `CharType.NPC`。

### 为什么 Adapter 先硬编码成 PROTAGONIST？

`adapter/adapter.py` 第 152 行：

```python
char_type=CharType.PROTAGONIST,  # TODO: 需要映射
```

原因：

1. **backend 没有 char_type 字段**：`CharacterAgent` 和 `CharacterConfig` 都不包含角色类型。Adapter 的 `_convert_character()` 方法从 backend 数据中拿不到 `char_type`，必须自己推断。
2. **推断逻辑未实现**：正常映射应该是——根据 `CharacterAgent` 中某字段（如 `role` 或 `name` 匹配主角名）推断类型。但 Adapter 当前没有保留"谁是主角"的上下文，也没有实现推断逻辑。
3. **安全兜底**：硬编码 PROTAGONIST 不会导致崩溃（至少保证创建的 novel_world Character 类型合法），但会导致所有角色都被当作主角处理，技能/碰撞系统可能给出语义错位的结果（如 NPC 触发主角专属事件）。

---

## 问题3：技能系统 — 空 SkillRegistry

### novel_world 的 SkillRegistry 设计意图

`novel_world/engine/skills/skill_registry.py`（337 行）和 `skill_model.py`（262 行）构成了完整的**叙事式技能体系**。

#### 四维度技能模型

`skill_model.py` 中的 `Skill` 包含 4 个子维度：

| 维度 | 类 | 含义 | 示例 |
|------|-----|------|------|
| **PASSIVE** | `Passive` | 核心特质/被动能力 | "天生神识敏锐，能感知方圆十里的灵力波动" |
| **ACTIVE** | `Active` | 主动手段/可发动的技能 | "万剑归宗 · 以神识驱动数百把飞剑同时攻击" |
| **LIMIT** | `Limit` | 限制/盲点/弱点 | "剑招威力越大，对自身经脉的反噬越重" |
| **COST** | `Cost` | 代价/后遗症 | "每次使用消耗三年寿元" |

#### 三类碰撞检测

`SkillRegistry.find_collisions()` 扫描所有角色对，检测：

| 碰撞类型 | 检测逻辑 | 触发条件 |
|----------|----------|----------|
| **PERCEPTION 对冲** | 角色A的感知技能 → 角色B的隐匿技能 | "能感知一切灵力波动" vs "能完全隐匿气息" |
| **GOAL 对冲** | 角色A的目标关键词 → 角色B的目标关键词 | "守卫禁地" vs "闯入禁地" |
| **ABILITY 对冲** | 角色A的主动技能标签 → 角色B的弱点标签 | "火系功法"攻击 vs "惧火体质" |

冲突判定使用内置对立词表：`_PERCEPTION_KEYWORDS`（感知检测/暗中行动等）和 `_GOAL_OPPOSITES`（守卫攻击/潜入逃跑等）。

### backend 是否有技能相关代码？

**backend 没有独立的技能系统。** 从代码结构看：

- `backend/engine.py` 中有 `hero_abilities_raw` 字段（第 195 行），用户输入后用逗号分隔存为 `hero_skills` 列表。但此列表**仅作为 `Character` 的 `skills` 属性存储**，不参与碰撞检测或叙事生成。
- `backend/collision_engine.py` 的碰撞检测仅基于**同位置判定**（两个角色在同一坐标），不与技能产生任何关联。
- `backend/narrative.py` 生成叙事时也会把角色信息传入 AI，但技能不会触发特殊的叙事逻辑。

### 当前技能系统是什么形态？

**novel_world 的技能系统是"叙事驱动式"，而非"数值 RPG 式"。** 关键证据：

1. 技能由自然语言描述（"精通暗杀，能在阴影中一击致命"），没有 HP/MP/ATK/DEF 等数值
2. 碰撞检测基于**语义关键词匹配**（感知词表、目标对立词表），而非数值比较（ATK > DEF）
3. 四维度模型（被动/主动/限制/代价）天然适合叙事冲突——"他的火焰剑克制她的冰霜盾"比"火系 +50% 伤害"更有故事感

这与 RPG 式技能（"扣血 300 点"、"+15% 暴击率"）完全不同。

### 小说场景下技能系统应该是什么方向？

novel_world 的叙事式技能系统**就是这个正确的方向**。小说的核心是冲突和张力，技能应服务于"角色 A 和角色 B 的能力如何碰撞出戏剧性"。数值化技能会削弱叙事真实感——"血量归零死去"远不如"被对手用自己最恐惧的方式击败"有阅读价值。

当前独木期建议：先不接入完整 SkillRegistry，而是**至少打通零阻力流水线**——把 backend 的 `hero_skills` 列表映射为 novel_world 的最简 `Skill` 模型（只有 name 和 description），注册到 SkillRegistry，让碰撞引擎能产出"技能交锋"类叙事。

---

## 问题4：AI 叙事降级 — 仍依赖 backend AI，无 novel_world 模板降级

### backend 的叙事生成方式

`backend/narrative.py` 的 `NarrativeGenerator` 有两个核心方法（`narrative.py` 共 124 行）：

- `generate_chapter()`：调用 `chat()` + `tian_dao_prompt()`（天道提示词）**全程依赖 AI**生成章节正文
- `generate_world_event()`：带 `world_stage` 分阶段提示（opening/rising/climax/falling/ending），也全程依赖 AI
- `determine_collisions()`：仅做**同位置判定**（坐标相同即为碰撞），也依赖 AI 生成碰撞叙事

**backend 没有离线模板**。AI 不可用时叙事直接为空，回退路径不存在。

### novel_world 的模板降级

novel_world 有**两层降级机制**：

#### 第一层：`_template_fallback`（`events.py` 第 1221 行起）

AI 调用失败时，`NarrativeEngine._template_fallback()` 返回基于主题的模板叙事。**为每个主题维护了 80+ 个模板**（以"修仙"主题为例，包含修炼突破、法宝奇遇、战斗交锋等 8 大类场景），使用 `{name}`、`{place}`、`{other}`、`{goal}` 占位符动态填充：

```
"{name}在{place}打坐沉沉入定，对{goal}有了新的领悟。"
```

#### 第二层：`_template_narrative`（`collision_engine.py` 第 500+ 行）

`CollisionEngine._generate_collision_narrative()` 优先调用 AI，降级时使用 `_template_narrative()`。为 4 种碰撞类型分别提供了中文渐进式模板：

| 碰撞类型 | 模板句子 | 叙事效果 |
|----------|----------|----------|
| 感知对冲 | 三段递进：感知 → 压制/反制 → 后果 | "A 的神识扫过……B 感到有人窥探……" |
| 目标对冲 | 三段递进：目标冲突 → 对抗 → 结果 | "A 要取走剑谱……B 拔剑拦住……" |
| 能力对冲 | 三段递进：能力描述 → 交锋 → 胜负/平手 | "A 的火系功法熊熊燃烧……B 的冰霜被压制……" |
| 接近碰撞 | 三段递进：靠近 → 发现 → 互动 | "A 出现在眼前……两人对视……" |

### 什么叫"模板降级"？

**模板降级 = 当 AI 网络不可用或响应超时时，用预写的叙事模板替代 AI 生成，保证系统不停摆。**

novel_world 的模板深度远超简单的"A走到B面前"——它按碰撞类型分支，每种类型有多套渐进句式，通过随机选句 + 角色名/场景填充产生变化感。虽然质量不如 AI 生成，但足以维持流水线运转。

### 为什么 backend 依赖 AI 而 novel_world 有离线模板？

**设计哲学不同：**

- **backend 是原型期产物**，假设"AI 永远在线"。上线时没有考虑离线降级的必要性。
- **novel_world 是工程化产物**，从架构层面就区分了"在线 AI 轨道"和"离线模板轨道"，两者在 CollisionEngine 里是并行的。

### TODO 的实际影响

当前 Adapter 用 backend 的 `NarrativeGenerator` 生成全部叙事——这意味**所有叙事仍然完全依赖 AI**。如果 AI 调用失败：
- backend 没有降级模板 → 叙事为空
- novel_world 的 `_template_fallback` 和 `_template_narrative` 没有被调用 → 离线能力被闲置

实际场景中，如果用户的 API Key 耗尽或大模型服务波动，小说生成会直接中断，而不是切换到模板模式继续产出可阅读的叙事。

---

## 问题5：地图/分阶段叙事 — 坐标随机移动没逻辑？

### Adapter 中坐标移动的实现

`adapter/adapter.py` 第 234-244 行 `_nw_tick_once()`：

```python
# 为每个角色生成随机步移
for c in list(self._nw_world.characters.values()):
    dx = random.choice([-1, 0, 1])   # 从{-1, 0, 1}中纯随机选
    dy = random.choice([-1, 0, 1])
    new_x = c.pos[0] + dx
    new_y = c.pos[1] + dy
    # clamp 到地图边界
    new_x = max(0, min(self._nw_world.map_size - 1, new_x))
    new_y = max(0, min(self._nw_world.map_size - 1, new_y))
    c.pos = (new_x, new_y)
```

### novel_world engine 中角色移动逻辑

`novel_world/engine/core/engine.py` 第 405-414 行 `_random_move_characters()`：

```python
def _random_move_characters(self):
    for c in self.world.characters:
        if not c.alive:
            continue
        if random.random() < 0.15:  # 15% 概率移动
            dx = random.randint(-1, 1)
            dy = random.randint(-1, 1)
            new_pos = self._clamp_pos((c.pos[0] + dx, c.pos[1] + dy))
            tile = self.world.get_tile(*new_pos)
            if tile and tile.tile_type != TileType.WATER:
                c.pos = new_pos
```

**两者的移动逻辑几乎完全相同：纯随机漫步。**

区别仅在于：
- novel_world 引擎有 15% 概率移动（不是每 tick 必动）
- novel_world 引擎有水域阻隔检测（`TileType.WATER`）
- Adapter 是每 tick 必移，且不检测地形

### backend 中角色移动逻辑

`backend/engine.py` 中 GameEngine 同样使用 `_random_move_characters()`——**纯随机移动**。backend 没有角色自主寻路或目标导向移动。

### 当前坐标移动是纯随机还是有目标导向？

**三套系统都是纯随机移动。** 没有任何一方实现了目标导向移动（如"向禁地方向移动"、"追踪反派"）。

### "上一秒东大路下一秒西大路"有没有这个问题？

**有，且证据明确：**

- Adapter 使用 `random.choice([-1, 0, 1])` 对 x 和 y 分别独立随机。这意味着：
  - tick N：  角色在 (10, 10)
  - tick N+1：可能移动到 (9, 9) → 往西北
  - tick N+2：可能移动到 (10, 8) → 往西
  - tick N+3：可能移动到 (11, 9) → 往东（方向完全反转）

在叙事中，角色"在东海边赶路"的描述和"坐标在三秒内从地图最东跳到最西"确实会产生矛盾。只不过当前因为这个移动太"微观"（每次 ±1 格），而叙事尺度太"宏观"（描述大段情节），所以这种矛盾在叙事文本中**暂时没有暴露**——AI 叙事没有把坐标信息写进文案。

### novel_world engine 有没有更好的移动逻辑只是 Adapter 还没接上？

**有的。** novel_world 的 `GoalScheduler` 和 `CausalCollisionScheduler` 提供了移动的"叙事理由"框架，虽然底层移动函数目前也是纯随机，但整体架构已经预留了目标导向移动的插槽：

1. **Goal 驱动移动**：`GoalScheduler` 管理角色的目标（如"前往禁地"、"追踪叶凡"），每个 Goal 可以附加 `target_location` 字段。`advance_tick` 流程中，角色移动应当是"朝目标位置趋近"而非纯随机——只是这个逻辑还未实现。
2. **接近碰撞**：`CollisionEngine` 使用**曼哈顿距离 ≤ 3** 判定接近碰撞（`collision_engine.py`），即两个角色靠近到 3 格以内才触发叙事级碰撞。这要求角色"主动接近对方"才有意义，纯随机很难触发有意义的接近。
3. **ChapterTimeline 四段式章节**：碰撞引擎按"铺垫 → 主角行动 → 配角入场 → 收尾"的叙事结构分配角色出场。这意味着角色的移动在语义上应有方向性——配角应该"入场"走向主角，而不是随机到处晃。

**总结**：移动逻辑目前三套系统都是纯随机，但 novel_world 的调度层架构已经为"目标导向移动"留好了接口（Goal.target_location、swimlane 中的动作序列、碰撞引擎的接近阈值），Adapter 接入这些调度模块即可获得更好的移动表现。这不是 novel_world 缺少能力，而是 Adapter 还没有把它们连起来。

---

## 总结

| TODO | 核心原因 | 影响程度 | 建议优先级 |
|------|----------|----------|-----------|
| 调度层未接入 | backend 没有等价概念，需要完整架构桥接 | 中：碰撞/目标管理缺失 | 阶段 2 |
| char_type 硬编码 | backend 无此字段，缺乏推断上下文 | 低：不影响运行，影响 NPC 语义 | 阶段 1 收尾 |
| SkillRegistry 空 | 映射逻辑简单但未实现 | 中：技能碰撞叙事缺失 | 阶段 2 |
| 模板降级未用 | 整体仍走 backend AI 管道 | 高：离线能力闲置 | 阶段 1 收尾 |
| 随机移动无逻辑 | 三套系统都是纯随机，非 Adapter 独有 | 中：叙事合理性有损 | 阶段 2 |
*（内容由AI生成，仅供参考）*
