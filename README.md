# 小说世界（Novel World）— 叙事引擎

单机运行的中文小说 AI 创作引擎。内置角色驱动叙事引擎、多 Agent 碰撞推演、大纲与卷纲规划、章节批量生成、多存档与导出能力，支持接入任意 OpenAI 兼容 API 的大模型。

当前版本：**0.9.1**

---

## 项目定位

面向个人小说创作者的本地化写作工作台：故事由"角色目标 + 世界规则 + 时间线"驱动，AI 按大纲逐章生成，同时通过**碰撞引擎**模拟角色间的意图冲突、约束与后果，使叙事保持连贯和可解释。

## 核心特性

- **角色驱动叙事**：角色档案、目标系统、世界规则、时间线与关键事件统一建模，章节生成时注入"本章规划 + 下一章走向"。
- **碰撞引擎（Collision Engine）**：多角色意图冲突推演、约束泛化与权重标定，支持 `weights.yaml` 重标定。
- **DM 模式与时间线检查**：DM 状态机干预剧情走向，章节数收尾（finale）与天命指引（divine guidance）模块。
- **多 Provider 模型路由（ModelRouter）**：兼容 OpenAI 格式，内置 DeepSeek / Ollama / OpenAI / 豆包 / Kimi 配置，支持运行时切换与回退。
- **多存档与导出**：章节级存档、快照与导出；API 降级与角色容错。
- **人工审校（Humanity Audit）**：AI 文本去 AI 味后处理管线。
- **开箱即用**：演示模式（`provider="none"`）无需任何 API Key 即可跑通完整流程。

## 技术栈与架构

| 层 | 技术 |
| --- | --- |
| 后端 | Python 3.11+ / Flask 3+（生产环境可用 waitress） |
| AI 接入 | OpenAI 兼容 SDK + 自研 ModelRouter（多 Provider 路由与降级） |
| 前端 | 原生 HTML / JS / CSS（无框架） |
| 数据 | 本地文件系统（YAML 配置 + JSON 存档），无数据库 |
| 打包 | PyInstaller（`build_exe.spec`） |
| CI | GitHub Actions（pytest + pip-audit） |

代码按功能域分模块：

```
novel_world/    # 引擎核心（角色/事件/碰撞/时间线/存档/导出等）
backend/        # 后端服务层（引擎配置、AI 客户端、双管线等）
api/            # Flask API 路由（16 个模块，见 /api/health）
frontend/       # 前端页面与静态资源
utils/          # 通用工具
tests/          # 自动化测试
docs/           # 设计文档与变更清单
```

## 快速开始

环境要求：Windows / Linux / macOS，Python 3.11+。

```bash
# 1. 创建虚拟环境并安装依赖
python -m venv .venv
.venv\Scripts\activate            # Windows（Linux/macOS: source .venv/bin/activate）
pip install -r requirements.txt

# 2. （可选）配置模型：复制 .env.example 为 .env 并填入密钥
copy .env.example .env            # Windows（Linux/macOS: cp .env.example .env）

# 3. 启动
python run_game.py                # 等价于 python app.py
```

启动后访问 `http://127.0.0.1:5000`，`GET /api/health` 可查看版本与各 API 模块健康状态。

Windows 下也可直接双击 `start.bat`（自动创建/使用 `.venv`、安装依赖、复制 `.env.example`、启动服务）。

## 模型配置

### 方式一：环境变量（`.env`）

```
AI_PROVIDER=deepseek
OPENAI_API_KEY=your_api_key_here
OPENAI_BASE_URL=https://api.deepseek.com/v1
OPENAI_MODEL=deepseek-v4-flash
HOST=127.0.0.1
PORT=5000
```

### 方式二：多 Provider 配置（`data/ai_config.json`）

复制 `data/ai_config.example.json` 为 `data/ai_config.json` 后按需填写（支持 DeepSeek / Ollama / OpenAI / 豆包 / Kimi）。该文件**不纳入版本控制**，由 ModelRouter 动态读取。

### 无需 API Key 的演示模式

`run_demo.py` 中可切换 `provider="none"`，碰撞引擎使用内置模板生成叙事文本，开箱即用。

## 目录结构

```
├── app.py / run_game.py      # 启动入口
├── run_demo.py               # 完整演示脚本
├── launcher.py               # 图形化启动器
├── novel_world/              # 引擎核心
├── backend/                  # 服务层（引擎配置 / AI 客户端 / 双管线）
├── api/                      # Flask 路由
├── frontend/                 # 前端
├── utils/                    # 工具
├── tests/                    # 测试
├── docs/                     # 设计文档
├── data/                     # 运行时数据（ai_config.json 不入库，example 入库）
├── character_settings/       # 角色设定（YAML）
├── world_settings/           # 世界观设定（YAML）
├── examples/                 # 示例
├── output/                   # 运行产物（不入库）
├── saves/                    # 存档（不入库）
└── temp/                     # 临时文件（不入库）
```

## 开源协议

本项目以 **GNU AGPL-3.0**（Affero GPL v3）发布，详见 [LICENSE](LICENSE)。使用、复制、修改、分发须遵循 AGPL-3.0 全部条款；修改版本须以 AGPL-3.0 重新授权并公开源码，以网络服务形式对外提供时须向用户提供对应完整源码。第三方依赖均为宽松许可（MIT / BSD / Apache-2.0 / MPL / ZPL / PSF），完整清单见 [THIRD_PARTY_LICENSES.md](THIRD_PARTY_LICENSES.md)。
