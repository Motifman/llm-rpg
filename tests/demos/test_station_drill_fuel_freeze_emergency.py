"""station_drill の燃料凍結が、全員を動かす時間制限つき協力妨害になることを保証する。"""

from __future__ import annotations

from pathlib import Path
import json

import pytest

from ai_rpg_world.application.llm.services.executors.spot_graph_tool_executor import (
    SpotGraphToolExecutor,
)
from ai_rpg_world.application.llm.services.executors.interact_helpers import (
    list_object_interactions,
)
from ai_rpg_world.application.world_graph.spot_graph_world_services import (
    SpotGraphWorldServices,
)
from ai_rpg_world.application.world_graph.world_flag_state import (
    WorldFlagMutationContext,
    WorldFlagMutationSource,
)
from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime
from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.service.game_end_condition_evaluator import (
    GameEndConditionEvaluator,
)
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId
from ai_rpg_world.domain.world_graph.value_object.spot_object_id import SpotObjectId


_DRILL = (
    Path(__file__).resolve().parents[2] / "data" / "scenarios" / "station_drill.json"
)
_MORI, _SENA, _KUZE = (PlayerId(i) for i in (1, 2, 3))
_ALARM = (
    "観測所じゅうに警報が鳴った。燃料が凍りはじめている。"
    "燃料庫の解氷弁と機関室の送油弁を同時に開けなければ、発電が止まる。"
)


@pytest.fixture()
def runtime():
    return create_world_runtime(_DRILL)


def _terminal_spec(runtime) -> ItemSpecId:
    return ItemSpecId.create(
        runtime.id_mapper.get_int("item_spec", "control_terminal")
    )


def _move(runtime, player_id: PlayerId, spot: str) -> None:
    graph = runtime._spot_graph_repo.find_graph()
    graph.teleport_entity(
        EntityId.create(int(player_id)),
        SpotId.create(runtime.id_mapper.get_int("spot", spot)),
    )
    runtime._spot_graph_repo.save(graph)


def _executor(runtime) -> SpotGraphToolExecutor:
    services = SpotGraphWorldServices(
        interaction=runtime._interaction_service,
        exploration=runtime._exploration_service,
        world_flags=runtime._world_flag_state,
        game_end_evaluator=GameEndConditionEvaluator(),
        exploration_progress=runtime._exploration_progress,
        movement=runtime._movement_service,
    )
    return SpotGraphToolExecutor(
        spot_graph_world_services=services,
        player_inventory_repository=runtime._player_inventory_repo,
        item_repository=runtime._item_repo,
        event_publisher=runtime._speech_event_publisher,
        sync_action_groups=runtime.scenario.synchronized_action_groups,
        time_provider=runtime._time_provider,
        spot_graph_repository=runtime._spot_graph_repo,
        sync_action_registry=(
            runtime._simulation_service._sync_action_resolver_stage._registry
        ),
    )


def _freeze(runtime) -> None:
    runtime.do_interact_with_item(_KUZE, _terminal_spec(runtime), "freeze_fuel")


def _prose(runtime, player_id: PlayerId) -> list[str]:
    return [
        entry.output.prose
        for entry in runtime._obs_buffer.get_observations(player_id)
    ]


def test_remote_freeze_sounds_the_alarm_for_every_player(runtime) -> None:
    """クゼがどの部屋から凍結させても、次の世界更新で8人全員へ警報が届く。"""
    _move(runtime, _KUZE, "observatory")

    _freeze(runtime)
    runtime.advance_tick()

    assert "fuel_frozen" in runtime._world_flag_state.as_frozen_set()
    for player_id in runtime.get_player_ids():
        assert _ALARM in _prose(runtime, player_id)


def test_only_the_terminal_owner_can_see_the_freeze_action(runtime) -> None:
    """凍結操作はクゼの所持品行だけに出て、クルーのプロンプトには現れない。"""
    kuze = runtime.build_full_prompt(_KUZE)["messages"][1]["content"]

    assert '燃料を凍結させる → "freeze_fuel"' in kuze
    for player_id in (_MORI, _SENA):
        prompt = runtime.build_full_prompt(player_id)["messages"][1]["content"]
        assert "freeze_fuel" not in prompt
        assert "燃料を凍結させる" not in prompt


@pytest.mark.parametrize(
    ("player_id", "spot", "action_name"),
    [
        (_MORI, "fuel_bay", "open_thaw_valve"),
        (_SENA, "machine_room", "open_oil_feed_valve"),
    ],
)
def test_valves_are_hidden_until_the_fuel_freezes(
    runtime, player_id: PlayerId, spot: str, action_name: str
) -> None:
    """解氷操作は平常時には存在ごと隠れ、凍結後だけ各現地の物体行へ現れる。"""
    _move(runtime, player_id, spot)
    before = runtime.build_observation(player_id)

    _freeze(runtime)
    after = runtime.build_observation(player_id)

    assert action_name not in before
    assert action_name in after


def test_wrong_name_guidance_does_not_reveal_an_inactive_valve(runtime) -> None:
    """誤った操作名への救済一覧も、平常時の解氷弁を名前ごと漏らさない。"""
    _move(runtime, _MORI, "fuel_bay")
    object_id = runtime.id_mapper.get_int("object", "fuel_thaw_valve")

    before = list_object_interactions(runtime, object_id, player_id=_MORI.value)
    _freeze(runtime)
    active = list_object_interactions(runtime, object_id, player_id=_MORI.value)

    assert "open_thaw_valve" not in before
    assert "open_thaw_valve" in active


def test_two_people_restore_fuel_within_the_three_tick_window(runtime) -> None:
    """別々の二人が猶予内に両室の弁を準備すると復旧し、締切を過ぎても燃料を失わない。"""
    _freeze(runtime)
    _move(runtime, _MORI, "fuel_bay")
    _move(runtime, _SENA, "machine_room")
    executor = _executor(runtime)

    left = executor._prepare_action(_MORI.value, {"action_name": "open_thaw_valve"})
    right = executor._prepare_action(
        _SENA.value, {"action_name": "open_oil_feed_valve"}
    )
    runtime.advance_tick()
    for _ in range(8):
        runtime.advance_tick()

    flags = runtime._world_flag_state.as_frozen_set()
    assert left.success is True
    assert right.success is True
    assert "fuel_restored" in flags
    assert "fuel_lost" not in flags
    assert runtime.check_game_end().reason != "燃料が凍りついて発電が止まった。"
    assert "open_thaw_valve" not in runtime.build_observation(_MORI)
    assert "open_oil_feed_valve" not in runtime.build_observation(_SENA)


def test_partial_prepare_times_out_but_does_not_cancel_the_deadline(runtime) -> None:
    """片方だけの準備は3手番で解除され、その後も8手番の全体締切は進み続ける。"""
    _freeze(runtime)
    _move(runtime, _MORI, "fuel_bay")
    executor = _executor(runtime)
    prepared = executor._prepare_action(
        _MORI.value, {"action_name": "open_thaw_valve"}
    )
    registry = runtime._simulation_service._sync_action_resolver_stage._registry

    for _ in range(3):
        runtime.advance_tick()

    assert prepared.success is True
    assert registry.entries_for("open_thaw_valve") == []
    assert "片方だけでは戻らない。レバーが元に戻った。" in _prose(
        runtime, _MORI
    )

    for _ in range(5):
        runtime.advance_tick()
    assert "fuel_lost" in runtime._world_flag_state.as_frozen_set()


def test_ignored_freeze_reaches_the_deadline_and_loses(runtime) -> None:
    """誰も弁を準備しなくても8手番後に fuel_lost が立ち、宣言した敗北になる。"""
    _freeze(runtime)

    for _ in range(8):
        runtime.advance_tick()

    result = runtime.check_game_end()
    assert "fuel_lost" in runtime._world_flag_state.as_frozen_set()
    assert result.is_ended is True
    assert result.result.value == "LOSE"
    declared_loss = next(
        condition
        for condition in json.loads(_DRILL.read_text(encoding="utf-8"))[
            "game_end_conditions"
        ]["lose"]
        if condition.get("target_flag") == "fuel_lost"
    )
    assert result.reason == "フラグ成立: fuel_lost"
    assert declared_loss["description"] == "燃料が凍りついて発電が止まった。"


def test_distance_equals_the_window_so_one_runner_cannot_cover_both_valves(
    runtime,
) -> None:
    """弁間の最短距離3は window=3 の境界外で、一人の移動による二役兼務を許さない。"""
    raw = json.loads(_DRILL.read_text(encoding="utf-8"))
    edges: dict[str, list[tuple[str, int]]] = {}
    for connection in raw["connections"]:
        edges.setdefault(connection["from"], []).append(
            (connection["to"], connection["travel_ticks"])
        )
        if connection.get("is_bidirectional", False):
            edges.setdefault(connection["to"], []).append(
                (connection["from"], connection["travel_ticks"])
            )
    costs = {"fuel_bay": 0}
    pending = [(0, "fuel_bay")]
    while pending:
        cost, spot = min(pending)
        pending.remove((cost, spot))
        if spot == "machine_room":
            break
        for neighbor, travel_ticks in edges.get(spot, ()):
            candidate = cost + travel_ticks
            if candidate < costs.get(neighbor, 10**9):
                costs[neighbor] = candidate
                pending.append((candidate, neighbor))
    distance = costs["machine_room"]
    group = runtime.scenario.synchronized_action_groups[0]

    assert distance == group.window_ticks == 3
    assert len(group.required_action_names) == 2


def test_one_player_is_rejected_when_trying_to_prepare_both_valves(runtime) -> None:
    """同一人物が移動済みでも二つ目の役割を兼ねられず、復旧フラグは立たない。"""
    _freeze(runtime)
    _move(runtime, _MORI, "fuel_bay")
    executor = _executor(runtime)
    first = executor._prepare_action(
        _MORI.value, {"action_name": "open_thaw_valve"}
    )
    _move(runtime, _MORI, "machine_room")
    second = executor._prepare_action(
        _MORI.value, {"action_name": "open_oil_feed_valve"}
    )
    runtime.advance_tick()

    assert first.success is True
    assert second.success is False
    assert "別の参加者" in second.message
    assert "fuel_restored" not in runtime._world_flag_state.as_frozen_set()


def test_pressure_gauge_shows_world_minutes_only_during_the_emergency(runtime) -> None:
    """燃料圧計は平常時は無表示で、凍結中だけ生の手番でなく残り分数を示す。"""
    _move(runtime, _MORI, "machine_room")
    before = runtime.build_observation(_MORI)

    _freeze(runtime)
    runtime.advance_tick()
    active = runtime.build_observation(_MORI)

    assert "燃料停止まであと" not in before
    assert "燃料停止まであと 35 分" in active
    assert "frozen_at_tick" not in active
    gauge_id = runtime.id_mapper.get_int("object", "fuel_pressure_gauge")
    machine_room = runtime._spot_interior_repo.find_by_spot_id(
        SpotId.create(runtime.id_mapper.get_int("spot", "machine_room"))
    )
    assert "frozen_at_tick" in machine_room.get_object(
        SpotObjectId.create(gauge_id)
    ).hidden_state_keys

    runtime._world_flag_state.add(
        "fuel_restored",
        context=WorldFlagMutationContext(
            source=WorldFlagMutationSource.SCENARIO_EVENT,
            actor_player_id=None,
        ),
    )
    restored = runtime.build_observation(_MORI)
    assert "燃料停止まであと" not in restored


def test_alarm_and_deadline_wake_every_player(runtime) -> None:
    """警報と締切は全員向けに手番を予約し、妨害を誰も知らない状態にしない。"""
    raw = json.loads(_DRILL.read_text(encoding="utf-8"))
    events = {event["id"]: event for event in raw["scenario_events"]}

    for event_id in ("fuel_freeze_alarm", "fuel_freeze_deadline"):
        observation = events[event_id]["observation"]
        assert observation["recipients"] == "all_players"
        assert observation["schedules_turn"] is True
