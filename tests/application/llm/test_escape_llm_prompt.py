"""escape_llm_prompt の公開導入文・ペルソナ・時間・行動量の圧表現。"""

from ai_rpg_world.application.llm.services.escape_llm_prompt import (
    EscapeCharacterPromptInput,
    build_escape_system_prompt,
    build_persona_block_from_escape_character,
    limited_action_and_time_pressure_text,
    safe_world_intro_text,
)
from ai_rpg_world.infrastructure.scenario.scenario_loader import ScenarioMetadata


def test_safe_intro_uses_llm_public_intro_and_avoids_spoiler_description() -> None:
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
        llm_public_intro="静原総合病院の廃墟。非ネタバレの探索用導入。",
    )
    intro = safe_world_intro_text(meta)
    assert "切除" not in intro
    assert "再編" not in intro
    assert "静原" in intro or "廃墟" in intro


def test_safe_intro_falls_back_to_default_when_llm_public_intro_empty() -> None:
    meta = ScenarioMetadata(
        id="generic_world",
        title="汎用脱出",
        description="ネタバレだらけの full description。",
        theme="test",
        difficulty="easy",
        estimated_ticks=1,
        author="test",
        tags=(),
        llm_public_intro="",
    )
    intro = safe_world_intro_text(meta)
    assert "静原" not in intro
    assert "脱出" in intro


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


def test_persona_block_includes_behavioral_rules_when_set() -> None:
    ch = EscapeCharacterPromptInput(
        character_id="r1",
        name="試験",
        first_person="私",
        behavioral_rules=("未確認の戸口には手を入れない", "一人で奥へ踏み込まない"),
    )
    block = build_persona_block_from_escape_character(
        ch, fallback_display_name="fallback"
    )
    assert "行動ルール" in block
    assert "未確認の戸口" in block
    assert "踏み込まない" in block


def test_escape_system_prompt_mentions_user_message_semantics() -> None:
    system = build_escape_system_prompt(
        world_title="テスト廃墟",
        persona_block="【ペルソナ】\n- 名前: X",
        safe_intro="廃墟から出る。",
        participant_names=(),
    )
    assert "tool calling" in system or "ツール" in system
    assert "渡される" in system
    assert "観測" in system
    assert "user:" not in system.lower()
    assert "他の探索者はいない" in system
    assert "自己のみ" in system or "他者" in system
    assert "inner_thought" in system
    assert "【ペルソナ】の口調" in system or "口調に揃え" in system
    assert "String Seed of Thought" not in system
    assert "文脈と履歴の限界" in system
    assert "memory_query" in system


def test_escape_system_prompt_includes_ssot_when_enabled() -> None:
    system = build_escape_system_prompt(
        world_title="テスト廃墟",
        persona_block="【ペルソナ】\n- 名前: X",
        safe_intro="廃墟から出る。",
        participant_names=(),
        enable_string_seed_of_thought=True,
    )
    assert "String Seed of Thought" in system
    assert "SSoT" in system
    assert "辞書順" in system
    assert "割った余り" in system


def test_escape_system_prompt_other_explorers_list_and_multiline() -> None:
    system = build_escape_system_prompt(
        world_title="テスト廃墟",
        persona_block="【ペルソナ】\n- 名前: 自分",
        safe_intro="廃墟から出る。",
        participant_names=("相棒",),
    )
    assert "  - 相棒" in system
    assert "同席する他の探索者" in system
    assert "他の探索者はいない" not in system
