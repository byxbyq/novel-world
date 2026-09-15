# Phase2 P1: 章节数量设定 + 自动收尾

> 实施日期：2026-07-17 | 状态：已完成

## 一、改动概要

| 文件 | 操作 | 说明 |
|------|------|------|
| `novel_world/adapter/adapter.py` | 修改 | run_chapter 检测 `is_last_chapter` 并传入叙事生成；新增 `_finalize_world` 终局结算方法；`_finalize_novel` 改用 PromptRegistry finale 模板 |
| `novel_world/engine/core/prompt_registry.py` | 修改 | `finale` 模板新增 `{final_context}` 注入点 |
| `frontend/index.html` | 修改 | DM 状态栏新增章节进度条 HTML 结构 |
| `frontend/style.css` | 修改 | 新增 `.chapter-progress-bar/fill/label` 样式 + `finale` 脉冲动画 |
| `frontend/app.js` | 修改 | dmPoll 进度条更新联动、`updateChapterProgress()` 函数、`dmStart` 重置警告、终局 alert 弹窗 |

## 二、章节终止逻辑

```
run_chapter(is_last_chapter=detected) →
  ├─ 非终章: generate_chapter(is_last_chapter=False) → 正常收尾
  └─ 终章:  _finalize_world() → 结算上下文注入 narrative
              generate_chapter(is_last_chapter=True) → 终局收尾 prompt
```

`tick()` 中的 `_finalize_novel` 由 total_chapters × ticks_per_chapter 触发，走相同的终局结算→finale 模板路径。

## 三、_finalize_world 终局结算

| 结算维度 | 规则 |
|----------|------|
| **势力结局** | 按成员数排序：霸主 / 中坚 / 衰微；检查敌对势力是否仍存活 |
| **角色结局** | 按已完成目标数判定：≥2 个 → "迎来归宿"；1 个 → "仍在追寻"；0 个 → "旅途延续" |
| **伏笔回收** | 从 TimelineChecker.unresolved_clues 提取超过半章未处理的伏笔，注入终局上下文要求回收 |

## 四、终局 Prompt 模板

`PromptRegistry.get("finale", ...)` 模板结构：

```
终局行为模式 → {end_behavior}
角色最终行动 → {actions_summary}
世界终局状态 → {world_end_state}
终局结算     → {final_context}（势力结局 + 角色结局 + 待回收伏笔）
叙事要求      → 收束伏笔 | 1000-2000 字 | 有力量感的结局
预期结局      → {ending_guidance}
```

## 五、前端进度条

- 随 DM 轮询自动更新 `[████████░░░░] 第 4/10 章`
- 终章自动切换红色脉冲动画 `finale` 样式
- 首次进入终章弹出 `alert("终局警告")` 提醒
- `dmStart` 重置进度条和警告状态
