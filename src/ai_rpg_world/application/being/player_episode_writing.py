"""プレイヤーの出来事を、その Being のエピソードとして書き起こす。"""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from typing import Any

from ai_rpg_world.application.llm.contracts.chunk_encoding import UnifiedRecentEventEntry
from ai_rpg_world.application.llm.services.recent_events_formatter import (
    DefaultRecentEventsFormatter,
)
from ai_rpg_world.application.trace import TraceEventKind
from ai_rpg_world.application.trace.recorder import ITraceRecorder
from ai_rpg_world.being.application.episode_writing import EpisodeWriter
from ai_rpg_world.domain.being.value_object.being_id import BeingId
from ai_rpg_world.domain.memory.expectation.repository.memory_turn_reader import (
    MemoryTurnReader,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId

_logger = logging.getLogger(__name__)

TRIGGER_COMPACTION = "compaction"
TRIGGER_LEAVING = "leaving"
_ERROR_TEXT_MAX_LENGTH = 300


class PlayerEpisodeWriting:
    """書き起こしの失敗で run を止めない。失敗は trace に残す。"""

    def __init__(
        self,
        *,
        writer: EpisodeWriter,
        being_id_of: Callable[[PlayerId], BeingId | None],
        turn_reader: MemoryTurnReader,
        environment_name_of: Callable[[PlayerId], str],
        persona_of: Callable[[int], tuple[str, str]],
        trace_recorder_provider: Callable[[], ITraceRecorder],
        current_tick_provider: Callable[[], int | None],
    ) -> None:
        self._writer = writer
        self._being_id_of = being_id_of
        self._turn_reader = turn_reader
        self._environment_name_of = environment_name_of
        self._persona_of = persona_of
        self._trace_recorder_provider = trace_recorder_provider
        self._current_tick_provider = current_tick_provider

    def write(
        self,
        player_id: PlayerId,
        entries: Sequence[UnifiedRecentEventEntry],
        *,
        trigger: str,
    ) -> None:
        base: dict[str, Any] = {
            "trigger": trigger,
            "being_id": None,
            "event_count": len(entries),
        }
        try:
            being_id = self._being_id_of(player_id)
            if being_id is None:
                self._record(player_id, outcome="skipped", skip_reason="no_being", **base)
                return
            base["being_id"] = being_id.value
            if not entries:
                self._record(player_id, outcome="skipped", skip_reason="no_events", **base)
                return
            written_turn = self._turn_reader.current_turn(being_id)
            environment_name = self._environment_name_of(player_id)
            self_name, persona = self._persona_of(int(player_id.value))
            result = self._writer.write(
                being_id=being_id,
                self_name=self_name,
                persona=persona,
                events_text=_render(entries),
                environment_name=environment_name,
                written_turn=written_turn,
            )
        except Exception as exc:
            _logger.warning(
                "episode writing failed (player_id=%s, trigger=%s): %s",
                player_id.value,
                trigger,
                exc,
            )
            self._record(
                player_id,
                outcome="failed",
                episode_count=0,
                error_type=type(exc).__name__,
                error=str(exc)[:_ERROR_TEXT_MAX_LENGTH],
                **base,
            )
            return
        self._record(
            player_id,
            outcome="written",
            episode_count=len(result.written),
            dropped_count=result.dropped_count,
            written_turn=written_turn,
            environment_name=environment_name,
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

    def skip(self, player_id: PlayerId, *, trigger: str, reason: str) -> None:
        self._record(player_id, trigger=trigger, outcome="skipped", skip_reason=reason)

    def _record(self, player_id: PlayerId, **payload: Any) -> None:
        try:
            self._trace_recorder_provider().record(
                TraceEventKind.EPISODE_WRITING,
                tick=self._current_tick_provider(),
                player_id=int(player_id.value),
                **payload,
            )
        except Exception:
            _logger.exception("trace recorder.record raised for EPISODE_WRITING; skipping")


def _render(entries: Sequence[UnifiedRecentEventEntry]) -> str:
    ordered = sorted(entries, key=lambda entry: entry.occurred_at.timestamp())
    return DefaultRecentEventsFormatter().format_unified_entries(ordered)


__all__ = ["TRIGGER_COMPACTION", "TRIGGER_LEAVING", "PlayerEpisodeWriting"]
