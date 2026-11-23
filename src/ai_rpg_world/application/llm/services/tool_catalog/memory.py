"""エピソード記憶メタツールの定義。"""

from ai_rpg_world.application.llm.contracts.dtos import ToolDefinitionDto
from ai_rpg_world.application.llm.contracts.interfaces import IAvailabilityResolver
from ai_rpg_world.application.llm.contracts.tool_category import ToolCategory
from ai_rpg_world.application.llm.services.availability_resolvers import (
    EpisodeRecallAvailabilityResolver,
)
from ai_rpg_world.application.llm.tool_constants import (
    TOOL_NAME_EPISODE_RECALL,
    TOOL_NAME_EPISODE_REVISE_INDEX,
)
from ai_rpg_world.being.application.episode_index_revision_tool import (
    episode_index_revision_description,
    episode_index_revision_parameters,
)
from ai_rpg_world.being.application.episode_recall_tool import episode_recall_description, episode_recall_parameters


def episode_recall_definition(max_handles: int) -> ToolDefinitionDto:
    """上限 M は profile の値なので、定義もそこから作る (#1623)。"""
    return ToolDefinitionDto(
        name=TOOL_NAME_EPISODE_RECALL,
        description=episode_recall_description(max_handles),
        parameters=episode_recall_parameters(max_handles),
        category=ToolCategory.META_COGNITIVE,
    )


EPISODE_REVISE_INDEX_DEFINITION = ToolDefinitionDto(
    name=TOOL_NAME_EPISODE_REVISE_INDEX,
    description=episode_index_revision_description(),
    parameters=episode_index_revision_parameters(),
    category=ToolCategory.META_COGNITIVE,
)


def get_memory_specs(
    *,
    episode_recall_max_handles: int | None = None,
    episode_index_revision_enabled: bool = False,
) -> list[tuple[ToolDefinitionDto, IAvailabilityResolver]]:
    """目次つきのエピソードの道具を返す。

    ``episode_recall_max_handles`` を渡すと、目次つきのエピソードの呼び出し
    ``episode_recall`` をその上限で出す (#1623)。None なら出さない。
    ``episode_index_revision_enabled`` は、その目次を直す ``episode_revise_index``。
    """
    specs: list[tuple[ToolDefinitionDto, IAvailabilityResolver]] = []
    if episode_recall_max_handles is not None:
        specs.append(
            (
                episode_recall_definition(episode_recall_max_handles),
                EpisodeRecallAvailabilityResolver(),
            )
        )
    if episode_index_revision_enabled:
        specs.append((EPISODE_REVISE_INDEX_DEFINITION, EpisodeRecallAvailabilityResolver()))
    return specs


__all__ = [
    "EPISODE_REVISE_INDEX_DEFINITION",
    "episode_recall_definition",
    "get_memory_specs",
]
