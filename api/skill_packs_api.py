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
    """导入技能包。
    支持两种请求体：
    1) 技能包 JSON：{id,name,type,description,content,...} -> 直接安装
    2) 小说文本蒸馏：{novel_text: "..."} -> novel_distill 解析并批量安装
    """
    try:
        data = request.get_json(silent=True) or {}
        if not data:
            return jsonify({"error": "请求体为空，请提供技能包 JSON 或小说文本"}), 400

        # 小说文本蒸馏模式
        novel_text = (data.get("novel_text") or "").strip()
        if novel_text:
            skill_type = data.get("skill_type", "technique")
            distills = novel_distill(novel_text, skill_type=skill_type)
            if not distills:
                return jsonify({"error": "未能从文本中解析出技能包，请使用 markdown 风格分段（## 技能名 + 说明/用法）"}), 400
            installed = []
            for pack_data in distills:
                pack = skill_manager.import_skill(pack_data)
                installed.append(pack.to_dict())
            return jsonify({
                "status": "ok",
                "count": len(installed),
                "skills": installed,
                "message": f"已从小说文本蒸馏并安装 {len(installed)} 个技能包",
            })

        # 直接导入技能包 JSON
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
