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

  function formatPrice(val) {
    if (val === null || val === undefined) return null;
    return `${Math.round(val)}p`;
  }

  function renderSources(sources) {
    if (!sources || !sources.length) return "";

    const cards = sources.map((src) => {
      const img = src.image_url
        ? `<img src="${escapeHtml(src.image_url)}" alt="" loading="lazy">`
        : `<div class="no-img">?</div>`;

      const rankLabel = src.rank != null ? ` · rank ${src.rank}` : "";
      const subtypeLabel = src.subtype ? ` · ${escapeHtml(src.subtype)}` : "";
      const sell = formatPrice(src.sell_median);
      const buy = formatPrice(src.buy_median);
      const prices = [
        sell ? `Sell median: ${sell}` : null,
        buy ? `Buy median: ${buy}` : null,
      ].filter(Boolean).join(" · ");

      const wiki = src.wiki_link
        ? `<a href="${escapeHtml(src.wiki_link)}" target="_blank" rel="noopener">Wiki</a>`
        : "";

      const snapshot = src.price_snapshot_date
        ? `<span class="snapshot-badge">Snapshot: ${escapeHtml(src.price_snapshot_date)}</span>`
        : "";

      return `
        <div class="source-card">
          ${img}
          <div class="source-info">
            <h4>${escapeHtml(src.item_name || src.slug)}</h4>
            <div class="source-meta">
              ${escapeHtml(src.slug)}${rankLabel}${subtypeLabel}
              ${prices ? `<br><span class="price">${escapeHtml(prices)}</span>` : ""}
              ${snapshot}
              ${wiki ? `<br>${wiki}` : ""}
            </div>
          </div>
        </div>`;
    }).join("");

    return `<div class="sources">${cards}</div>`;
  }

  function appendMessage(role, text, sources) {
    const wrap = document.createElement("div");
    wrap.className = `message ${role}`;
    const label = role === "user" ? "OPERATOR" : "ORDIS";
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

      appendMessage("ordis", data.reply, data.sources);
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
            Conversation buffer cleared, Operator. The market interface remains online.
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
