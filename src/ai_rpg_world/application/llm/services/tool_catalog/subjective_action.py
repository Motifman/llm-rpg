"""世界へ作用する tool 用の主観入力 schema と判定。"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from ai_rpg_world.application.llm.contracts.dtos import ToolDefinitionDto
from ai_rpg_world.application.llm.contracts.tool_category import ToolCategory
from ai_rpg_world.application.llm.tool_constants import (
    TOOL_NAME_ASSESS_SITUATION,
)

SUBJECTIVE_ACTION_FIELDS = ("inner_thought",)

SUBJECTIVE_ACTION_TEXT_FIELDS = ("inner_thought",)

REASON_FIRST_ACTION_OWNED_FIELDS = ("inner_thought",)

SUBJECTIVE_ACTION_FIELD_PROPERTIES: dict[str, dict[str, Any]] = {
    "inner_thought": {
        "type": "string",
        "description": (
            "システムメッセージ冒頭の【ペルソナ】に揃えた、この行動を選ぶ直前の "
            "**あなた自身の頭の中の独白** を短い一文で書く。"
            "読者・観測者に見せるための演技や情景描写ではなく、いま頭の中で"
            "実際に考えている言葉そのものを書くこと。未発見の事実を知った体で書かない。"
        ),
        "minLength": 1,
        "maxLength": 500,
    },
}


def assess_situation_definition() -> ToolDefinitionDto:
    """reason-first の評価段階で使う ``assess_situation`` 定義を返す。

    ここでは行動を実行せず、後続の行動 tool が実行を担う。
    """
    properties: dict[str, Any] = {
        "inner_thought": deepcopy(
            SUBJECTIVE_ACTION_FIELD_PROPERTIES["inner_thought"]
        ),
    }
    required = ["inner_thought"]

    return ToolDefinitionDto(
        name=TOOL_NAME_ASSESS_SITUATION,
        description=(
            "行動 tool を呼ぶ前に、現在の状況・失敗履歴・次の方針を短く評価する。"
            "ここでは行動を実行しない。"
        ),
        parameters={
            "type": "object",
            "properties": properties,
            "required": required,
        },
        category=ToolCategory.META_COGNITIVE,
    )


def is_subjective_action_tool(tool_name: str) -> bool:
    """世界へ作用する主観入力付き tool かどうか。"""

    if not isinstance(tool_name, str):
        return False
    return bool(tool_name)


def strip_reason_first_action_subjective_schema(
    definition: ToolDefinitionDto,
) -> ToolDefinitionDto:
    """reason-first の行動段階から step1 所有の主観フィールドだけを外す。

    2 段階ターンでは ``inner_thought`` を ``assess_situation`` で先に生成し、
    行動 tool には書かせない。
    """
    if not isinstance(definition, ToolDefinitionDto):
        raise TypeError("definition must be ToolDefinitionDto")
    parameters = deepcopy(definition.parameters)
    properties = dict(parameters.get("properties") or {})
    for field_name in REASON_FIRST_ACTION_OWNED_FIELDS:
        properties.pop(field_name, None)
    parameters["properties"] = properties
    required = [
        field_name
        for field_name in list(parameters.get("required") or [])
        if field_name not in REASON_FIRST_ACTION_OWNED_FIELDS
    ]
    if required:
        parameters["required"] = required
    else:
        parameters.pop("required", None)
    return ToolDefinitionDto(
        name=definition.name,
        description=definition.description,
        parameters=parameters,
        category=definition.category,
    )


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
