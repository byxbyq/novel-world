# -*- coding: utf-8 -*-
"""聊天式剧情讨论 API：对话路由 + SSE 流式通道 + RollbackStack

角色：剧情讨论伙伴 + 创作助手。区分讨论与操作：
- 讨论：只做文字回应
- 操作：从对话中识别意图，调用现有 API 执行，结果反馈给用户
"""

import json
import time
import re as regex
import threading
import queue
from collections import deque
from flask import Response, stream_with_context


# ═══════════════════════════════════════════
# RollbackStack —— 操作回滚栈
# ═══════════════════════════════════════════

class RollbackStack:
    """操作回滚栈：每次有副作用操作前保存状态快照，栈深度上限 20"""

    def __init__(self, max_depth=20):
        self._stack = []
        self.max_depth = max_depth

    def push(self, snapshot: dict):
        self._stack.append(snapshot)
        if len(self._stack) > self.max_depth:
            self._stack.pop(0)

    def pop(self):
        if not self._stack:
            return None
        return self._stack.pop()

    def clear(self):
        self._stack.clear()

    def __len__(self):
        return len(self._stack)


_rollback_stack = RollbackStack()


# ═══════════════════════════════════════════
# 对话历史
# ═══════════════════════════════════════════

_chat_history = deque(maxlen=20)


def _add_to_history(role: str, content: str, action: dict = None):
    entry = {"role": role, "content": content, "timestamp": time.time()}
    if action:
        entry["action"] = action
    _chat_history.append(entry)


# ═══════════════════════════════════════════
# Function 定义（用于 prompt 和 schema）
# ═══════════════════════════════════════════

FUNCTION_SPECS = [
    {
        "name": "add_character",
        "desc": "添加新角色",
        "params": {
            "name": "角色名称(str, 必填)",
            "gender": "性别(男/女, 默认男)",
            "age": "年龄(int, 默认20)",
            "personality": "性格描述(str)",
            "background": "背景故事(str)",
            "appearance": "外貌描述(str)",
            "abilities": "能力列表(list[str])",
            "weaknesses": "弱点列表(list[str])",
            "long_term_goal": "长期目标(str)",
            "initial_location": "初始位置(str)",
        },
        "side_effect": True,
    },
    {
        "name": "edit_character",
        "desc": "修改已有角色属性",
        "params": {
            "name": "角色名称(str, 必填)",
            "personality": "性格(str)",
            "background": "背景(str)",
            "abilities": "能力(list[str])",
            "weaknesses": "弱点(list[str])",
            "long_term_goal": "长期目标(str)",
            "current_mood": "当前情绪(str)",
            "current_location": "当前位置(str)",
            "gender": "性别(男/女)",
            "age": "年龄(int)",
        },
        "side_effect": True,
    },
    {
        "name": "inject_event",
        "desc": "注入世界事件",
        "params": {
            "description": "事件描述(str, 必填)",
            "type": "事件类型(inject_event/modify_character/force_move/add_goal, 默认inject_event)",
        },
        "side_effect": True,
    },
    {
        "name": "divine_guidance",
        "desc": "给角色天意指引（梦境/天启/暗示）",
        "params": {
            "character_name": "目标角色名(str, 必填)",
            "message": "指引内容(str, 必填)",
            "form": "融入形式(dream/epiphany/omen/encounter/inner_voice/auto, 默认auto)",
            "strength": "指引强度(hint/direct/vague, 默认hint)",
        },
        "side_effect": True,
    },
    {
        "name": "edit_outline",
        "desc": "修改小说大纲",
        "params": {"volumes": "新卷结构(list, 必填)"},
        "side_effect": True,
    },
    {
        "name": "generate_chapter",
        "desc": "生成/推演下一章",
        "params": {"title": "章节标题(str), 不填用大纲标题或自动生成"},
        "side_effect": True,
    },
    # ── 只读查询 ──
    {
        "name": "get_outline",
        "desc": "查看当前大纲",
        "params": {},
        "side_effect": False,
    },
    {
        "name": "get_character",
        "desc": "查看角色详细信息",
        "params": {"name": "角色名称(str, 必填)"},
        "side_effect": False,
    },
    {
        "name": "get_world_settings",
        "desc": "查看世界设定",
        "params": {},
        "side_effect": False,
    },
    {
        "name": "edit_world_settings",
        "desc": "修改世界设定（名称/类型/时代/描述/规则/地点/局势/基调/主线目标/视角，影响后续章节）",
        "params": {
            "name": "世界名称(str)",
            "genre": "类型(str)",
            "era": "时代(str)",
            "description": "世界描述(str)",
            "rules": "世界规则(list[str])",
            "key_locations": "关键地点(list[str])",
            "current_situation": "当前局势(str)",
            "tone": "叙事基调(str)",
            "main_objective": "主线目标(str)",
            "perspective": "叙事视角(third/first)",
        },
        "side_effect": True,
    },
    {
        "name": "post_process",
        "desc": "对文本执行去AI腔后处理",
        "params": {"content": "待处理文本(str, 必填)"},
        "side_effect": False,
    },
    {
        "name": "humanity_audit",
        "desc": "对文本执行六维度人味审计",
        "params": {"content": "待审核文本(str, 必填)"},
        "side_effect": False,
    },
]

# 有副作用的函数名集合
SIDE_EFFECT_FUNCTIONS = {f["name"] for f in FUNCTION_SPECS if f.get("side_effect")}


def _format_functions_for_prompt() -> str:
    """将函数定义格式化为 prompt 中的文本说明"""
    lines = []
    for f in FUNCTION_SPECS:
        params = f.get("params", {})
        if params:
            params_desc = "、".join(
                f"{k}({v})" for k, v in params.items()
            )
        else:
            params_desc = "无参数"
        lines.append(f"- {f['name']}: {f['desc']}。参数：{params_desc}")
    return "\n".join(lines)


# ═══════════════════════════════════════════
# 项目状态获取
# ═══════════════════════════════════════════

def _get_project_state_summary() -> str:
    """获取当前项目状态摘要，注入 system prompt"""
    parts = []

    with _engine_lock:
        if engine.world:
            wc = engine.world.config
            parts.append(
                f"【世界设定】名称：{wc.name}，类型：{wc.genre}，时代：{wc.era}，"
                f"基调：{wc.tone}，目标：{wc.main_objective or '未设定'}"
            )
            parts.append(f"当前局势：{wc.current_situation or '未设定'}，阶段：{wc.world_stage or 'opening'}")

        if engine._characters:
            chars_parts = []
            for c in engine._characters:
                p = getattr(c.config, "personality", "") or ""
                chars_parts.append(
                    f"{c.name}({getattr(c.config, 'gender', '男')}, "
                    f"{getattr(c.config, 'age', 20)}岁): {p[:30]}"
                )
            parts.append(f"【角色列表】{'；'.join(chars_parts)}")

        if engine.outline_data:
            vols = engine.outline_data.get("volumes", [])
            vol_summaries = []
            for vi, v in enumerate(vols):
                vol_summaries.append(
                    f"第{vi+1}卷《{v.get('name', '')}》(主题：{v.get('theme', '')})"
                )
            parts.append(f"【大纲】共{len(vols)}卷：{'；'.join(vol_summaries)}")

        total = engine.config.total_chapters if engine.world else 0
        current = len(engine.chapters)
        parts.append(f"【进度】已完成{current}/{total}章")

    return "\n".join(parts) if parts else "项目尚未初始化"


def _get_full_state() -> str:
    """获取更详细的项目状态（用于操作后刷新上下文）"""
    parts = [_get_project_state_summary()]

    with _engine_lock:
        if engine.outline_data:
            vols = engine.outline_data.get("volumes", [])
            for vi, v in enumerate(vols):
                chs = v.get("chapters", [])
                ch_titles = [ch.get("title", "") for ch in chs]
                parts.append(
                    f"第{vi+1}卷章节：{' → '.join(ch_titles[:10])}"
                )

    return "\n".join(parts)


# ═══════════════════════════════════════════
# 构建 System Prompt
# ═══════════════════════════════════════════

CHAT_SYSTEM_PROMPT = """你是一个小说创作助手，在项目中与作者对话。你的职责：
1. 自然讨论剧情走向、角色发展、世界设定
2. 分析角色动机，给出建设性建议
3. 当作者发出明确操作指令时，识别意图并输出函数调用

## 操作意图 vs 讨论意图
- 操作意图（需要调用函数）："加一个叫X的角色""创建角色X""修改X的性格""删除X""注入事件""生成下一章""看看角色X的状态""查看大纲""检查人味""去AI腔""修改世界设定""把主线目标改成..."等明确祈使句
- 讨论意图（只做文字回应）："我觉得""你认为""如果...会怎样""讨论一下""分析一下""这个角色为什么..."等探讨性质的话
- 模糊意图不调用函数，先和作者讨论确认

## 函数调用格式
当识别到操作意图时，在回复末尾（必须是末尾）追加以下格式的函数调用：
```function
{"name": "<函数名>", "params": {<参数>}}
```

## 有副作用的操作
调用以下函数前，如果对用户意图置信度不高（<0.8），先和用户确认再调用：
{side_effect_list}

## 当前项目状态
{project_state}
"""


def _build_messages(user_message: str, history: list) -> list:
    """构建发送给 LLM 的完整 messages 数组"""
    state = _get_project_state_summary()
    side_list = "、".join(sorted(SIDE_EFFECT_FUNCTIONS))
    func_desc = _format_functions_for_prompt()

    # 用 replace 而非 format，避免项目数据中的花括号被误解析
    system_content = (
        CHAT_SYSTEM_PROMPT
        .replace("{side_effect_list}", side_list)
        .replace("{project_state}", state)
    )
    system_content += f"\n\n## 可调用函数\n{func_desc}"

    messages = [{"role": "system", "content": system_content}]

    # 注入最近对话历史
    for h in history[-20:]:
        messages.append({"role": h["role"], "content": h["content"]})

    messages.append({"role": "user", "content": user_message})
    return messages


# ═══════════════════════════════════════════
# 函数执行调度
# ═══════════════════════════════════════════

def _call_internal_api(func_name: str, params: dict) -> dict:
    """通过 Flask test client 调用内部 API，返回 JSON 结果"""
    with _engine_lock:
        with app.test_client() as client:
            try:
                if func_name == "add_character":
                    resp = client.post("/api/add-character", json=params)
                elif func_name == "edit_character":
                    name = params.pop("name", "")
                    resp = client.put(f"/api/character/{name}", json=params)
                elif func_name == "inject_event":
                    body = {
                        "type": params.get("type", "inject_event"),
                        "description": params.get("description", ""),
                        "cmd": params.get("description", ""),
                    }
                    resp = client.post("/api/dm/inject", json=body)
                elif func_name == "divine_guidance":
                    resp = client.post("/api/dm/guidance", json=params)
                elif func_name == "edit_outline":
                    resp = client.put("/api/outline", json=params)
                elif func_name == "get_outline":
                    resp = client.get("/api/outline")
                elif func_name == "get_character":
                    name = params.get("name", "")
                    resp = client.get(f"/api/character/{name}")
                elif func_name == "get_world_settings":
                    resp = client.get("/api/world-config")
                elif func_name == "edit_world_settings":
                    resp = client.put("/api/world-config", json=params)
                elif func_name == "post_process":
                    resp = client.post("/api/post-process/run", json=params)
                elif func_name == "humanity_audit":
                    resp = client.post("/api/humanity/audit", json=params)
                elif func_name == "generate_chapter":
                    resp = client.post("/api/chapter", json=params)
                else:
                    return {"error": f"未知函数: {func_name}"}

                return resp.get_json() if resp else {"error": "无响应"}
            except Exception as e:
                return {"error": str(e)}


def _parse_function_call(text: str) -> dict | None:
    """从 AI 回复中提取函数调用 JSON"""
    match = regex.search(
        r'```function\s*\n(\{[\s\S]*?\})\s*\n```', text
    )
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass
    return None


# ═══════════════════════════════════════════
# 快照与回滚
# ═══════════════════════════════════════════

def _save_snapshot():
    """保存当前项目状态快照到回滚栈"""
    with _engine_lock:
        snapshot = {
            "characters": [],
            "chapters_count": len(engine.chapters),
        }
        # 世界设定快照（供 edit_world_settings 撤销）
        if engine.world:
            wc = engine.world.config
            snapshot["world_config"] = {
                "name": wc.name,
                "genre": wc.genre,
                "era": wc.era,
                "description": wc.description,
                "rules": list(wc.rules or []),
                "key_locations": list(wc.key_locations or []),
                "current_situation": wc.current_situation,
                "tone": wc.tone,
                "main_objective": wc.main_objective,
                "perspective": getattr(wc, "perspective", "third"),
            }
        for c in engine._characters:
            snapshot["characters"].append({
                "name": c.name,
                "gender": getattr(c.config, "gender", "男"),
                "age": getattr(c.config, "age", 20),
                "personality": getattr(c.config, "personality", ""),
                "background": getattr(c.config, "background", ""),
                "abilities": list(getattr(c.config, "abilities", []) or []),
                "weaknesses": list(getattr(c.config, "weaknesses", []) or []),
                "long_term_goal": (
                    c.long_term_goal.description if c.long_term_goal else ""
                ),
                "current_mood": c.current_mood,
                "current_location": c.current_location or "",
            })

        if engine.outline_data:
            snapshot["outline_data"] = json.loads(
                json.dumps(engine.outline_data, default=str)
            )

        _rollback_stack.push(snapshot)


def _restore_snapshot(snapshot: dict) -> str:
    """从快照恢复项目状态"""
    from backend.config import CharacterConfig
    from backend.character import CharacterAgent

    with _engine_lock:
        # 恢复世界设定
        if snapshot.get("world_config") and engine.world:
            wc = engine.world.config
            swc = snapshot["world_config"]
            old_main_obj = wc.main_objective
            wc.name = swc.get("name", wc.name)
            wc.genre = swc.get("genre", wc.genre)
            wc.era = swc.get("era", wc.era)
            wc.description = swc.get("description", wc.description)
            wc.rules = swc.get("rules", wc.rules)
            wc.key_locations = swc.get("key_locations", wc.key_locations)
            wc.current_situation = swc.get("current_situation", wc.current_situation)
            wc.tone = swc.get("tone", wc.tone)
            wc.main_objective = swc.get("main_objective", wc.main_objective)
            wc.perspective = swc.get("perspective", getattr(wc, "perspective", "third"))
            # 主线目标被回滚变化时重新校准目标权重
            if wc.main_objective != old_main_obj and wc.main_objective:
                try:
                    engine.align_goals_to_main_objective()
                except Exception:
                    pass

        # 恢复角色
        current_names = {c.name for c in engine._characters}
        snapshot_names = {c["name"] for c in snapshot.get("characters", [])}

        # 移除快照中不存在的角色
        for name in current_names - snapshot_names:
            engine._characters = [c for c in engine._characters if c.name != name]

        # 恢复/添加快照中的角色
        for sc in snapshot.get("characters", []):
            existing = None
            for c in engine._characters:
                if c.name == sc["name"]:
                    existing = c
                    break
            if existing:
                existing.config.personality = sc.get("personality", "")
                existing.config.background = sc.get("background", "")
                existing.config.abilities = sc.get("abilities", [])
                existing.config.weaknesses = sc.get("weaknesses", [])
                existing.config.gender = sc.get("gender", "男")
                existing.config.age = sc.get("age", 20)
                if sc.get("long_term_goal") and existing.long_term_goal:
                    existing.long_term_goal.description = sc["long_term_goal"]
                existing.current_mood = sc.get("current_mood", "平静")
                existing.current_location = sc.get("current_location", "")
            else:
                cfg = CharacterConfig(
                    name=sc["name"],
                    gender=sc.get("gender", "男"),
                    age=sc.get("age", 20),
                    personality=sc.get("personality", ""),
                    background=sc.get("background", ""),
                    abilities=sc.get("abilities", []),
                    weaknesses=sc.get("weaknesses", []),
                    long_term_goal=sc.get("long_term_goal", ""),
                )
                agent = CharacterAgent(cfg)
                engine._characters.append(agent)

        # 恢复大纲
        if "outline_data" in snapshot:
            engine.outline_data = snapshot["outline_data"]

        return f"已回滚：恢复{len(snapshot.get('characters', []))}个角色状态"


# ═══════════════════════════════════════════
# API 路由
# ═══════════════════════════════════════════

@app.route("/api/chat", methods=["POST"])
def api_chat():
    """非流式对话 —— 用于调试和简单问答

    请求：{"message": "用户消息", "history": [{"role": "user/assistant", "content": "..."}]}
    响应：{"reply": "AI回复", "action": null | {"type": "xxx", "params": {...}, "result": {...}}}
    """
    data = request.get_json() or {}
    message = (data.get("message") or "").strip()
    history = data.get("history", [])

    if not message:
        return jsonify({"reply": "", "error": "请提供消息内容"}), 400

    # 如果没有传 history，使用内存中的对话历史
    if not history:
        history = list(_chat_history)

    messages = _build_messages(message, history)

    # 非流式生成
    reply = model_router.chat_with_messages(
        messages, task="chat", temperature=0.7, max_tokens=2048
    )

    action = None

    # 检查是否有函数调用
    fc = _parse_function_call(reply)
    if fc:
        func_name = fc.get("name", "")
        params = fc.get("params", {})

        # 截取函数调用前的文本作为自然语言回复
        text_before = reply.split("```function")[0].strip()

        # 有副作用的操作前保存快照
        if func_name in SIDE_EFFECT_FUNCTIONS:
            _save_snapshot()

        result = _call_internal_api(func_name, params)
        action = {"type": func_name, "params": params, "result": result}

        # 用操作结果生成后续回复
        new_state = _get_full_state()
        result_context = (
            f"刚才执行了操作 {func_name}，参数：{json.dumps(params, ensure_ascii=False)}\n"
            f"操作结果：{json.dumps(result, ensure_ascii=False)}\n"
            f"更新后的项目状态：\n{new_state}"
        )

        followup_messages = [
            {"role": "system", "content": f"""你是小说创作助手。{result_context}

请用自然的语言告诉作者操作结果（不用太长，简洁明了）。如果操作成功，简要说明变化；如果失败，如实告知错误。"""},
            {"role": "user", "content": "请告知操作结果"},
        ]

        followup = model_router.chat_with_messages(
            followup_messages, task="chat", temperature=0.5, max_tokens=512
        )

        reply = f"{text_before}\n\n{followup}" if text_before else followup

    # 更新历史
    _add_to_history("user", message)
    _add_to_history("assistant", reply, action)

    return jsonify({"reply": reply, "action": action})


@app.route("/api/chat/stream", methods=["GET"])
def api_chat_stream():
    """SSE 流式对话 —— 用于前端实时显示

    查询参数：?message=用户消息
    SSE 事件：
      event: token  → data: "逐字"
      event: action → data: {"type": "xxx", "params": {...}, "result": {...}}
      event: done   → data: "完成"
    """
    message = (request.args.get("message") or "").strip()

    if not message:
        def _err():
            yield f"data: {json.dumps({'type': 'error', 'message': '请提供消息内容'}, ensure_ascii=False)}\n\n"
        return Response(stream_with_context(_err()), mimetype="text/event-stream")

    def generate():
        history = list(_chat_history)
        messages = _build_messages(message, history)

        # ── 线程 + 队列流式生成 ──
        token_queue = queue.Queue()
        stream_done = threading.Event()

        def stream_worker():
            try:
                def on_tok(t):
                    token_queue.put(("token", t))
                result = model_router.chat_with_messages(
                    messages, on_chunk=on_tok, task="chat",
                    temperature=0.7, max_tokens=2048,
                )
                token_queue.put(("done", result))
            except Exception as e:
                token_queue.put(("error", str(e)))
            finally:
                stream_done.set()

        t = threading.Thread(target=stream_worker, daemon=True)
        t.start()

        full_reply = ""
        action = None

        # 收集 token
        while not stream_done.is_set() or not token_queue.empty():
            try:
                msg_type, content = token_queue.get(timeout=0.05)
                if msg_type == "token":
                    full_reply += content
                    yield f"data: {json.dumps({'type': 'token', 'content': content}, ensure_ascii=False)}\n\n"
                elif msg_type == "done":
                    full_reply = content
                    break
                elif msg_type == "error":
                    yield f"data: {json.dumps({'type': 'error', 'message': content}, ensure_ascii=False)}\n\n"
                    return
            except queue.Empty:
                continue

        t.join(timeout=5)

        # 解析函数调用
        fc = _parse_function_call(full_reply)
        if fc:
            func_name = fc.get("name", "")
            params = fc.get("params", {})

            if func_name in SIDE_EFFECT_FUNCTIONS:
                _save_snapshot()

            result = _call_internal_api(func_name, params)
            action = {"type": func_name, "params": params, "result": result}

            # 发送 action 事件
            yield f"data: {json.dumps({'type': 'action', 'name': func_name, 'params': params, 'result': result}, ensure_ascii=False)}\n\n"

            # 生成简短操作结果反馈
            new_state = _get_full_state()
            result_context = (
                f"刚才执行了 {func_name}，参数：{json.dumps(params, ensure_ascii=False)}\n"
                f"结果：{json.dumps(result, ensure_ascii=False)}\n"
                f"更新后的状态：\n{new_state}"
            )

            followup_messages = [
                {"role": "system", "content": f"你是小说创作助手。{result_context}\n请简洁告知作者结果。"},
                {"role": "user", "content": "告知结果"},
            ]
            summary = model_router.chat_with_messages(
                followup_messages, task="chat", temperature=0.5, max_tokens=256
            )
            for ch in summary:
                yield f"data: {json.dumps({'type': 'token', 'content': ch}, ensure_ascii=False)}\n\n"

        # 更新历史
        _add_to_history("user", message)
        _add_to_history("assistant", full_reply, action)

        yield f"data: {json.dumps({'type': 'done'})}\n\n"

    return Response(stream_with_context(generate()), mimetype="text/event-stream")


@app.route("/api/chat/history", methods=["GET"])
def api_chat_history():
    """获取最近 20 轮对话历史"""
    return jsonify({"history": list(_chat_history)})


@app.route("/api/chat/confirm", methods=["POST"])
def api_chat_confirm():
    """确认待执行操作（前端确认卡片的“确认”按钮）。

    注意：带副作用的操作在后端解析到函数调用时已立即执行
    （见 api_chat_stream），本端点仅做确认回执；若要撤销
    已执行的操作，前端“取消”按钮走 /api/chat/undo 回滚快照。
    （历史上此端点未实现，前端点“确认”会 404 且被静默吞掉。）
    """
    data = request.get_json() or {}
    name = data.get("name", "")
    if name and name not in {f["name"] for f in FUNCTION_SPECS}:
        return jsonify({"error": f"未知操作: {name}"}), 400
    return jsonify({"status": "ok", "message": "操作已执行（确认回执）"})


@app.route("/api/chat/undo", methods=["POST"])
def api_chat_undo():
    """回滚最近一次有副作用的操作"""
    snapshot = _rollback_stack.pop()
    if snapshot is None:
        return jsonify({"status": "noop", "message": "没有可回滚的操作"})

    try:
        msg = _restore_snapshot(snapshot)
        return jsonify({
            "status": "ok",
            "message": msg,
            "remaining_undo_count": len(_rollback_stack),
        })
    except Exception as e:
        # 恢复失败，把快照推回去
        _rollback_stack.push(snapshot)
        return jsonify({"error": f"回滚失败: {e}"}), 500
