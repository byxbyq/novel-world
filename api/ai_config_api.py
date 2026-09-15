"""AI 模型配置 API：多 Provider 切换、用量统计、连接测试

从 书斋V66-新重构 移植，使用 ModelRouter 而非旧 AIClient。
"""


@app.route("/api/ai/config", methods=["GET"])
def api_ai_config_get():
    """获取当前 AI 模型配置"""
    try:
        cfg = {
            "provider": model_router.get_provider(),
            "deepseek": dict(model_router.config.get("deepseek", {})),
            "ollama": dict(model_router.config.get("ollama", {})),
            "openai": dict(model_router.config.get("openai", {})),
        }
        # 去掉内部字段
        for p in ("deepseek", "ollama", "openai"):
            if "_comment" in cfg[p]:
                del cfg[p]["_comment"]
        return jsonify({"ok": True, "config": cfg})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/ai/config", methods=["POST"])
def api_ai_config_post():
    """保存 AI 模型配置并切换 Provider"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({"ok": False, "error": "请求体为空"}), 400

        provider = data.get("provider")
        if provider and provider in ("deepseek", "ollama", "openai"):
            model_router.set_provider(provider)

        # 写入各 provider 配置
        for p in ("deepseek", "ollama", "openai"):
            if p in data and isinstance(data[p], dict):
                for k, v in data[p].items():
                    if k not in ("_comment",):
                        model_router.config[p][k] = v

        model_router._save_config()
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/ai/test", methods=["GET"])
def api_ai_test():
    """测试当前 AI 服务连接"""
    try:
        test_result = model_router.generate_safe("请回复 OK，只回复这两个字母")
        ok, msg = test_result
        return jsonify({
            "ok": ok,
            "message": msg[:200] if not ok else "连接成功",
        })
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/ai/usage", methods=["GET"])
def api_ai_usage():
    """获取 AI 用量统计"""
    try:
        stats = model_router.get_usage_stats()
        return jsonify({"ok": True, "usage": stats})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500
