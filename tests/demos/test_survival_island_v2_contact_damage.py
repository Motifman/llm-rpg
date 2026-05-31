"""survival_island_v2 の接触ダメージ interaction 経路検証 (Phase G #3)。

JSON で `APPLY_DAMAGE` を宣言した interaction (廃屋の崩れた梁・岩礁の縁)
を実行すると、PlayerStatusAggregate の HP が実際に減ることを確認する。
これまで APPLY_DAMAGE は effect_service が DamageSpec を作るところまでで
止まっており、apply_damage が呼ばれていない無効化状態だった。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId


SCENARIO_PATH = (
    Path(__file__).resolve().parents[2]
    / "data"
    / "scenarios"
    / "survival_island_v2.json"
)


@pytest.fixture
def runtime():
    from demos.escape_game.escape_game_runtime import create_escape_game_runtime
    return create_escape_game_runtime(SCENARIO_PATH)


def _move_to_spot(runtime, player_id: PlayerId, spot_string_id: str) -> None:
    """テスト用に強制テレポートで spot を移動させる (do_move を tick 消費させず)。"""
    graph = runtime._spot_graph_repo.find_graph()
    spot_int = runtime.id_mapper.get_int("spot", spot_string_id)
    spot_id = SpotId.create(spot_int)
    eid = EntityId.create(int(player_id))
    # 現在の spot から外して目的地に置く
    graph.unplace_entity(eid)
    graph.place_entity(eid, spot_id)
    runtime._spot_graph_repo.save(graph)


class TestCrumblingBeamDamage:
    """廃屋の崩れた梁を潜ると HP -15。"""

    def test_duck_under_で_HP_15_減る(self, runtime) -> None:
        ada = PlayerId(runtime.scenario.player_spawns[0].player_id)
        # 廃屋にテレポート (沼地経由の道を歩かせると tick が進んでしまうので強制)
        _move_to_spot(runtime, ada, "observation_outpost_ruins")
        status_before = runtime._player_status_repo.find_by_id(ada)
        hp_before = status_before.hp.value

        runtime.do_interact(ada, "crumbling_beam", "duck_under")

        status_after = runtime._player_status_repo.find_by_id(ada)
        assert status_after.hp.value == hp_before - 15

    def test_duck_under_で_chart_fragment_を獲得(self, runtime) -> None:
        ada = PlayerId(runtime.scenario.player_spawns[0].player_id)
        _move_to_spot(runtime, ada, "observation_outpost_ruins")

        runtime.do_interact(ada, "crumbling_beam", "duck_under")

        inv = runtime._player_inventory_repo.find_by_id(ada)
        from ai_rpg_world.domain.player.value_object.slot_id import SlotId
        from ai_rpg_world.application.world_graph.spot_inventory_helpers import (
            collect_owned_item_spec_ids_from_inventory,
        )
        owned = collect_owned_item_spec_ids_from_inventory(inv, runtime._item_repo)
        chart_spec_int = runtime.id_mapper.get_int("item_spec", "chart_fragment")
        assert any(s.value == chart_spec_int for s in owned)


class TestSlipperyCliffDamage:
    """岩礁海岸の濡れた縁を覗き込むと HP -5。"""

    def test_peer_over_で_HP_5_減る(self, runtime) -> None:
        ada = PlayerId(runtime.scenario.player_spawns[0].player_id)
        _move_to_spot(runtime, ada, "rocky_shore")
        status_before = runtime._player_status_repo.find_by_id(ada)
        hp_before = status_before.hp.value

        runtime.do_interact(ada, "slippery_cliff_edge", "peer_over")

        status_after = runtime._player_status_repo.find_by_id(ada)
        assert status_after.hp.value == hp_before - 5
