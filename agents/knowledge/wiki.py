"""Wiki URL construction and component display-name helpers."""
from __future__ import annotations

_WIKI_BASE = "https://wiki.warframe.com/w/"

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
        return f"{_WIKI_BASE}{name.replace(' ', '_')}"

    # Only Warframe Prime entries use the BaseName/Prime slash format
    if equipment_class == "warframes" and item_variant == "prime" and name.endswith(" Prime"):
        base = name[: name.rfind(" Prime")].strip()
        return f"{_WIKI_BASE}{base.replace(' ', '_')}/Prime"

    # Everything else (weapons, companions, etc.) — full name with underscores
    return f"{_WIKI_BASE}{name.replace(' ', '_')}"


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
