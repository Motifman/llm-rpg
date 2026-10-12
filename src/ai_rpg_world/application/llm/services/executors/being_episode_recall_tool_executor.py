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
from ai_rpg_world.being.application.episode_index_text import EPISODE_INDEX_HEADING
from ai_rpg_world.being.domain.episode import EpisodeRepository
from ai_rpg_world.being.domain.episode_recall import RecallResult, recall_episodes
from ai_rpg_world.domain.common.exception import DomainException
from ai_rpg_world.domain.memory.expectation.repository.memory_turn_reader import (
    MemoryTurnReader,
)

_logger = logging.getLogger(__name__)

UNKNOWN_EPISODE_TEXT = "そのような記憶は思い出せない。"
_MALFORMED_MESSAGE = (
    f"handles には、{EPISODE_INDEX_HEADING}に並ぶ ep_ で始まる呼び名を、"
    '1 件でも配列で渡してください (例: ["ep_3f2a7b"])。'
)
_ERROR_TEXT_MAX_LENGTH = 300


def _read_handles(arguments: dict[str, Any]) -> list[str] | None:
    raw = arguments.get("handles")
    if not isinstance(raw, list) or not raw:
        return None
    if not all(isinstance(h, str) and h.strip() for h in raw):
        return None
    return [h.strip() for h in raw]


def _result_text(result: RecallResult) -> str:
    if result.episode is None:
        return f"[{result.handle}] {UNKNOWN_EPISODE_TEXT}"
    return f"[{result.handle}] {result.episode.index.summary}\n  {result.episode.body}"


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
        handles = _read_handles(arguments)
        if handles is None:
            self._record(acting, outcome="rejected", reject_reason="malformed", max_handles=self.max_handles, **base)
            return LlmCommandResultDto(success=False, message=_MALFORMED_MESSAGE, error_code="INVALID_ARGUMENT")
        if len(set(handles)) > self.max_handles:
            self._record(acting, outcome="rejected", reject_reason="too_many", max_handles=self.max_handles, **base)
            return LlmCommandResultDto(
                success=False,
                message=f"一度に思い出せるのは {self.max_handles} 件までです。呼び名を減らしてください。",
                error_code="INVALID_ARGUMENT",
            )
        try:
            turn = self.turn_reader.current_turn(acting.being_id)
            results = recall_episodes(self.repository, acting.being_id, handles, turn=turn)
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
        return LlmCommandResultDto(success=True, message="\n".join(_result_text(r) for r in results))

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


__all__ = ["UNKNOWN_EPISODE_TEXT", "BeingEpisodeRecallToolExecutor"]
