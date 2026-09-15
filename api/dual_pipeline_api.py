"""双管线 API：管线状态查询与切换"""


@app.route("/api/pipeline/status", methods=["GET"])
def api_pipeline_status():
    """返回当前双管线状态"""
    try:
        status = {
            "default_pipe": dual_pipeline.default_pipe,
            "local_configured": dual_pipeline.local is not None,
            "api_configured": dual_pipeline.api is not None,
        }

        if dual_pipeline.local:
            status["local"] = {
                "base_url": dual_pipeline.local.base_url,
                "model": dual_pipeline.local.model,
                "provider": dual_pipeline.local.provider,
            }
        if dual_pipeline.api:
            status["api"] = {
                "base_url": dual_pipeline.api.base_url,
                "model": dual_pipeline.api.model,
                "provider": dual_pipeline.api.provider,
            }

        return jsonify({"status": "ok", "pipeline": status})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/pipeline/switch", methods=["POST"])
def api_pipeline_switch():
    """切换管线模式（local / api）"""
    try:
        data = request.get_json() or {}
        mode = (data.get("mode") or "").strip().lower()

        if mode not in ("local", "api"):
            return jsonify({"error": "mode 必须是 local 或 api"}), 400

        if mode == "local" and not dual_pipeline.local:
            return jsonify({"error": "本地管线未配置"}), 400
        if mode == "api" and not dual_pipeline.api:
            return jsonify({"error": "API 管线未配置"}), 400

        dual_pipeline.default_pipe = mode

        return jsonify({
            "status": "ok",
            "mode": mode,
            "model": dual_pipeline.local.model if mode == "local" else dual_pipeline.api.model,
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500
