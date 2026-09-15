# 公共 API 参考文档

本文档描述 `api/chapter_api.py` 与 `api/outline_api.py` 暴露的 HTTP 端点，
与代码实现保持同步（最近同步时间：2026-08-10）。

## 接口性质说明

- **公共接口**：所有 `@app.route("/api/...")` 注册的 HTTP 端点。它们构成
  前端（`frontend/*.js`）与 Flask 后端之间的契约，由 `app.py` 启动时通过
  `exec` 加载 `api/*_api.py` 动态注册，并通过 `flask_cors` 开放跨域。
  任何参数、返回值、状态码的变更都属于**公共 API 变更**，必须同步更新本文档与前端。
- **内部接口**：
  - 下划线前缀的模块级辅助函数（如 `_normalize_ai_volumes`、`_generate_outline_batch`）
    仅供 API 实现内部使用，不属于对外契约，可自由重构。
  - `api/*_api.py` 文件本身不是可导入的 Python 模块（无 `import` 语义，依赖
    `app.py` 注入的命名空间），属于内部实现细节。

## 通用约定

- 请求/响应均为 JSON（`Content-Type: application/json`）。
- 未初始化时调用需要游戏状态的端点，返回 `400 {"error": "游戏尚未初始化"}`。
- 需要 AI 能力的端点在 `OPENAI_API_KEY` 缺失或为占位符时返回 `401 {"error": "API Key 无效"}`。
- 引擎写操作在全局锁 `_engine_lock` 下执行。
- 大纲数据存在两种格式（见下文"大纲数据格式"），公共端点均按该约定收发。

---

## api/chapter_api.py —— 章节相关 API

### POST /api/init

初始化游戏：接收世界设定与角色设定，清除旧大纲并自动存档（`auto` 槽位）。

**请求体**：

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `world` | object | 是 | — | 世界设定，子字段：`name`、`genre`、`era`、`description`、`rules[]`、`key_locations[]`、`current_situation`、`tone`、`main_objective`、`world_stage`、`perspective` |
| `characters` | array | 是 | — | 角色列表，每项子字段：`name`、`age`、`gender`、`personality`、`background`、`appearance`、`short_term_goals[]`、`long_term_goal`、`abilities[]`、`weaknesses[]`、`initial_location`、`initial_relationships{}` |
| `engine_config` | object | 否 | `{}` | `total_chapters`（总章数）、`ticks_per_chapter`（每章推演刻度数） |

**响应 200**：`{"status": "ok", "state": <引擎状态对象>}`

**副作用**：重置 `_outlines["auto"]` 与 `engine.outline_data`，执行 `engine.save("auto")`。

### POST /api/chapter

生成下一章。标题为空时自动从大纲规划标题回填，否则回退为 `第N章`。
生成时会注入所属卷纲（主题/概要/关键事件/角色弧线）与本章、下一章的大纲规划作为上下文。

**请求体**：

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `title` | string | 否 | 大纲回填或 `第N章` | 章节标题 |

**响应**：

| 状态码 | 响应体 |
|--------|--------|
| 200 | `{"status": "ok", "chapter": <章节对象>}` |
| 400 | `{"error": "游戏尚未初始化"}` |
| 401 | `{"error": "API Key 无效或未配置，请在确认启动页面填写你的 OpenAI API Key"}` |
| 500 | `{"error": "<异常信息>"}`（AI 鉴权类异常归一为 401） |

**副作用**：章节列表同步到活跃分支存储 `_branch_chapters[_active_branch]`。

### GET /api/state

获取当前引擎状态。

**响应**：未初始化时 `{"status": "not_initialized"}`；否则 `{"status": "ok", "state": <引擎状态对象>}`。

### GET /api/chapters

获取所有已生成章节。标题为空的章节会从 `engine.outline_data` 的规划标题回填。

**响应 200**：`{"chapters": [{"chapter": 序号, "title": 标题, "narrative": 正文, ...}]}`

### POST /api/add-character

运行时添加新角色（同时注册到 backend 引擎与 novel_world 世界）。

**请求体**：

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `name` | string | 是 | — | 角色名（不可与已有角色重名） |
| `age` | int | 否 | 20 | 年龄 |
| `gender` | string | 否 | `"男"` | 性别 |
| `personality` | string | 否 | `""` | 性格描述 |
| `personality_list` | array | 否 | `[]` | 性格词条（供 novel_world 角色使用） |
| `background` / `appearance` | string | 否 | `""` | 背景 / 外貌 |
| `short_term_goals` | array | 否 | `[]` | 短期目标 |
| `long_term_goal` | string | 否 | `""` | 长期目标 |
| `abilities` / `weaknesses` | array | 否 | `[]` | 能力 / 弱点 |
| `initial_location` | string | 否 | `""` | 初始位置 |

**响应**：200 `{"status": "ok", "message": "角色 X 已添加"}`；400 名字为空或重名；500 `{"error": "添加失败: ..."}`。

### POST /api/guide-plot

逐章模式下引导情节（不走 DM 流程），按 `type` 分发。

**请求体**：

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `type` | string | 否 | `inject_event`（默认）/ `add_goal` / `modify_character` |

各类型附加参数：

- `inject_event`：`description`（必填，事件描述）。事件写入世界、所有角色记忆与本章事件列表。
- `add_goal`：`name`、`goal`（必填），`weight`（可选，默认 1.0）。为指定角色追加短期目标。
- `modify_character`：`name`、`field`（必填），`value`。`field` 取值：
  - `target`：改写首个短期目标描述并写入角色记忆；
  - `mood`：修改角色当前情绪；
  - `position`：修改角色在世界中的位置。

**响应**：200 `{"status": "ok", "message": ...}`；400 参数缺失或类型不支持；404 角色不存在；500 操作失败。

### DELETE /api/chapter/\<int:index\>

删除指定章节（0 起始索引），并对剩余章节重新编号（从 1 起）。

**响应**：200 `{"status": "ok", "removed_title": 标题}`；404 `{"error": "章节不存在"}`。

### PUT /api/chapter/\<int:index\>

编辑指定章节的标题和/或正文（仅更新传入的字段）。

**请求体**：`title`（string，可选）、`narrative`（string，可选）。

**响应**：200 `{"status": "ok"}`；404 `{"error": "章节不存在"}`。

### GET /api/chapter/\<int:index\>/history

获取章节的编辑历史版本列表。

**响应 200**：`{"index": 索引, "versions": [{"title", "narrative", "saved_at"}]}`。

### POST /api/chapter/\<int:index\>/history

将章节当前内容保存为一个历史版本，最多保留最近 10 个版本。

**响应**：200 `{"status": "ok", "version_count": 当前版本数}`；404 `{"error": "章节不存在"}`。

### POST /api/chapter/\<int:index\>/rollback

回滚章节：先把当前内容追加到版本列表末尾，再恢复列表最早的一个版本。

**响应**：200 `{"status": "ok", "restored_version": {title, narrative}}`；400 `{"error": "没有历史版本"}`；404 `{"error": "章节不存在"}`。

---

## api/outline_api.py —— 大纲系统 API

### 大纲数据格式

| 格式 | 结构 | 使用方 |
|------|------|--------|
| **AI 格式** | `{"name": 卷名, "theme": 主题, "chapters": [{"title", "summary"}]}` | 前端大纲规划弹窗、`engine.outline_data`、章节生成与标题回填 |
| **OutlineManager 格式** | `{"index", "title", "start_chapter", "end_chapter", "outline": {"summary", "theme", "key_events", "character_arcs"}, "chapters": [章节号...]}` | `outline_manager`、DM 面板 |

公共端点同时返回两种格式（`outline` 字段为 AI 格式，`volumes` 字段为
OutlineManager 格式）。输入侧兼容两种格式，内部经 `_normalize_ai_volumes`
归一化为 AI 格式处理。

### GET /api/outline

获取当前项目大纲。返回前将旧存档中可能存在的 OutlineManager 格式归一化为
AI 格式；若 `outline_manager` 为空（重启后不随存档恢复），会从
`engine.outline_data` 重建。

**响应**：

| 状态码 | 响应体 |
|--------|--------|
| 200 | `{"status": "ok", "volumes": [OM格式卷], "outline": {"volumes": [AI格式卷]}, "chapter_count": 已生成章数, "total_chapters": 规划总章数}` |
| 400 | `{"error": "游戏尚未初始化"}` |

### POST /api/outline/generate

AI 生成全书大纲。卷数超过 5 时自动分批生成（每批最多 5 卷），
后续批次携带前批大纲概要作为衔接上下文，最后一批要求收束主线。

**请求体**：

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `volume_count` | int | 否 | 3 | 总卷数 |
| `chapters_per_volume` | int | 否 | 5 | 每卷章节数 |

**响应**：200 `{"status": "ok", "volumes": [OM格式卷], "outline": {"volumes": [AI格式卷]}}`；
400 未初始化；401 API Key 无效；500 `{"error": "生成大纲失败：..."}`。

**副作用**：覆盖写入 `outline_manager` 与 `engine.outline_data`。

### POST /api/outline/continue

AI 续写大纲：在现有大纲基础上追加新卷，扩容 `total_chapters`，并重置终局锁
（`engine._novel_finalized = False`）允许继续生成。上下文包含已有大纲概要
与最近 3 章正文摘要（每章前 200 字）。

**请求体**：

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `volume_count` | int | 否 | 1 | 新增卷数 |
| `chapters_per_volume` | int | 否 | 5 | 每卷章节数 |

**响应**：

| 状态码 | 响应体 |
|--------|--------|
| 200 | `{"status": "ok", "message": 摘要文本, "volumes": [OM格式卷（含已有+新卷）], "outline": {"volumes": [AI格式卷（含已有+新卷）]}, "total_chapters": 扩容后总章数, "novel_finalized": false}` |
| 400 | `{"error": "游戏尚未初始化"}` |
| 401 | `{"error": "API Key 无效"}` |
| 500 | `{"error": "续写大纲失败：..."}` |

### POST /api/outline/summaries/regenerate

重建丢失的章节摘要：基于已有卷名/主题/章节标题，AI 逐批（每批最多 5 卷）
补写 `chapters[].summary`。只填充摘要为空的章节，已有摘要保留；
按章节标题匹配回填。

**请求体**：无。

**响应**：

| 状态码 | 响应体 |
|--------|--------|
| 200 | `{"status": "ok", "message": ..., "filled": 补写条数, "outline": {"volumes": [...]}}`；摘要已完整时 `filled: 0` 且不含 `outline` |
| 400 | 未初始化，或 `{"error": "当前没有大纲数据"}` |
| 401 | `{"error": "API Key 无效"}` |
| 500 | `{"error": "重建章节摘要失败：..."}` |

**副作用**：回写 `engine.outline_data` 并同步重建 `outline_manager`。

### PUT /api/outline

手动更新大纲（前端以 AI 格式提交）。输入先归一化为 AI 格式写入
`engine.outline_data`，再转换为 OutlineManager 格式同步到 `outline_manager`。

**请求体**：

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `volumes` | array | 是 | AI 格式卷列表 `[{"name", "theme", "chapters": [{"title", "summary"}]}]`；兼容旧版 OutlineManager 格式输入 |

**响应 200**：`{"status": "ok", "volumes": [OM格式卷], "outline": {"volumes": [AI格式卷]}}`。
`volumes` 为空时不做任何写入，仅返回当前数据。

### POST /api/outline/volume

向 `outline_manager` 添加一卷。

**请求体**：

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `title` | string | 是 | — | 卷标题 |
| `start_chapter` | int | 否 | 0 | 起始章节号 |
| `end_chapter` | int | 否 | 0 | 结束章节号 |

**响应**：200 `{"status": "ok", "volume_index": 新卷索引}`；400 `{"error": "请提供卷标题"}`。

### POST /api/outline/save

保存手动编辑的大纲 Markdown 到 `saves/outline_edited.md`。

**请求体**：`outline_markdown`（string）。

**响应 200**：`{"status": "ok", "saved_to": 保存路径}`。

### DELETE /api/outline/volume/\<int:vol_index\>

删除指定卷。

**响应**：200 `{"status": "ok"}`；400 `{"error": "删除失败"}`（索引无效）。

### POST /api/outline/volume/\<int:vol_index\>/generate

AI 生成指定卷的纲要（theme / summary / key_events / character_arcs）。
上下文包含：可选灵感输入、世界观设定、人物设定（最多 10 人）、前一卷概要、本卷章节列表。

**请求体**：

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `inspiration` | string | 否 | 灵感碎片（截取前 2000 字参与生成） |

**响应**：200 `{"status": "ok", "data": {"theme", "summary", "key_events", "character_arcs"}}`；
400 未初始化或卷索引无效；500 `{"error": "生成卷纲要失败：..."}`。

---

## app.py / api/dm_api.py —— 启动自检与实时预览

### GET /api/health

启动自检：API 模块装载结果、AI 配置、数据目录可写性。前端页面加载时自动调用，异常时弹提示。

响应字段：

| 字段 | 说明 |
|------|------|
| `status` | `ok` / `degraded` |
| `api_modules` | 各 `api/*_api.py` 装载结果列表（module/ok/error） |
| `failed_modules` | 装载失败的模块 |
| `ai` | `{provider, model, has_api_key}` |
| `data_dirs_writable` | `saves/`、`data/` 可写性 |

### GET /api/dm/preview?offset=N

增量获取正在生成的章节正文预览（配合流式生成，前端打字机展示）。

响应字段：

| 字段 | 说明 |
|------|------|
| `chapter` | 正在生成的章节号 |
| `text` | 从 offset 开始的新增文本 |
| `offset` | 下次拉取应传入的偏移量 |
| `total_length` | 当前预览总长度 |

注：新章开始或缓冲区重置时服务端会将 offset 归零并返回全文。

### GET /api/dm/state（新增字段）

| 字段 | 说明 |
|------|------|
| `phase` | 当前推演阶段（世界事件推演中 / 角色行动推演中 / 碰撞推演中 / AI 生成正文中 / 去AI味后处理与质量审计 / 本章完成，等待继续 …） |

---

## api/generate_api.py —— 世界设定中途编辑

### GET /api/world-config

获取当前世界设定，供开局后中途编辑（前端头部「设定」按钮）。未初始化时 400。

**响应 200**：`{"status": "ok", "config": {...}}`，`config` 子字段：
`name`、`genre`、`era`、`description`、`rules[]`、`key_locations[]`、
`current_situation`、`tone`、`main_objective`、`perspective`（third/first）。

### PUT /api/world-config

中途更新世界设定（影响后续章节生成，不改写已有章节）。

**请求体**：上述字段均可选，仅传需要修改的字段；`rules` / `key_locations` 逐条去空白并过滤空行；
`name` 传空白字符串时 400。

**副作用**：`main_objective` 变化时调用 `engine.align_goals_to_main_objective()`
重新校准角色目标权重（校准失败不阻塞保存）。前端保存后自动存 `auto` 槽位。

**响应**：200 `{"status": "ok", "message": "世界设定已更新"}`；400 未初始化或名称为空。

注：`main_objective` 与 `perspective` 已纳入 `backend/storage.py` 存档持久化；
旧存档缺字段时回退默认值（`""` / `"third"`）。
聊天助手（`api/chat_api.py`）的 `get_world_settings` / `edit_world_settings` 函数调用也路由到本端点；
带副作用操作的快照/回滚（`/api/chat/undo`）已覆盖世界设定字段。

---

## 内部辅助函数（非公共接口）

以下函数定义于 `api/outline_api.py`，仅供端点实现使用，不对外暴露：

| 函数 | 职责 |
|------|------|
| `_is_ai_format_volume(vol)` | 判断单个卷是否为 AI 格式 |
| `_om_volume_to_ai(vol)` | OutlineManager 格式卷 → AI 格式卷（章节摘要不可恢复时留空） |
| `_normalize_ai_volumes(volumes)` | 任意格式卷列表 → AI 格式（兼容旧存档） |
| `_ai_to_om_volumes(volumes)` | AI 格式卷列表 → OutlineManager 格式（自动分配章节区间） |
| `_generate_outline_batch(...)` | 生成一批（≤5 卷）大纲，供 `/api/outline/generate` 分批调用 |
