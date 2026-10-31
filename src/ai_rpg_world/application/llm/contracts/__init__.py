"""LLM 向け表示・記憶層の契約"""

from ai_rpg_world.application.llm.contracts.chunk_encoding import (
    UnifiedRecentEventLine,
    format_unified_timeline_as_recent_events_bullets,
    merge_observations_and_action_results_to_unified_timeline,
)
from ai_rpg_world.application.llm.contracts.dtos import (
    ActionResultEntry,
    LlmCommandResultDto,
    SystemPromptPlayerInfoDto,
    ToolDefinitionDto,
)

# -- end persona re-exports --
from ai_rpg_world.application.llm.contracts.interfaces import (
    IActionResultStore,
    IAvailabilityResolver,
    IAvailableToolsProvider,
    IContextFormatStrategy,
    ICurrentStateFormatter,
    IGameToolRegistry,
    ILLMPlayerResolver,
    ILlmTurnTrigger,
    IPromptBuilder,
    IRecentEventsFormatter,
    ISystemPromptBuilder,
)

# -- end memo re-exports --
# -- domain VO re-exports: persona (Issue #470 Phase 1 PR4) --
# 旧 ``persona.py`` から domain に昇格した VO の後方互換 re-export。
# 新規コードは concrete file から import すること:
#     from ai_rpg_world.domain.persona.value_object.agent_persona_dto import AgentPersonaDto
from ai_rpg_world.domain.persona.value_object.agent_persona_dto import AgentPersonaDto
from ai_rpg_world.domain.persona.value_object.persona_prompt_policy import (
    PersonaPromptPolicy,
)

__all__ = [
    "UnifiedRecentEventLine",
    "format_unified_timeline_as_recent_events_bullets",
    "merge_observations_and_action_results_to_unified_timeline",
    "ActionResultEntry",
    "LlmCommandResultDto",
    "SystemPromptPlayerInfoDto",
    "ToolDefinitionDto",
    "AgentPersonaDto",
    "PersonaPromptPolicy",
    "IActionResultStore",
    "IAvailabilityResolver",
    "IAvailableToolsProvider",
    "IContextFormatStrategy",
    "ICurrentStateFormatter",
    "IGameToolRegistry",
    "ILLMPlayerResolver",
    "ILlmTurnTrigger",
    "IPromptBuilder",
    "IRecentEventsFormatter",
    "ISystemPromptBuilder",
]
