"""会議が必ず終わることを保証する。

会議と投票 (docs/memory_system/meeting_and_voting_design.md §3) の PR 7。

終了条件を 3 つ持つのは、**どれか 1 つでも欠けると会議が止まる組み合わせが
ある**ため。

| 終了条件 | 無いとどうなるか |
|---|---|
| 全員が投票した | 議論が尽きても終わらない (PR 6 で実装) |
| 沈黙上限 | 全員が黙ると永久に会議 |
| tick 上限 | 喋り続けるだけで投票しなければ永久に会議 |

会議が終わらないと、以降の run は移動も採取もできないまま tick を消費する。
しかも「議論が続いている」ように見えるので、trace を読むまで気付けない。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime
from ai_rpg_world.application.world_graph.game_phase_store import GamePhaseStore
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
    rt = create_world_runtime(_SCENARIO)
    rt.call_emergency_meeting(_KUZE)
    return rt


def _pass_ticks(runtime, count: int) -> None:
    for _ in range(count):
        runtime.advance_tick()


class TestSilenceEndsTheMeeting:
    """全員が黙ったら会議が流れる。"""

    def test_meeting_survives_short_silence(self, runtime) -> None:
        """少し黙ったくらいでは終わらない。

        考える間が取れないと、議論が始まる前に閉じてしまう。
        """
        _pass_ticks(runtime, GamePhaseStore.DEFAULT_MEETING_SILENCE_LIMIT_TICKS - 1)

        assert runtime._game_phase_store.current.phase is GamePhase.MEETING

    def test_prolonged_silence_closes_it(self, runtime) -> None:
        """沈黙が続けば閉じる。"""
        _pass_ticks(runtime, GamePhaseStore.DEFAULT_MEETING_SILENCE_LIMIT_TICKS)

        assert runtime._game_phase_store.current.phase is GamePhase.FREE_ROAM

    def test_the_end_reason_is_recorded_as_silence(self, runtime) -> None:
        """終わり方が「沈黙」として残る。

        投票で決着したのか流れたのかは、会議が機能しているかの指標になる。
        """
        _pass_ticks(runtime, GamePhaseStore.DEFAULT_MEETING_SILENCE_LIMIT_TICKS)

        assert runtime._game_phase_store.current.trigger == "silence"

    def test_speaking_resets_the_silence_clock(self, runtime) -> None:
        """発言があれば沈黙の計測がやり直しになる。

        ここが効かないと、活発に議論していても開始からの経過だけで
        打ち切られる。
        """
        _pass_ticks(runtime, GamePhaseStore.DEFAULT_MEETING_SILENCE_LIMIT_TICKS - 1)
        runtime.do_say(_MORI, "まだ話すことがある")
        _pass_ticks(runtime, GamePhaseStore.DEFAULT_MEETING_SILENCE_LIMIT_TICKS - 1)

        assert runtime._game_phase_store.current.phase is GamePhase.MEETING


class TestTickLimitEndsTheMeeting:
    """喋り続けても、いつかは打ち切られる。"""

    def test_endless_talking_is_cut_off(self, runtime) -> None:
        """毎 tick 発言し続けても tick 上限で終わる。

        沈黙上限だけだと、喋り続けるだけで投票を避けられる。襲う側が
        議論を引き延ばして決着を防ぐ、という手が通ってしまう。
        """
        for _ in range(GamePhaseStore.DEFAULT_MEETING_TICK_LIMIT + 1):
            runtime.do_say(_MORI, "まだ結論は出ない")
            runtime.advance_tick()

        assert runtime._game_phase_store.current.phase is GamePhase.FREE_ROAM

    def test_the_end_reason_is_recorded_as_tick_limit(self, runtime) -> None:
        """終わり方が「時間切れ」として残る。"""
        for _ in range(GamePhaseStore.DEFAULT_MEETING_TICK_LIMIT + 1):
            runtime.do_say(_MORI, "まだ結論は出ない")
            runtime.advance_tick()

        assert runtime._game_phase_store.current.trigger == "tick_limit"


class TestTimeoutStillResolvesTheVote:
    """時間切れでも、投じられた票は集計する。"""

    def test_votes_cast_before_the_timeout_are_counted(self, runtime) -> None:
        """3 人が投票済みで 1 人が黙り込んでも、その 3 票で決まる。

        捨ててしまうと「投票したのに何も起きなかった」になり、投票そのものが
        無意味に見える。
        """
        from ai_rpg_world.domain.player.enum.player_outcome_enum import (
            PlayerOutcomeEnum,
        )

        for voter in (_MORI, _SENA, _AOI):
            runtime.cast_vote(voter, _KUZE)
        _pass_ticks(runtime, GamePhaseStore.DEFAULT_MEETING_SILENCE_LIMIT_TICKS)

        assert (
            runtime._player_outcome_registry.get_outcome(_KUZE)
            is PlayerOutcomeEnum.EJECTED
        )

    def test_the_result_is_delivered_on_timeout(self, runtime) -> None:
        """時間切れでも結果が全員に届く。

        届かないと「会議が終わったのか」も「誰が追放されたのか」も分から
        ないまま自由時間に戻る (設計 doc §6.4)。
        """
        for voter in (_MORI, _SENA, _AOI):
            runtime.cast_vote(voter, _KUZE)
        _pass_ticks(runtime, GamePhaseStore.DEFAULT_MEETING_SILENCE_LIMIT_TICKS)

        delivered = [
            e
            for e in runtime._obs_buffer.get_observations(_MORI)
            if e.output.structured.get("type") == "meeting_vote_resolved"
        ]
        assert delivered


class TestFreeRoamIsUnaffected:
    """自由時間の tick 進行を壊さない。"""

    def test_ticking_in_free_roam_does_nothing_special(self) -> None:
        """会議を開いていなければ、いくら tick が進んでも何も起きない。"""
        rt = create_world_runtime(_SCENARIO)

        _pass_ticks(rt, GamePhaseStore.DEFAULT_MEETING_TICK_LIMIT + 5)

        assert rt._game_phase_store.current.phase is GamePhase.FREE_ROAM
        assert rt._game_phase_store.current.trigger is None
