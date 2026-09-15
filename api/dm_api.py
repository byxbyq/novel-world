"""DM 模式 API：控制、干预、天意指引、时间线检查、势力管理"""

# ── DM 模式 API ──

@app.route("/api/dm/state", methods=["GET"])
def api_dm_state():
    """获取 DM 当前状态"""
    state = dm.get_state()
    with _engine_lock:
        state["intervention_log"] = [
            {"tick": e["tick"], "type": e["type"], "cmd": e["cmd"]}
            for e in dm._intervention_log
        ]
    return jsonify(state)


@app.route("/api/dm/preview", methods=["GET"])
def api_dm_preview():
    """增量获取正在生成的正文预览（前端按 offset 拉取新增部分）"""
    try:
        offset = int(request.args.get("offset", 0))
    except (TypeError, ValueError):
        offset = 0
    return jsonify(dm.get_preview(offset))


@app.route("/api/dm/characters", methods=["GET"])
def api_dm_characters():
    """获取角色列表（供 DM 干预面板使用）"""
    with _engine_lock:
        if not engine._characters:
            return jsonify({"characters": []})
        chars = []
        for c in engine._characters:
            chars.append({
                "name": c.name,
                "mood": c.current_mood,
                "location": c.current_location,
                "target": c.long_term_goal.description,
            })
        return jsonify({"characters": chars})


@app.route("/api/dm/start", methods=["POST"])
def api_dm_start():
    """开始推演（后台线程）"""
    with _engine_lock:
        if not engine.world:
            return jsonify({"error": "游戏尚未初始化"}), 400

        api_key = os.getenv("OPENAI_API_KEY", "")
        if not api_key or api_key == "your_api_key_here":
            return jsonify({"error": "API Key 无效或未配置"}), 401

        data = request.get_json() or {}
        title = data.get("title", "")

        if dm.get_state()["dm_state"] not in ("idle", "stopped"):
            return jsonify({"error": "推演已在运行中"}), 409

        dm.reset()
        dm.start(title)
        return jsonify({"status": "ok", "message": "推演已启动"})


@app.route("/api/dm/pause", methods=["POST"])
def api_dm_pause():
    """暂停推演"""
    ok = dm.pause()
    if ok:
        return jsonify({"status": "ok", "message": "已暂停"})
    return jsonify({"error": "当前状态不允许暂停"}), 409


@app.route("/api/dm/resume", methods=["POST"])
def api_dm_resume():
    """继续推演"""
    ok = dm.resume()
    if ok:
        return jsonify({"status": "ok", "message": "已继续"})
    return jsonify({"error": "当前状态不允许继续"}), 409


@app.route("/api/dm/step", methods=["POST"])
def api_dm_step():
    """单步执行 1 个 Tick"""
    ok = dm.step_once()
    if ok:
        return jsonify({"status": "ok", "message": "单步执行中"})
    return jsonify({"error": "当前状态不允许单步"}), 409


@app.route("/api/dm/stop", methods=["POST"])
def api_dm_stop():
    """终止推演"""
    dm.stop()
    return jsonify({"status": "ok", "message": "已终止"})


@app.route("/api/dm/inject", methods=["POST"])
def api_dm_inject():
    """注入 DM 干预指令"""
    data = request.get_json() or {}
    cmd_type = data.get("type", "")
    valid_types = {"modify_character", "inject_event", "force_move", "add_goal"}
    if cmd_type not in valid_types:
        return jsonify({"error": f"不支持的指令类型: {cmd_type}，可选: {', '.join(sorted(valid_types))}"}), 400
    result = dm.execute_command(data)
    if result.get("success"):
        return jsonify(result)
    return jsonify(result), 400


@app.route("/api/dm/snapshot", methods=["POST"])
def api_dm_snapshot():
    """创建快照（预留）"""
    return jsonify({"status": "ok", "message": "快照功能预留"}), 200


@app.route("/api/dm/rollback", methods=["POST"])
def api_dm_rollback():
    """回退到快照（预留）"""
    return jsonify({"status": "ok", "message": "回退功能预留"}), 200


# ── DM 质量问题联动 API ──

@app.route("/api/dm/issues", methods=["GET"])
def api_dm_issues():
    """获取质量管线推送的待处理问题列表"""
    issues = dm.get_pending_issues()
    return jsonify({"issues": issues, "count": len(issues)})


@app.route("/api/dm/issues/<issue_id>/resolve", methods=["POST"])
def api_dm_resolve_issue(issue_id):
    """处理质量问题：ignore / pause / rollback / fix"""
    data = request.get_json() or {}
    action = data.get("action", "ignore")
    resolved_by = data.get("resolved_by", "dm")

    valid_actions = {"ignore", "pause", "rollback", "fix"}
    if action not in valid_actions:
        return jsonify({"error": f"不支持的操作: {action}，可选: {', '.join(sorted(valid_actions))}"}), 400

    ok = dm.resolve_issue(issue_id, action, resolved_by)
    if ok:
        return jsonify({"status": "ok", "message": f"问题 {issue_id} 已处理: {action}"})
    return jsonify({"error": f"问题 {issue_id} 不存在或已处理"}), 404


# ── 天意指引 API ──

@app.route("/api/dm/guidance", methods=["POST"])
def api_dm_guidance():
    """发送天意指引"""
    data = request.get_json() or {}
    character_name = data.get("character_name", "")
    message = data.get("message", "")
    form_str = data.get("form", "auto")
    strength_str = data.get("strength", "hint")

    if not character_name or not message:
        return jsonify({"error": "缺少角色名称或指引内容"}), 400

    # 校验形式
    form_map = {
        "dream": GuidanceForm.DREAM,
        "epiphany": GuidanceForm.EPIPHANY,
        "omen": GuidanceForm.OMEN,
        "encounter": GuidanceForm.ENCOUNTER,
        "inner_voice": GuidanceForm.INNER_VOICE,
        "auto": GuidanceForm.AUTO,
    }
    if form_str not in form_map:
        return jsonify({"error": f"不支持的融入形式: {form_str}"}), 400

    # 校验强度
    strength_map = {
        "direct": GuidanceStrength.DIRECT,
        "hint": GuidanceStrength.HINT,
        "vague": GuidanceStrength.VAGUE,
    }
    if strength_str not in strength_map:
        return jsonify({"error": f"不支持的指引强度: {strength_str}"}), 400

    # 检查 DM 状态：仅 PAUSED 时允许注入
    dm_state = dm.get_state()
    if dm_state["dm_state"] != "paused":
        return jsonify({"error": "天意指引只能在暂停状态下发送"}), 409

    result = divine.send_guidance(
        character_name=character_name,
        message=message,
        form=form_map[form_str],
        strength=strength_map[strength_str],
    )
    return jsonify(result)


# ── 时间线检查 API ──

@app.route("/api/timeline/issues", methods=["GET"])
def api_timeline_issues():
    """获取所有待解决的时间线问题"""
    with _engine_lock:
        issues = engine.get_timeline_issues()
        return jsonify({"status": "ok", "issues": issues})


@app.route("/api/timeline/report", methods=["GET"])
def api_timeline_report():
    """获取时间线检查报告"""
    with _engine_lock:
        report = engine.get_timeline_report()
        return jsonify({"status": "ok", "report": report})


@app.route("/api/timeline/data", methods=["GET"])
def api_timeline_data():
    """获取可视化时间线数据：章节事件、角色动向、关键情节"""
    with _engine_lock:
        chapters = engine.chapters
        characters = getattr(engine, "_characters", [])

        # 回填空标题
        if engine.outline_data:
            vols = engine.outline_data.get("volumes", [])
            cumulative = 0
            outline_titles = {}
            for vol in vols:
                chs = vol.get("chapters", [])
                for idx, ch_info in enumerate(chs):
                    outline_titles[cumulative + idx + 1] = ch_info.get("title", "")
                cumulative += len(chs)
            for ch in chapters:
                if not ch.get("title"):
                    num = ch.get("chapter", 0)
                    ch["title"] = outline_titles.get(num, "")

        # 构建大纲章节映射（全局索引 -> 规划信息）
        outline_map = {}
        if engine.outline_data:
            cumulative = 0
            for vol in engine.outline_data.get("volumes", []):
                vol_name = vol.get("name", "")
                vol_theme = vol.get("theme", "")
                for i, ch_plan in enumerate(vol.get("chapters", [])):
                    global_idx = cumulative + i + 1
                    outline_map[global_idx] = {
                        "volume": vol_name,
                        "volume_theme": vol_theme,
                        "planned_title": ch_plan.get("title", ""),
                        "planned_summary": ch_plan.get("summary", ""),
                    }
                cumulative += len(vol.get("chapters", []))

        timeline = []
        for ch in chapters:
            num = ch.get("chapter", 0)
            plan = outline_map.get(num, {})
            entry = {
                "number": num,
                "title": ch.get("title", ""),
                "world_event": ch.get("world_event", ""),
                "narrative_len": len(ch.get("narrative", "")),
                "narrative_preview": (ch.get("narrative", "") or "")[:150],
                "character_actions": ch.get("character_actions", {}),
                "collisions": ch.get("collisions", []),
                # 大纲规划对比
                "planned_title": plan.get("planned_title", ""),
                "planned_summary": plan.get("planned_summary", ""),
                "volume": plan.get("volume", ""),
                "volume_theme": plan.get("volume_theme", ""),
                "has_outline": bool(plan),
            }
            timeline.append(entry)

        # 添加大纲中尚未生成的章节（规划但未执行）
        total_planned = len(outline_map)
        for ch_num in range(len(chapters) + 1, total_planned + 1):
            plan = outline_map.get(ch_num, {})
            if plan:
                timeline.append({
                    "number": ch_num,
                    "title": "",
                    "world_event": "",
                    "narrative_len": 0,
                    "narrative_preview": "",
                    "character_actions": {},
                    "collisions": [],
                    "planned_title": plan.get("planned_title", ""),
                    "planned_summary": plan.get("planned_summary", ""),
                    "volume": plan.get("volume", ""),
                    "volume_theme": plan.get("volume_theme", ""),
                    "has_outline": True,
                    "is_pending": True,
                })

        # Character list with current state
        char_list = []
        for c in characters:
            char_list.append({
                "name": c.name,
                "mood": c.current_mood,
                "location": c.current_location or "",
                "abilities": getattr(c.config, 'abilities', []) or [],
            })

        return jsonify({
            "status": "ok",
            "timeline": timeline,
            "characters": char_list,
            "total_chapters": len(chapters),
            "total_planned": total_planned,
            "has_outline": bool(engine.outline_data),
        })


# ── 势力管理 API（phase2_p1）──

@app.route("/api/dm/factions", methods=["GET"])
def api_dm_factions():
    """获取势力列表"""
    with _engine_lock:
        if not engine._nw_world:
            return jsonify({"factions": []})
        # 通过适配器获取势力摘要
        try:
            factions = engine.get_faction_summary()
        except Exception as e:
            return jsonify({"factions": [], "error": str(e)})
        return jsonify({"factions": factions})


@app.route("/api/dm/faction/<faction_id>", methods=["POST"])
def api_dm_update_faction(faction_id):
    """更新势力（名称/描述/敌对/同盟/目标等）"""
    with _engine_lock:
        data = request.get_json() or {}
        try:
            ok = engine.update_faction(faction_id, data)
            if ok:
                return jsonify({"status": "ok"})
            return jsonify({"error": "势力不存在"}), 404
        except Exception as e:
            return jsonify({"error": str(e)}), 500


@app.route("/api/dm/faction/<faction_id>/add_enemy", methods=["POST"])
def api_dm_add_enemy(faction_id):
    """为势力添加敌对关系（双向）"""
    with _engine_lock:
        data = request.get_json() or {}
        enemy_id = data.get("enemy_id", "")
        if not enemy_id:
            return jsonify({"error": "缺少 enemy_id"}), 400
        try:
            engine._nw_world.set_faction_enemies(faction_id, enemy_id)
            return jsonify({"status": "ok"})
        except Exception as e:
            return jsonify({"error": str(e)}), 500


@app.route("/api/dm/faction/<faction_id>/add_ally", methods=["POST"])
def api_dm_add_ally(faction_id):
    """为势力添加同盟关系（双向）"""
    with _engine_lock:
        data = request.get_json() or {}
        ally_id = data.get("ally_id", "")
        if not ally_id:
            return jsonify({"error": "缺少 ally_id"}), 400
        try:
            engine._nw_world.set_faction_allies(faction_id, ally_id)
            return jsonify({"status": "ok"})
        except Exception as e:
            return jsonify({"error": str(e)}), 500





# ── 时间线副本（分支）API ──
# 每个副本独立存储章节，互不干扰
# _active_branch: 当前活跃的分支ID ("main" 或 "branch_xxx")
# _branch_chapters: {branch_id: [chapters...]} 每个分支独立的章节列表
# _main_chapters_backup: 主线章节备份（当切换到副本时保存主线进度）

_active_branch = "main"
_branch_chapters = {}  # {branch_id: [chapter_dicts...]}

@app.route("/api/branches", methods=["GET"])
def api_list_branches():
    """列出所有副本/分支"""
    with _engine_lock:
        result = []
        # 主线
        main_count = len(_branch_chapters.get("main", engine.chapters))
        result.append({
            "id": "main",
            "name": "主线",
            "from_chapter": 0,
            "chapter_count": main_count,
            "is_active": _active_branch == "main",
            "created_at": "",
        })
        for bid, bdata in _branches.items():
            ch_count = len(_branch_chapters.get(bid, []))
            result.append({
                "id": bid,
                "name": bdata.get("name", ""),
                "from_chapter": bdata.get("from_chapter", 0),
                "chapter_count": ch_count,
                "is_active": _active_branch == bid,
                "created_at": bdata.get("created_at", ""),
            })
        return jsonify({
            "status": "ok",
            "branches": result,
            "active_branch": _active_branch,
        })


@app.route("/api/branches", methods=["POST"])
def api_create_branch():
    """从指定章节创建副本（分支）—— 不破坏主线"""
    with _engine_lock:
        data = request.get_json() or {}
        from_chapter = int(data.get("from_chapter", 0))
        name = data.get("name", "").strip()
        if not name:
            name = "副本-第%d章分叉" % from_chapter
        # 获取当前主线章节
        main_chapters = _branch_chapters.get("main", engine.chapters)
        if from_chapter < 0 or from_chapter > len(main_chapters):
            return jsonify({"error": "章节号超出范围（当前%d章）" % len(main_chapters)}), 400

        import datetime
        branch_id = "branch_%d_%s" % (len(_branches)+1, datetime.datetime.now().strftime("%H%M%S"))
        # 快照主线章节（截取到分叉点）作为副本的初始章节
        _branch_chapters[branch_id] = [dict(ch) for ch in main_chapters[:from_chapter]]
        _branches[branch_id] = {
            "name": name,
            "from_chapter": from_chapter,
            "created_at": datetime.datetime.now().isoformat()[:19],
        }
        return jsonify({
            "status": "ok",
            "branch_id": branch_id,
            "message": "副本[%s]已从第%d章创建（当前%d章）" % (name, from_chapter, from_chapter)
        })


@app.route("/api/branches/<branch_id>/switch", methods=["POST"])
def api_switch_branch(branch_id):
    """切换到指定副本 —— 保存当前进度，加载副本进度"""
    with _engine_lock:
        global _active_branch
        if branch_id != "main" and branch_id not in _branches:
            return jsonify({"error": "副本不存在"}), 404

        # 保存当前分支的章节状态
        _branch_chapters[_active_branch] = list(engine.chapters)

        # 切换到目标分支
        _active_branch = branch_id

        # 加载目标分支的章节（如果有的话）
        if branch_id in _branch_chapters:
            engine.chapters = list(_branch_chapters[branch_id])
        elif branch_id == "main":
            # 主线：恢复主线章节
            if "main" in _branch_chapters:
                engine.chapters = list(_branch_chapters["main"])

        bdata = _branches.get(branch_id, {"name": "主线"})
        return jsonify({
            "status": "ok",
            "message": "已切换到[%s]" % bdata.get("name", "主线"),
            "chapter_count": len(engine.chapters),
            "active_branch": _active_branch,
        })


@app.route("/api/branches/<branch_id>", methods=["DELETE"])
def api_delete_branch(branch_id):
    """删除副本"""
    with _engine_lock:
        global _active_branch
        if branch_id not in _branches:
            return jsonify({"error": "副本不存在"}), 404
        name = _branches[branch_id].get("name", "")
        # 如果删除的是当前活跃分支，切回主线
        if _active_branch == branch_id:
            _branch_chapters["main"] = list(engine.chapters) if _active_branch == "main" else _branch_chapters.get("main", [])
            _active_branch = "main"
            if "main" in _branch_chapters:
                engine.chapters = list(_branch_chapters["main"])
        del _branches[branch_id]
        _branch_chapters.pop(branch_id, None)
        return jsonify({"status": "ok", "message": "副本[%s]已删除" % name})
