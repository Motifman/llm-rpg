"""移動系ツールの引数解決。"""

from typing import Any, Dict, Optional

from ai_rpg_world.application.llm.contracts.dtos import (
    DestinationToolRuntimeTargetDto,
    MonsterToolRuntimeTargetDto,
    PlayerToolRuntimeTargetDto,
    ToolRuntimeContextDto,
)
from ai_rpg_world.application.llm.services._resolver_helpers import (
    ToolArgumentResolutionException,
    require_target_type,
)
from ai_rpg_world.application.llm.tool_constants import (
    TOOL_NAME_CANCEL_MOVEMENT,
    TOOL_NAME_MOVE_ONE_STEP,
    TOOL_NAME_MOVE_TO_DESTINATION,
    TOOL_NAME_PURSUIT_CANCEL,
    TOOL_NAME_PURSUIT_START,
)
from ai_rpg_world.domain.world.enum.world_enum import DirectionEnum


_LABEL_TO_DIRECTION = {
    "北": DirectionEnum.NORTH,
    "北東": DirectionEnum.NORTHEAST,
    "東": DirectionEnum.EAST,
    "南東": DirectionEnum.SOUTHEAST,
    "南": DirectionEnum.SOUTH,
    "南西": DirectionEnum.SOUTHWEST,
    "西": DirectionEnum.WEST,
    "北西": DirectionEnum.NORTHWEST,
}


class MovementArgumentResolver:
    """移動系ツールの引数解決。"""

    def resolve_args(
        self,
        tool_name: str,
        args: Dict[str, Any],
        runtime_context: ToolRuntimeContextDto,
    ) -> Optional[Dict[str, Any]]:
        if tool_name == TOOL_NAME_MOVE_TO_DESTINATION:
            return self._resolve_move_to_destination(args, runtime_context)
        if tool_name == TOOL_NAME_MOVE_ONE_STEP:
            return self._resolve_move_one_step(args)
        if tool_name == TOOL_NAME_PURSUIT_START:
            return self._resolve_pursuit_start(args, runtime_context)
        if tool_name == TOOL_NAME_PURSUIT_CANCEL:
            return {}
        if tool_name == TOOL_NAME_CANCEL_MOVEMENT:
            return {}
        return None

    def _resolve_move_to_destination(
        self,
        args: Dict[str, Any],
        runtime_context: ToolRuntimeContextDto,
    ) -> Dict[str, Any]:
        label = args.get("destination_label")
        if not isinstance(label, str) or not label:
            raise ToolArgumentResolutionException(
                "移動先ラベルが指定されていません。",
                "INVALID_DESTINATION_LABEL",
            )
        target = require_target_type(
            label,
            runtime_context,
            "移動先ラベル",
            (DestinationToolRuntimeTargetDto,),
            invalid_label_code="INVALID_DESTINATION_LABEL",
            invalid_kind_code="INVALID_DESTINATION_KIND",
        )
        spot_id = target.spot_id
        if spot_id is None and target.destination_type == "object":
            spot_id = runtime_context.current_spot_id
        if spot_id is None:
            raise ToolArgumentResolutionException(
                f"移動先として使えないラベルです: {label}",
                "INVALID_DESTINATION_KIND",
            )
        result: Dict[str, Any] = {
            "destination_type": target.destination_type or "spot",
            "target_spot_id": spot_id,
            "target_location_area_id": target.location_area_id,
        }
        if target.destination_type == "object" and target.world_object_id is not None:
            result["target_world_object_id"] = target.world_object_id
        return result

    def _resolve_move_one_step(self, args: Dict[str, Any]) -> Dict[str, Any]:
        label = args.get("direction_label")
        if not isinstance(label, str) or not label.strip():
            raise ToolArgumentResolutionException(
                "方向が指定されていません。北, 北東, 東, 南東, 南, 南西, 西, 北西 のいずれかを指定してください。",
                "INVALID_DIRECTION_LABEL",
            )
        label = label.strip()
        direction = _LABEL_TO_DIRECTION.get(label)
        if direction is None:
            raise ToolArgumentResolutionException(
                f"無効な方向です: {label}。北, 北東, 東, 南東, 南, 南西, 西, 北西 のいずれかを指定してください。",
                "INVALID_DIRECTION_LABEL",
            )
        return {"direction": direction}

    def _resolve_pursuit_start(
        self,
        args: Dict[str, Any],
        runtime_context: ToolRuntimeContextDto,
    ) -> Dict[str, Any]:
        label = args.get("target_label")
        if not isinstance(label, str) or not label:
            raise ToolArgumentResolutionException(
                "追跡対象ラベルが指定されていません。",
                "INVALID_TARGET_LABEL",
            )
        target = require_target_type(
            label,
            runtime_context,
            "追跡対象ラベル",
            (PlayerToolRuntimeTargetDto, MonsterToolRuntimeTargetDto),
        )
        if target.world_object_id is None:
            raise ToolArgumentResolutionException(
                f"追跡対象として解決できません: {label}",
                "INVALID_TARGET_KIND",
            )
        return {
            "target_world_object_id": target.world_object_id,
            "target_display_name": target.display_name,
        }
