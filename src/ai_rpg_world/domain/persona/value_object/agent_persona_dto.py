"""AgentPersonaDto — LLM agent の人格情報 (narrative persona) を保持する Value Object。

DDD 再編 (Issue #470 Phase 1 PR4): 元 ``application/llm/contracts/persona.py``
から domain に昇格。

K run (PR #466) で persona drift ゼロを 140 tick 維持できた背景には、本 VO の
不変性 (frozen + post_init validation) と prompt_fragment_builder の persona
section 設計がある。本 PR は構造的な「住まい」を整える純粋移動 (動作変化なし)。
"""

from __future__ import annotations

from dataclasses import dataclass

from ai_rpg_world.domain.persona.value_object._validators import ensure_str_tuple


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
        ensure_str_tuple("personality_traits", self.personality_traits)
        ensure_str_tuple("values", self.values)
        ensure_str_tuple("fears", self.fears)
        ensure_str_tuple("taboos", self.taboos)
        ensure_str_tuple("fragmented_memories", self.fragmented_memories)
        ensure_str_tuple("behavioral_rules", self.behavioral_rules)
        ensure_str_tuple("relationship_hints", self.relationship_hints)


__all__ = ["AgentPersonaDto"]
