"""
ツール名＋引数からコマンドを組み立てて実行し、LlmCommandResultDto を返すマッパー。
"""

from typing import Any, Dict, Optional

from ai_rpg_world.application.llm.contracts.dtos import LlmCommandResultDto
from ai_rpg_world.application.llm.remediation_mapping import get_remediation
from ai_rpg_world.application.llm.tool_constants import (
    TOOL_NAME_MOVE_TO_DESTINATION,
    TOOL_NAME_NO_OP,
)
from ai_rpg_world.application.world.contracts.dtos import MoveResultDto
from ai_rpg_world.application.world.services.movement_service import (
    MovementApplicationService,
)


class ToolCommandMapper:
    """
    ツール名と引数からコマンドを組み立て、対応するサービスを呼び出して
    LlmCommandResultDto を返す。失敗時は例外を捕捉し、error_code と remediation を付与する。
    """

    def __init__(
        self,
        movement_service: MovementApplicationService,
    ) -> None:
        move_to_destination = getattr(movement_service, "move_to_destination", None)
        if not callable(move_to_destination):
            raise TypeError("movement_service must have a callable move_to_destination")
        self._movement_service = movement_service

    def execute(
        self,
        player_id: int,
        tool_name: str,
        arguments: Optional[Dict[str, Any]] = None,
    ) -> LlmCommandResultDto:
        """
        ツールを実行し、結果を LlmCommandResultDto で返す。
        arguments は LLM の function call から渡される辞書（None の場合は {} として扱う）。
        """
        if not isinstance(player_id, int):
            raise TypeError("player_id must be int")
        if player_id <= 0:
            raise ValueError("player_id must be greater than 0")
        if not isinstance(tool_name, str):
            raise TypeError("tool_name must be str")
        if arguments is not None and not isinstance(arguments, dict):
            raise TypeError("arguments must be dict or None")
        args = arguments if arguments is not None else {}

        if tool_name == TOOL_NAME_NO_OP:
            return LlmCommandResultDto(
                success=True,
                message="何もしませんでした。",
            )
        if tool_name == TOOL_NAME_MOVE_TO_DESTINATION:
            return self._execute_move_to_destination(player_id, args)
        return LlmCommandResultDto(
            success=False,
            message="未知のツールです。",
            error_code="UNKNOWN_TOOL",
            remediation=get_remediation("UNKNOWN_TOOL"),
        )

    def _execute_move_to_destination(
        self,
        player_id: int,
        args: Dict[str, Any],
    ) -> LlmCommandResultDto:
        try:
            destination_type = args.get("destination_type")
            target_spot_id = args.get("target_spot_id")
            target_location_area_id = args.get("target_location_area_id")
            target_spot_id_int = int(target_spot_id) if isinstance(target_spot_id, (int, float)) else 0
            target_location_area_id_opt: Optional[int] = None
            if destination_type == "location" and target_location_area_id is not None:
                target_location_area_id_opt = (
                    int(target_location_area_id)
                    if isinstance(target_location_area_id, (int, float))
                    else None
                )
            result: MoveResultDto = self._movement_service.move_to_destination(
                player_id=player_id,
                destination_type=destination_type,  # type: ignore[arg-type]
                target_spot_id=target_spot_id_int,
                target_location_area_id=target_location_area_id_opt,
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
