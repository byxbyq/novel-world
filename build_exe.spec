# -*- mode: python ; coding: utf-8 -*-
"""
小说世界 - PyInstaller 打包配置
运行: pyinstaller build_exe.spec
"""

import os
import sys

PROJECT_DIR = r"H:\素材资源\小说\新建文件夹\小说世界(单边终局)"

# ── 数据目录（递归收集） ──
_data_dirs = []
for dirname in ["frontend", "api", "backend", "novel_world", "utils",
                "docs", "examples"]:
    src = os.path.join(PROJECT_DIR, dirname)
    if os.path.isdir(src):
        if dirname == "backend":
            # backend 含运行时数据子目录 data（ai_config.json/ai_usage.json），必须排除
            # 逐文件收集，跳过 data 与 __pycache__，保持相对路径
            for root2, dirs2, files2 in os.walk(src):
                dirs2[:] = [d for d in dirs2 if d not in ("data", "__pycache__")]
                for fn in files2:
                    full = os.path.join(root2, fn)
                    rel = os.path.relpath(full, PROJECT_DIR)
                    _data_dirs.append((full, os.path.dirname(rel).replace("\\", "/")))
        else:
            _data_dirs.append((src, dirname))

# ── 单独数据文件 ──
_data_files = []
for fname in ["VERSION", ".env.example", "requirements.txt",
              "characters.yaml", "factions.yaml", "map.yaml", "plot.yaml", "relationships.yaml"]:
    src = os.path.join(PROJECT_DIR, fname)
    if os.path.isfile(src):
        _data_files.append((src, "."))

# ── 合并所有 datas ──
all_datas = _data_dirs + _data_files

# ── 隐藏导入（运行时动态 import 的模块） ──
hidden_imports = [
    # Flask 隐式依赖
    "flask", "flask_cors", "jinja2", "werkzeug", "markupsafe", "itsdangerous", "click",
    # 项目动态导入
    "backend.config", "backend.world", "backend.character",
    "backend.ai_client", "backend.post_processor", "backend.model_router",
    "backend.skill_packs", "backend.distilled_memory", "backend.humanity_audit",
    "backend.dual_pipeline", "backend.outline_system",
    "novel_world.adapter",
    "novel_world.engine.dm_state", "novel_world.engine.divine_guidance",
    "novel_world.engine.core.prompt_registry",
    # API 子模块
    "api.generate_api", "api.chat_api",
    "api.post_process_api", "api.skill_packs_api", "api.model_api",
    "api.humanity_audit_api", "api.dual_pipeline_api", "api.outline_api",
    "api.dm_api", "api.character_api", "api.chapter_api",
    # 第三方
    "dotenv", "httpx", "httpcore", "certifi", "charset_normalizer",
    "tqdm", "idna", "urllib3",
    # 资源管理
    "re", "threading",
]

a = Analysis(
    [os.path.join(PROJECT_DIR, "app.py")],
    pathex=[PROJECT_DIR],
    binaries=[],
    datas=all_datas,
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "tkinter", "matplotlib", "pandas", "scipy", "PIL", "cv2",
        "notebook", "jupyter", "IPython", "ipykernel",
        "setuptools", "pip", "wheel",
        "torch", "torchvision", "torchaudio", "torchtext",
        "numpy", "faiss", "sentence_transformers", "transformers",
        "tokenizers", "huggingface_hub", "safetensors", "scikit-learn",
        "tensorboard", "tensorflow", "keras",
        "sqlalchemy", "sqlite3", "pymongo",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=None,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=None)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="小说世界",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
