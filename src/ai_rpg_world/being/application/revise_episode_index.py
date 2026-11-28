from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from ai_rpg_world.being.application.episode_index_revision_tool import (
    HANDLE,
    INDEX_NOT_REVISED_TEXT,
    MALFORMED_INDEX_REVISION_TEXT,
    EpisodeIndexRevisionOutcome,
    EpisodeIndexRevisionResult,
    IndexRevisionRejectReason,
    index_revised_text,
    read_index_revision,
    unknown_handle_text,
)
from ai_rpg_world.being.domain.being_id import BeingId
from ai_rpg_world.being.domain.episode import EpisodeRepository
from ai_rpg_world.domain.being.exception.being_exceptions import EpisodeValidationException


@dataclass(frozen=True, kw_only=True)
class ReviseEpisodeIndexCommand:
    """``arguments`` は目次を直すツールに書かれた引数。``turn`` は直した記憶のターン。"""

    being_id: BeingId
    arguments: Mapping[str, object]
    turn: int


@dataclass(frozen=True)
class EpisodeIndexRevisionAnswer:
    """``body`` は本人に返す文。"""

    body: str
    revision: EpisodeIndexRevisionOutcome

    @property
    def succeeded(self) -> bool:
        return self.revision.outcome is EpisodeIndexRevisionResult.REVISED


class ReviseEpisodeIndex:
    def __init__(self, *, episodes: EpisodeRepository) -> None:
        self._episodes = episodes

    def execute(self, command: ReviseEpisodeIndexCommand) -> EpisodeIndexRevisionAnswer:
        handle = command.arguments.get(HANDLE)
        request = read_index_revision(command.arguments)
        if request is None:
            return EpisodeIndexRevisionAnswer(
                MALFORMED_INDEX_REVISION_TEXT,
                EpisodeIndexRevisionOutcome(
                    handle=handle if isinstance(handle, str) else None,
                    outcome=EpisodeIndexRevisionResult.REJECTED,
                    reject_reason=IndexRevisionRejectReason.MALFORMED,
                ),
            )
        episode = self._episodes.find_by_handle(command.being_id, request.handle)
        if episode is None:
            return EpisodeIndexRevisionAnswer(
                unknown_handle_text(request.handle),
                EpisodeIndexRevisionOutcome(
                    handle=request.handle,
                    outcome=EpisodeIndexRevisionResult.REJECTED,
                    reject_reason=IndexRevisionRejectReason.UNKNOWN_HANDLE,
                ),
            )
        before = episode.index
        # 保存の失敗まで「直せなかった」と返すと、本人は書き方が悪かったと読んで同じ直しを繰り返す (D2261)。
        try:
            episode.revise_index(request.index, turn=command.turn)
        except EpisodeValidationException:
            return EpisodeIndexRevisionAnswer(
                INDEX_NOT_REVISED_TEXT,
                EpisodeIndexRevisionOutcome(handle=request.handle, outcome=EpisodeIndexRevisionResult.FAILED),
            )
        self._episodes.save(episode)
        return EpisodeIndexRevisionAnswer(
            index_revised_text(request.handle, request.index),
            EpisodeIndexRevisionOutcome(
                handle=request.handle,
                outcome=EpisodeIndexRevisionResult.REVISED,
                before=before,
                after=request.index,
                truncated=request.truncated,
            ),
        )


__all__ = ["EpisodeIndexRevisionAnswer", "ReviseEpisodeIndex", "ReviseEpisodeIndexCommand"]
