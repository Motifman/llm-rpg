"""フェーズ遷移が、実際に走っている世界で全員に届くことを保証する。

store が状態を持てても、遷移が event として publish されなければ誰にも
届かない。しかも届かないことは「まだ会議が始まっていない」と区別が
付かないので、静かに壊れる。

`PlayerDownedEvent` を publish し忘れて DEAD outcome が確定しなかった
(#832 H-1) のとまったく同じ形なので、遷移を publish する経路を e2e で
固定する。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world_graph.enum.game_phase import GamePhase

_SCENARIO = (
    Path(__file__).resolve().parents[2] / "data" / "scenarios" / "darkened_station.json"
)

_MORI = PlayerId(1)
_SENA = PlayerId(2)
_KUZE = PlayerId(3)
_AOI = PlayerId(4)


@pytest.fixture()
def runtime():
    return create_world_runtime(_SCENARIO)


def _phase_observations(runtime, player_id: PlayerId) -> list:
    return [
        entry
        for entry in runtime._obs_buffer.get_observations(player_id)
        if entry.output.structured.get("type") == "game_phase_changed"
    ]


class TestMeetingStartReachesEveryone:
    """招集が全員に届く。"""

    def test_every_player_gets_the_observation(self, runtime) -> None:
        """離れた場所に居る人にも届く。

        会議は世界全体のモード変化なので、同じ部屋に居る必要はない。
        届かない人が居ると、その人だけ議論に参加できないまま進む。
        """
        runtime.begin_meeting(initiator_player_id=_KUZE, trigger="emergency_button")

        for pid in (_MORI, _SENA, _AOI):
            assert _phase_observations(runtime, pid), f"player {int(pid)} に届いていない"

    def test_the_initiator_is_named(self, runtime) -> None:
        """誰が招集したかが読める。

        招集した人は疑いの的にも信頼の的にもなる。名前が出ないと、会議の
        きっかけそのものが推理の材料にならない。
        """
        runtime.begin_meeting(initiator_player_id=_KUZE, trigger="emergency_button")

        prose = _phase_observations(runtime, _MORI)[0].output.prose
        assert "クゼ" in prose

    def test_the_observation_wakes_the_recipient(self, runtime) -> None:
        """観測が schedules_turn を立てている。

        False だと会議が始まっても誰も起きず、沈黙上限で即終了する。
        """
        runtime.begin_meeting(initiator_player_id=_KUZE, trigger="emergency_button")

        assert _phase_observations(runtime, _MORI)[0].output.schedules_turn is True


class TestStoreAndEventStayInSync:
    """store の状態と、配られた観測が食い違わない。"""

    def test_store_reflects_the_meeting(self, runtime) -> None:
        """招集後は store も MEETING になっている。"""
        runtime.begin_meeting(initiator_player_id=_KUZE, trigger="emergency_button")

        assert runtime._game_phase_store.current.phase is GamePhase.MEETING

    def test_ending_returns_to_free_roam_and_is_announced(self, runtime) -> None:
        """終了も store と観測の両方に反映される。"""
        runtime.begin_meeting(initiator_player_id=_KUZE, trigger="emergency_button")
        before = len(_phase_observations(runtime, _MORI))

        runtime.end_meeting(reason="vote_concluded")

        assert runtime._game_phase_store.current.phase is GamePhase.FREE_ROAM
        assert len(_phase_observations(runtime, _MORI)) == before + 1


class TestRejectedTransitionsChangeNothing:
    """成立しない遷移で、状態も観測も動かない。"""

    def test_second_meeting_is_rejected_without_emitting(self, runtime) -> None:
        """会議中の再招集は例外になり、観測も増えない。

        1 tick 内で 2 人が緊急ボタンを押すのは実際に起こりうる。2 人目の
        ぶんまで「会議が始まった」が配られると、同じ会議が二度始まったよう
        に読める。
        """
        from ai_rpg_world.domain.world_graph.exception.spot_graph_exception import (
            GamePhaseTransitionException,
        )

        runtime.begin_meeting(initiator_player_id=_KUZE, trigger="emergency_button")
        before = len(_phase_observations(runtime, _MORI))

        with pytest.raises(GamePhaseTransitionException):
            runtime.begin_meeting(initiator_player_id=_SENA, trigger="body_report")

        assert len(_phase_observations(runtime, _MORI)) == before
        assert runtime._game_phase_store.current.trigger == "emergency_button"
