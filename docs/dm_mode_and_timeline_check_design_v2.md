# 时间线检查功能 & 实时 DM 模式 - 完整设计方案（v2）

> 设计日期：2026-07-17  
> v2 更新：2026-07-17  
> 参考项目：书斋V65 检查机制  
> 目标项目：小说世界 (H:\小说\小说世界\)

---

## v2 变更说明

基于 [design_vs_code_gap_analysis.md](./design_vs_code_gap_analysis.md) 的全面差距分析，v2 新增以下三个遗漏项的完整设计方案：

| 变更编号 | 内容 | 插入位置 | 影响范围 |
|----------|------|----------|----------|
| **遗漏一** | **Prompt 管理体系**：Prompt Registry、DM 干预联动、Prompt 合规度检查、热重载、版本回滚 | §3.10（新增） | DM 模式、TimelineChecker |
| **遗漏二** | **章节数量设定**：总章节数、每章 Tick 数、章节间自动暂停、达到上限行为、运行时修改 | §3.3（新增，原 §3.3~§3.8 顺延） | EngineConfig、DM 启动面板 |
| **遗漏三** | **已有隐式检查层对齐**：TimelineChecker 在现有模块上的定位、质量管控分层架构图、DM 干预与 NarrativeCorrector 联动、双代码体系对接策略 | §2.7（新增）、§4.4（新增）、§5 实施路线图扩充 | 第2章、第4章、实施计划 |

其他改动：
- 目录更新以反映新增章节
- §5 实施路线图增加 Prompt 管理、EngineConfig、质量层对接三个阶段
- 全文交叉引用更新

---

## 目录

1. [书斋检查机制解读](#1-书斋检查机制解读)
2. [功能一：时间线检查功能](#2-功能一时间线检查功能)
   - 2.1 设计目标
   - 2.2 检查什么（检查维度矩阵）
   - 2.3 触发时机
   - 2.4 检查粒度与方式
   - 2.5 输出形式
   - 2.6 技术实现要点
   - 2.7 已有隐式检查层对齐（v2 新增）
3. [功能二：实时 DM 模式](#3-功能二实时-dm-模式)
   - 3.1 设计目标
   - 3.2 整体架构
   - 3.3 章节数量设定与引擎配置（v2 新增）
   - 3.4 暂停机制
   - 3.5 干预能力
   - 3.6 恢复机制
   - 3.7 Web 界面设计
   - 3.8 后端实现要点
   - 3.9 WebSocket 实时通信
   - 3.10 Prompt 管理体系（v2 新增）
4. [两功能联动设计](#4-两功能联动设计)
   - 4.1 检查 → 暂停 → 干预 → 再检查的闭环
   - 4.2 联动场景示例
   - 4.3 检查策略联动配置
   - 4.4 DM 干预与已有质量模块的联动（v2 新增）
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

#### 维度七：Prompt 合规度检查 (Prompt Compliance)（v2 新增）

```
检查对象：AI 生成的叙事内容是否遵循了当前生效的 system prompt 约束
检查逻辑：
  - 角色性格偏离：叙事中角色的言行是否与 prompt 中定义的性格设定一致
  - 语气风格不一致：叙事语调是否与 prompt 中的风格要求匹配（如"紧张"→ 出现轻松调侃）
  - 视角违规：prompt 要求"第三人称"，实际出现"第一人称"叙述
  - 禁止元素出现：prompt 中明确禁用的词汇/桥段是否仍然出现
数据来源：PromptRegistry.current_prompt + NarrativeValidator 规则库
实现方式：规则匹配（零Token），在 FastCheck 层执行
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
Tick后自动： 快速规则检查（100ms内），只检查硬约束（角色行踪/时间线倒流/世界状态单调性/Prompt合规度）
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
│   ├── world_monotonicity (世界状态单调性)
│   └── prompt_compliance (Prompt合规度)（v2 新增）
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
│  ✅ Prompt合规度       0 issues    （v2 新增）       │
└─────────────────────────────────────────────────────┘
```

### 2.6 技术实现要点

#### 2.6.1 模块位置

```
novel_world/engine/quality/timeline_checker.py   (新模块，预计 ~600行，含 Prompt 合规度)
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
        # v2 新增：引用已有质量模块和 Prompt Registry
        self.narrative_validator = None      # NarrativeValidator
        self.narrative_corrector = None      # NarrativeCorrector
        self.hard_constraint_ctrl = None     # HardConstraintController
        self.prompt_registry = None          # PromptRegistry

    # ── 快速检查（Tick后自动，<100ms） ──

    def fast_check(self, tick_range: tuple = None) -> List[TimelineIssue]:
        """快速规则检查：角色行踪 + 时间线倒流 + 世界状态单调性 + Prompt合规度"""
        issues = []
        issues.extend(self.check_character_trail(tick_range))
        issues.extend(self.check_timeline_backflow(tick_range))
        issues.extend(self.check_world_monotonicity(tick_range))
        issues.extend(self.check_prompt_compliance(tick_range))  # v2 新增
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

    # v2 新增：Prompt 合规度检查
    def check_prompt_compliance(self, tick_range=None) -> List[TimelineIssue]:
        """检查 AI 输出是否遵循当前生效 prompt 的约束（零Token规则匹配）"""
        issues = []
        if not self.prompt_registry:
            return issues
        current_prompt = self.prompt_registry.get_current("narrative_generation")
        if not current_prompt:
            return issues

        # 1. 检查禁止词汇：prompt 中禁用的词汇是否出现在叙事中
        # 2. 检查格式遵守：prompt 要求的格式（如"每段不超过150字"）是否被违反
        # 3. 检查视角一致性：prompt 指定"第三人称"但叙事中出现"我"
        # 4. 检查语气一致性：prompt 指定的风格关键词与叙事文本风格对比
        return issues

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
| Prompt 合规度 | PromptRegistry.current + NarrativeValidator 规则库 | PromptRegistry 待建 |

### 2.7 已有隐式检查层对齐（v2 新增）

#### 2.7.1 设计原则：事中约束 + 事后检查 双层互补

代码中已存在 12+ 个质量管控模块，它们和本设计的 TimelineChecker 形成**互补而非替代**关系：

| 层级 | 现有模块 | 定位 | 与 TimelineChecker 关系 |
|------|----------|------|--------------------------|
| **生成前** | HardConstraintController | 高频词替换、空洞表述拦截 | TimelineChecker 不负责此层 |
| **生成中** | NarrativeValidator | 禁止词汇/铁律规则校验 | TimelineChecker 复用其规则库做 Prompt 合规度检查 |
| **生成中** | NarrativeCorrector | 人设防崩塌、不可击败角色保护 | **DM 干预"不通过"时触发 NarrativeCorrector 重写** |
| **生成中** | WorldRuleGuard | 关键词和规则条件校验 | 与 TimelineChecker 的世界单调性检查互补 |
| **生成中** | NarrativeQualityController | 片段去重/时间排序/视角控制 | TimelineChecker 不负责片段级去重 |
| **生成中** | EventDeduplicator | 句式模式和冲突类型去重 | 不重叠 |
| **生成后** | ConsistencyChecker（已有 8 维度） | 跨模块数据对齐 | TimelineChecker 在此基础上添加时间专项维度 |
| **生成后** | TimelineChecker（本设计） | **事后**：时间维度专项检查 | 新增的"事后检查"层 |
| **叙事结构** | PlotNodeManager | 起承转合、剧情节奏管控 | 比 TimelineChecker 更高层的叙事结构管控 |
| **叙事结构** | SelfEvolution | 白城主自我进化 | 不直接与 TimelineChecker 交互 |

#### 2.7.2 完整质量管控分层架构图

```
┌──────────────────────────────────────────────────────────────────┐
│                      叙事结构管控层                                │
│  PlotNodeManager (起承转合)    SelfEvolution (自我进化)            │
└──────────────────────────────┬───────────────────────────────────┘
                               │ 管控剧情节奏
                               ▼
┌──────────────────────────────────────────────────────────────────┐
│                    ┌─ 生成前（Pre-Generation） ─┐                  │
│  HardConstraintController                       ← 词表替换        │
│  (高频词替换 / 空洞表述拦截)                     ← 零Token        │
├──────────────────────────────────────────────────────────────────┤
│                    ┌─ 生成中（In-Generation） ─┐                   │
│  NarrativeValidator      ← 禁止词汇/铁律校验                     │
│  NarrativeCorrector      ← 人设防崩塌/不可击败角色               │
│  WorldRuleGuard          ← 世界观规则拦截                         │
│  NarrativeQualityController ← 去重/排序/视角                      │
│  EventDeduplicator       ← 句式/冲突去重                          │
├──────────────────────────────────────────────────────────────────┤
│                    ┌─ 生成后（Post-Generation） ─┐                 │
│  ConsistencyChecker (8维度)  ← 跨模块数据对齐                     │
│  TimelineChecker (7维度)     ← 时间维度专项检查  ★本设计★        │
│    ├── FastCheck:   角色行踪/时间倒流/世界单调性/Prompt合规度     │
│    ├── DeepCheck:   因果链/伏笔回收/成长曲线                     │
│    └── AIAssisted:  情节矛盾/角色漂移/叙事连贯性                  │
├──────────────────────────────────────────────────────────────────┤
│                    ┌─ DM 干预层（实时） ─┐                         │
│  DMManager                                                ★本设计★ │
│    ├── 暂停 → 查看 TimelineChecker 报告                            │
│    ├── 干预 → 触发 NarrativeCorrector 重写                        │
│    ├── 修改 → 更新 PromptRegistry 模板                            │
│    └── 恢复 → 重新检查验证                                        │
└──────────────────────────────────────────────────────────────────┘
```

#### 2.7.3 DM 干预调用已有模块的流程

当 DM 在审查检查报告后决定"不通过"时，系统的处理链路：

```
DM 点击"不通过，要求重写"
        │
        ▼
DMManager.require_rewrite(tick_id, reason)
        │
        ├── 1. 记录干预历史
        │
        ├── 2. 根据 reason 路由到对应处理模块：
        │   ├── reason="人设崩塌"     → NarrativeCorrector.enforce_character_consistency()
        │   ├── reason="违规词汇"     → HardConstraintController.rebuild_blocklist()
        │   ├── reason="世界规则违反"  → WorldRuleGuard.add_rule()
        │   ├── reason="风格/语气"    → PromptRegistry.update_style_params()
        │   └── reason="情节矛盾"     → NarrativeCorrector.rewrite_with_constraint()
        │
        ├── 3. 应用修正后重新生成该 tick 叙事
        │
        └── 4. TimelineChecker.fast_check() 验证修正结果 → 通过则恢复运行
```

#### 2.7.4 ConsistencyChecker 现有维度与 TimelineChecker 的对齐

代码中 `ConsistencyChecker` 已有的检查维度与 TimelineChecker 的关系：

| ConsistencyChecker 维度 | TimelineChecker 维度 | 处理方式 |
|--------------------------|----------------------|----------|
| character_state | character_trail + progression_curve | TimelineChecker 从时间维度细化 |
| timeline | timeline_backflow + causal_chain | TimelineChecker 扩展为专项检查 |
| goal | progression_curve（关联） | 保留在 ConsistencyChecker |
| foreshadowing | foreshadowing_loop | TimelineChecker 接管时间相关逻辑 |
| time_backflow | timeline_backflow | TimelineChecker 接管，ConsistencyChecker 委托 |
| **item** | world_monotonicity | 物品状态单调性移入 TimelineChecker |
| **six_axis** | — | 保留在 ConsistencyChecker（非时间维度） |
| **world_rule** | world_monotonicity（部分） | 世界观不可逆变更移入 TimelineChecker |

#### 2.7.5 双代码体系对接策略

项目存在 `backend/`（Flask简化版）和 `novel_world/engine/`（完整框架）两套代码体系。

**推荐策略（方案C）：保持双轨，通过适配层桥接**

```
backend/                          novel_world/engine/
  (Flask + 前端)                    (纯Python框架)
       │                                   │
       │  API 适配层                         │
       ├── dm_adapter.py ───────────────→ dm_manager.py
       ├── check_adapter.py ────────────→ timeline_checker.py
       ├── prompt_adapter.py ───────────→ prompt_registry.py
       └── config_adapter.py ───────────→ engine_config.py
       │                                   │
       ▼                                   ▼
  现有前端 DM 面板                    独立开发，可单独测试
```

| 体系 | 职责 | DM/Timeline 角色 |
|------|------|------------------|
| `backend/` | 继续服务现有前端（角色设定、章节生成、存档） | 负责 API 暴露 + WebSocket 推送 + DM 面板渲染 |
| `novel_world/engine/` | 承载所有新增核心逻辑 | TimelineChecker、DMManager、PromptRegistry、EngineConfig 均在此实现 |
| 适配层 | 桥接两套体系 | 薄层（~100行/适配器），不包含业务逻辑 |

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
│  │          │  │          │  │ │ 章节配置 (v2新增)││ │
│  │          │  │          │  │ │ 总章节: 3  ▲▼   ││ │
│  │          │  │          │  │ │ Tick/章:20 ▲▼   ││ │
│  │          │  │          │  │ │ 自动暂停: ☑     ││ │
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
│  │          │  │          │  │ │ [Prompt管理] (v2新增)││
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
│  │ - /resume        │  │ - EngineConfig管理器     │ │
│  │ - /step          │  │ - 断点管理器             │ │
│  │ - /inject_event  │  │ - 干预队列               │ │
│  │ - /modify_char   │  │ - 干预历史               │ │
│  │ - /force_action  │  │ - 撤销/重做              │ │
│  │ - /add_char      │  │ - Prompt联动             │ │
│  │ - /remove_char   │  │                          │ │
│  │ - /adjust_world  │  │                          │ │
│  │ - /set_breakpoint│  │                          │ │
│  │ - /config        │  │                          │ │
│  │ - /prompt/*      │  │                          │ │
│  └──────────────────┘  └──────────────────────────┘ │
└─────────────────────────────────────────────────────┘
```

### 3.3 章节数量设定与引擎配置（v2 新增）

#### 3.3.1 设计目标

在 DM 启动模拟之前，提供基本的运行参数配置。这些配置决定了引擎的推进边界和行为，是整个 DM 模式的"起手设定"。

#### 3.3.2 EngineConfig 数据结构

```python
# novel_world/engine/config/engine_config.py

from dataclasses import dataclass, field
from enum import Enum

class ChapterEndBehavior(Enum):
    """达到总章节数上限后的行为"""
    AUTO_END = "auto_end"            # 自动收尾并终止
    LOOP_LAST = "loop_last"          # 循环最后一章（无限重复最后一个tick）
    INFINITE = "infinite"            # 无限循环（忽略章节上限，持续生成）

@dataclass
class EngineConfig:
    """引擎运行配置"""

    # ── 章节数量设定 ──
    total_chapters: int = 3                    # 总章节数，1~N
    ticks_per_chapter: int = 20                # 每章 Tick 数，1~N
    auto_pause_between_chapters: bool = True   # 章节间自动暂停（便于DM审阅）
    chapter_end_behavior: ChapterEndBehavior = ChapterEndBehavior.AUTO_END

    # ── DM 策略（参见 §4.3） ──
    auto_pause_on_blocker: bool = True
    recheck_after_intervention: bool = True

    # ── 性能控制 ──
    tick_speed: float = 1.0          # 运行速度倍率（0.5 = 慢速, 2.0 = 加速）
    max_consecutive_blockers: int = 3  # 连续 BLOCKER 超过此值自动终止

    def validate(self) -> List[str]:
        """校验配置合法性，返回错误列表"""
        errors = []
        if self.total_chapters < 1:
            errors.append("总章节数必须 ≥ 1")
        if self.ticks_per_chapter < 1:
            errors.append("每章 Tick 数必须 ≥ 1")
        if self.tick_speed <= 0:
            errors.append("运行速度必须 > 0")
        return errors
```

#### 3.3.3 DM 启动面板（UI）

在 DM 面板中增加"启动配置"区域，在启动模拟前展示：

```
┌─────────────────────────────────────────────────────┐
│  ⚙ 模拟启动配置                                     │
├─────────────────────────────────────────────────────┤
│                                                      │
│  总章节数:      [ 3 ]  (1~20)                        │
│  每章 Tick 数:  [ 20 ] (1~100)                       │
│  章节间自动暂停: [☑ 是]  便于审阅和干预              │
│                                                      │
│  达到上限后:    ○ 自动收尾并终止                      │
│                 ○ 循环最后一章                        │
│                 ○ 无限循环                            │
│                                                      │
│  运行速度:      [1.0x]  ▼  (0.5x / 1.0x / 2.0x)     │
│                                                      │
│              [启动模拟]   [取消]                      │
└─────────────────────────────────────────────────────┘
```

#### 3.3.4 运行时修改

DM 可以在运行过程中修改章节配置，修改后下一 tick 生效：

```python
class DMManager:
    # ...

    def update_config(self, modifications: dict):
        """运行时修改引擎配置"""
        config = self.engine.config

        if "total_chapters" in modifications:
            new_total = modifications["total_chapters"]
            if new_total < config.total_chapters and self.engine.current_chapter > new_total:
                # 减少总章节数且当前已超过新上限 → 立即触发章节结束
                self._trigger_chapter_end()
            config.total_chapters = new_total

        if "ticks_per_chapter" in modifications:
            config.ticks_per_chapter = modifications["ticks_per_chapter"]
            # 如果当前章节 tick 数已超过新上限，下一 tick 即触发章节结束

        if "auto_pause_between_chapters" in modifications:
            config.auto_pause_between_chapters = modifications["auto_pause_between_chapters"]

        if "chapter_end_behavior" in modifications:
            config.chapter_end_behavior = ChapterEndBehavior(modifications["chapter_end_behavior"])

        self.config_history.append(config.copy())  # 记录配置变更历史
```

#### 3.3.5 API 端点

```python
# GET  /api/dm/config          → 获取当前配置
# PUT  /api/dm/config          → 修改配置（运行时）
# POST /api/dm/config/validate → 校验配置合法性
```

#### 3.3.6 与 NovelEngine 的集成

```python
class NovelEngine:
    def __init__(self, config: EngineConfig = None, ...):
        self.config = config or EngineConfig()
        self.current_chapter = 0
        self.current_tick_in_chapter = 0

    def advance_tick(self, ...) -> TickResult:
        # ... 现有流程 ...

        self.current_tick_in_chapter += 1

        # 检查是否达到每章 tick 上限
        if self.current_tick_in_chapter >= self.config.ticks_per_chapter:
            result.chapter_end = True
            self.current_chapter += 1
            self.current_tick_in_chapter = 0

            # 检查是否达到总章节数
            if self.current_chapter >= self.config.total_chapters:
                if self.config.chapter_end_behavior == ChapterEndBehavior.AUTO_END:
                    result.simulation_end = True
                elif self.config.chapter_end_behavior == ChapterEndBehavior.LOOP_LAST:
                    self.current_chapter = self.config.total_chapters - 1  # 锁定最后一章
                # INFINITE：什么都不做，继续推进

        return result
```

### 3.4 暂停机制

#### 3.4.1 状态机

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

#### 3.4.2 暂停触发条件

| 触发类型 | 条件 | 实现方式 |
|----------|------|----------|
| **Tick 计数断点** | 当前 tick_id == N | 每次 advance_tick 后检查 |
| **碰撞类型断点** | 碰撞类型匹配（战斗/对话/事件） | 碰撞检测后检查 |
| **角色状态断点** | 角色到达某位置/境界/状态 | tick 结束后检查 |
| **章节间自动暂停** | auto_pause_between_chapters=True 且达到每章末 | §3.3 EngineConfig 驱动 |
| **自定义条件断点** | Python 表达式求值 | 沙箱化 eval，限制可用变量 |
| **时间线检查阻断** | 检查发现 BLOCKER 级别问题 | 自动暂停 |
| **手动暂停** | 用户点击暂停按钮 | WebSocket 消息 → 设置标志位 |

#### 3.4.3 断点配置数据结构

```python
@dataclass
class Breakpoint:
    id: str
    type: str  # "tick" | "collision" | "character" | "chapter_end" | "custom" | "check_blocker"
    condition: str  # 条件表达式
    enabled: bool = True
    one_shot: bool = False  # 触发一次后自动禁用
    hit_count: int = 0

# 示例
Breakpoint(id="bp_001", type="tick", condition="50", one_shot=True)
Breakpoint(id="bp_002", type="collision", condition="type=='combat'")
Breakpoint(id="bp_003", type="character", condition="name=='叶辰' and realm=='金丹期'")
Breakpoint(id="bp_004", type="chapter_end", condition="true")  # 由 EngineConfig.auto_pause_between_chapters 控制
Breakpoint(id="bp_005", type="custom", condition="len(engine.goals.get_active_goals()) > 20")
```

### 3.5 干预能力

暂停状态下，DM 可执行以下干预操作。所有干预都会记录到干预历史中，支持撤销。

#### 3.5.1 注入事件 (Inject Event)

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

#### 3.5.2 修改角色属性 (Modify Character)

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

#### 3.5.3 强制行动 (Force Action)

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

#### 3.5.4 增减角色 (Add/Remove Character)

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

#### 3.5.5 调整世界观参数 (Adjust World)

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

### 3.6 恢复机制

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

### 3.7 Web 界面设计

#### 3.7.1 布局变更

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
│ │ 章: 2/3   │           │ [调整世界观]      │   │
│ │ 状态:运行 │           │ [Prompt管理]      │   │
│ └───────────┴───────────┴──────────────────┘   │
│  时间线检查: ✅ 通过  [运行检查]  [查看报告]      │
└────────────────────────────────────────────────┘
```

#### 3.7.2 CSS 新增样式（关键部分）

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

/* v2 新增：启动配置面板 */
.dm-config-panel {
    background: #0f3460;
    border-radius: 8px;
    padding: 16px;
    margin-bottom: 12px;
}

.dm-config-row {
    display: flex;
    align-items: center;
    gap: 8px;
    margin-bottom: 8px;
}

.dm-config-row label {
    min-width: 120px;
    color: #a8a8b3;
    font-size: 13px;
}

.dm-config-row input[type="number"] {
    width: 60px;
    padding: 4px 8px;
    background: #1a1a2e;
    border: 1px solid #e94560;
    color: #e4e4e4;
    border-radius: 4px;
}

.dm-config-row select {
    padding: 4px 8px;
    background: #1a1a2e;
    border: 1px solid #e94560;
    color: #e4e4e4;
    border-radius: 4px;
}

/* v2 新增：Prompt 管理面板 */
.dm-prompt-panel {
    max-height: 400px;
    overflow-y: auto;
}

.dm-prompt-item {
    background: #0f3460;
    border-radius: 6px;
    padding: 10px;
    margin-bottom: 8px;
    border-left: 3px solid #e94560;
}

.dm-prompt-version {
    font-size: 11px;
    color: #6c757d;
    margin-top: 4px;
}
```

#### 3.7.3 JavaScript 关键逻辑

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
            case 'config_update':
                this.updateConfigUI(msg.config);
                break;
            case 'prompt_update':
                this.updatePromptUI(msg.prompts);
                break;
        }
    },

    pause() { this.ws.send(JSON.stringify({cmd: 'pause'})); },
    resume() { this.ws.send(JSON.stringify({cmd: 'resume'})); },
    step() { this.ws.send(JSON.stringify({cmd: 'step'})); },
    setBreakpoint(bp) { this.ws.send(JSON.stringify({cmd: 'set_breakpoint', bp})); },

    // v2 新增：启动配置
    startSimulation(config) {
        this.ws.send(JSON.stringify({cmd: 'start', config}));
    },
    updateConfig(mods) {
        this.ws.send(JSON.stringify({cmd: 'update_config', modifications: mods}));
    },

    // 干预操作
    injectEvent(data) {
        this.ws.send(JSON.stringify({cmd: 'inject_event', ...data}));
    },
    modifyChar(data) {
        this.ws.send(JSON.stringify({cmd: 'modify_char', ...data}));
    },
    // ... 其他干预方法

    // v2 新增：Prompt 管理
    getPrompts() { this.ws.send(JSON.stringify({cmd: 'get_prompts'})); },
    updatePrompt(promptId, template) {
        this.ws.send(JSON.stringify({cmd: 'update_prompt', prompt_id: promptId, template}));
    },
    rollbackPrompt(promptId, version) {
        this.ws.send(JSON.stringify({cmd: 'rollback_prompt', prompt_id: promptId, version}));
    },
    previewPrompt(promptId, template, sampleContext) {
        this.ws.send(JSON.stringify({cmd: 'preview_prompt', prompt_id: promptId, template, sample_context: sampleContext}));
    },
};
```

### 3.8 后端实现要点

#### 3.8.1 DMManager 模块

```
novel_world/engine/dm/              (新目录)
├── __init__.py
├── dm_manager.py          (~500行) DM 核心管理器（含配置管理和 Prompt 联动）
├── breakpoint_manager.py  (~150行) 断点管理
├── intervention_queue.py  (~100行) 干预队列
└── snapshot_manager.py    (~200行) 快照管理

novel_world/engine/config/          (v2 新增)
├── __init__.py
└── engine_config.py       (~80行)  EngineConfig 数据结构

novel_world/engine/prompt/          (v2 新增)
├── __init__.py
├── prompt_registry.py     (~300行) Prompt 注册表
└── prompt_templates/               (数据目录)
    └── templates.json              Prompt 模板存储
```

#### 3.8.2 DMManager 核心骨架

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
        self.config_history = []        # v2 新增：配置变更历史
        # v2 新增：PromptRegistry 引用
        self.prompt_registry = None

    def start(self, config: EngineConfig = None):
        """启动推进循环"""
        if config:
            self.engine.config = config
        self.state = self.STATE_RUNNING
        self._run_loop(self.engine.config.tick_speed)

    def pause(self, reason: str = "manual"):
        """暂停推进"""
        self.state = self.STATE_PAUSED
        self._notify_clients({"type": "paused", "reason": reason})

    def resume(self):
        """恢复推进"""
        # 先应用干预队列
        self._apply_pending_interventions()
        self.state = self.STATE_RUNNING
        self._run_loop(self.engine.config.tick_speed)

    def step_once(self):
        """单步执行"""
        self.state = self.STATE_STEPPING
        self._apply_pending_interventions()
        result = self.engine.advance_tick()
        self.state = self.STATE_PAUSED
        self._notify_clients({"type": "tick_result", "result": result.to_dict()})
        return result

    # v2 新增：配置管理
    def update_config(self, modifications: dict):
        """运行时修改引擎配置"""
        config = self.engine.config
        self.config_history.append(config.copy())

        if "total_chapters" in modifications:
            new_total = modifications["total_chapters"]
            if new_total < config.total_chapters and self.engine.current_chapter > new_total:
                self._trigger_chapter_end()
            config.total_chapters = new_total

        if "ticks_per_chapter" in modifications:
            config.ticks_per_chapter = modifications["ticks_per_chapter"]

        if "auto_pause_between_chapters" in modifications:
            config.auto_pause_between_chapters = modifications["auto_pause_between_chapters"]

        if "chapter_end_behavior" in modifications:
            config.chapter_end_behavior = ChapterEndBehavior(modifications["chapter_end_behavior"])

        if "tick_speed" in modifications:
            config.tick_speed = modifications["tick_speed"]

        self._notify_clients({"type": "config_update", "config": config.to_dict()})

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

            # 章节间自动暂停（v2 新增）
            if result.chapter_end and self.engine.config.auto_pause_between_chapters:
                self.pause(f"第{self.engine.current_chapter}章结束，自动暂停供DM审阅")
                return

            # 模拟终止检查（v2 新增）
            if result.simulation_end:
                self.state = self.STATE_IDLE
                self._notify_clients({"type": "simulation_end", "reason": "达到总章节上限"})
                return

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

    # v2 新增：DM"不通过"时触发已有质量模块重写
    def require_rewrite(self, tick_id: int, reason: str):
        """
        DM 审查不通过，触发重写。
        根据 reason 路由到对应的已有质量模块。
        """
        self.snapshot_manager.create_snapshot(f"pre_rewrite_{tick_id}")

        if "人设" in reason or "性格" in reason:
            # 路由到 NarrativeCorrector
            self.engine.narrative_corrector.enforce_character_consistency(tick_range=(tick_id, tick_id))
        elif "违规" in reason or "禁止" in reason:
            self.engine.hard_constraint_ctrl.rebuild_blocklist()
        elif "世界规则" in reason:
            self.engine.world_rule_guard.add_rule(reason)
        elif "风格" in reason or "语气" in reason:
            # 路由到 PromptRegistry 修改风格参数
            if self.prompt_registry:
                self.prompt_registry.update_style_params({"tone": reason})
        elif "情节" in reason or "矛盾" in reason:
            self.engine.narrative_corrector.rewrite_with_constraint(tick_range=(tick_id, tick_id))

        # 重新生成该 tick 叙事
        result = self.engine.regenerate_tick(tick_id)
        return result

    def _apply_pending_interventions(self):
        """应用干预队列中的所有待处理干预"""
        for intervention_type, data in self.intervention_queue:
            handler = self._intervention_handlers.get(intervention_type)
            if handler:
                handler(data)
        self.intervention_queue.clear()
```

#### 3.8.3 API 路由

```python
# 在 app.py 中新增

from novel_world.engine.dm.dm_manager import DMManager
from novel_world.engine.config.engine_config import EngineConfig

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

# ── v2 新增：配置管理 API ──

@app.route("/api/dm/config", methods=["GET"])
def dm_get_config():
    if not dm_manager or not dm_manager.engine:
        return jsonify({"error": "引擎未初始化"}), 400
    config = dm_manager.engine.config
    return jsonify({
        "total_chapters": config.total_chapters,
        "ticks_per_chapter": config.ticks_per_chapter,
        "auto_pause_between_chapters": config.auto_pause_between_chapters,
        "chapter_end_behavior": config.chapter_end_behavior.value,
        "tick_speed": config.tick_speed,
    })

@app.route("/api/dm/config", methods=["PUT"])
def dm_update_config():
    data = request.get_json()
    dm_manager.update_config(data)
    return jsonify({"status": "ok"})

@app.route("/api/dm/config/validate", methods=["POST"])
def dm_validate_config():
    data = request.get_json()
    config = EngineConfig(**data)
    errors = config.validate()
    return jsonify({"valid": len(errors) == 0, "errors": errors})

# ── v2 新增：DM 不通过 → 触发重写 ──

@app.route("/api/dm/require_rewrite", methods=["POST"])
def dm_require_rewrite():
    data = request.get_json()
    result = dm_manager.require_rewrite(data["tick_id"], data["reason"])
    return jsonify({"status": "ok", "result": result.to_dict()})

# ── v2 新增：Prompt 管理 API ──

@app.route("/api/dm/prompts", methods=["GET"])
def dm_get_prompts():
    """获取所有 Prompt 模板及其版本"""
    if not dm_manager or not dm_manager.prompt_registry:
        return jsonify({"error": "PromptRegistry 未初始化"}), 400
    prompts = dm_manager.prompt_registry.list_all()
    return jsonify({"prompts": prompts})

@app.route("/api/dm/prompts/<prompt_id>", methods=["GET"])
def dm_get_prompt(prompt_id):
    """获取指定 Prompt 的当前版本和历史版本"""
    registry = dm_manager.prompt_registry
    current = registry.get_current(prompt_id)
    history = registry.get_history(prompt_id)
    return jsonify({"current": current, "history": history})

@app.route("/api/dm/prompts/<prompt_id>", methods=["PUT"])
def dm_update_prompt(prompt_id):
    """DM 修改 Prompt 模板（自动版本递增、热重载）"""
    data = request.get_json()
    registry = dm_manager.prompt_registry
    new_version = registry.update(prompt_id, data["template"], reason=data.get("reason", "DM modification"))
    return jsonify({"status": "ok", "new_version": new_version})

@app.route("/api/dm/prompts/<prompt_id>/rollback", methods=["POST"])
def dm_rollback_prompt(prompt_id):
    """回滚到指定版本"""
    data = request.get_json()
    registry = dm_manager.prompt_registry
    success = registry.rollback(prompt_id, data["version"])
    return jsonify({"status": "ok" if success else "version_not_found"})

@app.route("/api/dm/prompts/preview", methods=["POST"])
def dm_preview_prompt():
    """预览 Prompt 修改效果（使用样本上下文模拟生成）"""
    data = request.get_json()
    registry = dm_manager.prompt_registry
    preview = registry.preview(data["prompt_id"], data["template"], data.get("sample_context"))
    return jsonify({"preview": preview})

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

### 3.9 WebSocket 实时通信

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

### 3.10 Prompt 管理体系（v2 新增）

#### 3.10.1 设计目标

代码中散落了 13 个硬编码 prompt（详见缺口分析报告 §5.3），需要系统化管理。Prompt 管理是 DM 干预和 Timeline 检查的前提——没有可控的 prompt，DM 无法真正干预生成质量。

#### 3.10.2 Prompt Registry 核心设计

```python
# novel_world/engine/prompt/prompt_registry.py

import json
import hashlib
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional
from pathlib import Path

@dataclass
class PromptTemplate:
    """单个 Prompt 模板"""
    id: str                           # 唯一标识，如 "narrative_generation"
    name: str                         # 人类可读名称，如 "Tick叙事生成Prompt"
    category: str                     # 分类: "narrative" | "character" | "collision" | "world" | "analysis"
    role: str                         # System role: "system" | "user" | "assistant"
    template: str                     # 模板内容，支持 {variable} 占位符
    variables: List[str]              # 模板中使用的变量列表
    version: int = 1                  # 当前版本号
    created_at: str = ""              # 创建时间
    updated_at: str = ""              # 最后修改时间
    changelog: List[dict] = field(default_factory=list)  # 变更日志
    active: bool = True               # 是否当前生效

    def render(self, context: dict) -> str:
        """使用上下文变量渲染模板"""
        result = self.template
        for var in self.variables:
            placeholder = "{" + var + "}"
            if var in context:
                result = result.replace(placeholder, str(context[var]))
        return result

class PromptRegistry:
    """Prompt 注册表：集中管理所有 prompt，支持版本号、变更日志、热重载、回滚"""

    STORAGE_DIR = "novel_world/engine/prompt/prompt_templates/"
    HISTORY_FILE = "version_history.jsonl"

    def __init__(self, storage_dir: str = None):
        self.storage_dir = Path(storage_dir or self.STORAGE_DIR)
        self._prompts: Dict[str, PromptTemplate] = {}
        self._history: Dict[str, List[dict]] = {}  # prompt_id → [历史版本列表]
        self._load_all()

    def _load_all(self):
        """从磁盘加载所有模板和历史"""
        # 加载模板 JSON
        main_file = self.storage_dir / "templates.json"
        if main_file.exists():
            with open(main_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                for key, tmpl_data in data.items():
                    self._prompts[key] = PromptTemplate(**tmpl_data)

        # 加载历史 JSONL
        history_file = self.storage_dir / self.HISTORY_FILE
        if history_file.exists():
            with open(history_file, "r", encoding="utf-8") as f:
                for line in f:
                    record = json.loads(line.strip())
                    pid = record["prompt_id"]
                    if pid not in self._history:
                        self._history[pid] = []
                    self._history[pid].append(record)

    def get_current(self, prompt_id: str) -> Optional[PromptTemplate]:
        """获取当前生效的 prompt（DMManager 和 TimelineChecker 的主要入口）"""
        return self._prompts.get(prompt_id)

    def get_history(self, prompt_id: str) -> List[dict]:
        """获取指定 prompt 的所有历史版本"""
        return self._history.get(prompt_id, [])

    def list_all(self) -> dict:
        """列出所有 prompt（供 DM 面板展示）"""
        result = {}
        for pid, tmpl in self._prompts.items():
            result[pid] = {
                "id": tmpl.id,
                "name": tmpl.name,
                "category": tmpl.category,
                "version": tmpl.version,
                "active": tmpl.active,
                "updated_at": tmpl.updated_at,
            }
        return result

    def update(self, prompt_id: str, new_template: str, reason: str = "") -> int:
        """
        DM 修改 prompt 模板。
        自动版本递增、持久化、记录变更日志。
        返回新版本号。
        """
        if prompt_id not in self._prompts:
            raise KeyError(f"Prompt '{prompt_id}' not found")

        old = self._prompts[prompt_id]
        new_version = old.version + 1

        # 记录到历史
        history_record = {
            "prompt_id": prompt_id,
            "version": old.version,
            "template": old.template,
            "variables": old.variables,
            "saved_at": old.updated_at,
        }
        if prompt_id not in self._history:
            self._history[prompt_id] = []
        self._history[prompt_id].append(history_record)

        # 追加历史到磁盘
        with open(self.storage_dir / self.HISTORY_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(history_record, ensure_ascii=False) + "\n")

        # 更新当前版本
        old.template = new_template
        old.version = new_version
        old.updated_at = datetime.now().isoformat()
        old.variables = self._extract_variables(new_template)
        old.changelog.append({
            "version": new_version,
            "reason": reason,
            "timestamp": datetime.now().isoformat(),
        })

        # 持久化模板
        self._save_all()

        # 通知热重载（下一 tick 自动生效，无需重启引擎）
        self._on_hot_reload(prompt_id, new_version)

        return new_version

    def rollback(self, prompt_id: str, target_version: int) -> bool:
        """回滚到指定历史版本"""
        if prompt_id not in self._history:
            return False

        history = self._history[prompt_id]
        target_record = None
        for rec in history:
            if rec["version"] == target_version:
                target_record = rec
                break

        if not target_record:
            return False

        # 回滚即创建一个新版本，内容等于目标历史版本
        current = self._prompts[prompt_id]
        new_version = current.version + 1

        history_record = {
            "prompt_id": prompt_id,
            "version": current.version,
            "template": current.template,
            "variables": current.variables,
            "saved_at": current.updated_at,
        }
        if prompt_id not in self._history:
            self._history[prompt_id] = []
        self._history[prompt_id].append(history_record)

        current.template = target_record["template"]
        current.variables = target_record["variables"]
        current.version = new_version
        current.updated_at = datetime.now().isoformat()
        current.changelog.append({
            "version": new_version,
            "reason": f"Rollback to version {target_version}",
            "timestamp": datetime.now().isoformat(),
        })

        self._save_all()
        self._on_hot_reload(prompt_id, new_version)
        return True

    def update_style_params(self, params: dict):
        """
        DM 干预时修改风格参数（如 {tone} = "紧张" → "轻松"）。
        不修改模板本身，只修改 Prompt 变量映射表。
        """
        # 实现细节：维护一个 _style_overrides 字典
        # 在 render() 时优先使用 overrides 中的值
        pass

    def preview(self, prompt_id: str, template: str, sample_context: dict = None) -> str:
        """
        预览修改后的 prompt 输出效果（用于 DM 面板的"预览"功能）。
        使用样本上下文渲染模板，DM 可对比修改前后的差异。
        """
        temp_tmpl = PromptTemplate(
            id=prompt_id,
            name="preview",
            category="",
            role="system",
            template=template,
            variables=self._extract_variables(template),
        )
        rendered = temp_tmpl.render(sample_context or {})
        return rendered

    def _extract_variables(self, template: str) -> List[str]:
        """从模板字符串中提取 {variable} 变量名"""
        import re
        return re.findall(r"\{(\w+)\}", template)

    def _on_hot_reload(self, prompt_id: str, version: int):
        """热重载回调：通知所有注册的消费者 prompt 已更新"""
        # 下一 tick 自动使用新版本，无需重启引擎
        # NovelEngine 在每次调用 AI 前检查 PromptRegistry 版本
        pass

    def _save_all(self):
        """持久化所有模板到磁盘"""
        data = {}
        for pid, tmpl in self._prompts.items():
            data[pid] = {
                "id": tmpl.id,
                "name": tmpl.name,
                "category": tmpl.category,
                "role": tmpl.role,
                "template": tmpl.template,
                "variables": tmpl.variables,
                "version": tmpl.version,
                "created_at": tmpl.created_at,
                "updated_at": tmpl.updated_at,
                "changelog": tmpl.changelog,
                "active": tmpl.active,
            }
        with open(self.storage_dir / "templates.json", "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
```

#### 3.10.3 13 个 Prompt 的注册映射

从代码中提取的 13 个硬编码 prompt，迁移到 PromptRegistry 后的注册表：

| Prompt ID | 名称 | 分类 | 原始位置 |
|-----------|------|------|----------|
| `tian_dao` | 天道角色设定 | narrative | `backend/ai_client.py:tian_dao_prompt()` |
| `character_agent` | 角色Agent设定 | character | `backend/ai_client.py:character_agent_prompt()` |
| `world_generation` | 世界构建师 | world | `backend/ai_client.py:generate_world()` |
| `character_generation` | 角色批量生成 | character | `backend/ai_client.py:generate_characters()` |
| `content_analysis` | 编辑分析师 | analysis | `backend/ai_client.py:analyze_content()` |
| `chapter_narrative` | 章节正文生成 | narrative | `backend/narrative.py:generate_chapter()` |
| `world_event` | 世界事件决策 | narrative | `backend/narrative.py:generate_world_event()` |
| `collision_narrative` | 碰撞叙事 | collision | `backend/collision.py:process_collision()` |
| `tick_narrative` | Tick叙事生成 | narrative | `novel_world/engine/core/events.py:_build_prompts()` |
| `story_intro` | 故事开头 | narrative | `novel_world/engine/core/engine.py:_generate_story_intro()` |
| `collision_prompt` | 碰撞叙事Prompt | collision | `novel_world/engine/collision/collision_engine.py:_build_collision_prompt()` |
| `entry_narrative` | 角色入场叙事 | collision | `novel_world/engine/collision/collision_engine.py:_generate_entry_narrative()` |
| `chapter_aggregation` | 章节润色衔接 | narrative | `novel_world/engine/collision/collision_engine.py:_aggregate_chapter_text()` |

#### 3.10.4 DM 面板 - Prompt 管理界面

```
┌─────────────────────────────────────────────────────────────┐
│  📝 Prompt 管理                          [关闭]             │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  筛选: [全部 ▼]  搜索: [________________]                    │
│                                                              │
│  ┌───────────────────────────────────────────────────────┐  │
│  │ narrative_generation   Tick叙事生成    v12   [查看]    │  │
│  │ collision_prompt       碰撞叙事Prompt   v5   [查看]    │  │
│  │ tian_dao              天道角色设定     v3   [查看]    │  │
│  │ ...                                                   │  │
│  └───────────────────────────────────────────────────────┘  │
│                                                              │
│  ── 选中: collision_prompt (v5) ──                           │
│                                                              │
│  [模板编辑区]                                                │
│  ┌───────────────────────────────────────────────────────┐  │
│  │ 你是一位网文作家，擅长{style}风格。                    │  │
│  │ 当前场景：{scene_description}                         │  │
│  │ 角色A：{character_a} | 角色B：{character_b}             │  │
│  │ 要求：                                                │  │
│  │ 1. {requirement_1}                                    │  │
│  │ 2. {requirement_2}                                    │  │
│  │ ...                                                   │  │
│  └───────────────────────────────────────────────────────┘  │
│                                                              │
│  变量列表: style, scene_description, character_a, ...       │
│                                                              │
│  [预览修改效果]  [保存 (→v6)]  [回滚到 v4]  [查看历史]     │
│                                                              │
│  ── 变更历史 ──                                             │
│  v5: DM修改 - 增加"注重氛围和细节"  2026-07-16 14:30        │
│  v4: DM修改 - 战斗描写更激烈         2026-07-15 09:00        │
│  v3: 初始版本                        2026-07-10 10:00        │
└─────────────────────────────────────────────────────────────┘
```

#### 3.10.5 热重载机制

```python
# NovelEngine 中集成 PromptRegistry 的热重载

class NovelEngine:
    def __init__(self, ..., prompt_registry: PromptRegistry = None):
        self.prompt_registry = prompt_registry
        self._prompt_cache: Dict[str, PromptTemplate] = {}
        self._prompt_version_snapshot: Dict[str, int] = {}  # 记录上次使用的版本

    def _get_prompt(self, prompt_id: str) -> PromptTemplate:
        """获取 prompt，自动检测热重载（版本比对，零开销）"""
        if not self.prompt_registry:
            return self._prompt_cache.get(prompt_id)

        current = self.prompt_registry.get_current(prompt_id)
        if not current:
            return self._prompt_cache.get(prompt_id)

        cached_version = self._prompt_version_snapshot.get(prompt_id, -1)
        if current.version != cached_version:
            # 版本变更：更新缓存（热重载生效）
            self._prompt_cache[prompt_id] = current
            self._prompt_version_snapshot[prompt_id] = current.version
            # 可选：记录日志
            print(f"[PromptRegistry] Hot-reloaded '{prompt_id}' to v{current.version}")

        return self._prompt_cache[prompt_id]
```

#### 3.10.6 Prompt 合规度检查（TimelineChecker 集成）

参见 §2.2 维度七和 §2.4 中的 `FastCheck.prompt_compliance`。该检查：
- 在 FastCheck 层执行（零Token）
- 基于 NarrativeValidator 规则库和 PromptRegistry 当前生效的模板约束
- 检查叙事输出是否偏离了 system prompt 中定义的角色性格、语气风格、视角规则
- 发现偏离时产出 WARNING 级别 issue，DM 可在面板中查看并决定是否修改 prompt

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
│               Prompt修改   触发NarrativeCorrector│
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

**场景（v2新增）：Prompt 合规度检查发现角色语气偏离**

```
1. 检查触发：章节末全量检查（FastCheck 中的 prompt_compliance 维度）
2. 发现问题：WARNING 级别
   ┌─────────────────────────────────────────────┐
   │ ⚠️ WARNING: Prompt 合规度 - 角色 "叶辰"     │
   │   性格设定为"冷漠寡言"，但叙事中发现大量    │
   │   温暖对话（占比 > 40%）                     │
   │   → 建议：检查 prompt 中角色性格描述是否    │
   │     被 AI 遵循，或调整 prompt 约束强度      │
   ├─────────────────────────────────────────────┤
   │ 可选干预：                                    │
   │ [修改 narrative_generation prompt]            │
   │ [修改叶辰角色设定]                            │
   │ [忽略]                                        │
   └─────────────────────────────────────────────┘
3. DM 选择"修改 prompt" → 打开 Prompt 管理面板
4. 在 character_agent prompt 中增加约束："叶辰的对白不超过20字，不带感情色彩"
5. 保存 prompt（自动版本递增 + 热重载）
6. 回退到该 tick 重新生成 → TimelineChecker 验证 → PASS
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

    # v2 新增：Prompt 合规度检查策略
    check_prompt_compliance: bool = True  # 是否启用 Prompt 合规度检查
    prompt_compliance_template_ids: List[str] = field(default_factory=lambda: [
        "tian_dao", "character_agent", "collision_prompt", "tick_narrative"
    ])  # 对哪些 prompt 模板做合规度检查
```

### 4.4 DM 干预与已有质量模块的联动（v2 新增）

#### 4.4.1 DM"不通过"的完整处理链路

当 DM 审查检查报告后决定"不通过，要求重写"时：

```
DM 点击"不通过，要求重写"
        │
        ▼
DMManager.require_rewrite(tick_id, reason)
        │
        ├── 1. 创建干预前快照（snapshot_manager）
        │
        ├── 2. 根据 reason 路由到对应处理模块：
        │   ├── "人设崩塌" / "性格不一致"
        │   │   → NarrativeCorrector.enforce_character_consistency()
        │   │   → 确保不可击败角色、人设防崩塌规则被强制执行
        │   │
        │   ├── "违规词汇" / "禁止内容"
        │   │   → HardConstraintController.rebuild_blocklist()
        │   │   → NarrativeValidator 规则库追加新规则
        │   │
        │   ├── "世界规则违反"
        │   │   → WorldRuleGuard.add_rule()
        │   │
        │   ├── "风格/语气不对"
        │   │   → PromptRegistry.update_style_params()
        │   │   → 更新对应 prompt 模板的风格变量
        │   │
        │   └── "情节矛盾"
        │       → NarrativeCorrector.rewrite_with_constraint()
        │       → 基于 DM 指定的约束条件重新生成叙事
        │
        ├── 3. 应用修正后重新生成该 tick 叙事
        │
        └── 4. TimelineChecker.fast_check() 验证修正结果
            ├── PASS → 通知 DM，恢复运行
            └── 仍有问题 → 再次展示报告，回到步骤 2
```

#### 4.4.2 干预链路的模块依赖关系

```
DMManager
    ├── 依赖 → NarrativeCorrector     (人设/情节重写)
    ├── 依赖 → HardConstraintController (词表/规则)
    ├── 依赖 → WorldRuleGuard          (世界观规则)
    ├── 依赖 → PromptRegistry          (风格/Prompt修改)
    ├── 依赖 → SnapshotManager         (快照/回退)
    ├── 依赖 → NovelEngine             (重新生成tick)
    └── 依赖 → TimelineChecker         (修复验证)

TimelineChecker (v2)
    ├── 依赖 → PromptRegistry          (获取当前 prompt 做合规度检查)
    ├── 依赖 → NarrativeValidator      (复用规则库做 prompt 合规度匹配)
    ├── 依赖 → NarrativeCorrector      (AI辅助检查时参考校正规则)
    └── 依赖 → ConsistencyChecker      (继承数据对齐结果)
```

---

## 5. 实施路线图

### 阶段一：时间线检查核心（1-2天）

| 任务 | 说明 | 预计行数 |
|------|------|----------|
| 创建 `timeline_checker.py` | 实现 7 个维度的规则检查（含 Prompt 合规度） | ~600行 |
| 集成到 `NovelEngine.advance_tick()` | 在 tick 流程中插入检查调用 | ~30行修改 |
| 新增 API: `/api/check/timeline` | 手动触发检查 | ~40行 |
| 单元测试 | 覆盖各维度检查逻辑 | ~200行 |

### 阶段二：EngineConfig + PromptRegistry（1天）（v2 新增）

| 任务 | 说明 | 预计行数 |
|------|------|----------|
| 创建 `engine_config.py` | EngineConfig 数据结构 + 校验 | ~80行 |
| 创建 `prompt_registry.py` | PromptRegistry 核心 + 版本管理 + 热重载 | ~300行 |
| 迁移现有 Prompt | 从 7 个文件提取 13 个 prompt 到 templates.json | ~200行 |
| 集成到 NovelEngine | PromptRegistry 注入 + `_get_prompt()` 热重载 | ~50行修改 |
| 新增 API | `/api/dm/config`、`/api/dm/prompts/*` | ~80行 |

### 阶段三：DM 模式基础（2-3天）

| 任务 | 说明 | 预计行数 |
|------|------|----------|
| 创建 `dm_manager.py` | 核心状态机和运行循环（含配置管理和 Prompt 联动） | ~500行 |
| 创建 `breakpoint_manager.py` | 断点管理 | ~150行 |
| 创建 `snapshot_manager.py` | 快照与回退 | ~200行 |
| 创建 `intervention_queue.py` | 干预队列 | ~100行 |
| 新增 DM API 路由（/api/dm/*） | REST API 端点（含 require_rewrite） | ~250行 |
| 集成到 app.py | 初始化 DM 管理器 | ~50行 |

### 阶段四：质量管控层对接（1天）（v2 新增）

| 任务 | 说明 | 预计行数 |
|------|------|----------|
| DM → NarrativeCorrector 联动 | `require_rewrite()` 路由到 NarrativeCorrector | ~80行 |
| DM → HardConstraintController 联动 | 词表/规则动态更新 | ~40行 |
| DM → WorldRuleGuard 联动 | 世界观规则动态追加 | ~30行 |
| TimelineChecker → NarrativeValidator 联通 | Prompt 合规度检查复用规则库 | ~50行 |
| 适配层（backend ↔ novel_world/engine） | dm_adapter / check_adapter / prompt_adapter | ~300行 |
| 端到端集成测试 | DM"不通过"→重写→验证的完整链路 | ~100行 |

### 阶段五：Web 前端 DM 面板（1-2天）

| 任务 | 说明 |
|------|------|
| CSS/HTML 新增 DM 面板 | 底部可折叠面板（含启动配置区） |
| JS DM 管理器逻辑 | WebSocket 通信、UI 交互 |
| 干预表单弹窗 | 注入事件/修改角色/强制行动等表单 |
| 断点配置 UI | 可视化添加/删除/启停断点 |
| Prompt 管理界面 | 模板编辑、预览、版本回滚、变更历史 |
| 时间线检查结果展示 | 在 DM 面板中集成检查报告 |

### 阶段六：联动与优化（1天）

| 任务 | 说明 |
|------|------|
| 检查→暂停联动 | 配置自动暂停策略 |
| 干预后重新检查 | 干预 → 验证闭环 |
| Prompt 修改 → 热重载 → 重新生成 | 完整 Prompt 干预链路 |
| 检查结果可视化 | 时间线图表展示检查结果 |
| 压力测试与性能优化 | 确保检查不影响叙事生成性能 |

---

> **v2 设计总结**：在 v1 基础上，补充了三个关键遗漏项的完整设计——Prompt 管理体系（集中注册、版本管理、热重载、DM 联动）、章节数量设定（EngineConfig、DM 启动面板、运行时修改）、已有隐式检查层对齐（质量管控分层架构、DM 与 NarrativeCorrector 等模块的联动、双代码体系对接策略）。TimelineChecker 新增 Prompt 合规度检查维度，DM 模式具备了对 AI 生成质量的完整"暂停-审查-修改Prompt-重写-验证"闭环控制能力。
