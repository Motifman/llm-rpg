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
        "environment": {
            "weather": {
                "enabled": True,
                "initial": {"weather_type": "FOG", "intensity": 0.5},
                "update_interval_ticks": 4,
                "announce_changes": True,
            }
        },
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
                                            "effect_type": "CHANGE_OBJECT_STATE",
                                            "parameters": {"new_state": {"opened": True}},
                                        },
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
                "passage": {"kind": "DOOR", "state": "LOCKED"},
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
        "scenario_events": [
            {
                "id": "tick_event",
                "trigger": "ON_TICK",
                "once": True,
                "conditions": [{"condition_type": "TICK_AT_LEAST", "tick": 3}],
                "observation": {
                    "category": "environment",
                    "recipients": "players_at_spot",
                    "target_spot": "room_a",
                    "schedules_turn": True,
                    "breaks_movement": False,
                },
                "effects": [
                    {
                        "effect_type": "SET_FLAG",
                        "parameters": {"flag_name": "tick_event_done"},
                    }
                ],
            }
        ],
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
                assert conn.passage.traversable is False
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
                effect = obj.interactions[0].effects[0]
                assert effect.parameters["state_updates"] == {"opened": True}
                return
        pytest.fail("No interior with objects found")

    def test_parses_scenario_events(self) -> None:
        result = ScenarioLoader().load_from_dict(_minimal_scenario())
        assert len(result.scenario_events) == 1
        ev = result.scenario_events[0]
        assert ev.event_id == "tick_event"
        assert ev.conditions[0].condition_type == "TICK_AT_LEAST"
        assert ev.observation_category == "environment"
        assert ev.recipients == "players_at_spot"
        assert ev.target_spot_id == result.id_mapper.get_int("spot", "room_a")

    def test_parses_weather_config(self) -> None:
        result = ScenarioLoader().load_from_dict(_minimal_scenario())
        assert result.weather_config is not None
        assert result.weather_config.enabled is True
        assert result.weather_config.initial_state.weather_type.value == "FOG"
        assert result.weather_config.initial_state.intensity == 0.5
        assert result.weather_config.update_interval_ticks == 4

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
        assert len(nodes) == 16

    def test_all_spots_have_interiors(self, result) -> None:
        for node in result.graph.iter_spot_nodes():
            assert node.spot_id in result.interiors

    def test_locked_connections_exist(self, result) -> None:
        locked = [c for c in result.graph.all_connections() if not c.passage.traversable]
        assert any(c.name == "裏口への通路" for c in locked)

    def test_items_count(self, result) -> None:
        assert len(result.item_spec_definitions) == 24

    def test_lore_items_exist(self, result) -> None:
        lore_items = [i for i in result.item_spec_definitions if i.category == "LORE"]
        assert len(lore_items) >= 3

    def test_two_players(self, result) -> None:
        assert len(result.player_spawns) == 1

    def test_win_condition_is_all_at_outside(self, result) -> None:
        assert len(result.win_conditions) == 1
        wc = result.win_conditions[0]
        assert wc.condition_type == GameEndConditionTypeEnum.ALL_AT_SPOT
        outside_id = result.id_mapper.get_int("spot", "outside")
        assert wc.target_spot_id is not None
        assert int(wc.target_spot_id.value) == outside_id

    def test_lose_condition_is_tick_limit(self, result) -> None:
        assert len(result.lose_conditions) == 1
        assert result.lose_conditions[0].tick_limit == 150

    def test_revealed_detail_object_starts_hidden(self, result) -> None:
        reception_id_int = result.id_mapper.get_int("spot", "ward_reception")
        from ai_rpg_world.domain.world.value_object.spot_id import SpotId
        interior = result.interiors[SpotId.create(reception_id_int)]
        detail_id = result.id_mapper.get_int("object", "suture_pattern_detail")
        detail = next(
            obj for obj in interior.objects if obj.object_id.value == detail_id
        )
        assert detail.is_visible is False

    def test_hospital_weather_and_scenario_event_metadata(self, result) -> None:
        assert result.weather_config is not None
        assert result.weather_config.initial_state.weather_type.value == "FOG"
        assert result.weather_config.update_interval_ticks == 8
        rear_exit_event = next(
            ev for ev in result.scenario_events if ev.event_id == "rear_exit_route_revealed"
        )
        assert rear_exit_event.recipients == "players_at_spot"
        assert rear_exit_event.breaks_movement is True


class TestScenarioLoaderPassageBlock:
    """`connections[].passage` ブロックの解釈挙動。"""

    def _scenario_with_passage(self, passage_dict) -> dict:
        scn = _minimal_scenario()
        scn["connections"] = [
            {
                "id": "a_b_wall",
                "from": "room_a",
                "to": "room_b",
                "name": "教室間の壁",
                "travel_ticks": 1,
                "is_bidirectional": True,
                "passage": passage_dict,
            }
        ]
        return scn

    def test_wall_intact_passage_yields_impassable_low_sound(self) -> None:
        """passage.kind=WALL,state=INTACT で接続が通行不可・音透過率0.1になる。"""
        scn = self._scenario_with_passage({"kind": "WALL", "state": "INTACT"})
        result = ScenarioLoader().load_from_dict(scn)
        wall_conn = next(
            c for c in result.graph.all_connections() if c.name == "教室間の壁"
        )
        assert wall_conn.passage.traversable is False
        assert wall_conn.passage.sound_permeability == pytest.approx(0.1)
        assert wall_conn.passage is not None
        assert wall_conn.passage.kind.value == "WALL"
        assert wall_conn.passage.state == "INTACT"

    def test_door_open_passage_yields_passable_full_sound(self) -> None:
        """passage.kind=DOOR,state=OPEN で接続が通行可・音透過率1.0になる。"""
        scn = self._scenario_with_passage({"kind": "DOOR", "state": "OPEN"})
        result = ScenarioLoader().load_from_dict(scn)
        conn = next(c for c in result.graph.all_connections() if c.name == "教室間の壁")
        assert conn.passage.traversable is True
        assert conn.passage.sound_permeability == pytest.approx(1.0)

    def test_passage_overrides_apply(self) -> None:
        """passage の sound_permeability override が反映される。"""
        scn = self._scenario_with_passage(
            {"kind": "WALL", "state": "INTACT", "sound_permeability": 0.25}
        )
        result = ScenarioLoader().load_from_dict(scn)
        conn = next(c for c in result.graph.all_connections() if c.name == "教室間の壁")
        assert conn.passage.sound_permeability == pytest.approx(0.25)

    def test_unknown_kind_raises_validation(self) -> None:
        """未知の passage.kind は PassageValidationException になる。"""
        from ai_rpg_world.domain.world_graph.exception.spot_graph_exception import (
            PassageValidationException,
        )

        scn = self._scenario_with_passage({"kind": "MAGICAL_VOID"})
        with pytest.raises(PassageValidationException, match="passage.kind"):
            ScenarioLoader().load_from_dict(scn)

    def test_open_traversable_override_via_scenario(self) -> None:
        """OPEN でも traversable override がシナリオJSON経由で適用される。"""
        scn = self._scenario_with_passage(
            {"kind": "OPEN", "traversable": False, "sound_permeability": 0.5}
        )
        result = ScenarioLoader().load_from_dict(scn)
        conn = next(c for c in result.graph.all_connections() if c.name == "教室間の壁")
        assert conn.passage.traversable is False
        assert conn.passage.sound_permeability == pytest.approx(0.5)

    def test_legacy_initially_passable_key_is_rejected(self) -> None:
        """旧スキーマの `initially_passable` キーが残っていれば作家エラーになる。"""
        from ai_rpg_world.infrastructure.scenario.scenario_loader import ScenarioLoadError

        scn = _minimal_scenario()
        scn["connections"] = [
            {
                "id": "a_b_wall",
                "from": "room_a",
                "to": "room_b",
                "name": "教室間の壁",
                "travel_ticks": 1,
                "is_bidirectional": True,
                "initially_passable": True,
                "passage": {"kind": "OPEN"},
            }
        ]
        with pytest.raises(ScenarioLoadError, match="initially_passable"):
            ScenarioLoader().load_from_dict(scn)

    def test_legacy_sound_permeability_top_level_key_is_rejected(self) -> None:
        """旧スキーマの接続レベル `sound_permeability` キーが残っていれば作家エラーになる。"""
        from ai_rpg_world.infrastructure.scenario.scenario_loader import ScenarioLoadError

        scn = _minimal_scenario()
        scn["connections"] = [
            {
                "id": "a_b_wall",
                "from": "room_a",
                "to": "room_b",
                "name": "教室間の壁",
                "travel_ticks": 1,
                "is_bidirectional": True,
                "sound_permeability": 0.5,
                "passage": {"kind": "OPEN"},
            }
        ]
        with pytest.raises(ScenarioLoadError, match="sound_permeability"):
            ScenarioLoader().load_from_dict(scn)
