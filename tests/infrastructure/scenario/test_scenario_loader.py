"""ScenarioLoader のユニットテスト。"""

from __future__ import annotations

from pathlib import Path

import pytest

from ai_rpg_world.domain.world.enum.world_enum import SpotCategoryEnum
from ai_rpg_world.domain.world_graph.enum.game_end_condition_type import GameEndConditionTypeEnum
from ai_rpg_world.domain.world_graph.enum.lighting_enum import LightingEnum
from ai_rpg_world.domain.world_graph.enum.temperature_enum import TemperatureEnum
from ai_rpg_world.infrastructure.scenario.scenario_loader import (
    ScenarioLoadError,
    ScenarioLoader,
)

SCENARIO_DIR = Path(__file__).resolve().parents[3] / "data" / "scenarios"
HOSPITAL_SCENARIO = SCENARIO_DIR / "abandoned_hospital.json"


def _minimal_scenario() -> dict:
    return {
        "scenario_format_version": "1.0",
        "metadata": {
            "id": "test",
            "title": "Test Scenario",
            "description": "",
            "theme": "test",
            "difficulty": "easy",
            "estimated_ticks": 10,
            "author": "test",
            "tags": [],
        },
        "item_specs": [
            {"id": "key", "name": "鍵", "description": "ドアの鍵", "category": "KEY_ITEM"},
        ],
        "spots": [
            {
                "id": "room_a",
                "name": "部屋A",
                "description": "テスト部屋A",
                "category": "OTHER",
                "atmosphere": {"lighting": "BRIGHT", "temperature": "NORMAL"},
                "interior": {
                    "objects": [
                        {
                            "id": "chest",
                            "name": "箱",
                            "description": "テスト箱",
                            "object_type": "CHEST",
                            "state": {},
                            "interactions": [
                                {
                                    "action_name": "open",
                                    "display_label": "開ける",
                                    "preconditions": [],
                                    "effects": [
                                        {
                                            "effect_type": "GIVE_ITEM",
                                            "parameters": {"item_spec": "key"},
                                        }
                                    ],
                                }
                            ],
                        }
                    ],
                },
            },
            {
                "id": "room_b",
                "name": "部屋B",
                "description": "テスト部屋B",
            },
        ],
        "connections": [
            {
                "id": "a_to_b",
                "from": "room_a",
                "to": "room_b",
                "name": "扉",
                "travel_ticks": 1,
                "is_bidirectional": True,
                "passage_conditions": [
                    {
                        "condition_type": "ITEM_REQUIRED",
                        "required_item": "key",
                        "failure_message": "鍵が必要です",
                    }
                ],
                "initially_passable": False,
            }
        ],
        "players": [
            {"id": "p1", "name": "Player 1", "spawn_spot": "room_a", "initial_items": []},
        ],
        "game_end_conditions": {
            "win": {"type": "ALL_AT_SPOT", "target_spot": "room_b"},
            "lose": {"type": "TICK_LIMIT", "tick_limit": 50},
        },
        "initial_flags": [],
    }


class TestScenarioLoaderMinimal:
    def test_loads_minimal_scenario(self) -> None:
        loader = ScenarioLoader()
        result = loader.load_from_dict(_minimal_scenario())

        assert result.metadata.id == "test"
        assert result.metadata.title == "Test Scenario"

    def test_creates_spots(self) -> None:
        result = ScenarioLoader().load_from_dict(_minimal_scenario())
        nodes = list(result.graph.iter_spot_nodes())
        assert len(nodes) == 2
        names = {n.name for n in nodes}
        assert "部屋A" in names
        assert "部屋B" in names

    def test_spot_atmosphere(self) -> None:
        result = ScenarioLoader().load_from_dict(_minimal_scenario())
        for node in result.graph.iter_spot_nodes():
            if node.name == "部屋A":
                assert node.atmosphere is not None
                assert node.atmosphere.lighting == LightingEnum.BRIGHT
                assert node.atmosphere.temperature == TemperatureEnum.NORMAL

    def test_creates_connections(self) -> None:
        result = ScenarioLoader().load_from_dict(_minimal_scenario())
        conns = result.graph.all_connections()
        assert len(conns) == 2  # bidirectional → forward + reverse

    def test_passage_condition_on_connection(self) -> None:
        result = ScenarioLoader().load_from_dict(_minimal_scenario())
        for conn in result.graph.all_connections():
            if conn.name == "扉":
                assert len(conn.passage_conditions) == 1
                assert conn.is_passable is False
                break
        else:
            pytest.fail("Connection '扉' not found")

    def test_parses_item_specs(self) -> None:
        result = ScenarioLoader().load_from_dict(_minimal_scenario())
        assert len(result.item_spec_definitions) == 1
        assert result.item_spec_definitions[0].name == "鍵"

    def test_parses_players(self) -> None:
        result = ScenarioLoader().load_from_dict(_minimal_scenario())
        assert len(result.player_spawns) == 1
        assert result.player_spawns[0].name == "Player 1"

    def test_parses_game_end_conditions(self) -> None:
        result = ScenarioLoader().load_from_dict(_minimal_scenario())
        assert len(result.win_conditions) == 1
        assert result.win_conditions[0].condition_type == GameEndConditionTypeEnum.ALL_AT_SPOT
        assert len(result.lose_conditions) == 1
        assert result.lose_conditions[0].condition_type == GameEndConditionTypeEnum.TICK_LIMIT
        assert result.lose_conditions[0].tick_limit == 50

    def test_interior_objects_and_interactions(self) -> None:
        result = ScenarioLoader().load_from_dict(_minimal_scenario())
        for spot_id, interior in result.interiors.items():
            if len(interior.objects) > 0:
                obj = interior.objects[0]
                assert obj.name == "箱"
                assert len(obj.interactions) == 1
                assert obj.interactions[0].action_name == "open"
                return
        pytest.fail("No interior with objects found")

    def test_unsupported_version_raises(self) -> None:
        raw = _minimal_scenario()
        raw["scenario_format_version"] = "99.0"
        with pytest.raises(ScenarioLoadError, match="Unsupported"):
            ScenarioLoader().load_from_dict(raw)

    def test_id_mapper_consistency(self) -> None:
        result = ScenarioLoader().load_from_dict(_minimal_scenario())
        mapper = result.id_mapper
        spot_int = mapper.get_int("spot", "room_a")
        assert mapper.get_str("spot", spot_int) == "room_a"


class TestScenarioLoaderHospital:
    """abandoned_hospital.json の読み込み統合テスト。"""

    @pytest.fixture()
    def result(self):
        return ScenarioLoader().load_from_file(HOSPITAL_SCENARIO)

    def test_loads_all_spots(self, result) -> None:
        nodes = list(result.graph.iter_spot_nodes())
        assert len(nodes) == 8

    def test_all_spots_have_interiors(self, result) -> None:
        for node in result.graph.iter_spot_nodes():
            assert node.spot_id in result.interiors

    def test_locked_connections_exist(self, result) -> None:
        locked = [c for c in result.graph.all_connections() if not c.is_passable]
        assert len(locked) >= 2  # directors_office, hidden_passage, exit_to_outside (+ reverses)

    def test_items_count(self, result) -> None:
        assert len(result.item_spec_definitions) == 10

    def test_lore_items_exist(self, result) -> None:
        lore_items = [i for i in result.item_spec_definitions if i.category == "LORE"]
        assert len(lore_items) >= 3

    def test_two_players(self, result) -> None:
        assert len(result.player_spawns) == 2

    def test_win_condition_is_all_at_outside(self, result) -> None:
        assert len(result.win_conditions) == 1
        wc = result.win_conditions[0]
        assert wc.condition_type == GameEndConditionTypeEnum.ALL_AT_SPOT
        outside_id = result.id_mapper.get_int("spot", "outside")
        assert wc.target_spot_id is not None
        assert int(wc.target_spot_id.value) == outside_id

    def test_lose_condition_is_tick_limit(self, result) -> None:
        assert len(result.lose_conditions) == 1
        assert result.lose_conditions[0].tick_limit == 120

    def test_discoverable_items_in_entrance(self, result) -> None:
        entrance_id_int = result.id_mapper.get_int("spot", "entrance_hall")
        from ai_rpg_world.domain.world.value_object.spot_id import SpotId
        interior = result.interiors[SpotId.create(entrance_id_int)]
        assert len(interior.discoverable_items) == 1

    def test_multiple_interactions_on_emergency_door(self, result) -> None:
        exit_id_int = result.id_mapper.get_int("spot", "emergency_exit")
        from ai_rpg_world.domain.world.value_object.spot_id import SpotId
        interior = result.interiors[SpotId.create(exit_id_int)]
        door = interior.objects[0]
        assert len(door.interactions) == 2  # unlock + use_reagent
