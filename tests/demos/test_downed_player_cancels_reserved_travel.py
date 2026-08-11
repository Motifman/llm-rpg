"""ダウンしたプレイヤーが、予約済みの移動で次の tick に動かないことを保証する。

run 012 では、セナが連絡通路から物資庫への移動を予約した同じ tick にクゼに
倒された。その次の tick で予約だけが消化され、死体が物資庫へ移動したため、
死体発見と会議の位置情報まで殺害現場と食い違った。

予約の作成経路ではなく、tick 境界で予約を消化する共通経路で止める。今後別の
移動予約入口が増えても、ダウン中の身体が勝手に移動しないためである。
"""

from pathlib import Path

from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId
from tests.demos.station_drill_lighting_helpers import darken_spot


_SCENARIO = (
    Path(__file__).resolve().parents[2] / "data" / "scenarios" / "station_drill.json"
)
_SENA = PlayerId(2)
_KUZE = PlayerId(3)


def _place(runtime, player_id: PlayerId, spot_name: str) -> None:
    graph = runtime._spot_graph_repo.find_graph()
    entity_id = EntityId.create(int(player_id))
    graph.unplace_entity(entity_id)
    graph.place_entity(
        entity_id,
        SpotId.create(runtime.id_mapper.get_int("spot", spot_name)),
    )
    runtime._spot_graph_repo.save(graph)


def test_downed_player_stays_at_the_attack_scene_on_the_next_tick() -> None:
    """移動予約後に同じ tick で倒されると、次の tick でも殺害現場に留まる。"""
    runtime = create_world_runtime(_SCENARIO)
    _place(runtime, _SENA, "corridor")
    _place(runtime, _KUZE, "corridor")
    darken_spot(runtime)

    runtime.do_move(_SENA, "storage")
    runtime.do_interact_with_player(_KUZE, _SENA, "strike_down")

    assert runtime.get_player_spot_name(_SENA) == "連絡通路"
    assert runtime._player_status_repo.find_by_id(_SENA).is_down

    runtime.advance_tick()

    assert runtime.get_player_spot_name(_SENA) == "連絡通路"
    navigation = runtime._player_status_repo.find_by_id(
        _SENA
    ).spot_navigation_state
    assert navigation is not None
    assert not navigation.is_traveling
