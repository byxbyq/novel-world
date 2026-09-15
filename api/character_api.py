"""角色相关 API：关系图谱、项目进度、角色编辑/详情"""

# ── 角色关系图谱 API ──

@app.route("/api/character-relations", methods=["GET"])
def api_character_relations():
    """获取角色关系图谱数据"""
    with _engine_lock:
        if not engine._characters:
            return jsonify({"nodes": [], "edges": []})

        nodes = []
        edges = []
        char_names = set()

        for c in engine._characters:
            char_names.add(c.name)
            nodes.append({
                "id": c.name,
                "gender": getattr(c.config, "gender", "") or "男",
                "age": getattr(c.config, "age", 20) or 20,
                "personality": getattr(c.config, "personality", "") or "",
                "location": c.current_location or "",
                "mood": c.current_mood or "",
                "goal": c.long_term_goal.description if c.long_term_goal else "",
                "npc_tier": getattr(c, "npc_tier", "main"),
            })

        # 从关系文本中提取关系
        for c in engine._characters:
            rel_text = c.relationship_text() if hasattr(c, 'relationship_text') else ""
            if rel_text:
                for other in engine._characters:
                    if other.name != c.name and other.name in rel_text:
                        # 提取关系描述（简单取两句之间提到对方名字的句子）
                        edges.append({
                            "source": c.name,
                            "target": other.name,
                            "label": "相关",
                        })

        # 去重边
        seen = set()
        unique_edges = []
        for e in edges:
            key = tuple(sorted([e["source"], e["target"]]))
            if key not in seen:
                seen.add(key)
                unique_edges.append(e)

        return jsonify({"nodes": nodes, "edges": unique_edges})


# ── 项目进度 API ──

@app.route("/api/progress", methods=["GET"])
def api_progress():
    """获取项目整体进度"""
    with _engine_lock:
        if not engine.world:
            return jsonify({"error": "游戏尚未初始化"}), 400

        total = engine.config.total_chapters
        current = len(engine.chapters)
        world_name = engine.world.config.name if engine.world else ""
        main_obj = engine.world.config.main_objective if engine.world else ""

        # 角色统计
        char_count = len(engine._characters)

        # 章节字数统计
        total_words = sum(len(ch.get("narrative", "")) for ch in engine.chapters)

        # 大纲进度
        outline = _outlines.get("auto", {})
        outline_volumes = len(outline.get("volumes", []))

        return jsonify({
            "status": "ok",
            "world_name": world_name,
            "main_objective": main_obj,
            "chapters_done": current,
            "chapters_total": total,
            "character_count": char_count,
            "total_words": total_words,
            "outline_volumes": outline_volumes,
        })





@app.route("/api/scan-characters", methods=["POST"])
def api_scan_characters():
    """扫描已有章节正文，发现并添加新角色。

    方法：收集所有2-4字候选名 → 在正文中搜索 → 根据上下文信号评分 → 过滤
    """
    import re
    from backend.config import CharacterConfig
    from backend.character import CharacterAgent

    with _engine_lock:
        if not engine.world:
            return jsonify({"error": "游戏尚未初始化"}), 400

        existing_names = set(c.name for c in engine._characters)

        # 非人名过滤
        skip_words = {
            "他们", "我们", "你们", "众人", "大家", "所有人", "任何人",
            "弟子", "弟子们", "长老", "长老们", "宗主", "掌门",
            "师兄", "师弟", "师姐", "师妹", "前辈", "晚辈", "小子",
            "一人", "两人", "三人", "四人", "五人", "六人", "七人", "八人", "九人", "十人",
            "一道", "一丝", "一股", "一阵", "一声", "一抹", "一片", "一团",
            "天玄宗", "血影宗", "青云宗", "内门", "外门", "真传",
            # 常见非人名短语
            "在心中", "心中问", "在心中问", "风在心中", "中问",
            "嘿嘿", "低声", "沉声", "随即", "老者", "随即咧嘴",
        }

        # 2字普通名词过滤
        skip_2char = {
            "目光", "心中", "身形", "衣袖", "手中", "脸色", "嘴角", "声音", "语气",
            "身影", "瞳孔", "膝盖", "指尖", "衣袂", "衣袍", "长啸", "呼啸",
            "地面", "通道", "石碑", "碎片", "宝珠", "锁链", "宫殿", "光柱", "封印",
            "灵力", "灵气", "气血", "魔气", "血光", "符文", "阵法", "禁制",
            "上古", "远古", "天外", "幽暗", "深邃", "漆黑", "幽蓝", "血红", "血色",
            "恐怖", "狰狞", "刺耳", "悠长", "古老", "苍老", "铜印", "长幡", "掌印",
            "血影", "天光", "口气",
        }

        # 收集所有2-4字候选名（用非贪婪+边界方式）
        all_text = "".join(ch.get("narrative", "") for ch in engine.chapters)

        # 逐位置滑动窗口提取所有唯一的2-4字组合
        candidates = set()
        chinese_runs = re.findall(r'[一-龥]+', all_text)
        for run in chinese_runs:
            for i in range(len(run)):
                for length in (2, 3, 4):
                    if i + length <= len(run):
                        w = run[i:i+length]
                        if w not in skip_words and not w.endswith("的") and not w.startswith("的"):
                            if not (len(w) == 2 and w in skip_2char):
                                candidates.add(w)

        # 对每个候选名，在正文中搜索并评分
        name_score = {}
        for name in candidates:
            score = 0
            for m in re.finditer(re.escape(name), all_text):
                start = m.start()
                end = m.end()
                after = all_text[end:min(len(all_text), end+6)]
                before = all_text[max(0, start-6):start]

                # 强信号：名字后面紧跟说话/动作词
                strong_after = ["道：", "道，", "说：", "说，", "冷笑", "一笑",
                                "冷声道", "沉声道", "淡淡道", "缓缓道", "急道", "怒道",
                                "喝道", "笑道", "哼道", "问道", "答道"]
                # 中等信号
                medium_after = ["目光", "身形", "衣袖", "手中", "脸色", "嘴角",
                                "声音", "语气", "身影", "一脚", "一手",
                                "瞳孔", "嘴角", "衣袖", "苍老", "冷冷",
                                "缓缓", "淡淡", "默默", "暗暗"]

                for sig in strong_after:
                    if after.startswith(sig):
                        score += 3
                        break
                else:
                    for sig in medium_after:
                        if after.startswith(sig):
                            score += 1
                            break

            if score > 0:
                name_score[name] = score

        # 只保留得分>=4的，用AI补全人物卡
        new_chars = []
        from backend.ai_client import chat as ai_chat

        for name, score in sorted(name_score.items(), key=lambda x: -x[1]):
            if score >= 4 and name not in existing_names:
                # 收集该角色在正文中的上下文
                name_contexts = []
                for m in re.finditer(re.escape(name), all_text):
                    start = m.start()
                    ctx = all_text[max(0, start-30):min(len(all_text), start+len(name)+30)]
                    name_contexts.append(ctx)
                context_text = "\n---\n".join(name_contexts[:5])

                # 用AI补全人物卡
                personality = ""
                background = ""
                long_term_goal = ""
                gender = "男"
                age = 20
                abilities = []

                try:
                    fill_prompt = f"""请根据以下小说正文中「{name}」出现的上下文，为这个角色补全人物卡。

角色名：{name}
信号强度：{score}

上下文片段：
{context_text}

请根据上下文推断这个角色的信息，输出格式（每行一个字段，用|分隔）：
{name}|性别|年龄(估)|性格(几个词)|能力/特长|背景(一句话)|长期目标(一句话)|短期目标(几个词用/分隔)
如果无法推断某项，留空即可。"""
                    fill_response = ai_chat(
                        system_prompt="你是小说角色分析师，根据正文上下文推断角色信息。",
                        user_prompt=fill_prompt,
                        temperature=0.3,
                        max_tokens=300,
                    )
                    if fill_response and fill_response.strip() and "|" in fill_response:
                        parts = [p.strip() for p in fill_response.strip().split("|")]
                        raw_gender = parts[1] if len(parts) > 1 else ""
                        gender = raw_gender if raw_gender in ("男", "女") else "男"
                        if len(parts) > 2:
                            try:
                                age_str = parts[2].replace("岁", "").replace("(估)", "").strip()
                                age = int(age_str) if age_str else 20
                            except:
                                pass
                        personality = parts[3] if len(parts) > 3 else ""
                        abilities = [a.strip() for a in parts[4].split("/")] if len(parts) > 4 and parts[4] else []
                        background = parts[5] if len(parts) > 5 else ""
                        long_term_goal = parts[6] if len(parts) > 6 and parts[6] else ""
                except Exception:
                    pass  # AI补全失败，用空值

                cfg = CharacterConfig(
                    name=name, gender=gender, age=age,
                    personality=personality, background=background,
                    abilities=abilities, weaknesses=[],
                    long_term_goal=long_term_goal, short_term_goals=[],
                    initial_location="",
                )
                agent = CharacterAgent(cfg)
                agent.remember("角色登场", f"扫描发现（信号强度:{score}）")
                # 设置NPC级别
                has_personality = bool(personality and len(personality) > 3)
                has_background = bool(background and len(background) > 5)
                has_goal = bool(long_term_goal and len(long_term_goal) > 3)
                info_score = sum([has_personality, has_background, has_goal])
                agent.npc_tier = "key_npc" if info_score >= 2 else "minor_npc"
                agent.appearance_count = score
                new_chars.append(agent)

        for agent in new_chars:
            engine._characters.append(agent)
            # 同步到 novel_world
            try:
                from novel_world.engine.core.character import Character as NWCharacter, CharType, CharState
                import random as _rng
                nw_char = NWCharacter(
                    name=agent.name,
                    char_type=CharType.KEY_NPC if agent.npc_tier == "key_npc" else CharType.NPC,
                    state=CharState.IDLE,
                    personality=[agent.config.personality] if agent.config.personality else [],
                    pos=(_rng.randint(0, engine._nw_world.map_size[0]-1),
                         _rng.randint(0, engine._nw_world.map_size[1]-1)),
                    goal=agent.config.background or "",
                )
                engine._nw_world.add_character(nw_char)
                engine._nw_characters.append(nw_char)
            except Exception:
                pass

        return jsonify({
            "status": "ok",
            "found": len(new_chars),
            "names": [c.name for c in new_chars],
            "total": len(engine._characters),
            "all_scores": {k: v for k, v in sorted(name_score.items(), key=lambda x: -x[1])[:20]},
            "details": [{"name": c.name, "npc_tier": getattr(c, "npc_tier", "minor_npc"),
                         "personality": c.config.personality[:30] if c.config.personality else ""} for c in new_chars]
        })

# ── 角色编辑 API ──

@app.route("/api/character/<name>", methods=["PUT"])
def api_edit_character(name):
    """编辑角色属性"""
    with _engine_lock:
        char = None
        for c in engine._characters:
            if c.name == name:
                char = c
                break
        if not char:
            return jsonify({"error": f"角色'{name}'不存在"}), 404

        data = request.get_json() or {}
        try:
            if "personality" in data:
                char.config.personality = data["personality"]
            if "background" in data:
                char.config.background = data["background"]
            if "abilities" in data:
                char.config.abilities = data["abilities"]
            if "weaknesses" in data:
                char.config.weaknesses = data["weaknesses"]
            if "long_term_goal" in data:
                char.long_term_goal.description = data["long_term_goal"]
            if "current_mood" in data:
                char.current_mood = data["current_mood"]
            if "current_location" in data:
                char.current_location = data["current_location"]
            if "gender" in data:
                char.config.gender = data["gender"]
            if "age" in data:
                char.config.age = int(data["age"])
            return jsonify({"status": "ok", "message": f"角色 {name} 已更新"})
        except Exception as e:
            return jsonify({"error": str(e)}), 500


@app.route("/api/character/<name>", methods=["GET"])
def api_get_character(name):
    """获取单个角色详细信息"""
    with _engine_lock:
        for c in engine._characters:
            if c.name == name:
                return jsonify({
                    "status": "ok",
                    "character": {
                        "name": c.name,
                        "gender": getattr(c.config, "gender", "") or "男",
                        "age": getattr(c.config, "age", 20) or 20,
                        "personality": getattr(c.config, "personality", ""),
                        "background": getattr(c.config, "background", ""),
                        "abilities": getattr(c.config, "abilities", []) or [],
                        "weaknesses": getattr(c.config, "weaknesses", []) or [],
                        "long_term_goal": c.long_term_goal.description if c.long_term_goal else "",
                        "short_term_goals": [g.description for g in c.short_term_goals],
                        "current_mood": c.current_mood,
                        "current_location": c.current_location or "",
                        "npc_tier": getattr(c, "npc_tier", "main"),
                        "appearance_count": getattr(c, "appearance_count", 0),
                    }
                })
        return jsonify({"error": f"角色'{name}'不存在"}), 404


