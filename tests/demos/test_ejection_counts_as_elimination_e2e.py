"""追放が「退場」として陣営の勝敗に効くことを保証する。

会議と投票 (docs/memory_system/meeting_and_voting_design.md §6.2) の PR 5。

## ここを外すと何が起きるか

陣営の勝敗条件 (#848) は「生存者が閾値以下なら成立」で、生存の定義は
もともと **「DEAD 以外」** だった。`EJECTED` を足しただけで生存判定を
直し忘れると、**追放された相手が生存側に数えられ、陣営の全滅が永久に
成立しない**。

しかも症状は「まだゲームが続いている」で、`SURVIVING_PLAYERS_WITH_STATE_AT_MOST`
が壊れていることと区別が付かない。だから追放を実際に行って、勝敗が動く
ところまで通す。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime
from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.player.enum.player_outcome_enum import PlayerOutcomeEnum
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
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


class TestEjectionIsRecorded:
    """追放が outcome として残る。"""

    def test_outcome_becomes_ejected(self, runtime) -> None:
        """追放した相手の outcome が EJECTED になる。"""
        runtime.eject_player(_KUZE)

        assert (
            runtime._player_outcome_registry.get_outcome(_KUZE)
            is PlayerOutcomeEnum.EJECTED
        )

    def test_ejection_is_distinguishable_from_death(self, runtime) -> None:
        """殺害と読み分けられる。

        分析で「殺されたのか追放されたのか」を区別したい。DEAD に丸めると
        その情報が消える。
        """
        runtime.eject_player(_KUZE)

        assert (
            runtime._player_outcome_registry.get_outcome(_KUZE)
            is not PlayerOutcomeEnum.DEAD
        )

    def test_ejection_does_not_create_a_departed_position(self, runtime) -> None:
        """身体記録があっても、第1版では EJECTED を幽霊位置へ置かない。

        身体記録が無い追放者では後段のガードでも通ってしまうため、DEAD だけを
        配置する outcome の境界そのものを検査する。
        """
        runtime._fallen_body_registry.record(_SENA, SpotId(1), WorldTick(3))
        runtime._player_outcome_registry.set_outcome(
            _SENA, PlayerOutcomeEnum.EJECTED
        )

        assert runtime._departed_position_store.find(_SENA) is None


class TestEjectionCountsTowardFactionElimination:
    """追放された相手は陣営の生存者に数えない。"""

    def test_ejecting_the_last_crew_ends_the_run(self, runtime) -> None:
        """crew を追放し切ると敗北で終わる。

        **ここが本 PR の主眼。** 生存判定を直し忘れると、追放された相手が
        生存側へ回り、この assert が永久に通らなくなる。
        """
        for pid in _ALL_CREW:
            runtime.eject_player(pid)

        result = runtime.check_game_end()

        assert result.is_ended is True
        assert result.result == GameResultEnum.LOSE

    def test_one_remaining_crew_keeps_the_run_going(self, runtime) -> None:
        """1 人でも残っていれば続く。"""
        runtime.eject_player(_MORI)
        runtime.eject_player(_SENA)

        assert runtime.check_game_end().is_ended is False

    def test_mixing_death_and_ejection_still_ends_it(self, runtime) -> None:
        """殺害と追放が混ざっていても全滅は成立する。

        両方とも「退場」として数える。片方だけ数えると、混ざった局面で
        勝敗が確定しない。
        """
        status = runtime._player_status_repo.find_by_id(_MORI)
        status.apply_damage(status.hp.value)
        runtime._player_status_repo.save(status)
        runtime._player_outcome_registry.set_outcome(_MORI, PlayerOutcomeEnum.DEAD)
        runtime.eject_player(_SENA)
        runtime.eject_player(_AOI)

        assert runtime.check_game_end().is_ended is True

    def test_ejecting_the_keeper_does_not_end_the_crew_faction(self, runtime) -> None:
        """別陣営を追放しても crew の全滅にはならない。"""
        runtime.eject_player(_KUZE)

        assert runtime.check_game_end().is_ended is False
