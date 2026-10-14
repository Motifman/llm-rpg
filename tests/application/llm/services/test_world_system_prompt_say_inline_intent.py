"""world system prompt が、行動に添える一言を結果ではなく意図として書くよう頼むことを保証する。"""

import pytest

from ai_rpg_world.application.llm.services.world_llm_prompt import (
    build_world_system_prompt,
)


def _say_inline_guidance_line(prompt: str) -> str:
    section = prompt.split("\n【独白と一言の書き方】\n", 1)[1].split("\n\n", 1)[0]
    lines = [line for line in section.splitlines() if "`say_inline`" in line]
    assert len(lines) == 1
    return lines[0]


@pytest.mark.parametrize("tool_schema_mode", ["legacy", "reason_first"])
def test_say_inline_guidance_asks_for_intent_not_result(tool_schema_mode: str) -> None:
    """【独白と一言の書き方】の一言の項は、行動の結果ではなくこれから何をするかを言うよう頼み、
    結果は次の観測で分かると理由を添える。mine_v1_005 T35 で、断られた取得に
    「見つけました」と添えて相手に届いた先取りを防ぐため (#1612)。"""
    prompt = build_world_system_prompt(
        relevant_memories_shown=True,
        world_title="廃坑の山村",
        persona_block="名前: サヨ",
        safe_intro="掘り場にいる。",
        tool_schema_mode=tool_schema_mode,
    )

    line = _say_inline_guidance_line(prompt)

    assert "行動の結果ではなく、これから何をするかを言う" in line
    assert "結果は次の観測で分かる" in line
