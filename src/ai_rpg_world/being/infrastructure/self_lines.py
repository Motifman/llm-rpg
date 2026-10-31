"""いきさつとエピソードの書き手に、自分が誰かを伝える行 (design_decisions D1469-2)。"""

from __future__ import annotations

from ai_rpg_world.being.domain.persona import Persona


def self_lines(persona: Persona) -> list[str]:
    """一人称が決まっていなければ、一人称の行を出さない。仮の一人称を書かせないため。"""
    lines = [f"あなた = {persona.name}"]
    if persona.first_person is not None:
        lines.append(f"あなたの一人称 = {persona.first_person}")
    return lines


__all__ = ["self_lines"]
