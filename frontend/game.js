/* game.js - 游戏核心：初始化、状态刷新、章节生成/显示/列表/编辑/删除、存档、角色添加、情节引导 */

// ── 确认页 ──
function updateReview() {
  const chars = collectCharacters();
  const rules = document.getElementById("world-rules").value.split("\n").filter(Boolean);
  const locations = document.getElementById("world-locations").value.split("\n").filter(Boolean);

  let html = '<div class="review-section">';
  html += '<h3>世界设定</h3>';
  html += `<p>名称：${val("world-name")} | 类型：${val("world-genre")} | 时代：${val("world-era")}</p>`;
  html += `<p>描述：${val("world-desc")}</p>`;
  html += `<p>基调：${val("world-tone")} | 地点：${locations.join("、") || "未设置"}</p>`;
  html += `<p>规则：${rules.join("；") || "未设置"}</p>`;
  html += '</div>';

  html += '<div class="review-section">';
  html += `<h3>角色列表（${chars.length}人）</h3>`;
  chars.forEach(c => {
    html += `<p><strong>${c.name}</strong>（${c.gender}，${c.age}岁）—— ${c.long_term_goal || "无长期目标"}</p>`;
  });
  html += '</div>';

  document.getElementById("review-content").innerHTML = html;
}

// ── 初始化游戏 ──
async function initGame() {
  const chars = collectCharacters();
  if (!chars.length) { alert("请至少添加一个角色"); return; }
  if (!chars.every(c => c.name)) { alert("请为所有角色填写姓名"); return; }

  const rules = document.getElementById("world-rules").value.split("\n").map(s => s.trim()).filter(Boolean);
  const locations = document.getElementById("world-locations").value.split("\n").map(s => s.trim()).filter(Boolean);

  // 读取引擎配置
  const totalChapters = parseInt(document.getElementById("config-total-chapters")?.value) || 20;
  const ticksPerChapter = parseInt(document.getElementById("config-ticks")?.value) || 20;
  const perspective = document.getElementById("config-perspective")?.value || "third";

  const payload = {
    world: {
      name: val("world-name"),
      genre: val("world-genre"),
      era: val("world-era"),
      description: val("world-desc"),
      rules: rules,
      key_locations: locations,
      current_situation: val("world-situation"),
      tone: val("world-tone"),
      perspective: perspective,
      main_objective: val("world-main-objective"),
    },
    characters: chars,
    engine_config: {
      total_chapters: totalChapters,
      ticks_per_chapter: ticksPerChapter,
    }
  };

  try {
    const res = await fetch("/api/init", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    const data = await res.json();
    if (data.status === "ok") {
      showGamePage();
      refreshState(data.state);
      // 新建项目自动保存（统一用 auto 槽位）
      fetch("/api/save", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ slot: "auto" })
      });
    } else {
      alert("初始化失败：" + JSON.stringify(data));
    }
  } catch (e) {
    alert("连接服务器失败：" + e.message);
  }
}

// ── 页面切换 ──
function showGamePage() {
  document.getElementById("projects-page").classList.remove("active");
  document.getElementById("setup-page").classList.remove("active");
  document.getElementById("timeline-page").classList.remove("active");
  document.getElementById("game-page").classList.add("active");
  document.getElementById("game-title").textContent = val("world-name") || "小说世界";
}

// ── 状态刷新 ──
async function refreshState(state) {
  if (!state) {
    const res = await fetch("/api/state");
    const data = await res.json();
    if (data.status !== "ok") return;
    state = data.state;
  }

  document.getElementById("game-chapter").textContent = `第 ${state.world.chapter} 章`;

  // 刷新情节引导的角色下拉
  if (state.characters) {
    const sel = document.getElementById("guide-goal-char");
    if (sel) {
      const curVal = sel.value;
      sel.innerHTML = '<option value="">角色</option>';
      state.characters.forEach(c => {
        const opt = document.createElement("option");
        opt.value = c.name;
        opt.textContent = c.name;
        sel.appendChild(opt);
      });
      if (curVal) sel.value = curVal;
    }
  }

  // 角色状态
  let charHtml = "";
  state.characters.forEach(c => {
    charHtml += `<div class="char-status-card" style="position:relative;">
      <button onclick="editCharacter('${escapeHtml(c.name)}')" style="position:absolute;top:6px;right:6px;padding:2px 6px;font-size:10px;border:1px solid #ccc;border-radius:3px;background:#fff;cursor:pointer;" title="编辑">✎</button>
      <div class="char-name">${escapeHtml(c.name)} · ${escapeHtml(c.location || "位置未知")}</div>
      <div class="char-detail">
        心情：${escapeHtml(c.mood)}<br>
        长期目标：${escapeHtml(c.long_term_goal || "无")}<br>
        短期目标：${c.active_short_goals.length ? escapeHtml(c.active_short_goals.join("；")) : "暂无"}
      </div>
    </div>`;
  });
  document.getElementById("character-status").innerHTML = charHtml || '<p class="placeholder">暂无角色</p>';
}

// ── 生成下一章 ──
async function nextChapter() {
  const btn = document.getElementById("btn-next-chapter");
  btn.disabled = true;
  btn.textContent = "天道推演中……";

  const title = document.getElementById("chapter-title").value.trim();
  const content = document.getElementById("chapter-content");
  const startTime = Date.now();
  content.innerHTML = '<div class="loading">天道正在编织命运</div><div id="chapter-elapsed" style="text-align:center;color:#888;font-size:13px;margin-top:8px;">已用时：0秒</div>';
  const timerEl = setInterval(() => {
    const el = document.getElementById("chapter-elapsed");
    if (!el) { clearInterval(timerEl); return; }
    const s = Math.floor((Date.now() - startTime) / 1000);
    el.textContent = `已用时：${s}秒（通常需60-90秒）`;
  }, 1000);

  try {
    const res = await busyFetch("/api/chapter", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title })
    }, "天道推演中（AI 生成本章正文）");
    const data = await res.json();
    if (data.status === "ok") {
      clearInterval(timerEl);
      displayChapter(data.chapter);
      // 连线框状态同步：推演完成后自动更新画布 + 跑一致性检测
      if (typeof WireframeCanvas !== 'undefined') {
        try { WireframeCanvas.syncFromEngine(); } catch(e) {}
        try { WireframeCanvas.runGlobalCheck(); } catch(e) {}
      }
      refreshState(null);
      refreshChapterList();
      // 章节后自动保存
      fetch("/api/save", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ slot: "auto" })
      });
    } else {
      clearInterval(timerEl);
      content.innerHTML = `<p style="color:red">生成失败：${data.error}</p>`;
    }
  } catch (e) {
    clearInterval(timerEl);
    if (e.name === "AbortError") {
      content.innerHTML = '<p style="color:#e67e22">已中止等待（后端任务可能仍在继续，稍后可刷新章节列表查看）</p>';
    } else {
      content.innerHTML = `<p style="color:red">连接失败：${e.message}</p>`;
    }
  } finally {
    btn.disabled = false;
    btn.textContent = "天道推演下一章";
    document.getElementById("chapter-title").value = "";
  }
}

// ── 显示章节 ──
// knownIndex：章节在后端数组中的真实索引。不传时按章节号反查。
// 注意：不能用 chapter.chapter - 1 当索引——章节号可能不连续（删过章会跳号），
// 会导致按钮请求打到不存在的索引上报“章节不存在”
async function displayChapter(chapter, knownIndex = null) {
  let idx = knownIndex;
  if (idx === null || idx === undefined) {
    try {
      const res = await fetch("/api/chapters");
      const data = await res.json();
      idx = (data.chapters || []).findIndex(c => c.chapter === chapter.chapter);
    } catch (e) {
      idx = -1;
    }
    if (idx < 0) idx = chapter.chapter - 1;
  }
  let html = `<h2>${chapter.title || `第${chapter.chapter}章`}</h2>`;

  if (chapter.world_event) {
    html += `<p style="color:var(--accent);font-weight:700;margin:10px 0">【世界事件】${chapter.world_event}</p>`;
  }

  html += `<div>${chapter.narrative || "（无内容）"}</div>`;

  // AI味检测面板
  if (chapter.ai_flavor) {
    const af = chapter.ai_flavor;
    const scoreColor = af.after_score <= 15 ? 'var(--success, #27ae60)' 
                      : af.after_score <= 35 ? 'var(--warning, #e67e22)' 
                      : 'var(--danger, #e74c3c)';
    const probColor = af.ai_probability < 20 ? 'var(--success, #27ae60)'
                     : af.ai_probability < 40 ? 'var(--warning, #e67e22)'
                     : 'var(--danger, #e74c3c)';
    const stats = af.stats || {};
    html += `<div style="margin-top:16px;padding:12px 16px;background:var(--bg-alt,rgba(0,0,0,0.03));border-radius:8px;border:1px solid var(--border);font-size:13px;">`;
    html += `<div style="display:flex;gap:16px;flex-wrap:wrap;align-items:center;margin-bottom:8px;">`;
    html += `<strong style="color:var(--ink);">AI味检测</strong>`;
    html += `<span style="color:${scoreColor};font-weight:700;">评分 ${af.before_score}→${af.after_score}/100 (${af.after_level})</span>`;
    html += `<span style="color:${probColor};font-weight:700;">AI概率 ${af.ai_probability}%</span>`;
    // 去AI味按钮
    html += `<button id="btn-rule-clean-${idx}" class="btn-deai btn-deai-rule" onclick="reDeAiChapter(${idx})"><span class="deai-spinner"></span>规则清洗</button>`;
    html += `<button id="btn-deep-deai-${idx}" class="btn-deai btn-deai-deep" onclick="localFixChapter(${idx})"><span class="deai-spinner"></span>深度去AI味</button>`;
    html += `<button id="btn-humanize-${idx}" class="btn-deai btn-deai-human" onclick="humanizeChapter(${idx})"><span class="deai-spinner"></span>去AI味(书斋同款)</button>`;
    html += `</div>`;
    // 关键统计
    if (stats.burstiness_cv !== undefined) {
      html += `<div style="display:flex;gap:12px;flex-wrap:wrap;color:var(--ink-light);font-size:12px;">`;
      html += `<span>句长变异: ${stats.burstiness_cv}</span>`;
      html += `<span>词汇多样性: ${stats.ttr}</span>`;
      html += `<span>段落均匀度: ${stats.para_cv}</span>`;
      html += `<span>"的"字密度: ${stats.de_density}/千字</span>`;
      html += `<span>连接词密度: ${stats.connector_density}/千字</span>`;
      html += `</div>`;
    }
    html += `</div>`;
  }

  if (chapter.collisions && chapter.collisions.length) {
    html += `<div style="margin-top:20px;padding-top:16px;border-top:1px solid var(--border);font-size:13px;color:var(--ink-light)">`;
    html += "<strong>本章碰撞：</strong>";
    chapter.collisions.forEach(col => {
      html += `<div style="margin:4px 0">${col.characters.join(" vs ")}`;
      if (col.goal_changes.length) {
        html += ` — ${col.goal_changes.join("；")}`;
      }
      html += "</div>";
    });
    html += "</div>";
  }

  document.getElementById("chapter-content").innerHTML = html;
  document.getElementById("game-chapter").textContent = `第 ${chapter.chapter} 章`;
}

// ── 内容兜底校验：自动检测并清理重复段落 ──
// 使用段落全文做指纹，精确检测完全相同的重复段落
function validateAndCleanContent(content) {
  if (!content || content.length < 100) return { cleaned: false, content, removedCount: 0 };

  // 按 \n\n 分段，兼容单 \n 的情况
  let paragraphs = content.split('\n\n');
  if (paragraphs.length < 3) {
    paragraphs = content.split('\n');
  }
  if (paragraphs.length < 3) return { cleaned: false, content, removedCount: 0 };

  const cleaned = [];
  const seenTexts = new Set();
  let removedCount = 0;

  for (const p of paragraphs) {
    const trimmed = p.trim();
    // 只对超过30字的段落做重复检测，避免误杀短对话
    if (trimmed.length > 30) {
      // 用全文做指纹：去除多余空白后整段对比
      const normalized = trimmed.replace(/\s+/g, ' ');
      if (seenTexts.has(normalized)) {
        removedCount++;
        console.log('[内容校验] 检测到重复段落:', normalized.substring(0, 40) + '...');
        continue; // 跳过重复段落
      }
      seenTexts.add(normalized);
    }
    cleaned.push(p);
  }

  if (removedCount > 0) {
    // 保持原有分隔格式
    const separator = content.includes('\n\n') ? '\n\n' : '\n';
    return {
      cleaned: true,
      content: cleaned.join(separator),
      removedCount,
    };
  }

  return { cleaned: false, content, removedCount: 0 };
}

// ── 保存章节正文到后端 ──
async function saveChapterContent(index, narrative) {
  try {
    const res = await fetch(`/api/chapter/${index}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ narrative }),
    });
    const data = await res.json();
    return data.status === "ok";
  } catch (e) {
    console.error('[保存章节内容] 失败:', e);
    return false;
  }
}

// ── 规则清洗（快速，不消耗Token） ──
// _deAiProcessing 用于防止去AI味操作并发请求
let _deAiProcessing = false;

async function reDeAiChapter(index) {
  // 防止与深度去AI味并发
  if (_deAiProcessing) {
    showToast("正在处理中，请等待完成...", "info");
    return;
  }

  const btn = document.getElementById(`btn-rule-clean-${index}`);
  const deepBtn = document.getElementById(`btn-deep-deai-${index}`);

  if (!confirm(`对该章节执行规则清洗？\n（削「的」字密度、去连接词、替换AI高频词，不消耗Token，速度快）`)) return;

  // 锁定状态
  _deAiProcessing = true;
  if (btn) {
    btn.classList.add('processing');
    const spinner = btn.querySelector('.deai-spinner');
    btn.textContent = '清洗中…';
    if (spinner) btn.insertBefore(spinner, btn.firstChild);
  }
  if (deepBtn) {
    deepBtn.classList.add('processing');
  }

  try {
    const res = await fetch(`/api/post-process/chapter/${index}`, { method: "POST" });
    const data = await res.json();
    if (data.status === "ok") {
      // 重新加载该章节
      const chRes = await fetch("/api/chapters");
      const chData = await chRes.json();
      if (chData.chapters[index]) {
        const chapter = chData.chapters[index];

        // ── 兜底校验：自动检测并清理重复段落 ──
        const validation = validateAndCleanContent(chapter.narrative || '');
        if (validation.cleaned && validation.removedCount > 0) {
          const saved = await saveChapterContent(index, validation.content);
          if (saved) {
            chapter.narrative = validation.content;
            showToast(`已自动清理${validation.removedCount}处重复段落`, "success");
          }
        }

        // ── 字数变化保护 ──
        if (data.original_length && data.cleaned_length) {
          const changeRatio = Math.abs(data.cleaned_length - data.original_length) / data.original_length;
          if (changeRatio > 0.5) {
            showToast(`⚠️ 修复后字数变化${Math.round(changeRatio * 100)}%（${data.original_length}→${data.cleaned_length}），请检查内容`, "warning");
          }
        }

        displayChapter(chapter, index);

        // 持久化保存到存档（防止刷新后内容回退）
        fetch("/api/save", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ slot: "auto" })
        });
      }
      const af = data.ai_flavor;
      const msg = `去AI味完成：评分 ${af.before_score}→${af.after_score}/100，AI概率 ${af.ai_probability}%`;
      showToast(msg, af.after_score <= 15 ? "success" : "warning");
    } else {
      showToast("去AI味失败：" + (data.error || "未知错误"), "error");
    }
  } catch (e) {
    showToast("连接失败：" + e.message, "error");
  } finally {
    _deAiProcessing = false;
    if (btn && btn.classList.contains('processing')) {
      btn.classList.remove('processing');
      const spinner = btn.querySelector('.deai-spinner');
      btn.textContent = '规则清洗';
      if (spinner) btn.insertBefore(spinner, btn.firstChild);
    }
    if (deepBtn && deepBtn.classList.contains('processing')) {
      deepBtn.classList.remove('processing');
    }
  }
}

// ── 深度去AI味（规则清洗 + 多轮AI局部修复） ──

async function localFixChapter(index) {
  // 防止并发点击
  if (_deAiProcessing) {
    showToast("正在处理中，请等待完成...", "info");
    return;
  }

  const btn = document.getElementById(`btn-deep-deai-${index}`);
  const ruleBtn = document.getElementById(`btn-rule-clean-${index}`);

  // 检查当前评分，决定是否需要 force
  let needForce = false;
  let forceHint = "";
  try {
    const chRes = await fetch("/api/chapters");
    const chData = await chRes.json();
    if (chData.chapters[index] && chData.chapters[index].ai_flavor) {
      const af = chData.chapters[index].ai_flavor;
      if (af.after_score <= 20 && af.ai_probability <= 25) {
        needForce = true;
        forceHint = `\n\n当前评分 ${af.after_score}/100 已达标（≤20）。\n点击"确定"将强制重新检测和修复，点击"取消"则保持现状。`;
      }
    }
  } catch (e) { /* 忽略预检失败 */ }

  if (!confirm(
    `深度去AI味将执行以下操作：\n\n` +
    `1. 规则清洗：削「的」字密度、去连接词、替换AI高频词（不消耗Token）\n` +
    `2. 多轮AI修复：最多5轮，每轮修复8个问题段落\n` +
    `3. 第3轮起启用激进模式（大幅重写措辞和句式）\n` +
    `4. 修复后自动清除黑名单词汇\n\n` +
    `整个过程可能需要2-5分钟，请耐心等待。${forceHint}`
  )) return;

  // 锁定状态：添加 processing 类（显示 spinner + 灰化）
  _deAiProcessing = true;
  if (btn) {
    btn.classList.add('processing');
    // 保留 spinner span，替换文本节点
    const spinner = btn.querySelector('.deai-spinner');
    btn.textContent = '深度修复中…';
    if (spinner) btn.insertBefore(spinner, btn.firstChild);
  }
  if (ruleBtn) {
    ruleBtn.classList.add('processing');
  }

  try {
    showToast("正在执行深度去AI味（规则清洗+多轮AI修复），请耐心等待2-5分钟...", "info");
    const res = await fetch(`/api/post-process/local-fix/${index}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        max_fixes: 8,
        multi_round: true,
        max_rounds: 5,
        force_continue: true,
        apply_rules: true,
        force: needForce,  // 达标时强制重新处理
      }),
    });
    const data = await res.json();
    if (data.status === "ok") {
      const report = data.fix_report || {};
      const rounds = report.rounds || 1;
      const fixed = report.total_fixed || report.fixed || 0;
      const ruleCleaned = report.rule_cleaned ? "规则清洗✓ " : "";
      const skippedReason = data.skipped_reason || report.skipped_reason || "";

      // 根据结果构建不同消息
      if (!data.content_changed) {
        // 内容未变化 — 根据原因给出明确提示
        if (skippedReason === 'already_at_target') {
          showToast(
            `当前AI味已达标（评分${data.after_score}/100，概率${data.after_probability}%），无需再次处理。\n` +
            `如需强制重新修复，请再点击一次并在确认框中选择"确定"。`,
            "success"
          );
        } else if (skippedReason === 'no_issues_found') {
          showToast("未检测到AI味问题，内容质量良好。", "success");
        } else if (skippedReason === 'no_improvement') {
          showToast(
            `本轮修复未产生变化。\n` +
            `评分 ${data.before_score}→${data.after_score}/100，AI概率 ${data.before_probability}%→${data.after_probability}%。\n` +
            `可能原因：剩余问题段落无法定位或长度异常。建议手动编辑。`,
            "warning"
          );
        } else {
          showToast(`深度去AI味完成，但内容未变化。评分 ${data.after_score}/100`, "info");
        }
      } else {
        // 内容已变化 — 展示修复结果
        let detailMsg = `${ruleCleaned}${rounds}轮修复${fixed}处\n`;
        detailMsg += `评分 ${data.before_score}→${data.after_score}/100，`;
        detailMsg += `AI概率 ${data.before_probability}%→${data.after_probability}%`;

        if (report.round_reports && report.round_reports.length > 0) {
          detailMsg += "\n\n各轮详情：";
          report.round_reports.forEach(r => {
            const mode = r.aggressive ? " [激进]" : "";
            const rFixed = r.fix_report?.fixed || 0;
            detailMsg += `\n第${r.round}轮: 修复${rFixed}处${mode}`;
          });
        }

        const success = data.after_score <= 20 && data.after_probability <= 25;
        const improved = data.after_score < data.before_score;

        if (success) {
          showToast(detailMsg, "success");
        } else if (improved) {
          showToast(detailMsg + "\n\n已改善但仍未达标，可再次点击继续修复", "warning");
        } else {
          showToast(detailMsg + "\n\n改善有限，建议手动编辑或尝试重新生成", "warning");
        }
      }

      // 重新加载该章节
      const chRes = await fetch("/api/chapters");
      const chData = await chRes.json();
      if (chData.chapters[index]) {
        const chapter = chData.chapters[index];

        // ── 兜底校验：自动检测并清理重复段落 ──
        const validation = validateAndCleanContent(chapter.narrative || '');
        if (validation.cleaned && validation.removedCount > 0) {
          const saved = await saveChapterContent(index, validation.content);
          if (saved) {
            chapter.narrative = validation.content;
            showToast(`已自动清理${validation.removedCount}处重复段落`, "success");
          }
        }

        // ── 字数变化保护 ──
        if (data.original_length && data.fixed_length) {
          const changeRatio = Math.abs(data.fixed_length - data.original_length) / data.original_length;
          if (changeRatio > 0.5) {
            showToast(`⚠️ 修复后字数变化${Math.round(changeRatio * 100)}%（${data.original_length}→${data.fixed_length}），请检查内容`, "warning");
          }
        }

        displayChapter(chapter, index);

        // 持久化保存到存档（防止刷新后内容回退）
        fetch("/api/save", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ slot: "auto" })
        });
      }
    } else {
      showToast("深度去AI味失败：" + (data.error || "未知错误"), "error");
    }
  } catch (e) {
    showToast("连接失败：" + e.message, "error");
  } finally {
    // 解锁状态
    _deAiProcessing = false;
    // 按钮状态会在 displayChapter 重新渲染时自动恢复
    // 但如果没有重新渲染（如出错时），手动恢复
    if (btn && btn.classList.contains('processing')) {
      btn.classList.remove('processing');
      const spinner = btn.querySelector('.deai-spinner');
      btn.textContent = '深度去AI味';
      if (spinner) btn.insertBefore(spinner, btn.firstChild);
    }
    if (ruleBtn && ruleBtn.classList.contains('processing')) {
      ruleBtn.classList.remove('processing');
    }
  }
}

// ── 去AI味（移植自书斋V66“去AI味”，全文粗粝重写 temp=1.3，可反复执行）──

async function humanizeChapter(index) {
  if (_deAiProcessing) {
    showToast("正在处理中，请等待完成...", "info");
    return;
  }

  const btn = document.getElementById(`btn-humanize-${index}`);

  if (!confirm(
    `去AI味（书斋同款）：\n\n` +
    `原理：用完全不同的语言重新讲同一个故事（temp 1.3，可打乱段落顺序）。\n` +
    `书斋实测：反复执行可将外部 AIGC 检测降到 4~5%。\n` +
    `用法：点一次 → 外部检测 → 不够低就再点一次，直到满意。\n\n` +
    `注意：改写幅度大，建议先保存当前版本。继续吗？`
  )) return;

  _deAiProcessing = true;
  if (btn) btn.classList.add('processing');

  try {
    showToast("正在去AI味重写全文（书斋同款），请耐心等待1-3分钟...", "info");
    const res = await busyFetch(`/api/post-process/humanize/${index}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({})
    }, "去AI味重写中");
    const data = await res.json();
    if (data.status === "ok" && data.content_changed) {
      const r = data.report || {};
      showToast(`去AI味完成（${r.original_length}→${r.new_length}字）。去外部检测器复验，不够低就再点一次`, "success");
      await loadChapter(index);
      fetch("/api/save", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ slot: "auto" })
      });
    } else if (data.status === "noop") {
      showToast("去AI味未生效：" + ((data.report || {}).reason || "结果异常已回退"), "warning");
    } else {
      showToast("去AI味失败：" + (data.error || "未知错误"), "error");
    }
  } catch (e) {
    if (e.name === "AbortError") {
      showToast("已中止等待（后端重写可能仍在继续，稍后刷新章节查看）", "warning");
    } else {
      showToast("连接失败：" + e.message, "error");
    }
  } finally {
    _deAiProcessing = false;
    if (btn && btn.classList.contains('processing')) {
      btn.classList.remove('processing');
    }
  }
}

// ── 章节列表 ──
async function refreshChapterList() {
  const res = await fetch("/api/chapters");
  const data = await res.json();
  const list = document.getElementById("chapter-list");

  if (!data.chapters.length) {
    list.innerHTML = '<p style="color:var(--ink-light);font-size:13px">暂无章节</p>';
    return;
  }

  list.innerHTML = data.chapters.map((ch, i) => `
    <div class="chapter-item${i === data.chapters.length - 1 ? ' active' : ''}"
         onclick="loadChapter(${i})">
      <span>第${ch.chapter}章 ${escapeHtml(ch.title || '')}</span>
      <span class="chapter-item-actions" style="float:right;display:none;gap:4px;">
        <button onclick="editChapter(${i}, event)" style="padding:2px 6px;font-size:11px;border:1px solid #ccc;border-radius:3px;background:#fff;cursor:pointer;" title="编辑">✎</button>
        <button onclick="deleteChapter(${i}, event)" style="padding:2px 6px;font-size:11px;border:1px solid #e74c3c;border-radius:3px;background:#fff;color:#e74c3c;cursor:pointer;" title="删除">✕</button>
      </span>
    </div>
  `).join("\n");
  // Show actions on hover
  list.querySelectorAll(".chapter-item").forEach(item => {
    const actions = item.querySelector(".chapter-item-actions");
    if (actions) {
      item.addEventListener("mouseenter", () => actions.style.display = "flex");
      item.addEventListener("mouseleave", () => actions.style.display = "none");
    }
  });

  // 更新世界事件
  if (data.chapters.length) {
    const last = data.chapters[data.chapters.length - 1];
    if (last.world_event) {
      const eventsDiv = document.getElementById("world-events");
      const eventHtml = data.chapters
        .filter(ch => ch.world_event)
        .map(ch => `<div class="event-item">第${ch.chapter}章：${ch.world_event}</div>`)
        .join("");
      eventsDiv.innerHTML = eventHtml || '<p style="color:var(--ink-light);font-size:13px">暂无世界事件</p>';
    }
  }
}

function loadChapter(index) {
  fetch("/api/chapters")
    .then(r => r.json())
    .then(data => {
      if (data.chapters[index]) {
        displayChapter(data.chapters[index], index);
        document.querySelectorAll(".chapter-item").forEach((el, i) => {
          el.classList.toggle("active", i === index);
        });
      }
    });
}

// ── 存档 ──
async function saveGame() {
  // 获取现有存档列表
  const savesRes = await fetch("/api/saves");
  const savesData = await savesRes.json();
  const existingSlots = (savesData.saves || []).map(s => s.slot);

  // 弹出存档管理对话框
  const overlay = document.createElement("div");
  overlay.className = "modal-overlay";
  overlay.innerHTML = `
    <div class="modal-dialog" style="min-width:380px;">
      <h3>保存游戏</h3>
      <div style="margin-bottom:12px;">
        <input id="save-slot-input" type="text" placeholder="存档名称" value="save_${new Date().getTime()}" style="width:100%;padding:8px;border:1px solid #ddd;border-radius:6px;font-size:14px;">
      </div>
      ${existingSlots.length > 0 ? `
        <div style="margin-bottom:12px;font-size:12px;color:#888;">已有存档（点击覆盖）：</div>
        <div style="max-height:150px;overflow-y:auto;">
          ${existingSlots.map(s => `<div class="save-slot-item" onclick="document.getElementById('save-slot-input').value='${s}'" style="padding:6px 10px;margin-bottom:4px;background:#f5f5f5;border-radius:4px;cursor:pointer;font-size:13px;">${s}</div>`).join("")}
        </div>
      ` : '<div style="font-size:12px;color:#888;margin-bottom:12px;">暂无存档</div>'}
      <div class="modal-actions">
        <button class="btn-cancel" onclick="this.closest('.modal-overlay').remove()">取消</button>
        <button class="btn-confirm" id="btn-confirm-save">保存</button>
      </div>
    </div>
  `;
  document.body.appendChild(overlay);

  overlay.querySelector("#btn-confirm-save").addEventListener("click", async () => {
    const slot = document.getElementById("save-slot-input").value.trim() || "auto";
    const res = await fetch("/api/save", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ slot })
    });
    const data = await res.json();
    overlay.remove();
    if (data.status === "ok") {
      showToast(`已保存到「${slot}」`, "success");
    } else {
      showToast("保存失败：" + data.error, "error");
    }
  });
}

async function loadGame() {
  const res = await fetch("/api/saves");
  const data = await res.json();
  if (!data.saves.length) {
    showToast("没有存档", "error");
    return;
  }

  const overlay = document.createElement("div");
  overlay.className = "modal-overlay";
  overlay.innerHTML = `
    <div class="modal-dialog" style="min-width:420px;">
      <h3>加载存档</h3>
      <div style="max-height:300px;overflow-y:auto;margin-bottom:16px;">
        ${data.saves.map(s => `
          <div class="save-slot-item" data-slot="${s.slot}" style="padding:10px 14px;margin-bottom:6px;background:#f5f5f5;border-radius:6px;cursor:pointer;border:2px solid transparent;transition:all 0.2s;">
            <div style="font-weight:bold;font-size:14px;">${s.slot}</div>
            <div style="font-size:12px;color:#888;">${s.world_name || "未命名"} · 第${s.chapter}章 · ${s.saved_at || ""}</div>
          </div>
        `).join("")}
      </div>
      <div class="modal-actions">
        <button class="btn-cancel" onclick="this.closest('.modal-overlay').remove()">取消</button>
      </div>
    </div>
  `;
  document.body.appendChild(overlay);

  overlay.querySelectorAll(".save-slot-item").forEach(item => {
    item.addEventListener("click", async () => {
      const slot = item.dataset.slot;
      overlay.remove();
      const loadRes = await fetch("/api/load/" + slot, { method: "POST" });
      const loadData = await loadRes.json();
      if (loadData.status === "ok") {
        showGamePage();
        refreshState(loadData.state);
        refreshChapterList();
        fetch("/api/chapters").then(r => r.json()).then(d => {
          if (d.chapters.length) displayChapter(d.chapters[d.chapters.length - 1], d.chapters.length - 1);
        });
        showToast(`已加载「${slot}」`, "success");
      } else {
        showToast("加载失败：" + loadData.error, "error");
      }
    });
  });
}

// ── 章节删除 ──
async function deleteChapter(index, event) {
  event.stopPropagation();
  if (!confirm(`确定删除第${index + 1}章吗？`)) return;
  const res = await fetch(`/api/chapter/${index}`, { method: "DELETE" });
  const data = await res.json();
  if (data.status === "ok") {
    refreshChapterList();
    showToast("章节已删除", "success");
    // 如果还有章节，显示最后一章
    const chaptersRes = await fetch("/api/chapters");
    const chaptersData = await chaptersRes.json();
    if (chaptersData.chapters.length > 0) {
      displayChapter(chaptersData.chapters[chaptersData.chapters.length - 1], chaptersData.chapters.length - 1);
    } else {
      document.getElementById("chapter-content").innerHTML = '<p class="placeholder">所有章节已删除</p>';
    }
    // 持久化保存到存档（防止刷新后恢复已删除章节）
    fetch("/api/save", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ slot: "auto" })
    });
  } else {
    showToast("删除失败：" + data.error, "error");
  }
}

// ── 章节编辑 ──
let _editingChapterIndex = null;

function editChapter(index, event) {
  event.stopPropagation();
  _editingChapterIndex = index;
  fetch("/api/chapters").then(r => r.json()).then(data => {
    const ch = data.chapters[index];
    if (!ch) return;
    const overlay = document.createElement("div");
    overlay.className = "modal-overlay";
    overlay.innerHTML = `
      <div class="modal-dialog" style="min-width:600px;max-width:80vw;max-height:80vh;overflow-y:auto;">
        <h3>编辑第${ch.chapter}章</h3>
        <div style="margin-bottom:10px;">
          <label style="font-size:12px;color:#888;">标题</label>
          <input id="edit-ch-title" type="text" value="${escapeHtml(ch.title || '')}" style="width:100%;padding:8px;border:1px solid #ddd;border-radius:4px;font-size:14px;">
        </div>
        <div style="margin-bottom:10px;">
          <label style="font-size:12px;color:#888;">正文</label>
          <textarea id="edit-ch-narrative" rows="15" style="width:100%;padding:8px;border:1px solid #ddd;border-radius:4px;font-size:14px;line-height:1.8;resize:vertical;">${escapeHtml(ch.narrative || '')}</textarea>
        </div>
        <div class="modal-actions">
          <button class="btn-cancel" onclick="this.closest('.modal-overlay').remove()">取消</button>
          <button class="btn-secondary" onclick="showChapterHistory(${index})" style="padding:6px 12px;font-size:12px;">历史版本</button>
          <button class="btn-confirm" id="btn-save-chapter-edit">保存</button>
        </div>
      </div>
    `;
    document.body.appendChild(overlay);
    overlay.querySelector("#btn-save-chapter-edit").addEventListener("click", async () => {
      await fetch(`/api/chapter/${index}/history`, { method: "POST" });
      const newTitle = document.getElementById("edit-ch-title").value;
      const newNarrative = document.getElementById("edit-ch-narrative").value;
      const res = await fetch(`/api/chapter/${index}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title: newTitle, narrative: newNarrative })
      });
      const saveData = await res.json();
      if (saveData.status === "ok") {
        overlay.remove();
        refreshChapterList();
        // 重新显示编辑后的章节
        const chRes = await fetch("/api/chapters");
        const chData = await chRes.json();
        if (chData.chapters[index]) displayChapter(chData.chapters[index], index);
        showToast("章节已保存", "success");
        // 持久化保存到存档（防止刷新后内容回退）
        fetch("/api/save", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ slot: "auto" })
        });
      } else {
        showToast("保存失败：" + saveData.error, "error");
      }
    });
  });
}

// ── 添加角色（运行时） ──

function toggleAddCharForm() {
  const form = document.getElementById("add-char-form");
  form.style.display = form.style.display === "none" ? "block" : "none";
  document.getElementById("add-char-msg").style.display = "none";
}

function submitAddChar() {
  const name = document.getElementById("new-char-name").value.trim();
  if (!name) { alert("请填写角色名"); return; }
  const personality = document.getElementById("new-char-personality").value.trim();
  const data = {
    name: name,
    age: parseInt(document.getElementById("new-char-age").value) || 20,
    gender: document.getElementById("new-char-gender").value,
    personality: personality,
    personality_list: personality ? personality.split(/[，,、]/).map(s => s.trim()).filter(Boolean) : [],
    long_term_goal: document.getElementById("new-char-goal").value.trim(),
    initial_location: document.getElementById("new-char-location").value.trim(),
    background: document.getElementById("new-char-bg").value.trim(),
    short_term_goals: document.getElementById("new-char-goal").value.trim() ? [document.getElementById("new-char-goal").value.trim()] : [],
  };
  const msgEl = document.getElementById("add-char-msg");
  fetch("/api/add-character", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data)
  }).then(r => r.json()).then(d => {
    if (d.status === "ok") {
      msgEl.textContent = d.message;
      msgEl.style.color = "#4caf50";
      msgEl.style.display = "block";
      // 清空表单
      document.getElementById("new-char-name").value = "";
      document.getElementById("new-char-personality").value = "";
      document.getElementById("new-char-goal").value = "";
      document.getElementById("new-char-location").value = "";
      document.getElementById("new-char-bg").value = "";
      // 刷新状态
      refreshState(null);
      // 持久化保存到存档（防止刷新后角色丢失）
      fetch("/api/save", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ slot: "auto" })
      });
      setTimeout(() => { toggleAddCharForm(); }, 1500);
    } else {
      msgEl.textContent = d.error || "添加失败";
      msgEl.style.color = "#f44336";
      msgEl.style.display = "block";
    }
  }).catch(e => {
    msgEl.textContent = "请求失败: " + e.message;
    msgEl.style.color = "#f44336";
    msgEl.style.display = "block";
  });
}

// ── 情节引导（始终可用） ──

function guidePlotEvent() {
  const desc = document.getElementById("guide-event-desc").value.trim();
  if (!desc) { alert("请填写事件描述"); return; }
  const msgEl = document.getElementById("guide-msg");
  fetch("/api/guide-plot", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ type: "inject_event", description: desc })
  }).then(r => r.json()).then(d => {
    if (d.status === "ok") {
      msgEl.textContent = "事件已注入，将影响下一章走向";
      msgEl.style.color = "#4caf50";
      msgEl.style.display = "block";
      document.getElementById("guide-event-desc").value = "";
      setTimeout(() => { msgEl.style.display = "none"; }, 3000);
    } else {
      msgEl.textContent = d.error || "注入失败";
      msgEl.style.color = "#f44336";
      msgEl.style.display = "block";
    }
  }).catch(e => {
    msgEl.textContent = "请求失败: " + e.message;
    msgEl.style.color = "#f44336";
    msgEl.style.display = "block";
  });
}

function guideAddGoal() {
  const name = document.getElementById("guide-goal-char").value;
  const goal = document.getElementById("guide-goal-text").value.trim();
  if (!name) { alert("请选择角色"); return; }
  if (!goal) { alert("请填写目标"); return; }
  const msgEl = document.getElementById("guide-msg");
  fetch("/api/guide-plot", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ type: "add_goal", name: name, goal: goal })
  }).then(r => r.json()).then(d => {
    if (d.status === "ok") {
      msgEl.textContent = d.message;
      msgEl.style.color = "#4caf50";
      msgEl.style.display = "block";
      document.getElementById("guide-goal-text").value = "";
      setTimeout(() => { msgEl.style.display = "none"; }, 3000);
    } else {
      msgEl.textContent = d.error || "添加失败";
      msgEl.style.color = "#f44336";
      msgEl.style.display = "block";
    }
  }).catch(e => {
    msgEl.textContent = "请求失败: " + e.message;
    msgEl.style.color = "#f44336";
    msgEl.style.display = "block";
  });
}



// ── 扫描正文发现角色 ──
function scanCharacters() {
  fetch("/api/scan-characters", { method: "POST" })
    .then(r => r.json())
    .then(d => {
      if (d.status === "ok") {
        const msg = d.found > 0
          ? `发现 ${d.found} 个新角色: ${d.names.join("、")}`
          : "未发现新角色（正文中可能没有符合条件的新角色名）";
        showToast(msg, d.found > 0 ? "success" : "info");
        // 刷新角色状态面板
        refreshState();
        // 刷新时间线角色列表
        if (typeof loadTimelineData === "function") loadTimelineData();
      } else {
        showToast(d.error || "扫描失败", "error");
      }
    })
    .catch(e => showToast("扫描失败: " + e, "error"));
}
