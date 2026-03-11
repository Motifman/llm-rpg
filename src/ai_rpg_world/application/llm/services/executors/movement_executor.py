"""
Movement ツール（to_destination, pursuit_start, pursuit_cancel）の実行。

ToolCommandMapper のサブマッパーとして、移動・追跡関連のツール実行のみを担当する。
"""

from typing import Any, Callable, Dict, Optional

from ai_rpg_world.application.llm.contracts.dtos import LlmCommandResultDto
from ai_rpg_world.application.llm.remediation_mapping import get_remediation
from ai_rpg_world.application.llm.services.tool_executor_helpers import exception_result, unknown_tool
from ai_rpg_world.application.llm.tool_constants import (
    TOOL_NAME_MOVE_TO_DESTINATION,
    TOOL_NAME_PURSUIT_CANCEL,
    TOOL_NAME_PURSUIT_START,
)
from ai_rpg_world.application.world.contracts.commands import (
    CancelPursuitCommand,
    StartPursuitCommand,
)
from ai_rpg_world.application.world.contracts.dtos import (
    MoveResultDto,
    PursuitCommandResultDto,
)
from ai_rpg_world.application.world.services.movement_service import (
    MovementApplicationService,
)


class MovementToolExecutor:
    """
    Movement ツールの実行を担当するサブマッパー。

    get_handlers() でツール名→ハンドラの辞書を返す。
    movement_service は必須。pursuit_service はオプション（None の場合は pursuit 系は空）。
    """

    def __init__(
        self,
        movement_service: MovementApplicationService,
        pursuit_service: Optional[Any] = None,
    ) -> None:
        move_to_destination = getattr(movement_service, "move_to_destination", None)
        if not callable(move_to_destination):
            raise TypeError("movement_service must have a callable move_to_destination")
        if pursuit_service is not None and not callable(
            getattr(pursuit_service, "start_pursuit", None)
        ):
            raise TypeError("pursuit_service must have a callable start_pursuit")
        if pursuit_service is not None and not callable(
            getattr(pursuit_service, "cancel_pursuit", None)
        ):
            raise TypeError("pursuit_service must have a callable cancel_pursuit")
        self._movement_service = movement_service
        self._pursuit_service = pursuit_service

    def get_handlers(self) -> Dict[str, Callable[[int, Dict[str, Any]], LlmCommandResultDto]]:
        """利用可能なツール名→ハンドラの辞書を返す。"""
        result: Dict[str, Callable[[int, Dict[str, Any]], LlmCommandResultDto]] = {
            TOOL_NAME_MOVE_TO_DESTINATION: self._execute_move_to_destination,
        }
        if self._pursuit_service is not None:
            result[TOOL_NAME_PURSUIT_START] = self._execute_pursuit_start
            result[TOOL_NAME_PURSUIT_CANCEL] = self._execute_pursuit_cancel
        return result

    def _execute_move_to_destination(
        self,
        player_id: int,
        args: Dict[str, Any],
    ) -> LlmCommandResultDto:
        try:
            destination_type = args.get("destination_type")
            target_spot_id = args.get("target_spot_id")
            target_location_area_id = args.get("target_location_area_id")
            target_world_object_id = args.get("target_world_object_id")
            target_spot_id_int = int(target_spot_id) if isinstance(target_spot_id, (int, float)) else 0
            target_location_area_id_opt: Optional[int] = None
            if destination_type == "location" and target_location_area_id is not None:
                target_location_area_id_opt = (
                    int(target_location_area_id)
                    if isinstance(target_location_area_id, (int, float))
                    else None
                )
            target_world_object_id_opt: Optional[int] = None
            if destination_type == "object" and target_world_object_id is not None:
                target_world_object_id_opt = (
                    int(target_world_object_id)
                    if isinstance(target_world_object_id, (int, float))
                    else None
                )
            result: MoveResultDto = self._movement_service.move_to_destination(
                player_id=player_id,
                destination_type=destination_type,  # type: ignore[arg-type]
                target_spot_id=target_spot_id_int,
                target_location_area_id=target_location_area_id_opt,
                target_world_object_id=target_world_object_id_opt,
            )
            return LlmCommandResultDto(
                success=result.success,
                message=result.message if result.success else (result.error_message or result.message),
            )
        except Exception as e:
            error_code = getattr(e, "error_code", "SYSTEM_ERROR")
            return LlmCommandResultDto(
                success=False,
                message=str(e),
                error_code=error_code,
                remediation=get_remediation(error_code),
            )

    def _execute_pursuit_start(
        self,
        player_id: int,
        args: Dict[str, Any],
    ) -> LlmCommandResultDto:
        if self._pursuit_service is None:
            return unknown_tool("追跡開始ツールはまだ利用できません。")
        try:
            target_world_object_id = args.get("target_world_object_id")
            result: PursuitCommandResultDto = self._pursuit_service.start_pursuit(
                StartPursuitCommand(
                    player_id=player_id,
                    target_world_object_id=(
                        int(target_world_object_id)
                        if isinstance(target_world_object_id, (int, float))
                        else 0
                    ),
                )
            )
            return LlmCommandResultDto(
                success=result.success,
                message=result.message,
                was_no_op=result.no_op,
            )
        except Exception as e:
            return exception_result(e)

    def _execute_pursuit_cancel(
        self,
        player_id: int,
        args: Dict[str, Any],
    ) -> LlmCommandResultDto:
        del args
        if self._pursuit_service is None:
            return unknown_tool("追跡中断ツールはまだ利用できません。")
        try:
            result: PursuitCommandResultDto = self._pursuit_service.cancel_pursuit(
                CancelPursuitCommand(player_id=player_id)
            )
            return LlmCommandResultDto(
                success=result.success,
                message=result.message,
                was_no_op=result.no_op,
            )
        except Exception as e:
            return exception_result(e)
