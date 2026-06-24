"""Generic WFI CDN images for prime set component slugs."""
from __future__ import annotations

from config import WFI_CDN_BASE

# Longest suffixes first so chassis/neuroptics/systems beat generic blueprint.
_PART_IMAGE_FILES: tuple[tuple[str, str], ...] = (
    ("_chassis_blueprint", "GenericWarframePrimeChassis.png"),
    ("_neuroptics_blueprint", "GenericWarframePrimeHelmet.png"),
    ("_systems_blueprint", "GenericWarframePrimeSystem.png"),
    ("_barrel", "GenericGunPrimeBarrel.png"),
    ("_receiver", "GenericGunPrimeReceiver.png"),
    ("_stock", "GenericGunPrimeStock.png"),
    ("_blueprint", "blueprint.png"),
)


def part_image_url(slug: str) -> str:
    """Return WFI CDN URL for a market part slug based on component type."""
    s = (slug or "").lower()
    for suffix, filename in _PART_IMAGE_FILES:
        if s.endswith(suffix):
            return WFI_CDN_BASE + filename
    return ""
