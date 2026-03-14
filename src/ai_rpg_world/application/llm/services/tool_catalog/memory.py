"""メモリ・TODO・作業メモ系ツールの定義。"""

from typing import List, Tuple

from ai_rpg_world.application.llm.contracts.dtos import ToolDefinitionDto
from ai_rpg_world.application.llm.contracts.interfaces import IAvailabilityResolver
from ai_rpg_world.application.llm.services.availability_resolvers import (
    MemoryQueryAvailabilityResolver,
    SubagentAvailabilityResolver,
    TodoAddAvailabilityResolver,
    TodoCompleteAvailabilityResolver,
    TodoListAvailabilityResolver,
    WorkingMemoryAppendAvailabilityResolver,
)
from ai_rpg_world.application.llm.tool_constants import (
    TOOL_NAME_MEMORY_QUERY,
    TOOL_NAME_SUBAGENT,
    TOOL_NAME_TODO_ADD,
    TOOL_NAME_TODO_COMPLETE,
    TOOL_NAME_TODO_LIST,
    TOOL_NAME_WORKING_MEMORY_APPEND,
)

MEMORY_QUERY_PARAMETERS = {
    "type": "object",
    "properties": {
        "expr": {
            "type": "string",
            "description": "DSL 式。例: episodic.take(10), facts.take(5), state",
        },
        "output_mode": {
            "type": "string",
            "enum": ["text", "preview", "count", "handle"],
            "description": "出力形式。text=全文, preview=先頭5件, count=件数のみ, handle=サーバ内参照（subagent で再利用可）",
        },
    },
    "required": ["expr"],
}
MEMORY_QUERY_DEFINITION = ToolDefinitionDto(
    name=TOOL_NAME_MEMORY_QUERY,
    description="メモリ変数（episodic, facts, laws, recent_events, state, working_memory）を DSL 式で検索します。",
    parameters=MEMORY_QUERY_PARAMETERS,
)

SUBAGENT_PARAMETERS = {
    "type": "object",
    "properties": {
        "bindings": {
            "type": "object",
            "description": "名前付き入力。各値は DSL 式または handle:h_xxx。例: {\"episodes\": \"episodic.take(20)\"} または {\"episodes\": \"handle:h_abc123\"}",
        },
        "query": {
            "type": "string",
            "description": "自然言語クエリ。bindings のデータを使って要約・教訓を求めます。",
        },
    },
    "required": ["bindings", "query"],
}
SUBAGENT_DEFINITION = ToolDefinitionDto(
    name=TOOL_NAME_SUBAGENT,
    description="絞り込んだメモリを渡し、要約・教訓を取得します（read-only）。",
    parameters=SUBAGENT_PARAMETERS,
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

WORKING_MEMORY_APPEND_PARAMETERS = {
    "type": "object",
    "properties": {
        "text": {"type": "string", "description": "追加するテキスト（仮説・メモなど）"},
    },
    "required": ["text"],
}
WORKING_MEMORY_APPEND_DEFINITION = ToolDefinitionDto(
    name=TOOL_NAME_WORKING_MEMORY_APPEND,
    description="作業メモにテキストを追加します。仮説や中間結論を記録できます。",
    parameters=WORKING_MEMORY_APPEND_PARAMETERS,
)


def get_memory_query_specs() -> List[Tuple[ToolDefinitionDto, IAvailabilityResolver]]:
    """memory_query ツールの (definition, resolver) 一覧を返す。"""
    return [(MEMORY_QUERY_DEFINITION, MemoryQueryAvailabilityResolver())]


def get_subagent_specs() -> List[Tuple[ToolDefinitionDto, IAvailabilityResolver]]:
    """subagent ツールの (definition, resolver) 一覧を返す。"""
    return [(SUBAGENT_DEFINITION, SubagentAvailabilityResolver())]


def get_todo_specs() -> List[Tuple[ToolDefinitionDto, IAvailabilityResolver]]:
    """TODO 系ツールの (definition, resolver) 一覧を返す。"""
    return [
        (TODO_ADD_DEFINITION, TodoAddAvailabilityResolver()),
        (TODO_LIST_DEFINITION, TodoListAvailabilityResolver()),
        (TODO_COMPLETE_DEFINITION, TodoCompleteAvailabilityResolver()),
    ]


def get_working_memory_specs() -> List[Tuple[ToolDefinitionDto, IAvailabilityResolver]]:
    """working_memory_append ツールの (definition, resolver) 一覧を返す。"""
    return [
        (WORKING_MEMORY_APPEND_DEFINITION, WorkingMemoryAppendAvailabilityResolver()),
    ]


def get_memory_specs(
    *,
    memory_query_enabled: bool = False,
    subagent_enabled: bool = False,
    todo_enabled: bool = False,
    working_memory_enabled: bool = False,
) -> List[Tuple[ToolDefinitionDto, IAvailabilityResolver]]:
    """メモリ系ツールの (definition, resolver) 一覧を返す。有効なカテゴリのみ含む。"""
    specs: List[Tuple[ToolDefinitionDto, IAvailabilityResolver]] = []
    if memory_query_enabled:
        specs.extend(get_memory_query_specs())
    if subagent_enabled:
        specs.extend(get_subagent_specs())
    if todo_enabled:
        specs.extend(get_todo_specs())
    if working_memory_enabled:
        specs.extend(get_working_memory_specs())
    return specs


__all__ = [
    "get_memory_specs",
    "get_memory_query_specs",
    "get_subagent_specs",
    "get_todo_specs",
    "get_working_memory_specs",
]
