"""倒れている人を見つけたと知らせる手段が、エージェントに届いていることを保証する。

会議と投票 (docs/memory_system/meeting_and_voting_design.md) の PR 8 前半。

## なぜこの PR が要るか

PR 1〜7 で会議は「始まればフェーズが切り替わり、投票し、追放し、必ず終わる」
ところまで動くようになった。ところが `WorldRuntime.report_body` を呼んで
いるのは **テストだけ** で、tool にも interaction にもなっていない。
つまりエージェントには会議を始める手段が一つも無い。

これは `initial_state` や `initial_items` と同じ「参照はあるが本番経路に
乗っていない」形で、実装が揃っているぶん**動いているように見える**のが
たちが悪い。runtime のテストは全部通るのに、run では一度も会議が起きない。
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from ai_rpg_world.application.llm.services.executors.spot_graph_tool_executor import (
    SpotGraphToolExecutor,
)
from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime
from ai_rpg_world.domain.player.value_object.player_id import PlayerId

_SCENARIO = (
    Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "scenarios" / "darkened_station.json"
)

_KUZE = PlayerId(3)
_AOI = PlayerId(4)


@pytest.fixture()
def runtime():
    return create_world_runtime(_SCENARIO)


def _tool_names(runtime) -> list[str]:
    return [d.name for d in runtime.get_tool_definitions(for_every_player=True)]


def _executor(*, runtime) -> SpotGraphToolExecutor:
    """`_report_body` は runtime に委譲する薄い wrapper なので周辺は埋める。"""
    services = MagicMock()
    services.movement = MagicMock()
    return SpotGraphToolExecutor(
        spot_graph_world_services=services,
        player_inventory_repository=MagicMock(),
        item_repository=MagicMock(),
        event_publisher=MagicMock(),
        spot_graph_repository=MagicMock(),
        runtime=runtime,
    )


class TestTheToolIsExposed:
    """報告する手段が tool 一覧に出ている。"""

    def test_available_during_free_roam(self, runtime) -> None:
        """自由時間には出る。

        ここが無いと、死体を見つけても知らせる手段が無い。
        """
        assert "report_body" in _tool_names(runtime)

    def test_absent_during_a_meeting(self, runtime) -> None:
        """会議中には出ない。

        既に話し合っている最中に「見つけた」を出しても始められない。
        並ぶと「選べるのに必ず失敗する手」になる (#860 で潰した形)。
        """
        runtime.begin_meeting(initiator_player_id=_KUZE, trigger="emergency_button")

        assert "report_body" not in _tool_names(runtime)

    def test_the_handler_is_registered(self, runtime) -> None:
        """定義だけ出して handler が無い、にならない。

        露出と実装が別々に足されるので、片方だけ入る形が起きうる。
        vote を足したときも同じ組で確かめている。
        """
        assert "report_body" in _executor(runtime=runtime).get_handlers()


class TestTheHandlerDelegatesToTheRuntime:
    """handler は runtime.report_body に委譲する。"""

    def test_it_passes_the_reporter_and_the_target(self) -> None:
        """報告した本人と、指された相手の両方が runtime に渡る。

        取り違えると、**倒れている本人が報告したこと**になって招集の起点が
        ずれる (全員が死体ではなく報告者の場所に集まる)。
        """
        runtime = MagicMock()
        executor = _executor(runtime=runtime)

        executor._report_body(3, {"target_player_id": 4})

        reporter, target = runtime.report_body.call_args[0]
        assert int(reporter) == 3
        assert int(target) == 4


class TestReportingStartsAMeeting:
    """報告が通れば会議が始まり、通らなければ理由が返る。"""

    def _fell(self, runtime, player_id: PlayerId) -> None:
        status = runtime._player_status_repo.find_by_id(player_id)
        status.apply_damage(status.hp.value)
        runtime._player_status_repo.save(status)

    def test_a_meeting_begins(self, runtime) -> None:
        """倒れている相手を報告すると、フェーズが会議に変わる。"""
        from ai_rpg_world.domain.world_graph.enum.game_phase import GamePhase

        self._fell(runtime, _AOI)
        executor = _executor(runtime=runtime)

        result = executor._report_body(int(_KUZE), {"target_player_id": int(_AOI)})

        assert result.success, result.message
        assert runtime._game_phase_store.current.phase is GamePhase.MEETING

    def test_reporting_someone_who_is_fine_is_refused(self, runtime) -> None:
        """元気に動いている相手は報告できない。

        通してしまうと、いつでも会議を開ける手段になる。緊急ボタンに
        回数とクールダウンを置いた意味が消える。
        """
        executor = _executor(runtime=runtime)

        result = executor._report_body(int(_KUZE), {"target_player_id": int(_AOI)})

        assert result.success is False
        assert result.message

    def test_the_target_is_required(self, runtime) -> None:
        """相手を指さない報告は弾かれる。

        投票と違って棄権に当たるものが無い。誰を見つけたのかが会議の
        出発点なので、空のまま通すと意味が定まらない。
        """
        executor = _executor(runtime=runtime)

        result = executor._report_body(int(_KUZE), {"target_player_id": None})

        assert result.success is False


class TestPhaseLimitedToolsCannotSkipTheDispatchCheck:
    """フェーズ限定の tool も、起動時の dispatch 整合検査に掛かる。

    **vote が実際に素通りしていた。** 起動時検査は現在フェーズ (= 自由時間)
    の tool 一覧しか見ておらず、会議中にしか出ない vote は比較対象に入って
    いなかった。handler 未登録のまま起動が通り、会議が始まって初めて
    UNSUPPORTED_TOOL になる。PR #589 / #590 で潰した silent failure が、
    フェーズという新しい軸で戻ってきていた。
    """

    def test_the_meeting_only_tool_is_visible_to_the_check(self, runtime) -> None:
        """会議フェーズとして訊けば vote が出る。

        検査はこの口を使って両フェーズを突き合わせる。ここが効かないと、
        会議専用 tool を足した人は起動時に何も言われない。
        """
        names = [
            d.name
            for d in runtime.get_tool_definitions(
                as_meeting_phase=True,
                for_every_player=True,
            )
        ]

        assert "vote" in names

    def test_asking_for_free_roam_shows_the_other_block(self, runtime) -> None:
        """自由時間として訊けば自由時間の tool が出る。

        会議中に検査が走った場合でも、自由時間側の tool を見落とさない。
        """
        runtime.begin_meeting(initiator_player_id=_KUZE, trigger="emergency_button")

        names = [
            d.name
            for d in runtime.get_tool_definitions(
                as_meeting_phase=False,
                for_every_player=True,
            )
        ]

        assert "travel_to" in names

    def test_the_override_does_not_change_the_actual_phase(self, runtime) -> None:
        """訊いただけでフェーズは変わらない。

        検査のための問い合わせが世界の状態を動かすと、起動しただけで
        会議が始まったことになる。
        """
        from ai_rpg_world.domain.world_graph.enum.game_phase import GamePhase

        runtime.get_tool_definitions(
            as_meeting_phase=True,
            for_every_player=True,
        )

        assert runtime._game_phase_store.current.phase is GamePhase.FREE_ROAM
