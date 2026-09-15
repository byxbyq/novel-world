# Phase 1 P0: Tick 主循环重排 — 改动清单

## 概述

在 Adapter 适配层中，将角色移动逻辑从「全员无差别随机游走」重排为「目标导向移动优先、背景随机移动兜底」，使得有叙事目标的角色向其他角色方向移动以制造交互，而不是被随机漂移稀释主线张力。

**影响文件**：仅 `novel_world/adapter/adapter.py`（+ 本说明文档），不涉及 novel_world/engine 内部代码。

---

## 原来的执行顺序

### 1. `_nw_tick_once()` — 单个 Tick（原：第 ~306-317 行）

```
for char in all:
    随机 dx = random.choice([-1, 0, 1])
    随机 dy = random.choice([-1, 0, 1])
    更新 char.pos（边界 0~39, 0~24）

tick(chars)  # 碰撞检测
```

**问题**：无论角色有没有目标（如「前往落星崖寻找镇派剑谱」），移动方向都是纯随机，角色在 40×25 的网格上做无意义布朗运动。

### 2. `run_chapter()` — 章节 Tick 循环（原：第 ~397-412 行）

```
for _ in range(ticks_per_chapter):
    for char in all:
        随机 dx = random.choice([-1, 0, 1])
        随机 dy = random.choice([-1, 0, 1])
        更新 char.pos（边界 0~39, 0~24）
    tick(chars)
```

**问题**：与 `_nw_tick_once` 完全相同的问题，只是多了一层章节循环。

### novel_world/engine 内部（无改动）

- **`NovelEngine.advance_tick()`**（novel_engine.py L~260-330）：
  流程为「时间轴推进 → 目标推进 → 碰撞检测 → 规则守卫 → 一致性校验」，不含角色移动逻辑。
- **`CollisionEngine.tick()`**（collision_engine.py L~334-390）：
  流程为「全局 tick +1 → 过滤存活角色 → `_detect_collisions` → 碰撞优先级排序/去重」，不含角色移动逻辑。

**结论**：角色移动逻辑完全在 engine 外部（adapter / run_demo），不在 engine 内部。

---

## 修改后的执行顺序

### 新增 `_goal_directed_move()` 方法（adapter.py 第 ~296-337 行）

```python
def _goal_directed_move(self):
    """目标导向角色移动。

    规则：
    - 有目标（goal 非空）的角色：向最近的其他角色方向移动 → 制造交互
    - 无目标的角色：随机小幅移动（纯背景路人行为）
    """
    if not self._nw_characters:
        return

    nw_map_w = self._nw_world.map_size[0] if self._nw_world else 40
    nw_map_h = self._nw_world.map_size[1] if self._nw_world else 25

    alive = [c for c in self._nw_characters if c.alive]

    for char in alive:
        if not char.goal:
            # ── 无目标：纯背景路人，随机小幅移动 ──
            dx = random.choice([-1, 0, 1])
            dy = random.choice([-1, 0, 1])
        else:
            # ── 有目标：向最近的其他角色方向移动 ──
            others = [c for c in alive if c.id != char.id]
            if not others:
                dx = random.choice([-1, 0, 1])
                dy = random.choice([-1, 0, 1])
            else:
                nearest = min(others, key=lambda o:
                    abs(o.pos[0] - char.pos[0]) + abs(o.pos[1] - char.pos[1]))
                tx, ty = nearest.pos
                sx, sy = char.pos
                dx = 1 if tx > sx else (-1 if tx < sx else 0)
                dy = 1 if ty > sy else (-1 if ty < sy else 0)
                # 目标导向移动可以更激进（步长 1~2）
                if random.random() < 0.3:
                    dx *= 2
                    dy *= 2

        new_x = max(0, min(nw_map_w - 1, char.pos[0] + dx))
        new_y = max(0, min(nw_map_h - 1, char.pos[1] + dy))
        char.pos = (new_x, new_y)
```

### 修改后的 `_nw_tick_once()`（adapter.py 第 ~339-355 行）

```
确保章节已开始（如需要则 start_new_chapter）

_goal_directed_move()    ← 目标导向 + 背景随机
tick(chars)              ← 碰撞检测（不变）
```

### 修改后的 `run_chapter()`（adapter.py 第 ~430-437 行）

```
for _ in range(ticks_per_chapter):
    _goal_directed_move()    ← 目标导向 + 背景随机
    tick(chars)              ← 碰撞检测（不变）

finalize_chapter()           ← 章节收尾（不变）
```

---

## 变更说明

### 新增

| 项 | 说明 |
|---|---|
| `import random` | 新增顶部导入（原在函数内部 `import random`，已移除） |
| `_goal_directed_move()` | 新增 ~42 行方法，封装目标导向移动逻辑 |

### 修改

| 位置 | 原代码 | 新代码 |
|---|---|---|
| `_nw_tick_once()` L~306-317 | 内联随机移动循环（~12 行） | `self._goal_directed_move()` 一行调用 |
| `run_chapter()` L~397-412 | 内联随机移动循环 + `import random`（~17 行） | `self._goal_directed_move()` 一行调用 |

### 未改动

| 模块 | 说明 |
|---|---|
| `CollisionEngine.tick()` | 碰撞检测逻辑不变 |
| `NovelEngine.advance_tick()` | 调度层逻辑不变（原本就不含移动） |
| `_detect_collisions()` | 碰撞判定算法不变 |
| 叙事生成流程 | 碰撞后的叙事生成不变 |
| `run_demo.py` | 独立于 Adapter，不受影响 |

### 设计决策

1. **为何用「向最近角色移动」而非 faction/char_type 区分**：当前 Adapter 中所有角色的 `faction_id` 和 `char_type` 均未有效填充（见 adapter_todo_explanation.md 问题 2），因此退而使用 goal 字符串的非空判断，并以「向最近其他角色移动」作为收敛策略。这确保有叙事目标的角色彼此靠近、增加碰撞概率，而非被随机游走稀释。

2. **步长 1~2 的随机加速**：纯 ±1 步长在 40×25 网格上收敛太慢，30% 概率步长×2 适度加速角色相遇，不破坏碰撞逻辑。

3. **地图尺寸从 World 读取**：`nw_map_w` / `nw_map_h` 直接读取 `self._nw_world.map_size`，不再硬编码 `(40, 25)`，兼容非默认地图。

### 验证

- `run_demo.py` 运行通过，无报错（3 章 × 20 tick，正常运行）
- `python -c "from novel_world.adapter import EngineAdapter"` 导入成功，无语法错误
