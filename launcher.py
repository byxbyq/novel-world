# -*- coding: utf-8 -*-
"""
小说世界 — 统一启动中台

职责：
1. 环境自动检测（显卡显存 / 内存 / 本地模型文件 / API Key 状态）
2. 统一引擎初始化（YAML 配置加载 + AI 客户端 + EngineAdapter）
3. 双模式入口（命令行离线 / Web GUI）共用同一套初始化逻辑
4. 运行模式自动降级（高端 → 平衡 → 轻量）

使用方式：
    命令行批量：  python launcher.py offline --chapters 5
    Web GUI：     python launcher.py web --port 5000
    仅检测：      python launcher.py detect
"""

import os
import sys
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger("launcher")

PROJECT_ROOT = Path(__file__).resolve().parent


# ==========================================================================
# 一、环境检测
# ==========================================================================

@dataclass
class EnvironmentReport:
    """环境检测报告"""
    os: str = ""
    python_version: str = ""
    memory_gb: float = 0.0
    gpu_available: bool = False
    gpu_name: str = ""
    gpu_vram_gb: float = 0.0
    api_key_available: bool = False
    api_base_url: str = ""
    local_model_path: str = ""
    local_model_exists: bool = False
    vllm_available: bool = False
    vllm_url: str = ""
    recommended_mode: str = "none"  # none / api / local_7b / local_14b / local_27b / vllm
    mode_reason: str = ""
    model_tier: str = "light"  # ultra / balanced / light / api

    def to_dict(self) -> dict:
        return {
            "os": self.os,
            "python_version": self.python_version,
            "memory_gb": round(self.memory_gb, 1),
            "gpu_available": self.gpu_available,
            "gpu_name": self.gpu_name,
            "gpu_vram_gb": round(self.gpu_vram_gb, 1),
            "api_key_available": self.api_key_available,
            "recommended_mode": self.recommended_mode,
            "mode_reason": self.mode_reason,
        }


def detect_environment() -> EnvironmentReport:
    """自动检测运行环境，推荐最优运行模式。"""
    report = EnvironmentReport()

    # 操作系统
    import platform
    report.os = platform.system()
    report.python_version = platform.python_version()

    # 内存
    try:
        import psutil
        mem = psutil.virtual_memory()
        report.memory_gb = mem.total / (1024 ** 3)
    except ImportError:
        report.memory_gb = 0.0
        logger.debug("psutil 未安装，无法检测内存")

    # GPU + 显存
    try:
        import torch
        if torch.cuda.is_available():
            report.gpu_available = True
            report.gpu_name = torch.cuda.get_device_name(0)
            vram_bytes = torch.cuda.get_device_properties(0).total_memory
            report.gpu_vram_gb = vram_bytes / (1024 ** 3)
    except ImportError:
        report.gpu_available = False
        logger.debug("torch 未安装，无法检测 GPU")

    # API Key
    api_key = os.getenv("OPENAI_API_KEY", "")
    report.api_base_url = os.getenv("OPENAI_BASE_URL", "https://api.deepseek.com/v1")
    if api_key and api_key not in ("sk-placeholder", "your_api_key_here", ""):
        report.api_key_available = True

    # 本地模型文件
    report.local_model_path = os.getenv("LOCAL_MODEL_PATH", "")
    if report.local_model_path and os.path.exists(report.local_model_path):
        report.local_model_exists = True

    # vLLM 服务检测
    try:
        import requests
        vllm_url = "http://localhost:8000/v1/models"
        resp = requests.get(vllm_url, timeout=2)
        if resp.status_code == 200:
            report.vllm_available = True
            report.vllm_url = vllm_url.replace("/models", "/chat/completions")
    except Exception:
        pass

    # 模型层级
    if report.gpu_vram_gb >= 22:
        report.model_tier = "ultra"
    elif report.gpu_vram_gb >= 10:
        report.model_tier = "balanced"
    elif report.gpu_vram_gb >= 6:
        report.model_tier = "light"
    elif report.api_key_available:
        report.model_tier = "api"
    else:
        report.model_tier = "light"

    # 推荐模式（从高到低匹配，vLLM 优先级最高）
    if report.vllm_available:
        report.recommended_mode = "vllm"
        report.mode_reason = "检测到 vLLM 本地推理服务，性能最优"
    elif report.gpu_available and report.gpu_vram_gb >= 22:
        report.recommended_mode = "local_27b"
        report.mode_reason = f"24G 显存显卡 {report.gpu_name}，推荐本地 27B 重度模式"
    elif report.gpu_available and report.gpu_vram_gb >= 10:
        report.recommended_mode = "local_14b"
        report.mode_reason = f"{report.gpu_vram_gb:.0f}G 显存显卡 {report.gpu_name}，推荐本地 14B 平衡模式"
    elif report.api_key_available:
        report.recommended_mode = "api"
        report.mode_reason = "检测到 API Key，推荐云端 API 轻量模式"
    elif report.gpu_available and report.gpu_vram_gb >= 6:
        report.recommended_mode = "local_7b"
        report.mode_reason = f"{report.gpu_vram_gb:.0f}G 显存，推荐本地 7B 入门模式"
    else:
        report.recommended_mode = "none"
        report.mode_reason = "无 API Key 且无可用 GPU，使用模板降级模式（无 AI 叙事）"

    return report


# ==========================================================================
# 二、配置加载（从 YAML → 构造完整引擎）
# ==========================================================================

def _load_yaml(filename: str) -> dict:
    """加载项目根目录下的 YAML 配置文件"""
    path = PROJECT_ROOT / filename
    if not path.exists():
        logger.warning(f"配置文件不存在：{path}")
        return {}
    import yaml
    with open(path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f) or {}


def build_engine_from_yaml(
    mode: str = "auto",
    total_chapters: int = 5,
    ticks_per_chapter: int = 20,
    main_objective_override: str = "",
) -> tuple:
    """从 YAML 配置文件构造完整的离线推演引擎。

    返回:
        (EngineAdapter, EnvironmentReport, dict) — 引擎实例、环境报告、配置摘要
    """
    from backend.engine_config import EngineConfig
    from backend.config import WorldConfig, CharacterConfig
    from backend.world import World
    from backend.character import CharacterAgent, Goal

    # 1. 环境检测
    env_report = detect_environment()

    # 2. 确定 AI provider
    provider = _resolve_provider(mode, env_report)

    # 3. 初始化统一 AI 客户端
    from backend.ai_client import init_client as _init_backend_ai
    _init_backend_ai(provider=provider)

    # 4. 加载配置
    plot_cfg = _load_yaml("plot.yaml")
    map_cfg = _load_yaml("map.yaml")
    chars_cfg = _load_yaml("characters.yaml")
    factions_cfg = _load_yaml("factions.yaml")
    world_mech_cfg = _load_yaml("world_mechanics.yaml")

    # 5. 构造 WorldConfig
    world_init = plot_cfg.get("world_init", {})
    novel_meta = plot_cfg.get("novel_meta", {})
    genre = world_init.get("theme", "修仙")
    main_obj = main_objective_override or world_init.get("main_objective", "")

    world_config = WorldConfig(
        name=novel_meta.get("title", "未名世界"),
        genre=genre,
        main_objective=main_obj,
        description=world_init.get("description", ""),
        tone=plot_cfg.get("narrative_style", {}).get("tone", "客观叙事") if isinstance(plot_cfg.get("narrative_style"), dict) else "客观叙事",
        current_situation="故事即将展开，各方势力暗流涌动。",
    )
    world_config.factions = factions_cfg.get("factions", [])

    # 加载世界机制到 world_config
    if world_mech_cfg and world_mech_cfg.get('rules'):
        world_config.world_rules = [
            f"{r.get('name', '')}：{r.get('description', '')}"
            for r in world_mech_cfg['rules']
        ]

    # 加载主线约束
    story_constraint_cfg = plot_cfg.get("story_constraint", None)
    if story_constraint_cfg:
        world_config.story_constraint = dict(story_constraint_cfg)

    world = World(world_config)

    # 6. 构造角色
    characters = []
    char_list = chars_cfg.get("characters", chars_cfg.get("chars", []))
    for cdata in char_list:
        name = cdata.get("name", "")
        if not name:
            continue
        cc = CharacterConfig(
            name=name,
            gender=cdata.get("gender", "男"),
            age=int(cdata.get("age", 25)),
            personality=cdata.get("personality", ""),
            background=cdata.get("fate_arc", cdata.get("background", "")),
        )
        # 属性
        if "attrs" in cdata:
            cc.attributes = dict(cdata["attrs"])

        agent = CharacterAgent(cc)

        # 短期目标
        goal_text = cdata.get("goal", "")
        if goal_text:
            agent.short_term_goals.append(Goal(content=goal_text, priority=8))

        # 终极目标
        ult = cdata.get("ultimate_goal", "")
        if ult:
            agent.long_term_goal.description = ult

        # 所属势力
        faction = cdata.get("faction", "")
        if faction:
            agent.config.faction = faction

        characters.append(agent)

    # 7. 引擎配置
    engine_config = EngineConfig(
        total_chapters=total_chapters,
        ticks_per_chapter=ticks_per_chapter,
        tick_speed="normal",
        end_behavior="wrap_up",
        ai_provider=provider,
        offline_mode=(provider == "none"),
    )

    # 8. 构造 EngineAdapter
    from novel_world.adapter.adapter import EngineAdapter
    adapter = EngineAdapter(config=engine_config)
    adapter.init_game(world, characters)

    config_summary = {
        "world_name": world_config.name,
        "genre": genre,
        "main_objective": main_obj,
        "characters_count": len(characters),
        "factions_count": len(factions_cfg.get("factions", [])),
        "total_chapters": total_chapters,
        "ticks_per_chapter": ticks_per_chapter,
        "ai_provider": provider,
    }

    return adapter, env_report, config_summary


def _resolve_provider(mode: str, env_report: EnvironmentReport) -> str:
    """将用户指定的 mode 解析为具体的 provider 值"""
    if mode == "auto":
        rec = env_report.recommended_mode
        if rec.startswith("local_"):
            return "local"
        return rec

    mode_map = {
        "none": "none",
        "api": "api",
        "local": "local",
        "local_7b": "local",
        "local_14b": "local",
        "local_27b": "local",
    }
    return mode_map.get(mode, "none")


# ==========================================================================
# 三、离线模式入口
# ==========================================================================

def run_offline(
    mode: str = "auto",
    total_chapters: int = 5,
    ticks_per_chapter: int = 20,
    output_dir: str = None,
    main_objective: str = "",
) -> dict:
    """运行离线批量推演，生成完整小说。

    Args:
        mode: 运行模式 auto/none/api/local
        total_chapters: 总章节数
        ticks_per_chapter: 每章 tick 数
        output_dir: 输出目录，默认 output/
        main_objective: 覆盖主线目标

    Returns:
        生成结果摘要 dict
    """
    from datetime import datetime
    start_time = datetime.now()

    print("=" * 60)
    print("  小说世界引擎 — 离线批量推演")
    print(f"  启动时间：{start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    print()

    # 1. 环境检测
    print("[检测] 运行环境...")
    env_report = detect_environment()
    print(f"  OS: {env_report.os} / Python {env_report.python_version}")
    print(f"  内存: {env_report.memory_gb:.1f} GB")
    if env_report.gpu_available:
        print(f"  GPU: {env_report.gpu_name} ({env_report.gpu_vram_gb:.1f} GB)")
    else:
        print("  GPU: 未检测到")
    print(f"  API Key: {'可用' if env_report.api_key_available else '不可用/占位符'}")
    print(f"  推荐模式: {env_report.recommended_mode} — {env_report.mode_reason}")
    print()

    # 2. 构建引擎
    print("[初始化] 从 YAML 构建引擎...")
    adapter, env_report, summary = build_engine_from_yaml(
        mode=mode,
        total_chapters=total_chapters,
        ticks_per_chapter=ticks_per_chapter,
        main_objective_override=main_objective,
    )
    print(f"  世界: {summary['world_name']} ({summary['genre']})")
    print(f"  主线: {summary['main_objective']}")
    print(f"  角色: {summary['characters_count']} 个")
    print(f"  势力: {summary['factions_count']} 个")
    print(f"  章节: {total_chapters} 章 × {ticks_per_chapter} tick")
    print(f"  AI 模式: {summary['ai_provider']}")
    print()

    # 3. 推演循环
    print("[推演] 开始生成章节...")
    print()

    chapters = []
    output_path = Path(output_dir) if output_dir else PROJECT_ROOT / "output"
    output_path.mkdir(parents=True, exist_ok=True)
    chapters_dir = output_path / "chapters"
    chapters_dir.mkdir(parents=True, exist_ok=True)

    import re
    for ch in range(1, total_chapters + 1):
        title = f"第{ch}章"
        print(f"--- 第 {ch} 章 ---")
        result = adapter.run_chapter(title)
        chapters.append(result)

        # 保存单章
        safe_title = re.sub(r'[\\/:*?"<>|]', '_', title)
        ch_file = chapters_dir / f"chapter_{ch:03d}_{safe_title}.txt"
        text = result.get("narrative", result.get("text", ""))
        with open(ch_file, 'w', encoding='utf-8') as f:
            f.write(f"{title}\n\n")
            f.write(text)
            f.write("\n\n")
            collisions = result.get("collisions", [])
            if collisions:
                f.write(f"\n--- 本章碰撞 ({len(collisions)} 次) ---\n")
                for i, c in enumerate(collisions):
                    if isinstance(c, dict):
                        f.write(f"  [{i+1}] {c.get('char_a_name','?')} vs {c.get('char_b_name','?')} "
                                f"[{c.get('collision_type','?')}]\n")
        print(f"  完成：{ch_file.name}（{len(text)} 字，{len(result.get('collisions', []))} 次碰撞）")

    print()
    print("[导出] 合并完整小说...")
    full_novel_file = output_path / "full_novel.txt"
    with open(full_novel_file, 'w', encoding='utf-8') as f:
        f.write(f"{summary['world_name']}\n")
        f.write(f"{'=' * 40}\n\n")
        for ch in chapters:
            title = ch.get("title", "")
            text = ch.get("narrative", ch.get("text", ""))
            f.write(f"\n{title}\n\n")
            f.write(text)
            f.write("\n\n")
    print(f"  完整小说：{full_novel_file}")

    # 摘要报告
    end_time = datetime.now()
    duration = (end_time - start_time).total_seconds()
    total_words = sum(len(ch.get("narrative", ch.get("text", ""))) for ch in chapters)
    total_collisions = sum(len(ch.get("collisions", [])) for ch in chapters)

    report = {
        "world_name": summary["world_name"],
        "genre": summary["genre"],
        "total_chapters": len(chapters),
        "total_words": total_words,
        "total_collisions": total_collisions,
        "duration_seconds": round(duration, 1),
        "ai_provider": summary["ai_provider"],
        "output_file": str(full_novel_file),
        "env_report": env_report.to_dict(),
    }

    # 保存报告
    report_file = output_path / "generation_report.json"
    with open(report_file, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print()
    print("=" * 60)
    print("  推演完成！")
    print(f"  章节数：{len(chapters)}  总字数：{total_words}")
    print(f"  碰撞次数：{total_collisions}  用时：{duration:.1f}s")
    print(f"  完整小说：{full_novel_file}")
    print("=" * 60)

    return report


# ==========================================================================
# 四、Web GUI 模式入口
# ==========================================================================

def run_web(host: str = "127.0.0.1", port: int = 5000, mode: str = "auto"):
    """启动 Web GUI 模式（Flask 后端）。

    Args:
        host: 监听地址
        port: 监听端口
        mode: AI 模式 auto/none/api/local
    """
    print("=" * 60)
    print("  小说世界 — Web GUI 模式")
    print("=" * 60)

    # 环境检测
    env_report = detect_environment()
    print(f"  推荐模式: {env_report.recommended_mode} — {env_report.mode_reason}")

    # 初始化 AI 客户端
    provider = _resolve_provider(mode, env_report)
    from backend.ai_client import init_client as _init_backend_ai
    _init_backend_ai(provider=provider)
    print(f"  AI 模式: {provider}")
    print()

    # 启动 Flask
    from app import app
    print(f"  访问地址：http://{host}:{port}")
    print("  按 Ctrl+C 停止")
    print()
    app.run(host=host, port=port, debug=False)


# ==========================================================================
# 五、命令行入口
# ==========================================================================

def main():
    import argparse
    parser = argparse.ArgumentParser(description="小说世界 — 统一启动中台")
    sub = parser.add_subparsers(dest="command", help="命令")

    # detect
    p_detect = sub.add_parser("detect", help="仅检测环境，输出推荐模式")

    # offline
    p_off = sub.add_parser("offline", help="离线批量推演")
    p_off.add_argument("--mode", default="auto", help="运行模式 auto/none/api/local")
    p_off.add_argument("--chapters", type=int, default=5, help="总章节数")
    p_off.add_argument("--ticks", type=int, default=20, help="每章 tick 数")
    p_off.add_argument("--output", default=None, help="输出目录")
    p_off.add_argument("--main-objective", default="", help="覆盖主线目标")

    # web
    p_web = sub.add_parser("web", help="Web GUI 模式")
    p_web.add_argument("--host", default="127.0.0.1", help="监听地址")
    p_web.add_argument("--port", type=int, default=5000, help="监听端口")
    p_web.add_argument("--mode", default="auto", help="AI 模式 auto/none/api/local")

    args = parser.parse_args()

    if args.command == "detect":
        report = detect_environment()
        print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
        print(f"\n推荐模式：{report.recommended_mode}")
        print(f"原因：{report.mode_reason}")
        return

    if args.command == "offline":
        run_offline(
            mode=args.mode,
            total_chapters=args.chapters,
            ticks_per_chapter=args.ticks,
            output_dir=args.output,
            main_objective=args.main_objective,
        )
        return

    if args.command == "web":
        run_web(host=args.host, port=args.port, mode=args.mode)
        return

    # 默认：显示帮助
    parser.print_help()


if __name__ == "__main__":
    main()
