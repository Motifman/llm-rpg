"""短期記憶の範囲の出来事から、Being 本人がエピソードの中身を書く (#1824、design_decisions D1824-19)。"""

from __future__ import annotations

from dataclasses import dataclass

from ai_rpg_world.being.application.recent_events_text import experience_lines
from ai_rpg_world.being.domain.episode_writer import EpisodeContents, EpisodeWriter
from ai_rpg_world.being.domain.short_term_memory import Experience
from ai_rpg_world.domain.being.value_object.being_id import BeingId


@dataclass(frozen=True)
class WriteEpisodesCommand:
    """``experiences`` はまとめる範囲の出来事 (``recent()`` と同じ順)。``environment_name`` は記憶に加えるときにだけ使い、書き手には渡さない。"""

    being_id: BeingId
    self_name: str
    persona: str
    experiences: tuple[Experience, ...]
    environment_name: str
    written_turn: int


class WriteEpisodes:
    """記憶には触らない。書けなければ例外を投げる。"""

    def __init__(self, writer: EpisodeWriter) -> None:
        self._writer = writer

    def execute(self, command: WriteEpisodesCommand) -> EpisodeContents:
        """出来事が行にならない (結果の来ない 1 手だけの) 範囲は、書き手を呼ばずに中身無しを返す。"""
        events_text = experience_lines(command.experiences)
        if events_text is None:
            return EpisodeContents(contents=())
        return self._writer.write(self_name=command.self_name, persona=command.persona, events_text=events_text)


__all__ = ["WriteEpisodes", "WriteEpisodesCommand"]
