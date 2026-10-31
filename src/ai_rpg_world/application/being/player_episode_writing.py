"""環境を離れるときに、プレイヤーの Being の短期記憶からエピソードを書き起こし、trace に残す (#1626、design_decisions D1824-23)。"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from ai_rpg_world.application.trace import TraceEventKind
from ai_rpg_world.application.trace.recorder import ITraceRecorder
from ai_rpg_world.being.application.write_episodes_on_leaving import (
    WriteEpisodesOnLeaving,
    WriteEpisodesOnLeavingCommand,
)
from ai_rpg_world.being.domain.being_id import BeingId
from ai_rpg_world.being.domain.memory_turn_clock import MemoryTurnReader
from ai_rpg_world.being.domain.persona import Persona
from ai_rpg_world.domain.player.value_object.player_id import PlayerId

_logger = logging.getLogger(__name__)

TRIGGER_LEAVING = "leaving"
_ERROR_TEXT_MAX_LENGTH = 300


class PlayerEpisodeWriting:
    """プレイヤーの Being を引いて ``WriteEpisodesOnLeaving`` を呼び、書き起こしのたびに trace を 1 件残す。

    名前と一人称は Being の人柄 (``persona_of``) から、人格の文はゲームの側 (``persona_text_of``) から引く
    (design_decisions D1469-2)。

    書き起こしの失敗で run を止めない。
    """

    def __init__(
        self,
        *,
        write_episodes: WriteEpisodesOnLeaving,
        being_id_of: Callable[[PlayerId], BeingId | None],
        turn_reader: MemoryTurnReader,
        environment_name_of: Callable[[PlayerId], str],
        persona_of: Callable[[BeingId], Persona],
        persona_text_of: Callable[[int], str],
        trace_recorder_provider: Callable[[], ITraceRecorder],
        current_tick_provider: Callable[[], int | None],
    ) -> None:
        self._write_episodes = write_episodes
        self._being_id_of = being_id_of
        self._turn_reader = turn_reader
        self._environment_name_of = environment_name_of
        self._persona_of = persona_of
        self._persona_text_of = persona_text_of
        self._trace_recorder_provider = trace_recorder_provider
        self._current_tick_provider = current_tick_provider

    def write(self, player_id: PlayerId, *, trigger: str) -> None:
        base: dict[str, Any] = {"trigger": trigger, "being_id": None, "event_count": None}
        try:
            being_id = self._being_id_of(player_id)
            if being_id is None:
                self._record(player_id, outcome="skipped", skip_reason="no_being", **base)
                return
            base["being_id"] = being_id.value
            written_turn = self._turn_reader.current_turn(being_id)
            environment_name = self._environment_name_of(player_id)
            outcome = self._write_episodes.execute(
                WriteEpisodesOnLeavingCommand(
                    being_id=being_id,
                    persona=self._persona_of(being_id),
                    persona_text=self._persona_text_of(int(player_id.value)),
                    environment_name=environment_name,
                    written_turn=written_turn,
                )
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
        base["event_count"] = outcome.experience_count
        base["awaited_until_turn"] = outcome.awaited_until_turn
        result = outcome.result
        if result is None:
            self._record(player_id, outcome="skipped", skip_reason="no_events", **base)
            return
        self._record(
            player_id,
            outcome="written",
            episode_count=len(result.written),
            dropped_count=result.dropped_count,
            rewritten=result.rewritten,
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


__all__ = ["TRIGGER_LEAVING", "PlayerEpisodeWriting"]
