#!/usr/bin/env python3
"""Tests for generic part component images."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from agents.knowledge.part_images import part_image_url


class PartImageTests(unittest.TestCase):
    def test_warframe_chassis(self):
        url = part_image_url("nova_prime_chassis_blueprint")
        self.assertTrue(url.endswith("GenericWarframePrimeChassis.png"))

    def test_warframe_neuroptics(self):
        url = part_image_url("ash_prime_neuroptics_blueprint")
        self.assertTrue(url.endswith("GenericWarframePrimeHelmet.png"))

    def test_weapon_barrel(self):
        url = part_image_url("acceltra_prime_barrel")
        self.assertTrue(url.endswith("GenericGunPrimeBarrel.png"))

    def test_generic_blueprint(self):
        url = part_image_url("nova_prime_blueprint")
        self.assertTrue(url.endswith("blueprint.png"))


if __name__ == "__main__":
    unittest.main()
