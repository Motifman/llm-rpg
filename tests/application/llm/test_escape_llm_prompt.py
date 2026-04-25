"""escape_llm_prompt の公開導入文・ペルソナ・時間・行動量の圧表現。"""

from ai_rpg_world.application.llm.services.escape_llm_prompt import (
    EscapeCharacterPromptInput,
    build_escape_system_prompt,
    build_persona_block_from_escape_character,
    limited_action_and_time_pressure_text,
    safe_world_intro_text,
)
from ai_rpg_world.infrastructure.scenario.scenario_loader import ScenarioMetadata


def test_safe_intro_for_abandoned_hospital_avoids_spoiler_keywords() -> None:
    meta = ScenarioMetadata(
        id="abandoned_hospital",
        title="廃病院からの脱出",
        description=(
            "この説明には切除や再編などネタバレ語を含むが、LLM には渡さない。"
        ),
        theme="psychological_horror",
        difficulty="medium",
        estimated_ticks=150,
        author="test",
        tags=(),
    )
    intro = safe_world_intro_text(meta)
    assert "切除" not in intro
    assert "再編" not in intro
    assert "静原" in intro or "廃墟" in intro


def test_limited_action_text_has_no_concrete_count() -> None:
    text = limited_action_and_time_pressure_text()
    assert "ティック" not in text
    assert "150" not in text
    assert "限り" in text or "制限" in text


def test_persona_block_from_escape_character_contains_name() -> None:
    ch = EscapeCharacterPromptInput(
        character_id="abc",
        name="門前の少女",
        first_person="ぼく",
        personality_tags=("内向的",),
        speech_samples=("……。",),
        fragmented_memory="扉の前で立ち尽くしていた記憶だけがある。",
        values="誰かを待つこと",
        strengths="忍耐",
        weaknesses="決断が怖い",
        interpersonal_tendency="距離を取りがち",
        appearance="小柄",
    )
    block = build_persona_block_from_escape_character(
        ch, fallback_display_name="fallback"
    )
    assert "門前の少女" in block
    assert "ぼく" in block
    assert "……。" in block


def test_escape_system_prompt_mentions_user_message_semantics() -> None:
    system = build_escape_system_prompt(
        world_title="テスト廃墟",
        persona_block="【ペルソナ】\n- 名前: X",
        safe_intro="廃墟から出る。",
        participant_names=("X",),
    )
    assert "tool calling" in system or "ツール" in system
    assert "渡される" in system
    assert "観測" in system
    assert "user:" not in system.lower()
    assert "1名しかいない" in system or "他者" in system
