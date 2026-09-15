# 阶段2 P1：TimelineChecker Fast 规则检查 — 改动清单

## 概述

实现 TimelineChecker 的 Fast 层——纯规则、零 AI 调用的时间线一致性检查。覆盖 5 个检测维度，接入 Adapter 的 Tick 循环，新增 API + 前端面板。

---

## 改动的 6 个文件

| 文件 | 操作 | 说明 |
|------|------|------|
| `novel_world/engine/quality/timeline_checker.py` | **新增** | Fast 规则检查核心类，5 个检测维度 |
| `novel_world/adapter/adapter.py` | **修改** | 导入 + 实例变量 + Tick 循环接入 + 3 个辅助方法 |
| `app.py` | **修改** | 新增 2 个 API 端点（issues / report） |
| `frontend/index.html` | **修改** | DM 干预面板新增「时间线检查」Tab |
| `frontend/app.js` | **修改** | 新增 `refreshTimelineIssues()` + DM 轮询集成 |
| `frontend/style.css` | **修改** | 新增 Timeline badge/entry 样式 |

---

## 五维度 Fast 检测规则

| 维度 | 方法 | 检测内容 | 严重度 |
|------|------|----------|--------|
| **1. 时间回溯** | `_check_temporal_order` | Tick 必须递增；time_marker 不能倒退（morning→evening→night 顺序） | ERROR / WARNING |
| **2. 角色一致性** | `_check_character_consistency` | 角色名单变化（消逝/新增）需有叙事理由；位置跳变不超过合理范围；关系反转需有冲突事件 | WARNING / INFO |
| **3. 物品一致性** | `_check_item_consistency` | 归属变更需有交接叙事；同一物品不能同时出现在两处 | WARNING / ERROR |
| **4. 世界规则** | `_check_world_rules` | 从 WorldConfig.rules 逐条解析："X 只存在于 Y" / "禁止 X" / "X 不能 Y" 三种约束模板 | ERROR |
| **5. 伏笔追踪** | `_check_clues` | 正则匹配埋设伏笔；识别回收叙事；超期未回收（30 Tick 阈值）警告 | INFO / WARNING |

---

## Adapter 集成

### Tick 级别检查
在 `run_chapter()` 的 novel_world Tick 循环内部，每次 `_nw_collision.tick()` 后调用 `_nw_tick_timeline_check(tick_i)` — 轻量检查（仅 Tick 顺序 + 角色位置）。

### 章节级别检查
在 `run_chapter()` 叙事生成完成后，调用 `_run_timeline_check(narrative, dm_controller)` — 全维度检查（含叙事文本分析、世界规则、伏笔）。

### 新增方法
```python
adapter._run_timeline_check(narrative, dm_controller)  # 全维度检查
adapter._nw_tick_timeline_check(tick_i)                  # Tick 级轻量检查
adapter._extract_character_relations(char)               # 角色关系提取
adapter.get_timeline_issues()                            # 获取所有问题
adapter.get_timeline_report()                            # 获取报告
```

---

## API

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/timeline/issues` | GET | 获取所有待解决的时间线问题列表 |
| `/api/timeline/report` | GET | 获取检查报告（含未回收/已回收伏笔统计） |

---

## 前端面板

DM 干预面板新增「时间线检查」Tab，包含：

- **刷新按钮** + 问题统计摘要（blocker/error/warning/info 计数）
- **问题列表** — 按时间倒序，每条含：
  - 严重度标签（颜色区分）
  - 检测维度
  - 位置（章节/Tick）
  - 问题描述 + 修复建议
- **未回收伏笔列表** — 显示伏笔内容 + 已埋设时长

### 自动刷新
DM 暂停状态下，1 秒轮询自动刷新时间线检查结果。

---

## 数据流

```
章节推演 → Tick 循环
  ├─ 每 Tick：_nw_tick_timeline_check() → 时间回溯 + 角色位置
  └─ 叙事生成后：_run_timeline_check()
       → TimelineChecker.check()
         → 5 个维度逐项检查
           → 返回 TimelineIssue 列表
             → 写入日志 + 推送 DM 通知（error/blocker）
             → API 可查询
             → 前端面板渲染
```

---

## 验证要点

1. **Tick 顺序**：推演若干 Tick 后，检查报告中的 `_prev_tick` 严格递增
2. **角色跳变**：手动制造角色瞬间移动到远处 → 应检测到 WARNING
3. **世界规则**：在 WorldConfig.rules 中设置 "魔法只存在于秘境" → 叙事中出现非秘境魔法应报 ERROR
4. **伏笔回收**：叙事中出现「神秘的玉佩」→ 30 Tick 后仍未提及 → 报告 WARNING
5. **API**：`GET /api/timeline/issues` 返回问题列表 JSON 格式正确
6. **前端**：DM 暂停后切换到「时间线检查」Tab → 显示统计和问题列表
