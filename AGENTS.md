# AGENTS.md

> 本文件用于指导 AI 编码代理理解和修改本项目。所有结构描述均与当前代码保持一致；改动代码前请先阅读「变更路由指引」。

## 1. 项目概述

**小说世界** 是一个 AI 驱动的交互式小说生成系统。它以多智能体仿真为核心：角色携带目标、技能与信念入场，在世界中对撞并自动生长剧情，由 DM 控制器与天意指引推动叙事，最终产出章节文本。

- **后端**：Python + Flask，对外暴露 REST API。
- **引擎**：基于 Tick 驱动的仿真引擎（`novel_world/engine`），角色行动 → 碰撞 → 生成剧情。
- **AI**：通过 OpenAI 兼容接口 + `ModelRouter` 路由多模型，支持去 AI 味后处理、人性审计、双管线生成等增强能力。
- **前端**：原生 HTML/JS/CSS 单页应用，轮询后端状态并渲染章节、时间线与 DM 面板。

运行入口：`python app.py`（Flask 服务）、`launcher.py`（桌面启动器）、`run_game.py` / `run_demo.py`（命令行演示）。

## 2. 核心架构

系统分为五层，自上而下调用：

| 层 | 目录 | 职责 |
| --- | --- | --- |
| 接口层 | `api/` | Flask 蓝图，按功能域拆分（章节/角色/DM/大纲/导出/提示词等），无业务逻辑 |
| 后端服务 | `backend/` | 配置、AI 客户端、模型路由、后处理器、技能包、蒸馏记忆、人性审计、双管线、大纲系统 |
| 适配层 | `novel_world/adapter/` | `EngineAdapter` 薄桥接，对外暴露与旧 `GameEngine` 相同的 API，对内转发到重型引擎 |
| 引擎核心 | `novel_world/engine/` | Tick 调度、碰撞检测、目标/事件、提示词注册、DM 状态机、天意指引、小说输出 |
| 前端 | `frontend/` | 原生 JS 渲染与轮询，无框架依赖 |

调用链：`frontend` → `api/*` → `backend/*` / `novel_world.adapter.EngineAdapter` → `novel_world.engine.*`。

`app.py` 负责装配全局实例（`engine`、`dm`、`divine`、`model_router`、`skill_manager`、`outline_manager` 等），是所有 API 模块共享的入口。

## 3. 关键模块说明

### `novel_world/engine/core/prompt_registry.py` — 提示词注册中心
- `PromptRegistry` 集中管理所有硬编码 AI prompt 模板，支持 `{variable_name}` 变量注入。
- v2 特性：版本历史、回滚（`rollback`）、热重载（`reload_from_file`）。
- 用法：`PromptRegistry.get(name, **vars)` 获取渲染结果；`update` 自动归档旧版本。
- **约定**：新增/修改 prompt 一律经此注册，禁止在业务代码里散落硬编码 prompt 字符串。

### `novel_world/engine/collision/` — 碰撞检测
- 入口 `collision_engine.py`：人物 Skill 在世界中对撞自动生成剧情，核心逻辑为「人人带目标入场 + 人人带独立剧情 + 人人有专属技能 + 相遇自动技能碰撞」。
- 碰撞模型三类：感知对冲 / 目标对冲 / 能力对冲。
- `weight_loader.py` + `weight_calibrator.py` + `weights.yaml`：碰撞权重可配置、可校准。
- 已集成 Phase 3 模块：`agent`、`beliefs`、`theory_of_mind`、`arc_reflection`（导入失败时自动降级）。

### `novel_world/adapter/adapter.py` — 适配器（薄桥接层）
- `EngineAdapter` 对外暴露与 `backend.engine.GameEngine` 完全相同的 API 签名，内部转换为重型引擎执行。
- 方法按功能域拆分至 `adapter_mixins/`：`LifecycleMixin`（初始化/存档/角色管理）、`ChapterMixin`（章节执行）、`QualityMixin`（时间线检查/终局结算/DM/势力）。
- **约定**：修改引擎调用入口时改 Mixin，不要在 `adapter.py` 里堆逻辑；`adapter.py` 仅作类组合。

### `app.py` — API 装载机制（exec 注入）
- 所有 `api/*_api.py` 不走常规 import，而是由 `app.py` 以 `exec(compile(...))` 注入共享命名空间 `_api_ns` 执行。
- **约定**：新增 API 文件必须以 `_api.py` 结尾才会被装载；文件内可直接使用 `app`、`engine`、`dm`、`model_router` 等预注入全局名，无需（也不应）反向 import `app`；装载失败仅打印 `[FAIL]` 不中断服务，排查接口缺失先看启动日志。

### 双 AI 客户端 — base_url 与 api_url 语义不同
- `backend/ai_client.py`：多 provider 客户端，`config[provider]["base_url"]` 是 **provider 根地址**（如 `https://api.deepseek.com`，不含 `/chat/completions`）；API Key 按 `_ENV_KEY_MAP` 从环境变量取（`DEEPSEEK_API_KEY` / `OPENAI_API_KEY` / `DOUBAO_API_KEY` / `KIMI_API_KEY`）。
- `novel_world/engine/core/ai_client.py`：引擎侧客户端，`api_url` 是 **完整 chat 端点**（含 `/chat/completions`），由 `adapter_mixins/lifecycle.py` 从 `.env` 的 `OPENAI_BASE_URL` 传入。
- **约定**：两者语义不可混用；改 `.env` 或切换 provider 时先确认消费方是哪一侧。
- **配置单一真源**：API Key / base_url / model 一律以 `data/ai_config.json` 为准（前端模型配置页与 `/api/save-key` 都写入此文件，`ModelRouter` 与旧 `AIClient` 共享读取）；`.env` 仅作为引擎侧 `OPENAI_BASE_URL` / `OPENAI_API_KEY` 的环境变量来源，勿直接修改。

## 4. 编码约定

- **语言**：Python 3；前端为原生 JavaScript（无构建工具、无框架）。
- **依赖管理**：使用 `requirements.txt`，所有依赖指定最低版本（如 `flask>=3.0`）。安装：`pip install -r requirements.txt`。新增第三方依赖必须同步写入 `requirements.txt`。
- **核心依赖**：Flask / Flask-CORS / OpenAI / python-dotenv / httpx / requests / numpy / PyYAML / psutil / cryptography / tqdm。
- **配置**：环境变量经 `.env`（`python-dotenv`）加载；运行时数据存于 `saves/`、`backend/data/`、`data/`，**勿将这些数据目录误认为代码**。
- **文件头**：每个 Python 模块顶部保留 `# -*- coding: utf-8 -*-` 与中文 docstring 说明职责；新增文件遵循同样风格。
- **备份文件**：`*_backup.py`、`*_original.py_failed`、`__pycache__/`、`build/`、`dist/` 均为历史/产物，**不要修改或导入**。
- **打包兼容**：涉及资源路径需兼容 PyInstaller（`sys._MEIPASS`），参考 `app.py` 的 `BASE_DIR` 处理。

## 5. 变更路由指引

按「改什么」定位「改哪里」。八大源码根目录及其入口：

| 变更类型 | 定位目录 | 说明 |
| --- | --- | --- |
| 新增/修改 HTTP 接口 | `api/` | 按功能域选择对应 `*_api.py`，路由注册在 `app.py` |
| AI 调用 / 模型路由 / 后处理 / 记忆 / 审计 | `backend/` | 对应 `ai_client.py`、`model_router/`、`post_processor/`、`distilled_memory/`、`humanity_audit/` |
| 引擎逻辑 / 碰撞 / 提示词 / DM / 天意 | `novel_world/engine/` | `core/`、`collision/`、`dm_state.py`、`divine_guidance.py` |
| 引擎对外 API 签名 / 桥接 | `novel_world/adapter/` | 改 `adapter_mixins/`，勿堆逻辑于 `adapter.py` |
| 向量记忆 / 通用工具 | `utils/` | `memory_manager.py`、`vector_memory.py` |
| 前端渲染 / 交互 / 轮询 | `frontend/` | 原生 JS；注意轮询状态覆盖（见已知坑） |
| 设计文档 / 架构说明 | `docs/` | Markdown；重大架构调整需同步更新本文档 |
| 示例配置 / 角色模板 | `examples/` | `character_example.json` 等参考样例 |

测试位于 `tests/`（`test_chapter_api.py`、`test_dm_state.py`、`test_outline_api.py`、`test_hard_constraints.py`、`test_model_router.py`、`test_post_processor.py`、`test_skill_packs.py`），改动上述模块后应运行相关测试。

**改动前检查清单**：
1. 提示词改动 → 走 `PromptRegistry`，勿硬编码。
2. 引擎对外行为改动 → 检查 `EngineAdapter` 对应 Mixin 是否需同步。
3. 新增依赖 → 更新 `requirements.txt`。
4. 涉及存档/数据 → 仅读写 `saves/` 与约定数据目录。
5. 影响架构 → 更新 `docs/` 与本文件相关章节。
