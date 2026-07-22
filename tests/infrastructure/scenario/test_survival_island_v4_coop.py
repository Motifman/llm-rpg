"""survival_island_v4_coop の静的な読み込み・地図品質を保証する。"""

from __future__ import annotations

import heapq
import json
from pathlib import Path
from typing import Any

import pytest

from ai_rpg_world.infrastructure.scenario.scenario_loader import ScenarioLoader
from ai_rpg_world.infrastructure.scenario.spot_map_validator import (
    KeySpotRequirement,
    MapValidationConfig,
    validate_spot_map,
)


_SCENARIOS = Path(__file__).resolve().parents[3] / "data" / "scenarios"
_V3_PATH = _SCENARIOS / "survival_island_v3_coop.json"
_V4_PATH = _SCENARIOS / "survival_island_v4_coop.json"


@pytest.fixture(scope="module")
def raw_v4() -> dict[str, Any]:
    return json.loads(_V4_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def loaded_v4():
    return ScenarioLoader().load_from_file(_V4_PATH)


class TestSurvivalIslandV4Load:
    """v4 シナリオが loader で解決でき、座標つき新版として識別できることを保証する。"""

    def test_loads_as_new_scenario_without_replacing_v3(self, loaded_v4) -> None:
        """v4 は v3 と別 id のシナリオとして読み込まれ、実験再現性のため v3 を置換しない。"""
        assert _V3_PATH.exists()
        assert loaded_v4.metadata.id == "survival_island_v4_coop"

    def test_all_spots_have_position_and_bidirectional_connections_expand(self, loaded_v4) -> None:
        """全 25 spot に position があり、33 本の双方向接続は loader 上で 66 接続に展開される。"""
        spots = list(loaded_v4.graph.iter_spot_nodes())

        assert len(spots) == 25
        assert sum(1 for spot in spots if spot.position is not None) == 25
        assert len(loaded_v4.graph.all_connections()) == 66

    def test_loads_six_areas_and_all_spots_have_area_id(self, loaded_v4) -> None:
        """v4 は6区画の area 定義を持ち、全 spot がいずれかの area_id に属する。"""
        areas = {area.area_id: area for area in loaded_v4.areas}
        spots = list(loaded_v4.graph.iter_spot_nodes())

        assert set(areas) == {"shore", "base", "forest", "river", "mountain", "swamp"}
        assert all(spot.area_id in areas for spot in spots)
        assert areas["mountain"].visible_name == "切り立った山影"
        assert areas["mountain"].prominence == 0.95
        assert areas["mountain"].position_source == "centroid"

    def test_loads_signal_smoke_distant_cue_from_object_state(self, loaded_v4) -> None:
        """狼煙の遠景兆候は救助 flag ではなく signal_fire_pit.state.lit を source にする。"""
        assert len(loaded_v4.distant_cues) == 1
        cue = loaded_v4.distant_cues[0]

        assert cue.cue_id == "summit_signal_smoke"
        assert cue.source.kind == "object_state"
        assert (
            cue.source.object_id.value
            == loaded_v4.id_mapper.get_int("object", "signal_fire_pit")
        )
        assert cue.source.state_key == "lit"
        assert cue.source.equals is True
        assert cue.origin_area_id == "mountain"
        assert cue.visible_name == "白い煙"
        assert cue.prominence == 1.0
        assert cue.ambient_descriptions["far"] == "北東の山の方に白い煙が見える。"
        assert cue.appear_event is not None
        assert cue.appear_event.message == "{direction}の山の方から白い煙が上がった。"
        assert cue.appear_event.schedules_turn is True


class TestSurvivalIslandV4MapValidation:
    """v4 の座標・接続品質を spot map validator で固定する。"""

    def test_validator_accepts_v4_without_errors_or_distance_mismatch(self, raw_v4) -> None:
        """距離係数 1.6 の検査で error と travel_ticks 距離不整合を出さない。"""
        result = validate_spot_map(
            raw_v4,
            MapValidationConfig(
                start_spot_id="campsite",
                key_spots=(KeySpotRequirement("summit"),),
                distance_to_tick_ratio=1.6,
            ),
        )

        assert result.ok is True
        assert result.errors == []
        assert result.skipped_checks == []
        assert result.metrics["positioned_spot_count"] == 25
        assert result.metrics["area_count"] == 6
        assert result.metrics["distant_cue_count"] == 1
        assert result.metrics["unreachable_spots"] == []
        assert result.metrics["cycle_rank"] == 9
        assert result.metrics["articulation_spots"] == [
            "cave_entry",
            "foothills",
            "highland_spring",
            "mountain_path",
            "observation_outpost_ruins",
            "shipwreck_beach",
        ]
        assert "TRAVEL_TICKS_DISTANCE_MISMATCH" not in {
            issue.code for issue in result.warnings
        }
        assert "SPOT_AREA_ID_MISSING" not in {issue.code for issue in result.warnings}
        assert "AREA_CENTROID_UNAVAILABLE" not in {issue.code for issue in result.errors}
        assert not {
            issue.code for issue in result.errors if issue.code.startswith("DISTANT_CUE")
        }


class TestSurvivalIslandV4CoveCarving:
    """hidden_cove の東ルート案内断片が read 系 interaction として配置されていることを保証する。"""

    def test_cove_carving_reveals_east_route_without_existing_consumer(self, raw_v4) -> None:
        """cove_carving は east_route_revealed を立てるが、現時点では参照側を持たない知識フラグである。"""
        interaction = _find_interaction(raw_v4, "hidden_cove", "cove_carving", "read_carving")

        assert interaction["display_label"] == "刻み跡を読む"
        assert (
            interaction["witness_observation_message"]
            == "{actor}が入江の岩肌の刻み跡を読んでいる。"
        )
        effect_types = [effect["effect_type"] for effect in interaction["effects"]]
        assert effect_types == ["CHANGE_OBJECT_STATE", "SET_FLAG", "SHOW_MESSAGE"]
        flag_effect = interaction["effects"][1]
        assert flag_effect["parameters"] == {
            "flag_name": "east_route_revealed",
            "value": True,
        }
        assert _flag_reference_count(raw_v4, "east_route_revealed") == 1

    def test_cove_carving_is_loaded_with_witness_message(self, loaded_v4) -> None:
        """ScenarioLoader 後も read_carving と目撃者文面が InteractionDef に残る。"""
        interactions = {
            (obj.name, interaction.action_name): interaction
            for interior in loaded_v4.interiors.values()
            for obj in interior.objects
            for interaction in obj.interactions
        }

        interaction = interactions[("岩肌の刻み跡", "read_carving")]

        assert interaction.witness_observation_message == "{actor}が入江の岩肌の刻み跡を読んでいる。"
        assert [effect.effect_type.value for effect in interaction.effects] == [
            "CHANGE_OBJECT_STATE",
            "SET_FLAG",
            "SHOW_MESSAGE",
        ]


class TestSurvivalIslandV4SurvivalEconomy:
    """v4 の移動時間変更が救助窓に対して破綻しないことを粗く固定する。"""

    def test_shortest_campsite_to_summit_route_still_fits_rescue_window(self, raw_v4) -> None:
        """拠点から山頂への最短移動だけで救助窓 144/192 tick を不可能にしない。"""
        travel_ticks, route = _shortest_path(raw_v4, "campsite", "summit")

        assert travel_ticks == 9
        assert route == [
            "campsite_to_river_mouth",
            "river_mouth_to_upper",
            "upper_to_spring",
            "spring_to_foothills",
            "foothills_to_path",
            "path_to_summit",
        ]
        assert travel_ticks < raw_v4["outcome_resolution"]["rescue_at_ticks"][0]
        assert raw_v4["outcome_resolution"]["stranded_at_tick"] == 240


def _find_spot(raw: dict[str, Any], spot_id: str) -> dict[str, Any]:
    for spot in raw["spots"]:
        if spot["id"] == spot_id:
            return spot
    raise AssertionError(f"spot not found: {spot_id}")


def _find_object(raw: dict[str, Any], spot_id: str, object_id: str) -> dict[str, Any]:
    interior = _find_spot(raw, spot_id).get("interior") or {}
    for obj in interior.get("objects", []):
        if obj["id"] == object_id:
            return obj
    raise AssertionError(f"object not found: {spot_id}/{object_id}")


def _find_interaction(
    raw: dict[str, Any],
    spot_id: str,
    object_id: str,
    action_name: str,
) -> dict[str, Any]:
    for interaction in _find_object(raw, spot_id, object_id).get("interactions", []):
        if interaction["action_name"] == action_name:
            return interaction
    raise AssertionError(f"interaction not found: {spot_id}/{object_id}.{action_name}")


def _flag_reference_count(raw: Any, flag_name: str) -> int:
    if isinstance(raw, dict):
        return sum(
            (1 if key == "flag_name" and value == flag_name else 0)
            + _flag_reference_count(value, flag_name)
            for key, value in raw.items()
        )
    if isinstance(raw, list):
        return sum(_flag_reference_count(item, flag_name) for item in raw)
    return 0


def _shortest_path(raw: dict[str, Any], start: str, goal: str) -> tuple[int, list[str]]:
    graph: dict[str, list[tuple[str, int, str]]] = {spot["id"]: [] for spot in raw["spots"]}
    for connection in raw["connections"]:
        source = connection["from"]
        target = connection["to"]
        travel_ticks = int(connection.get("travel_ticks", 1))
        edge_id = connection["id"]
        graph[source].append((target, travel_ticks, edge_id))
        if connection.get("is_bidirectional", True):
            graph[target].append((source, travel_ticks, edge_id))

    queue: list[tuple[int, str, list[str]]] = [(0, start, [])]
    visited: set[str] = set()
    while queue:
        distance, spot_id, route = heapq.heappop(queue)
        if spot_id in visited:
            continue
        visited.add(spot_id)
        if spot_id == goal:
            return distance, route
        for next_spot, travel_ticks, edge_id in graph[spot_id]:
            if next_spot not in visited:
                heapq.heappush(queue, (distance + travel_ticks, next_spot, route + [edge_id]))
    raise AssertionError(f"route not found: {start}->{goal}")
