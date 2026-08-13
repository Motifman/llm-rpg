"""去った主体の有効化と interaction ごとの能力宣言を保証する。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ai_rpg_world.domain.world_graph.enum.interaction_actor_plane import (
    InteractionActorPlane,
)
from ai_rpg_world.infrastructure.scenario.scenario_loader import (
    ScenarioLoadError,
    ScenarioLoader,
)


_ROOT = Path(__file__).resolve().parents[3]
_DRILL = _ROOT / "data" / "scenarios" / "station_drill.json"
_LEGACY = _ROOT / "tests" / "fixtures" / "scenarios" / "darkened_station.json"


def _interaction(result, action_name: str):
    for node in result.graph.iter_spot_nodes():
        interior = result.interiors.get(node.spot_id)
        if interior is None:
            continue
        for obj in interior.objects:
            for interaction in obj.interactions:
                if interaction.action_name == action_name:
                    return interaction
    raise AssertionError(f"interaction not found: {action_name}")


def _player_interaction(result, action_name: str):
    for interaction in result.player_interactions:
        if interaction.action_name == action_name:
            return interaction
    raise AssertionError(f"player interaction not found: {action_name}")


def test_station_drill_explicitly_enables_departed_agents() -> None:
    """station_drill だけが去った主体を明示的に有効化する。"""
    assert ScenarioLoader().load_from_file(_DRILL).departed_agents_enabled is True


def test_scenario_without_the_declaration_keeps_the_feature_disabled() -> None:
    """宣言の無い既存シナリオは従来どおり死亡後の手番を持たない。"""
    assert ScenarioLoader().load_from_file(_LEGACY).departed_agents_enabled is False


def test_task_and_lantern_declare_different_actor_planes() -> None:
    """担当作業は両層、ランタン取得は生者だけに限定される。"""
    result = ScenarioLoader().load_from_file(_DRILL)

    assert _interaction(result, "inspect_grow_light_wiring").allowed_actor_planes == (
        InteractionActorPlane.LIVING,
        InteractionActorPlane.DEPARTED,
    )
    assert _interaction(result, "take_lantern").allowed_actor_planes == (
        InteractionActorPlane.LIVING,
    )


def test_station_player_interactions_are_explicitly_living_only() -> None:
    """襲撃と略奪は幽霊から除外する層を、既定値に頼らず宣言する。"""
    result = ScenarioLoader().load_from_file(_DRILL)

    for action_name in (
        "strike_down",
        "loot_from_downed",
    ):
        assert _player_interaction(result, action_name).allowed_actor_planes == (
            InteractionActorPlane.LIVING,
        )


def test_unknown_actor_plane_fails_while_loading(tmp_path: Path) -> None:
    """未知の層名は実験開始後まで持ち越さず、シナリオ読込時に拒否する。"""
    raw = json.loads(_DRILL.read_text(encoding="utf-8"))
    interaction = next(
        interaction
        for spot in raw["spots"]
        for obj in spot.get("interior", {}).get("objects", [])
        for interaction in obj.get("interactions", [])
    )
    interaction["allowed_actor_planes"] = ["LIVING", "UNKNOWN"]
    path = tmp_path / "invalid.json"
    path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(ScenarioLoadError, match="allowed_actor_planes"):
        ScenarioLoader().load_from_file(path)


def test_departed_agents_enabled_requires_a_boolean(tmp_path: Path) -> None:
    """有効化宣言を文字列で書くと truthy と解釈せず、起動前に拒否する。"""
    raw = json.loads(_LEGACY.read_text(encoding="utf-8"))
    raw["departed_agents_enabled"] = "true"
    path = tmp_path / "invalid-departed-agents-enabled.json"
    path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(ScenarioLoadError, match="departed_agents_enabled"):
        ScenarioLoader().load_from_file(path)
