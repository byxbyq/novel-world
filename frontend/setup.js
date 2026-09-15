/* setup.js - 设置向导、角色管理、AI智能填充、工具函数 */

/* 小说世界 - 前端逻辑 */

// ── 状态 ──
let characters = [];
let charIdCounter = 0;
let currentChapterTitle = "";

// ── 设置向导 Tab 切换 ──
document.querySelectorAll(".setup-tabs .tab").forEach(tab => {
  tab.addEventListener("click", () => {
    const target = tab.dataset.tab;
    document.querySelectorAll(".setup-tabs .tab").forEach(t => t.classList.remove("active"));
    tab.classList.add("active");
    document.querySelectorAll(".tab-content").forEach(c => c.classList.remove("active"));
    document.getElementById("tab-" + target).classList.add("active");

    if (target === "review") updateReview();
  });
});

// ── 角色管理 ──
function addCharacter() {
  const id = ++charIdCounter;
  const card = document.createElement("div");
  card.className = "character-card";
  card.id = "char-" + id;
  card.innerHTML = `
    <button class="remove-char" onclick="removeCharacter(${id})">✕</button>
    <h4>角色 ${characters.length + 1}</h4>
    <div class="form-row">
      <div class="form-group">
        <label>姓名</label>
        <input class="char-name" value="">
      </div>
      <div class="form-group">
        <label>性别</label>
        <select class="char-gender">
          <option value="男">男</option>
          <option value="女">女</option>
        </select>
      </div>
      <div class="form-group">
        <label>年龄</label>
        <input class="char-age" type="number" value="20" min="1">
      </div>
    </div>
    <div class="form-group">
      <label>性格</label>
      <input class="char-personality" placeholder="如：冷峻孤傲，实则重情重义">
    </div>
    <div class="form-group">
      <label>背景故事</label>
      <textarea class="char-background" rows="2" placeholder="简要描述角色的来历和过往"></textarea>
    </div>
    <div class="form-group">
      <label>外貌</label>
      <input class="char-appearance" placeholder="如：一身白衣，背负长剑">
    </div>
    <div class="form-group">
      <label>长期目标</label>
      <input class="char-long-goal" placeholder="如：飞升仙界，寻找失散的师父">
    </div>
    <div class="form-group">
      <label>短期目标（一行一个）</label>
      <textarea class="char-short-goals" rows="2" placeholder="通过宗门考核&#10;获得一件法器"></textarea>
    </div>
    <div class="form-group">
      <label>能力特长（逗号分隔）</label>
      <input class="char-abilities" placeholder="如：剑术高超, 阵法精通">
    </div>
    <div class="form-group">
      <label>弱点（逗号分隔）</label>
      <input class="char-weaknesses" placeholder="如：冲动, 不善交际">
    </div>
    <div class="form-group">
      <label>初始位置</label>
      <input class="char-location" placeholder="如：青云宗山门外">
    </div>
  `;
  document.getElementById("character-list").appendChild(card);
}

function removeCharacter(id) {
  document.getElementById("char-" + id).remove();
}

function collectCharacters() {
  const cards = document.querySelectorAll(".character-card");
  return Array.from(cards).map(card => {
    const get = cls => card.querySelector("." + cls)?.value || "";
    return {
      name: get("char-name"),
      gender: get("char-gender"),
      age: parseInt(get("char-age")) || 20,
      personality: get("char-personality"),
      background: get("char-background"),
      appearance: get("char-appearance"),
      long_term_goal: get("char-long-goal"),
      short_term_goals: get("char-short-goals").split("\n").map(s => s.trim()).filter(Boolean),
      abilities: get("char-abilities").split(",").map(s => s.trim()).filter(Boolean),
      weaknesses: get("char-weaknesses").split(",").map(s => s.trim()).filter(Boolean),
      initial_location: get("char-location"),
      initial_relationships: {}
    };
  });
}

function val(id) { return document.getElementById(id).value; }

// ── AI 模型配置（已迁移到 model_config.js）──
function saveApiKey() {
  // 已废弃：模型配置现由 model_config.js 中 loadModelConfig/saveModelConfig 统一管理
  toggleModelPopover();
}

// ── AI 智能填充 ──

function collectWorldData() {
  const rules = document.getElementById("world-rules").value.split("\n").map(s => s.trim()).filter(Boolean);
  const locations = document.getElementById("world-locations").value.split("\n").map(s => s.trim()).filter(Boolean);

  return {
    name: val("world-name"),
    genre: val("world-genre"),
    era: val("world-era"),
    description: val("world-desc"),
    tone: val("world-tone"),
    rules: rules,
    key_locations: locations,
    current_situation: val("world-situation"),
    main_objective: val("world-main-objective"),
  };
}

function fillWorldForm(world) {
  if (world.name) document.getElementById("world-name").value = world.name;
  if (world.genre) {
    const genreSelect = document.getElementById("world-genre");
    const genres = Array.from(genreSelect.options).map(o => o.value);
    if (genres.includes(world.genre)) {
      genreSelect.value = world.genre;
    } else {
      genreSelect.value = "自定义";
    }
  }
  if (world.era) {
    const eraSelect = document.getElementById("world-era");
    const eras = Array.from(eraSelect.options).map(o => o.value);
    if (eras.includes(world.era)) {
      eraSelect.value = world.era;
    }
  }
  if (world.description) document.getElementById("world-desc").value = world.description;
  if (world.tone) {
    const toneSelect = document.getElementById("world-tone");
    const tones = Array.from(toneSelect.options).map(o => o.value);
    if (tones.includes(world.tone)) {
      toneSelect.value = world.tone;
    }
  }
  if (world.rules && world.rules.length) {
    document.getElementById("world-rules").value = world.rules.join("\n");
  }
  if (world.key_locations && world.key_locations.length) {
    document.getElementById("world-locations").value = world.key_locations.join("\n");
  }
  if (world.current_situation) document.getElementById("world-situation").value = world.current_situation;
  if (world.main_objective) document.getElementById("world-main-objective").value = world.main_objective;
}

async function ensureModelConfigured() {
  try {
    const r = await fetch("/api/ai/config");
    const d = await r.json();
    if (!d.ok || !d.config) return false;
    const cfg = d.config;
    const provider = cfg.provider || "deepseek";
    if (provider === "ollama") return true;
    if (provider === "deepseek") return !!(cfg.deepseek && (cfg.deepseek.api_key || cfg.deepseek.base_url));
    if (provider === "openai") return !!(cfg.openai && (cfg.openai.api_key || cfg.openai.base_url));
    return false;
  } catch (e) {
    return false;
  }
}

async function aiFillWorld() {
  if (!await ensureModelConfigured()) {
    alert("请先点击顶部「AI 模型」配置模型，再使用 AI 功能");
    return;
  }
  const btn = document.getElementById("btn-ai-world");
  const originalText = btn.textContent;
  btn.disabled = true;
  btn.textContent = "生成中...";

  try {
    const worldData = collectWorldData();
    const res = await busyFetch("/api/generate-world", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(worldData)
    }, "AI 正在生成世界观");
    const data = await res.json();
    if (data.status === "ok") {
      fillWorldForm(data.world);
    } else {
      alert(data.error || "AI 生成失败");
    }
  } catch (e) {
    alert(e.name === "AbortError" ? "已中止等待，可稍后重试" : "连接服务器失败：" + e.message);
  } finally {
    btn.disabled = false;
    btn.textContent = originalText;
  }
}

function fillCharacterCards(characters) {
  // 清除现有角色卡片
  const list = document.getElementById("character-list");
  list.innerHTML = "";

  characters.forEach((ch, index) => {
    const id = ++charIdCounter;
    const card = document.createElement("div");
    card.className = "character-card";
    card.id = "char-" + id;
    card.innerHTML = `
      <button class="remove-char" onclick="removeCharacter(${id})">✕</button>
      <h4>角色 ${index + 1}</h4>
      <div class="form-row">
        <div class="form-group">
          <label>姓名</label>
          <input class="char-name" value="${escapeHtml(ch.name || '')}">
        </div>
        <div class="form-group">
          <label>性别</label>
          <select class="char-gender">
            <option value="男"${ch.gender === '男' ? ' selected' : ''}>男</option>
            <option value="女"${ch.gender === '女' ? ' selected' : ''}>女</option>
          </select>
        </div>
        <div class="form-group">
          <label>年龄</label>
          <input class="char-age" type="number" value="${ch.age || 20}" min="1">
        </div>
      </div>
      <div class="form-group">
        <label>性格</label>
        <input class="char-personality" value="${escapeHtml(ch.personality || '')}" placeholder="如：冷峻孤傲，实则重情重义">
      </div>
      <div class="form-group">
        <label>背景故事</label>
        <textarea class="char-background" rows="2" placeholder="简要描述角色的来历和过往">${escapeHtml(ch.background || '')}</textarea>
      </div>
      <div class="form-group">
        <label>外貌</label>
        <input class="char-appearance" value="${escapeHtml(ch.appearance || '')}" placeholder="如：一身白衣，背负长剑">
      </div>
      <div class="form-group">
        <label>长期目标</label>
        <input class="char-long-goal" value="${escapeHtml(ch.long_term_goal || '')}" placeholder="如：飞升仙界，寻找失散的师父">
      </div>
      <div class="form-group">
        <label>短期目标（一行一个）</label>
        <textarea class="char-short-goals" rows="2" placeholder="通过宗门考核&#10;获得一件法器">${escapeHtml((ch.short_term_goals || []).join("\n"))}</textarea>
      </div>
      <div class="form-group">
        <label>能力特长（逗号分隔）</label>
        <input class="char-abilities" value="${escapeHtml((ch.abilities || []).join("，"))}" placeholder="如：剑术高超, 阵法精通">
      </div>
      <div class="form-group">
        <label>弱点（逗号分隔）</label>
        <input class="char-weaknesses" value="${escapeHtml((ch.weaknesses || []).join("，"))}" placeholder="如：冲动, 不善交际">
      </div>
      <div class="form-group">
        <label>初始位置</label>
        <input class="char-location" value="${escapeHtml(ch.initial_location || '')}" placeholder="如：青云宗山门外">
      </div>
    `;
    list.appendChild(card);
  });
}

function escapeHtml(str) {
  if (!str) return "";
  return str.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

function showCharCountDialog(callback) {
  // 移除已有弹窗
  const existing = document.querySelector(".modal-overlay");
  if (existing) existing.remove();

  const overlay = document.createElement("div");
  overlay.className = "modal-overlay";
  let selectedCount = 2;

  overlay.innerHTML = `
    <div class="modal-dialog">
      <h3>选择生成角色数量</h3>
      <div class="count-options">
        ${[1, 2, 3, 4, 5].map(n => `
          <button class="count-btn${n === selectedCount ? ' selected' : ''}" data-count="${n}">${n}</button>
        `).join("")}
      </div>
      <div class="modal-actions">
        <button class="btn-cancel">取消</button>
        <button class="btn-confirm">确认生成</button>
      </div>
    </div>
  `;

  // 数量选择
  overlay.querySelectorAll(".count-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      overlay.querySelectorAll(".count-btn").forEach(b => b.classList.remove("selected"));
      btn.classList.add("selected");
      selectedCount = parseInt(btn.dataset.count);
    });
  });

  // 取消
  overlay.querySelector(".btn-cancel").addEventListener("click", () => {
    overlay.remove();
  });

  // 确认
  overlay.querySelector(".btn-confirm").addEventListener("click", () => {
    overlay.remove();
    callback(selectedCount);
  });

  // 点击遮罩关闭
  overlay.addEventListener("click", (e) => {
    if (e.target === overlay) overlay.remove();
  });

  document.body.appendChild(overlay);
}

async function aiFillCharacters() {
  if (!await ensureModelConfigured()) {
    alert("请先点击顶部「AI 模型」配置模型，再使用 AI 功能");
    return;
  }
  const btn = document.getElementById("btn-ai-chars");
  const originalText = btn.textContent;

  showCharCountDialog(async (count) => {
    btn.disabled = true;
    btn.textContent = "生成中...";

    try {
      const worldData = collectWorldData();
      const res = await busyFetch("/api/generate-characters", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ world: worldData, count: count })
      }, "AI 正在生成角色");
      const data = await res.json();
      if (data.status === "ok") {
        fillCharacterCards(data.characters);
      } else {
        alert(data.error || "AI 生成失败");
      }
    } catch (e) {
      alert(e.name === "AbortError" ? "已中止等待，可稍后重试" : "连接服务器失败：" + e.message);
    } finally {
      btn.disabled = false;
      btn.textContent = originalText;
    }
  });
}


// ── 灵感输入折叠 ──
(function() {
  const header = document.getElementById("inspiration-header");
  const body = document.getElementById("inspiration-body");
  const arrow = document.getElementById("inspiration-arrow");

  header.addEventListener("click", () => {
    const isExpanded = body.style.display !== "none";
    if (isExpanded) {
      body.style.display = "none";
      arrow.textContent = "▶";
    } else {
      body.style.display = "block";
      arrow.textContent = "▼";
    }
  });

  // 默认折叠
  body.style.display = "none";
})();

// ── AI 分析内容 ──
async function analyzeContent() {
  if (!await ensureModelConfigured()) {
    const msg = document.getElementById("inspiration-msg");
    msg.textContent = "请先点击顶部「AI 模型」配置模型，再使用 AI 功能";
    msg.className = "error";
    return;
  }
  const input = document.getElementById("inspiration-input");
  const btn = document.getElementById("btn-analyze-content");
  const msg = document.getElementById("inspiration-msg");
  const content = input.value.trim();

  if (!content) {
    msg.textContent = "请先输入需要分析的内容";
    msg.className = "error";
    return;
  }

  msg.textContent = "";
  msg.className = "";
  const originalText = btn.textContent;
  btn.disabled = true;
  btn.textContent = "✦ 分析中...";

  try {
    const res = await fetch("/api/analyze-content", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ content })
    });
    const data = await res.json();

    if (data.status === "ok") {
      // 填充世界设定
      if (data.world) {
        fillWorldForm(data.world);
      }

      // 填充角色设定
      if (data.characters && data.characters.length > 0) {
        fillCharacterCards(data.characters);
      }

      // 切换到世界设定 tab
      const worldTab = document.querySelector('.setup-tabs .tab[data-tab="world"]');
      if (worldTab) worldTab.click();

      const charCount = data.characters ? data.characters.length : 0;
      msg.textContent = `已从你的内容中提取出 ${charCount} 个角色和世界设定`;
      msg.className = "success";
    } else {
      if (data.error && (data.error.includes("API Key") || data.error.includes("未配置"))) {
        msg.innerHTML = `${data.error}，点击<a href="#" onclick="toggleModelPopover();return false;" style="color:var(--accent);text-decoration:underline">这里</a>前往配置 AI 模型`;
        msg.className = "error";
      } else {
        msg.textContent = data.error || "AI 分析失败";
        msg.className = "error";
      }
    }
  } catch (e) {
    msg.textContent = "连接服务器失败：" + e.message;
    msg.className = "error";
  } finally {
    btn.disabled = false;
    btn.textContent = originalText;
  }
}

// ── 初始化 ──
addCharacter(); // 默认添加第一个角色

