"""station_drill の九区画地図と、今回の拡張範囲を固定する。"""

from __future__ import annotations

from collections import Counter
from copy import deepcopy
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


_SCENARIO_PATH = (
    Path(__file__).resolve().parents[3] / "data" / "scenarios" / "station_drill.json"
)
_KEY_SPOTS = (
    KeySpotRequirement("hall", severity="error"),
    KeySpotRequirement("machine_room", severity="error"),
)
_POSITIONS = {
    "observatory": (-2.0, 2.0),
    "medbay": (0.0, 2.0),
    "greenhouse": (2.0, 2.0),
    "comms": (-2.0, 0.0),
    "hall": (0.0, 0.0),
    "machine_room": (2.0, 0.0),
    "fuel_bay": (-2.0, -2.0),
    "corridor": (0.0, -2.0),
    "storage": (2.0, -2.0),
}
_EXISTING_CONNECTION_TICKS = {
    "hall_to_corridor": 1,
    "corridor_to_storage": 1,
    "hall_to_storage": 2,
    "hall_to_machine_room": 1,
    "machine_room_to_storage": 1,
}
_NEW_CONNECTIONS = {
    "observatory_to_medbay": ("observatory", "medbay", 1),
    "medbay_to_greenhouse": ("medbay", "greenhouse", 1),
    "comms_to_hall": ("comms", "hall", 1),
    "observatory_to_comms": ("observatory", "comms", 1),
    "comms_to_fuel_bay": ("comms", "fuel_bay", 1),
    "medbay_to_hall": ("medbay", "hall", 1),
    "greenhouse_to_machine_room": ("greenhouse", "machine_room", 1),
    "fuel_bay_to_corridor": ("fuel_bay", "corridor", 1),
}
_NEW_SPOT_OBJECTS = {
    "observatory": {
        "weather_instruments",
        "observation_records",
        "bulkhead_panel",
        "observatory_vent",
    },
    "medbay": {"medical_bed", "medical_supply_shelf"},
    "greenhouse": {"cultivation_rack", "grow_lights"},
    "comms": {"mainland_radio"},
    "fuel_bay": {"fuel_tank", "fuel_heater", "fuel_pump"},
}


@pytest.fixture(scope="module")
def raw_station() -> dict[str, Any]:
    return json.loads(_SCENARIO_PATH.read_text(encoding="utf-8"))


class TestStationDrillMapTopology:
    """九区画の座標・接続と、重要地点への冗長経路を保証する。"""

    def test_all_nine_indoor_spots_load_at_the_declared_coordinates(
        self, raw_station: dict[str, Any]
    ) -> None:
        """九区画は設計座標どおりに読み込め、すべて屋内かつ初期照明 BRIGHT である。"""
        loaded = ScenarioLoader().load_from_file(_SCENARIO_PATH)
        loaded_spots = list(loaded.graph.iter_spot_nodes())
        loaded_positions = {
            loaded.id_mapper.get_str("spot", spot.spot_id.value): (
                spot.position.x,
                spot.position.y,
            )
            for spot in loaded_spots
        }
        spots = {spot["id"]: spot for spot in raw_station["spots"]}

        assert len(loaded_spots) == 9
        assert set(spots) == set(_POSITIONS)
        assert loaded_positions == _POSITIONS
        assert all(raw_spot["is_outdoor"] is False for raw_spot in raw_station["spots"])
        assert all(
            raw_spot["atmosphere"]["lighting"] == "BRIGHT"
            for raw_spot in raw_station["spots"]
        )

    def test_thirteen_edges_preserve_the_existing_five_travel_ticks(
        self, raw_station: dict[str, Any]
    ) -> None:
        """接続は設計した 13 辺で、既存 5 辺の移動時間を変更しない。"""
        connections = {edge["id"]: edge for edge in raw_station["connections"]}

        assert len(connections) == 13
        assert {
            edge_id: connections[edge_id]["travel_ticks"]
            for edge_id in _EXISTING_CONNECTION_TICKS
        } == _EXISTING_CONNECTION_TICKS
        assert {
            edge_id: (edge["from"], edge["to"], edge["travel_ticks"])
            for edge_id, edge in connections.items()
            if edge_id in _NEW_CONNECTIONS
        } == _NEW_CONNECTIONS

    def test_validator_reports_no_warning_with_both_key_spots(
        self, raw_station: dict[str, Any]
    ) -> None:
        """hall と machine_room を重要地点として検査しても、単一辺・単一地点喪失を含む警告が無い。"""
        result = validate_spot_map(
            raw_station,
            MapValidationConfig(
                start_spot_id="observatory",
                key_spots=_KEY_SPOTS,
                distance_to_tick_ratio=1.0,
            ),
        )

        assert tuple(requirement.spot_id for requirement in _KEY_SPOTS) == (
            "hall",
            "machine_room",
        )
        assert result.ok is True
        assert result.errors == []
        assert result.warnings == []
        assert result.skipped_checks == []
        assert result.metrics["cycle_rank"] == 5
        assert result.metrics["articulation_spots"] == []

    @pytest.mark.parametrize(
        "key_spot, removed_connections",
        [
            (
                "hall",
                {
                    "comms_to_hall",
                    "hall_to_corridor",
                    "hall_to_storage",
                    "hall_to_machine_room",
                },
            ),
            (
                "machine_room",
                {"hall_to_machine_room", "machine_room_to_storage"},
            ),
        ],
    )
    def test_key_spot_validation_is_not_an_unused_configuration(
        self,
        raw_station: dict[str, Any],
        key_spot: str,
        removed_connections: set[str],
    ) -> None:
        """各重要地点を単一路に変えた反例では、同じ検査設定が到達不能リスクを名指しする。"""
        single_route = deepcopy(raw_station)
        single_route["connections"] = [
            edge
            for edge in single_route["connections"]
            if edge["id"] not in removed_connections
        ]

        result = validate_spot_map(
            single_route,
            MapValidationConfig(start_spot_id="observatory", key_spots=_KEY_SPOTS),
        )

        key_spot_issues = [
            issue
            for issue in result.errors
            if issue.code == "KEY_SPOT_SINGLE_EDGE_ROUTE"
        ]
        assert any(key_spot in issue.spots for issue in key_spot_issues)

    def test_hall_has_the_unique_maximum_degree_of_five(
        self, raw_station: dict[str, Any]
    ) -> None:
        """集会室は次数 5 の唯一の中心で、追加接続が中心性を別区画へ移さない。"""
        degrees: Counter[str] = Counter()
        for edge in raw_station["connections"]:
            degrees[edge["from"]] += 1
            degrees[edge["to"]] += 1

        assert degrees["hall"] == 5
        assert [spot_id for spot_id, degree in degrees.items() if degree == 5] == [
            "hall"
        ]


class TestStationDrillMapExpansionScope:
    """新規区画の設備を保ちつつ、後続のタスク再配置が指定範囲に収まることを保証する。"""

    def test_new_spots_contain_the_declared_non_task_objects(
        self, raw_station: dict[str, Any]
    ) -> None:
        """新規五区画には設計した設備と、その設備に属する追加物体だけがある。"""
        spots = {spot["id"]: spot for spot in raw_station["spots"]}

        assert {
            spot_id: {
                obj["id"] for obj in spots[spot_id]["interior"]["objects"]
            }
            for spot_id in _NEW_SPOT_OBJECTS
        } == _NEW_SPOT_OBJECTS

    def test_new_spots_set_only_the_eight_relocated_task_flags(
        self, raw_station: dict[str, Any]
    ) -> None:
        """新規五区画には指定された8件だけがあり、旧4室のタスクを混ぜない。"""
        spots = {spot["id"]: spot for spot in raw_station["spots"]}
        task_flags = {
            effect.get("parameters", {}).get("flag_name")
            for spot_id in _NEW_SPOT_OBJECTS
            for obj in spots[spot_id]["interior"]["objects"]
            for interaction in obj.get("interactions", [])
            for effect in interaction.get("effects", [])
            if effect.get("effect_type") == "SET_FLAG"
            and str(effect.get("parameters", {}).get("flag_name", "")).startswith(
                "task_"
            )
        }

        assert task_flags == {
            "task_wind_instruments",
            "task_observation_records",
            "task_hygiene_supplies",
            "task_cultivation_stock",
            "task_grow_light_wiring",
            "task_mainland_radio",
            "task_heating_fuel",
            "task_fuel_pump",
        }
