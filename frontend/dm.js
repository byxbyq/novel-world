/* dm.js - DM模式：控制、干预面板、天意指引、时间线检查、势力、Prompt管理、批量编辑、章节进度条 */

// ── DM 控制 ──
let dmPollTimer = null;
let dmLatestResult = null;
let _dmPollFailCount = 0; // 轮询连续失败计数（容忍热重载/短暂断连）

let _dmStartTime = null;
let _dmTimerInterval = null;
let _dmAutoTimeout = null;
let _dmLastShownChapter = 0;      // 已展示到第几章（避免重复刷新）
let _dmLastProgressTime = 0;      // 最近一次有新章节产出的时间戳（超时保护用）
let _dmPreviewOffset = 0;         // 正文实时预览增量拉取位置

// 增量拉取正在生成的正文预览（打字机效果）
function dmPollPreview() {
  fetch("/api/dm/preview?offset=" + _dmPreviewOffset)
    .then(r => r.json())
    .then(p => {
      if (!p || !p.total_length) return;
      const box = document.getElementById("dm-live-preview");
      const textEl = document.getElementById("dm-live-preview-text");
      if (!box || !textEl) return;
      // 服务端 offset 被重置（新章开始/缓冲区清空）→ 清屏重新展示
      const serverStart = p.offset - p.text.length;
      if (serverStart === 0 && _dmPreviewOffset > 0) {
        textEl.textContent = "";
      }
      if (p.text) {
        textEl.textContent += p.text;
        textEl.scrollTop = textEl.scrollHeight;
      }
      _dmPreviewOffset = p.offset;
      const countEl = document.getElementById("dm-live-preview-count");
      if (countEl) countEl.textContent = "已生成 " + p.total_length + " 字";
      box.style.display = "block";
    })
    .catch(() => {});
}

function dmHidePreview() {
  const box = document.getElementById("dm-live-preview");
  if (box) box.style.display = "none";
  const textEl = document.getElementById("dm-live-preview-text");
  if (textEl) textEl.textContent = "";
  _dmPreviewOffset = 0;
}

// 拉取并展示最新一章正文（供推演过程中实时刷新和终止后收尾使用）
function _dmShowLatestChapter() {
  fetch("/api/chapters").then(r => r.json()).then(d => {
    if (d.chapters && d.chapters.length) {
      displayChapter(d.chapters[d.chapters.length - 1]);
    }
  }).catch(e => console.error("加载章节失败:", e));
}

function dmStart() {
  const title = document.getElementById("chapter-title").value.trim();
  fetch("/api/dm/start", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title })
  })
  .then(r => r.json())
  .then(data => {
    if (data.status === "ok") {
      _finaleWarned = false;
      const fill = document.getElementById("chapter-progress-fill");
      if (fill) { fill.style.width = "0%"; fill.classList.remove("finale"); }
      const bar = document.getElementById("chapter-progress-bar");
      if (bar) bar.style.display = "none";

      // 启动计时器
      _dmStartTime = Date.now();
      _dmLastShownChapter = 0;
      _dmLastProgressTime = Date.now();
      if (_dmTimerInterval) clearInterval(_dmTimerInterval);
      _dmTimerInterval = setInterval(_updateDmTimer, 1000);
      // 5分钟无新章节产出才判定卡死（每章生成本身就需要数分钟，有产出则持续续期）
      if (_dmAutoTimeout) clearTimeout(_dmAutoTimeout);
      _dmAutoTimeout = setTimeout(() => {
        if (document.getElementById("dm-state-label").textContent.includes("RUNNING")
            && Date.now() - _dmLastProgressTime > 300000) {
          dmStopSilent();
          alert("推演已超过5分钟无新章节产出，已自动终止。请检查API连接或减少章节复杂度。");
        }
      }, 305000);

      dmStartPolling();
      updateDMButtons("running");
      document.getElementById("chapter-content").innerHTML =
        '<div class="loading">天道正在编织命运（DM 模式）</div><div id="dm-elapsed" style="text-align:center;color:#888;font-size:13px;margin-top:8px;">已用时：0秒</div>';
    } else {
      alert(data.error || "启动失败");
    }
  })
  .catch(e => alert("连接失败：" + e.message));
}

function _updateDmTimer() {
  if (!_dmStartTime) return;
  const elapsed = Math.floor((Date.now() - _dmStartTime) / 1000);
  const min = Math.floor(elapsed / 60);
  const sec = elapsed % 60;
  const el = document.getElementById("dm-elapsed");
  if (el) el.textContent = `已用时：${min > 0 ? min + "分" : ""}${sec}秒`;
}

function dmStopSilent() {
  fetch("/api/dm/stop", { method: "POST" })
    .then(r => r.json())
    .then(() => {
      dmStopPolling();
      _stopDmTimer();
      updateDMButtons("stopped");
      // 终止后收尾：刷新章节列表并展示已生成的最新章，替换加载动画
      refreshChapterList();
      refreshState(null);
      _dmShowLatestChapter();
      // 连线框状态同步：DM推演结束后自动更新画布
      if (typeof WireframeCanvas !== 'undefined') {
        try { WireframeCanvas.syncFromEngine(); } catch(e) {}
        try { WireframeCanvas.runGlobalCheck(); } catch(e) {}
      }
    });
}

function _stopDmTimer() {
  if (_dmTimerInterval) { clearInterval(_dmTimerInterval); _dmTimerInterval = null; }
  if (_dmAutoTimeout) { clearTimeout(_dmAutoTimeout); _dmAutoTimeout = null; }
  _dmStartTime = null;
}

function dmPause() {
  fetch("/api/dm/pause", { method: "POST" })
    .then(r => r.json())
    .then(data => {
      if (data.status === "ok") {
        updateDMButtons("paused");
      }
    })
    .catch(e => console.error(e));
}

function dmResume() {
  fetch("/api/dm/resume", { method: "POST" })
    .then(r => r.json())
    .then(data => {
      if (data.status === "ok") {
        updateDMButtons("running");
      }
    })
    .catch(e => console.error(e));
}

function dmStep() {
  fetch("/api/dm/step", { method: "POST" })
    .then(r => r.json())
    .then(data => {
      if (data.status === "ok") {
        // step 后自动回到 paused
        updateDMButtons("paused");
      }
    })
    .catch(e => console.error(e));
}

function dmStop() {
  if (!confirm("确定要终止推演吗？")) return;
  fetch("/api/dm/stop", { method: "POST" })
    .then(r => r.json())
    .then(data => {
      dmStopPolling();
      _stopDmTimer();
      updateDMButtons("stopped");
      // 终止后收尾：刷新章节列表并展示已生成的最新章，替换加载动画
      refreshChapterList();
      refreshState(null);
      _dmShowLatestChapter();
      // 连线框状态同步：DM推演结束后自动更新画布
      if (typeof WireframeCanvas !== 'undefined') {
        try { WireframeCanvas.syncFromEngine(); } catch(e) {}
        try { WireframeCanvas.runGlobalCheck(); } catch(e) {}
      }
    })
    .catch(e => console.error(e));
}

function updateDMButtons(state) {
  const start = document.getElementById("dm-btn-start");
  const pause = document.getElementById("dm-btn-pause");
  const resume = document.getElementById("dm-btn-resume");
  const step = document.getElementById("dm-btn-step");
  const stop = document.getElementById("dm-btn-stop");

  // 默认全部禁用
  [start, pause, resume, step, stop].forEach(b => b.disabled = true);

  switch (state) {
    case "idle":
      start.disabled = false;
      break;
    case "running":
      pause.disabled = false;
      stop.disabled = false;
      break;
    case "paused":
      resume.disabled = false;
      step.disabled = false;
      stop.disabled = false;
      break;
    case "stopped":
      start.disabled = false;
      break;
  }
}

function dmStartPolling() {
  if (dmPollTimer) return;
  _dmPollFailCount = 0;
  dmPollTimer = setInterval(dmPoll, 1000);
}

function dmStopPolling() {
  if (dmPollTimer) {
    clearInterval(dmPollTimer);
    dmPollTimer = null;
  }
}

function dmPoll() {
  fetch("/api/dm/state")
    .then(r => r.json())
    .then(data => {
      _dmPollFailCount = 0; // 成功一次即重置失败计数
      // 更新状态标签
      const label = document.getElementById("dm-state-label");
      label.textContent = "状态: " + data.dm_state.toUpperCase();
      label.className = "state-" + data.dm_state;

      // 更新进度
      const totalChapters = data.total_chapters || 1;
      const currentChapter = data.current_chapter || 0;
      document.getElementById("dm-progress").textContent =
        `Tick: ${data.current_tick}/${totalChapters * data.ticks_per_chapter} | 章节: ${currentChapter}/${totalChapters}`;

      // 更新阶段提示（世界事件/角色行动/碰撞/AI生成正文/后处理…）
      const phaseEl = document.getElementById("dm-phase-label");
      if (phaseEl) phaseEl.textContent = data.phase ? "⚙ " + data.phase : "";

      // 运行中：增量拉取正文预览；非运行状态：隐藏预览区
      if (data.dm_state === "running") {
        dmPollPreview();
      } else {
        dmHidePreview();
      }

      // 更新章节进度条
      updateChapterProgress(currentChapter, totalChapters);

      // 同步按钮状态
      updateDMButtons(data.dm_state);

      // 更新干预面板显隐
      updateInterventionPanel(data.dm_state);

      // 更新干预日志
      if (data.dm_state === "paused") {
        refreshIntervLog();
        refreshTimelineIssues(true);
        refreshDmIssues(true);
        refreshFactions();
      }

      // 推演过程中有新章节产出 → 实时刷新展示（每章生成完立即可见）
      const latestNum = data.chapter_number || currentChapter;
      if (data.has_result && latestNum > _dmLastShownChapter
          && (data.dm_state === "running" || data.dm_state === "paused")) {
        _dmLastShownChapter = latestNum;
        _dmLastProgressTime = Date.now();
        refreshChapterList();
        _dmShowLatestChapter();
      }

      // 检查是否有结果产出（正常跑完全部章节，或被终止后）
      if (data.has_result && (data.dm_state === "idle" || data.dm_state === "stopped")) {
        dmStopPolling();
        _stopDmTimer();
        updateDMButtons(data.dm_state);
        // 刷新章节内容
        refreshChapterList();
        refreshState(null);
        _dmShowLatestChapter();
      }

      // 检查错误
      if (data.last_error) {
        dmStopPolling();
        updateDMButtons("idle");
        document.getElementById("chapter-content").innerHTML =
          `<p style="color:var(--accent)">推演出错：${data.last_error}</p>`;
      }
    })
    .catch(e => {
      // 单次失败（如 Flask 热重载瞬间/短暂断连）不永久停轮询，
      // 否则后端重启一次 DM 面板就永久冻结；连续失败 15 次才放弃
      _dmPollFailCount++;
      console.warn("DM轮询失败(" + _dmPollFailCount + "/15):", e.message);
      if (_dmPollFailCount >= 15) {
        console.error("DM轮询连续失败，停止轮询");
        dmStopPolling();
      }
    });
}

// ── DM 干预面板 ──

let intervCharactersLoaded = false;

// Tab 切换
document.addEventListener("click", function(e) {
  if (e.target.classList.contains("interv-tab")) {
    const tabName = e.target.dataset.tab;
    // 更新 active 状态
    document.querySelectorAll(".interv-tab").forEach(t => t.classList.remove("active"));
    e.target.classList.add("active");
    document.querySelectorAll(".interv-tab-content").forEach(c => c.classList.remove("active"));
    document.getElementById("tab-" + tabName).classList.add("active");

    // 切换连线框 tab 时刷新预览
    if (tabName === "interv-wireframe") {
      updateWireframePreview();
    }
  }
});

function updateInterventionPanel(dmState) {
  const panel = document.getElementById("dm-intervention-panel");
  const statusMsg = document.getElementById("interv-status-msg");

  if (dmState === "paused") {
    panel.style.display = "block";
    statusMsg.textContent = "推演已暂停，可进行干预";

    // 首次显示时加载角色列表
    if (!intervCharactersLoaded) {
      loadIntervCharacters();
    }
  } else {
    panel.style.display = "none";
    intervCharactersLoaded = false;
    document.getElementById("interv-status-msg").textContent = "";
  }
}

function loadIntervCharacters() {
  fetch("/api/dm/characters")
    .then(r => r.json())
    .then(data => {
      const sel1 = document.getElementById("interv-char-select");
      const sel2 = document.getElementById("interv-goal-char");
      const sel3 = document.getElementById("guidance-char-select");
      sel1.innerHTML = '<option value="">-- 选择角色 --</option>';
      sel2.innerHTML = '<option value="">-- 选择角色 --</option>';
      sel3.innerHTML = '<option value="">-- 选择角色 --</option>';
      if (data.characters) {
        data.characters.forEach(c => {
          const opt = `<option value="${c.name}">${c.name}</option>`;
          sel1.innerHTML += opt;
          sel2.innerHTML += opt;
          sel3.innerHTML += opt;
        });
      }
      intervCharactersLoaded = true;
    })
    .catch(e => console.error("加载角色列表失败:", e));
}

function dmInjectModify() {
  const name = document.getElementById("interv-char-select").value;
  const field = document.getElementById("interv-field-select").value;
  const value = document.getElementById("interv-value-input").value.trim();
  if (!name || !value) {
    alert("请选择角色并填写新值");
    return;
  }
  const cmd = { type: "modify_character", name, field, value };
  sendIntervention(cmd);
}

function dmInjectEvent() {
  const desc = document.getElementById("interv-event-desc").value.trim();
  if (!desc) {
    alert("请填写事件描述");
    return;
  }
  const cmd = { type: "inject_event", description: desc };
  sendIntervention(cmd);
  document.getElementById("interv-event-desc").value = "";
}

function dmInjectGoal() {
  const name = document.getElementById("interv-goal-char").value;
  const goal = document.getElementById("interv-goal-text").value.trim();
  if (!name || !goal) {
    alert("请选择角色并填写目标描述");
    return;
  }
  const cmd = { type: "add_goal", name, goal, weight: 1.0 };
  sendIntervention(cmd);
  document.getElementById("interv-goal-text").value = "";
}

function sendIntervention(cmd) {
  const statusMsg = document.getElementById("interv-status-msg");
  statusMsg.textContent = "执行中...";

  fetch("/api/dm/inject", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(cmd)
  })
    .then(r => r.json())
    .then(data => {
      if (data.success) {
        statusMsg.textContent = data.message || "干预已执行";
        // 刷新干预日志
        setTimeout(refreshIntervLog, 300);
      } else {
        statusMsg.textContent = "错误: " + (data.error || "未知错误");
      }
    })
    .catch(e => {
      statusMsg.textContent = "请求失败: " + e.message;
    });
}

// ── 天意指引 ──

function dmSendGuidance() {
  const char = document.getElementById("guidance-char-select").value;
  const msgText = document.getElementById("guidance-message").value.trim();
  const form = document.getElementById("guidance-form").value;
  const strength = document.getElementById("guidance-strength").value;
  const guidanceMsg = document.getElementById("guidance-msg");

  if (!char) {
    guidanceMsg.style.display = "block";
    guidanceMsg.textContent = "请选择目标角色";
    guidanceMsg.className = "interv-guidance-msg error";
    return;
  }
  if (!msgText) {
    guidanceMsg.style.display = "block";
    guidanceMsg.textContent = "请输入指引内容";
    guidanceMsg.className = "interv-guidance-msg error";
    return;
  }

  guidanceMsg.style.display = "block";
  guidanceMsg.textContent = "正在发送天意指引...";
  guidanceMsg.className = "interv-guidance-msg";

  fetch("/api/dm/guidance", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      character_name: char,
      message: msgText,
      form: form,
      strength: strength,
    })
  })
    .then(r => r.json())
    .then(data => {
      if (data.success) {
        guidanceMsg.textContent = `天意指引已发送给「${char}」（形式：${form}，强度：${strength}）`;
        guidanceMsg.className = "interv-guidance-msg success";
        document.getElementById("guidance-message").value = "";

        // 同步更新干预日志和状态提示
        document.getElementById("interv-status-msg").textContent =
          `天意指引已注入：${char}`;
        setTimeout(refreshIntervLog, 300);
      } else {
        guidanceMsg.textContent = "发送失败: " + (data.error || "未知错误");
        guidanceMsg.className = "interv-guidance-msg error";
      }
    })
    .catch(e => {
      guidanceMsg.textContent = "请求失败: " + e.message;
      guidanceMsg.className = "interv-guidance-msg error";
    });
}

function refreshIntervLog() {
  fetch("/api/dm/state")
    .then(r => r.json())
    .then(data => {
      const logDiv = document.getElementById("interv-log");
      const entries = data.intervention_log || [];
      if (entries.length === 0) {
        logDiv.innerHTML = '<div class="interv-empty">暂无干预记录</div>';
        return;
      }
      let html = "";
      entries.slice().reverse().forEach(e => {
        const tick = e.tick || "?";
        const cmd = e.cmd || {};
        let desc = "";
        switch (e.type) {
          case "modify_character":
            desc = `Tick ${tick} — 修改了 ${cmd.name} 的 ${cmd.field}: "${cmd.value}"`;
            break;
          case "inject_event":
            if (cmd.guidance_form) {
              desc = `Tick ${tick} — 天意指引 → ${(cmd.target_characters||["?"]).join("、")}（${cmd.guidance_form}/${cmd.guidance_strength}）`;
            } else {
              desc = `Tick ${tick} — 注入事件: "${(cmd.description || "").slice(0, 40)}..."`;
            }
            break;
          case "force_move":
            desc = `Tick ${tick} — 移动 ${cmd.name} 到 ${cmd.position}`;
            break;
          case "add_goal":
            desc = `Tick ${tick} — 为 ${cmd.name} 添加目标: "${cmd.goal}"`;
            break;
          default:
            desc = `Tick ${tick} — ${e.type}`;
        }
        html += `<div class="interv-log-entry">${desc}</div>`;
      });
      logDiv.innerHTML = html;
    })
    .catch(e => console.error("加载干预日志失败:", e));
}

// ── 时间线检查 ──

function refreshTimelineIssues(silent) {
  Promise.all([
    fetch("/api/timeline/issues").then(r => r.json()),
    fetch("/api/timeline/report").then(r => r.json()),
  ])
    .then(([issuesData, reportData]) => {
      const issues = issuesData.issues || [];
      const report = reportData.report || {};

      // 更新统计摘要
      const blockerCount = issues.filter(i => i.level === "blocker").length;
      const errorCount = issues.filter(i => i.level === "error").length;
      const warningCount = issues.filter(i => i.level === "warning").length;
      const infoCount = issues.filter(i => i.level === "info").length;

      const summary = document.getElementById("timeline-summary");
      let summaryText = "";
      if (blockerCount) summaryText += `blocker×${blockerCount} `;
      if (errorCount) summaryText += `error×${errorCount} `;
      if (warningCount) summaryText += `warning×${warningCount} `;
      if (infoCount) summaryText += `info×${infoCount}`;
      summary.textContent = summaryText || "无问题";
      summary.style.color = (blockerCount || errorCount) ? "#e74c3c" :
                            warningCount ? "#f39c12" : "#27ae60";

      // 渲染问题列表
      const issueDiv = document.getElementById("timeline-issues");
      if (issues.length === 0) {
        issueDiv.innerHTML = '<div class="interv-empty">暂无问题</div>';
      } else {
        let html = "";
        issues.slice().reverse().forEach(i => {
          const levelClass = "timeline-" + i.level;
          const levelLabel = { blocker: "致命", error: "错误", warning: "警告", info: "提示" }[i.level] || i.level;
          html += `<div class="interv-log-entry ${levelClass}" style="border-left:3px solid ${
            {blocker:"#e74c3c", error:"#e67e22", warning:"#f39c12", info:"#3498db"}[i.level] || "#999"
          };">
            <div class="timeline-issue-header">
              <span class="timeline-badge timeline-badge-${i.level}">${levelLabel}</span>
              <span class="timeline-dim">${i.dimension}</span>
              <span style="font-size:11px;color:#888;">Ch${i.chapter}/Tick${i.tick}</span>
            </div>
            <div class="timeline-issue-msg">${i.message}</div>
            ${i.suggestion ? `<div class="timeline-issue-sug">建议：${i.suggestion}</div>` : ""}
          </div>`;
        });
        issueDiv.innerHTML = html;
      }

      // 渲染伏笔列表
      const clueDiv = document.getElementById("timeline-clues");
      const unresolved = report.unresolved_clues || [];
      if (unresolved.length === 0) {
        clueDiv.innerHTML = '<div class="interv-empty">暂无未回收伏笔</div>';
      } else {
        let html = "";
        unresolved.forEach(c => {
          html += `<div class="interv-log-entry">
            <span class="timeline-badge timeline-badge-warning">伏笔</span>
            ${c.content}
            <span style="font-size:11px;color:#888;">(Ch${c.found_chapter}, ${c.age_ticks}Tick未回收)</span>
          </div>`;
        });
        clueDiv.innerHTML = html;
      }
    })
    .catch(e => {
      if (!silent) {
        console.error("加载时间线检查失败:", e);
      }
    });
}

// ── 质量告警（DM联动闭环）──

function refreshDmIssues(silent) {
  fetch("/api/dm/issues")
    .then(r => r.json())
    .then(data => {
      const issues = data.issues || [];
      const summary = document.getElementById("dm-issues-summary");
      const listDiv = document.getElementById("dm-issues-list");

      // 统计各严重级别
      const pending = issues.filter(i => i.status === "pending");
      const bCount = pending.filter(i => i.severity === "blocker").length;
      const eCount = pending.filter(i => i.severity === "error").length;
      const wCount = pending.filter(i => i.severity === "warning").length;
      const iCount = pending.filter(i => i.severity === "info").length;

      let summaryText = [];
      if (bCount) summaryText.push(`致命×${bCount}`);
      if (eCount) summaryText.push(`错误×${eCount}`);
      if (wCount) summaryText.push(`警告×${wCount}`);
      if (iCount) summaryText.push(`提示×${iCount}`);
      summary.textContent = summaryText.join(" ") || "无";
      summary.style.color = (bCount || eCount) ? "#e74c3c" :
                            wCount ? "#f39c12" : "#27ae60";

      if (pending.length === 0) {
        listDiv.innerHTML = '<div class="interv-empty">暂无质量告警</div>';
        return;
      }

      const severityColors = {
        blocker: "#e74c3c",
        error: "#e67e22",
        warning: "#f39c12",
        info: "#3498db"
      };
      const severityLabels = {
        blocker: "致命",
        error: "错误",
        warning: "警告",
        info: "提示"
      };

      let html = "";
      pending.reverse().forEach(issue => {
        const color = severityColors[issue.severity] || "#999";
        const label = severityLabels[issue.severity] || issue.severity;
        html += `<div class="interv-log-entry" style="border-left:3px solid ${color};padding:8px;margin-bottom:6px;background:#fafaf5;">
          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px;">
            <span>
              <span class="timeline-badge" style="background:${color};color:#fff;padding:1px 6px;border-radius:3px;font-size:11px;">${label}</span>
              <span class="timeline-dim" style="margin-left:6px;font-size:11px;color:var(--ink-light);">${issue.type} / ${issue.dimension || ""}</span>
            </span>
            <span style="font-size:10px;color:var(--ink-light);">Ch${issue.chapter} Tick${issue.tick} · ${issue.id}</span>
          </div>
          <div style="font-size:13px;color:var(--ink);margin-bottom:4px;">${issue.message}</div>
          ${issue.suggestion ? `<div style="font-size:11px;color:#f39c12;margin-bottom:6px;">建议: ${issue.suggestion}</div>` : ""}
          <div style="display:flex;gap:4px;flex-wrap:wrap;">
            <button class="interv-btn" style="padding:2px 8px;font-size:11px;background:#27ae60;" onclick="resolveDmIssue('${issue.id}','fix')">修复</button>
            <button class="interv-btn" style="padding:2px 8px;font-size:11px;background:#e74c3c;" onclick="resolveDmIssue('${issue.id}','pause')">暂停</button>
            <button class="interv-btn" style="padding:2px 8px;font-size:11px;background:#e67e22;" onclick="resolveDmIssue('${issue.id}','rollback')">回滚</button>
            <button class="interv-btn" style="padding:2px 8px;font-size:11px;background:#666;" onclick="resolveDmIssue('${issue.id}','ignore')">忽略</button>
          </div>
        </div>`;
      });
      listDiv.innerHTML = html;
    })
    .catch(e => {
      if (!silent) {
        console.error("加载DM问题失败:", e);
      }
    });
}

function resolveDmIssue(issueId, action) {
  const labels = { fix: "修复", pause: "暂停", rollback: "回滚", ignore: "忽略" };
  const label = labels[action] || action;
  if (action === "pause" && !confirm(`确定要暂停推演以处理问题 ${issueId} 吗？`)) return;
  if (action === "rollback" && !confirm(`确定要回滚以处理问题 ${issueId} 吗？此操作不可撤销。`)) return;

  fetch(`/api/dm/issues/${issueId}/resolve`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ action: action, resolved_by: "dm" })
  })
    .then(r => r.json())
    .then(data => {
      if (data.status === "ok") {
        showToast ? showToast(`问题 ${issueId}: ${label}`) : console.log(`问题 ${issueId}: ${label}`);
        refreshDmIssues();
        if (action === "pause") {
          updateDMButtons("paused");
        }
      } else {
        alert(data.error || "操作失败");
      }
    })
    .catch(e => alert("请求失败: " + e.message));
}

// ── 势力管理（phase2_p1）──

function refreshFactions() {
  fetch("/api/dm/factions")
    .then(r => r.json())
    .then(data => {
      const factions = data.factions || [];
      const container = document.getElementById("faction-list");
      if (factions.length === 0) {
        container.innerHTML = '<div class="interv-empty">暂未初始化势力</div>';
        return;
      }
      let html = "";
      factions.forEach(f => {
        const goalsHtml = (f.goals || []).map(g => {
          const desc = typeof g === "string" ? g : (g.description || "");
          const prog = (typeof g === "object" && g.progress !== undefined) ? g.progress : 0;
          return `<span style="font-size:11px;color:var(--ink-light);">${desc} (${Math.round(prog * 100)}%)</span>`;
        }).join("<br>") || "无目标";

        const enemiesHtml = (f.enemies || []).length
          ? f.enemies.map(e => `<span style="background:rgba(231,76,60,0.1);color:#e74c3c;padding:2px 6px;border-radius:3px;margin:2px;">${e}</span>`).join(" ")
          : "无";

        const alliesHtml = (f.allies || []).length
          ? f.allies.map(a => `<span style="background:rgba(39,174,96,0.1);color:#27ae60;padding:2px 6px;border-radius:3px;margin:2px;">${a}</span>`).join(" ")
          : "无";

        const territoryHtml = (f.territory || []).length
          ? f.territory.join(", ")
          : "未划分";

        html += `<div class="interv-log-entry" style="margin-bottom:8px;">
          <div style="display:flex;justify-content:space-between;align-items:center;">
            <strong style="color:${f.color || 'var(--ink)'};">${f.name}</strong>
            <span style="font-size:11px;color:var(--ink-light);">${f.member_count || 0}人</span>
          </div>
          <div style="font-size:11px;color:var(--ink-light);margin-top:4px;">
            领地：${territoryHtml}
          </div>
          <div style="font-size:11px;margin-top:2px;">
            敌对：${enemiesHtml} &nbsp; 同盟：${alliesHtml}
          </div>
          <div style="font-size:11px;margin-top:4px;line-height:1.5;">
            目标：${goalsHtml}
          </div>
        </div>`;
      });
      container.innerHTML = html;
    })
    .catch(e => {
      document.getElementById("faction-list").innerHTML =
        '<div class="interv-empty" style="color:#e74c3c;">加载失败</div>';
      console.error("加载势力列表失败:", e);
    });
}

// 在切换 Tab 时触发势力数据刷新
(function() {
  const factionTab = document.querySelector('.interv-tab[data-tab="interv-factions"]');
  if (factionTab) {
    factionTab.addEventListener("click", () => {
      setTimeout(refreshFactions, 50);
    });
  }
})();

// ── 章节进度条（phase2_p1）──

let _finaleWarned = false;

function updateChapterProgress(currentChapter, totalChapters) {
  const bar = document.getElementById("chapter-progress-bar");
  const fill = document.getElementById("chapter-progress-fill");
  const label = document.getElementById("chapter-progress-label");

  if (!bar || !fill || !label || totalChapters <= 0) return;

  bar.style.display = "block";
  const pct = Math.min((currentChapter / totalChapters) * 100, 100);
  fill.style.width = pct + "%";

  const isLast = currentChapter >= totalChapters;
  if (isLast) {
    fill.classList.add("finale");
    label.textContent = "终局章节";
    // 终局警告（只弹一次）
    if (!_finaleWarned && currentChapter === totalChapters) {
      _finaleWarned = true;
      setTimeout(() => {
        alert("【终局警告】\n\n即将进入终局章节（第" + totalChapters + "章）——这是整部小说的最后篇章。\n所有伏笔将被收束，势力命运将尘埃落定。");
      }, 300);
    }
  } else {
    fill.classList.remove("finale");
    label.textContent = `第 ${currentChapter}/${totalChapters} 章`;
  }
}

// ── Prompt 管理（phase2_p2）──

let _promptEditingName = null;

async function refreshPrompts() {
  const listEl = document.getElementById("prompt-list");
  if (!listEl) return;
  listEl.innerHTML = '<div class="interv-empty">加载中...</div>';

  try {
    const res = await fetch("/api/prompts");
    const data = await res.json();
    if (data.error) { listEl.innerHTML = `<div class="interv-empty">错误: ${data.error}</div>`; return; }

    const prompts = data.prompts || [];
    if (prompts.length === 0) {
      listEl.innerHTML = '<div class="interv-empty">暂无注册 Prompt</div>';
      return;
    }

    listEl.innerHTML = prompts.map(p => {
      const histBadge = p.history_count > 0
        ? `<span style="background:#2196f3;color:#fff;border-radius:3px;padding:1px 5px;font-size:10px;">${p.history_count} 版本</span>`
        : "";
      return `<div style="padding:4px 0;border-bottom:1px solid var(--border);cursor:pointer;display:flex;justify-content:space-between;align-items:center;"
                 onclick="openPromptEditor('${p.name}')"
                 onmouseenter="this.style.background='#fafaf5'" onmouseleave="this.style.background=''">
        <span style="font-size:13px;font-weight:bold;color:var(--ink);">${p.name}</span>
        <span style="font-size:11px;color:var(--ink-light);">${histBadge} ${p.current_length}字</span>
      </div>`;
    }).join("");
  } catch (e) {
    listEl.innerHTML = `<div class="interv-empty">请求失败: ${e.message}</div>`;
  }
}

async function openPromptEditor(name) {
  _promptEditingName = name;
  document.getElementById("prompt-editor-section").style.display = "block";
  document.getElementById("prompt-editor-name").textContent = name;
  document.getElementById("prompt-edit-msg").style.display = "none";

  try {
    const res = await fetch(`/api/prompts/${name}`);
    const data = await res.json();
    document.getElementById("prompt-editor-text").value = data.template || "";
  } catch (e) {
    document.getElementById("prompt-editor-text").value = "加载失败: " + e.message;
  }

  // 同时加载版本历史
  await refreshPromptHistory(name);
}

async function refreshPromptHistory(name) {
  if (!name) name = _promptEditingName;
  const section = document.getElementById("prompt-history-section");
  const listEl = document.getElementById("prompt-history-list");
  if (!section || !listEl) return;

  try {
    const res = await fetch(`/api/prompts/${name}/history`);
    const data = await res.json();
    if (data.error) { listEl.innerHTML = ""; return; }

    const history = data.history || [];
    if (history.length === 0) {
      listEl.innerHTML = '<div class="interv-empty">暂无历史版本</div>';
    } else {
      listEl.innerHTML = history.map((h, i) => {
        const latest = i === 0;
        return `<div style="padding:3px 6px;border-bottom:1px solid var(--border);font-size:11px;display:flex;justify-content:space-between;align-items:center;${latest ? 'background:rgba(39,174,96,0.08);' : ''}">
          <span>${h.version} ${latest ? '<span style="color:#27ae60;">(最新)</span>' : ''}</span>
          <span style="color:var(--ink-light);">${h.length}字 ${h.preview}</span>
        </div>`;
      }).join("");
    }
    section.style.display = "block";
  } catch (e) {
    listEl.innerHTML = "";
  }
}

async function savePromptEdit() {
  const name = _promptEditingName;
  const template = document.getElementById("prompt-editor-text").value;
  const msgEl = document.getElementById("prompt-edit-msg");
  if (!template.trim()) { msgEl.textContent = "模板不能为空"; msgEl.style.color = "#f44336"; msgEl.style.display = "block"; return; }

  try {
    const res = await fetch(`/api/prompts/${name}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ template })
    });
    const data = await res.json();
    if (data.error) { msgEl.textContent = "错误: " + data.error; msgEl.style.color = "#f44336"; }
    else { msgEl.textContent = "已保存，旧版本 " + data.saved_version + " 已备份"; msgEl.style.color = "#4caf50"; }
    msgEl.style.display = "block";
    await refreshPromptHistory(name);
  } catch (e) {
    msgEl.textContent = "请求失败: " + e.message; msgEl.style.color = "#f44336"; msgEl.style.display = "block";
  }
}

async function rollbackPrompt() {
  const name = _promptEditingName;
  const msgEl = document.getElementById("prompt-edit-msg");
  if (!confirm(`确定要将 "${name}" 回滚到上一个版本吗？`)) return;

  try {
    const res = await fetch(`/api/prompts/${name}/rollback`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ steps: 1 }) });
    const data = await res.json();
    if (data.error) { msgEl.textContent = "错误: " + data.error; msgEl.style.color = "#f44336"; }
    else if (data.rolled_to) {
      msgEl.textContent = "已回滚到 " + data.rolled_to;
      const verRes = await fetch(`/api/prompts/${name}`);
      const verData = await verRes.json();
      document.getElementById("prompt-editor-text").value = verData.template || "";
    } else { msgEl.textContent = data.message || "无可回滚版本"; msgEl.style.color = "#ff9800"; }
    msgEl.style.display = "block";
    await refreshPromptHistory(name);
  } catch (e) {
    msgEl.textContent = "请求失败: " + e.message; msgEl.style.color = "#f44336"; msgEl.style.display = "block";
  }
}

function cancelPromptEdit() {
  _promptEditingName = null;
  document.getElementById("prompt-editor-section").style.display = "none";
  document.getElementById("prompt-history-section").style.display = "none";
  document.getElementById("prompt-edit-msg").style.display = "none";
}

// ── 批量编辑（phase2_p2）──

async function batchEditCharacters() {
  const idsRaw = document.getElementById("batch-char-ids").value.trim();
  const field = document.getElementById("batch-char-field").value;
  const valueRaw = document.getElementById("batch-char-value").value.trim();
  const msgEl = document.getElementById("batch-char-msg");

  if (!valueRaw) { msgEl.textContent = "请输入值"; msgEl.style.color = "#f44336"; msgEl.style.display = "block"; return; }

  let ids = idsRaw === "" || idsRaw === "all" ? "all" : idsRaw.split(",").map(s => s.trim()).filter(Boolean);
  let updateVal = valueRaw;

  if (field === "personality") {
    updateVal = valueRaw.split(",").map(s => s.trim()).filter(Boolean);
  } else if (field === "pos") {
    const parts = valueRaw.split(",");
    if (parts.length !== 2) { msgEl.textContent = "位置格式错误，应为 x,y（如 5,3）"; msgEl.style.color = "#f44336"; msgEl.style.display = "block"; return; }
    updateVal = [parseInt(parts[0].trim()), parseInt(parts[1].trim())];
    if (isNaN(updateVal[0]) || isNaN(updateVal[1])) { msgEl.textContent = "位置必须是整数"; msgEl.style.color = "#f44336"; msgEl.style.display = "block"; return; }
  }

  try {
    const res = await fetch("/api/characters/batch", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ character_ids: ids, updates: { [field]: updateVal } })
    });
    const data = await res.json();
    if (data.error) { msgEl.textContent = "错误: " + data.error; msgEl.style.color = "#f44336"; }
    else {
      msgEl.textContent = `已修改 ${data.modified_count} 个角色`; msgEl.style.color = "#4caf50";
      fetch("/api/save", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ slot: "auto" }) });
    }
    msgEl.style.display = "block";
  } catch (e) {
    msgEl.textContent = "请求失败: " + e.message; msgEl.style.color = "#f44336"; msgEl.style.display = "block";
  }
}

async function batchEditFactions() {
  const idsRaw = document.getElementById("batch-fac-ids").value.trim();
  const field = document.getElementById("batch-fac-field").value;
  const valueRaw = document.getElementById("batch-fac-value").value.trim();
  const msgEl = document.getElementById("batch-fac-msg");

  if (!idsRaw || !valueRaw) { msgEl.textContent = "请填写势力 id 和值"; msgEl.style.color = "#f44336"; msgEl.style.display = "block"; return; }

  const ids = idsRaw.split(",").map(s => s.trim()).filter(Boolean);
  let updateVal = valueRaw.split(",").map(s => s.trim()).filter(Boolean);

  try {
    const res = await fetch("/api/factions/batch", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ faction_ids: ids, updates: { [field]: updateVal } })
    });
    const data = await res.json();
    if (data.error) { msgEl.textContent = "错误: " + data.error; msgEl.style.color = "#f44336"; }
    else {
      msgEl.textContent = `已修改 ${data.modified_count} 个势力`; msgEl.style.color = "#4caf50";
      fetch("/api/save", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ slot: "auto" }) });
    }
    msgEl.style.display = "block";
  } catch (e) {
    msgEl.textContent = "请求失败: " + e.message; msgEl.style.color = "#f44336"; msgEl.style.display = "block";
  }
}

async function batchImportCharacters() {
  const raw = document.getElementById("batch-import-json").value.trim();
  const msgEl = document.getElementById("batch-import-msg");
  if (!raw) { msgEl.textContent = "请输入 JSON 数据"; msgEl.style.color = "#f44336"; msgEl.style.display = "block"; return; }

  let chars;
  try { chars = JSON.parse(raw); } catch (e) { msgEl.textContent = "JSON 解析错误: " + e.message; msgEl.style.color = "#f44336"; msgEl.style.display = "block"; return; }
  if (!Array.isArray(chars)) { msgEl.textContent = "JSON 应为数组"; msgEl.style.color = "#f44336"; msgEl.style.display = "block"; return; }

  try {
    const res = await fetch("/api/characters/import", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ characters: chars })
    });
    const data = await res.json();
    if (data.error) { msgEl.textContent = "错误: " + data.error; msgEl.style.color = "#f44336"; }
    else {
      msgEl.textContent = `成功导入 ${data.imported} 个角色`; msgEl.style.color = "#4caf50";
      fetch("/api/save", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ slot: "auto" }) });
    }
    msgEl.style.display = "block";
  } catch (e) {
    msgEl.textContent = "请求失败: " + e.message; msgEl.style.color = "#f44336"; msgEl.style.display = "block";
  }
}

// ── 后处理面板（Phase 1）──────────────────────────────────────────────────
async function refreshPostProcessRules() {
  const listEl = document.getElementById("postprocess-rules-list");
  listEl.innerHTML = '<div class="interv-empty">加载中...</div>';
  try {
    const res = await fetch("/api/post-process/rules");
    const data = await res.json();
    if (data.rules && data.rules.length) {
      listEl.innerHTML = data.rules.map(r => {
        const enabled = r.enabled !== false;
        const color = enabled ? "#4caf50" : "#999";
        return `<div class="interv-log-line" style="display:flex;justify-content:space-between;">
          <span>${r.name || r.id}</span>
          <span style="color:${color};font-size:12px;">${enabled ? "已启用" : "已禁用"}</span>
        </div>`;
      }).join("");
    } else {
      listEl.innerHTML = '<div class="interv-empty">无规则</div>';
    }
  } catch (e) {
    listEl.innerHTML = `<div class="interv-empty">加载失败: ${e.message}</div>`;
  }
}

function togglePPRule(ruleId) {
  const cb = document.getElementById(`pp-${ruleId}`);
  if (!cb) return;
  const msgEl = document.getElementById("pp-rule-msg");
  msgEl.textContent = `规则 "${ruleId}" 已${cb.checked ? "启用" : "禁用"}`;
  msgEl.style.display = "block";
  msgEl.style.color = "#4caf50";
  setTimeout(() => { msgEl.style.display = "none"; }, 2000);
  // 调用后端 toggle API
  fetch("/api/post-process/toggle-rule", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ rule_id: ruleId, enabled: cb.checked })
  }).catch(() => {});
}

// ── 技能包管理（Phase 1）──────────────────────────────────────────────────
async function refreshSkillPacks() {
  const listEl = document.getElementById("skillpack-list");
  listEl.innerHTML = '<div class="interv-empty">加载中...</div>';
  try {
    const res = await fetch("/api/skill-packs/list");
    const data = await res.json();
    const packs = data.skills || data.packs || [];
    if (packs.length) {
      listEl.innerHTML = packs.map(p => `
        <div class="interv-log-line" style="display:flex;justify-content:space-between;align-items:center;">
          <div>
            <strong>${p.name || p.id || "未命名"}</strong>
            <span style="font-size:11px;color:#888;margin-left:8px;">${p.type || ""}</span>
          </div>
          <span style="font-size:11px;color:#888;">${(p.updated_at || p.created_at || "").slice(0, 10)}</span>
        </div>
        <div style="font-size:11px;color:#666;margin:2px 0 6px 0;">${p.description || ""}</div>`).join("");
    } else {
      listEl.innerHTML = '<div class="interv-empty">暂无技能包</div>';
    }
  } catch (e) {
    listEl.innerHTML = `<div class="interv-empty">加载失败: ${e.message}</div>`;
  }
}

function importSkillPack() {
  const msgEl = document.getElementById("skillpack-msg");
  const inputEl = document.getElementById("skillpack-input");
  const raw = (inputEl ? inputEl.value : "").trim();
  if (!raw) {
    msgEl.textContent = "请先在上方粘贴技能包 JSON 或小说文本";
    msgEl.style.color = "#f44336";
    msgEl.style.display = "block";
    return;
  }

  let body;
  try {
    const parsed = JSON.parse(raw);
    body = parsed;
  } catch (e) {
    body = { novel_text: raw };
  }

  fetch("/api/skill-packs/import", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body)
  })
    .then(r => r.json())
    .then(data => {
      if (data.error) {
        msgEl.textContent = "导入失败: " + data.error;
        msgEl.style.color = "#f44336";
        msgEl.style.display = "block";
        return;
      }
      msgEl.textContent = data.message || "导入完成";
      msgEl.style.color = "#4caf50";
      msgEl.style.display = "block";
      if (inputEl) inputEl.value = "";
      refreshSkillPacks();
    })
    .catch(e => {
      msgEl.textContent = "导入失败: " + e.message;
      msgEl.style.color = "#f44336";
      msgEl.style.display = "block";
    });
}

// ── 模型切换（多 Provider 架构）────────────────────────────────────────────

// 各 Provider 的预置模型列表
const PROVIDER_MODELS = {
  deepseek: ["deepseek-v4-flash", "deepseek-v4-pro", "deepseek-chat"],
  openai: ["gpt-4o-mini", "gpt-4o", "gpt-4-turbo"],
  doubao: ["doubao-pro-32k", "doubao-pro-128k", "doubao-lite-32k"],
  kimi: ["moonshot-v1-8k", "moonshot-v1-32k", "moonshot-v1-128k"],
  ollama: ["qwen3:14b", "qwen2.5:7b", "llama3:8b", "deepseek-r1:8b"]
};

function onProviderChange() {
  const provider = document.getElementById("provider-select").value;
  const modelSelect = document.getElementById("model-select");
  const models = PROVIDER_MODELS[provider] || [];
  modelSelect.innerHTML = models.map(m => `<option value="${m}">${m}</option>`).join("");
}

// [已清理] loadModelConfig / switchModel / DOMContentLoaded — 旧式 DOM 元素 api-base-url / api-key-model / api-key-status 已从 index.html 删除
// 模型配置现已由 js/model_config.js 统一管理（loadModelConfig / saveModelConfig，走 /api/ai/config）

// ── 大纲管理（Phase 2）────────────────────────────────────────────────────
async function refreshOutline() {
  const treeEl = document.getElementById("outline-tree");
  console.log("[refreshOutline] treeEl:", treeEl);
  treeEl.innerHTML = '<div class="interv-empty">加载中...</div>';
  try {
    const res = await fetch("/api/outline");
    const data = await res.json();
    console.log("[refreshOutline] data:", data);
    const volumes = data.volumes || [];
    console.log("[refreshOutline] volumes count:", volumes.length);
    if (volumes.length) {
      let html = "";
      volumes.forEach((vol, vi) => {
        const volOutline = vol.outline || {};
        const hasOutline = volOutline.summary || volOutline.theme;
        html += `<div class="outline-vol-section" style="margin-bottom:8px;border:1px solid var(--border);border-radius:6px;overflow:hidden">`;
        // 卷标题行
        html += `<div class="outline-vol-header" data-vol="${vi}" style="display:flex;align-items:center;gap:8px;padding:8px 12px;background:var(--surface);cursor:pointer;user-select:none" onclick="toggleVolOutline(this, ${vi})">
          <span id="vol-arrow-${vi}" style="font-size:12px;color:var(--ink-light);transition:0.2s">${hasOutline ? '\u25b6' : '\u00b7'}</span>
          <span style="font-weight:bold;color:#ff9800;flex:1">${vol.title}</span>
          <span style="font-size:11px;color:var(--ink-light)">${vol.chapter_count || 0}章</span>
          <span style="font-size:10px;color:var(--accent);cursor:pointer;margin-left:8px" onclick="event.stopPropagation();if(typeof WireframeCanvas!=='undefined'){try{WireframeCanvas.open('plan')}catch(e){}}">连线框</span>
        </div>`;
        // 卷纲要详情
        html += `<div class="outline-vol-body" id="vol-body-${vi}" style="display:none;padding:8px 12px;background:var(--bg);border-top:1px solid var(--border)">`;
        if (volOutline.summary) {
          html += `<div style="font-size:12px;color:var(--ink-light);margin-bottom:6px;line-height:1.6">${volOutline.summary}</div>`;
        }
        if (volOutline.key_events && volOutline.key_events.length) {
          html += `<div style="font-size:11px;color:var(--ink-light);margin-bottom:4px">关键事件（点击可定位连线框节点）：</div>`;
          volOutline.key_events.forEach(ev => {
            const evEsc = escapeHtml(ev);
            html += `<div style="font-size:12px;color:var(--ink);padding-left:12px;cursor:pointer" title="点击定位到连线框对应章节节点" data-wf-event="${evEsc}" onclick="event.stopPropagation();if(typeof WireframeCanvas!=='undefined'){try{WireframeCanvas.focusByEventText(this.dataset.wfEvent)}catch(e){}}">\u00b7 ${evEsc}</div>`;
          });
        }
        if (volOutline.character_arcs && volOutline.character_arcs.length) {
          html += `<div style="font-size:11px;color:var(--ink-light);margin-top:6px;margin-bottom:4px">角色弧线：</div>`;
          volOutline.character_arcs.forEach(arc => {
            html += `<div style="font-size:12px;color:var(--ink);padding-left:12px">\u00b7 ${arc}</div>`;
          });
        }
        html += `<button onclick="generateVolumeOutline(${vi})" style="margin-top:8px;padding:3px 12px;background:var(--accent);color:#fff;border:none;border-radius:4px;cursor:pointer;font-size:12px">${hasOutline ? '重新生成卷纲要' : 'AI 生成卷纲要'}</button>`;
        html += `</div></div>`;
      });
      treeEl.innerHTML = html;
    } else {
      treeEl.innerHTML = '<div class="interv-empty">暂无大纲，请先生成全书大纲</div>';
    }
    // 生成编辑器 Markdown
    if (volumes.length) {
      let md = "";
      volumes.forEach((vol, vi) => {
        md += `# ${vol.title}\n\n`;
        const vo = vol.outline || {};
        if (vo.theme) md += `> 主题：${vo.theme}\n\n`;
        if (vo.summary) md += `${vo.summary}\n\n`;
        if (vo.key_events && vo.key_events.length) {
          md += `## 关键事件\n`;
          vo.key_events.forEach(ev => { md += `- ${ev}\n`; });
          md += "\n";
        }
        if (vo.character_arcs && vo.character_arcs.length) {
          md += `## 角色弧线\n`;
          vo.character_arcs.forEach(arc => { md += `- ${arc}\n`; });
          md += "\n";
        }
      });
      document.getElementById("outline-editor-text").value = md;
    }
  } catch (e) {
    treeEl.innerHTML = `<div class="interv-empty">加载失败: ${e.message}</div>`;
  }
}

function generateOutline() {
  const msgEl = document.getElementById("outline-msg");
  msgEl.textContent = "AI 正在生成大纲...";
  msgEl.style.color = "#f39c12";
  msgEl.style.display = "block";
  fetch("/api/outline/generate", { method: "POST" })
    .then(r => r.json())
    .then(data => {
      msgEl.textContent = "大纲已生成";
      msgEl.style.color = "#4caf50";
      refreshOutline();
    })
    .catch(e => {
      msgEl.textContent = "生成失败: " + e.message;
      msgEl.style.color = "#f44336";
    });
}

function saveOutline() {
  const raw = document.getElementById("outline-editor-text").value;
  const msgEl = document.getElementById("outline-msg");
  fetch("/api/outline/save", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ outline_markdown: raw })
  })
  .then(r => r.json())
  .then(data => {
    msgEl.textContent = "大纲已保存";
    msgEl.style.color = "#4caf50";
    msgEl.style.display = "block";
    setTimeout(() => { msgEl.style.display = "none"; }, 2000);
    refreshOutline();
  })
  .catch(e => {
    msgEl.textContent = "保存失败: " + e.message;
    msgEl.style.color = "#f44336";
    msgEl.style.display = "block";
  });
}

function exportOutline() {
  const raw = document.getElementById("outline-editor-text").value;
  if (!raw) { showToast("大纲为空"); return; }
  const blob = new Blob([raw], { type: "text/markdown" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = "outline_" + new Date().toISOString().slice(0, 10) + ".md";
  a.click();
  showToast("大纲已导出");
}

// ── 人味审（Phase 3）──────────────────────────────────────────────────────
async function runHumanityAudit() {
  const scoresEl = document.getElementById("humanity-scores");
  const reportEl = document.getElementById("humanity-report");
  scoresEl.innerHTML = '<div class="interv-empty">审核中...</div>';
  reportEl.innerHTML = '<div class="interv-empty">等待结果...</div>';

  try {
    // 取当前（最新）章节正文作为审核内容
    const chRes = await fetch("/api/chapters");
    const chData = await chRes.json();
    const chapters = (chData && chData.chapters) || [];
    if (!chapters.length) {
      scoresEl.innerHTML = '<div class="interv-empty">暂无可审核章节，请先生成章节</div>';
      reportEl.innerHTML = '<div class="interv-empty">-</div>';
      return;
    }
    const latest = chapters[chapters.length - 1];
    const content = (latest && latest.narrative) || "";
    if (!content) {
      scoresEl.innerHTML = '<div class="interv-empty">最新章节正文为空，无法审核</div>';
      reportEl.innerHTML = '<div class="interv-empty">-</div>';
      return;
    }

    const res = await fetch("/api/humanity/audit", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ content: content })
    });
    const data = await res.json();
    if (data.error) {
      scoresEl.innerHTML = `<div class="interv-empty">错误: ${data.error}</div>`;
      reportEl.innerHTML = '<div class="interv-empty">-</div>';
      return;
    }
    // 渲染六维度评分
    const dimLabels = {
      inner_voice: "内心独白",
      warmth: "角色温度",
      c_layer_action: "C层动作",
      thermal_haptic: "温度触觉",
      wit: "幽默自嘲",
      sensory_density: "感官密度"
    };
    const scores = data.scores || {};
    scoresEl.innerHTML = Object.entries(dimLabels).map(([key, label]) => {
      const s = scores[key] || 0;
      const barWidth = Math.round(s * 100);
      const barColor = s >= 0.6 ? "#4caf50" : (s >= 0.35 ? "#f39c12" : "#f44336");
      return `<div style="margin:4px 0;">
        <div style="display:flex;justify-content:space-between;font-size:12px;">
          <span>${label}</span><span style="color:${barColor};">${s.toFixed(2)}</span>
        </div>
        <div style="background:var(--border);border-radius:3px;height:6px;margin-top:2px;">
          <div style="background:${barColor};width:${barWidth}%;height:6px;border-radius:3px;"></div>
        </div>
      </div>`;
    }).join("");

    // 渲染报告
    const index = data.humanity_index || 0;
    const statusColor = index >= 0.55 ? "#4caf50" : "#f44336";
    let reportHtml = `<div style="font-size:14px;margin-bottom:8px;">
      综合人味指数: <span style="color:${statusColor};font-weight:bold;font-size:18px;">${index.toFixed(2)}</span> / 1.00
    </div>`;
    if (data.strengths && data.strengths.length) {
      reportHtml += `<div style="margin-bottom:4px;"><strong>亮点:</strong></div>`;
      data.strengths.forEach(s => { reportHtml += `<div class="interv-log-line" style="color:#4caf50;">+ ${s}</div>`; });
    }
    if (data.flaws && data.flaws.length) {
      reportHtml += `<div style="margin-top:8px;margin-bottom:4px;"><strong>问题:</strong></div>`;
      data.flaws.forEach(f => { reportHtml += `<div class="interv-log-line" style="color:#f44336;">- ${f}</div>`; });
    }
    if (data.rewrite_hint) {
      reportHtml += `<div class="interv-log-line" style="margin-top:8px;color:#f39c12;font-style:italic;">> ${data.rewrite_hint}</div>`;
    }
    reportEl.innerHTML = reportHtml;
    showToast(`人味审完成: ${index.toFixed(2)}`);
  } catch (e) {
    scoresEl.innerHTML = `<div class="interv-empty">请求失败: ${e.message}</div>`;
    reportEl.innerHTML = '<div class="interv-empty">-</div>';
  }
}

// ═══════════════════════════════════════════
// 连线框 Tab 交互
// ═══════════════════════════════════════════
function updateWireframePreview() {
  const preview = document.getElementById("wireframe-mini-preview");
  const msg = document.getElementById("wf-mini-msg");
  if (!preview) return;

  fetch("/api/project/planning-cards")
    .then(r => r.json())
    .then(res => {
      if (res.ok && res.data) {
        const nodes = res.data.nodes || [];
        const edges = res.data.edges || [];
        const meta = res.data.meta || {};
        const lastSaved = meta.last_saved || "未保存";

        if (nodes.length === 0) {
          preview.innerHTML = "<div style='font-size:12px;color:var(--ink-light);'>画布为空，点击「打开连线框画布」开始规划</div>";
        } else {
          const types = {};
          nodes.forEach(n => { types[n.type||'free'] = (types[n.type||'free']||0) + 1; });
          const summary = Object.entries(types).map(([t,c]) => {
            const labels = { character:'人物', foreshadow:'伏笔', chapter:'章节', worldview:'世界观', free:'自由' };
            return `${labels[t]||t}:${c}`;
          }).join("，");

          preview.innerHTML = [
            `<div style="font-size:12px;color:var(--ink-light);text-align:left;padding:12px;line-height:1.8;">`,
            `<strong>节点统计：</strong>${nodes.length} 个节点 · ${edges.length} 条连线`,
            `<br><strong>类型分布：</strong>${summary}`,
            `<br><strong>最后保存：</strong>${lastSaved}`,
            `<br>`,
            `<br><span style="color:var(--accent);cursor:pointer;" onclick="WireframeCanvas.open('plan')">点击打开完整画布 →</span>`,
            `</div>`,
          ].join("");
        }
      }
    })
    .catch(() => {
      preview.innerHTML = "<div style='font-size:12px;color:var(--ink-light);'>加载失败，请检查服务器连接</div>";
    });
}

function toggleVolOutline(headerEl, vi) {
  const body = document.getElementById("vol-body-" + vi);
  const arrow = document.getElementById("vol-arrow-" + vi);
  if (body.style.display === "none") {
    body.style.display = "block";
    if (arrow) arrow.textContent = "\u25bc";
  } else {
    body.style.display = "none";
    if (arrow) arrow.textContent = "\u25b6";
  }
}

function generateVolumeOutline(vi) {
  const msgEl = document.getElementById("outline-msg");
  msgEl.textContent = "AI 正在生成第" + (parseInt(vi) + 1) + "卷纲要...";
  msgEl.style.color = "#f39c12";
  msgEl.style.display = "block";
  fetch("/api/outline/volume/" + vi + "/generate", { method: "POST" })
    .then(r => r.json())
    .then(data => {
      msgEl.textContent = "卷纲要已生成";
      msgEl.style.color = "#4caf50";
      refreshOutline();
    })
    .catch(e => {
      msgEl.textContent = "卷纲要生成失败: " + e.message;
      msgEl.style.color = "#f44336";
    });
}

