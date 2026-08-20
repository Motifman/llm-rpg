"""会議開始が宣言された致命的妨害だけを解除し、全員へ知らせることを保証する。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ai_rpg_world.application.llm.services.executors.spot_graph_tool_executor import (
    SpotGraphToolExecutor,
)
from ai_rpg_world.application.world_graph.spot_graph_world_services import (
    SpotGraphWorldServices,
)
from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime
from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.exception.spot_graph_exception import (
    GamePhaseTransitionException,
)
from ai_rpg_world.domain.world_graph.service.game_end_condition_evaluator import (
    GameEndConditionEvaluator,
)
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId


_DRILL = (
    Path(__file__).resolve().parents[2] / "data" / "scenarios" / "station_drill.json"
)
_MORI, _SENA, _KUZE = (PlayerId(i) for i in (1, 2, 3))
_MANUAL_RESTORE = "レバーが噛み合い、配管に熱が戻る音がした。"
_MEETING_RESTORE = "凍結は止まった。配管に熱が戻っている。"
_GLOBAL_RESTORE = "警報が止まった。二つの弁が開き、配管に熱が戻った。"


@pytest.fixture()
def runtime():
    return create_world_runtime(_DRILL)


def _terminal_spec(runtime) -> ItemSpecId:
    return ItemSpecId.create(
        runtime.id_mapper.get_int("item_spec", "control_terminal")
    )


def _freeze(runtime) -> None:
    runtime.do_interact_with_item(_KUZE, _terminal_spec(runtime), "freeze_fuel")


def _cut_power(runtime) -> None:
    runtime.do_interact_with_item(_KUZE, _terminal_spec(runtime), "cut_power")


def _put_body_next_to_reporter(runtime) -> None:
    runtime.do_interact_with_player(_KUZE, _MORI, "strike_down")


def _report(runtime) -> None:
    _put_body_next_to_reporter(runtime)
    result = runtime.report_body(_SENA, _MORI)
    assert result.success is True


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


def _restore_with_valves(runtime) -> None:
    _move(runtime, _MORI, "fuel_bay")
    _move(runtime, _SENA, "machine_room")
    executor = _executor(runtime)
    executor._prepare_action(_MORI.value, {"action_name": "open_thaw_valve"})
    executor._prepare_action(_SENA.value, {"action_name": "open_oil_feed_valve"})
    runtime.advance_tick()
    runtime.advance_tick()


def _prose(runtime, player_id: PlayerId) -> list[str]:
    return [
        entry.output.prose
        for entry in runtime._obs_buffer.get_observations(player_id)
    ]


def test_body_report_resolves_the_condition_with_declared_meeting_effects(runtime) -> None:
    """凍結中の遺体報告で会議が始まると、凍結が降り復旧済みが立つ。"""
    _freeze(runtime)

    _report(runtime)

    flags = runtime._world_flag_state.as_frozen_set()
    assert "fuel_frozen" not in flags
    assert "fuel_restored" in flags


def test_meeting_does_not_clear_blackout_without_declared_meeting_effects(runtime) -> None:
    """停電中に会議が始まっても、解除効果を宣言しない power_out は残る。"""
    _cut_power(runtime)

    _report(runtime)

    assert "power_out" in runtime._world_flag_state.as_frozen_set()


def test_meeting_restoration_cancels_the_existing_deadline(runtime) -> None:
    """会議解除が fuel_restored を立てるため、凍結時計が残っても期限敗北しない。"""
    _freeze(runtime)
    _report(runtime)

    for _ in range(10):
        runtime.advance_tick()

    flags = runtime._world_flag_state.as_frozen_set()
    assert "fuel_restored" in flags
    assert "fuel_lost" not in flags
    assert runtime.check_game_end().reason != "フラグ成立: fuel_lost"


def test_meeting_restoration_reaches_every_player_immediately(runtime) -> None:
    """会議開始による解除音は、弁の参加者に限らず8人全員へ直ちに届く。"""
    _freeze(runtime)

    _report(runtime)

    for player_id in runtime.get_player_ids():
        assert _MEETING_RESTORE in _prose(runtime, player_id)


def test_button_cannot_use_meeting_resolution_during_a_critical_condition(runtime) -> None:
    """凍結中の緊急招集は拒否され、遺体報告だけが会議解除へ進める。"""
    _freeze(runtime)

    result = runtime.call_emergency_meeting(_SENA)

    assert result.success is False
    flags = runtime._world_flag_state.as_frozen_set()
    assert "fuel_frozen" in flags
    assert "fuel_restored" not in flags


def test_rejected_meeting_start_does_not_apply_resolution_effects(runtime) -> None:
    """会議遷移が拒否された場合は、致命的妨害の状態だけを先に動かさない。"""
    runtime.begin_meeting(initiator_player_id=_SENA, trigger="body_report")
    _freeze(runtime)

    with pytest.raises(GamePhaseTransitionException):
        runtime.begin_meeting(initiator_player_id=_KUZE, trigger="body_report")

    flags = runtime._world_flag_state.as_frozen_set()
    assert "fuel_frozen" in flags
    assert "fuel_restored" not in flags


def test_restoration_paths_share_flags_but_describe_their_own_cause() -> None:
    """同期操作と会議は同じ妨害状態を解くが、起きていない原因を互いの語りへ混ぜない。"""
    manual = create_world_runtime(_DRILL)
    meeting = create_world_runtime(_DRILL)
    _freeze(manual)
    _freeze(meeting)

    _restore_with_valves(manual)
    _report(meeting)
    meeting.advance_tick()

    # prepared:* は同期操作 registry の参加記録で、妨害そのものの状態ではない。
    # 二つの解決経路が揃えるべき真実源だけを比較する。
    sabotage_flags = {
        "fuel_frozen",
        "fuel_restored",
        "fuel_announced",
        "fuel_lost",
    }
    assert (
        manual._world_flag_state.as_frozen_set() & sabotage_flags
        == meeting._world_flag_state.as_frozen_set() & sabotage_flags
    )
    for player_id in manual.get_player_ids():
        assert _GLOBAL_RESTORE in _prose(manual, player_id)
        assert _GLOBAL_RESTORE in _prose(meeting, player_id)
        assert _MEETING_RESTORE not in _prose(manual, player_id)
        assert _MANUAL_RESTORE not in _prose(meeting, player_id)
    assert _MANUAL_RESTORE in _prose(manual, _MORI)
    assert _MANUAL_RESTORE in _prose(manual, _SENA)
    for player_id in meeting.get_player_ids():
        assert _MEETING_RESTORE in _prose(meeting, player_id)


def test_meeting_resolution_is_declared_as_effects_not_a_second_boolean() -> None:
    """状態遷移は resolution 一箇所に置き、会議と同期操作は同じ flag を参照する。"""
    raw = json.loads(_DRILL.read_text(encoding="utf-8"))
    conditions = {entry["flag"]: entry for entry in raw["ongoing_conditions"]}
    restore_group = next(
        group
        for group in raw["synchronized_action_groups"]
        if group["id"] == "restore_frozen_fuel"
    )

    assert "critical" not in conditions["fuel_frozen"]
    assert "on_meeting_start" not in conditions["power_out"]
    assert conditions["fuel_frozen"]["resolution"] == [
        {
            "effect_type": "CLEAR_FLAG",
            "parameters": {"flag_name": "fuel_frozen"},
        },
        {
            "effect_type": "SET_FLAG",
            "parameters": {"flag_name": "fuel_restored"},
        },
    ]
    assert conditions["fuel_frozen"]["on_meeting_start"] == [
        {
            "effect_type": "RESOLVE_ONGOING_CONDITION",
            "parameters": {"flag": "fuel_frozen"},
        },
        {
            "effect_type": "SHOW_MESSAGE",
            "parameters": {"message": _MEETING_RESTORE},
        },
    ]
    assert restore_group["on_complete"] == [
        {
            "effect_type": "RESOLVE_ONGOING_CONDITION",
            "parameters": {"flag": "fuel_frozen"},
        },
        {
            "effect_type": "SHOW_MESSAGE",
            "parameters": {"message": _MANUAL_RESTORE},
        },
    ]
    assert _MEETING_RESTORE != _MANUAL_RESTORE
