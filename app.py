"""Flask 后端服务 —— 模块化架构"""

import os
import re
import sys
import json
import random
import logging
import threading
import glob
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from dotenv import load_dotenv, set_key

# PyInstaller 兼容：打包后资源在 sys._MEIPASS
BASE_DIR = getattr(sys, "_MEIPASS", os.path.dirname(__file__))


# ── 应用版本号（VERSION 文件 > git tag > dev）──
def _resolve_app_version() -> str:
    version_file = os.path.join(os.path.dirname(__file__), "VERSION")
    try:
        if os.path.exists(version_file):
            with open(version_file, "r", encoding="utf-8") as f:
                v = f.read().strip()
                if v:
                    return v
    except OSError:
        pass
    try:
        import subprocess
        out = subprocess.run(
            ["git", "describe", "--tags", "--always"],
            capture_output=True, text=True, timeout=3,
            cwd=os.path.dirname(__file__),
        )
        if out.returncode == 0 and out.stdout.strip():
            return out.stdout.strip()
    except Exception:
        pass
    return "dev"


APP_VERSION = _resolve_app_version()


# ── 日志脱敏：遮蔽用户目录绝对路径与明文 API Key ──
# 通过 LogRecordFactory 在记录创建时全局脱敏，
# 对任何 logger/handler（含后续新增）均生效。
_HOME_PATHS = sorted(
    {os.path.expanduser("~"), os.path.expanduser("~").replace("\\", "/")},
    key=len, reverse=True,
)


def _mask_sensitive(text: str) -> str:
    """遮蔽 sk- 开头的 API Key 与用户主目录前缀"""
    if re.search(r"sk-[A-Za-z0-9]{8,}", text):
        text = re.sub(r"sk-[A-Za-z0-9]{4}[A-Za-z0-9]+", "sk-***", text)
    for h in _HOME_PATHS:
        if h and h in text:
            text = text.replace(h, "~")
    return text


_orig_log_record_factory = logging.getLogRecordFactory()


def _masked_log_record_factory(*args, **kwargs):
    record = _orig_log_record_factory(*args, **kwargs)
    if isinstance(record.msg, str):
        try:
            text = record.getMessage()  # 先格式化，覆盖占位符 args 中的敏感值
        except Exception:
            return record
        masked = _mask_sensitive(text)
        if masked != text:
            record.msg = masked
            record.args = ()
    return record


logging.setLogRecordFactory(_masked_log_record_factory)

# 加载 .env
ENV_PATH = os.path.join(BASE_DIR, ".env")
if not os.path.exists(ENV_PATH):
    ENV_PATH = os.path.join(os.path.dirname(__file__), ".env")
load_dotenv(ENV_PATH, override=True)

sys.path.insert(0, BASE_DIR)
from backend.config import WorldConfig, CharacterConfig
from backend.world import World
from backend.character import CharacterAgent
from novel_world.adapter import EngineAdapter
from novel_world.engine.dm_state import DMController, DMState
from novel_world.engine.divine_guidance import (
    DivineGuidance, GuidanceForm, GuidanceStrength,
)
from backend.ai_client import init_client, _client, get_client, get_available_providers, switch_model, get_usage_stats, set_router

# Phase 1-3 移植的 backend 模块
from backend.post_processor import apply_de_ai_postprocess, detect_ai_flavor, compute_ai_score, sanitize_user_input
from backend.model_router import ModelRouter
from backend.skill_packs import SkillPackManager, novel_distill
from backend.distilled_memory import DistillService, MemorySynthesizer, VectorMemory
from backend.humanity_audit import verve_review, render_humanity_report
from backend.dual_pipeline import DualPipeline
from backend.outline_system import OutlineManager

app = Flask(
    __name__,
    static_folder=None,
)
CORS(app)
FRONTEND_DIR = os.path.join(BASE_DIR, "frontend")

# 全局引擎实例
engine = EngineAdapter()
_engine_lock = threading.Lock()

# DM 控制器
dm = DMController(engine)

# 天意指引
divine = DivineGuidance(dm)


def get_world():
    """获取当前引擎的 NWWorld 实例。若未初始化则抛出 RuntimeError。"""
    if engine._nw_world is None:
        raise RuntimeError("引擎尚未初始化，请先调用 /api/init")
    return engine._nw_world


# ── Phase 1-3 移植模块实例化 ──
model_router = ModelRouter()
set_router(model_router)  # 让 ai_client 所有函数走 ModelRouter
skill_manager = SkillPackManager()
distill_service = DistillService(llm_callable=model_router.generate)
verve_review_svc = verve_review  # 函数引用，无需实例化
dual_pipeline = DualPipeline()
outline_manager = OutlineManager()

# ── 全局变量（API 模块共享）──
_outlines = {}  # {slot: {volumes: [...], chapters: [...]}}
_chapter_versions = {}  # {chapter_index: [versions...]}
_branches = {}  # {branch_id: {name, from_chapter}}
_active_branch = "main"  # 当前活跃分支
_branch_chapters = {}  # {branch_id: [chapter_dicts...]} 每个分支独立章节


# ── 静态文件 ──

@app.route("/")
def index():
    return send_from_directory(FRONTEND_DIR, "index.html")


@app.route("/<path:path>")
def serve_static(path):
    response = send_from_directory(FRONTEND_DIR, path)
    # 开发环境禁用静态文件缓存，确保 JS/CSS 修改即时生效
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


# ── 注册 API 模块 ──
# 每个 API 文件中的路由使用 @app.route，需要访问上述全局变量
# 通过 exec 注入命名空间，避免循环导入

_api_ns = {
    "app": app,
    "engine": engine,
    "_engine_lock": _engine_lock,
    "dm": dm,
    "divine": divine,
    "get_world": get_world,
    "FRONTEND_DIR": FRONTEND_DIR,
    "ENV_PATH": ENV_PATH,
    "_outlines": _outlines,
    "_chapter_versions": _chapter_versions,
    "_branches": _branches,
    "_active_branch": _active_branch,
    "_branch_chapters": _branch_chapters,
    "os": os, "re": re, "sys": sys, "json": json,
    "random": random, "threading": threading, "logging": logging,
    "request": request, "jsonify": jsonify,
    "send_from_directory": send_from_directory,
    "WorldConfig": WorldConfig, "CharacterConfig": CharacterConfig,
    "World": World, "CharacterAgent": CharacterAgent,
    "EngineAdapter": EngineAdapter,
    "DMController": DMController, "DMState": DMState,
    "DivineGuidance": DivineGuidance,
    "GuidanceForm": GuidanceForm, "GuidanceStrength": GuidanceStrength,
    "init_client": init_client, "_client": _client,
    "set_key": set_key,
    # 多 Provider AI
    "get_client": get_client,
    "get_available_providers": get_available_providers,
    "switch_model": switch_model,
    "get_usage_stats": get_usage_stats,
    "set_router": set_router,
    # Phase 1-3 移植模块
    "model_router": model_router,
    "skill_manager": skill_manager,
    "novel_distill": novel_distill,
    "distill_service": distill_service,
    "verve_review_svc": verve_review_svc,
    "render_humanity_report": render_humanity_report,
    "dual_pipeline": dual_pipeline,
    "outline_manager": outline_manager,
    "apply_de_ai_postprocess": apply_de_ai_postprocess,
    "detect_ai_flavor": detect_ai_flavor,
    "compute_ai_score": compute_ai_score,
    "sanitize_user_input": sanitize_user_input,
}

api_dir = os.path.join(os.path.dirname(__file__), "api")
_api_load_report = []   # 供 /api/health 启动自检使用
for f in sorted(glob.glob(os.path.join(api_dir, "*_api.py"))):
    mod_name = os.path.basename(f)[:-3]
    try:
        with open(f, "r", encoding="utf-8") as fh:
            code = fh.read()
        exec(compile(code, f, "exec"), _api_ns)
        print(f"  [OK] api/{mod_name}")
        _api_load_report.append({"module": mod_name, "ok": True})
    except Exception as e:
        print(f"  [FAIL] api/{mod_name}: {e}")
        _api_load_report.append({"module": mod_name, "ok": False, "error": str(e)})


@app.route("/api/health", methods=["GET"])
def api_health():
    """启动自检：API 模块装载结果、AI 配置、数据目录可写性"""
    provider = model_router.get_provider()
    cfg = model_router.config.get(provider, {})
    try:
        api_key = model_router._get_api_key(cfg, provider=provider)
    except Exception:
        api_key = cfg.get("api_key", "") or os.getenv("OPENAI_API_KEY", "")

    dirs = {}
    for d in ("saves", "data"):
        path = os.path.join(os.path.dirname(__file__), d)
        dirs[d] = os.path.isdir(path) and os.access(path, os.W_OK)

    failed_modules = [m for m in _api_load_report if not m["ok"]]
    healthy = not failed_modules and bool(api_key) and all(dirs.values())
    return jsonify({
        "status": "ok" if healthy else "degraded",
        "version": APP_VERSION,
        "api_modules": _api_load_report,
        "failed_modules": failed_modules,
        "ai": {
            "provider": provider,
            "model": cfg.get("model", ""),
            "has_api_key": bool(api_key),
        },
        "data_dirs_writable": dirs,
    })


# ═══════════════════════════════════════════
# 连线框 API（从书斋V66移植）
# ═══════════════════════════════════════════

SAVES_DIR = os.path.join(os.path.dirname(__file__), "saves")
PLANNING_CARDS_FILE = os.path.join(SAVES_DIR, "planning_cards.json")

@app.route("/api/project/planning-cards", methods=["GET"])
def api_planning_cards_get():
    """从 saves/ 目录读取 planning_cards.json"""
    try:
        if os.path.exists(PLANNING_CARDS_FILE):
            with open(PLANNING_CARDS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            return jsonify({"ok": True, "data": data})
        else:
            return jsonify({"ok": True, "data": {"nodes": [], "edges": [], "meta": {}}})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/project/planning-cards", methods=["POST"])
def api_planning_cards_post():
    """保存到 saves/planning_cards.json"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({"ok": False, "error": "请求体为空"}), 400
        os.makedirs(SAVES_DIR, exist_ok=True)
        with open(PLANNING_CARDS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/project/planning-check", methods=["POST"])
def api_planning_check():
    """AI 一致性检测：用现有 AI 客户端检查连线框节点与章节正文的一致性"""
    try:
        data = request.get_json()
        nodes = data.get("nodes", [])
        edges = data.get("edges", [])
        chapter_text = (data.get("chapter_text", "") or "").strip()

        if not nodes and not edges:
            return jsonify({"ok": True, "results": {}, "detail": "无待检测内容"})

        if not chapter_text:
            return jsonify({"ok": True, "results": {}, "detail": "无章节正文"})

        # 构建 prompt
        node_desc = "\n".join([
            f"- [{n.get('type', 'free')}] {n.get('title', '未命名')}: {n.get('summary', '')}"
            for n in nodes
        ])
        edge_desc = "\n".join([
            f"- {e.get('label', '连线')}: {e.get('from', '')} → {e.get('to', '')}"
            for e in edges
        ])

        prompt = f"""你是一个小说设定一致性检测器。请根据提供的章节正文，判断每个连线框节点（人物/伏笔/章节/世界观设定）是否与正文一致。

## 章节正文
{chapter_text[:3000]}

## 连线框节点
{node_desc}

## 连线关系
{edge_desc}

请对每个节点输出：
- consistent: 设定与正文一致
- needs_update: 设定与正文冲突或需要更新
- uninvolved: 设定在本章节正文中未涉及

以 JSON 格式返回，格式为：{{"results": {{"节点ID": "状态"}}}}"""

        results = {}
        used_ai = False

        # 历史 bug：这里曾用 from-import 绑定的 _client（导入时为 None 且
        # 永远不跟随 init_client 重绑定）走旧 OpenAI SDK 路径，导致 AI 分支
        # 永远静默空转。改走 ModelRouter（当前有效 key/provider 的唯一入口）
        try:
            content = model_router.chat_with_messages(
                [
                    {"role": "system", "content": "你是一个小说设定一致性检测器。仅返回JSON。"},
                    {"role": "user", "content": prompt},
                ],
                task="check", temperature=0.1, max_tokens=1000,
            )
            if content and not content.startswith(("[错误]", "[生成失败:")):
                # 提取 JSON
                json_match = re.search(r'\{[\s\S]*\}', content)
                if json_match:
                    ai_result = json.loads(json_match.group(0))
                    results = ai_result.get("results", {})
                    used_ai = True
        except Exception as e:
            print(f"[planning-check] AI调用失败: {e}")

        return jsonify({
            "ok": True,
            "results": results,
            "used_ai": used_ai,
            "detail": "AI 检测完成" if used_ai else "AI 不可用，返回空结果"
        })
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/world-settings", methods=["GET"])
def api_world_settings():
    """返回世界设定 [{key, val}] 格式，从当前加载的 WorldConfig 中提取"""
    try:
        if not engine.world:
            return jsonify({"settings": []})

        wc = engine.world.config
        settings = [
            {"key": "名称", "val": wc.name},
            {"key": "类型", "val": wc.genre},
            {"key": "时代", "val": wc.era},
            {"key": "描述", "val": wc.description},
            {"key": "基调", "val": wc.tone},
            {"key": "当前局势", "val": wc.current_situation},
            {"key": "阶段", "val": wc.world_stage},
            {"key": "视角", "val": wc.perspective},
        ]
        return jsonify({"settings": settings})
    except Exception as e:
        return jsonify({"settings": [], "error": str(e)})


@app.route("/api/hooks", methods=["GET"])
def api_hooks():
    """从 TruthLedger 或干预日志中返回伏笔列表 [{content}]"""
    hooks = []
    try:
        # 从 DM 干预日志中提取 inject_event 类型的伏笔指令
        with _engine_lock:
            for entry in dm._intervention_log:
                if entry.get("type") == "inject_event" and entry.get("cmd"):
                    hooks.append({"content": str(entry["cmd"])[:120]})

        # 从 TruthLedger 提取伏笔
        try:
            if engine._nw_world and hasattr(engine._nw_world, '_truth_ledger'):
                ledger = engine._nw_world._truth_ledger
                for fs in getattr(ledger, 'foreshadowing', []):
                    content = fs.content if hasattr(fs, 'content') else str(fs)
                    hooks.append({
                        "content": content[:120],
                        "id": getattr(fs, 'id', ''),
                        "status": getattr(fs, 'status', 'planted'),
                        "planted_chapter": getattr(fs, 'planted_chapter', 0),
                        "hook_type": getattr(fs, 'hook_type', ''),
                        "strength": getattr(fs, 'strength', 2),
                    })
        except Exception:
            pass

        # 去重（按 content 去重）
        seen = set()
        unique_hooks = []
        for h in hooks:
            key = h["content"]
            if key not in seen:
                seen.add(key)
                unique_hooks.append(h)

        return jsonify({"hooks": unique_hooks[:50]})
    except Exception as e:
        return jsonify({"hooks": [], "error": str(e)})


# ── 多 Provider 模型切换 API ──
# ── 启动 ──

def main():
    # ModelRouter 已在模块顶层初始化并注册，直接使用即可
    host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("PORT", 5000))
    print(f"小说世界 启动于 http://{host}:{port}")
    # 长时运行推荐 waitress（多线程生产服务器，轮询+长生成并发更稳）：
    #   设置 USE_WAITRESS=1 启用；未安装时自动回退 Flask 开发服务器
    if os.getenv("USE_WAITRESS", "") == "1":
        try:
            from waitress import serve
            print("使用 waitress 生产服务器（threads=8）")
            serve(app, host=host, port=port, threads=8)
            return
        except ImportError:
            print("waitress 未安装（pip install waitress），回退 Flask 开发服务器")
    app.run(host=host, port=port, threaded=True,
            debug=not getattr(sys, "frozen", False))


if __name__ == "__main__":
    main()
