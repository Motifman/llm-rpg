"""会議の判断材料として、最後の集合からの世界時間を末尾へ表示する。"""

from __future__ import annotations

from pathlib import Path

import pytest

from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


_DRILL = (
    Path(__file__).resolve().parents[2] / "data" / "scenarios" / "station_drill.json"
)
_MORI = PlayerId(1)
_KUZE = PlayerId(3)
_HEADER = "【時間の経過】"
_INSTRUCTION = "利用可能なツールから、次に取るべき 1 つの行動だけを選んでください。"


@pytest.fixture()
def runtime():
    return create_world_runtime(_DRILL)


def _user_prompt(runtime, player_id: PlayerId = _MORI) -> str:
    return runtime.build_full_prompt(player_id)["messages"][1]["content"]


def test_elapsed_time_restarts_when_a_meeting_ends_and_advances_afterward(
    runtime,
) -> None:
    """会議終了直後は 0 分で、自由時間が 5 tick 進むと 25 分になる。"""
    runtime.advance_tick()
    runtime.advance_tick()
    runtime.begin_meeting(initiator_player_id=_KUZE, trigger="emergency_button")
    runtime.advance_tick()
    runtime.end_meeting(reason="vote_concluded")

    assert "最後に全員が集まってから 0 分が過ぎている。" in _user_prompt(runtime)

    for _ in range(5):
        runtime.advance_tick()

    assert "最後に全員が集まってから 25 分が過ぎている。" in _user_prompt(runtime)


def test_meeting_omits_the_elapsed_time_section(runtime) -> None:
    """全員が集まっている会議中は、時間の経過の節を丸ごと省略する。"""
    runtime.begin_meeting(initiator_player_id=_KUZE, trigger="emergency_button")

    assert _HEADER not in _user_prompt(runtime)


def test_elapsed_time_is_immediately_before_the_actual_tail_instruction(runtime) -> None:
    """実プロンプトでは経過時間を直近の出来事より後、最終指示の直前に置く。"""
    for _ in range(5):
        runtime.advance_tick()

    user = _user_prompt(runtime)
    section = f"{_HEADER}\n- ここでの行動が始まってから 25 分が過ぎている。"
    assert user.index("【直近の出来事】") < user.index(_HEADER)
    assert user.endswith(f"{section}\n\n{_INSTRUCTION}")


def test_before_the_first_meeting_uses_the_start_of_the_world(runtime) -> None:
    """会議がまだ無ければ、存在しない前回集合でなく世界開始からの経過を出す。"""
    for _ in range(3):
        runtime.advance_tick()

    user = _user_prompt(runtime)
    assert "ここでの行動が始まってから 15 分が過ぎている。" in user
    assert "最後に全員が集まってから" not in user


def test_departed_player_also_sees_time_since_the_last_gathering(runtime) -> None:
    """死亡後に手番を持つ幽霊にも、生存者と同じ世界時間が届く。"""
    runtime.do_interact_with_player(_KUZE, _MORI, "strike_down")
    runtime.advance_tick()

    assert runtime._departed_position_store.find(_MORI) is not None
    assert "ここでの行動が始まってから 5 分が過ぎている。" in _user_prompt(
        runtime, _MORI
    )
