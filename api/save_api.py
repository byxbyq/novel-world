"""存档与项目管理 API"""

@app.route("/api/save", methods=["POST"])
def api_save():
    """保存游戏"""
    with _engine_lock:
        data = request.get_json() or {}
        slot = data.get("slot", "auto")
        try:
            engine.save(slot)
            return jsonify({"status": "ok", "slot": slot})
        except ValueError as e:
            return jsonify({"error": str(e)}), 400
        except Exception as e:
            return jsonify({"error": str(e)}), 500


@app.route("/api/load/<slot>", methods=["POST"])
def api_load(slot):
    """加载存档"""
    with _engine_lock:
        try:
            loaded = engine.load(slot)
        except ValueError as e:
            return jsonify({"error": str(e)}), 400
        if loaded:
            # 同步大纲到 _outlines（前端依赖此变量，始终用 "auto" 键）
            if engine.outline_data:
                _outlines["auto"] = engine.outline_data
            # 同步章节到活跃分支
            try:
                _branch_chapters[_active_branch] = list(engine.chapters)
            except Exception:
                pass
            return jsonify({"status": "ok", "state": engine.get_state()})
        return jsonify({"error": "存档不存在"}), 404


@app.route("/api/saves", methods=["GET"])
def api_saves():
    """列出存档"""
    return jsonify({"saves": engine.storage.list_slots()})


@app.route("/api/projects", methods=["GET"])
def api_projects():
    """列出所有项目（基于存档）"""
    saves = engine.storage.list_slots()
    projects = []
    for s in saves:
        projects.append({
            "id": s["slot"],
            "name": s.get("world_name", "未命名"),
            "chapter": s.get("chapter", 0),
            "saved_at": s.get("saved_at", ""),
        })
    # Sort by saved_at descending
    projects.sort(key=lambda x: x.get("saved_at", ""), reverse=True)
    return jsonify({"projects": projects})


@app.route("/api/delete_save/<slot>", methods=["DELETE"])
def api_delete_save(slot):
    """删除存档"""
    with _engine_lock:
        try:
            engine.storage.delete_slot(slot)
        except ValueError as e:
            return jsonify({"error": str(e)}), 400
        return jsonify({"status": "ok"})


@app.route("/api/save-key", methods=["POST"])
def api_save_key():
    """保存 API Key：写入单一真源 data/ai_config.json，并同步 .env 与各客户端"""
    data = request.get_json() or {}
    key = (data.get("key") or "").strip()
    provider = (data.get("provider") or "deepseek").strip()

    if not key:
        return jsonify({"error": "API Key 不能为空"}), 400
    if not key.startswith("sk-"):
        return jsonify({"error": "API Key 格式不正确，应以 sk- 开头"}), 400

    try:
        # 1. 单一真源：写入 data/ai_config.json（通过 ModelRouter 生效）
        if provider in model_router.config:
            model_router.config[provider]["api_key"] = key
            model_router._save_config()
        # 2. 同步 .env（引擎侧 OPENAI_BASE_URL 链路仍从环境变量取 Key）
        set_key(ENV_PATH, "OPENAI_API_KEY", key)
        os.environ["OPENAI_API_KEY"] = key
        # 3. 同步旧 AIClient 内存配置（若已实例化，避免与真源漂移）
        if _client is not None and provider in _client.config:
            _client.config[provider]["api_key"] = key
        # 4. 同步引擎侧客户端
        if engine._nw_ai_client is not None:
            engine._nw_ai_client.provider = "api"
            engine._nw_ai_client.api_key = key
        return jsonify({"status": "ok", "message": f"API Key 已保存至 {provider} 配置并生效"})
    except Exception as e:
        return jsonify({"error": f"保存失败：{str(e)}"}), 500


