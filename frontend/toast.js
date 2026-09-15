/* toast.js - 全局通知组件 */

// ── Toast 提示 ──
function showToast(msg, type = "success") {
  let toast = document.getElementById("global-toast");
  if (!toast) {
    toast = document.createElement("div");
    toast.id = "global-toast";
    toast.style.cssText = "position:fixed;top:20px;right:20px;padding:12px 20px;border-radius:8px;font-size:14px;z-index:9999;transition:opacity 0.3s;box-shadow:0 4px 12px rgba(0,0,0,0.15);";
    document.body.appendChild(toast);
  }
  toast.textContent = msg;
  toast.style.background = type === "error" ? "#f44336" : type === "warning" ? "#e67e22" : "#4caf50";
  toast.style.color = "#fff";
  toast.style.opacity = "1";
  toast.style.display = "block";
  setTimeout(() => { toast.style.opacity = "0"; setTimeout(() => { toast.style.display = "none"; }, 300); }, 3000);
}

// ── 长任务进度条：超过 3 秒显示加载提示，超过 60 秒提供中止按钮 ──
function _getBusyBar() {
  let bar = document.getElementById("busy-bar");
  if (!bar) {
    bar = document.createElement("div");
    bar.id = "busy-bar";
    bar.style.cssText = "position:fixed;bottom:24px;left:50%;transform:translateX(-50%);display:none;align-items:center;gap:12px;padding:10px 18px;border-radius:10px;background:rgba(20,20,30,0.92);color:#fff;font-size:14px;z-index:10000;box-shadow:0 6px 20px rgba(0,0,0,0.35);";
    bar.innerHTML =
      '<span id="busy-spinner" style="width:16px;height:16px;border:2px solid rgba(255,255,255,0.3);border-top-color:#fff;border-radius:50%;animation:busySpin 0.8s linear infinite;"></span>' +
      '<span id="busy-label"></span>' +
      '<span id="busy-elapsed" style="color:#aaa;font-size:12px;"></span>' +
      '<button id="busy-cancel" style="display:none;padding:4px 12px;border:none;border-radius:6px;background:#e74c3c;color:#fff;cursor:pointer;font-size:13px;">中止</button>';
    document.body.appendChild(bar);
    if (!document.getElementById("busy-bar-style")) {
      const st = document.createElement("style");
      st.id = "busy-bar-style";
      st.textContent = "@keyframes busySpin { to { transform: rotate(360deg); } }";
      document.head.appendChild(st);
    }
  }
  return bar;
}

/**
 * 带长任务提示的 fetch：
 * - 超过 3 秒未完成 → 底部显示「label + 已用时」进度条
 * - 超过 60 秒未完成 → 进度条上出现「中止」按钮（客户端放弃等待）
 * 中止时 reject AbortError，调用方 catch 后可自行提示。
 */
async function busyFetch(url, options = {}, label = "处理中") {
  const bar = _getBusyBar();
  const labelEl = bar.querySelector("#busy-label");
  const elapsedEl = bar.querySelector("#busy-elapsed");
  const cancelBtn = bar.querySelector("#busy-cancel");

  const controller = new AbortController();
  const started = Date.now();
  let shown = false;

  const hide = () => {
    bar.style.display = "none";
    cancelBtn.style.display = "none";
  };
  const show = () => {
    if (shown) return;
    shown = true;
    labelEl.textContent = label;
    bar.style.display = "flex";
  };

  const t3 = setTimeout(show, 3000);
  const t60 = setTimeout(() => { if (shown) cancelBtn.style.display = "inline-block"; }, 60000);
  const tick = setInterval(() => {
    if (shown) elapsedEl.textContent = "已用时 " + Math.floor((Date.now() - started) / 1000) + " 秒";
  }, 1000);
  cancelBtn.onclick = () => controller.abort();

  try {
    const res = await fetch(url, Object.assign({}, options, { signal: controller.signal }));
    return res;
  } finally {
    clearTimeout(t3);
    clearTimeout(t60);
    clearInterval(tick);
    cancelBtn.onclick = null;
    hide();
  }
}

