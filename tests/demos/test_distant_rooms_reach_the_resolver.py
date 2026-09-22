"""本番の runtime が、ここでも隣でもない部屋の名前を、行き先の候補にせず失敗理由用にだけ運ぶ。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ai_rpg_world.application.llm.services._argument_resolvers.spot_graph_resolver import (
    DESTINATION_NOT_ADJACENT,
    SpotGraphArgumentResolver,
)
from ai_rpg_world.application.llm.services._resolver_helpers import (
    ToolArgumentResolutionException,
)
from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId

_SCENARIO = Path(__file__).resolve().parents[2] / "data" / "scenarios" / "station_drill.json"
_MORI = PlayerId(1)


def _move(runtime, player_id: PlayerId, spot: str) -> None:
    graph = runtime._spot_graph_repo.find_graph()
    entity_id = EntityId.create(int(player_id))
    graph.unplace_entity(entity_id)
    graph.place_entity(entity_id, SpotId.create(runtime.id_mapper.get_int("spot", spot)))
    runtime._spot_graph_repo.save(graph)


def _spot_names_by_adjacency(current: str) -> tuple[str, set[str], set[str]]:
    """シナリオ JSON から、いまの部屋名・隣の部屋名・それ以外の部屋名を引く。"""
    data = json.loads(_SCENARIO.read_text())
    names = {spot["id"]: spot["name"] for spot in data["spots"]}
    adjacent: set[str] = set()
    for conn in data["connections"]:
        if conn["from"] == current:
            adjacent.add(names[conn["to"]])
        if conn["to"] == current and conn.get("is_bidirectional", True):
            adjacent.add(names[conn["from"]])
    here = names[current]
    return here, adjacent, set(names.values()) - adjacent - {here}


def test_distant_rooms_are_carried_apart_from_the_destinations() -> None:
    """遠い部屋の名前は、ここと隣を除いた世界の部屋そのもので、行き先の候補とは重ならない。"""
    runtime = create_world_runtime(_SCENARIO)
    _move(runtime, _MORI, "corridor")
    here, adjacent, elsewhere = _spot_names_by_adjacency("corridor")

    context = runtime.build_llm_context(_MORI).tool_runtime_context

    assert set(context.distant_spot_names) == elsewhere
    assert here not in context.distant_spot_names
    assert adjacent.isdisjoint(context.distant_spot_names)
    destinations = {t.display_name for t in context.targets.values() if t.kind == "spot_graph_destination"}
    assert destinations.isdisjoint(context.distant_spot_names)


def test_a_distant_room_written_as_a_destination_fails_for_that_reason() -> None:
    """本番の context で遠い部屋を行き先に書くと「隣接していない」で失敗し、行ける場所が並ぶ。"""
    runtime = create_world_runtime(_SCENARIO)
    _move(runtime, _MORI, "corridor")
    context = runtime.build_llm_context(_MORI).tool_runtime_context
    distant_room = sorted(context.distant_spot_names)[0]

    with pytest.raises(ToolArgumentResolutionException) as caught:
        SpotGraphArgumentResolver().resolve_args(
            "travel_to", {"destination_label": distant_room, "inner_thought": ""}, context
        )

    assert caught.value.error_code == DESTINATION_NOT_ADJACENT
    assert str(caught.value).startswith(f"「{distant_room}」はここと隣接していません。有効な接続先: ")
