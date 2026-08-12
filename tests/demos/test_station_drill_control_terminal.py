"""制御端末による遠隔妨害と、現地での停電復旧が一続きになることを保証する。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime
from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.exception.spot_graph_exception import (
    InteractionNotAllowedException,
)
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId


_DRILL = (
    Path(__file__).resolve().parents[2] / "data" / "scenarios" / "station_drill.json"
)
_MORI, _SENA, _KUZE, _AOI, _HAGI = (PlayerId(i) for i in range(1, 6))
_ROOMS = ("hall", "corridor", "storage", "machine_room")
_TASK_ACTIONS = {
    _MORI: "log_weather",
    _SENA: "tighten_wiring",
    _AOI: "count_supplies",
    _HAGI: "check_generator",
}
_TASK_OBJECTS = {
    _MORI: "気象記録簿",
    _SENA: "配線箱",
    _AOI: "棚卸し帳",
    _HAGI: "発電機",
}


@pytest.fixture()
def runtime():
    return create_world_runtime(_DRILL)


def _scenario() -> dict:
    return json.loads(_DRILL.read_text(encoding="utf-8"))


def _terminal_spec(runtime) -> ItemSpecId:
    return ItemSpecId.create(
        runtime.id_mapper.get_int("item_spec", "control_terminal")
    )


def _move(runtime, player_id: PlayerId, spot: str) -> None:
    graph = runtime._spot_graph_repo.find_graph()
    graph.unplace_entity(EntityId.create(int(player_id)))
    graph.place_entity(
        EntityId.create(int(player_id)),
        SpotId.create(runtime.id_mapper.get_int("spot", spot)),
    )
    runtime._spot_graph_repo.save(graph)


def _lighting(runtime, spot: str) -> str:
    graph = runtime._spot_graph_repo.find_graph()
    spot_id = SpotId.create(runtime.id_mapper.get_int("spot", spot))
    return graph.get_spot(spot_id).atmosphere.lighting.value


def _blackout(runtime) -> None:
    runtime.do_interact_with_item(_KUZE, _terminal_spec(runtime), "cut_power")


def _has_object_row(runtime, player_id: PlayerId, object_name: str) -> bool:
    """担当欄ではなく、現在地に見えている物体行だけを調べる。"""
    return any(
        line.strip().startswith(f'- "{object_name}"')
        for line in runtime.build_observation(player_id).splitlines()
    )


def test_only_the_keeper_sees_and_can_use_the_control_terminal(runtime) -> None:
    """制御端末は所持者だけの prompt に出て、未所持者は内部 ID でも呼べない。"""
    keeper_prompt = runtime.build_full_prompt(_KUZE)["messages"][1]["content"]

    assert '"制御端末"' in keeper_prompt
    assert '照明を落とす → "cut_power"' in keeper_prompt
    assert '隔壁を降ろす → "seal_bulkhead"' in keeper_prompt
    assert "観測所の配電と隔壁を遠隔操作する古い端末。" in keeper_prompt
    assert "そのままは食べられない" not in next(
        line for line in keeper_prompt.splitlines() if '"制御端末"' in line
    )
    for crew in (_MORI, _SENA, _AOI, _HAGI):
        prompt = runtime.build_full_prompt(crew)["messages"][1]["content"]
        assert "制御端末" not in prompt
        with pytest.raises(InteractionNotAllowedException, match="持っていない"):
            runtime.do_interact_with_item(
                crew, _terminal_spec(runtime), "cut_power"
            )


def test_blackout_and_bulkhead_cooldowns_are_independent(runtime) -> None:
    """停電の直後でも、同じ端末から別の隔壁操作を続けて実行できる。"""
    spec_id = _terminal_spec(runtime)

    runtime.do_interact_with_item(_KUZE, spec_id, "cut_power")
    result = runtime.do_interact_with_item(_KUZE, spec_id, "seal_bulkhead")

    assert any("隔壁" in message for message in result.messages)


def test_blackout_hides_each_crew_task_in_all_four_rooms(runtime) -> None:
    """一手の停電で 4 室が暗くなり、各室の作業対象が担当者の一覧から消える。"""
    placements = {
        _MORI: "hall",
        _SENA: "corridor",
        _AOI: "storage",
        _HAGI: "machine_room",
    }
    for player_id, spot in placements.items():
        _move(runtime, player_id, spot)
        assert _has_object_row(runtime, player_id, _TASK_OBJECTS[player_id])
        assert _TASK_ACTIONS[player_id] in runtime.build_observation(player_id)

    _blackout(runtime)

    assert {_lighting(runtime, spot) for spot in _ROOMS} == {"DARK"}
    for player_id in placements:
        assert not _has_object_row(runtime, player_id, _TASK_OBJECTS[player_id])


def test_main_distribution_panel_restores_all_rooms_without_a_role_gate(
    runtime,
) -> None:
    """停電後に機関室へ来たクルーは、暗所でも主配電盤を見つけて全室を復旧できる。"""
    _blackout(runtime)
    _move(runtime, _HAGI, "machine_room")
    observation = runtime.build_observation(_HAGI)

    assert '"主配電盤"' in observation
    assert '配電を復旧する → "restore_power"' in observation

    runtime.do_interact(_HAGI, "main_distribution_panel", "restore_power")

    assert {_lighting(runtime, spot) for spot in _ROOMS} == {"BRIGHT"}


def test_blackout_observation_reaches_every_affected_room(runtime) -> None:
    """遠隔停電の観測は、端末の場所でなく影響を受けた 4 室の在席者へ届く。"""
    placements = {
        _MORI: "hall",
        _SENA: "corridor",
        _AOI: "storage",
        _HAGI: "machine_room",
    }
    for player_id, spot in placements.items():
        _move(runtime, player_id, spot)
    before = {
        player_id: len(runtime._obs_buffer.get_observations(player_id))
        for player_id in placements
    }

    _blackout(runtime)

    for player_id in placements:
        new_entries = runtime._obs_buffer.get_observations(player_id)[
            before[player_id] :
        ]
        assert any(
            entry.output.structured.get("type") == "spot_public_effect_observed"
            for entry in new_entries
        )


def test_sabotage_keeps_the_world_design_asymmetric() -> None:
    """停電は一操作で 4 室へ効き、灯りは 2 個だけで、復旧には現地移動を要する。"""
    data = _scenario()
    terminal = next(
        item for item in data["item_specs"] if item["id"] == "control_terminal"
    )
    blackout = next(
        action
        for action in terminal["interactions"]
        if action["action_name"] == "cut_power"
    )
    bulkhead = next(
        action
        for action in terminal["interactions"]
        if action["action_name"] == "seal_bulkhead"
    )
    affected_spots = {
        effect["parameters"]["target_spot"]
        for effect in blackout["effects"]
        if effect["effect_type"] == "CHANGE_ATMOSPHERE"
    }
    storage = next(spot for spot in data["spots"] if spot["id"] == "storage")
    lantern_case = next(
        obj
        for obj in storage["interior"]["objects"]
        if obj["id"] == "emergency_lantern_case"
    )
    machine_room = next(
        spot for spot in data["spots"] if spot["id"] == "machine_room"
    )
    restore_panel = next(
        obj
        for obj in machine_room["interior"]["objects"]
        if obj["id"] == "main_distribution_panel"
    )

    assert affected_spots == set(_ROOMS)
    assert blackout["cooldown_ticks"] == 10
    assert bulkhead["cooldown_ticks"] == 20
    assert lantern_case["state"]["lanterns_remaining"] == 2 < len(affected_spots)
    assert restore_panel["interactions"][0]["action_name"] == "restore_power"
    assert machine_room["id"] != "hall"  # 全員の開始地点から移動が必要
    assert {player["spawn_spot"] for player in data["players"]} == {"hall"}


def test_remote_bulkhead_keeps_the_existing_reactive_binding() -> None:
    """端末は明示した隔壁盤の手番を記録し、盤と 4 手番の自動復旧宣言を残す。"""
    data = _scenario()
    terminal = next(
        item for item in data["item_specs"] if item["id"] == "control_terminal"
    )
    action = next(
        action
        for action in terminal["interactions"]
        if action["action_name"] == "seal_bulkhead"
    )
    record = next(
        effect
        for effect in action["effects"]
        if effect["effect_type"] == "RECORD_OBJECT_STATE_TICK"
    )
    hall = next(spot for spot in data["spots"] if spot["id"] == "hall")
    panel = next(
        obj
        for obj in hall["interior"]["objects"]
        if obj["id"] == "bulkhead_panel"
    )
    binding = data["reactive_bindings"]["passages"][0]

    assert record["parameters"] == {
        "target_object": "bulkhead_panel",
        "state_key": "sealed_at_tick",
    }
    assert panel["interactions"] == []
    assert binding["predicate"]["children"][0]["ticks_offset"] == 4


def test_inert_bulkhead_panel_does_not_advertise_a_local_control() -> None:
    """操作を失った隔壁盤は、手元で隔壁を降ろせる物体だと宣伝しない。"""
    data = _scenario()
    hall = next(spot for spot in data["spots"] if spot["id"] == "hall")
    panel = next(
        obj
        for obj in hall["interior"]["objects"]
        if obj["id"] == "bulkhead_panel"
    )

    assert panel["interactions"] == []
    assert "非常時に扉を降ろす" not in panel["description"]
    assert "状態を示すだけ" in panel["description"]


@pytest.mark.parametrize("player_id", (_MORI, _SENA, _AOI, _HAGI))
def test_each_crew_member_knows_power_can_be_cut_without_learning_the_role(
    runtime,
    player_id: PlayerId,
) -> None:
    """クルーは遠隔停電を事前に知るが、誰が可能かを役割名では教えられない。"""
    system = runtime.build_full_prompt(player_id)["messages"][0]["content"]

    assert "離れた場所から配電を落とす手段がある" in system
    added_knowledge = system.split("離れた場所から配電を落とす手段がある", 1)[1]
    assert "keeper" not in added_knowledge
    assert "管理人" not in added_knowledge


def test_the_keeper_is_not_given_the_crew_only_blackout_limitation(runtime) -> None:
    """実際に端末を持つクゼへ「自分には操作できない」という嘘を渡さない。"""
    system = runtime.build_full_prompt(_KUZE)["messages"][0]["content"]

    assert "離れた場所から配電を落とす手段がある" not in system
