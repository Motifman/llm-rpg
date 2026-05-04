"""スポットグラフ用 LLM ツール定義"""

from typing import List, Tuple

from ai_rpg_world.application.llm.contracts.dtos import ToolDefinitionDto
from ai_rpg_world.application.llm.contracts.interfaces import IAvailabilityResolver
from ai_rpg_world.application.llm.services.spot_graph_availability_resolvers import (
    SpotGraphToolsAvailabilityResolver,
)
from ai_rpg_world.application.llm.services.tool_catalog.inner_thought import (
    inner_thought_property,
)
from ai_rpg_world.application.llm.tool_constants import (
    TOOL_NAME_SAY,
    TOOL_NAME_SPOT_GRAPH_EXPLORE,
    TOOL_NAME_SPOT_GRAPH_INTERACT,
    TOOL_NAME_SPOT_GRAPH_PREPARE_ACTION,
    TOOL_NAME_SPOT_GRAPH_SET_SUB_LOCATION,
    TOOL_NAME_SPOT_GRAPH_TRAVEL_TO,
    TOOL_NAME_SPOT_GRAPH_WAIT,
    TOOL_NAME_WHISPER,
)

_RESOLVER = SpotGraphToolsAvailabilityResolver()
_IT = inner_thought_property()

TRAVEL_TO_DEFINITION = ToolDefinitionDto(
    name=TOOL_NAME_SPOT_GRAPH_TRAVEL_TO,
    description="スポットグラフ上で、指定した接続先ラベルへ移動を開始する（経路は最短・通行条件を満たす必要がある）。",
    parameters={
        "type": "object",
        "properties": {
            "destination_label": {
                "type": "string",
                "description": "接続先ラベル（現在の状況に表示された S1, S2 等）。",
            },
            "inner_thought": _IT,
        },
        "required": ["destination_label", "inner_thought"],
    },
)

SET_SUB_LOCATION_DEFINITION = ToolDefinitionDto(
    name=TOOL_NAME_SPOT_GRAPH_SET_SUB_LOCATION,
    description="現在のスポット内のサブロケーションを変更する。",
    parameters={
        "type": "object",
        "properties": {
            "sub_location_label": {
                "type": "string",
                "description": "サブロケーションラベル（現在の状況に表示された SL1, SL2 等）。未指定でクリア。",
            },
            "inner_thought": _IT,
        },
        "required": ["inner_thought"],
    },
)

EXPLORE_DEFINITION = ToolDefinitionDto(
    name=TOOL_NAME_SPOT_GRAPH_EXPLORE,
    description="現在のスポットを探索する（発見・ドロップ等はシナリオ依存）。",
    parameters={
        "type": "object",
        "properties": {
            "inner_thought": _IT,
        },
        "required": ["inner_thought"],
    },
)

INTERACT_DEFINITION = ToolDefinitionDto(
    name=TOOL_NAME_SPOT_GRAPH_INTERACT,
    description="現在のスポット内のオブジェクトに対し、指定した操作名で相互作用する。パズル操作の場合はparametersに入力値を指定する。",
    parameters={
        "type": "object",
        "properties": {
            "object_label": {
                "type": "string",
                "description": "オブジェクトラベル（現在の状況に表示された OBJ1, OBJ2 等）。",
            },
            "action_name": {
                "type": "string",
                "description": "操作名（オブジェクトに定義された action_name）。",
            },
            "parameters": {
                "type": "object",
                "description": "パズル入力等の追加パラメータ（例: {\"code\": \"1234\"}）。パズルでない操作では省略可。",
            },
            "inner_thought": _IT,
        },
        "required": ["object_label", "action_name", "inner_thought"],
    },
)

WAIT_DEFINITION = ToolDefinitionDto(
    name=TOOL_NAME_SPOT_GRAPH_WAIT,
    description="その場で短く待機し、時間経過に伴う環境変化や出来事を観測する。",
    parameters={
        "type": "object",
        "properties": {
            "reason": {
                "type": "string",
                "description": "待機する理由（任意）。",
            },
            "inner_thought": _IT,
        },
        "required": ["inner_thought"],
    },
)


SAY_DEFINITION = ToolDefinitionDto(
    name=TOOL_NAME_SAY,
    description="周囲に聞こえるように発言する。同じスポットにいる全員と、音が通る接続先にも届く。",
    parameters={
        "type": "object",
        "properties": {
            "content": {
                "type": "string",
                "description": "発言する内容。",
            },
            "inner_thought": _IT,
        },
        "required": ["content", "inner_thought"],
    },
)

WHISPER_DEFINITION = ToolDefinitionDto(
    name=TOOL_NAME_WHISPER,
    description="同じスポットにいる特定のプレイヤーにだけ囁く。",
    parameters={
        "type": "object",
        "properties": {
            "target_label": {
                "type": "string",
                "description": "同じ場所にいるプレイヤーラベル（P1, P2 等）。",
            },
            "content": {
                "type": "string",
                "description": "囁く内容。",
            },
            "inner_thought": _IT,
        },
        "required": ["target_label", "content", "inner_thought"],
    },
)


PREPARE_ACTION_DEFINITION = ToolDefinitionDto(
    name=TOOL_NAME_SPOT_GRAPH_PREPARE_ACTION,
    description="協力アクションの準備をする。他のプレイヤーが対応するアクションを実行できるようになる。例えば、ドアを支える準備をすることで他のプレイヤーがそのドアを通れるようになる。",
    parameters={
        "type": "object",
        "properties": {
            "action_id": {
                "type": "string",
                "description": "準備するアクションID（操作対象に表示される協力アクション名）。",
            },
            "inner_thought": _IT,
        },
        "required": ["action_id", "inner_thought"],
    },
)


def get_spot_graph_specs() -> List[Tuple[ToolDefinitionDto, IAvailabilityResolver]]:
    return [
        (TRAVEL_TO_DEFINITION, _RESOLVER),
        (SET_SUB_LOCATION_DEFINITION, _RESOLVER),
        (EXPLORE_DEFINITION, _RESOLVER),
        (INTERACT_DEFINITION, _RESOLVER),
        (PREPARE_ACTION_DEFINITION, _RESOLVER),
        (WAIT_DEFINITION, _RESOLVER),
        (SAY_DEFINITION, _RESOLVER),
        (WHISPER_DEFINITION, _RESOLVER),
    ]


__all__ = [
    "get_spot_graph_specs",
    "TRAVEL_TO_DEFINITION",
    "SET_SUB_LOCATION_DEFINITION",
    "EXPLORE_DEFINITION",
    "INTERACT_DEFINITION",
    "PREPARE_ACTION_DEFINITION",
    "WAIT_DEFINITION",
    "SAY_DEFINITION",
    "WHISPER_DEFINITION",
]
