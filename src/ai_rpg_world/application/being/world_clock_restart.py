"""回をやり直す読み込みで、前の回の世界の tick を記憶から外す (#1514)。

新しい回の世界の tick は 0 から始まる。snapshot に世界の tick の絶対値が
残ったまま書き戻すと、前の回の tick 90 の記録が新しい回の tick 5 より新しく
見え、想起の枠や余韻が tick 90 を過ぎるまで居座る。負の値にずらす案は、
``GoalEntry`` と ``PendingPrediction`` が負の tick を拒むので採らない。
#1464 で記憶が世界の tick を持たなくなれば、このモジュールは要らなくなる。
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

WORLD_TICK_FIELDS_BY_CODEC: dict[str, frozenset[str]] = {
    "memo_entry_to_dict": frozenset({"added_at_tick"}),
    "_fulfillment_to_dict": frozenset({"completed_at_tick"}),
    "goal_entry_to_dict": frozenset({"created_tick"}),
    "recall_slot_entry_to_dict": frozenset({"entered_tick"}),
    "afterglow_entry_to_dict": frozenset({"entered_tick"}),
    "episode_tick_pair_to_dict": frozenset({"tick"}),
    "belief_evidence_to_dict": frozenset({"tick"}),
    "pending_prediction_to_dict": frozenset({"tick_from", "tick_to", "created_tick"}),
}

_RESET_TO_ROUND_START: dict[str, tuple[tuple[str, ...], ...]] = {
    "memo": (("added_at_tick",), ("fulfillment_context", "completed_at_tick")),
    "goal_journal": (("created_tick",),),
    "belief_evidence_buffer": (("tick",),),
    "recall_slot_entries": (("entered_tick",),),
    "recall_slot_cooldown": (("tick",),),
    "afterglow_entries": (("entered_tick",),),
    "recall_habituation_last_recalled": (("tick",),),
}

# 窓が前の回の世界の時計を指していて、初期状態に戻った世界では判定できない。
_DROPPED_AT_ROUND_START = "pending_predictions"


class WorldClockRestartCoverageError(RuntimeError):
    """書き換えの表に無い欄に、前の回の世界の tick が残っているとき。"""


@dataclass(frozen=True)
class WorldClockRestartReport:
    reset_tick_fields: int
    dropped_pending_predictions: int

    def to_trace_dict(self) -> dict[str, int]:
        return {
            "reset_tick_fields": self.reset_tick_fields,
            "dropped_pending_predictions": self.dropped_pending_predictions,
        }


def restart_world_clock_in_payload(payload_json: str) -> tuple[str, WorldClockRestartReport]:
    payload = json.loads(payload_json)
    reset = 0
    for store_key, paths in _RESET_TO_ROUND_START.items():
        for element in payload.get(store_key, []):
            for path in paths:
                reset += _reset_to_zero(element, path)
    dropped = len(payload.get(_DROPPED_AT_ROUND_START, []))
    if _DROPPED_AT_ROUND_START in payload:
        payload[_DROPPED_AT_ROUND_START] = []
    leftovers = sorted(set(_nonzero_tick_keys(payload)))
    if leftovers:
        raise WorldClockRestartCoverageError(
            "前の回の世界の tick が残っている欄があります。"
            f"world_clock_restart の表に足してください: {leftovers}"
        )
    return json.dumps(payload, ensure_ascii=False), WorldClockRestartReport(
        reset_tick_fields=reset,
        dropped_pending_predictions=dropped,
    )


def _reset_to_zero(element: Any, path: tuple[str, ...]) -> int:
    node = element
    for key in path[:-1]:
        if not isinstance(node, dict):
            return 0
        node = node.get(key)
    if not isinstance(node, dict) or node.get(path[-1]) is None:
        return 0
    node[path[-1]] = 0
    return 1


def _nonzero_tick_keys(node: Any) -> Iterator[str]:
    if isinstance(node, dict):
        for key, value in node.items():
            if "tick" in key and isinstance(value, int) and not isinstance(value, bool) and value != 0:
                yield key
            yield from _nonzero_tick_keys(value)
    elif isinstance(node, list):
        for value in node:
            yield from _nonzero_tick_keys(value)


__all__ = [
    "WORLD_TICK_FIELDS_BY_CODEC",
    "WorldClockRestartCoverageError",
    "WorldClockRestartReport",
    "restart_world_clock_in_payload",
]
