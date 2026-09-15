# Phase1 P1: EngineConfig 标准化 & main_objective 扩展

> **日期**: 2026-07-17  
> **状态**: 完成  
> **关联**: Phase1 P0（数据模型统一）→ Phase1 P1（引擎配置标准化）

---

## 背景

深度批判验证结论：
- World 类缺少世界级目标字段
- `max_chapters` 配置缺失  
- 引擎配置散落在 `run_demo.py` 硬编码常量 + `backend/engine_config.py` 雏形中
- design document v2 已设计 `EngineConfig` 和 `WorldConfig.main_objective`

---

## 改动概览

| 文件 | 改动类型 | 说明 |
|------|----------|------|
| `backend/engine_config.py` | **扩展** | EngineConfig 新增 `tick_speed` / `npc_filter_enabled` / `offline_mode` / `ai_provider`；调整默认值 |
| `backend/config.py` | **扩展** | WorldConfig 新增 `engine_config` 字段 + `main_objective_weight` 字段；导入 EngineConfig |
| `backend/engine.py` | **修改** | `align_goals_to_main_objective` 权重计算接入 `main_objective_weight` 全局缩放系数 |
| `novel_world/engine/core/world.py` | **新增属性** | World 类新增 `main_objective: str` 属性 |
| `run_demo.py` | **重构** | 导入 `EngineConfig`，创建标准化配置实例；硬编码常量改为读取 config；设置世界主线目标 |

---

## 详细改动

### 1. `backend/engine_config.py` — EngineConfig 扩展

原有 4 个字段，扩展到 9 个：

```python
@dataclass
class EngineConfig:
    # ── 章节节奏控制 ──
    total_chapters: int = 10             # 原默认 3 → 10
    ticks_per_chapter: int = 20          # 不变
    tick_speed: str = "normal"           # 【新增】slow / normal / fast
    auto_pause_between_chapters: bool = True  # 不变

    # ── 终局控制 ──
    end_behavior: str = "wrap_up"        # 原 "auto_epilogue" → "wrap_up"（对齐任务定义）
    expected_ending: str = ""            # 不变

    # ── 运行模式 ──
    npc_filter_enabled: bool = False     # 【新增】
    offline_mode: bool = False           # 【新增】
    ai_provider: str = "local"           # 【新增】local / api / none
```

> **兼容性**：`end_behavior` 变更安全（该字段当前未被任何 `.py` 消费，仅定义）。

### 2. `backend/config.py` — WorldConfig 接入 EngineConfig

```python
# 新增导入
from .engine_config import EngineConfig

# WorldConfig 新增字段
engine_config: EngineConfig = field(default_factory=EngineConfig)  # 引擎运行时配置
main_objective_weight: float = 1.0                                   # 主线权重缩放系数
```

世界主线目标已存在 (`main_objective`) + `world_stage` + `advance_world_stage()`。本次仅补齐权重控制参数。

### 3. `backend/engine.py` — 权重缩放接入

`align_goals_to_main_objective()` 中权重计算全部乘以 `main_objective_weight`：

```python
weight_mul = self.world.config.main_objective_weight
# high:     (1.5 + ...) * weight_mul
# low:      (0.3 + ...) * weight_mul  
# neutral:  1.0 * weight_mul
```

`weight_mul = 1.0` 时行为与改动前完全一致。

### 4. `novel_world/engine/core/world.py` — 补充 main_objective

```python
class World:
    def __init__(...):
        ...
        self.main_objective: str = ""  # 世界级主线目标
```

该字段由 `run_demo.py` 写入，供引擎组件读取（后续阶段 DM 模式做自动拆解绑定）。

### 5. `run_demo.py` — 配置化重构

**Before** (硬编码):
```python
TOTAL_CHAPTERS = 3
TICKS_PER_CHAPTER = 20
```

**After** (配置驱动):
```python
from backend.engine_config import EngineConfig

engine_config = EngineConfig(
    total_chapters=3,
    ticks_per_chapter=20,
    tick_speed="normal",
    end_behavior="wrap_up",
    ai_provider="none",
    offline_mode=True,
)

TOTAL_CHAPTERS = engine_config.total_chapters
TICKS_PER_CHAPTER = engine_config.ticks_per_chapter
```

同时设置了世界级主线目标：
```python
world.main_objective = "李青云在落星崖击败魔尊玄冥，寻回镇派剑谱，重振天机阁"
```

---

## 验证结果

```
python run_demo.py
```

- 3 章 × 20 tick 正常运行，**0 报错**
- 碰撞检测正常：6 次碰撞（目标对冲 / 势力冲突 / 能力对冲 ×3 / 感知对冲）
- 章节生成正常，小说导出成功
- 控制台输出确认 `EngineConfig` 字段生效：
  ```
  [Step 8] 开始生成小说（3章 x 20 tick）...
    -> 引擎配置：speed=normal, ai=none
  ```

---

## 待后续阶段接入

| 功能 | EngineConfig 字段 | 当前状态 | 后续阶段 |
|------|-------------------|----------|----------|
| 推演速度控制 | `tick_speed` | 已定义，未消费 | P2 runtime 调速 |
| NPC 过滤 | `npc_filter_enabled` | 已定义，未消费 | 需要 NPC 角色标记支持 |
| 离线模式 | `offline_mode` | demo 中使用，未在 engine 中校验 | P2 统一降级逻辑 |
| main_objective 自动拆解 | `main_objective` + `main_objective_weight` | 手动设置，备用 | 阶段2 DM 模式 |
