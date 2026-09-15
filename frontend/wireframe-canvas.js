/**
 * 小说世界 - 连线框画布模块（wireframe-canvas.js）- 从书斋V66移植
 *
 * 核心定位：贯穿写作全流程的「设定可视化 + 正文对照校验」工具
 * 双场景复用同一套连线数据：
 *   - 前置规划（plan模式）：纯全屏画布，搭建人物关系/伏笔链/章节因果
 *   - 后置修改（compare模式）：左右双屏，左画布右正文，对照校验设定一致性
 *
 * 核心原则：连线框不自动改写正文，仅提供对照、定位、一键修改联动
 *
 * 数据结构（planning_cards）：
 *   { nodes: [{id,type,title,summary,quotes,x,y,color,chapter_ref}], edges: [{id,from,to,label,arrow}], meta: {} }
 */
(function (global) {
  'use strict';

  // ═══════════════════════════════════════════
  // 状态
  // ═══════════════════════════════════════════
  const state = {
    mode: 'plan',           // 'plan' | 'compare'
    nodes: [],
    edges: [],
    meta: {},
    selectedNode: null,
    selectedEdge: null,
    // 画布视口
    viewport: { x: 0, y: 0, scale: 1 },
    // 交互状态
    draggingNode: null,
    dragOffset: { x: 0, y: 0 },
    panning: false,
    panStart: { x: 0, y: 0 },
    connectMode: false,
    connectFrom: null,
    boxSelectStart: null,
    boxSelectEnd: null,
    boxSelecting: false,
    // 右键菜单位置
    contextMenuPos: { x: 0, y: 0 },
    // 对照校验状态
    checkResults: {},       // { nodeId: 'consistent' | 'needs_update' | 'uninvolved' }
    // 撤销/重做
    history: [],
    historyIndex: -1,
    dirty: false,
  };

  // 节点类型与颜色映射
  const NODE_TYPES = {
    character: { label: '人物', color: '#3b82f6' },
    foreshadow: { label: '伏笔', color: '#f59e0b' },
    chapter: { label: '章节', color: '#10b981' },
    worldview: { label: '世界观', color: '#8b5cf6' },
    free: { label: '自由', color: '#6b7280' },
  };


  // ── 数据缓存（从后端加载，替代全局变量）──
  let _cachedCharacters = [];
  let _cachedChapters = [];
  let _cachedWorldSettings = [];
  let _cachedHooks = [];
  let _cachedChapterIndex = 0;
  let _cacheLoaded = false;

  async function refreshCache() {
    try {
      const [stateResp, chaptersResp, wsResp, hooksResp] = await Promise.all([
        fetch('/api/state').then(r => r.ok ? r.json() : null),
        fetch('/api/chapters').then(r => r.ok ? r.json() : null),
        fetch('/api/world-settings').then(r => r.ok ? r.json() : null),
        fetch('/api/hooks').then(r => r.ok ? r.json() : null),
      ]);
      if (stateResp && stateResp.status === 'ok' && stateResp.state) {
        _cachedCharacters = (stateResp.state.characters || []).map(c => ({
          name: c.name, title: c.name, personality: c.personality || '',
          description: c.long_term_goal || '', content: c.long_term_goal || ''
        }));
        _cachedChapterIndex = (stateResp.state.world && stateResp.state.world.chapter) ? stateResp.state.world.chapter - 1 : 0;
        if (_cachedChapterIndex < 0) _cachedChapterIndex = 0;
      }
      if (chaptersResp && chaptersResp.chapters) {
        _cachedChapters = chaptersResp.chapters;
        // world.chapter 是持久计数器，失败/中止也会累加，可能与章节列表脱节。
        // 优先按编号在列表里定位真实章节；失配时回退到最后一章（写完即当前章），
        // 仅在完全无法定位时才用钳制后的计数器值
        if (_cachedChapters.length > 0) {
          const target = (_cachedChapterIndex || 0) + 1;
          const hit = _cachedChapters.findIndex(c => c.chapter === target);
          if (hit >= 0) {
            _cachedChapterIndex = hit;
          } else {
            _cachedChapterIndex = _cachedChapters.length - 1;
          }
        } else {
          _cachedChapterIndex = 0;
        }
      }
      if (wsResp && wsResp.settings) {
        _cachedWorldSettings = wsResp.settings;
      }
      if (hooksResp && hooksResp.hooks) {
        _cachedHooks = hooksResp.hooks;
      }
      _cacheLoaded = true;
    } catch (e) {
      console.warn('[Wireframe] 缓存刷新失败:', e);
    }
  }

  function getCharacters() { return _cachedCharacters; }
  function getChapters() { return _cachedChapters; }
  // 章节正文字段：后端 /api/chapters 返回 narrative（兼容旧字段 content）
  function chapterText(ch) { return (ch && (ch.narrative || ch.content)) || ''; }
  // 章节编号：优先后端 chapter 字段（真实编号），缺失时回退数组下标+1。
  // 不直接用下标推导——历史跳号/删章场景下 i+1 会与实际编号错位，
  // 导致自动生成的节点 chapter_ref 与正文对不上
  function chapterNum(ch, i) { return (ch && Number(ch.chapter)) || (i + 1); }
  function getWorldSettings() { return _cachedWorldSettings; }
  function getHooks() { return _cachedHooks; }
  function getCurrentChapterIndex() { return _cachedChapterIndex; }

  // DOM引用
  let overlay = null;
  // 画布未打开时登记的待消费聚焦（加载完成后由 openWireframe 消费），
  // 避免聚焦动作与 loadFromBackend 异步加载竞态
  let pendingFocus = null; // { nodeId } | { chapterRef }
  let svgEl = null;
  let canvasGroup = null;
  let statusEl = null;
  let contextMenuEl = null;
  let comparePanelEl = null;

  // ═══════════════════════════════════════════
  // 工具函数
  // ═══════════════════════════════════════════
  function uid() {
    return 'n_' + Date.now().toString(36) + Math.random().toString(36).slice(2, 6);
  }
  function uidEdge() {
    return 'e_' + Date.now().toString(36) + Math.random().toString(36).slice(2, 6);
  }

  // 屏幕坐标→画布坐标
  function screenToCanvas(sx, sy) {
    const rect = svgEl.getBoundingClientRect();
    const x = (sx - rect.left - state.viewport.x) / state.viewport.scale;
    const y = (sy - rect.top - state.viewport.y) / state.viewport.scale;
    return { x, y };
  }

  // 防抖保存
  let saveTimer = null;
  function scheduleSave() {
    state.dirty = true;
    if (saveTimer) clearTimeout(saveTimer);
    saveTimer = setTimeout(saveToBackend, 800);
  }

  // ═══════════════════════════════════════════
  // 持久化
  // ═══════════════════════════════════════════
  async function loadFromBackend() {
    try {
      const resp = await fetch('/api/project/planning-cards'); const res = await resp.json();
      if (res && res.ok && res.data) {
        state.nodes = Array.isArray(res.data.nodes) ? res.data.nodes : [];
        state.edges = Array.isArray(res.data.edges) ? res.data.edges : [];
        state.meta = res.data.meta || {};
        if (state.meta.viewport) state.viewport = state.meta.viewport;
      }
    } catch (e) {
      console.warn('[Wireframe] 加载失败:', e);
    }
  }

  // ═══════════════════════════════════════════
  // 自动生成：从项目数据一键生成节点+连线
  // ═══════════════════════════════════════════
  function autoGenerateFromProject() {
    state.nodes = [];
    state.edges = [];

    const marginX = 180;
    const marginY = 80;
    const colGap = 220;
    const rowGap = 140;
    let col = 0;
    let row = 0;

    const _chars = getCharacters();
    const _chapters = getChapters();
    const _ws = getWorldSettings();

    const charNodeIds = {};
    const chapterNodeIds = {};
    const wsNodeIds = {};

    // 第1列：世界观设定
    _ws.forEach((s) => {
      const id = uid();
      wsNodeIds[s.key] = id;
      state.nodes.push({
        id: id, type: 'worldview',
        title: (s.key || '设定').slice(0, 16),
        summary: (s.val || '').slice(0, 80),
        x: marginX + col * colGap,
        y: marginY + row * rowGap,
        color: NODE_TYPES.worldview.color,
      });
      row++;
    });
    col++; row = 0;

    // 第2列：人物
    _chars.forEach((c) => {
      const id = uid();
      charNodeIds[c.name] = id;
      state.nodes.push({
        id: id, type: 'character',
        title: (c.name || c.title || '未命名').slice(0, 16),
        summary: (c.description || c.personality || '').slice(0, 80),
        x: marginX + col * colGap,
        y: marginY + row * rowGap,
        color: NODE_TYPES.character.color,
      });
      row++;
    });
    col++; row = 0;

    // 第3列：章节（上半部分）+ 伏笔（下半部分）
    const _hooks = getHooks();

    _chapters.forEach((ch, i) => {
      const id = uid();
      const chRef = '第' + chapterNum(ch, i) + '章';
      chapterNodeIds[chRef] = id;
      state.nodes.push({
        id: id, type: 'chapter',
        title: chRef + ' ' + (ch.title || '').slice(0, 10),
        summary: (ch.outline || '').slice(0, 80),
        x: marginX + col * colGap,
        y: marginY + row * rowGap,
        color: NODE_TYPES.chapter.color,
        chapter_ref: chRef,
      });
      row++;
    });

    // 伏笔放在章节下方
    const hookStartRow = row + 1;
    _hooks.forEach((h, i) => {
      const id = uid();
      state.nodes.push({
        id: id, type: 'foreshadow',
        title: ('伏笔' + (i + 1) + ' ').slice(0, 6) + (h.content || '').slice(0, 14),
        summary: (h.content || '').slice(0, 80),
        x: marginX + col * colGap,
        y: marginY + (hookStartRow + i) * rowGap,
        color: NODE_TYPES.foreshadow.color,
      });
    });

    // 生成连线
    // 1. 世界观 → 人物（所有人都受世界观约束）
    Object.values(charNodeIds).forEach((cId) => {
      Object.values(wsNodeIds).forEach((wsId) => {
        state.edges.push({
          id: uidEdge(), from: wsId, to: cId,
          label: '约束',
          arrow: 'forward',
        });
      });
    });

    // 2. 人物 → 章节（按出场章节连线）
    _chapters.forEach((ch, i) => {
      const chRef = '第' + chapterNum(ch, i) + '章';
      const chNodeId = chapterNodeIds[chRef];
      if (!chNodeId) return;
      if (ch.characters && Array.isArray(ch.characters)) {
        ch.characters.forEach((charName) => {
          const cId = charNodeIds[charName];
          if (cId) {
            state.edges.push({
              id: uidEdge(), from: cId, to: chNodeId,
              label: '出场',
              arrow: 'forward',
            });
          }
        });
      }
      // 没有人物列表，默认所有人物都在第1章出现
      if (i === 0 && (!ch.characters || !ch.characters.length)) {
        Object.values(charNodeIds).forEach((cId) => {
          state.edges.push({
            id: uidEdge(), from: cId, to: chNodeId,
            label: '出场',
            arrow: 'forward',
          });
        });
      }
    });

    // 3. 章节 → 章节（顺序因果链）
    Object.values(chapterNodeIds).forEach((id, i, arr) => {
      if (i < arr.length - 1) {
        state.edges.push({
          id: uidEdge(), from: id, to: arr[i + 1],
          label: '承接',
          arrow: 'forward',
        });
      }
    });

    pushHistory();
    scheduleSave();
  }

  async function saveToBackend() {
    if (!state.dirty) return;
    try {
      state.meta.last_saved = new Date().toLocaleString('zh-CN');
      state.meta.viewport = state.viewport;
      const payload = {
        nodes: state.nodes,
        edges: state.edges,
        meta: state.meta,
      };
      await fetch('/api/project/planning-cards', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      state.dirty = false;
      updateStatus();
    } catch (e) {
      console.warn('[Wireframe] 保存失败:', e);
    }
  }

  // ═══════════════════════════════════════════
  // 历史记录（撤销/重做）
  // ═══════════════════════════════════════════
  function pushHistory() {
    // 截断未来历史
    state.history = state.history.slice(0, state.historyIndex + 1);
    state.history.push(JSON.stringify({ nodes: state.nodes, edges: state.edges }));
    if (state.history.length > 50) state.history.shift();
    state.historyIndex = state.history.length - 1;
  }

  function undo() {
    if (state.historyIndex <= 0) return;
    state.historyIndex--;
    const snap = JSON.parse(state.history[state.historyIndex]);
    state.nodes = snap.nodes;
    state.edges = snap.edges;
    renderAll();
    scheduleSave();
  }

  function redo() {
    if (state.historyIndex >= state.history.length - 1) return;
    state.historyIndex++;
    const snap = JSON.parse(state.history[state.historyIndex]);
    state.nodes = snap.nodes;
    state.edges = snap.edges;
    renderAll();
    scheduleSave();
  }

  // ═══════════════════════════════════════════
  // 节点CRUD
  // ═══════════════════════════════════════════
  function createNode(x, y, opts) {
    opts = opts || {};
    const node = {
      id: uid(),
      type: opts.type || 'free',
      title: opts.title || '新节点',
      summary: opts.summary || '',
      quotes: opts.quotes || '',
      x: x,
      y: y,
      color: opts.color || NODE_TYPES[opts.type || 'free'].color,
      chapter_ref: opts.chapter_ref || '',
    };
    state.nodes.push(node);
    pushHistory();
    renderAll();
    scheduleSave();
    return node;
  }

  function deleteNode(id) {
    state.nodes = state.nodes.filter(n => n.id !== id);
    // 删除关联连线
    state.edges = state.edges.filter(e => e.from !== id && e.to !== id);
    if (state.selectedNode && state.selectedNode.id === id) state.selectedNode = null;
    pushHistory();
    renderAll();
    scheduleSave();
  }

  function updateNode(id, patch) {
    const n = state.nodes.find(x => x.id === id);
    if (!n) return;
    Object.assign(n, patch);
    pushHistory();
    renderAll();
    scheduleSave();
  }

  // ═══════════════════════════════════════════
  // 连线CRUD
  // ═══════════════════════════════════════════
  function createEdge(fromId, toId, label) {
    // 去重
    if (state.edges.some(e => e.from === fromId && e.to === toId)) return null;
    const edge = {
      id: uidEdge(),
      from: fromId,
      to: toId,
      label: label || '',
      arrow: true,
    };
    state.edges.push(edge);
    pushHistory();
    renderAll();
    scheduleSave();
    return edge;
  }

  function deleteEdge(id) {
    state.edges = state.edges.filter(e => e.id !== id);
    if (state.selectedEdge && state.selectedEdge.id === id) state.selectedEdge = null;
    pushHistory();
    renderAll();
    scheduleSave();
  }

  function updateEdge(id, patch) {
    const e = state.edges.find(x => x.id === id);
    if (!e) return;
    Object.assign(e, patch);
    pushHistory();
    renderAll();
    scheduleSave();
  }

  // ═══════════════════════════════════════════
  // 渲染层
  // ═══════════════════════════════════════════
  function renderAll() {
    if (!canvasGroup) return;
    canvasGroup.innerHTML = '';

    // 应用视口变换
    canvasGroup.setAttribute('transform',
      `translate(${state.viewport.x}, ${state.viewport.y}) scale(${state.viewport.scale})`);

    // 渲染连线（先连线后节点，节点在上层）
    state.edges.forEach(renderEdge);
    // 渲染节点
    state.nodes.forEach(renderNode);

    updateStatus();
  }

  function renderNode(node) {
    const g = document.createElementNS('http://www.w3.org/2000/svg', 'g');
    g.setAttribute('class', 'wf-node');
    g.setAttribute('transform', `translate(${node.x}, ${node.y})`);
    g.dataset.id = node.id;

    const isSelected = state.selectedNode && state.selectedNode.id === node.id;
    const w = 180, h = 80;

    // 卡片背景
    const rect = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
    rect.setAttribute('width', w);
    rect.setAttribute('height', h);
    rect.setAttribute('rx', 8);
    rect.setAttribute('fill', '#ffffff');
    rect.setAttribute('stroke', isSelected ? '#ef4444' : node.color);
    rect.setAttribute('stroke-width', isSelected ? 3 : 2);
    g.appendChild(rect);

    // 类型色条
    const bar = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
    bar.setAttribute('width', 4);
    bar.setAttribute('height', h);
    bar.setAttribute('fill', node.color);
    bar.setAttribute('rx', 2);
    g.appendChild(bar);

    // 标题
    const title = document.createElementNS('http://www.w3.org/2000/svg', 'text');
    title.setAttribute('x', 14);
    title.setAttribute('y', 22);
    title.setAttribute('font-size', 13);
    title.setAttribute('font-weight', 'bold');
    title.setAttribute('fill', '#1f2937');
    const titleText = node.title.length > 14 ? node.title.slice(0, 14) + '…' : node.title;
    title.textContent = titleText;
    g.appendChild(title);

    // 摘要
    if (node.summary) {
      const sum = document.createElementNS('http://www.w3.org/2000/svg', 'text');
      sum.setAttribute('x', 14);
      sum.setAttribute('y', 42);
      sum.setAttribute('font-size', 11);
      sum.setAttribute('fill', '#6b7280');
      const sumText = node.summary.length > 20 ? node.summary.slice(0, 20) + '…' : node.summary;
      sum.textContent = sumText;
      g.appendChild(sum);
    }

    // 章节引用
    if (node.chapter_ref) {
      const ref = document.createElementNS('http://www.w3.org/2000/svg', 'text');
      ref.setAttribute('x', 14);
      ref.setAttribute('y', 64);
      ref.setAttribute('font-size', 10);
      ref.setAttribute('fill', '#9ca3af');
      ref.textContent = '@' + node.chapter_ref;
      g.appendChild(ref);
    }

    // 校验状态标记（只要有检测结果就渲染，推演后自动检测在 plan 模式下也能看到标红）
    if (state.checkResults[node.id]) {
      const st = state.checkResults[node.id];
      const badgeColors = {
        consistent: '#10b981',
        needs_update: '#ef4444',
        uninvolved: '#9ca3af',
      };
      const badge = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
      badge.setAttribute('cx', w - 10);
      badge.setAttribute('cy', 10);
      badge.setAttribute('r', 6);
      badge.setAttribute('fill', badgeColors[st] || '#9ca3af');
      g.appendChild(badge);
    }

    // 事件绑定
    g.addEventListener('mousedown', onNodeMouseDown.bind(null, node));
    g.addEventListener('dblclick', onNodeDoubleClick.bind(null, node));
    g.addEventListener('contextmenu', onNodeContextMenu.bind(null, node));

    canvasGroup.appendChild(g);
  }

  function renderEdge(edge) {
    const from = state.nodes.find(n => n.id === edge.from);
    const to = state.nodes.find(n => n.id === edge.to);
    if (!from || !to) return;

    // 贝塞尔曲线起止点（卡片边缘中点）
    const x1 = from.x + 90, y1 = from.y + 40;
    const x2 = to.x + 90, y2 = to.y + 40;
    const mx = (x1 + x2) / 2, my = (y1 + y2) / 2;
    // 贝塞尔控制点
    const cx1 = x1, cy1 = my;
    const cx2 = x2, cy2 = my;
    const path = `M ${x1} ${y1} C ${cx1} ${cy1}, ${cx2} ${cy2}, ${x2} ${y2}`;

    const isSelected = state.selectedEdge && state.selectedEdge.id === edge.id;

    const g = document.createElementNS('http://www.w3.org/2000/svg', 'g');
    g.setAttribute('class', 'wf-edge');
    g.dataset.id = edge.id;
    g.style.cursor = 'pointer';

    const p = document.createElementNS('http://www.w3.org/2000/svg', 'path');
    p.setAttribute('d', path);
    p.setAttribute('fill', 'none');
    p.setAttribute('stroke', isSelected ? '#ef4444' : '#9ca3af');
    p.setAttribute('stroke-width', isSelected ? 3 : 2);
    p.setAttribute('marker-end', 'url(#wf-arrow)');
    g.appendChild(p);

    // 标签
    if (edge.label) {
      const labelBg = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
      const labelText = document.createElementNS('http://www.w3.org/2000/svg', 'text');
      labelText.setAttribute('x', mx);
      labelText.setAttribute('y', my);
      labelText.setAttribute('font-size', 11);
      labelText.setAttribute('text-anchor', 'middle');
      labelText.setAttribute('fill', '#374151');
      labelText.textContent = edge.label.length > 8 ? edge.label.slice(0, 8) + '…' : edge.label;
      g.appendChild(labelBg);
      g.appendChild(labelText);
    }

    g.addEventListener('click', onEdgeClick.bind(null, edge));
    g.addEventListener('contextmenu', onEdgeContextMenu.bind(null, edge));

    canvasGroup.appendChild(g);
  }

  function updateStatus() {
    if (!statusEl) return;
    const saved = state.meta.last_saved || '未保存';
    const checkCount = state.mode === 'compare'
      ? Object.values(state.checkResults).filter(v => v === 'needs_update').length
      : 0;
    const checkInfo = state.mode === 'compare' && Object.keys(state.checkResults).length > 0
      ? ` | ⚠️需更新:${checkCount}` : '';
    statusEl.textContent = `节点:${state.nodes.length} | 连线:${state.edges.length} | ${saved}${checkInfo}`;
  }

  // ═══════════════════════════════════════════
  // 交互层
  // ═══════════════════════════════════════════

  // 节点拖拽
  function onNodeMouseDown(node, e) {
    if (e.button !== 0) return;
    e.stopPropagation();

    // 连线模式
    if (state.connectMode) {
      if (!state.connectFrom) {
        state.connectFrom = node;
        showToast('选择目标节点完成连线');
      } else if (state.connectFrom.id !== node.id) {
        const label = prompt('连线标签（如：伏笔埋设/因果/感情线，可留空）:', '');
        if (label !== null) createEdge(state.connectFrom.id, node.id, label);
        state.connectFrom = null;
        state.connectMode = false;
        document.getElementById('wf-connect-btn') && (document.getElementById('wf-connect-btn').classList.remove('active'));
      }
      return;
    }

    state.selectedNode = node;
    state.selectedEdge = null;
    state.draggingNode = node;
    const pos = screenToCanvas(e.clientX, e.clientY);
    state.dragOffset = { x: pos.x - node.x, y: pos.y - node.y };
    renderAll();

    // compare模式下点击章节节点，对照面板跟随显示该章正文
    if (state.mode === 'compare' && node.type === 'chapter' && node.chapter_ref) {
      const panel = document.getElementById('wf-compare-panel');
      if (panel && panel.style.display !== 'none') {
        loadChapterToComparePanel(node);
      }
    }
  }

  function onNodeDoubleClick(node, e) {
    e.stopPropagation();
    openNodeEditor(node);
  }

  function onNodeContextMenu(node, e) {
    e.preventDefault();
    e.stopPropagation();
    state.selectedNode = node;
    showContextMenu(e.clientX, e.clientY, 'node');
    renderAll();
  }

  function onEdgeClick(edge, e) {
    e.stopPropagation();
    state.selectedEdge = edge;
    state.selectedNode = null;
    renderAll();
  }

  function onEdgeContextMenu(edge, e) {
    e.preventDefault();
    e.stopPropagation();
    state.selectedEdge = edge;
    showContextMenu(e.clientX, e.clientY, 'edge');
    renderAll();
  }

  // 画布事件（空白处）
  function onCanvasMouseDown(e) {
    if (e.target !== svgEl && e.target.tagName !== 'rect' && e.target.tagName !== 'svg') return;
    if (e.button === 0) {
      // 左键：平移或框选
      if (e.shiftKey) {
        // Shift框选
        state.boxSelecting = true;
        state.boxSelectStart = screenToCanvas(e.clientX, e.clientY);
      } else {
        state.panning = true;
        state.panStart = { x: e.clientX - state.viewport.x, y: e.clientY - state.viewport.y };
      }
      // 取消选择
      state.selectedNode = null;
      state.selectedEdge = null;
      hideContextMenu();
      renderAll();
    }
  }

  function onMouseMove(e) {
    if (state.draggingNode) {
      const pos = screenToCanvas(e.clientX, e.clientY);
      state.draggingNode.x = pos.x - state.dragOffset.x;
      state.draggingNode.y = pos.y - state.dragOffset.y;
      renderAll();
    } else if (state.panning) {
      state.viewport.x = e.clientX - state.panStart.x;
      state.viewport.y = e.clientY - state.panStart.y;
      renderAll();
    }
  }

  function onMouseUp(e) {
    if (state.draggingNode) {
      scheduleSave();
    }
    state.draggingNode = null;
    state.panning = false;
    state.boxSelecting = false;
  }

  // 滚轮缩放
  function onWheel(e) {
    e.preventDefault();
    const delta = e.deltaY > 0 ? 0.9 : 1.1;
    const newScale = Math.max(0.2, Math.min(3, state.viewport.scale * delta));
    // 以鼠标位置为中心缩放
    const rect = svgEl.getBoundingClientRect();
    const mx = e.clientX - rect.left;
    const my = e.clientY - rect.top;
    state.viewport.x = mx - (mx - state.viewport.x) * (newScale / state.viewport.scale);
    state.viewport.y = my - (my - state.viewport.y) * (newScale / state.viewport.scale);
    state.viewport.scale = newScale;
    renderAll();
  }

  // 画布空白双击→新建节点
  function onCanvasDoubleClick(e) {
    if (e.target !== svgEl && e.target.tagName !== 'svg') return;
    const pos = screenToCanvas(e.clientX, e.clientY);
    const node = createNode(pos.x, pos.y);
    state.selectedNode = node;
    openNodeEditor(node);
  }

  // 画布右键→新建菜单
  function onCanvasContextMenu(e) {
    if (e.target !== svgEl && e.target.tagName !== 'svg' && e.target.tagName !== 'rect') return;
    // 只在纯空白处触发（rect是网格背景）
    e.preventDefault();
    state.contextMenuPos = screenToCanvas(e.clientX, e.clientY);
    showContextMenu(e.clientX, e.clientY, 'canvas');
  }

  // 键盘
  function onKeyDown(e) {
    if (!overlay || overlay.style.display === 'none') return;
    if (e.key === 'Delete' || e.key === 'Backspace') {
      if (state.selectedNode) {
        deleteNode(state.selectedNode.id);
      } else if (state.selectedEdge) {
        deleteEdge(state.selectedEdge.id);
      }
    } else if (e.key === 'Escape') {
      state.connectMode = false;
      state.connectFrom = null;
      state.selectedNode = null;
      state.selectedEdge = null;
      hideContextMenu();
      renderAll();
    } else if ((e.ctrlKey || e.metaKey) && e.key === 'z') {
      e.preventDefault();
      if (e.shiftKey) redo(); else undo();
    }
  }

  // ═══════════════════════════════════════════
  // 节点编辑器
  // ═══════════════════════════════════════════
  function openNodeEditor(node) {
    const editor = document.getElementById('wf-node-editor');
    if (!editor) return;
    document.getElementById('wf-edit-title').value = node.title || '';
    document.getElementById('wf-edit-summary').value = node.summary || '';
    document.getElementById('wf-edit-quotes').value = node.quotes || '';
    document.getElementById('wf-edit-ref').value = node.chapter_ref || '';
    document.getElementById('wf-edit-type').value = node.type || 'free';
    editor.style.display = 'flex';
    editor.dataset.nodeId = node.id;
  }

  function saveNodeEditor() {
    const editor = document.getElementById('wf-node-editor');
    if (!editor) return;
    const id = editor.dataset.nodeId;
    const type = document.getElementById('wf-edit-type').value;
    updateNode(id, {
      title: document.getElementById('wf-edit-title').value.trim() || '未命名',
      summary: document.getElementById('wf-edit-summary').value.trim(),
      quotes: document.getElementById('wf-edit-quotes').value.trim(),
      chapter_ref: document.getElementById('wf-edit-ref').value.trim(),
      type: type,
      color: NODE_TYPES[type].color,
    });
    editor.style.display = 'none';
  }

  // ═══════════════════════════════════════════
  // 右键菜单
  // ═══════════════════════════════════════════
  function showContextMenu(clientX, clientY, targetType) {
    hideContextMenu();
    const menu = contextMenuEl;
    if (!menu) return;
    menu.innerHTML = '';

    const items = [];
    if (targetType === 'canvas') {
      items.push({ label: '➕ 新建节点', action: () => {
        const node = createNode(state.contextMenuPos.x, state.contextMenuPos.y);
        state.selectedNode = node;
        openNodeEditor(node);
      }});
    } else if (targetType === 'node') {
      items.push({ label: '✏️ 编辑节点', action: () => openNodeEditor(state.selectedNode) });
      items.push({ label: '🎨 修改颜色', action: () => {
        const type = prompt('选择类型：character/foreshadow/chapter/worldview/free', state.selectedNode.type);
        if (type && NODE_TYPES[type]) updateNode(state.selectedNode.id, { type, color: NODE_TYPES[type].color });
      }});
      items.push({ label: '🗑️ 删除节点', action: () => deleteNode(state.selectedNode.id) });
      if (state.mode === 'compare') {
        items.push({ label: '📋 查看相关段落', action: () => checkNodeConsistency(state.selectedNode) });
      }
    } else if (targetType === 'edge') {
      items.push({ label: '✏️ 编辑标签', action: () => {
        const label = prompt('连线标签:', state.selectedEdge.label || '');
        if (label !== null) updateEdge(state.selectedEdge.id, { label });
      }});
      items.push({ label: '🗑️ 删除连线', action: () => deleteEdge(state.selectedEdge.id) });
      if (state.mode === 'compare') {
        items.push({ label: '📋 对照正文', action: () => checkEdgeConsistency(state.selectedEdge) });
      }
    }

    items.forEach(item => {
      const div = document.createElement('div');
      div.className = 'wf-ctx-item';
      div.textContent = item.label;
      div.onclick = () => { item.action(); hideContextMenu(); };
      menu.appendChild(div);
    });

    menu.style.display = 'block';
    menu.style.left = clientX + 'px';
    menu.style.top = clientY + 'px';
  }

  function hideContextMenu() {
    if (contextMenuEl) contextMenuEl.style.display = 'none';
  }

  // ═══════════════════════════════════════════
  // 对照校验（compare模式核心）
  // ═══════════════════════════════════════════

  /**
   * 全局不一致检测：扫描所有节点，AI判断与正文的匹配度
   * 调用后端 /api/project/planning-check，若AI不可用则前端关键词兜底
   *
   * 对齐规则：带 chapter_ref 的节点按其引用章节取正文对照（避免拿第3章的
   * 伏笔去跟第9章比导致误判 uninvolved），无引用的节点用当前章。
   */
  async function runGlobalCheck() {
    if (state.nodes.length === 0) {
      showToast('画布为空，无可检测内容');
      return;
    }
    showToast('正在检测设定一致性...');
    try {
      // ── 按对照章节给节点分组 ──
      const curIdx = getCurrentChapterIndex();
      const groups = {}; // idx -> [nodes]
      state.nodes.forEach(node => {
        let idx = curIdx;
        if (node.chapter_ref) {
          const refIdx = findChapterIndexByRef(node.chapter_ref);
          if (refIdx >= 0) idx = refIdx;
        }
        (groups[idx] = groups[idx] || []).push(node);
      });

      // 每组取正文：缓存优先，无则重拉一次 /api/chapters
      let fresh = null;
      const textOf = (idx) => {
        let t = chapterText(getChapters()[idx]);
        if (t.trim().length > 50) return t.trim();
        if (fresh === null) {
          fresh = []; // 只拉一次
          return '';
        }
        t = chapterText(fresh[idx]);
        return t.trim().length > 50 ? t.trim() : '';
      };

      let results = {};
      let usedAI = false;
      let checkedChapters = 0;

      for (const idxStr of Object.keys(groups)) {
        const idx = parseInt(idxStr, 10);
        let text = textOf(idx);
        if (!text && fresh && fresh.length === 0) {
          try {
            const resp = await fetch('/api/chapters');
            if (resp.ok) fresh = (await resp.json()).chapters || [];
          } catch (e) {}
          text = textOf(idx);
        }
        if (!text && idx === curIdx) {
          // 当前章无正文：兜底找任意有内容的章节（与旧行为一致）
          text = await getCurrentChapterText();
        }
        if (!text) {
          // 引用章节无有效正文，无从对照 → 标未涉及（不得误报 needs_update）
          groups[idxStr].forEach(n => { results[n.id] = 'uninvolved'; });
          continue;
        }
        checkedChapters++;

        let groupResults = null;
        try {
          const controller = new AbortController();
          const timeout = setTimeout(() => controller.abort(), 30000);
          const resp = await fetch('/api/project/planning-check', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              nodes: groups[idxStr],
              edges: idx === curIdx ? state.edges : [],
              chapter_text: text,
            }),
            signal: controller.signal,
          });
          clearTimeout(timeout);
          const res = await resp.json();
          if (res && res.ok && res.results && Object.keys(res.results).length > 0) {
            groupResults = res.results;
            usedAI = true;
          }
        } catch (e) {
          console.warn('[Wireframe] AI检测失败，使用前端兜底:', e.message);
        }

        // AI 无结果时关键词兜底（逐组，用该组自己的正文）
        if (!groupResults) {
          groupResults = {};
          const lowerText = text.toLowerCase();
          groups[idxStr].forEach(node => {
            const title = (node.title || '').toLowerCase();
            const summary = (node.summary || '').toLowerCase();
            const chapterRef = (node.chapter_ref || '').toLowerCase();
            const nodeType = (node.type || '').toLowerCase();

            const searchTerms = [
              ...title.split(/[\s·\-_【】\[\]()（）]+/).filter(t => t.length >= 2),
              ...summary.split(/[\s,，。.!！?？；;:：、\(\)（）\[\]【】"'']+/).filter(t => t.length >= 2 && t.length <= 20),
            ].slice(0, 8);

            let matchCount = 0;
            searchTerms.forEach(term => {
              if (lowerText.indexOf(term) >= 0) matchCount++;
            });

            if (nodeType === 'chapter' && chapterRef) {
              // 节点引用的就是本章 → 至少是有关联的，按标题匹配判一致/未涉及
              const chapterMatch = lowerText.indexOf(chapterRef) >= 0 ||
                                   lowerText.indexOf(title.replace(/第.章·?/, '')) >= 0;
              groupResults[node.id] = chapterMatch ? 'consistent' : 'uninvolved';
            } else if (matchCount >= 2) {
              groupResults[node.id] = 'consistent';
            } else if (matchCount === 1 && searchTerms.length <= 3) {
              groupResults[node.id] = 'consistent';
            } else if (matchCount === 0 && searchTerms.length > 0) {
              groupResults[node.id] = 'needs_update';
            } else {
              groupResults[node.id] = 'uninvolved';
            }
          });
        }
        Object.assign(results, groupResults);
      }

      state.checkResults = results;
      renderAll();

      const needsUpdate = Object.values(results).filter(v => v === 'needs_update').length;
      const consistent = Object.values(results).filter(v => v === 'consistent').length;
      const uninvolved = Object.values(results).filter(v => v === 'uninvolved').length;
      const chapterInfo = checkedChapters > 1 ? `（对照${checkedChapters}个章节）` : '';
      showToast(`检测完成：${consistent} 一致，${needsUpdate} 需更新，${uninvolved} 未涉及${usedAI ? '（AI）' : '（关键词）'}${chapterInfo}`);
      updateCheckBadge(needsUpdate);

    } catch (e) {
      console.error('[Wireframe] 对照检测失败:', e);
      showToast('对照检测失败: ' + e.message);
    }
  }

  // 单节点对照
  async function checkNodeConsistency(node) {
    showToast('正在检测节点「' + node.title + '」...');
    try {
      // 节点带章节引用时优先用对应章的正文，否则回退到当前章
      const chapterText = getChapterTextByRef(node.chapter_ref) || await getCurrentChapterText();
      const resp = await fetch('/api/project/planning-check', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          nodes: [node],
          edges: [],
          chapter_text: chapterText,
        }),
      });
      const res = await resp.json();
      if (res && res.ok && res.results && res.results[node.id]) {
        state.checkResults[node.id] = res.results[node.id];
        renderAll();
        const statusMap = { consistent: '✅ 已一致', needs_update: '⚠️ 需更新', uninvolved: '⬜ 未涉及' };
        showToast('「' + node.title + '」: ' + statusMap[res.results[node.id]]);
        // 在对照面板显示相关段落
        if (state.mode === 'compare') showInComparePanel(node, res.results[node.id]);
      }
    } catch (e) {
      showToast('检测失败: ' + e.message);
    }
  }

  // 连线对照
  async function checkEdgeConsistency(edge) {
    const from = state.nodes.find(n => n.id === edge.from);
    const to = state.nodes.find(n => n.id === edge.to);
    if (!from || !to) return;
    showToast('正在检测「' + from.title + '→' + to.title + '」...');
    try {
      const chapterText = await getCurrentChapterText();
      const resp = await fetch('/api/project/planning-check', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          nodes: [from, to],
          edges: [edge],
          chapter_text: chapterText,
        }),
      });
      const res = await resp.json();
      if (res && res.ok && res.detail) {
        showInComparePanel({ from, to, edge }, 'edge', res.detail);
      }
    } catch (e) {
      showToast('检测失败: ' + e.message);
    }
  }

  function updateCheckBadge(count) {
    const badge = document.getElementById('wf-check-badge');
    if (badge) {
      badge.style.display = count > 0 ? 'flex' : 'none';
      badge.textContent = count;
    }
  }

  // 获取当前章节正文（直接读后端已保存数据，绝不触发AI生成）
  // 若当前章节无有效正文，自动查找其他有内容的章节
  async function getCurrentChapterText() {
    try {
      const idx = getCurrentChapterIndex();
      if (idx < 0) return '';

      const GENERATING_PATTERN = /^(⏳|⌛)?\s*(AI|ai|系统)?\s*(正在|正在生成|正在写作|生成中)/;

      const isValidText = function(text) {
        if (!text || typeof text !== 'string') return false;
        const trimmed = text.trim();
        if (trimmed.length < 50) return false;
        if (GENERATING_PATTERN.test(trimmed)) return false;
        if (trimmed.indexOf('预计需要') >= 0) return false;
        if (trimmed.indexOf('请稍候') >= 0 && trimmed.length < 100) return false;
        return true;
      };

      // 尝试获取指定章节正文（正文在 narrative 字段）
      const tryGetChapter = async function(i) {
        const t = chapterText(getChapters()[i]);
        if (isValidText(t)) {
          return t.trim();
        }
        try {
          const resp = await fetch('/api/chapters');
          if (resp.ok) {
            const res = await resp.json();
            const text = chapterText((res.chapters || [])[i]);
            if (isValidText(text)) return text.trim();
          }
        } catch (e) {}
        return '';
      };

      // 先尝试当前章节
      let text = await tryGetChapter(idx);
      if (text) return text;

      // 兜底：遍历其他章节找有效正文
      if (getChapters().length > 0) {
        for (let i = 0; i < getChapters().length; i++) {
          if (i === idx) continue;
          text = await tryGetChapter(i);
          if (text) return text;
        }
      }

      return '';
    } catch (e) {
      return '';
    }
  }

  // 在对照面板显示
  function showInComparePanel(node, status, detail) {
    if (!comparePanelEl) return;
    const statusMap = {
      consistent: { text: '已一致', color: '#10b981' },
      needs_update: { text: '需更新', color: '#ef4444' },
      uninvolved: { text: '未涉及', color: '#9ca3af' },
    };
    if (node.from) {
      // 连线对照
      comparePanelEl.innerHTML = `
        <div style="padding:12px;border-bottom:1px solid var(--border)">
          <strong>🔗 连线对照</strong><br>
          <span style="color:${NODE_TYPES[node.from.type]?.color || '#666'}">${node.from.title}</span>
          → <span style="color:${NODE_TYPES[node.to.type]?.color || '#666'}">${node.to.title}</span>
          <br><small>标签：${node.edge.label || '无'}</small>
        </div>
        <div style="padding:12px;font-size:13px;line-height:1.6">${detail || '无详细信息'}</div>
      `;
    } else {
      const s = statusMap[status] || statusMap.uninvolved;
      comparePanelEl.innerHTML = `
        <div style="padding:12px;border-bottom:1px solid var(--border)">
          <strong>📋 ${node.title}</strong>
          <span style="float:right;color:${s.color};font-weight:bold">${s.text}</span>
        </div>
        <div style="padding:12px;font-size:13px;line-height:1.6">
          ${node.summary || '无摘要'}<br><br>
          ${node.quotes ? '<strong>关键引用：</strong><br>' + node.quotes : ''}
        </div>
      `;
    }
  }

  // 联动C5：唤起协作草稿AI改写
  function invokeC5Rewrite(nodeId) {
    const node = state.nodes.find(n => n.id === nodeId);
    if (!node) return;
    showToast('已将节点「' + (node.title || '') + '」的设定上下文发送到 DM 干预面板');
    fetch('/api/dm/inject', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        type: 'inject_event',
        description: '[连线框联动] 节点: ' + (node.title || '') + ' — ' + (node.summary || '无摘要')
      })
    }).catch(e => console.warn('[Wireframe] DM注入失败:', e));
  }

  // ═══════════════════════════════════════════
  // 素材库
  // ═══════════════════════════════════════════
  function buildAssetLibrary() {
    const lib = document.getElementById('wf-asset-lib');
    if (!lib) return;
    lib.innerHTML = '';

    // 人物
    const chars = getCharacters();
    chars.forEach(c => {
      addAssetItem(lib, 'character', c.name || c.title || '未命名', c);
    });

    // 伏笔
    try {
      const hooks = getHooks();
      hooks.forEach(h => {
        addAssetItem(lib, 'foreshadow', (h.content || '').slice(0, 12), h);
      });
    } catch (e) {}

    // 章节
    try {
      const chs = getChapters();
      chs.forEach((ch, i) => {
        const ref = '第' + chapterNum(ch, i) + '章';
        addAssetItem(lib, 'chapter', ref + ' ' + (ch.title || ''), { chapter_ref: ref });
      });
    } catch (e) {}

    // 世界观
    try {
      const ws = getWorldSettings();
      ws.forEach(s => {
        addAssetItem(lib, 'worldview', s.key || '设定', s);
      });
    } catch (e) {}
  }

  function addAssetItem(lib, type, label, data) {
    const item = document.createElement('div');
    item.className = 'wf-asset-item';
    item.draggable = true;
    item.style.borderLeftColor = NODE_TYPES[type].color;
    item.textContent = label;
    item.dataset.type = type;
    item.dataset.data = JSON.stringify(data);
    item.addEventListener('dragstart', (e) => {
      e.dataTransfer.setData('text/plain', JSON.stringify({ type, data }));
    });
    // compare模式下点击章节素材，对照面板切换到该章正文
    if (type === 'chapter' && data.chapter_ref) {
      item.style.cursor = 'pointer';
      item.addEventListener('click', () => {
        if (state.mode !== 'compare') return;
        loadChapterToComparePanel({ chapter_ref: data.chapter_ref });
      });
    }
    lib.appendChild(item);
  }

  // 素材拖拽到画布
  function onCanvasDrop(e) {
    e.preventDefault();
    const raw = e.dataTransfer.getData('text/plain');
    if (!raw) return;
    try {
      const { type, data } = JSON.parse(raw);
      const pos = screenToCanvas(e.clientX, e.clientY);
      const title = type === 'character' ? (data.name || data.title || '人物')
        : type === 'chapter' ? (data.chapter_ref || '章节')
        : data.key || data.content || '节点';
      createNode(pos.x, pos.y, {
        type,
        title: title.slice(0, 20),
        summary: (data.content || data.description || '').slice(0, 60),
        chapter_ref: data.chapter_ref || '',
      });
    } catch (err) {
      console.warn('[Wireframe] 拖拽解析失败:', err);
    }
  }

  // ═══════════════════════════════════════════
  // 工具栏动作
  // ═══════════════════════════════════════════
  function toolbarNew() {
    const cx = (svgEl.clientWidth / 2 - state.viewport.x) / state.viewport.scale;
    const cy = (svgEl.clientHeight / 2 - state.viewport.y) / state.viewport.scale;
    const node = createNode(cx, cy);
    state.selectedNode = node;
    openNodeEditor(node);
  }

  function toggleConnectMode() {
    state.connectMode = !state.connectMode;
    state.connectFrom = null;
    const btn = document.getElementById('wf-connect-btn');
    if (btn) btn.classList.toggle('active', state.connectMode);
    showToast(state.connectMode ? '连线模式：先点起点节点，再点终点节点' : '已退出连线模式');
  }

  function zoomIn() {
    state.viewport.scale = Math.min(3, state.viewport.scale * 1.2);
    renderAll();
  }
  function zoomOut() {
    state.viewport.scale = Math.max(0.2, state.viewport.scale * 0.8);
    renderAll();
  }
  function zoomReset() {
    state.viewport = { x: 0, y: 0, scale: 1 };
    renderAll();
  }

  function exportImage() {
    if (!svgEl) return;
    const xml = new XMLSerializer().serializeToString(svgEl);
    const blob = new Blob([xml], { type: 'image/svg+xml' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'wireframe-' + Date.now() + '.svg';
    a.click();
    URL.revokeObjectURL(url);
    showToast('已导出SVG');
  }

  function toggleCompare() {
    const panel = document.getElementById('wf-compare-panel');
    if (panel) {
      const show = panel.style.display === 'none';
      panel.style.display = show ? 'flex' : 'none';
      state.mode = show ? 'compare' : 'plan';  // 同步模式，否则徽标/状态栏判断与实际面板脱节
      renderAll();
      if (show) {
        // 加载当前章节正文到对照面板
        loadChapterToComparePanel();
      }
    }
  }

  // 按章节引用定位章节数组下标（找不到返回 -1）
  // 单一事实来源：getChapterTextByRef 与 loadChapterToComparePanel 共用，
  // 避免两处各自推导导致下标/编号错位
  function findChapterIndexByRef(ref) {
    const num = parseChapterRefNumber(ref);
    if (num <= 0) return -1;
    const chs = getChapters();
    let idx = chs.findIndex(c => c.chapter === num);
    if (idx < 0 && num <= chs.length) idx = num - 1;
    return idx;
  }

  // 按章节引用取对应正文（找不到或无有效正文时返回空串）
  function getChapterTextByRef(ref) {
    const idx = findChapterIndexByRef(ref);
    if (idx < 0) return '';
    const t = chapterText(getChapters()[idx]);
    return t.trim().length > 50 ? t.trim() : '';
  }

  // 解析章节引用中的编号：支持“第4章”“第七章”“第12章”等写法
  function parseChapterRefNumber(ref) {
    if (!ref) return 0;
    const m = String(ref).match(/第\s*([0-9０-９]+)\s*章/);
    if (m) return parseInt(m[1], 10) || 0;
    const CM = { '零': 0, '一': 1, '二': 2, '三': 3, '四': 4, '五': 5, '六': 6, '七': 7, '八': 8, '九': 9 };
    const mc = String(ref).match(/第\s*([零一二三四五六七八九十百]+)\s*章/);
    if (!mc) return 0;
    const s = mc[1];
    if (s === '十') return 10;
    const tens = s.indexOf('十');
    if (tens >= 0) {
      const t = tens === 0 ? 1 : (CM[s.slice(0, tens)] || 0);
      const rest = s.slice(tens + 1);
      return t * 10 + (rest ? (CM[rest] || 0) : 0);
    }
    if (s.length === 1) return CM[s] || 0;
    return 0;
  }

  async function loadChapterToComparePanel(node) {
    if (!comparePanelEl) return;

    let text = '';
    let usedIdx = -1;

    // 优先：点击了章节节点时，按 chapter_ref 定位到对应章节（而不是世界状态的“当前章”）
    if (node && node.chapter_ref) {
      const idx = findChapterIndexByRef(node.chapter_ref);
      if (idx >= 0) {
        const t = chapterText(getChapters()[idx]);
        if (t.trim().length > 50) {
          text = t.trim();
          usedIdx = idx;
        }
      }
    }

    // 否则回退到当前章节
    if (!text) {
      text = await getCurrentChapterText();
      usedIdx = getCurrentChapterIndex();
    }

    // 如果当前章节无有效正文，遍历寻找第一个有内容的章节
    if (!text && getChapters().length > 0) {
      comparePanelEl.innerHTML = '<div style="padding:16px;color:var(--muted);font-size:12px">当前章节暂无有效正文，正在加载其他有内容的章节…</div>';
      // 从第1章开始（第0章可能是生成中）
      for (let i = 0; i < getChapters().length; i++) {
        if (i === getCurrentChapterIndex()) continue;
        const ch = getChapters()[i];
        const chText = chapterText(ch);
        if (chText.trim().length > 100 && !/AI正在生成|预计需要/.test(chText)) {
          text = chText.trim();
          usedIdx = i;
          break;
        }
      }
      // 如果缓存没有，重新拉后端
      if (!text) {
        try {
          const resp = await fetch('/api/chapters');
          const fresh = resp.ok ? ((await resp.json()).chapters || []) : [];
          for (let i = 0; i < fresh.length; i++) {
            if (i === getCurrentChapterIndex()) continue;
            const chText = chapterText(fresh[i]);
            if (chText.trim().length > 100
                && !/AI正在生成|预计需要/.test(chText)) {
              text = chText.trim();
              usedIdx = i;
              break;
            }
          }
        } catch(e) {}
      }
    }

    if (!text) {
      comparePanelEl.innerHTML = `
        <div style="padding:16px;color:var(--muted);font-size:12px;line-height:1.7">
          <div style="font-weight:600;color:var(--ink);margin-bottom:8px">📋 正文对照</div>
          <div style="margin-bottom:12px">所有章节均暂无有效正文内容。</div>
          <div style="opacity:0.8">请先在步骤6（写作）中完成章节正文生成。</div>
        </div>`;
      return;
    }

    // 显示章节编号 + 标题 + 正文（编号取后端真实 chapter 字段，避免下标推导错位）
    const usedCh = getChapters()[usedIdx];
    const chNum = usedCh ? chapterNum(usedCh, usedIdx) : (usedIdx + 1);
    const chTitle = (usedCh && usedCh.title) ? ('第' + chNum + '章 ' + usedCh.title) : ('第' + chNum + '章');
    const header = `<div style="padding:10px 12px;border-bottom:1px solid var(--border);background:var(--surface);font-size:12px;color:var(--muted)">📖 ${chTitle} · 正文对照</div>`;

    // 按段落分割
    const paras = text.split(/\n\s*\n/).filter(p => p.trim());
    const body = paras.map((p, i) =>
      `<div class="wf-para" data-idx="${i}" style="padding:10px 12px;border-bottom:1px solid var(--border);font-size:13px;line-height:1.7;cursor:pointer">${p.replace(/</g, '&lt;').slice(0, 200)}${p.length > 200 ? '…' : ''}</div>`
    ).join('');

    comparePanelEl.innerHTML = header + body;

    // 点击段落定位
    comparePanelEl.querySelectorAll('.wf-para').forEach(el => {
      el.addEventListener('click', () => {
        comparePanelEl.querySelectorAll('.wf-para').forEach(x => x.classList.remove('selected'));
        el.classList.add('selected');
      });
    });
  }

  // ═══════════════════════════════════════════
  // Toast
  // ═══════════════════════════════════════════
  function showToast(msg) {
    if (typeof global.showToast === 'function') global.showToast(msg);
    else if (typeof window.showToast === 'function') window.showToast(msg);
    else console.log('[Wireframe]', msg);
  }

  // ═══════════════════════════════════════════
  // 首次教学
  // ═══════════════════════════════════════════
  let tutorialBound = false;
  function showTutorial() {
    const key = 'wf_tutorial_done';
    if (localStorage.getItem(key)) return;
    const tut = document.getElementById('wf-tutorial');
    if (!tut) return;

    tut.style.display = 'flex';

    // 只绑定一次事件
    if (!tutorialBound) {
      tutorialBound = true;

      const closeHandler = () => {
        tut.style.display = 'none';
        const noshow = document.getElementById('wf-tut-noshow');
        if (noshow && noshow.checked) {
          localStorage.setItem(key, '1');
        }
      };

      const closeBtn = document.getElementById('wf-tut-close');
      if (closeBtn) {
        closeBtn.addEventListener('click', closeHandler);
      }

      // 点击遮罩层关闭
      tut.addEventListener('click', (e) => {
        if (e.target === tut) closeHandler();
      });

      // ESC键关闭
      document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' && tut.style.display === 'flex') {
          closeHandler();
        }
      });
    }
  }

  // ═══════════════════════════════════════════
  // 主入口
  // ═══════════════════════════════════════════

  /**
   * 打开连线框
   * @param {string} mode - 'plan' 规划模式（纯画布） | 'compare' 对照模式（双屏）
   */
  async function openWireframe(mode) {
    mode = mode || 'plan';
    state.mode = mode;
    overlay = document.getElementById('wf-overlay');
    if (!overlay) {
      console.error('[Wireframe] overlay元素不存在');
      return;
    }

    // 模式切换UI
    const comparePanel = document.getElementById('wf-compare-panel');
    if (comparePanel) {
      comparePanel.style.display = mode === 'compare' ? 'flex' : 'none';
    }

    overlay.style.display = 'flex';

    // 获取DOM引用
    svgEl = document.getElementById('wf-svg');
    canvasGroup = document.getElementById('wf-canvas-group');
    statusEl = document.getElementById('wf-status');
    contextMenuEl = document.getElementById('wf-context-menu');
    comparePanelEl = document.getElementById('wf-compare-content');

    // 箭头marker定义
    if (!document.getElementById('wf-arrow')) {
      const defs = document.createElementNS('http://www.w3.org/2000/svg', 'defs');
      defs.innerHTML = `<marker id="wf-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z" fill="#9ca3af"/></marker>`;
      svgEl.appendChild(defs);
    }

    // 刷新数据缓存
    await refreshCache();

    // 加载数据
    await loadFromBackend();

    // 如果画布为空，自动从项目数据生成
    if (state.nodes.length === 0) {
      autoGenerateFromProject();
    }

    // 绑定事件（确保只绑一次）
    bindEvents();

    // 构建素材库
    buildAssetLibrary();

    // 渲染
    renderAll();

    // 消费外部跳转聚焦（画布未打开时由 focusNode/focusNodeByRef 登记，
    // 必须等数据加载完成后再定位，否则高亮会被 loadFromBackend 的重渲染覆盖）
    if (pendingFocus) {
      const pf = pendingFocus;
      pendingFocus = null;
      if (pf.nodeId) focusNode(pf.nodeId);
      else if (pf.chapterRef) focusNodeByRef(pf.chapterRef);
    }

    // 对照模式加载正文
    if (mode === 'compare') {
      loadChapterToComparePanel();
    }

    // 首次教学
    showTutorial();
  }

  function closeWireframe() {
    if (saveTimer) clearTimeout(saveTimer);
    saveToBackend();
    if (overlay) overlay.style.display = 'none';
  }

  let eventsBound = false;
  function bindEvents() {
    if (eventsBound) return;
    eventsBound = true;

    // 画布事件
    svgEl.addEventListener('mousedown', onCanvasMouseDown);
    svgEl.addEventListener('dblclick', onCanvasDoubleClick);
    svgEl.addEventListener('contextmenu', onCanvasContextMenu);
    svgEl.addEventListener('wheel', onWheel, { passive: false });
    svgEl.addEventListener('dragover', (e) => e.preventDefault());
    svgEl.addEventListener('drop', onCanvasDrop);

    // 全局鼠标
    document.addEventListener('mousemove', onMouseMove);
    document.addEventListener('mouseup', onMouseUp);
    document.addEventListener('keydown', onKeyDown);

    // 点击空白关闭右键菜单
    document.addEventListener('click', hideContextMenu);

    // 工具栏按钮（用事件委托，避免找不到元素）
    document.addEventListener('click', (e) => {
      const t = e.target.closest('[data-wf-action]');
      if (!t) return;
      const action = t.dataset.wfAction;
      switch (action) {
        case 'new': toolbarNew(); break;
        case 'connect': toggleConnectMode(); break;
        case 'undo': undo(); break;
        case 'redo': redo(); break;
        case 'zoom-in': zoomIn(); break;
        case 'zoom-out': zoomOut(); break;
        case 'zoom-reset': zoomReset(); break;
        case 'auto-gen': autoGenerateFromProject(); renderAll(); showToast('已自动生成连线框'); break;
        case 'export': exportImage(); break;
        case 'toggle-compare': toggleCompare(); break;
        case 'check': runGlobalCheck(); break;
        case 'close': closeWireframe(); break;
        case 'save-edit': saveNodeEditor(); break;
        case 'cancel-edit': document.getElementById('wf-node-editor').style.display = 'none'; break;
      }
    });
  }

  // ═══════════════════════════════════════════
  // 状态同步：从后端同步章节节点
  // ═══════════════════════════════════════════

  /**
   * 从 /api/chapters 拉取最新章节列表，与画布中已有 chapter 节点按 chapter_ref
   * 比对，找出缺失的章节并自动创建节点和承接连线。
   * 避免重复创建已存在的节点。
   */
  async function syncFromEngine() {
    try {
      await refreshCache();
      const chapters = getChapters();
      if (!chapters || chapters.length === 0) return;

      const existingRefs = new Set();
      state.nodes.forEach(n => {
        if (n.type === 'chapter' && n.chapter_ref) {
          existingRefs.add(n.chapter_ref);
        }
      });

      const marginX = 180;
      const marginY = 80;
      const colGap = 220;
      const rowGap = 140;
      let col = 0;
      let row = 0;

      // 计算已有 chapter 节点的最大列/行，新节点从已有区域之后开始
      state.nodes.forEach(n => {
        if (n.type === 'chapter') {
          const c = Math.floor((n.x - marginX) / colGap);
          const r = Math.floor((n.y - marginY) / rowGap);
          if (c > col) col = c;
          if (r > row) row = r;
        }
      });
      col++;
      row = 0;

      const newNodes = [];
      const prevChapterNodeIds = [];

      chapters.forEach((ch, i) => {
        const chRef = '第' + chapterNum(ch, i) + '章';
        if (existingRefs.has(chRef)) {
          // 记录已有节点的 id，用于后续连线
          const existing = state.nodes.find(n => n.type === 'chapter' && n.chapter_ref === chRef);
          if (existing) prevChapterNodeIds.push(existing.id);
          return;
        }

        const id = uid();
        const node = {
          id, type: 'chapter',
          title: chRef + ' ' + (ch.title || '').slice(0, 10),
          summary: (ch.outline || '').slice(0, 80),
          x: marginX + col * colGap,
          y: marginY + row * rowGap,
          color: NODE_TYPES.chapter.color,
          chapter_ref: chRef,
        };
        state.nodes.push(node);
        newNodes.push(node);
        prevChapterNodeIds.push(id);
        row++;
      });

      if (newNodes.length === 0) return;

      // 为新节点建立承接连线
      for (let i = 1; i < prevChapterNodeIds.length; i++) {
        const fromId = prevChapterNodeIds[i - 1];
        const toId = prevChapterNodeIds[i];
        const already = state.edges.some(e => e.from === fromId && e.to === toId);
        if (!already) {
          state.edges.push({
            id: uidEdge(), from: fromId, to: toId,
            label: '承接', arrow: 'forward',
          });
        }
      }

      pushHistory();
      scheduleSave();
      renderAll();
      showToast('连线框已同步 ' + newNodes.length + ' 个新章节节点');
    } catch (e) {
      console.warn('[Wireframe] syncFromEngine 失败:', e);
    }
  }

  /**
   * 定位到指定 nodeId 的节点：viewport 居中 + scale 1.2 + 红色描边高亮2秒。
   * 如 overlay 未打开则登记待消费聚焦并打开 plan 模式，由 openWireframe
   * 在数据加载完成后执行（避免与异步加载竞态导致高亮丢失）。
   * @param {string} nodeId
   */
  function focusNode(nodeId) {
    const node = state.nodes.find(n => n.id === nodeId);
    if (!node) return;
    if (!overlay || overlay.style.display === 'none') {
      pendingFocus = { nodeId };
      openWireframe('plan');
      return;
    }
    doFocusNode(node);
  }

  // 实际执行聚焦：视口居中 + 红色高亮 2 秒
  function doFocusNode(node) {
    if (!svgEl) return;
    const rect = svgEl.getBoundingClientRect();
    const cx = rect.width / 2;
    const cy = rect.height / 2;
    const targetScale = 1.2;
    state.viewport.scale = targetScale;
    state.viewport.x = cx - node.x * targetScale;
    state.viewport.y = cy - node.y * targetScale;
    renderAll();

    const g = canvasGroup.querySelector(`g.wf-node[data-id="${CSS.escape(node.id)}"]`);
    if (g) {
      const rectEl = g.querySelector('rect');
      if (rectEl) {
        const origStroke = rectEl.getAttribute('stroke');
        const origWidth = rectEl.getAttribute('stroke-width');
        rectEl.setAttribute('stroke', '#ef4444');
        rectEl.setAttribute('stroke-width', '4');
        setTimeout(() => {
          rectEl.setAttribute('stroke', origStroke);
          rectEl.setAttribute('stroke-width', origWidth);
        }, 2000);
      }
    }
  }

  /**
   * 按 chapter_ref（如 '第3章'）查找节点并定位。
   * 画布未打开时登记待消费聚焦再打开（加载完成后再查找/同步，避免
   * syncFromEngine 先于 loadFromBackend 执行导致节点被覆盖）；
   * 已打开但节点不存在时先从引擎同步一次，仍无则静默返回。
   * @param {string} chapterRef
   */
  async function focusNodeByRef(chapterRef) {
    if (!overlay || overlay.style.display === 'none') {
      pendingFocus = { chapterRef };
      openWireframe('plan');
      return;
    }
    let node = state.nodes.find(n => n.chapter_ref === chapterRef);
    if (!node) {
      await syncFromEngine();
      node = state.nodes.find(n => n.chapter_ref === chapterRef);
    }
    if (node) {
      doFocusNode(node);
    }
  }

  /**
   * 大纲关键事件联动：优先从文本中提取章节引用定位节点，无引用则打开画布总览。
   * @param {string} eventText
   */
  function focusByEventText(eventText) {
    const m = (eventText || '').match(/第\s*([0-9一二三四五六七八九十百]+)\s*章/);
    if (m) {
      focusNodeByRef('第' + m[1] + '章');
    } else if (typeof WireframeCanvas !== 'undefined') {
      try { openWireframe('plan'); } catch (e) {}
    }
  }

  // ═══════════════════════════════════════════
  // 导出
  // ═══════════════════════════════════════════
  global.WireframeCanvas = {
    open: openWireframe,
    close: closeWireframe,
    runGlobalCheck: runGlobalCheck,
    invokeC5Rewrite: invokeC5Rewrite,
    getState: () => ({ nodes: state.nodes, edges: state.edges }),
    /** 从后端章节数据同步画布节点（新增缺失章节节点+承接连线） */
    syncFromEngine,
    /** 按 nodeId 定位画布节点（居中+高亮） */
    focusNode,
    /** 按 chapter_ref 定位画布节点 */
    focusNodeByRef,
    /** 按大纲关键事件文本定位（自动提取章节引用） */
    focusByEventText,
  };

})(typeof window !== 'undefined' ? window : this);
