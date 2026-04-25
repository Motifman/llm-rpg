import pytest

from ai_rpg_world.application.llm.contracts.persona import (
    AgentPersonaDto,
    PersonaPromptPolicy,
)
from ai_rpg_world.application.llm.services.persona_prompt_fragment_builder import (
    PersonaPromptFragmentBuilder,
)


def test_persona_prompt_fragment_includes_enabled_sections() -> None:
    persona = AgentPersonaDto(
        character_id="gate_girl",
        display_name="門前の少女",
        first_person="わたし",
        speech_style="静かで短い言葉を使う",
        personality_traits=("控えめ", "不安を隠す"),
        values=("相手を置いていかない",),
        fears=("忘れられること",),
        taboos=("自分が本物ではないと断定しない",),
        background_summary="門の前に立っている少女。",
        fragmented_memories=("白い廊下", "誰かの名前を呼んだ感覚"),
        behavioral_rules=("分からないことは分からないと言う",),
        relationship_hints=("ユーザーの声を知らない声として受け取る",),
    )

    text = PersonaPromptFragmentBuilder().build(persona)

    assert "【ペルソナ】" in text
    assert "門前の少女" in text
    assert "わたし" in text
    assert "白い廊下" in text
    assert "自分が本物ではないと断定しない" in text


def test_persona_prompt_policy_can_omit_memory_sections() -> None:
    persona = AgentPersonaDto(
        character_id="gate_girl",
        display_name="門前の少女",
        first_person="わたし",
        speech_style="静か",
        fragmented_memories=("白い廊下",),
    )
    policy = PersonaPromptPolicy(include_fragmented_memories=False)

    text = PersonaPromptFragmentBuilder(policy).build(persona)

    assert "門前の少女" in text
    assert "白い廊下" not in text


def test_persona_prompt_builder_rejects_invalid_persona() -> None:
    with pytest.raises(TypeError, match="persona must be AgentPersonaDto"):
        PersonaPromptFragmentBuilder().build("not persona")  # type: ignore[arg-type]
