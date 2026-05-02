"""ScenarioIdMapper のユニットテスト。"""

from __future__ import annotations

import pytest

from ai_rpg_world.infrastructure.scenario.scenario_id_mapper import (
    ScenarioIdMapper,
    ScenarioIdMappingError,
)


class TestScenarioIdMapper:
    def test_register_assigns_sequential_ids(self) -> None:
        mapper = ScenarioIdMapper()
        a = mapper.register("spot", "room_a")
        b = mapper.register("spot", "room_b")
        assert a == 1
        assert b == 2

    def test_register_same_id_returns_same_number(self) -> None:
        mapper = ScenarioIdMapper()
        first = mapper.register("spot", "room_a")
        second = mapper.register("spot", "room_a")
        assert first == second

    def test_get_int_returns_registered_id(self) -> None:
        mapper = ScenarioIdMapper()
        mapper.register("spot", "room_a")
        assert mapper.get_int("spot", "room_a") == 1

    def test_get_int_raises_for_unknown(self) -> None:
        mapper = ScenarioIdMapper()
        with pytest.raises(ScenarioIdMappingError, match="Unknown string ID"):
            mapper.get_int("spot", "nonexistent")

    def test_get_str_returns_string_id(self) -> None:
        mapper = ScenarioIdMapper()
        mapper.register("spot", "room_a")
        assert mapper.get_str("spot", 1) == "room_a"

    def test_get_str_raises_for_unknown(self) -> None:
        mapper = ScenarioIdMapper()
        with pytest.raises(ScenarioIdMappingError, match="Unknown numeric ID"):
            mapper.get_str("spot", 999)

    def test_namespaces_are_independent(self) -> None:
        mapper = ScenarioIdMapper()
        spot_id = mapper.register("spot", "alpha")
        obj_id = mapper.register("object", "alpha")
        assert spot_id == 1
        assert obj_id == 1
        assert mapper.get_str("spot", 1) == "alpha"
        assert mapper.get_str("object", 1) == "alpha"

    def test_contains(self) -> None:
        mapper = ScenarioIdMapper()
        mapper.register("item_spec", "key")
        assert mapper.contains("item_spec", "key") is True
        assert mapper.contains("item_spec", "no_key") is False

    def test_unknown_namespace_raises(self) -> None:
        mapper = ScenarioIdMapper()
        with pytest.raises(ScenarioIdMappingError, match="Unknown namespace"):
            mapper.register("invalid_ns", "x")
