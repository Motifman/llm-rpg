"""発言系ツールの定義（whisper, say）。"""

from typing import List, Tuple

from ai_rpg_world.application.llm.contracts.dtos import ToolDefinitionDto
from ai_rpg_world.application.llm.contracts.interfaces import IAvailabilityResolver
from ai_rpg_world.application.llm.services.availability_resolvers import (
    SayAvailabilityResolver,
    WhisperAvailabilityResolver,
)
from ai_rpg_world.application.llm.tool_constants import TOOL_NAME_SAY, TOOL_NAME_WHISPER

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

SAY_PARAMETERS = {
    "type": "object",
    "properties": {
        "content": {
            "type": "string",
            "description": "周囲に向けて発言する内容。",
        },
    },
    "required": ["content"],
}

SAY_DEFINITION = ToolDefinitionDto(
    name=TOOL_NAME_SAY,
    description="周囲に聞こえるように発言します。",
    parameters=SAY_PARAMETERS,
)


def get_speech_specs() -> List[Tuple[ToolDefinitionDto, IAvailabilityResolver]]:
    """発言系ツールの (definition, resolver) 一覧を返す。"""
    return [
        (WHISPER_DEFINITION, WhisperAvailabilityResolver()),
        (SAY_DEFINITION, SayAvailabilityResolver()),
    ]


__all__ = [
    "get_speech_specs",
    "WHISPER_DEFINITION",
    "SAY_DEFINITION",
]
