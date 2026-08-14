"""制御端末による遠隔妨害と、現地での停電復旧が一続きになることを保証する。"""

from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path

import pytest

from ai_rpg_world.application.common.exceptions import ApplicationException
from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime
from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.exception.spot_graph_exception import (
    InteractionNotAllowedException,
)
from ai_rpg_world.domain.world_graph.service.item_interaction_registry import (
    ItemInteractionRegistry,
)
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId


_DRILL = (
    Path(__file__).resolve().parents[2] / "data" / "scenarios" / "station_drill.json"
)
_MORI, _SENA, _KUZE, _AOI, _HAGI, _YURA, _JIN, _SAKI = (
    PlayerId(i) for i in range(1, 9)
)
_ROOMS = (
    "observatory",
    "medbay",
    "greenhouse",
    "comms",
    "fuel_bay",
    "hall",
    "corridor",
    "storage",
    "machine_room",
)


@pytest.fixture()
def runtime():
    return create_world_runtime(_DRILL)


def _scenario() -> dict:
    return json.loads(_DRILL.read_text(encoding="utf-8"))


def _task_objects_by_room() -> dict[str, tuple[str, ...]]:
    """完了フラグを書く宣言から、各室の作業物体名を導出する。"""
    found: dict[str, tuple[str, ...]] = {}
    for spot in _scenario()["spots"]:
        names = []
        for obj in spot.get("interior", {}).get("objects", []):
            if any(
                effect["effect_type"] == "SET_FLAG"
                and effect["parameters"].get("flag_name", "").startswith("task_")
                for interaction in obj.get("interactions", [])
                for effect in interaction.get("effects", [])
            ):
                names.append(obj["name"])
        found[spot["id"]] = tuple(names)
    return found


def _terminal_spec(runtime) -> ItemSpecId:
    return ItemSpecId.create(
        runtime.id_mapper.get_int("item_spec", "control_terminal")
    )


def _install_terminal_action(runtime, action) -> None:
    """合成した制御端末操作だけを application service の登録簿へ入れる。"""
    runtime._interaction_service._item_interaction_registry = (
        ItemInteractionRegistry({_terminal_spec(runtime): (action,)})
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


def test_both_keepers_see_and_can_use_the_control_terminal(runtime) -> None:
    """制御端末はインポスター二人の prompt に出て、クルーは内部 ID でも呼べない。"""
    for keeper in (_KUZE, _JIN):
        keeper_prompt = runtime.build_full_prompt(keeper)["messages"][1]["content"]
        assert '"制御端末"' in keeper_prompt
        assert '照明を落とす → "cut_power"' in keeper_prompt
        assert '隔壁を降ろす → "seal_bulkhead"' in keeper_prompt
        assert '燃料を凍結させる → "freeze_fuel"' in keeper_prompt
        assert "観測所の配電・隔壁・燃料系を遠隔操作する古い端末。" in keeper_prompt
        assert "そのままは食べられない" not in next(
            line for line in keeper_prompt.splitlines() if '"制御端末"' in line
        )
    for other in (_MORI, _SENA, _AOI, _HAGI, _YURA, _SAKI):
        prompt = runtime.build_full_prompt(other)["messages"][1]["content"]
        assert "制御端末" not in prompt
        with pytest.raises(InteractionNotAllowedException, match="持っていない"):
            runtime.do_interact_with_item(
                other, _terminal_spec(runtime), "cut_power"
            )


def test_world_scoped_terminal_cooldown_blocks_the_partner(runtime) -> None:
    """クゼが停電させた直後は、同じ端末を持つジンも実行結果で拒否される。"""
    spec_id = _terminal_spec(runtime)
    runtime.do_interact_with_item(_KUZE, spec_id, "cut_power")

    with pytest.raises(InteractionNotAllowedException, match="まだそれはできない"):
        runtime.do_interact_with_item(_JIN, spec_id, "cut_power")


def test_world_scoped_terminal_cooldown_allows_the_partner_after_twenty_five_ticks(
    runtime,
) -> None:
    """非扉妨害の共有待ち時間25手番が経過すれば、相方のジンも再び使える。"""
    spec_id = _terminal_spec(runtime)
    runtime.do_interact_with_item(_KUZE, spec_id, "cut_power")
    for _ in range(25):
        runtime.advance_tick()

    assert runtime.do_interact_with_item(_JIN, spec_id, "freeze_fuel") is not None


def test_world_scoped_terminal_cooldown_survives_a_snapshot(runtime) -> None:
    """保存と復元を挟んでも、クゼの停電で始まった共有待ち時間はジンの凍結を拒む。"""
    from ai_rpg_world.application.being.world_subsystems import (
        InteractionCooldownSubsystemCodec,
    )

    spec_id = _terminal_spec(runtime)
    runtime.do_interact_with_item(_KUZE, spec_id, "cut_power")
    codec = InteractionCooldownSubsystemCodec()
    saved = codec.capture(runtime)

    restored = create_world_runtime(_DRILL)
    codec.restore(restored, saved)

    with pytest.raises(InteractionNotAllowedException, match="まだそれはできない"):
        restored.do_interact_with_item(_JIN, _terminal_spec(restored), "freeze_fuel")


def test_blackout_blocks_the_partners_fuel_freeze(runtime) -> None:
    """クゼが停電させると、別操作でも同じ共有待ち時間に属するジンの凍結は拒否される。"""
    spec_id = _terminal_spec(runtime)
    runtime.do_interact_with_item(_KUZE, spec_id, "cut_power")

    with pytest.raises(InteractionNotAllowedException, match="まだそれはできない"):
        runtime.do_interact_with_item(_JIN, spec_id, "freeze_fuel")


def test_fuel_freeze_blocks_the_partners_blackout(runtime) -> None:
    """クゼが燃料を凍結させると、逆向きでもジンの停電は共有待ち時間で拒否される。"""
    spec_id = _terminal_spec(runtime)
    runtime.do_interact_with_item(_KUZE, spec_id, "freeze_fuel")

    with pytest.raises(InteractionNotAllowedException, match="まだそれはできない"):
        runtime.do_interact_with_item(_JIN, spec_id, "cut_power")


def test_blackout_and_bulkhead_cooldowns_are_independent(runtime) -> None:
    """停電の直後でも、同じ端末から別の隔壁操作を続けて実行できる。"""
    spec_id = _terminal_spec(runtime)

    runtime.do_interact_with_item(_KUZE, spec_id, "cut_power")
    result = runtime.do_interact_with_item(_KUZE, spec_id, "seal_bulkhead")

    assert any("隔壁" in message for message in result.messages)


@pytest.mark.parametrize("non_door_action", ("cut_power", "freeze_fuel"))
def test_bulkhead_does_not_block_non_door_sabotage(
    runtime, non_door_action: str
) -> None:
    """隔壁は独立した短い待ち時間なので、使用直後も停電と凍結を妨げない。"""
    spec_id = _terminal_spec(runtime)
    runtime.do_interact_with_item(_KUZE, spec_id, "seal_bulkhead")

    assert runtime.do_interact_with_item(_JIN, spec_id, non_door_action) is not None


def test_bulkhead_cooldown_expires_after_ten_ticks(runtime) -> None:
    """隔壁は非扉妨害より短い10手番だけ待たせ、境界で再び使える。"""
    spec_id = _terminal_spec(runtime)
    runtime.do_interact_with_item(_KUZE, spec_id, "seal_bulkhead")
    for _ in range(9):
        runtime.advance_tick()
    with pytest.raises(InteractionNotAllowedException, match="まだそれはできない"):
        runtime.do_interact_with_item(_JIN, spec_id, "seal_bulkhead")

    runtime.advance_tick()

    assert runtime.do_interact_with_item(_JIN, spec_id, "seal_bulkhead") is not None


def test_blackout_hides_tasks_in_every_room(runtime) -> None:
    """停電は全9室を暗くし、どの作業物体も灯りなしでは一覧から消える。"""
    task_objects = _task_objects_by_room()
    assert sum(map(len, task_objects.values())) == 16
    assert {_lighting(runtime, spot) for spot in _ROOMS} == {"BRIGHT"}

    _blackout(runtime)

    assert {_lighting(runtime, spot) for spot in _ROOMS} == {"DARK"}
    for spot in _ROOMS:
        _move(runtime, _SENA, spot)
        for object_name in task_objects[spot]:
            assert not _has_object_row(runtime, _SENA, object_name)


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


def test_blackout_observation_reaches_affected_rooms(runtime) -> None:
    """遠隔停電の観測は、端末の場所でなく影響を受けた各室の在席者へ届く。"""
    placements = {
        _MORI: "observatory",
        _SENA: "medbay",
        _AOI: "greenhouse",
        _HAGI: "comms",
        _YURA: "fuel_bay",
        _JIN: "storage",
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
    """停電は一操作で9室へ効き、灯りは2個だけで、復旧には現地移動を要する。"""
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
    frozen = next(
        action
        for action in terminal["interactions"]
        if action["action_name"] == "freeze_fuel"
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
    assert blackout["cooldown_ticks"] == 25
    assert bulkhead["cooldown_ticks"] == 10
    assert frozen["cooldown_ticks"] == 25
    assert blackout["cooldown_group"] == frozen["cooldown_group"]
    assert "cooldown_group" not in bulkhead
    assert {
        blackout["cooldown_scope"],
        bulkhead["cooldown_scope"],
        frozen["cooldown_scope"],
    } == {"world"}
    assert lantern_case["state"]["lanterns_remaining"] == 2 < len(affected_spots)
    assert restore_panel["interactions"][0]["action_name"] == "restore_power"
    assert machine_room["id"] != "hall"  # 全員の開始地点から移動が必要
    assert {player["spawn_spot"] for player in data["players"]} == {"hall"}


def test_remote_bulkhead_closes_both_observatory_passages() -> None:
    """端末は観測室の隔壁盤へ記録し、二本を同じ4手番だけ閉じる。"""
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
    observatory = next(
        spot for spot in data["spots"] if spot["id"] == "observatory"
    )
    panel = next(
        obj
        for obj in observatory["interior"]["objects"]
        if obj["id"] == "bulkhead_panel"
    )
    bindings = data["reactive_bindings"]["passages"]

    assert record["parameters"] == {
        "target_object": "bulkhead_panel",
        "state_key": "sealed_at_tick",
    }
    assert panel["interactions"] == []
    assert {binding["target"] for binding in bindings} == {
        "observatory_to_medbay",
        "observatory_to_comms",
    }
    assert all(
        binding["predicate"]["children"][0]["ticks_offset"] == 4
        for binding in bindings
    )


def test_remote_item_effect_rejects_an_object_missing_from_the_world(runtime) -> None:
    """道具が明示した物体を解決できなければ、成功扱いへ縮退せず停止する。"""
    action = next(
        action
        for action in runtime._interaction_service._item_interaction_registry.interactions_for(
            _terminal_spec(runtime)
        )
        if action.action_name == "seal_bulkhead"
    )
    missing_object = replace(
        action.effects[0],
        parameters={**action.effects[0].parameters, "object_id": 999_999},
    )
    _install_terminal_action(
        runtime,
        replace(action, effects=(missing_object, *action.effects[1:])),
    )

    with pytest.raises(
        ApplicationException,
        match="道具操作が明示した対象物を世界から解決できません",
    ):
        runtime.do_interact_with_item(
            _KUZE, _terminal_spec(runtime), "seal_bulkhead"
        )


def test_remote_item_effect_rejects_objects_owned_by_different_rooms(runtime) -> None:
    """一操作が異なる二室の物体を指す場合は、片方だけへ適用せず停止する。"""
    action = next(
        action
        for action in runtime._interaction_service._item_interaction_registry.interactions_for(
            _terminal_spec(runtime)
        )
        if action.action_name == "seal_bulkhead"
    )
    distribution_panel_id = runtime.id_mapper.get_int(
        "object", "main_distribution_panel"
    )
    second_room_effect = replace(
        action.effects[0],
        parameters={
            **action.effects[0].parameters,
            "object_id": distribution_panel_id,
        },
    )
    _install_terminal_action(
        runtime,
        replace(
            action,
            effects=(action.effects[0], second_room_effect, *action.effects[1:]),
        ),
    )

    with pytest.raises(
        ApplicationException,
        match="一つの道具操作から複数の部屋の物体へ効果を適用",
    ):
        runtime.do_interact_with_item(
            _KUZE, _terminal_spec(runtime), "seal_bulkhead"
        )


def test_inert_bulkhead_panel_does_not_advertise_a_local_control() -> None:
    """操作を失った隔壁盤は、手元で隔壁を降ろせる物体だと宣伝しない。"""
    data = _scenario()
    observatory = next(
        spot for spot in data["spots"] if spot["id"] == "observatory"
    )
    panel = next(
        obj
        for obj in observatory["interior"]["objects"]
        if obj["id"] == "bulkhead_panel"
    )

    assert panel["interactions"] == []
    assert "非常時に扉を降ろす" not in panel["description"]
    assert "状態を示すだけ" in panel["description"]


@pytest.mark.parametrize(
    "player_id", (_MORI, _SENA, _AOI, _HAGI, _YURA, _SAKI)
)
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


@pytest.mark.parametrize("player_id", (_KUZE, _JIN))
def test_each_terminal_holder_knows_the_shared_sabotage_hand(
    runtime, player_id: PlayerId
) -> None:
    """二人の system に共通端末と、凍結で二人が別室へ向かう事実を一度だけ出す。"""
    system = runtime.build_full_prompt(player_id)["messages"][0]["content"]

    assert system.count("制御端末から、離れた場所にいても") == 1
    assert "同じ端末から隔壁を降ろして通行を止める" in system
    assert "同じ端末から燃料を凍結させることもできる" in system
    assert "この間隔は二人で共通で、相方が使った直後はあなたも使えない" in system
    assert "誰が操作したかは他の者には伝わらない" in system
    assert "燃料が凍り始めたまま放置されれば発電が止まり、クルーは負ける" in system
    assert "戻すには、燃料庫と機関室の弁を二人が同時に開けるしかない" in system
    assert system.count(
        "その二人は点検を中断して、別々の部屋へ向かうことになる"
    ) == 1


def test_persona_text_avoids_known_tactical_phrases() -> None:
    """全 persona の全段落から既知の戦術語を除くが、未知の言い換えはレビューで見る。"""
    scenario = _scenario()
    forbidden_tactics = ("待つ", "待ち伏せ", "狙え", "走る", "決められる")

    for player in scenario["players"]:
        role = player["initial_state"]["role"]
        role_knowledge = "\n\n".join(
            (player["persona_prompt"], scenario["role_personas"][role])
        )
        assert all(word not in role_knowledge for word in forbidden_tactics), player["id"]


@pytest.mark.parametrize(
    "player_id", (_MORI, _SENA, _AOI, _HAGI, _YURA, _SAKI)
)
def test_crew_systems_do_not_receive_the_impostor_hand_description(
    runtime,
    player_id: PlayerId,
) -> None:
    """クルーの事前知識には、インポスター二人の端末説明を混ぜない。"""
    system = runtime.build_full_prompt(player_id)["messages"][0]["content"]

    assert "制御端末から、離れた場所にいても" not in system
    assert "同じ端末から隔壁を降ろして通行を止める" not in system
    assert "燃料が凍り始めたまま放置されれば発電が止まり、クルーは負ける" not in system
    assert "戻すには、燃料庫と機関室の弁を二人が同時に開けるしかない" not in system
    assert "その二人は点検を中断して、別々の部屋へ向かうことになる" not in system


def test_sabotage_hand_description_hides_role_names_and_declared_ticks() -> None:
    """端末の手札説明は役割名も待ち時間の数値も二重に宣言しない。"""
    scenario = _scenario()
    paragraph = next(
        part
        for part in scenario["role_personas"]["keeper"].split("\n\n")
        if "制御端末から、離れた場所にいても" in part
    )

    assert "keeper" not in paragraph
    assert "管理人" not in paragraph
    assert "10" not in paragraph
    assert "20" not in paragraph
    assert "25" not in paragraph


def test_old_sabotage_locations_have_no_operable_remnants() -> None:
    """旧四室配置には隔壁盤・通気口・旧接続の反応 binding を残さない。"""
    data = _scenario()
    objects_by_spot = {
        spot["id"]: {
            obj["id"] for obj in spot.get("interior", {}).get("objects", [])
        }
        for spot in data["spots"]
    }

    assert "bulkhead_panel" not in objects_by_spot["hall"]
    assert "observatory_vent" not in objects_by_spot["corridor"]
    assert "storage_vent" not in objects_by_spot["machine_room"]
    assert all(
        old_id not in object_ids
        for object_ids in objects_by_spot.values()
        for old_id in ("corridor_vent", "machine_room_vent")
    )
    assert "hall_to_corridor" not in {
        binding["target"] for binding in data["reactive_bindings"]["passages"]
    }
