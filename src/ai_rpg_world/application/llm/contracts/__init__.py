"""LLM 向け表示・記憶層の契約"""

from ai_rpg_world.application.llm.contracts.dtos import (
    ActionResultEntry,
    LlmCommandResultDto,
    SystemPromptPlayerInfoDto,
    ToolDefinitionDto,
    TodoEntry,
)
from ai_rpg_world.application.llm.contracts.episodic_episode_store_port import (
    IEpisodicEpisodeStore,
)
from ai_rpg_world.application.llm.contracts.episodic_chunk_subjective_llm_port import (
    IEpisodicChunkSubjectiveCompletionPort,
)
from ai_rpg_world.application.llm.contracts.chunk_encoding import (
    ChunkEncodingInput,
    UnifiedRecentEventLine,
    build_chunk_encoding_input,
    chunk_encoding_episode_generation_allowed,
    format_unified_timeline_as_recent_events_bullets,
    merge_observations_and_action_results_to_unified_timeline,
)
from ai_rpg_world.application.llm.contracts.episodic_memory import (
    EpisodicCue,
    EpisodicCueSource,
    EpisodeAction,
    EpisodeLocation,
    EpisodeSource,
    SubjectiveEpisode,
)
from ai_rpg_world.application.llm.contracts.episodic_reinterpretation import (
    EpisodicRecallObservation,
    EpisodicReinterpretationEntry,
    EpisodicReinterpretationStatus,
    IEpisodicRecallBufferStore,
    IEpisodicReinterpretationCompletionPort,
    IEpisodicReinterpretationJournalStore,
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
    "ChunkEncodingInput",
    "UnifiedRecentEventLine",
    "build_chunk_encoding_input",
    "chunk_encoding_episode_generation_allowed",
    "format_unified_timeline_as_recent_events_bullets",
    "merge_observations_and_action_results_to_unified_timeline",
    "IEpisodicEpisodeStore",
    "IEpisodicChunkSubjectiveCompletionPort",
    "EpisodicCue",
    "EpisodicCueSource",
    "EpisodeAction",
    "EpisodeLocation",
    "EpisodeSource",
    "SubjectiveEpisode",
    "EpisodicRecallObservation",
    "EpisodicReinterpretationEntry",
    "EpisodicReinterpretationStatus",
    "IEpisodicRecallBufferStore",
    "IEpisodicReinterpretationCompletionPort",
    "IEpisodicReinterpretationJournalStore",
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
