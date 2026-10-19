"""death graceをplayer単位で確定し、退場状態と通知を分離する。"""

import logging
from pathlib import Path
from typing import Any
from unittest.mock import Mock

import pytest
from tests.runtime_config_helpers import runtime_config

from ai_rpg_world.application.common.exceptions import CommandPostCommitException
from ai_rpg_world.application.player.services.player_death_grace_tick_stage import (
    PlayerDeathGraceTickStage,
)
from ai_rpg_world.application.player.services.player_death_grace_timer import (
    PlayerDeathGraceTimer,
)
from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime
from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.player.enum.player_outcome_enum import PlayerOutcomeEnum
from ai_rpg_world.domain.player.service.player_outcome_registry import (
    PlayerOutcomeRegistry,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.value_object.spot_id import SpotId

_SCENARIO = Path("data/scenarios/forbidden_library_demo.json")
_BODY_SPOT = SpotId(1)


def _runtime() -> Any:
    return create_world_runtime(
        _SCENARIO,
        config=runtime_config(scenario_random_seed=42),
    )


def _stage(runtime: Any) -> Any:
    return runtime._simulation_service._death_grace_stage


def _prepare_overdue_status(runtime: Any, player_id: PlayerId) -> None:
    status = runtime._player_status_repo.find_by_id(player_id)
    if not status.is_down:
        status.apply_damage(status.hp.value)
        status.clear_events()
        runtime._player_status_repo.save(status)
    runtime._death_grace_timer.register(player_id, downed_at_tick=0)


def _prepare_overdue(runtime: Any, player_id: PlayerId) -> None:
    _prepare_overdue_status(runtime, player_id)
    runtime._fallen_body_registry.record(
        player_id,
        _BODY_SPOT,
        WorldTick(0),
    )


def _deadline(runtime: Any) -> WorldTick:
    return WorldTick(_stage(runtime)._grace_ticks)


def test_missing_scope_rejects_before_reading_the_timer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """確定区間未配線なら期限超過候補を読む前にstageを拒否する。"""
    timer = PlayerDeathGraceTimer()
    overdue_players = Mock(
        side_effect=AssertionError("未配線時にtimerを読んではならない")
    )
    monkeypatch.setattr(timer, "overdue_players", overdue_players)
    stage = PlayerDeathGraceTickStage(
        outcome_registry=PlayerOutcomeRegistry.new_for_players([PlayerId(1)]),
        grace_timer=timer,
        grace_ticks=30,
    )

    with pytest.raises(RuntimeError, match="CommandScopeFactoryが未配線"):
        stage.run(WorldTick(30))

    overdue_players.assert_not_called()


def test_cancel_failure_rolls_back_outcome_timer_departure_and_notification(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """timer掃除失敗ではDEAD・pending削除・退場位置・通知を全て戻す。"""
    runtime = _runtime()
    player_id = runtime.get_player_ids()[0]
    _prepare_overdue(runtime, player_id)
    observed: list[PlayerId] = []
    runtime._player_outcome_registry.register_callback(
        lambda changed_id, _old, _new: observed.append(changed_id)
    )
    original_cancel = runtime._death_grace_timer.cancel

    def cancel_then_fail(changed_id: PlayerId) -> None:
        original_cancel(changed_id)
        raise RuntimeError("grace timer cleanup failed")

    monkeypatch.setattr(runtime._death_grace_timer, "cancel", cancel_then_fail)

    with pytest.raises(RuntimeError, match="grace timer cleanup failed"):
        _stage(runtime).run(_deadline(runtime))

    assert (
        runtime._player_outcome_registry.get_outcome(player_id)
        is PlayerOutcomeEnum.UNRESOLVED
    )
    assert runtime._death_grace_timer.is_pending(player_id)
    assert runtime._departed_position_store.find(player_id) is None
    assert observed == []


def test_success_notifies_after_all_departure_state_is_committed() -> None:
    """DEAD通知はoutcome・timer・退場位置が全て確定した後に届く。"""
    runtime = _runtime()
    player_id = runtime.get_player_ids()[0]
    _prepare_overdue(runtime, player_id)
    observed: list[tuple[PlayerOutcomeEnum, bool, SpotId | None]] = []

    def observe(changed_id: PlayerId, _old: Any, _new: Any) -> None:
        observed.append(
            (
                runtime._player_outcome_registry.get_outcome(changed_id),
                runtime._death_grace_timer.is_pending(changed_id),
                runtime._departed_position_store.find(changed_id),
            )
        )

    runtime._player_outcome_registry.register_callback(observe)

    _stage(runtime).run(_deadline(runtime))

    assert observed == [(PlayerOutcomeEnum.DEAD, False, _BODY_SPOT)]


def test_committed_player_survives_later_player_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """先行playerの死亡確定は、後続playerの失敗で巻き戻されない。"""
    runtime = _runtime()
    first, second = runtime.get_player_ids()[:2]
    _prepare_overdue(runtime, first)
    _prepare_overdue(runtime, second)
    observed: list[PlayerId] = []
    runtime._player_outcome_registry.register_callback(
        lambda changed_id, _old, _new: observed.append(changed_id)
    )
    original_cancel = runtime._death_grace_timer.cancel

    def fail_second(changed_id: PlayerId) -> None:
        original_cancel(changed_id)
        if changed_id == second:
            raise RuntimeError("second player failed")

    monkeypatch.setattr(runtime._death_grace_timer, "cancel", fail_second)

    with pytest.raises(RuntimeError, match="second player failed"):
        _stage(runtime).run(_deadline(runtime))

    assert runtime._player_outcome_registry.get_outcome(first) is PlayerOutcomeEnum.DEAD
    assert not runtime._death_grace_timer.is_pending(first)
    assert runtime._departed_position_store.find(first) == _BODY_SPOT
    assert (
        runtime._player_outcome_registry.get_outcome(second)
        is PlayerOutcomeEnum.UNRESOLVED
    )
    assert runtime._death_grace_timer.is_pending(second)
    assert runtime._departed_position_store.find(second) is None
    assert observed == [first]


def test_stale_overdue_candidate_is_rechecked_inside_scope(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """scope待機中に蘇生済みとなった候補を古い一覧からDEADにしない。"""
    runtime = _runtime()
    player_id = runtime.get_player_ids()[0]
    monkeypatch.setattr(
        runtime._death_grace_timer,
        "overdue_players",
        lambda **_kwargs: [player_id],
    )

    _stage(runtime).run(_deadline(runtime))

    assert (
        runtime._player_outcome_registry.get_outcome(player_id)
        is PlayerOutcomeEnum.UNRESOLVED
    )
    assert runtime._departed_position_store.find(player_id) is None


def test_revived_status_repairs_stale_timer_from_legacy_partial_state() -> None:
    """旧経路で蘇生だけ確定した状態も、生存者をDEADにせず掃除する。"""
    runtime = _runtime()
    player_id = runtime.get_player_ids()[0]
    _prepare_overdue(runtime, player_id)
    status = runtime._player_status_repo.find_by_id(player_id)
    status.revive(hp_recovery_rate=0.4)
    status.clear_events()
    runtime._player_status_repo.save(status)

    assert not runtime._player_status_repo.find_by_id(player_id).is_down
    assert runtime._death_grace_timer.is_pending(player_id)
    # statusだけ保存された旧pipelineの部分適用を直接構築する。現在の正規command
    # ではtimer取消失敗時にstatusもrollbackされるため、この状態は作られない。
    assert runtime._fallen_body_registry.find(player_id) is not None

    _stage(runtime).run(_deadline(runtime))

    assert (
        runtime._player_outcome_registry.get_outcome(player_id)
        is PlayerOutcomeEnum.UNRESOLVED
    )
    assert not runtime._death_grace_timer.is_pending(player_id)
    assert runtime._fallen_body_registry.find(player_id) is None
    assert runtime._departed_position_store.find(player_id) is None


def test_missing_body_commits_death_and_timer_cleanup_with_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """身体記録欠落でも死亡とpending掃除を確定し、退場位置欠落を警告する。"""
    runtime = _runtime()
    player_id = runtime.get_player_ids()[0]
    _prepare_overdue_status(runtime, player_id)

    with caplog.at_level(logging.WARNING):
        _stage(runtime).run(_deadline(runtime))

    assert runtime._player_outcome_registry.get_outcome(player_id) is PlayerOutcomeEnum.DEAD
    assert not runtime._death_grace_timer.is_pending(player_id)
    assert runtime._departed_position_store.find(player_id) is None
    assert "has no fallen-body record" in caplog.text


def test_resolved_player_clears_only_pending_timer_inside_scope() -> None:
    """既にRESCUEDのplayerは結果を塗り替えず、期限切れpendingだけを掃除する。"""
    runtime = _runtime()
    player_id = runtime.get_player_ids()[0]
    _prepare_overdue(runtime, player_id)
    runtime._player_outcome_registry.set_outcome(
        player_id,
        PlayerOutcomeEnum.RESCUED,
    )
    observed: list[PlayerId] = []
    runtime._player_outcome_registry.register_callback(
        lambda changed_id, _old, _new: observed.append(changed_id)
    )

    _stage(runtime).run(_deadline(runtime))

    assert (
        runtime._player_outcome_registry.get_outcome(player_id)
        is PlayerOutcomeEnum.RESCUED
    )
    assert not runtime._death_grace_timer.is_pending(player_id)
    assert runtime._departed_position_store.find(player_id) is None
    assert observed == []


def test_post_commit_cleanup_failure_notifies_and_preserves_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """commit済みcleanup失敗では死亡を通知して専用例外を維持する。"""
    runtime = _runtime()
    player_id = runtime.get_player_ids()[0]
    _prepare_overdue(runtime, player_id)
    observed: list[PlayerId] = []
    runtime._player_outcome_registry.register_callback(
        lambda changed_id, _old, _new: observed.append(changed_id)
    )
    data_store = runtime._item_repo._data_store
    original_release = data_store.release_uow_transaction

    def release_then_fail() -> None:
        original_release()
        raise RuntimeError("death grace cleanup failed")

    monkeypatch.setattr(data_store, "release_uow_transaction", release_then_fail)

    with pytest.raises(CommandPostCommitException):
        _stage(runtime).run(_deadline(runtime))

    assert runtime._player_outcome_registry.get_outcome(player_id) is PlayerOutcomeEnum.DEAD
    assert not runtime._death_grace_timer.is_pending(player_id)
    assert runtime._departed_position_store.find(player_id) == _BODY_SPOT
    assert observed == [player_id]


def test_runtime_wires_all_death_grace_rollback_resources() -> None:
    """本番factoryはoutcome・timer・退場位置の共有instanceを参加させる。"""
    runtime = _runtime()
    factory = _stage(runtime)._command_scope_factory
    resources = {
        participant.rollback_resource
        for participant in factory._transaction_factory._participants
    }

    assert runtime._player_outcome_registry in resources
    assert runtime._death_grace_timer in resources
    assert runtime._fallen_body_registry in resources
    assert runtime._departed_position_store in resources
