from __future__ import annotations

from typing import Any

from tests.event_handoff_helpers import discard_events

from ai_rpg_world.application.being.player_episode_writing import (
    TRIGGER_LEAVING,
    PlayerEpisodeWriting,
)
from ai_rpg_world.application.llm.exceptions import LlmApiCallException
from ai_rpg_world.application.trace import TraceEventKind
from ai_rpg_world.application.trace.recorder import NullTraceRecorder
from ai_rpg_world.being.application.episode_writing import AddEpisodesToMemory
from ai_rpg_world.being.application.write_episodes_on_leaving import WriteEpisodesOnLeaving
from ai_rpg_world.being.contract import UNKNOWN, Observation, ObservedTime, SeenOrHeard
from ai_rpg_world.being.domain.being_id import BeingId
from ai_rpg_world.being.domain.persona import Persona
from ai_rpg_world.being.domain.short_term_memory import ShortTermMemory
from ai_rpg_world.being.infrastructure.in_memory_episode_repository import (
    InMemoryEpisodeRepository,
)
from ai_rpg_world.being.infrastructure.in_memory_memory_turn_clock import (
    InMemoryMemoryTurnClock,
)
from ai_rpg_world.being.infrastructure.in_memory_short_term_memory_repository import (
    InMemoryShortTermMemoryRepository,
)
from ai_rpg_world.being.infrastructure.llm_episode_writer import (
    EpisodeWritingCompletion,
    LlmEpisodeWriter,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId

ADA = PlayerId(1)
ADA_BEING = BeingId("being_p1")


class _Recorder(NullTraceRecorder):
    def __init__(self) -> None:
        self.events: list[tuple[str, int | None, dict[str, Any]]] = []

    def record(self, kind: str, *, tick: int | None = None, player_id: int | None = None, **payload: Any):  # type: ignore[override]
        self.events.append((kind, player_id, payload))
        return super().record(kind, tick=tick, player_id=player_id, **payload)

    def of(self, kind: str) -> list[dict[str, Any]]:
        return [p for k, _, p in self.events if k == kind]


class _Completion(EpisodeWritingCompletion):
    def __init__(self, response: Any = None, error: Exception | None = None) -> None:
        self.response = response
        self.error = error
        self.messages: list[list[dict[str, str]]] = []

    def complete_episode_writing_json(self, messages: list[dict[str, str]]) -> Any:
        self.messages.append(messages)
        if self.error is not None:
            raise self.error
        return self.response


def _seen(body: str) -> Observation:
    return Observation(
        body=body,
        route=SeenOrHeard(),
        time=ObservedTime(display="深夜 0:01"),
        subject_is_self=False,
        subject_name=UNKNOWN,
        source=UNKNOWN,
        place=UNKNOWN,
        addressed_to_self=UNKNOWN,
    )


def _item(**overrides: str) -> dict[str, str]:
    item = {"about": "金庫を開けた", "recall_when": "金庫の話が出たとき", "body": "紙の番号で金庫が開いた。"}
    item.update(overrides)
    return item


def _make(
    completion: EpisodeWritingCompletion,
    *,
    being: BeingId | None = ADA_BEING,
    remembered: tuple[str, ...] = ("金庫が開いた。",),
):
    """Being の短期記憶に、``remembered`` の出来事をターン 1 から 1 つずつ見たことにしておく。"""
    repository = InMemoryEpisodeRepository(handoff=discard_events)
    store = InMemoryShortTermMemoryRepository(handoff=discard_events)
    memory = ShortTermMemory.empty(ADA_BEING)
    for turn, body in enumerate(remembered):
        memory.perceive(_seen(body), current_turn=turn)
    store.save(memory)
    turns = InMemoryMemoryTurnClock()
    recorder = _Recorder()
    writing = PlayerEpisodeWriting(
        write_episodes=WriteEpisodesOnLeaving(store, LlmEpisodeWriter(completion), AddEpisodesToMemory(repository)),
        being_id_of=lambda pid: being,
        turn_reader=turns,
        environment_name_of=lambda pid: "地下の金庫室",
        persona_of=lambda being_id: Persona(name="エイダ", first_person="わたし"),
        persona_text_of=lambda pid: "慎重な錠前師",
        trace_recorder_provider=lambda: recorder,
        current_tick_provider=lambda: 7,
    )
    return writing, repository, turns, recorder


class TestPlayerEpisodeWritingInput:
    """PlayerEpisodeWriting がプレイヤーの Being の短期記憶の出来事を、書き起こしの部品に渡す形を保証する。"""

    def test_unsummarized_experiences_are_passed_as_recent_events_lines(self) -> None:
        """Being の短期記憶のまだまとめていない出来事を、覚えた順に【直近の出来事】と同じ行の形で書き手に渡す。"""
        completion = _Completion({"episodes": []})
        writing, *_ = _make(completion, remembered=("棚を調べた。", "金庫が開いた。"))

        writing.write(ADA, trigger=TRIGGER_LEAVING)

        user = completion.messages[0][1]["content"]
        assert "- [深夜 0:01] 棚を調べた。\n- [深夜 0:01] 金庫が開いた。" in user

    def test_name_and_first_person_come_from_the_being_persona(self) -> None:
        """書き手には、Being の人柄の名前と一人称と、ゲームの側の人格の文を渡す。"""
        completion = _Completion({"episodes": []})
        writing, *_ = _make(completion)

        writing.write(ADA, trigger=TRIGGER_LEAVING)

        user = completion.messages[0][1]["content"]
        assert "あなた = エイダ\nあなたの一人称 = わたし\nあなたの人物像 = 慎重な錠前師" in user

    def test_episode_carries_being_turn_and_environment_name(self) -> None:
        """書いたエピソードは、その Being の記憶のターン数と環境の名前を持ち、Being の記録に入る。"""
        writing, repository, turns, _ = _make(_Completion({"episodes": [_item()]}))
        for _ in range(4):
            turns.advance_turn(ADA_BEING)

        writing.write(ADA, trigger=TRIGGER_LEAVING)

        (episode,) = repository.list_by_being(ADA_BEING)
        assert episode.written_turn == 4
        assert episode.environment_name == "地下の金庫室"


class _Sequence(EpisodeWritingCompletion):
    def __init__(self, *responses: Any) -> None:
        self.responses = list(responses)

    def complete_episode_writing_json(self, messages: list[dict[str, str]]) -> Any:
        return self.responses.pop(0)


class TestPlayerEpisodeWritingRewrite:
    """離れるときの書き起こしで、崩れた応答を書き直させて通ったことが trace に残ることを保証する (design_decisions D1626)。"""

    def test_rewritten_writing_is_traced(self) -> None:
        """1 回目の応答が崩れて 2 回目で書けたときは、outcome が written で、rewritten が True になる。"""
        writing, repository, _, recorder = _make(_Sequence({"episodes": [_item(about=" ")]}, {"episodes": [_item()]}))  # type: ignore[arg-type]

        writing.write(ADA, trigger=TRIGGER_LEAVING)

        (payload,) = recorder.of(TraceEventKind.EPISODE_WRITING)
        assert (payload["outcome"], payload["rewritten"], payload["episode_count"]) == ("written", True, 1)
        assert len(repository.list_by_being(ADA_BEING)) == 1

    def test_twice_broken_response_is_traced_as_failed_with_both_reasons(self) -> None:
        """2 回とも応答が崩れていたら、1 件も記録に入れず、outcome が failed で、error に 1 回目と 2 回目の理由が残る。"""
        writing, repository, _, recorder = _make(
            _Sequence({"episodes": [_item(about=" ")]}, {"episodes": "金庫"})  # type: ignore[arg-type]
        )

        writing.write(ADA, trigger=TRIGGER_LEAVING)

        (payload,) = recorder.of(TraceEventKind.EPISODE_WRITING)
        assert (payload["outcome"], payload["error_type"]) == ("failed", "EpisodeWritingResponseException")
        assert "episodes list" in payload["error"] and "first attempt: episode about" in payload["error"]
        assert repository.list_by_being(ADA_BEING) == ()


class TestPlayerEpisodeWritingTrace:
    """PlayerEpisodeWriting が書き起こしのたびに、何が起きたかを trace に 1 件残すことを保証する。"""

    def test_written_episodes_are_traced(self) -> None:
        """書けたときは、呼んだきっかけ、件数、各エピソードの呼び名・目次・本文の長さ、切り詰めを残す。"""
        writing, repository, _, recorder = _make(_Completion({"episodes": [_item(), _item(about="あ" * 45)]}))

        writing.write(ADA, trigger=TRIGGER_LEAVING)

        (payload,) = recorder.of(TraceEventKind.EPISODE_WRITING)
        first, second = repository.list_by_being(ADA_BEING)
        assert payload["outcome"] == "written"
        assert payload["trigger"] == "leaving"
        assert payload["being_id"] == "being_p1"
        assert payload["event_count"] == 1
        assert payload["awaited_until_turn"] is None
        assert payload["episode_count"] == 2
        assert payload["dropped_count"] == 0
        assert payload["rewritten"] is False
        assert payload["episodes"] == [
            {
                "handle": first.handle,
                "summary": "金庫を開けた",
                "recall_when": "金庫の話が出たとき",
                "body_length": 12,
                "truncated": {},
            },
            {
                "handle": second.handle,
                "summary": "あ" * 40,
                "recall_when": "金庫の話が出たとき",
                "body_length": 12,
                "truncated": {"about": 45},
            },
        ]

    def test_awaited_range_is_traced(self) -> None:
        """いきさつを待っている範囲があれば、その終わりのターンを awaited_until_turn に残す。"""
        completion = _Completion({"episodes": []})
        writing, *_, recorder = _make(completion, remembered=tuple(f"ターン {n}" for n in range(1, 21)))
        store = writing._write_episodes._store
        memory = store.get(ADA_BEING)
        memory.end_turn(turn=20)
        store.save(memory)

        writing.write(ADA, trigger=TRIGGER_LEAVING)

        (payload,) = recorder.of(TraceEventKind.EPISODE_WRITING)
        assert (payload["awaited_until_turn"], payload["event_count"]) == (10, 10)

    def test_zero_episodes_is_traced_as_written(self) -> None:
        """0 件が返ったときも、呼んだことと 0 件だったことを残す。"""
        writing, _, _, recorder = _make(_Completion({"episodes": []}), remembered=("雨が降った。",))

        writing.write(ADA, trigger=TRIGGER_LEAVING)

        (payload,) = recorder.of(TraceEventKind.EPISODE_WRITING)
        assert payload["outcome"] == "written"
        assert payload["episode_count"] == 0

    def test_completion_failure_is_traced_and_swallowed(self) -> None:
        """呼び出しが失敗したら、例外を外へ出さず、エピソードを作らず、失敗と理由を残す。"""
        writing, repository, _, recorder = _make(
            _Completion(error=LlmApiCallException("down", error_code="LLM_RATE_LIMIT"))
        )

        writing.write(ADA, trigger=TRIGGER_LEAVING)

        (payload,) = recorder.of(TraceEventKind.EPISODE_WRITING)
        assert payload["outcome"] == "failed"
        assert payload["error_type"] == "LlmApiCallException"
        assert payload["episode_count"] == 0
        assert repository.list_by_being(ADA_BEING) == ()

    def test_malformed_response_is_traced_as_failed(self) -> None:
        """応答の形が崩れていたら、失敗として残し、エピソードを作らない。"""
        writing, repository, _, recorder = _make(_Completion({"episodes": [_item(body="")]}))

        writing.write(ADA, trigger=TRIGGER_LEAVING)

        (payload,) = recorder.of(TraceEventKind.EPISODE_WRITING)
        assert payload["outcome"] == "failed"
        assert payload["error_type"] == "EpisodeWritingResponseException"
        assert repository.list_by_being(ADA_BEING) == ()

    def test_being_lookup_failure_is_traced_and_swallowed(self) -> None:
        """Being を引く処理が例外を投げても、外へ出さず、LLM を呼ばず、失敗として残す。"""
        completion = _Completion({"episodes": [_item()]})
        writing, *_, recorder = _make(completion)

        def _broken(pid: PlayerId) -> BeingId | None:
            raise RuntimeError("resolver down")

        writing._being_id_of = _broken

        writing.write(ADA, trigger=TRIGGER_LEAVING)

        (payload,) = recorder.of(TraceEventKind.EPISODE_WRITING)
        assert payload["outcome"] == "failed"
        assert payload["being_id"] is None
        assert completion.messages == []

    def test_player_without_being_is_skipped_without_calling(self) -> None:
        """Being が引けないプレイヤーは、LLM を呼ばず、飛ばした理由を残す。"""
        completion = _Completion({"episodes": [_item()]})
        writing, _, _, recorder = _make(completion, being=None)

        writing.write(ADA, trigger=TRIGGER_LEAVING)

        (payload,) = recorder.of(TraceEventKind.EPISODE_WRITING)
        assert payload["outcome"] == "skipped"
        assert payload["skip_reason"] == "no_being"
        assert completion.messages == []

    def test_no_events_is_skipped_without_calling(self) -> None:
        """Being の短期記憶にまとめていない出来事が 1 つも無ければ、LLM を呼ばず、飛ばした理由と出来事の数 0 を残す。"""
        completion = _Completion({"episodes": [_item()]})
        writing, _, _, recorder = _make(completion, remembered=())

        writing.write(ADA, trigger=TRIGGER_LEAVING)

        (payload,) = recorder.of(TraceEventKind.EPISODE_WRITING)
        assert payload["outcome"] == "skipped"
        assert payload["skip_reason"] == "no_events"
        assert payload["event_count"] == 0
        assert completion.messages == []
