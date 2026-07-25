"""world system prompt の行動選択ルールを保証する。"""

from ai_rpg_world.application.llm.services.world_llm_prompt import (
    build_world_system_prompt,
)


def test_system_prompt_tells_agent_to_choose_displayed_object_actions() -> None:
    """条件で拒否されうるため、表示された操作から選ぶ規約を system prompt に含める。"""
    prompt = build_world_system_prompt(
        world_title="島",
        persona_block="名前: エイダ",
        safe_intro="浜辺にいる。",
        participant_names=("ノア",),
    )

    assert "行動は条件を満たさないと拒否されることがある" in prompt
    assert "各オブジェクトに表示された操作の中から選ぶ" in prompt
