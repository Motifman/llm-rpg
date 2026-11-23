"""LLM を呼ばず、範囲の出来事の件数だけを書いたいきさつを返す。"""

from __future__ import annotations

from ai_rpg_world.being.domain.backstory_writer import BackstoryWriter, WrittenBackstory
from ai_rpg_world.being.domain.persona import Persona
from ai_rpg_world.being.domain.short_term_memory import Backstory, Experience


class ScriptedBackstoryWriter(BackstoryWriter):
    def __init__(self) -> None:
        self.written: list[int] = []

    def write(
        self,
        *,
        persona: Persona,
        persona_text: str,
        experiences: tuple[Experience, ...],
        previous: Backstory | None,
        until_turn: int,
        written_turn: int,
    ) -> WrittenBackstory:
        self.written.append(until_turn)
        return WrittenBackstory(
            backstory=Backstory(
                flow=f"{persona.name}が {len(experiences)} 件の出来事を過ごした",
                mood="",
                written_turn=written_turn,
                until_turn=until_turn,
            )
        )


__all__ = ["ScriptedBackstoryWriter"]
