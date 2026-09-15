"""Prompt 管理 API：CRUD、版本历史、回滚"""

# ── Prompt 管理 API（phase2_p2）──

@app.route("/api/prompts", methods=["GET"])
def api_prompts_list():
    """列出所有 prompt 元信息"""
    try:
        from novel_world.engine.core.prompt_registry import PromptRegistry
        return jsonify({"prompts": PromptRegistry.get_all_metadata()})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/prompts/<name>", methods=["GET"])
def api_prompt_get(name):
    """获取指定 prompt 的当前版本"""
    try:
        from novel_world.engine.core.prompt_registry import PromptRegistry
        raw = PromptRegistry.get_raw(name)
        return jsonify({"name": name, "template": raw})
    except KeyError:
        return jsonify({"error": f"Prompt '{name}' 未注册"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/prompts/<name>", methods=["PUT"])
def api_prompt_update(name):
    """更新 prompt（自动保存旧版本）"""
    try:
        from novel_world.engine.core.prompt_registry import PromptRegistry
        data = request.get_json() or {}
        new_template = data.get("template", "")
        if not new_template:
            return jsonify({"error": "缺少 template 字段"}), 400
        version = PromptRegistry.update(name, new_template)
        return jsonify({"status": "ok", "saved_version": version})
    except KeyError:
        return jsonify({"error": f"Prompt '{name}' 未注册"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/prompts/<name>/history", methods=["GET"])
def api_prompt_history(name):
    """获取版本历史"""
    try:
        from novel_world.engine.core.prompt_registry import PromptRegistry
        history = PromptRegistry.get_history(name)
        return jsonify({"name": name, "history": history, "current_length": len(PromptRegistry.get_raw(name))})
    except KeyError:
        return jsonify({"error": f"Prompt '{name}' 未注册"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/prompts/<name>/version/<version>", methods=["GET"])
def api_prompt_version(name, version):
    """获取指定版本内容"""
    try:
        from novel_world.engine.core.prompt_registry import PromptRegistry
        template = PromptRegistry.get_version(name, version)
        return jsonify({"name": name, "version": version, "template": template})
    except KeyError as e:
        return jsonify({"error": str(e)}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/prompts/<name>/rollback", methods=["POST"])
def api_prompt_rollback(name):
    """回滚到上一版本"""
    try:
        from novel_world.engine.core.prompt_registry import PromptRegistry
        data = request.get_json() or {}
        steps = int(data.get("steps", 1))
        version = PromptRegistry.rollback(name, steps)
        if version is None:
            return jsonify({"status": "ok", "message": "无历史版本可回滚"})
        return jsonify({"status": "ok", "rolled_to": version})
    except KeyError:
        return jsonify({"error": f"Prompt '{name}' 未注册"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/prompts/reload", methods=["POST"])
def api_prompt_reload():
    """从 JSON 文件热重载"""
    try:
        from novel_world.engine.core.prompt_registry import PromptRegistry
        data = request.get_json() or {}
        filepath = data.get("filepath", "")
        if not filepath:
            return jsonify({"error": "缺少 filepath 字段"}), 400
        result = PromptRegistry.reload_from_file(filepath)
        return jsonify({"status": "ok", **result})
    except FileNotFoundError as e:
        return jsonify({"error": str(e)}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500


