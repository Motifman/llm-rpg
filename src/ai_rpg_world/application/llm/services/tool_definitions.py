"""LLM ツールの定義（名前・説明・parameters スキーマ）とデフォルト登録"""

from ai_rpg_world.application.llm.contracts.dtos import ToolDefinitionDto
from ai_rpg_world.application.llm.contracts.interfaces import IGameToolRegistry
from ai_rpg_world.application.llm.services.availability_resolvers import (
    NoOpAvailabilityResolver,
    SetDestinationAvailabilityResolver,
    WhisperAvailabilityResolver,
)
from ai_rpg_world.application.llm.tool_constants import (
    TOOL_NAME_MOVE_TO_DESTINATION,
    TOOL_NAME_NO_OP,
    TOOL_NAME_WHISPER,
)

# no_op: パラメータなし
NO_OP_DEFINITION = ToolDefinitionDto(
    name=TOOL_NAME_NO_OP,
    description="何もしない。このターンは行動を起こさず待機します。",
    parameters={"type": "object", "properties": {}, "required": []},
)

# 移動（1 ツール）。内部では destination_label を runtime context で既存の destination args に解決する。
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
    description="指定した目的地（スポットまたはロケーション）へ移動します。",
    parameters=MOVE_TO_DESTINATION_PARAMETERS,
)

WHISPER_PARAMETERS = {
    "type": "object",
    "properties": {
        "target_label": {
            "type": "string",
            "description": "現在の状況に表示されたプレイヤーラベル（例: P1）。",
        },
        "content": {
            "type": "string",
            "description": "囁く内容。",
        },
    },
    "required": ["target_label", "content"],
}

WHISPER_DEFINITION = ToolDefinitionDto(
    name=TOOL_NAME_WHISPER,
    description="視界内の特定プレイヤーにだけ囁きを送ります。",
    parameters=WHISPER_PARAMETERS,
)


def register_default_tools(
    registry: IGameToolRegistry,
    *,
    speech_enabled: bool = False,
) -> None:
    """no_op と move_to_destination を登録し、必要なら whisper も追加する。"""
    if not isinstance(registry, IGameToolRegistry):
        raise TypeError("registry must be IGameToolRegistry")
    registry.register(NO_OP_DEFINITION, NoOpAvailabilityResolver())
    registry.register(MOVE_TO_DESTINATION_DEFINITION, SetDestinationAvailabilityResolver())
    if speech_enabled:
        registry.register(WHISPER_DEFINITION, WhisperAvailabilityResolver())
