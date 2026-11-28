from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from ai_rpg_world.being.application.episode_recall_tool import (
    MALFORMED_HANDLES_TEXT,
    read_handles,
    recalled_text,
    too_many_handles_text,
)
from ai_rpg_world.being.domain.being_id import BeingId
from ai_rpg_world.being.domain.episode import EpisodeRepository
from ai_rpg_world.being.domain.episode_recall import EpisodeRecallHandles, recall_episodes
from ai_rpg_world.domain.being.exception.being_exceptions import EpisodeRecallLimitExceededException


@dataclass(frozen=True, kw_only=True)
class RecallEpisodesCommand:
    """``arguments`` は思い出すツールに書かれた引数。``turn`` は思い出した記憶のターン。"""

    being_id: BeingId
    arguments: Mapping[str, object]
    turn: int


@dataclass(frozen=True)
class EpisodeRecallAnswer:
    """``body`` は本人に返す文。知らない呼び名は、古い run と同じく、思い出せないと答える成功にする。"""

    body: str
    succeeded: bool


class RecallEpisodes:
    def __init__(self, *, episodes: EpisodeRepository, recall_limit: int) -> None:
        if recall_limit < 1:
            raise ValueError("recall_limit must be >= 1")
        self._episodes = episodes
        self._recall_limit = recall_limit

    def execute(self, command: RecallEpisodesCommand) -> EpisodeRecallAnswer:
        handles = read_handles(command.arguments)
        if handles is None:
            return EpisodeRecallAnswer(MALFORMED_HANDLES_TEXT, succeeded=False)
        try:
            within = EpisodeRecallHandles.within(handles, limit=self._recall_limit)
        except EpisodeRecallLimitExceededException as refusal:
            return EpisodeRecallAnswer(too_many_handles_text(refusal.limit), succeeded=False)
        return EpisodeRecallAnswer(
            recalled_text(recall_episodes(self._episodes, command.being_id, within, turn=command.turn)),
            succeeded=True,
        )


__all__ = ["EpisodeRecallAnswer", "RecallEpisodes", "RecallEpisodesCommand"]
