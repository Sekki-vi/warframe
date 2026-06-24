"""Knowledge Agent — WFI-only Ordis sub-agent."""
from __future__ import annotations

import re
from typing import Any

from openai import OpenAI

from agents.knowledge.intent import QueryIntent, parse_query_intent, strip_question_prefix
from agents.knowledge.keyword import exact_match, keyword_search
from agents.knowledge.merge import merge_hits
from agents.knowledge.semantic import semantic_search
from agents.market import get_set_parts, run_orders_query
from chat.config import get_chat_config

SYSTEM_PROMPT = """You are Ordis, a Cephalon knowledge subsystem aboard a Tenno's Orbiter.

Persona:
- Formal, helpful, and slightly dramatic in a sci-fi manner.
- Address the user as "Operator" occasionally.

Rules:
- Answer ONLY using the provided knowledge context. If context is insufficient, say so clearly.
- For build/parts queries, list ONLY the market-listed components provided in context.
- For recommendation requests, discuss ONLY the items in the knowledge context (typically up to 3). Give brief stats from context.
- For random item requests, discuss ONLY the single item in context.
- When recommending weapons, list WEAPONS only — not mods — unless the Operator explicitly asked for mods.
- Never invent item stats or names not present in the context.
"""

_client: OpenAI | None = None
_cfg: dict | None = None


def _get_client() -> tuple[dict, OpenAI]:
    global _client, _cfg
    if _cfg is None:
        _cfg = get_chat_config()
        _client = OpenAI(api_key=_cfg["openai_key"])
    return _cfg, _client


def _trim_history(history: list[dict[str, str]], max_turns: int) -> list[dict[str, str]]:
    if len(history) <= max_turns * 2:
        return history
    return history[-(max_turns * 2) :]


def _build_context(hits: list[dict[str, Any]], *, parts_parent: str | None = None) -> str:
    if not hits:
        return "No relevant items were retrieved from the knowledge base."
    blocks: list[str] = []
    if parts_parent:
        blocks.append(f"Market-listed parts to build {parts_parent}:")
    for i, hit in enumerate(hits, 1):
        header = f"[{i}] {hit.get('name')}"
        if hit.get("tier"):
            header += f" (tier: {hit.get('tier')})"
        parts = [header]
        if hit.get("text"):
            parts.append(hit["text"])
        blocks.append("\n".join(parts))
    return "\n\n".join(blocks)


def _is_price_query(query: str) -> bool:
    q = query.lower()
    return bool(
        re.search(
            r"\b(price|platinum|cost|how much|sell|buy|seller|trade|market|who is selling)\b",
            q,
        )
    )


def _semantic_top_k(intent: QueryIntent) -> int:
    if intent.kind in ("random", "single"):
        return 1
    if intent.kind == "recommend":
        return min(3, intent.result_count)
    return 5


_PARTS_PREFIX = re.compile(
    r"^(?:what\s+)?(?:parts?\s+(?:to|do\s+i\s+need\s+to|are\s+needed\s+to|for|required\s+to)\s+)?"
    r"(?:build|craft|make)\s+",
    re.I,
)


def _resolve_parts_target(query: str) -> dict[str, Any] | None:
    """Resolve item for a parts/build query."""
    for candidate in (query, strip_question_prefix(query)):
        hit = exact_match(candidate)
        if hit:
            return hit

    stripped = _PARTS_PREFIX.sub("", query.strip()).strip()
    if stripped and stripped != query.strip():
        hit = exact_match(stripped)
        if hit:
            return hit

    from agents.knowledge.alias_index import load_alias_index
    from wfi_lookup import slugify

    q = query.lower()
    index = load_alias_index()
    best: tuple[int, str] | None = None
    for name, doc_id in index["name_to_doc"].items():
        if len(name) < 4:
            continue
        if name in q or name.replace(" ", "") in q.replace(" ", ""):
            score = len(name)
            if best is None or score > best[0]:
                best = (score, doc_id)
    if best:
        doc = index["docs_by_id"].get(best[1])
        if doc:
            return {
                "doc_id": doc.get("id") or best[1],
                "slug": doc.get("slug") or best[1],
                "name": doc.get("name") or "",
                "wfm_slug": doc.get("wfm_slug") or "",
            }
    slug_guess = slugify(stripped) if stripped else ""
    if slug_guess and slug_guess in index["docs_by_id"]:
        doc = index["docs_by_id"][slug_guess]
        return {
            "doc_id": slug_guess,
            "slug": slug_guess,
            "name": doc.get("name") or "",
            "wfm_slug": doc.get("wfm_slug") or "",
        }
    return None


def _lookup_part_doc(wfm_slug: str) -> dict[str, Any] | None:
    from agents.knowledge.alias_index import load_alias_index

    if not wfm_slug:
        return None
    index = load_alias_index()
    doc_id = index.get("slug_to_doc", {}).get(wfm_slug)
    if doc_id:
        doc = index["docs_by_id"].get(doc_id)
        if doc:
            return doc
    for doc in index["docs_by_id"].values():
        if doc.get("wfm_slug") == wfm_slug:
            return doc
    return None


def _parent_wiki_link(target: dict[str, Any]) -> str:
    """Wiki URL for the parent frame/weapon set, not individual components."""
    from agents.knowledge.alias_index import load_alias_index

    item_slug = target.get("slug") or target.get("doc_id") or ""
    index = load_alias_index()
    parent_doc = index["docs_by_id"].get(item_slug) if item_slug else None
    if parent_doc and parent_doc.get("wiki_link"):
        return parent_doc["wiki_link"]
    name = (target.get("name") or "").strip()
    if name:
        return f"https://wiki.warframe.com/w/{name.replace(' ', '_')}"
    return ""


def _parts_hits(query: str, cache: dict[str, Any]) -> tuple[list[dict[str, Any]], str | None]:
    target = _resolve_parts_target(query)
    if not target:
        return [], None

    item_slug = target.get("slug") or target.get("doc_id") or ""
    wfm_slug = target.get("wfm_slug") or ""
    parent_name = target.get("name") or item_slug
    parent_wiki = _parent_wiki_link(target)
    parts = get_set_parts(item_slug, wfm_slug, cache=cache)
    if not parts:
        return [], parent_name

    hits: list[dict[str, Any]] = []
    for i, part in enumerate(parts):
        part_slug = part.get("slug") or part.get("wfm_slug") or ""
        doc = _lookup_part_doc(part_slug) if part_slug else None
        hits.append(
            {
                "doc_id": part_slug,
                "name": part.get("name") or (doc or {}).get("name") or "",
                "slug": part_slug,
                "wfm_slug": part_slug,
                "source": "wfm_set",
                "image_url": part.get("image_url") or (doc or {}).get("image_url") or "",
                "wiki_link": parent_wiki if i == 0 else "",
                "text": f"Component for {parent_name}.",
                "score": 1.0,
            }
        )
    return hits, parent_name


def retrieve(query: str) -> tuple[list[dict[str, Any]], QueryIntent]:
    intent = parse_query_intent(query)
    cache: dict[str, Any] = {}

    if intent.want_set_parts:
        hits, _parent = _parts_hits(query, cache)
        if hits:
            return hits, intent
        exact = exact_match(query) or exact_match(strip_question_prefix(query))
        if exact:
            return [exact], intent

    keyword_hits = keyword_search(query, intent)
    if intent.kind == "single" or (
        keyword_hits and keyword_hits[0].get("source") == "exact"
    ):
        return keyword_hits[:1], intent
    if intent.tier_filter or (
        intent.variant and intent.kind in ("recommend", "random", "lookup")
    ):
        return keyword_hits[: intent.result_count], intent
    semantic_hits = semantic_search(query, top_k=_semantic_top_k(intent))
    hits = merge_hits(keyword_hits, semantic_hits, max_results=intent.result_count)
    return hits, intent


def build_sources(hits: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """UI-facing source cards."""
    return [
        {
            "name": h.get("name"),
            "description": "",
            "tier": h.get("tier") or "",
            "image_url": h.get("image_url"),
            "wiki_link": h.get("wiki_link"),
        }
        for h in hits
    ]


def answer(message: str, history: list[dict[str, str]] | None = None) -> dict[str, Any]:
    cfg, client = _get_client()
    history = list(history or [])

    if _is_price_query(message):
        market = run_orders_query(message)
        reply = market.get("reply") or (
            "Operator, I could not retrieve live market data for that request."
        )
        history.append({"role": "user", "content": message})
        history.append({"role": "assistant", "content": reply})
        return {"reply": reply, "sources": [], "history": history}

    hits, intent = retrieve(message)
    parts_parent = None
    if intent.want_set_parts and hits and hits[0].get("source") == "wfm_set":
        target = _resolve_parts_target(message)
        parts_parent = (target or {}).get("name")

    context = _build_context(hits, parts_parent=parts_parent)

    messages: list[dict[str, str]] = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages.extend(_trim_history(history, cfg["max_history"]))
    messages.append(
        {
            "role": "user",
            "content": f"Knowledge context:\n{context}\n\nOperator query: {message}",
        }
    )

    response = client.chat.completions.create(
        model=cfg["chat_model"],
        messages=messages,
        temperature=cfg["temperature"],
    )
    reply = response.choices[0].message.content or ""

    history.append({"role": "user", "content": message})
    history.append({"role": "assistant", "content": reply})

    sources = build_sources(hits)

    return {"reply": reply, "sources": sources, "history": history}
