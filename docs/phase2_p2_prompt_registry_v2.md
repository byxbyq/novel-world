# Phase2 P2: PromptRegistry v2 — 版本管理 + 回滚 + 热重载

## 改动概述

将 PromptRegistry 从静态字典存储升级为完整版本管理体系，每个 prompt 独立维护历史版本链，支持编辑回滚和 JSON 文件热重载。前端 DM 面板新增「Prompt 管理」Tab。

---

## 改动文件清单（3 个文件）

### 1. `novel_world/engine/core/prompt_registry.py`（重写类体）

| 改动项 | 说明 |
|--------|------|
| 数据结构 | `_prompts: Dict[str, str]` → `_prompts: Dict[str, dict]`，每个 entry 含 `current` + `history[]` + 各版本 key |
| `_history_depth` | 新增类属性，默认 5，超过时自动淘汰最旧版本 |
| `register()` | 已存在时走 update 路径（自动 `_save_version`），已存在时不走版本保存的 bug 已修复 |
| `_save_version()` | 新增内部方法：生成 `v{timestamp}_{序号}` ID，存入历史，超限淘汰 |
| `_get_current()` | 新增内部方法，统一 get/get_raw 的 current 取值逻辑 |
| `update(name, new_template)` | 新增：保存当前 → 覆盖当前 → 返回旧版本 ID |
| `get_version(name, version)` | 新增：按版本 ID 取历史模板 |
| `rollback(name, steps=1)` | 新增：回退 1 步（或多步），自动保存当前版本后再切换 |
| `get_history(name)` | 新增：返回 `[{version, preview, length}, ...]`（最新在前） |
| `get_all_metadata()` | 新增：返回所有 prompt 的列表元信息（名称/长度/版本数/变量列表） |
| `reload_from_file(filepath)` | 新增：从 JSON 热加载，已存在的走 update，新注册的走 register，返回 `{loaded, skipped, errors}` |
| `export_to_file(filepath)` | 新增：导出所有当前 prompt 到 JSON |
| `get_raw()/get()/list_all()` | 保持 v1 API 不变，内部改为走 `_get_current()` |
| `_get_placeholders()` | 保持 v1 API 不变，内部改为走 `_get_current()` |

### 2. `app.py`（+6 个 API 端点）

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/prompts` | GET | 列出所有 prompt 元信息 |
| `/api/prompts/<name>` | GET | 获取当前版本模板 |
| `/api/prompts/<name>` | PUT | 更新模板（自动保存旧版本） |
| `/api/prompts/<name>/history` | GET | 获取版本历史 |
| `/api/prompts/<name>/version/<version>` | GET | 获取指定版本内容 |
| `/api/prompts/<name>/rollback` | POST | 回滚到上一版本 |
| `/api/prompts/reload` | POST | 从 JSON 文件热重载 |

### 3. `frontend/index.html` + `frontend/app.js`（前端 Prompt 管理 Tab）

| 组件 | 说明 |
|------|------|
| `interv-tabs` 新增按钮 | DM 干预面板新增「Prompt 管理」Tab |
| `tab-interv-prompts` | Tab 内容区：刷新列表 → 点击 prompt 进入编辑 |
| `prompt-editor-section` | 编辑区：textarea + 保存/回滚/取消按钮 + 状态提示 |
| `prompt-history-section` | 版本历史列表（最新版本绿色高亮） |
| `refreshPrompts()` | 加载 prompt 列表，显示名称/字数/版本数徽标 |
| `openPromptEditor(name)` | 加载模板到编辑器 + 同时加载历史 |
| `savePromptEdit()` | PUT 提交模板，自动备份 → 刷新历史 |
| `rollbackPrompt()` | confirm → POST rollback → 刷新编辑器 + 历史 |
| `cancelPromptEdit()` | 关闭编辑器/历史面板 |

---

## 验证结果

11 项测试全部通过：

1. 26 个内置模板正常注册
2. get_raw / get 正常返回
3. update 自动保存旧版本，返回版本 ID
4. 当前版本已更新
5. get_version 可精确还原旧版本内容
6. rollback 回退后内容恢复
7. 历史版本链完整
8. get_all_metadata 返回 26 条元信息
9. export_to_file 导出 26 条
10. reload_from_file 全量 loaded=26, skipped=0
11. register 重复注册走 update 路径，历史正确累积

历史深度上限 = 5 自动淘汰已验证（11 号测试中 register 多次后 history 维持 5 条）。
