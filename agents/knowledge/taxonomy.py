"""Derive equipment_class, weapon_subtype, and taxonomy from WFI fields."""
from __future__ import annotations

from wfi_lookup import slugify

_CATEGORY_TO_CLASS: dict[str, str] = {
    "Primary": "primary",
    "Secondary": "secondary",
    "Melee": "melee",
    "Mods": "mods",
    "Warframes": "warframes",
    "Arch-Gun": "archgun",
    "Arch-Melee": "archmelee",
    "Sentinels": "sentinels",
    "Pets": "pets",
    "Relics": "relics",
    "Arcanes": "arcanes",
    "Resources": "resources",
    "Glyphs": "glyphs",
    "Skins": "skins",
    "Misc": "misc",
}


def derive_taxonomy(category: str | None, item_type: str | None) -> tuple[str, str, str]:
    """Return (equipment_class, weapon_subtype, taxonomy path)."""
    cat = (category or "").strip()
    typ = (item_type or "").strip()

    equipment_class = _CATEGORY_TO_CLASS.get(cat, slugify(cat) if cat else "")
    weapon_subtype = slugify(typ) if typ else ""

    if not equipment_class:
        equipment_class = "unknown"
    if not weapon_subtype:
        weapon_subtype = "unknown"

    taxonomy = f"{equipment_class}/{weapon_subtype}"
    return equipment_class, weapon_subtype, taxonomy


def is_weapon_taxonomy(equipment_class: str, weapon_subtype: str) -> bool:
    """True for actual weapons (not mods) with a weapon-like subtype."""
    if equipment_class in ("primary", "secondary", "melee", "archgun", "archmelee"):
        return weapon_subtype not in ("unknown", "") and not weapon_subtype.endswith("_mod")
    return False
