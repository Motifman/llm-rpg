"""LLM ターン実行で共有する型と定数。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from ai_rpg_world.application.llm.contracts.dtos import LlmCommandResultDto
from ai_rpg_world.domain.player.value_object.player_id import PlayerId

WORLD_ACTION_MOMENTARY_BLANK = "一瞬の空白"
WORLD_RESULT_MOMENTARY_BLANK = "意識が途切れ、この間の自分の行動を思い出せない。"
WORLD_ACTION_HESITATION = "迷い"
WORLD_RESULT_HESITATION = "何をするか決めきれず、時間が過ぎた。"

ACTION_RESULT_TRACE_RESERVED_KEYS = frozenset(
    {
        "tick",
        "player_id",
        "tool",
        "success",
        "error_code",
        "result_summary",
    }
)


def action_result_extra_trace_payload(
    trace_payload: Dict[str, Any] | None,
) -> Dict[str, Any]:
    """tool 側の trace_payload を action_result trace 用に安全化する。

    ``action_result`` trace は tick / player_id / tool などを明示引数で渡す。
    tool 側 payload に同名キーがあると ``record(..., **payload)`` が
    TypeError になり、行全体が消える。元 payload は ``tool_trace_payload``
    にネストして必ず残し、直下には予約名と衝突しないキーだけを互換用に残す。
    """
    raw = dict(trace_payload or {})
    if not raw:
        return {}
    safe = {
        key: value
        for key, value in raw.items()
        if key not in ACTION_RESULT_TRACE_RESERVED_KEYS
        and key != "tool_trace_payload"
    }
    safe["tool_trace_payload"] = raw
    return safe


@dataclass
class LlmPhaseAResult:
    """1 ターンの Phase A (snapshot + LLM 呼び出し) の出力。

    Phase B (tool 実行) の入力として保持する。LLM 呼び出し例外を捕まえた場合は
    ``exception`` に詰め、Phase B 側で LlmCommandResultDto を組み立てる。
    """
    player_id: PlayerId
    prompt: dict
    tools_payload: list
    tool_call: Optional[dict]
    exception: Optional[BaseException]
    llm_call_id: Optional[str] = None
    subjective_overrides: dict[str, Any] = field(default_factory=dict)
    failure_result: Optional[LlmCommandResultDto] = None
    reason_first_turn_id: Optional[str] = None


@dataclass(frozen=True)
class ReasonFirstGateDecision:
    """Phase A 入口で reason-first 2段階を使うかの判定結果。"""

    enabled: bool
    reason: str
