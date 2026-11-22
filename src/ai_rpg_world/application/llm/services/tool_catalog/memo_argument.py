"""環境の tool に付ける、メモ帳を書く引数 ``memo`` (#1628)。"""

from __future__ import annotations

from copy import deepcopy

from ai_rpg_world.application.llm.contracts.dtos import ToolDefinitionDto
from ai_rpg_world.being.application.memo_argument import MEMO_FIELD_NAME, memo_field_property


def with_memo_schema(definition: ToolDefinitionDto, *, episode_source_offered: bool) -> ToolDefinitionDto:
    """省略できる引数として足す。毎回書かせると、書くことが無いターンにも何かを書かせてしまう。"""
    if not isinstance(definition, ToolDefinitionDto):
        raise TypeError("definition must be ToolDefinitionDto")
    parameters = deepcopy(definition.parameters)
    properties = dict(parameters.get("properties") or {})
    properties[MEMO_FIELD_NAME] = memo_field_property(episode_source_offered=episode_source_offered)
    parameters["properties"] = properties
    return ToolDefinitionDto(
        name=definition.name,
        description=definition.description,
        parameters=parameters,
        category=definition.category,
    )


__all__ = ["with_memo_schema"]
