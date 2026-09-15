# Phase2 P0: DM 状态机 + WebSocket 通道（轮询方案）改动清单

> 日期：2026-07-17
> 状态：已完成

---

## 概述

实现 DM 模式状态机，支持暂停/继续/单步/终止推演。采用 HTTP 轮询方案替代 WebSocket，最小化对 Flask 架构的改动。

**状态机**：`IDLE → RUNNING ⇄ PAUSED → STOPPED`

---

## 改动文件清单

| # | 文件 | 改动类型 | 说明 |
|---|------|----------|------|
| 1 | `novel_world/engine/dm_state.py` | **新建** | DM 状态机 + DMController |
| 2 | `novel_world/adapter/adapter.py` | 修改 | `run_chapter` 增加 DM 检查点 + `_dm_sync_state` 辅助方法 |
| 3 | `app.py` | 修改 | 导入 DM 模块 + 全局 dm 实例 + 7 个 DM API 端点 |
| 4 | `frontend/index.html` | 修改 | 新增 DM 控制栏 HTML |
| 5 | `frontend/app.js` | 修改 | 新增 DM 控制 JS 逻辑（轮询 + 按钮处理） |
| 6 | `frontend/style.css` | 修改 | 新增 DM 控制栏样式 |

---

## 1. novel_world/engine/dm_state.py（新建）

### 核心类

**DMState 枚举**：`IDLE | RUNNING | PAUSED | STOPPED`

**DMController 类**（线程安全）：

| 方法 | 状态转换 | 说明 |
|------|----------|------|
| `start(title)` | IDLE → RUNNING | 启动后台推演线程 |
| `pause()` | RUNNING → PAUSED | 暂停 Tick 推进 |
| `resume()` | PAUSED → RUNNING | 继续推演 |
| `step_once()` | PAUSED → RUNNING(单帧) | 执行 1 Tick 后自动 PAUSED |
| `stop()` | 任意 → STOPPED | 终止推演 |
| `reset()` | STOPPED → IDLE | 清理状态准备下一轮 |
| `get_state()` | - | 返回当前状态字典（供前端轮询） |

### 内部机制
- `_run_loop(title)` — 后台线程主循环，调用 `engine.run_chapter(title, dm_controller=self)`
- `_checkpoint()` — Tick 边界检查：RUNNING 继续 / PAUSED 阻塞 / STOPPED 抛 InterruptedError
- `_post_tick_checkpoint()` — 单步模式支持：执行完当前 tick 自动回到 PAUSED
- 使用 `threading.Event` 实现高效的跨线程状态同步

---

## 2. novel_world/adapter/adapter.py（修改 5 处）

### 2.1 run_chapter 签名变更
```python
def run_chapter(self, title: str = "", dm_controller=None) -> dict:
```

### 2.2 新增 DM 检查点（4 处）

| 位置 | 行号附近 | 说明 |
|------|----------|------|
| 世界事件后 | L402 | 天道事件生成完毕 → checkpoint |
| 角色行动后 | L419 | 所有角色行动完毕 → checkpoint |
| 碰撞循环内 | L451 | 每个 novel_world Tick 前 → checkpoint（**核心**） |
| 碰撞合并后 | L490 | 碰撞检测完毕 → checkpoint |

### 2.3 新增 `_dm_sync_state` 辅助方法
```python
def _dm_sync_state(self, dm_controller, chapter_log=None):
    """同步 tick/chapter 信息到 DM 控制器"""
```
每个检查点前调用，确保 `dm_controller.current_tick` 等信息实时更新。

---

## 3. app.py（修改 2 处 + 新增 7 个端点）

### 3.1 导入
```python
from novel_world.engine.dm_state import DMController, DMState
```

### 3.2 全局实例
```python
dm = DMController(engine)
```

### 3.3 新增 API 端点

| 方法 | 端点 | 说明 |
|------|------|------|
| GET | `/api/dm/state` | 返回当前 DM 状态（含 tick/chapter/错误信息） |
| POST | `/api/dm/start` | 启动后台推演（校验初始化、API Key、状态冲突） |
| POST | `/api/dm/pause` | 暂停推演 |
| POST | `/api/dm/resume` | 继续推演 |
| POST | `/api/dm/step` | 单步执行 1 个 Tick |
| POST | `/api/dm/stop` | 终止推演 |
| POST | `/api/dm/inject` | 预留：DM 指令注入 |
| POST | `/api/dm/snapshot` | 预留：创建快照 |
| POST | `/api/dm/rollback` | 预留：回退快照 |

---

## 4. frontend/index.html（修改 1 处）

在 `.chapter-header` 与 `#chapter-content` 之间插入 DM 控制栏：

```html
<div id="dm-control-bar" class="dm-control-bar">
  <div class="dm-buttons">
    <button>▶ 开始推演</button>
    <button>⏸ 暂停</button>
    <button>▶ 继续</button>
    <button>⏭ 单步</button>
    <button>⏹ 终止</button>
  </div>
  <div class="dm-status">
    <span>状态: IDLE</span>
    <span>Tick: 0/0 | 章节: 0/0</span>
  </div>
</div>
```

---

## 5. frontend/app.js（新增 ~150 行）

### 核心函数

| 函数 | 说明 |
|------|------|
| `dmStart()` | POST `/api/dm/start` → 启动轮询 |
| `dmPause()` | POST `/api/dm/pause` |
| `dmResume()` | POST `/api/dm/resume` |
| `dmStep()` | POST `/api/dm/step` → 单步后自动 paused |
| `dmStop()` | POST `/api/dm/stop` → 确认弹窗 |
| `updateDMButtons(state)` | 根据状态启用/禁用按钮 |
| `dmStartPolling()` | 启动 1s 间隔轮询 |
| `dmStopPolling()` | 停止轮询 |
| `dmPoll()` | 轮询主逻辑：更新状态标签、进度、按钮、结果展示 |

### 按钮状态表

| DM状态 | 启用按钮 |
|--------|----------|
| IDLE | 开始推演 |
| RUNNING | 暂停、终止 |
| PAUSED | 继续、单步、终止 |
| STOPPED | 开始推演 |

---

## 6. frontend/style.css（新增 ~80 行）

新增 `.dm-control-bar`、`.dm-btn`、`.dm-status` 等样式，状态颜色区分：
- IDLE: 灰色
- RUNNING: 绿色加粗
- PAUSED: 橙色加粗
- STOPPED: 红色加粗

---

## 架构要点

```
用户点击 [▶ 开始推演]
  → POST /api/dm/start
  → DMController.start() 启动后台线程
  → 前端 1s 轮询 GET /api/dm/state
  → 后台线程调用 engine.run_chapter(title, dm_controller=self)
  → run_chapter 在 4 个检查点处调用 dm_controller._checkpoint()
  → 用户点击 [⏸ 暂停]  → PAUSED → 检查点阻塞
  → 用户点击 [▶ 继续]  → RUNNING → 检查点通过
  → 用户点击 [⏭ 单步]  → 执行 1 Tick → 自动 PAUSED
  → 用户点击 [⏹ 终止]  → STOPPED → 抛出 InterruptedError
  → 推演完成 → 前端自动刷新章节内容
```

---

## 验证方式

1. 启动 `python app.py`
2. 浏览器打开 `http://127.0.0.1:5000`
3. 完成世界和角色设定 → 启动天道引擎
4. 点击 DM 栏「开始推演」→ 观察状态从 IDLE → RUNNING
5. 点击「暂停」→ 观察状态变为 PAUSED，Tick 停止推进
6. 点击「单步」→ 观察 Tick+1 后自动回到 PAUSED
7. 点击「继续」→ 推演恢复
8. 点击「终止」→ 推演停止，可重新开始
