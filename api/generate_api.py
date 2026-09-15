"""AI 生成与配置 API：世界生成、角色生成、内容分析、引擎配置"""

# ── EngineConfig API（修复一） ──

@app.route("/api/engine/config", methods=["GET"])
def api_get_engine_config():
    """获取当前引擎配置"""
    with _engine_lock:
        return jsonify({
            "total_chapters": engine.config.total_chapters,
            "ticks_per_chapter": engine.config.ticks_per_chapter,
            "auto_pause_between_chapters": engine.config.auto_pause_between_chapters,
            "end_behavior": engine.config.end_behavior,
            "expected_ending": engine.config.expected_ending,
        })


@app.route("/api/engine/config", methods=["POST"])
def api_set_engine_config():
    """更新引擎配置"""
    with _engine_lock:
        data = request.get_json() or {}
        engine.config.total_chapters = data.get("total_chapters", engine.config.total_chapters)
        engine.config.ticks_per_chapter = data.get("ticks_per_chapter", engine.config.ticks_per_chapter)
        engine.config.auto_pause_between_chapters = data.get("auto_pause_between_chapters", engine.config.auto_pause_between_chapters)
        engine.config.end_behavior = data.get("end_behavior", engine.config.end_behavior)
        engine.config.expected_ending = data.get("expected_ending", engine.config.expected_ending)

        # 如果主线目标被更新，重新校准角色目标权重（修复三）
        if engine.world:
            new_main_objective = data.get("main_objective")
            if new_main_objective is not None and new_main_objective != engine.world.config.main_objective:
                engine.world.config.main_objective = new_main_objective
                engine.align_goals_to_main_objective()

        return jsonify({"status": "ok"})


# ── 世界设定编辑 API（开局后中途修改初始设定） ──

@app.route("/api/world-config", methods=["GET"])
def api_get_world_config():
    """获取当前世界设定（供中途编辑）"""
    with _engine_lock:
        if not engine.world:
            return jsonify({"error": "游戏尚未初始化"}), 400
        wc = engine.world.config
        return jsonify({
            "status": "ok",
            "config": {
                "name": wc.name,
                "genre": wc.genre,
                "era": wc.era,
                "description": wc.description,
                "rules": wc.rules or [],
                "key_locations": wc.key_locations or [],
                "current_situation": wc.current_situation,
                "tone": wc.tone,
                "main_objective": wc.main_objective,
                "perspective": getattr(wc, "perspective", "third"),
            }
        })


@app.route("/api/world-config", methods=["PUT"])
def api_update_world_config():
    """中途更新世界设定；主线目标变化时重新校准角色目标权重"""
    with _engine_lock:
        if not engine.world:
            return jsonify({"error": "游戏尚未初始化"}), 400
        wc = engine.world.config
        data = request.get_json() or {}

        if "name" in data:
            new_name = str(data["name"]).strip()
            if not new_name:
                return jsonify({"error": "世界名称不能为空"}), 400
            wc.name = new_name
        for field in ("genre", "era", "description", "current_situation", "tone", "perspective"):
            if field in data:
                setattr(wc, field, data[field])
        if "rules" in data:
            wc.rules = [str(r).strip() for r in (data["rules"] or []) if str(r).strip()]
        if "key_locations" in data:
            wc.key_locations = [str(p).strip() for p in (data["key_locations"] or []) if str(p).strip()]

        # 主线目标变化 → 重新校准角色目标权重（与 /api/engine/config 同一机制）
        if "main_objective" in data and data["main_objective"] != wc.main_objective:
            wc.main_objective = data["main_objective"]
            try:
                engine.align_goals_to_main_objective()
            except Exception:
                pass  # 校准失败不阻塞设定保存

        return jsonify({"status": "ok", "message": "世界设定已更新"})


@app.route("/api/generate-world", methods=["POST"])
def api_generate_world():
    """AI 生成/补全世界设定"""
    api_key = os.getenv("OPENAI_API_KEY", "")
    if not api_key or api_key == "your_api_key_here":
        return jsonify({"error": "请先在确认启动页面填写 OpenAI API Key"}), 401

    data = request.get_json() or {}
    try:
        from backend.ai_client import generate_world
        result = generate_world(data)
        return jsonify({"status": "ok", "world": result})
    except Exception as e:
        err_msg = str(e)
        if "401" in err_msg or "unauthorized" in err_msg.lower() or "invalid api key" in err_msg.lower():
            return jsonify({"error": "API Key 无效，请在确认启动页面重新填写"}), 401
        return jsonify({"error": f"AI 生成失败：{err_msg}"}), 500


@app.route("/api/generate-characters", methods=["POST"])
def api_generate_characters():
    """AI 生成角色"""
    api_key = os.getenv("OPENAI_API_KEY", "")
    if not api_key or api_key == "your_api_key_here":
        return jsonify({"error": "请先在确认启动页面填写 OpenAI API Key"}), 401

    data = request.get_json() or {}
    world_data = data.get("world", {})
    count = int(data.get("count", 2))
    count = max(1, min(5, count))

    try:
        from backend.ai_client import generate_characters
        result = generate_characters(world_data, count)
        return jsonify({"status": "ok", "characters": result})
    except Exception as e:
        err_msg = str(e)
        if "401" in err_msg or "unauthorized" in err_msg.lower() or "invalid api key" in err_msg.lower():
            return jsonify({"error": "API Key 无效，请在确认启动页面重新填写"}), 401
        return jsonify({"error": f"AI 生成失败：{err_msg}"}), 500


@app.route("/api/analyze-content", methods=["POST"])
def api_analyze_content():
    """AI 分析灵感/大纲文本，提取世界和角色设定"""
    api_key = os.getenv("OPENAI_API_KEY", "")
    if not api_key or api_key == "your_api_key_here":
        return jsonify({"error": "请先点击顶部「AI 模型」配置 API Key"}), 401

    data = request.get_json() or {}
    content = (data.get("content") or "").strip()

    if not content:
        return jsonify({"error": "请输入需要分析的文本内容"}), 400

    try:
        from backend.ai_client import analyze_content
        result = analyze_content(content)
        return jsonify({"status": "ok", "world": result.get("world", {}), "characters": result.get("characters", [])})
    except Exception as e:
        err_msg = str(e)
        if "401" in err_msg or "unauthorized" in err_msg.lower() or "invalid api key" in err_msg.lower():
            return jsonify({"error": "API Key 无效，请点击顶部「AI 模型」重新配置"}), 401
        return jsonify({"error": f"AI 分析失败：{err_msg}"}), 500


