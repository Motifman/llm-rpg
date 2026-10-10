"""互いを知らない 2 つの班に、会う前の相手の結果の告知と、声が届いた人数から、名前も存在も届かないことを保証する (#1531)。"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

# circular import 回避 (= Phase 9-4c test と同じ順序)
from ai_rpg_world.application.llm.services.action_result_store import (  # noqa: F401
    DefaultActionResultStore,
)
from ai_rpg_world.application.llm.services.world_llm_turn.speech_handler import (
    build_audience_summary,
)
from ai_rpg_world.application.speech.services.audience_feedback import zero_audience_text
from ai_rpg_world.application.speech.services.speech_audience_resolver import (
    SpeechAudienceMember,
)
from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime
from ai_rpg_world.domain.player.enum.player_enum import SpeechChannel
from ai_rpg_world.domain.player.enum.player_outcome_enum import PlayerOutcomeEnum
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world_graph.enum.sound_clarity import SoundClarityEnum

_SCENARIO = (
    Path(__file__).resolve().parents[1] / "fixtures" / "scenarios" / "two_teams_unaware.json"
)


def _ids_by_name(runtime) -> dict[str, PlayerId]:
    return {runtime.get_player_name(pid): pid for pid in runtime.get_player_ids()}


def _outcome_proses(runtime, recipient: PlayerId) -> list[str]:
    return [
        entry.output.prose
        for entry in runtime._obs_buffer.get_observations(recipient)
        if entry.output.structured.get("type") == "player_outcome_resolved"
    ]


def _walk(runtime, player_id: PlayerId, *spots: str) -> None:
    for spot in spots:
        runtime.do_move(player_id, spot)
        runtime.advance_until_player_idle(player_id)


_OUTCOMES = [PlayerOutcomeEnum.RESCUED, PlayerOutcomeEnum.STRANDED, PlayerOutcomeEnum.DEAD]


class TestOutcomeAnnouncement:
    """結果の告知が、主体を知る受け手にだけ届くことを保証する。"""

    @pytest.mark.parametrize("outcome", _OUTCOMES, ids=lambda o: o.value)
    def test_outcome_of_a_stranger_reaches_only_those_who_know_them(self, outcome) -> None:
        """西のゲンジの救助・取り残し・死亡のどれが決まっても、本人と仲間のサヤには名前付きで届き、東のミナトには何も届かずプロンプトにも名前が出ない。"""
        runtime = create_world_runtime(_SCENARIO)
        ids = _ids_by_name(runtime)

        runtime._player_outcome_registry.set_outcome(ids["ゲンジ"], outcome)

        assert len(_outcome_proses(runtime, ids["ゲンジ"])) == 1
        assert "ゲンジ" in _outcome_proses(runtime, ids["サヤ"])[0]
        assert _outcome_proses(runtime, ids["ミナト"]) == []
        minato = runtime.build_full_prompt(ids["ミナト"])["messages"][1]["content"]
        assert "ゲンジ" not in minato

    def test_ejection_reaches_everyone(self) -> None:
        """会議の投票で決まる追放は、会っていない東のミナトにも名前付きで届く。追放は会議の場で全員が見て決めることなので伏せない。"""
        runtime = create_world_runtime(_SCENARIO)
        ids = _ids_by_name(runtime)

        runtime._player_outcome_registry.set_outcome(ids["ゲンジ"], PlayerOutcomeEnum.EJECTED)

        assert "ゲンジ" in _outcome_proses(runtime, ids["ミナト"])[0]

    def test_outcome_of_someone_met_reaches_them(self) -> None:
        """西の野営地でゲンジと会ったあとのミナトには、ゲンジの救助が名前付きで届く。"""
        runtime = create_world_runtime(_SCENARIO)
        ids = _ids_by_name(runtime)
        _walk(runtime, ids["ミナト"], "pass", "camp_west")

        runtime._player_outcome_registry.set_outcome(ids["ゲンジ"], PlayerOutcomeEnum.RESCUED)

        assert "ゲンジ" in _outcome_proses(runtime, ids["ミナト"])[0]


class _Resolver:
    def __init__(self, members: list[SpeechAudienceMember]) -> None:
        self._members = members

    def resolve_audience_with_clarity(self, **_kwargs) -> list[SpeechAudienceMember]:
        return list(self._members)


def _clear(pid: PlayerId) -> SpeechAudienceMember:
    return SpeechAudienceMember(player_id=pid, clarity=SoundClarityEnum.CLEAR)


class TestAudienceCount:
    """話した本人に返る人数が、本人の知っている聞き手だけを数えることを保証する。"""

    def test_unmet_listeners_are_not_counted(self) -> None:
        """叫んだミナトに、仲間のトウカと会っていないゲンジ・サヤが聞いたとき、返る人数は 1 名になる。"""
        runtime = create_world_runtime(_SCENARIO)
        ids = _ids_by_name(runtime)
        wiring = SimpleNamespace(
            runtime=runtime,
            speech_audience_resolver=_Resolver([_clear(ids["トウカ"]), _clear(ids["ゲンジ"]), _clear(ids["サヤ"])]),
        )

        text = build_audience_summary(wiring, ids["ミナト"], SpeechChannel.SHOUT, None)

        assert text == "（1 名に届いた）"

    def test_only_unmet_listeners_read_like_nobody_heard(self) -> None:
        """会っていない相手だけが聞いたときは、誰にも届かなかったときと同じ文を返す。文が違えば、誰かがいると分かる。"""
        runtime = create_world_runtime(_SCENARIO)
        ids = _ids_by_name(runtime)
        wiring = SimpleNamespace(
            runtime=runtime,
            speech_audience_resolver=_Resolver([_clear(ids["ゲンジ"])]),
        )

        text = build_audience_summary(wiring, ids["ミナト"], SpeechChannel.SHOUT, None)

        assert text == f"（{zero_audience_text(SpeechChannel.SHOUT)}）"

    def test_runtime_without_acquaintances_counts_everyone(self) -> None:
        """知り合いの記録を持たない runtime では、これまでどおり聞いた全員を数える。"""
        wiring = SimpleNamespace(
            runtime=SimpleNamespace(),
            speech_audience_resolver=_Resolver([_clear(PlayerId(2)), _clear(PlayerId(3))]),
        )

        assert build_audience_summary(wiring, PlayerId(1), SpeechChannel.SAY, None) == "（2 名に届いた）"


class _NoCallClient:
    def invoke(self, messages, tools, tool_choice="required", **kwargs):
        raise AssertionError("実 LLM は呼ばない")


def _speak(runtime, player_id: PlayerId, content: str) -> str:
    """runtime の配線と本物の聞き手の解決を通して、叫んだ本人に返る文を得る。"""
    from ai_rpg_world.application.llm.tool_constants import TOOL_NAME_SPEECH
    from ai_rpg_world.presentation.spot_graph_game.runtime_manager import _WorldLlmWiring

    wiring = _WorldLlmWiring(
        runtime=runtime,
        observation_buffer=runtime._obs_buffer,
        short_term_memory=runtime._short_term_memory,
        llm_client=_NoCallClient(),
    )
    prompt = runtime.build_full_prompt(player_id)
    result = wiring._tool_handlers[TOOL_NAME_SPEECH](
        player_id, {"channel": "shout", "content": content}, prompt["tool_runtime_context"]
    )
    return result.message


class TestAudienceCountThroughTheSpeakTool:
    """発話の道具を通しても、叫んだ本人に返る人数が知っている聞き手だけになることを保証する。"""

    def test_shout_from_the_pass_counts_only_the_teammate_before_meeting(self) -> None:
        """峠で叫んだミナトの声は東の仲間トウカと西の 2 人に届くが、会う前に返る人数は 1 名になる。"""
        runtime = create_world_runtime(_SCENARIO)
        ids = _ids_by_name(runtime)
        _walk(runtime, ids["ミナト"], "pass")

        message = _speak(runtime, ids["ミナト"], "おーい")

        assert message.startswith("（1 名"), message

    def test_shout_from_the_pass_counts_everyone_after_meeting(self) -> None:
        """西の野営地で 2 人と会ってから峠に戻って叫ぶと、返る人数は 3 名になる。"""
        runtime = create_world_runtime(_SCENARIO)
        ids = _ids_by_name(runtime)
        _walk(runtime, ids["ミナト"], "pass", "camp_west", "pass")

        message = _speak(runtime, ids["ミナト"], "おーい")

        assert message.startswith("（3 名"), message
