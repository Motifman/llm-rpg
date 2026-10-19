from ai_rpg_world.domain.world_graph.value_object.world_flag_registry import WorldFlagRegistry


class TestWorldFlagRegistry:
    def test_empty(self):
        r = WorldFlagRegistry.empty()
        assert not r.contains("a")

    def test_add_remove(self):
        """追加・削除は元の登録簿を変えず、新しい旗集合を返す。"""
        empty = WorldFlagRegistry.empty()
        r = empty.with_added("x", "y")
        assert r.contains("x") and r.contains("y")
        r2 = r.with_removed("x")
        assert not r2.contains("x") and r2.contains("y")
        assert empty.as_frozen_set() == frozenset()
        assert r.as_frozen_set() == frozenset({"x", "y"})
        assert r2.as_frozen_set() == frozenset({"y"})

    def test_merge(self):
        """結合は両入力を変えず、その和集合を返す。"""
        a = WorldFlagRegistry.of("a")
        b = WorldFlagRegistry.of("b")
        m = a.merge(b)
        assert m.contains("a") and m.contains("b")
        assert a.as_frozen_set() == frozenset({"a"})
        assert b.as_frozen_set() == frozenset({"b"})
        assert m.as_frozen_set() == frozenset({"a", "b"})

    def test_as_frozen_set(self):
        """公開した旗集合は全要素を含むfrozensetで、外側から変更できない。"""
        r = WorldFlagRegistry.of("z")
        flags = r.as_frozen_set()
        assert "z" in flags
        assert isinstance(flags, frozenset)
        assert flags == frozenset({"z"})
