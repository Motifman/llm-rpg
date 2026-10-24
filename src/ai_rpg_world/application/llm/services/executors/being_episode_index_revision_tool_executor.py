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
from ai_rpg_world.being.application.episode_index_text import EPISODE_INDEX_HEADING
from ai_rpg_world.being.domain.episode import (
    INDEX_TEXT_MAX_LENGTH,
    EpisodeIndex,
    EpisodeRepository,
)
from ai_rpg_world.being.domain.memory_turn_clock import (
    MemoryTurnReader,
)
from ai_rpg_world.domain.common.exception import DomainException

_logger = logging.getLogger(__name__)

_TEXT_KEYS = ("about", "recall_when")
_MALFORMED_MESSAGE = (
    f"handle には{EPISODE_INDEX_HEADING}の ep_ で始まる呼び名を、"
    "about にはどんな記憶か、recall_when にはどんな時に思い出すかを、それぞれ文で書いてください。"
)
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
        handle = arguments.get("handle")
        base: dict[str, Any] = {
            "being_id": acting.being_id.value,
            "handle": handle if isinstance(handle, str) else None,
        }
        raw = {key: arguments.get(key) for key in _TEXT_KEYS}
        if not isinstance(handle, str) or not handle.strip() or not all(
            isinstance(v, str) and v.strip() for v in raw.values()
        ):
            self._record(acting, outcome="rejected", reject_reason="malformed", **base)
            return LlmCommandResultDto(success=False, message=_MALFORMED_MESSAGE, error_code="INVALID_ARGUMENT")
        handle = handle.strip()
        base["handle"] = handle
        texts: dict[str, str] = {}
        truncated: dict[str, int] = {}
        for key, value in raw.items():
            text = str(value).strip()
            if len(text) > INDEX_TEXT_MAX_LENGTH:
                truncated[key] = len(text)
                text = text[:INDEX_TEXT_MAX_LENGTH]
            texts[key] = text
        episode = self.repository.find_by_handle(acting.being_id, handle)
        if episode is None:
            self._record(acting, outcome="rejected", reject_reason="unknown_handle", **base)
            return LlmCommandResultDto(
                success=False,
                message=f"{handle} という記憶は無い。{EPISODE_INDEX_HEADING}の呼び名を使ってください。",
                error_code="INVALID_ARGUMENT",
            )
        index = EpisodeIndex(summary=texts["about"], recall_when=texts["recall_when"])
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
            return LlmCommandResultDto(success=False, message="目次を直せなかった。", error_code="INVALID_STATE")
        self._record(
            acting,
            outcome="revised",
            turn=turn,
            before=_index_payload(previous),
            after=_index_payload(index),
            truncated=truncated,
            **base,
        )
        return LlmCommandResultDto(
            success=True,
            message=f"[{handle}] の目次を直した: {index.summary} — 思い出すとき: {index.recall_when}",
        )

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
