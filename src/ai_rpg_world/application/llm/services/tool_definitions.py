"""LLM ツールの定義（名前・説明・parameters スキーマ）とデフォルト登録"""

from ai_rpg_world.application.llm.contracts.dtos import ToolDefinitionDto
from ai_rpg_world.application.llm.contracts.interfaces import IGameToolRegistry
from ai_rpg_world.application.llm.services.availability_resolvers import (
    NoOpAvailabilityResolver,
    SetDestinationAvailabilityResolver,
)
from ai_rpg_world.application.llm.tool_constants import (
    TOOL_NAME_MOVE_TO_DESTINATION,
    TOOL_NAME_NO_OP,
)

# no_op: パラメータなし
NO_OP_DEFINITION = ToolDefinitionDto(
    name=TOOL_NAME_NO_OP,
    description="何もしない。このターンは行動を起こさず待機します。",
    parameters={"type": "object", "properties": {}, "required": []},
)

# 移動（1 ツール）。内部で SetDestinationCommand を使用。パラメータは同スキーマ。
MOVE_TO_DESTINATION_PARAMETERS = {
    "type": "object",
    "properties": {
        "destination_type": {
            "type": "string",
            "enum": ["spot", "location"],
            "description": "目的地の種類。spot=スポット単位、location=スポット内のロケーションエリア。",
        },
        "target_spot_id": {
            "type": "integer",
            "description": "目的地のスポットID。",
        },
        "target_location_area_id": {
            "type": "integer",
            "description": "destination_type が location のとき必須。ロケーションエリアID。",
        },
    },
    "required": ["destination_type", "target_spot_id"],
}

MOVE_TO_DESTINATION_DEFINITION = ToolDefinitionDto(
    name=TOOL_NAME_MOVE_TO_DESTINATION,
    description="指定した目的地（スポットまたはロケーション）へ移動します。",
    parameters=MOVE_TO_DESTINATION_PARAMETERS,
)


def register_default_tools(registry: IGameToolRegistry) -> None:
    """no_op と move_to_destination をレジストリに登録する。"""
    if not isinstance(registry, IGameToolRegistry):
        raise TypeError("registry must be IGameToolRegistry")
    registry.register(NO_OP_DEFINITION, NoOpAvailabilityResolver())
    registry.register(MOVE_TO_DESTINATION_DEFINITION, SetDestinationAvailabilityResolver())
