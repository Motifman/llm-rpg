"""Structured persona DTOs for LLM-controlled characters."""

from __future__ import annotations

from dataclasses import dataclass


def _ensure_str_tuple(name: str, values: tuple[str, ...]) -> None:
    if not isinstance(values, tuple):
        raise TypeError(f"{name} must be tuple")
    for value in values:
        if not isinstance(value, str):
            raise TypeError(f"{name} must contain only str")


@dataclass(frozen=True)
class AgentPersonaDto:
    """Narrative persona information converted into prompt fragments."""

    character_id: str
    display_name: str
    first_person: str
    speech_style: str
    personality_traits: tuple[str, ...] = ()
    values: tuple[str, ...] = ()
    fears: tuple[str, ...] = ()
    taboos: tuple[str, ...] = ()
    background_summary: str = ""
    fragmented_memories: tuple[str, ...] = ()
    behavioral_rules: tuple[str, ...] = ()
    relationship_hints: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for name in ("character_id", "display_name", "first_person", "speech_style"):
            if not isinstance(getattr(self, name), str):
                raise TypeError(f"{name} must be str")
        if not isinstance(self.background_summary, str):
            raise TypeError("background_summary must be str")
        _ensure_str_tuple("personality_traits", self.personality_traits)
        _ensure_str_tuple("values", self.values)
        _ensure_str_tuple("fears", self.fears)
        _ensure_str_tuple("taboos", self.taboos)
        _ensure_str_tuple("fragmented_memories", self.fragmented_memories)
        _ensure_str_tuple("behavioral_rules", self.behavioral_rules)
        _ensure_str_tuple("relationship_hints", self.relationship_hints)


@dataclass(frozen=True)
class PersonaPromptPolicy:
    """Controls which persona sections are rendered into the system prompt."""

    include_background: bool = True
    include_traits: bool = True
    include_values: bool = True
    include_fears: bool = True
    include_taboos: bool = True
    include_fragmented_memories: bool = True
    include_behavioral_rules: bool = True
    include_relationship_hints: bool = True
    max_items_per_section: int = 6

    def __post_init__(self) -> None:
        for name in (
            "include_background",
            "include_traits",
            "include_values",
            "include_fears",
            "include_taboos",
            "include_fragmented_memories",
            "include_behavioral_rules",
            "include_relationship_hints",
        ):
            if not isinstance(getattr(self, name), bool):
                raise TypeError(f"{name} must be bool")
        if not isinstance(self.max_items_per_section, int):
            raise TypeError("max_items_per_section must be int")
        if self.max_items_per_section < 1:
            raise ValueError("max_items_per_section must be positive")
