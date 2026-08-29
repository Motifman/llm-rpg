"""会議が投票で決着することを保証する。

会議と投票 (docs/memory_system/meeting_and_voting_design.md) の PR 6。
ここまで会議は「話して終わり」だった。

## 結果は追放の有無にかかわらず配る (§6.4)

同点や棄権最多のとき、世界には何も起きない。誰も移動せず state も変わらない
ので、**ドメインイベントが自然には発生しない**。放っておくと各エージェント
には「投票した」「気付いたら自由時間に戻っていた」しか残らず、次の 3 つが
区別できなくなる。

- 集計結果 (誰に何票入ったか)
- 会議が終わったのか、まだ続いているのか
- 誰も追放されなかったのか、**誰かが追放されたが自分は見ていなかった**のか

特別扱いせず、必ず「投票が終わった」を配る。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime
from ai_rpg_world.domain.player.enum.player_outcome_enum import PlayerOutcomeEnum
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world_graph.enum.game_phase import GamePhase
from ai_rpg_world.presentation.spot_graph_game.runtime_manager import _WorldLlmWiring
from ai_rpg_world.application.llm.services.llm_client_stub import StubLlmClient

_SCENARIO = (
    Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "scenarios" / "darkened_station.json"
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


def _vote_observations(runtime, player_id: PlayerId) -> list:
    return [
        e
        for e in runtime._obs_buffer.get_observations(player_id)
        if e.output.structured.get("type") == "meeting_vote_resolved"
    ]


def _vote_progress_observations(runtime, player_id: PlayerId) -> list:
    return [
        e
        for e in runtime._obs_buffer.get_observations(player_id)
        if e.output.structured.get("type") == "meeting_vote_cast"
    ]


class TestVotingIsRejectedOutsideMeetings:
    """会議中でなければ投票できない。"""

    def test_voting_in_free_roam_is_refused(self) -> None:
        """自由時間の投票は拒否される。

        toolset から外すだけでは、悪性クライアントや provider の変換崩れで
        届く可能性がある (設計 doc H-6)。reason-first が action_phase で
        assess_situation を弾いているのと同じ保険。
        """
        rt = create_world_runtime(_SCENARIO)  # 会議を開かない

        result = rt.cast_vote(_MORI, _KUZE)

        assert result.success is False
        assert result.message


class TestVotingClosesTheMeeting:
    """全員が投票したら会議が終わる。"""

    def test_meeting_continues_until_everyone_voted(self, runtime) -> None:
        """まだ投票していない人が居る間は続く。"""
        runtime.cast_vote(_MORI, _KUZE)
        runtime.cast_vote(_SENA, _KUZE)

        assert runtime._game_phase_store.current.phase is GamePhase.MEETING

    def test_last_vote_ends_the_meeting(self, runtime) -> None:
        """最後の 1 票で会議が閉じる。"""
        for voter in (_MORI, _SENA, _KUZE, _AOI):
            runtime.cast_vote(voter, _KUZE)

        assert runtime._game_phase_store.current.phase is GamePhase.FREE_ROAM

    def test_voting_twice_is_refused(self, runtime) -> None:
        """同じ人が二度投票できない。

        許すと、最後の 1 人が投票しないまま票だけ積み増せる。
        """
        runtime.cast_vote(_MORI, _KUZE)

        result = runtime.cast_vote(_MORI, _SENA)

        assert result.success is False

    def test_vote_tool_disappears_for_the_player_who_already_voted(
        self, runtime
    ) -> None:
        """投票済みの本人には vote を出さず、会議で話す手段は残す。

        投票先は変更できないため、投票後の vote は選べても必ず
        ALREADY_VOTED になる手である。run 011 では実際に 2 回選ばれた。
        """
        runtime.cast_vote(_MORI, _KUZE)

        offered = {
            definition.name
            for definition in runtime.get_tool_definitions(player_id=_MORI)
        }

        assert "vote" not in offered
        assert "speak" in offered

    def test_llm_payload_hides_vote_after_the_player_voted(self, runtime) -> None:
        """実際に LLM へ渡すツール一覧でも、投票済み本人の vote を隠す。"""
        runtime.cast_vote(_MORI, _KUZE)
        wiring = _WorldLlmWiring(
            runtime=runtime,
            observation_buffer=runtime._obs_buffer,
            short_term_memory=runtime._short_term_memory,
            llm_client=StubLlmClient(None),
        )

        offered = {
            tool["function"]["name"]
            for tool in wiring._build_tools_payload(_MORI)
        }

        assert "vote" not in offered
        assert "speak" in offered

    def test_vote_tool_remains_for_a_player_who_has_not_voted(self, runtime) -> None:
        """他人が投票しても、未投票の本人には vote を残す。"""
        runtime.cast_vote(_MORI, _KUZE)

        offered = {
            definition.name
            for definition in runtime.get_tool_definitions(player_id=_SENA)
        }

        assert "vote" in offered

    def test_tool_definitions_require_an_explicit_audience(self, runtime) -> None:
        """本人も全体検査も指定しない呼び出しは、渡し忘れとして落とす。"""
        with pytest.raises(ValueError, match="player_id|for_every_player"):
            runtime.get_tool_definitions()

    def test_all_player_validation_keeps_tools_needed_by_someone(self, runtime) -> None:
        """全体整合検査では、1人が投票済みでも未投票者の vote を残す。"""
        runtime.cast_vote(_MORI, _KUZE)

        offered = {
            definition.name
            for definition in runtime.get_tool_definitions(for_every_player=True)
        }

        assert "vote" in offered

    def test_tool_definitions_reject_two_audiences_at_once(self, runtime) -> None:
        """本人向けと全体検査向けを同時指定した曖昧な呼び出しは落とす。"""
        with pytest.raises(ValueError, match="player_id|for_every_player"):
            runtime.get_tool_definitions(
                player_id=_MORI,
                for_every_player=True,
            )

    def test_execution_guard_uses_the_voters_own_toolset(self, runtime) -> None:
        """投票済み本人の直接呼び出しも、同じ露出入口で実行前に拒否する。"""
        runtime.cast_vote(_MORI, _KUZE)
        wiring = _WorldLlmWiring(
            runtime=runtime,
            observation_buffer=runtime._obs_buffer,
            short_term_memory=runtime._short_term_memory,
            llm_client=StubLlmClient(None),
        )

        result = wiring._reason_tool_is_not_offered(
            "vote",
            _MORI,
            offered_tool_names_at_prompt=frozenset(),
        )

        assert result is not None
        assert result.error_code == "TOOL_NOT_OFFERED_NOW"


class TestVotingProgressIsPublicWithoutRevealingTheTarget:
    """投票の進み具合だけを全員へ知らせ、投票先は締切まで伏せる。"""

    def test_voter_name_and_remaining_count_are_delivered(self, runtime) -> None:
        """1 人が投票すると、誰が済ませたかと残り人数が全員へ届く。"""
        runtime.cast_vote(_MORI, _KUZE)

        observation = _vote_progress_observations(runtime, _SENA)[0]
        assert observation.output.prose == "モリが投票を済ませた。まだ 3 人が投票していない。"

    def test_progress_does_not_reveal_the_vote_target(self, runtime) -> None:
        """締切前の進捗観測には投票先の名前も識別子も含めない。"""
        runtime.cast_vote(_MORI, _KUZE)

        observation = _vote_progress_observations(runtime, _SENA)[0]
        assert "クゼ" not in observation.output.prose
        assert "target" not in observation.output.structured
        assert observation.output.structured == {
            "type": "meeting_vote_cast",
            "voter_display_name": "モリ",
            "remaining_voter_count": 3,
        }

    def test_voter_does_not_receive_a_duplicate_progress_observation(
        self, runtime
    ) -> None:
        """投票した本人はツール結果で知るため、同じ進捗観測を重ねない。"""
        runtime.cast_vote(_MORI, _KUZE)

        assert _vote_progress_observations(runtime, _MORI) == []

    def test_vote_progress_uses_the_command_event_handoff(self, runtime) -> None:
        """旧publisher参照を外しても、確定後handoffから投票進捗が届く。"""
        runtime._speech_event_publisher = None

        runtime.cast_vote(_MORI, _KUZE)

        assert len(_vote_progress_observations(runtime, _SENA)) == 1


class TestEjection:
    """最多票の相手が追放される。"""

    def test_the_majority_target_is_ejected(self, runtime) -> None:
        """3 対 1 でクゼが追放される。"""
        runtime.cast_vote(_MORI, _KUZE)
        runtime.cast_vote(_SENA, _KUZE)
        runtime.cast_vote(_AOI, _KUZE)
        runtime.cast_vote(_KUZE, _MORI)

        assert (
            runtime._player_outcome_registry.get_outcome(_KUZE)
            is PlayerOutcomeEnum.EJECTED
        )

    def test_a_tie_ejects_nobody(self, runtime) -> None:
        """割れたら誰も追放されない (クゼ 2 票・モリ 2 票)。"""
        runtime.cast_vote(_MORI, _KUZE)
        runtime.cast_vote(_SENA, _KUZE)
        runtime.cast_vote(_KUZE, _MORI)
        runtime.cast_vote(_AOI, _MORI)

        outcomes = [
            runtime._player_outcome_registry.get_outcome(p)
            for p in (_MORI, _SENA, _KUZE, _AOI)
        ]
        assert PlayerOutcomeEnum.EJECTED not in outcomes


class TestResultIsAlwaysDelivered:
    """追放の有無にかかわらず、結果が全員に届く。"""

    def _vote_all_skip(self, runtime) -> None:
        for voter in (_MORI, _SENA, _KUZE, _AOI):
            runtime.cast_vote(voter, None)

    def test_everyone_gets_the_result_when_someone_is_ejected(self, runtime) -> None:
        """追放が起きたとき、全員に結果が届く。"""
        for voter in (_MORI, _SENA, _AOI):
            runtime.cast_vote(voter, _KUZE)
        runtime.cast_vote(_KUZE, None)

        for pid in (_MORI, _SENA, _AOI):
            assert _vote_observations(runtime, pid), f"{int(pid)} に届いていない"

    def test_everyone_gets_the_result_when_nobody_is_ejected(self, runtime) -> None:
        """**誰も追放されなくても**結果が届く。

        ここが本 PR の主眼。何も起きないケースはドメインイベントが自然には
        出ないので、実装から漏れる。
        """
        self._vote_all_skip(runtime)

        for pid in (_MORI, _SENA, _AOI):
            assert _vote_observations(runtime, pid), f"{int(pid)} に届いていない"

    def test_the_prose_says_nobody_was_ejected(self, runtime) -> None:
        """「誰も追放されなかった」と読める文になる。"""
        self._vote_all_skip(runtime)

        prose = _vote_observations(runtime, _MORI)[0].output.prose
        assert "追放" in prose

    def test_the_tally_is_included(self, runtime) -> None:
        """誰が誰に入れたかが結果に含まれる。

        投票行動そのものが次の会議の材料になる (設計 doc §2.3)。集計だけ
        だと社会的推論の材料が一段減る。
        """
        for voter in (_MORI, _SENA, _AOI):
            runtime.cast_vote(voter, _KUZE)
        runtime.cast_vote(_KUZE, None)

        structured = _vote_observations(runtime, _MORI)[0].output.structured
        assert structured["ballots"]
        assert structured["counts"]


class TestIncapacitatedPlayersDoNotBlockTheVote:
    """倒れている相手は投票の母数に入らない。"""

    def test_meeting_closes_without_the_fallen(self, runtime) -> None:
        """倒れている人を待たずに会議が閉じる。

        母数に残すと、投票する機会が無い人を永久に待つことになる。
        過半数の計算も狂い、「誰も追放できない」が「同点で追放なし」と
        区別できなくなる (設計 doc H-1)。
        """
        status = runtime._player_status_repo.find_by_id(_AOI)
        status.apply_damage(status.hp.value)
        runtime._player_status_repo.save(status)

        for voter in (_MORI, _SENA, _KUZE):
            runtime.cast_vote(voter, _KUZE)

        assert runtime._game_phase_store.current.phase is GamePhase.FREE_ROAM


class TestTheProseMatchesWhatActuallyHappened:
    """結果の文が、実際に起きたことと食い違わない。

    **実 run で食い違いが出た。** 誰も投票しないまま会議が時間切れになった
    とき、「投票が終わった。票が割れ、誰も追放されなかった。」と届いていた。
    票は 1 つも入っていない (counts も skip_count も空)。

    「割れた」は**票が入って拮抗した**という意味なので、これを読んだ
    エージェントは「他の誰かは投票したが意見が分かれた」と受け取る。実際は
    全員が投票しなかっただけで、次の会議で取るべき手はまったく違う
    (議論が拮抗しているのか、そもそも誰も動いていないのか)。
    """

    def _prose(self, runtime) -> str:
        return _vote_observations(runtime, _MORI)[0].output.prose

    def _let_it_time_out(self, runtime) -> None:
        """誰も喋らず投票もしないまま会議を時間切れにする。

        `end_meeting` を直接呼ぶと集計を通らない。**実 run で起きたのは
        時間切れ経路**なので、そこを通す。
        """
        from ai_rpg_world.application.world_graph.game_phase_store import (
            GamePhaseStore,
        )

        for _ in range(GamePhaseStore.DEFAULT_MEETING_SILENCE_LIMIT_TICKS + 1):
            runtime.advance_tick()

    def test_nobody_voting_is_not_described_as_a_split(self, runtime) -> None:
        """1 票も入らなければ「割れた」とは言わない。"""
        self._let_it_time_out(runtime)

        prose = self._prose(runtime)
        assert "割れ" not in prose, prose

    def test_nobody_voting_says_so(self, runtime) -> None:
        """1 票も入らなかったことが読み取れる。

        「投票が終わった」だけだと、静かに投票が行われた末の結果に読める。
        """
        self._let_it_time_out(runtime)

        assert "誰も票を投じ" in self._prose(runtime)

    def test_a_real_tie_is_still_described_as_a_split(self, runtime) -> None:
        """本当に割れたときは「割れた」と言う。

        直しすぎて、同数の拮抗まで「誰も投票しなかった」になっては困る。
        """
        runtime.cast_vote(_MORI, _KUZE)
        runtime.cast_vote(_SENA, _KUZE)
        runtime.cast_vote(_KUZE, _MORI)
        runtime.cast_vote(_AOI, _MORI)

        prose = self._prose(runtime)
        assert "割れ" in prose, prose

    def test_a_real_tie_names_the_tie_as_the_reason(self, runtime) -> None:
        """名指し票の首位が同数なら、同点で決まらなかったと伝える。"""
        runtime.cast_vote(_MORI, _KUZE)
        runtime.cast_vote(_SENA, _KUZE)
        runtime.cast_vote(_KUZE, _MORI)
        runtime.cast_vote(_AOI, _MORI)

        assert "最多票が同数" in self._prose(runtime)

    def test_skips_outnumbering_a_named_target_are_not_called_a_split(
        self, runtime
    ) -> None:
        """棄権が名指しの最多票以上なら、票割れではなく棄権を理由にする。"""
        runtime.cast_vote(_MORI, _KUZE)
        runtime.cast_vote(_SENA, None)
        runtime.cast_vote(_KUZE, None)
        runtime.cast_vote(_AOI, None)

        prose = self._prose(runtime)
        assert "棄権が最多票を上回り" in prose
        assert "票が割れ" not in prose

    def test_vote_result_has_no_double_full_stop(self, runtime) -> None:
        """集計の見出しと票数をつないでも二重句点を出さない。"""
        runtime.cast_vote(_MORI, _KUZE)
        runtime.cast_vote(_SENA, None)
        runtime.cast_vote(_KUZE, None)
        runtime.cast_vote(_AOI, None)

        assert "。。" not in self._prose(runtime)

    def test_all_skipping_is_not_described_as_nobody_voting(self, runtime) -> None:
        """全員が棄権したのは「誰も投票しなかった」ではない。

        棄権は**保留するという意思表示**で、票の不在ではない (設計 doc
        §2.3)。混ぜると、全員が判断を保留した事実が消える。
        """
        for voter in (_MORI, _SENA, _KUZE, _AOI):
            runtime.cast_vote(voter, None)

        prose = self._prose(runtime)
        assert "棄権" in prose, prose
