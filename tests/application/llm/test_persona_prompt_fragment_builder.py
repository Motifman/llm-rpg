import pytest

from ai_rpg_world.domain.persona.value_object.agent_persona_dto import AgentPersonaDto
from ai_rpg_world.domain.persona.value_object.persona_prompt_policy import PersonaPromptPolicy
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


def test_persona_prompt_fragment_includes_self_identification_line() -> None:
    """ペルソナブロック冒頭に「あなた=ペルソナ本人」の自認行が含まれる。

    LLM が自分の名前を「他者の呼称」として使ってしまう (例: リン自身がリン
    に呼びかける) 振る舞いの抑止が目的。ルールではなく簡潔な自認文として
    入れる。
    """
    persona = AgentPersonaDto(
        character_id="rin",
        display_name="リン",
        first_person="わたし",
        speech_style="落ち着いた口調",
    )

    text = PersonaPromptFragmentBuilder().build(persona)

    assert "あなたは「リン」本人である" in text
    assert "「リン」=あなた自身" in text


def test_persona_prompt_builder_rejects_invalid_persona() -> None:
    with pytest.raises(TypeError, match="persona must be AgentPersonaDto"):
        PersonaPromptFragmentBuilder().build("not persona")  # type: ignore[arg-type]
