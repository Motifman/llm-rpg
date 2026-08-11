"""station_drill のランタンを、停電中に取得できる有限資源として保証する。

run 013 ではモリとハギが初期所持するランタン自身によって暗所が DIM になり、
この2人を構造的に襲えなかった。ランタンを物資庫へ移すだけでは、通常の物体が
DARK で見えないため「灯りを取るために灯りが要る」詰みになる。本試験は明示した
停電、暗所での取得、取得後の防御を公開 runtime から一続きで固定する。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ai_rpg_world.application.world_graph.spot_inventory_helpers import (
    collect_owned_item_spec_ids_from_inventory,
)
from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.exception.spot_graph_exception import (
    InteractionNotAllowedException,
)
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId
from tests.demos.station_drill_lighting_helpers import darken_spot

_SCENARIO = (
    Path(__file__).resolve().parents[2] / "data" / "scenarios" / "station_drill.json"
)

_MORI, _SENA, _KUZE, _AOI, _HAGI = (PlayerId(i) for i in range(1, 6))
_CREW = (_MORI, _SENA, _AOI, _HAGI)
_DARK_SPOTS = ("corridor", "storage", "machine_room")


def _move(runtime, player_id: PlayerId, spot: str) -> None:
    graph = runtime._spot_graph_repo.find_graph()
    entity = EntityId.create(int(player_id))
    graph.unplace_entity(entity)
    graph.place_entity(
        entity,
        SpotId.create(runtime.id_mapper.get_int("spot", spot)),
    )
    runtime._spot_graph_repo.save(graph)


def _owns_lantern(runtime, player_id: PlayerId) -> bool:
    inventory = runtime._player_inventory_repo.find_by_id(player_id)
    assert inventory is not None
    owned = collect_owned_item_spec_ids_from_inventory(
        inventory, runtime._item_repo
    )
    lantern = runtime.id_mapper.get_int("item_spec", "lantern")
    return any(spec.value == lantern for spec in owned)


class TestLanternsStartInStorage:
    """初期所持をやめても、停電した物資庫からランタン2個を取得できる。"""

    def test_mori_and_hagi_start_without_lanterns(self) -> None:
        """run 013 で常時守られていたモリとハギは、無灯火で開始する。"""
        runtime = create_world_runtime(_SCENARIO)

        assert not _owns_lantern(runtime, _MORI)
        assert not _owns_lantern(runtime, _HAGI)

    def test_two_lanterns_are_reachable_through_the_public_runtime(self) -> None:
        """灯りの無い人物にもケースと取得操作が見え、2人が1個ずつ取れる。

        ``build_observation`` で対象を登録してから ``do_interact`` する公開入口を
        通す。内部サービスを直接呼ぶと、暗所の対象解決が詰んでいても通るため。
        """
        runtime = create_world_runtime(_SCENARIO)
        darken_spot(runtime, "storage")

        for player_id in (_MORI, _HAGI):
            _move(runtime, player_id, "storage")
            prompt = runtime.build_observation(player_id)
            assert "非常用ランタンケース" in prompt
            assert 'ランタンを取り出す → "take_lantern"' in prompt
            if player_id == _MORI:
                assert "資材棚" not in prompt, (
                    "暗所可視は非常用品の宣言だけに効き、通常物体を漏らさない"
                )

            runtime.do_interact(
                player_id, "emergency_lantern_case", "take_lantern"
            )
            assert _owns_lantern(runtime, player_id)


@pytest.mark.parametrize("spot", _DARK_SPOTS)
@pytest.mark.parametrize("target", _CREW)
def test_every_unlit_crew_member_can_be_struck_in_each_dark_spot(
    spot: str,
    target: PlayerId,
) -> None:
    """停電させた3室では、灯りの無い全クルーが strike_down の対象になる。"""
    runtime = create_world_runtime(_SCENARIO)
    darken_spot(runtime, spot)
    _move(runtime, _KUZE, spot)
    _move(runtime, target, spot)

    runtime.do_interact_with_player(_KUZE, target, "strike_down")

    assert runtime._player_status_repo.find_by_id(target).is_down


def test_a_crew_member_who_takes_a_lantern_can_still_be_struck() -> None:
    """ランタンで暗所が DIM になっても、一本化した襲撃は実行できる。"""
    runtime = create_world_runtime(_SCENARIO)
    darken_spot(runtime, "storage")
    _move(runtime, _MORI, "storage")
    runtime.build_observation(_MORI)
    runtime.do_interact(_MORI, "emergency_lantern_case", "take_lantern")
    darken_spot(runtime, "corridor")
    _move(runtime, _KUZE, "corridor")
    _move(runtime, _MORI, "corridor")

    runtime.do_interact_with_player(_KUZE, _MORI, "strike_down")

    assert runtime._player_status_repo.find_by_id(_MORI).is_down
