"""Issue #168 PR-3: ``MovementToolExecutor`` の失敗 DTO が learnable に
なっているか検証する。

``MoveResultDto`` には ``error_code`` フィールドが無いため、executor 入口で
ツール別の default_error_code (MOVEMENT_FAILED / MOVEMENT_INVALID /
PURSUIT_*) にフォールバックして必ず ``error_code`` + ``remediation`` を付ける
不変条件を回帰防止する。
"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock

from ai_rpg_world.application.llm.services.executors.movement_executor import (
    MovementToolExecutor,
)
from ai_rpg_world.application.world.contracts.dtos import (
    MoveResultDto,
    PursuitCommandResultDto,
)
from ai_rpg_world.domain.world.enum.world_enum import DirectionEnum


def _failing_move_result(message: str = "経路が塞がれている") -> MoveResultDto:
    return MoveResultDto(
        success=False,
        player_id=1,
        player_name="tester",
        from_spot_id=1,
        from_spot_name="A",
        to_spot_id=2,
        to_spot_name="B",
        from_coordinate={"x": 0, "y": 0, "z": 0},
        to_coordinate={"x": 1, "y": 0, "z": 0},
        moved_at=datetime.now(),
        busy_until_tick=0,
        message=message,
        error_message=message,
    )


def _success_move_result() -> MoveResultDto:
    return MoveResultDto(
        success=True,
        player_id=1,
        player_name="tester",
        from_spot_id=1,
        from_spot_name="A",
        to_spot_id=2,
        to_spot_name="B",
        from_coordinate={"x": 0, "y": 0, "z": 0},
        to_coordinate={"x": 1, "y": 0, "z": 0},
        moved_at=datetime.now(),
        busy_until_tick=10,
        message="移動成功",
        error_message=None,
    )


def _build_executor(*, with_pursuit: bool = False) -> MovementToolExecutor:
    movement = MagicMock()
    pursuit = MagicMock() if with_pursuit else None
    return MovementToolExecutor(
        movement_service=movement, pursuit_service=pursuit
    )


def _assert_learnable_failure(result, expected_error_code: str) -> None:
    assert result.success is False
    assert result.error_code == expected_error_code
    assert result.remediation, f"remediation が空: {result!r}"


class TestMoveToDestinationFailure:
    """``move_to_destination`` 失敗時の error_code 付与。"""

    def test_failing_result_yields_learnable_dto(self) -> None:
        """MoveResultDto.success=False → MOVEMENT_FAILED + remediation が必ず付く。"""
        executor = _build_executor()
        executor._movement_service.move_to_destination.return_value = (
            _failing_move_result()
        )
        result = executor._execute_move_to_destination(
            player_id=1,
            args={"destination_type": "spot", "target_spot_id": 2},
        )
        _assert_learnable_failure(result, "MOVEMENT_FAILED")
        assert "経路が塞がれている" in result.message

    def test_successful_result_passes_through(self) -> None:
        executor = _build_executor()
        executor._movement_service.move_to_destination.return_value = (
            _success_move_result()
        )
        result = executor._execute_move_to_destination(
            player_id=1,
            args={"destination_type": "spot", "target_spot_id": 2},
        )
        assert result.success is True
        assert "成功" in result.message


class TestMoveOneStepFailure:
    """``move_one_step`` 失敗時の error_code = MOVEMENT_INVALID。"""

    def test_failing_result_yields_learnable_dto(self) -> None:
        executor = _build_executor()
        executor._movement_service.move_tile.return_value = _failing_move_result(
            "その方向には移動できない"
        )
        result = executor._execute_move_one_step(
            player_id=1, args={"direction": DirectionEnum.NORTH}
        )
        _assert_learnable_failure(result, "MOVEMENT_INVALID")

    def test_invalid_direction_is_learnable(self) -> None:
        """direction が DirectionEnum でない → INVALID_DIRECTION + remediation。"""
        executor = _build_executor()
        result = executor._execute_move_one_step(
            player_id=1, args={"direction": "北"}
        )
        _assert_learnable_failure(result, "INVALID_DIRECTION")


class TestCancelMovementFailure:
    def test_failing_cancel_yields_learnable_dto(self) -> None:
        executor = _build_executor()
        executor._movement_service.cancel_movement.return_value = (
            _failing_move_result("中断できる移動が無い")
        )
        result = executor._execute_cancel_movement(player_id=1, args={})
        _assert_learnable_failure(result, "MOVEMENT_FAILED")


class TestPursuitFailures:
    def test_pursuit_start_failure_is_learnable(self) -> None:
        executor = _build_executor(with_pursuit=True)
        executor._pursuit_service.start_pursuit.return_value = (
            PursuitCommandResultDto(
                success=False,
                message="対象が視界外",
                target_world_object_id=None,
                target_display_name=None,
                no_op=False,
            )
        )
        result = executor._execute_pursuit_start(
            player_id=1, args={"target_world_object_id": 42}
        )
        _assert_learnable_failure(result, "PURSUIT_START_FAILED")
        # no_op=False が伝播
        assert result.was_no_op is False

    def test_pursuit_cancel_failure_is_learnable(self) -> None:
        executor = _build_executor(with_pursuit=True)
        executor._pursuit_service.cancel_pursuit.return_value = (
            PursuitCommandResultDto(
                success=False,
                message="追跡中ではない",
                no_op=False,
            )
        )
        result = executor._execute_pursuit_cancel(player_id=1, args={})
        _assert_learnable_failure(result, "PURSUIT_CANCEL_FAILED")

    def test_pursuit_no_op_success_is_preserved(self) -> None:
        """no_op の成功は learnable failure 化しない (success=True のまま)。"""
        executor = _build_executor(with_pursuit=True)
        executor._pursuit_service.start_pursuit.return_value = (
            PursuitCommandResultDto(
                success=True,
                message="既に追跡中",
                no_op=True,
            )
        )
        result = executor._execute_pursuit_start(
            player_id=1, args={"target_world_object_id": 42}
        )
        assert result.success is True
        assert result.was_no_op is True
        # 成功なので error_code は付かない
        assert result.error_code is None or result.error_code == ""
