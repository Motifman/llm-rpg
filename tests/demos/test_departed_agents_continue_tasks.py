"""死亡した担当者が、生者へ混ざらずに作業を続ける挙動を保証する。"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime
from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.player.enum.player_outcome_enum import PlayerOutcomeEnum
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId
from ai_rpg_world.domain.world_graph.enum.interaction_actor_plane import (
    InteractionActorPlane,
)
from ai_rpg_world.domain.world_graph.enum.interaction_condition_type import (
    InteractionConditionTypeEnum,
)
from ai_rpg_world.domain.world_graph.value_object.interaction_condition import (
    InteractionCondition,
)


_SCENARIO = (
    Path(__file__).resolve().parents[2] / "data" / "scenarios" / "station_drill.json"
)
_SENA = PlayerId(2)
_KUZE = PlayerId(3)
_AOI = PlayerId(4)
_HAGI = PlayerId(5)


def _spot(runtime, name: str) -> SpotId:
    return SpotId.create(runtime.id_mapper.get_int("spot", name))


def _place_living(runtime, player_id: PlayerId, spot_name: str) -> None:
    graph = runtime._spot_graph_repo.find_graph()
    entity_id = EntityId.create(int(player_id))
    graph.unplace_entity(entity_id)
    graph.place_entity(entity_id, _spot(runtime, spot_name))
    runtime._spot_graph_repo.save(graph)


def _make_dead(runtime, player_id: PlayerId, spot_name: str) -> None:
    _place_living(runtime, player_id, spot_name)
    runtime._fallen_body_registry.record(
        player_id, _spot(runtime, spot_name), WorldTick(runtime.current_tick())
    )
    status = runtime._player_status_repo.find_by_id(player_id)
    status.apply_damage(status.hp.value)
    runtime._player_status_repo.save(status)
    runtime._player_outcome_registry.set_outcome(player_id, PlayerOutcomeEnum.DEAD)


@pytest.fixture()
def runtime():
    return create_world_runtime(_SCENARIO)


def test_departed_position_is_visible_only_from_the_departed_side(runtime) -> None:
    """別位置へ動いた幽霊は生者の現在状況に混ざらず、本人には移動先が見える。"""
    _make_dead(runtime, _SENA, "corridor")
    _place_living(runtime, _AOI, "storage")
    runtime._departed_position_store.move(_SENA, _spot(runtime, "storage"))

    living_text = runtime.build_observation(_AOI)
    departed_text = runtime.build_observation(_SENA)

    assert '"セナ"' not in living_text
    assert "現在地: 物資庫" in departed_text
    assert '"アオイ"' in departed_text
    assert EntityId.create(int(_SENA)) not in runtime._spot_graph_repo.find_graph().presence_at(
        _spot(runtime, "storage")
    ).present_entity_ids


def test_departed_position_does_not_count_as_physical_presence(runtime) -> None:
    """別位置の幽霊は PLAYERS_AT_SPOT の協力人数へ混ざらない。"""
    _make_dead(runtime, _SENA, "corridor")
    _place_living(runtime, _AOI, "storage")
    runtime._departed_position_store.move(_SENA, _spot(runtime, "storage"))
    storage = runtime._spot_interior_repo.find_by_spot_id(_spot(runtime, "storage"))
    assert storage is not None
    lantern_case = next(
        obj for obj in storage.objects if obj.name == "非常用ランタンケース"
    )
    take_lantern = next(
        interaction
        for interaction in lantern_case.interactions
        if interaction.action_name == "take_lantern"
    )
    two_people_required = replace(
        take_lantern,
        allowed_actor_planes=(
            InteractionActorPlane.LIVING,
            InteractionActorPlane.DEPARTED,
        ),
        preconditions=take_lantern.preconditions
        + (
            InteractionCondition(
                condition_type=InteractionConditionTypeEnum.PLAYERS_AT_SPOT,
                required_player_count=2,
                failure_message="二人いなければ扱えない。",
            ),
        ),
    )
    runtime._spot_interior_repo.save(
        _spot(runtime, "storage"),
        storage.replace_object(
            replace(lantern_case, interactions=(two_people_required,))
        ),
    )

    with pytest.raises(Exception, match="二人いなければ"):
        runtime.do_interact(_SENA, "emergency_lantern_case", "take_lantern")


def test_departed_player_can_move_without_moving_the_body(runtime) -> None:
    """幽霊の移動完了は別位置だけを変え、身体を倒れた場所に残す。"""
    _make_dead(runtime, _SENA, "corridor")

    runtime.do_move(_SENA, "storage")
    for _ in range(10):
        runtime.advance_tick()
        if runtime.get_player_spot_name(_SENA) == "物資庫":
            break

    assert runtime.get_player_spot_name(_SENA) == "物資庫"
    assert runtime._fallen_body_registry.find(_SENA).spot_id == _spot(
        runtime, "corridor"
    )
    assert runtime._spot_graph_repo.find_graph().get_entity_spot(
        EntityId.create(int(_SENA))
    ) == _spot(runtime, "corridor")


def test_missing_departed_position_never_falls_back_to_moving_the_body(runtime) -> None:
    """DEAD の別位置が欠けた不整合時は、身体の物理位置を移動に使わず止まる。"""
    _place_living(runtime, _SENA, "corridor")
    status = runtime._player_status_repo.find_by_id(_SENA)
    status.apply_damage(status.hp.value)
    runtime._player_status_repo.save(status)
    runtime._player_outcome_registry.set_outcome(_SENA, PlayerOutcomeEnum.DEAD)

    with pytest.raises(RuntimeError, match="去った主体の位置がありません"):
        runtime.do_move(_SENA, "storage")

    assert runtime.get_player_spot_id(_SENA) is None
    assert runtime._spot_graph_repo.find_graph().get_entity_spot(
        EntityId.create(int(_SENA))
    ) == _spot(runtime, "corridor")


def test_departed_player_can_complete_their_declared_task(runtime) -> None:
    """死亡した配線担当が三段階を終えると、共有世界の task_wiring が立つ。"""
    _make_dead(runtime, _SENA, "corridor")

    for action_name in (
        "tighten_wiring",
        "tighten_wiring_2",
        "tighten_wiring_3",
    ):
        runtime.do_interact(_SENA, "junction_box", action_name)

    assert "task_wiring" in runtime._world_flag_state.as_frozen_set()


def test_departed_player_is_offered_only_their_physical_capabilities(runtime) -> None:
    """幽霊には移動・作業・発話・待機だけを出し、取得や対人操作を宣伝しない。"""
    _make_dead(runtime, _SENA, "corridor")
    dark_text = runtime.build_observation(_SENA)
    _place_living(runtime, _AOI, "storage")
    runtime.do_interact(_AOI, "emergency_lantern_case", "take_lantern")
    _place_living(runtime, _AOI, "corridor")

    tools = {definition.name for definition in runtime.get_tool_definitions(player_id=_SENA)}
    text = runtime.build_observation(_SENA)

    assert {"travel_to", "interact", "speak", "wait"} <= tools
    assert {"pickup_item", "give_item", "report_body", "listen"}.isdisjoint(tools)
    assert "tighten_wiring" not in dark_text
    assert '"tighten_wiring"' in text
    assert "take_lantern" not in text
    assert "生きている者には姿が見えず、声も届かない" in text


def test_undeclared_interaction_is_rejected_for_departed_player(runtime) -> None:
    """生者専用のランタン取得は表示だけでなく実行入口でも拒否する。"""
    _make_dead(runtime, _SENA, "storage")

    with pytest.raises(Exception, match="今の自分には"):
        runtime.do_interact(_SENA, "emergency_lantern_case", "take_lantern")


def test_departed_player_cannot_use_the_sabotage_panel(runtime) -> None:
    """幽霊にはインポスター専用の隔壁妨害を表示せず、直接指定も拒否する。"""
    _make_dead(runtime, _KUZE, "hall")

    assert "seal_bulkhead" not in runtime.build_observation(_KUZE)
    with pytest.raises(Exception, match="今の自分には"):
        runtime.do_interact(_KUZE, "bulkhead_panel", "seal_bulkhead")


def test_departed_speech_reaches_departed_but_not_the_living(runtime) -> None:
    """同じ場所の幽霊同士には声が届き、生者には話者の観測が漏れない。"""
    _make_dead(runtime, _SENA, "corridor")
    _make_dead(runtime, _HAGI, "machine_room")
    runtime._departed_position_store.move(_SENA, _spot(runtime, "storage"))
    runtime._departed_position_store.move(_HAGI, _spot(runtime, "storage"))
    _place_living(runtime, _AOI, "storage")
    departed_before = len(runtime._obs_buffer.get_observations(_HAGI))
    living_before = len(runtime._obs_buffer.get_observations(_AOI))

    runtime.do_say(_SENA, "配線は続けられる")

    departed = runtime._obs_buffer.get_observations(_HAGI)[departed_before:]
    living = runtime._obs_buffer.get_observations(_AOI)[living_before:]
    assert any("配線は続けられる" in entry.output.prose for entry in departed)
    assert all("配線は続けられる" not in entry.output.prose for entry in living)


def test_world_actions_follow_the_same_perception_matrix(runtime) -> None:
    """同じ場所の生者の行為は幽霊へ届き、幽霊の行為は生者へ漏れない。"""
    _make_dead(runtime, _SENA, "corridor")
    _place_living(runtime, _KUZE, "corridor")
    living_before = len(runtime._obs_buffer.get_observations(_KUZE))

    runtime.do_interact(_SENA, "junction_box", "tighten_wiring")

    living = runtime._obs_buffer.get_observations(_KUZE)[living_before:]
    assert all("配線箱の中をいじっている" not in entry.output.prose for entry in living)

    runtime._departed_position_store.move(_SENA, _spot(runtime, "storage"))
    _place_living(runtime, _AOI, "storage")
    departed_before = len(runtime._obs_buffer.get_observations(_SENA))

    runtime.do_interact(_AOI, "emergency_lantern_case", "take_lantern")

    departed = runtime._obs_buffer.get_observations(_SENA)[departed_before:]
    assert any("非常用ランタンケースを開けた" in entry.output.prose for entry in departed)
