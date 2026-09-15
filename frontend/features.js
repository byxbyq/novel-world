/* features.js - 功能模块：项目管理、大纲系统、角色关系图、进度面板、导出、版本历史、角色编辑 */


// ── 项目管理 ──

function showPage(pageId) {
  document.querySelectorAll(".page").forEach(p => p.classList.remove("active"));
  document.getElementById(pageId).classList.add("active");
}

function showNewProjectPage() {
  showPage("setup-page");
}

function backToProjects() {
  showPage("projects-page");
  loadProjectsList();
}

async function loadProjectsList() {
  const container = document.getElementById("projects-list");
  container.innerHTML = '<div class="projects-loading">加载中...</div>';
  try {
    const res = await fetch("/api/projects");
    const data = await res.json();
    const projects = data.projects || [];
    if (!projects.length) {
      container.innerHTML = '<div class="projects-empty">还没有项目，点击上方「+ 新建项目」开始创作</div>';
      return;
    }
    container.innerHTML = projects.map(p => {
      const date = p.saved_at ? p.saved_at.replace("T", " ").substring(0, 16) : "";
      return `<div class="project-card">
        <div class="project-info">
          <h3>${p.name}</h3>
          <span>第${p.chapter}章 · ${date}</span>
        </div>
        <div class="project-actions">
          <button onclick="openProject('${p.id}')">打开</button>
          <button class="btn-danger" onclick="deleteProject('${p.id}')">删除</button>
        </div>
      </div>`;
    }).join("");
  } catch (e) {
    container.innerHTML = '<div class="projects-empty">加载失败：' + e.message + '</div>';
  }
}

async function openProject(slot) {
  const res = await fetch("/api/load/" + slot, { method: "POST" });
  const data = await res.json();
  if (data.status === "ok") {
    showPage("game-page");
    refreshState(data.state);
    refreshChapterList();
    // 加载大纲（从存档恢复）
    if (typeof loadOutline === "function") loadOutline();
    // 显示最后一章
    fetch("/api/chapters").then(r => r.json()).then(d => {
      if (d.chapters && d.chapters.length) {
        displayChapter(d.chapters[d.chapters.length - 1]);
      }
    });
  } else {
    alert("打开失败：" + (data.error || "未知错误"));
  }
}

async function deleteProject(slot) {
  if (!confirm("确定要删除这个项目吗？此操作不可恢复。")) return;
  const res = await fetch("/api/delete_save/" + slot, { method: "DELETE" });
  const data = await res.json();
  if (data.status === "ok") {
    loadProjectsList();
  } else {
    alert("删除失败：" + (data.error || ""));
  }
}


// ── 大纲系统 ──

let _currentOutline = null;

async function showOutlinePanel() {
  const overlay = document.createElement("div");
  overlay.className = "modal-overlay outline-overlay";
  overlay.id = "outline-overlay";
  overlay.innerHTML = `
    <div class="outline-modal-box">
      <div class="outline-modal-header">
        <h3>大纲规划</h3>
        <button class="outline-close-btn" onclick="this.closest('.modal-overlay').remove()">&times;</button>
      </div>
      <div id="outline-content" class="outline-scroll-area">
        <div class="outline-loading-hint">加载中...</div>
      </div>
      <div class="outline-footer">
        <div class="outline-param-group">
          <label>卷数</label>
          <input type="number" id="outline-volume-count" value="3" min="1" max="10" class="outline-param-input">
          <label>每卷章数</label>
          <input type="number" id="outline-chapters-per-volume" value="5" min="2" max="20" class="outline-param-input">
        </div>
        <div class="outline-footer-btns">
          <button class="btn-primary" onclick="generateOutlineModal()">AI 生成大纲</button>
          <button class="btn-secondary" onclick="continueOutlineModal()" style="background:#6366f1;color:#fff;">继续生成大纲</button>
          <button class="btn-secondary" onclick="regenChapterSummaries()" style="background:#e67e22;color:#fff;">重建章节摘要</button>
          <button class="btn-secondary" onclick="saveOutlineModal()">保存修改</button>
          <button class="btn-cancel" onclick="this.closest('.modal-overlay').remove()">关闭</button>
        </div>
      </div>
      <div id="outline-modal-msg" class="outline-msg-area"></div>
    </div>
  `;
  document.body.appendChild(overlay);
  await loadOutline();
}

async function loadOutline() {
  try {
    const res = await fetch("/api/outline");
    const data = await res.json();
    _currentOutline = data.outline || {volumes: [], chapters: []};
    // 恢复卷数/每卷章数输入框
    const vols = _currentOutline.volumes || [];
    const volInput = document.getElementById("outline-volume-count");
    const chInput = document.getElementById("outline-chapters-per-volume");
    if (volInput && vols.length > 0) volInput.value = vols.length;
    if (chInput && vols.length > 0 && vols[0].chapters) chInput.value = vols[0].chapters.length;
    // 仅在大纲面板已打开时渲染
    if (document.getElementById("outline-content")) renderOutline();
  } catch (e) {
    const container = document.getElementById("outline-content");
    if (container) container.innerHTML = '<div style="color:#e74c3c;">加载失败</div>';
  }
}

function renderOutline() {
  const container = document.getElementById("outline-content");
  if (!container) return;
  if (!_currentOutline || !_currentOutline.volumes || _currentOutline.volumes.length === 0) {
    container.innerHTML = '<div class="outline-empty-hint">暂无大纲，点击"AI 生成大纲"开始规划</div>';
    return;
  }

  let html = '';
  _currentOutline.volumes.forEach((vol, vi) => {
    html += `<div class="outline-volume-card">`;
    html += `<div class="outline-volume-title">
      <span class="outline-vol-prefix">第${vi + 1}卷</span>
      <input type="text" value="${escapeHtml(vol.name || '')}" oninput="_currentOutline.volumes[${vi}].name=this.value" class="outline-vol-name-input" placeholder="卷名">
    </div>`;
    html += `<div class="outline-volume-theme">
      <span class="outline-vol-theme-label">主题</span>
      <input type="text" value="${escapeHtml(vol.theme || '')}" oninput="_currentOutline.volumes[${vi}].theme=this.value" class="outline-vol-theme-input" placeholder="本卷主题">
    </div>`;
    if (vol.chapters && vol.chapters.length > 0) {
      html += `<div class="outline-chapter-list">`;
      vol.chapters.forEach((ch, ci) => {
        const summaryText = escapeHtml(ch.summary || '');
        html += `<div class="outline-chapter-item">
          <div class="outline-chapter-item-header">
            <span class="outline-chapter-num">第${ci + 1}章</span>
            <input type="text" value="${escapeHtml(ch.title || '')}" oninput="_currentOutline.volumes[${vi}].chapters[${ci}].title=this.value" class="outline-ch-title-input" placeholder="章节标题">
          </div>
          <textarea class="outline-ch-summary-textarea" placeholder="章节内容摘要（可展开编辑）" oninput="_currentOutline.volumes[${vi}].chapters[${ci}].summary=this.value">${summaryText}</textarea>
        </div>`;
      });
      html += `</div>`;
    }
    html += `</div>`;
  });
  container.innerHTML = html;
  // 使用 requestAnimationFrame 确保 DOM 布局完成后再测量高度
  requestAnimationFrame(() => {
    container.querySelectorAll('.outline-ch-summary-textarea').forEach(ta => {
      autoResizeTextarea(ta);
      ta.addEventListener('input', function() { autoResizeTextarea(this); });
    });
  });
}

function autoResizeTextarea(el) {
  el.style.height = 'auto';
  el.style.height = Math.max(80, el.scrollHeight + 4) + 'px';
}

async function generateOutlineModal() {
  const msgEl = document.getElementById("outline-modal-msg");
  msgEl.textContent = "AI 正在生成大纲，请稍候...";
  msgEl.style.color = "#6366f1";

  try {
    const res = await busyFetch("/api/outline/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        volume_count: parseInt(document.getElementById("outline-volume-count")?.value) || 3,
        chapters_per_volume: parseInt(document.getElementById("outline-chapters-per-volume")?.value) || 5
      })
    }, "AI 正在生成大纲");
    const data = await res.json();
    if (data.status === "ok") {
      _currentOutline = data.outline;
      renderOutline();
      // 自动同步总章节数到引擎配置
      let totalFromOutline = 0;
      if (data.outline.volumes) {
        data.outline.volumes.forEach(v => { totalFromOutline += (v.chapters || []).length; });
      }
      if (totalFromOutline > 0) {
        const cfgInput = document.getElementById("config-total-chapters");
        if (cfgInput) cfgInput.value = totalFromOutline;
        msgEl.textContent = `大纲已生成（共${totalFromOutline}章），章节生成将严格遵循大纲规划。你可以手动修改后保存`;
      } else {
        msgEl.textContent = "大纲已生成，你可以手动修改后保存";
      }
      msgEl.style.color = "#4caf50";
      // 大纲生成后自动保存，防止服务器重启丢失
      fetch("/api/save", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ slot: "auto" })
      });
    } else {
      msgEl.textContent = "生成失败：" + data.error;
      msgEl.style.color = "#e74c3c";
    }
  } catch (e) {
    msgEl.textContent = e.name === "AbortError" ? "已中止等待，可稍后重试" : "请求失败：" + e.message;
    msgEl.style.color = "#e74c3c";
  }
}

async function saveOutlineModal() {
  const msgEl = document.getElementById("outline-modal-msg");
  try {
    // 直接以 AI 格式（name/theme/chapters[{title,summary}]）提交，
    // 后端负责转换为 OutlineManager 格式，避免章节摘要丢失
    const volumes = _currentOutline?.volumes || [];

    const res = await fetch("/api/outline", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ volumes })
    });
    const data = await res.json();
    if (data.status === "ok") {
      // 以后端归一化后的数据为准，保持本地与存档一致
      if (data.outline) _currentOutline = data.outline;
      renderOutline();
      // 同步章节数到引擎配置
      let total = 0;
      if (_currentOutline && _currentOutline.volumes) {
        _currentOutline.volumes.forEach(v => { total += (v.chapters || []).length; });
      }
      if (total > 0) {
        const cfgInput = document.getElementById("config-total-chapters");
        if (cfgInput) cfgInput.value = total;
      }
      msgEl.textContent = `大纲已保存，章节生成将遵循此大纲（共${total || '?'}章）`;
      msgEl.style.color = "#4caf50";
      // 持久化保存到存档（防止刷新后大纲丢失）
      fetch("/api/save", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ slot: "auto" })
      });
    } else {
      msgEl.textContent = "保存失败：" + (data.error || "未知错误");
      msgEl.style.color = "#e74c3c";
    }
  } catch (e) {
    msgEl.textContent = "请求失败：" + e.message;
    msgEl.style.color = "#e74c3c";
  }
}

// ── 重建章节摘要（AI 补写丢失的 chapters[].summary）──

async function regenChapterSummaries() {
  const msgEl = document.getElementById("outline-modal-msg");
  msgEl.textContent = "AI 正在重建章节摘要，请稍候...";
  msgEl.style.color = "#e67e22";
  try {
    const res = await busyFetch("/api/outline/summaries/regenerate", { method: "POST" }, "AI 正在重建章节摘要");
    const data = await res.json();
    if (data.status === "ok") {
      if (data.outline) _currentOutline = data.outline;
      renderOutline();
      msgEl.textContent = data.message || "章节摘要已重建";
      msgEl.style.color = "#4caf50";
      // 自动保存到存档
      fetch("/api/save", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ slot: "auto" })
      });
    } else {
      msgEl.textContent = "重建失败：" + (data.error || "未知错误");
      msgEl.style.color = "#e74c3c";
    }
  } catch (e) {
    msgEl.textContent = e.name === "AbortError" ? "已中止等待，可稍后重试" : "请求失败：" + e.message;
    msgEl.style.color = "#e74c3c";
  }
}

// ── 继续生成大纲（续写扩容）──

async function continueOutlineModal() {
  const msgEl = document.getElementById("outline-modal-msg");
  const volCount = parseInt(document.getElementById("outline-volume-count")?.value) || 1;
  const chPerVol = parseInt(document.getElementById("outline-chapters-per-volume")?.value) || 5;

  msgEl.textContent = `AI 正在续写 ${volCount} 卷（每卷 ${chPerVol} 章）的大纲，请稍候...`;
  msgEl.style.color = "#6366f1";

  try {
    const res = await busyFetch("/api/outline/continue", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        volume_count: volCount,
        chapters_per_volume: chPerVol
      })
    }, "AI 正在续写大纲");
    const data = await res.json();
    if (data.status === "ok") {
      // 更新本地大纲数据
      _currentOutline = data.outline || _currentOutline;
      renderOutline();

      // 同步 total_chapters 到前端配置
      const cfgInput = document.getElementById("config-total-chapters");
      if (cfgInput && data.total_chapters) cfgInput.value = data.total_chapters;

      msgEl.textContent = data.message || `续写成功，总章节数已扩容至 ${data.total_chapters} 章`;
      msgEl.style.color = "#4caf50";

      // 自动保存
      fetch("/api/save", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ slot: "auto" })
      });
    } else {
      msgEl.textContent = "续写失败：" + (data.error || "未知错误");
      msgEl.style.color = "#e74c3c";
    }
  } catch (e) {
    msgEl.textContent = e.name === "AbortError" ? "已中止等待，可稍后重试" : "请求失败：" + e.message;
    msgEl.style.color = "#e74c3c";
  }
}

// ── 角色关系图谱 ──

async function showRelationGraph() {
  const overlay = document.createElement("div");
  overlay.className = "modal-overlay";
  overlay.innerHTML = `
    <div class="modal-dialog" style="min-width:600px;max-width:80vw;max-height:80vh;">
      <h3>角色关系图谱</h3>
      <div id="relation-graph-content" style="min-height:300px;display:flex;align-items:center;justify-content:center;">
        <div style="color:#888;">加载中...</div>
      </div>
      <div class="modal-actions">
        <button class="btn-cancel" onclick="this.closest('.modal-overlay').remove()">关闭</button>
      </div>
    </div>
  `;
  document.body.appendChild(overlay);

  try {
    const res = await fetch("/api/character-relations");
    const data = await res.json();
    renderRelationGraph(data);
  } catch (e) {
    document.getElementById("relation-graph-content").innerHTML = '<div style="color:#e74c3c;">加载失败</div>';
  }
}

function renderRelationGraph(data) {
  const container = document.getElementById("relation-graph-content");
  const nodes = data.nodes || [];
  const edges = data.edges || [];

  if (nodes.length === 0) {
    container.innerHTML = '<div style="color:#888;">暂无角色</div>';
    return;
  }

  // Simple SVG graph
  const width = 500;
  const height = 400;
  const cx = width / 2;
  const cy = height / 2;
  const radius = Math.min(width, height) * 0.35;

  // Position nodes in a circle
  const positions = nodes.map((n, i) => {
    const angle = (2 * Math.PI * i) / nodes.length - Math.PI / 2;
    return {
      x: cx + radius * Math.cos(angle),
      y: cy + radius * Math.sin(angle),
      node: n
    };
  });

  let svg = `<svg width="${width}" height="${height}" style="background:#fafafa;border-radius:8px;">`;

  // Draw edges
  edges.forEach(e => {
    const src = positions.find(p => p.node.id === e.source);
    const tgt = positions.find(p => p.node.id === e.target);
    if (src && tgt) {
      svg += `<line x1="${src.x}" y1="${src.y}" x2="${tgt.x}" y2="${tgt.y}" stroke="#ccc" stroke-width="1.5"/>`;
      // Label
      const mx = (src.x + tgt.x) / 2;
      const my = (src.y + tgt.y) / 2;
      svg += `<text x="${mx}" y="${my}" font-size="10" fill="#888" text-anchor="middle">${e.label || ""}</text>`;
    }
  });

  // Draw nodes
  positions.forEach(p => {
    const color = p.node.gender === "女" ? "#e91e63" : "#1976d2";
    svg += `<circle cx="${p.x}" cy="${p.y}" r="24" fill="${color}" opacity="0.15" stroke="${color}" stroke-width="2"/>`;
    svg += `<text x="${p.x}" y="${p.y + 4}" font-size="12" font-weight="bold" fill="${color}" text-anchor="middle">${p.node.id}</text>`;
    // Info below
    svg += `<text x="${p.x}" y="${p.y + 38}" font-size="9" fill="#888" text-anchor="middle">${p.node.location || ""}</text>`;
  });

  svg += `</svg>`;
  container.innerHTML = svg;
}

// ── 项目进度面板 ──

async function showProgressPanel() {
  const overlay = document.createElement("div");
  overlay.className = "modal-overlay";
  overlay.innerHTML = `
    <div class="modal-dialog" style="min-width:450px;">
      <h3>项目进度</h3>
      <div id="progress-content" style="margin-bottom:16px;">
        <div style="text-align:center;color:#888;padding:20px;">加载中...</div>
      </div>
      <div class="modal-actions">
        <button class="btn-cancel" onclick="this.closest('.modal-overlay').remove()">关闭</button>
      </div>
    </div>
  `;
  document.body.appendChild(overlay);

  try {
    const res = await fetch("/api/progress");
    const data = await res.json();
    renderProgress(data);
  } catch (e) {
    document.getElementById("progress-content").innerHTML = '<div style="color:#e74c3c;">加载失败</div>';
  }
}

function renderProgress(data) {
  const container = document.getElementById("progress-content");
  const pct = data.chapters_total > 0 ? Math.round((data.chapters_done / data.chapters_total) * 100) : 0;

  let html = `
    <div style="text-align:center;margin-bottom:16px;">
      <div style="font-size:24px;font-weight:bold;color:#333;">${data.world_name || "未命名"}</div>
      <div style="font-size:12px;color:#888;margin-top:4px;">${data.main_objective || "无主线目标"}</div>
    </div>
    <div style="margin-bottom:16px;">
      <div style="display:flex;justify-content:space-between;font-size:13px;margin-bottom:4px;">
        <span>章节进度</span>
        <span>${data.chapters_done} / ${data.chapters_total} 章 (${pct}%)</span>
      </div>
      <div style="height:12px;background:#e0e0e0;border-radius:6px;overflow:hidden;">
        <div style="height:100%;width:${pct}%;background:linear-gradient(90deg,#4488FF,#44DDDD);border-radius:6px;transition:width 0.3s;"></div>
      </div>
    </div>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;">
      <div style="background:#f5f5f5;padding:12px;border-radius:8px;text-align:center;">
        <div style="font-size:20px;font-weight:bold;color:#333;">${data.character_count}</div>
        <div style="font-size:11px;color:#888;">角色数</div>
      </div>
      <div style="background:#f5f5f5;padding:12px;border-radius:8px;text-align:center;">
        <div style="font-size:20px;font-weight:bold;color:#333;">${(data.total_words / 1000).toFixed(1)}k</div>
        <div style="font-size:11px;color:#888;">总字数</div>
      </div>
      <div style="background:#f5f5f5;padding:12px;border-radius:8px;text-align:center;">
        <div style="font-size:20px;font-weight:bold;color:#333;">${data.outline_volumes}</div>
        <div style="font-size:11px;color:#888;">大纲卷数</div>
      </div>
      <div style="background:#f5f5f5;padding:12px;border-radius:8px;text-align:center;">
        <div style="font-size:20px;font-weight:bold;color:#333;">${data.chapters_total - data.chapters_done}</div>
        <div style="font-size:11px;color:#888;">剩余章节</div>
      </div>
    </div>
  `;
  container.innerHTML = html;
}

// ── 世界设定编辑面板（开局后中途修改初始设定） ──

function _selectOptionsHtml(values, current) {
  const opts = values.slice();
  if (current && !opts.includes(current)) opts.push(current);
  return opts.map(v => `<option value="${escapeHtml(v)}"${v === current ? ' selected' : ''}>${escapeHtml(v)}</option>`).join("");
}

async function showWorldSettingsPanel() {
  const overlay = document.createElement("div");
  overlay.className = "modal-overlay";
  overlay.innerHTML = `
    <div class="modal-dialog" style="min-width:520px;max-height:85vh;overflow-y:auto;">
      <h3>世界设定（中途编辑）</h3>
      <div id="world-settings-content" style="margin-bottom:12px;">
        <div style="text-align:center;color:#888;padding:20px;">加载中...</div>
      </div>
      <div class="modal-actions">
        <button class="btn-cancel" onclick="this.closest('.modal-overlay').remove()">取消</button>
        <button class="btn-confirm" id="btn-save-world-settings" disabled>保存</button>
      </div>
    </div>
  `;
  document.body.appendChild(overlay);

  try {
    const res = await fetch("/api/world-config");
    const data = await res.json();
    if (data.error || !data.config) {
      overlay.querySelector("#world-settings-content").innerHTML = `<div style="color:#e74c3c;">${escapeHtml(data.error || "加载失败")}</div>`;
      return;
    }
    const wc = data.config;
    overlay.querySelector("#world-settings-content").innerHTML = `
      <div style="margin-bottom:10px;">
        <label style="font-size:12px;color:#888;">世界名称</label>
        <input id="ws-name" type="text" value="${escapeHtml(wc.name || '')}" style="width:100%;padding:6px;border:1px solid #ddd;border-radius:4px;">
      </div>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:10px;">
        <div>
          <label style="font-size:12px;color:#888;">类型</label>
          <select id="ws-genre" style="width:100%;padding:6px;border:1px solid #ddd;border-radius:4px;">
            ${_selectOptionsHtml(["玄幻","科幻","末世","都市","神话","奇幻","恐怖","自定义"], wc.genre)}
          </select>
        </div>
        <div>
          <label style="font-size:12px;color:#888;">时代</label>
          <select id="ws-era" style="width:100%;padding:6px;border:1px solid #ddd;border-radius:4px;">
            ${_selectOptionsHtml(["古代","近现代","现代","未来","架空"], wc.era)}
          </select>
        </div>
      </div>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:10px;">
        <div>
          <label style="font-size:12px;color:#888;">叙事基调</label>
          <select id="ws-tone" style="width:100%;padding:6px;border:1px solid #ddd;border-radius:4px;">
            ${_selectOptionsHtml(["史诗冒险","黑暗残酷","轻松日常","权谋博弈","热血燃向"], wc.tone)}
          </select>
        </div>
        <div>
          <label style="font-size:12px;color:#888;">叙事视角</label>
          <select id="ws-perspective" style="width:100%;padding:6px;border:1px solid #ddd;border-radius:4px;">
            <option value="third"${wc.perspective === 'third' ? ' selected' : ''}>第三人称</option>
            <option value="first"${wc.perspective === 'first' ? ' selected' : ''}>第一人称</option>
          </select>
        </div>
      </div>
      <div style="margin-bottom:10px;">
        <label style="font-size:12px;color:#888;">世界描述</label>
        <textarea id="ws-desc" rows="3" style="width:100%;padding:6px;border:1px solid #ddd;border-radius:4px;">${escapeHtml(wc.description || '')}</textarea>
      </div>
      <div style="margin-bottom:10px;">
        <label style="font-size:12px;color:#888;">世界规则（一行一条）</label>
        <textarea id="ws-rules" rows="3" style="width:100%;padding:6px;border:1px solid #ddd;border-radius:4px;">${escapeHtml((wc.rules || []).join('\n'))}</textarea>
      </div>
      <div style="margin-bottom:10px;">
        <label style="font-size:12px;color:#888;">关键地点（一行一个）</label>
        <textarea id="ws-locations" rows="2" style="width:100%;padding:6px;border:1px solid #ddd;border-radius:4px;">${escapeHtml((wc.key_locations || []).join('\n'))}</textarea>
      </div>
      <div style="margin-bottom:10px;">
        <label style="font-size:12px;color:#888;">当前局势</label>
        <textarea id="ws-situation" rows="2" style="width:100%;padding:6px;border:1px solid #ddd;border-radius:4px;">${escapeHtml(wc.current_situation || '')}</textarea>
      </div>
      <div style="margin-bottom:10px;">
        <label style="font-size:12px;color:#888;">主线目标（修改后会自动重新校准角色目标权重）</label>
        <textarea id="ws-main-objective" rows="2" style="width:100%;padding:6px;border:1px solid #ddd;border-radius:4px;">${escapeHtml(wc.main_objective || '')}</textarea>
      </div>
      <div style="font-size:11px;color:#999;">提示：设定修改影响后续章节生成，不会改写已有章节。</div>
    `;

    overlay.querySelector("#btn-save-world-settings").disabled = false;
    overlay.querySelector("#btn-save-world-settings").addEventListener("click", async (ev) => {
      const btn = ev.currentTarget;
      btn.disabled = true;
      btn.textContent = "保存中...";
      const updates = {
        name: document.getElementById("ws-name").value.trim(),
        genre: document.getElementById("ws-genre").value,
        era: document.getElementById("ws-era").value,
        tone: document.getElementById("ws-tone").value,
        perspective: document.getElementById("ws-perspective").value,
        description: document.getElementById("ws-desc").value,
        rules: document.getElementById("ws-rules").value.split("\n").map(s => s.trim()).filter(Boolean),
        key_locations: document.getElementById("ws-locations").value.split("\n").map(s => s.trim()).filter(Boolean),
        current_situation: document.getElementById("ws-situation").value,
        main_objective: document.getElementById("ws-main-objective").value,
      };
      try {
        const saveRes = await fetch("/api/world-config", {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(updates)
        });
        const saveData = await saveRes.json();
        if (saveData.status === "ok") {
          overlay.remove();
          showToast("世界设定已更新", "success");
          const titleEl = document.getElementById("game-title");
          if (titleEl && updates.name) titleEl.textContent = updates.name;
          // 持久化到存档（防止刷新后设定回退）
          fetch("/api/save", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ slot: "auto" })
          });
        } else {
          showToast("保存失败：" + (saveData.error || "未知错误"), "error");
          btn.disabled = false;
          btn.textContent = "保存";
        }
      } catch (e) {
        showToast("请求失败：" + e.message, "error");
        btn.disabled = false;
        btn.textContent = "保存";
      }
    });
  } catch (e) {
    overlay.querySelector("#world-settings-content").innerHTML = `<div style="color:#e74c3c;">加载失败：${escapeHtml(e.message)}</div>`;
  }
}

// 启动自检：/api/health —— 发现异常时向用户提示具体原因
function runHealthCheck() {
  fetch("/api/health")
    .then(r => r.json())
    .then(h => {
      if (!h || h.status === "ok") return;
      const problems = [];
      if (h.failed_modules && h.failed_modules.length) {
        problems.push("API 模块装载失败: " + h.failed_modules.map(m => m.module).join(", "));
      }
      if (h.ai && !h.ai.has_api_key) {
        problems.push("AI API Key 未配置（可在干预面板“模型切换”页签设置）");
      }
      if (h.data_dirs_writable) {
        Object.entries(h.data_dirs_writable).forEach(([dir, ok]) => {
          if (!ok) problems.push("数据目录 " + dir + "/ 缺失或不可写");
        });
      }
      if (problems.length && typeof showToast === "function") {
        showToast("启动自检异常：" + problems.join("；"), "warning");
      }
    })
    .catch(() => {});
}

// 页面加载时显示项目列表
document.addEventListener("DOMContentLoaded", () => {
  loadProjectsList();
  runHealthCheck();
});


// ── 导出 ──
function exportNovel() {
  const overlay = document.createElement("div");
  overlay.className = "modal-overlay";
  overlay.innerHTML = `
    <div class="modal-dialog" style="min-width:360px;">
      <h3>导出全文</h3>
      <p style="font-size:13px;color:var(--ink-light);margin:0 0 16px 0;">选择导出格式：</p>
      <div style="display:flex;flex-direction:column;gap:10px;">
        <button class="btn-primary" onclick="doExport('txt')" style="padding:12px;font-size:14px;text-align:left;">
          <b>TXT 纯文本</b><br><span style="font-size:11px;color:var(--ink-light);">通用格式，可直接粘贴到任何编辑器</span>
        </button>
        <button class="btn-primary" onclick="doExport('md')" style="padding:12px;font-size:14px;text-align:left;">
          <b>Markdown</b><br><span style="font-size:11px;color:var(--ink-light);">带标题层级和表格，适合 Typora/Obsidian</span>
        </button>
        <button class="btn-primary" onclick="doExport('html')" style="padding:12px;font-size:14px;text-align:left;">
          <b>HTML 网页</b><br><span style="font-size:11px;color:var(--ink-light);">带排版样式，可直接在浏览器阅读</span>
        </button>
      </div>
      <div class="modal-actions" style="margin-top:16px;">
        <button class="btn-cancel" onclick="this.closest('.modal-overlay').remove()">取消</button>
      </div>
    </div>
  `;
  document.body.appendChild(overlay);
}

async function doExport(format) {
  try {
    const res = await fetch("/api/export?format=" + format);
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      alert("导出失败：" + (err.error || "未知错误"));
      return;
    }
    const blob = await res.blob();
    // 从响应头提取文件名，支持 filename*=UTF-8''... 和 filename=... 两种格式
    let filename = "小说导出." + format;
    const cd = res.headers.get("Content-Disposition");
    if (cd) {
      // 优先匹配 filename*=UTF-8''... (RFC 5987)
      const mStar = cd.match(/filename\*=UTF-8''([^;]+)/i);
      if (mStar && mStar[1]) {
        filename = decodeURIComponent(mStar[1]);
      } else {
        // 兜底匹配 filename=...
        const m = cd.match(/filename=(['"]?)([^'";\n]*)\1/i);
        if (m && m[2]) filename = decodeURIComponent(m[2]);
      }
    }
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
    // 关闭弹窗
    const overlay = document.querySelector(".modal-overlay");
    if (overlay) overlay.remove();
  } catch (e) {
    alert("导出失败：" + e.message);
  }
}



async function showChapterHistory(index) {
  // First save current version
  await fetch(`/api/chapter/${index}/history`, { method: "POST" });
  
  const res = await fetch(`/api/chapter/${index}/history`);
  const data = await res.json();
  const versions = data.versions || [];
  
  if (versions.length === 0) {
    showToast("暂无历史版本", "error");
    return;
  }

  const overlay = document.createElement("div");
  overlay.className = "modal-overlay";
  overlay.innerHTML = `
    <div class="modal-dialog" style="min-width:500px;max-height:70vh;overflow-y:auto;">
      <h3>章节历史版本</h3>
      <div style="margin-bottom:12px;">
        ${versions.map((v, i) => `
          <div style="padding:8px 12px;margin-bottom:6px;background:#f5f5f5;border-radius:4px;display:flex;justify-content:space-between;align-items:center;">
            <div>
              <div style="font-weight:bold;font-size:13px;">版本 ${i + 1}</div>
              <div style="font-size:11px;color:#888;">${escapeHtml((v.narrative || '').substring(0, 50))}...</div>
            </div>
            <button onclick="rollbackChapter(${index}, ${i}, this)" style="padding:4px 10px;font-size:11px;border:1px solid #e67e22;border-radius:3px;background:#fff;color:#e67e22;cursor:pointer;">恢复</button>
          </div>
        `).join("")}
      </div>
      <div class="modal-actions">
        <button class="btn-cancel" onclick="this.closest('.modal-overlay').remove()">关闭</button>
      </div>
    </div>
  `;
  document.body.appendChild(overlay);
}

async function rollbackChapter(index, versionIdx, btn) {
  const res = await fetch(`/api/chapter/${index}/rollback`, { method: "POST" });
  const data = await res.json();
  if (data.status === "ok") {
    btn.closest(".modal-overlay").remove();
    refreshChapterList();
    const chRes = await fetch("/api/chapters");
    const chData = await chRes.json();
    if (chData.chapters[index]) displayChapter(chData.chapters[index]);
    showToast("已恢复到上一版本", "success");
  } else {
    showToast("回滚失败：" + data.error, "error");
  }
}

// ── 角色编辑 ──
async function editCharacter(name, event) {
  if (event) event.stopPropagation();
  try {
    const res = await fetch(`/api/character/${encodeURIComponent(name)}`);
    const data = await res.json();
    if (data.error) { showToast(data.error, "error"); return; }
    const ch = data.character;

    const overlay = document.createElement("div");
    overlay.className = "modal-overlay";
    overlay.innerHTML = `
      <div class="modal-dialog" style="min-width:500px;max-height:80vh;overflow-y:auto;">
        <h3>编辑角色：${escapeHtml(ch.name)}</h3>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:10px;">
          <div>
            <label style="font-size:12px;color:#888;">性别</label>
            <select id="edit-char-gender" style="width:100%;padding:6px;border:1px solid #ddd;border-radius:4px;">
              <option value="男"${ch.gender === '男' ? ' selected' : ''}>男</option>
              <option value="女"${ch.gender === '女' ? ' selected' : ''}>女</option>
            </select>
          </div>
          <div>
            <label style="font-size:12px;color:#888;">年龄</label>
            <input id="edit-char-age" type="number" value="${ch.age || 20}" style="width:100%;padding:6px;border:1px solid #ddd;border-radius:4px;">
          </div>
        </div>
        <div style="margin-bottom:10px;">
          <label style="font-size:12px;color:#888;">性格</label>
          <input id="edit-char-personality" type="text" value="${escapeHtml(ch.personality || '')}" style="width:100%;padding:6px;border:1px solid #ddd;border-radius:4px;">
        </div>
        <div style="margin-bottom:10px;">
          <label style="font-size:12px;color:#888;">背景</label>
          <textarea id="edit-char-background" rows="2" style="width:100%;padding:6px;border:1px solid #ddd;border-radius:4px;">${escapeHtml(ch.background || '')}</textarea>
        </div>
        <div style="margin-bottom:10px;">
          <label style="font-size:12px;color:#888;">能力（逗号分隔）</label>
          <input id="edit-char-abilities" type="text" value="${escapeHtml((ch.abilities || []).join('，'))}" style="width:100%;padding:6px;border:1px solid #ddd;border-radius:4px;">
        </div>
        <div style="margin-bottom:10px;">
          <label style="font-size:12px;color:#888;">弱点（逗号分隔）</label>
          <input id="edit-char-weaknesses" type="text" value="${escapeHtml((ch.weaknesses || []).join('，'))}" style="width:100%;padding:6px;border:1px solid #ddd;border-radius:4px;">
        </div>
        <div style="margin-bottom:10px;">
          <label style="font-size:12px;color:#888;">长期目标</label>
          <input id="edit-char-goal" type="text" value="${escapeHtml(ch.long_term_goal || '')}" style="width:100%;padding:6px;border:1px solid #ddd;border-radius:4px;">
        </div>
        <div style="margin-bottom:10px;">
          <label style="font-size:12px;color:#888;">当前心情</label>
          <input id="edit-char-mood" type="text" value="${escapeHtml(ch.current_mood || '')}" style="width:100%;padding:6px;border:1px solid #ddd;border-radius:4px;">
        </div>
        <div style="margin-bottom:10px;">
          <label style="font-size:12px;color:#888;">当前位置</label>
          <input id="edit-char-location" type="text" value="${escapeHtml(ch.current_location || '')}" style="width:100%;padding:6px;border:1px solid #ddd;border-radius:4px;">
        </div>
        <div class="modal-actions">
          <button class="btn-cancel" onclick="this.closest('.modal-overlay').remove()">取消</button>
          <button class="btn-confirm" id="btn-save-char-edit">保存</button>
        </div>
      </div>
    `;
    document.body.appendChild(overlay);

    overlay.querySelector("#btn-save-char-edit").addEventListener("click", async () => {
      const updates = {
        gender: document.getElementById("edit-char-gender").value,
        age: parseInt(document.getElementById("edit-char-age").value) || 20,
        personality: document.getElementById("edit-char-personality").value,
        background: document.getElementById("edit-char-background").value,
        abilities: document.getElementById("edit-char-abilities").value.split(/[,，]/).map(s => s.trim()).filter(Boolean),
        weaknesses: document.getElementById("edit-char-weaknesses").value.split(/[,，]/).map(s => s.trim()).filter(Boolean),
        long_term_goal: document.getElementById("edit-char-goal").value,
        current_mood: document.getElementById("edit-char-mood").value,
        current_location: document.getElementById("edit-char-location").value,
      };
      const saveRes = await fetch(`/api/character/${encodeURIComponent(name)}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(updates)
      });
      const saveData = await saveRes.json();
      if (saveData.status === "ok") {
        overlay.remove();
        showToast(`角色 ${name} 已更新`, "success");
        refreshState(null);
        // 持久化保存到存档（防止刷新后角色数据回退）
        fetch("/api/save", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ slot: "auto" })
        });
      } else {
        showToast("保存失败：" + saveData.error, "error");
      }
    });
  } catch (e) {
    showToast("请求失败：" + e.message, "error");
  }
}

