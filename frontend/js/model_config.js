/* model_config.js - 多模型配置弹窗
   从 书斋V66-新重构 frontend/js/api.js 移植，适配小说世界项目 */

var currentProvider = 'deepseek';

function toggleModelPopover() {
  var pop = document.getElementById('model-popover');
  if (!pop) return;
  var visible = pop.classList.contains('visible');
  if (visible) {
    pop.classList.remove('visible');
  } else {
    loadModelConfig();
    loadAIUsage(false);   // 打开弹窗时自动加载用量统计
    pop.classList.add('visible');
  }
}

function switchModelProvider(prov) {
  currentProvider = prov;
  document.querySelectorAll('.mp-tab').forEach(function(t) {
    t.classList.toggle('active', t.dataset.provider === prov);
  });
  var panel = document.getElementById('mp-' + prov + '-panel');
  ['deepseek', 'ollama', 'openai'].forEach(function(p) {
    var el = document.getElementById('mp-' + p + '-panel');
    if (el) el.style.display = p === prov ? 'block' : 'none';
  });
  saveModelConfig();
}

function getModelConfig() {
  var el = function(id) { return document.getElementById(id); };
  return {
    provider: currentProvider,
    deepseek: {
      api_key: (el('mp-api-key') && el('mp-api-key').value) || '',
      base_url: (el('mp-endpoint') && el('mp-endpoint').value) || 'https://api.deepseek.com',
      model: (el('mp-model-name') && el('mp-model-name').value) || 'deepseek-v4-flash',
      temperature: parseFloat((el('mp-temp') && el('mp-temp').value) || 0.7),
      max_tokens: parseInt((el('mp-maxwords') && el('mp-maxwords').value) || 4096)
    },
    ollama: {
      base_url: (el('mp-ollama-host') && el('mp-ollama-host').value) || 'http://localhost:11434',
      model: (el('mp-ollama-model') && el('mp-ollama-model').value) || 'qwen2.5:14b',
      temperature: parseFloat((el('mp-temp') && el('mp-temp').value) || 0.7),
      max_tokens: parseInt((el('mp-maxwords') && el('mp-maxwords').value) || 4096)
    },
    openai: {
      api_key: '',
      base_url: 'https://api.openai.com/v1',
      model: 'gpt-4o-mini',
      temperature: parseFloat((el('mp-temp') && el('mp-temp').value) || 0.7),
      max_tokens: parseInt((el('mp-maxwords') && el('mp-maxwords').value) || 4096)
    }
  };
}

function updateModelBadge(cfg) {
  var provider = (cfg && cfg.provider) || currentProvider || 'deepseek';
  var hasKey = false, label = '未配置', dotClass = '';
  if (provider === 'ollama') {
    hasKey = true;
    label = (cfg && cfg.ollama && cfg.ollama.model) || 'Ollama';
    dotClass = ' ok';
  } else if (provider === 'deepseek') {
    hasKey = !!(cfg && cfg.deepseek && cfg.deepseek.api_key);
    if (!hasKey && cfg && cfg.deepseek && cfg.deepseek.base_url) hasKey = true;
    label = hasKey ? ((cfg && cfg.deepseek && cfg.deepseek.model) || 'DeepSeek') : '未配置';
    dotClass = hasKey ? ' ok' : '';
  } else {
    hasKey = !!(cfg && cfg.openai && cfg.openai.api_key);
    if (!hasKey && cfg && cfg.openai && cfg.openai.base_url) hasKey = true;
    label = hasKey ? 'OpenAI' : '未配置';
    dotClass = hasKey ? ' ok' : '';
  }
  var className = 'model-badge' + (hasKey ? ' configured' : ' unconfigured');
  var html = '<span class="conn-dot' + dotClass + '"></span>' + label;
  // 更新所有 model-badge 元素（设置页 + 游戏页）
  document.querySelectorAll('.model-badge').forEach(function(badge) {
    badge.className = className;
    badge.innerHTML = html;
  });
}

async function saveModelConfig() {
  var cfg = getModelConfig();
  try {
    await fetch('/api/ai/config', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(cfg)
    });
    updateModelBadge(cfg);
  } catch(e) { console.error('saveModelConfig error:', e); }
}

async function loadModelConfig() {
  var cfg = null;
  try {
    var r = await fetch('/api/ai/config');
    var d = await r.json();
    if (d.ok && d.config) {
      cfg = d.config;
      currentProvider = cfg.provider || 'deepseek';
      var el = function(id) { return document.getElementById(id); };
      if (cfg.deepseek) {
        if (el('mp-api-key')) el('mp-api-key').value = cfg.deepseek.api_key || '';
        if (el('mp-endpoint')) el('mp-endpoint').value = cfg.deepseek.base_url || 'https://api.deepseek.com';
        if (el('mp-model-name')) el('mp-model-name').value = cfg.deepseek.model || 'deepseek-v4-flash';
      }
      if (cfg.ollama) {
        if (el('mp-ollama-host')) el('mp-ollama-host').value = cfg.ollama.base_url || 'http://localhost:11434';
        if (el('mp-ollama-model')) el('mp-ollama-model').value = cfg.ollama.model || 'qwen2.5:14b';
      }
      var temp = (cfg.deepseek && cfg.deepseek.temperature) || (cfg.ollama && cfg.ollama.temperature) || 0.7;
      var maxTok = (cfg.deepseek && cfg.deepseek.max_tokens) || (cfg.ollama && cfg.ollama.max_tokens) || 4096;
      if (el('mp-temp')) el('mp-temp').value = temp;
      if (el('mp-temp-val')) el('mp-temp-val').textContent = temp;
      if (el('mp-maxwords')) el('mp-maxwords').value = maxTok;
      switchModelProvider(currentProvider);
    }
  } catch(e) { console.error('loadModelConfig error:', e); }
  updateModelBadge(cfg || getModelConfig());
}

async function testConnection() {
  var status = document.getElementById('mp-conn-status');
  if (status) {
    status.innerHTML = '<div class="mp-conn test">测试中…</div>';
  }
  try {
    var r = await fetch('/api/ai/test');
    var d = await r.json();
    if (status) {
      if (d.ok) {
        status.innerHTML = '<div class="mp-conn ok">连接成功 - ' + d.message + '</div>';
      } else {
        status.innerHTML = '<div class="mp-conn err">连接失败: ' + (d.error || d.message || '未知错误') + '</div>';
      }
    }
  } catch(e) {
    if (status) {
      status.innerHTML = '<div class="mp-conn err">连接失败: ' + e.message + '</div>';
    }
  }
}

async function loadAIUsage(showRefresh) {
  var body = document.getElementById('mp-usage-body');
  if (!body) return;
  if (showRefresh) body.innerHTML = '<span style="opacity:0.5">加载中…</span>';
  try {
    var r = await fetch('/api/ai/usage');
    var d = await r.json();
    if (d.ok && d.usage) {
      var u = d.usage;
      var fmt = function(n) { return n >= 10000 ? (n/10000).toFixed(1) + '万' : n.toLocaleString(); };
      var html = '<div style="display:flex;gap:12px;flex-wrap:wrap;margin-bottom:6px">';
      html += '<span>调用: <b>' + u.total_calls + '</b> 次</span>';
      html += '<span>Token: <b>' + fmt(u.total_tokens) + '</b></span>';
      html += '<span>估算费用: <b style="color:var(--accent)">' + (u.total_cost_cny || 0).toFixed(2) + '</b></span>';
      html += '</div>';
      // 月度配额预警（data/ai_config.json 的 monthly_quota_tokens）
      if (u.monthly && u.monthly.level && u.monthly.level !== 'unlimited') {
        var m = u.monthly;
        var color = m.level === 'exceeded' ? '#e74c3c' : (m.level === 'warning' ? '#e67e22' : '#4caf50');
        var text = m.level === 'exceeded' ? '⚠ 本月用量已超出配额' : (m.level === 'warning' ? '⚠ 本月用量已达 ' + m.used_pct + '%' : '本月用量 ' + m.used_pct + '%');
        html += '<div style="margin:6px 0;padding:6px 10px;border-radius:6px;font-size:12px;background:' + color + '22;color:' + color + ';border:1px solid ' + color + '66">';
        html += text + '（' + fmt(m.used_tokens) + ' / ' + fmt(m.quota_tokens) + ' token，本月费用约 ' + (m.used_cost_cny || 0).toFixed(2) + ' 元）';
        html += '</div>';
      }
      if (u.by_day && Object.keys(u.by_day).length > 0) {
        var days = Object.entries(u.by_day).sort(function(a, b) { return b[0].localeCompare(a[0]); }).slice(0, 7);
        html += '<div style="opacity:0.7;font-size:11px;margin-bottom:4px">近 ' + days.length + ' 天:</div>';
        html += '<div style="display:flex;gap:4px;flex-direction:column">';
        days.forEach(function(day) {
          var dt = day[1];
          html += '<div style="display:flex;justify-content:space-between;font-size:11px;opacity:0.8">';
          html += '<span>' + day[0] + '</span>';
          html += '<span>' + dt.calls + '次 / ' + fmt(dt.tokens) + 't</span>';
          html += '</div>';
        });
        html += '</div>';
      }
      body.innerHTML = html;
    }
  } catch(e) { console.error('loadAIUsage error:', e); }
}

// 点击外部关闭弹窗
document.addEventListener('click', function(e) {
  var pop = document.getElementById('model-popover');
  if (!pop || !pop.classList.contains('visible')) return;
  // 检查点击是否在任意 model-badge 内
  var clickedBadge = e.target.closest('.model-badge');
  if (clickedBadge) return;
  if (!pop.contains(e.target)) {
    pop.classList.remove('visible');
  }
});

// 页面加载时自动检测模型配置状态，更新所有徽章
document.addEventListener('DOMContentLoaded', function() {
  loadModelConfig();
});
