"""LLM 向け表示・記憶層の契約"""

from ai_rpg_world.application.llm.contracts.dtos import (
    ActionResultEntry,
    LlmCommandResultDto,
    SystemPromptPlayerInfoDto,
    ToolDefinitionDto,
)

# -- domain VO re-exports: memo (Issue #470 Phase 1 PR3) --
# 旧 ``dtos.py`` から domain に昇格した memo 系 VO を後方互換のため re-export。
# 新規コードは concrete file から import すること:
#     from ai_rpg_world.domain.memory.memo.value_object.memo_entry import MemoEntry
from ai_rpg_world.domain.memory.memo.value_object.memo_entry import (
    MemoEntry,
    TodoEntry,  # 旧名 alias
)
from ai_rpg_world.domain.memory.memo.value_object.memo_fulfillment_context import (
    MemoFulfillmentContext,
)
# -- end memo re-exports --
from ai_rpg_world.domain.memory.episodic.repository.episodic_episode_repository import (
    EpisodicEpisodeRepository,
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

# -- domain VO re-exports: episodic reinterpretation (Issue #470 Phase 1 PR5) --
from ai_rpg_world.domain.memory.episodic.value_object.episodic_recall_observation import (
    EpisodicRecallObservation,
)
from ai_rpg_world.domain.memory.episodic.value_object.episodic_reinterpretation_entry import (
    EpisodicReinterpretationEntry,
)
from ai_rpg_world.domain.memory.episodic.value_object.episodic_reinterpretation_status import (
    EpisodicReinterpretationStatus,
)
# -- domain Repository re-exports: episodic reinterpretation (Issue #470 Phase 1 PR5) --
from ai_rpg_world.domain.memory.episodic.repository.episodic_recall_buffer_repository import (
    EpisodicRecallBufferRepository,
)
from ai_rpg_world.domain.memory.episodic.repository.episodic_reinterpretation_journal_repository import (
    EpisodicReinterpretationJournalRepository,
)
# -- end episodic reinterpretation re-exports --
# -- domain VO re-exports: persona (Issue #470 Phase 1 PR4) --
# 旧 ``persona.py`` から domain に昇格した VO の後方互換 re-export。
# 新規コードは concrete file から import すること:
#     from ai_rpg_world.domain.persona.value_object.agent_persona_dto import AgentPersonaDto
from ai_rpg_world.domain.persona.value_object.agent_persona_dto import AgentPersonaDto
from ai_rpg_world.domain.persona.value_object.persona_prompt_policy import (
    PersonaPromptPolicy,
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
    ISlidingWindowMemory,
    ISystemPromptBuilder,
)
from ai_rpg_world.domain.memory.memo.repository.memo_repository import MemoRepository

__all__ = [
    "ChunkEncodingInput",
    "UnifiedRecentEventLine",
    "build_chunk_encoding_input",
    "chunk_encoding_episode_generation_allowed",
    "format_unified_timeline_as_recent_events_bullets",
    "merge_observations_and_action_results_to_unified_timeline",
    "EpisodicEpisodeRepository",
    "EpisodicCue",
    "EpisodicCueSource",
    "EpisodeAction",
    "EpisodeLocation",
    "EpisodeSource",
    "SubjectiveEpisode",
    "EpisodicRecallObservation",
    "EpisodicReinterpretationEntry",
    "EpisodicReinterpretationStatus",
    "EpisodicRecallBufferRepository",
    "EpisodicReinterpretationJournalRepository",
    "ActionResultEntry",
    "LlmCommandResultDto",
    "SystemPromptPlayerInfoDto",
    "ToolDefinitionDto",
    # memo VO (Issue #470 Phase 1 PR3 で domain に昇格、ここは後方互換 re-export)
    "MemoEntry",
    "MemoFulfillmentContext",
    "TodoEntry",
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
    "ISlidingWindowMemory",
    "ISystemPromptBuilder",
    "MemoRepository",
]
