"""プロンプト本文が勧める行動と、その場面で実際に出すツールが一致することを保証する。

## 何が起きていたか

station_drill の実 run で、本文が勧める行動を選んだ結果が
``TOOL_NOT_OFFERED_NOW`` になる形が 2 つあった。

- 会議中の死者に「移動と許された点検作業は続けられ」と出ていたが、会議中は
  死者にも travel_to / interact を出していない
- 投票済みの人に「いま投票しないと、誰も追放されないまま終わる」と出ていたが、
  投票済みの人には vote を出していない

どちらも、ツールの出し分けは ``ToolExposure`` が決めているのに、本文の側が
その判断を見ていなかった。無効化したツールの名前が本文に残る形
(tests/demos/test_disabled_tools_vanish_from_the_prompt.py) と同じ根で、
こちらはツール名ではなく行動を勧める文として残っていた。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ai_rpg_world.application.llm.services.llm_client_stub import StubLlmClient
from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime
from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.player.enum.player_outcome_enum import PlayerOutcomeEnum
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.presentation.spot_graph_game.runtime_manager import _WorldLlmWiring

_DRILL = (
    Path(__file__).resolve().parents[2] / "data" / "scenarios" / "station_drill.json"
)

_MORI, _SENA, _KUZE, _AOI = (PlayerId(i) for i in (1, 2, 3, 4))

#: 本文の中で、そのツールの行動を勧める文の断片。
#:
#: 正の対照 (``TestTheUrgingStillReachesThoseWhoCanAct``) で、この断片が
#: 実際に本文へ出る場面があることを固定している。断片が本文から消えただけで
#: 下の検査が空振りしないようにするため。
_URGING_BY_TOOL: dict[str, tuple[str, ...]] = {
    "vote": ("いま投票しないと", "投票しないまま打ち切られると"),
    "travel_to": ("移動と許された点検作業は続けられ",),
    "interact": ("移動と許された点検作業は続けられ",),
}


def _prompt_and_offered_tools(runtime, player_id: PlayerId) -> tuple[str, set[str]]:
    """エージェントが実際に読む本文と、実際に渡すツール名を返す。"""
    prompt = runtime.build_full_prompt(player_id)
    text = "\n".join(str(m["content"]) for m in prompt["messages"])
    wiring = _WorldLlmWiring(
        runtime=runtime,
        observation_buffer=runtime._obs_buffer,
        short_term_memory=runtime._short_term_memory,
        llm_client=StubLlmClient(None),
    )
    offered = {t["function"]["name"] for t in wiring._build_tools_payload(player_id)}
    return text, offered


def _urgings_for_tools_not_offered(text: str, offered: set[str]) -> list[str]:
    return [
        f"{tool}: {phrase}"
        for tool, phrases in _URGING_BY_TOOL.items()
        if tool not in offered
        for phrase in phrases
        if phrase in text
    ]


def _ghost_rule(text: str) -> str:
    """幽霊ルールの段落だけを返す。

    本文全体で探すと、同じ言い回しを含む観測 (最近の出来事欄) に救われて
    幽霊ルールが壊れても通ってしまう。
    """
    lines = text.splitlines()
    return lines[lines.index("【いまの存在状態】") + 1]


def _meeting_status_line(text: str) -> str:
    """会議の状況行だけを返す。理由は ``_ghost_rule`` と同じ。"""
    return next(line for line in text.splitlines() if line.startswith("話し合いの最中"))


def _make_dead(runtime, player_id: PlayerId, spot_name: str) -> None:
    spot = SpotId.create(runtime.id_mapper.get_int("spot", spot_name))
    runtime._fallen_body_registry.record(
        player_id, spot, WorldTick(runtime.current_tick())
    )
    status = runtime._player_status_repo.find_by_id(player_id)
    status.apply_damage(status.hp.value)
    runtime._player_status_repo.save(status)
    runtime._player_outcome_registry.set_outcome(player_id, PlayerOutcomeEnum.DEAD)
    runtime._departed_position_store.place(player_id, spot)


def _make_deadline_urgent(runtime) -> None:
    runtime._game_phase_store.meeting_tick_limit = 1


@pytest.fixture()
def meeting_with_a_ghost_and_a_voter():
    """セナが死んでいて、クゼが会議を呼び、モリだけが投票を済ませた場面。"""
    runtime = create_world_runtime(_DRILL)
    _make_dead(runtime, _SENA, "greenhouse")
    runtime.call_emergency_meeting(_KUZE)
    runtime.cast_vote(_MORI, _KUZE)
    return runtime


class TestNoProseUrgesAToolThatIsNotOffered:
    """会議中のどの視点でも、出していないツールの行動を本文が勧めない。"""

    @pytest.mark.parametrize("urgent", (False, True), ids=("early", "urgent"))
    @pytest.mark.parametrize(
        "player_id", (_MORI, _SENA, _AOI), ids=("voted", "ghost", "not_voted")
    )
    def test_prompt_urges_only_offered_tools_during_a_meeting(
        self, meeting_with_a_ghost_and_a_voter, player_id, urgent
    ) -> None:
        """投票済みの人・死者・未投票の人のいずれでも、締切の遠近を問わず、本文が勧める行動のツールは実際に渡すツールに含まれる。"""
        runtime = meeting_with_a_ghost_and_a_voter
        if urgent:
            _make_deadline_urgent(runtime)

        text, offered = _prompt_and_offered_tools(runtime, player_id)

        assert _urgings_for_tools_not_offered(text, offered) == []


class TestThoseWhoCannotActAreToldWhy:
    """行動を勧めない代わりに、いまそれができない事情を本文が伝える。"""

    def test_voter_is_told_they_already_voted(
        self, meeting_with_a_ghost_and_a_voter
    ) -> None:
        """投票済みの人の本文には、自分はもう投票したことと結果を待つことが書かれる。"""
        text, _ = _prompt_and_offered_tools(meeting_with_a_ghost_and_a_voter, _MORI)

        assert "自分はもう投票した" in _meeting_status_line(text)

    def test_ghost_is_told_they_can_move_again_after_the_meeting(
        self, meeting_with_a_ghost_and_a_voter
    ) -> None:
        """会議中の死者の幽霊ルールには、会議が終われば移動と点検に戻れることが書かれる。"""
        text, _ = _prompt_and_offered_tools(meeting_with_a_ghost_and_a_voter, _SENA)

        assert "話し合いが終われば" in _ghost_rule(text)

    def test_ghost_is_told_they_cannot_vote(
        self, meeting_with_a_ghost_and_a_voter
    ) -> None:
        """会議中の死者には vote を出さないので、幽霊ルールにも投票できないと書かれる。"""
        text, offered = _prompt_and_offered_tools(
            meeting_with_a_ghost_and_a_voter, _SENA
        )

        assert "vote" not in offered
        assert "投票はできない" in _ghost_rule(text)


class TestTheUrgingStillReachesThoseWhoCanAct:
    """行動できる人には従来どおり勧める。上の検査が空振りしないための正の対照。"""

    def test_player_who_has_not_voted_is_urged_before_the_deadline(
        self, meeting_with_a_ghost_and_a_voter
    ) -> None:
        """未投票の人には vote を渡し、締切が遠いうちは打ち切りの帰結が書かれる。"""
        text, offered = _prompt_and_offered_tools(
            meeting_with_a_ghost_and_a_voter, _AOI
        )

        assert "vote" in offered
        assert "投票しないまま打ち切られると" in _meeting_status_line(text)

    def test_player_who_has_not_voted_is_urged_near_the_deadline(
        self, meeting_with_a_ghost_and_a_voter
    ) -> None:
        """未投票の人には、締切が近いと「いま投票しないと」の促しが書かれる。"""
        runtime = meeting_with_a_ghost_and_a_voter
        _make_deadline_urgent(runtime)

        text, offered = _prompt_and_offered_tools(runtime, _AOI)

        assert "vote" in offered
        assert "いま投票しないと" in _meeting_status_line(text)

    def test_ghost_in_free_roam_is_told_they_can_move_and_inspect(self) -> None:
        """自由時間の死者には travel_to と interact を渡し、移動と点検を続けられると書かれる。"""
        runtime = create_world_runtime(_DRILL)
        _make_dead(runtime, _SENA, "greenhouse")

        text, offered = _prompt_and_offered_tools(runtime, _SENA)

        assert {"travel_to", "interact"} <= offered
        assert "移動と許された点検作業は続けられ" in _ghost_rule(text)


def _meeting_start_prose(runtime, player_id: PlayerId) -> str:
    return next(
        e.output.prose
        for e in runtime._obs_buffer.get_observations(player_id)
        if e.output.structured.get("type") == "game_phase_changed"
    )


class TestTheMeetingAnnouncementMatchesOfferedTools:
    """会議開始の観測が、受け取る本人に出すツールと食い違わない。

    観測は記憶に流れるので、状況行と違って次の手番で書き換わらない。
    """

    def test_living_player_is_told_they_can_speak_and_vote(self) -> None:
        """生者への会議開始の観測は「ここでできるのは、話すことと投票だけになった。」で終わり、実際に vote を渡す。"""
        runtime = create_world_runtime(_DRILL)
        runtime.call_emergency_meeting(_KUZE)

        prose = _meeting_start_prose(runtime, _AOI)
        _, offered = _prompt_and_offered_tools(runtime, _AOI)

        assert prose == (
            "クゼが緊急招集をかけた。全員が集まる。"
            "ここでできるのは、話すことと投票だけになった。"
        )
        assert "vote" in offered

    def test_ghost_is_told_they_can_only_speak(self) -> None:
        """死者への会議開始の観測は投票を勧めず、幽霊ルールと同じ言い方で、話すことと様子を見ることしかできないと書く。死者には vote を渡さない。"""
        runtime = create_world_runtime(_DRILL)
        _make_dead(runtime, _SENA, "greenhouse")
        runtime.call_emergency_meeting(_KUZE)

        prose = _meeting_start_prose(runtime, _SENA)
        _, offered = _prompt_and_offered_tools(runtime, _SENA)

        assert prose == (
            "クゼが緊急招集をかけた。全員が集まる。"
            "話し合いのあいだは、話すことと様子を見ることしかできず、投票はできない。"
        )
        assert "vote" not in offered
