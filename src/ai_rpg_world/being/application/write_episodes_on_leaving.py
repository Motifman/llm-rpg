"""環境を離れるときに、短期記憶のまだまとめていない出来事から、Being 本人がエピソードを書いて記憶に加える (#1626、design_decisions D1824-23)。"""

from __future__ import annotations

from dataclasses import dataclass

from ai_rpg_world.being.application.episode_writing import (
    AddEpisodesToMemory,
    AddEpisodesToMemoryCommand,
    EpisodeWritingResult,
)
from ai_rpg_world.being.application.recent_events_text import experience_lines
from ai_rpg_world.being.application.write_episodes import WriteEpisodes, WriteEpisodesCommand
from ai_rpg_world.being.domain.being_id import BeingId
from ai_rpg_world.being.domain.episode_writer import EpisodeWriter
from ai_rpg_world.being.domain.persona import Persona
from ai_rpg_world.being.domain.short_term_memory import ShortTermMemoryRepository


@dataclass(frozen=True)
class WriteEpisodesOnLeavingCommand:
    being_id: BeingId
    persona: Persona
    persona_text: str
    environment_name: str
    written_turn: int


@dataclass(frozen=True)
class EpisodesOnLeaving:
    """``result`` が None なら、まとめていない出来事が行にならず、書き手を呼ばなかった。

    ``awaited_until_turn`` は、まだいきさつを待っている範囲の終わり (待っていなければ None)。その範囲のエピソードは
    範囲が埋まったときに書いているので、ここでは書かない。終わりまでに記憶に入らなかったかを見分けるために返す。
    """

    experience_count: int
    result: EpisodeWritingResult | None
    awaited_until_turn: int | None = None


class WriteEpisodesOnLeaving:
    """範囲が埋まったときに書いた範囲は、二重に書かない。短期記憶は変えない。書けなければ例外を投げる。"""

    def __init__(
        self, store: ShortTermMemoryRepository, writer: EpisodeWriter, add_episodes: AddEpisodesToMemory
    ) -> None:
        self._store = store
        self._write_episodes = WriteEpisodes(writer)
        self._add_episodes = add_episodes

    def execute(self, command: WriteEpisodesOnLeavingCommand) -> EpisodesOnLeaving:
        memory = self._store.get(command.being_id)
        experiences = memory.unsummarized()
        awaited = memory.awaited_backstory
        awaited_until_turn = awaited.until_turn if awaited is not None else None
        if experience_lines(experiences) is None:
            return EpisodesOnLeaving(
                experience_count=len(experiences), result=None, awaited_until_turn=awaited_until_turn
            )
        contents = self._write_episodes.execute(
            WriteEpisodesCommand(
                being_id=command.being_id,
                persona=command.persona,
                persona_text=command.persona_text,
                experiences=experiences,
                environment_name=command.environment_name,
                written_turn=command.written_turn,
            )
        )
        result = self._add_episodes.add(
            AddEpisodesToMemoryCommand(
                being_id=command.being_id,
                contents=contents,
                environment_name=command.environment_name,
                written_turn=command.written_turn,
            )
        )
        return EpisodesOnLeaving(
            experience_count=len(experiences), result=result, awaited_until_turn=awaited_until_turn
        )


__all__ = ["EpisodesOnLeaving", "WriteEpisodesOnLeaving", "WriteEpisodesOnLeavingCommand"]
