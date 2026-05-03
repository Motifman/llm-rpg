"""LLM 向け表示・記憶層の契約"""

from ai_rpg_world.application.llm.contracts.dtos import (
    ActionResultEntry,
    LlmCommandResultDto,
    SystemPromptPlayerInfoDto,
    ToolDefinitionDto,
    TodoEntry,
)
from ai_rpg_world.application.llm.contracts.persona import (
    AgentPersonaDto,
    PersonaPromptPolicy,
)
from ai_rpg_world.application.llm.contracts.interfaces import (
    IActionResultStore,
    IAvailabilityResolver,
    IAvailableToolsProvider,
    IContextFormatStrategy,
    ICurrentStateFormatter,
    IGameToolRegistry,
    ILLMClient,
    ILLMPlayerResolver,
    ILlmTurnTrigger,
    IPromptBuilder,
    IRecentEventsFormatter,
    ISlidingWindowMemory,
    ISystemPromptBuilder,
    ITodoStore,
)

__all__ = [
    "ActionResultEntry",
    "LlmCommandResultDto",
    "SystemPromptPlayerInfoDto",
    "ToolDefinitionDto",
    "TodoEntry",
    "AgentPersonaDto",
    "PersonaPromptPolicy",
    "IActionResultStore",
    "IAvailabilityResolver",
    "IAvailableToolsProvider",
    "IContextFormatStrategy",
    "ICurrentStateFormatter",
    "IGameToolRegistry",
    "ILLMClient",
    "ILLMPlayerResolver",
    "ILlmTurnTrigger",
    "IPromptBuilder",
    "IRecentEventsFormatter",
    "ISlidingWindowMemory",
    "ISystemPromptBuilder",
    "ITodoStore",
]
