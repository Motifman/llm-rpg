"""ゲームの 1 ターンで、環境の tool に書かれた引数 ``memo`` をメモ帳に当てる (#1628)。"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from ai_rpg_world.application.llm.services.memo_arguments import (
    feedback_text,
    read_memo_operations,
    rejection_text,
)
from ai_rpg_world.application.llm.services.tool_catalog.memo_argument import (
    MEMO_FIELD_NAME,
)
from ai_rpg_world.application.trace import TraceEventKind
from ai_rpg_world.being.application.memo_writing import (
    AddMemo,
    EditMemo,
    MemoOperation,
    apply_memo_operations,
)
from ai_rpg_world.being.domain.memo_book import Memo
from ai_rpg_world.domain.player.value_object.player_id import PlayerId

if TYPE_CHECKING:
    from ai_rpg_world.application.llm.services.world_llm_turn.wiring import (
        WorldLlmWiring,
    )

logger = logging.getLogger(__name__)


#: 書き込みの途中で失敗したときに本人へ返す文。返さないと、書けたと思い込んだまま進む。
WRITING_FAILED_TEXT = "メモ帳に書けませんでした。もう一度書いてください。"


@dataclass(frozen=True)
class MemoCallOutcome:
    """``feedback`` は結果の文の末尾に足す文で、無ければ空文字。"""

    feedback: str = ""
    added_memo_ids: frozenset[str] = frozenset()


def apply_memo_from_call(
    wiring: WorldLlmWiring,
    player_id: PlayerId,
    *,
    tool_name: str,
    arguments: Mapping[str, Any],
    tools_payload: Any,
) -> MemoCallOutcome:
    """引数 ``memo`` を付けて送った tool の呼び出しだけを読む。行動の成否は問わない。

    メモは本人が書いたものなので、行動が断られても書いた事実は残す。
    読み取りや書き込みの失敗で行動を止めない。本人に返し、理由を trace に残す。
    """
    if not _offered_with_memo(tools_payload, tool_name):
        return MemoCallOutcome()
    runtime = wiring.runtime
    trace: dict[str, Any] = {
        "being_id": None,
        "turn": None,
        "tool": tool_name,
        "environment_name": None,
        "applied": [],
        "rejected": [],
        "skipped_reason": None,
        "error": None,
    }
    feedback: list[tuple[int | None, str]] = []
    added: frozenset[str] = frozenset()
    try:
        read = read_memo_operations(
            arguments, episode_source_offered=runtime.memo_episode_source_offered()
        )
        if not read.present:
            return MemoCallOutcome()
        for rejected in read.rejected:
            trace["rejected"].append(
                {"index": rejected.index, "reason": rejected.reason, "raw": rejected.raw, "detail": None}
            )
            feedback.append((rejected.index, rejection_text(rejected.reason)))
        acting = runtime._acting_being_for(player_id)
        if acting is None:
            trace["skipped_reason"] = "no_acting_being"
            return MemoCallOutcome(feedback=feedback_text([(None, WRITING_FAILED_TEXT)]))
        being_id = acting.being_id
        trace["being_id"] = being_id.value
        turn = runtime._memory_turn_clock.current_turn(being_id)
        trace["turn"] = turn
        environment_name = runtime.environment_name_for(player_id)
        trace["environment_name"] = environment_name
        store = runtime._being_memo_store
        outcome = apply_memo_operations(
            store.get(being_id),
            read.operations,
            turn=turn,
            environment_name=environment_name,
            new_memo_id=lambda: str(uuid.uuid4()),
            known_episode_handles=_episode_handles(runtime, being_id),
        )
        store.save(being_id, outcome.book)
        trace["applied"] = [
            _applied_payload(a.index, a.operation, a.memo) for a in outcome.applied
        ]
        added = frozenset(
            a.memo.memo_id for a in outcome.applied if isinstance(a.operation, AddMemo)
        )
        for r in outcome.rejected:
            trace["rejected"].append(
                {"index": r.index, "reason": r.reason, "raw": arguments[MEMO_FIELD_NAME][r.index], "detail": r.detail}
            )
            feedback.append((r.index, rejection_text(r.reason, kind=r.kind, detail=r.detail)))
    except Exception as exc:
        logger.exception("memo writing failed for player=%s", player_id.value)
        trace["skipped_reason"] = "writing_failed"
        trace["error"] = f"{type(exc).__name__}: {exc}"
        return MemoCallOutcome(feedback=feedback_text([(None, WRITING_FAILED_TEXT)]))
    finally:
        _record(runtime, player_id, trace)
    feedback.sort(key=lambda item: -1 if item[0] is None else item[0])
    return MemoCallOutcome(feedback=feedback_text(feedback), added_memo_ids=added)


def _episode_handles(runtime: Any, being_id: Any) -> frozenset[str]:
    if not runtime.memo_episode_source_offered():
        return frozenset()
    return frozenset(e.handle for e in runtime._being_episode_store.list_by_being(being_id))


def _applied_payload(index: int, operation: MemoOperation, memo: Memo) -> dict[str, Any]:
    do = "add" if isinstance(operation, AddMemo) else "edit" if isinstance(operation, EditMemo) else "remove"
    provenance = memo.provenance
    return {
        "index": index,
        "do": do,
        "handle": memo.handle,
        "kind": memo.kind.value,
        "text": memo.text,
        "provenance": None
        if provenance is None
        else {
            "source": provenance.source.value,
            "certainty": provenance.certainty.value,
            "from": provenance.source_from,
        },
    }


def _offered_with_memo(tools_payload: Any, name: str) -> bool:
    for tool in tools_payload or ():
        function = tool.get("function") if isinstance(tool, dict) else None
        if not isinstance(function, dict) or function.get("name") != name:
            continue
        parameters = function.get("parameters")
        properties = parameters.get("properties") if isinstance(parameters, dict) else None
        return isinstance(properties, dict) and MEMO_FIELD_NAME in properties
    return False


def _record(runtime: Any, player_id: PlayerId, payload: dict[str, Any]) -> None:
    recorder = getattr(runtime, "trace_recorder", None)
    if recorder is None:
        return
    try:
        tick = runtime.current_tick()
    except Exception:
        tick = None
    try:
        recorder.record(TraceEventKind.BEING_MEMO, tick=tick, player_id=player_id.value, **payload)
    except Exception:
        logger.exception("trace_recorder.record(%s) failed", TraceEventKind.BEING_MEMO)


__all__ = ["WRITING_FAILED_TEXT", "MemoCallOutcome", "apply_memo_from_call"]
