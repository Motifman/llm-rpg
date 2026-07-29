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
    participant_names: tuple[str, ...] = (),
    enable_string_seed_of_thought: bool = False,
) -> str:
    return build_world_system_prompt(
        world_title="テスト世界",
        persona_block="【ペルソナ】名前: エイダ",
        safe_intro="周囲を観察しながら暮らす世界。",
        participant_names=participant_names,
        tool_schema_mode=tool_schema_mode,
        expected_result_policy=expected_result_policy,
        enable_string_seed_of_thought=enable_string_seed_of_thought,
    )


def test_action_rules_drop_engine_vocabulary_without_adding_meaning() -> None:
    """行動ルールと参加者説明から実装注記だけを除き、世界内で必要な制約は短い文面で残す。"""
    prompt = _build_prompt(participant_names=("ノア",))

    expected_wording = (
        "【行動ルール】",
        "- 世界と相互作用する唯一の手段は、tool call である。",
        "- 1 回の応答で選べる tool は 1 つだけである。",
        "（自身の識別は上記【ペルソナ】の名前）",
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
@pytest.mark.parametrize("participant_names", ((), ("ノア",)))
@pytest.mark.parametrize("enable_string_seed_of_thought", (False, True))
def test_system_prompt_never_exposes_banned_engine_vocabulary(
    tool_schema_mode: str,
    expected_result_policy: str,
    participant_names: tuple[str, ...],
    enable_string_seed_of_thought: bool,
) -> None:
    """どの生成分岐でもエンジンの実装事情を世界の住人に見せない。"""
    prompt = _build_prompt(
        tool_schema_mode=tool_schema_mode,
        expected_result_policy=expected_result_policy,
        participant_names=participant_names,
        enable_string_seed_of_thought=enable_string_seed_of_thought,
    )

    for vocabulary in BANNED_ENGINE_VOCABULARY:
        assert vocabulary not in prompt
