"""陣営の全滅が、実際に走っている世界で勝敗として確定することを保証する。

条件を書けるだけでは足りない。役割は `PlayerStatusAggregate.state`、生死は
outcome registry と、判定材料が別々の場所にあるので、**runtime がその両方を
評価器へ渡していなければ勝敗は永久に成立しない**。しかも成立しないことは
「まだ続いている」と区別が付かないので、静かに壊れる。

`darkened_station` シナリオを土台にする (crew 全滅 = 敗北を宣言済み)。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime
from ai_rpg_world.domain.player.enum.player_outcome_enum import PlayerOutcomeEnum
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world_graph.enum.game_result_enum import GameResultEnum

_SCENARIO = (
    Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "scenarios" / "darkened_station.json"
)

_MORI = PlayerId(1)   # crew
_SENA = PlayerId(2)   # crew
_KUZE = PlayerId(3)   # keeper
_AOI = PlayerId(4)    # crew

_ALL_CREW = (_MORI, _SENA, _AOI)


@pytest.fixture()
def runtime():
    return create_world_runtime(_SCENARIO)


def _mark_dead(runtime, *player_ids: PlayerId) -> None:
    """指定した player の outcome を DEAD で確定させる。"""
    for pid in player_ids:
        runtime._player_outcome_registry.set_outcome(pid, PlayerOutcomeEnum.DEAD)


class TestFactionEliminationEndsTheRun:
    """crew が全滅したら run が敗北で終わる。"""

    def test_not_ended_while_any_crew_lives(self, runtime) -> None:
        """crew が 1 人でも生きていれば続行する。"""
        _mark_dead(runtime, _MORI, _SENA)

        assert runtime.check_game_end().is_ended is False

    def test_ended_when_all_crew_are_dead(self, runtime) -> None:
        """crew が全員 DEAD になったら終了する。"""
        _mark_dead(runtime, *_ALL_CREW)

        assert runtime.check_game_end().is_ended is True

    def test_result_is_lose(self, runtime) -> None:
        """結果は集団としての敗北になる。"""
        _mark_dead(runtime, *_ALL_CREW)

        assert runtime.check_game_end().result == GameResultEnum.LOSE

    def test_keeper_death_does_not_end_the_run(self, runtime) -> None:
        """襲う側が死んでも crew 全滅条件は成立しない。

        役割で数える対象を絞れていなければ、誰か 1 人死ぬたびに終わる。
        """
        _mark_dead(runtime, _KUZE)

        assert runtime.check_game_end().is_ended is False


class TestDownedCrewDoesNotEndTheRun:
    """倒れているだけでは終わらない (蘇生の余地を残す)。"""

    def test_all_crew_down_but_alive_keeps_going(self, runtime) -> None:
        """crew 全員が行動不能でも、DEAD が確定していなければ続行する。

        ここで終わらせると、駆けつけて助け起こす行為に意味が無くなる。
        """
        for pid in _ALL_CREW:
            status = runtime._player_status_repo.find_by_id(pid)
            status.apply_damage(status.hp.value)
            runtime._player_status_repo.save(status)

        assert all(
            runtime._player_status_repo.find_by_id(pid).is_down for pid in _ALL_CREW
        ), "前提が崩れている: crew が倒れていない"
        assert runtime.check_game_end().is_ended is False


class TestWinConditionStillWorks:
    """勝ち筋を潰していない。"""

    def test_finishing_the_work_still_wins(self, runtime) -> None:
        """点検と救難が揃えば勝利で終わる。

        敗北条件を足したときに勝利条件が評価されなくなっていないかを見る。

        **勝ち筋の形が変わったのでテストも変えた。** 以前は救難信号 1 つで
        勝てたが、それだと手分けする理由が生まれない (一人が最短で無線室へ
        向かえば終わる)。今は 5 つのうち 4 つを要求する。
        """
        for flag in ("task_antenna", "task_fuel", "task_supplies", "distress_sent"):
            runtime._world_flag_state.add(flag)

        result = runtime.check_game_end()

        assert result.is_ended is True
        assert result.result == GameResultEnum.WIN

    def test_the_distress_signal_alone_is_not_enough(self, runtime) -> None:
        """救難信号だけでは終わらない。

        一人勝ちの経路が残っていないことを固定する。勝利条件は複数書くと
        OR で評価されるので、独立した条件として残すと作業を足しても
        意味が無くなる。
        """
        runtime._world_flag_state.add("distress_sent")

        assert runtime.check_game_end().is_ended is False
