"""【ペルソナ】の文。人柄と、いまいる環境で知っていることを並べる (#2267)。"""

from __future__ import annotations

from collections.abc import Iterable

from ai_rpg_world.being.domain.persona import Persona

PERSONA_HEADING = "ペルソナ"


def persona_text(persona: Persona, known_facts: str | None) -> str:
    who = f"あなたは{persona.name}" + (f"、{_bare(persona.background)}" if persona.background else "") + "。"
    character = [who + "".join(f"{_bare(t)}。" for t in persona.traits)]
    if persona.values:
        character.append(f"大事にしていること: {_listed(persona.values)}。")
    if persona.fears:
        character.append(f"苦手なこと: {_listed(persona.fears)}。")
    speech = (f"話し方: {_bare(persona.speech)}。" if persona.speech else "") + (
        f"一人称は「{persona.first_person}」。" if persona.first_person else ""
    )
    paragraphs = ("\n".join(character), known_facts or "", speech)
    return "\n\n".join(p for p in paragraphs if p)


def _bare(text: str) -> str:
    return text.rstrip("。")


def _listed(texts: Iterable[str]) -> str:
    return "、".join(_bare(t) for t in texts)


__all__ = ["PERSONA_HEADING", "persona_text"]
