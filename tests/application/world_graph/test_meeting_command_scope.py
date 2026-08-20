"""会議開始の状態変更と成功観測が一つのCommandScopeで確定することを保証する。"""

from __future__ import annotations

from pathlib import Path

import pytest

from ai_rpg_world.application.common.event_delivery import (
    DeliveryChannel,
    DeliveryGuarantee,
)
from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime
from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.enum.game_phase import GamePhase
from ai_rpg_world.domain.world_graph.event.spot_graph_event import (
    GamePhaseChangedEvent,
)
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId
from ai_rpg_world.infrastructure.repository.in_memory_player_status_repository import (
    InMemoryPlayerStatusRepository,
)


_SCENARIO = (
    Path(__file__).resolve().parents[3]
    / "tests"
    / "fixtures"
    / "scenarios"
    / "darkened_station.json"
)
_DRILL = Path(__file__).resolve().parents[3] / "data" / "scenarios" / "station_drill.json"
_MORI = PlayerId(1)
_SENA = PlayerId(2)
_KUZE = PlayerId(3)
_AOI = PlayerId(4)


def _runtime():
    return create_world_runtime(_SCENARIO)


def _spot_of(runtime, player_id: PlayerId) -> SpotId:
    return runtime._spot_graph_repo.find_graph().get_entity_spot(
        EntityId.create(int(player_id))
    )


def _scatter(runtime) -> None:
    graph = runtime._spot_graph_repo.find_graph()
    for player_id, spot_name in (
        (_MORI, "storage"),
        (_SENA, "corridor"),
        (_AOI, "radio_room"),
    ):
        graph.unplace_entity(EntityId.create(int(player_id)))
        graph.place_entity(
            EntityId.create(int(player_id)),
            SpotId.create(runtime.id_mapper.get_int("spot", spot_name)),
        )
    runtime._spot_graph_repo.save(graph)


def _dispatcher(runtime):
    return runtime._meeting_command_service._command_scope_factory._sync_dispatcher


def _fail_before_commit(runtime, message: str) -> list[GamePhaseChangedEvent]:
    delivered: list[GamePhaseChangedEvent] = []
    dispatcher = _dispatcher(runtime)
    dispatcher.register_required_before_commit(
        GamePhaseChangedEvent,
        lambda event, context: (_ for _ in ()).throw(RuntimeError(message)),
    )
    dispatcher.register_after_commit(
        GamePhaseChangedEvent,
        delivered.append,
        channel=DeliveryChannel.OBSERVATION,
        guarantee=DeliveryGuarantee.BEST_EFFORT,
    )
    return delivered


def test_success_event_observes_committed_phase_and_gathering() -> None:
    """会議開始観測が届く時点ではフェーズと全生存者の集合が確定済みである。"""
    runtime = _runtime()
    _scatter(runtime)
    observations: list[tuple[GamePhase, bool]] = []
    _dispatcher(runtime).register_after_commit(
        GamePhaseChangedEvent,
        lambda _: observations.append(
            (
                runtime._game_phase_store.current.phase,
                len({_spot_of(runtime, pid) for pid in (_MORI, _SENA, _KUZE, _AOI)})
                == 1,
            )
        ),
        channel=DeliveryChannel.OBSERVATION,
        guarantee=DeliveryGuarantee.BEST_EFFORT,
    )

    result = runtime.call_emergency_meeting(_KUZE)

    assert result.success is True
    assert observations == [(GamePhase.MEETING, True)]


def test_sync_failure_rolls_back_button_phase_gathering_and_navigation() -> None:
    """commit前必須処理が失敗すると持ち札・フェーズ・位置・移動状態を戻す。"""
    runtime = _runtime()
    _scatter(runtime)
    runtime.do_move(_SENA, "generator_room")
    runtime.advance_tick()
    before_spots = {
        player_id: _spot_of(runtime, player_id)
        for player_id in (_MORI, _SENA, _KUZE, _AOI)
    }
    before_navigation = runtime._player_status_repo.find_by_id(
        _SENA
    ).spot_navigation_state
    runtime._game_phase_store.cast_vote(_MORI, _SENA)
    delivered = _fail_before_commit(runtime, "meeting sync failed")

    with pytest.raises(RuntimeError, match="meeting sync failed"):
        runtime.call_emergency_meeting(_KUZE)

    assert runtime._game_phase_store.current.phase is GamePhase.FREE_ROAM
    assert runtime._game_phase_store.has_emergency_button(_KUZE) is True
    assert runtime._game_phase_store.ballots == {int(_MORI): int(_SENA)}
    assert {
        player_id: _spot_of(runtime, player_id)
        for player_id in (_MORI, _SENA, _KUZE, _AOI)
    } == before_spots
    assert (
        runtime._player_status_repo.find_by_id(_SENA).spot_navigation_state
        == before_navigation
    )
    assert delivered == []


def test_body_report_failure_does_not_mark_the_body_as_reported() -> None:
    """死体報告のcommit前失敗では報告済み印と会議フェーズを残さない。"""
    runtime = _runtime()
    graph = runtime._spot_graph_repo.find_graph()
    graph.unplace_entity(EntityId.create(int(_SENA)))
    graph.place_entity(EntityId.create(int(_SENA)), _spot_of(runtime, _MORI))
    runtime._spot_graph_repo.save(graph)
    status = runtime._player_status_repo.find_by_id(_SENA)
    status.apply_damage(status.hp.value)
    events = tuple(status.get_events())
    status.clear_events()
    runtime._player_status_repo.save(status)
    runtime._speech_event_publisher.publish_all(events)
    _fail_before_commit(runtime, "body report sync failed")

    with pytest.raises(RuntimeError, match="body report sync failed"):
        runtime.report_body(_MORI, _SENA)

    assert runtime._game_phase_store.current.phase is GamePhase.FREE_ROAM
    assert runtime._game_phase_store.is_body_reported(_SENA) is False


def test_sync_failure_rolls_back_meeting_condition_resolution() -> None:
    """会議開始の必須処理が失敗すると異常flagの解決も開始前へ戻す。"""
    runtime = create_world_runtime(_DRILL)
    terminal_spec = ItemSpecId.create(
        runtime.id_mapper.get_int("item_spec", "control_terminal")
    )
    runtime.do_interact_with_item(_KUZE, terminal_spec, "freeze_fuel")
    runtime.do_interact_with_player(_KUZE, _MORI, "strike_down")
    _fail_before_commit(runtime, "meeting resolution sync failed")

    with pytest.raises(RuntimeError, match="meeting resolution sync failed"):
        runtime.report_body(_SENA, _MORI)

    flags = runtime._world_flag_state.as_frozen_set()
    assert "fuel_frozen" in flags
    assert "fuel_restored" not in flags
    assert runtime._game_phase_store.current.phase is GamePhase.FREE_ROAM


def test_status_save_failure_rolls_back_every_gathered_player(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """一人の移動状態保存に失敗してもgraphだけを集合済みにせず全体を戻す。"""
    runtime = _runtime()
    _scatter(runtime)
    before_spots = {
        player_id: _spot_of(runtime, player_id)
        for player_id in (_MORI, _SENA, _KUZE, _AOI)
    }
    original_save = InMemoryPlayerStatusRepository.save

    def save_then_fail(self, status) -> None:
        original_save(self, status)
        if status.player_id == _MORI:
            raise RuntimeError("meeting status save failed")

    monkeypatch.setattr(InMemoryPlayerStatusRepository, "save", save_then_fail)

    with pytest.raises(RuntimeError, match="meeting status save failed"):
        runtime.call_emergency_meeting(_KUZE)

    assert runtime._game_phase_store.current.phase is GamePhase.FREE_ROAM
    assert runtime._game_phase_store.has_emergency_button(_KUZE) is True
    assert {
        player_id: _spot_of(runtime, player_id)
        for player_id in (_MORI, _SENA, _KUZE, _AOI)
    } == before_spots


def test_button_interaction_finishes_with_the_meeting_command(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """会議確定後に外側interactionのgraph保存を続けず部分適用を作らない。"""
    runtime = _runtime()
    save_calls = 0
    original_save = runtime._spot_graph_repo.save

    def fail_on_second_save(graph) -> None:
        nonlocal save_calls
        save_calls += 1
        if save_calls == 2:
            raise RuntimeError("outer graph save failed")
        original_save(graph)

    monkeypatch.setattr(runtime._spot_graph_repo, "save", fail_on_second_save)

    result = runtime.do_interact(
        _KUZE,
        "emergency_button",
        "press_emergency_button",
    )

    assert result.action_display_label == "緊急招集ボタンを押す"
    assert runtime._game_phase_store.current.phase is GamePhase.MEETING
    assert runtime._game_phase_store.has_emergency_button(_KUZE) is False
    assert save_calls == 1


def test_trace_observer_failure_does_not_turn_commit_into_command_failure(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """確定後traceが失敗しても会議開始の成功結果と確定状態を維持する。"""
    runtime = _runtime()
    runtime._meeting_command_service._meeting_committed_observer = (
        lambda _: (_ for _ in ()).throw(RuntimeError("trace observer failed"))
    )

    result = runtime.call_emergency_meeting(_KUZE)

    assert result.success is True
    assert runtime._game_phase_store.current.phase is GamePhase.MEETING
    assert runtime._game_phase_store.has_emergency_button(_KUZE) is False
    assert "会議開始後のtrace記録に失敗しました" in caplog.text
