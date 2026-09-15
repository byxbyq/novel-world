# Phase2 P1: DM 干预功能 改动清单

## 改动总览

| 文件 | 类型 | 核心内容 |
|------|------|----------|
| `novel_world/engine/dm_state.py` | **修改** | 新增干预日志 + `execute_command` 四类指令执行器 + `get_intervention_context` / `clear_interventions` |
| `novel_world/adapter/adapter.py` | **修改** | 新增 `current_chapter_events`、`get_character`、`inject_world_event`；`run_chapter` 注入干预上下文到叙事生成 |
| `backend/narrative.py` | **修改** | `generate_chapter` 新增 `intervention_context` 参数，追加到 AI prompt |
| `app.py` | **修改** | `/api/dm/inject` 实际执行指令；新增 `/api/dm/characters`；`/api/dm/state` 返回 `intervention_log` |
| `frontend/index.html` | **修改** | DM 控制栏下方新增干预面板（角色修改 / 事件注入 / 添加目标 / 干预日志） |
| `frontend/app.js` | **修改** | 干预面板 JS：角色下拉填充、三类干预提交、日志刷新；`dmPoll` 集成面板显隐控制 |
| `frontend/style.css` | **修改** | 干预面板样式（橙色主题、表单行、日志列表） |

## 一、DMController 干预执行器

### 文件：`novel_world/engine/dm_state.py`

#### 1.1 干预日志存储

```python
self._intervention_log: list[dict] = []  # __init__ 中新增
```

每条日志包含 `tick` / `chapter` / `type` / `cmd`。

#### 1.2 `execute_command(cmd: dict) -> dict`

统一入口，按 `cmd["type"]` 分发到四个执行器：

| 指令类型 | 字段 | 行为 |
|----------|------|------|
| `modify_character` | name, field, value | 修改角色属性（target→long_term_goal / personality→config.personality / position→current_location / mood→current_mood） |
| `inject_event` | description | 调用 `engine.inject_world_event(cmd)` 追加到 `current_chapter_events` |
| `force_move` | name, position | 修改 `current_location` + 同步 `_backend_world.character_positions` |
| `add_goal` | name, goal, weight | `char.add_goal(description, priority)` 其中 priority = max(1, min(10, int(weight * 5))) |

所有执行在线程锁 `_lock` 保护下进行。

#### 1.3 叙事化上下文

```python
def get_intervention_context(self) -> str:
    """
    格式化干预日志为 AI prompt：
    [系统] DM 干预记录：
    - 第 5 Tick：修改 李青云.target = "寻找失落的卷轴"
    - 第 8 Tick：注入事件："天空出现异象..."
    请在后续叙事中自然融入以上干预的后果。
    """
```

`clear_interventions()` 在章节叙事生成后清空。

## 二、EngineAdapter 干预支持

### 文件：`novel_world/adapter/adapter.py`

#### 2.1 新增属性

```python
self.current_chapter_events: list[str] = []  # __init__ 中新增
```

#### 2.2 新增方法

```python
def get_character(self, name: str) -> CharacterAgent:
    """按名称查找角色，未找到抛出 ValueError"""

def inject_world_event(self, cmd: dict):
    """追加事件描述到 current_chapter_events"""
```

#### 2.3 `run_chapter` 修改

叙事生成（步骤4）前获取干预上下文，传入 `generate_chapter`；完成后清空干预日志和章节事件：

```python
intervention_context = dm_controller.get_intervention_context() if dm_controller else ""
narrative = self._narrator.generate_chapter(
    ..., intervention_context=intervention_context,
)
# 清理
dm_controller.clear_interventions()
self.current_chapter_events.clear()
```

## 三、叙事生成器

### 文件：`backend/narrative.py`

`generate_chapter` 新增 `intervention_context: str = ""` 参数。非空时追加到 user prompt 末尾：

```python
if intervention_context:
    prompt += f"\n\n{intervention_context}"
```

确保 AI 在生成章节正文时，将 DM 干预信息作为"已发生事实"自然融入叙事。

## 四、后端 API

### 文件：`app.py`

#### 4.1 `/api/dm/inject` (POST) — 实际执行

```python
data = request.get_json() or {}
valid_types = {"modify_character", "inject_event", "force_move", "add_goal"}
result = dm.execute_command(data)
```

替换原占位实现。

#### 4.2 `/api/dm/characters` (GET) — 新增

返回角色列表（name / mood / location / target），供干预面板角色下拉框填充。

#### 4.3 `/api/dm/state` (GET) — 增强

响应新增 `intervention_log` 字段，包含最近干预记录。

## 五、前端干预面板

### 文件：`frontend/index.html`

DM 控制栏和章节内容之间新增 `#dm-intervention-panel`（默认隐藏，PAUSED 时显示），包含：

- **角色修改**：角色选择（下拉）+ 字段选择（目标/性格/位置/情绪）+ 值输入 + 应用按钮
- **事件注入**：事件描述（文本域）+ 注入按钮
- **添加目标**：角色选择（下拉）+ 目标描述 + 添加按钮
- **干预日志**：最近干预记录列表

### 文件：`frontend/app.js`

新增函数：

| 函数 | 功能 |
|------|------|
| `updateInterventionPanel(dmState)` | 根据 DM 状态显隐面板；首次 PAUSED 时加载角色列表 |
| `loadIntervCharacters()` | 调用 `/api/dm/characters` 填充两个角色下拉框 |
| `dmInjectModify()` | 提交 `modify_character` 指令 |
| `dmInjectEvent()` | 提交 `inject_event` 指令 |
| `dmInjectGoal()` | 提交 `add_goal` 指令 |
| `sendIntervention(cmd)` | 统一 POST `/api/dm/inject`，显示结果 |
| `refreshIntervLog()` | 从 `/api/dm/state` 拉取 `intervention_log` 渲染到日志区 |

`dmPoll()` 集成：状态为 PAUSED 时调用 `updateInterventionPanel` 和 `refreshIntervLog`。

### 文件：`frontend/style.css`

新增 `.dm-intervention-panel` 及相关子类样式（橙色主题，与 DM 控制栏区分）。

## 六、数据流总览

```
用户点击 [应用/注入/添加]
  → dmInjectModify/Event/Goal()
    → POST /api/dm/inject {type, ...}
      → DMController.execute_command()
        → 修改角色数据 / 记录事件
        → 追加 _intervention_log
      → 返回 {success, message}
    → 更新 status-msg

用户点击 [继续/单步]
  → dmResume / dmStep()
    → dm._run_loop() → engine.run_chapter(dm_controller=self)
      → dm_controller.get_intervention_context()
      → generate_chapter(..., intervention_context=...)
        → prompt += "\n\n[系统] DM 干预记录：..."
        → AI 叙事中自然融入干预
      → dm_controller.clear_interventions()
```

## 七、安全约束

- 所有干预必须在 PAUSED 状态下执行（前端仅 PAUSED 时显示面板，后端不强制校验但设计如此）
- `execute_command` 在 `_lock` 保护下执行，与推演线程互斥
- 角色查找失败抛出 `ValueError`，被 `execute_command` 捕获返回错误
- 不支持的 `cmd_type` 返回 400
