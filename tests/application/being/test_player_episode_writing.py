from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from ai_rpg_world.application.being.player_episode_writing import (
    TRIGGER_COMPACTION,
    TRIGGER_LEAVING,
    PlayerEpisodeWriting,
)
from ai_rpg_world.application.llm.contracts.chunk_encoding import UnifiedRecentEventEntry
from ai_rpg_world.application.llm.contracts.dtos import ActionResultEntry
from ai_rpg_world.application.llm.exceptions import LlmApiCallException
from ai_rpg_world.application.observation.contracts.dtos import (
    ObservationEntry,
    ObservationOutput,
)
from ai_rpg_world.application.trace import TraceEventKind
from ai_rpg_world.application.trace.recorder import NullTraceRecorder
from ai_rpg_world.being.application.episode_writing import AddEpisodesToMemory
from ai_rpg_world.being.infrastructure.in_memory_episode_repository import (
    InMemoryEpisodeRepository,
)
from ai_rpg_world.being.infrastructure.in_memory_memory_turn_clock import (
    InMemoryMemoryTurnClock,
)
from ai_rpg_world.being.infrastructure.llm_episode_writer import (
    EpisodeWritingCompletion,
    LlmEpisodeWriter,
)
from ai_rpg_world.domain.being.value_object.being_id import BeingId
from ai_rpg_world.domain.player.value_object.player_id import PlayerId

ADA = PlayerId(1)
ADA_BEING = BeingId("being_p1")
_BASE = datetime(2026, 6, 1, tzinfo=timezone.utc)


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


def _observation(prose: str, minute: int) -> UnifiedRecentEventEntry:
    return UnifiedRecentEventEntry.from_observation(
        ObservationEntry(
            occurred_at=_BASE + timedelta(minutes=minute),
            game_time_label=f"深夜 0:{minute:02d}",
            output=ObservationOutput(prose=prose, structured={}),
        )
    )


def _action(summary: str, minute: int) -> UnifiedRecentEventEntry:
    return UnifiedRecentEventEntry.from_action_result(
        ActionResultEntry(
            occurred_at=_BASE + timedelta(minutes=minute),
            game_time_label=f"深夜 0:{minute:02d}",
            action_summary=summary,
            result_summary="成功した。",
        )
    )


def _item(**overrides: str) -> dict[str, str]:
    item = {"about": "金庫を開けた", "recall_when": "金庫の話が出たとき", "body": "紙の番号で金庫が開いた。"}
    item.update(overrides)
    return item


def _make(completion: _Completion, *, being: BeingId | None = ADA_BEING):
    repository = InMemoryEpisodeRepository()
    turns = InMemoryMemoryTurnClock()
    recorder = _Recorder()
    writing = PlayerEpisodeWriting(
        writer=LlmEpisodeWriter(completion),
        add_episodes=AddEpisodesToMemory(repository),
        being_id_of=lambda pid: being,
        turn_reader=turns,
        environment_name_of=lambda pid: "地下の金庫室",
        persona_of=lambda pid: ("エイダ", "慎重な錠前師"),
        trace_recorder_provider=lambda: recorder,
        current_tick_provider=lambda: 7,
    )
    return writing, repository, turns, recorder


class TestPlayerEpisodeWritingInput:
    """PlayerEpisodeWriting がプレイヤーの出来事を、書き起こしの部品に渡す形を保証する。"""

    def test_events_are_rendered_like_recent_events_oldest_first(self) -> None:
        """渡した出来事を、届いた順によらず古い順に、【直近の出来事】と同じ行の形で渡す。"""
        completion = _Completion({"episodes": []})
        writing, *_ = _make(completion)

        writing.write(ADA, [_observation("金庫が開いた。", 2), _action("棚を調べた", 1)], trigger=TRIGGER_COMPACTION)

        user = completion.messages[0][1]["content"]
        assert user.index("[行動] 棚を調べた") < user.index("金庫が開いた。")
        assert "- " in user

    def test_episode_carries_being_turn_and_environment_name(self) -> None:
        """書いたエピソードは、その Being の記憶のターン数と環境の名前を持ち、Being の記録に入る。"""
        writing, repository, turns, _ = _make(_Completion({"episodes": [_item()]}))
        for _ in range(4):
            turns.advance_turn(ADA_BEING)

        writing.write(ADA, [_observation("金庫が開いた。", 1)], trigger=TRIGGER_COMPACTION)

        (episode,) = repository.list_by_being(ADA_BEING)
        assert episode.written_turn == 4
        assert episode.environment_name == "地下の金庫室"


class TestPlayerEpisodeWritingTrace:
    """PlayerEpisodeWriting が書き起こしのたびに、何が起きたかを trace に 1 件残すことを保証する。"""

    def test_written_episodes_are_traced(self) -> None:
        """書けたときは、呼んだきっかけ、件数、各エピソードの呼び名・目次・本文の長さ、切り詰めを残す。"""
        writing, repository, _, recorder = _make(
            _Completion({"episodes": [_item(), _item(about="あ" * 45)]})
        )

        writing.write(ADA, [_observation("金庫が開いた。", 1)], trigger=TRIGGER_LEAVING)

        (payload,) = recorder.of(TraceEventKind.EPISODE_WRITING)
        first, second = repository.list_by_being(ADA_BEING)
        assert payload["outcome"] == "written"
        assert payload["trigger"] == "leaving"
        assert payload["being_id"] == "being_p1"
        assert payload["event_count"] == 1
        assert payload["episode_count"] == 2
        assert payload["dropped_count"] == 0
        assert payload["episodes"] == [
            {"handle": first.handle, "summary": "金庫を開けた", "recall_when": "金庫の話が出たとき", "body_length": 12, "truncated": {}},
            {"handle": second.handle, "summary": "あ" * 40, "recall_when": "金庫の話が出たとき", "body_length": 12, "truncated": {"about": 45}},
        ]

    def test_zero_episodes_is_traced_as_written(self) -> None:
        """0 件が返ったときも、呼んだことと 0 件だったことを残す。"""
        writing, _, _, recorder = _make(_Completion({"episodes": []}))

        writing.write(ADA, [_observation("雨が降った。", 1)], trigger=TRIGGER_COMPACTION)

        (payload,) = recorder.of(TraceEventKind.EPISODE_WRITING)
        assert payload["outcome"] == "written"
        assert payload["episode_count"] == 0

    def test_completion_failure_is_traced_and_swallowed(self) -> None:
        """呼び出しが失敗したら、例外を外へ出さず、エピソードを作らず、失敗と理由を残す。"""
        writing, repository, _, recorder = _make(
            _Completion(error=LlmApiCallException("down", error_code="LLM_RATE_LIMIT"))
        )

        writing.write(ADA, [_observation("金庫が開いた。", 1)], trigger=TRIGGER_COMPACTION)

        (payload,) = recorder.of(TraceEventKind.EPISODE_WRITING)
        assert payload["outcome"] == "failed"
        assert payload["error_type"] == "LlmApiCallException"
        assert payload["episode_count"] == 0
        assert repository.list_by_being(ADA_BEING) == ()

    def test_malformed_response_is_traced_as_failed(self) -> None:
        """応答の形が崩れていたら、失敗として残し、エピソードを作らない。"""
        writing, repository, _, recorder = _make(_Completion({"episodes": [_item(body="")]}))

        writing.write(ADA, [_observation("金庫が開いた。", 1)], trigger=TRIGGER_COMPACTION)

        (payload,) = recorder.of(TraceEventKind.EPISODE_WRITING)
        assert payload["outcome"] == "failed"
        assert payload["error_type"] == "EpisodeWritingResponseException"
        assert repository.list_by_being(ADA_BEING) == ()

    def test_being_lookup_failure_is_traced_and_swallowed(self) -> None:
        """Being を引く処理が例外を投げても、外へ出さず、LLM を呼ばず、失敗として残す。"""
        completion = _Completion({"episodes": [_item()]})
        writing, *_ , recorder = _make(completion)

        def _broken(pid: PlayerId) -> BeingId | None:
            raise RuntimeError("resolver down")

        writing._being_id_of = _broken

        writing.write(ADA, [_observation("金庫が開いた。", 1)], trigger=TRIGGER_COMPACTION)

        (payload,) = recorder.of(TraceEventKind.EPISODE_WRITING)
        assert payload["outcome"] == "failed"
        assert payload["being_id"] is None
        assert completion.messages == []

    def test_player_without_being_is_skipped_without_calling(self) -> None:
        """Being が引けないプレイヤーは、LLM を呼ばず、飛ばした理由を残す。"""
        completion = _Completion({"episodes": [_item()]})
        writing, _, _, recorder = _make(completion, being=None)

        writing.write(ADA, [_observation("金庫が開いた。", 1)], trigger=TRIGGER_COMPACTION)

        (payload,) = recorder.of(TraceEventKind.EPISODE_WRITING)
        assert payload["outcome"] == "skipped"
        assert payload["skip_reason"] == "no_being"
        assert completion.messages == []

    def test_no_events_is_skipped_without_calling(self) -> None:
        """出来事が 1 件も無ければ、LLM を呼ばず、飛ばした理由を残す。"""
        completion = _Completion({"episodes": [_item()]})
        writing, _, _, recorder = _make(completion)

        writing.write(ADA, [], trigger=TRIGGER_LEAVING)

        (payload,) = recorder.of(TraceEventKind.EPISODE_WRITING)
        assert payload["outcome"] == "skipped"
        assert payload["skip_reason"] == "no_events"
        assert completion.messages == []
