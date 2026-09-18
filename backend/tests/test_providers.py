"""Provider registry tests.

The headline regression here: the soil feed must be selected by its own
`so_provider` setting, not by a copy-paste reference to the weather setting.
"""
from __future__ import annotations

from app.providers.registry import ProviderRegistry, _REGISTRY, _SLOT_SETTING, registry


def test_soil_slot_maps_to_soil_setting():
    assert _SLOT_SETTING["soil"] == "soil_provider"


def test_every_slot_has_a_matching_setting_name():
    assert _SLOT_SETTING["rainfall"] == "rainfall_provider"
    assert _SLOT_SETTING["weather"] == "weather_provider"
    assert _SLOT_SETTING["river"] == "river_provider"
    assert _SLOT_SETTING["satellite"] == "satellite_provider"
    assert _SLOT_SETTING["terrain"] == "terrain_provider"
    assert _SLOT_SETTING["historical"] == "historical_provider"


def test_every_slot_registers_a_demo_impl():
    for slot, impls in _REGISTRY.items():
        assert "demo" in impls, f"slot '{slot}' lacks a demo implementation"


def test_registry_resolves_soil_to_demo():
    assert registry.get("soil").__class__.__name__ == "DemoSoilProvider"


def test_registry_isolation_new_instance():
    r = ProviderRegistry()
    r.get("soil")
    assert r.get("soil") is not registry.get("soil")