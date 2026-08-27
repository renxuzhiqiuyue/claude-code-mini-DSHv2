(() => {
  const treeEl = document.getElementById("tree");
  const rootMeta = document.getElementById("rootMeta");
  const emptyHint = document.getElementById("emptyHint");
  const viewerBody = document.getElementById("viewerBody");
  const fileTitle = document.getElementById("fileTitle");
  const fileMeta = document.getElementById("fileMeta");
  const textPane = document.getElementById("textPane");
  const messagesPane = document.getElementById("messagesPane");

  let activePath = null;

  function esc(s) {
    return String(s ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function roleClass(role) {
    if (role === "HumanMessage") return "human";
    if (role === "AIMessage") return "ai";
    if (role === "ToolMessage") return "tool";
    return "unknown";
  }

  function renderNode(node) {
    if (node.type === "dir") {
      const details = document.createElement("details");
      details.open = node.name === "solver" || !node.path.includes("/");
      const summary = document.createElement("summary");
      const row = document.createElement("div");
      row.className = "tree-item dir";
      row.innerHTML = `<span class="icon">▸</span><span>${esc(node.name)}</span>`;
      summary.appendChild(row);
      details.appendChild(summary);
      const ul = document.createElement("ul");
      (node.children || []).forEach((c) => {
        const li = document.createElement("li");
        li.appendChild(renderNode(c));
        ul.appendChild(li);
      });
      details.appendChild(ul);
      details.addEventListener("toggle", () => {
        row.querySelector(".icon").textContent = details.open ? "▾" : "▸";
      });
      return details;
    }

    const row = document.createElement("div");
    row.className = "tree-item file";
    row.dataset.path = node.path;
    const icon = node.ext === ".json" ? "{}" : "·";
    row.innerHTML = `<span class="icon">${icon}</span><span title="${esc(node.path)}">${esc(node.name)}</span>`;
    row.addEventListener("click", () => openFile(node.path));
    return row;
  }

  function markActive(path) {
    treeEl.querySelectorAll(".tree-item.file.active").forEach((el) => el.classList.remove("active"));
    const hit = treeEl.querySelector(`.tree-item.file[data-path="${CSS.escape(path)}"]`);
    if (hit) hit.classList.add("active");
  }

  async function loadTree() {
    const res = await fetch("/api/tree");
    if (!res.ok) {
      rootMeta.textContent = "无法加载目录";
      treeEl.textContent = await res.text();
      return;
    }
    const data = await res.json();
    rootMeta.textContent = data.root;
    const ul = document.createElement("ul");
    (data.children || []).forEach((c) => {
      const li = document.createElement("li");
      li.appendChild(renderNode(c));
      ul.appendChild(li);
    });
    treeEl.innerHTML = "";
    treeEl.appendChild(ul);
  }

  function renderMessages(messages) {
    messagesPane.innerHTML = "";
    if (!messages.length) {
      messagesPane.innerHTML = `<div class="empty" style="margin-top:2rem">无 messages</div>`;
      return;
    }
    messages.forEach((m) => {
      const cls = roleClass(m.role);
      const el = document.createElement("article");
      el.className = `msg ${cls}`;
      const hasDetails = m.details && Object.keys(m.details).length > 0;
      const detailsJson = hasDetails
        ? JSON.stringify(m.details, null, 2)
        : "";
      el.innerHTML = `
        <div class="msg-head">
          <span class="badge">${esc(m.role)}</span>
          <span class="msg-summary">${esc(m.summary)}</span>
          <span class="msg-index">#${m.index}</span>
        </div>
        <div class="msg-body">
          <div class="msg-section-title">内容</div>
          <div class="msg-content">${esc(m.content || "（空）")}</div>
          ${
            hasDetails
              ? `<div class="msg-section-title">详情</div><pre class="msg-details">${esc(detailsJson)}</pre>`
              : ""
          }
        </div>
      `;
      el.querySelector(".msg-head").addEventListener("click", () => {
        el.classList.toggle("open");
      });
      // 默认展开前几条，其余折叠
      if (m.index < 3) el.classList.add("open");
      messagesPane.appendChild(el);
    });
  }

  async function openFile(path) {
    activePath = path;
    markActive(path);
    const res = await fetch(`/api/file?path=${encodeURIComponent(path)}`);
    if (!res.ok) {
      emptyHint.classList.remove("hidden");
      viewerBody.classList.add("hidden");
      emptyHint.textContent = await res.text();
      return;
    }
    const data = await res.json();
    emptyHint.classList.add("hidden");
    viewerBody.classList.remove("hidden");
    fileTitle.textContent = data.path;
    const chips = [];
    chips.push(`<span>${esc(data.kind || "file")}</span>`);
    if (data.message_count != null) chips.push(`<span>${data.message_count} messages</span>`);
    const meta = data.meta || {};
    Object.entries(meta).forEach(([k, v]) => {
      if (v == null || v === "") return;
      const val = typeof v === "object" ? JSON.stringify(v) : String(v);
      chips.push(`<span>${esc(k)}: ${esc(val)}</span>`);
    });
    fileMeta.innerHTML = chips.join("");

    if (data.kind === "session" && (data.messages || []).length) {
      textPane.classList.add("hidden");
      messagesPane.classList.remove("hidden");
      renderMessages(data.messages);
      return;
    }

    // 纯文本 / 非 session JSON
    messagesPane.classList.add("hidden");
    textPane.classList.remove("hidden");
    textPane.textContent = data.text || JSON.stringify(data.raw ?? data, null, 2);
  }

  loadTree().catch((e) => {
    rootMeta.textContent = String(e);
  });
})();
