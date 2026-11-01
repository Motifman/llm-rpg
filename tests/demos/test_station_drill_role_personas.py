"""station_drill の人物像と役職共通知識が構造として分離されることを保証する。"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime
from ai_rpg_world.domain.player.value_object.player_id import PlayerId

_DRILL = Path(__file__).resolve().parents[2] / "data" / "scenarios" / "station_drill.json"


def _raw() -> dict:
    return json.loads(_DRILL.read_text(encoding="utf-8"))


def _players_by_role(runtime, role: str) -> tuple[PlayerId, ...]:
    return tuple(
        PlayerId(spawn.player_id) for spawn in runtime.scenario.player_spawns if spawn.initial_state.get("role") == role
    )


def test_each_crew_system_joins_its_person_and_the_identical_role_text() -> None:
    """クルー六人の system は各人物文の後ろに、同じ一つの crew 共通文を連結する。"""
    raw = _raw()
    runtime = create_world_runtime(_DRILL)
    crew_role = raw["role_personas"]["crew"]
    individual_by_id = {player["id"]: player["persona_prompt"] for player in raw["players"]}

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
    individual_by_id = {player["id"]: player["persona_prompt"] for player in raw["players"]}

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
    ぶんバイトが変わった。#1612 で、行動に添える一言には結果ではなくこれから
    することを書くよう【独白と一言の書き方】に 1 文足したので、そのぶんバイトが
    変わった。#1631 で、目次つきのエピソードが設定で止められない標準になり、
    【思い出せる出来事】と `episode_recall` を説明する 1 行ぶんバイトが変わった。
    同じく #1631 で、メモ帳が設定で止められない標準になり、【メモの書き方】の節の
    ぶんバイトが変わった。#1630 で、【現在の目的】をメッセージからシステムプロンプトの末尾へ移し、
    作法と環境の決まり (【この世界の決まり】) を分けて並べ直したので、バイトが変わった (D1630-4)。

    以後この検査が守るのは「**気づかないうちに system prompt が変わらない**」こと。
    値を更新するときは、prompt を変えた理由が PR にあるはずなので、それを確かめる
    こと。**理由の無い更新は、この検査を無意味にする。**
    """
    runtime = create_world_runtime(_DRILL)
    expected_by_string_id = {
        "mori": "ecf4dafa21c26a8c5666d1a132cf19ffd672574794ecfdeb48fabd825786a281",
        "sena": "0919195282a3fba49e099f9385a2602f13ea28f009cb4457ddc08f6bcb61abb0",
        "aoi": "360b7f9bccecd67f7e654468ff5a8c1131e76c73c8a5ca816160d85258a2a775",
        "hagi": "effd4a1cf92cb14a75a392da33d3e3bf90645d95445af03e7715d30c68c71a4a",
        "yura": "ac17a1e708420b282e94673c67d709f9c9887d4a357ab14c41716eca5b33944a",
        "saki": "57cbbb5b00e678d15fc95ed2c010cd6d856122b6a409a84b87f34385f98d2c53",
    }

    actual_by_string_id = {
        spawn.string_id: hashlib.sha256(
            runtime._world_llm_system_prompts_by_player_id[spawn.player_id].encode("utf-8")
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
