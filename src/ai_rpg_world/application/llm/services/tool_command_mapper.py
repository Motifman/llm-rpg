"""
ツール名＋引数からコマンドを組み立てて実行し、LlmCommandResultDto を返すマッパー。
"""

from typing import Any, Dict, Optional

from ai_rpg_world.application.llm.contracts.dtos import LlmCommandResultDto
from ai_rpg_world.application.llm.remediation_mapping import get_remediation
from ai_rpg_world.application.llm.tool_constants import (
    TOOL_NAME_NO_OP,
    TOOL_NAME_SET_DESTINATION,
)
from ai_rpg_world.application.world.contracts.commands import SetDestinationCommand
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
        set_destination = getattr(movement_service, "set_destination", None)
        if not callable(set_destination):
            raise TypeError("movement_service must have a callable set_destination")
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
        if tool_name == TOOL_NAME_SET_DESTINATION:
            return self._execute_set_destination(player_id, args)
        return LlmCommandResultDto(
            success=False,
            message="未知のツールです。",
            error_code="UNKNOWN_TOOL",
            remediation=get_remediation("UNKNOWN_TOOL"),
        )

    def _execute_set_destination(
        self,
        player_id: int,
        args: Dict[str, Any],
    ) -> LlmCommandResultDto:
        try:
            destination_type = args.get("destination_type")
            target_spot_id = args.get("target_spot_id")
            target_location_area_id = args.get("target_location_area_id")
            if destination_type not in ("spot", "location"):
                return LlmCommandResultDto(
                    success=False,
                    message=f"destination_type は 'spot' または 'location' で指定してください。取得値: {destination_type!r}",
                    error_code="INVALID_DESTINATION",
                    remediation=get_remediation("INVALID_DESTINATION"),
                )
            if not isinstance(target_spot_id, (int, float)) or int(target_spot_id) <= 0:
                return LlmCommandResultDto(
                    success=False,
                    message=f"target_spot_id は正の整数で指定してください。取得値: {target_spot_id!r}",
                    error_code="INVALID_DESTINATION",
                    remediation=get_remediation("INVALID_DESTINATION"),
                )
            target_spot_id_int = int(target_spot_id)
            target_location_area_id_opt: Optional[int] = None
            if destination_type == "location":
                if target_location_area_id is None:
                    return LlmCommandResultDto(
                        success=False,
                        message="destination_type が 'location' のときは target_location_area_id が必須です。",
                        error_code="INVALID_DESTINATION",
                        remediation=get_remediation("INVALID_DESTINATION"),
                    )
                if not isinstance(target_location_area_id, (int, float)) or int(target_location_area_id) <= 0:
                    return LlmCommandResultDto(
                        success=False,
                        message=f"target_location_area_id は正の整数で指定してください。取得値: {target_location_area_id!r}",
                        error_code="INVALID_DESTINATION",
                        remediation=get_remediation("INVALID_DESTINATION"),
                    )
                target_location_area_id_opt = int(target_location_area_id)

            command = SetDestinationCommand(
                player_id=player_id,
                destination_type=destination_type,  # type: ignore[arg-type]
                target_spot_id=target_spot_id_int,
                target_location_area_id=target_location_area_id_opt,
            )
            result = self._movement_service.set_destination(command)
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
