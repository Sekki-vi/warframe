"""Derive item variant classification from slug patterns."""
from __future__ import annotations

_VARIANT_EQUIPMENT = frozenset(
    {"primary", "secondary", "melee", "archgun", "archmelee", "warframes"}
)


def derive_item_variant(slug: str, equipment_class: str) -> str:
    """Return variant label for weapons/warframes, or empty string for other items."""
    if equipment_class not in _VARIANT_EQUIPMENT:
        return ""

    s = (slug or "").lower()
    if not s:
        return ""

    if equipment_class == "mods" or s.startswith("primed_"):
        return ""

    if s.startswith("kuva_"):
        return "kuva"
    if s.startswith("tenet_"):
        return "tenet"
    if s.startswith("prisma_"):
        return "prisma"
    if s.endswith("_prime"):
        return "prime"
    if s.endswith("_vandal"):
        return "vandal"
    if s.endswith("_wraith"):
        return "wraith"

    return "base"
