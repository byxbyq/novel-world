"""模型路由 API：列出可用 provider、切换模型、查看用量"""


@app.route("/api/model/list", methods=["GET"])
def api_model_list():
    """返回所有 provider 及当前配置"""
    try:
        providers = get_available_providers()
        current = next((p for p in providers if p["is_current"]), providers[0] if providers else {})
        return jsonify({
            "ok": True,
            "data": providers,
            "current_provider": current.get("provider", ""),
            "current_model": current.get("model", ""),
        })
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/model/switch", methods=["POST"])
def api_model_switch():
    """切换 AI 提供商和模型"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({"ok": False, "error": "请求体为空"}), 400
        result = switch_model(
            provider=data.get("provider"),
            model=data.get("model"),
            base_url=data.get("base_url"),
            api_key=data.get("api_key"),
        )
        return jsonify({"ok": True, "data": result})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/model/usage", methods=["GET"])
def api_model_usage():
    """获取 AI 用量统计"""
    try:
        stats = get_client().get_usage_stats()
        return jsonify({"ok": True, "data": stats})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500
