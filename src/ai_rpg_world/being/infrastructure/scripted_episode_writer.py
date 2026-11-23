"""LLM を呼ばず、範囲ごとに決めた件数のエピソードを書く。"""

from __future__ import annotations

from ai_rpg_world.being.domain.episode import BODY_MAX_LENGTH, EpisodeIndex
from ai_rpg_world.being.domain.episode_writer import EpisodeContent, EpisodeContents, EpisodeWriter
from ai_rpg_world.being.domain.persona import Persona


class ScriptedEpisodeWriter(EpisodeWriter):
    """書くたびに「<名前>の記憶 N」を 1 件書き、渡された出来事の文と人格の文を覚える。本文は出来事の文の頭を本文の上限まで写す。"""

    def __init__(self) -> None:
        self.written: list[tuple[str, str]] = []

    def write(self, *, persona: Persona, persona_text: str, events_text: str) -> EpisodeContents:
        self.written.append((persona_text, events_text))
        summary = f"{persona.name}の記憶 {len(self.written)}"
        return EpisodeContents(
            contents=(
                EpisodeContent(
                    index=EpisodeIndex(summary=summary, recall_when="思い出したいとき"),
                    body=events_text[:BODY_MAX_LENGTH],
                ),
            )
        )


__all__ = ["ScriptedEpisodeWriter"]
