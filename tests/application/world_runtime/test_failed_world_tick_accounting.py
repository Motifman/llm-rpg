"""失敗した world tick でも確定済みの時間と移動計測を失わないことを保証する。"""

from pathlib import Path

import pytest

from ai_rpg_world.application.common.exceptions import (
    CommandPostCommitException,
    SystemErrorException,
)
from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime


_REPO_ROOT = Path(__file__).resolve().parents[3]


class _FailingStage:
    def run(self, _current_tick) -> None:
        raise RuntimeError("later stage failed")


def test_failed_tick_updates_runtime_clock_and_tick_limit() -> None:
    """後段失敗でも消費したtickを残量表示と終了判定へ反映する。"""
    runtime = create_world_runtime(
        _REPO_ROOT / "data" / "scenarios" / "relay_puzzle_demo.json"
    )
    runtime._time_provider.advance_tick(49)
    runtime._tick = 49
    runtime._simulation_service._scenario_event_stage = _FailingStage()

    with pytest.raises(SystemErrorException, match="later stage failed"):
        runtime.advance_tick()

    assert runtime.current_tick() == 50
    assert runtime._tick == 50
    assert runtime._compute_tick_budget_remaining() == 0
    assert runtime.check_game_end().is_ended is True


def test_travel_metric_survives_a_later_stage_failure() -> None:
    """移動command確定後の後段失敗でも、そのplayerの移動1tickを記録する。"""
    runtime = create_world_runtime(
        _REPO_ROOT / "data" / "scenarios" / "forbidden_library_demo.json"
    )
    player_id = runtime.get_player_ids()[0]
    runtime.do_move(player_id, "reading_room")
    runtime._simulation_service._scenario_event_stage = _FailingStage()

    with pytest.raises(SystemErrorException, match="later stage failed"):
        runtime.advance_tick()

    assert runtime._cumulative_travel_ticks_by_player[int(player_id)] == 1


def test_travel_metric_survives_committed_cleanup_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """移動commit後の資源解放失敗でも、確定済みの移動1tickを記録する。"""
    runtime = create_world_runtime(
        _REPO_ROOT / "data" / "scenarios" / "forbidden_library_demo.json"
    )
    player_id = runtime.get_player_ids()[0]
    runtime.do_move(player_id, "reading_room")
    data_store = runtime._player_status_repo._data_store
    original_release = data_store.release_uow_transaction

    def release_then_fail() -> None:
        original_release()
        raise RuntimeError("transaction release failed")

    monkeypatch.setattr(data_store, "release_uow_transaction", release_then_fail)

    with pytest.raises(CommandPostCommitException):
        runtime.advance_tick()

    status = runtime._player_status_repo.find_by_id(player_id)
    assert status is not None
    assert status.spot_navigation_state is not None
    assert not status.spot_navigation_state.is_traveling
    assert runtime._cumulative_travel_ticks_by_player[int(player_id)] == 1


def test_arrival_read_failure_does_not_hide_committed_cleanup_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """確定後の到着確認も失敗した場合、元のcommit後例外を維持する。"""
    runtime = create_world_runtime(
        _REPO_ROOT / "data" / "scenarios" / "forbidden_library_demo.json"
    )
    player_id = runtime.get_player_ids()[0]
    runtime.do_move(player_id, "reading_room")
    runtime._travel_stage.set_on_arrival(lambda _player_id: None)
    repository = runtime._travel_stage._player_status_repository
    original_find = repository.find_by_id
    data_store = runtime._player_status_repo._data_store
    original_release = data_store.release_uow_transaction

    def arrival_read_fails(_player_id):
        raise LookupError("arrival read failed")

    def release_then_fail() -> None:
        original_release()
        monkeypatch.setattr(repository, "find_by_id", arrival_read_fails)
        raise RuntimeError("transaction release failed")

    monkeypatch.setattr(data_store, "release_uow_transaction", release_then_fail)

    with pytest.raises(CommandPostCommitException):
        runtime.advance_tick()

    monkeypatch.setattr(repository, "find_by_id", original_find)
    status = repository.find_by_id(player_id)
    assert status is not None
    assert status.spot_navigation_state is not None
    assert not status.spot_navigation_state.is_traveling
    assert runtime._cumulative_travel_ticks_by_player[int(player_id)] == 1
