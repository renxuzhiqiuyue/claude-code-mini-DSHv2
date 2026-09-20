(() => {
  const $ = (id) => document.getElementById(id);

  const treeEl = $("tree");
  const sessionList = $("sessionList");
  const chatLog = $("chatLog");
  const trajLog = $("trajLog");
  const chatForm = $("chatForm");
  const chatInput = $("chatInput");
  const btnSend = $("btnSend");
  const outputDir = $("outputDir");
  const btnSaveSettings = $("btnSaveSettings");
  const btnRefreshTree = $("btnRefreshTree");
  const statusLine = $("statusLine");
  const sessionTitle = $("sessionTitle");
  const subagentHint = $("subagentHint");
  const subagentWrap = $("subagentWrap");
  const subagentBtn = $("subagentBtn");
  const subagentMenu = $("subagentMenu");
  const runBadge = $("runBadge");
  const previewCode = $("previewCode");
  const previewTitle = $("previewTitle");
  const shell = $("appShell");
  const gate = $("sessionGate");
  const gateList = $("gateList");
  const consolidateGate = $("consolidateGate");
  const consolidateDesc = $("consolidateDesc");
  const compressGate = $("compressGate");
  const compressDesc = $("compressDesc");

  const AVATAR_USER = "/static/avatars/user.svg";
  const AVATAR_AGENT = "/static/avatars/agent-lulu.svg?v=4";

  let threadId = "";
  let currentSessionName = "";
  let parentSessionTitle = "";
  let liveEvents = [];
  let subagentIndex = [];
  let viewingSubKey = null; // e.g. session_xxx/solver/yyy.jsonl
  let sessionReady = false;
  let pendingOpen = null; // { name, title, compress?: boolean }
  let creatingSession = false;

  function setStatus(text) {
    statusLine.textContent = text || "就绪";
  }

  function escapeHtml(s) {
    return String(s || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function showApp() {
    gate.hidden = true;
    shell.hidden = false;
    sessionReady = true;
    clearPreview();
  }

  function showGate() {
    gate.hidden = false;
    compressGate.hidden = true;
    consolidateGate.hidden = true;
    shell.hidden = true;
    sessionReady = false;
  }

  function showCompressPrompt(name, title) {
    pendingOpen = { name, title: title || name, compress: null };
    compressDesc.innerHTML =
      `是否将会话 <strong>${escapeHtml(title || name)}</strong>（<code>${escapeHtml(name)}</code>）`
      + ` 的历史对话压缩为摘要？<br><span class="muted">压缩后仅保留「历史会话压缩」用户消息与助手摘要，原多轮消息与工具记录将被删除。</span>`;
    compressGate.hidden = false;
    consolidateGate.hidden = true;
    gate.hidden = true;
  }

  function showConsolidatePrompt(name, title) {
    if (!pendingOpen || pendingOpen.name !== name) {
      pendingOpen = { name, title: title || name, compress: pendingOpen?.compress ?? false };
    }
    consolidateDesc.innerHTML =
      `是否将会话 <strong>${escapeHtml(title || name)}</strong>（<code>${escapeHtml(name)}</code>）`
      + ` 的对话要点总结并写入 <code>.memory/MEMORY.md</code>？`;
    consolidateGate.hidden = false;
    compressGate.hidden = true;
    gate.hidden = true;
  }

  function appendBubble(role, text) {
    if (role === "user") return appendUserBubble(text);
    const div = document.createElement("div");
    div.className = `bubble ${role}`;
    div.textContent = text;
    chatLog.appendChild(div);
    chatLog.scrollTop = chatLog.scrollHeight;
    return div;
  }

  function makeAvatar(src, alt) {
    const img = document.createElement("img");
    img.className = "chat-avatar";
    img.src = src;
    img.alt = alt;
    img.width = 32;
    img.height = 32;
    img.loading = "lazy";
    img.decoding = "async";
    return img;
  }

  function appendUserBubble(text) {
    const row = document.createElement("div");
    row.className = "chat-row user";
    const bubble = document.createElement("div");
    bubble.className = "bubble user";
    bubble.textContent = text;
    row.appendChild(makeAvatar(AVATAR_USER, "用户"));
    row.appendChild(bubble);
    chatLog.appendChild(row);
    chatLog.scrollTop = chatLog.scrollHeight;
    return bubble;
  }

  function appendAgentRow(bubbleClass, fill) {
    const row = document.createElement("div");
    row.className = "chat-row assistant";
    const div = document.createElement("div");
    div.className = `bubble ${bubbleClass}`;
    fill(div);
    row.appendChild(makeAvatar(AVATAR_AGENT, "水豚噜噜"));
    row.appendChild(div);
    chatLog.appendChild(row);
    chatLog.scrollTop = chatLog.scrollHeight;
    return div;
  }

  function appendAssistantMarkdown(text) {
    return appendAgentRow("assistant", (div) => {
      const esc = text
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;");
      div.innerHTML = esc
        .replace(/`([^`]+)`/g, "<code>$1</code>")
        .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
        .replace(/\n/g, "<br>");
    });
  }

  function appendAgentToolBubble(text) {
    return appendAgentRow("tool", (div) => {
      div.textContent = text;
    });
  }

  function lastAssistantBubble() {
    for (let i = chatLog.children.length - 1; i >= 0; i--) {
      const row = chatLog.children[i];
      if (row.classList?.contains("chat-row") && row.classList.contains("assistant")) {
        return row.querySelector(".bubble.assistant");
      }
      if (row.classList?.contains("bubble") && row.classList.contains("assistant")) {
        return row;
      }
    }
    return null;
  }

  function appendFileChip(name, path) {
    const chip = document.createElement("button");
    chip.type = "button";
    chip.className = "file-chip";
    chip.textContent = `产物 ${name}`;
    chip.addEventListener("click", () => openFile(path));
    const last = lastAssistantBubble();
    if (last) {
      last.appendChild(document.createElement("br"));
      last.appendChild(chip);
    } else {
      chatLog.appendChild(chip);
    }
  }

  function switchTab(name, opts = {}) {
    document.querySelectorAll(".tab").forEach((t) => {
      t.classList.toggle("active", t.dataset.tab === name);
    });
    $("paneChat").classList.toggle("active", name === "chat");
    $("paneTraj").classList.toggle("active", name === "traj");

    // 点「对话」：回到主智能体（退出子代理轨迹视图）
    if (name === "chat" && viewingSubKey) {
      viewingSubKey = null;
      sessionTitle.textContent = parentSessionTitle || currentSessionName || "当前会话";
      if (currentSessionName) {
        $("btnDownloadLog").href = `/api/session/download?name=${encodeURIComponent(currentSessionName)}`;
      }
      refreshSubagentChrome();
      setStatus("主智能体对话");
      // 后台恢复父会话轨迹，下次进「轨迹」仍是主智能体
      if (sessionReady && currentSessionName) {
        loadTrajectory(currentSessionName, { asParent: true, keepTitle: true }).catch(() => {});
      }
    }

    // 仅手动点「轨迹」时刷新；程序内跳转子代理勿再加载父会话盖掉
    if (name === "traj" && sessionReady && opts.reload) {
      if (viewingSubKey) {
        loadTrajectory(viewingSubKey, { asSub: true }).catch((e) => setStatus(String(e.message || e)));
      } else {
        loadTrajectory(currentSessionName).catch((e) => setStatus(String(e.message || e)));
      }
    }
  }

  document.querySelectorAll(".tab").forEach((t) => {
    t.addEventListener("click", () => switchTab(t.dataset.tab, { reload: true }));
  });

  async function loadSettings() {
    const res = await fetch("/api/settings");
    const data = await res.json();
    outputDir.value = data.output_dir || "";
    if (data.session_ready && data.session) {
      currentSessionName = data.session;
      threadId = data.thread_id || currentSessionName;
      sessionTitle.textContent = currentSessionName;
      $("btnDownloadLog").href = `/api/session/download?name=${encodeURIComponent(currentSessionName)}`;
    }
    return data;
  }

  function renderNode(node) {
    if (node.type === "file") {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "file";
      btn.textContent = node.name;
      btn.dataset.path = node.path;
      btn.addEventListener("click", () => openFile(node.path, btn));
      return btn;
    }
    const details = document.createElement("details");
    details.open = node.path.split("/").length <= 2;
    const summary = document.createElement("summary");
    summary.textContent = node.name;
    details.appendChild(summary);
    for (const child of node.children || []) {
      details.appendChild(renderNode(child));
    }
    return details;
  }

  async function loadTree() {
    treeEl.textContent = "加载中…";
    const res = await fetch("/api/tree?max_depth=5");
    const data = await res.json();
    treeEl.innerHTML = "";
    const blocked = new Set(["skills", ".skills", "memory", ".memory", ".MEMORY"]);
    for (const root of data.roots || []) {
      if (blocked.has(root.name) || blocked.has(String(root.name || "").toLowerCase())) continue;
      treeEl.appendChild(renderNode(root));
    }
  }

  function renderSessionButtons(sessions, container, onPick) {
    container.innerHTML = "";
    if (!sessions.length) {
      container.innerHTML = '<div class="muted" style="padding:8px">暂无历史会话</div>';
      return;
    }
    for (const s of sessions) {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = container === gateList ? "gate-item" : "session-item";
      if (s.name === currentSessionName && container !== gateList) btn.classList.add("active");
      const tag = s.consolidated ? '<span class="tag">已总结</span>' : "";
      btn.innerHTML = `<span class="t">${escapeHtml(s.title || s.name)}${tag}</span>`
        + `<span class="meta">${escapeHtml(s.name)}${s.subagents ? ` · ${s.subagents} 子代理` : ""}</span>`;
      btn.addEventListener("click", () => onPick(s));
      container.appendChild(btn);
    }
  }

  async function loadSessions() {
    const res = await fetch("/api/sessions");
    const data = await res.json();
    renderSessionButtons(data.sessions || [], sessionList, (s) => askConsolidateThenOpen(s));
    renderSessionButtons(data.sessions || [], gateList, (s) => askConsolidateThenOpen(s));
    return data;
  }

  function askConsolidateThenOpen(s) {
    if (s.needs_compress) {
      showCompressPrompt(s.name, s.title);
    } else {
      pendingOpen = { name: s.name, title: s.title || s.name, compress: false };
      showConsolidatePrompt(s.name, s.title);
    }
  }

  async function createNew() {
    if (creatingSession) return;
    creatingSession = true;
    const gateBtn = $("gateNew");
    const railBtn = $("btnNewChat");
    if (gateBtn) gateBtn.disabled = true;
    if (railBtn) railBtn.disabled = true;
    setStatus("正在新建会话…");
    try {
      const res = await fetch("/api/session/new", { method: "POST" });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "新建失败");
      currentSessionName = data.session;
      threadId = data.thread_id || currentSessionName;
      parentSessionTitle = currentSessionName;
      sessionTitle.textContent = currentSessionName;
      viewingSubKey = null;
      subagentIndex = [];
      refreshSubagentChrome();
      $("btnDownloadLog").href = `/api/session/download?name=${encodeURIComponent(currentSessionName)}`;
      chatLog.innerHTML = "";
      liveEvents = [];
      renderTrajectory([]);
      consolidateGate.hidden = true;
      compressGate.hidden = true;
      showApp();
      setStatus(`新会话 ${currentSessionName}`);
      await Promise.all([loadTree(), loadSessions()]);
      switchTab("chat");
    } finally {
      creatingSession = false;
      if (gateBtn) gateBtn.disabled = false;
      if (railBtn) railBtn.disabled = false;
    }
  }

  async function openExisting(name, title, opts = {}) {
    const compress = !!opts.compress;
    const consolidate = !!opts.consolidate;
    let statusHint = "正在打开会话…";
    if (compress && consolidate) statusHint = "正在压缩、总结并打开…";
    else if (compress) statusHint = "正在压缩历史并打开…";
    else if (consolidate) statusHint = "正在总结会话并打开…";
    setStatus(statusHint);
    const res = await fetch("/api/session/open", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, compress, consolidate }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.detail || "打开失败");
    currentSessionName = data.session || name;
    threadId = data.thread_id || currentSessionName;
    parentSessionTitle = title || currentSessionName;
    sessionTitle.textContent = parentSessionTitle;
    viewingSubKey = null;
    $("btnDownloadLog").href = `/api/session/download?name=${encodeURIComponent(currentSessionName)}`;
    let note = `已打开会话 ${currentSessionName}`;
    if (data.compress?.compressed) {
      note += " · 历史已压缩";
    } else if (data.compress?.message) {
      note += ` · ${data.compress.message}`;
    }
    if (data.consolidate) {
      note += data.consolidate.updated
        ? " · 已写入 MEMORY.md"
        : ` · ${data.consolidate.message || "未改 MEMORY.md"}`;
    }
    consolidateGate.hidden = true;
    compressGate.hidden = true;
    showApp();
    await Promise.all([loadTree(), loadSessions(), loadChatHistory(currentSessionName)]);
    await loadTrajectory(currentSessionName);
    switchTab("traj");
    setStatus(note);
  }

  async function openFile(path, btn) {
    document.querySelectorAll(".tree .file.active").forEach((el) => el.classList.remove("active"));
    if (btn) btn.classList.add("active");
    previewTitle.textContent = path;
    previewTitle.style.color = "var(--ink)";
    $("btnClosePreview").hidden = false;
    previewCode.classList.remove("preview-empty");
    previewCode.textContent = "加载中…";
    const res = await fetch(`/api/file?path=${encodeURIComponent(path)}`);
    const data = await res.json();
    if (!res.ok) {
      previewCode.textContent = data.detail || "读取失败";
      return;
    }
    previewCode.textContent = data.content || "";
  }

  function clearPreview() {
    document.querySelectorAll(".tree .file.active").forEach((el) => el.classList.remove("active"));
    previewTitle.textContent = "预览";
    previewTitle.style.color = "";
    $("btnClosePreview").hidden = true;
    previewCode.classList.add("preview-empty");
    previewCode.textContent = "点击左侧工作区文件以预览";
  }

  $("btnClosePreview").addEventListener("click", clearPreview);

  async function saveSettings() {
    btnSaveSettings.disabled = true;
    try {
      const res = await fetch("/api/settings", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ output_dir: outputDir.value.trim() }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "设置失败");
      outputDir.value = data.output_dir;
      setStatus(`OUTPUT_DIR → ${data.output_dir}`);
      await loadTree();
    } catch (e) {
      appendBubble("error", String(e.message || e));
    } finally {
      btnSaveSettings.disabled = false;
    }
  }

  async function decidePermission(requestId, allow, bubble) {
    const buttons = bubble.querySelectorAll("button");
    buttons.forEach((b) => { b.disabled = true; });
    try {
      const res = await fetch("/api/permission", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ request_id: requestId, allow }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || `HTTP ${res.status}`);
      const note = document.createElement("div");
      note.textContent = allow ? "已批准，继续执行…" : "已拒绝";
      note.style.marginTop = "0.4rem";
      note.style.color = allow ? "var(--ok)" : "var(--warn)";
      bubble.appendChild(note);
    } catch (e) {
      buttons.forEach((b) => { b.disabled = false; });
      appendBubble("error", `权限提交失败: ${e.message || e}`);
    }
  }

  function appendPermission(data) {
    const div = document.createElement("div");
    div.className = "bubble permission";
    const title = document.createElement("div");
    title.className = "perm-title";
    title.textContent = `权限确认 · ${data.tool || "bash"}`;
    const reason = document.createElement("div");
    reason.textContent = data.reason || "需要人工确认";
    const cmd = document.createElement("pre");
    cmd.className = "perm-cmd";
    cmd.textContent = data.command || JSON.stringify(data.args || {}, null, 2);
    const actions = document.createElement("div");
    actions.className = "perm-actions";
    const allowBtn = document.createElement("button");
    allowBtn.type = "button";
    allowBtn.textContent = "允许";
    const denyBtn = document.createElement("button");
    denyBtn.type = "button";
    denyBtn.className = "deny";
    denyBtn.textContent = "拒绝";
    allowBtn.addEventListener("click", () => decidePermission(data.request_id, true, div));
    denyBtn.addEventListener("click", () => decidePermission(data.request_id, false, div));
    actions.appendChild(allowBtn);
    actions.appendChild(denyBtn);
    div.appendChild(title);
    div.appendChild(reason);
    div.appendChild(cmd);
    div.appendChild(actions);
    chatLog.appendChild(div);
    chatLog.scrollTop = chatLog.scrollHeight;
    return div;
  }

  function parseSSEChunk(buffer) {
    const events = [];
    const parts = buffer.split("\n\n");
    const rest = parts.pop() || "";
    for (const block of parts) {
      let event = "message";
      const dataLines = [];
      for (const line of block.split("\n")) {
        if (line.startsWith("event:")) event = line.slice(6).trim();
        else if (line.startsWith("data:")) dataLines.push(line.slice(5).trim());
      }
      if (dataLines.length) {
        try {
          events.push({ event, data: JSON.parse(dataLines.join("\n")) });
        } catch (_) {
          events.push({ event, data: { message: dataLines.join("\n") } });
        }
      }
    }
    return { events, rest };
  }

  function truncate(s, n) {
    s = String(s || "").replace(/\s+/g, " ").trim();
    return s.length > n ? s.slice(0, n) + "…" : s;
  }

  /** 从 session jsonl 事件恢复对话页（与轨迹同源）。 */
  function restoreChatFromEvents(events) {
    chatLog.innerHTML = "";
    liveEvents = Array.isArray(events) ? events.slice() : [];
    for (const ev of liveEvents) {
      const t = ev.type;
      if (t === "user/message") {
        const text = (ev.text || "").trim();
        if (text) appendBubble("user", text);
      } else if (t === "assistant/message") {
        const text = (ev.text || "").trim();
        if (text) appendAssistantMarkdown(text);
      } else if (t === "tool/call") {
        appendAgentToolBubble(`调用工具: ${ev.name || "tool"}`);
      } else if (t === "tool/result") {
        const snippet = truncate(ev.content || "", 1200);
        appendAgentToolBubble(`${ev.name || "tool"}\n${snippet}`);
      }
    }
    if (chatLog.lastElementChild) {
      chatLog.scrollTop = chatLog.scrollHeight;
    }
  }

  async function loadChatHistory(name) {
    const sessionName = name || currentSessionName;
    if (!sessionName) return;
    const res = await fetch(`/api/session/log?name=${encodeURIComponent(sessionName)}`);
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "加载对话失败");
    restoreChatFromEvents(data.events || []);
  }

  /** 将 jsonl 事件折叠成轨迹行：配对 tool/call+result，按 USER 分 Turn。 */
  function buildTrajectoryRows(events) {
    const pending = new Map(); // tool_call_id -> row index in current buffer
    const flat = [];
    let nTools = 0;
    let nSubs = 0;

    const push = (row) => {
      flat.push(row);
      return flat.length - 1;
    };

    for (const ev of events || []) {
      const t = ev.type;
      if (t === "session/meta") {
        if (ev.resumed) continue;
        push({
          role: "CONTEXT",
          body: `source=${ev.source || ""} · thread=${ev.thread_id || ev.id || ""}`,
        });
      } else if (t === "user/message") {
        push({ role: "USER", body: ev.text || "", turnStart: true });
      } else if (t === "assistant/message") {
        const text = (ev.text || "").trim();
        if (text) push({ role: "ASSISTANT", body: text });
        // tool_calls 细节以 tool/call 行为准，避免重复
      } else if (t === "tool/call") {
        nTools += 1;
        const id = ev.tool_call_id || "";
        const args = truncate(JSON.stringify(ev.args || {}), 220);
        const idx = push({
          role: "TOOL",
          name: ev.name || "tool",
          args,
          result: "…",
          tool_call_id: id,
        });
        if (id) pending.set(id, idx);
      } else if (t === "tool/result") {
        const id = ev.tool_call_id || "";
        const snippet = truncate(ev.content || "", 240) || "(empty)";
        if (id && pending.has(id)) {
          flat[pending.get(id)].result = snippet;
          pending.delete(id);
        } else {
          nTools += 1;
          push({
            role: "TOOL",
            name: ev.name || "tool",
            args: "",
            result: snippet,
          });
        }
      } else if (t === "subagent/start") {
        nSubs += 1;
        push({
          role: "SUBAGENT",
          body: `start ${ev.name || "solver"}`,
          subPath: ev.path || "",
        });
      } else if (t === "subagent/end") {
        push({
          role: "SUBAGENT",
          body: `end ${ev.name || "solver"} · ${truncate(ev.summary || "", 180)}`,
          subPath: ev.path || "",
        });
      }
    }

    // 按 USER 切 Turn
    const turns = [];
    let cur = { rows: [] };
    for (const row of flat) {
      if (row.turnStart) {
        if (cur.rows.length) turns.push(cur);
        cur = { rows: [row] };
      } else {
        cur.rows.push(row);
      }
    }
    if (cur.rows.length) turns.push(cur);

    return { turns, nTools, nSubs, nEvents: (events || []).length };
  }

  function formatDuration(ms) {
    if (ms == null || !Number.isFinite(ms) || ms < 0) return "";
    if (ms < 1000) return `${Math.round(ms)}ms`;
    if (ms < 60000) return `${(ms / 1000).toFixed(ms < 10000 ? 1 : 0)}秒`;
    return `${Math.round(ms / 60000)}分`;
  }

  function collectSubagents(events) {
    const byPath = new Map();
    let lastSolveDesc = "";
    for (const ev of events || []) {
      const t = ev.type;
      if (t === "tool/call" && (ev.name === "solve_task" || ev.name === "task")) {
        lastSolveDesc =
          (ev.args && (ev.args.description || ev.args.prompt || ev.args.task)) || "";
      }
      if (t === "subagent/start") {
        const path = ev.path || "";
        if (!path) continue;
        const desc = String(lastSolveDesc || "");
        byPath.set(path, {
          path,
          name: ev.name || "solver",
          title: truncate(desc, 36) || path.split("/").pop() || path,
          desc,
          startTs: ev.ts || "",
          endTs: "",
          summary: "",
          done: false,
        });
      }
      if (t === "subagent/end") {
        const path = ev.path || "";
        if (!path) continue;
        const row = byPath.get(path) || {
          path,
          name: ev.name || "solver",
          title: path.split("/").pop() || path,
          desc: "",
          startTs: "",
        };
        row.endTs = ev.ts || "";
        row.summary = ev.summary || "";
        row.done = true;
        if (!row.desc && row.summary) row.desc = row.summary;
        if (row.title === (path.split("/").pop() || path) && row.summary) {
          row.title = truncate(row.summary, 36);
        }
        byPath.set(path, row);
      }
    }
    return [...byPath.values()];
  }

  function subagentKey(path) {
    if (!path) return "";
    if (path.includes("/solver/")) return path;
    return `${currentSessionName}/${path}`;
  }

  function closeSubagentMenu() {
    if (!subagentMenu || !subagentBtn) return;
    subagentMenu.hidden = true;
    subagentBtn.setAttribute("aria-expanded", "false");
  }

  function positionSubagentMenu() {
    if (!subagentMenu || !subagentBtn) return;
    const r = subagentBtn.getBoundingClientRect();
    const width = Math.min(420, Math.max(320, window.innerWidth - 24));
    let left = r.left;
    if (left + width > window.innerWidth - 12) {
      left = Math.max(12, window.innerWidth - width - 12);
    }
    subagentMenu.style.top = `${Math.round(r.bottom + 6)}px`;
    subagentMenu.style.left = `${Math.round(left)}px`;
    subagentMenu.style.width = `${width}px`;
  }

  function refreshSubagentChrome() {
    if (!subagentWrap || !subagentHint) return;
    const n = subagentIndex.length;
    if (!n) {
      subagentWrap.hidden = true;
      closeSubagentMenu();
      return;
    }
    subagentWrap.hidden = false;
    subagentHint.textContent = `${n} 个子代理`;
    if (!subagentMenu.hidden) renderSubagentMenu();
  }

  function renderSubagentMenu() {
    if (!subagentMenu) return;
    subagentMenu.innerHTML = "";
    if (viewingSubKey) {
      const back = document.createElement("button");
      back.type = "button";
      back.className = "subagent-parent";
      back.textContent = "← 返回父会话轨迹";
      back.addEventListener("click", (e) => {
        e.preventDefault();
        e.stopPropagation();
        closeSubagentMenu();
        openParentTrajectory().catch((err) => setStatus(String(err.message || err)));
      });
      subagentMenu.appendChild(back);
    }
    if (!subagentIndex.length) {
      const empty = document.createElement("div");
      empty.className = "subagent-empty";
      empty.textContent = "暂无子代理";
      subagentMenu.appendChild(empty);
      positionSubagentMenu();
      return;
    }
    for (const sub of subagentIndex) {
      const key = subagentKey(sub.path);
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "subagent-item" + (viewingSubKey === key ? " active" : "");
      btn.setAttribute("role", "option");

      const dot = document.createElement("span");
      dot.className = "subagent-dot" + (sub.done ? "" : " running");
      btn.appendChild(dot);

      const title = document.createElement("div");
      title.className = "subagent-item-title";
      title.textContent = sub.title || sub.name || "solver";
      btn.appendChild(title);

      const meta = document.createElement("div");
      meta.className = "subagent-item-meta";
      const start = parseEventTs(sub.startTs || sub.start_ts);
      const end = parseEventTs(sub.endTs || sub.end_ts) || start;
      meta.textContent = formatDuration(start != null && end != null ? end - start : null) || "—";
      btn.appendChild(meta);

      const descText = sub.desc || sub.summary || "";
      if (descText) {
        const desc = document.createElement("div");
        desc.className = "subagent-item-desc";
        desc.textContent = truncate(descText, 120);
        btn.appendChild(desc);
      }

      btn.addEventListener("click", (e) => {
        e.preventDefault();
        e.stopPropagation();
        closeSubagentMenu();
        openSubagentTrajectory(sub).catch((err) => setStatus(String(err.message || err)));
      });
      subagentMenu.appendChild(btn);
    }
    positionSubagentMenu();
  }

  function toggleSubagentMenu() {
    if (!subagentMenu || !subagentBtn || subagentWrap.hidden) return;
    const open = subagentMenu.hidden;
    if (open) {
      renderSubagentMenu();
      subagentMenu.hidden = false;
      subagentBtn.setAttribute("aria-expanded", "true");
      positionSubagentMenu();
    } else {
      closeSubagentMenu();
    }
  }

  async function openParentTrajectory() {
    viewingSubKey = null;
    sessionTitle.textContent = parentSessionTitle || currentSessionName;
    $("btnDownloadLog").href = `/api/session/download?name=${encodeURIComponent(currentSessionName)}`;
    await loadTrajectory(currentSessionName, { asParent: true });
    switchTab("traj");
    setStatus("父会话轨迹");
  }

  async function openSubagentTrajectory(sub) {
    const key = subagentKey(sub.path);
    viewingSubKey = key;
    sessionTitle.textContent = sub.title || sub.name || "子代理";
    $("btnDownloadLog").href = `/api/session/download?name=${encodeURIComponent(key)}`;
    setStatus(`加载子代理轨迹…`);
    try {
      switchTab("traj"); // 先切到轨迹页，且不 reload 父会话
      await loadTrajectory(key, { asSub: true });
      refreshSubagentChrome();
      setStatus(`子代理轨迹 · ${sub.path}`);
    } catch (e) {
      viewingSubKey = null;
      setStatus(`打开失败: ${e.message || e}`);
      throw e;
    }
  }

  async function refreshSubagentIndexFromApi() {
    if (!currentSessionName) return;
    try {
      const res = await fetch(
        `/api/session/subagents?name=${encodeURIComponent(currentSessionName)}`,
      );
      const data = await res.json().catch(() => ({}));
      if (!res.ok) return;
      const items = data.subagents || [];
      subagentIndex = items.map((s) => ({
        path: s.path,
        name: s.name || "solver",
        title: s.title || s.path,
        desc: s.desc || s.summary || "",
        summary: s.summary || "",
        startTs: s.start_ts || s.startTs || "",
        endTs: s.end_ts || s.endTs || "",
        done: s.done !== false,
      }));
      refreshSubagentChrome();
      const mSubs = $("mSubs");
      if (mSubs) mSubs.textContent = String(subagentIndex.length);
    } catch (_) {
      /* ignore */
    }
  }

  if (subagentBtn) {
    subagentBtn.addEventListener("click", (e) => {
      e.preventDefault();
      e.stopPropagation();
      toggleSubagentMenu();
    });
  }
  const metricSubs = $("metricSubs");
  if (metricSubs) {
    metricSubs.addEventListener("click", (e) => {
      e.preventDefault();
      e.stopPropagation();
      if (subagentWrap.hidden) {
        setStatus("当前会话没有子代理");
        return;
      }
      if (subagentMenu.hidden) toggleSubagentMenu();
      else closeSubagentMenu();
    });
  }
  document.addEventListener("click", (e) => {
    if (!subagentWrap || subagentWrap.hidden || !subagentMenu || subagentMenu.hidden) return;
    const t = e.target;
    if (subagentWrap.contains(t) || subagentMenu.contains(t) || (metricSubs && metricSubs.contains(t))) return;
    closeSubagentMenu();
  });
  window.addEventListener("resize", () => {
    if (subagentMenu && !subagentMenu.hidden) positionSubagentMenu();
  });

  // 菜单挂到 body，避免被顶栏 overflow / stacking 裁切
  if (subagentMenu && subagentMenu.parentElement !== document.body) {
    document.body.appendChild(subagentMenu);
  }
  function parseEventTs(ts) {
    if (!ts) return null;
    const ms = Date.parse(String(ts).replace(" ", "T"));
    return Number.isFinite(ms) ? ms : null;
  }

  function formatEventTime(ms) {
    if (ms == null || !Number.isFinite(ms)) return "—";
    const d = new Date(ms);
    const pad = (n, w = 2) => String(n).padStart(w, "0");
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} `
      + `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}.`
      + `${pad(d.getMilliseconds(), 3)}`;
  }

  function formatDurationMs(ms) {
    if (ms == null || !Number.isFinite(ms)) return "—";
    return ms >= 1000 ? `${(ms / 1000).toFixed(2)}s` : `${Math.round(ms)}ms`;
  }

  /**
   * 串行三车道：Input / Message / Tool，同一时刻只占一格；
   * actualMs = 真实时长（tooltip / 文案）；weight = 仅用于绘制的等效宽度
   * （最短 1s、最长 20s，不改实际值）。
   */
  function buildTimelineSpans(events) {
    const TL_MIN_DISPLAY_MS = 1000;
    const TL_MAX_DISPLAY_MS = 20000;
    const list = (events || []).filter((ev) => {
      const t = ev.type;
      // timeline 不展示 context / session meta
      if (t === "session/meta") return false;
      return (
        t === "user/message" ||
        t === "assistant/message" ||
        t === "tool/call" ||
        t === "tool/result" ||
        t === "subagent/start" ||
        t === "subagent/end"
      );
    });
    if (!list.length) return [];

    const resultById = new Map();
    for (const ev of list) {
      if (ev.type === "tool/result" && ev.tool_call_id) {
        resultById.set(ev.tool_call_id, ev);
      }
    }

    // tool/call → tool/result 闭区间内的事件并入该 tool，避免与子代理条重叠计时
    const covered = new Set();
    for (let i = 0; i < list.length; i++) {
      const ev = list[i];
      if (ev.type !== "tool/call") continue;
      const rid = ev.tool_call_id || "";
      if (!rid || !resultById.has(rid)) continue;
      const j = list.findIndex((e, k) => k > i && e === resultById.get(rid));
      if (j > i) {
        for (let k = i + 1; k < j; k++) covered.add(k);
        covered.add(j); // result 本身也不单独成条
      }
    }

    const spans = [];
    for (let i = 0; i < list.length; i++) {
      if (covered.has(i)) continue;
      const ev = list[i];
      const t = ev.type;
      if (t === "tool/result") continue;

      let lane = "message";
      let label = t;
      let resultEv = null;
      let resultIdx = -1;
      if (t === "user/message") {
        lane = "input";
        label = "user";
      } else if (t === "assistant/message") {
        lane = "message";
        label = (ev.text || "").trim() ? "assistant" : "assistant+tools";
      } else if (t === "tool/call") {
        lane = "tool";
        label = ev.name || "tool";
        const rid = ev.tool_call_id || "";
        if (rid && resultById.has(rid)) {
          resultEv = resultById.get(rid);
          resultIdx = list.findIndex((e, k) => k > i && e === resultEv);
        }
      } else if (t === "subagent/start" || t === "subagent/end") {
        lane = "message";
        label = t.replace("subagent/", "sub:");
      } else {
        continue;
      }

      const textLen = String(ev.text || ev.content || ev.summary || "").length;
      const startMs = parseEventTs(ev.ts);
      const nextIdx = resultIdx > i ? resultIdx + 1 : i + 1;
      const next = list[nextIdx];
      const nextMs = next ? parseEventTs(next.ts) : null;

      if (lane === "input") {
        // Input 真实间隔原样保留；条宽由后面 weight 上限 20s 约束
        let actual = 0;
        if (startMs != null && nextMs != null && nextMs > startMs) {
          actual = nextMs - startMs;
        }
        const fallback = Math.max(400, Math.min(3000, 200 + textLen * 8));
        const realMs = actual > 0 ? actual : fallback;
        spans.push({
          lane: "input",
          label,
          startMs,
          endMs: startMs != null ? startMs + realMs : null,
          weightHint: actual > 0 ? null : fallback,
          textLen,
          seq: spans.length,
        });
        continue;
      }

      let endMs = null;
      let compressIdle = false;
      let weightHint = null;
      if (lane === "tool" && resultEv) {
        endMs = parseEventTs(resultEv.ts);
        if (startMs != null && (endMs == null || endMs <= startMs)) {
          const rlen = String(resultEv.content || "").length;
          weightHint = Math.max(300, Math.min(30000, 200 + rlen * 2));
          endMs = startMs + weightHint;
        }
      } else if (nextMs != null && startMs != null && nextMs > startMs) {
        endMs = nextMs;
        if (next.type === "user/message") compressIdle = true;
      } else {
        const est = Math.max(500, Math.min(180000, 400 + textLen * 25));
        weightHint = est;
        endMs = startMs != null ? startMs + est : null;
      }

      if (startMs != null && (endMs == null || endMs <= startMs) && weightHint == null) {
        endMs = startMs + 1;
      }

      spans.push({
        lane,
        label,
        startMs,
        endMs,
        weightHint,
        compressIdle,
        textLen,
        seq: spans.length,
      });
    }

    if (!spans.length) return [];

    function spanActualMs(s) {
      if (s.weightHint != null) return Math.max(1, s.weightHint);
      if (s.compressIdle) return 1;
      return Math.max(1, (s.endMs || 0) - (s.startMs || 0));
    }

    const assignOffsets = (list) => {
      let cursor = 0;
      for (const s of list) {
        const actual = spanActualMs(s);
        s.actualMs = actual;
        s.weight = Math.min(TL_MAX_DISPLAY_MS, Math.max(TL_MIN_DISPLAY_MS, actual));
        s.offset = cursor;
        cursor += s.weight;
      }
      list.totalWeight = cursor;
    };

    const timed = spans.every(
      (s) => s.weightHint != null || (s.startMs != null && s.endMs != null),
    );
    if (!timed) {
      for (const s of spans) {
        if (s.weightHint == null) s.weightHint = 1;
      }
    }

    const actualTotal = spans.reduce((a, s) => a + spanActualMs(s), 0);

    // 旧日志秒级时间戳撞车：仅修正用于布局的估算，actualMs 仍反映估算值
    if (actualTotal <= spans.length * 2) {
      let wall = null;
      if (viewingSubKey) {
        const sub = subagentIndex.find((s) => subagentKey(s.path) === viewingSubKey);
        if (sub) {
          const a = parseEventTs(sub.startTs || sub.start_ts);
          const b = parseEventTs(sub.endTs || sub.end_ts);
          if (a != null && b != null && b > a) wall = b - a;
        }
      }
      for (const s of spans) {
        if (s.lane === "input") {
          s.weightHint = Math.min(TL_MAX_DISPLAY_MS, Math.max(400, s.textLen ? 200 + s.textLen * 8 : 800));
        } else if (s.lane === "tool") {
          s.weightHint = Math.max(300, Math.min(30000, 300 + (s.textLen || 0) * 2));
        } else {
          s.weightHint = Math.max(500, Math.min(180000, 400 + (s.textLen || 20) * 25));
        }
        s.compressIdle = false;
      }
      if (wall && wall > spans.length) {
        const inputSpans = spans.filter((s) => s.lane === "input");
        const others = spans.filter((s) => s.lane !== "input");
        const inputSum = inputSpans.reduce((a, s) => a + spanActualMs(s), 0);
        const otherSum = others.reduce((a, s) => a + spanActualMs(s), 0) || 1;
        const remain = Math.max(wall - Math.min(inputSum, TL_MAX_DISPLAY_MS), others.length * 50);
        for (const s of others) {
          s.weightHint = Math.max(50, Math.round((spanActualMs(s) / otherSum) * remain));
        }
      }
    }

    assignOffsets(spans);
    return spans;
  }

  function paintTimeline(events) {
    const input = $("tlInput");
    const message = $("tlMessage");
    const tools = $("tlTools");
    if (!input || !message || !tools) return;
    input.innerHTML = "";
    message.innerHTML = "";
    tools.innerHTML = "";

    const spans = buildTimelineSpans(events);
    const total = spans.totalWeight || 1;
    const lanes = { input, message, tool: tools };

    for (const s of spans) {
      const bar = lanes[s.lane];
      if (!bar) continue;
      const seg = document.createElement("div");
      seg.className = `tl-seg ${s.lane === "tool" ? "tool" : s.lane}`;
      const left = (s.offset / total) * 100;
      const width = Math.max((s.weight / total) * 100, 0.4);
      seg.style.left = `${left}%`;
      seg.style.width = `${width}%`;
      const dur = s.actualMs != null ? s.actualMs : s.weight;
      const startStr = formatEventTime(s.startMs);
      const durStr = formatDurationMs(dur);
      seg.title = s.startMs != null
        ? `${s.lane}: ${s.label}\n开始 ${startStr} · 耗时 ${durStr}`
        : `${s.lane}: ${s.label} · 耗时 ${durStr}`;
      bar.appendChild(seg);
    }
  }

  function appendTrajRow(role, bodyEl) {
    const el = document.createElement("div");
    el.className = "traj-row";
    const badge = document.createElement("span");
    badge.className = `role-badge ${role}`;
    badge.textContent = role;
    el.appendChild(badge);
    el.appendChild(bodyEl);
    trajLog.appendChild(el);
  }

  function renderTrajectory(events) {
    trajLog.innerHTML = "";
    const { turns, nTools, nSubs, nEvents } = buildTrajectoryRows(events);

    $("mEvents").textContent = String(nEvents);
    const mTurns = $("mTurns");
    if (mTurns) mTurns.textContent = String(turns.length);
    $("mTools").textContent = String(nTools);
    if (!viewingSubKey) {
      subagentIndex = collectSubagents(events);
    }
    $("mSubs").textContent = String(subagentIndex.length || nSubs);
    refreshSubagentChrome();
    paintTimeline(events);

    if (!turns.length) {
      const empty = document.createElement("div");
      empty.className = "muted";
      empty.style.padding = "12px";
      empty.textContent = "暂无轨迹事件";
      trajLog.appendChild(empty);
      return;
    }

    turns.forEach((turn, ti) => {
      const head = document.createElement("div");
      head.className = "traj-turn";
      head.textContent = `Turn ${ti + 1}`;
      trajLog.appendChild(head);

      for (const row of turn.rows) {
        if (row.role === "TOOL") {
          const body = document.createElement("div");
          body.className = "traj-body traj-tool-line";
          const name = document.createElement("span");
          name.className = "traj-tool-name";
          name.textContent = row.name || "tool";
          body.appendChild(name);
          if (row.args) {
            const args = document.createElement("span");
            args.className = "traj-tool-args";
            args.textContent = row.args;
            body.appendChild(args);
          }
          const arrow = document.createElement("span");
          arrow.className = "traj-tool-arrow";
          arrow.textContent = "→";
          body.appendChild(arrow);
          const result = document.createElement("span");
          result.className = "traj-tool-result";
          result.textContent = row.result || "";
          body.appendChild(result);
          appendTrajRow("TOOL", body);
        } else {
          const body = document.createElement("div");
          body.className = "traj-body";
          body.textContent = row.body || "";
          if (row.subPath && currentSessionName && row.role === "SUBAGENT") {
            const link = document.createElement("span");
            link.className = "sub-link";
            link.textContent = "查看轨迹";
            const open = (e) => {
              e.preventDefault();
              e.stopPropagation();
              const sub =
                subagentIndex.find((s) => s.path === row.subPath) || {
                  path: row.subPath,
                  name: "solver",
                  title: row.subPath.split("/").pop() || "子代理",
                };
              openSubagentTrajectory(sub).catch((err) => setStatus(String(err.message || err)));
            };
            link.addEventListener("click", open);
            body.appendChild(link);
            // 整行可点
            body.style.cursor = "pointer";
            body.title = "打开子代理轨迹";
            body.addEventListener("click", open);
          }
          appendTrajRow(row.role, body);
        }
      }
    });
  }

  async function loadTrajectory(name, opts = {}) {
    const q = name ? `?name=${encodeURIComponent(name)}` : "";
    const res = await fetch(`/api/session/log${q}`);
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "加载轨迹失败");
    liveEvents = data.events || [];
    const asSub = !!opts.asSub || (name && String(name).includes("/solver/"));
    if (!asSub) {
      viewingSubKey = null;
      subagentIndex = collectSubagents(liveEvents);
      if (!opts.keepTitle) {
        sessionTitle.textContent = parentSessionTitle || currentSessionName || "当前会话";
      }
      renderTrajectory(liveEvents);
      await refreshSubagentIndexFromApi();
    } else {
      renderTrajectory(liveEvents);
    }
  }

  async function sendChat(text) {
    if (!sessionReady) {
      appendBubble("error", "请先选择或新建会话");
      return;
    }
    appendBubble("user", text);
    liveEvents.push({ type: "user/message", text });
    btnSend.disabled = true;
    chatInput.disabled = true;
    runBadge.textContent = "RUNNING";
    runBadge.style.background = "#dbeafe";
    runBadge.style.color = "#1e40af";
    setStatus("思考中…");

    try {
      const res = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: text, thread_id: threadId }),
      });
      if (!res.ok || !res.body) {
        const err = await res.text();
        throw new Error(err || `HTTP ${res.status}`);
      }

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buf = "";
      let assistantEl = null;

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buf += decoder.decode(value, { stream: true });
        const parsed = parseSSEChunk(buf);
        buf = parsed.rest;
        for (const ev of parsed.events) {
          if (ev.event === "status") {
            setStatus(ev.data.message || "处理中…");
            if (ev.data.thread_id) threadId = ev.data.thread_id;
          } else if (ev.event === "tool_call") {
            const calls = ev.data.calls || [];
            for (const c of calls) {
              liveEvents.push({ type: "tool/call", name: c.name, args: c.args || {} });
            }
            appendAgentToolBubble(`调用工具: ${calls.map((c) => c.name).join(", ")}`);
          } else if (ev.event === "tool") {
            liveEvents.push({
              type: "tool/result",
              name: ev.data.name || "tool",
              content: ev.data.content || "",
            });
            appendAgentToolBubble(`${ev.data.name || "tool"}\n${(ev.data.content || "").slice(0, 1200)}`);
            const m = String(ev.data.content || "").match(/([\w./-]+\.(?:md|py|json|csv|png|pdf|docx))/);
            if (m && outputDir.value) {
              const outName = outputDir.value.split(/[/\\]/).pop() || ".output";
              appendFileChip(m[1].split("/").pop(), `${outName}/${m[1].replace(/^\.\//, "")}`);
            }
          } else if (ev.event === "assistant" || ev.event === "assistant_partial") {
            const content = ev.data.content || "";
            if (!assistantEl || ev.event === "assistant") {
              assistantEl = appendAssistantMarkdown(content);
              if (ev.event === "assistant") {
                liveEvents.push({ type: "assistant/message", text: content });
              }
            } else {
              assistantEl.textContent += content;
            }
            chatLog.scrollTop = chatLog.scrollHeight;
          } else if (ev.event === "permission") {
            setStatus("等待权限确认…");
            appendPermission(ev.data);
          } else if (ev.event === "error") {
            appendBubble("error", ev.data.message || "错误");
          } else if (ev.event === "done") {
            setStatus("完成");
            await loadSessions();
            await loadTrajectory(currentSessionName).catch(() => {});
            loadTree().catch(() => {});
          }
        }
      }
    } catch (e) {
      appendBubble("error", String(e.message || e));
      setStatus("失败");
    } finally {
      btnSend.disabled = false;
      chatInput.disabled = false;
      chatInput.focus();
      runBadge.textContent = "READY";
      runBadge.style.background = "";
      runBadge.style.color = "";
      if ($("paneTraj").classList.contains("active")) renderTrajectory(liveEvents);
    }
  }

  chatForm.addEventListener("submit", (e) => {
    e.preventDefault();
    const text = chatInput.value.trim();
    if (!text) return;
    chatInput.value = "";
    sendChat(text);
  });

  chatInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      chatForm.requestSubmit();
    }
  });

  btnSaveSettings.addEventListener("click", saveSettings);
  btnRefreshTree.addEventListener("click", () => {
    Promise.all([loadTree(), loadSessions()]).catch(() => {});
  });
  $("btnNewChat").addEventListener("click", (e) => {
    e.preventDefault();
    e.stopPropagation();
    createNew().catch((err) => appendBubble("error", String(err.message || err)));
  });
  $("gateNew").addEventListener("click", (e) => {
    e.preventDefault();
    e.stopPropagation();
    createNew().catch((err) => alert(String(err.message || err)));
  });
  $("compressYes").addEventListener("click", () => {
    if (!pendingOpen) return;
    pendingOpen.compress = true;
    showConsolidatePrompt(pendingOpen.name, pendingOpen.title);
  });
  $("compressNo").addEventListener("click", () => {
    if (!pendingOpen) return;
    pendingOpen.compress = false;
    showConsolidatePrompt(pendingOpen.name, pendingOpen.title);
  });
  $("consolidateYes").addEventListener("click", () => {
    if (!pendingOpen) return;
    const { name, title, compress } = pendingOpen;
    pendingOpen = null;
    openExisting(name, title, { compress: !!compress, consolidate: true }).catch((e) => {
      alert(String(e.message || e));
      showGate();
      loadSessions().catch(() => {});
    });
  });
  $("consolidateNo").addEventListener("click", () => {
    if (!pendingOpen) return;
    const { name, title, compress } = pendingOpen;
    pendingOpen = null;
    openExisting(name, title, { compress: !!compress, consolidate: false }).catch((e) => {
      alert(String(e.message || e));
      showGate();
      loadSessions().catch(() => {});
    });
  });

  Promise.all([loadSettings(), loadSessions()])
    .then(async (results) => {
      const settings = results[0];
      if (settings.session_ready && settings.session) {
        currentSessionName = settings.session;
        threadId = settings.thread_id || currentSessionName;
        parentSessionTitle = currentSessionName;
        sessionTitle.textContent = currentSessionName;
        showApp();
        await loadTree();
        await loadChatHistory(currentSessionName).catch(() => {});
        await loadTrajectory(currentSessionName).catch(() => {});
        setStatus(`已连接 · ${currentSessionName}`);
      } else {
        showGate();
        setStatus("请选择或新建会话");
      }
    })
    .catch((e) => {
      showGate();
      alert(String(e));
    });
})();
