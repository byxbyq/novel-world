/* chat.js - 聊天式剧情讨论面板：SSE 流式对话 + 操作确认 + 浮动面板 */

(function () {
  "use strict";

  // ── DOM 引用 ──
  const overlay = document.getElementById("chat-overlay");
  const toggleBtn = document.getElementById("chat-toggle");
  const closeBtn = document.getElementById("chat-close");
  const messagesEl = document.getElementById("chat-messages");
  const inputEl = document.getElementById("chat-input");
  const sendBtn = document.getElementById("chat-send");
  const headerEl = document.getElementById("chat-header");

  let isOpen = false;
  let isStreaming = false;
  let pendingConfirm = null; // { name, params, result } 等待确认的操作

  // ── 面板开关 ──
  toggleBtn.addEventListener("click", () => {
    isOpen = !isOpen;
    overlay.style.display = isOpen ? "flex" : "none";
    toggleBtn.style.display = isOpen ? "none" : "block";
    if (isOpen) {
      inputEl.focus();
      scrollToBottom();
    }
  });

  closeBtn.addEventListener("click", () => {
    isOpen = false;
    overlay.style.display = "none";
    toggleBtn.style.display = "block";
  });

  // ── 拖拽 ──
  let dragState = null;
  headerEl.addEventListener("mousedown", (e) => {
    if (e.target === closeBtn) return;
    dragState = {
      startX: e.clientX,
      startY: e.clientY,
      startRight: parseInt(overlay.style.right || "20"),
      startBottom: parseInt(overlay.style.bottom || "80"),
    };
    document.addEventListener("mousemove", onDrag);
    document.addEventListener("mouseup", onDragEnd);
    headerEl.style.cursor = "grabbing";
  });

  function onDrag(e) {
    if (!dragState) return;
    const dx = dragState.startX - e.clientX;
    const dy = dragState.startY - e.clientY;
    overlay.style.right = (dragState.startRight + dx) + "px";
    overlay.style.bottom = (dragState.startBottom + dy) + "px";
  }

  function onDragEnd() {
    dragState = null;
    headerEl.style.cursor = "grab";
    document.removeEventListener("mousemove", onDrag);
    document.removeEventListener("mouseup", onDragEnd);
  }

  // ── 发送消息 ──
  sendBtn.addEventListener("click", sendMessage);
  inputEl.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  });

  function sendMessage() {
    const text = inputEl.value.trim();
    if (!text || isStreaming) return;

    // 渲染用户消息
    appendMessage("user", text);
    inputEl.value = "";
    inputEl.style.height = "auto";

    // 渲染 AI 占位气泡
    const aiBubble = appendMessage("ai", "", true);
    const aiContent = aiBubble.querySelector(".chat-bubble-content");

    // 进入 streaming 状态
    setStreaming(true);
    pendingConfirm = null;

    // 建立 SSE 连接
    const encoded = encodeURIComponent(text);
    const es = new EventSource("/api/chat/stream?message=" + encoded);
    let fullText = "";
    let hasAction = false;

    es.onmessage = function (event) {
      try {
        const data = JSON.parse(event.data);
        switch (data.type) {
          case "token":
            fullText += data.content;
            aiContent.textContent = fullText;
            scrollToBottom();
            break;

          case "action":
            hasAction = true;
            // 移除占位文本，插入操作结果卡片
            const card = createActionCard(data.name, data.params, data.result);
            aiBubble.appendChild(card);

            // 有副作用的操作，显示确认卡片
            if (isSideEffectFn(data.name)) {
              pendingConfirm = { name: data.name, params: data.params, result: data.result };
              const confirmCard = createConfirmCard(data.name, data.params);
              aiBubble.appendChild(confirmCard);
            }
            scrollToBottom();
            break;

          case "confirm":
            // 后端明确要求确认（备用路径）
            pendingConfirm = { name: data.name, params: data.params, result: data.result };
            const cc = createConfirmCard(data.name, data.params);
            aiBubble.appendChild(cc);
            scrollToBottom();
            break;

          case "done":
            es.close();
            setStreaming(false);
            // 如果 AI 气泡只有占位没内容，移除它
            if (!fullText && !hasAction) {
              aiBubble.remove();
            }
            break;

          case "error":
            es.close();
            setStreaming(false);
            aiContent.textContent = "错误: " + (data.message || "连接失败");
            aiContent.style.color = "#e74c3c";
            break;
        }
      } catch (err) {
        // JSON 解析失败，忽略
      }
    };

    es.onerror = function () {
      es.close();
      setStreaming(false);
      if (!fullText && !hasAction) {
        aiContent.textContent = "连接中断，请重试";
        aiContent.style.color = "#e74c3c";
      }
    };
  }

  // ── 辅助函数 ──

  function appendMessage(role, text, isPlaceholder) {
    const wrapper = document.createElement("div");
    wrapper.className = "chat-msg " + role;

    const bubble = document.createElement("div");
    bubble.className = "chat-bubble " + role;

    if (role === "user") {
      bubble.textContent = text;
      wrapper.appendChild(bubble);
    } else {
      const content = document.createElement("div");
      content.className = "chat-bubble-content";
      if (isPlaceholder) {
        content.innerHTML = '<span class="chat-loading-dots"><span>.</span><span>.</span><span>.</span></span>';
      } else {
        content.textContent = text;
      }
      bubble.appendChild(content);
      wrapper.appendChild(bubble);
    }

    messagesEl.appendChild(wrapper);
    scrollToBottom();
    return bubble;
  }

  function createActionCard(name, params, result) {
    const card = document.createElement("div");
    card.className = "chat-action-card";

    const iconMap = {
      add_character: "👤",
      edit_character: "✏️",
      inject_event: "⚡",
      divine_guidance: "✨",
      edit_outline: "📋",
      generate_chapter: "📖",
      get_outline: "📋",
      get_character: "👤",
      get_world_settings: "🌍",
      post_process: "🔧",
      humanity_audit: "🎭",
    };

    const labelMap = {
      add_character: "添加角色",
      edit_character: "编辑角色",
      inject_event: "注入事件",
      divine_guidance: "天意指引",
      edit_outline: "修改大纲",
      generate_chapter: "生成章节",
      get_outline: "查看大纲",
      get_character: "查看角色",
      get_world_settings: "查看世界设定",
      post_process: "去AI腔",
      humanity_audit: "人味审计",
    };

    const tabMap = {
      add_character: "interv-data",
      edit_character: "interv-data",
      inject_event: "interv-data",
      divine_guidance: "interv-guidance",
      edit_outline: "interv-outline",
      generate_chapter: null,
      humanity_audit: "interv-humanity",
    };

    const icon = iconMap[name] || "⚙️";
    const label = labelMap[name] || name;
    const success = result && !result.error;

    let desc = "";
    if (name === "add_character" && params.name) desc = `角色「${params.name}」已添加`;
    else if (name === "edit_character" && params.name) desc = `角色「${params.name}」已更新`;
    else if (name === "inject_event") desc = `事件已注入`;
    else if (name === "divine_guidance") desc = `已向「${params.character_name || "?"}」发送指引`;
    else if (name === "edit_outline") desc = "大纲已更新";
    else if (name === "generate_chapter") desc = "章节已生成";
    else if (name === "get_outline") desc = "已获取大纲";
    else if (name === "get_character") desc = `已查看角色「${params.name || "?"}」`;
    else if (name === "get_world_settings") desc = "已获取世界设定";
    else if (name === "post_process") desc = "后处理完成";
    else if (name === "humanity_audit") desc = "人味审计完成";
    else desc = `已执行：${label}`;

    card.innerHTML = `<span class="chat-action-icon">${icon}</span>
      <span class="chat-action-label">${label}</span>
      <span class="chat-action-desc" style="color:${success ? '#4caf50' : '#e74c3c'}">${success ? desc : (result.error || '执行失败')}</span>`;

    const targetTab = tabMap[name];
    if (targetTab) {
      card.style.cursor = "pointer";
      card.title = "点击跳转到对应面板";
      card.addEventListener("click", () => {
        // 打开 DM 干预面板并切换到对应 tab
        const panel = document.getElementById("dm-intervention-panel");
        if (panel) panel.style.display = "block";
        const tab = document.querySelector(`.interv-tab[data-tab="${targetTab}"]`);
        if (tab) tab.click();
      });
    }

    return card;
  }

  function createConfirmCard(name, params) {
    const card = document.createElement("div");
    card.className = "chat-confirm-card";

    const labelMap = {
      add_character: `确认添加角色「${params.name || "?"}」？`,
      edit_character: `确认修改角色「${params.name || "?"}」？`,
      inject_event: "确认注入此事件？",
      divine_guidance: "确认发送天意指引？",
      edit_outline: "确认修改大纲？",
      generate_chapter: "确认生成下一章？",
    };

    card.innerHTML = `<div class="chat-confirm-text">${labelMap[name] || "确认执行此操作？"}</div>
      <div class="chat-confirm-btns">
        <button class="chat-confirm-yes">确认</button>
        <button class="chat-confirm-no">取消</button>
      </div>`;

    card.querySelector(".chat-confirm-yes").addEventListener("click", () => {
      fetch("/api/chat/confirm", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: name, params: params, confirmed: true }),
      }).catch((e) => {
        if (typeof showToast === "function") showToast("确认请求失败：" + e.message, "warning");
      });
      card.querySelector(".chat-confirm-text").textContent = "已确认执行";
      card.querySelector(".chat-confirm-btns").remove();
      card.style.borderColor = "#4caf50";
      pendingConfirm = null;
    });

    card.querySelector(".chat-confirm-no").addEventListener("click", () => {
      fetch("/api/chat/undo", { method: "POST" })
        .then((r) => r.json())
        .then((d) => {
          if (typeof showToast === "function") showToast(d.message || "已回滚", d.status === "ok" ? "success" : "warning");
        })
        .catch((e) => {
          if (typeof showToast === "function") showToast("回滚失败：" + e.message, "error");
        });
      card.querySelector(".chat-confirm-text").textContent = "已取消";
      card.querySelector(".chat-confirm-btns").remove();
      card.style.borderColor = "#e74c3c";
      pendingConfirm = null;
    });

    return card;
  }

  function setStreaming(streaming) {
    isStreaming = streaming;
    inputEl.disabled = streaming;
    sendBtn.disabled = streaming;
    if (streaming) {
      sendBtn.textContent = "…";
    } else {
      sendBtn.textContent = "发送";
    }
  }

  function scrollToBottom() {
    messagesEl.scrollTop = messagesEl.scrollHeight;
  }

  function isSideEffectFn(name) {
    return ["add_character", "edit_character", "inject_event", "divine_guidance",
            "edit_outline", "generate_chapter", "edit_world_settings"].includes(name);
  }

  // ── 自动调整 textarea 高度 ──
  inputEl.addEventListener("input", () => {
    inputEl.style.height = "auto";
    inputEl.style.height = Math.min(inputEl.scrollHeight, 120) + "px";
  });
})();
