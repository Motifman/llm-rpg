import pytest

from ai_rpg_world.domain.world_graph.value_object.world_flag_registry import WorldFlagRegistry


class TestWorldFlagRegistry:
    def test_empty(self):
        r = WorldFlagRegistry.empty()
        assert not r.contains("a")

    def test_add_remove(self):
        r = WorldFlagRegistry.empty().with_added("x", "y")
        assert r.contains("x") and r.contains("y")
        r2 = r.with_removed("x")
        assert not r2.contains("x") and r2.contains("y")

    def test_merge(self):
        a = WorldFlagRegistry.of("a")
        b = WorldFlagRegistry.of("b")
        m = a.merge(b)
        assert m.contains("a") and m.contains("b")

    def test_as_frozen_set(self):
        r = WorldFlagRegistry.of("z")
        assert "z" in r.as_frozen_set()
