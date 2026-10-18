"""Being の snapshot の memory payload から、消した部品の欄を捨てる。"""

from __future__ import annotations

import json
from typing import Any

# 消した部品の欄は、拒まずに捨て、捨てた件数を trace に残す。古い snapshot から
# replay / 再開できるようにするため (#1631)。
REMOVED_MEMORY_PAYLOAD_KEYS: tuple[str, ...] = (
    "afterglow_entries",
    "recall_slot_entries",
    "recall_slot_cooldown",
    "recall_habituation_last_recalled",
    "belief_evidence_buffer",
    "belief_evidence_received_event_ids",
    "pending_predictions",
    "memo",
)


def drop_removed_memory_payload_keys(payload_json: str) -> tuple[str, dict[str, int]]:
    try:
        payload = json.loads(payload_json)
    except json.JSONDecodeError:
        # 壊れた payload は、このあと restore が形式の誤りとして止める。
        return payload_json, {}
    if not isinstance(payload, dict):
        return payload_json, {}
    present = [key for key in REMOVED_MEMORY_PAYLOAD_KEYS if key in payload]
    if not present:
        return payload_json, {}
    counts: dict[str, int] = {}
    for key in present:
        value: Any = payload.pop(key)
        count = len(value) if isinstance(value, list) else 1
        # 空の欄は捨てても失うものが無いので、件数に載せない。
        if count:
            counts[key] = count
    return json.dumps(payload, ensure_ascii=False), counts


__all__ = [
    "REMOVED_MEMORY_PAYLOAD_KEYS",
    "drop_removed_memory_payload_keys",
]
