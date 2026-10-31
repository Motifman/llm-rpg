"""Being 本人が書いたエピソードの中身に、ID と呼び名を付け、エピソードとして記憶に加える。

中身を書くのは、ドメインに置く抽象クラス ``EpisodeWriter``。どこで区切って書かせるかは呼ぶ側が決める。
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass, field

from ai_rpg_world.being.domain.episode import Episode, EpisodeRepository
from ai_rpg_world.being.domain.episode_writer import EpisodeContents
from ai_rpg_world.domain.being.value_object.being_id import BeingId


@dataclass(frozen=True)
class WrittenEpisode:
    """``truncated`` は切り詰めた項目 (応答の鍵の名前) と、切り詰める前の長さ。"""

    episode: Episode
    truncated: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True)
class AddEpisodesToMemoryCommand:
    being_id: BeingId
    contents: EpisodeContents
    environment_name: str
    written_turn: int


@dataclass(frozen=True)
class EpisodeWritingResult:
    written: tuple[WrittenEpisode, ...]
    dropped_count: int = 0
    rewritten: bool = False


class AddEpisodesToMemory:
    """呼び名を決めるのに Being の保存先を読むので、保存先に書く人と同じスレッドで呼ぶ。"""

    def __init__(
        self,
        repository: EpisodeRepository,
        *,
        new_episode_id: Callable[[], str] = lambda: str(uuid.uuid4()),
    ) -> None:
        self._repository = repository
        self._new_episode_id = new_episode_id

    def add(self, command: AddEpisodesToMemoryCommand) -> EpisodeWritingResult:
        being_id, contents = command.being_id, command.contents
        taken = {e.handle for e in self._repository.list_by_being(being_id)}
        written: list[WrittenEpisode] = []
        for content in contents.contents:
            episode = Episode.write(
                being_id=being_id,
                episode_id=self._new_episode_id(),
                environment_name=command.environment_name,
                written_turn=command.written_turn,
                index=content.index,
                body=content.body,
                taken_handles=taken,
                truncated=content.truncated,
                rewritten=contents.rewritten,
            )
            taken.add(episode.handle)
            written.append(WrittenEpisode(episode=episode, truncated=content.truncated))
        for w in written:
            self._repository.add(w.episode)
        return EpisodeWritingResult(
            written=tuple(written), dropped_count=contents.dropped_count, rewritten=contents.rewritten
        )


__all__ = ["AddEpisodesToMemory", "AddEpisodesToMemoryCommand", "EpisodeWritingResult", "WrittenEpisode"]
