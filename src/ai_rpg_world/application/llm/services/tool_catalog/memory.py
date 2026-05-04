"""TODO 系およびエピソード記憶メタツールの定義。"""

from typing import List, Tuple

from ai_rpg_world.application.llm.contracts.dtos import ToolDefinitionDto
from ai_rpg_world.application.llm.contracts.interfaces import IAvailabilityResolver
from ai_rpg_world.application.llm.contracts.tool_category import ToolCategory
from ai_rpg_world.application.llm.services.availability_resolvers import (
    MemoryExploreRelatedAvailabilityResolver,
    TodoAddAvailabilityResolver,
    TodoCompleteAvailabilityResolver,
    TodoListAvailabilityResolver,
)
from ai_rpg_world.application.llm.tool_constants import (
    TOOL_NAME_MEMORY_EXPLORE_RELATED,
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
    category=ToolCategory.AUXILIARY,
)

TODO_LIST_DEFINITION = ToolDefinitionDto(
    name=TOOL_NAME_TODO_LIST,
    description="未完了の TODO 一覧を取得します。",
    parameters={"type": "object", "properties": {}, "required": []},
    category=ToolCategory.AUXILIARY,
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
    category=ToolCategory.AUXILIARY,
)

MEMORY_EXPLORE_RELATED_PARAMETERS = {
    "type": "object",
    "properties": {
        "episode_id": {
            "type": "string",
            "description": "起点となる主観エピソード ID",
        },
        "top_k": {
            "type": "integer",
            "description": "返す隣接エピソードの最大件数（既定 5、最大 64）",
        },
    },
    "required": ["episode_id"],
}

MEMORY_EXPLORE_RELATED_DEFINITION = ToolDefinitionDto(
    name=TOOL_NAME_MEMORY_EXPLORE_RELATED,
    description=(
        "リンクされた関連エピソード記憶を列挙します。"
        "結果はプロンプト文脈向けの JSON であり、世界状態は変えません。"
    ),
    parameters=MEMORY_EXPLORE_RELATED_PARAMETERS,
    category=ToolCategory.META_COGNITIVE,
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
    episodic_explore_related_enabled: bool = False,
) -> List[Tuple[ToolDefinitionDto, IAvailabilityResolver]]:
    """TODO および任意で memory_explore_related を返す。"""
    specs: List[Tuple[ToolDefinitionDto, IAvailabilityResolver]] = []
    if todo_enabled:
        specs.extend(get_todo_specs())
    if episodic_explore_related_enabled:
        specs.append(
            (MEMORY_EXPLORE_RELATED_DEFINITION, MemoryExploreRelatedAvailabilityResolver())
        )
    return specs


__all__ = [
    "MEMORY_EXPLORE_RELATED_DEFINITION",
    "get_memory_specs",
    "get_todo_specs",
]
