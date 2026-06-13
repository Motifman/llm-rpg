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
from ai_rpg_world.domain.memory.episodic.value_object.subjective_episode import (
    SubjectiveEpisode,
)
# -- end domain re-exports --

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
