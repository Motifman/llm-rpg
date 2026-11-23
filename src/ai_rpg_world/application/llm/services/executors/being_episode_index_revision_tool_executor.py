"""【思い出せる出来事】の目次を、本人が直す (#1623)。"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from ai_rpg_world.application.being.acting_being import ActingBeing
from ai_rpg_world.application.llm.contracts.dtos import LlmCommandResultDto
from ai_rpg_world.application.llm.tool_constants import TOOL_NAME_EPISODE_REVISE_INDEX
from ai_rpg_world.application.trace import TraceEventKind
from ai_rpg_world.application.trace.recorder import ITraceRecorder
from ai_rpg_world.being.application.episode_index_revision_tool import (
    HANDLE,
    INDEX_NOT_REVISED_TEXT,
    MALFORMED_INDEX_REVISION_TEXT,
    index_revised_text,
    read_index_revision,
    unknown_handle_text,
)
from ai_rpg_world.being.domain.episode import EpisodeIndex, EpisodeRepository
from ai_rpg_world.being.domain.memory_turn_clock import MemoryTurnReader
from ai_rpg_world.domain.common.exception import DomainException

_logger = logging.getLogger(__name__)

_ERROR_TEXT_MAX_LENGTH = 300


def _index_payload(index: EpisodeIndex) -> dict[str, str]:
    return {"about": index.summary, "recall_when": index.recall_when}


@dataclass
class BeingEpisodeIndexRevisionToolExecutor:
    """長すぎる文は切り詰める。ドメインは上限を超えた文を受け付けない (design_decisions D1623)。"""

    repository: EpisodeRepository
    turn_reader: MemoryTurnReader
    trace_recorder_provider: Callable[[], ITraceRecorder]
    current_tick_provider: Callable[[], int | None]

    def get_handlers(
        self,
    ) -> dict[str, Callable[[ActingBeing, dict[str, Any]], LlmCommandResultDto]]:
        return {TOOL_NAME_EPISODE_REVISE_INDEX: self._run}

    def _run(self, acting: ActingBeing, arguments: dict[str, Any]) -> LlmCommandResultDto:
        handle = arguments.get(HANDLE)
        base: dict[str, Any] = {
            "being_id": acting.being_id.value,
            "handle": handle if isinstance(handle, str) else None,
        }
        request = read_index_revision(arguments)
        if request is None:
            self._record(acting, outcome="rejected", reject_reason="malformed", **base)
            return LlmCommandResultDto(
                success=False, message=MALFORMED_INDEX_REVISION_TEXT, error_code="INVALID_ARGUMENT"
            )
        base["handle"] = request.handle
        episode = self.repository.find_by_handle(acting.being_id, request.handle)
        if episode is None:
            self._record(acting, outcome="rejected", reject_reason="unknown_handle", **base)
            return LlmCommandResultDto(
                success=False, message=unknown_handle_text(request.handle), error_code="INVALID_ARGUMENT"
            )
        index = request.index
        try:
            turn = self.turn_reader.current_turn(acting.being_id)
            previous = episode.index
            episode.revise_index(index, turn=turn)
            self.repository.save(episode)
        except DomainException as exc:
            _logger.warning("episode index revision failed (being_id=%s): %s", acting.being_id.value, exc)
            self._record(
                acting,
                outcome="failed",
                error_type=type(exc).__name__,
                error=str(exc)[:_ERROR_TEXT_MAX_LENGTH],
                **base,
            )
            return LlmCommandResultDto(success=False, message=INDEX_NOT_REVISED_TEXT, error_code="INVALID_STATE")
        self._record(
            acting,
            outcome="revised",
            turn=turn,
            before=_index_payload(previous),
            after=_index_payload(index),
            truncated=request.truncated,
            **base,
        )
        return LlmCommandResultDto(success=True, message=index_revised_text(request.handle, index))

    def _record(self, acting: ActingBeing, **payload: Any) -> None:
        try:
            self.trace_recorder_provider().record(
                TraceEventKind.EPISODE_INDEX_REVISION,
                tick=self.current_tick_provider(),
                player_id=int(acting.player_id.value),
                **payload,
            )
        except Exception:
            _logger.exception("trace recorder.record raised for EPISODE_INDEX_REVISION; skipping")


__all__ = ["BeingEpisodeIndexRevisionToolExecutor"]
