"""世界へ作用する tool 用の主観入力 schema と判定。"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict

from ai_rpg_world.application.llm.contracts.dtos import (
    EMOTION_HINT_VALUES,
    ToolDefinitionDto,
)
from ai_rpg_world.application.llm.tool_constants import (
    TOOL_NAME_NO_OP,
    TOOL_NAME_PREFIX_TODO,
)

SUBJECTIVE_ACTION_FIELDS = (
    "inner_thought",
    "intention",
    "expected_result",
    "attention",
    "emotion_hint",
)

SUBJECTIVE_ACTION_TEXT_FIELDS = (
    "inner_thought",
    "intention",
    "expected_result",
    "attention",
)

SUBJECTIVE_ACTION_FIELD_PROPERTIES: Dict[str, Dict[str, Any]] = {
    "inner_thought": {
        "type": "string",
        "description": (
            "システムメッセージ先頭の【ペルソナ】に揃えた、この行動を選ぶ直前の短い一文。"
            "観測者向けに表示される。未発見の事実を知った体で書かないこと。"
        ),
        "minLength": 1,
        "maxLength": 500,
    },
    "intention": {
        "type": "string",
        "description": "この行動で何を達成したいか。予測結果や感情ではなく、行動目的を書く。",
        "minLength": 1,
        "maxLength": 500,
    },
    "expected_result": {
        "type": "string",
        "description": (
            "この行動をした結果、何が分かる・何が起きると予測しているか。"
            "願望や目的ではなく、行動前の予測を書く。"
        ),
        "minLength": 1,
        "maxLength": 500,
    },
    "attention": {
        "type": "string",
        "description": "現在もっとも注意している対象、手がかり、関係、危険、問いを短く書く。",
        "minLength": 1,
        "maxLength": 500,
    },
    "emotion_hint": {
        "type": "string",
        "description": "行動直前の主要感情。検索・集計しやすい単一ラベルで選ぶ。",
        "enum": list(EMOTION_HINT_VALUES),
    },
}


def is_subjective_action_tool(tool_name: str) -> bool:
    """世界へ作用する主観入力付き tool かどうか。"""

    if not isinstance(tool_name, str):
        return False
    if tool_name == TOOL_NAME_NO_OP:
        return False
    if tool_name.startswith(TOOL_NAME_PREFIX_TODO):
        return False
    return bool(tool_name)


def with_subjective_action_schema(definition: ToolDefinitionDto) -> ToolDefinitionDto:
    """対象 tool の JSON Schema に主観入力を足した定義を返す。"""

    if not isinstance(definition, ToolDefinitionDto):
        raise TypeError("definition must be ToolDefinitionDto")
    if not is_subjective_action_tool(definition.name):
        return definition

    parameters = deepcopy(definition.parameters)
    properties = dict(parameters.get("properties") or {})
    required = list(parameters.get("required") or [])
    for name, prop in SUBJECTIVE_ACTION_FIELD_PROPERTIES.items():
        properties[name] = deepcopy(prop)
        if name not in required:
            required.append(name)
    parameters["properties"] = properties
    parameters["required"] = required
    return ToolDefinitionDto(
        name=definition.name,
        description=definition.description,
        parameters=parameters,
        category=definition.category,
    )
