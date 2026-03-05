"""ツールレジストリのデフォルト実装"""

from typing import List, Tuple

from ai_rpg_world.application.llm.contracts.dtos import ToolDefinitionDto
from ai_rpg_world.application.llm.contracts.interfaces import (
    IAvailabilityResolver,
    IGameToolRegistry,
)


class DefaultGameToolRegistry(IGameToolRegistry):
    """ツール定義とリゾルバをメモリで保持するレジストリ。"""

    def __init__(self) -> None:
        self._entries: List[Tuple[ToolDefinitionDto, IAvailabilityResolver]] = []

    def register(
        self,
        definition: ToolDefinitionDto,
        resolver: IAvailabilityResolver,
    ) -> None:
        if not isinstance(definition, ToolDefinitionDto):
            raise TypeError("definition must be ToolDefinitionDto")
        if not isinstance(resolver, IAvailabilityResolver):
            raise TypeError("resolver must be IAvailabilityResolver")
        self._entries.append((definition, resolver))

    def get_definitions_with_resolvers(
        self,
    ) -> List[Tuple[ToolDefinitionDto, IAvailabilityResolver]]:
        return list(self._entries)
