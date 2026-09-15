"""章节相关 API：生成、状态、列表、添加角色、引导、编辑/删除、版本历史"""

@app.route("/api/init", methods=["POST"])
def api_init():
    """初始化游戏：接收世界设定和角色设定"""
    with _engine_lock:
        data = request.get_json()

        # 解析世界设定
        wd = data.get("world", {})
        world_config = WorldConfig(
            name=wd.get("name", "未命名世界"),
            genre=wd.get("genre", "玄幻"),
            era=wd.get("era", "古代"),
            description=wd.get("description", ""),
            rules=wd.get("rules", []),
            key_locations=wd.get("key_locations", []),
            current_situation=wd.get("current_situation", ""),
            tone=wd.get("tone", "史诗冒险"),
            main_objective=wd.get("main_objective", ""),
            world_stage=wd.get("world_stage", "opening"),
            perspective=wd.get("perspective", "third"),
        )
        world = World(world_config)

        # 解析角色设定
        characters = []
        for cd in data.get("characters", []):
            char_config = CharacterConfig(
                name=cd.get("name", ""),
                age=cd.get("age", 20),
                gender=cd.get("gender") or "男",
                personality=cd.get("personality", ""),
                background=cd.get("background", ""),
                appearance=cd.get("appearance", ""),
                short_term_goals=cd.get("short_term_goals", []),
                long_term_goal=cd.get("long_term_goal", ""),
                abilities=cd.get("abilities", []),
                weaknesses=cd.get("weaknesses", []),
                initial_location=cd.get("initial_location", ""),
                initial_relationships=cd.get("initial_relationships", {}),
            )
            characters.append(CharacterAgent(char_config))

        engine.init_game(world, characters)

        # 应用引擎配置
        ec = data.get("engine_config", {})
        if ec.get("total_chapters"):
            engine.config.total_chapters = int(ec["total_chapters"])
        if ec.get("ticks_per_chapter"):
            engine.config.ticks_per_chapter = int(ec["ticks_per_chapter"])

        # 新建项目：清除旧大纲，避免污染新项目
        _outlines["auto"] = None
        engine.outline_data = None
        # 同步引擎配置到前端状态
        engine.config.total_chapters = int(ec.get("total_chapters", engine.config.total_chapters))

        # 启动即自动保存
        engine.save("auto")

        return jsonify({"status": "ok", "state": engine.get_state()})


@app.route("/api/chapter", methods=["POST"])
def api_chapter():
    """生成下一章"""
    with _engine_lock:
        if not engine.world:
            return jsonify({"error": "游戏尚未初始化"}), 400

        # 检查 API Key 是否有效
        api_key = os.getenv("OPENAI_API_KEY", "")
        if not api_key or api_key == "your_api_key_here":
            return jsonify({
                "error": "API Key 无效或未配置，请在确认启动页面填写你的 OpenAI API Key"
            }), 401

        data = request.get_json() or {}
        title = data.get("title", "").strip()

        # 标题为空时，从大纲获取规划标题或自动生成
        if not title:
            next_ch = len(engine.chapters) + 1
            if engine.outline_data:
                vols = engine.outline_data.get("volumes", [])
                cumulative = 0
                for vol in vols:
                    chs = vol.get("chapters", [])
                    if next_ch <= cumulative + len(chs):
                        local_idx = next_ch - cumulative - 1
                        if 0 <= local_idx < len(chs):
                            title = chs[local_idx].get("title", "")
                            break
                    cumulative += len(chs)
            if not title:
                title = f"第{next_ch}章"

        try:
            # 构建当前章的卷纲上下文
            next_ch = len(engine.chapters) + 1
            vol_outline_context = ""
            volumes = outline_manager.get_volumes()
            for vol in volumes:
                chs = vol.get("chapters", [])
                if next_ch in chs:
                    vo = vol.get("outline", {})
                    if vo:
                        lines = []
                        if vo.get("theme"):
                            lines.append(f"【卷主题】{vo['theme']}")
                        if vo.get("summary"):
                            lines.append(f"【卷概要】{vo['summary']}")
                        if vo.get("key_events"):
                            lines.append(f"【卷关键事件】" + "；".join(vo["key_events"]))
                        if vo.get("character_arcs"):
                            lines.append(f"【卷角色弧线】" + "；".join(vo["character_arcs"]))
                        vol_outline_context = "\n".join(lines)
                    break

            # 叠加本章的大纲规划（章节级标题+摘要，来自 engine.outline_data）
            if engine.outline_data:
                cumulative = 0
                for vol in engine.outline_data.get("volumes", []):
                    chs = vol.get("chapters", [])
                    if next_ch <= cumulative + len(chs):
                        local_idx = next_ch - cumulative - 1
                        if 0 <= local_idx < len(chs):
                            ch_plan = chs[local_idx]
                            if isinstance(ch_plan, dict):
                                plan_lines = []
                                if ch_plan.get("title"):
                                    plan_lines.append(f"【本章规划标题】{ch_plan['title']}")
                                if (ch_plan.get("summary") or "").strip():
                                    plan_lines.append(f"【本章规划内容】{ch_plan['summary']}")
                                # 附上下一章规划，便于衔接
                                nxt = chs[local_idx + 1] if local_idx + 1 < len(chs) else None
                                if isinstance(nxt, dict) and (nxt.get("summary") or "").strip():
                                    plan_lines.append(f"【下一章走向】{nxt['summary']}")
                                if plan_lines:
                                    vol_outline_context = (vol_outline_context + "\n" if vol_outline_context else "") + "\n".join(plan_lines)
                        break
                    cumulative += len(chs)

            chapter = engine.run_chapter(
                title=title,
                outline_context=vol_outline_context,
            )
            # 同步当前章节到活跃分支存储
            if "_branch_chapters" in dir() or True:
                try:
                    _branch_chapters[_active_branch] = list(engine.chapters)
                except Exception:
                    pass
            return jsonify({"status": "ok", "chapter": chapter})
        except Exception as e:
            err_msg = str(e)
            if "401" in err_msg or "unauthorized" in err_msg.lower() or "invalid api key" in err_msg.lower():
                return jsonify({
                    "error": "API Key 无效或未配置，请在确认启动页面填写你的 OpenAI API Key"
                }), 401
            return jsonify({"error": err_msg}), 500


@app.route("/api/state", methods=["GET"])
def api_state():
    """获取当前状态"""
    with _engine_lock:
        if not engine.world:
            return jsonify({"status": "not_initialized"})
        return jsonify({"status": "ok", "state": engine.get_state()})


@app.route("/api/chapters", methods=["GET"])
def api_chapters():
    """获取所有已生成章节（标题为空时从大纲回填）"""
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
        for ch in engine.chapters:
            if not ch.get("title"):
                num = ch.get("chapter", 0)
                ch["title"] = outline_titles.get(num, "")
    return jsonify({"chapters": engine.chapters})


@app.route("/api/add-character", methods=["POST"])
def api_add_character():
    """运行时添加新角色"""
    with _engine_lock:
        if not engine.world:
            return jsonify({"error": "游戏尚未初始化"}), 400
        data = request.get_json() or {}
        name = data.get("name", "").strip()
        if not name:
            return jsonify({"error": "角色名不能为空"}), 400
        # 检查重复
        for c in engine._characters:
            if c.name == name:
                return jsonify({"error": f"角色'{name}'已存在"}), 400
        try:
            from backend.config import CharacterConfig
            from backend.character import CharacterAgent
            from novel_world.engine.core.character import Character, CharType, CharState
            # 1. 添加 backend 角色
            char_config = CharacterConfig(
                name=name,
                age=int(data.get("age", 20)),
                gender=data.get("gender", "男"),
                personality=data.get("personality", ""),
                background=data.get("background", ""),
                appearance=data.get("appearance", ""),
                short_term_goals=data.get("short_term_goals", []),
                long_term_goal=data.get("long_term_goal", ""),
                abilities=data.get("abilities", []),
                weaknesses=data.get("weaknesses", []),
                initial_location=data.get("initial_location", ""),
            )
            new_char = CharacterAgent(char_config)
            engine._characters.append(new_char)
            # 2. 添加 novel_world 角色
            import random
            nw_char = Character(
                name=name,
                char_type=CharType.NPC,
                state=CharState.IDLE,
                personality=data.get("personality_list", []),
                pos=(random.randint(0, engine._nw_world.map_size[0]-1), random.randint(0, engine._nw_world.map_size[1]-1)),
                goal=data.get("long_term_goal", ""),
            )
            engine._nw_world.add_character(nw_char)
            engine._nw_characters.append(nw_char)
            return jsonify({"status": "ok", "message": f"角色 {name} 已添加"})
        except Exception as e:
            return jsonify({"error": f"添加失败: {str(e)}"}), 500


@app.route("/api/guide-plot", methods=["POST"])
def api_guide_plot():
    """逐章模式下引导情节（不走DM流程）"""
    with _engine_lock:
        if not engine.world:
            return jsonify({"error": "游戏尚未初始化"}), 400
        data = request.get_json() or {}
        guide_type = data.get("type", "inject_event")
        try:
            if guide_type == "inject_event":
                desc = data.get("description", "").strip()
                if not desc:
                    return jsonify({"error": "事件描述不能为空"}), 400
                engine.world.add_event("world", desc, [c.name for c in engine._characters])
                for char in engine._characters:
                    char.remember("世界事件", desc)
                engine.current_chapter_events.append(desc)
                return jsonify({"status": "ok", "message": "事件已注入"})
            elif guide_type == "add_goal":
                name = data.get("name", "").strip()
                goal = data.get("goal", "").strip()
                if not name or not goal:
                    return jsonify({"error": "角色名和目标不能为空"}), 400
                for char in engine._characters:
                    if char.name == name:
                        from backend.character import Goal
                        char.short_term_goals.append(Goal(content=goal, weight=float(data.get("weight", 1.0))))
                        return jsonify({"status": "ok", "message": f"已为 {name} 添加目标"})
                return jsonify({"error": f"角色 {name} 不存在"}), 404
            elif guide_type == "modify_character":
                name = data.get("name", "").strip()
                field = data.get("field", "")
                value = data.get("value", "")
                if not name or not field:
                    return jsonify({"error": "角色名和字段不能为空"}), 400
                for char in engine._characters:
                    if char.name == name:
                        if field == "target":
                            if char.short_term_goals:
                                char.short_term_goals[0].description = value
                            char.remember("目标变更", value)
                        elif field == "mood":
                            char.current_mood = value
                        elif field == "position":
                            engine.world.set_character_position(name, value)
                        return jsonify({"status": "ok", "message": f"已修改 {name} 的 {field}"})
                return jsonify({"error": f"角色 {name} 不存在"}), 404
            else:
                return jsonify({"error": f"不支持的引导类型: {guide_type}"}), 400
        except Exception as e:
            return jsonify({"error": f"操作失败: {str(e)}"}), 500


@app.route("/api/chapter/<int:index>", methods=["DELETE"])
def api_delete_chapter(index):
    """删除指定章节"""
    with _engine_lock:
        if index < 0 or index >= len(engine.chapters):
            return jsonify({"error": "章节不存在"}), 404
        removed = engine.chapters.pop(index)
        # 重新编号
        for i, ch in enumerate(engine.chapters):
            ch["chapter"] = i + 1
        return jsonify({"status": "ok", "removed_title": removed.get("title", "")})


@app.route("/api/chapter/<int:index>", methods=["PUT"])
def api_edit_chapter(index):
    """编辑指定章节正文"""
    with _engine_lock:
        if index < 0 or index >= len(engine.chapters):
            return jsonify({"error": "章节不存在"}), 404
        data = request.get_json() or {}
        new_title = data.get("title")
        new_narrative = data.get("narrative")
        if new_title is not None:
            engine.chapters[index]["title"] = new_title
        if new_narrative is not None:
            engine.chapters[index]["narrative"] = new_narrative
        return jsonify({"status": "ok"})



@app.route("/api/chapter/<int:index>/history", methods=["GET"])
def api_chapter_history(index):
    """获取章节编辑历史"""
    versions = _chapter_versions.get(index, [])
    return jsonify({"index": index, "versions": versions})


@app.route("/api/chapter/<int:index>/history", methods=["POST"])
def api_chapter_save_version(index):
    """保存章节当前版本到历史"""
    with _engine_lock:
        if index < 0 or index >= len(engine.chapters):
            return jsonify({"error": "章节不存在"}), 404
        ch = engine.chapters[index]
        version = {
            "title": ch.get("title", ""),
            "narrative": ch.get("narrative", ""),
            "saved_at": str(len(_chapter_versions.get(index, [])) + 1),
        }
        if index not in _chapter_versions:
            _chapter_versions[index] = []
        _chapter_versions[index].append(version)
        # 只保留最近10个版本
        if len(_chapter_versions[index]) > 10:
            _chapter_versions[index] = _chapter_versions[index][-10:]
        return jsonify({"status": "ok", "version_count": len(_chapter_versions[index])})


@app.route("/api/chapter/<int:index>/rollback", methods=["POST"])
def api_chapter_rollback(index):
    """回滚到上一个版本"""
    with _engine_lock:
        if index < 0 or index >= len(engine.chapters):
            return jsonify({"error": "章节不存在"}), 404
        versions = _chapter_versions.get(index, [])
        if not versions:
            return jsonify({"error": "没有历史版本"}), 400
        # 先保存当前版本
        ch = engine.chapters[index]
        current = {"title": ch.get("title", ""), "narrative": ch.get("narrative", "")}
        versions.append(current)
        # 恢复到上一版本
        prev = versions.pop(0)
        ch["title"] = prev["title"]
        ch["narrative"] = prev["narrative"]
        return jsonify({"status": "ok", "restored_version": prev})

