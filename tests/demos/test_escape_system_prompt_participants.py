"""脱出ランタイムの system prompt 用「同局面の他者」名の組み立て。"""

from __future__ import annotations

from ai_rpg_world.application.llm.services.escape_llm_prompt import EscapeCharacterPromptInput
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.infrastructure.scenario.scenario_loader import PlayerSpawnConfig


def test_other_explorer_names_excludes_controlled_character_id() -> None:
    from demos.escape_game.escape_game_runtime import _other_explorer_names_for_escape_system_prompt

    spot = SpotId.create(1)
    me = PlayerSpawnConfig(
        string_id="p_a",
        player_id=1,
        name="門前",
        spawn_spot_id=spot,
        initial_items=(),
    )
    other = PlayerSpawnConfig(
        string_id="p_b",
        player_id=2,
        name="相棒",
        spawn_spot_id=spot,
        initial_items=(),
    )
    ch = EscapeCharacterPromptInput(character_id="p_a", name="門前", first_person="私")
    assert _other_explorer_names_for_escape_system_prompt((me, other), ch) == ("相棒",)
    assert _other_explorer_names_for_escape_system_prompt((me,), ch) == ()


def test_other_explorer_names_falls_back_first_spawn_without_character() -> None:
    from demos.escape_game.escape_game_runtime import _other_explorer_names_for_escape_system_prompt

    spot = SpotId.create(1)
    a = PlayerSpawnConfig(
        string_id="a",
        player_id=1,
        name="一人目",
        spawn_spot_id=spot,
        initial_items=(),
    )
    b = PlayerSpawnConfig(
        string_id="b",
        player_id=2,
        name="二人目",
        spawn_spot_id=spot,
        initial_items=(),
    )
    assert _other_explorer_names_for_escape_system_prompt((a, b), None) == ("二人目",)
