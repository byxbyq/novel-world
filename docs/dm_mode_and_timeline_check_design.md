# 时间线检查功能 & 实时 DM 模式 - 完整设计方案

> 设计日期：2026-07-17  
> 参考项目：书斋V65 检查机制  
> 目标项目：小说世界 (H:\小说\小说世界\)

---

## 目录

1. [书斋检查机制解读](#1-书斋检查机制解读)
2. [功能一：时间线检查功能](#2-功能一时间线检查功能)
3. [功能二：实时 DM 模式](#3-功能二实时-dm-模式)
4. [两功能联动设计](#4-两功能联动设计)
5. [实施路线图](#5-实施路线图)

---

## 1. 书斋检查机制解读

### 1.1 核心理念

书斋的检查机制遵循一个核心原则：**防止 AI 胡编乱造**。每当 AI 生成内容后，系统会从三个维度进行审查：内容质量、跨模块一致性、世界观合规。三道防线由轻到重，层层拦截。

### 1.2 三层架构

```
┌─────────────────────────────────────────────────┐
│                 API 路由层 (validate.py)          │
│  /api/validate/all  /api/validate/batch          │
│  /api/validate/consistency  /api/validate/ai-flavor │
└────────────────────┬────────────────────────────┘
                     │
    ┌────────────────┼────────────────┐
    ▼                ▼                ▼
┌────────┐   ┌──────────────┐   ┌──────────────┐
│ audit  │   │ consistency  │   │ world_rule   │
│  .py   │   │  _checker.py │   │  _guard.py   │
├────────┤   ├──────────────┤   ├──────────────┤
│规则驱动│   │跨模块数据对齐│   │规则守卫      │
│零Token │   │ERROR/WARN/   │   │Block/Warn/   │
│        │   │INFO 三级     │   │Info 三级     │
└────────┘   └──────────────┘   └──────────────┘
```

### 1.3 三类检查详解

#### A. 内容质量审计 (audit.py)

| 检查项 | 触发 | 方法 | 输出 |
|--------|------|------|------|
| AI味检测 | 手动/生成后 | 统计特征(句子突发性/词汇多样性/段落均匀性/句式重复度) + 规则匹配(Buzzword词表/公式化句式/7Gate规则) | score(0-100) + level + ai_probability + issues[] |
| 战力崩坏检测 | 手动 | 基于TruthLedger校验：境界跳跃/死亡复活/越级战胜 | 结构化违规列表 |
| 文风指纹 | 手动 | 提取句长/TTR/修辞/对话密度指纹 → 计算偏离度 | style_fingerprint + deviation |
| 综合审计 | 手动 | AI味(40%) + 战力(35%) + 伏笔逾期(25%) 加权 | 总评分 |

#### B. 跨模块一致性校验 (consistency_checker.py)

| 检查维度 | 对齐对象 | 严重级别 |
|----------|----------|----------|
| 角色状态对齐 | TruthLedger.lifecycle_stage ↔ SwimlaneManager.lifecycle | ERROR |
| 时间线角色对齐 | WorldTimeline.active_characters ↔ SwimlaneManager | ERROR |
| 目标-生命周期 | GoalScheduler.status ↔ 角色生死状态 | ERROR |
| 伏笔时间线 | 回收时间 ≥ 埋设时间 | WARNING |
| 时间线倒流 | 更晚章节角色出现在更早tick | ERROR |

#### C. 世界观规则守卫 (world_rule_guard.py)

| 规则类型 | 示例 | 动作 |
|----------|------|------|
| forbidden_word | 禁止"现代科技"出现在玄幻场景 | Block + 替换 |
| character_boundary | 某角色不能说特定句式 | Block |
| scene_rule | 特定场景禁止某种行为 | Warn/Block |

### 1.4 对小说世界的启示

书斋检查机制的设计哲学可以迁移到小说世界：

| 书斋概念 | 小说世界对应物 | 迁移方式 |
|----------|---------------|----------|
| AI味检测（统计+规则） | 叙事质量检测（重复/NPC抢戏/节奏崩坏） | 规则检测层，零Token |
| 战力崩坏 | 角色能力一致性（境界/技能/战力） | 基于TruthLedger的跨tick校验 |
| 文风指纹 | 叙事风格一致性 | 可选扩展 |
| 跨模块一致性 | **已有** ConsistencyChecker | 扩充时间线专项检查 |
| 世界观规则守卫 | **已有** WorldRuleGuard | 增强为可配置断点 |
| /api/validate/all | 单次全维度检查API | 新增所有检查入口 |

---

## 2. 功能一：时间线检查功能

### 2.1 设计目标

**核心原则：防止AI生成的叙事在时间维度上出现矛盾。** 确保小说的因果关系、角色行踪、事件先后顺序、伏笔回收等时间敏感内容保持逻辑自洽。

### 2.2 检查什么（检查维度矩阵）

#### 维度一：角色行踪一致性 (Character Trail)

```
检查对象：每个角色的 {tick → 位置} 映射
检查逻辑：
  - 同一角色在同一tick不能出现在两个不同位置
  - 连续tick之间位置迁移必须合理（不能瞬移，除非有传送设定）
  - 角色死亡后不应在任何后续tick作为"出现"的角色
数据来源：WorldTimeline.active_characters × SwimlaneManager × TruthLedger
```

#### 维度二：因果链完整性 (Causal Chain)

```
检查对象：事件与事件之间的因果关系
检查逻辑：
  - 每个"结果"事件必须有至少一个"原因"事件在之前的tick
  - 如果某个事件被标记为某个角色的"动机来源"，该事件必须存在
  - 结局事件不应在关键前置事件之前出现
数据来源：CausalCollisionScheduler 的碰撞记录 + SixAxisGraph 因果边
```

#### 维度三：伏笔-回收闭环 (Foreshadowing Loop)

```
检查对象：所有已埋设伏笔是否在合理时间内回收
检查逻辑：
  - 伏笔回收 tick > 埋设 tick（绝对硬约束）
  - 长期未回收伏笔（超过设定阈值，如50 tick）→ WARNING
  - 回收时内容与埋设时的暗示是否一致（需AI辅助）
  - 已标记为"回收"的伏笔不能再被引用为"未回收"状态
数据来源：TruthLedger.clues + 碰撞日志
```

#### 维度四：时间线倒流检测 (Timeline Backflow)

```
检查对象：tick 序列中的时间标记
检查逻辑：
  - time_marker（如 morning/noon/evening/night）必须单调递增
  - 如果使用"第N天"的标记，天数不能回退
  - 跨章节时，后一章的起始 tick 对应的绝对时间不能早于前一章结束
数据来源：WorldTimeline.tick 的 time_marker + chapter 字段
```

#### 维度五：角色成长/衰退一致性 (Progression Curve)

```
检查对象：角色的能力值/境界/关系值变化趋势
检查逻辑：
  - 境界不能跳跃（炼气→元婴 中间必须经过筑基、金丹）
  - 能力值突然大幅变化需要关联事件解释（检查碰撞日志）
  - 关系值突变（好感+50 → 好感-80）需要对应事件
  - 死亡角色在后续tick不应有属性变更
数据来源：TruthLedger.character_states + SixAxisGraph 边权重
```

#### 维度六：世界状态单调性 (World State Monotonicity)

```
检查对象：不可逆的世界状态变更
检查逻辑：
  - 标记为"已毁灭"的地点不能再次作为场景
  - 标记为"已死亡"的角色不能再次行动
  - 消耗性道具不能反复使用（除非有补充记录）
  - 世界规则的变更必须有"规则变更事件"对应
数据来源：WorldState + ItemManager + TruthLedger
```

### 2.3 触发时机

| 触发方式 | 触发点 | 检查粒度 | 适用场景 |
|----------|--------|----------|----------|
| **Tick后自动** | 每次advance_tick()结束 | 增量（仅当前tick相关） | 默认模式，实时守护 |
| **碰撞后自动** | detect_at_tick()产生碰撞后 | 增量（仅碰撞相关角色/事件） | 碰撞密度高时 |
| **章节末自动** | 每章最后一tick | 全量（本章范围） | 章节输出前的最终把关 |
| **手动触发** | API调用 | 全量/指定范围 | 作者审查、调试 |

#### 触发节奏建议

```
Tick后自动： 快速规则检查（100ms内），只检查硬约束（角色行踪/时间线倒流/世界状态单调性）
碰撞后自动： 中等规则检查（300ms内），检查因果链/伏笔回收/角色成长
章节末自动： 全量+AI辅助（可耗时长），检查所有维度 + 生成总结报告
手动触发：   全量检查，可指定维度
```

### 2.4 检查粒度与方式

#### 检查执行架构

```
TimelineChecker (新模块)
├── FastCheck   (零Token规则检查，<100ms)
│   ├── character_trail (角色行踪)
│   ├── timeline_backflow (时间线倒流)
│   └── world_monotonicity (世界状态单调性)
│
├── DeepCheck   (规则+数据检查，<500ms)
│   ├── causal_chain (因果链)
│   ├── foreshadowing_loop (伏笔回收)
│   └── progression_curve (成长曲线)
│
└── AIAssistedCheck (AI辅助，耗时长)
    ├── plot_contradiction (情节矛盾，需AI理解语义)
    ├── characterization_drift (角色性格漂移)
    └── narrative_coherence (叙事连贯性)
```

#### 问题严重级别

```python
class TimelineIssueLevel(Enum):
    BLOCKER = "blocker"   # 硬错误，必须修正后才能继续（如：死人在活动）
    ERROR = "error"       # 严重矛盾，强烈建议修正（如：时间线倒流）
    WARNING = "warning"   # 潜在问题（如：伏笔超期未回收）
    INFO = "info"         # 提示信息（如：角色已连续N tick未出现）
```

### 2.5 输出形式

#### API 格式

```json
{
  "check_id": "tl_20260717_001",
  "timestamp": 1752710000,
  "scope": "chapter_3",
  "trigger": "chapter_end",
  "summary": {
    "total_issues": 5,
    "blocker": 0,
    "error": 2,
    "warning": 2,
    "info": 1,
    "passed": true
  },
  "dimensions": {
    "character_trail": {
      "status": "pass",
      "issues": []
    },
    "causal_chain": {
      "status": "warning",
      "issues": [...]
    },
    ...
  },
  "issues": [
    {
      "id": "iss_001",
      "level": "error",
      "dimension": "timeline_backflow",
      "message": "第 47 tick 时间标记为 'evening'，但第 48 tick 回退到 'morning'",
      "detail": {
        "tick_47": {"time_marker": "evening", "chapter": 3},
        "tick_48": {"time_marker": "morning", "chapter": 3}
      },
      "suggestion": "将第 48 tick 的 time_marker 改为 'night' 或 'next_morning'",
      "related_characters": [],
      "related_ticks": [47, 48]
    }
  ]
}
```

#### Web 前端展示

时间线检查结果在前端以**时间线可视化面板**呈现：

```
┌─────────────────────────────────────────────────────┐
│  ⏱ 时间线检查报告 - 第3章              [展开全部]   │
├─────────────────────────────────────────────────────┤
│  ✅ 角色行踪一致性    0 issues                       │
│  ⚠️ 因果链完整性      2 issues    [展开]            │
│  ❌ 时间线倒流         1 issue     [展开]            │
│      tick 47→48 时间回退: evening → morning         │
│      → 建议改为 'night'                             │
│  ✅ 伏笔回收           0 issues                      │
│  ⚠️ 角色成长曲线      1 issue     [展开]            │
└─────────────────────────────────────────────────────┘
```

### 2.6 技术实现要点

#### 2.6.1 模块位置

```
novel_world/engine/quality/timeline_checker.py   (新模块，预计 ~500行)
novel_world/engine/scheduler/consistency_checker.py  (扩充 timeline 检查维度)
```

#### 2.6.2 核心代码骨架

```python
# timeline_checker.py

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Set
from novel_world.engine.scheduler.world_timeline import WorldTimeline, Tick
from novel_world.engine.scheduler.swimlane_manager import SwimlaneManager
from novel_world.engine.memory.truth_ledger import TruthLedger

class TimelineIssueLevel(Enum):
    BLOCKER = "blocker"
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"

@dataclass
class TimelineIssue:
    level: TimelineIssueLevel
    dimension: str
    message: str
    detail: dict = field(default_factory=dict)
    suggestion: str = ""
    related_characters: List[str] = field(default_factory=list)
    related_ticks: List[int] = field(default_factory=list)

class TimelineChecker:
    """时间线检查器 - 专注于时间维度的数据一致性"""

    def __init__(self):
        self.timeline: Optional[WorldTimeline] = None
        self.swimlanes: Optional[SwimlaneManager] = None
        self.truth_ledger: Optional[TruthLedger] = None
        self.goal_scheduler = None
        self.collision_scheduler = None
        self.graph = None

    # ── 快速检查（Tick后自动，<100ms） ──

    def fast_check(self, tick_range: tuple = None) -> List[TimelineIssue]:
        """快速规则检查：角色行踪 + 时间线倒流 + 世界状态单调性"""
        issues = []
        issues.extend(self.check_character_trail(tick_range))
        issues.extend(self.check_timeline_backflow(tick_range))
        issues.extend(self.check_world_monotonicity(tick_range))
        return issues

    # ── 深度检查（碰撞后/章节末，<500ms） ──

    def deep_check(self, tick_range: tuple = None) -> List[TimelineIssue]:
        """深度规则检查：因果链 + 伏笔回收 + 成长曲线"""
        issues = self.fast_check(tick_range)
        issues.extend(self.check_causal_chain(tick_range))
        issues.extend(self.check_foreshadowing_loop(tick_range))
        issues.extend(self.check_progression_curve(tick_range))
        return issues

    # ── 全量检查（章节末/手动，含AI辅助） ──

    def full_check(self, tick_range: tuple = None,
                   with_ai: bool = True) -> List[TimelineIssue]:
        """全量检查，可选AI辅助"""
        issues = self.deep_check(tick_range)
        if with_ai:
            issues.extend(self.ai_assisted_check(tick_range))
        return issues

    # ── 各维度检查方法 ──

    def check_character_trail(self, tick_range=None) -> List[TimelineIssue]:
        """角色行踪一致性检查"""
        issues = []
        # 1. 收集所有角色的 {tick: [位置]}
        # 2. 检查同一tick多位置
        # 3. 检查连续tick位置迁移合理性
        # 4. 检查死亡角色出现
        return issues

    def check_timeline_backflow(self, tick_range=None) -> List[TimelineIssue]:
        """时间线倒流检测"""
        issues = []
        # 1. 遍历 tick 序列
        # 2. 检查 time_marker 单调性
        # 3. 检查绝对时间（如 day_count）不回退
        return issues

    def check_causal_chain(self, tick_range=None) -> List[TimelineIssue]:
        """因果链完整性检查"""
        # 遍历碰撞记录，确保每个"结果"有对应"原因"
        pass

    def check_foreshadowing_loop(self, tick_range=None) -> List[TimelineIssue]:
        """伏笔回收闭环检查"""
        # 检查回收tick > 埋设tick，超期警告
        pass

    def check_progression_curve(self, tick_range=None) -> List[TimelineIssue]:
        """角色成长/衰退一致性"""
        # 检查境界跳跃、能力值突变、关系值突变
        pass

    def check_world_monotonicity(self, tick_range=None) -> List[TimelineIssue]:
        """世界状态单调性检查"""
        # 检查已毁灭地点、已死亡角色、消耗品使用
        pass

    def ai_assisted_check(self, tick_range=None) -> List[TimelineIssue]:
        """AI辅助检查：情节矛盾、角色性格漂移、叙事连贯性"""
        # 调用 AI 分析连续 tick 的叙事摘要
        # 检查情节是否前后矛盾（如前面说某人是孤儿，后面突然出现父母）
        pass
```

#### 2.6.3 与现有系统的集成

在 `NovelEngine.advance_tick()` 中增加检查调用：

```python
def advance_tick(self, ...) -> TickResult:
    # ... 现有流程（推进时间轴/目标/碰撞/规则守卫/一致性）...

    # ── 新增：时间线检查 ──
    if self.timeline_checker:
        # Tick后快速检查（硬约束）
        fast_issues = self.timeline_checker.fast_check(
            tick_range=(current.tick_id, current.tick_id)
        )
        result.timeline_issues = fast_issues

        # 如果上一tick是章节末 → 全量检查
        if self._is_chapter_end(current):
            full_issues = self.timeline_checker.full_check(
                tick_range=(self._chapter_start_tick, current.tick_id)
            )
            result.timeline_issues = full_issues

    return result
```

#### 2.6.4 数据来源映射

| 检查维度 | 依赖数据 | 当前状态 |
|----------|----------|----------|
| 角色行踪 | WorldTimeline.active_characters + TruthLedger.char_states | 数据就绪 |
| 因果链 | collision_engine碰撞记录 + SixAxisGraph | 数据就绪 |
| 伏笔回收 | TruthLedger.clues + WorldTimeline | 需要标记埋设/回收字段 |
| 时间线倒流 | WorldTimeline.time_marker | 数据就绪 |
| 成长曲线 | TruthLedger.char_states + SkillRegistry | 数据就绪 |
| 世界单调性 | WorldState + TruthLedger | 数据就绪 |

---

## 3. 功能二：实时 DM 模式

### 3.1 设计目标

让作者/操作者像 TRPG 的 DM（地下城主）一样，在小说世界的自动化叙事运行过程中拥有**实时干预能力**。可以随时暂停、查看状态、注入事件、调整参数，然后恢复运行。

### 3.2 整体架构

```
┌─────────────────────────────────────────────────────┐
│                    Web 前端                          │
│  ┌──────────┐  ┌──────────┐  ┌───────────────────┐ │
│  │ 叙事面板 │  │ 状态面板 │  │   DM 面板 (新增)   │ │
│  │          │  │          │  │ ┌─────────────────┐│ │
│  │ 章节正文 │  │ 角色列表 │  │ │ 运行控制        ││ │
│  │ 世界事件 │  │ 状态数值 │  │ │ [▶暂停] [⏭步进] ││ │
│  │          │  │          │  │ │ 速度: [1x] [2x]  ││ │
│  │          │  │          │  │ ├─────────────────┤│ │
│  │          │  │          │  │ │ 断点配置        ││ │
│  │          │  │          │  │ │ ☑ Tick=50       ││ │
│  │          │  │          │  │ │ ☐ 碰撞:战斗     ││ │
│  │          │  │          │  │ │ ☐ 自定义条件    ││ │
│  │          │  │          │  │ ├─────────────────┤│ │
│  │          │  │          │  │ │ 干预面板        ││ │
│  │          │  │          │  │ │ [注入事件]      ││ │
│  │          │  │          │  │ │ [修改角色]      ││ │
│  │          │  │          │  │ │ [强制行动]      ││ │
│  │          │  │          │  │ │ [增减角色]      ││ │
│  │          │  │          │  │ │ [调整世界观]    ││ │
│  │          │  │          │  │ ├─────────────────┤│ │
│  │          │  │          │  │ │ 检查联动        ││ │
│  │          │  │          │  │ │ [运行时间线检查] ││ │
│  │          │  │          │  │ │ 上次: ✅通过     ││ │
│  │          │  │          │  │ └─────────────────┘│ │
│  └──────────┘  └──────────┘  └───────────────────┘ │
└──────────────────────┬──────────────────────────────┘
                       │ WebSocket
┌──────────────────────┴──────────────────────────────┐
│                  后端 (Flask)                        │
│  ┌──────────────────┐  ┌──────────────────────────┐ │
│  │ /api/dm/*        │  │ DMManager (新模块)       │ │
│  │ - /pause         │  │ - 运行状态机             │ │
│  │ - /resume        │  │ - 断点管理器             │ │
│  │ - /step          │  │ - 干预队列               │ │
│  │ - /inject_event  │  │ - 干预历史               │ │
│  │ - /modify_char   │  │ - 撤销/重做              │ │
│  │ - /force_action  │  │                          │ │
│  │ - /add_char      │  │                          │ │
│  │ - /remove_char   │  │                          │ │
│  │ - /adjust_world  │  │                          │ │
│  │ - /set_breakpoint│  │                          │ │
│  └──────────────────┘  └──────────────────────────┘ │
└─────────────────────────────────────────────────────┘
```

### 3.3 暂停机制

#### 3.3.1 状态机

```
                 ┌──────────┐
        init()   │  IDLE    │  stop()
    ───────────▶ │ (未运行)  │ ◀────────
                 └─────┬────┘
                       │ start()
                       ▼
                 ┌──────────┐        pause()
                 │ RUNNING  │ ──────────────────┐
                 │ (运行中)  │                    │
                 └─────┬────┘                    ▼
                       │                   ┌──────────┐
                       │ tick_end          │ PAUSED   │
                       │ (自然tick结束)    │ (已暂停)  │
                       └──────────────────▶│          │
                                           └─────┬────┘
                                                 │
                          ┌──────────────────────┼──────────────────┐
                          │ resume()             │ step_once()      │ abort()
                          ▼                      ▼                  ▼
                    ┌──────────┐          ┌───────────┐     ┌──────────┐
                    │ RUNNING  │          │STEPPING   │     │  IDLE    │
                    │ (继续)   │          │(单步执行) │     │ (终止)   │
                    └──────────┘          └─────┬─────┘     └──────────┘
                                                │ done
                                                ▼
                                          ┌──────────┐
                                          │ PAUSED   │
                                          └──────────┘
```

#### 3.3.2 暂停触发条件

| 触发类型 | 条件 | 实现方式 |
|----------|------|----------|
| **Tick 计数断点** | 当前 tick_id == N | 每次 advance_tick 后检查 |
| **碰撞类型断点** | 碰撞类型匹配（战斗/对话/事件） | 碰撞检测后检查 |
| **角色状态断点** | 角色到达某位置/境界/状态 | tick 结束后检查 |
| **自定义条件断点** | Python 表达式求值 | 沙箱化 eval，限制可用变量 |
| **时间线检查阻断** | 检查发现 BLOCKER 级别问题 | 自动暂停 |
| **手动暂停** | 用户点击暂停按钮 | WebSocket 消息 → 设置标志位 |

#### 3.3.3 断点配置数据结构

```python
@dataclass
class Breakpoint:
    id: str
    type: str  # "tick" | "collision" | "character" | "custom" | "check_blocker"
    condition: str  # 条件表达式
    enabled: bool = True
    one_shot: bool = False  # 触发一次后自动禁用
    hit_count: int = 0

# 示例
Breakpoint(id="bp_001", type="tick", condition="50", one_shot=True)
Breakpoint(id="bp_002", type="collision", condition="type=='combat'")
Breakpoint(id="bp_003", type="character", condition="name=='叶辰' and realm=='金丹期'")
Breakpoint(id="bp_004", type="custom", condition="len(engine.goals.get_active_goals()) > 20")
```

### 3.4 干预能力

暂停状态下，DM 可执行以下干预操作。所有干预都会记录到干预历史中，支持撤销。

#### 3.4.1 注入事件 (Inject Event)

```python
@dataclass
class InjectedEvent:
    """注入的事件"""
    id: str
    tick: int
    event_type: str  # "plot_twist" | "encounter" | "disaster" | "revelation" | "misc"
    description: str  # 事件描述（将传递给AI生成叙事）
    target_characters: List[str]
    target_location: str = ""
    priority: int = 5  # 1-10，决定与正常碰撞事件的优先级
    affect_goals: bool = False  # 是否影响角色目标

# API: POST /api/dm/inject_event
{
    "event_type": "plot_twist",
    "description": "叶辰在秘境深处发现了一本上古剑诀残卷",
    "target_characters": ["叶辰"],
    "target_location": "远古秘境",
    "priority": 7
}
```

#### 3.4.2 修改角色属性 (Modify Character)

可修改的属性：
- 基本属性：姓名、性格描述、背景故事
- 状态属性：境界/等级、位置、生命状态（alive/dead/sealed）
- 关系值：六轴图权重（好感度/上下级/亲疏等）
- 目标：增减角色目标、强制完成/放弃目标
- 技能：增减技能、修改技能等级
- 物品：增减物品

```python
# API: POST /api/dm/modify_char
{
    "character": "叶辰",
    "modifications": {
        "realm": "元婴期",           # 境界提升
        "location": "天元古城",      # 位置变更
        "relations": {
            "林婉儿": {"fb": 85}     # 好感度改为85
        },
        "add_abilities": ["御剑术·大成"],
        "add_items": ["上古剑诀残卷"]
    }
}
```

#### 3.4.3 强制行动 (Force Action)

让某个角色在下一次 tick 执行特定行动，覆盖他原本的 AI 目标。

```python
# API: POST /api/dm/force_action
{
    "character": "叶辰",
    "action": "去天机阁查询上古剑诀的来历",
    "duration_ticks": 3,  # 持续3个tick
    "priority": "override"  # 覆盖现有目标
}
```

#### 3.4.4 增减角色 (Add/Remove Character)

```python
# API: POST /api/dm/add_char
{
    "name": "云逸仙尊",
    "role": "mentor",  # protagonist/antagonist/heroine/npc/mentor
    "personality": "深不可测，看似随意实则洞察一切",
    "realm": "化神期",
    "location": "天机阁",
    "goal": "寻找传人"
}

# API: POST /api/dm/remove_char
{
    "character": "路人甲",
    "method": "kill"  # "kill" | "depart" | "vanish"
    # kill: 标记死亡并生成死亡叙事
    # depart: 标记离开当前舞台
    # vanish: 静默移除（不生成叙事）
}
```

#### 3.4.5 调整世界观参数 (Adjust World)

```python
# API: POST /api/dm/adjust_world
{
    "modifications": {
        "add_rule": "天元古城上空出现灵气旋涡，所有修炼速度+50%",
        "add_location": {
            "name": "剑冢秘境",
            "description": "上古剑修陨落之地，埋藏着无数名剑"
        },
        "modify_global_state": {
            "灵气浓度": "high",  # low/normal/high/critical
            "天下大势": "正道联盟正在集结"
        }
    }
}
```

### 3.5 恢复机制

干预完成后，DM 可以选择不同的恢复模式：

| 恢复模式 | 行为 | 使用场景 |
|----------|------|----------|
| **继续运行** (resume) | 从暂停点继续，引擎正常推进 | 干预不影响叙事流 |
| **单步执行** (step) | 仅推进一个 tick 然后再次暂停 | 想要逐步观察干预效果 |
| **回退重来** (rollback) | 回退到干预前的状态，修改干预参数重新执行 | 干预效果不满意 |
| **从指定 tick 开始** | 跳转到任意历史 tick 重新运行 | 大范围修改 |

```python
class DMManager:
    def resume(self):
        """恢复运行"""
        self._state = "RUNNING"
        self._apply_pending_interventions()  # 先应用待处理的干预
        self.engine.continue_loop()

    def step_once(self):
        """单步执行一个 tick"""
        self._state = "STEPPING"
        self._apply_pending_interventions()
        result = self.engine.advance_tick()
        self._state = "PAUSED"
        return result

    def rollback(self, to_tick: int):
        """回退到指定 tick"""
        snapshot = self._snapshots.get(to_tick)
        if snapshot:
            self.engine.restore_from_snapshot(snapshot)
            self._state = "PAUSED"
```

**快照机制**：每次干预前自动创建快照（引擎完整状态序列化），方便回退。

### 3.6 Web 界面设计

#### 3.6.1 布局变更

在现有三栏布局基础上，新增**底部 DM 面板**（可折叠）：

```
┌────────────┬─────────────────────┬──────────────┐
│  左侧面板   │     中间正文        │  右侧面板     │
│  -章节列表  │                     │  -角色状态    │
│  -世界事件  │    [叙事内容]        │              │
│            │                     │              │
│            │                     │              │
├────────────┴─────────────────────┴──────────────┤
│  DM 面板 (可折叠)                    [−] 折叠     │
│ ┌───────────┬───────────┬──────────────────┐   │
│ │ 运行控制   │ 断点配置   │ 干预操作          │   │
│ │ [▶] [⏸]  │ ☑Tick=50  │ [注入事件]        │   │
│ │ [⏭] [⏹]  │ ☐碰撞:战斗│ [修改角色]        │   │
│ │ 速度:1x ▼ │ ☐自定义   │ [强制行动]        │   │
│ │ Tick: 47  │           │ [增减角色]        │   │
│ │ 状态:运行 │           │ [调整世界观]      │   │
│ └───────────┴───────────┴──────────────────┘   │
│  时间线检查: ✅ 通过  [运行检查]  [查看报告]      │
└────────────────────────────────────────────────┘
```

#### 3.6.2 CSS 新增样式（关键部分）

```css
/* DM 面板 */
.dm-panel {
    position: fixed;
    bottom: 0;
    left: 0;
    right: 0;
    background: #1a1a2e;
    border-top: 2px solid #e94560;
    z-index: 100;
    transition: height 0.3s;
}

.dm-panel.collapsed {
    height: 40px;
}

.dm-panel-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 8px 16px;
    background: #16213e;
    cursor: pointer;
}

.dm-panel-body {
    display: grid;
    grid-template-columns: 1fr 1fr 2fr;
    gap: 16px;
    padding: 12px 16px;
    max-height: 300px;
    overflow-y: auto;
}

.dm-section {
    background: #16213e;
    border-radius: 8px;
    padding: 12px;
}

/* 运行控制按钮 */
.dm-btn {
    padding: 6px 12px;
    border: 1px solid #e94560;
    background: transparent;
    color: #e94560;
    border-radius: 4px;
    cursor: pointer;
    font-size: 14px;
}

.dm-btn:hover {
    background: #e94560;
    color: #fff;
}

.dm-btn.active {
    background: #e94560;
    color: #fff;
}

/* 干预表单 */
.dm-intervention-form {
    display: none;
    position: fixed;
    top: 50%;
    left: 50%;
    transform: translate(-50%, -50%);
    background: #1a1a2e;
    border: 2px solid #e94560;
    border-radius: 12px;
    padding: 24px;
    z-index: 200;
    min-width: 400px;
    max-width: 600px;
}

.dm-intervention-form.active {
    display: block;
}
```

#### 3.6.3 JavaScript 关键逻辑

```javascript
// DM 管理器
const DMManager = {
    state: 'idle',  // idle | running | paused | stepping
    currentTick: 0,
    breakpoints: [],

    // WebSocket 连接
    ws: null,

    connect() {
        this.ws = new WebSocket(`ws://${location.host}/ws/dm`);
        this.ws.onmessage = (e) => this.handleMessage(JSON.parse(e.data));
    },

    handleMessage(msg) {
        switch (msg.type) {
            case 'tick_update':
                this.currentTick = msg.tick;
                this.updateUI();
                break;
            case 'paused':
                this.state = 'paused';
                this.onPaused(msg.reason);
                break;
            case 'check_result':
                this.showCheckResult(msg.result);
                break;
        }
    },

    pause() { this.ws.send(JSON.stringify({cmd: 'pause'})); },
    resume() { this.ws.send(JSON.stringify({cmd: 'resume'})); },
    step() { this.ws.send(JSON.stringify({cmd: 'step'})); },
    setBreakpoint(bp) { this.ws.send(JSON.stringify({cmd: 'set_breakpoint', bp})); },

    // 干预操作
    injectEvent(data) {
        this.ws.send(JSON.stringify({cmd: 'inject_event', ...data}));
    },
    modifyChar(data) {
        this.ws.send(JSON.stringify({cmd: 'modify_char', ...data}));
    },
    // ... 其他干预方法
};
```

### 3.7 后端实现要点

#### 3.7.1 DMManager 模块

```
novel_world/engine/dm/              (新目录)
├── __init__.py
├── dm_manager.py          (~400行) DM 核心管理器
├── breakpoint_manager.py  (~150行) 断点管理
├── intervention_queue.py  (~100行) 干预队列
└── snapshot_manager.py    (~200行) 快照管理
```

#### 3.7.2 DMManager 核心骨架

```python
# dm_manager.py

class DMManager:
    """DM 模式管理器"""

    STATE_IDLE = "idle"
    STATE_RUNNING = "running"
    STATE_PAUSED = "paused"
    STATE_STEPPING = "stepping"

    def __init__(self, engine: NovelEngine):
        self.engine = engine
        self.state = self.STATE_IDLE
        self.breakpoint_manager = BreakpointManager()
        self.intervention_queue = []
        self.snapshot_manager = SnapshotManager(engine)
        self.intervention_history = []  # 支持撤销

    def start(self, speed: float = 1.0):
        """启动推进循环"""
        self.state = self.STATE_RUNNING
        self._run_loop(speed)

    def pause(self, reason: str = "manual"):
        """暂停推进"""
        self.state = self.STATE_PAUSED
        self._notify_clients({"type": "paused", "reason": reason})

    def resume(self):
        """恢复推进"""
        # 先应用干预队列
        self._apply_pending_interventions()
        self.state = self.STATE_RUNNING
        self._run_loop()

    def step_once(self):
        """单步执行"""
        self.state = self.STATE_STEPPING
        self._apply_pending_interventions()
        result = self.engine.advance_tick()
        self.state = self.STATE_PAUSED
        self._notify_clients({"type": "tick_result", "result": result.to_dict()})
        return result

    def _run_loop(self, speed: float = 1.0):
        """运行循环"""
        while self.state == self.STATE_RUNNING:
            # 断点检查
            bp = self.breakpoint_manager.check(self.engine)
            if bp:
                self.pause(f"断点触发: {bp.condition}")
                return

            # 推进 tick
            result = self.engine.advance_tick()
            self._notify_clients({"type": "tick_update", "tick": result.tick_id})

            # 时间线检查阻断
            if self._should_block_on_check(result):
                self.pause("时间线检查发现 BLOCKER 级别问题")
                return

            # 速度控制
            time.sleep(1.0 / speed)

    # ── 干预方法 ──

    def inject_event(self, event: InjectedEvent):
        """注入事件（加入干预队列，下次 tick 前执行）"""
        self.intervention_queue.append(("inject_event", event))
        self.intervention_history.append(("inject_event", event))

    def modify_character(self, char_name: str, modifications: dict):
        """修改角色属性"""
        self.snapshot_manager.create_snapshot("pre_modify_char")  # 干预前快照
        self.intervention_queue.append(("modify_char", (char_name, modifications)))
        self.intervention_history.append(("modify_char", (char_name, modifications)))

    def force_action(self, char_name: str, action: str, duration: int, priority: str):
        """强制角色行动"""
        self.intervention_queue.append(("force_action", (char_name, action, duration, priority)))

    def add_character(self, char_data: dict):
        """添加角色"""
        self.snapshot_manager.create_snapshot("pre_add_char")
        self.intervention_queue.append(("add_char", char_data))

    def remove_character(self, char_name: str, method: str):
        """移除角色"""
        self.snapshot_manager.create_snapshot("pre_remove_char")
        self.intervention_queue.append(("remove_char", (char_name, method)))

    def adjust_world(self, modifications: dict):
        """调整世界观参数"""
        self.snapshot_manager.create_snapshot("pre_adjust_world")
        self.intervention_queue.append(("adjust_world", modifications))

    def undo_last_intervention(self):
        """撤销最后一次干预"""
        if self.intervention_history:
            last = self.intervention_history.pop()
            self.snapshot_manager.rollback_to_last()
            return True
        return False

    def _apply_pending_interventions(self):
        """应用干预队列中的所有待处理干预"""
        for intervention_type, data in self.intervention_queue:
            handler = self._intervention_handlers.get(intervention_type)
            if handler:
                handler(data)
        self.intervention_queue.clear()
```

#### 3.7.3 API 路由

```python
# 在 app.py 中新增

from novel_world.engine.dm.dm_manager import DMManager

dm_manager = None  # 在 init 时创建

@app.route("/api/dm/pause", methods=["POST"])
def dm_pause():
    dm_manager.pause("manual")
    return jsonify({"status": "paused", "tick": dm_manager.engine.timeline.current_tick})

@app.route("/api/dm/resume", methods=["POST"])
def dm_resume():
    dm_manager.resume()
    return jsonify({"status": "running"})

@app.route("/api/dm/step", methods=["POST"])
def dm_step():
    result = dm_manager.step_once()
    return jsonify({"status": "paused", "result": result.to_dict()})

@app.route("/api/dm/inject_event", methods=["POST"])
def dm_inject_event():
    data = request.get_json()
    event = InjectedEvent(
        id=f"dm_{int(time.time())}",
        tick=dm_manager.engine.timeline.current_tick,
        event_type=data["event_type"],
        description=data["description"],
        target_characters=data.get("target_characters", []),
        target_location=data.get("target_location", ""),
        priority=data.get("priority", 5),
    )
    dm_manager.inject_event(event)
    return jsonify({"status": "ok", "event_id": event.id})

@app.route("/api/dm/modify_char", methods=["POST"])
def dm_modify_char():
    data = request.get_json()
    dm_manager.modify_character(data["character"], data["modifications"])
    return jsonify({"status": "ok"})

@app.route("/api/dm/force_action", methods=["POST"])
def dm_force_action():
    data = request.get_json()
    dm_manager.force_action(
        data["character"], data["action"],
        data.get("duration_ticks", 1),
        data.get("priority", "override"),
    )
    return jsonify({"status": "ok"})

@app.route("/api/dm/add_char", methods=["POST"])
def dm_add_char():
    data = request.get_json()
    dm_manager.add_character(data)
    return jsonify({"status": "ok"})

@app.route("/api/dm/remove_char", methods=["POST"])
def dm_remove_char():
    data = request.get_json()
    dm_manager.remove_character(data["character"], data.get("method", "depart"))
    return jsonify({"status": "ok"})

@app.route("/api/dm/adjust_world", methods=["POST"])
def dm_adjust_world():
    data = request.get_json()
    dm_manager.adjust_world(data["modifications"])
    return jsonify({"status": "ok"})

@app.route("/api/dm/set_breakpoint", methods=["POST"])
def dm_set_breakpoint():
    data = request.get_json()
    bp = Breakpoint(
        id=f"bp_{int(time.time())}",
        type=data["type"],
        condition=data["condition"],
        one_shot=data.get("one_shot", True),
    )
    dm_manager.breakpoint_manager.add(bp)
    return jsonify({"status": "ok", "breakpoint_id": bp.id})

@app.route("/api/dm/breakpoints", methods=["GET"])
def dm_get_breakpoints():
    bps = dm_manager.breakpoint_manager.list_all()
    return jsonify({"breakpoints": [asdict(bp) for bp in bps]})

@app.route("/api/dm/undo", methods=["POST"])
def dm_undo():
    success = dm_manager.undo_last_intervention()
    return jsonify({"status": "ok" if success else "nothing_to_undo"})

@app.route("/api/dm/state", methods=["GET"])
def dm_state():
    return jsonify({
        "state": dm_manager.state,
        "tick": dm_manager.engine.timeline.current_tick if dm_manager.engine else 0,
        "pending_interventions": len(dm_manager.intervention_queue),
    })

# ── 时间线检查 API ──

@app.route("/api/check/timeline", methods=["POST"])
def check_timeline():
    data = request.get_json() or {}
    tick_range = data.get("tick_range")
    check_type = data.get("type", "fast")  # fast | deep | full

    checker = dm_manager.engine.timeline_checker if dm_manager else None
    if not checker:
        return jsonify({"error": "引擎未初始化"}), 400

    if check_type == "fast":
        issues = checker.fast_check(tick_range)
    elif check_type == "deep":
        issues = checker.deep_check(tick_range)
    else:
        issues = checker.full_check(tick_range)

    return jsonify(checker.format_report(issues))
```

### 3.8 WebSocket 实时通信

DM 模式需要一个持续的通信通道来推送 tick 更新、暂停通知、检查结果等。

```python
# ws_manager.py

import json
from flask_sock import Sock

sock = Sock()

@sock.route("/ws/dm")
def dm_ws(ws):
    """DM WebSocket 连接"""
    dm_manager.register_client(ws)
    try:
        while True:
            msg = ws.receive()
            if msg:
                data = json.loads(msg)
                dm_manager.handle_client_command(data)
    except Exception:
        pass
    finally:
        dm_manager.unregister_client(ws)
```

---

## 4. 两功能联动设计

### 4.1 检查 → 暂停 → 干预 → 再检查 的闭环

```
┌────────────────────────────────────────────────┐
│                                                │
│  ① Tick推进                                     │
│       │                                        │
│       ▼                                        │
│  ② 时间线检查 (自动)                             │
│       │                                        │
│       ├── PASS ──→ 继续①                        │
│       │                                        │
│       └── BLOCKER/ERROR ──→ ③ DM自动暂停        │
│                                    │            │
│                                    ▼            │
│                          ④ 展示检查报告          │
│                                    │            │
│                                    ▼            │
│                          ⑤ DM决定干预方式        │
│                               │                 │
│                    ┌──────────┼──────────┐      │
│                    ▼          ▼          ▼      │
│               修改角色    注入事件    调整规则    │
│                    │          │          │      │
│                    └──────────┼──────────┘      │
│                               ▼                 │
│                    ⑥ 重新检查 (验证修复)         │
│                               │                 │
│                               ├── PASS ──→ ①    │
│                               │                 │
│                               └── 仍有问题 ──→ ⑤ │
│                                                │
└────────────────────────────────────────────────┘
```

### 4.2 联动场景示例

**场景：时间线检查发现"女配在第47 tick已死亡，但在第52 tick又出现了"**

```
1. 检查触发：章节末全量检查
2. 自动暂停：BLOCKER 级别问题
3. DM 看到报告：
   ┌─────────────────────────────────────────────┐
   │ ❌ BLOCKER: 角色 "苏婉儿" 状态冲突           │
   │   第 47 tick (ch3): 标记为死亡               │
   │   第 52 tick (ch3): 作为活跃角色出现         │
   │   → 建议：确认苏婉儿的生死状态               │
   ├─────────────────────────────────────────────┤
   │ 可选干预：                                    │
   │ [回退到 tick 47] [修改tick 52叙事] [复活角色] │
   └─────────────────────────────────────────────┘
4. DM 选择"修改tick 52叙事"：
   - 将tick 52中出现的角色从"苏婉儿"改为"苏婉儿的替身/幻象"
   - 或添加事件解释"苏婉儿被复活"
5. 重新检查 → PASS → 继续推演
```

### 4.3 检查策略联动配置

```python
@dataclass
class DMPolicy:
    """DM 策略配置 - 定义检查与干预的联动规则"""

    # 哪些检查级别触发自动暂停
    auto_pause_on: Set[TimelineIssueLevel] = field(default_factory=lambda: {TimelineIssueLevel.BLOCKER})

    # 哪些检查维度触发自动暂停
    auto_pause_dimensions: Set[str] = field(default_factory=lambda: {
        "timeline_backflow", "world_monotonicity"
    })

    # 暂停后是否自动展示建议干预方案
    suggest_intervention: bool = True

    # 干预后是否自动重新检查
    recheck_after_intervention: bool = True

    # 连续 BLOCKER 超过 N 次是否终止
    max_consecutive_blockers: int = 3

    # 检查触发节奏
    check_on_tick: bool = True       # 每个 tick 后快速检查
    check_on_collision: bool = True  # 碰撞后深度检查
    check_on_chapter_end: bool = True  # 章节末全量检查
```

---

## 5. 实施路线图

### 阶段一：时间线检查核心（1-2天）

| 任务 | 说明 | 预计行数 |
|------|------|----------|
| 创建 `timeline_checker.py` | 实现 6 个维度的规则检查 | ~500行 |
| 集成到 `NovelEngine.advance_tick()` | 在 tick 流程中插入检查调用 | ~30行修改 |
| 新增 API: `/api/check/timeline` | 手动触发检查 | ~40行 |
| 单元测试 | 覆盖各维度检查逻辑 | ~200行 |

### 阶段二：DM 模式基础（2-3天）

| 任务 | 说明 | 预计行数 |
|------|------|----------|
| 创建 `dm_manager.py` | 核心状态机和运行循环 | ~400行 |
| 创建 `breakpoint_manager.py` | 断点管理 | ~150行 |
| 创建 `snapshot_manager.py` | 快照与回退 | ~200行 |
| 创建 `intervention_queue.py` | 干预队列 | ~100行 |
| 新增 API 路由（/api/dm/*） | REST API 端点 | ~200行 |
| 集成到 app.py | 初始化 DM 管理器 | ~50行 |

### 阶段三：Web 前端 DM 面板（1-2天）

| 任务 | 说明 |
|------|------|
| CSS/HTML 新增 DM 面板 | 底部可折叠面板 |
| JS  DM 管理器逻辑 | WebSocket 通信、UI 交互 |
| 干预表单弹窗 | 注入事件/修改角色/强制行动等表单 |
| 断点配置 UI | 可视化添加/删除/启停断点 |
| 时间线检查结果展示 | 在 DM 面板中集成检查报告 |

### 阶段四：联动与优化（1天）

| 任务 | 说明 |
|------|------|
| 检查→暂停联动 | 配置自动暂停策略 |
| 干预后重新检查 | 干预 → 验证闭环 |
| 检查结果可视化 | 时间线图表展示检查结果 |
| 压力测试与性能优化 | 确保检查不影响叙事生成性能 |

---

> **设计总结**：时间线检查功能借鉴书斋"三层检查 + 零Token规则 + AI辅助"的架构，针对小说世界的时间维度设计 6 个专项检查维度。实时 DM 模式为作者提供"暂停-观察-干预-恢复"的完整控制循环，两个功能通过自动暂停和干预后验证形成闭环，确保 AI 生成的叙事始终在作者掌控之中。
