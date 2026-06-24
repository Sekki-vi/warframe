"""Build text_for_embedding and metadata.text from WFI item fields."""
from __future__ import annotations

import re
from typing import Any

from agents.knowledge.taxonomy import derive_taxonomy
from agents.knowledge.variants import derive_item_variant

_STAT_PREFIX = re.compile(r"^[+\-]?\d+(\.\d+)?%?\s*", re.I)


def _effect_keywords(wfi: dict[str, Any]) -> str | None:
    keywords: set[str] = set()
    for level in wfi.get("levelStats") or []:
        if not isinstance(level, dict):
            continue
        for stat in level.get("stats") or []:
            if not isinstance(stat, str):
                continue
            cleaned = _STAT_PREFIX.sub("", stat).strip().lower()
            if cleaned:
                keywords.add(cleaned)
    if not keywords:
        return None
    return ", ".join(sorted(keywords))


def effect_keyword_list(wfi: dict[str, Any]) -> list[str]:
    text = _effect_keywords(wfi)
    if not text:
        return []
    return [part.strip() for part in text.split(",") if part.strip()]


def _weapon_stats_summary(wfi: dict[str, Any]) -> str | None:
    dmg = wfi.get("damage") or {}
    total = dmg.get("total") or wfi.get("totalDamage")
    if not total:
        return None
    parts = [f"{total} total damage"]
    crit = wfi.get("criticalChance")
    status = wfi.get("procChance")
    rate = wfi.get("fireRate")
    if crit is not None:
        parts.append(f"{round(crit * 100)}% crit")
    if status is not None:
        parts.append(f"{round(status * 100)}% status")
    if rate is not None:
        parts.append(f"{rate} fire rate")
    return ", ".join(parts)


def _warframe_stats_summary(wfi: dict[str, Any]) -> str | None:
    """Base stats summary for warframe entries (health/shield/armor/energy/sprint)."""
    sprint = wfi.get("sprintSpeed") or wfi.get("sprint")
    health = wfi.get("health")
    shield = wfi.get("shield")
    armor = wfi.get("armor")
    power = wfi.get("power")
    if sprint is None and health is None:
        return None
    parts: list[str] = []
    if sprint is not None:
        parts.append(f"sprint speed {sprint}")
    if health is not None:
        parts.append(f"HP {health}")
    if shield is not None:
        parts.append(f"shield {shield}")
    if armor is not None:
        parts.append(f"armor {armor}")
    if power is not None:
        parts.append(f"energy {power}")
    return ", ".join(parts)


def _rank_effects_summary(wfi: dict[str, Any]) -> str | None:
    stats = wfi.get("levelStats")
    if not stats:
        return None
    samples: list[str] = []
    for i, level in enumerate(stats[:3]):
        if isinstance(level, dict) and level.get("stats"):
            samples.append(f"rank {i}: {'; '.join(level['stats'])}")
    if len(stats) > 3:
        last = stats[-1]
        if isinstance(last, dict) and last.get("stats"):
            samples.append(f"max rank: {'; '.join(last['stats'])}")
    return " | ".join(samples) if samples else None


def _core_lines(slug: str, wfi: dict[str, Any]) -> list[str]:
    name = wfi.get("name") or slug
    lines = [f"{name} ({slug})."]

    if wfi.get("description"):
        lines.append(f"Description: {wfi['description']}")

    cat = wfi.get("category")
    typ = wfi.get("type")
    if cat or typ:
        lines.append(f"Category: {' / '.join(b for b in (cat, typ) if b)}.")

    equipment_class, _, taxonomy = derive_taxonomy(cat, typ)
    lines.append(f"Taxonomy: {taxonomy}.")

    variant = derive_item_variant(slug, equipment_class)
    if variant:
        lines.append(f"Variant: {variant}.")

    if wfi.get("masteryReq") is not None:
        lines.append(f"Mastery rank required: {wfi['masteryReq']}.")
    if wfi.get("rarity"):
        lines.append(f"Rarity: {wfi['rarity']}.")
    if wfi.get("polarity"):
        lines.append(f"Polarity: {wfi['polarity']}.")
    if wfi.get("tradable") is False:
        lines.append("Not tradable on market.")

    rank_fx = _rank_effects_summary(wfi)
    if rank_fx:
        lines.append(f"Mod ranks: {rank_fx}.")

    effects = _effect_keywords(wfi)
    if effects:
        lines.append(f"Effect keywords: {effects}.")

    stats = _weapon_stats_summary(wfi)
    if stats:
        lines.append(f"Stats: {stats}.")
    frame_stats = _warframe_stats_summary(wfi)
    if frame_stats:
        lines.append(f"Base stats: {frame_stats}.")

    if wfi.get("relic_rewards_summary"):
        lines.append(f"Relic rewards include: {wfi['relic_rewards_summary']}.")
    if wfi.get("drop_locations"):
        lines.append(f"Drop locations: {', '.join(wfi['drop_locations'])}.")
    if wfi.get("_componentOf"):
        lines.append(f"Component of: {wfi['_componentOf']}.")

    return lines


def build_text_for_embedding(slug: str, wfi: dict[str, Any]) -> str:
    """Rich text for vector embedding (search-oriented)."""
    name = wfi.get("name") or slug
    lines = _core_lines(slug, wfi)
    # Extra aliases for retrieval
    lines.append(f"Also known as: {name}, {slug.replace('_', ' ')}.")
    return " ".join(lines)


def build_metadata_text(slug: str, wfi: dict[str, Any], *, max_chars: int = 2000) -> str:
    """Shorter context for LLM (stored in metadata.text)."""
    text = " ".join(_core_lines(slug, wfi))
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 3] + "..."
