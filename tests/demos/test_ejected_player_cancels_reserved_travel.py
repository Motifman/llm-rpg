"""追放者の移動予約を、実 runtime の tick 境界で取り消す。

追放は player を graph から外すが、ダウンとは異なり ``is_down`` を立てない。
移動予約が残ったままだと、次の tick に graph 上にいない player を動かそうとして
例外になり、以後のワールド進行を止める。予約の作成側ではなく、全予約が通る
消化側と outcome registry の実配線を公開入口で保証する。
"""

from pathlib import Path

from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


_SCENARIO = (
    Path(__file__).resolve().parents[2] / "data" / "scenarios" / "station_drill.json"
)
_KUZE = PlayerId(3)


def test_ejected_player_does_not_resume_reserved_travel_on_the_next_tick() -> None:
    """移動予約後に追放されても、次の tick は例外なく元の spot で at_rest になる。"""
    runtime = create_world_runtime(_SCENARIO)
    starting_spot_id = runtime.id_mapper.get_int("spot", "hall")

    runtime.do_move(_KUZE, "corridor")
    before_ejection = runtime._player_status_repo.find_by_id(_KUZE)
    assert before_ejection is not None
    assert before_ejection.spot_navigation_state is not None
    assert before_ejection.spot_navigation_state.is_traveling
    assert runtime.eject_player(_KUZE)

    runtime.advance_tick()

    after_tick = runtime._player_status_repo.find_by_id(_KUZE)
    assert after_tick is not None
    navigation = after_tick.spot_navigation_state
    assert navigation is not None
    assert not navigation.is_traveling
    assert int(navigation.current_spot_id) == starting_spot_id
