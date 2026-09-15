"""人味审 API：六维度人味审计"""


@app.route("/api/humanity/audit", methods=["POST"])
def api_humanity_audit():
    """对文本执行六维度人味审计"""
    data = request.get_json() or {}
    content = (data.get("content") or "").strip()

    if not content:
        return jsonify({"error": "请提供待审核的文本内容"}), 400

    try:
        result = verve_review_svc(content)

        return jsonify({
            "status": "ok",
            "audit": {
                "scores": result.scores,
                "humanity_index": result.humanity_index,
                "flaws": result.flaws,
                "strengths": result.strengths,
                "rewrite_hint": result.rewrite_hint,
                "text_sample": result.text_sample,
            },
        })
    except Exception as e:
        return jsonify({"error": f"审计失败: {str(e)}"}), 500


@app.route("/api/humanity/report", methods=["POST"])
def api_humanity_report():
    """生成人味审计报告（Markdown）"""
    data = request.get_json() or {}
    content = (data.get("content") or "").strip()

    if not content:
        return jsonify({"error": "请提供待审核的文本内容"}), 400

    try:
        result = verve_review_svc(content)
        report = render_humanity_report(result)
        return jsonify({
            "status": "ok",
            "report": report,
            "humanity_index": result.humanity_index,
        })
    except Exception as e:
        return jsonify({"error": f"生成报告失败: {str(e)}"}), 500
