"""批量操作 API：批量编辑角色/势力、批量导入"""

# ── 批量编辑 API（phase2_p2）──

@app.route("/api/characters/batch", methods=["POST"])
def api_characters_batch():
    """批量修改角色属性"""
    try:
        data = request.get_json() or {}
        character_ids = data.get("character_ids", [])
        updates = data.get("updates", {})
        if not character_ids or not updates:
            return jsonify({"error": "缺少 character_ids 或 updates 字段"}), 400

        world = get_world()
        count = 0
        for c in world.characters:
            if character_ids == "all" or c.id in character_ids:
                for key, val in updates.items():
                    if key == "personality":
                        if hasattr(c, 'personality'):
                            # 追加模式
                            existing = getattr(c, 'personality', [])
                            if isinstance(existing, list):
                                if isinstance(val, list):
                                    for v in val:
                                        if v not in existing:
                                            existing.append(v)
                                else:
                                    if val not in existing:
                                        existing.append(val)
                            c.personality = existing
                    elif key == "faction_id":
                        old_fid = getattr(c, 'faction_id', '')
                        if old_fid and old_fid in world.factions:
                            cid = getattr(c, 'id', '')
                            if cid in world.factions[old_fid].member_ids:
                                world.factions[old_fid].member_ids.remove(cid)
                        c.faction_id = val
                        if val in world.factions:
                            cid2 = getattr(c, 'id', '')
                            if cid2 not in world.factions[val].member_ids:
                                world.factions[val].member_ids.append(cid2)
                    elif key == "pos":
                        if isinstance(val, list) and len(val) == 2:
                            c.pos = (int(val[0]), int(val[1]))
                    else:
                        if hasattr(c, key):
                            setattr(c, key, val)
                count += 1

        return jsonify({"status": "ok", "modified_count": count})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/factions/batch", methods=["POST"])
def api_factions_batch():
    """批量修改势力关系"""
    try:
        data = request.get_json() or {}
        faction_ids = data.get("faction_ids", [])
        updates = data.get("updates", {})
        if not faction_ids or not updates:
            return jsonify({"error": "缺少 faction_ids 或 updates 字段"}), 400

        world = get_world()
        count = 0
        for fid in faction_ids:
            if fid in world.factions:
                f = world.factions[fid]
                for key, val in updates.items():
                    if key == "set_enemies":
                        for eid in val:
                            if eid in world.factions:
                                f.add_enemy(eid)
                    elif key == "set_allies":
                        for aid in val:
                            if aid in world.factions:
                                f.add_ally(aid)
                    elif key == "add_resources":
                        if hasattr(f, 'controlled_resources'):
                            for r in val:
                                if r not in f.controlled_resources:
                                    f.controlled_resources.append(r)
                    else:
                        if hasattr(f, key):
                            setattr(f, key, val)
                count += 1

        return jsonify({"status": "ok", "modified_count": count})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/characters/import", methods=["POST"])
def api_characters_import():
    """批量导入角色（JSON 格式）"""
    try:
        data = request.get_json() or {}
        characters_data = data.get("characters", [])
        if not characters_data:
            return jsonify({"error": "缺少 characters 数组"}), 400

        world = get_world()
        imported = 0
        for cd in characters_data:
            if not cd.get("name"):
                continue
            from novel_world.engine.core.character import Character, CharState, CharType
            c = Character(
                name=cd["name"],
                char_type=CharType.NPC,
                state=CharState.IDLE,
                personality=cd.get("personality", []),
                pos=tuple(cd.get("pos", (random.randint(0, world.map_size[0]-1) if hasattr(world, 'map_size') else 0, 0))),
                faction_id=cd.get("faction_id", ""),
                goal=cd.get("goal", ""),
                skills=cd.get("skills", []),
                description=cd.get("description", ""),
            )
            if 'attributes' in cd:
                for k, v in cd.get('attributes', {}).items():
                    if hasattr(c, k):
                        setattr(c, k, v)
            world.add_character(c)
            imported += 1

        return jsonify({"status": "ok", "imported": imported})
    except Exception as e:
        return jsonify({"error": str(e)}), 500



