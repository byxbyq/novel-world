"""大纲系统 API：获取、生成、保存大纲（基于 OutlineManager）"""

# ── 大纲系统 API ──


# ── 大纲格式归一化工具 ──
# AI 格式（前端大纲规划弹窗 / engine.outline_data / 章节生成依赖）：
#   {"name": 卷名, "theme": 主题, "chapters": [{"title", "summary"}]}
# OutlineManager 格式（outline_manager / DM 面板）：
#   {"index", "title", "start_chapter", "end_chapter",
#    "outline": {"summary", "theme", "key_events", "character_arcs"}, "chapters": [章节号...]}

def _is_ai_format_volume(vol):
    """判断单个卷是否为 AI 格式"""
    if not isinstance(vol, dict):
        return False
    chs = vol.get("chapters") or []
    if chs and isinstance(chs[0], dict):
        return True
    return "name" in vol and "outline" not in vol


def _om_volume_to_ai(vol):
    """OutlineManager 格式卷 → AI 格式卷（章节摘要已不可恢复时留空）"""
    out = vol.get("outline") or {}
    if isinstance(out, str):
        out = {"summary": out}
    key_events = out.get("key_events") or []
    start = int(vol.get("start_chapter", 0) or 0)
    end = int(vol.get("end_chapter", 0) or 0)
    n = len(key_events)
    if n == 0 and start > 0 and end >= start:
        n = end - start + 1
    chapters = [
        {"title": key_events[i] if i < len(key_events) else "", "summary": ""}
        for i in range(n)
    ]
    return {
        "name": vol.get("title") or vol.get("name") or "",
        "theme": out.get("theme") or out.get("summary") or "",
        "chapters": chapters,
    }


def _normalize_ai_volumes(volumes):
    """将任意格式的卷列表归一化为 AI 格式（兼容旧存档的 OutlineManager 格式）"""
    ai_vols = []
    for vol in (volumes or []):
        if not isinstance(vol, dict):
            continue
        ai_vols.append(vol if _is_ai_format_volume(vol) else _om_volume_to_ai(vol))
    return ai_vols


def _ai_to_om_volumes(volumes):
    """AI 格式卷列表 → OutlineManager 格式（自动分配章节区间）"""
    om_vols = []
    ch_offset = 0
    for vi, vol in enumerate(volumes or []):
        chs = vol.get("chapters") or []
        titles = []
        for ch in chs:
            titles.append(ch.get("title", "") if isinstance(ch, dict) else str(ch))
        ch_count = len(chs)
        start_ch = ch_offset + 1
        end_ch = ch_offset + ch_count
        ch_offset += ch_count
        theme = vol.get("theme", "") or ""
        om_vols.append({
            "index": vi,
            "title": vol.get("name") or vol.get("title") or f"第{vi + 1}卷",
            "start_chapter": start_ch,
            "end_chapter": end_ch,
            "outline": {
                "summary": theme,
                "theme": theme,
                "key_events": titles,
                "character_arcs": vol.get("character_arcs", []) or [],
            },
        })
    return om_vols


@app.route("/api/outline", methods=["GET"])
def api_get_outline():
    """获取当前项目大纲"""
    with _engine_lock:
        if not engine.world:
            return jsonify({"error": "游戏尚未初始化"}), 400
        outline = getattr(engine, 'outline_data', None)
        # 归一化为 AI 格式，避免旧存档的 OutlineManager 格式导致前端面板显示为空
        if outline and outline.get("volumes"):
            outline = {"volumes": _normalize_ai_volumes(outline["volumes"])}
        # outline_manager 不随存档恢复，重启后从 engine.outline_data 重建
        if not outline_manager.get_volumes() and outline and outline.get("volumes"):
            outline_manager.set_volumes(_ai_to_om_volumes(outline["volumes"]))
        return jsonify({
            "status": "ok",
            "volumes": outline_manager.get_volumes(),
            "outline": outline,
            "chapter_count": len(engine.chapters),
            "total_chapters": engine.config.total_chapters,
        })


@app.route("/api/outline/generate", methods=["POST"])
def api_generate_outline():
    """AI 生成大纲（大批量时自动分批生成）"""
    api_key = os.getenv("OPENAI_API_KEY", "")
    if not api_key or api_key == "your_api_key_here":
        return jsonify({"error": "API Key 无效"}), 401

    with _engine_lock:
        data = request.get_json() or {}
        if not engine.world:
            return jsonify({"error": "游戏尚未初始化"}), 400
        volume_count = int(data.get("volume_count", 3))
        chapters_per_volume = int(data.get("chapters_per_volume", 5))
        world_info = engine.world.config.to_prompt_text()
        char_info = "\n".join(
            f"{c.name}（{getattr(c.config, 'gender', '') or '男'}，{getattr(c.config, 'age', 20)}岁）目标：{c.long_term_goal.description}"
            for c in engine._characters
        )

    try:
        from backend.ai_client import chat
        import re as _re

        # ── 分批策略：超过5卷时分批生成，每批最多5卷 ──
        BATCH_SIZE = 5
        all_volumes_raw = []

        if volume_count <= BATCH_SIZE:
            # 小批量：一次性生成
            all_volumes_raw = _generate_outline_batch(
                chat, world_info, char_info,
                volume_count, chapters_per_volume,
                start_volume=1, prev_context=""
            )
        else:
            # 大批量：分批生成
            total_batches = (volume_count + BATCH_SIZE - 1) // BATCH_SIZE
            prev_context = ""
            for batch_idx in range(total_batches):
                start_vol = batch_idx * BATCH_SIZE + 1
                end_vol = min(start_vol + BATCH_SIZE - 1, volume_count)
                batch_count = end_vol - start_vol + 1

                is_last_batch = (batch_idx == total_batches - 1)
                batch_volumes = _generate_outline_batch(
                    chat, world_info, char_info,
                    batch_count, chapters_per_volume,
                    start_volume=start_vol,
                    prev_context=prev_context,
                    is_final_batch=is_last_batch,
                    total_volumes=volume_count,
                )
                all_volumes_raw.extend(batch_volumes)

                # 构建下一批的上下文
                prev_context = "已有大纲概要：\n"
                for vol in all_volumes_raw:
                    vol_name = vol.get("name", "")
                    vol_theme = vol.get("theme", "")
                    ch_titles = [ch.get("title", "") for ch in vol.get("chapters", [])]
                    prev_context += f"《{vol_name}》主题：{vol_theme}；章节：{', '.join(ch_titles)}\n"

        # 将 AI 生成的卷结构导入 OutlineManager
        volumes_list = []
        for vi, vol in enumerate(all_volumes_raw):
            start_ch = vi * chapters_per_volume + 1
            end_ch = (vi + 1) * chapters_per_volume
            chapter_titles = [ch.get("title", "") for ch in vol.get("chapters", [])]
            volumes_list.append({
                "index": vi,
                "title": vol.get("name", f"第{vi+1}卷"),
                "start_chapter": start_ch,
                "end_chapter": end_ch,
                "outline": {
                    "summary": vol.get("theme", ""),
                    "theme": vol.get("theme", ""),
                    "key_events": chapter_titles,
                    "character_arcs": [],
                },
            })

        outline_data = {"volumes": all_volumes_raw}

        with _engine_lock:
            outline_manager.set_volumes(volumes_list)
            engine.outline_data = outline_data
        return jsonify({
            "status": "ok",
            "volumes": outline_manager.get_volumes(),
            "outline": outline_data,
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": f"生成大纲失败：{str(e)}"}), 500


def _generate_outline_batch(chat_fn, world_info, char_info,
                            volume_count, chapters_per_volume,
                            start_volume=1, prev_context="",
                            is_final_batch=False, total_volumes=None):
    """生成一批大纲卷（最多5卷）

    Args:
        chat_fn: AI chat 函数
        world_info: 世界设定文本
        char_info: 角色信息文本
        volume_count: 本批要生成的卷数
        chapters_per_volume: 每卷章节数
        start_volume: 本批起始卷号（用于提示AI位置）
        prev_context: 前批次已生成的大纲摘要（用于衔接）
        is_final_batch: 是否为最后一批（需要收束主线）
        total_volumes: 总卷数（用于上下文）
    Returns:
        list[dict]: 卷数据列表
    """
    import re as _re
    import json

    batch_hint = ""
    if total_volumes:
        batch_hint = f"（这是第{start_volume}~{start_volume + volume_count - 1}卷，共{total_volumes}卷）"

    ending_req = ""
    if is_final_batch:
        ending_req = "\n5. 这是最后一批，必须收束主线，给出结局"
    if prev_context:
        prev_context = f"\n\n已有前文大纲（请衔接，不要重复）：\n{prev_context}"

    prompt = f"""基于以下世界设定和角色，规划{volume_count}卷、每卷{chapters_per_volume}章的小说大纲{batch_hint}。

世界设定：
{world_info}

角色：
{char_info}{prev_context}

请按以下格式输出（严格JSON）：
{{"volumes": [
  {{"name": "卷名", "theme": "本卷主题（一句话）", "chapters": [
    {{"title": "章节标题", "summary": "一句话概括内容"}}
  ]}}
]}}

要求：
1. 每卷有明确的核心冲突和推进方向
2. 章节之间有因果联系，不要孤立事件
3. 每卷必须有{chapters_per_volume}个章节
4. 只输出JSON，不要其他内容{ending_req}"""

    response = chat_fn(
        system_prompt="你是小说大纲规划师，擅长构建有节奏感的故事结构。只输出JSON。",
        user_prompt=prompt,
        temperature=0.7,
        max_tokens=4096,
    )

    if not response or not response.strip():
        raise RuntimeError("AI 未返回任何内容")

    # 提取 JSON
    json_match = _re.search(r'\{[\s\S]*\}', response)
    if not json_match:
        raise RuntimeError(f"AI 返回格式异常，无法提取JSON。响应前200字：{response[:200]}")

    json_str = json_match.group()
    try:
        outline_data = json.loads(json_str)
    except json.JSONDecodeError as e:
        # 尝试修复常见的JSON格式问题
        try:
            # 尝试补全缺失的括号
            fixed = json_str
            open_braces = fixed.count('{') - fixed.count('}')
            open_brackets = fixed.count('[') - fixed.count(']')
            if open_braces > 0:
                fixed += '}' * open_braces
            if open_brackets > 0:
                fixed += ']' * open_brackets
            outline_data = json.loads(fixed)
        except:
            raise RuntimeError(f"JSON解析失败：{str(e)}。响应前300字：{response[:300]}")

    volumes_raw = outline_data.get("volumes", [])
    if not volumes_raw:
        raise RuntimeError(f"AI返回的大纲中没有卷数据。响应前200字：{response[:200]}")

    return volumes_raw


@app.route("/api/outline/continue", methods=["POST"])
def api_continue_outline():
    """AI 续写大纲：在现有大纲基础上追加新卷，扩容 total_chapters，重置终局锁。

    请求参数：
      - volume_count: 新增卷数（默认 1）
      - chapters_per_volume: 每卷章节数（默认 5）
    """
    api_key = os.getenv("OPENAI_API_KEY", "")
    if not api_key or api_key == "your_api_key_here":
        return jsonify({"error": "API Key 无效"}), 401

    with _engine_lock:
        if not engine.world:
            return jsonify({"error": "游戏尚未初始化"}), 400
        data = request.get_json() or {}
        volume_count = int(data.get("volume_count", 1))
        chapters_per_volume = int(data.get("chapters_per_volume", 5))

        # 收集当前故事上下文
        world_info = engine.world.config.to_prompt_text()
        char_info = "\n".join(
            f"{c.name}（{getattr(c.config, 'gender', '') or '男'}，{getattr(c.config, 'age', 20)}岁）目标：{c.long_term_goal.description}"
            for c in engine._characters
        )

        # 已有大纲概要
        existing_outline = getattr(engine, 'outline_data', None) or {}
        existing_volumes = existing_outline.get("volumes", [])
        existing_summary = ""
        for vol in existing_volumes:
            vol_name = vol.get("name", "")
            vol_theme = vol.get("theme", "")
            ch_titles = [ch.get("title", "") for ch in vol.get("chapters", [])]
            existing_summary += f"《{vol_name}》主题：{vol_theme}；章节：{', '.join(ch_titles)}\n"

        # 已生成章节的内容摘要（取最近 3 章）
        recent_chapters = ""
        for ch in engine.chapters[-3:]:
            ch_title = ch.get("title", "")
            ch_narrative = ch.get("narrative", "")
            # 每章取前 200 字作为摘要
            preview = ch_narrative[:200].replace("\n", " ") if ch_narrative else ""
            recent_chapters += f"第{ch.get('chapter', '?')}章《{ch_title}》：{preview}...\n"

        current_total = engine.config.total_chapters
        current_chapter_count = len(engine.chapters)
        finalized = getattr(engine, '_novel_finalized', False)

    try:
        from backend.ai_client import chat

        prompt = f"""你正在为一部已有 {current_chapter_count} 章的小说续写大纲。

世界设定：
{world_info}

角色：
{char_info}

已有大纲：
{existing_summary or "（无）"}

最近章节内容摘要：
{recent_chapters or "（无）"}

当前状态：已写 {current_chapter_count} 章，原计划 {current_total} 章，{"已触发终局" if finalized else "尚未终局"}。

请基于以上信息，续写 {volume_count} 卷、每卷 {chapters_per_volume} 章的新大纲。
要求：
1. 必须承接已有剧情，不要重复已有内容
2. 推进角色目标和主线矛盾
3. 如果是最终续写卷，可以收束主线
4. 章节之间有因果联系

请按以下格式输出（严格JSON）：
{{"volumes": [
  {{"name": "卷名", "theme": "本卷主题（一句话）", "chapters": [
    {{"title": "章节标题", "summary": "一句话概括内容"}},
    ...{chapters_per_volume}个章节
  ]}},
  ...{volume_count}卷
]}}

只输出JSON，不要其他内容。"""

        response = chat(
            system_prompt="你是小说大纲规划师，擅长构建有节奏感的故事结构，尤其擅长续写和扩展已有故事。",
            user_prompt=prompt,
            temperature=0.7,
            max_tokens=4096,
        )

        # 提取 JSON
        import re as _re
        json_match = _re.search(r'\{[\s\S]*\}', response)
        if not json_match:
            return jsonify({"error": "AI 返回格式异常"}), 500

        new_outline_data = json.loads(json_match.group())
        new_volumes_raw = new_outline_data.get("volumes", [])

        # 计算新卷的起始章节号
        new_chapter_start = current_total + 1

        # 构建 OutlineManager 格式的卷数据
        new_volumes_list = []
        for vi, vol in enumerate(new_volumes_raw):
            start_ch = new_chapter_start + vi * chapters_per_volume
            end_ch = start_ch + chapters_per_volume - 1
            chapter_titles = [ch.get("title", "") for ch in vol.get("chapters", [])]
            new_volumes_list.append({
                "index": len(existing_volumes) + vi,
                "title": vol.get("name", f"续卷{vi+1}"),
                "start_chapter": start_ch,
                "end_chapter": end_ch,
                "outline": {
                    "summary": vol.get("theme", ""),
                    "theme": vol.get("theme", ""),
                    "key_events": chapter_titles,
                    "character_arcs": [],
                },
            })

        with _engine_lock:
            # 1. 追加到 outline_manager（保留已有卷）
            existing_om_volumes = outline_manager.get_volumes()
            merged_volumes = existing_om_volumes + new_volumes_list
            outline_manager.set_volumes(merged_volumes)

            # 2. 追加到 engine.outline_data（保留已有卷）
            merged_outline_volumes = existing_volumes + new_volumes_raw
            engine.outline_data = {"volumes": merged_outline_volumes}

            # 3. 扩容 total_chapters
            added_chapters = volume_count * chapters_per_volume
            engine.config.total_chapters = current_total + added_chapters

            # 4. 重置终局锁，允许继续生成
            engine._novel_finalized = False

        return jsonify({
            "status": "ok",
            "message": f"已续写 {volume_count} 卷（{added_chapters} 章），total_chapters: {current_total} → {engine.config.total_chapters}",
            "volumes": outline_manager.get_volumes(),
            "outline": engine.outline_data,
            "total_chapters": engine.config.total_chapters,
            "novel_finalized": False,
        })

    except Exception as e:
        return jsonify({"error": f"续写大纲失败：{str(e)}"}), 500


@app.route("/api/outline/summaries/regenerate", methods=["POST"])
def api_regenerate_chapter_summaries():
    """重建丢失的章节摘要：基于已有卷名/主题/章节标题，AI 逐卷补写 chapters[].summary

    只填充摘要为空的章节，已有摘要的保留。分批处理（每批最多5卷）避免超token。
    """
    api_key = os.getenv("OPENAI_API_KEY", "")
    if not api_key or api_key == "your_api_key_here":
        return jsonify({"error": "API Key 无效"}), 401

    with _engine_lock:
        if not engine.world:
            return jsonify({"error": "游戏尚未初始化"}), 400
        outline = getattr(engine, 'outline_data', None)
        if not outline or not outline.get("volumes"):
            return jsonify({"error": "当前没有大纲数据"}), 400
        volumes = _normalize_ai_volumes(outline["volumes"])

    # 统计需要补写的卷
    pending_idx = [
        vi for vi, vol in enumerate(volumes)
        if any(not (ch.get("summary") or "").strip() for ch in (vol.get("chapters") or []))
    ]
    if not pending_idx:
        return jsonify({"status": "ok", "message": "所有章节摘要已完整，无需重建", "filled": 0})

    try:
        from backend.ai_client import chat
        import re as _re

        BATCH_SIZE = 5
        filled = 0
        for b in range(0, len(pending_idx), BATCH_SIZE):
            batch_idx = pending_idx[b:b + BATCH_SIZE]
            batch_vols = [volumes[vi] for vi in batch_idx]

            vols_desc = ""
            for vol in batch_vols:
                chs = vol.get("chapters") or []
                ch_lines = "\n".join(
                    f"  {ci + 1}. 《{ch.get('title', '')}》"
                    + (f" 摘要：{ch.get('summary', '')}" if (ch.get("summary") or "").strip() else " 摘要：（待补写）")
                    for ci, ch in enumerate(chs)
                )
                vols_desc += f"卷《{vol.get('name', '')}》主题：{vol.get('theme', '')}\n{ch_lines}\n\n"

            prompt = f"""以下是一部小说的大纲卷结构，部分章节的摘要丢失了（标记为“待补写”）。
请根据卷名、主题、章节标题和前后的已有摘要，为“待补写”的章节各补写一句话摘要（一句话概括本章内容，30字以内），保持与已有摘要风格、剧情走向一致。

{vols_desc}
请按以下格式输出（严格JSON）：
{{"chapters": [{{"title": "章节标题", "summary": "补写的摘要"}}]}}
只输出需要补写的章节，只输出JSON。"""

            response = chat(
                system_prompt="你是小说大纲规划师。只输出JSON。",
                user_prompt=prompt,
                temperature=0.7,
                max_tokens=4096,
            )
            if not response or not response.strip():
                continue

            json_match = _re.search(r'\{[\s\S]*\}', response)
            if not json_match:
                continue
            try:
                result = json.loads(json_match.group())
            except json.JSONDecodeError:
                continue

            # 按标题匹配回填到对应卷
            new_summaries = {
                (item.get("title") or "").strip(): (item.get("summary") or "").strip()
                for item in result.get("chapters", []) if isinstance(item, dict)
            }
            for vol in batch_vols:
                for ch in (vol.get("chapters") or []):
                    if (ch.get("summary") or "").strip():
                        continue
                    s = new_summaries.get((ch.get("title") or "").strip())
                    if s:
                        ch["summary"] = s
                        filled += 1

        with _engine_lock:
            engine.outline_data = {"volumes": volumes}
            outline_manager.set_volumes(_ai_to_om_volumes(volumes))

        return jsonify({
            "status": "ok",
            "message": f"已重建 {filled} 条章节摘要",
            "filled": filled,
            "outline": engine.outline_data,
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": f"重建章节摘要失败：{str(e)}"}), 500


@app.route("/api/outline", methods=["PUT"])
def api_update_outline():
    """手动更新大纲（前端以 AI 格式提交：name/theme/chapters[{title,summary}]）

    engine.outline_data 保存完整 AI 格式（章节生成与标题回填依赖 chapters[].summary），
    同时转换为 OutlineManager 格式同步到 outline_manager。
    """
    with _engine_lock:
        data = request.get_json() or {}
        volumes_data = data.get("volumes", [])
        if volumes_data:
            # 统一归一化为 AI 格式（兼容旧版 OutlineManager 格式输入）
            ai_volumes = _normalize_ai_volumes(volumes_data)
            engine.outline_data = {"volumes": ai_volumes}
            outline_manager.set_volumes(_ai_to_om_volumes(ai_volumes))
        return jsonify({
            "status": "ok",
            "volumes": outline_manager.get_volumes(),
            "outline": getattr(engine, 'outline_data', None),
        })


@app.route("/api/outline/volume", methods=["POST"])
def api_add_volume():
    """添加卷"""
    with _engine_lock:
        data = request.get_json() or {}
        title = data.get("title", "")
        if not title:
            return jsonify({"error": "请提供卷标题"}), 400
        idx = outline_manager.add_volume(
            title=title,
            start_chapter=data.get("start_chapter", 0),
            end_chapter=data.get("end_chapter", 0),
        )
        return jsonify({"status": "ok", "volume_index": idx})


@app.route("/api/outline/save", methods=["POST"])
def api_save_outline():
    """保存手动编辑的大纲 Markdown"""
    data = request.get_json() or {}
    raw_md = data.get("outline_markdown", "")
    save_dir = os.path.join(os.path.dirname(FRONTEND_DIR), "saves")
    os.makedirs(save_dir, exist_ok=True)
    save_path = os.path.join(save_dir, "outline_edited.md")
    with open(save_path, "w", encoding="utf-8") as f:
        f.write(raw_md)
    return jsonify({"status": "ok", "saved_to": save_path})


@app.route("/api/outline/volume/<int:vol_index>", methods=["DELETE"])
def api_delete_volume(vol_index):
    """删除卷"""
    with _engine_lock:
        ok = outline_manager.delete_volume(vol_index)
        if not ok:
            return jsonify({"error": "删除失败"}), 400
        return jsonify({"status": "ok"})


@app.route("/api/outline/volume/<int:vol_index>/generate", methods=["POST"])
def api_generate_volume_outline(vol_index):
    """AI 生成指定卷的纲要（summary / key_events / character_arcs）"""
    with _engine_lock:
        if not engine.world:
            return jsonify({"error": "游戏尚未初始化"}), 400
        volumes = outline_manager.get_volumes()
        if vol_index < 0 or vol_index >= len(volumes):
            return jsonify({"error": "卷索引无效"}), 400
        vol = volumes[vol_index]

    data = request.get_json() or {}
    inspiration = data.get("inspiration", "")

    # 收集上下文
    ctx_parts = []
    if inspiration:
        ctx_parts.append("【灵感碎片】\n" + inspiration[:2000])

    # 世界观设定
    world_text = engine.world.config.to_prompt_text()
    if world_text:
        ctx_parts.append("【世界观设定】\n" + world_text[:1500])

    # 人物设定
    chars = getattr(engine, '_characters', []) or []
    if chars:
        char_lines = []
        for c in chars[:10]:
            name = c.name
            identity = getattr(c.config, 'identity', '') or ''
            goal = c.long_term_goal.description if hasattr(c, 'long_term_goal') and c.long_term_goal else ''
            desc = f"- {name}"
            if identity: desc += f"（{identity}）"
            if goal: desc += f" 目标：{goal}"
            char_lines.append(desc)
        if char_lines:
            ctx_parts.append("【人物设定】\n" + "\n".join(char_lines[:1500]))

    # 前一卷纲要
    if vol_index > 0:
        prev = outline_manager.get_volume_outline(vol_index - 1)
        if prev.get("summary"):
            ctx_parts.append("【前一卷概要】" + prev.get("summary", "")[:500])

    # 本卷章节列表
    ch_list = []
    for ci in (vol.get("chapters") or []):
        ci = int(ci)
        if 0 < ci <= len(getattr(engine, 'chapters', []) or []):
            ch_list.append(f"第{ci}章: {engine.chapters[ci-1].get('title', '')}")
    ctx_parts.append(f"【本卷信息】\n卷标题: {vol.get('title', '')}\n包含章节: {'、'.join(ch_list) if ch_list else '待定'}")

    context = "\n\n".join(ctx_parts)

    prompt = context + """\n\n你是一位资深小说编辑。请根据以上信息，为本卷生成纲要。严格按照以下JSON格式输出：

{
  "theme": "本卷核心主题（一句话，12字以内）",
  "summary": "本卷故事概要（100-200字，包含起承转合）",
  "key_events": ["关键事件1", "关键事件2", "关键事件3"],
  "character_arcs": ["角色弧线1", "角色弧线2"]
}

只输出JSON，不要其他内容。"""

    try:
        from backend.ai_client import chat
        response = chat(
            system_prompt="你是小说大纲规划师，擅长构建有节奏感的故事结构。",
            user_prompt=prompt,
            temperature=0.7,
            max_tokens=2048,
        )

        import re as _re
        json_match = _re.search(r'\{[\s\S]*\}', response)
        obj = {"theme": "", "summary": "", "key_events": [], "character_arcs": []}
        if json_match:
            obj = json.loads(json_match.group())

        with _engine_lock:
            outline_manager.set_volume_outline(vol_index, {
                "theme": obj.get("theme", ""),
                "summary": obj.get("summary", ""),
                "key_events": obj.get("key_events", []),
                "character_arcs": obj.get("character_arcs", []),
            })

        return jsonify({"status": "ok", "data": obj})
    except Exception as e:
        return jsonify({"error": f"生成卷纲要失败：{str(e)}"}), 500