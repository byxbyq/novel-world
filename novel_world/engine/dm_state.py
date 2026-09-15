# -*- coding: utf-8 -*-
"""
DM 状态机 + 控制器

管理推演状态（IDLE → RUNNING ⇄ PAUSED → STOPPED），
在独立线程中运行推演循环，支持暂停/继续/单步/终止。
"""

import threading
import logging
import uuid
from enum import Enum

logger = logging.getLogger("DMController")


class DMState(Enum):
    IDLE = "idle"           # 未开始
    RUNNING = "running"     # 正在推演
    PAUSED = "paused"       # 暂停等待
    STOPPED = "stopped"     # 已终止


class InterruptedError(Exception):
    """推演被外部指令中断"""
    pass


class DMController:
    """DM 控制器，管理推演状态和外部指令"""

    def __init__(self, engine_adapter):
        self.state = DMState.IDLE
        self.engine = engine_adapter
        self._lock = threading.RLock()

        # 线程同步原语
        self._resume_event = threading.Event()   # 控制暂停/继续
        self._step_mode = False                   # True = 执行1个tick后自动暂停
        self._step_done = threading.Event()       # 单步完成信号

        # 后台线程
        self._thread = None

        # 运行时状态（用于前端轮询）
        self.current_tick = 0
        self.current_chapter = 0
        self.total_chapters = 0
        self.ticks_per_chapter = 0
        self.last_error = None

        # 干预日志
        self._intervention_log: list[dict] = []

        # 质量管线待处理问题队列（线程安全）
        self._pending_issues: list[dict] = []
        self._issues_lock = threading.Lock()

        # 结果
        self.latest_chapter = None

        # 进度阶段与正文实时预览（供前端增量轮询）
        self.phase = ""
        self._preview_text = ""
        self._preview_chapter = 0
        self._preview_lock = threading.Lock()

    # ── 日志 ──

    def _log(self, category: str, source: str, data: dict = None):
        """记录 DM 干预日志，供前端查询和调试追溯。"""
        entry = {
            "category": category,
            "source": source,
            "data": data or {},
            "chapter": self.current_chapter,
            "tick": self.current_tick,
        }
        if not hasattr(self, "_log_entries"):
            self._log_entries = []
        self._log_entries.append(entry)
        logger.debug(f"DM log [{category}] {source}: {data}")

    # ── 状态转换 ──

    def start(self, title: str = ""):
        """IDLE → RUNNING，在后台线程中开始推演"""
        with self._lock:
            if self.state != DMState.IDLE:
                return False
            self.state = DMState.RUNNING
            self._resume_event.set()
            self._step_mode = False
            self._step_done.clear()
            self.total_chapters = self.engine.config.total_chapters
            self.ticks_per_chapter = self.engine.config.ticks_per_chapter
            self.current_tick = 0
            # 从已生成章节数续写，避免进度归零重复计数
            bw = getattr(self.engine, "_backend_world", None)
            self.current_chapter = bw.current_chapter if bw else 0
            self.last_error = None
            self.latest_chapter = None
            self.phase = "准备中"
            with self._preview_lock:
                self._preview_text = ""
                self._preview_chapter = 0

        self._thread = threading.Thread(
            target=self._run_loop,
            args=(title,),
            daemon=True,
            name="DM-Thread",
        )
        self._thread.start()
        return True

    def pause(self):
        """RUNNING → PAUSED"""
        with self._lock:
            if self.state != DMState.RUNNING:
                return False
            self.state = DMState.PAUSED
            self._resume_event.clear()
        return True

    def resume(self):
        """PAUSED → RUNNING"""
        with self._lock:
            if self.state != DMState.PAUSED:
                return False
            self.state = DMState.RUNNING
            self._step_mode = False
            self._resume_event.set()
        return True

    def step_once(self):
        """PAUSED 状态下执行 1 个 Tick 然后回到 PAUSED"""
        with self._lock:
            if self.state != DMState.PAUSED:
                return False
            self.state = DMState.RUNNING
            self._step_mode = True
            self._step_done.clear()
            self._resume_event.set()
        return True

    def stop(self):
        """任意状态 → STOPPED"""
        with self._lock:
            self.state = DMState.STOPPED
            self._resume_event.set()   # 唤醒可能在等待的线程
            self._step_done.set()
        return True

    def reset(self):
        """STOPPED → IDLE，清理状态"""
        with self._lock:
            self.state = DMState.IDLE
            self._step_mode = False
            self.current_tick = 0
            self.current_chapter = 0
            self.last_error = None
            self.latest_chapter = None
            self.phase = ""
            with self._preview_lock:
                self._preview_text = ""
                self._preview_chapter = 0

    # ── 阶段与预览 ──

    def set_phase(self, phase: str):
        """更新当前推演阶段（供前端展示进度语义）"""
        with self._lock:
            self.phase = phase

    def preview_reset(self, chapter: int):
        """开始新一章正文生成前清空预览缓冲"""
        with self._preview_lock:
            self._preview_text = ""
            self._preview_chapter = chapter

    def preview_append(self, chunk: str):
        """AI 流式回调：追加正文分片（运行在 DM 线程）"""
        if not chunk:
            return
        with self._preview_lock:
            self._preview_text += chunk

    def get_preview(self, offset: int = 0) -> dict:
        """增量获取正文预览（前端按 offset 拉取新增部分）"""
        with self._preview_lock:
            text = self._preview_text
            if offset < 0 or offset > len(text):
                offset = 0
            return {
                "chapter": self._preview_chapter,
                "text": text[offset:],
                "offset": len(text),
                "total_length": len(text),
            }

    # ── 内部方法 ──

    def _checkpoint(self):
        """在 Tick 边界处检查状态。

        规则：
        - RUNNING → 继续
        - PAUSED → 阻塞等待 resume / step / stop
        - STOPPED → 抛出 InterruptedError
        - step_mode → 执行完当前 tick 后自动回到 PAUSED
        """
        with self._lock:
            state = self.state
            step_mode = self._step_mode

        if state == DMState.STOPPED:
            raise InterruptedError("推演已被终止")

        if state == DMState.PAUSED:
            # 等待恢复信号
            self._resume_event.wait()

            with self._lock:
                state = self.state
                step_mode = self._step_mode

            if state == DMState.STOPPED:
                raise InterruptedError("推演已被终止")

            # 恢复后继续执行

        # step_mode 处理：外部在 resume_event.set() 之前已标记
        # 这里在 checkpoint 返回后主循环会执行一个 tick，
        # 下一个 checkpoint 到来时检查 step_mode 并自动暂停
        # 我们在上一个 checkpoint 之后已经设置好了 step_mode，
        # 当前是 single-step 的执行帧——执行完后自动暂停。

    def _post_tick_checkpoint(self):
        """每完成一章后的检查——自动暂停，等待用户确认正文后再继续下一章"""
        with self._lock:
            self._step_mode = False
            if self.state == DMState.STOPPED:
                return
            self.state = DMState.PAUSED
            self.phase = "本章完成，等待继续"
            self._resume_event.clear()

        # 阻塞等待 继续 / 终止（STOPPED 会在此抛出 InterruptedError）
        self._checkpoint()

    def _run_loop(self, title: str):
        """推演主循环（运行在后台线程）。

        每章生成完成后自动暂停，等待用户阅读正文/干预，
        用户点"继续"才生成下一章；直到 total_chapters 全部完成。
        """
        try:
            while True:
                with self._lock:
                    if self.state == DMState.STOPPED:
                        break
                    if self.current_chapter >= self.total_chapters:
                        break

                self._checkpoint()

                next_chapter = self.current_chapter + 1
                chapter = self.engine.run_chapter(title, dm_controller=self)

                with self._lock:
                    self.current_chapter = next_chapter
                    self.current_tick = 0
                    if chapter:
                        self.latest_chapter = chapter

                self._post_tick_checkpoint()

            with self._lock:
                if self.state != DMState.STOPPED:
                    self.state = DMState.IDLE
        except InterruptedError:
            logger.info("DM: 推演被终止")
            with self._lock:
                self.state = DMState.STOPPED
                self.phase = "已终止"
        except Exception as e:
            logger.error(f"DM: 推演异常 - {e}")
            with self._lock:
                self.last_error = str(e)
                self.state = DMState.IDLE
                self.phase = "发生错误"

    # ── DM 干预指令执行 ──

    def execute_command(self, cmd: dict) -> dict:
        """执行一条 DM 干预指令，返回执行结果。

        支持指令类型：
        - modify_character: {type, name, field, value}
        - inject_event: {type, description}
        - force_move: {type, name, position}
        - add_goal: {type, name, goal, weight}
        """
        cmd_type = cmd.get("type", "")

        with self._lock:
            try:
                if cmd_type == "modify_character":
                    result = self._exec_modify_character(cmd)
                elif cmd_type == "inject_event":
                    result = self._exec_inject_event(cmd)
                elif cmd_type == "force_move":
                    result = self._exec_force_move(cmd)
                elif cmd_type == "add_goal":
                    result = self._exec_add_goal(cmd)
                else:
                    return {"success": False, "error": f"不支持的指令类型: {cmd_type}"}

                self._intervention_log.append({
                    "tick": self.current_tick,
                    "chapter": self.current_chapter,
                    "type": cmd_type,
                    "cmd": cmd,
                })
                return result

            except Exception as e:
                logger.error(f"DM 干预执行失败: {e}")
                return {"success": False, "error": str(e)}

    def _exec_modify_character(self, cmd: dict) -> dict:
        char = self.engine.get_character(cmd["name"])
        field = cmd["field"]
        value = cmd["value"]

        field_map = {
            "target": "long_term_goal",
            "personality": "config.personality",
            "position": "current_location",
            "mood": "current_mood",
        }
        if field not in field_map:
            return {"success": False, "error": f"不支持的修改字段: {field}"}

        if field == "target":
            char.long_term_goal.description = value
        elif field == "personality":
            char.config.personality = value
        elif field == "position":
            char.current_location = value
            if self.engine._backend_world:
                self.engine._backend_world.set_character_position(cmd["name"], value)
        elif field == "mood":
            char.current_mood = value

        return {"success": True, "message": f"修改 {cmd['name']}.{field} = {value}"}

    def _exec_inject_event(self, cmd: dict) -> dict:
        desc = cmd.get("description", "")
        self.engine.inject_world_event(cmd)
        return {"success": True, "message": f"注入事件: {desc[:50]}..."}

    def _exec_force_move(self, cmd: dict) -> dict:
        char = self.engine.get_character(cmd["name"])
        char.current_location = cmd["position"]
        if self.engine._backend_world:
            self.engine._backend_world.set_character_position(cmd["name"], cmd["position"])
        if hasattr(self.engine, '_nw_characters') and self.engine._nw_characters:
            for nc in self.engine._nw_characters:
                if nc.name == cmd["name"]:
                    pos = cmd["position"]
                    if isinstance(pos, (list, tuple)) and len(pos) >= 2:
                        nc.pos = (int(pos[0]), int(pos[1]))
                    elif isinstance(pos, str):
                        parts = pos.replace('（','(').replace('）',')').split(',')
                        try:
                            nc.pos = (int(parts[0].strip('() ')), int(parts[1].strip('() ')))
                        except (ValueError, IndexError):
                            pass
                    break
        return {"success": True, "message": f"移动 {cmd['name']} 到 {cmd['position']}"}

    def _exec_add_goal(self, cmd: dict) -> dict:
        char = self.engine.get_character(cmd["name"])
        weight = cmd.get("weight", 1.0)
        priority = max(1, min(10, int(weight * 5)))
        char.add_goal(description=cmd["goal"], priority=priority)
        return {"success": True, "message": f"为 {cmd['name']} 添加目标: {cmd['goal']}"}

    def get_intervention_context(self) -> str:
        """格式化干预日志为 AI prompt 上下文"""
        with self._lock:
            if not self._intervention_log:
                return ""
            lines = ["[系统] DM 干预记录："]
            for entry in self._intervention_log:
                tick = entry.get("tick", "?")
                cmd = entry.get("cmd", {})
                if entry["type"] == "modify_character":
                    lines.append(
                        f"- 第{tick} Tick：修改 {cmd.get('name','?')}.{cmd.get('field','?')}"
                        f" = \"{cmd.get('value','?')}\""
                    )
                elif entry["type"] == "inject_event":
                    lines.append(
                        f"- 第{tick} Tick：注入事件：\"{cmd.get('description','?')}\""
                    )
                elif entry["type"] == "force_move":
                    lines.append(
                        f"- 第{tick} Tick：强制移动 {cmd.get('name','?')}"
                        f" 到 {cmd.get('position','?')}"
                    )
                elif entry["type"] == "add_goal":
                    lines.append(
                        f"- 第{tick} Tick：为 {cmd.get('name','?')}"
                        f" 添加目标：\"{cmd.get('goal','?')}\""
                    )
                else:
                    lines.append(f"- 第{tick} Tick：{entry['type']}")
            lines.append("请在后续叙事中自然融入以上干预的后果。")
            return "\n".join(lines)

    def clear_interventions(self):
        """清空干预日志（章节叙事生成后调用）"""
        with self._lock:
            self._intervention_log.clear()

    # ── 质量管线问题反馈 ──

    def add_issue(self, issue_data: dict) -> str:
        """质量管线向 DM 推送一个待处理问题。

        issue_data 格式:
            {
                "source": "timeline_checker" | "power_check" | ...,
                "severity": "blocker" | "error" | "warning" | "info",
                "message": str,
                "dimension": str,
                "tick": int,
                "chapter": int,
                "suggestion": str,
                "related_characters": [str, ...],
                "detail": dict,
            }
        返回 issue_id。
        """
        issue_id = str(uuid.uuid4())[:8]
        entry = {
            "id": issue_id,
            "type": issue_data.get("source", "quality_pipeline"),
            "severity": issue_data.get("severity", "warning"),
            "message": issue_data.get("message", ""),
            "dimension": issue_data.get("dimension", ""),
            "tick": issue_data.get("tick", self.current_tick),
            "chapter": issue_data.get("chapter", self.current_chapter),
            "suggestion": issue_data.get("suggestion", ""),
            "related_characters": issue_data.get("related_characters", []),
            "detail": issue_data.get("detail", {}),
            "status": "pending",
            "timestamp": None,   # 由调用方填充
            "resolved_by": None,
            "resolved_action": None,
        }
        with self._issues_lock:
            self._pending_issues.append(entry)
        logger.info(f"DM 收到质量问题: [{issue_id}] {entry['severity']} - {entry['message'][:60]}")
        return issue_id

    def resolve_issue(self, issue_id: str, action: str, resolved_by: str = "dm") -> bool:
        """处理一个质量问题。

        action 支持: ignore / pause / rollback / fix
        """
        valid_actions = {"ignore", "pause", "rollback", "fix"}
        if action not in valid_actions:
            logger.warning(f"DM 收到不支持的问题处理动作: {action}")
            return False

        with self._issues_lock:
            for issue in self._pending_issues:
                if issue["id"] == issue_id:
                    issue["status"] = "resolved"
                    issue["resolved_by"] = resolved_by
                    issue["resolved_action"] = action
                    import datetime
                    issue["timestamp"] = datetime.datetime.now().isoformat()

                    # action=pause 时自动暂停推演
                    if action == "pause":
                        with self._lock:
                            if self.state == DMState.RUNNING:
                                self.state = DMState.PAUSED
                                self._resume_event.clear()

                    logger.info(f"DM 处理问题: [{issue_id}] action={action}")
                    return True
        logger.warning(f"DM 找不到待处理问题: {issue_id}")
        return False

    def get_pending_issues(self) -> list[dict]:
        """获取所有待处理问题（供 API 轮询）"""
        with self._issues_lock:
            return list(self._pending_issues)

    # ── 状态查询 ──

    def get_state(self) -> dict:
        """获取当前 DM 状态（供前端轮询）"""
        with self._lock:
            chapter_info = {}
            if self.latest_chapter:
                chapter_info = {
                    "chapter_title": self.latest_chapter.get("title", ""),
                    "chapter_number": self.latest_chapter.get("chapter", 0),
                }
            return {
                "dm_state": self.state.value,
                "phase": self.phase,
                "current_tick": self.current_tick,
                "current_chapter": self.current_chapter,
                "total_chapters": self.total_chapters,
                "ticks_per_chapter": self.ticks_per_chapter,
                "has_result": self.latest_chapter is not None,
                "last_error": self.last_error,
                **chapter_info,
            }
