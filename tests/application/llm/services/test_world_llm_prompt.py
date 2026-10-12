"""世界の住人に渡す system prompt がエンジンの実装事情を語らないことを保証する。"""

from __future__ import annotations

import pytest

from ai_rpg_world.application.llm.services.world_llm_prompt import (
    build_world_system_prompt,
)

BANNED_ENGINE_VOCABULARY = ("LLM", "関数呼び出し", "サーバー", "全キャラクター共通")


def _build_prompt(
    *,
    tool_schema_mode: str = "legacy",
    expected_result_policy: str = "off",
    enable_string_seed_of_thought: bool = False,
) -> str:
    return build_world_system_prompt(
        relevant_memories_shown=True,
        active_recall_offered=True,
        world_title="テスト世界",
        persona_block="【ペルソナ】名前: エイダ",
        safe_intro="周囲を観察しながら暮らす世界。",
        tool_schema_mode=tool_schema_mode,
        expected_result_policy=expected_result_policy,
        enable_string_seed_of_thought=enable_string_seed_of_thought,
    )


def test_action_rules_drop_engine_vocabulary_without_adding_meaning() -> None:
    """行動ルールから実装注記だけを除き、世界内で必要な制約は短い文面で残す。"""
    prompt = _build_prompt()

    expected_wording = (
        "【行動ルール】",
        "- 世界と相互作用する唯一の手段は、tool call である。",
        "- 1 回の応答で選べる tool は 1 つだけである。",
    )
    removed_wording = (
        "【行動ルール（全キャラクター共通）】",
        "- 世界と相互作用する唯一の手段は、LLM への tool calling（関数呼び出し）である。",
        "- 1回の応答で選べるのは 1 つのツールだけとする（サーバーは先頭の tool_call だけを実行しうる。必ず 1 つに絞る）。",
        "（自身の識別は上記【ペルソナ】の名前。シナリオに応じて複数）",
    )

    for wording in expected_wording:
        assert wording in prompt
    for wording in removed_wording:
        assert wording not in prompt


@pytest.mark.parametrize("tool_schema_mode", ("legacy", "reason_first"))
@pytest.mark.parametrize("expected_result_policy", ("off", "optional", "required"))
@pytest.mark.parametrize("enable_string_seed_of_thought", (False, True))
def test_system_prompt_never_exposes_banned_engine_vocabulary(
    tool_schema_mode: str,
    expected_result_policy: str,
    enable_string_seed_of_thought: bool,
) -> None:
    """どの生成分岐でもエンジンの実装事情を世界の住人に見せない。"""
    prompt = _build_prompt(
        tool_schema_mode=tool_schema_mode,
        expected_result_policy=expected_result_policy,
        enable_string_seed_of_thought=enable_string_seed_of_thought,
    )

    for vocabulary in BANNED_ENGINE_VOCABULARY:
        assert vocabulary not in prompt


def _build_with_persona(persona_block: str) -> str:
    return build_world_system_prompt(
        relevant_memories_shown=True,
        active_recall_offered=True,
        world_title="テスト世界",
        persona_block=persona_block,
        safe_intro="周囲を観察しながら暮らす世界。",
    )


def test_scenario_persona_text_without_heading_is_placed_under_the_persona_heading() -> None:
    """シナリオの persona_prompt のように見出しの無い人物像を渡すと、【ペルソナ】の見出しの下に置かれ、本文の「上記【ペルソナ】」が実在する見出しを指す。"""
    persona_text = "あなたはエイダ、40代の医師。\n\n話し方: 落ち着いた敬体。"

    prompt = _build_with_persona(persona_text)

    assert prompt.count("\n【ペルソナ】\n") == 1
    assert prompt.index("【ペルソナ】\n") < prompt.index(persona_text)


def test_persona_block_that_already_has_the_heading_is_not_given_a_second_one() -> None:
    """人物像の組み立て部品が作る【ペルソナ】始まりの節は、見出しを重ねずにそのまま置かれる。"""
    persona_block = "【ペルソナ】\n- 名前: エイダ"

    prompt = _build_with_persona(persona_block)

    assert prompt.count("【ペルソナ】\n") == 1
    assert persona_block in prompt


def test_system_prompt_does_not_list_who_is_known() -> None:
    """system prompt には誰を知っているかの節を置かない。知り合いが増えるたびに system prompt が変わらないようにする。"""
    prompt = _build_prompt()

    assert "【同じ局面にいる者】" not in prompt
    assert "【知っている人】" not in prompt
