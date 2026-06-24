"""Parse user query intent for retrieval caps and taxonomy routing."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

IntentKind = Literal["random", "recommend", "lookup", "single"]

_RANDOM_WORDS = re.compile(r"\b(random|any|pick one|pick me)\b", re.I)
_RECOMMEND_WORDS = re.compile(
    r"\b(recommend|recommendation|suggestion|suggest|best|good|top|list|which)\b",
    re.I,
)
_QUESTION_PREFIX = re.compile(
    r"^(?:what is|what are|tell me about|describe|info on|who is)\s+",
    re.I,
)
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


_PARTS_QUERY = re.compile(
    r"\b(?:parts?\s+(?:to|for|needed|required)|what\s+(?:do\s+i\s+need|parts)|"
    r"components?\s+(?:to|for|needed)|blueprints?\s+for|build)\b",
    re.I,
)


@dataclass
class QueryIntent:
    kind: IntentKind
    result_count: int
    subtypes: list[str]
    want_mods: bool
    variant: str | None = None
    browse_equipment_class: str | None = None
    tier_filter: str | None = None
    want_set_parts: bool = False


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
    from agents.knowledge.alias_index import load_alias_index
    from wfi_lookup import slugify

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


def _detect_set_parts_query(query: str) -> bool:
    return bool(_PARTS_QUERY.search(query))


def parse_query_intent(query: str) -> QueryIntent:
    """Classify query and choose default result cap."""
    subtypes = _detect_subtypes(query)
    want_mods = _detect_mods_query(query)
    variant = _detect_variant(query, want_mods=want_mods)
    browse_equipment_class = _detect_browse_equipment_class(query)
    tier_filter = _detect_tier_filter(query)
    want_set_parts = _detect_set_parts_query(query)
    explicit = _parse_explicit_count(query)
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
            want_set_parts=want_set_parts,
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
        want_set_parts=want_set_parts,
    )


def _detect_exact_item_query(query: str) -> bool:
    q = query.strip()
    if len(q.split()) <= 3 and not _RECOMMEND_WORDS.search(q) and not _RANDOM_WORDS.search(q):
        return True
    return False
