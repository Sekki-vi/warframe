(function () {
  const messagesEl = document.getElementById("messages");
  const form = document.getElementById("chat-form");
  const input = document.getElementById("message-input");
  const sendBtn = document.getElementById("send-btn");
  const clearBtn = document.getElementById("clear-btn");
  const chips = document.getElementById("prompt-chips");

  function escapeHtml(text) {
    const div = document.createElement("div");
    div.textContent = text;
    return div.innerHTML;
  }

  function truncate(text, maxLen) {
    if (!text || text.length <= maxLen) return text || "";
    return text.slice(0, maxLen - 1).trim() + "…";
  }

  function renderSources(sources) {
    if (!sources || !sources.length) return "";

    const cards = sources.map((src) => {
      const img = src.image_url
        ? `<img src="${escapeHtml(src.image_url)}" alt="" loading="lazy">`
        : `<div class="no-img">?</div>`;

      const desc = truncate(src.description || "", 200);
      const tier = src.tier
        ? `<span class="tier-badge tier-${escapeHtml(src.tier.toLowerCase())}">${escapeHtml(src.tier)}</span>`
        : "";
      const wiki = src.wiki_link
        ? `<a href="${escapeHtml(src.wiki_link)}" target="_blank" rel="noopener">Wiki</a>`
        : "";
      const descBlock = desc
        ? `<p class="source-desc">${escapeHtml(desc)}</p>`
        : "";

      return `
        <div class="source-card">
          ${img}
          <div class="source-info">
            <h4>${escapeHtml(src.name || "")} ${tier}</h4>
            ${descBlock}
            ${wiki ? `<div class="source-links">${wiki}</div>` : ""}
          </div>
        </div>`;
    }).join("");

    return `<div class="sources">${cards}</div>`;
  }

  function appendMessage(role, text, extras) {
    const wrap = document.createElement("div");
    wrap.className = `message ${role}`;
    const label = role === "user" ? "OPERATOR" : "ORDIS";
    const sources = extras && extras.sources;
    wrap.innerHTML = `
      <div class="message-label">${label}</div>
      <div class="message-body">${escapeHtml(text)}</div>
      ${role === "ordis" && sources ? renderSources(sources) : ""}
    `;
    messagesEl.appendChild(wrap);
    messagesEl.scrollTop = messagesEl.scrollHeight;
  }

  function appendLoading() {
    const el = document.createElement("div");
    el.className = "message ordis loading-msg";
    el.innerHTML = `
      <div class="message-label">ORDIS</div>
      <div class="message-body loading-dots">Processing transmission</div>
    `;
    messagesEl.appendChild(el);
    messagesEl.scrollTop = messagesEl.scrollHeight;
    return el;
  }

  function setLoading(loading) {
    sendBtn.disabled = loading;
    input.disabled = loading;
  }

  async function sendMessage(text) {
    const message = text.trim();
    if (!message) return;

    appendMessage("user", message);
    input.value = "";
    setLoading(true);
    const loadingEl = appendLoading();

    try {
      const res = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message }),
      });
      const data = await res.json();
      loadingEl.remove();

      if (!res.ok) {
        appendMessage("ordis", `Transmission error: ${data.error || "Unknown failure."}`);
        return;
      }

      appendMessage("ordis", data.reply, { sources: data.sources });
    } catch (err) {
      loadingEl.remove();
      appendMessage("ordis", `Connection lost, Operator. ${err.message}`);
    } finally {
      setLoading(false);
      input.focus();
    }
  }

  form.addEventListener("submit", (e) => {
    e.preventDefault();
    sendMessage(input.value);
  });

  clearBtn.addEventListener("click", async () => {
    try {
      await fetch("/api/clear", { method: "POST" });
      messagesEl.innerHTML = `
        <div class="message ordis">
          <div class="message-label">ORDIS</div>
          <div class="message-body">
            Conversation buffer cleared, Operator. The knowledge subsystem remains online.
          </div>
        </div>`;
    } catch (err) {
      console.error(err);
    }
  });

  chips.addEventListener("click", (e) => {
    const chip = e.target.closest(".chip");
    if (!chip) return;
    sendMessage(chip.dataset.prompt || "");
  });
})();
