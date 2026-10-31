"""起動時に用意する Being の人柄に、シナリオのプレイヤーの名前が入ることを保証する (design_decisions D1469-1)。"""

from __future__ import annotations

import json
from pathlib import Path

from ai_rpg_world.application.llm.wiring.resolved_runtime_config import ResolvedLlmRuntimeConfig
from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime
from ai_rpg_world.being.domain.persona import Persona

_SCENARIO = Path(__file__).resolve().parents[3] / "data" / "scenarios" / "mine_village_v1.json"


def test_each_player_being_is_named_after_the_scenario_player() -> None:
    """各プレイヤーの Being は、シナリオの players[].name を名前に持ち、シナリオに無い一人称などは決めない。"""
    runtime = create_world_runtime(_SCENARIO, config=ResolvedLlmRuntimeConfig.for_tests())
    names = [player["name"] for player in json.loads(_SCENARIO.read_text(encoding="utf-8"))["players"]]

    personas = []
    for player_id in runtime.get_player_ids():
        being_id = runtime._aux_being_resolver.resolve_being_id(runtime._aux_being_default_world_id, player_id)
        personas.append(runtime._aux_being_repository.find_by_id(being_id).persona)

    assert sorted(personas, key=lambda p: p.name) == sorted(
        (Persona(name=name) for name in names), key=lambda p: p.name
    )
