"""station_drill の位置表示盤が、名前を漏らさず生者と遺体の反応数を示すことを保証する。"""

from pathlib import Path

import pytest

from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId


_SCENARIO = Path(__file__).resolve().parents[2] / "data/scenarios/station_drill.json"
_MORI = PlayerId(1)
_SENA = PlayerId(2)
_KUZE = PlayerId(3)
_PLAYER_NAMES = ("モリ", "セナ", "クゼ", "アオイ", "ハギ", "ユラ", "ジン", "サキ")
_SPOT_NAMES = ("観測室", "医務室", "温室", "通信室", "燃料庫", "集会室", "連絡通路", "物資庫", "機関室")


@pytest.fixture()
def runtime():
    return create_world_runtime(_SCENARIO)


def _spot(runtime, name: str) -> SpotId:
    return SpotId.create(runtime.id_mapper.get_int("spot", name))


def _place(runtime, player_id: PlayerId, spot_name: str) -> None:
    graph = runtime._spot_graph_repo.find_graph()
    entity = EntityId.create(int(player_id))
    try:
        graph.unplace_entity(entity)
    except Exception:
        pass
    graph.place_entity(entity, _spot(runtime, spot_name))
    graph.clear_events()
    runtime._spot_graph_repo.save(graph)


def _view(runtime, player_id: PlayerId) -> str:
    result = runtime.do_interact(
        player_id, "station_occupancy_display", "view_room_occupancy"
    )
    return "\n".join(result.messages)


def test_display_lists_all_nine_rooms_but_no_player_names(runtime) -> None:
    """表示盤は無人室を含む9区画の反応数を出し、誰の名前も表示しない。"""
    _place(runtime, _MORI, "observatory")

    message = _view(runtime, _MORI)

    assert message.count("\n- ") == 9
    for spot_name in _SPOT_NAMES:
        assert f"- {spot_name}:" in message
    assert "- 観測室: 1 人" in message
    assert "- 集会室: 7 人" in message
    assert all(player_name not in message for player_name in _PLAYER_NAMES)


@pytest.mark.parametrize("player_id", [_MORI, _KUZE])
def test_crew_and_impostor_can_both_use_the_display(runtime, player_id) -> None:
    """役割にかかわらず、生存しているクルーとインポスターは表示盤を使える。"""
    _place(runtime, player_id, "observatory")

    assert "観測室: 1 人" in _view(runtime, player_id)


def test_fallen_body_counts_as_one_but_departed_position_does_not(runtime) -> None:
    """遺体は一つの反応として残り、同じ死者の幽霊位置を二重には数えない。"""
    _place(runtime, _MORI, "observatory")
    _place(runtime, _SENA, "observatory")
    _place(runtime, _KUZE, "observatory")
    runtime.do_interact_with_player(_KUZE, _MORI, "strike_down")
    # 表示盤の範囲が幽霊 store を参照しないことを独立に固定する。
    runtime._departed_position_store.place(_MORI, _spot(runtime, "machine_room"))

    message = _view(runtime, _SENA)

    # セナとクゼの生者2人 + モリの遺体1体。幽霊のモリは機関室へ足さない。
    assert "- 観測室: 3 人" in message
    assert "- 機関室: 0 人" in message


def test_same_room_witness_sees_someone_looking_at_the_display(runtime) -> None:
    """表示内容は本人だけに返し、同席者には閲覧した行為だけが見える。"""
    _place(runtime, _MORI, "observatory")
    _place(runtime, _SENA, "observatory")

    _view(runtime, _MORI)

    prose = [
        entry.output.prose
        for entry in runtime._obs_buffer.get_observations(_SENA)
    ]
    assert "モリが位置表示盤を覗き込んでいる。" in prose
    assert not any("集会室:" in message for message in prose)
