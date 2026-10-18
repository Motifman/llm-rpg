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
    IShortTermMemory,
    ISystemPromptBuilder,
)

# -- end memo re-exports --
from ai_rpg_world.domain.memory.episodic.repository.episodic_episode_repository import (
    EpisodicEpisodeRepository,
)

# -- domain VO re-exports (Issue #470 Phase 1 PR2) --
# 旧 ``application/llm/contracts/episodic_memory.py`` から domain に昇格した
# Value Object 群を、既存 import パターン互換のため本 __init__ で re-export する。
# 新規コードは concrete file から直接 import すること:
#     from ai_rpg_world.domain.memory.episodic.value_object.subjective_episode import SubjectiveEpisode
from ai_rpg_world.domain.memory.episodic.value_object.episode_action import EpisodeAction
from ai_rpg_world.domain.memory.episodic.value_object.episode_location import (
    EpisodeLocation,
)
from ai_rpg_world.domain.memory.episodic.value_object.episode_source import EpisodeSource
from ai_rpg_world.domain.memory.episodic.value_object.episodic_cue import EpisodicCue
from ai_rpg_world.domain.memory.episodic.value_object.episodic_cue_source import (
    EpisodicCueSource,
)

# -- end domain re-exports --
from ai_rpg_world.domain.memory.episodic.value_object.subjective_episode import (
    SubjectiveEpisode,
)

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
    "EpisodicEpisodeRepository",
    "EpisodicCue",
    "EpisodicCueSource",
    "EpisodeAction",
    "EpisodeLocation",
    "EpisodeSource",
    "SubjectiveEpisode",
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
    "IShortTermMemory",
    "ISystemPromptBuilder",
]
