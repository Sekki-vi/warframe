#!/usr/bin/env python3
"""Unit tests for item variant derivation."""
from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from agents.knowledge.variants import derive_item_variant


def test_derive_item_variant() -> None:
    cases = [
        ("cedo", "primary", "base"),
        ("cedo_prime", "primary", "prime"),
        ("kuva_bramma", "primary", "kuva"),
        ("tenet_arx", "primary", "tenet"),
        ("ignis_wraith", "primary", "wraith"),
        ("braton_vandal", "primary", "vandal"),
        ("prisma_gorgon", "primary", "prisma"),
        ("primed_flow", "mods", ""),
        ("wisp_prime", "warframes", "prime"),
        ("ash", "warframes", "base"),
    ]
    for slug, ec, expected in cases:
        got = derive_item_variant(slug, ec)
        assert got == expected, f"{slug}/{ec}: expected {expected!r}, got {got!r}"


if __name__ == "__main__":
    test_derive_item_variant()
    print("OK  derive_item_variant")
