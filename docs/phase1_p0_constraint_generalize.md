# Phase1 P0: HardConstraintController 可配置化改造

## 改造日期
2026-07-17

## 问题诊断

深度批判验证确认：`novel_world/engine/quality/hard_constraint_controller.py`（914行）的
`HardConstraintController` 将 Demo 故事「陈阳×苏晚」的角色名、主线阶段、关系类型等全部硬编码在类内部。
质量控制层与具体故事强耦合，换一个世界观即失效。

## 改造方案

方案A（推荐，最小改动）：新增 `constraints` 配置块从 `WorldConfig` 读取，不传则回退到内置 Demo 默认值。

## 改动清单

### 1. `backend/config.py` — WorldConfig 新增 `constraints` 字段

```python
@dataclass
class WorldConfig:
    ...
    constraints: dict = field(default_factory=dict)
```

字段结构：
```python
{
    "mainline_characters": ["主角A", "主角B"],
    "core_relation_type": "异性爱情",           # None = 不锁定
    "mainline_core_characters": ["核心角色..."] , # 默认同 mainline_characters
    "mainline_stages": {
        "stage_1": {"name": "...", "description": "...",
                    "keywords": [...], "min_narratives": N, "max_narratives": M},
        ...
    },
    "supporting_characters": {
        "配角A": {"probability": 0.3, "base_cooldown": 3},
        ...
    },
    "mainline_keywords": ["关键词1", ...],
    "completion_keywords": ["完成标志词1", ...],
    "ending_templates": ["收尾模板1", ...],
}
```

### 2. `hard_constraint_controller.py` — 全面改造

#### 新增内置 Demo 默认常量（~80行）
所有硬编码的值提升为模块级 `_DEFAULT_*` 常量，明确标注"仅在未传入 constraints 时使用"：

- `_DEFAULT_MAINLINE_CHARACTERS` = `["陈阳", "苏晚"]`
- `_DEFAULT_CORE_RELATION_TYPE` = `"异性爱情"`
- `_DEFAULT_MAINLINE_CORE_CHARACTERS` = `["林夏", "苏晴"]`
- `_DEFAULT_MAINLINE_STAGES` = 三阶段恋爱故事
- `_DEFAULT_SUPPORTING_CHARACTERS` = 赵磊/阿花/婴儿/猫
- `_DEFAULT_MAINLINE_KEYWORDS` / `_DEFAULT_COMPLETION_KEYWORDS` / `_DEFAULT_ENDING_TEMPLATES`

#### `HardState` — 去除硬编码默认值
- `配角_cooldown/概率/base_cooldown` → `field(default_factory=dict)`，由 controller 初始化时填充
- `core_relation_type` → 空字符串，由 controller 初始化时填充
- `mainline_core_characters` → `field(default_factory=list)`，由 controller 初始化时填充

#### `HardConstraintController.__init__` — 新增 `constraints` 参数
```python
def __init__(self, theme: str = "日常", constraints: dict = None):
```
所有实例属性从 `constraints` 中读取，缺失项回退到 `_DEFAULT_*`：
- `self.mainline_characters`
- `self.mainline_stages`
- `self.mainline_keywords`
- `self.completion_keywords`
- `self.ending_templates`
- `self.core_relation_type`
- `self._mainline_core_chars`
- `self._supporting_names` / `_supporting_cooldown` / `_supporting_prob` / `_supporting_base_cd`

#### 方法中硬编码引用全部替换

| 原引用 | 替换为 |
|--------|--------|
| `["苏晚","陈阳","约会",...]` | `self.mainline_keywords` |
| `"陈阳" in narrative and "苏晚" in narrative` | `all(ch in narrative for ch in self.mainline_characters[:2])` |
| `["赵磊","阿花","婴儿","猫"]` | `self._supporting_names` |
| `MAINLINE_STAGES.get(...)` | `self.mainline_stages.get(...)` |
| `["stage_1","stage_2","stage_3"]` | `list(self.mainline_stages.keys())` |
| `["确定关系","在一起",...]` | `self.completion_keywords` |
| 收尾模板列表 | `self.ending_templates` |
| `"林夏"` (硬编码替换) | `self.state.mainline_core_characters[0]` |

#### `get_hard_controller()` — 新增 `constraints` 参数
```python
def get_hard_controller(theme="日常", constraints=None) -> HardConstraintController
```

#### 保留的向后兼容性
- `MAINLINE_STAGES` 全局常量仍然存在，指向 `_DEFAULT_MAINLINE_STAGES`
- 不传 `constraints` 时行为与改造前完全一致
- 所有原有 API 签名不变

## 验证

```bash
# 测试1：不传 constraints — Demo 默认值
ctrl = get_hard_controller()
# → mainline_characters = ["陈阳", "苏晚"]
# → stages = ["stage_1", "stage_2", "stage_3"]

# 测试2：自定义 constraints
ctrl = HardConstraintController(constraints={
    "mainline_characters": ["张三", "李四"],
    "core_relation_type": "师徒关系",
})
# → mainline_characters = ["张三", "李四"]

# 测试3：空 constraints — 回退默认值
ctrl = HardConstraintController(constraints={})
# → 行为与不传完全一致

# 测试4：叙事校验通过
ctrl.validate_narrative_hard("陈阳在街道上遇到了苏晚，两人一起去了咖啡馆约会")
# → 通过，未被拦截
```

## 未完成项（TODO）

- [ ] 后端 `world_builder.py` 中新增约束编辑入口（改动较大，标记 TODO）
- [ ] 前端 `world_config_tab` 中新增约束编辑 UI（改动较大，标记 TODO）
- [ ] `app.py` 中将 `WorldConfig.constraints` 传入 `get_hard_controller()`（当前 controller 未被 app.py 直接使用，待集成时处理）

## 影响范围

- 本次改动**零破坏性**：所有原有调用方不传 constraints 时自动回退到 Demo 默认值
- 换世界观时只需在 `WorldConfig` 中增加 `constraints` 配置块即可
- `backend/config.py` 新增一个可选字段
- `hard_constraint_controller.py` 内部重构，对外 API 向前兼容
