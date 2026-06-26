"""
Warframe AI — Web UI
Pure frontend. Talks to a backend agent via HTTP.
Set BACKEND_URL to point at any compatible agent:
  Manager Agent:  http://localhost:8502  (recommended)
  Market Agent:   http://localhost:8000  (direct, bypasses Manager)
"""

import os
import requests
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8502")
TIMEOUT     = 60


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


# ── Page config ───────────────────────────────────────────────────────────────

st.set_page_config(page_title="Warframe AI", page_icon="⚔️", layout="wide")

# ── Sidebar ───────────────────────────────────────────────────────────────────

with st.sidebar:
    st.title("⚔️ Warframe AI")
    st.caption(f"Backend: `{BACKEND_URL}`")
    st.divider()

    # User identity
    st.subheader("👤 User")
    user_id    = st.text_input("User ID",    value="player_001", key="uid")
    session_id = st.text_input("Session ID", value="session_001", key="sid")

    # Auth level (Manager provides this; Market Agent doesn't — show if available)
    user_info = api_get(f"/user/{user_id}")
    if user_info and "auth_level" in user_info:
        level = user_info["auth_level"]
        label = user_info.get("label", "")
        icons = {0: "🔵", 1: "🟢", 2: "🟡", 3: "🟠", 4: "🔴"}
        st.markdown(f"**Level {level}** {icons.get(level, '⚪')} {label}")

    st.divider()

    # Sub-agent / backend health
    st.subheader("🔌 Status")
    health = api_get("/health")
    if health:
        st.success(f"Backend online — v{health.get('version','?')}")
        # If Manager, show sub-agent statuses
        sub = health.get("sub_agents", {})
        for name, info in sub.items():
            icon = "🟢" if info["status"] == "ok" else "🔴"
            st.caption(f"{icon} {name.capitalize()} Agent")
    else:
        st.error("Backend offline")

    st.divider()

    # Portfolio
    st.subheader("📦 Portfolio")
    portfolio = api_get("/portfolio")
    if portfolio and portfolio.get("holdings"):
        for h in portfolio["holdings"]:
            st.markdown(f"**{h['item_name']}**  \n{h['quantity']}x @ {h['avg_buy_price']}p avg")
            st.divider()
    else:
        st.caption("No holdings yet.")

    st.divider()

    # Session controls
    st.subheader("💬 Session")
    c1, c2 = st.columns(2)
    if c1.button("Clear Chat", use_container_width=True):
        st.session_state.messages = []
        api_post(f"/session/{session_id}", {}) if hasattr(requests, 'delete') else None
        st.rerun()
    if c2.button("Refresh", use_container_width=True):
        st.rerun()

# ── Item Explorer ─────────────────────────────────────────────────────────────

st.title("🔍 Item Explorer")
query = st.text_input("Search item", placeholder="e.g. Ash Prime Set, Volt Prime Blueprint")

if query:
    results = api_get("/search", params={"q": query})
    if not results or not results.get("results"):
        st.warning("No items found.")
    else:
        items    = results["results"]
        selected = st.selectbox("Select item", [r["name"] for r in items])
        slug     = next(r["slug"] for r in items if r["name"] == selected)

        details = api_get(f"/item/{slug}")
        orders  = api_get(f"/orders/{slug}")

        # ── HERO — image once at the top ─────────────────────────────────────
        if details:
            st.divider()
            img_col, info_col = st.columns([1, 4])

            with img_col:
                if details.get("image_url"):
                    st.image(details["image_url"], width=160)

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

                m1, m2, m3, m4 = st.columns(4)
                if details.get("mastery_rank") is not None:
                    m1.metric("Mastery Rank", details["mastery_rank"])
                if details.get("ducats"):
                    m2.metric("Ducat Value", f"{details['ducats']} ⬡")
                if details.get("trading_tax"):
                    m3.metric("Trading Tax", f"{details['trading_tax']:,} cr")
                if details.get("wiki_link"):
                    m4.markdown(f"<br>[📖 Wiki]({details['wiki_link']})", unsafe_allow_html=True)

        # ── TABS — specs only, no images ──────────────────────────────────────
        st.divider()
        tab_orders, tab_compare, tab_trade = st.tabs(
            ["📊 Live Orders", "🔄 Compare Items", "💰 Log Trade"]
        )

        # TAB 1 — Live Orders
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
                            {"#": i+1, "Price (p)": o["price_platinum"],
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
                            {"#": i+1, "Price (p)": o["price_platinum"],
                             "Qty": o["quantity"], "Buyer": o["seller"],
                             "Active": "🟢 In-Game" if o.get("active") else "🔵 Online"}
                            for i, o in enumerate(rows)
                        ])
                    else:
                        st.caption("No online buyers right now.")

                st.caption("🟢 In-Game = actively playing  |  🔵 Online = on site only")

        # TAB 2 — Compare Items
        with tab_compare:
            st.caption("Compare items side-by-side — specs and live prices only.")

            if "compare_list" not in st.session_state:
                st.session_state.compare_list = []

            a_col, b_col = st.columns([4, 1])
            add_q = a_col.text_input("Add item", key="cmp", label_visibility="collapsed",
                                     placeholder="Type item name to add...")
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

        # TAB 3 — Log Trade
        with tab_trade:
            t1, t2, t3, t4 = st.columns(4)
            trade_type = t1.selectbox("Type", ["buy", "sell"])
            qty        = t2.number_input("Quantity", min_value=1, value=1)
            default_p  = int(orders.get("best_sell_price_platinum") or 1) if orders else 1
            price      = t3.number_input("Price (platinum)", min_value=1, value=default_p)

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

# ── Chat ──────────────────────────────────────────────────────────────────────

st.divider()
st.subheader("🤖 Ask the Agent")

if "messages" not in st.session_state:
    st.session_state.messages = []

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if msg.get("agents_called"):
            agents_str = " + ".join(f"**{a.capitalize()} Agent**" for a in msg["agents_called"])
            st.caption(f"via {agents_str}")

if prompt := st.chat_input("Ask about prices, items, portfolio, forecasts..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
            res = api_post("/query", {
                "message":    prompt,
                "user_id":    st.session_state.get("uid", "player_001"),
                "session_id": st.session_state.get("sid", "session_001"),
            })

        if res and "error" not in res:
            response       = res.get("response", str(res))
            agents_called  = res.get("agents_called", [])
            flagged        = res.get("guardrail_flagged", False)

            st.markdown(response)
            if agents_called:
                st.caption("via " + " + ".join(f"**{a.capitalize()} Agent**" for a in agents_called))
            if flagged:
                st.caption("⚠️ Guardrail flagged")

            st.session_state.messages.append({
                "role": "assistant", "content": response,
                "agents_called": agents_called,
            })
        else:
            err = res.get("error", "Unknown error") if res else "No response"
            st.error(err)
            st.session_state.messages.append({"role": "assistant", "content": err})
