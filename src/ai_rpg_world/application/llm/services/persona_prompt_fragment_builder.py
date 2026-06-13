"""Build system-prompt fragments from structured character personas."""

from __future__ import annotations

from ai_rpg_world.domain.persona.value_object.agent_persona_dto import AgentPersonaDto
from ai_rpg_world.domain.persona.value_object.persona_prompt_policy import PersonaPromptPolicy


class PersonaPromptFragmentBuilder:
    """Converts structured persona data into a compact prompt section."""

    def __init__(self, policy: PersonaPromptPolicy | None = None) -> None:
        self._policy = policy or PersonaPromptPolicy()

    def build(self, persona: AgentPersonaDto) -> str:
        if not isinstance(persona, AgentPersonaDto):
            raise TypeError("persona must be AgentPersonaDto")

        lines = [
            "【ペルソナ】",
            f"- あなたは「{persona.display_name}」本人である。「{persona.display_name}」=あなた自身であり、他者ではない。",
            f"- 名前: {persona.display_name}",
            f"- 一人称: {persona.first_person}",
            f"- 話し方: {persona.speech_style}",
        ]
        self._append_text_section(
            lines,
            "背景",
            persona.background_summary,
            self._policy.include_background,
        )
        self._append_list_section(
            lines,
            "性格傾向",
            persona.personality_traits,
            self._policy.include_traits,
        )
        self._append_list_section(
            lines,
            "価値観",
            persona.values,
            self._policy.include_values,
        )
        self._append_list_section(lines, "恐れ", persona.fears, self._policy.include_fears)
        self._append_list_section(
            lines,
            "禁忌",
            persona.taboos,
            self._policy.include_taboos,
        )
        self._append_list_section(
            lines,
            "断片記憶",
            persona.fragmented_memories,
            self._policy.include_fragmented_memories,
        )
        self._append_list_section(
            lines,
            "行動ルール",
            persona.behavioral_rules,
            self._policy.include_behavioral_rules,
        )
        self._append_list_section(
            lines,
            "関係性の手がかり",
            persona.relationship_hints,
            self._policy.include_relationship_hints,
        )
        return "\n".join(lines).strip()

    def _append_text_section(
        self,
        lines: list[str],
        title: str,
        text: str,
        enabled: bool,
    ) -> None:
        if enabled and text:
            lines.append(f"- {title}: {text}")

    def _append_list_section(
        self,
        lines: list[str],
        title: str,
        values: tuple[str, ...],
        enabled: bool,
    ) -> None:
        if not enabled or not values:
            return
        selected = values[: self._policy.max_items_per_section]
        lines.append(f"- {title}:")
        for value in selected:
            lines.append(f"  - {value}")
