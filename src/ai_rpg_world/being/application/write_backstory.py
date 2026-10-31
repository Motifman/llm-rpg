"""短期記憶の範囲のいきさつを書く (#1824、design_decisions D1824-18)。"""

from __future__ import annotations

from dataclasses import dataclass

from ai_rpg_world.being.domain.backstory_writer import BackstoryWriter
from ai_rpg_world.being.domain.short_term_memory import Backstory, Experience
from ai_rpg_world.domain.being.value_object.being_id import BeingId


@dataclass(frozen=True)
class WriteBackstoryCommand:
    """``experiences`` (``until_turn`` までの出来事、``recent()`` と同じ順) を、``previous`` に続くいきさつにまとめる。"""

    being_id: BeingId
    self_name: str
    persona: str
    experiences: tuple[Experience, ...]
    previous: Backstory | None
    until_turn: int
    written_turn: int


class WriteBackstory:
    """記憶には触らない。書けなければ例外を投げる。"""

    def __init__(self, writer: BackstoryWriter) -> None:
        self._writer = writer

    def execute(self, command: WriteBackstoryCommand) -> Backstory:
        return self._writer.write(
            self_name=command.self_name,
            persona=command.persona,
            experiences=command.experiences,
            previous=command.previous,
            until_turn=command.until_turn,
            written_turn=command.written_turn,
        )


__all__ = ["WriteBackstory", "WriteBackstoryCommand"]
