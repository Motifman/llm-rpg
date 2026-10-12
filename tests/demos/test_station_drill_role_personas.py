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


def test_crew_migration_preserves_the_pre_split_system_bytes() -> None:
    """共通文だけを抜き出したクルー六人の system sha256 が、意図せず動かない。

    もとは #1115 の分割が**バイトを変えていない**ことを示すために置いた。共通引数の
    説明を system prompt へ寄せた時点で、**意図してバイトが変わった**ので値を更新
    してある。#1521 で、persona_prompt に【ペルソナ】の見出しが付くようになり
    (本文が「上記【ペルソナ】」と指す見出しが無かった)、見出しの 1 行ぶん
    バイトが変わった。#1520 で、誰を知っているかを system prompt に書かず、毎ターンの
    メッセージの【知っている人】に移したので、【同じ局面にいる者】の節のぶん
    バイトが変わった。#1616 で、記憶の指示が出ている欄とツールだけを指すように
    なり、記憶の部品を有効にしないこの世界では【関連する記憶】と能動想起の文の
    ぶんバイトが変わった。

    以後この検査が守るのは「**気づかないうちに system prompt が変わらない**」こと。
    値を更新するときは、prompt を変えた理由が PR にあるはずなので、それを確かめる
    こと。**理由の無い更新は、この検査を無意味にする。**
    """
    runtime = create_world_runtime(_DRILL)
    expected_by_string_id = {
        "mori": "d0546525e97e2ad7ecbad200a738b394b61f411e90824032620a60d56f49bda5",
        "sena": "0891c0bb068163225f25132edcaa44d8ec4ef48bc984887b79d7e48d051b2a48",
        "aoi": "e3f8362ce2d2ee7df092b63dd389e2c50979a236ae6e84c5663e40f8a19e8ec0",
        "hagi": "0fdfa70ec1a9500241e011fa6d47136ee6f4e8bd7b75b4f4be0e2f457918db32",
        "yura": "f8facae373400d31517332324f7678b25e1e0e9cb91cedc6052c130098aefd10",
        "saki": "d65c206dc7a9b710ae9d563e33ca9ded192f20d17ee8e3b958dc97279f813b5a",
    }

    actual_by_string_id = {
        spawn.string_id: hashlib.sha256(
            runtime._world_llm_system_prompts_by_player_id[spawn.player_id].encode(
                "utf-8"
            )
        ).hexdigest()
        for spawn in runtime.scenario.player_spawns
        if spawn.initial_state.get("role") == "crew"
    }

    assert actual_by_string_id == expected_by_string_id


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
