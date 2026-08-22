"""天候・昼夜遷移の確定境界契約。"""

import random

import pytest

from ai_rpg_world.application.common.command_scope_factory import CommandScopeFactory
from ai_rpg_world.application.common.exceptions import (
    CommandPostCommitException,
    TransactionCommittedCleanupException,
)
from ai_rpg_world.application.world_graph.spot_graph_day_night_stage_service import (
    SpotGraphDayNightStageService,
)
from ai_rpg_world.application.world_graph.spot_graph_environment_stage_service import (
    SpotGraphEnvironmentStageService,
)
from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.world.enum.weather_enum import WeatherTypeEnum
from ai_rpg_world.domain.world.value_object.weather_state import WeatherState
from ai_rpg_world.domain.world_graph.value_object.day_night_cycle_def import (
    DayNightCycleDef,
)
from ai_rpg_world.domain.world_graph.value_object.day_night_phase_def import (
    DayNightPhaseDef,
)
from ai_rpg_world.infrastructure.events.command_event_dispatcher import (
    CommandEventDispatcher,
)
from ai_rpg_world.infrastructure.unit_of_work.interaction_rollback_participants import (
    build_day_night_rollback_participants,
    build_weather_rollback_participants,
)
from ai_rpg_world.infrastructure.unit_of_work.rollback_participant_transaction_adapter import (
    RollbackParticipantTransactionFactory,
)


class _Transaction:
    """commit故障を注入できる最小transaction。"""

    def __init__(
        self,
        *,
        fail_commit: bool = False,
        fail_after_commit: bool = False,
    ) -> None:
        self._active = False
        self._fail_commit = fail_commit
        self._fail_after_commit = fail_after_commit

    @property
    def is_active(self) -> bool:
        return self._active

    def begin(self) -> None:
        self._active = True

    def commit(self) -> None:
        if self._fail_commit:
            raise RuntimeError("environment commit failed")
        self._active = False
        if self._fail_after_commit:
            raise TransactionCommittedCleanupException(
                cleanup_error=RuntimeError("environment cleanup failed")
            )

    def rollback(self) -> None:
        self._active = False


class _TransactionFactory:
    def __init__(
        self,
        *,
        fail_commit: bool = False,
        fail_after_commit: bool = False,
    ) -> None:
        self._fail_commit = fail_commit
        self._fail_after_commit = fail_after_commit

    def create(self) -> _Transaction:
        return _Transaction(
            fail_commit=self._fail_commit,
            fail_after_commit=self._fail_after_commit,
        )


def _scope_factory(
    *,
    participants,
    fail_commit: bool = False,
    fail_after_commit: bool = False,
):
    dispatcher = CommandEventDispatcher()
    return CommandScopeFactory[object](
        RollbackParticipantTransactionFactory(
            _TransactionFactory(
                fail_commit=fail_commit,
                fail_after_commit=fail_after_commit,
            ),
            participants=participants,
        ),
        sync_dispatcher=dispatcher,
        after_commit_handoff=dispatcher,
    )


def _day_night_cycle() -> DayNightCycleDef:
    return DayNightCycleDef(
        ticks_per_day=4,
        starting_tick_in_day=0,
        phases=(
            DayNightPhaseDef(
                name="day",
                start_ratio=0.0,
                display_text="昼",
                ambient_light=1.0,
                is_dark=False,
            ),
            DayNightPhaseDef(
                name="night",
                start_ratio=0.5,
                display_text="夜",
                ambient_light=0.1,
                is_dark=True,
            ),
        ),
    )


def test_weather_callback_observes_committed_state() -> None:
    """天候callbackは新しい天候が確定した後にだけ呼ばれる。"""
    holder = {
        "state": WeatherState(WeatherTypeEnum.CLEAR, 0.5),
    }
    observed: list[tuple[WeatherState, WeatherState]] = []
    stage = SpotGraphEnvironmentStageService(
        weather_state_provider=lambda: holder["state"],
        weather_state_setter=lambda state: holder.__setitem__("state", state),
        update_interval_ticks=1,
        random_source=random.Random(181),
        on_weather_changed=lambda state: observed.append((state, holder["state"])),
    )
    stage.set_command_scope_factory(
        _scope_factory(
            participants=build_weather_rollback_participants(stage=stage),
        )
    )

    stage.run(WorldTick(1))

    assert observed == [(holder["state"], holder["state"])]


def test_weather_commit_failure_restores_state_rng_and_skips_callback() -> None:
    """天候commit失敗は現天候・乱数位置を戻し、成功callbackを呼ばない。"""
    original = WeatherState(WeatherTypeEnum.CLEAR, 0.5)
    holder = {"state": original}
    observed: list[WeatherState] = []
    stage = SpotGraphEnvironmentStageService(
        weather_state_provider=lambda: holder["state"],
        weather_state_setter=lambda state: holder.__setitem__("state", state),
        update_interval_ticks=1,
        random_source=random.Random(181),
        on_weather_changed=observed.append,
    )
    original_rng = stage.random_state()
    stage.set_command_scope_factory(
        _scope_factory(
            participants=build_weather_rollback_participants(stage=stage),
            fail_commit=True,
        )
    )

    with pytest.raises(RuntimeError, match="environment commit failed"):
        stage.run(WorldTick(1))

    assert holder["state"] == original
    assert stage.random_state() == original_rng
    assert observed == []


def test_weather_callback_failure_keeps_committed_transition() -> None:
    """確定後の天候callback失敗は遷移成功を失敗へ変えない。"""
    original = WeatherState(WeatherTypeEnum.CLEAR, 0.5)
    holder = {"state": original}
    stage = SpotGraphEnvironmentStageService(
        weather_state_provider=lambda: holder["state"],
        weather_state_setter=lambda state: holder.__setitem__("state", state),
        update_interval_ticks=1,
        random_source=random.Random(181),
        on_weather_changed=lambda _state: (_ for _ in ()).throw(
            RuntimeError("weather observation failed")
        ),
    )
    stage.set_command_scope_factory(
        _scope_factory(
            participants=build_weather_rollback_participants(stage=stage),
        )
    )

    stage.run(WorldTick(1))

    assert holder["state"] != original


def test_weather_post_commit_failure_still_notifies_committed_transition() -> None:
    """commit済み後処理失敗でも天候を通知し、元の確定後例外を維持する。"""
    holder = {
        "state": WeatherState(WeatherTypeEnum.CLEAR, 0.5),
    }
    observed: list[WeatherState] = []
    stage = SpotGraphEnvironmentStageService(
        weather_state_provider=lambda: holder["state"],
        weather_state_setter=lambda state: holder.__setitem__("state", state),
        update_interval_ticks=1,
        random_source=random.Random(181),
        on_weather_changed=observed.append,
    )
    stage.set_command_scope_factory(
        _scope_factory(
            participants=build_weather_rollback_participants(stage=stage),
            fail_after_commit=True,
        )
    )

    with pytest.raises(CommandPostCommitException):
        stage.run(WorldTick(1))

    assert observed == [holder["state"]]


def test_day_night_callback_observes_committed_phase() -> None:
    """昼夜callbackは新しいフェーズが確定した後にだけ呼ばれる。"""
    observed: list[tuple[str, str]] = []
    stage = SpotGraphDayNightStageService(
        _day_night_cycle(),
        phase_changed_callback=lambda _old, new: observed.append(
            (new.phase_name, stage.current_time_of_day().phase_name)
        ),
    )
    stage.set_command_scope_factory(
        _scope_factory(
            participants=build_day_night_rollback_participants(stage=stage),
        )
    )

    stage.run(WorldTick(2))

    assert observed == [("night", "night")]


def test_day_night_commit_failure_restores_phase_and_skips_callback() -> None:
    """昼夜commit失敗は開始前フェーズへ戻り、成功callbackを呼ばない。"""
    observed: list[str] = []
    stage = SpotGraphDayNightStageService(
        _day_night_cycle(),
        phase_changed_callback=lambda _old, new: observed.append(new.phase_name),
    )
    stage.set_command_scope_factory(
        _scope_factory(
            participants=build_day_night_rollback_participants(stage=stage),
            fail_commit=True,
        )
    )

    with pytest.raises(RuntimeError, match="environment commit failed"):
        stage.run(WorldTick(2))

    assert stage.current_time_of_day().phase_name == "day"
    assert observed == []


def test_day_night_callback_failure_keeps_committed_phase() -> None:
    """確定後の昼夜callback失敗はフェーズ遷移成功を失敗へ変えない。"""
    stage = SpotGraphDayNightStageService(
        _day_night_cycle(),
        phase_changed_callback=lambda _old, _new: (_ for _ in ()).throw(
            RuntimeError("day/night observation failed")
        ),
    )
    stage.set_command_scope_factory(
        _scope_factory(
            participants=build_day_night_rollback_participants(stage=stage),
        )
    )

    stage.run(WorldTick(2))

    assert stage.current_time_of_day().phase_name == "night"


def test_day_night_post_commit_failure_still_notifies_committed_phase() -> None:
    """commit済み後処理失敗でも昼夜変更を通知し、確定後例外を維持する。"""
    observed: list[str] = []
    stage = SpotGraphDayNightStageService(
        _day_night_cycle(),
        phase_changed_callback=lambda _old, new: observed.append(new.phase_name),
    )
    stage.set_command_scope_factory(
        _scope_factory(
            participants=build_day_night_rollback_participants(stage=stage),
            fail_after_commit=True,
        )
    )

    with pytest.raises(CommandPostCommitException):
        stage.run(WorldTick(2))

    assert stage.current_time_of_day().phase_name == "night"
    assert observed == ["night"]
