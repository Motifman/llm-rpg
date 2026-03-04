"""利用可能ツール取得のデフォルト実装"""

from typing import Any, Dict, List, Optional

from ai_rpg_world.application.llm.contracts.interfaces import (
    IAvailableToolsProvider,
    IGameToolRegistry,
)
from ai_rpg_world.application.world.contracts.dtos import PlayerCurrentStateDto


def _to_openai_tool(definition: Any) -> Dict[str, Any]:
    """ToolDefinitionDto を OpenAI の tools 要素の形式に変換する。"""
    return {
        "type": "function",
        "function": {
            "name": definition.name,
            "description": definition.description,
            "parameters": {
                "type": "object",
                "properties": definition.parameters.get("properties", {}),
                "required": definition.parameters.get("required", []),
            },
        },
    }


class DefaultAvailableToolsProvider(IAvailableToolsProvider):
    """レジストリとコンテキストから利用可能なツールだけを OpenAI 形式で返す。"""

    def __init__(self, registry: IGameToolRegistry) -> None:
        if not isinstance(registry, IGameToolRegistry):
            raise TypeError("registry must be IGameToolRegistry")
        self._registry = registry

    def get_available_tools(
        self,
        context: Optional[PlayerCurrentStateDto],
    ) -> List[Dict[str, Any]]:
        result: List[Dict[str, Any]] = []
        for definition, resolver in self._registry.get_definitions_with_resolvers():
            if resolver.is_available(context):
                result.append(_to_openai_tool(definition))
        return result
