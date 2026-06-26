"""Knowledge Agent — non-tradable WFI Ordis sub-agent (single module)."""
from __future__ import annotations

import json
import random
import re
import time
from dataclasses import dataclass
from html import unescape
from typing import Any, Literal
from urllib.parse import unquote

import requests
from openai import OpenAI
from pinecone import Pinecone

from config import CACHE_DIR, KNOWLEDGE_INDEX_JSON, get_agent_config
from agents.knowledge.wfi_lookup import load_or_build_lookup, slugify

IntentKind = Literal["random", "recommend", "lookup", "single"]
SEMANTIC_MIN_SCORE = 0.35
EXCLUDED_EQUIPMENT = frozenset({"skins", "glyphs", "sigils", "node", "misc"})
WIKI_API = "https://wiki.warframe.com/api.php"
WIKI_BASE = "https://wiki.warframe.com/w/"
WIKI_PAGE_BASE = "https://wiki.warframe.com/w/"
CACHE_FILE = CACHE_DIR / "wiki_drops.json"
_CACHE_TTL_SEC = 7 * 24 * 3600
_MAX_SOURCES = 8
_MAX_SUMMARY_CHARS = 480

SYSTEM_PROMPT = """You are Ordis, a Cephalon knowledge subsystem aboard a Tenno's Orbiter.

Persona:
- Formal, helpful, and slightly dramatic in a sci-fi manner.
- Address the user as "Operator" occasionally.

Rules:
- Answer ONLY using the provided knowledge context. If context is insufficient, say so clearly.
- Keep replies concise: 2–4 sentences unless the Operator asks for more detail.
- Give a direct description only. Do NOT end with a question, offer, or prompt (e.g. "Would you like to know more?", "Shall I explain further?", "What would you like to know next?").
- If drop or acquisition sources are in the context, include them briefly in one sentence. Do not invent drop locations.
- Never mention prices, platinum, sellers, orders, or warframe.market listings.
- If asked about prices or trading, explain that market data is handled by a separate subsystem.
- Never invent item stats or names not present in the context.
"""

_client: OpenAI | None = None
_cfg: dict | None = None
_pinecone_index = None
_openai_embed: OpenAI | None = None
_semantic_cfg: dict | None = None


# --- Alias index ---

def load_alias_index() -> dict[str, Any]:
    if not KNOWLEDGE_INDEX_JSON.exists():
        raise FileNotFoundError(
            f"Knowledge index not found at {KNOWLEDGE_INDEX_JSON}. "
            "Place a pre-built knowledge_index.json in data/processed/."
        )
    return json.loads(KNOWLEDGE_INDEX_JSON.read_text(encoding="utf-8"))


# Generic names WFI stores on component/blueprint docs
_GENERIC_COMPONENT_NAMES: frozenset[str] = frozenset(
    {
        "blueprint",
        "chassis",
        "neuroptics",
        "systems",
        "barrel",
        "stock",
        "receiver",
        "blade",
        "handle",
        "guard",
        "string",
        "upper limb",
        "lower limb",
        "carapace",
        "cerebrum",
        "pouch",
        "disc",
    }
)

_VARIANT_LABELS: dict[str, str] = {
    "prime": "Prime",
    "vandal": "Vandal",
    "wraith": "Wraith",
    "kuva": "Kuva",
    "tenet": "Tenet",
    "prisma": "Prisma",
}


def compute_wiki_url(name: str, item_variant: str, equipment_class: str) -> str:
    """Return canonical Warframe wiki URL for an item.

    Component/blueprint docs (equipment_class == "unknown") get an empty string
    — the wiki belongs on the parent frame or weapon, not its parts.

    URL patterns:
      - Warframe Prime variants:  /w/FrameName/Prime  (e.g. Nova/Prime, Ash/Prime)
      - All other items:          /w/Full_Item_Name   (e.g. Cedo_Prime, Boltor_Vandal)
      - Primed mods:              /w/Primed_ModName   (e.g. Primed_Flow)
      - Base items / Kuva/Tenet:  /w/Item_Name
    """
    if not name or equipment_class == "unknown":
        return ""

    # Primed mods: "Primed Flow" → Primed_Flow (not Flow/Prime)
    if name.lower().startswith("primed "):
        return f"{WIKI_PAGE_BASE}{name.replace(' ', '_')}"

    # Only Warframe Prime entries use the BaseName/Prime slash format
    if equipment_class == "warframes" and item_variant == "prime" and name.endswith(" Prime"):
        base = name[: name.rfind(" Prime")].strip()
        return f"{WIKI_PAGE_BASE}{base.replace(' ', '_')}/Prime"

    # Everything else (weapons, companions, etc.) — full name with underscores
    return f"{WIKI_PAGE_BASE}{name.replace(' ', '_')}"


def component_display_name(slug: str, stored_name: str, equipment_class: str) -> str:
    """Return a proper display name for a hit.

    For component docs whose WFI name is a generic word (e.g. "Blueprint",
    "Chassis"), derive the display name by title-casing the slug so that
    "nova_prime_chassis" becomes "Nova Prime Chassis".  All other docs keep
    their stored name unchanged.
    """
    if equipment_class == "unknown" and stored_name.lower() in _GENERIC_COMPONENT_NAMES:
        return slug.replace("_", " ").title()
    return stored_name



_ACQUISITION_SECTION = re.compile(
    r'id="Acquisition"[^>]*>.*?</h2>(.*?)(?=<div class="mw-heading mw-heading2">|<h2[^>]*id=|\Z)',
    re.IGNORECASE | re.DOTALL,
)
_BOILERPLATE = re.compile(
    r"all drop rates data is obtained from de's official drop tables",
    re.IGNORECASE,
)
_TAG_RE = re.compile(r"<[^>]+>")
_EDIT_MARKERS = re.compile(r"\[ edit \| edit source \]", re.IGNORECASE)
_TABLE_ROW = re.compile(r"<tr[^>]*>(.*?)</tr>", re.IGNORECASE | re.DOTALL)
_TABLE_CELL = re.compile(r"<t[dh][^>]*>(.*?)</t[dh]>", re.IGNORECASE | re.DOTALL)


def wiki_page_from_url(wiki_link: str) -> str:
    """Return MediaWiki page title from a canonical wiki URL."""
    link = (wiki_link or "").strip()
    if not link.startswith(WIKI_BASE):
        return ""
    return unquote(link[len(WIKI_BASE) :]).strip("/")


def _clean_html_text(fragment: str) -> str:
    text = _TAG_RE.sub(" ", fragment)
    text = _EDIT_MARKERS.sub("", text)
    text = unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def parse_acquisition_html(html: str) -> list[str]:
    """Extract acquisition summary lines from parsed wiki HTML."""
    match = _ACQUISITION_SECTION.search(html or "")
    if not match:
        return []

    section = match.group(1)
    sources: list[str] = []
    seen: set[str] = set()

    def _add(line: str) -> None:
        line = line.strip(" .")
        if not line or len(line) < 4:
            return
        if _BOILERPLATE.search(line):
            return
        key = line.lower()
        if key in seen:
            return
        seen.add(key)
        sources.append(line)

    # Lead paragraph(s) before tables
    for para in re.findall(r"<p[^>]*>(.*?)</p>", section, re.IGNORECASE | re.DOTALL):
        text = _clean_html_text(para)
        if text and not text.lower().startswith("this section"):
            _add(text)
            if len(sources) >= 2:
                break

    for item in re.findall(r"<li[^>]*>(.*?)</li>", section, re.IGNORECASE | re.DOTALL):
        text = _clean_html_text(item)
        if text:
            _add(text)
            if len(sources) >= 3:
                break

    # Acquisition table: Item | Source | ...
    for row in _TABLE_ROW.findall(section):
        if "acquisition-table" not in section and "<th" in row and "Source" in row:
            continue
        cells = [_clean_html_text(c) for c in _TABLE_CELL.findall(row)]
        cells = [c for c in cells if c]
        if len(cells) >= 2 and cells[0].lower() not in ("item", "source"):
            item, source = cells[0], cells[1]
            if source and not _BOILERPLATE.search(source):
                _add(f"{item}: {source}" if item else source)

    out: list[str] = []
    for line in sources:
        if len(line) > _MAX_SUMMARY_CHARS:
            line = line[: _MAX_SUMMARY_CHARS - 1].rstrip() + "…"
        out.append(line)
        if len(out) >= _MAX_SOURCES:
            break
    return out


def _load_cache() -> dict[str, Any]:
    if not CACHE_FILE.exists():
        return {}
    try:
        return json.loads(CACHE_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def _save_cache(data: dict[str, Any]) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def fetch_acquisition(wiki_link: str, *, force: bool = False) -> list[str]:
    """Return acquisition lines for a wiki page (cached on disk)."""
    page = wiki_page_from_url(wiki_link)
    if not page:
        return []

    cache = _load_cache()
    entry = cache.get(page) or {}
    fetched_at = entry.get("fetched_at") or 0
    if not force and entry.get("sources") is not None and (time.time() - fetched_at) < _CACHE_TTL_SEC:
        return list(entry.get("sources") or [])

    params = {
        "action": "parse",
        "page": page,
        "prop": "text",
        "format": "json",
    }
    try:
        resp = requests.get(WIKI_API, params=params, timeout=20)
        resp.raise_for_status()
        payload = resp.json()
        html = payload.get("parse", {}).get("text", {}).get("*") or ""
        sources = parse_acquisition_html(html)
    except (requests.RequestException, json.JSONDecodeError, KeyError):
        sources = list(entry.get("sources") or [])

    cache[page] = {"fetched_at": time.time(), "sources": sources, "wiki_link": wiki_link}
    _save_cache(cache)
    return sources




def _wfi_drop_locations(slug: str) -> list[str]:
    if not slug:
        return []
    wfi = load_or_build_lookup()["by_slug"].get(slug) or {}
    return list(wfi.get("drop_locations") or [])


def resolve_drop_sources(
    *,
    slug: str,
    wiki_link: str = "",
    drop_locations: list[str] | None = None,
) -> list[str]:
    """Return drop/acquisition source lines for an item."""
    locations = list(drop_locations or []) or _wfi_drop_locations(slug)
    if locations:
        return locations[:8]

    if wiki_link:
        wiki_sources = fetch_acquisition(wiki_link)
        if wiki_sources:
            return wiki_sources

    return []


def enrich_hit_drops(hit: dict[str, Any]) -> dict[str, Any]:
    """Attach drop_sources to a retrieval hit."""
    slug = hit.get("slug") or hit.get("doc_id") or ""
    sources = resolve_drop_sources(
        slug=slug,
        wiki_link=hit.get("wiki_link") or "",
        drop_locations=hit.get("drop_locations"),
    )
    if not sources:
        return hit
    return {**hit, "drop_sources": sources}

from dataclasses import dataclass
from typing import Literal

_RANDOM_WORDS = re.compile(r"\b(random|any|pick one|pick me)\b", re.I)
_RECOMMEND_WORDS = re.compile(
    r"\b(recommend|recommendation|suggestion|suggest|best|good|top|list|which)\b",
    re.I,
)
_QUESTION_PREFIX = re.compile(
    r"^(?:what is|what are|what does(?: the)?|tell me about|describe|info on|who is)\s+",
    re.I,
)
_SIGNATURE_WEAPON = re.compile(
    r"\bsignature\s+(?:weapon|weapons|rifle|pistol|shotgun|bow|melee|sword|gun)\b",
    re.I,
)
_DESCRIPTIVE_QUERY = re.compile(
    r"\b("
    r"accuracy|magazine|damage|crit|critical|status|fire rate|multishot|"
    r"punch through|range|reload|polarity|capacity|duration|efficiency|"
    r"strength|health|shield|armor|sprint|ability|passive|obtain|location|"
    r"where|how|what does|describe|tell me about|large|heavy|fast"
    r")\b",
    re.I,
)
_QUERY_TOKEN_STOP = frozenset(
    {
        "what",
        "does",
        "the",
        "do",
        "is",
        "are",
        "about",
        "tell",
        "me",
        "describe",
        "how",
        "who",
        "which",
        "when",
        "where",
        "why",
        "a",
        "an",
        "this",
        "that",
        "weapon",
        "weapons",
        "warframe",
        "warframes",
        "good",
        "best",
        "any",
        "some",
        "with",
        "for",
        "and",
        "or",
        "shotgun",
        "rifle",
        "pistol",
        "bow",
        "melee",
        "launcher",
        "sniper",
        "thrown",
        "throwing",
        "glaive",
        "whip",
        "staff",
        "polearm",
        "claws",
        "dagger",
        "machete",
        "hammer",
        "sword",
        "katana",
        "gun",
        "guns",
        "assault",
        "prime",
        "vandal",
        "wraith",
        "kuva",
        "tenet",
        "prisma",
    }
)
_WEAPON_EQUIPMENT = ("primary", "secondary", "melee", "archgun", "archmelee")
_TIER_FILTER = re.compile(
    r"\b([SABCD])\s*(?:-?\s*tier|-?\s*rank)\b|\b(?:tier|rank)\s*([SABCD])\b",
    re.I,
)
_COUNT_PATTERN = re.compile(
    r"\b(?:(\d+)\s+(?:different\s+)?(?:good\s+)?(?:weapons?\s+)?|"
    r"(?:give me|show me|list|recommend)\s+(\d+))\b",
    re.I,
)
_WARFRAME_WORDS = re.compile(r"\bwarframes?\b", re.I)
_SPEED_SORT = re.compile(
    r"\b(fastest|most speed|highest sprint|base speed|sprint speed|quickest|speediest)\b",
    re.I,
)
_MOD_NAME = re.compile(r"\bprimed\b", re.I)
_BROWSE_VARIANT = re.compile(
    r"\b(kuva|tenet|prisma|vandal|wraith|prime|base|normal|standard)\b"
    r".*\b(shotgun|rifle|pistol|bow|melee|weapon|warframe)s?\b|"
    r"\b(shotgun|rifle|pistol|bow|melee|weapon|warframe)s?\b.*"
    r"\b(kuva|tenet|prisma|vandal|wraith|prime|base|normal|standard)\b",
    re.I,
)

_VARIANT_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("kuva", re.compile(r"\bkuva\b", re.I)),
    ("tenet", re.compile(r"\btenet\b", re.I)),
    ("prisma", re.compile(r"\bprisma\b", re.I)),
    ("vandal", re.compile(r"\bvandal\b", re.I)),
    ("wraith", re.compile(r"\bwraith\b", re.I)),
    ("base", re.compile(r"\b(base|normal|standard)\b", re.I)),
    ("prime", re.compile(r"\bprime\b", re.I)),
]

_WEAPON_SUBTYPES = {
    "shotgun",
    "rifle",
    "pistol",
    "bow",
    "launcher",
    "sniper",
    "thrown",
    "throwing",
    "dual pistols",
    "dual swords",
    "glaive",
    "whip",
    "nunchaku",
    "staff",
    "polearm",
    "claws",
    "dagger",
    "machete",
    "hammer",
    "sword",
    "katana",
}


@dataclass
class QueryIntent:
    kind: IntentKind
    result_count: int
    subtypes: list[str]
    want_mods: bool
    variant: str | None = None
    browse_equipment_class: str | None = None
    tier_filter: str | None = None
    speed_sort: bool = False


def strip_question_prefix(query: str) -> str:
    return _QUESTION_PREFIX.sub("", query.strip()).strip()


def _detect_subtypes(query: str) -> list[str]:
    q = query.lower()
    found: list[str] = []
    for subtype in _WEAPON_SUBTYPES:
        key = subtype.replace(" ", "_")
        if key in q.replace("-", " ") or subtype in q:
            found.append(key)
    for word in ("shotgun", "rifle", "pistol", "bow", "melee"):
        if word in q and word not in found:
            if word == "melee":
                found.append("melee")
            else:
                found.append(word)
    return list(dict.fromkeys(found))


def _detect_mods_query(query: str) -> bool:
    q = query.lower()
    return "mod" in q or "mods" in q


def _query_matches_item_name(query: str) -> bool:
    index = load_alias_index()
    for candidate in (query, strip_question_prefix(query)):
        c = candidate.strip().lower()
        if not c:
            continue
        if (
            c in index["name_to_doc"]
            or slugify(candidate) in index["slug_to_doc"]
            or slugify(candidate) in index["alias_to_doc"]
        ):
            return True
    return False


def _detect_variant(query: str, *, want_mods: bool) -> str | None:
    if want_mods:
        return None
    if _query_matches_item_name(query):
        return None
    if not _BROWSE_VARIANT.search(query):
        return None
    for label, pattern in _VARIANT_PATTERNS:
        if pattern.search(query):
            return label
    return None


def _detect_tier_filter(query: str) -> str | None:
    m = _TIER_FILTER.search(query)
    if not m:
        return None
    for g in m.groups():
        if g:
            return g.upper()
    return None


def _detect_browse_equipment_class(query: str) -> str | None:
    if _WARFRAME_WORDS.search(query) and not _detect_mods_query(query):
        return "warframes"
    return None


def _parse_explicit_count(query: str) -> int | None:
    m = _COUNT_PATTERN.search(query)
    if not m:
        return None
    for g in m.groups():
        if g:
            try:
                return max(1, min(10, int(g)))
            except ValueError:
                pass
    return None


def _detect_single_item_query(query: str) -> bool:
    if _detect_mods_query(query):
        return False
    stripped = strip_question_prefix(query)
    if _QUESTION_PREFIX.match(query.strip()):
        return _query_matches_item_name(query)
    q = query.strip()
    if len(q.split()) <= 4 and not _RECOMMEND_WORDS.search(q) and not _RANDOM_WORDS.search(q):
        if _detect_subtypes(q) or _detect_browse_equipment_class(q):
            return False
        return _query_matches_item_name(query)
    return False


def parse_query_intent(query: str) -> QueryIntent:
    """Classify query and choose default result cap."""
    subtypes = _detect_subtypes(query)
    want_mods = _detect_mods_query(query)
    variant = _detect_variant(query, want_mods=want_mods)
    browse_equipment_class = _detect_browse_equipment_class(query)
    tier_filter = _detect_tier_filter(query)
    explicit = _parse_explicit_count(query)
    speed_sort = bool(_SPEED_SORT.search(query))
    q_lower = query.lower()

    if _detect_single_item_query(query):
        return QueryIntent(
            kind="single",
            result_count=1,
            subtypes=subtypes,
            want_mods=want_mods,
            variant=None,
            browse_equipment_class=browse_equipment_class,
            tier_filter=tier_filter,
            speed_sort=speed_sort,
        )

    browse_target = subtypes or browse_equipment_class or "weapon" in q_lower

    if _RANDOM_WORDS.search(query):
        kind: IntentKind = "random"
        default_count = 1
    elif _RECOMMEND_WORDS.search(query) and browse_target:
        kind = "recommend"
        default_count = 3
    elif (subtypes or browse_equipment_class) and not _detect_exact_item_query(query):
        if _RANDOM_WORDS.search(query):
            kind = "random"
            default_count = 1
        elif _RECOMMEND_WORDS.search(query):
            kind = "recommend"
            default_count = 3
        else:
            kind = "lookup"
            default_count = 5
    else:
        kind = "lookup"
        default_count = 5

    result_count = explicit if explicit is not None else default_count
    if kind == "random":
        result_count = 1
    elif kind == "recommend" and explicit is None:
        result_count = 3

    return QueryIntent(
        kind=kind,
        result_count=result_count,
        subtypes=subtypes,
        want_mods=want_mods,
        variant=variant,
        browse_equipment_class=browse_equipment_class,
        tier_filter=tier_filter,
        speed_sort=speed_sort,
    )


def _detect_exact_item_query(query: str) -> bool:
    q = query.strip()
    if len(q.split()) <= 3 and not _RECOMMEND_WORDS.search(q) and not _RANDOM_WORDS.search(q):
        return True
    return False



_STAT_DAMAGE = re.compile(r"(\d+(?:\.\d+)?)\s+total damage", re.I)
_STAT_CRIT = re.compile(r"(\d+)% crit", re.I)

_WARFRAME_PART_SUFFIXES = (
    "_blueprint",
    "_neuroptics",
    "_chassis",
    "_systems",
    "_harness",
    "_carapace",
    "_wings",
    "_cerebrum",
    "_neural",
)


def _stat_score(doc: dict[str, Any]) -> float:
    text = doc.get("metadata_text") or doc.get("text") or ""
    score = 0.0
    m = _STAT_DAMAGE.search(text)
    if m:
        score += float(m.group(1)) * 0.01
    m = _STAT_CRIT.search(text)
    if m:
        score += float(m.group(1))
    return score


def _filter_by_variant(docs: list[dict[str, Any]], variant: str | None) -> list[dict[str, Any]]:
    if not variant:
        return docs
    return [d for d in docs if (d.get("item_variant") or "base") == variant]


def rank_candidates(
    docs: list[dict[str, Any]],
    *,
    intent: QueryIntent,
    seed: int | None = None,
) -> list[dict[str, Any]]:
    """Sort and sample docs for browse/recommend/random intents."""
    if not docs:
        return []

    if intent.want_mods:
        pool = list(docs)
    else:
        pool = [d for d in docs if d.get("equipment_class") != "mods"]

    pool = _filter_by_variant(pool, intent.variant)

    if not pool:
        return []

    rng = random.Random(seed)

    if intent.kind == "random":
        return [rng.choice(pool)]

    if intent.speed_sort:
        pool.sort(key=lambda d: -(d.get("sprint_speed") or 0.0))
        return pool[: intent.result_count]

    pool.sort(key=lambda d: (-_stat_score(d), d.get("name") or ""))

    if intent.kind == "recommend":
        rng.shuffle(pool)
        return pool[: intent.result_count]

    return pool[: intent.result_count]


def is_warframe_doc(doc: dict[str, Any]) -> bool:
    """True for full warframe entries, not blueprints or parts."""
    if doc.get("equipment_class") != "warframes":
        return False
    slug = doc.get("slug") or doc.get("id") or ""
    if any(slug.endswith(sfx) for sfx in _WARFRAME_PART_SUFFIXES):
        return False
    typ = (doc.get("type") or "").lower()
    if typ and typ not in ("warframe", "warframes"):
        return False
    return True




def _doc_to_hit(doc: dict[str, Any], source: str, score: float = 1.0) -> dict[str, Any]:
    slug = doc.get("slug") or doc.get("id") or ""
    ec = doc.get("equipment_class") or ""
    name = component_display_name(slug, doc.get("name") or "", ec)
    wiki = compute_wiki_url(name, doc.get("item_variant") or "", ec)
    return {
        "doc_id": slug or doc.get("id") or "",
        "name": name,
        "slug": slug,
        "category": doc.get("category") or "",
        "type": doc.get("type") or "",
        "equipment_class": ec,
        "weapon_subtype": doc.get("weapon_subtype") or "",
        "taxonomy": doc.get("taxonomy") or "",
        "tier": doc.get("tier") or "",
        "item_variant": doc.get("item_variant") or "",
        "image_url": doc.get("image_url") or "",
        "wiki_link": wiki,
        "drop_locations": list(doc.get("drop_locations") or []),
        "description": doc.get("description") or "",
        "text": doc.get("metadata_text") or doc.get("text") or "",
        "sprint_speed": doc.get("sprint_speed"),
        "score": score,
        "source": source,
    }


def _normalize_query(query: str) -> str:
    q = query.strip().lower()
    if q.endswith(" set"):
        q = q[:-4].strip()
    return q


def _exact_match_candidates(query: str) -> list[str]:
    raw = _normalize_query(query)
    stripped = _normalize_query(strip_question_prefix(query))
    return list(
        dict.fromkeys(
            [
                raw,
                stripped,
                slugify(query),
                slugify(strip_question_prefix(query)),
                slugify(raw),
                slugify(stripped),
            ]
        )
    )


def exact_match(query: str, index: dict[str, Any] | None = None) -> dict[str, Any] | None:
    index = index or load_alias_index()
    docs_by_id = index["docs_by_id"]

    for q in _exact_match_candidates(query):
        if not q:
            continue
        doc_id = (
            index["name_to_doc"].get(q)
            or index["slug_to_doc"].get(q)
            or index["alias_to_doc"].get(q)
        )
        if doc_id and doc_id in docs_by_id:
            return _doc_to_hit(docs_by_id[doc_id], "exact", 1.0)
    return None


def _embedded_exact_match(query: str, index: dict[str, Any] | None = None) -> dict[str, Any] | None:
    """Match a known item name embedded in a longer question (e.g. 'soma rifle do' -> soma)."""
    index = index or load_alias_index()
    docs_by_id = index["docs_by_id"]
    tokens = [
        token
        for token in re.findall(r"[a-z0-9]+", query.lower())
        if token not in _QUERY_TOKEN_STOP and len(token) >= 2
    ]
    if not tokens:
        return None

    for size in (3, 2, 1):
        for i in range(len(tokens) - size + 1):
            chunk_tokens = tokens[i : i + size]
            chunk = "_".join(chunk_tokens)
            phrase = " ".join(chunk_tokens)
            doc_id = (
                index["slug_to_doc"].get(chunk)
                or index["alias_to_doc"].get(chunk)
                or index["name_to_doc"].get(phrase)
            )
            if doc_id and doc_id in docs_by_id:
                return _doc_to_hit(docs_by_id[doc_id], "exact", 1.0)
    return None


def _frames_in_query(query: str, index: dict[str, Any]) -> list[tuple[str, str]]:
    q = query.lower()
    frames: list[tuple[str, str]] = []
    for doc_id in index.get("equipment_class_to_docs", {}).get("warframes", []):
        doc = index["docs_by_id"].get(doc_id)
        if not doc or not is_warframe_doc(doc):
            continue
        slug = doc.get("slug") or ""
        base_slug = slug.removesuffix("_prime")
        name = (doc.get("name") or "").lower().replace(" prime", "").strip()
        if base_slug and base_slug in q:
            frames.append((slug, doc.get("name") or name.title()))
        elif name and re.search(rf"\b{re.escape(name)}\b", q):
            frames.append((slug, doc.get("name") or name.title()))
    return frames


def _signature_weapon_match(query: str, index: dict[str, Any] | None = None) -> dict[str, Any] | None:
    """Resolve '<Frame> signature weapon' to the weapon whose lore text names that frame."""
    if not _SIGNATURE_WEAPON.search(query):
        return None
    index = index or load_alias_index()
    frames = _frames_in_query(query, index)
    if not frames:
        return None

    _, frame_name = max(frames, key=lambda item: len(item[1]))
    frame_key = frame_name.lower().replace(" prime", "").strip()
    pattern = re.compile(
        rf"{re.escape(frame_key)}['']?s signature|"
        rf"signature (?:weapon|weapons|rifle|pistol|shotgun|bow|melee|gun)s? (?:of )?{re.escape(frame_key)}|"
        rf"{re.escape(frame_key)}.*\bsignature\b",
        re.I,
    )

    candidates: list[dict[str, Any]] = []
    for ec in _WEAPON_EQUIPMENT:
        for doc_id in index.get("equipment_class_to_docs", {}).get(ec, []):
            doc = index["docs_by_id"].get(doc_id)
            if not doc:
                continue
            text = f"{doc.get('description') or ''} {doc.get('metadata_text') or ''}"
            if pattern.search(text):
                candidates.append(doc)

    if not candidates:
        return None

    candidates.sort(
        key=lambda doc: (
            0 if (doc.get("item_variant") or "base") == "base" else 1,
            0 if doc.get("weapon_subtype") != "companion_weapon" else 1,
            doc.get("name") or "",
        )
    )
    return _doc_to_hit(candidates[0], "keyword", 0.95)


def _should_taxonomy_browse(query: str, intent: QueryIntent) -> bool:
    has_browse = intent.subtypes or intent.browse_equipment_class or (
        intent.variant and not intent.want_mods
    )
    if not has_browse:
        return False
    if _DESCRIPTIVE_QUERY.search(query):
        return False
    if intent.kind in ("random", "recommend"):
        return True
    if intent.kind != "lookup":
        return False
    return bool(
        _RECOMMEND_WORDS.search(query)
        or _RANDOM_WORDS.search(query)
        or intent.tier_filter
        or _parse_explicit_count(query) is not None
    )


def _filter_pool(pool: list[dict[str, Any]], intent: QueryIntent) -> list[dict[str, Any]]:
    if intent.variant:
        pool = [d for d in pool if (d.get("item_variant") or "base") == intent.variant]
    return pool


def _collect_warframe_pool(index: dict[str, Any], intent: QueryIntent) -> list[dict[str, Any]]:
    docs_by_id = index["docs_by_id"]
    pool: list[dict[str, Any]] = []
    for doc_id in index.get("equipment_class_to_docs", {}).get("warframes", []):
        doc = docs_by_id.get(doc_id)
        if doc and is_warframe_doc(doc):
            pool.append(doc)
    return _filter_pool(pool, intent)


def _collect_variant_weapon_pool(index: dict[str, Any], intent: QueryIntent) -> list[dict[str, Any]]:
    if not intent.variant:
        return []
    docs_by_id = index["docs_by_id"]
    pool: list[dict[str, Any]] = []
    for doc_id in index.get("variant_to_docs", {}).get(intent.variant, []):
        doc = docs_by_id.get(doc_id)
        if not doc:
            continue
        ec = doc.get("equipment_class") or ""
        if ec in ("primary", "secondary", "melee", "archgun", "archmelee"):
            pool.append(doc)
    return _filter_pool(pool, intent)


def _collect_taxonomy_pool(
    query: str,
    index: dict[str, Any],
    intent: QueryIntent,
    *,
    subtypes: list[str] | None = None,
) -> list[dict[str, Any]]:
    if intent.browse_equipment_class == "warframes" and not intent.want_mods:
        return _collect_warframe_pool(index, intent)

    if intent.variant and not intent.subtypes and not intent.want_mods:
        pool = _collect_variant_weapon_pool(index, intent)
        if pool:
            return pool

    docs_by_id = index["docs_by_id"]
    subtypes = subtypes or intent.subtypes or _detect_subtypes(query)
    if not subtypes:
        return []

    want_mods = intent.want_mods or _detect_mods_query(query)
    pool: list[dict[str, Any]] = []
    seen: set[str] = set()

    for subtype in subtypes:
        if want_mods:
            doc_ids = index["weapon_subtype_to_docs"].get(f"{subtype}_mod", [])
            if not doc_ids:
                doc_ids = [
                    d
                    for d, doc in docs_by_id.items()
                    if doc.get("weapon_subtype") == f"{subtype}_mod"
                ]
        else:
            doc_ids = []
            for ec in ("primary", "secondary", "melee", "archgun", "archmelee"):
                tax_key = f"{ec}/{subtype}"
                doc_ids.extend(index["taxonomy_to_docs"].get(tax_key, []))
            doc_ids = list(dict.fromkeys(doc_ids))

        for doc_id in doc_ids:
            if doc_id in seen:
                continue
            doc = docs_by_id.get(doc_id)
            if not doc:
                continue
            if not want_mods and doc.get("equipment_class") == "mods":
                continue
            seen.add(doc_id)
            pool.append(doc)

    return _filter_pool(pool, intent)


def taxonomy_search(
    query: str,
    intent: QueryIntent,
    index: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    index = index or load_alias_index()
    pool = _collect_taxonomy_pool(query, index, intent)
    if not pool:
        return []

    ranked = rank_candidates(pool, intent=intent, seed=hash(query) & 0xFFFFFFFF)
    return [_doc_to_hit(doc, "taxonomy", 0.95 - i * 0.01) for i, doc in enumerate(ranked)]


def _mod_context_filter(query: str, doc: dict[str, Any]) -> bool:
    q = query.lower()
    tax = doc.get("taxonomy") or ""
    ws = doc.get("weapon_subtype") or ""

    if "melee" in q:
        return "melee" in tax or ws.endswith("melee_mod")
    if "shotgun" in q and "mod" in q:
        return "shotgun" in tax
    if "rifle" in q and "mod" in q:
        return "rifle" in tax
    if "pistol" in q and "mod" in q:
        return "pistol" in tax or "dual_pistols" in tax
    if "warframe" in q and "mod" in q:
        return tax == "mods/warframe_mod"
    return True


def _effect_search(
    query: str,
    index: dict[str, Any],
    *,
    limit: int = 5,
) -> list[dict[str, Any]]:
    if "mod" not in query.lower():
        return []

    q = query.lower()
    effect_index = index.get("effect_to_docs") or {}
    docs_by_id = index["docs_by_id"]

    phrases = sorted(effect_index.keys(), key=len, reverse=True)
    hits: list[dict[str, Any]] = []
    seen: set[str] = set()

    for phrase in phrases:
        if phrase in q:
            for doc_id in effect_index[phrase]:
                if doc_id in seen:
                    continue
                doc = docs_by_id.get(doc_id)
                if not doc or doc.get("equipment_class") != "mods":
                    continue
                if not _mod_context_filter(query, doc):
                    continue
                seen.add(doc_id)
                score = 0.98 if doc.get("slug", "").startswith("primed_") else 0.92
                hits.append(_doc_to_hit(doc, "keyword", score))

    if not hits:
        return []

    hits.sort(
        key=lambda h: (
            0 if (h.get("slug") or "").startswith("primed_") else 1,
            -(h.get("score") or 0),
        )
    )
    return hits[:limit]


def keyword_search(
    query: str,
    intent: QueryIntent,
    index: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    index = index or load_alias_index()
    exact = exact_match(query, index)
    if exact:
        return [exact]

    signature = _signature_weapon_match(query, index)
    if signature:
        return [signature]

    embedded = _embedded_exact_match(query, index)
    if embedded:
        return [embedded]

    if intent.kind == "single":
        return []

    if _should_taxonomy_browse(query, intent) and (
        intent.kind in ("random", "recommend") or _detect_mods_query(query)
    ):
        tax_hits = taxonomy_search(query, intent, index)
        if tax_hits:
            return tax_hits

    if _should_taxonomy_browse(query, intent) and intent.kind == "lookup":
        pool = _collect_taxonomy_pool(query, index, intent)
        if pool and not _detect_mods_query(query):
            browse_intent = QueryIntent(
                kind="recommend",
                result_count=intent.result_count,
                subtypes=intent.subtypes,
                want_mods=intent.want_mods,
                variant=intent.variant,
                browse_equipment_class=intent.browse_equipment_class,
                tier_filter=intent.tier_filter,
            )
            ranked = rank_candidates(pool, intent=browse_intent, seed=hash(query) & 0xFFFFFFFF)
            return [_doc_to_hit(d, "taxonomy", 0.9) for d in ranked[: intent.result_count]]

    effect_hits = _effect_search(query, index, limit=intent.result_count)
    if effect_hits:
        return effect_hits

    return []




def _text_overlap_score(query: str, hit: dict[str, Any]) -> float:
    tokens = [
        token
        for token in re.findall(r"[a-z0-9]+", query.lower())
        if token not in _QUERY_TOKEN_STOP and len(token) >= 3
    ]
    if not tokens:
        return 0.0
    text = (hit.get("text") or hit.get("description") or "").lower()
    return sum(1 for token in tokens if token in text) / len(tokens)


def _filter_hits_by_subtypes(
    hits: list[dict[str, Any]],
    subtypes: list[str],
) -> list[dict[str, Any]]:
    if not subtypes:
        return hits
    allowed = {
        f"{equipment_class}/{subtype}"
        for subtype in subtypes
        for equipment_class in ("primary", "secondary", "melee", "archgun", "archmelee")
    }
    filtered = [
        hit
        for hit in hits
        if hit.get("taxonomy") in allowed or hit.get("weapon_subtype") in subtypes
    ]
    return filtered or hits


def _is_noise_hit(hit: dict[str, Any]) -> bool:
    ec = hit.get("equipment_class") or ""
    slug = hit.get("slug") or hit.get("doc_id") or ""
    if ec in EXCLUDED_EQUIPMENT:
        return True
    if slug.endswith("_skin"):
        return True
    return False


def merge_hits(
    *hit_lists: list[dict[str, Any]],
    max_results: int = 5,
) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}

    priority = {"exact": 3, "taxonomy": 2, "keyword": 2, "semantic": 1}

    for hits in hit_lists:
        for hit in hits:
            doc_id = hit.get("doc_id") or hit.get("slug") or ""
            if not doc_id:
                continue
            src = hit.get("source", "semantic")
            score = float(hit.get("score") or 0)

            if src == "semantic":
                if score < SEMANTIC_MIN_SCORE or _is_noise_hit(hit):
                    continue

            boost = priority.get(src, 0) * 10 + score
            existing = merged.get(doc_id)
            if existing is None or boost > existing["_boost"]:
                merged[doc_id] = {**hit, "_boost": boost}

    ranked = sorted(merged.values(), key=lambda h: h["_boost"], reverse=True)

    exact_hits = [h for h in ranked if h.get("source") == "exact"]
    if exact_hits:
        clean = {k: v for k, v in exact_hits[0].items() if k != "_boost"}
        return [clean]

    out: list[dict[str, Any]] = []
    for hit in ranked[:max_results]:
        clean = {k: v for k, v in hit.items() if k != "_boost"}
        out.append(clean)
    return out



_pinecone_index = None
_openai_embed: OpenAI | None = None
_semantic_cfg: dict | None = None


def _clients() -> tuple[dict, OpenAI, Any]:
    global _pinecone_index, _openai_embed, _semantic_cfg
    if _semantic_cfg is None:
        _semantic_cfg = get_agent_config()
        _openai_embed = OpenAI(api_key=_semantic_cfg["openai_key"])
        pc = Pinecone(api_key=_semantic_cfg["pinecone_key"])
        _pinecone_index = pc.Index(_semantic_cfg["index_name"])
    return _semantic_cfg, _openai_embed, _pinecone_index


def _match_to_hit(match: Any) -> dict[str, Any]:
    meta = match.metadata or {}
    slug = meta.get("slug") or ""
    ec = meta.get("equipment_class") or ""
    name = component_display_name(slug, meta.get("name") or "", ec)
    wiki = compute_wiki_url(name, meta.get("item_variant") or "", ec)
    return {
        "doc_id": meta.get("doc_id") or "",
        "name": name,
        "slug": slug,
        "category": meta.get("category") or "",
        "type": meta.get("type") or "",
        "equipment_class": ec,
        "weapon_subtype": meta.get("weapon_subtype") or "",
        "taxonomy": meta.get("taxonomy") or "",
        "image_url": meta.get("image_url") or "",
        "wiki_link": wiki,
        "tier": meta.get("tier") or "",
        "item_variant": meta.get("item_variant") or "",
        "description": meta.get("description") or "",
        "text": meta.get("text") or "",
        "sprint_speed": float(meta["sprint_speed"]) if meta.get("sprint_speed") is not None else None,
        "score": float(match.score) if match.score is not None else 0.0,
        "source": "semantic",
    }


def semantic_search(query: str, *, top_k: int | None = None) -> list[dict[str, Any]]:
    cfg, client, index = _clients()
    k = top_k if top_k is not None else cfg["top_k"]
    embedding = client.embeddings.create(model=cfg["embed_model"], input=[query]).data[0].embedding
    results = index.query(
        namespace=cfg["namespace"],
        vector=embedding,
        top_k=k,
        include_metadata=True,
    )
    return [_match_to_hit(m) for m in results.matches]

# --- Public API ---

def _get_client() -> tuple[dict, OpenAI]:
    global _client, _cfg
    if _cfg is None:
        _cfg = get_agent_config()
        _client = OpenAI(api_key=_cfg["openai_key"])
    return _cfg, _client


def _trim_history(history: list[dict[str, str]], max_turns: int) -> list[dict[str, str]]:
    if len(history) <= max_turns * 2:
        return history
    return history[-(max_turns * 2) :]


def _build_context(hits: list[dict[str, Any]]) -> str:
    if not hits:
        return "No relevant items were retrieved from the knowledge base."
    hit = hits[0]
    parts_out = [f"{hit.get('name')}"]
    if hit.get("text"):
        parts_out.append(hit["text"])
    drops = hit.get("drop_sources") or []
    if drops:
        parts_out.append("Drop sources: " + "; ".join(drops[:4]))
    return "\n".join(parts_out)


def _is_price_query(query: str) -> bool:
    q = query.lower()
    return bool(
        re.search(
            r"\b(price|platinum|cost|how much|sell|buy|seller|trade|market|who is selling)\b",
            q,
        )
    )


def retrieve(query: str) -> tuple[list[dict[str, Any]], QueryIntent]:
    intent = parse_query_intent(query)
    keyword_hits = keyword_search(query, intent)
    if keyword_hits:
        return keyword_hits[:1], intent

    descriptive = bool(_DESCRIPTIVE_QUERY.search(query))
    semantic_hits = semantic_search(query, top_k=5 if descriptive else 1)
    if descriptive and semantic_hits:
        semantic_hits = _filter_hits_by_subtypes(semantic_hits, intent.subtypes)
        semantic_hits.sort(
            key=lambda hit: (_text_overlap_score(query, hit) * 2.0 + float(hit.get("score") or 0)),
            reverse=True,
        )
        semantic_hits = semantic_hits[:1]

    hits = merge_hits(keyword_hits, semantic_hits, max_results=1)
    return hits[:1], intent


def build_sources(hits: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not hits:
        return []
    h = hits[0]
    return [{
        "name": h.get("name"),
        "description": h.get("description") or "",
        "tier": "",
        "image_url": h.get("image_url"),
        "wiki_link": h.get("wiki_link"),
        "drop_sources": list(h.get("drop_sources") or [])[:4],
    }]


def answer(message: str, history: list[dict[str, str]] | None = None) -> dict[str, Any]:
    cfg, client = _get_client()
    history = list(history or [])
    if _is_price_query(message):
        reply = (
            "Operator, pricing and seller information is routed through the market subsystem, "
            "which is not connected to this knowledge interface yet. "
            "I can describe non-tradable items from my warframe-items corpus."
        )
        history.append({"role": "user", "content": message})
        history.append({"role": "assistant", "content": reply})
        return {"reply": reply, "sources": [], "history": history}
    hits, _intent = retrieve(message)
    if hits:
        hits = [enrich_hit_drops(hits[0])]
    resolved_slug = hits[0].get("slug") or hits[0].get("doc_id") if hits else ""
    equipment_class = hits[0].get("equipment_class") if hits else ""
    context = _build_context(hits)
    messages: list[dict[str, str]] = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages.extend(_trim_history(history, cfg["max_history"]))
    messages.append({"role": "user", "content": f"Knowledge context:\n{context}\n\nOperator query: {message}"})
    response = client.chat.completions.create(model=cfg["chat_model"], messages=messages, temperature=cfg["temperature"])
    reply = response.choices[0].message.content or ""
    history.append({"role": "user", "content": message})
    history.append({"role": "assistant", "content": reply})
    return {"reply": reply, "sources": build_sources(hits), "history": history, "resolved_slug": resolved_slug, "equipment_class": equipment_class}
