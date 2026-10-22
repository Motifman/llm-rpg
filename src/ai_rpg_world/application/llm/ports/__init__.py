"""LLM API との境界となる Port interface 群。

Issue #470 Phase 1 cleanup: 旧 ``application/llm/contracts/`` 配下に散在していた
LLM Port を本 package に集約。``contracts/`` には domain VO の re-export と
それ以外の interface (Repository / Service contract / DTO) のみが残る。

Port = 外部 LLM API との境界 (= application 層の責務)。
"""

from ai_rpg_world.application.llm.ports.llm_client_port import ILLMClient
from ai_rpg_world.application.llm.ports.short_term_memory_completion_ports import (
    IShortTermMemorySummaryCompletionPort,
)
from ai_rpg_world.application.llm.ports.typed_judgment_port import (
    ChoiceQuestion,
    ITypedJudgmentPort,
    JudgmentResult,
    JudgmentSource,
    NoulQuestion,
    Question,
    ScoreQuestion,
    TypedJudgmentUnavailableException,
)

__all__ = [
    "ChoiceQuestion",
    "ILLMClient",
    "IShortTermMemorySummaryCompletionPort",
    "ITypedJudgmentPort",
    "JudgmentResult",
    "JudgmentSource",
    "NoulQuestion",
    "Question",
    "ScoreQuestion",
    "TypedJudgmentUnavailableException",
]
