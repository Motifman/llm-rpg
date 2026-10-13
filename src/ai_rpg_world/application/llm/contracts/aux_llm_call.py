"""行動を決める呼び出し以外で呼んだ LLM の 1 回ぶんの記録 (#1617)。

行動の呼び出しは ``LlmCallMetrics`` で ``llm_call`` に残る。記憶の部品と Jev は
そこに混ぜない。混ぜると行動の費用と記憶の費用が分けられなくなり、連続失敗で
run を止める監視にも記憶の失敗が数えられてしまう。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Protocol


class AuxLlmComponent(str, Enum):
    """呼び出した部品。report.md はこの単位で費用を分ける。"""

    EPISODE_SUBJECTIVE = "episode_subjective"
    SEMANTIC_GIST = "semantic_gist"
    BELIEF_CONSOLIDATION = "belief_consolidation"
    SHORT_TERM_SUMMARY = "short_term_summary"
    SHORT_TERM_LONG_SUMMARY = "short_term_long_summary"
    EPISODE_WRITING = "episode_writing"
    TYPED_JUDGMENT = "typed_judgment"


@dataclass(frozen=True)
class AuxLlmCall:
    """``None`` は「応答に無かった」。0 と区別するために使う。

    Jev の Decisions endpoint は費用もトークン数も返さない (#1429 で確認)。
    0 で埋めると「無料だった」と読めてしまう。
    """

    component: AuxLlmComponent
    model: str
    wall_latency_ms: int
    success: bool
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    cached_tokens: int | None = None
    cost_usd: float | None = None
    error_code: str | None = None
    question_names: tuple[str, ...] = ()


class AuxLlmCallSink(Protocol):
    def record(self, call: AuxLlmCall) -> None: ...


__all__ = ["AuxLlmCall", "AuxLlmCallSink", "AuxLlmComponent"]
