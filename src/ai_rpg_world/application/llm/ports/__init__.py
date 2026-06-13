"""LLM 完了 Port interface 群。

Issue #470 Phase 1 cleanup: 旧 ``application/llm/contracts/`` 配下に散在していた
LLM 完了 Port を本 package に集約。``contracts/`` には domain VO の re-export と
それ以外の interface (Repository / Service contract) のみが残る。

Port = 外部 LLM API への口 (= application 層の責務)。

NOTE: ``contracts/episodic_subjective_scheduler_port.py`` (= スケジューリング抽象
``IEpisodicSubjectiveCompletionScheduler``) は **LLM 完了 Port ではなく** scheduler
抽象なので本 package の管轄外。A3 (Phase 1 cleanup) で別途配置を検討する。
"""

from ai_rpg_world.application.llm.ports.episodic_chunk_subjective_completion_port import (
    IEpisodicChunkSubjectiveCompletionPort,
)
from ai_rpg_world.application.llm.ports.episodic_reinterpretation_completion_port import (
    IEpisodicReinterpretationCompletionPort,
)
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
    "ISemanticGistCompletionPort",
    "IShortTermMemoryLongSummaryCompletionPort",
    "IShortTermMemorySummaryCompletionPort",
]
