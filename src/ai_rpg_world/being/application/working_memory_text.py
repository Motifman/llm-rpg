"""作業記憶 (#1630) を、システムプロンプトと毎ターンのメッセージの文にする。"""

from __future__ import annotations

from ai_rpg_world.being.domain.working_memory import Section, WorkingMemory


def section_text(section: Section) -> str:
    body = "\n".join(section.lines)
    return f"【{section.heading}】\n{body}" if section.heading is not None else body


def system_prompt_text(memory: WorkingMemory) -> str:
    return "\n\n".join(section_text(s) for s in memory.system)


def message_text(memory: WorkingMemory) -> str:
    """区画、繰り返しの警告、知らせ、締めの一文の順に、空行で区切って並べる。"""
    return "\n\n".join(p for p in ("\n\n".join(section_text(s) for s in memory.message), closing_text(memory)) if p)


def closing_text(memory: WorkingMemory) -> str:
    """メッセージのうち区画より後ろ (繰り返しの警告、知らせ、締めの一文) の文。"""
    parts: list[str] = []
    if memory.closing is not None and memory.closing.warning:
        parts.append(memory.closing.warning)
    parts.extend(section_text(s) for s in memory.notices)
    if memory.closing is not None:
        parts.append(memory.closing.instruction)
    return "\n\n".join(parts)


__all__ = ["closing_text", "message_text", "section_text", "system_prompt_text"]
