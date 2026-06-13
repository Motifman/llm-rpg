"""LLM API への口となる Port interface 群。

Issue #470 Phase 1 cleanup: 旧 ``application/llm/contracts/`` 配下に散在していた
LLM Port を本 package に集約。``contracts/`` には domain VO の re-export と
それ以外の interface (Repository / Service contract / DTO) のみが残る。

Port = 外部 LLM API への口 (= application 層の責務)。

NOTE: スケジューリング抽象 ``IEpisodicSubjectiveCompletionScheduler``
(= 「いつ呼ぶか」の制御) は LLM API 口ではないため ``application/llm/scheduler/``
に分離。
"""

from ai_rpg_world.application.llm.ports.episodic_chunk_subjective_completion_port import (
    IEpisodicChunkSubjectiveCompletionPort,
)
from ai_rpg_world.application.llm.ports.episodic_reinterpretation_completion_port import (
    IEpisodicReinterpretationCompletionPort,
)
from ai_rpg_world.application.llm.ports.llm_client_port import ILLMClient
from ai_rpg_world.application.llm.ports.semantic_gist_completion_port import (
    ISemanticGistCompletionPort,
)
from ai_rpg_world.application.llm.ports.short_term_memory_completion_ports import (
    IShortTermMemoryLongSummaryCompletionPort,
    IShortTermMemorySummaryCompletionPort,
)

__all__ = [
    "IEpisodicChunkSubjectiveCompletionPort",
    "IEpisodicReinterpretationCompletionPort",
    "ILLMClient",
    "ISemanticGistCompletionPort",
    "IShortTermMemoryLongSummaryCompletionPort",
    "IShortTermMemorySummaryCompletionPort",
]
