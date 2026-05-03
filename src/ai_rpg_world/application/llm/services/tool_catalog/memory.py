"""TODO 系ツールの定義。

履歴・想起・長期記憶系ツールは削除済み。プロンプトへ入る過去文脈は
SlidingWindow の直近観測だけに限定する。
"""

from typing import List, Tuple

from ai_rpg_world.application.llm.contracts.dtos import ToolDefinitionDto
from ai_rpg_world.application.llm.contracts.interfaces import IAvailabilityResolver
from ai_rpg_world.application.llm.services.availability_resolvers import (
    TodoAddAvailabilityResolver,
    TodoCompleteAvailabilityResolver,
    TodoListAvailabilityResolver,
)
from ai_rpg_world.application.llm.tool_constants import (
    TOOL_NAME_TODO_ADD,
    TOOL_NAME_TODO_COMPLETE,
    TOOL_NAME_TODO_LIST,
)

TODO_ADD_PARAMETERS = {
    "type": "object",
    "properties": {
        "content": {"type": "string", "description": "TODO の内容"},
    },
    "required": ["content"],
}
TODO_ADD_DEFINITION = ToolDefinitionDto(
    name=TOOL_NAME_TODO_ADD,
    description="TODO を追加します。",
    parameters=TODO_ADD_PARAMETERS,
)

TODO_LIST_DEFINITION = ToolDefinitionDto(
    name=TOOL_NAME_TODO_LIST,
    description="未完了の TODO 一覧を取得します。",
    parameters={"type": "object", "properties": {}, "required": []},
)

TODO_COMPLETE_PARAMETERS = {
    "type": "object",
    "properties": {
        "todo_id": {"type": "string", "description": "完了する TODO の ID"},
    },
    "required": ["todo_id"],
}
TODO_COMPLETE_DEFINITION = ToolDefinitionDto(
    name=TOOL_NAME_TODO_COMPLETE,
    description="指定した TODO を完了にします。",
    parameters=TODO_COMPLETE_PARAMETERS,
)


def get_todo_specs() -> List[Tuple[ToolDefinitionDto, IAvailabilityResolver]]:
    """TODO 系ツールの (definition, resolver) 一覧を返す。"""
    return [
        (TODO_ADD_DEFINITION, TodoAddAvailabilityResolver()),
        (TODO_LIST_DEFINITION, TodoListAvailabilityResolver()),
        (TODO_COMPLETE_DEFINITION, TodoCompleteAvailabilityResolver()),
    ]


def get_memory_specs(
    *,
    todo_enabled: bool = False,
) -> List[Tuple[ToolDefinitionDto, IAvailabilityResolver]]:
    """旧 memory カタログ名を残し、TODO 系だけを返す。"""
    return get_todo_specs() if todo_enabled else []


__all__ = [
    "get_memory_specs",
    "get_todo_specs",
]
