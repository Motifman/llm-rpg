"""移動系ツールの定義（no_op, move_to_destination, move_one_step, cancel_movement）。"""

from typing import List, Tuple

from ai_rpg_world.application.llm.contracts.dtos import ToolDefinitionDto
from ai_rpg_world.application.llm.contracts.interfaces import IAvailabilityResolver
from ai_rpg_world.application.llm.services.availability_resolvers import (
    CancelMovementAvailabilityResolver,
    MoveOneStepAvailabilityResolver,
    NoOpAvailabilityResolver,
    SetDestinationAvailabilityResolver,
)
from ai_rpg_world.application.llm.tool_constants import (
    TOOL_NAME_CANCEL_MOVEMENT,
    TOOL_NAME_MOVE_ONE_STEP,
    TOOL_NAME_MOVE_TO_DESTINATION,
    TOOL_NAME_NO_OP,
)

NO_OP_DEFINITION = ToolDefinitionDto(
    name=TOOL_NAME_NO_OP,
    description="何もしない。このターンは行動を起こさず待機します。",
    parameters={"type": "object", "properties": {}, "required": []},
)

MOVE_TO_DESTINATION_PARAMETERS = {
    "type": "object",
    "properties": {
        "destination_label": {
            "type": "string",
            "description": "現在の状況に表示された移動先ラベル（例: S1）。",
        },
    },
    "required": ["destination_label"],
}

MOVE_TO_DESTINATION_DEFINITION = ToolDefinitionDto(
    name=TOOL_NAME_MOVE_TO_DESTINATION,
    description="指定した目的地（スポット、ロケーション、または視界内オブジェクト）へ移動します。",
    parameters=MOVE_TO_DESTINATION_PARAMETERS,
)

CANCEL_MOVEMENT_DEFINITION = ToolDefinitionDto(
    name=TOOL_NAME_CANCEL_MOVEMENT,
    description="設定済みの経路をキャンセルし、移動を中断します。移動中のみ利用可能です。",
    parameters={"type": "object", "properties": {}, "required": []},
)

MOVE_ONE_STEP_PARAMETERS = {
    "type": "object",
    "properties": {
        "direction_label": {
            "type": "string",
            "description": "隣接タイルへ移動する方向。北, 北東, 東, 南東, 南, 南西, 西, 北西 のいずれか。",
        },
    },
    "required": ["direction_label"],
}

MOVE_ONE_STEP_DEFINITION = ToolDefinitionDto(
    name=TOOL_NAME_MOVE_ONE_STEP,
    description="指定した方向へ隣接タイルに1歩だけ移動します。最も細かい粒度の移動です。",
    parameters=MOVE_ONE_STEP_PARAMETERS,
)


def get_movement_specs() -> List[Tuple[ToolDefinitionDto, IAvailabilityResolver]]:
    """常時登録する移動系ツールの (definition, resolver) 一覧を返す。"""
    return [
        (NO_OP_DEFINITION, NoOpAvailabilityResolver()),
        (MOVE_TO_DESTINATION_DEFINITION, SetDestinationAvailabilityResolver()),
        (MOVE_ONE_STEP_DEFINITION, MoveOneStepAvailabilityResolver()),
        (CANCEL_MOVEMENT_DEFINITION, CancelMovementAvailabilityResolver()),
    ]


__all__ = [
    "get_movement_specs",
    "NO_OP_DEFINITION",
    "MOVE_TO_DESTINATION_DEFINITION",
    "MOVE_ONE_STEP_DEFINITION",
    "CANCEL_MOVEMENT_DEFINITION",
]
