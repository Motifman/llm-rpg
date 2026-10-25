"""短期記憶が古いターンのいきさつを頼んだとき、その範囲のエピソードを裏で書き起こし、その Being のターンの始めに記憶に加える (#1824、design_decisions D1824-14)。"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from ai_rpg_world.application.trace import TraceEventKind
from ai_rpg_world.application.trace.recorder import ITraceRecorder
from ai_rpg_world.being.application.episode_writing import AddEpisodesToMemory
from ai_rpg_world.being.application.recent_events_text import NO_RECENT_EVENTS, experiences_text
from ai_rpg_world.being.domain.episode_writer import EpisodeContents, EpisodeWriter
from ai_rpg_world.being.domain.short_term_memory import FoldRequested
from ai_rpg_world.domain.being.value_object.being_id import BeingId

TRIGGER_FOLD = "fold"


@dataclass(frozen=True)
class WriterCircumstances:
    """書き起こす本人の名前と性格と、いる環境の名前。"""

    self_name: str
    persona: str
    environment_name: str


@dataclass(frozen=True)
class WrittenEpisodeContents:
    """裏のスレッドで書いた中身。``contents`` が None なら、行にする出来事が無く書かなかった。"""

    being_id: BeingId
    contents: EpisodeContents | None
    environment_name: str
    written_turn: int
    event_count: int


class BeingEpisodeWriting:
    """``note`` と ``apply`` をターンを進めるスレッドで、``write`` を裏のスレッドで呼ぶ (design_decisions D1837 の 4)。"""

    def __init__(
        self,
        *,
        writer: EpisodeWriter,
        add_episodes: AddEpisodesToMemory,
        circumstances_of: Callable[[BeingId], WriterCircumstances],
        trace_recorder_provider: Callable[[], ITraceRecorder | None],
        current_tick_provider: Callable[[], int | None],
    ) -> None:
        self._writer = writer
        self._add_episodes = add_episodes
        self._circumstances_of = circumstances_of
        self._trace_recorder_provider = trace_recorder_provider
        self._current_tick_provider = current_tick_provider
        self._circumstances: dict[int, WriterCircumstances] = {}

    def note(self, request: FoldRequested) -> None:
        """名前と性格と環境は Being の保存先を走査して引くので、裏のスレッドではなく、配送に渡す前にここで引いておく。

        環境は頼むたびに変わり得るので、頼みごとごとに覚える。
        """
        self._circumstances[request.event_id] = self._circumstances_of(request.being_id)

    def write(self, request: FoldRequested) -> WrittenEpisodeContents:
        """記憶には触らない。書けなければ例外を投げ、非同期の配送が失敗として trace に残す。"""
        circumstances = self._circumstances.pop(request.event_id, None)
        if circumstances is None:
            raise LookupError(f"circumstances of {request.being_id.value} were not noted; see the failure of note")
        events_text = experiences_text(request.experiences)
        contents = None
        if events_text != NO_RECENT_EVENTS:
            contents = self._writer.write(
                self_name=circumstances.self_name,
                persona=circumstances.persona,
                events_text=events_text,
            )
        return WrittenEpisodeContents(
            being_id=request.being_id,
            contents=contents,
            environment_name=circumstances.environment_name,
            written_turn=request.turn,
            event_count=len(request.experiences),
        )

    def apply(self, written: WrittenEpisodeContents) -> None:
        base: dict[str, Any] = {
            "trigger": TRIGGER_FOLD,
            "being_id": written.being_id.value,
            "event_count": written.event_count,
        }
        if written.contents is None:
            self._record(outcome="skipped", skip_reason="no_events", **base)
            return
        result = self._add_episodes.add(
            written.contents,
            being_id=written.being_id,
            environment_name=written.environment_name,
            written_turn=written.written_turn,
        )
        self._record(
            outcome="written",
            episode_count=len(result.written),
            dropped_count=result.dropped_count,
            written_turn=written.written_turn,
            environment_name=written.environment_name,
            episodes=[
                {
                    "handle": w.episode.handle,
                    "summary": w.episode.index.summary,
                    "recall_when": w.episode.index.recall_when,
                    "body_length": len(w.episode.body),
                    "truncated": dict(w.truncated),
                }
                for w in result.written
            ],
            **base,
        )

    def _record(self, **payload: Any) -> None:
        recorder = self._trace_recorder_provider()
        if recorder is None:
            return
        recorder.record(TraceEventKind.EPISODE_WRITING, tick=self._current_tick_provider(), **payload)


__all__ = ["TRIGGER_FOLD", "BeingEpisodeWriting", "WriterCircumstances", "WrittenEpisodeContents"]
