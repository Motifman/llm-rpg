"""LLM 向け表示・記憶層の契約"""

from ai_rpg_world.application.llm.contracts.dtos import (
    ActionResultEntry,
    LlmCommandResultDto,
    SystemPromptPlayerInfoDto,
    ToolDefinitionDto,
)
from ai_rpg_world.application.llm.contracts.interfaces import (
    IActionResultStore,
    IAvailabilityResolver,
    IAvailableToolsProvider,
    IContextFormatStrategy,
    ICurrentStateFormatter,
    IGameToolRegistry,
    ILLMClient,
    IPromptBuilder,
    IRecentEventsFormatter,
    ISlidingWindowMemory,
    ISystemPromptBuilder,
)

__all__ = [
    "ActionResultEntry",
    "LlmCommandResultDto",
    "SystemPromptPlayerInfoDto",
    "ToolDefinitionDto",
    "IActionResultStore",
    "IAvailabilityResolver",
    "IAvailableToolsProvider",
    "IContextFormatStrategy",
    "ICurrentStateFormatter",
    "IGameToolRegistry",
    "ILLMClient",
    "IPromptBuilder",
    "IRecentEventsFormatter",
    "ISlidingWindowMemory",
    "ISystemPromptBuilder",
]
