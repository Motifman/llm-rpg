"""【思い出せる出来事】の呼び名から、エピソードの本文を呼び出す (#1623)。"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from ai_rpg_world.application.being.acting_being import ActingBeing
from ai_rpg_world.application.llm.contracts.dtos import LlmCommandResultDto
from ai_rpg_world.application.llm.tool_constants import TOOL_NAME_EPISODE_RECALL
from ai_rpg_world.application.trace import TraceEventKind
from ai_rpg_world.application.trace.recorder import ITraceRecorder
from ai_rpg_world.being.application.episode_recall_tool import (
    MALFORMED_HANDLES_TEXT,
    read_handles,
    recalled_text,
    too_many_handles_text,
)
from ai_rpg_world.being.domain.episode import EpisodeRepository
from ai_rpg_world.being.domain.episode_recall import EpisodeRecallHandles, recall_episodes
from ai_rpg_world.being.domain.memory_turn_clock import (
    MemoryTurnReader,
)
from ai_rpg_world.domain.being.exception.being_exceptions import EpisodeRecallLimitExceededException
from ai_rpg_world.domain.common.exception import DomainException

_logger = logging.getLogger(__name__)

_ERROR_TEXT_MAX_LENGTH = 300


@dataclass
class BeingEpisodeRecallToolExecutor:
    """上限 M はスキーマの ``maxItems`` にも書くが、provider は守らせないのでここで確かめる。"""

    repository: EpisodeRepository
    turn_reader: MemoryTurnReader
    max_handles: int
    trace_recorder_provider: Callable[[], ITraceRecorder]
    current_tick_provider: Callable[[], int | None]

    def __post_init__(self) -> None:
        if not isinstance(self.max_handles, int) or self.max_handles < 1:
            raise ValueError("max_handles must be int >= 1")

    def get_handlers(
        self,
    ) -> dict[str, Callable[[ActingBeing, dict[str, Any]], LlmCommandResultDto]]:
        return {TOOL_NAME_EPISODE_RECALL: self._run}

    def _run(self, acting: ActingBeing, arguments: dict[str, Any]) -> LlmCommandResultDto:
        base: dict[str, Any] = {
            "being_id": acting.being_id.value,
            "requested": arguments.get("handles"),
        }
        handles = read_handles(arguments)
        if handles is None:
            self._record(acting, outcome="rejected", reject_reason="malformed", max_handles=self.max_handles, **base)
            return LlmCommandResultDto(success=False, message=MALFORMED_HANDLES_TEXT, error_code="INVALID_ARGUMENT")
        try:
            within = EpisodeRecallHandles.within(handles, limit=self.max_handles)
        except EpisodeRecallLimitExceededException:
            self._record(acting, outcome="rejected", reject_reason="too_many", max_handles=self.max_handles, **base)
            return LlmCommandResultDto(
                success=False,
                message=too_many_handles_text(self.max_handles),
                error_code="INVALID_ARGUMENT",
            )
        try:
            turn = self.turn_reader.current_turn(acting.being_id)
            results = recall_episodes(self.repository, acting.being_id, within, turn=turn)
        except DomainException as exc:
            _logger.warning("episode recall failed (being_id=%s): %s", acting.being_id.value, exc)
            self._record(
                acting,
                outcome="failed",
                error_type=type(exc).__name__,
                error=str(exc)[:_ERROR_TEXT_MAX_LENGTH],
                **base,
            )
            return LlmCommandResultDto(
                success=False, message="思い出そうとしたが、うまく思い出せなかった。", error_code="INVALID_STATE"
            )
        self._record(
            acting,
            outcome="recalled",
            turn=turn,
            results=[
                {
                    "handle": r.handle,
                    "found": r.episode is not None,
                    "recall_count": None if r.episode is None else r.episode.recall_count,
                }
                for r in results
            ],
            **base,
        )
        return LlmCommandResultDto(success=True, message=recalled_text(results))

    def _record(self, acting: ActingBeing, **payload: Any) -> None:
        try:
            self.trace_recorder_provider().record(
                TraceEventKind.EPISODE_RECALL,
                tick=self.current_tick_provider(),
                player_id=int(acting.player_id.value),
                **payload,
            )
        except Exception:
            _logger.exception("trace recorder.record raised for EPISODE_RECALL; skipping")


__all__ = ["BeingEpisodeRecallToolExecutor"]
