"""起動時に用意する Being の人柄にシナリオのプレイヤーの名前が入り、書き手がその人柄を使うことを保証する (design_decisions D1469-1、D1469-2)。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from ai_rpg_world.application.llm.services.stub_episode_writing_completion import StubEpisodeWritingCompletion
from ai_rpg_world.application.llm.wiring.resolved_runtime_config import ResolvedLlmRuntimeConfig
from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime
from ai_rpg_world.being.contract import UNKNOWN, Observation, ObservedTime, SeenOrHeard
from ai_rpg_world.being.domain.being import Being
from ai_rpg_world.being.domain.persona import Persona

_SCENARIO = Path(__file__).resolve().parents[3] / "data" / "scenarios" / "mine_village_v1.json"


def test_each_player_being_is_named_after_the_scenario_player() -> None:
    """各プレイヤーの Being は、シナリオの players[].name を名前に、players[].first_person を一人称に持つ。"""
    runtime = create_world_runtime(_SCENARIO, config=ResolvedLlmRuntimeConfig.for_tests())
    players = json.loads(_SCENARIO.read_text(encoding="utf-8"))["players"]
    expected = [Persona(name=player["name"], first_person=player["first_person"]) for player in players]

    personas = []
    for player_id in runtime.get_player_ids():
        being_id = runtime._aux_being_resolver.resolve_being_id(runtime._aux_being_default_world_id, player_id)
        personas.append(runtime._aux_being_repository.find_by_id(being_id).persona)

    assert sorted(personas, key=lambda p: p.name) == sorted(expected, key=lambda p: p.name)


def test_leaving_writer_is_told_the_name_and_first_person_of_the_being(monkeypatch: pytest.MonkeyPatch) -> None:
    """離れるときの書き起こしでは、Being の保存先にある人柄の名前と一人称を、書き手への文の先頭に入れる。"""
    sent: list[list[dict[str, Any]]] = []
    original = StubEpisodeWritingCompletion.complete_episode_writing_json

    def _capture(self: StubEpisodeWritingCompletion, messages: list[dict[str, Any]]) -> dict[str, Any]:
        sent.append(messages)
        return original(self, messages)

    monkeypatch.setattr(StubEpisodeWritingCompletion, "complete_episode_writing_json", _capture)
    runtime = create_world_runtime(_SCENARIO, config=ResolvedLlmRuntimeConfig.for_tests())
    player_id = runtime.get_player_ids()[0]
    being_id = runtime._aux_being_resolver.resolve_being_id(runtime._aux_being_default_world_id, player_id)
    being = runtime._aux_being_repository.find_by_id(being_id)
    runtime._aux_being_repository.save(
        Being(being_id=being_id, persona=Persona(name="ゲン", first_person="俺"), attachment=being.attachment)
    )
    memory = runtime._being_short_term_memory_store.get(being_id)
    memory.perceive(
        Observation(
            body="鐘が鳴った",
            route=SeenOrHeard(),
            time=ObservedTime(display="深夜 0:01"),
            subject_is_self=False,
            subject_name=UNKNOWN,
            source=UNKNOWN,
            place=UNKNOWN,
            addressed_to_self=UNKNOWN,
        ),
        current_turn=0,
    )
    runtime._being_short_term_memory_store.save(memory)

    runtime.write_episodes_on_leaving()

    assert any("あなた = ゲン\nあなたの一人称 = 俺\n" in messages[-1]["content"] for messages in sent)


def test_action_prompt_tells_the_same_first_person_as_the_persona() -> None:
    """行動を決める LLM の system prompt にも、Being の人柄と同じ一人称が書いてある (persona_prompt に書き足したつなぎ)。"""
    runtime = create_world_runtime(_SCENARIO, config=ResolvedLlmRuntimeConfig.for_tests())

    for player_id in runtime.get_player_ids():
        being_id = runtime._aux_being_resolver.resolve_being_id(runtime._aux_being_default_world_id, player_id)
        first_person = runtime._aux_being_repository.find_by_id(being_id).persona.first_person
        assert f"一人称は「{first_person}」" in runtime.build_system_prompt(player_id)
