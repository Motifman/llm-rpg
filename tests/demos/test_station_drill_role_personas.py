"""station_drill の人物像と役職共通知識が構造として分離されることを保証する。"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


_DRILL = (
    Path(__file__).resolve().parents[2] / "data" / "scenarios" / "station_drill.json"
)


def _raw() -> dict:
    return json.loads(_DRILL.read_text(encoding="utf-8"))


def _players_by_role(runtime, role: str) -> tuple[PlayerId, ...]:
    return tuple(
        PlayerId(spawn.player_id)
        for spawn in runtime.scenario.player_spawns
        if spawn.initial_state.get("role") == role
    )


def test_each_crew_system_joins_its_person_and_the_identical_role_text() -> None:
    """クルー六人の system は各人物文の後ろに、同じ一つの crew 共通文を連結する。"""
    raw = _raw()
    runtime = create_world_runtime(_DRILL)
    crew_role = raw["role_personas"]["crew"]
    individual_by_id = {
        player["id"]: player["persona_prompt"] for player in raw["players"]
    }

    for spawn in runtime.scenario.player_spawns:
        if spawn.initial_state.get("role") != "crew":
            continue
        system = runtime._world_llm_system_prompts_by_player_id[spawn.player_id]
        individual = individual_by_id[spawn.string_id]
        assert f"{individual}\n\n{crew_role}" in system
        assert system.count(crew_role) == 1


def test_each_impostor_system_receives_the_same_role_facts_after_personal_text() -> None:
    """インポスター二人も人物文の後ろに同一の keeper 共通知識を一度だけ受け取る。"""
    raw = _raw()
    runtime = create_world_runtime(_DRILL)
    keeper_role = raw["role_personas"]["keeper"]
    individual_by_id = {
        player["id"]: player["persona_prompt"] for player in raw["players"]
    }

    for spawn in runtime.scenario.player_spawns:
        if spawn.initial_state.get("role") != "keeper":
            continue
        system = runtime._world_llm_system_prompts_by_player_id[spawn.player_id]
        assert f"{individual_by_id[spawn.string_id]}\n\n{keeper_role}" in system
        assert system.count(keeper_role) == 1


def test_system_prompt_hashes_are_stable_across_runtime_reconstruction() -> None:
    """同じシナリオから run を組み直しても八人の system prompt sha256 は変わらない。"""
    first = create_world_runtime(_DRILL)
    second = create_world_runtime(_DRILL)

    def hashes(runtime) -> dict[int, str]:
        return {
            player_id: hashlib.sha256(prompt.encode("utf-8")).hexdigest()
            for player_id, prompt in runtime._world_llm_system_prompts_by_player_id.items()
        }

    assert hashes(first) == hashes(second)


def test_role_personas_match_the_equivalent_legacy_expanded_personas(
    tmp_path: Path,
) -> None:
    """役職文を人物文へ展開した旧形式は、新形式と八人の system がバイト単位で一致する。"""
    raw = _raw()
    role_personas = raw.pop("role_personas")
    for player in raw["players"]:
        role = player["initial_state"]["role"]
        player["persona_prompt"] = (
            f"{player['persona_prompt']}\n\n{role_personas[role]}"
        )
    legacy_path = tmp_path / "station_drill_expanded_personas.json"
    legacy_path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")

    structured = create_world_runtime(_DRILL)
    legacy = create_world_runtime(legacy_path)

    assert structured._world_llm_system_prompts_by_player_id == (
        legacy._world_llm_system_prompts_by_player_id
    )


def test_persona_join_does_not_depend_on_current_items_or_world_tick() -> None:
    """役職文の連結は現在の持ち物や tick を見ず、run 中に八人の system hash を変えない。"""
    runtime = create_world_runtime(_DRILL)
    before = dict(runtime._world_llm_system_prompts_by_player_id)

    runtime.advance_tick()

    assert runtime._world_llm_system_prompts_by_player_id == before


def test_role_knowledge_does_not_leak_across_roles() -> None:
    """crew と keeper の共通知識は対応する役職だけへ入り、逆側へ混ざらない。"""
    raw = _raw()
    runtime = create_world_runtime(_DRILL)
    crew_role = raw["role_personas"]["crew"]
    keeper_role = raw["role_personas"]["keeper"]

    for player_id in _players_by_role(runtime, "crew"):
        system = runtime._world_llm_system_prompts_by_player_id[int(player_id)]
        assert crew_role in system
        assert keeper_role not in system
    for player_id in _players_by_role(runtime, "keeper"):
        system = runtime._world_llm_system_prompts_by_player_id[int(player_id)]
        assert keeper_role in system
        assert crew_role not in system
