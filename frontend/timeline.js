/* timeline.js - 时间线页面：可视化、角色管理、情节引导 */

// ── 时间线页面 ──

function showTimelinePage() {
  document.querySelectorAll(".page").forEach(p => p.classList.remove("active"));
  document.getElementById("timeline-page").classList.add("active");
  loadTimelineData();
}

function backToGame() {
  document.querySelectorAll(".page").forEach(p => p.classList.remove("active"));
  document.getElementById("game-page").classList.add("active");
  refreshState();
}

function loadTimelineData() {
  // Inject pending chapter style if not already present
  if (!document.getElementById("timeline-pending-style")) {
    const st = document.createElement("style");
    st.id = "timeline-pending-style";
    st.textContent = ".timeline-pending { opacity: 0.65; border-left: 3px dashed #f0a030 !important; }";
    document.head.appendChild(st);
  }
  fetch("/api/timeline/data").then(r => r.json()).then(data => {
    if (data.status !== "ok") return;
    
    // Update chapter count
    const countEl = document.getElementById("timeline-chapter-count");
    if (countEl) {
      let txt = data.total_chapters + " 章";
      if (data.total_planned && data.total_planned > data.total_chapters) {
        txt += " / 规划 " + data.total_planned + " 章";
      }
      countEl.textContent = txt;
    }
    
    // Render timeline
    const container = document.getElementById("timeline-content");
    if (!container) return;
    
    if (data.timeline.length === 0) {
      container.innerHTML = '<div class="timeline-empty">暂无章节，请先推演章节</div>';
    } else {
      let html = "";
      data.timeline.forEach((ch, idx) => {
        const isPending = ch.is_pending;
        const hasOutline = ch.has_outline;
        const cls = isPending ? "timeline-chapter timeline-pending" : "timeline-chapter";
        html += '<div class="' + cls + '">';
        html += '<div class="timeline-chapter-number">第' + ch.number + '章';
        if (ch.volume) html += ' <span style="font-size:11px;color:#888;">[' + escapeHtml(ch.volume) + ']</span>';
        if (isPending) html += ' <span style="font-size:10px;color:#f0a030;">(待生成)</span>';
        if (!isPending) html += ' <span style="font-size:10px;color:var(--accent);cursor:pointer;margin-left:8px" onclick="event.stopPropagation();if(typeof WireframeCanvas!==\'undefined\'){try{WireframeCanvas.focusNodeByRef(\'第' + ch.number + '章\')}catch(e){}}">连线框</span>';
        html += '</div>';
        
        // 实际标题
        if (ch.title) html += '<div class="timeline-chapter-title">' + escapeHtml(ch.title) + '</div>';
        
        // 大纲规划标题（如果和实际不同则显示对比）
        if (hasOutline && ch.planned_title && ch.planned_title !== ch.title) {
          html += '<div style="font-size:12px;color:#6366f1;margin-top:2px;">';
          if (isPending) {
            html += '规划：' + escapeHtml(ch.planned_title);
          } else {
            html += '规划：' + escapeHtml(ch.planned_title) + ' (实际：' + escapeHtml(ch.title || '无') + ')';
          }
          html += '</div>';
        }
        
        // 大纲规划内容摘要
        if (hasOutline && ch.planned_summary) {
          html += '<div style="font-size:12px;color:#888;margin-top:4px;padding:4px 8px;background:#1a1a2e;border-radius:4px;border-left:3px solid #6366f1;">';
          html += escapeHtml(ch.planned_summary);
          html += '</div>';
        }
        
        // 实际内容预览
        if (ch.narrative_preview && !isPending) {
          html += '<div style="font-size:11px;color:#666;margin-top:4px;font-style:italic;">';
          html += escapeHtml(ch.narrative_preview.substring(0, 80)) + (ch.narrative_preview.length > 80 ? '...' : '');
          html += '</div>';
        }
        
        if (ch.world_event) html += '<div class="timeline-chapter-event">世界事件：' + escapeHtml(ch.world_event) + '</div>';
        
        // Character actions (only for generated chapters)
        if (!isPending) {
          const actions = ch.character_actions || {};
          const charNames = Object.keys(actions);
          if (charNames.length > 0) {
            html += '<div class="timeline-chapter-chars">';
            charNames.forEach(name => {
              html += '<span class="timeline-char-tag">' + escapeHtml(name) + '</span>';
            });
            html += '</div>';
            charNames.forEach(name => {
              const action = actions[name];
              if (action) {
                html += '<div class="timeline-char-action"><b>' + escapeHtml(name) + '：</b>' + escapeHtml(action) + '</div>';
              }
            });
          }
        }
        
        html += '</div>';
        if (idx < data.timeline.length - 1) {
          html += '<div class="timeline-connector"></div>';
        }
      });
      container.innerHTML = html;
    }
    
    // Render characters
    const charContainer = document.getElementById("timeline-characters");
    if (charContainer) {
      if (data.characters.length === 0) {
        charContainer.innerHTML = '<div style="color:#999;font-size:13px;">暂无角色</div>';
      } else {
        let html = "";
        data.characters.forEach(c => {
          html += '<div class="timeline-char-card">';
          html += '<div class="char-name">' + escapeHtml(c.name) + '</div>';
          if (c.location) html += '<div class="char-info">位置：' + escapeHtml(c.location) + '</div>';
          if (c.mood) html += '<div class="char-info">心情：' + escapeHtml(c.mood) + '</div>';
          if (c.abilities && c.abilities.length > 0) {
            html += '<div class="char-abilities">能力：' + c.abilities.map(escapeHtml).join("、") + '</div>';
          }
          html += '</div>';
        });
        charContainer.innerHTML = html;
      }
    }
  }).catch(err => {
    console.error("Failed to load timeline:", err);
  });
}

function escapeHtml(text) {
  if (!text) return "";
  const div = document.createElement("div");
  div.textContent = text;
  return div.innerHTML;
}

function showAddCharForm() {
  document.getElementById("tl-add-char-form").style.display = "block";
}

function hideAddCharForm() {
  document.getElementById("tl-add-char-form").style.display = "none";
  // Clear inputs
  ["tl-new-char-name", "tl-new-char-personality", "tl-new-char-abilities", "tl-new-char-weaknesses", "tl-new-char-goal"].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.value = "";
  });
}

function addNewCharacter() {
  const name = document.getElementById("tl-new-char-name").value.trim();
  if (!name) { alert("请输入角色名"); return; }
  
  const data = {
    name: name,
    gender: "男",
    age: 20,
    personality: document.getElementById("tl-new-char-personality").value.trim(),
    abilities: document.getElementById("tl-new-char-abilities").value.trim().split(/[,，]/).map(s => s.trim()).filter(s => s),
    weaknesses: document.getElementById("tl-new-char-weaknesses").value.trim().split(/[,，]/).map(s => s.trim()).filter(s => s),
    long_term_goal: document.getElementById("tl-new-char-goal").value.trim(),
  };
  
  fetch("/api/add-character", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify(data)
  }).then(r => r.json()).then(res => {
    if (res.error) {
      alert("添加失败：" + res.error);
    } else {
      hideAddCharForm();
      loadTimelineData(); // Refresh
    }
  }).catch(err => {
    alert("请求失败：" + err);
  });
}

function sendPlotGuidance() {
  const input = document.getElementById("plot-guidance-input");
  const feedback = document.getElementById("guidance-feedback");
  const text = input.value.trim();
  if (!text) { feedback.textContent = "请输入引导内容"; return; }
  
  feedback.textContent = "发送中...";
  
  fetch("/api/guide-plot", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({type: "inject_event", description: text})
  }).then(r => r.json()).then(res => {
    if (res.error) {
      feedback.textContent = "失败：" + res.error;
    } else {
      feedback.textContent = "已发送引导：" + text.substring(0, 30) + "...";
      input.value = "";
    }
  }).catch(err => {
    feedback.textContent = "请求失败";
  });
}


// ── 副本（分支）管理 ──

function showBranchPanel() {
  const overlay = document.createElement("div");
  overlay.className = "modal-overlay";
  overlay.id = "branch-overlay";
  overlay.innerHTML = `
    <div class="modal-dialog" style="min-width:500px;max-width:70vw;">
      <h3>时间线副本</h3>
      <p style="font-size:12px;color:#888;margin:0 0 12px 0;">
        从任意章节创建副本，探索不同的故事走向。
      </p>
      <div id="branch-list" style="margin-bottom:16px;">
        <div style="color:#888;text-align:center;padding:10px;">加载中...</div>
      </div>
      <div style="border-top:1px solid #333;padding-top:12px;">
        <h4 style="margin:0 0 8px 0;font-size:14px;">创建新副本</h4>
        <div style="display:flex;gap:8px;align-items:center;">
          <label style="font-size:12px;color:#888;">从第</label>
          <input type="number" id="branch-from-chapter" min="0" value="0" style="width:60px;padding:4px;background:#1a1a2e;color:#e0e0e0;border:1px solid #333;border-radius:4px;">
          <label style="font-size:12px;color:#888;">章分叉，名称</label>
          <input type="text" id="branch-name" placeholder="可选" style="flex:1;padding:4px 8px;background:#1a1a2e;color:#e0e0e0;border:1px solid #333;border-radius:4px;">
          <button class="btn-primary" onclick="createBranch()" style="padding:6px 14px;font-size:12px;">创建</button>
        </div>
      </div>
      <div id="branch-msg" style="font-size:12px;color:#888;margin-top:8px;"></div>
      <div class="modal-actions">
        <button class="btn-cancel" onclick="this.closest('.modal-overlay').remove()">关闭</button>
      </div>
    </div>
  `;
  document.body.appendChild(overlay);
  loadBranchList();
}

function loadBranchList() {
  fetch("/api/branches").then(r => r.json()).then(data => {
    const container = document.getElementById("branch-list");
    if (!container) return;
    if (data.status !== "ok" || !data.branches || data.branches.length === 0) {
      container.innerHTML = '<div style="color:#888;font-size:13px;">暂无副本</div>';
      return;
    }
    let html = '<div style="display:flex;flex-direction:column;gap:8px;">';
    data.branches.forEach(b => {
      const isActive = b.is_active;
      const badge = isActive ? '<span style="background:#4caf50;color:#fff;padding:1px 6px;border-radius:3px;font-size:10px;margin-left:6px;">当前</span>' : '';
      html += '<div style="display:flex;align-items:center;gap:10px;padding:8px 12px;background:#1a1a2e;border-radius:6px;border:1px solid #333;">';
      html += '<div style="flex:1;">';
      html += '<div style="font-size:14px;font-weight:500;">' + escapeHtml(b.name) + badge + '</div>';
      html += '<div style="font-size:11px;color:#888;">';
      if (isActive) {
        html += '主线 · ' + b.chapter_count + ' 章';
      } else {
        html += '从第' + b.from_chapter + '章分叉 · ' + b.chapter_count + ' 章 · ' + (b.created_at || '');
      }
      html += '</div></div>';
      if (!isActive) {
        html += '<button class="btn-secondary" onclick="switchBranch(\'' + b.id + '\')" style="padding:4px 10px;font-size:11px;">切换</button>';
        html += '<button class="btn-cancel" onclick="deleteBranch(\'' + b.id + '\')" style="padding:4px 10px;font-size:11px;">删除</button>';
      }
      html += '</div>';
    });
    html += '</div>';
    container.innerHTML = html;
  }).catch(err => {
    const container = document.getElementById("branch-list");
    if (container) container.innerHTML = '<div style="color:#e74c3c;">加载失败</div>';
  });
}

function createBranch() {
  const fromCh = parseInt(document.getElementById("branch-from-chapter")?.value) || 0;
  const name = document.getElementById("branch-name")?.value?.trim() || "";
  const msgEl = document.getElementById("branch-msg");
  
  fetch("/api/branches", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({ from_chapter: fromCh, name: name })
  }).then(r => r.json()).then(data => {
    if (data.error) {
      if (msgEl) { msgEl.textContent = "失败：" + data.error; msgEl.style.color = "#e74c3c"; }
    } else {
      if (msgEl) { msgEl.textContent = data.message; msgEl.style.color = "#4caf50"; }
      loadBranchList();
    }
  }).catch(err => {
    if (msgEl) { msgEl.textContent = "请求失败"; msgEl.style.color = "#e74c3c"; }
  });
}

function switchBranch(branchId) {
  const msgEl = document.getElementById("branch-msg");
  
  fetch("/api/branches/" + branchId + "/switch", {
    method: "POST"
  }).then(r => r.json()).then(data => {
    if (data.error) {
      if (msgEl) { msgEl.textContent = "失败：" + data.error; msgEl.style.color = "#e74c3c"; }
    } else {
      if (msgEl) { msgEl.textContent = data.message + "（" + data.chapter_count + "章）"; msgEl.style.color = "#4caf50"; }
      loadBranchList();
      loadTimelineData();
      if (typeof refreshState === "function") refreshState();
    }
  }).catch(err => {
    if (msgEl) { msgEl.textContent = "请求失败"; msgEl.style.color = "#e74c3c"; }
  });
}

function deleteBranch(branchId) {
  if (!confirm("确定删除此副本？")) return;
  const msgEl = document.getElementById("branch-msg");
  
  fetch("/api/branches/" + branchId, {
    method: "DELETE"
  }).then(r => r.json()).then(data => {
    if (data.error) {
      if (msgEl) { msgEl.textContent = "失败：" + data.error; msgEl.style.color = "#e74c3c"; }
    } else {
      if (msgEl) { msgEl.textContent = data.message; msgEl.style.color = "#4caf50"; }
      loadBranchList();
    }
  }).catch(err => {
    if (msgEl) { msgEl.textContent = "请求失败"; msgEl.style.color = "#e74c3c"; }
  });
}
