# Phase2 P1: 天意指引 改动清单

> 日期：2026-07-17
> 状态：已完成

---

## 一、功能概述

天意指引是 DM 干预管线的上层封装 —— DM 以"天道/命运"身份向单个角色传递信息，并通过梦境/顿悟/天象/偶遇/内心独白五种叙事形式自然融入小说正文。

核心设计原则：**复用而非重建**。天意指引不发明新的注入通道，而是构造特殊的 `inject_event` 指令，走已有 DM 干预管线。导航性描述作为 `description` 字段存入 `_intervention_log`，在下一章叙事生成时由 `get_intervention_context()` 格式化注入 AI prompt。

---

## 二、改动文件

| 文件 | 改动量 | 核心内容 |
|------|--------|----------|
| `novel_world/engine/divine_guidance.py` | **新增** ~90 行 | DivineGuidance 核心类：GuidanceForm / GuidanceStrength 枚举，6种形式模板，send_guidance() 构造叙事化 inject_event |
| `app.py` | +55 行 | 导入 divine_guidance 模块，初始化全局 divine 实例，新增 `POST /api/dm/guidance` 端点 |
| `frontend/index.html` | +57 行 | 干预面板改造为 Tab 结构（"数据干预" + "天意指引"）；天意指引 Tab 含角色选择/内容输入/形式选择/强度选择/发送按钮 |
| `frontend/app.js` | +70 行 | Tab 切换事件委托、loadIntervCharacters 扩展填充 guidance-char-select、dmSendGuidance() 发送逻辑、refreshIntervLog 增强识别天意指引条目 |
| `frontend/style.css` | +75 行 | Tab 样式（.interv-tabs / .interv-tab / .interv-tab-content）、天意发送按钮样式、guidance-msg 成功/错误样式 |

---

## 三、核心数据流

```
暂停 → 切换至「天意指引」Tab
  → 选择角色 / 输入内容 / 选择形式强度
  → POST /api/dm/guidance
    → divine.send_guidance()
      → 构造 inject_event cmd（description 含叙事模板）
      → dm.execute_command(cmd)
        → _intervention_log 追加
        → engine.inject_world_event(cmd)

继续推演 → run_chapter
  → dm.get_intervention_context()
    → 格式化为 "[系统] DM 干预记录：..."
    → append 到 generate_chapter 的 AI prompt
  → AI 按叙事模板自然融入正文
```

---

## 四、新增 API

### `POST /api/dm/guidance`

```json
{
  "character_name": "李青云",
  "message": "天机阁的后山藏着失落的功法",
  "form": "dream",
  "strength": "hint"
}
```

| 参数 | 类型 | 可选值 |
|------|------|--------|
| character_name | string | 目标角色名 |
| message | string | 指引内容 |
| form | string | dream / epiphany / omen / encounter / inner_voice / auto |
| strength | string | direct / hint / vague |

**约束**：仅 DM 状态为 `paused` 时允许调用（返回 409 否则）。

---

## 五、五种融入形式 + 叙事模板

| 形式 | 关键词 | 叙事模板概要 |
|------|--------|-------------|
| 梦境 (DREAM) | 夜、梦、睡 | 角色入睡后梦境中接收指引，含象征性意象，醒来应有反应 |
| 顿悟 (EPIPHANY) | 灵感、突然 | 日常场景中灵光一闪，通过环境触发引出内心转变 |
| 天象 (OMEN) | 星象、异象、征兆 | 描写契合世界观的异常天象，角色观察后有所感触 |
| 偶遇 (ENCOUNTER) | 路人、老者 | 偶然遇到神秘路人，对方无心之言暗含深意，说完自然离去 |
| 内心独白 (INNER_VOICE) | 直觉、预感 | 角色心中莫名升起预感，用内心独白或自由间接引语展现 |

AUTO 模式下基于关键词启发式选择：含"修炼/突破/功法" → INNER_VOICE；含"预言/灾难/命运" → OMEN；含"遗产/秘典/古" → ENCOUNTER；含"梦/睡/夜" → DREAM；DIRECT → DREAM；HINT → ENCOUNTER；默认 INNER_VOICE。

---

## 六、前端改动细节

### 6.1 Tab 结构

干预面板 header 下方新增两个 Tab：
- **数据干预**：原有角色修改 / 事件注入 / 添加目标 / 干预日志
- **天意指引**：角色选择 → 指引内容 → 形式下拉 → 强度下拉 → 发送按钮 → 结果消息

### 6.2 交互行为

- Tab 切换通过事件委托 `click` 监听 `.interv-tab`，切换 `.active` 状态
- 发送后自动清空输入框，显示成功/失败消息
- 干预日志中天意指引条目显示为 `Tick N — 天意指引 → 角色名（形式/强度）`
