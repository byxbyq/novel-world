---
AIGC:
    Label: "1"
    ContentProducer: 001191440300708461136T1XGW3
    ProduceID: 62a5f052892935463ed1c42751e16e2e_ab905dcd818a11f1bbe75254006c9bbf
    ReservedCode1: IDquJ4f/yrS5KOUk4Ow42BeeWLK1b1vgx3KMpN/Ps9m2OEWbXZ+mUDfipm/XmvYhzYv2hJZCvTXbnNt+sLFAzrjbEGMeDaFK4psVmmrTFOwud0IVlT8hvSr80BKTk7e/NZ28exrwtxQ+ytXyR+AIU/0iE7xBbeX0D4X4y5zlqzSoOUBs9HL6Na0xRKU=
    ContentPropagator: 001191440300708461136T1XGW3
    PropagateID: 62a5f052892935463ed1c42751e16e2e_ab905dcd818a11f1bbe75254006c9bbf
    ReservedCode2: IDquJ4f/yrS5KOUk4Ow42BeeWLK1b1vgx3KMpN/Ps9m2OEWbXZ+mUDfipm/XmvYhzYv2hJZCvTXbnNt+sLFAzrjbEGMeDaFK4psVmmrTFOwud0IVlT8hvSr80BKTk7e/NZ28exrwtxQ+ytXyR+AIU/0iE7xBbeX0D4X4y5zlqzSoOUBs9HL6Na0xRKU=
---

# 小说世界引擎 深层批判验证报告

> 验证日期：2026-07-17
> 方法：逐文件代码扫描 + 交叉对比设计文档
> 宗旨：不美化，代码什么样就说什么样

---

## 批判一验证：底层推演逻辑 — 随机游走优先 vs 目标驱动

### 1.1 Tick 循环执行顺序

**结论：成立**

**证据 A — novel_world/engine/core/engine.py（新引擎核心）**

文件：`H:\小说\小说世界\novel_world\engine\core\engine.py`，第 315 行

```python
def tick(self):
    # 第一步：随机移动
    self._random_move_characters()    # ← 第 315 行，注释："角色随机小范围移动"
    
    # 第二步：叙事生成
    ...
```

`_random_move_characters()` 方法以 15% 概率让每个角色在 ±1 格内随机移动。这个方法**在叙事生成之前**被调用，且角色的目标状态完全不影响移动决策。

**证据 B — backend/engine.py（旧引擎）**

文件：`H:\小说\小说世界\backend\engine.py`，第 156 行起

```python
def run_chapter(self):
    # 1. 天道决定世界事件
    world_event = self.narrative_gen.generate_world_event(...)
    # 2. 每个角色根据目标行动
    # 3. 碰撞引擎处理碰撞
    # 4. 天道生成章节正文
```

旧引擎 `advance_tick()` 方法（约第 120 行）**仅做章节/Tick 计数管理，没有随机移动**。旧引擎的 `run_chapter()` 流程是：世界事件 → 角色行动 → 碰撞 → 生成正文。这比新引擎合理，但两个引擎**没有整合**。

**证据 C — novel_world/engine/novel_engine.py（统一门面）**

文件：`H:\小说\小说世界\novel_world\engine\novel_engine.py`，约第 70-120 行

```python
def advance_tick(self):
    # 1. 推进时间轴
    # 2. 批量推进所有活跃角色目标 GoalScheduler.tick_advance
    # 3. 碰撞检测 CausalCollisionScheduler.detect_at_tick
    # 4. 规则守卫校验
    # 5. 一致性校验
    # 6. 保存状态
```

NovelEngine 的流程更完整（目标推进 → 碰撞 → 校验），但它**不调用 `_random_move_characters()`**。这意味着实际使用的 engine.py 中的 tick() 和 NovelEngine 的 advance_tick() 是**两套不同链路**。

**根本原因**：新引擎的 CoreEngine.tick() 在叙事生成前插入了随机移动步骤，注释明确写"角色随机小范围移动"。这不是设计疏忽，是显式编码的优先级决策。而 NovelEngine 有更好的流程但不走 tick()。

---

### 1.2 碰撞引擎是否以长期目标作为冲突源

**结论：部分成立**

**证据 A — backend/collision.py（旧引擎碰撞，135 行）**

文件：`H:\小说\小说世界\backend\collision.py`，第 16-80 行

```python
def process_collision(self, char_a, char_b, world) -> dict:
    prompt = f"""【碰撞事件】
{char_a.name} 和 {char_b.name} 在「{world.get_character_position(char_a.name)}」相遇了。
...
{char_a.name}的当前状态：
{char_a.full_state_text()}"""
```

旧碰撞引擎判定逻辑极其简单：**两个角色在同一位置 → 触发 AI prompt**。`full_state_text()` 包含角色长期目标描述，但碰撞引擎**没有代码检索角色的长期目标来驱动碰撞类型选择**。碰撞类型（能力对冲/感知对冲/接近碰撞）概念在旧引擎中**完全不存在**。

**证据 B — novel_world/engine/collision/collision_engine.py（新碰撞引擎，1395 行）**

文件：`H:\小说\小说世界\novel_world\engine\collision\collision_engine.py`

新碰撞引擎包含更复杂的设计：

1.  **4 种碰撞类型**：感知对冲（PERCEPTION_CLASH）、目标对冲（GOAL_CLASH）、能力对冲（ABILITY_CLASH）、接近碰撞（PROXIMITY_COLLISION）
2.  **目标对冲检测**：`_OPPOSITE_KEYWORDS` 对照表（第 ~300 行），包含 15 对对立关键词：
    ```python
    _OPPOSITE_KEYWORDS = [
        ("保护", "摧毁"), ("守卫", "进攻"), ("拯救", "毁灭"),
        ("集结", "镇压"), ("推翻", "维持"), ("解放", "奴役"),
        ...
    ]
    ```
    检测角色 `current_goal` / `goal` 字段中的对立关键词来触发目标驱动碰撞。
3.  **EntryMotivation 枚举**包含 `GOAL_DRIVEN`、`FATE_DRIVEN`、`RELATION_DRIVEN`、`ACCIDENT` 四种进入动机。
4.  **接近碰撞**仅在双方都有目标时才触发，但**没有领地/势力影响逻辑**。

**不足**：
-   目标对冲仅基于关键词字符串匹配，不检测目标的语义层级（长期 vs 短期 vs 终极）。
-   双方长期目标对立时，系统**不会主动提升碰撞烈度**——碰撞烈度由碰撞类型决定，而非根据目标对立程度动态调整。
-   接近碰撞的判断逻辑中没有势力领地（faction territory）参与。

**根本原因**：新碰撞引擎做了一半的目标驱动——有 `GOAL_CLASH` 类型和 `_OPPOSITE_KEYWORDS` 对照表，但目标语义理解停留在字符串匹配层，且没有动态烈度调节。

---

### 1.3 地域-资源-角色目标联动

**结论：不成立（已有的部分是设计骨架，缺少执行代码）**

**证据 A — World / Tile / Faction 数据结构**

文件：`H:\小说\小说世界\novel_world\engine\core\world.py`

-   `Tile`（第 24-60 行）：包含 `x, y, tile_type, faction_id, resources（{food, material, energy}）, name, description`
-   `Faction`（第 79-130 行）：包含 `id, name, member_ids, resources, territory, leader_id, goals`
-   `FactionGoal`（第 66-75 行）：`description, progress(0.0~1.0), weight`

**证据 B — 角色有"向目标地点移动"的逻辑吗？**

文件：`H:\小说\小说世界\novel_world\engine\core\character.py`，第 20-45 行

```python
@dataclass
class Character:
    pos: tuple = (0, 0)        # 只有坐标，没有目标地点字段
    goal: str = ""             # 目标描述，纯文本，无位置语义
    faction_id: str = ""       # 势力 ID 字段存在
    state: CharState           # 含 MOVING 状态
```

角色有 `pos` 坐标和 `MOVING` 状态，但**没有 `target_location` 字段**。`_random_move_characters()` 中的移动是完全随机的（±1 格），不读取角色的目标或 faction 领地。

**证据 C — 势力有领地概念，但角色移动不受其影响**

文件：`H:\小说\小说世界\novel_world\engine\core\world.py`，第 176-180 行

```python
def get_tile(self, x, y):
    return self.tiles.get((x, y))

def get_characters_at(self, x, y):
    return [c for c in self.characters if c.pos == (x, y) and c.alive]
```

World 可以查询某位置的字符和 faction_id，但**没有任何方法计算"角色到目标地点的路径"**，也没有"领地范围内移动受限"的逻辑。

**证据 D — 地域资源是否参与碰撞驱动？**

文件：`H:\小说\小说世界\novel_world\engine\collision\collision_engine.py`

在 1395 行的碰撞引擎中，搜索 `resource`、`territory`、`tile`、`terrain`——结果：0 处引用。碰撞判定**不读取 Tile 的资源字段**。

**证据 E — 势力目标对齐机制**

文件：`H:\小说\小说世界\novel_world\engine\core\world.py`，第 247-285 行

```python
def align_faction_goals(self, main_objective: str):
    """根据世界主线目标，为每个势力生成贴合主线的势力目标"""
    for faction in self.factions.values():
        prompt = f"""世界主线目标：{main_objective}
势力名称：{faction.name}
请为该势力生成 1-3 个贴合世界主线目标的势力目标"""
        response = chat(...)  # AI 生成
```

这个方法**存在且正确**——根据主线目标为每个势力生成势力目标。但它是通过 AI prompt 生成文本描述，没有将势力目标转化为可执行的行为参数（如"该势力角色倾向于移动到哪些地块"）。

**根本原因**：数据结构已有骨架（Tile 有资源、Faction 有领地+目标、Character 有 faction_id），但**执行层缺失**——没有路径规划、没有领地约束、没有资源驱动碰撞。`_random_move_characters()` 的存在恰恰证明了"地域-资源-角色目标联动"不是暂时没做，而是被随机移动替代了。

---

## 批判二验证：前置设定约束弱，后置补救工具多

### 2.1 是否存在前置筛选/权重配置

**结论：成立（仅存在最小化的单点机制，无系统性前置约束层）**

**已存在的前置约束**（仅有 2 处）：

**证据 A — Goal 权重机制**

文件：`H:\小说\小说世界\backend\character.py`，第 11 行和第 118-128 行

```python
@dataclass
class Goal:
    description: str
    priority: int = 5
    weight: float = 1.0       # ← 调度权重

def select_primary_goal(self) -> Goal | None:
    """按 weight 加权随机选择当前应推进的目标"""
    active = [...]
    weights = [max(g.weight, 0.01) for g in active]
    return random.choices(active, weights=weights, k=1)[0]
```

`select_primary_goal()` 按权重随机选择目标——这是前置的"目标选择"机制。但**仅此一处**，且权重如何设置是代码内部的（通过 `align_goals_to_main_objective()` 设置），用户无法手动配置。

**证据 B — EngineConfig 终局控制**

文件：`H:\小说\小说世界\backend\engine_config.py`，第 8-19 行

```python
@dataclass
class EngineConfig:
    total_chapters: int = 3
    ticks_per_chapter: int = 20
    auto_pause_between_chapters: bool = True
    end_behavior: str = "auto_epilogue"
    expected_ending: str = ""
```

有章节上限和终局行为配置，但**没有**"只在核心角色中触发碰撞"、"关闭交易闲逛事件"、"锁定冲突类型"等前置约束。

**不存在的前置约束**（列表）：

| 缺失的前置约束 | 当前状态 |
|---|---|
| 核心角色权重配置（用户手动设权重） | 不存在，权重由代码自动计算 |
| 事件类型过滤（如关闭"交易""闲逛"事件） | 不存在，所有事件均由 AI 自由生成 |
| 冲突类型锁定（如只看"战斗"碰撞） | 不存在，碰撞类型由引擎内部决定 |
| 启动前角色筛选（只看前N个角色） | 不存在 |
| 碰撞密度上限（每 Tick 最多 N 次碰撞） | 不存在 |

---

### 2.2 DM / TimelineChecker / PromptRegistry 是否有前置约束能力

**结论：成立（全是设计文档，代码中不存在）**

**证据 A — DM 设计文档是纯设计**

文件：`H:\小说\小说世界\docs\dm_mode_and_timeline_check_design_v2.md`（2346 行）

这是完整的**设计文档**，不是代码。开头写明：
> 设计日期：2026-07-17
> v2 更新：2026-07-17

设计文档中描述的 DM 模式包含：
-   `TimelineChecker`（7 维度检查：角色行踪/因果链/伏笔回收/时间倒流/成长曲线/世界单调性/Prompt合规度）
-   `DMManager`（暂停→查看报告→干预→修改Prompt→恢复→重新检查）
-   `PromptRegistry`（Prompt 模板管理、版本回滚、热重载）

但在代码中搜索 `TimelineChecker`、`DMManager`、`PromptRegistry`——**0 个 .py 文件包含这些类**。全部处于设计阶段。

**证据 B — WorldRuleGuard 是纯事后校验**

文件：`H:\小说\小说世界\novel_world\engine\scheduler\world_rule_guard.py`，第 1-20 行

```python
"""
世界观规则守卫层 - 在叙事输出前校验内容是否符合世界观设定

核心职责：
  1. 检查叙事文本是否包含违反世界观设定的内容
  2. 检查角色行为是否符合其设定
  3. 检查场景描述是否符合世界规则
  4. 提供违规报告和修复建议
"""
```

注意注释原文："在叙事输出**前**校验"——但实际代码实现是：

```python
def check_narrative(self, narrative: str) -> List[GuardViolation]:
    # 对已生成的叙事文本进行关键词匹配
```

这是**事后校验**：AI 已经生成了违规内容，然后 WorldRuleGuard 检查并报告。它不拦截 tick 执行中的行为。

**证据 C — WorldRuleGuard 只有 3 条默认规则**

文件：`H:\小说\小说世界\novel_world\engine\scheduler\world_rule_guard.py`，第 137-150 行

```python
def _init_default_rules(self):
    defaults = [
        WorldRule(id="no_modern_tech", name="禁止现代科技", ...),
        WorldRule(id="no_mixed_lang", name="禁止中英混杂", ...),
        WorldRule(id="no_explicit", name="禁止露骨内容", ...),
    ]
```

仅 3 条默认规则，都是内容过滤（禁词）。用户填写在 WorldConfig.rules 中的规则（如"修为等级：炼气→筑基→金丹→元婴→化神"）**没有被 WorldRuleGuard 解析为可执行的约束规则**——它们只是作为纯文本注入 AI prompt。

**证据 D — HardConstraintController 是硬编码的特定主线校验**

文件：`H:\小说\小说世界\novel_world\engine\quality\hard_constraint_controller.py`

这个 914 行的控制器有大量校验：高频词替换、相似度拦截、场景嵌套检测、配角屏蔽、主线阶段管理等。但仔细阅读发现：

```python
# 硬编码的角色名（第 136 行）
self.mainline_characters = ["陈阳", "苏晚"]

# 硬编码的主线阶段（第 79-101 行）
MAINLINE_STAGES = {
    "stage_1": {"name": "初识/试探", ...},
    "stage_2": {"name": "关系升温", ...},
    "stage_3": {"name": "关系确定/延伸", ...},
}

# 硬编码的配角（第 124 行）
配角_cooldown: Dict[str, int] = {"赵磊": 0, "阿花": 0, "婴儿": 0, "猫": 0}
```

这是为**一个特定的日常恋爱故事**（陈阳×苏晚）硬编码的约束器，不是通用的小说世界引擎约束。角色名、主线阶段、配角名全部硬编码。

**根本原因**：这是典型的"后置补救"设计模式。生成前没有可配置的约束层，生成时依靠 AI prompt 自由发挥，生成后由大量校验模块（HardConstraintController / NarrativeCorrector / WorldRuleGuard / RuleValidator）拦截修正。代码中存在 19+ 个 quality/ 下的校验文件，但没有一个"在 Tick 推演前施加约束"的前置模块。

---

## 批判三验证：分层设定体系 — 模块数据割裂

### 3.1 世界规则是否约束角色行为

**结论：不成立（规则仅以文本形式存在，不参与行为约束）**

**证据 A — WorldConfig.rules 的去向**

文件：`H:\小说\小说世界\backend\config.py`，第 62 行

```python
class WorldConfig:
    rules: list[str] = field(default_factory=list)  # 世界规则

    def to_prompt_text(self) -> str:
        if self.rules:
            parts.append(f"世界规则：{'；'.join(self.rules)}")
```

用户填写的世界规则（如"不可杀人"、"修为等级：炼气→筑基→金丹"）的唯一出路是 `to_prompt_text()`——拼接成字符串注入 AI prompt。没有任何代码将这些规则解析为可拦截角色行为的约束。

**证据 B — WorldRuleGuard 不拦截角色行为**

文件：`H:\小说\小说世界\novel_world\engine\scheduler\world_rule_guard.py`

WorldRuleGuard 的检测对象是**叙事文本**（已生成的文字），不是**角色行为**（角色即将执行的动作）。当角色在 tick 执行中决定"杀人"时，WorldRuleGuard 不参与；它只在叙事文本已经生成后才检查文本中是否包含"杀人"这个词。

**证据 C — 规则到行为的映射完全缺失**

在全部代码中搜索 `rule` 和 `constraint` 的关系：
-   `WorldConfig.rules` → 注入 prompt（纯文本）
-   `WorldRuleGuard._init_default_rules()` → 禁词检测（仅 3 条）
-   没有任何代码将用户规则解析为行为约束条件

---

### 3.2 性格是否影响行动方式

**结论：不成立（性格仅作为 prompt 背景描述，无分支选择逻辑）**

**证据 A — backend/character.py 中的性格使用**

文件：`H:\小说\小说世界\backend\character.py`，第 146-164 行

```python
def full_state_text(self) -> str:
    parts = [
        f"当前心情：{self.current_mood}",
        f"当前位置：{self.current_location or '未知'}",
    ]
    goals = self.active_goals_text()
    ...
```

`full_state_text()` 是生成 AI prompt 的核心方法。注意：这里**没有直接引用 `self.config.personality`**。性格在 `CharacterConfig.to_prompt_text()` 中输出，但 `CharacterAgent` 自身的行为逻辑不读取性格。

**证据 B — novel_world/engine/core/character.py 中的性格**

文件：`H:\小说\小说世界\novel_world\engine\core\character.py`，第 43-48 行

```python
class Character:
    personality: str = ""       # 性格描述
    fate_arc: str = ""          # 命运线/当前处境
    story_state: str = ""       # AI维护的当前状态
```

`personality` 是一个纯字符串字段。在 `generate_random_character()` 中从 `_PERSONALITIES` 词典随机选取一个描述。但**整个代码库中没有任何地方根据性格值进入不同的行动分支**。同样是"复仇"目标：
-   刚烈角色（"勇敢冲动、嫉恶如仇"）和隐忍角色（"冷静智慧、心思细密"）在代码层面**走完全相同的执行路径**。
-   区别仅在于 AI prompt 中多了一行"性格：XXX"，由 AI 自行理解。

**证据 C — 行动生成不读取性格**

搜索全部代码中 `personality` 字段的引用：
-   赋值（初始化、随机生成）
-   序列化/反序列化
-   prompt 文本拼接

没有任何 `if character.personality == "刚烈": do_X() else: do_Y()` 这样的分支逻辑。

---

### 3.3 全局主线锚定配置验证

**结论：部分成立**

**证据 A — WorldConfig 已有主线目标字段**

文件：`H:\小说\小说世界\backend\config.py`，第 79-80 行

```python
main_objective: str = ""       # 世界主线目标
world_stage: str = "opening"   # 叙事阶段：opening/rising/climax/falling/ending
```

**有**。WorldConfig 包含 `main_objective` 和 `world_stage`，且 `advance_world_stage()` 方法按章节进度自动推进阶段。

**证据 B — Goal 权重对齐机制**

文件：`H:\小说\小说世界\backend\engine.py`，约第 260-320 行

```python
def align_goals_to_main_objective(self):
    """根据主线目标调整所有角色目标的权重"""
    for char in self.characters:
        for goal in [...]:
            relevance = self._calc_goal_relevance(goal.description, main_obj)
            goal.weight = relevance  # 与主线越相关权重越高
```

**有**。`align_goals_to_main_objective()` 调整目标权重，使角色优先推进与主线相关的目标。结合 `select_primary_goal()` 按权重随机选择——这是一个**可用但间接**的机制。

**证据 C — 缺失：novel_world 引擎中没有主线锚定**

文件：`H:\小说\小说世界\novel_world\engine\core\character.py`，第 43 行

```python
class Character:
    goal: str = ""    # 纯文本目标，没有 weight 字段
```

NovelWorld 引擎的 Character 类中 **goal 是纯字符串，没有 weight 字段，没有 select_primary_goal 方法，没有 align_goals_to_main_objective**。两个引擎的数据模型不互通。

**根本原因**：backend 引擎做了一部分（WorldConfig.main_objective + Goal.weight + align_goals），但 novel_world 引擎没有。两个引擎的数据模型本身就不一致，全局主线锚定只在 backend 引擎中部分实现。

---

## 批判四验证：产出链路 — 重模拟、轻成文

### 4.1 剧情收拢机制验证

**结论：成立（仅存在 EngineConfig 字段和 AI prompt 引导，无结构性收束）**

**证据 A — max_chapters 到达后的收尾**

文件：`H:\小说\小说世界\backend\engine_config.py`，第 17-19 行

```python
end_behavior: str = "auto_epilogue"  # auto_epilogue / loop_last / infinite
expected_ending: str = ""            # 预期结局描述
```

EngineConfig 有 `end_behavior` 和 `expected_ending` 两个控制字段。在 `backend/engine.py` 的 `_finalize_novel()` 方法中，到达 `total_chapters` 后会调用 AI 生成尾声。但这是**一次 AI prompt 调用的收尾**，不是结构性的：

-   是否回收了所有伏笔？——没有伏笔数据模型，无法检查。
-   是否给所有角色的长期目标一个结局？——没有遍历角色目标的代码。
-   是否生成势力结局？——没有。
-   是否有结构化的"结局检查单"？——没有。

**证据 B — HardConstraintController 的主线收尾**

文件：`H:\小说\小说世界\novel_world\engine\quality\hard_constraint_controller.py`，约第 262-290 行

```python
def check_mainline_ending(self, narrative: str):
    completion_keywords = ["确定关系", "在一起", "成为恋人", "确定恋爱关系"]
    if any(kw in narrative for kw in completion_keywords):
        self.state.mainline_completed = True
        self.state.mainline_ending_triggered = True
    
    if self.state.mainline_completed:
        self.state.mainline_ending_narrative_count += 1
        if self.state.mainline_ending_narrative_count > self.state.mainline_ending_max:
            return (True, "", "主线收尾已完成，停止生成")
```

这是唯一的结构化收尾机制，但它是为**特定恋爱主线**硬编码的（"确定关系"、"在一起"等关键词），且 `mainline_ending_max = 2` 意味着收尾最多 2 条叙事后就强制停止。

**不存在**：
-   伏笔回收闭环检测
-   角色目标收束（逐个检查角色的目标完成状态）
-   势力结局生成
-   多线程叙事收束

---

### 4.2 叙事质量管控验证

**结论：成立（质量管控停留在句式修正+去重+禁词拦截，无线上的叙事管控）**

**证据 A — 19 个 quality/ 模块的功能清单**

路径：`H:\小说\小说世界\novel_world\engine\quality\`

| 模块 | 实际功能 | 层级 |
|---|---|---|
| `hard_constraint_controller.py` (914行) | 高频词替换、相似度拦截、空洞句式检测、场景嵌套校验、配角屏蔽、主线收尾 | 句式+结构 |
| `narrative_corrector.py` (552行) | 事件去重、角色约束（OOC检测）、世界观过滤、剧情结构检查 | 去重+角色 |
| `rule_validator.py` (466行) | 无名NPC检测、反派OOC、主角焦点、事件重复、路人死亡结尾、道具使用 | 角色+事件 |
| `narrative_dedup.py` | 事件去重器 | 去重 |
| `narrative_enhancer.py` | — | — |
| `narrative_quality_controller.py` | 片段去重/时间排序/视角控制 | 去重+排序 |
| `narrative_state_manager.py` | — | — |
| `narrative_structure.py` | — | — |
| `narrative_cache.py` | — | — |
| `pace_controller.py` (42行) | 碰撞概率乘数调节（slow/normal/fast/intense） | 节奏 |
| `plot_brancher.py` | — | — |
| `plot_nodes.py` | — | — |
| `scene_variator.py` | — | — |
| `scene_params.py` | — | — |
| `character_params.py` | — | — |
| `event_memory.py` | — | — |
| `relationship_tracker.py` | — | — |
| `action_expander.py` | — | — |
| `global_consistency_manager.py` | — | — |

**核心发现**：名称听起来涵盖叙事管控的模块（`plot_nodes`、`plot_brancher`、`narrative_structure`、`narrative_enhancer`）大多是**骨架/占位**代码。真正有实质校验逻辑的只有 4 个：

1.  **hard_constraint_controller.py** — 但硬编码为特定恋爱故事
2.  **narrative_corrector.py** — 但功能是去重+禁词+OOC检测
3.  **rule_validator.py** — 但校验项是"无名NPC""路人死亡"
4.  **pace_controller.py** — 仅 42 行，只做概率乘法

**缺失的叙事管控**：
-   **章节节奏调控**：无。pace_controller 只调碰撞概率，不调叙事节奏（如"本章应有 3 个高潮点"）。
-   **主次剧情区分**：无。所有事件在 AI 生成时没有优先级差异。
-   **支线压缩**：无。AI 生成了什么就是什么，没有自动识别并压缩偏离主线的支线。
-   **高潮/低谷节奏曲线**：无。HardConstraintController 有"主线阶段"概念但只是标签，不驱动叙事节奏。

---

### 4.3 批量编辑工具验证

**结论：成立（Web 界面仅支持逐个手动输入，无批量编辑能力）**

**证据 A — 前端角色输入**

文件：`H:\小说\小说世界\frontend\app.js`，第 23-88 行

```javascript
function addCharacter() {
  // 每次调用添加一个角色卡片
  // 每个卡片包含：姓名/性别/年龄/性格/背景/外貌/长期目标/短期目标/能力/弱点/位置
}
```

每个角色是一个独立的 HTML 表单卡片，**逐个手动输入**。没有：
-   批量导入（CSV/JSON/文本）
-   批量编辑角色目标（如"所有反派增加一个目标"）
-   批量编辑势力诉求
-   批量编辑地域资源

**证据 B — Web 界面各 Tab**

文件：`H:\小说\小说世界\frontend\index.html`

3 个 Tab：
1.  **世界设定** — 单一表单，手动输入
2.  **角色设定** — 逐个添加角色卡片
3.  **确认启动** — 预览 + API Key 输入 + 启动按钮

游戏主界面（第 139-175 行）：
-   左侧：章节列表 + 世界事件（只读）
-   中间：章节正文 + 手动输入标题 + 下一章按钮
-   右侧：角色状态（只读）

**没有**批量编辑面板。

**证据 C — API 层**

`frontend/app.js` 中 `initGame()` 函数发送的 payload 结构：
```javascript
const payload = {
    world: { name, genre, era, description, rules, key_locations, current_situation, tone },
    characters: chars  // 逐个收集的表单数据
};
```

API 只有一个 `/api/init` 端点（初始化游戏）和 `/api/save-key`（保存 API Key）。**没有**批量编辑的 API 端点。

---

## 总结：按致命程度排序的底层问题

### 致命级（必须优先修复 — 引擎架构缺陷）

| 优先级 | 问题 | 批判编号 | 影响 |
|---|---|---|---|
| **P0** | **Tick 循环中随机移动在目标行为之前执行** | 批判一 1.1 | 角色每 Tick 有 15% 概率随机移动，且这在目标行为处理之前。这意味着无论用户设定了多么精细的角色目标，引擎的第一步永远是"先随机走一步"。破坏了所有目标驱动的叙事逻辑。 |
| **P0** | **两个引擎未整合，数据模型不一致** | 批判三 3.3 | backend/engine.py 有 Goal.weight + align_goals_to_main_objective，novel_world/engine/core/engine.py 没有。两个引擎共享同一个项目但互不通信。Goal 在一个引擎是带权重的对象，在另一个引擎是纯字符串。 |
| **P0** | **HardConstraintController 硬编码为特定故事** | 批判二 2.2 | 914 行的"硬约束控制器"只能用于一个特定的陈阳×苏晚恋爱故事。角色名、主线阶段、配角名全部硬编码。换了世界设定就完全无效。 |

### 严重级（影响叙事质量的核心缺失）

| 优先级 | 问题 | 批判编号 | 影响 |
|---|---|---|---|
| **P1** | **无前置约束层——全部是事后补救** | 批判二 2.1/2.2 | 用户无法配置"只看核心角色""关闭闲逛事件""锁定冲突类型"。所有约束靠 AI prompt 中的文本描述，然后靠 19 个 quality/ 模块事后拦截。生成成本高、效果不稳定。 |
| **P1** | **DM/TimelineChecker/PromptRegistry 仅存在于设计文档** | 批判二 2.2 | 2346 行的 v2 设计文档描述了完整的时间线检查和 DM 干预体系，但代码中 0 个类实现。DM 模式目前是纯概念。 |
| **P1** | **性格不影响行动分支** | 批判三 3.2 | "刚烈角色复仇"和"隐忍角色复仇"在代码中走相同的执行路径，区别仅在于 AI prompt 中多一行"性格：XXX"。性格是背景描述，不是分支条件。 |
| **P1** | **世界规则仅以文本形式存在，不参与行为约束** | 批判三 3.1 | 用户填写的"不可杀人"规则没有被解析为可执行的约束，只是注入 prompt 的一行文字。WorldRuleGuard 仅事后检查叙事文本中是否出现"杀"字。 |

### 重要级（影响用户体验和作品完整度）

| 优先级 | 问题 | 批判编号 | 影响 |
|---|---|---|---|
| **P2** | **地域-资源-角色目标无联动** | 批判一 3 | Tile 有资源、Faction 有领地、Character 有 faction_id——数据骨架完整，但执行层缺失。角色移动是随机的，碰撞驱动不读资源，没有路径规划。 |
| **P2** | **无结构性剧情收束** | 批判四 4.1 | max_chapters 到达后只做一次 AI prompt 调用生成尾声，没有伏笔回收检查、没有角色目标逐一收束、没有势力结局。 |
| **P2** | **质量管控停留在句式修正层** | 批判四 4.2 | 19 个 quality/ 模块中仅有 4 个有实质逻辑，且功能都是去重/禁词/OOC/高频词替换。缺少章节节奏调控、主次剧情区分、支线压缩。 |
| **P2** | **Web 界面无批量编辑能力** | 批判四 4.3 | 所有设定按角色逐个手动输入，无批量导入/导出，无批量目标编辑，无势力资源批量配置界面。 |
| **P2** | **碰撞引擎的目标驱动停留在关键词匹配** | 批判一 1.2 | 目标对冲使用 15 对 `_OPPOSITE_KEYWORDS` 做字符串匹配，不检测目标的语义层级，不根据目标对立程度动态调整碰撞烈度。 |

### 设计债务（不致命但拖累迭代速度）

| 问题 | 批判编号 |
|---|---|
| 两个引擎并行开发，backend.py 和 novel_world/ 互不整合 | 批判一/三 |
| `novel_world/engine/core/engine.py` 的 `tick()` 和 `novel_world/engine/novel_engine.py` 的 `advance_tick()` 是两套不同链路 | 批判一 1.1 |
| 设计文档（docs/）和代码之间差距巨大，v2 设计文档中的 80% 模块未实现 | 批判二 2.2 |
| 19 个 quality/ 文件中有 ~15 个是骨架代码，实际功能空 | 批判四 4.2 |
| `backend/collision.py`（135行）和 `novel_world/collision/collision_engine.py`（1395行）是两套完全不同的碰撞实现 | 批判一 1.2 |

---

## 最终评价

批判用户对小说世界引擎的四个深层批判**基本全部成立**。引擎的核心问题可以总结为一句话：

> **"重模拟轻成文"**——引擎把大量精力投入到碰撞引擎、GoalScheduler、质量校验模块（19 个文件！）等"模拟基础设施"，但底层驱动逻辑是随机游走先行，前置约束缺失，模块数据割裂，最终产出缺少结构性收束。这些不是"暂时没做"的功能——`_random_move_characters()` 是刻意编码在 tick() 第一步的，HardConstraintController 是特意为单一故事硬编码的——它们是**架构决策的结果**。

最优先需要修复的是 P0 级三项：移除 Tick 循环中的随机游走优先逻辑、统一两个引擎的数据模型、将 HardConstraintController 泛化为通用约束器。这三项不修，加多少 quality/ 模块都是治标不治本。
*（内容由AI生成，仅供参考）*
