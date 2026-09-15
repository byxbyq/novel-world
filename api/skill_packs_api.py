"""技能包系统 API：列表、导入、搜索"""


@app.route("/api/skill-packs/list", methods=["GET"])
def api_skill_packs_list():
    """返回已安装技能包列表"""
    try:
        keyword = request.args.get("keyword", "")
        skill_type = request.args.get("type", "")

        if keyword or skill_type:
            skills = skill_manager.search_skills(keyword=keyword, skill_type=skill_type)
        else:
            skills = skill_manager.list_skills()

        return jsonify({
            "status": "ok",
            "count": len(skills),
            "skills": [s.to_dict() for s in skills],
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/skill-packs/import", methods=["POST"])
def api_skill_packs_import():
    """导入技能包"""
    try:
        data = request.get_json() or {}
        if not data:
            return jsonify({"error": "请求体为空"}), 400

        pack = skill_manager.import_skill(data)
        return jsonify({
            "status": "ok",
            "skill": pack.to_dict(),
        })
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/skill-packs/<pack_id>", methods=["GET"])
def api_skill_packs_get(pack_id):
    """获取单个技能包详情"""
    try:
        pack = skill_manager.get_skill(pack_id)
        if not pack:
            return jsonify({"error": "技能包不存在"}), 404
        return jsonify({"status": "ok", "skill": pack.to_dict()})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/skill-packs/<pack_id>", methods=["DELETE"])
def api_skill_packs_delete(pack_id):
    """删除技能包"""
    try:
        ok = skill_manager.delete_skill(pack_id)
        if not ok:
            return jsonify({"error": "技能包不存在或删除失败"}), 404
        return jsonify({"status": "ok"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
