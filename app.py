"""
Warframe AI — Web UI
Pure frontend. Talks to a backend agent via HTTP.
Set BACKEND_URL to point at any compatible agent:
  Manager Agent:  http://localhost:8602  (recommended)
  Market Agent:   http://localhost:8000  (direct, bypasses Manager)
"""

import os
import re
import requests
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8602")
TIMEOUT     = 60

_CHART_LINE = re.compile(r"\n\nForecast chart \([^)]+\): https?://\S+", re.I)


def _display_response(text: str, plot_url: str | None) -> str:
    if plot_url:
        return _CHART_LINE.sub("", text).strip()
    return text


def _fetch_chart_bytes(plot_url: str) -> bytes | None:
    """Fetch chart image server-side so the browser never needs to reach the backend URL."""
    match = re.search(r"/charts/.+", plot_url)
    if not match:
        return None
    url = BACKEND_URL.rstrip("/") + match.group()
    try:
        r = requests.get(url, timeout=10)
        return r.content if r.ok else None
    except Exception:
        return None


def render_forecast_chart(plot_url: str | None, label: str = "Forecast chart") -> None:
    if not plot_url:
        return
    with st.expander(label, expanded=True):
        img_bytes = _fetch_chart_bytes(plot_url)
        if img_bytes:
            st.image(img_bytes, use_container_width=True)
        else:
            st.caption("Chart unavailable.")


# ── HTTP helpers ──────────────────────────────────────────────────────────────

def api_get(path: str, params: dict = None) -> dict | None:
    try:
        r = requests.get(f"{BACKEND_URL}{path}", params=params, timeout=10)
        return r.json() if r.ok else None
    except Exception:
        return None


def api_post(path: str, body: dict) -> dict | None:
    try:
        r = requests.post(f"{BACKEND_URL}{path}", json=body, timeout=TIMEOUT)
        return r.json() if r.ok else {"error": r.text}
    except requests.exceptions.ConnectionError:
        return {"error": f"Backend offline — start the agent at {BACKEND_URL}"}
    except Exception as e:
        return {"error": str(e)}


def render_source_cards(sources: list[dict] | None) -> None:
    """Knowledge agent info card — image, description, wiki link, drop sources."""
    for src in sources or []:
        if not src.get("name") and not src.get("description"):
            continue
        st.divider()
        img_col, info_col = st.columns([1, 4])
        with img_col:
            if src.get("image_url"):
                st.image(src["image_url"], width=140)
        with info_col:
            title = src.get("name") or "Item"
            tier = src.get("tier")
            if tier:
                title = f"{title}  ·  **Tier {tier}**"
            st.markdown(f"#### {title}")
            if src.get("description"):
                st.write(src["description"])
            if src.get("wiki_link"):
                st.markdown(f"[📖 Wiki]({src['wiki_link']})")
            drops = src.get("drop_sources") or []
            if drops:
                st.caption("**Drop sources:** " + " · ".join(drops))


def render_item_explorer() -> None:
    query = st.text_input("Search item", placeholder="e.g. Ash Prime Set, Volt Prime Blueprint")

    if not query:
        return

    results = api_get("/search", params={"q": query})
    if not results or not results.get("results"):
        st.warning("No items found.")
        return

    items = results["results"]
    selected = st.selectbox("Select item", [r["name"] for r in items])
    slug = next(r["slug"] for r in items if r["name"] == selected)

    details = api_get(f"/item/{slug}")
    orders = api_get(f"/orders/{slug}")

    if details:
        st.divider()
        img_col, info_col = st.columns([1, 3])

        with img_col:
            if details.get("image_url"):
                st.image(details["image_url"], width=120)

        with info_col:
            title = details.get("name", selected)
            if details.get("vaulted"):
                title += "  🔒 *Vaulted*"
            st.subheader(title)

            tags = " · ".join(t.capitalize() for t in details.get("tags", []))
            if tags:
                st.caption(tags)
            if details.get("description"):
                st.write(details["description"])

            m1, m2 = st.columns(2)
            if details.get("mastery_rank") is not None:
                m1.metric("Mastery Rank", details["mastery_rank"])
            if details.get("ducats"):
                m2.metric("Ducat Value", f"{details['ducats']} ⬡")
            m3, m4 = st.columns(2)
            if details.get("trading_tax"):
                m3.metric("Trading Tax", f"{details['trading_tax']:,} cr")
            if details.get("wiki_link"):
                m4.markdown(f"[📖 Wiki]({details['wiki_link']})")

    st.divider()
    tab_orders, tab_compare, tab_trade = st.tabs(
        ["📊 Live Orders", "🔄 Compare Items", "💰 Log Trade"]
    )

    with tab_orders:
        if not orders or "error" in orders:
            st.error("Could not load orders.")
        else:
            c1, c2, c3 = st.columns(3)
            c1.metric("Lowest Sell", f"{orders.get('best_sell_price_platinum', 'N/A')}p")
            c2.metric("Highest Buy", f"{orders.get('best_buy_price_platinum',  'N/A')}p")
            c3.metric("Spread",      f"{orders.get('spread_platinum',           'N/A')}p")

            st.markdown("")
            sell_col, buy_col = st.columns(2)

            with sell_col:
                st.markdown("**🟥 Sell Orders** — cheapest first")
                rows = orders.get("cheapest_sell_orders", [])
                if rows:
                    st.table([
                        {"#": i + 1, "Price (p)": o["price_platinum"],
                         "Qty": o["quantity"], "Seller": o["seller"],
                         "Active": "🟢 In-Game" if o.get("active") else "🔵 Online"}
                        for i, o in enumerate(rows)
                    ])
                else:
                    st.caption("No online sellers right now.")

            with buy_col:
                st.markdown("**🟩 Buy Orders** — highest first")
                rows = orders.get("highest_buy_orders", [])
                if rows:
                    st.table([
                        {"#": i + 1, "Price (p)": o["price_platinum"],
                         "Qty": o["quantity"], "Buyer": o["seller"],
                         "Active": "🟢 In-Game" if o.get("active") else "🔵 Online"}
                        for i, o in enumerate(rows)
                    ])
                else:
                    st.caption("No online buyers right now.")

            st.caption("🟢 In-Game = actively playing  |  🔵 Online = on site only")

    with tab_compare:
        st.caption("Compare items side-by-side — specs and live prices only.")

        if "compare_list" not in st.session_state:
            st.session_state.compare_list = []

        a_col, b_col = st.columns([4, 1])
        add_q = a_col.text_input(
            "Add item", key="cmp", label_visibility="collapsed",
            placeholder="Type item name to add...",
        )
        if b_col.button("Add", use_container_width=True) and add_q:
            res = api_get("/search", params={"q": add_q})
            if res and res.get("results"):
                entry = res["results"][0]
                if entry["slug"] not in [c["slug"] for c in st.session_state.compare_list]:
                    st.session_state.compare_list.append(entry)

        if st.button("Clear All"):
            st.session_state.compare_list = []

        compare_slugs = [{"slug": slug, "name": selected}] + [
            c for c in st.session_state.compare_list if c["slug"] != slug
        ]

        if len(compare_slugs) > 1:
            rows = []
            for item in compare_slugs:
                d = api_get(f"/item/{item['slug']}") or {}
                o = api_get(f"/orders/{item['slug']}") or {}
                rows.append({
                    "Item":       d.get("name", item["name"]),
                    "Tags":       ", ".join(d.get("tags", [])),
                    "MR":         d.get("mastery_rank", "-"),
                    "Ducats ⬡":   d.get("ducats", "-"),
                    "Sell (p)":   o.get("best_sell_price_platinum", "-"),
                    "Buy (p)":    o.get("best_buy_price_platinum",  "-"),
                    "Spread (p)": o.get("spread_platinum", "-"),
                    "Vaulted":    "🔒 Yes" if d.get("vaulted") else "No",
                })
            st.dataframe(rows, use_container_width=True, hide_index=True)
        else:
            st.info("Add more items above to compare.")

    with tab_trade:
        t1, t2, t3, t4 = st.columns(4)
        trade_type = t1.selectbox("Type", ["buy", "sell"])
        qty = t2.number_input("Quantity", min_value=1, value=1)
        default_p = int(orders.get("best_sell_price_platinum") or 1) if orders else 1
        price = t3.number_input("Price (platinum)", min_value=1, value=default_p)

        if t4.button("Log Trade", use_container_width=True):
            if details:
                if trade_type == "buy":
                    res = api_post("/portfolio/buy", {
                        "item_slug":      slug,
                        "item_name":      details.get("name", selected),
                        "quantity":       int(qty),
                        "price_per_unit": float(price),
                    })
                else:
                    res = api_post("/portfolio/sell", {
                        "item_slug":      slug,
                        "quantity":       int(qty),
                        "price_per_unit": float(price),
                    })
                if res and "message" in res:
                    st.success(res["message"])
                elif res and "error" in res:
                    st.error(res["error"])
                st.rerun()


def _assistant_message_from_response(res: dict) -> dict:
    response = res.get("response", str(res))
    plot_url = res.get("plot_url")
    return {
        "role": "assistant",
        "content": response,
        "agents_called": res.get("agents_called", []),
        "sources": res.get("sources", []),
        "plot_url": plot_url,
        "chart_label": res.get("chart_label", "Forecast chart") if plot_url else None,
        "guardrail_flagged": res.get("guardrail_flagged", False),
        "usage": res.get("usage") or {},
    }


def _render_chat_message(msg: dict) -> None:
    with st.chat_message(msg["role"]):
        plot_url = msg.get("plot_url")
        content = _display_response(msg["content"], plot_url)
        if content.strip():
            st.markdown(content)
        render_forecast_chart(plot_url, msg.get("chart_label", "Forecast chart"))
        if msg.get("sources"):
            render_source_cards(msg["sources"])
        if msg.get("agents_called"):
            agents_str = " + ".join(f"**{a.capitalize()} Agent**" for a in msg["agents_called"])
            caption = f"via {agents_str}"
            tok = (msg.get("usage") or {}).get("total")
            if tok:
                caption += f"  ·  🎟️ {tok:,} tokens"
            st.caption(caption)
        if msg.get("guardrail_flagged"):
            st.caption("⚠️ Guardrail flagged")


def render_chat_history() -> None:
    if "messages" not in st.session_state:
        st.session_state.messages = []

    # Base height is a fallback; CSS stretches this container to fill the viewport.
    history = st.container(height=600)
    with history:
        for msg in st.session_state.messages:
            _render_chat_message(msg)

    if st.session_state.get("_awaiting_response"):
        prompt = st.session_state.messages[-1]["content"]
        with st.spinner("Thinking..."):
            res = api_post("/query", {
                "message":    prompt,
                "user_id":    st.session_state.get("uid", "player_001"),
                "session_id": st.session_state.get("sid", "session_001"),
            })

        if res and "error" not in res:
            st.session_state.messages.append(_assistant_message_from_response(res))
        else:
            err = res.get("error", "Unknown error") if res else "No response"
            st.session_state.messages.append({"role": "assistant", "content": err})

        st.session_state._awaiting_response = False
        st.rerun()


def handle_chat_input() -> None:
    """Top-level chat input — Streamlit docks this to the viewport bottom."""
    if prompt := st.chat_input("Ask about prices, items, portfolio, forecasts..."):
        st.session_state.messages.append({"role": "user", "content": prompt})
        st.session_state._awaiting_response = True
        st.rerun()


# ── Page config ───────────────────────────────────────────────────────────────

st.set_page_config(page_title="Warframe AI", page_icon="⚔️", layout="wide")

st.markdown(
    """
    <style>
    /* App-shell layout. The main content area fills the viewport and never
       scrolls as a page, so the "Ask the Agent" / "Item Explorer" headers stay
       mounted at the top. Each column is a full-height flex column whose body
       scrolls independently, and the chat input lives inside the chat column so
       it ends exactly at that column's right border. */
    [data-testid="stMainBlockContainer"] {
        height: 100vh;
        overflow: hidden;
        padding-top: 2.5rem;
        padding-bottom: 0;
    }
    /* Propagate full height from the main block down to the columns row. */
    [data-testid="stMainBlockContainer"] > [data-testid="stVerticalBlock"] {
        height: 100%;
        min-height: 0;
    }
    [data-testid="stMainBlockContainer"] > [data-testid="stVerticalBlock"] > [data-testid="stLayoutWrapper"] {
        flex: 1 1 auto;
        min-height: 0;
    }
    [data-testid="stMainBlockContainer"] [data-testid="stHorizontalBlock"] {
        height: 100%;
        min-height: 0;
    }
    /* Each main column + its inner block becomes a full-height flex column. */
    [data-testid="stMainBlockContainer"] [data-testid="stColumn"],
    [data-testid="stMainBlockContainer"] [data-testid="stColumn"] > [data-testid="stVerticalBlock"] {
        height: 100%;
        display: flex;
        flex-direction: column;
        min-height: 0;
    }
    /* Direct children of a column's block (header, chat input) keep natural height. */
    [data-testid="stMainBlockContainer"] [data-testid="stColumn"] > [data-testid="stVerticalBlock"] > [data-testid="stElementContainer"] {
        flex: 0 0 auto;
    }
    /* The top-level bounded body (chat history / item explorer) grows and scrolls. */
    [data-testid="stMainBlockContainer"] [data-testid="stColumn"] > [data-testid="stVerticalBlock"] > [data-testid="stLayoutWrapper"] {
        flex: 1 1 auto;
        height: auto !important;
        min-height: 0;
        overflow: auto;
    }
    [data-testid="stMainBlockContainer"] [data-testid="stColumn"] [data-testid="stChatInput"] {
        margin-top: 0.5rem;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# ── Sidebar ───────────────────────────────────────────────────────────────────

with st.sidebar:
    st.title("⚔️ Warframe AI")
    st.divider()

    session_id = st.session_state.get("sid", "session_001")

    st.subheader("📦 Portfolio")
    portfolio = api_get("/portfolio")
    if portfolio and portfolio.get("holdings"):
        for h in portfolio["holdings"]:
            info_col, btn_col = st.columns([4, 1])
            info_col.markdown(f"**{h['item_name']}**  \n{h['quantity']}x @ {h['avg_buy_price']}p avg")
            if btn_col.button("✕", key=f"rm_{h['item_slug']}", help="Remove from portfolio"):
                try:
                    requests.delete(f"{BACKEND_URL}/portfolio/{h['item_slug']}", timeout=10)
                except Exception:
                    pass
                st.rerun()
            st.divider()
    else:
        st.caption("No holdings yet.")

    st.divider()

    st.subheader("🎟️ Token Usage")
    usage_stats = api_get("/usage")
    if usage_stats and usage_stats.get("total"):
        total = usage_stats["total"]
        st.metric("Total tokens", f"{total.get('total', 0):,}")
        st.caption(
            f"{total.get('prompt', 0):,} prompt · {total.get('completion', 0):,} completion "
            f"· {total.get('calls', 0)} calls"
        )
        by_agent = usage_stats.get("by_agent") or {}
        for name, b in sorted(by_agent.items(), key=lambda kv: -kv[1].get("total", 0)):
            st.caption(f"• {name.capitalize()}: {b.get('total', 0):,}")
    else:
        st.caption("No LLM calls yet.")

    st.divider()

    st.subheader("💬 Session")
    c1, c2 = st.columns(2)
    if c1.button("Clear Chat", use_container_width=True):
        st.session_state.messages = []
        st.session_state._awaiting_response = False
        try:
            requests.delete(f"{BACKEND_URL}/session/{session_id}", timeout=10)
        except Exception:
            pass
        st.rerun()
    if c2.button("Refresh", use_container_width=True):
        # Reset cumulative token usage to zero.
        try:
            requests.delete(f"{BACKEND_URL}/usage", timeout=10)
        except Exception:
            pass
        st.rerun()

# ── Main layout: chat center, Item Explorer right ─────────────────────────────

chat_col, explorer_col = st.columns([3, 2], gap="large")

with chat_col:
    st.subheader("🤖 Ask the Agent")
    render_chat_history()
    # Input lives inside the chat column so it spans only that column and ends
    # at its right border (app-shell pins it to the bottom of the column).
    handle_chat_input()

with explorer_col:
    st.subheader("🔍 Item Explorer")
    # Bounded container so the explorer scrolls independently of the chat.
    with st.container(height=600):
        render_item_explorer()
