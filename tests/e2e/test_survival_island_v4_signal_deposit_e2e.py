"""v4 狼煙台へ材料を持ち寄り、実所持と object.state を一致させる E2E。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.support.overflow_sinks import IGNORE_OVERFLOW

from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime
from ai_rpg_world.application.world_graph.spot_inventory_helpers import (
    count_owned_item_instances_by_spec,
    grant_item_specs_to_inventory,
)
from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.exception.spot_graph_exception import (
    InteractionNotAllowedException,
)
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId
from ai_rpg_world.domain.world_graph.value_object.spot_object_id import SpotObjectId


SCENARIO = (
    Path(__file__).resolve().parents[2]
    / "data"
    / "scenarios"
    / "survival_island_v4_coop.json"
)


def _player_id(runtime, string_id: str) -> PlayerId:
    spawn = next(s for s in runtime.scenario.player_spawns if s.string_id == string_id)
    return PlayerId(int(spawn.player_id))


def _item_id(runtime, string_id: str) -> ItemSpecId:
    return ItemSpecId.create(runtime.id_mapper.get_int("item_spec", string_id))


def _pit_id(runtime) -> SpotObjectId:
    return SpotObjectId.create(runtime.id_mapper.get_int("object", "signal_fire_pit"))


def _move_to_summit(runtime, *players: PlayerId) -> None:
    graph = runtime._spot_graph_repo.find_graph()
    summit = SpotId.create(runtime.id_mapper.get_int("spot", "summit"))
    for player in players:
        entity = EntityId.create(int(player))
        graph.unplace_entity(entity)
        graph.place_entity(entity, summit)
    runtime._spot_graph_repo.save(graph)


def _grant(runtime, player: PlayerId, *items: str) -> None:
    grant_item_specs_to_inventory(
        player,
        tuple(_item_id(runtime, item) for item in items),
        runtime._item_repo,
        runtime._item_spec_repo,
        runtime._player_inventory_repo,
        overflow_sink=IGNORE_OVERFLOW,
    )


def _owned_count(runtime, player: PlayerId, item: str) -> int:
    inventory = runtime._player_inventory_repo.find_by_id(player)
    counts = count_owned_item_instances_by_spec(inventory, runtime._item_repo)
    return counts.get(_item_id(runtime, item), 0)


def _pit(runtime):
    summit = SpotId.create(runtime.id_mapper.get_int("spot", "summit"))
    return runtime._spot_interior_repo.find_by_spot_id(summit).get_object(_pit_id(runtime))


class TestDistributedSignalDeposit:
    """別々の所持者が順に投入し、実インベントリから消えた合計で点火できる。"""

    def test_two_players_deposit_materials_then_light_signal(self) -> None:
        """2人が流木2+1と枯れ葉2を持ち寄ると、所持を消費して狼煙を点火できる。"""
        runtime = create_world_runtime(SCENARIO)
        ada = _player_id(runtime, "ada")
        noah = _player_id(runtime, "noah")
        _move_to_summit(runtime, ada, noah)
        _grant(runtime, ada, "driftwood", "driftwood", "flint")
        _grant(runtime, noah, "driftwood", "dry_leaves", "dry_leaves")

        runtime._interaction_service.execute_interaction(
            ada, _pit_id(runtime), "add_driftwood"
        )
        runtime._interaction_service.execute_interaction(
            noah, _pit_id(runtime), "add_driftwood"
        )
        runtime._interaction_service.execute_interaction(
            noah, _pit_id(runtime), "add_dry_leaves"
        )
        result = runtime._interaction_service.execute_interaction(
            ada, _pit_id(runtime), "light_signal"
        )

        assert _owned_count(runtime, ada, "driftwood") == 0
        assert _owned_count(runtime, noah, "driftwood") == 0
        assert _owned_count(runtime, noah, "dry_leaves") == 0
        assert _pit(runtime).state["driftwood_stacked"] == 3
        assert _pit(runtime).state["dry_leaves_stacked"] == 2
        assert _pit(runtime).state["lit"] is True
        assert "白い煙" in " ".join(result.messages)

    def test_direct_light_with_personal_materials_fails_before_deposit(self) -> None:
        """1人が旧条件の材料3+2+1を持っていても、狼煙台へ積む前は点火できない。"""
        runtime = create_world_runtime(SCENARIO)
        ada = _player_id(runtime, "ada")
        noah = _player_id(runtime, "noah")
        _move_to_summit(runtime, ada, noah)
        _grant(
            runtime,
            ada,
            "driftwood",
            "driftwood",
            "driftwood",
            "dry_leaves",
            "dry_leaves",
            "flint",
        )

        with pytest.raises(InteractionNotAllowedException, match="流木が足りない"):
            runtime._interaction_service.execute_interaction(
                ada, _pit_id(runtime), "light_signal"
            )

        assert _pit(runtime).state["lit"] is False
        assert _owned_count(runtime, ada, "driftwood") == 3

    def test_deposit_wakes_co_located_witness_with_declared_message(self) -> None:
        """投入の目撃文は同席者へ届き、観測駆動で次の起動を予約する。"""
        runtime = create_world_runtime(SCENARIO)
        ada = _player_id(runtime, "ada")
        noah = _player_id(runtime, "noah")
        _move_to_summit(runtime, ada, noah)
        _grant(runtime, ada, "driftwood")
        runtime._obs_buffer.drain(noah)

        runtime._interaction_service.execute_interaction(
            ada, _pit_id(runtime), "add_driftwood"
        )

        outputs = [entry.output for entry in runtime._obs_buffer.get_observations(noah)]
        witnessed = next(
            output for output in outputs if "狼煙台に流木を積み上げた" in output.prose
        )
        assert witnessed.prose == "エイダが狼煙台に流木を積み上げた。"
        assert witnessed.schedules_turn is True

    def test_fixed_three_with_two_owned_keeps_inventory_and_state_in_sync(
        self, tmp_path: Path
    ) -> None:
        """quantity=3 に対して所持2個なら、実インベントリ減算と state 加算はともに2になる。"""
        scenario = json.loads(SCENARIO.read_text(encoding="utf-8"))
        pit = next(
            obj
            for spot in scenario["spots"]
            if spot["id"] == "summit"
            for obj in spot["interior"]["objects"]
            if obj["id"] == "signal_fire_pit"
        )
        deposit = next(
            action
            for action in pit["interactions"]
            if action["action_name"] == "add_driftwood"
        )
        deposit["effects"][0]["parameters"]["quantity"] = 3
        path = tmp_path / "fixed_quantity_deposit.json"
        path.write_text(json.dumps(scenario, ensure_ascii=False), encoding="utf-8")
        runtime = create_world_runtime(path)
        ada = _player_id(runtime, "ada")
        _move_to_summit(runtime, ada)
        _grant(runtime, ada, "driftwood", "driftwood")

        runtime._interaction_service.execute_interaction(
            ada, _pit_id(runtime), "add_driftwood"
        )

        assert _owned_count(runtime, ada, "driftwood") == 0
        assert _pit(runtime).state["driftwood_stacked"] == 2
