"""后处理去AI腔 API：AI味检测 + 文本清洗 + 规则管理 + 局部段落修复"""

import json
from backend.post_processor import (
    DE_REPLACEMENTS,
    CONNECTOR_REPLACEMENTS,
    AI_WORDS_LIMIT,
    AI_WORDS_SYNONYMS,
    DE_DENSITY_TARGET,
    apply_de_ai_postprocess,
    apply_structure_perturb,
    detect_ai_flavor,
    compute_ai_score,
    local_fix_from_flavor,
    local_fix_multi_round,
    anti_external_rewrite,
    humanize_rewrite,
)

# 规则开关状态（内存中）
_rules_state = {
    "de_density": True,
    "connector_replace": True,
    "ai_words_limit": True,
    "ai_detection": True,
    "structure_perturb": True,
}


@app.route("/api/post-process/run", methods=["POST"])
def api_post_process_run():
    """对文本执行去AI腔后处理 + AI味检测"""
    data = request.get_json() or {}
    content = (data.get("content") or "").strip()

    if not content:
        return jsonify({"error": "请提供待处理的文本内容"}), 400

    result = {"original_length": len(content)}

    # 去AI腔清洗
    try:
        cleaned = content
        if _rules_state.get("de_density"):
            cleaned = apply_de_ai_postprocess(
                cleaned,
                de_density_target=DE_DENSITY_TARGET,
                words_limit=AI_WORDS_LIMIT if _rules_state.get("ai_words_limit") else {},
                connector_reps=CONNECTOR_REPLACEMENTS if _rules_state.get("connector_replace") else {},
                de_reps=DE_REPLACEMENTS,
                words_synonyms=AI_WORDS_SYNONYMS,
            )
        result["cleaned"] = cleaned
        result["cleaned_length"] = len(cleaned)
        result["chars_removed"] = len(content) - len(cleaned)
    except Exception as e:
        result["cleaned"] = content
        result["clean_error"] = str(e)

    # AI味检测
    try:
        if _rules_state.get("ai_detection"):
            flavor = detect_ai_flavor(cleaned if "cleaned" in result else content)
            score = compute_ai_score(flavor)
            result["ai_flavor"] = flavor
            result["ai_score"] = score
    except Exception as e:
        result["ai_flavor"] = {"error": str(e)}

    return jsonify({"status": "ok", "result": result})


@app.route("/api/post-process/rules", methods=["GET"])
def api_post_process_rules():
    """返回去AI腔规则列表及开关状态"""
    return jsonify({
        "status": "ok",
        "rules": {
            "de_density": {
                "name": "\"的\"字密度控制",
                "target": DE_DENSITY_TARGET,
                "enabled": _rules_state.get("de_density", True),
            },
            "connector_replace": {
                "name": "连接词替换",
                "count": len(CONNECTOR_REPLACEMENTS),
                "enabled": _rules_state.get("connector_replace", True),
            },
            "ai_words_limit": {
                "name": "AI高频词限制",
                "count": len(AI_WORDS_LIMIT),
                "enabled": _rules_state.get("ai_words_limit", True),
            },
            "ai_detection": {
                "name": "AI味检测",
                "enabled": _rules_state.get("ai_detection", True),
            },
            "structure_perturb": {
                "name": "结构扰动（拆长段/合短段，不耗Token）",
                "enabled": _rules_state.get("structure_perturb", True),
            },
        },
    })


@app.route("/api/post-process/toggle-rule", methods=["POST"])
def api_post_process_toggle_rule():
    """切换规则开关"""
    data = request.get_json() or {}
    rule_id = (data.get("rule") or "").strip()

    if rule_id not in _rules_state:
        return jsonify({"error": f"未知规则: {rule_id}", "available": list(_rules_state.keys())}), 400

    _rules_state[rule_id] = not _rules_state[rule_id]
    return jsonify({
        "status": "ok",
        "rule": rule_id,
        "enabled": _rules_state[rule_id],
    })


@app.route("/api/post-process/chapter/<int:index>", methods=["POST"])
def api_post_process_chapter(index):
    """对已生成的章节重新执行去AI味后处理"""
    with _engine_lock:
        if index < 0 or index >= len(engine.chapters):
            return jsonify({"error": "章节不存在"}), 404

        ch = engine.chapters[index]
        original = ch.get("narrative", "")
        if not original:
            return jsonify({"error": "该章节没有正文内容"}), 400

        # 后处理前检测
        before_flavor = detect_ai_flavor(original)

        # 执行后处理
        cleaned = apply_de_ai_postprocess(
            original,
            de_density_target=DE_DENSITY_TARGET,
            words_limit=AI_WORDS_LIMIT if _rules_state.get("ai_words_limit") else {},
            connector_reps=CONNECTOR_REPLACEMENTS if _rules_state.get("connector_replace") else {},
            de_reps=DE_REPLACEMENTS,
            words_synonyms=AI_WORDS_SYNONYMS,
        )
        # 结构扰动：只拆合段落不改文字，破坏外部检测器的均匀性特征
        if _rules_state.get("structure_perturb"):
            cleaned = apply_structure_perturb(cleaned)

        # 更新章节正文
        ch["narrative"] = cleaned

        # 后处理后检测
        after_flavor = detect_ai_flavor(cleaned)

        ch["ai_flavor"] = {
            "before_score": before_flavor.get("score", 0),
            "before_level": before_flavor.get("level", "unknown"),
            "after_score": after_flavor.get("score", 0),
            "after_level": after_flavor.get("level", "unknown"),
            "ai_probability": after_flavor.get("ai_probability", 0),
            "summary": after_flavor.get("summary", ""),
            "stats": after_flavor.get("stats", {}),
        }

        return jsonify({
            "status": "ok",
            "chapter_index": index,
            "ai_flavor": ch["ai_flavor"],
            "original_length": len(original),
            "cleaned_length": len(cleaned),
        })


@app.route("/api/post-process/local-fix/<int:index>", methods=["POST"])
def api_local_fix_chapter(index):
    """对已生成章节执行深度去AI味

    完整流程：规则清洗 → 多轮AI局部修复 → 黑名单后处理
    - 规则清洗：削"的"字、去连接词、替换AI高频词（不消耗Token）
    - 多轮AI修复：反复检测→定位→重写→后处理，第3轮起激进模式
    - 跨轮追踪已修复段落，避免重复
    - force_continue=true 时即使分数不降也继续尝试不同段落
    """
    with _engine_lock:
        if index < 0 or index >= len(engine.chapters):
            return jsonify({"error": "章节不存在"}), 404

        ch = engine.chapters[index]
        original = ch.get("narrative", "")
        if not original:
            return jsonify({"error": "该章节没有正文内容"}), 400

        data = request.get_json() or {}
        max_fixes = data.get("max_fixes", 8)
        dry_run = data.get("dry_run", False)
        multi_round = data.get("multi_round", True)
        max_rounds = data.get("max_rounds", 5)
        force_continue = data.get("force_continue", True)
        apply_rules = data.get("apply_rules", True)
        force = data.get("force", False)  # 强制重新处理（即使已达标）

        # 检测当前AI味
        before_flavor = detect_ai_flavor(original)

        if multi_round and not dry_run:
            # 深度多轮修复（规则清洗 + AI修复）
            fixed_content, fix_report = local_fix_multi_round(
                original,
                max_rounds=max_rounds,
                max_fixes_per_round=max_fixes,
                force_continue=force_continue,
                apply_rules_first=apply_rules,
                force=force,
            )
        else:
            # 单轮修复
            fixed_content, fix_report = local_fix_from_flavor(
                original, before_flavor, max_fixes=max_fixes, dry_run=dry_run
            )

        # 非dry_run时更新章节正文
        if not dry_run and fix_report.get("content_changed", False):
            ch["narrative"] = fixed_content
            # 修复后重新检测
            after_flavor = detect_ai_flavor(fixed_content)
            ch["ai_flavor"] = {
                "before_score": before_flavor.get("score", 0),
                "before_level": before_flavor.get("level", "unknown"),
                "after_score": after_flavor.get("score", 0),
                "after_level": after_flavor.get("level", "unknown"),
                "ai_probability": after_flavor.get("ai_probability", 0),
                "summary": after_flavor.get("summary", ""),
                "stats": after_flavor.get("stats", {}),
                "local_fix": fix_report,
            }
        else:
            after_flavor = before_flavor

        return jsonify({
            "status": "ok",
            "chapter_index": index,
            "dry_run": dry_run,
            "multi_round": multi_round,
            "fix_report": fix_report,
            "before_score": before_flavor.get("score", 0),
            "after_score": after_flavor.get("score", 0),
            "before_probability": before_flavor.get("ai_probability", 0),
            "after_probability": after_flavor.get("ai_probability", 0),
            "original_length": len(original),
            "fixed_length": len(fixed_content),
            "content_changed": fix_report.get("content_changed", False),
            "skipped_reason": fix_report.get("skipped_reason", ""),
        })


@app.route("/api/post-process/anti-external/<int:index>", methods=["POST"])
def api_anti_external_chapter(index):
    """反外部检测全文重写：逐段高温度重写，专门降低外部 AIGC 检测器的判定

    与深度去AI味的区别：不依赖自家检测结果定位，逐段重写全部长段落，
    自家检测已达标（但外部检测仍判 AI）时使用此接口。
    耗 Token 较多（每段一次 AI 调用），耗时约 2-5 分钟。
    """
    with _engine_lock:
        if index < 0 or index >= len(engine.chapters):
            return jsonify({"error": "章节不存在"}), 404

        ch = engine.chapters[index]
        original = ch.get("narrative", "")
        if not original:
            return jsonify({"error": "该章节没有正文内容"}), 400

        data = request.get_json() or {}
        max_paragraphs = data.get("max_paragraphs")  # None=全部

        before_flavor = detect_ai_flavor(original)

        fixed_content, report = anti_external_rewrite(
            original, max_paragraphs=max_paragraphs
        )

        if report.get("content_changed", False):
            ch["narrative"] = fixed_content
            after_flavor = detect_ai_flavor(fixed_content)
            ch["ai_flavor"] = {
                "before_score": before_flavor.get("score", 0),
                "before_level": before_flavor.get("level", "unknown"),
                "after_score": after_flavor.get("score", 0),
                "after_level": after_flavor.get("level", "unknown"),
                "ai_probability": after_flavor.get("ai_probability", 0),
                "summary": after_flavor.get("summary", ""),
                "stats": after_flavor.get("stats", {}),
                "anti_external": report,
            }
        else:
            after_flavor = before_flavor

        return jsonify({
            "status": "ok",
            "chapter_index": index,
            "report": report,
            "before_score": before_flavor.get("score", 0),
            "after_score": after_flavor.get("score", 0),
            "content_changed": report.get("content_changed", False),
            "original_length": len(original),
            "fixed_length": len(fixed_content),
        })


@app.route("/api/post-process/humanize/<int:index>", methods=["POST"])
def api_humanize_chapter(index):
    """人类化重写（移植自书斋V66“去AI味”按钮）：全文粗粝重写，temperature=1.3

    书斋实测：反复执行可将外部 AIGC 检测降到 4~5%。
    每轮产生完全不同的变体（可打乱段落顺序），逐步脱离 LLM 统计分布。
    """
    with _engine_lock:
        if index < 0 or index >= len(engine.chapters):
            return jsonify({"error": "章节不存在"}), 404

        ch = engine.chapters[index]
        original = ch.get("narrative", "")
        if not original:
            return jsonify({"error": "该章节没有正文内容"}), 400

        before_flavor = detect_ai_flavor(original)

        new_content, report = humanize_rewrite(original)

        if report.get("content_changed", False):
            ch["narrative"] = new_content
            after_flavor = detect_ai_flavor(new_content)
            ch["ai_flavor"] = {
                "before_score": before_flavor.get("score", 0),
                "before_level": before_flavor.get("level", "unknown"),
                "after_score": after_flavor.get("score", 0),
                "after_level": after_flavor.get("level", "unknown"),
                "ai_probability": after_flavor.get("ai_probability", 0),
                "summary": after_flavor.get("summary", ""),
                "stats": after_flavor.get("stats", {}),
                "humanize": report,
            }

        return jsonify({
            "status": "ok" if report.get("content_changed") else "noop",
            "chapter_index": index,
            "report": report,
            "before_score": before_flavor.get("score", 0),
            "content_changed": report.get("content_changed", False),
            "original_length": len(original),
            "fixed_length": len(new_content),
        })
