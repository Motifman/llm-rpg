"""追跡系ツールの定義（pursuit_start, pursuit_cancel）。"""

from typing import List, Tuple

from ai_rpg_world.application.llm.contracts.dtos import ToolDefinitionDto
from ai_rpg_world.application.llm.contracts.interfaces import IAvailabilityResolver
from ai_rpg_world.application.llm.services.availability_resolvers import (
    PursuitCancelAvailabilityResolver,
    PursuitStartAvailabilityResolver,
)
from ai_rpg_world.application.llm.tool_constants import (
    TOOL_NAME_PURSUIT_CANCEL,
    TOOL_NAME_PURSUIT_START,
)

PURSUIT_START_PARAMETERS = {
    "type": "object",
    "properties": {
        "target_label": {
            "type": "string",
            "description": "現在の状況に表示されたプレイヤーまたはモンスターのラベル（例: P1, M1）。",
        },
    },
    "required": ["target_label"],
}

PURSUIT_START_DEFINITION = ToolDefinitionDto(
    name=TOOL_NAME_PURSUIT_START,
    description="現在見えているプレイヤーまたはモンスターの追跡を開始します。",
    parameters=PURSUIT_START_PARAMETERS,
)

PURSUIT_CANCEL_DEFINITION = ToolDefinitionDto(
    name=TOOL_NAME_PURSUIT_CANCEL,
    description="現在の追跡を中断します。",
    parameters={"type": "object", "properties": {}, "required": []},
)


def get_pursuit_specs() -> List[Tuple[ToolDefinitionDto, IAvailabilityResolver]]:
    """追跡系ツールの (definition, resolver) 一覧を返す。"""
    return [
        (PURSUIT_START_DEFINITION, PursuitStartAvailabilityResolver()),
        (PURSUIT_CANCEL_DEFINITION, PursuitCancelAvailabilityResolver()),
    ]


__all__ = [
    "get_pursuit_specs",
    "PURSUIT_START_DEFINITION",
    "PURSUIT_CANCEL_DEFINITION",
]
