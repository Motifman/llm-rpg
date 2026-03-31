"""スポットグラフ用 LLM ツール定義"""

from typing import List, Tuple

from ai_rpg_world.application.llm.contracts.dtos import ToolDefinitionDto
from ai_rpg_world.application.llm.contracts.interfaces import IAvailabilityResolver
from ai_rpg_world.application.llm.services.spot_graph_availability_resolvers import (
    SpotGraphToolsAvailabilityResolver,
)
from ai_rpg_world.application.llm.tool_constants import (
    TOOL_NAME_SPOT_GRAPH_EXPLORE,
    TOOL_NAME_SPOT_GRAPH_INTERACT,
    TOOL_NAME_SPOT_GRAPH_SET_SUB_LOCATION,
    TOOL_NAME_SPOT_GRAPH_TRAVEL_TO,
)

_RESOLVER = SpotGraphToolsAvailabilityResolver()

TRAVEL_TO_DEFINITION = ToolDefinitionDto(
    name=TOOL_NAME_SPOT_GRAPH_TRAVEL_TO,
    description="スポットグラフ上で、指定したスポット ID へ移動を開始する（経路は最短・通行条件を満たす必要がある）。",
    parameters={
        "type": "object",
        "properties": {
            "destination_spot_id": {
                "type": "integer",
                "description": "移動先のスポット ID（現在状態の接続先に表示された ID と一致させる）。",
            },
        },
        "required": ["destination_spot_id"],
    },
)

SET_SUB_LOCATION_DEFINITION = ToolDefinitionDto(
    name=TOOL_NAME_SPOT_GRAPH_SET_SUB_LOCATION,
    description="現在のスポット内のサブロケーションを変更する。省略または 0 で未指定（クリア）扱い。",
    parameters={
        "type": "object",
        "properties": {
            "sub_location_id": {
                "type": "integer",
                "description": "サブロケーション ID。未設定でクリアする場合は 0 または省略。",
            },
        },
        "required": [],
    },
)

EXPLORE_DEFINITION = ToolDefinitionDto(
    name=TOOL_NAME_SPOT_GRAPH_EXPLORE,
    description="現在のスポットを探索する（発見・ドロップ等はシナリオ依存）。",
    parameters={"type": "object", "properties": {}, "required": []},
)

INTERACT_DEFINITION = ToolDefinitionDto(
    name=TOOL_NAME_SPOT_GRAPH_INTERACT,
    description="現在のスポット内のオブジェクトに対し、指定した操作名で相互作用する。",
    parameters={
        "type": "object",
        "properties": {
            "object_id": {
                "type": "integer",
                "description": "スポットオブジェクト ID。",
            },
            "action_name": {
                "type": "string",
                "description": "操作名（オブジェクトに定義された action_name）。",
            },
        },
        "required": ["object_id", "action_name"],
    },
)


def get_spot_graph_specs() -> List[Tuple[ToolDefinitionDto, IAvailabilityResolver]]:
    return [
        (TRAVEL_TO_DEFINITION, _RESOLVER),
        (SET_SUB_LOCATION_DEFINITION, _RESOLVER),
        (EXPLORE_DEFINITION, _RESOLVER),
        (INTERACT_DEFINITION, _RESOLVER),
    ]


__all__ = [
    "get_spot_graph_specs",
    "TRAVEL_TO_DEFINITION",
    "SET_SUB_LOCATION_DEFINITION",
    "EXPLORE_DEFINITION",
    "INTERACT_DEFINITION",
]
